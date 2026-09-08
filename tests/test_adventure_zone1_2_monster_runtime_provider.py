"""Focused proof for the Owner-approved exact Zone1/2 source authority."""

from __future__ import annotations

from pathlib import Path

import pytest

from adventure_monster_runtime_contract import (
    AdventureMonsterRuntimeProviderRegistry,
    AdventureQuestionBinding,
    ClientAuthorityClaimError,
    MissingBindingError,
    ProviderDisabledError,
    UnknownProviderError,
    StaleQuestionBindingError,
    WrongZoneBindingError,
    build_f006_defeat_event_fields,
    persistence_metadata,
    reject_client_authority_claims,
    validate_runtime_binding,
)
from adventure_zone1_2_monster_runtime_provider import (
    DEFERRED_REWARD_DROP_POLICY,
    ZONE1_2_BINDING_SOURCE,
    ZONE1_2_MONSTER_RUNTIME_PROVIDER,
    ZONE1_2_PERSISTENCE_VERSION,
    ZONE1_2_PROFILE_VERSION,
    get_zone1_2_monster_profile,
    iter_zone1_2_monster_profiles,
    require_zone1_2_monster_profile,
)
from adventure_zone3_monster_authority import (
    ZONE3_NORMAL_ATTACK,
    ZONE3_NORMAL_IDS,
    ZONE3_NORMAL_MAX_HP,
)
from adventure_zone4_10_monster_runtime_provider import (
    iter_zone4_10_monster_profiles,
)
from monster_combat_profiles import (
    MAP_BATTLE_DEFAULT_ATTACK,
    MAP_BATTLE_DEFAULT_HP,
    build_map_battle_compatibility_overrides,
)
from monster_settlement import build_monster_defeated_event


QUESTION = AdventureQuestionBinding(8101, "question-revision-8101")
ZONE1_IDS = {
    "M001",
    "M002",
    "M003",
    "M004",
    "M005",
    "M006",
    "M007",
    "M008",
    "M009",
    "M010",
    "M100",
    "M105",
    "M107",
    "M110",
}
ZONE2_IDS = {
    "M011",
    "M012",
    "M013",
    "M014",
    "M015",
    "M016",
    "M017",
    "M018",
    "M019",
    "M020",
    "M021",
    "M088",
    "M091",
    "M094",
}


def _battle(binding, *, state="OPEN", hp=None):
    return {
        "zone_key": binding.zone_key,
        "question_id": binding.question_binding.question_id,
        "question_revision": binding.question_binding.question_revision,
        "migration_source": binding.persistence_source,
        "migration_version": binding.persistence_version,
        "profile_id": binding.profile_id,
        "profile_version": binding.profile_version,
        "monster_hp": binding.max_hp if hp is None else hp,
        "monster_hp_max": binding.max_hp,
        "player_hp": 20,
        "player_hp_max": 20,
        "state": state,
    }


def test_exact_28_rows_cover_owner_roster_and_combat_authority():
    rows = iter_zone1_2_monster_profiles()

    assert len(rows) == 28
    assert {row.monster_id for row in rows} == ZONE1_IDS | ZONE2_IDS
    assert len({row.monster_id for row in rows}) == 28
    assert len({row.profile_id for row in rows}) == 28
    assert sum(row.zone_key == "Z1" for row in rows) == 14
    assert sum(row.zone_key == "Z2" for row in rows) == 14
    assert sum(row.encounter_class == "NORMAL" for row in rows) == 19
    assert sum(row.encounter_class == "ELITE" for row in rows) == 7
    assert sum(row.encounter_class == "BOSS" for row in rows) == 2

    expected_values = {
        ("Z1", "NORMAL"): (60, 5),
        ("Z1", "ELITE"): (78, 6),
        ("Z1", "BOSS"): (96, 7),
        ("Z2", "NORMAL"): (80, 6),
        ("Z2", "ELITE"): (104, 8),
        ("Z2", "BOSS"): (128, 9),
    }
    for row in rows:
        assert (row.max_hp, row.attack) == expected_values[
            (row.zone_key, row.encounter_class)
        ]
        assert row.profile_id == (
            f"adventure_{row.zone_key.lower()}_"
            f"{row.encounter_class.lower()}_{row.monster_id}"
        )
        assert row.profile_version == ZONE1_2_PROFILE_VERSION
        assert row.family_id is None
        assert row.taxonomy_status == "DEFER_TAXONOMY"
        assert row.reward_drop_policy == DEFERRED_REWARD_DROP_POLICY
        assert row.server_enabled is True


