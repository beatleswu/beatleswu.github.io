"""Production-dialect concurrency evidence for ACT-C D1."""

from __future__ import annotations

from datetime import datetime
from threading import Event, Thread
import time
from typing import Any

import pytest

from coin_reward_authority import (
    CAP_POLICY_NORMAL,
    DAILY_COIN_CAP,
    grant_coins_in_transaction,
)
from postgres_test_harness import disposable_postgres


FIXED_NOW = datetime(2026, 9, 11, 12, 0, 0)


def _open(database_url: str):
    import psycopg2
    from psycopg2.extras import DictCursor

    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(database_url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def _reset(database_url: str):
    conn = _open(database_url)
    conn.execute("DROP TABLE IF EXISTS currency_log, user_stats CASCADE")
    conn.execute(
        """CREATE TABLE user_stats (
            user_id BIGINT PRIMARY KEY,
            coins BIGINT NOT NULL DEFAULT 0,
            xp BIGINT NOT NULL DEFAULT 0
        )"""
    )
    conn.execute(
        """CREATE TABLE currency_log (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            delta BIGINT NOT NULL,
            balance_after BIGINT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute("INSERT INTO user_stats(user_id, coins) VALUES(1, 400)")
    conn.execute(
        """INSERT INTO currency_log
            (user_id, delta, balance_after, reason, created_at)
            VALUES(1, 400, 400, 'seed', '2026-09-11T08:00:00')"""
    )
    conn.commit()
    return conn


def _wait_for_lock(observer: Any, backend_pid: int, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = observer.execute(
            """SELECT state, wait_event_type, wait_event
                 FROM pg_stat_activity
                WHERE pid=?""",
            (backend_pid,),
        ).fetchone()
        if row and row["state"] == "active" and row["wait_event_type"] == "Lock":
            return dict(row)
        time.sleep(0.05)
    raise AssertionError(f"backend {backend_pid} never waited on a PostgreSQL lock")


def test_postgres_concurrent_normal_cap_serializes_and_keeps_ledger_coherent() -> None:
    """Two real PostgreSQL transactions contend on the intended row lock.

    Transaction A pre-locks the balance row.  Transaction B is then observed
    in PostgreSQL's lock wait state before A grants and commits.  B resumes,
    re-reads the committed ledger total, and receives only the remaining
    amount.  No authority retry is used.
    """

    with disposable_postgres(name_prefix="go-odyssey-act-c-d1-pg-cap") as postgres:
        conn_a = _reset(postgres["database_url"])
        conn_b = _open(postgres["database_url"])
        observer = _open(postgres["database_url"])
        b_ready = Event()
        b_go = Event()
        b_state: dict[str, Any] = {}

        conn_a.execute("BEGIN")
        conn_a.execute(
            "SELECT coins FROM user_stats WHERE user_id=? FOR UPDATE",
            (1,),
        )

        def run_b() -> None:
            try:
                conn_b.execute("BEGIN")
                b_state["pid"] = int(
                    conn_b.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
                )
                b_ready.set()
                assert b_go.wait(timeout=10)
                b_state["result"] = grant_coins_in_transaction(
                    conn_b,
                    user_id=1,
                    server_computed_amount=100,
                    server_owned_reason="rewards_sync:stage:pg-concurrent-b",
                    cap_policy=CAP_POLICY_NORMAL,
                    now=FIXED_NOW,
                )
                conn_b.commit()
            except Exception as exc:
                b_state["error"] = exc
                conn_b.rollback()

        worker = Thread(target=run_b, name="act-c-pg-cap-b", daemon=True)
        worker.start()
        assert b_ready.wait(timeout=10)
        b_go.set()

        try:
            lock_wait = _wait_for_lock(observer, b_state["pid"])
            a_result = grant_coins_in_transaction(
                conn_a,
                user_id=1,
                server_computed_amount=100,
                server_owned_reason="rewards_sync:stage:pg-concurrent-a",
                cap_policy=CAP_POLICY_NORMAL,
                now=FIXED_NOW,
            )
            conn_a.commit()
            worker.join(timeout=10)
            assert not worker.is_alive()
            assert "error" not in b_state, b_state.get("error")
            b_result = b_state["result"]
        finally:
            if worker.is_alive():
                conn_a.rollback()
                worker.join(timeout=10)
            else:
                conn_a.rollback()
            observer.rollback()
            observer.close()
            conn_b.close()
            conn_a.close()

        check = _open(postgres["database_url"])
        try:
            row = check.execute(
                "SELECT coins FROM user_stats WHERE user_id=?", (1,)
            ).fetchone()
            assert lock_wait["wait_event_type"] == "Lock"
            assert a_result.granted_amount == 100
            assert b_result.granted_amount == 0
            assert a_result.coins_after == 500
            assert b_result.daily_earned_before == DAILY_COIN_CAP
            assert row["coins"] == 500
            ledger = check.execute(
                """SELECT delta, balance_after, reason
                     FROM currency_log
                    WHERE user_id=? AND delta>0 AND created_at>=?
                    ORDER BY id""",
                (1, "2026-09-11"),
            ).fetchall()
            assert [tuple(item) for item in ledger] == [
                (400, 400, "seed"),
                (100, 500, "rewards_sync:stage:pg-concurrent-a"),
            ]
            ordinary_earned = check.execute(
                """SELECT COALESCE(SUM(delta), 0) AS earned
                     FROM currency_log
                    WHERE user_id=? AND delta>0 AND created_at>=?
                      AND reason NOT LIKE ?""",
                (1, "2026-09-11", "friend_challenge_reward:%"),
            ).fetchone()["earned"]
            assert ordinary_earned == DAILY_COIN_CAP
        finally:
            check.close()


def test_postgres_caller_rollback_removes_balance_and_ledger_together() -> None:
    with disposable_postgres(name_prefix="go-odyssey-act-c-d1-pg-rollback") as postgres:
        conn = _reset(postgres["database_url"])
        conn.execute("DELETE FROM currency_log WHERE user_id=?", (1,))
        conn.execute("UPDATE user_stats SET coins=0 WHERE user_id=?", (1,))
        conn.commit()

        try:
            grant_coins_in_transaction(
                conn,
                user_id=1,
                server_computed_amount=25,
                server_owned_reason="rewards_sync:stage:pg-rollback",
                cap_policy=CAP_POLICY_NORMAL,
                now=FIXED_NOW,
            )
            raise RuntimeError("forced caller rollback")
        except RuntimeError as exc:
            assert str(exc) == "forced caller rollback"
            conn.rollback()

        row = conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=?", (1,)
        ).fetchone()
        assert row["coins"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM currency_log WHERE user_id=?", (1,)
        ).fetchone()["count"] == 0
        conn.close()
