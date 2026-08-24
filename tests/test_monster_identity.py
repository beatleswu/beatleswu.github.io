"""Wave F0 stable Monster identity and vocabulary contracts."""

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from monster_identity import (
    CANONICAL_BATTLEFIELD_MONSTER_COUNT,
    CANONICAL_BATTLEFIELD_IDENTITY_SPECS,
    ENCOUNTER_CLASS_BATTLEFIELD_BOSS,
    ENCOUNTER_CLASS_NORMAL,
    build_battlefield_identity_registry,
    resolve_monster_identity,
)


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
IDENTITY_SOURCE = (ROOT / "monster_identity.py").read_text(encoding="utf-8")
MAP_BATTLE_SOURCE = (ROOT / "map_battle_runtime.py").read_text(encoding="utf-8")


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


def test_current_battlefield_roster_has_one_stable_identity_per_entry():
    registry = build_battlefield_identity_registry(ROSTER)

    assert len(ROSTER) == CANONICAL_BATTLEFIELD_MONSTER_COUNT == 20
    assert len(registry.entries) == 20
    assert len(registry.by_id) == 20
    assert len(registry.by_roster_slot) == 20
    assert [entry.roster_slot for entry in registry.entries] == list(range(1, 21))
    assert [entry.monster_id for entry in registry.entries] == [
        f"legacy_bf_{zone:02d}_{kind}"
        for zone in range(1, 11)
        for kind in ("normal", "boss")
    ]


@pytest.mark.parametrize(
    ("slot", "zone", "encounter_class"),
    [
        (1, "zone_01", ENCOUNTER_CLASS_NORMAL),
        (2, "zone_01", ENCOUNTER_CLASS_BATTLEFIELD_BOSS),
        (11, "zone_06", ENCOUNTER_CLASS_NORMAL),
        (12, "zone_06", ENCOUNTER_CLASS_BATTLEFIELD_BOSS),
        (19, "zone_10", ENCOUNTER_CLASS_NORMAL),
        (20, "zone_10", ENCOUNTER_CLASS_BATTLEFIELD_BOSS),
    ],
)
def test_registry_exposes_zone_slot_class_contract(slot, zone, encounter_class):
    registry = build_battlefield_identity_registry(ROSTER)
    identity = registry.by_roster_slot[slot]

    assert identity.zone_id == zone
    assert identity.roster_slot == slot
    assert identity.encounter_class == encounter_class
    assert identity.display_name_key.startswith("monster.battlefield.")


def test_legacy_monster_type_resolves_only_with_server_context():
    registry = build_battlefield_identity_registry(ROSTER)

    identity = resolve_monster_identity(
        {
            "monster_type": "caterpillar",
            "stage": "LV1",
            "encounter_type": "normal",
        },
        registry=registry,
    )

    assert identity is not None
    assert identity.monster_id == "legacy_bf_01_normal"
    assert identity.family_id == "slime_goblin"

    # A type alone is ambiguous for the normal/Boss pair and must not guess.
    assert resolve_monster_identity({"monster_type": "caterpillar"}, registry=registry) is None


def test_battle_monster_type_and_taxonomy_family_resolve_without_renaming_legacy_fields():
    registry = build_battlefield_identity_registry(ROSTER)
    identity = resolve_monster_identity(
        {
            "stage": "LV2",
            "monster_family": "goblin_bat",
            "battle_monster_type": "cave_bat",
            "encounter_type": "chapter_boss",
        },
        registry=registry,
    )

    assert identity is not None
    assert identity.monster_id == "legacy_bf_02_boss"
    assert identity.encounter_class == ENCOUNTER_CLASS_BATTLEFIELD_BOSS


def test_display_name_and_art_are_not_standalone_gameplay_authority():
    registry = build_battlefield_identity_registry(ROSTER)
    display_name = ROSTER[0][1]

    assert resolve_monster_identity({"display_name": display_name}, registry=registry) is None
    assert resolve_monster_identity({"avatar": "/assets/monsters/slime_chibi.png"}, registry=registry) is None


def test_unknown_legacy_identity_fails_closed():
    registry = build_battlefield_identity_registry(ROSTER)

    assert resolve_monster_identity(
        {"monster_type": "never_seen_before", "stage": "LV1"},
        registry=registry,
    ) is None
    assert resolve_monster_identity(
        {"encounter_type": "lord_trial", "stage": "LV1"},
        registry=registry,
    ) is None


def test_intentional_identity_corruption_is_detected():
    corrupted_duplicate = list(CANONICAL_BATTLEFIELD_IDENTITY_SPECS)
    corrupted_duplicate[1] = replace(
        corrupted_duplicate[1],
        monster_id=corrupted_duplicate[0].monster_id,
    )
    with pytest.raises(ValueError, match="IDs must be unique"):
        build_battlefield_identity_registry(ROSTER, identity_specs=corrupted_duplicate)

    corrupted_zone = list(CANONICAL_BATTLEFIELD_IDENTITY_SPECS)
    corrupted_zone[0] = replace(corrupted_zone[0], zone_id="zone_10")
    with pytest.raises(ValueError, match="corrupted canonical"):
        build_battlefield_identity_registry(ROSTER, identity_specs=corrupted_zone)

    with pytest.raises(ValueError, match="exactly 20"):
        build_battlefield_identity_registry(ROSTER[:-1])


def test_existing_response_and_combat_boundaries_remain_present():
    assert "monster_type" in APP_SOURCE
    assert "battle_monster_type" in APP_SOURCE
    assert '"monster_id":' in IDENTITY_SOURCE
    assert '"family_id":' in IDENTITY_SOURCE
    assert "_battlefield_identity_payload" in APP_SOURCE
    assert "resolve_monster_identity" in APP_SOURCE
    assert "_map_battle_question_by_id" in APP_SOURCE
    assert "question.update(identity.runtime_fields())" in APP_SOURCE

    # F003 must not move settlement or damage authority into the identity
    # adapter.  B025 remains the owner of the known settlement defect.
    assert "def settle_answer(" in MAP_BATTLE_SOURCE
    assert "calculate_combat_effects(" in MAP_BATTLE_SOURCE
    assert "DROP_TABLE_CHANGED" not in APP_SOURCE
