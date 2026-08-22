"""Focused D5A tests for the shared transactional outbox foundation."""

from __future__ import annotations

import json
import os
import sqlite3

import pytest

from event_outbox import (
    DuplicateOutboxEvent,
    OutboxValidationError,
    append_event,
    get_event_by_idempotency_key,
)
from migrations.domain_event_outbox_v1 import (
    INDEX_SPECS,
    TABLE_NAME,
    downgrade_for_isolated_test,
    upgrade,
    validate_schema,
)


def _sqlite_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    upgrade(conn)
    conn.commit()
    return conn


def _append(conn, *, player_id="player-1", event_type="ITEM_ACQUISITION", key="key-1", outcome="SUCCESS", payload=None):
    return append_event(
        conn,
        event_type=event_type,
        player_id=player_id,
        lineage_id="lineage-1",
        idempotency_key=key,
        outcome=outcome,
        payload=payload or {"operation": "grant", "value": 1},
        occurred_at="2026-08-22T00:00:00+00:00",
    )


def test_schema_creation_has_exact_envelope_and_v1_indexes():
    conn = _sqlite_db()
    status = validate_schema(conn)
    assert status["missing"] == []
    assert status["columns"] == sorted(
        {
            "event_id", "schema_version", "event_type", "player_id",
            "occurred_at", "lineage_id", "source_event_id",
            "idempotency_key", "outcome", "payload", "created_at",
            "published_at",
        }
    )
    assert set(status["indexes"]) == {name for name, _columns in INDEX_SPECS}
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (TABLE_NAME,),
    ).fetchone()[0] == 1


def test_successful_event_insert_and_published_at_unset():
    conn = _sqlite_db()
    result = _append(conn)
    row = conn.execute(
        f"SELECT event_id, outcome, published_at FROM {TABLE_NAME} WHERE event_id=?",
        (result["event_id"],),
    ).fetchone()
    assert row["event_id"] == result["event_id"]
    assert row["outcome"] == "SUCCESS"
    assert row["published_at"] is None


def test_payload_json_round_trip_preserves_nested_unicode():
    conn = _sqlite_db()
    payload = {"operation": "grant", "metadata": {"label": "題數券", "values": [5, 10]}}
    result = _append(conn, payload=payload)
    raw = conn.execute(
        f"SELECT payload FROM {TABLE_NAME} WHERE event_id=?",
        (result["event_id"],),
    ).fetchone()[0]
    assert json.loads(raw) == payload


def test_payload_rejects_sensitive_provider_or_secret_fields():
    conn = _sqlite_db()
    with pytest.raises(OutboxValidationError, match="forbidden sensitive field"):
        _append(conn, payload={"operation": "grant", "provider_reference": "safe-ref", "raw_payload": {}})


def test_same_player_family_and_key_rejects_and_recovers_original():
    conn = _sqlite_db()
    first = _append(conn, key="same-key")
    with pytest.raises(DuplicateOutboxEvent) as exc_info:
        _append(conn, key="same-key", payload={"operation": "different"})
    assert exc_info.value.existing_event_id == first["event_id"]
    assert get_event_by_idempotency_key(
        conn, player_id="player-1", event_type="ITEM_ACQUISITION", idempotency_key="same-key"
    )["event_id"] == first["event_id"]


def test_same_key_across_players_is_allowed():
    conn = _sqlite_db()
    first = _append(conn, player_id="player-1", key="shared-key")
    second = _append(conn, player_id="player-2", key="shared-key")
    assert first["event_id"] != second["event_id"]


def test_same_player_key_across_event_families_is_allowed():
    conn = _sqlite_db()
    first = _append(conn, event_type="ITEM_ACQUISITION", key="shared-key")
    second = _append(conn, event_type="GACHA_DRAW", key="shared-key")
    assert first["event_id"] != second["event_id"]


