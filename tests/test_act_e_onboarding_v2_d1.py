from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from migrations import w2_a1_onboarding_v1 as onboarding_migration
from onboarding_v2_transition import (
    DETERMINISTIC_V2_MAPPING,
    GO_PRODUCTION_DB_MIGRATION,
    LEGACY_GRANDFATHERED,
    NO_SAFE_MAPPING,
    V2_CANONICAL,
    LegacyState,
    analyze_legacy_users,
    classify_legacy_state,
    legacy_compatibility_retirement_condition,
    legacy_stage_mapping_table,
    new_entrant_cutover_contract,
    resolve_onboarding_question_identity,
    transition_existing_legacy_user,
    transition_existing_legacy_users,
)
from wave2_onboarding_authority import (
    COMPLETED,
    IN_PROGRESS,
    STEP_NEXT_ACTION,
    start,
    resume,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE newbie_quest_state (
            user_id INTEGER PRIMARY KEY,
            stage INTEGER NOT NULL DEFAULT 1,
            graduated INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE newbie_quest_tasks (
            user_id INTEGER NOT NULL,
            task_key TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            completed_at TEXT NOT NULL,
            PRIMARY KEY (user_id, task_key)
        );
        CREATE TABLE newbie_quest_events (
            user_id INTEGER NOT NULL,
            event_key TEXT NOT NULL,
            event_name TEXT NOT NULL,
            task_key TEXT,
            payload TEXT NOT NULL DEFAULT '{}',
            occurred_at TEXT NOT NULL,
            PRIMARY KEY (user_id, event_key)
        );
        CREATE TABLE legacy_reward_sentinel (
            user_id INTEGER PRIMARY KEY,
            coins INTEGER NOT NULL,
            marker TEXT NOT NULL
        );
        """
    )
    onboarding_migration.upgrade(conn)
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


def _insert_legacy(
    conn,
    user_id: int,
    *,
    stage: int,
    graduated: int,
    task_key: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO newbie_quest_state VALUES (?, ?, ?, ?, ?)",
        (user_id, stage, graduated, "2026-01-01T00:00:00", "2026-01-01T00:01:00"),
    )
    task_key = task_key or f"legacy_stage_{stage}"
    conn.execute(
        "INSERT INTO newbie_quest_tasks VALUES (?, ?, 'historical', '2026-01-01T00:02:00')",
        (user_id, task_key),
    )
    conn.execute(
        "INSERT INTO newbie_quest_events VALUES (?, ?, 'historical_task', ?, '{}', '2026-01-01T00:02:00')",
        (user_id, f"event:{user_id}", task_key),
    )
    conn.execute(
        "INSERT INTO legacy_reward_sentinel VALUES (?, 123, 'must-remain-byte-for-byte')",
        (user_id,),
    )


def _legacy_snapshot(conn, user_id: int):
    return {
        "state": tuple(
            conn.execute(
                "SELECT user_id,stage,graduated,created_at,updated_at "
                "FROM newbie_quest_state WHERE user_id=?",
                (user_id,),
            ).fetchone()
        ),
        "tasks": [
            tuple(row)
            for row in conn.execute(
                "SELECT user_id,task_key,source,completed_at "
                "FROM newbie_quest_tasks WHERE user_id=?",
                (user_id,),
            ).fetchall()
        ],
        "events": [
            tuple(row)
            for row in conn.execute(
                "SELECT user_id,event_key,event_name,task_key,payload,occurred_at "
                "FROM newbie_quest_events WHERE user_id=?",
                (user_id,),
            ).fetchall()
        ],
        "reward": tuple(
            conn.execute(
                "SELECT user_id,coins,marker FROM legacy_reward_sentinel WHERE user_id=?",
                (user_id,),
            ).fetchone()
        ),
    }


def test_stage_1_to_7_matrix_is_conservative_and_graduated_is_terminal():
    rows = legacy_stage_mapping_table()
    assert len(rows) == 14
    for stage in range(1, 8):
        incomplete = next(
            row for row in rows
            if row["legacy_stage"] == stage and row["legacy_graduated"] is False
        )
        graduated = next(
            row for row in rows
            if row["legacy_stage"] == stage and row["legacy_graduated"] is True
        )
        assert incomplete["classification"] == NO_SAFE_MAPPING
        assert incomplete["compatibility_path"] == LEGACY_GRANDFATHERED
        assert incomplete["target_status"] is None
        assert graduated["classification"] == DETERMINISTIC_V2_MAPPING
        assert graduated["target_status"] == COMPLETED
        assert graduated["target_step"] == STEP_NEXT_ACTION
        assert graduated["compatibility_path"] == V2_CANONICAL


def test_owner_supplied_188_row_shape_produces_24_terminal_and_164_grandfathered(connection):
    for user_id in range(1, 165):
        _insert_legacy(connection, user_id, stage=((user_id - 1) % 7) + 1, graduated=0)
    for user_id in range(165, 189):
        _insert_legacy(connection, user_id, stage=((user_id - 1) % 7) + 1, graduated=1)
    connection.commit()

    report = analyze_legacy_users(connection)
    assert report["legacy_user_count"] == 188
    assert report["deterministically_mappable_count"] == 24
    assert report["grandfathered_count"] == 164
    assert len(report["deterministic_user_ids"]) == 24
    assert len(report["grandfathered_user_ids"]) == 164


def test_unmappable_legacy_user_is_grandfathered_without_reset_or_reward(connection):
    _insert_legacy(connection, 1, stage=6, graduated=0)
    before = _legacy_snapshot(connection, 1)
    connection.commit()

    result = transition_existing_legacy_user(
        connection,
        1,
        dry_run=False,
        allow_write=True,
        owner_gate=GO_PRODUCTION_DB_MIGRATION,
    )

    assert result["ok"] is True
    assert result["classification"] == NO_SAFE_MAPPING
    assert result["action"] == "GRANDFATHER_LEGACY"
    assert result["legacy_mutated"] is False
    assert result["v2_mutated"] is False
    assert connection.execute(
        "SELECT COUNT(*) FROM wave2_onboarding_state_v1 WHERE user_id=1"
    ).fetchone()[0] == 0
    assert _legacy_snapshot(connection, 1) == before


def test_graduated_legacy_user_maps_to_completed_and_is_idempotent(connection):
    _insert_legacy(connection, 1, stage=4, graduated=1)
    before = _legacy_snapshot(connection, 1)
    connection.commit()

    plan = transition_existing_legacy_user(connection, 1)
    assert plan["ok"] is True
    assert plan["planned"] is True
    assert plan["v2_mutated"] is False
    assert connection.execute(
        "SELECT COUNT(*) FROM wave2_onboarding_state_v1 WHERE user_id=1"
    ).fetchone()[0] == 0

    blocked = transition_existing_legacy_user(connection, 1, dry_run=False)
    assert blocked["ok"] is False
    assert blocked["status_code"] == 403
    assert blocked["reason"] == "GO_PRODUCTION_DB_MIGRATION_REQUIRED"

    applied = transition_existing_legacy_user(
        connection,
        1,
        dry_run=False,
        allow_write=True,
        owner_gate=GO_PRODUCTION_DB_MIGRATION,
    )
    assert applied["ok"] is True
    assert applied["changed"] is True
    assert applied["v2_mutated"] is True
    state = connection.execute(
        "SELECT state_version,status,current_step,first_context_attempt_id "
        "FROM wave2_onboarding_state_v1 WHERE user_id=1"
    ).fetchone()
    assert tuple(state) == (1, COMPLETED, STEP_NEXT_ACTION, None)
    assert _legacy_snapshot(connection, 1) == before

    retry = transition_existing_legacy_user(
        connection,
        1,
        dry_run=False,
        allow_write=True,
        owner_gate=GO_PRODUCTION_DB_MIGRATION,
    )
    assert retry["ok"] is True
    assert retry["changed"] is False
    assert retry["reason"] == "EXISTING_V2_STATE_PRESERVED"
    assert _legacy_snapshot(connection, 1) == before


def test_existing_v2_progress_is_never_overwritten_by_legacy_terminal_mapping(connection):
    _insert_legacy(connection, 1, stage=7, graduated=1)
    assert start(connection, 1)["changed"] is True
    assert resume(connection, 1, expected_state_version=1)["changed"] is True
    before = tuple(
        connection.execute(
            "SELECT state_version,status,current_step,first_context_attempt_id "
            "FROM wave2_onboarding_state_v1 WHERE user_id=1"
        ).fetchone()
    )

    result = transition_existing_legacy_user(
        connection,
        1,
        dry_run=False,
        allow_write=True,
        owner_gate=GO_PRODUCTION_DB_MIGRATION,
    )
    assert result["ok"] is True
    assert result["changed"] is False
    assert result["reason"] == "EXISTING_V2_STATE_PRESERVED"
    after = tuple(
        connection.execute(
            "SELECT state_version,status,current_step,first_context_attempt_id "
            "FROM wave2_onboarding_state_v1 WHERE user_id=1"
        ).fetchone()
    )
    assert after == before
    assert after[1] == IN_PROGRESS


def test_bulk_transition_is_read_only_by_default_and_applies_only_terminal_rows(connection):
    _insert_legacy(connection, 1, stage=1, graduated=0)
    _insert_legacy(connection, 2, stage=7, graduated=1)
    before = {user_id: _legacy_snapshot(connection, user_id) for user_id in (1, 2)}
    connection.commit()

    plan = transition_existing_legacy_users(connection)
    assert plan["ok"] is True
    assert plan["changed"] is False
    assert [result["action"] for result in plan["results"]] == [
        "PLAN_TERMINAL_V2_MAPPING"
    ]
    assert connection.execute(
        "SELECT COUNT(*) FROM wave2_onboarding_state_v1"
    ).fetchone()[0] == 0

    applied = transition_existing_legacy_users(
        connection,
        dry_run=False,
        allow_write=True,
        owner_gate=GO_PRODUCTION_DB_MIGRATION,
    )
    assert applied["ok"] is True
    assert applied["changed"] is True
    assert tuple(
        connection.execute(
            "SELECT status,current_step FROM wave2_onboarding_state_v1 WHERE user_id=2"
        ).fetchone()
    ) == (COMPLETED, STEP_NEXT_ACTION)
    assert connection.execute(
        "SELECT COUNT(*) FROM wave2_onboarding_state_v1 WHERE user_id=1"
    ).fetchone()[0] == 0
    assert _legacy_snapshot(connection, 1) == before[1]
    assert _legacy_snapshot(connection, 2) == before[2]


def test_bulk_transition_requires_the_separate_migration_gate(connection):
    _insert_legacy(connection, 2, stage=7, graduated=1)
    connection.commit()

    blocked = transition_existing_legacy_users(connection, dry_run=False)

    assert blocked["ok"] is False
    assert blocked["changed"] is False
    assert blocked["results"][0]["status_code"] == 403
    assert blocked["results"][0]["reason"] == "GO_PRODUCTION_DB_MIGRATION_REQUIRED"
    assert connection.execute(
        "SELECT COUNT(*) FROM wave2_onboarding_state_v1"
    ).fetchone()[0] == 0


def test_grandfathered_compatibility_has_an_explicit_non_mutating_retirement_condition():
    pending = legacy_compatibility_retirement_condition(
        v2_cutover_enabled=False,
        preservation_audit_passed=False,
    )
    assert pending["retirable"] is False
    assert pending["legacy_mutated"] is False
    assert pending["deletion_authorized"] is False

    ready = legacy_compatibility_retirement_condition(
        v2_cutover_enabled=True,
        preservation_audit_passed=True,
        legacy_state_preserved=True,
    )
    assert ready["retirable"] is True
    assert ready["condition"] == "V2_CUTOVER_ENABLED_AND_PRESERVATION_AUDIT_PASSED"


def test_new_entrant_cutover_is_v2_only_and_does_not_authorize_legacy():
    result = new_entrant_cutover_contract(
        onboarding_required=1,
        onboarding_path=None,
        legacy_state_present=False,
    )
    assert result == {
        "entry_path": V2_CANONICAL,
        "legacy_allowed": False,
        "new_entrant": True,
        "reason": "NEW_ENTRANT_V2_ONLY",
    }

    existing = new_entrant_cutover_contract(
        onboarding_required=0,
        onboarding_path="newbie",
        legacy_state_present=True,
    )
    assert existing["entry_path"] == LEGACY_GRANDFATHERED
    assert existing["legacy_allowed"] is True
    assert existing["new_entrant"] is False


def test_puzzle_identity_hot_state_requires_exact_active_binding(monkeypatch):
    import identity_read_adapter

    class FakeReader:
        def __init__(self, _conn):
            pass

        def bootstrap_state(self):
            return {"tables_present": True, "hot": True}

        def key_for(self, _question_id):
            return type(
                "Key",
                (),
                {
                    "kind": identity_read_adapter.IdentityKeyKind.UUID,
                    "value": "11111111-1111-4111-8111-111111111111",
                    "attachable": True,
                    "reason": "exact single binding",
                    "candidates": (),
                },
            )()

    monkeypatch.setattr(identity_read_adapter, "BootstrapGatedIdentityReader", FakeReader)
    exact = resolve_onboarding_question_identity(object(), 31001)
    assert exact["status"] == "EXACT"
    assert exact["allowed"] is True
    assert exact["source_record_uuid"] == "11111111-1111-4111-8111-111111111111"

    class AmbiguousReader(FakeReader):
        def key_for(self, _question_id):
            return type(
                "Key",
                (),
                {
                    "kind": identity_read_adapter.IdentityKeyKind.UNRESOLVED,
                    "value": "31001",
                    "attachable": False,
                    "reason": "ambiguous alias",
                    "candidates": ("u1", "u2"),
                },
            )()

    monkeypatch.setattr(identity_read_adapter, "BootstrapGatedIdentityReader", AmbiguousReader)
    ambiguous = resolve_onboarding_question_identity(object(), 31001)
    assert ambiguous["status"] == "UNRESOLVED"
    assert ambiguous["allowed"] is False
    assert ambiguous["candidates"] == ["u1", "u2"]


def test_v2_migration_is_candidate_only_and_not_startup_wired():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "w2_a1_onboarding_v1" not in source
    assert onboarding_migration.validate_schema(sqlite3.connect(":memory:"))["present"] is False


def test_invalid_legacy_state_is_no_safe_mapping():
    result = classify_legacy_state(LegacyState(user_id=1, stage=9, graduated=False))
    assert result.classification == NO_SAFE_MAPPING
    assert result.compatibility_path == LEGACY_GRANDFATHERED
    assert result.target_status is None
