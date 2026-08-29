"""B071A canonical historical leaderboard evidence tests."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from community_leaderboard_rewards import fetch_leaderboard_participant_rows
from migrations.historical_leaderboard_evidence_v1 import (
    SOURCE_PREFIX,
    TABLE_NAME,
    upgrade,
    validate_schema,
)
from tools.historical_leaderboard_restoration import restore_ledger


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            nickname TEXT,
            plan TEXT,
            is_admin INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE review_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            grade INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL,
            source TEXT,
            source_context TEXT
        )"""
    )
    conn.execute(
        "CREATE TABLE user_stats (user_id INTEGER PRIMARY KEY, rank_level TEXT)"
    )
    conn.execute(
        """CREATE TABLE player_appearance (
            user_id INTEGER PRIMARY KEY,
            character_key TEXT,
            combat_armor TEXT,
            combat_weapon TEXT,
            combat_cape TEXT,
            combat_offhand TEXT,
            combat_hat TEXT,
            combat_pet TEXT,
            combat_aura TEXT
        )"""
    )
    upgrade(conn)
    conn.commit()
    return conn


def _add_user(conn: sqlite3.Connection, user_id: int, name: str = "user") -> None:
    conn.execute(
        "INSERT INTO users(id, username, nickname, plan, is_admin) VALUES (?, ?, ?, ?, ?)",
        (user_id, f"{name}_{user_id}", name, "free", 0),
    )
    conn.execute(
        "INSERT INTO user_stats(user_id, rank_level) VALUES (?, ?)",
        (user_id, "LV1"),
    )
    conn.execute(
        "INSERT INTO player_appearance(user_id, character_key) VALUES (?, ?)",
        (user_id, "apprentice"),
    )