def test_exact_class_assignments_and_roster_slots_are_not_range_derived():
    rows = {row.monster_id: row for row in iter_zone1_2_monster_profiles()}
    assert {mid for mid, row in rows.items() if row.zone_key == "Z1" and row.encounter_class == "NORMAL"} == {
        "M001", "M002", "M003", "M004", "M005", "M006", "M007", "M008", "M009", "M010"
    }
    assert {mid for mid, row in rows.items() if row.zone_key == "Z1" and row.encounter_class == "ELITE"} == {
        "M100", "M105", "M107"
    }
    assert rows["M110"].encounter_class == "BOSS"
    assert {mid for mid, row in rows.items() if row.zone_key == "Z2" and row.encounter_class == "NORMAL"} == {
        "M011", "M012", "M013", "M014", "M015", "M016", "M017", "M018", "M019"
    }
    assert {mid for mid, row in rows.items() if row.zone_key == "Z2" and row.encounter_class == "ELITE"} == {
        "M020", "M021", "M088", "M091"
    }
    assert rows["M094"].encounter_class == "BOSS"
    assert [rows[mid].roster_slot for mid in sorted(ZONE1_IDS)]
    assert {row.roster_slot for row in rows.values() if row.zone_key == "Z1"} == set(range(1, 15))
    assert {row.roster_slot for row in rows.values() if row.zone_key == "Z2"} == set(range(1, 15))


def test_taxonomy_and_reward_drop_are_explicitly_deferred():
    rows = iter_zone1_2_monster_profiles()
    assert all(row.family_id is None for row in rows)
    assert all(row.taxonomy_status == "DEFER_TAXONOMY" for row in rows)
    assert all(
        row.reward_drop_policy == DEFERRED_REWARD_DROP_POLICY for row in rows
    )
    assert DEFERRED_REWARD_DROP_POLICY == "DEFER_Z1_Z2_REWARD_DROP_POLICY"
    for row in rows:
        assert ZONE1_2_MONSTER_RUNTIME_PROVIDER.reward_policy_for(row.monster_id) is None
        binding = ZONE1_2_MONSTER_RUNTIME_PROVIDER.bind_new_battle(101, row.zone_key, QUESTION)
        assert binding.drop_profile_id is None
        assert binding.reward_profile_id is None
        assert "legacy" not in (binding.binding_source or "").casefold()


def test_shared_provider_dispatch_is_deterministic_and_zone_bounded():
    registry = AdventureMonsterRuntimeProviderRegistry(
        (ZONE1_2_MONSTER_RUNTIME_PROVIDER,)
    )
    first = registry.resolve_binding(
        zone_key="Z1",
        question_binding=QUESTION,
        user_id=101,
    )
    second = registry.resolve_binding(
        zone_key="Z1",
        question_binding=QUESTION,
        user_id=999,
    )
    assert first.monster_id == second.monster_id
    assert first.zone_key == "Z1"
    assert get_zone1_2_monster_profile(first.monster_id) is not None
    assert registry.resolve_binding(
        zone_key="Z2",
        question_binding=QUESTION,
        user_id=101,
    ).zone_key == "Z2"

    with pytest.raises(WrongZoneBindingError):
        registry.resolve_binding(
            zone_key="Z3",
            question_binding=QUESTION,
            provider_id=ZONE1_2_MONSTER_RUNTIME_PROVIDER.provider_id,
        )
    with pytest.raises(UnknownProviderError):
        registry.resolve_binding(zone_key="Z4", question_binding=QUESTION)


