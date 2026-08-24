"""F004 canonical Monster profile registry contracts."""

import ast
from pathlib import Path

import pytest

from monster_identity import (
    CANONICAL_BATTLEFIELD_IDENTITY_SPECS,
    ENCOUNTER_CLASS_BATTLEFIELD_BOSS,
    ENCOUNTER_CLASS_NORMAL,
    MonsterIdentityRegistry,
    build_battlefield_identity_registry,
)
from monster_profiles import (
    CANONICAL_MONSTER_PROFILE_REGISTRY,
    CANONICAL_PROFILE_COUNT,
    build_canonical_monster_profile_registry,
    get_monster_profile,
    get_stat_profile,
)


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
PROFILE_SOURCE = (ROOT / "monster_profiles.py").read_text(encoding="utf-8")


def _literal_assignment(name):
    tree = ast.parse(APP_SOURCE)
    node = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    )
    return ast.literal_eval(node.value)


ROSTER = _literal_assignment("_BATTLEFIELD_ROSTER")
IDENTITIES = build_battlefield_identity_registry(ROSTER).entries


def test_all_f003_identities_have_exactly_one_profile():
    registry = CANONICAL_MONSTER_PROFILE_REGISTRY

    assert CANONICAL_PROFILE_COUNT == 20
    assert len(registry.profiles) == 20
    assert len(registry.by_id) == 20
    assert [profile.monster_id for profile in registry.profiles] == [
        identity.monster_id for identity in IDENTITIES
    ]
    assert [profile.roster_slot for profile in registry.profiles] == list(range(1, 21))
    assert set(registry.by_roster_slot) == set(range(1, 21))
    assert set(registry.by_id) == {
        f"legacy_bf_{zone:02d}_{kind}"
        for zone in range(1, 11)
        for kind in ("normal", "boss")
    }


def test_profile_contract_and_encounter_class_counts():
    profiles = CANONICAL_MONSTER_PROFILE_REGISTRY.profiles

    assert all(profile.enabled is True for profile in profiles)
    assert all(profile.roster_slot >= 1 for profile in profiles)
    assert all(profile.zone_key.startswith("zone_") for profile in profiles)
    assert all(profile.display_key.startswith("monster.battlefield.") for profile in profiles)
    assert all(profile.taxonomy_family for profile in profiles)
    assert all(profile.stat_profile_id.startswith("stat_") for profile in profiles)
    assert all(profile.drop_profile_id.startswith("drop_legacy_") for profile in profiles)
    assert all(profile.reward_profile_id == "reward_battlefield_legacy" for profile in profiles)
    assert all(profile.presentation_profile_id.startswith("presentation_") for profile in profiles)
    assert sum(profile.encounter_class == ENCOUNTER_CLASS_NORMAL for profile in profiles) == 10
    assert sum(
        profile.encounter_class == ENCOUNTER_CLASS_BATTLEFIELD_BOSS
        for profile in profiles
    ) == 10


def test_current_hp_and_attack_values_are_preserved_exactly():
    registry = CANONICAL_MONSTER_PROFILE_REGISTRY

    for identity, roster_entry in zip(IDENTITIES, ROSTER):
        profile = registry.by_id[identity.monster_id]
        stat = get_stat_profile(profile.stat_profile_id)
        assert stat is not None
        assert (stat.max_hp, stat.attack) == (roster_entry[2], roster_entry[3])


def test_profile_references_are_truthful_legacy_adapters_not_new_drop_or_reward_runtime():
    registry = CANONICAL_MONSTER_PROFILE_REGISTRY

    assert len(registry.stat_profiles) == 20
    assert len(registry.drop_profiles) == 9
    assert len(registry.reward_profiles) == 1
    assert len(registry.presentation_profiles) == 20
    assert all(
        drop.status == "LEGACY_COMPATIBILITY_REFERENCE"
        and drop.source_ref == "app._roll_loot + EQUIPMENT_DEFS.drop_from"
        for drop in registry.drop_profiles.values()
    )
    assert all(
        reward.status == "LEGACY_COMPATIBILITY_REFERENCE"
        and reward.source_ref == "app._update_monster_and_quests"
        for reward in registry.reward_profiles.values()
    )


def test_unknown_profile_fails_closed_without_inheriting_another_profile():
    assert get_monster_profile("not-a-canonical-monster") is None
    assert get_monster_profile(None) is None
    assert get_monster_profile("dragon") is None


def test_registry_rejects_incomplete_identity_coverage():
    incomplete = MonsterIdentityRegistry(
        entries=IDENTITIES[:-1],
        by_id={identity.monster_id: identity for identity in IDENTITIES[:-1]},
        by_roster_slot={identity.roster_slot: identity for identity in IDENTITIES[:-1]},
    )
    with pytest.raises(ValueError, match="all 20"):
        build_canonical_monster_profile_registry(incomplete)


def test_f004_does_not_add_a_second_identity_resolver_or_runtime_writer():
    assert PROFILE_SOURCE.count("def resolve_monster_identity") == 0
    assert "settle_map_battle_submission" not in PROFILE_SOURCE
    assert "def _update_monster_and_quests" not in PROFILE_SOURCE
    assert "CREATE TABLE" not in PROFILE_SOURCE
    assert "QUEST_PROGRESS_WRITTEN" not in PROFILE_SOURCE


def test_app_and_protected_runtime_boundaries_are_unchanged():
    assert "from monster_profiles" not in APP_SOURCE
    assert "_BATTLEFIELD_ROSTER" in APP_SOURCE
    assert "monster_type" in APP_SOURCE
    assert "EQUIPMENT_DEFS" in APP_SOURCE
    assert "def settle_answer(" not in PROFILE_SOURCE
    assert CANONICAL_BATTLEFIELD_IDENTITY_SPECS
