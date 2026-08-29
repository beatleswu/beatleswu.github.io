"""E047 deterministic Battlefield shadow-caller contracts."""

from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from battlefield_monster_catalog_shadow_caller import (
    ADVENTURE_ACTIVE_CALLER_INTEGRATED,
    ADVENTURE_PROFILE_AUTO_INHERITS_BATTLEFIELD,
    ART002_GAMEPLAY_AUTHORITY,
    ATK_DRIFT,
    BATTLEFIELD_BOSS,
    BATTLEFIELD_NORMAL,
    COMMON_RARE_ELITE_ENABLED,
    COMBAT_CLASS_FREQUENCY_COUPLED,
    CONTEXT_MISMATCH,
    F009_ACTIVE_CALLER_INTEGRATED,
    F009_ENABLED,
    F009_SELECTION_AUTHORITY_CHANGED,
    F034_PLANNING_ZONE_USED_FOR_GAMEPLAY,
    HP_DRIFT,
    IDENTITY_DRIFT,
    LORD_ACTIVE_CALLER_INTEGRATED,
    LORD_NUMERIC_PROFILE_CREATED,
    MATCH,
    MISSING_PROFILE,
    PROFILE_REF_DRIFT,
    PROFILE_VERSION_DRIFT,
    PROFILE_VERSION_COMPATIBILITY,
    SHADOW_CALLER_ACTIVE_GAMEPLAY_AUTHORITY,
    SHADOW_CALLER_MUTATION_CAPABLE,
    SHADOW_CALLER_PLAYER_VISIBLE,
    SHADOW_CALLER_SIDE_EFFECTS,
    SHADOW_DIAGNOSTIC_ARTIFACT_CREATED,
    SHADOW_DIAGNOSTIC_DETERMINISTIC,
    SHADOW_DRIFT_TYPES,
    SHADOW_DRIFT_TYPES_EXPLICIT,
    SHADOW_FAILURE_CHANGES_ACTIVE_RESULT,
    SHADOW_RESULT_CAN_MUTATE_GAMEPLAY,
    SHADOW_RESULT_CAN_SELECT_MONSTER,
    SHADOW_RESULT_CAN_SET_HP_ATK,
    UNKNOWN_MONSTER,
    UNKNOWN_MONSTER_FAIL_CLOSED,
    UNKNOWN_PROFILE,
    UNKNOWN_PROFILE_FAIL_CLOSED,
    MISSING_PROFILE_FAIL_CLOSED,
    WORLD_ACTIVE_CALLER_INTEGRATED,
    build_shadow_diagnostic_artifact,
    classify_shadow_drift,
    observe_battlefield_encounter,
    observe_battlefield_shadow_matrix,
    render_shadow_diagnostic_json,
)
from monster_catalog_foundation import (
    BATTLEFIELD_BOSS as FOUNDATION_BOSS,
    BATTLEFIELD_NORMAL as FOUNDATION_NORMAL,
    CANONICAL_MONSTER_CATALOG,
    CombatProfileReference,
    PROFILE_REGISTRY_VERSION,
    get_monster,
)


ROOT = Path(__file__).resolve().parents[1]


def _literal_assignment(name: str):
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    node = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        )
    )
    return ast.literal_eval(node.value)


def test_caller_is_observational_and_side_effect_free():
    assert SHADOW_CALLER_ACTIVE_GAMEPLAY_AUTHORITY is False
    assert SHADOW_CALLER_PLAYER_VISIBLE is False
    assert SHADOW_CALLER_MUTATION_CAPABLE is False
    assert SHADOW_RESULT_CAN_MUTATE_GAMEPLAY is False
    assert SHADOW_RESULT_CAN_SELECT_MONSTER is False
    assert SHADOW_RESULT_CAN_SET_HP_ATK is False
    assert SHADOW_FAILURE_CHANGES_ACTIVE_RESULT is False
    assert SHADOW_CALLER_SIDE_EFFECTS == "NONE"
    assert SHADOW_DIAGNOSTIC_ARTIFACT_CREATED is True
    assert SHADOW_DIAGNOSTIC_DETERMINISTIC is True
    assert PRODUCTION_TELEMETRY_NOT_PRESENT_IN_SOURCE()