def test_unknown_disabled_and_missing_profiles_fail_closed():
    disabled = type(ZONE1_2_MONSTER_RUNTIME_PROVIDER)(enabled=False)
    disabled_registry = AdventureMonsterRuntimeProviderRegistry((disabled,))
    with pytest.raises(ProviderDisabledError):
        disabled_registry.resolve_binding(zone_key="Z1", question_binding=QUESTION)

    empty_registry = AdventureMonsterRuntimeProviderRegistry(())
    with pytest.raises(UnknownProviderError):
        empty_registry.resolve_binding(zone_key="Z1", question_binding=QUESTION)
    with pytest.raises(MissingBindingError):
        require_zone1_2_monster_profile("M022")


def test_client_cannot_supply_identity_or_profile_authority():
    with pytest.raises(ClientAuthorityClaimError):
        reject_client_authority_claims({"monster_id": "M001"})
    with pytest.raises(ClientAuthorityClaimError):
        reject_client_authority_claims({"profile_id": "adventure_z1_boss_M110"})


def test_restore_preserves_original_identity_and_rejects_stale_question():
    binding = ZONE1_2_MONSTER_RUNTIME_PROVIDER.bind_new_battle(101, "Z1", QUESTION)
    restored = ZONE1_2_MONSTER_RUNTIME_PROVIDER.restore_binding(
        _battle(binding),
        QUESTION,
    )
    assert restored.monster_id == binding.monster_id
    assert restored.zone_key == binding.zone_key
    assert restored.encounter_class == binding.encounter_class
    assert restored.profile_id == binding.profile_id
    assert restored.profile_version == binding.profile_version
    assert restored.max_hp == binding.max_hp

    with pytest.raises(StaleQuestionBindingError):
        ZONE1_2_MONSTER_RUNTIME_PROVIDER.restore_binding(
            _battle(binding),
            AdventureQuestionBinding(QUESTION.question_id, "different-revision"),
        )


def test_shared_contract_persistence_and_f006_seams_remain_compatible():
    binding = ZONE1_2_MONSTER_RUNTIME_PROVIDER.bind_new_battle(101, "Z2", QUESTION)
    validated = validate_runtime_binding(
        binding,
        expected_zone_key="Z2",
        expected_question_binding=QUESTION,
        expected_provider_id=ZONE1_2_MONSTER_RUNTIME_PROVIDER.provider_id,
        battle=_battle(binding),
    )
    assert validated.family_id is None
    assert persistence_metadata(binding) == {
        "migration_source": ZONE1_2_BINDING_SOURCE,
        "migration_version": binding.persistence_version,
    }
    event = build_monster_defeated_event(
        **build_f006_defeat_event_fields(
            binding,
            settlement_id="z1-z2-test-settlement",
            user_id=101,
            hp_before=binding.max_hp,
            hp_after=0,
        )
    )
    assert event.monster_id == binding.monster_id
    assert event.zone_id == binding.zone_key
    assert event.family_id is None


def test_e055_zone3_and_zone4_10_authority_remain_separate():
    assert {f"M{number:03d}" for number in range(22, 29)}.issubset(set(ZONE3_NORMAL_IDS))
    assert ZONE3_NORMAL_MAX_HP == 100
    assert ZONE3_NORMAL_ATTACK == 8
    assert {row.monster_id for row in iter_zone1_2_monster_profiles()}.isdisjoint(
        set(ZONE3_NORMAL_IDS)
    )
    assert len(iter_zone4_10_monster_profiles()) == 79
    assert {row.monster_id for row in iter_zone1_2_monster_profiles()}.isdisjoint(
        {row.monster_id for row in iter_zone4_10_monster_profiles()}
    )


def test_legacy_fallback_remains_present_and_is_not_promoted():
    assert build_map_battle_compatibility_overrides({}) == {
        "max_hp": MAP_BATTLE_DEFAULT_HP,
        "attack": MAP_BATTLE_DEFAULT_ATTACK,
    }
    assert ZONE1_2_MONSTER_RUNTIME_PROVIDER.reward_policy_for("M001") is None


def test_no_live_app_wiring_or_second_runtime_was_added():
    app_source = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(
        encoding="utf-8"
    )
    assert "adventure_zone1_2_monster_runtime_provider" not in app_source
    assert ZONE1_2_MONSTER_RUNTIME_PROVIDER.runtime_role == "canonical_zone1_2_provider"
