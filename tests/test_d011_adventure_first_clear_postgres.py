"""D011 disposable PostgreSQL proof for Adventure first-clear CAS behavior.

The test is deliberately opt-in.  It refuses to connect unless the caller
provides an explicitly disposable URL and an explicit safety marker.

Current F030/F028 Mapping A owns first-clear reward settlement as wardrobe
ownership.  These PostgreSQL tests retain the database-level clear CAS,
retry, and rollback proof and explicitly ensure the retired legacy coin grant
does not return; Mapping A ownership settlement is covered by the F028/F030
authority suites.
"""

from __future__ import annotations

import os
import threading

import pytest

import app as app_module
from db import PostgresConnectionWrapper


ZONE_KEY = "d011_zone"


def _postgres_url() -> str:
    url = os.environ.get("D011_ADVENTURE_POSTGRES_URL", "").strip()
    if not url or os.environ.get("D011_ADVENTURE_POSTGRES_DISPOSABLE") != "1":
        pytest.skip(
            "D011 PostgreSQL acceptance requires an explicit disposable URL "
            "and D011_ADVENTURE_POSTGRES_DISPOSABLE=1"
        )
    return url


def _connect(url: str) -> PostgresConnectionWrapper:
    import psycopg2
    from psycopg2.extras import DictCursor

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def _setup(url: str) -> None:
    conn = _connect(url)
    try:
        conn.execute("DROP TABLE IF EXISTS currency_log")
        conn.execute("DROP TABLE IF EXISTS user_stats")
        conn.execute("DROP TABLE IF EXISTS adventure_boss_progress")
        conn.execute("""
            CREATE TABLE adventure_boss_progress (
                user_id INTEGER NOT NULL,
                zone_key TEXT NOT NULL,
                cleared INTEGER NOT NULL DEFAULT 0,
                stars INTEGER NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                best_score INTEGER NOT NULL DEFAULT 0,
                cooldown_until_seen INTEGER NOT NULL DEFAULT 0,
                last_attempt_at TEXT,
                cleared_at TEXT,
                updated_at TEXT,
                PRIMARY KEY (user_id, zone_key)
            )
        """)
        conn.execute("""
            CREATE TABLE user_stats (
                user_id INTEGER PRIMARY KEY,
                coins INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE currency_log (
                id BIGSERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def disposable_postgres():
    url = _postgres_url()
    try:
        _setup(url)
    except Exception as exc:  # pragma: no cover - environment-specific
        pytest.fail(f"disposable PostgreSQL setup failed: {exc}")
    try:
        yield url
    finally:
        conn = _connect(url)
        try:
            conn.execute("DROP TABLE IF EXISTS currency_log")
            conn.execute("DROP TABLE IF EXISTS user_stats")
            conn.execute("DROP TABLE IF EXISTS adventure_boss_progress")
            conn.commit()
        finally:
            conn.close()


def _run_first_clear(url: str, barrier: threading.Barrier, outcomes, errors) -> None:
    conn = _connect(url)
    try:
        barrier.wait(timeout=10)
        result = app_module._adventure_boss_record_attempt(
            conn,
            9001,
            ZONE_KEY,
            True,
            20,
            0,
            "2026-08-24T12:00:00",
        )
        conn.commit()
        outcomes.append(result)
    except Exception as exc:  # pragma: no cover - assertion reports details
        conn.rollback()
        errors.append(exc)
    finally:
        conn.close()


def test_concurrent_first_clear_has_one_winner_and_no_legacy_coin_grant(disposable_postgres):
    barrier = threading.Barrier(2)
    outcomes = []
    errors = []
    threads = [
        threading.Thread(
            target=_run_first_clear,
            args=(disposable_postgres, barrier, outcomes, errors),
        )
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert errors == []
    assert len(outcomes) == 2
    assert sum(result["is_first_clear"] for result in outcomes) == 1
    assert sum(result["is_replay"] for result in outcomes) == 1

    conn = _connect(disposable_postgres)
    try:
        progress = conn.execute(
            "SELECT cleared, attempts FROM adventure_boss_progress "
            "WHERE user_id=? AND zone_key=?",
            (9001, ZONE_KEY),
        ).fetchone()
        reward = conn.execute(
            "SELECT COUNT(*) AS count, COALESCE(SUM(delta), 0) AS total "
            "FROM currency_log WHERE user_id=? AND reason=?",
            (9001, f"adventure_first_clear:{ZONE_KEY}"),
        ).fetchone()
        balance = conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=?", (9001,)
        ).fetchone()
    finally:
        conn.close()

    assert progress["cleared"] == 1
    assert progress["attempts"] == 2
    assert reward["count"] == 0
    assert reward["total"] == 0
    assert balance is None


def test_first_clear_retry_replays_without_legacy_coin_grant(disposable_postgres):
    conn = _connect(disposable_postgres)
    try:
        first = app_module._adventure_boss_record_attempt(
            conn, 9002, ZONE_KEY, True, 20, 0, "2026-08-24T12:00:00"
        )
        assert first == {
            "operation_id": "adventure:first_clear:9002:d011_zone",
            "is_replay": False,
            "is_first_clear": True,
        }
        conn.commit()

        retry = app_module._adventure_boss_record_attempt(
            conn, 9002, ZONE_KEY, True, 20, 0, "2026-08-24T12:01:00"
        )
        assert retry == {
            "operation_id": "adventure:first_clear:9002:d011_zone",
            "is_replay": True,
            "is_first_clear": False,
        }
        conn.commit()

        progress = conn.execute(
            "SELECT cleared, attempts FROM adventure_boss_progress "
            "WHERE user_id=? AND zone_key=?",
            (9002, ZONE_KEY),
        ).fetchone()
        reward = conn.execute(
            "SELECT COUNT(*) AS count FROM currency_log WHERE user_id=?", (9002,)
        ).fetchone()
    finally:
        conn.close()

    assert progress["cleared"] == 1
    assert progress["attempts"] == 2
    assert reward["count"] == 0


def test_rollback_removes_clear_and_legacy_coin_state(disposable_postgres):
    conn = _connect(disposable_postgres)
    try:
        with pytest.raises(RuntimeError, match="forced D011 rollback"):
            app_module._adventure_boss_record_attempt(
                conn, 9003, ZONE_KEY, True, 20, 0, "2026-08-24T12:00:00"
            )
            raise RuntimeError("forced D011 rollback")
    finally:
        conn.rollback()
        conn.close()

    conn = _connect(disposable_postgres)
    try:
        progress = conn.execute(
            "SELECT COUNT(*) AS count FROM adventure_boss_progress "
            "WHERE user_id=? AND zone_key=?",
            (9003, ZONE_KEY),
        ).fetchone()
        reward = conn.execute(
            "SELECT COUNT(*) AS count FROM currency_log WHERE user_id=?", (9003,)
        ).fetchone()
    finally:
        conn.close()

    assert progress["count"] == 0
    assert reward["count"] == 0
