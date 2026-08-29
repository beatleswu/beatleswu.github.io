"""E049 bounded, non-authoritative Battlefield shadow migration contracts."""

from __future__ import annotations

import ast
import json
import os
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "e049-bounded-shadow-test-secret")
import app as app_module  # noqa: E402

from battlefield_monster_catalog_shadow_caller import (  # noqa: E402
    ATK_DRIFT,
    BATTLEFIELD_BOSS,
    BATTLEFIELD_NORMAL,
    CONTEXT_MISMATCH,
    HP_DRIFT,
    IDENTITY_DRIFT,
    MATCH,
    MISSING_PROFILE,
    PROFILE_REF_DRIFT,
    PROFILE_VERSION_COMPATIBILITY,
    PROFILE_VERSION_DRIFT,
    UNKNOWN_MONSTER,
    UNKNOWN_PROFILE,
    classify_shadow_drift,
    observe_battlefield_encounter,
    observe_battlefield_shadow_matrix,
)
from battlefield_monster_catalog_shadow_runtime import (  # noqa: E402
    CATALOG_CAN_CHANGE_COMBAT_RESULT,
    CATALOG_CAN_MUTATE_PLAYER_STATE,
    CATALOG_CAN_SETTLE_REWARD,
    CATALOG_MUTATION_EXECUTED,
    CATALOG_SETTLEMENT_EXECUTED,
    BattlefieldShadowCollector,
    PATH_ROLE_MUTATION,
    PATH_ROLE_SETTLEMENT,
    PERMANENT_LEGACY_FALLBACK_PATH,
    PHASE_BOSS_BATTLEFIELD_CONSUMERS,
    PHASE_MUTATION_AND_SETTLEMENT,
    PHASE_NORMAL_BATTLEFIELD_CONSUMERS,
    PHASE_STATUS_READ_ONLY_PROJECTION,
    PLAYER_PII_LOGGED,
    PRODUCTION_TELEMETRY_ADDED,
    SHADOW_DIAGNOSTIC_DRIFT_TYPES,
    SHADOW_DIAGNOSTIC_MATRIX_COMPLETE,
    SHADOW_OBSERVATION_ERROR,
    SHADOW_RECORDS_DETERMINISTIC,
    TIME_BOXED_COMPATIBILITY_BRIDGE,
)
from monster_catalog_foundation import (  # noqa: E402
    CANONICAL_MONSTER_CATALOG,
    CombatProfileReference,
    PROFILE_REGISTRY_VERSION,
    get_monster,
)
from monster_combat_profiles import resolve_monster_combat_profile  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    tree = ast.parse(APP_SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(APP_SOURCE, node) or ""
    raise AssertionError(f"missing function: {name}")


def _profile(monster_id: str = "legacy_bf_01_normal"):
    return resolve_monster_combat_profile(
        {"monster_id": monster_id},
        context="LEGACY_BATTLEFIELD",
    )


def _catalog_with_reference(monster_id: str, reference):
    entry = get_monster(monster_id)
    assert entry is not None
    refs = dict(entry.context_profile_refs)
    refs[BATTLEFIELD_NORMAL] = reference
    updated = replace(entry, context_profile_refs=refs)
    return replace(
        CANONICAL_MONSTER_CATALOG,
        entries=tuple(
            updated if item.monster_id == monster_id else item
            for item in CANONICAL_MONSTER_CATALOG.entries
        ),
        by_id={**CANONICAL_MONSTER_CATALOG.by_id, monster_id: updated},
    )


def test_shadow_runtime_contract_is_non_authoritative_and_non_pii():
    assert CATALOG_CAN_MUTATE_PLAYER_STATE is False
    assert CATALOG_CAN_SETTLE_REWARD is False
    assert CATALOG_CAN_CHANGE_COMBAT_RESULT is False
    assert CATALOG_MUTATION_EXECUTED is False
    assert CATALOG_SETTLEMENT_EXECUTED is False
    assert PERMANENT_LEGACY_FALLBACK_PATH is False
    assert TIME_BOXED_COMPATIBILITY_BRIDGE is False
    assert PLAYER_PII_LOGGED is False
    assert PRODUCTION_TELEMETRY_ADDED is False
    assert SHADOW_RECORDS_DETERMINISTIC is True
    assert SHADOW_DIAGNOSTIC_MATRIX_COMPLETE is True
    runtime_source = (ROOT / "battlefield_monster_catalog_shadow_runtime.py").read_text(
        encoding="utf-8"
    )
    assert "user_id" not in runtime_source
    assert "INSERT INTO" not in runtime_source
    assert "requests." not in runtime_source


def test_status_projection_shadow_test_passes_without_changing_profile():
    profile = _profile()
    before = profile.runtime_fields()
    collector = BattlefieldShadowCollector()
    record = collector.observe(
        {
            "monster_id": profile.canonical_monster_id,
            "roster_slot": profile.roster_slot,
            "current_hp": profile.max_hp,
            "current_atk": profile.attack,
        },
        context=BATTLEFIELD_NORMAL,
        phase=PHASE_STATUS_READ_ONLY_PROJECTION,
        zone=profile.zone_key,
        current_profile=profile,
    )
    assert record["status"] == "PASS"
    assert record["drift_type"] == MATCH
    assert record["phase"] == PHASE_STATUS_READ_ONLY_PROJECTION
    assert record["active_result_unchanged"] is True
    assert profile.runtime_fields() == before
    assert "user_id" not in record
    assert "session" not in record


def test_normal_10_id_shadow_test_passes_with_zero_drift():
    records = observe_battlefield_shadow_matrix()
    normal = [record for record in records if record.encounter_class == "NORMAL"]
    assert len(normal) == 10
    assert all(record.status == "PASS" for record in normal)
    assert all(record.drift_type == MATCH for record in normal)


def test_boss_10_id_shadow_test_passes_with_zero_drift():
    records = observe_battlefield_shadow_matrix()
    bosses = [
        record for record in records if record.encounter_class == "BATTLEFIELD_BOSS"
    ]
    assert len(bosses) == 10
    assert all(record.status == "PASS" for record in bosses)
    assert all(record.drift_type == MATCH for record in bosses)


def test_mutation_path_shadow_test_passes_and_cannot_mutate():
    profile = _profile()
    collector = BattlefieldShadowCollector()
    record = collector.observe(
        {"monster_id": profile.canonical_monster_id},
        context=BATTLEFIELD_NORMAL,
        phase=PHASE_MUTATION_AND_SETTLEMENT,
        path_role=PATH_ROLE_MUTATION,
        zone=profile.zone_key,
        current_profile=profile,
    )
    assert record["status"] == "PASS"
    assert record["path_role"] == PATH_ROLE_MUTATION
    assert record["mutation_capable"] is False
    assert record["active_result_unchanged"] is True


def test_settlement_path_shadow_test_passes_and_cannot_settle():
    profile = _profile()
    collector = BattlefieldShadowCollector()
    record = collector.observe(
        {"monster_id": profile.canonical_monster_id},
        context=BATTLEFIELD_NORMAL,
        phase=PHASE_MUTATION_AND_SETTLEMENT,
        path_role=PATH_ROLE_SETTLEMENT,
        zone=profile.zone_key,
        current_profile=profile,
    )
    assert record["status"] == "PASS"
    assert record["path_role"] == PATH_ROLE_SETTLEMENT
    assert record["mutation_capable"] is False
    assert CATALOG_SETTLEMENT_EXECUTED is False


def test_zero_drift_contract_is_deterministic():
    collector = BattlefieldShadowCollector()
    for record in observe_battlefield_shadow_matrix():
        collector.observe(
            {
                "monster_id": record.current_monster_id,
                "current_hp": record.current_hp,
                "current_atk": record.current_atk,
            },
            context=(
                BATTLEFIELD_BOSS
                if record.encounter_class == "BATTLEFIELD_BOSS"
                else BATTLEFIELD_NORMAL
            ),
            phase=(
                PHASE_BOSS_BATTLEFIELD_CONSUMERS
                if record.encounter_class == "BATTLEFIELD_BOSS"
                else PHASE_NORMAL_BATTLEFIELD_CONSUMERS
            ),
            zone=record.zone,
        )
    first = collector.artifact()
    second = collector.artifact()
    assert first == second
    assert first["status"] == "PASS"
    assert first["drift_count"] == 0
    assert json.loads(collector.render_json()) == first
    assert len(first["records"]) == 20


def test_identity_drift_fail_is_explicit():
    base = {
        "current_monster_id": "monster",
        "shadow_monster_id": "monster",
        "current_context": BATTLEFIELD_NORMAL,
        "shadow_context": BATTLEFIELD_NORMAL,
        "current_profile_id": "profile",
        "shadow_profile_id": "profile",
        "current_profile_version": "f008.v1",
        "shadow_profile_version": "e045.profile.v1",
        "current_hp": 80,
        "shadow_hp": 80,
        "current_atk": 2,
        "shadow_atk": 2,
    }
    assert classify_shadow_drift(**{**base, "shadow_monster_id": "other"}) == IDENTITY_DRIFT


def test_context_drift_fail_is_explicit():
    base = {
        "current_monster_id": "monster",
        "shadow_monster_id": "monster",
        "current_context": BATTLEFIELD_NORMAL,
        "shadow_context": BATTLEFIELD_BOSS,
        "current_profile_id": "profile",
        "shadow_profile_id": "profile",
        "current_profile_version": "f008.v1",
        "shadow_profile_version": "e045.profile.v1",
        "current_hp": 80,
        "shadow_hp": 80,
        "current_atk": 2,
        "shadow_atk": 2,
    }
    assert classify_shadow_drift(**base) == CONTEXT_MISMATCH


def test_profile_id_drift_fail_is_explicit():
    base = {
        "current_monster_id": "monster",
        "shadow_monster_id": "monster",
        "current_context": BATTLEFIELD_NORMAL,
        "shadow_context": BATTLEFIELD_NORMAL,
        "current_profile_id": "profile-a",
        "shadow_profile_id": "profile-b",
        "current_profile_version": "f008.v1",
        "shadow_profile_version": "e045.profile.v1",
        "current_hp": 80,
        "shadow_hp": 80,
        "current_atk": 2,
        "shadow_atk": 2,
    }
    assert classify_shadow_drift(**base) == PROFILE_REF_DRIFT


def test_profile_version_drift_fail_is_explicit():
    base = {
        "current_monster_id": "monster",
        "shadow_monster_id": "monster",
        "current_context": BATTLEFIELD_NORMAL,
        "shadow_context": BATTLEFIELD_NORMAL,
        "current_profile_id": "profile",
        "shadow_profile_id": "profile",
        "current_profile_version": "f009.v1",
        "shadow_profile_version": "e045.profile.v1",
        "current_hp": 80,
        "shadow_hp": 80,
        "current_atk": 2,
        "shadow_atk": 2,
    }
    assert classify_shadow_drift(**base) == PROFILE_VERSION_DRIFT
    assert ("f008.v1", "e045.profile.v1") in PROFILE_VERSION_COMPATIBILITY


def test_hp_and_atk_drift_fail_are_explicit():
    base = {
        "current_monster_id": "monster",
        "shadow_monster_id": "monster",
        "current_context": BATTLEFIELD_NORMAL,
        "shadow_context": BATTLEFIELD_NORMAL,
        "current_profile_id": "profile",
        "shadow_profile_id": "profile",
        "current_profile_version": "f008.v1",
        "shadow_profile_version": "e045.profile.v1",
        "current_hp": 80,
        "shadow_hp": 80,
        "current_atk": 2,
        "shadow_atk": 2,
    }
    assert classify_shadow_drift(**{**base, "shadow_hp": 81}) == HP_DRIFT
    assert classify_shadow_drift(**{**base, "shadow_atk": 3}) == ATK_DRIFT


def test_unknown_monster_fail_does_not_change_input():
    runtime = {"monster_id": "not-a-monster"}
    before = dict(runtime)
    record = observe_battlefield_encounter(runtime, context=BATTLEFIELD_NORMAL)
    assert runtime == before
    assert record.status == "FAIL"
    assert record.drift_type == UNKNOWN_MONSTER
    assert record.shadow_monster_id is None


def test_unknown_profile_fail_is_typed_and_not_fallback():
    catalog = _catalog_with_reference(
        "legacy_bf_01_normal",
        CombatProfileReference("missing-profile", PROFILE_REGISTRY_VERSION),
    )
    record = observe_battlefield_encounter(
        {"monster_id": "legacy_bf_01_normal"},
        context=BATTLEFIELD_NORMAL,
        catalog=catalog,
    )
    assert record.status == "FAIL"
    assert record.drift_type == UNKNOWN_PROFILE
    assert record.shadow_profile is None


def test_missing_profile_fail_is_typed_and_not_fallback():
    entry = get_monster("legacy_bf_01_normal")
    assert entry is not None
    refs = dict(entry.context_profile_refs)
    refs[BATTLEFIELD_NORMAL] = None
    updated = replace(entry, context_profile_refs=refs)
    catalog = replace(
        CANONICAL_MONSTER_CATALOG,
        entries=tuple(
            updated if item.monster_id == entry.monster_id else item
            for item in CANONICAL_MONSTER_CATALOG.entries
        ),
        by_id={**CANONICAL_MONSTER_CATALOG.by_id, entry.monster_id: updated},
    )
    record = observe_battlefield_encounter(
        {"monster_id": entry.monster_id},
        context=BATTLEFIELD_NORMAL,
        catalog=catalog,
    )
    assert record.status == "FAIL"
    assert record.drift_type == MISSING_PROFILE


def test_shadow_diagnostic_matrix_is_complete_and_context_firewalled():
    expected = {
        MATCH,
        IDENTITY_DRIFT,
        CONTEXT_MISMATCH,
        PROFILE_REF_DRIFT,
        PROFILE_VERSION_DRIFT,
        HP_DRIFT,
        ATK_DRIFT,
        UNKNOWN_MONSTER,
        UNKNOWN_PROFILE,
        MISSING_PROFILE,
    }
    assert set(SHADOW_DIAGNOSTIC_DRIFT_TYPES) == expected
    assert SHADOW_OBSERVATION_ERROR not in SHADOW_DIAGNOSTIC_DRIFT_TYPES
    mismatch = observe_battlefield_encounter(
        {"monster_id": "legacy_bf_01_normal"},
        context=BATTLEFIELD_BOSS,
    )
    assert mismatch.status == "FAIL"
    assert mismatch.drift_type == CONTEXT_MISMATCH


def test_app_integration_uses_request_local_shadow_only_in_approved_order():
    assert "battlefield_monster_catalog_shadow_runtime" in APP_SOURCE
    assert "from monster_catalog_foundation" not in APP_SOURCE
    assert "resolve_context_profile" not in APP_SOURCE
    assert "CATALOG_MUTATION_EXECUTED = True" not in APP_SOURCE
    assert "CATALOG_SETTLEMENT_EXECUTED = True" not in APP_SOURCE
    status_source = _function_source("monster_status")
    normal_boss_source = _function_source(
        "_lane_b_monster_update_with_authoritative_profile"
    )
    mutation_source = _function_source("_update_monster_and_quests")
    assert "PHASE_STATUS_READ_ONLY_PROJECTION" in status_source
    assert "PHASE_NORMAL_BATTLEFIELD_CONSUMERS" in normal_boss_source
    assert "PHASE_BOSS_BATTLEFIELD_CONSUMERS" in normal_boss_source
    assert "PHASE_MUTATION_AND_SETTLEMENT" in mutation_source
    assert "BATTLEFIELD_SHADOW_MUTATION" in mutation_source
    assert "BATTLEFIELD_SHADOW_SETTLEMENT" in mutation_source
    assert "_publish_battlefield_shadow_records" in status_source
    assert "_publish_battlefield_shadow_records" in APP_SOURCE


def test_active_authority_and_firewalls_remain_unchanged():
    assert "resolve_monster_combat_profile" in APP_SOURCE
    assert "resolve_context_profile" not in APP_SOURCE
    assert "monster_catalog_foundation" not in APP_SOURCE
    assert "monster_encounter_selector" in APP_SOURCE
    assert "adventure_boss_start" in APP_SOURCE
    assert "adventure_boss_finish" in APP_SOURCE
    assert "current_result = shadow" not in APP_SOURCE
    assert "CATALOG_CAN_MUTATE_PLAYER_STATE = True" not in APP_SOURCE
    assert "CATALOG_CAN_SETTLE_REWARD = True" not in APP_SOURCE


def test_current_server_profile_override_is_observed_as_drift_not_replaced():
    profile = resolve_monster_combat_profile(
        {"monster_id": "legacy_bf_01_normal"},
        context="LEGACY_BATTLEFIELD",
        trusted_compatibility_overrides={"max_hp": 81},
        compatibility_mode="LEGACY_PERSISTED_BATTLE_STATE",
    )
    record = observe_battlefield_encounter(
        {
            "monster_id": profile.canonical_monster_id,
            "current_hp": profile.max_hp,
            "current_atk": profile.attack,
        },
        context=BATTLEFIELD_NORMAL,
        current_profile=profile,
    )
    assert record.status == "DRIFT"
    assert record.drift_type == HP_DRIFT
    assert record.current_hp == 81
    assert record.shadow_hp == 80
