"""Characterization and pure-contract tests for the Backend V1A1 seam.

These tests intentionally do not import ``app``.  The legacy Flask operation
and its durable authority remain untouched; this file proves that the new
plain contracts and serializer can represent the existing response shapes
without introducing a second runtime path.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from legacy_review_serializer import LegacyReviewSerializer
from review_compatibility import (
    LegacyReviewCompatibilityAdapter,
    adapt_legacy_review_result,
    serialize_legacy_review_result,
)
from review_contracts import (
    CORE_20_FIELDS,
    FULL_26_FIELDS,
    INTERNAL_DUPLICATE_4_FIELDS,
    T2_OPTIONAL_FIELDS,
    ReviewCommand,
    ReviewOutcome,
    ReviewOutcomeKind,
)


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def _full_payload() -> dict[str, object]:
    return {
        "ok": True,
        "ease_factor": 2.5,
        "interval": 3,
        "due_date": "2026-08-17",
        "new_badges": [],
        "stats": {"xp": 10, "total_correct": 1},
        "xp_gain": 10,
        "combo_mult": 1.0,
        "pet_xp_added": 0,
        "pet_xp_ratio": 0.0,
        "pet_xp_gained": 1,
        "combo_streak": 1,
        "shield_used": False,
        "xp_potion_active": False,
        "ranked_up": False,
        "new_rank_level": None,
        "pet": None,
        "practice": {"level": 1},
        "training": {"level": 1},
        "new_appearance_items": [],
        "monster": {"defeated": False},
        "player": {"hp": 30},
        "quest_updates": [],
        "sp": None,
        "loot": None,
        "appearance_loot": None,
    }


def _core_payload() -> dict[str, object]:
    full = _full_payload()
    return {field: full[field] for field in CORE_20_FIELDS}


def _duplicate_payload() -> dict[str, object]:
    return {
        "ok": True,
        "progression_applied": False,
        "progression_duplicate": True,
        "question_id": 7001,
    }


def test_characterization_locks_legacy_public_and_internal_shapes():
    route_start = APP_SOURCE.index("@app.route('/api/srs/review'")
    operation_start = APP_SOURCE.index("def _srs_review_operation", route_start)
    operation_end = APP_SOURCE.index("def _run_map_battle_progression", operation_start)
    operation = APP_SOURCE[operation_start:operation_end]

    assert "return _srs_review_operation(" in APP_SOURCE[route_start:operation_start]
    for field in CORE_20_FIELDS:
        assert f"'{field}'" in operation, field

    monster_start = APP_SOURCE.index("def _update_monster_and_quests")
    monster_end = APP_SOURCE.index("@app.route('/api/monster/status'", monster_start)
    monster_operation = APP_SOURCE[monster_start:monster_end]
    for field in T2_OPTIONAL_FIELDS:
        assert f"'{field}'" in monster_operation, field

    assert "'progression_applied': False" in operation
    assert "'progression_duplicate': True" in operation
    assert "'question_id': qid" in operation


def test_contract_field_sets_are_exact_and_ordered():
    assert len(CORE_20_FIELDS) == 20
    assert len(FULL_26_FIELDS) == 26
    assert FULL_26_FIELDS[:20] == CORE_20_FIELDS
    assert FULL_26_FIELDS[20:] == T2_OPTIONAL_FIELDS
    assert INTERNAL_DUPLICATE_4_FIELDS == (
        "ok",
        "progression_applied",
        "progression_duplicate",
        "question_id",
    )


def test_review_command_is_plain_and_does_not_import_web_or_storage():
    source = (ROOT / "review_contracts.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not any(module == "flask" or module.startswith("flask.") for module in imported_modules)
    assert "app" not in imported_modules
    assert "sqlite3" not in imported_modules
    assert "psycopg" not in imported_modules

    command = ReviewCommand(
        question_id=7001,
        grade=5,
        response_ms=4200,
        source_context="practice",
        internal=False,
    )
    assert command.question_id == 7001
    assert command.grade == 5
    assert command.response_ms == 4200


def test_review_outcome_is_plain_snapshot_data():
    payload = _full_payload()
    outcome = ReviewOutcome.public_full(payload)
    payload["xp_gain"] = 999

    assert outcome.kind is ReviewOutcomeKind.PUBLIC_FULL
    assert outcome.payload["xp_gain"] == 10
    assert not hasattr(outcome, "commit")
    assert not hasattr(outcome, "rollback")


@pytest.mark.parametrize(
    ("kind", "payload", "expected"),
    [
        (ReviewOutcomeKind.PUBLIC_FULL, _full_payload(), FULL_26_FIELDS),
        (ReviewOutcomeKind.PUBLIC_CORE, _core_payload(), CORE_20_FIELDS),
        (
            ReviewOutcomeKind.INTERNAL_DUPLICATE,
            _duplicate_payload(),
            INTERNAL_DUPLICATE_4_FIELDS,
        ),
    ],
)
def test_serializer_preserves_exact_shape_and_value_types(kind, payload, expected):
    result = LegacyReviewSerializer.serialize(ReviewOutcome(kind, payload))
    assert tuple(result) == expected
    assert result == payload
    assert result["ok"] is True


def test_core_result_preserves_missing_optional_fields_not_nulls():
    result = serialize_legacy_review_result(_core_payload())
    assert tuple(result) == CORE_20_FIELDS
    for field in T2_OPTIONAL_FIELDS:
        assert field not in result

    full = _full_payload()
    assert serialize_legacy_review_result(full)["loot"] is None
    assert "loot" in serialize_legacy_review_result(full)


def test_optional_t2_failure_is_core_shape_and_not_six_null_fields():
    core = _core_payload()
    adapted = adapt_legacy_review_result(core)
    assert adapted.kind is ReviewOutcomeKind.PUBLIC_CORE
    serialized = LegacyReviewSerializer.serialize(adapted)
    assert set(serialized) == set(CORE_20_FIELDS)
    assert not any(field in serialized for field in T2_OPTIONAL_FIELDS)


def test_adapter_round_trips_public_full_and_public_core_without_business_logic():
    full = _full_payload()
    core = _core_payload()
    assert serialize_legacy_review_result(full) == full
    assert serialize_legacy_review_result(core) == core
    assert LegacyReviewCompatibilityAdapter.to_legacy_payload(full) == full
    assert LegacyReviewCompatibilityAdapter.to_legacy_payload(core) == core


def test_internal_duplicate_is_internal_only_and_not_a_public_envelope():
    duplicate = _duplicate_payload()
    outcome = adapt_legacy_review_result(duplicate, internal=True)
    assert outcome.kind is ReviewOutcomeKind.INTERNAL_DUPLICATE
    assert serialize_legacy_review_result(duplicate, internal=True) == duplicate

    with pytest.raises(ValueError, match="internal duplicate"):
        adapt_legacy_review_result(duplicate, internal=False)


@pytest.mark.parametrize(
    "payload",
    [
        {**_core_payload(), "monster": None},
        {**_full_payload(), "unexpected": True},
        {"ok": True},
    ],
)
def test_adapter_rejects_partial_or_unknown_shapes(payload):
    with pytest.raises(ValueError, match="unrecognized legacy review result shape"):
        adapt_legacy_review_result(payload)


def test_serializer_has_no_storage_or_transaction_dependency():
    source = (ROOT / "legacy_review_serializer.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not any(module in {"flask", "sqlite3", "psycopg"} for module in imported_modules)
    for forbidden in ("get_db", "commit(", "rollback(", "jsonify"):
        assert forbidden not in source
