"""E051 Battlefield MonsterCatalog authority-cutover contracts.

These tests exercise the source candidate only.  The candidate changes the
definition authority for Battlefield resolution, while state mutation,
settlement, reward, progression, Adventure, Lord, and Map Battle boundaries
remain separate contracts.
"""

from __future__ import annotations

import ast
import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "e051-authority-cutover-test-secret")
import app as app_module  # noqa: E402

from battlefield_monster_catalog_authority import (  # noqa: E402
    ACTIVE_F003_F004_F008_BATTLEFIELD_AUTHORITY_CALLERS,
    ACTIVE_SILENT_LEGACY_FALLBACK_COUNT,
    ADVENTURE_INCLUDED,
    ADVENTURE_PROFILE_AUTO_INHERITS_BATTLEFIELD,
    ATK_DRIFT,
    ART002_GAMEPLAY_AUTHORITY,
    ART003_GAMEPLAY_AUTHORITY,
    BATTLEFIELD_BOSS,
    BATTLEFIELD_NORMAL,
    BattlefieldCatalogUnknownMonster,
    BOSS_AUTHORITY_SOURCE,
    BOSS_CUTOVER,
    CANDIDATE_LEGACY_F003_F004_F008_ACTIVE_AUTHORITY,
    CANDIDATE_MONSTER_CATALOG_ACTIVE_AUTHORITY,
    COMBAT_CLASS_FREQUENCY_COUPLED,
    CONTEXT_MISMATCH,
    FAIL_CLOSED_DIAGNOSTIC_MATRIX_COMPLETE,
    F009_ENABLED,
    F009_INCLUDED,
    F035_ZONE_USED_FOR_GAMEPLAY,
    F036_BATCH_PLAN_USED_FOR_RUNTIME,
    HP_DRIFT,
    IDENTITY_DRIFT,
    LORD_INCLUDED,
    LORD_NUMERIC_PROFILE_CREATED,
    MATCH,
    MISSING_PROFILE,
    MONSTER_CATALOG_ACTIVE_AUTHORITY,
    MONSTER_CATALOG_DIRECT_PLAYER_STATE_MUTATION,
    MONSTER_CATALOG_DIRECT_REWARD_SETTLEMENT,
    MUTATION_PATH_CUTOVER,
    NORMAL_AUTHORITY_SOURCE,
    NORMAL_CUTOVER,
    NORMAL_BOSS_LORD_COLLAPSED,
    PROFILE_REF_DRIFT,
    PROFILE_VERSION_DRIFT,
    REWARD_AUTHORITY_CHANGED,
    ROLLBACK_REQUIRES_DATA_REPAIR,
    ROLLBACK_REQUIRES_SCHEMA_CHANGE,
    ROLLBACK_TARGET_AUTHORITY,
    SETTLEMENT_PATH_RESOLUTION_CUTOVER,
    STATUS_READONLY_CUTOVER,
    UNKNOWN_ACTIVE_CONSUMERS,
    UNKNOWN_MONSTER,
    UNKNOWN_PROFILE,
    battlefield_catalog_binding_source,
    read_battlefield_state_max_hp,
    resolve_battlefield_catalog_profile,
)
from monster_catalog_foundation import (  # noqa: E402
    CANONICAL_MONSTER_CATALOG,
    CombatProfileReference,
    MonsterCatalog,
    PROFILE_REGISTRY_VERSION,
    get_monster,
)


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    tree = ast.parse(APP_SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(APP_SOURCE, node) or ""
    raise AssertionError(f"missing function: {name}")


def _catalog_source(index: int, row: tuple) -> dict[str, object]:
    return {
        "monster_idx": index,
        "encounter_kind": row[4],
        "profile_max_hp": row[2],
        "profile_attack": row[3],
    }


def _broken_catalog(reference):
    entry = get_monster("legacy_bf_01_normal")
    assert entry is not None
    refs = dict(entry.context_profile_refs)
    refs[BATTLEFIELD_NORMAL] = reference
    updated = replace(entry, context_profile_refs=refs)
    return replace(
        CANONICAL_MONSTER_CATALOG,
        entries=tuple(
            updated if item.monster_id == entry.monster_id
            else item
            for item in CANONICAL_MONSTER_CATALOG.entries
        ),
        by_id={**CANONICAL_MONSTER_CATALOG.by_id, entry.monster_id: updated},
    )


def test_candidate_switches_only_battlefield_definition_authority():
    assert CANDIDATE_MONSTER_CATALOG_ACTIVE_AUTHORITY is True
    assert MONSTER_CATALOG_ACTIVE_AUTHORITY is True
    assert CANDIDATE_LEGACY_F003_F004_F008_ACTIVE_AUTHORITY is False
    assert ACTIVE_F003_F004_F008_BATTLEFIELD_AUTHORITY_CALLERS == 0
    assert ACTIVE_SILENT_LEGACY_FALLBACK_COUNT == 0
    assert UNKNOWN_ACTIVE_CONSUMERS == 0
    assert STATUS_READONLY_CUTOVER is True
    assert NORMAL_CUTOVER is True
    assert BOSS_CUTOVER is True
    assert MUTATION_PATH_CUTOVER is True
    assert SETTLEMENT_PATH_RESOLUTION_CUTOVER is True
    assert NORMAL_AUTHORITY_SOURCE == "MONSTER_CATALOG"
    assert BOSS_AUTHORITY_SOURCE == "MONSTER_CATALOG"


def test_all_ten_normal_and_boss_profiles_match_approved_baseline():
    normal_count = 0
    boss_count = 0
    expected_normal_hp = (80, 130, 200, 220, 260, 520, 760, 1100, 1700, 2400)
    expected_normal_atk = (2, 3, 4, 5, 6, 12, 16, 20, 28, 36)
    expected_boss_hp = (100, 160, 240, 260, 290, 700, 920, 1350, 2000, 2800)
    expected_boss_atk = (2, 4, 5, 6, 7, 14, 18, 22, 32, 40)

    for index, row in enumerate(app_module._BATTLEFIELD_ROSTER):
        profile = resolve_battlefield_catalog_profile(_catalog_source(index, row))
        zone = index // 2
        assert profile.roster_slot == index + 1
        assert profile.zone_key == f"zone_{zone + 1:02d}"
        assert profile.profile_version == PROFILE_REGISTRY_VERSION
        assert profile.context == (
            BATTLEFIELD_BOSS if row[4] == "boss" else BATTLEFIELD_NORMAL
        )
        if row[4] == "boss":
            boss_count += 1
            assert profile.max_hp == expected_boss_hp[zone]
            assert profile.attack == expected_boss_atk[zone]
        else:
            normal_count += 1
            assert profile.max_hp == expected_normal_hp[zone]
            assert profile.attack == expected_normal_atk[zone]
        assert profile.max_hp == row[2]
        assert profile.attack == row[3]

    assert normal_count == 10
    assert boss_count == 10


def test_active_battlefield_callers_do_not_resolve_through_legacy_stat_authority():
    active_callers = (
        "_get_or_create_battlefield",
        "_lane_b_monster_update_with_authoritative_profile",
        "_update_monster_and_quests",
        "monster_status",
    )
    for name in active_callers:
        source = _function_source(name)
        assert "resolve_battlefield_catalog_profile" in source
        assert "resolve_monster_combat_profile" not in source
        assert "build_legacy_battlefield_compatibility_overrides" not in source

    settlement_source = _function_source("_settle_monster_defeat_in_tx")
    assert "if battlefield_authority is not None:" in settlement_source
    assert "settlement_monster_id = battlefield_authority.monster_id" in settlement_source
    assert "Separate Map Battle compatibility path" in settlement_source


@pytest.mark.parametrize(
    ("name", "source", "expected_code"),
    [
        (
            "identity",
            {
                "monster_id": "legacy_bf_01_normal",
                "roster_slot": 2,
            },
            IDENTITY_DRIFT,
        ),
        (
            "context",
            {"monster_id": "legacy_bf_01_normal", "context": BATTLEFIELD_BOSS},
            CONTEXT_MISMATCH,
        ),
        (
            "profile_ref",
            {"monster_id": "legacy_bf_01_normal", "profile_id": "wrong"},
            PROFILE_REF_DRIFT,
        ),
        (
            "profile_version",
            {
                "monster_id": "legacy_bf_01_normal",
                "profile_version": "wrong-version",
            },
            PROFILE_VERSION_DRIFT,
        ),
        (
            "hp",
            {"monster_id": "legacy_bf_01_normal", "profile_max_hp": 81},
            HP_DRIFT,
        ),
        (
            "atk",
            {"monster_id": "legacy_bf_01_normal", "profile_attack": 3},
            ATK_DRIFT,
        ),
        (
            "unknown_monster",
            {"monster_id": "not-a-canonical-monster"},
            UNKNOWN_MONSTER,
        ),
    ],
)
def test_fail_closed_authority_errors_are_typed(name, source, expected_code):
    with pytest.raises(Exception) as captured:
        resolve_battlefield_catalog_profile(source)
    assert captured.value.code == expected_code, name


def test_unknown_and_missing_profiles_fail_closed_without_legacy_recovery():
    unknown_profile_catalog = _broken_catalog(
        CombatProfileReference("not-a-profile", PROFILE_REGISTRY_VERSION)
    )
    with pytest.raises(Exception) as captured:
        resolve_battlefield_catalog_profile(
            {"monster_id": "legacy_bf_01_normal"},
            catalog=unknown_profile_catalog,
        )
    assert captured.value.code == UNKNOWN_PROFILE

    entry = get_monster("legacy_bf_01_normal")
    assert entry is not None
    refs = dict(entry.context_profile_refs)
    refs[BATTLEFIELD_NORMAL] = None
    missing_entry = replace(entry, context_profile_refs=refs)
    missing_catalog = replace(
        CANONICAL_MONSTER_CATALOG,
        entries=tuple(
            missing_entry if item.monster_id == entry.monster_id
            else item
            for item in CANONICAL_MONSTER_CATALOG.entries
        ),
        by_id={**CANONICAL_MONSTER_CATALOG.by_id, entry.monster_id: missing_entry},
    )
    with pytest.raises(Exception) as captured:
        resolve_battlefield_catalog_profile(
            {"monster_id": entry.monster_id},
            catalog=missing_catalog,
        )
    assert captured.value.code == MISSING_PROFILE


def test_existing_battle_state_is_not_mistaken_for_profile_authority():
    state = {
        "monster_idx": 0,
        "monster_type": "caterpillar",
        "monster_name": "LV B021 encounter",
        "max_hp": 1000,
        "current_hp": 640,
    }
    profile = resolve_battlefield_catalog_profile(
        battlefield_catalog_binding_source(state)
    )
    assert profile.monster_id == "legacy_bf_01_normal"
    assert profile.max_hp == 80
    assert read_battlefield_state_max_hp(state) == 1000
    assert "max_hp" not in battlefield_catalog_binding_source(state)
    assert "current_hp" not in battlefield_catalog_binding_source(state)


def test_cutover_does_not_give_catalog_mutation_or_reward_authority():
    assert MONSTER_CATALOG_DIRECT_PLAYER_STATE_MUTATION is False
    assert MONSTER_CATALOG_DIRECT_REWARD_SETTLEMENT is False
    assert REWARD_AUTHORITY_CHANGED is False
    assert "settle_monster_defeat" not in (
        (ROOT / "battlefield_monster_catalog_authority.py").read_text(encoding="utf-8")
    )
    assert "INSERT INTO" not in (
        (ROOT / "battlefield_monster_catalog_authority.py").read_text(encoding="utf-8")
    )
    assert ROLLBACK_TARGET_AUTHORITY == "F003_F004_F008"
    assert ROLLBACK_REQUIRES_SCHEMA_CHANGE is False
    assert ROLLBACK_REQUIRES_DATA_REPAIR is False


def test_fail_closed_firewalls_remain_closed():
    assert FAIL_CLOSED_DIAGNOSTIC_MATRIX_COMPLETE is True
    assert NORMAL_BOSS_LORD_COLLAPSED is False
    assert LORD_INCLUDED is False
    assert LORD_NUMERIC_PROFILE_CREATED is False
    assert ADVENTURE_INCLUDED is False
    assert ADVENTURE_PROFILE_AUTO_INHERITS_BATTLEFIELD is False
    assert F009_ENABLED is False
    assert F009_INCLUDED is False
    assert COMBAT_CLASS_FREQUENCY_COUPLED is False
    assert F035_ZONE_USED_FOR_GAMEPLAY is False
    assert F036_BATCH_PLAN_USED_FOR_RUNTIME is False
    assert ART002_GAMEPLAY_AUTHORITY is False
    assert ART003_GAMEPLAY_AUTHORITY is False


def test_active_srs_path_handles_catalog_resolution_failure_without_fallback():
    operation_source = _function_source("_srs_review_operation")
    assert "except BattlefieldCatalogAuthorityError as error:" in operation_source
    assert "battlefield_catalog_authority_unavailable" in operation_source
    assert "quest_runtime_pending" in operation_source
    catalog_error_pos = operation_source.rindex(
        "except BattlefieldCatalogAuthorityError as error:"
    )
    assert operation_source.index("except Exception:", catalog_error_pos) > catalog_error_pos


def test_status_path_handles_catalog_resolution_failure_without_fallback():
    status_source = _function_source("monster_status")
    assert "except BattlefieldCatalogAuthorityError as error:" in status_source
    assert "battlefield_catalog_authority_unavailable" in status_source
    assert "return jsonify" in status_source


def test_status_endpoint_returns_typed_failure_when_catalog_cannot_resolve(monkeypatch):
    class _ReadOnlyDb:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def rollback(self):
            self.rolled_back = True

    def _blocked(*args, **kwargs):
        raise BattlefieldCatalogUnknownMonster("test-only unknown Monster")

    monkeypatch.setattr(app_module, "get_db", lambda: _ReadOnlyDb())
    monkeypatch.setattr(app_module, "_get_or_create_battlefield", _blocked)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1

    response = client.get("/api/monster/status")
    assert response.status_code == 503
    assert response.get_json() == {
        "error": "battlefield_catalog_authority_unavailable",
        "code": UNKNOWN_MONSTER,
        "retryable": True,
    }


def test_authority_module_has_no_client_or_presentation_identity_derivation():
    authority_source = (ROOT / "battlefield_monster_catalog_authority.py").read_text(
        encoding="utf-8"
    )
    assert "resolve_monster_identity" not in authority_source
    assert "resolve_monster_combat_profile" not in authority_source
    assert "array fallback" in authority_source
    assert "random" not in authority_source.lower()
    assert "monster_type" not in authority_source
