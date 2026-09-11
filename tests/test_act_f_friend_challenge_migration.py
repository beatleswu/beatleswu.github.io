"""ACT-F evidence for the Friend Challenge migration candidate."""

from __future__ import annotations

from datetime import datetime
import inspect
import sqlite3

import pytest

from coin_reward_authority import (
    FRIEND_CHALLENGE_SETTLED,
    settle_friend_challenge_reward_in_transaction,
)
from migrations import friend_challenge_reward_settlements_v1 as migration


FIXED_NOW = datetime(2026, 9, 11, 12, 0, 0)


@pytest.fixture()
def connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _create_reward_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE user_stats (
            user_id INTEGER PRIMARY KEY,
            coins INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE currency_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            delta INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        INSERT INTO user_stats(user_id, coins) VALUES (1, 0);
        """
    )


def test_migration_is_additive_exact_and_catalog_guarded(connection):
    dry_run = migration.upgrade(connection, dry_run=True)
    assert dry_run["dry_run"] is True
    assert dry_run["planned_create"] == [migration.TABLE_NAME]
    assert migration.validate_schema(connection)["present"] is False

    result = migration.upgrade(connection)
    assert result["created"] == [migration.TABLE_NAME]
    connection.commit()

    assert migration.validate_schema(connection)["valid"] is True
    columns = connection.execute(
        f"PRAGMA table_info({migration.TABLE_NAME})"
    ).fetchall()
    assert [(row[1], row[2], row[3]) for row in columns] == [
        ("challenge_id", "INTEGER", 1),
        ("user_id", "INTEGER", 1),
        ("settlement_status", "TEXT", 1),
        ("created_at", "TEXT", 1),
        ("settled_at", "TEXT", 0),
    ]
    assert {
        row[1]
        for row in connection.execute(
            f"PRAGMA index_list({migration.TABLE_NAME})"
        ).fetchall()
    } == {migration.INDEX_SPECS[0][0], "sqlite_autoindex_friend_challenge_reward_settlements_1"}


def test_migration_is_idempotent_and_rejects_weakened_existing_schema(connection):
    first = migration.upgrade(connection)
    connection.commit()
    second = migration.upgrade(connection)
    assert first["created"] == [migration.TABLE_NAME]
    assert second["created"] == []
    assert second["valid"] is True

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            f"INSERT INTO {migration.TABLE_NAME} "
            "(challenge_id,user_id,settlement_status,created_at) "
            "VALUES (1,1,'INVALID','2026-09-11T12:00:00')"
        )
    connection.rollback()


def test_migration_has_no_transaction_control():
    source = inspect.getsource(migration)
    assert ".commit(" not in source
    assert ".rollback(" not in source


def test_failed_caller_transaction_rolls_back_pending_claim_and_allows_retry(connection):
    migration.upgrade(connection)
    _create_reward_tables(connection)
    connection.commit()

    connection.execute("BEGIN")

    def fail_after_claim(_conn):
        raise RuntimeError("downstream reward failed")

    with pytest.raises(RuntimeError, match="downstream reward failed"):
        settle_friend_challenge_reward_in_transaction(
            connection,
            challenge_id=901,
            user_id=1,
            server_computed_coins=25,
            apply_non_coin_rewards=fail_after_claim,
            now=FIXED_NOW,
        )
    # ACT-A owns this rollback.  The failed transaction cannot commit its
    # temporary PENDING reservation, so a legitimate retry is not blocked.
    connection.rollback()
    assert connection.execute(
        f"SELECT COUNT(*) FROM {migration.TABLE_NAME}"
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT coins FROM user_stats WHERE user_id=1"
    ).fetchone()[0] == 0

    retried = settle_friend_challenge_reward_in_transaction(
        connection,
        challenge_id=901,
        user_id=1,
        server_computed_coins=25,
        apply_non_coin_rewards=lambda _conn: {"result": "win"},
        now=FIXED_NOW,
    )
    connection.commit()
    assert retried.status == FRIEND_CHALLENGE_SETTLED
    assert connection.execute(
        f"SELECT settlement_status FROM {migration.TABLE_NAME} "
        "WHERE challenge_id=901 AND user_id=1"
    ).fetchone()[0] == "SETTLED"