def _add_historical_row(
    conn: sqlite3.Connection,
    *,
    key: str,
    user_id: int,
    question_id: int,
    timestamp: str = "2026-08-24T00:00:00",
) -> None:
    evidence = json.dumps({"source": "B070"}, separators=(",", ":"))
    raw = getattr(conn, "_conn", conn)
    if not raw.__class__.__module__.startswith("sqlite3"):
        from psycopg2.extras import Json

        evidence = Json({"source": "B070"})
    conn.execute(
        f"""INSERT INTO {TABLE_NAME} (
            canonical_idempotency_key, user_id, question_id, source_prefix,
            canonical_source, legacy_event_id, legacy_source, event_timestamp,
            score, period_key, period_start_at, period_end_at, policy_version,
            reconciliation_class, evidence_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            key,
            user_id,
            question_id,
            SOURCE_PREFIX,
            SOURCE_PREFIX + key,
            f"review_log:{question_id}",
            "practice",
            timestamp,
            1,
            "2026-W35",
            "2026-08-24T00:00:00+08:00",
            "2026-08-31T00:00:00+08:00",
            "POLICY_3_PLAYER_PRESERVATION",
            "C_LEGACY_ONLY_BUT_PLAUSIBLE",
            evidence,
            "2026-08-30T00:00:00+00:00",
        ),
    )


def test_schema_is_additive_and_source_score_constraints_are_fail_closed():
    conn = _db()
    status = validate_schema(conn)
    assert status["present"] is True
    assert status["missing"] == []
    assert set(status["columns"]) == {
        "canonical_idempotency_key", "user_id", "question_id", "source_prefix",
        "canonical_source", "legacy_event_id", "legacy_source", "event_timestamp",
        "score", "period_key", "period_start_at", "period_end_at", "policy_version",
        "reconciliation_class", "evidence_json", "created_at",
    }
    _add_user(conn, 1)
    _add_historical_row(
        conn,
        key="b069:weekly:2026-W35:user:1:question:1",
        user_id=1,
        question_id=1,
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            f"UPDATE {TABLE_NAME} SET source_prefix='practice' "
            "WHERE canonical_idempotency_key=?",
            ("b069:weekly:2026-W35:user:1:question:1",),
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            f"UPDATE {TABLE_NAME} SET score=2 "
            "WHERE canonical_idempotency_key=?",
            ("b069:weekly:2026-W35:user:1:question:1",),
        )


def test_live_consumer_unions_historical_sink_and_deduplicates_trusted_overlap():
    conn = _db()
    _add_user(conn, 1, "historical")
    conn.execute(
        """INSERT INTO review_log(
            user_id, question_id, grade, reviewed_at, source, source_context
        ) VALUES (?, ?, ?, ?, ?, ?)""",
            (1, 100, 3, "2026-08-24T00:00:00", "rt:baseline", ""),
    )
    # This overlap is intentionally seeded directly to prove the consumer's
    # UNION-by-(user, question) guard even if a legacy database contains it.
    _add_historical_row(
        conn,
        key="b069:weekly:2026-W35:user:1:question:100",
        user_id=1,
        question_id=100,
    )
    _add_historical_row(
        conn,
        key="b069:weekly:2026-W35:user:1:question:101",
        user_id=1,
        question_id=101,
    )
    conn.commit()

    rows = fetch_leaderboard_participant_rows(
        conn,
        "2026-08-23T16:00:00",
        "2026-08-30T16:00:00",
    )
    assert len(rows) == 1
    assert rows[0]["id"] == 1
    assert rows[0]["score"] == 2


def test_exact_b070_ledger_import_and_live_consumer_contract():
    ledger_path = os.environ.get("B070_LEADERBOARD_LEDGER_PATH")
    if not ledger_path:
        pytest.skip("B070_LEADERBOARD_LEDGER_PATH is required for the full exact-ledger fixture")
    path = Path(ledger_path)
    assert path.is_file()
    ledger = json.loads(path.read_text(encoding="utf-8"))
    restored = [row for row in ledger["score_units"] if row["restore"] is True]
    user_ids = sorted({int(row["user_id"]) for row in restored})

    conn = _db()
    for user_id in user_ids:
        _add_user(conn, user_id, "ledger")
    # Equivalent trusted baseline for the two B070 critical-user assertions;
    # these question IDs are intentionally outside the reviewed ledger.
    conn.executemany(
        """INSERT INTO review_log(
            user_id, question_id, grade, reviewed_at, source, source_context
        ) VALUES (?, ?, ?, ?, ?, ?)""",
        [
            (991283, 9000000 + index, 3, "2026-08-24T00:00:00", "rt:baseline", "")
            for index in range(12)
        ],
    )
    conn.commit()

    dry_run = restore_ledger(conn, path, dry_run=True)
    assert dry_run["insertable_rows"] == 7436
    assert dry_run["insertable_score_total"] == 7436

    inserted = restore_ledger(conn, path)
    assert inserted["inserted_rows"] == 7436
    assert inserted["inserted_score_total"] == 7436
    assert inserted["final_rows"] == 7436
    assert inserted["final_score_total"] == 7436
    assert inserted["final_user_count"] == 27

    rerun = restore_ledger(conn, path)
    assert rerun["insertable_rows"] == 0
    assert rerun["insertable_score_total"] == 0
    assert rerun["inserted_rows"] == 0
    assert rerun["inserted_score_total"] == 0

    rows = fetch_leaderboard_participant_rows(
        conn,
        "2026-08-23T16:00:00",
        "2026-08-30T16:00:00",
    )
    by_user = {int(row["id"]): row for row in rows}
    assert by_user[991283]["score"] == 2829
    assert by_user[991260]["score"] == 1281


def _postgres_db(database_url):
    import psycopg2
    from psycopg2.extras import DictCursor

    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(database_url)
    raw.autocommit = False
    raw.cursor_factory = DictCursor
    conn = PostgresConnectionWrapper(raw, pooled=False)
    conn.execute(
        """CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            nickname TEXT,
            plan TEXT,
            is_admin INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE review_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            grade INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL,
            source TEXT,
            source_context TEXT
        )"""
    )
    conn.execute("CREATE TABLE user_stats (user_id INTEGER PRIMARY KEY, rank_level TEXT)")
    conn.execute(
        """CREATE TABLE player_appearance (
            user_id INTEGER PRIMARY KEY,
            character_key TEXT,
            combat_armor TEXT,
            combat_weapon TEXT,
            combat_cape TEXT,
            combat_offhand TEXT,
            combat_hat TEXT,
            combat_pet TEXT,
            combat_aura TEXT
        )"""
    )
    upgrade(conn)
    conn.commit()
    return conn


def test_postgres_schema_and_live_consumer_are_compatible_with_production_types():
    from postgres_test_harness import disposable_postgres

    with disposable_postgres(name_prefix="go-odyssey-b071a-pg") as database:
        conn = _postgres_db(database["database_url"])
        try:
            _add_user(conn, 1, "postgres")
            conn.execute(
                """INSERT INTO review_log(
                    user_id, question_id, grade, reviewed_at, source, source_context
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (1, 700, 3, "2026-08-24T00:00:00", "rt:baseline", ""),
            )
            _add_historical_row(
                conn,
                key="b069:weekly:2026-W35:user:1:question:701",
                user_id=1,
                question_id=701,
            )
            conn.commit()
            assert validate_schema(conn)["missing"] == []
            rows = fetch_leaderboard_participant_rows(
                conn,
                "2026-08-23T16:00:00",
                "2026-08-30T16:00:00",
            )
            assert len(rows) == 1
            assert rows[0]["score"] == 2
        finally:
            conn.close()


def test_postgres_exact_b070_ledger_import_is_atomic_and_idempotent():
    ledger_path = os.environ.get("B070_LEADERBOARD_LEDGER_PATH")
    if not ledger_path:
        pytest.skip("B070_LEADERBOARD_LEDGER_PATH is required for the full exact-ledger fixture")
    path = Path(ledger_path)
    ledger = json.loads(path.read_text(encoding="utf-8"))
    restored = [row for row in ledger["score_units"] if row["restore"] is True]
    user_ids = sorted({int(row["user_id"]) for row in restored})

    from postgres_test_harness import disposable_postgres

    with disposable_postgres(name_prefix="go-odyssey-b071a-ledger") as database:
        conn = _postgres_db(database["database_url"])
        try:
            for user_id in user_ids:
                _add_user(conn, user_id, "ledger")
            with conn.cursor() as cursor:
                cursor.executemany(
                    """INSERT INTO review_log(
                        user_id, question_id, grade, reviewed_at, source, source_context
                    ) VALUES (%s, %s, %s, %s, %s, %s)""",
                    [
                        (991283, 9100000 + index, 3, "2026-08-24T00:00:00", "rt:baseline", "")
                        for index in range(12)
                    ],
                )
            conn.commit()

            result = restore_ledger(conn, path)
            assert result["inserted_rows"] == 7436
            assert result["inserted_score_total"] == 7436
            assert result["final_user_count"] == 27
            rerun = restore_ledger(conn, path)
            assert rerun["insertable_rows"] == 0
            assert rerun["insertable_score_total"] == 0
            assert rerun["inserted_rows"] == 0
            assert rerun["inserted_score_total"] == 0
        finally:
            conn.close()