def test_business_fixture_and_outbox_rollback_together():
    conn = _sqlite_db()
    conn.execute("CREATE TABLE fixture_mutation (id TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.commit()
    conn.execute("INSERT INTO fixture_mutation(id, value) VALUES (?, ?)", ("mutation-1", "pending"))
    _append(conn, key="rollback-key")
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM fixture_mutation").fetchone()[0] == 0
    assert conn.execute(
        f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE idempotency_key=?", ("rollback-key",)
    ).fetchone()[0] == 0


def test_business_fixture_and_outbox_commit_together():
    conn = _sqlite_db()
    conn.execute("CREATE TABLE fixture_mutation (id TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.commit()
    conn.execute("INSERT INTO fixture_mutation(id, value) VALUES (?, ?)", ("mutation-1", "committed"))
    result = _append(conn, key="commit-key")
    conn.commit()
    assert conn.execute("SELECT value FROM fixture_mutation WHERE id=?", ("mutation-1",)).fetchone()[0] == "committed"
    assert conn.execute(
        f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE event_id=?", (result["event_id"],)
    ).fetchone()[0] == 1


@pytest.mark.parametrize("outcome", ["FAILED", "UNKNOWN", "UNVERIFIED"])
def test_fail_closed_outcomes_are_valid(outcome):
    conn = _sqlite_db()
    result = _append(conn, key=f"{outcome}-key", outcome=outcome)
    assert result["outcome"] == outcome


def test_append_only_surface_has_no_generic_payload_update_api():
    import event_outbox

    assert not hasattr(event_outbox, "update_event")
    assert not hasattr(event_outbox, "delete_event")


def test_isolated_schema_downgrade_drops_only_outbox_table():
    conn = _sqlite_db()
    conn.execute("CREATE TABLE unrelated_fixture (id INTEGER PRIMARY KEY)")
    downgrade_for_isolated_test(conn)
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (TABLE_NAME,),
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='unrelated_fixture'"
    ).fetchone()[0] == 1


def test_disposable_postgres_schema_and_transaction_contract():
    url = os.environ.get("D5A_OUTBOX_POSTGRES_URL")
    if not url or os.environ.get("D5A_OUTBOX_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    from urllib.parse import urlsplit

    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "test" not in database and "d5a" not in database:
        pytest.skip("refusing PostgreSQL URL without a test/d5a database name")

    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw_conn = psycopg2.connect(url)
    raw_conn.cursor_factory = DictCursor
    conn = PostgresConnectionWrapper(raw_conn)
    try:
        downgrade_for_isolated_test(conn)
        conn.commit()
        status = upgrade(conn)
        assert status["missing"] == []
        assert set(status["indexes"]) == {name for name, _columns in INDEX_SPECS}
        type_rows = conn.execute(
            """SELECT column_name, data_type
                 FROM information_schema.columns
                WHERE table_schema='public' AND table_name=?""",
            (TABLE_NAME,),
        ).fetchall()
        types = {row["column_name"]: row["data_type"] for row in type_rows}
        assert types["payload"] == "jsonb"
        assert types["occurred_at"] == "timestamp with time zone"
        assert types["created_at"] == "timestamp with time zone"

        conn.execute("CREATE TABLE d5a_business_fixture (id TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.commit()

        first = _append(conn, key="pg-key")
        conn.commit()
        assert conn.execute(
            f"SELECT payload->>'operation' AS operation FROM {TABLE_NAME} WHERE event_id=?",
            (first["event_id"],),
        ).fetchone()["operation"] == "grant"
        assert conn.execute(
            f"SELECT published_at FROM {TABLE_NAME} WHERE event_id=?",
            (first["event_id"],),
        ).fetchone()["published_at"] is None

        conn.execute(
            "INSERT INTO d5a_business_fixture(id, value) VALUES (?, ?)",
            ("duplicate-before", "kept"),
        )
        with pytest.raises(DuplicateOutboxEvent):
            _append(conn, key="pg-key")
        conn.execute(
            "INSERT INTO d5a_business_fixture(id, value) VALUES (?, ?)",
            ("duplicate-after", "still-kept"),
        )
        conn.commit()
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM d5a_business_fixture"
        ).fetchone()["n"] == 2

        same_key_other_player = _append(conn, player_id="player-2", key="pg-shared-key")
        same_key_other_family = _append(conn, event_type="GACHA_DRAW", key="pg-shared-key")
        unknown = _append(conn, key="pg-unknown", outcome="UNKNOWN")
        unverified = _append(conn, key="pg-unverified", outcome="UNVERIFIED")
        conn.commit()
        assert same_key_other_player["event_id"] != same_key_other_family["event_id"]
        assert conn.execute(
            f"SELECT COUNT(*) AS n FROM {TABLE_NAME} WHERE event_id IN (?, ?, ?)",
            (unknown["event_id"], unverified["event_id"], same_key_other_player["event_id"]),
        ).fetchone()["n"] == 3

        conn.execute(
            "INSERT INTO d5a_business_fixture(id, value) VALUES (?, ?)",
            ("rollback", "should-disappear"),
        )
        rollback_event = _append(conn, key="pg-rollback")
        conn.rollback()
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM d5a_business_fixture WHERE id=?", ("rollback",)
        ).fetchone()["n"] == 0
        assert conn.execute(
            f"SELECT COUNT(*) AS n FROM {TABLE_NAME} WHERE event_id=?",
            (rollback_event["event_id"],),
        ).fetchone()["n"] == 0

        conn.execute(
            "INSERT INTO d5a_business_fixture(id, value) VALUES (?, ?)",
            ("commit", "should-remain"),
        )
        commit_event = _append(conn, key="pg-commit")
        conn.commit()
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM d5a_business_fixture WHERE id=?", ("commit",)
        ).fetchone()["n"] == 1
        assert conn.execute(
            f"SELECT COUNT(*) AS n FROM {TABLE_NAME} WHERE event_id=?",
            (commit_event["event_id"],),
        ).fetchone()["n"] == 1
    finally:
        conn.rollback()
        conn.execute("DROP TABLE IF EXISTS d5a_business_fixture")
        downgrade_for_isolated_test(conn)
        conn.commit()
        conn.close()
