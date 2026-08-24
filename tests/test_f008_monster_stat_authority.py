"""F008 Monster stat-authority unification contracts."""

from dataclasses import replace
from pathlib import Path

import pytest

from map_battle_runtime import _FORBIDDEN_CLIENT_FIELDS
from monster_combat_profiles import (
    MAP_BATTLE_DEFAULT_ATTACK,
    MAP_BATTLE_DEFAULT_HP,
    MonsterCombatProfileError,
    build_map_battle_compatibility_overrides,
    resolve_monster_combat_profile,
)
from monster_profiles import (
    CANONICAL_MONSTER_PROFILE_REGISTRY,
    MonsterProfileRegistry,
)


ROOT = Path(__file__).resolve().parents[1]


def test_all_current_20_profiles_resolve_to_the_existing_stat_values():
    registry = CANONICAL_MONSTER_PROFILE_REGISTRY

    assert len(registry.profiles) == 20
    for profile in registry.profiles:
        stat = registry.stat_profiles[profile.stat_profile_id]
        resolved = resolve_monster_combat_profile(
            {"monster_id": profile.monster_id}
        )
        assert resolved.canonical_monster_id == profile.monster_id
        assert resolved.max_hp == stat.max_hp
        assert resolved.attack == stat.attack
        assert resolved.encounter_class in {"COMMON", "BATTLEFIELD_BOSS"}
        assert resolved.stat_source == "F004_MONSTER_PROFILE_REGISTRY"


def test_legacy_vocabularies_bind_identity_without_display_name_authority():
    resolved = resolve_monster_combat_profile(
        {
            "stage": "LV4",
            "encounter_type": "normal",
            "monster_family": "forest_spirit",
            "battle_monster_type": "forest_spirit",
            "monster_name": "localized content label",
        }
    )

    assert resolved.canonical_monster_id == "legacy_bf_04_normal"
    assert resolved.zone_key == "zone_04"
    assert resolved.encounter_class == "COMMON"
    assert resolved.max_hp == 220
    assert resolved.attack == 5


def test_raw_question_stat_fields_are_not_authority_without_explicit_compatibility():
    resolved = resolve_monster_combat_profile(
        {
            "monster_id": "legacy_bf_01_normal",
            "monster_hp_max": 1,
            "monster_atk": 999,
        }
    )

    assert (resolved.max_hp, resolved.attack) == (80, 2)
    assert resolved.compatibility_mode == "NONE"


def test_map_battle_compatibility_preserves_current_100_hp_8_attack_fallback():
    question = {"zone_key": "legacy::forest"}
    overrides = build_map_battle_compatibility_overrides(question)
    resolved = resolve_monster_combat_profile(
        question,
        context="MAP_BATTLE",
        trusted_compatibility_overrides=overrides,
        compatibility_mode="MAP_BATTLE_LEGACY_STATE",
    )

    assert overrides == {"max_hp": MAP_BATTLE_DEFAULT_HP, "attack": MAP_BATTLE_DEFAULT_ATTACK}
    assert resolved.canonical_monster_id is None
    assert (resolved.max_hp, resolved.attack) == (100, 8)
    assert resolved.compatibility_mode == "MAP_BATTLE_LEGACY_STATE"


def test_profile_bound_map_battle_keeps_identity_but_explicitly_preserves_legacy_stats():
    question = {
        "stage": "LV4",
        "encounter_type": "normal",
        "monster_family": "forest_spirit",
        "battle_monster_type": "forest_spirit",
        "monster_name": "not-a-gameplay-key",
        "monster_atk": 8,
    }
    resolved = resolve_monster_combat_profile(
        question,
        context="MAP_BATTLE",
        trusted_compatibility_overrides={"max_hp": 100, "attack": 8},
        compatibility_mode="MAP_BATTLE_LEGACY_STATE",
        compatibility_reason="preserve current Map Battle pacing",
        compatibility_source="server_map_battle_state",
    )

    assert resolved.canonical_monster_id == "legacy_bf_04_normal"
    assert (resolved.max_hp, resolved.attack) == (100, 8)
    assert resolved.stat_source.endswith("+COMPATIBILITY_OVERRIDE")
    assert resolved.override_reason == "preserve current Map Battle pacing"


def test_unknown_identity_fails_closed_and_cannot_become_battlefield_boss():
    with pytest.raises(MonsterCombatProfileError):
        resolve_monster_combat_profile(
            {
                "stage": "LV4",
                "encounter_type": "lord_trial",
                "battle_monster_type": "never-seen",
            },
            context="MAP_BATTLE",
            trusted_compatibility_overrides={"max_hp": 100, "attack": 8},
        )


def test_client_monster_authority_fields_are_forbidden_at_map_battle_boundary():
    required = {
        "monster_id",
        "monster_hp",
        "monster_hp_max",
        "monster_atk",
        "monster_attack",
        "encounter_class",
        "encounter_kind",
        "is_boss",
        "drop_profile_id",
        "reward_profile_id",
    }
    assert required <= _FORBIDDEN_CLIENT_FIELDS


def test_one_resolver_handles_100_synthetic_profiles_without_id_branches():
    base = CANONICAL_MONSTER_PROFILE_REGISTRY
    profiles = list(base.profiles)
    stats = dict(base.stat_profiles)
    by_id = dict(base.by_id)
    by_slot = dict(base.by_roster_slot)

    for index in range(100):
        source_profile = base.profiles[index % len(base.profiles)]
        monster_id = f"synthetic_f008_{index:03d}"
        stat_id = f"stat_{monster_id}"
        profile = replace(
            source_profile,
            monster_id=monster_id,
            roster_slot=1001 + index,
            stat_profile_id=stat_id,
            drop_profile_id=source_profile.drop_profile_id,
            reward_profile_id=source_profile.reward_profile_id,
            presentation_profile_id=source_profile.presentation_profile_id,
        )
        stat = replace(
            base.stat_profiles[source_profile.stat_profile_id],
            profile_id=stat_id,
        )
        profiles.append(profile)
        stats[stat_id] = stat
        by_id[monster_id] = profile
        by_slot[profile.roster_slot] = profile

    synthetic_registry = MonsterProfileRegistry(
        profiles=tuple(profiles),
        by_id=by_id,
        by_roster_slot=by_slot,
        stat_profiles=stats,
        drop_profiles=base.drop_profiles,
        reward_profiles=base.reward_profiles,
        presentation_profiles=base.presentation_profiles,
    )

    for profile in profiles:
        resolved = resolve_monster_combat_profile(
            {"monster_id": profile.monster_id},
            profile_registry=synthetic_registry,
        )
        assert resolved.canonical_monster_id == profile.monster_id


def test_resolver_never_owns_mutable_current_hp():
    resolved = resolve_monster_combat_profile({"monster_id": "legacy_bf_01_normal"})
    assert "current_hp" not in resolved.runtime_fields()