def PRODUCTION_TELEMETRY_NOT_PRESENT_IN_SOURCE():
    source = (ROOT / "battlefield_monster_catalog_shadow_caller.py").read_text(
        encoding="utf-8"
    )
    return "requests.post" not in source and "INSERT INTO" not in source


def test_battlefield_shadow_matrix_covers_current_authority_and_foundation():
    roster = _literal_assignment("_BATTLEFIELD_ROSTER")
    records = observe_battlefield_shadow_matrix()
    assert len(records) == 20
    assert sum(record.encounter_class == "NORMAL" for record in records) == 10
    assert sum(record.encounter_class == "BATTLEFIELD_BOSS" for record in records) == 10
    assert all(record.status == "PASS" for record in records)
    assert all(record.drift_type == MATCH for record in records)

    expected = []
    for index, row in enumerate(roster):
        zone_number = index // 2 + 1
        encounter_class = "NORMAL" if row[4] == "normal" else "BATTLEFIELD_BOSS"
        expected.append(
            (
                f"zone_{zone_number:02d}",
                encounter_class,
                f"legacy_bf_{zone_number:02d}_{'normal' if row[4] == 'normal' else 'boss'}",
                row[2],
                row[3],
            )
        )
    expected.sort(key=lambda item: (item[0], 0 if item[1] == "NORMAL" else 1))
    actual = [
        (
            record.zone,
            record.encounter_class,
            record.current_monster_id,
            record.current_hp,
            record.current_atk,
        )
        for record in records
    ]
    assert actual == expected
    assert all(
        record.current_profile["source"] == "F004_MONSTER_PROFILE_REGISTRY"
        for record in records
    )


def test_diagnostic_artifact_is_machine_readable_and_deterministic():
    first = build_shadow_diagnostic_artifact()
    second = build_shadow_diagnostic_artifact()
    assert first == second
    assert first["status"] == "PASS"
    assert first["drift_count"] == 0
    assert len(first["records"]) == 20
    assert json.loads(render_shadow_diagnostic_json()) == first
    assert render_shadow_diagnostic_json() == render_shadow_diagnostic_json()


def test_drift_taxonomy_is_explicit_and_ordered():
    base = {
        "current_monster_id": "monster",
        "shadow_monster_id": "monster",
        "current_context": BATTLEFIELD_NORMAL,
        "shadow_context": BATTLEFIELD_NORMAL,
        "current_profile_id": "profile",
        "shadow_profile_id": "profile",
        "current_hp": 80,
        "shadow_hp": 80,
        "current_atk": 2,
        "shadow_atk": 2,
    }
    cases = (
        ({}, MATCH),
        ({"shadow_monster_id": "other"}, IDENTITY_DRIFT),
        ({"shadow_context": BATTLEFIELD_BOSS}, CONTEXT_MISMATCH),
        ({"shadow_profile_id": "other"}, PROFILE_REF_DRIFT),
        ({"shadow_profile_id": None}, MISSING_PROFILE),
        (
            {
                "current_profile_version": "f009.v1",
                "shadow_profile_version": "e045.profile.v1",
            },
            PROFILE_VERSION_DRIFT,
        ),
        ({"shadow_hp": 81}, HP_DRIFT),
        ({"shadow_atk": 3}, ATK_DRIFT),
    )
    for overrides, expected in cases:
        assert classify_shadow_drift(**{**base, **overrides}) == expected

    assert set(
        (
            MATCH,
            IDENTITY_DRIFT,
            PROFILE_REF_DRIFT,
            PROFILE_VERSION_DRIFT,
            HP_DRIFT,
            ATK_DRIFT,
            MISSING_PROFILE,
            UNKNOWN_MONSTER,
            UNKNOWN_PROFILE,
            CONTEXT_MISMATCH,
        )
    ) == set(SHADOW_DRIFT_TYPES)
    assert SHADOW_DRIFT_TYPES_EXPLICIT is True
    assert ("f008.v1", "e045.profile.v1") in PROFILE_VERSION_COMPATIBILITY


def test_unknown_identity_is_a_typed_failure_without_active_result_change():
    runtime = {"monster_id": "not-a-canonical-monster"}
    before = dict(runtime)
    record = observe_battlefield_encounter(runtime, context=BATTLEFIELD_NORMAL)

    assert runtime == before
    assert record.status == "FAIL"
    assert record.drift_type == UNKNOWN_MONSTER
    assert record.current_monster_id == "not-a-canonical-monster"
    assert record.shadow_monster_id is None
    assert record.current_hp is None
    assert UNKNOWN_MONSTER_FAIL_CLOSED is True


