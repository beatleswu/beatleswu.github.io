"""Fail-closed additive schema tests for Wave 2 onboarding state."""

from __future__ import annotations

import sqlite3

import pytest

from migrations import w2_a1_onboarding_v1 as migration


@pytest.fixture()
def connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def test_upgrade_creates_exact_table_and_contract(connection):
    result = migration.upgrade(connection)
    connection.commit()
    assert result["created"] == [migration.TABLE_NAME]
    assert migration.validate_schema(connection)["valid"] is True
    columns = connection.execute(
        f"PRAGMA table_info({migration.TABLE_NAME})"
    ).fetchall()
    assert [row[1] for row in columns] == [
        "user_id",
        "state_version",
        "status",
        "current_step",
        "first_context_attempt_id",
        "updated_at",
    ]
    assert columns[1][4] == "0"
    assert columns[5][4].upper() == "CURRENT_TIMESTAMP"
    connection.execute(
        f"""INSERT INTO {migration.TABLE_NAME}
            (user_id,status,current_step) VALUES (?,?,?)""",
        (7, "NOT_ENROLLED", "start"),
    )
    row = connection.execute(
        f"""SELECT state_version,first_context_attempt_id,updated_at
              FROM {migration.TABLE_NAME} WHERE user_id=7"""
    ).fetchone()
    assert row[0] == 0
    assert row[1] is None
    assert row[2]


def test_upgrade_is_idempotent_and_dry_run_is_pure(connection):
    dry_run = migration.upgrade(connection, dry_run=True)
    assert dry_run["dry_run"] is True
    assert migration.validate_schema(connection)["present"] is False
    first = migration.upgrade(connection)
    connection.commit()
    second = migration.apply(connection)
    assert first["created"] == [migration.TABLE_NAME]
    assert second["created"] == []
    assert second["valid"] is True


def test_unrelated_table_is_not_touched(connection):
    connection.execute("CREATE TABLE sentinel (id INTEGER PRIMARY KEY, value TEXT)")
    connection.execute("INSERT INTO sentinel VALUES (1, 'keep')")
    migration.upgrade(connection)
    assert connection.execute(
        "SELECT value FROM sentinel WHERE id=1"
    ).fetchone()[0] == "keep"


def _create_contract_table(connection, *, state_default="0", include_step_check=True, status_values=None):
    values = status_values or migration.STATUS_VALUES
    status_sql = ", ".join(f"'{value}'" for value in values)
    step_sql = ", ".join(f"'{value}'" for value in migration.STEP_VALUES)
    step_check = (
        f"CHECK (current_step IN ({step_sql}))"
        if include_step_check
        else ""
    )
    connection.execute(
        f"""CREATE TABLE {migration.TABLE_NAME} (
            user_id INTEGER PRIMARY KEY,
            state_version INTEGER NOT NULL DEFAULT {state_default}
                CHECK (state_version >= 0),
            status TEXT NOT NULL CHECK (status IN ({status_sql})),
            current_step TEXT NOT NULL {step_check},
            first_context_attempt_id TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )


def test_wrong_default_is_detected(connection):
    _create_contract_table(connection, state_default="1")
    with pytest.raises(migration.SchemaMismatch, match="default"):
        migration.validate_schema(connection)


def test_missing_current_step_check_is_detected(connection):
    _create_contract_table(connection, include_step_check=False)
    with pytest.raises(migration.SchemaMismatch, match="current_step CHECK"):
        migration.upgrade(connection)


def test_weakened_status_check_is_detected(connection):
    _create_contract_table(
        connection,
        status_values=("NOT_ENROLLED", "NOT_STARTED"),
    )
    with pytest.raises(migration.SchemaMismatch, match="status CHECK"):
        migration.validate_schema(connection)


def test_state_and_step_checks_reject_invalid_values(connection):
    migration.upgrade(connection)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            f"""INSERT INTO {migration.TABLE_NAME}
                (user_id,status,current_step) VALUES (?,?,?)""",
            (1, "NOT_ENROLLED", "zone3_arrival"),
        )