def test_missing_and_unknown_profile_references_fail_closed():
    entry = get_monster("legacy_bf_01_normal")
    assert entry is not None

    missing_refs = dict(entry.context_profile_refs)
    missing_refs[FOUNDATION_NORMAL] = None
    missing_entry = replace(entry, context_profile_refs=missing_refs)
    missing_catalog = replace(
        CANONICAL_MONSTER_CATALOG,
        entries=tuple(
            missing_entry if item.monster_id == entry.monster_id else item
            for item in CANONICAL_MONSTER_CATALOG.entries
        ),
        by_id={**CANONICAL_MONSTER_CATALOG.by_id, entry.monster_id: missing_entry},
    )
    missing = observe_battlefield_encounter(
        {"monster_id": entry.monster_id},
        context=BATTLEFIELD_NORMAL,
        catalog=missing_catalog,
    )
    assert missing.status == "FAIL"
    assert missing.drift_type == MISSING_PROFILE

    unknown_refs = dict(entry.context_profile_refs)
    unknown_refs[FOUNDATION_NORMAL] = CombatProfileReference(
        profile_id="unknown-profile",
        version=PROFILE_REGISTRY_VERSION,
    )
    unknown_entry = replace(entry, context_profile_refs=unknown_refs)
    unknown_catalog = replace(
        CANONICAL_MONSTER_CATALOG,
        entries=tuple(
            unknown_entry if item.monster_id == entry.monster_id else item
            for item in CANONICAL_MONSTER_CATALOG.entries
        ),
        by_id={**CANONICAL_MONSTER_CATALOG.by_id, entry.monster_id: unknown_entry},
    )
    unknown = observe_battlefield_encounter(
        {"monster_id": entry.monster_id},
        context=BATTLEFIELD_NORMAL,
        catalog=unknown_catalog,
    )
    assert unknown.status == "FAIL"
    assert unknown.drift_type == UNKNOWN_PROFILE
    assert UNKNOWN_PROFILE_FAIL_CLOSED is True
    assert MISSING_PROFILE_FAIL_CLOSED is True


def test_context_boundaries_do_not_activate_other_lanes():
    mismatch = observe_battlefield_encounter(
        {"monster_id": "legacy_bf_01_normal"},
        context=BATTLEFIELD_BOSS,
    )
    assert mismatch.status == "FAIL"
    assert mismatch.drift_type == CONTEXT_MISMATCH

    invalid = observe_battlefield_encounter(
        {"monster_id": "legacy_bf_01_normal"},
        context="LORD",
    )
    assert invalid.status == "FAIL"
    assert invalid.drift_type == CONTEXT_MISMATCH

    adventure = observe_battlefield_encounter(
        {"monster_id": "legacy_bf_01_normal"},
        context="ADVENTURE_NORMAL",
    )
    assert adventure.status == "FAIL"
    assert adventure.drift_type == CONTEXT_MISMATCH

    assert F009_ENABLED is False
    assert F009_ACTIVE_CALLER_INTEGRATED is False
    assert F009_SELECTION_AUTHORITY_CHANGED is False
    assert ADVENTURE_ACTIVE_CALLER_INTEGRATED is False
    assert ADVENTURE_PROFILE_AUTO_INHERITS_BATTLEFIELD is False
    assert LORD_ACTIVE_CALLER_INTEGRATED is False
    assert LORD_NUMERIC_PROFILE_CREATED is False
    assert WORLD_ACTIVE_CALLER_INTEGRATED is False
    assert COMMON_RARE_ELITE_ENABLED is False
    assert COMBAT_CLASS_FREQUENCY_COUPLED is False
    assert ART002_GAMEPLAY_AUTHORITY is False
    assert F034_PLANNING_ZONE_USED_FOR_GAMEPLAY is False


def test_no_runtime_wiring_or_player_facing_integration_was_added():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "battlefield_monster_catalog_shadow_caller" not in app_source
    assert "SHADOW_CALLER_CONSUMER" not in app_source
