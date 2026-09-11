"""Focused ACT-C D1 tests for canonical Coin reward settlement."""

from __future__ import annotations

from datetime import datetime
import sqlite3
import threading
from typing import Any

import pytest

from coin_reward_authority import (
    CAP_POLICY_EXEMPT_FRIEND_CHALLENGE,
    CAP_POLICY_NORMAL,
    DAILY_COIN_CAP,
    FRIEND_CHALLENGE_ALREADY_SETTLED,
    FRIEND_CHALLENGE_CURRENCY_REASON_PREFIX,
    FRIEND_CHALLENGE_SETTLED,
    FRIEND_CHALLENGE_SETTLED_NO_DETAIL,
    CoinRewardValidationError,
    grant_coins_in_transaction,
    settle_friend_challenge_reward_in_transaction,
    settle_rewards_sync_claim_in_transaction,
)


FIXED_NOW = datetime(2026, 9, 11, 12, 0, 0)
FRIEND_CLAIM_TABLE = "friend_challenge_reward_settlements"


class CountingConnection:
    """Caller-owned SQLite wrapper used to prove no transaction control leaks."""

    def __init__(self, raw: sqlite3.Connection):
        self._conn = raw
        self.commit_count = 0
        self.rollback_count = 0
        self.fail_currency_log = False

    def execute(self, statement: str, parameters: Any = ()):
        if self.fail_currency_log and "INSERT INTO currency_log" in statement:
            raise RuntimeError("simulated ledger failure")
        return self._conn.execute(statement, parameters)

    def commit(self) -> None:
        self.commit_count += 1
        self._conn.commit()

    def rollback(self) -> None:
        self.rollback_count += 1
        self._conn.rollback()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


def _connection(*, with_claims: bool = True) -> CountingConnection:
    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    conn = CountingConnection(raw)
    conn.execute(
        "CREATE TABLE user_stats ("
        "user_id INTEGER PRIMARY KEY, coins INTEGER NOT NULL DEFAULT 0, "
        "xp INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE currency_log ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
        "delta INTEGER NOT NULL, balance_after INTEGER NOT NULL, "
        "reason TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE reward_claimed ("
        "user_id INTEGER NOT NULL, stage_key TEXT NOT NULL, "
        "coins INTEGER NOT NULL DEFAULT 0, xp INTEGER NOT NULL DEFAULT 0, "
        "claimed_at TEXT, PRIMARY KEY(user_id, stage_key))"
    )
    if with_claims:
        _create_friend_challenge_claims(conn)
    conn.execute("INSERT INTO user_stats(user_id, coins, xp) VALUES(1, 0, 0)")
    conn.commit()
    return conn


def _create_friend_challenge_claims(conn: CountingConnection) -> None:
    conn.execute(
        f"""CREATE TABLE {FRIEND_CLAIM_TABLE} (
            challenge_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            settlement_status TEXT NOT NULL
                CHECK (settlement_status IN ('PENDING','SETTLED')),
            created_at TEXT NOT NULL,
            settled_at TEXT,
            PRIMARY KEY (challenge_id, user_id)
        )"""
    )
    conn.execute(
        f"CREATE INDEX idx_friend_challenge_reward_settlements_user_settled_at "
        f"ON {FRIEND_CLAIM_TABLE} (user_id, settled_at)"
    )


def _seed_ledger(conn: CountingConnection, amount: int, *, at: str = "2026-09-11T08:00:00") -> None:
    conn.execute("UPDATE user_stats SET coins=? WHERE user_id=1", (amount,))
    conn.execute(
        "INSERT INTO currency_log(user_id,delta,balance_after,reason,created_at) "
        "VALUES(?,?,?,?,?)",
        (1, amount, amount, "seed", at),
    )
    conn.commit()


def test_friend_challenge_claim_contract_has_no_reward_payload_columns() -> None:
    conn = _connection()
    columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({FRIEND_CLAIM_TABLE})").fetchall()
    }
    assert columns == {
        "challenge_id",
        "user_id",
        "settlement_status",
        "created_at",
        "settled_at",
    }
    assert "treasure_name" not in columns
    assert "result_payload" not in columns


def test_canonical_grant_writes_balance_and_ledger_without_transaction_control() -> None:
    conn = _connection()
    before_commit = conn.commit_count
    before_rollback = conn.rollback_count

    result = grant_coins_in_transaction(
        conn,
        user_id=1,
        server_computed_amount=25,
        server_owned_reason="reward_sync:stage:demo::LV1::1-2",
        cap_policy=CAP_POLICY_NORMAL,
        now=FIXED_NOW,
    )

    assert result.granted_amount == 25
    assert result.coins_before == 0
    assert result.coins_after == 25
    assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 25
    ledger = conn.execute(
        "SELECT delta,balance_after,reason FROM currency_log WHERE user_id=1"
    ).fetchall()
    assert [(row[0], row[1], row[2]) for row in ledger] == [
        (25, 25, "reward_sync:stage:demo::LV1::1-2")
    ]
    assert conn.commit_count == before_commit
    assert conn.rollback_count == before_rollback

    conn.commit()
    assert conn.commit_count == before_commit + 1


def test_normal_daily_cap_is_derived_from_ledger_and_never_overgrants() -> None:
    conn = _connection()
    _seed_ledger(conn, 490)

    first = grant_coins_in_transaction(
        conn,
        user_id=1,
        server_computed_amount=30,
        server_owned_reason="reward_sync:stage:cap-test",
        cap_policy=CAP_POLICY_NORMAL,
        now=FIXED_NOW,
    )
    second = grant_coins_in_transaction(
        conn,
        user_id=1,
        server_computed_amount=30,
        server_owned_reason="reward_sync:stage:cap-test-2",
        cap_policy=CAP_POLICY_NORMAL,
        now=FIXED_NOW,
    )

    assert first.granted_amount == 10
    assert first.daily_earned_after == DAILY_COIN_CAP
    assert second.granted_amount == 0
    assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 500
    assert conn.execute(
        "SELECT COALESCE(SUM(delta),0) FROM currency_log "
        "WHERE user_id=1 AND delta>0 AND created_at>=?",
        ("2026-09-11",),
    ).fetchone()[0] == DAILY_COIN_CAP


def test_normal_daily_cap_cannot_overgrant_under_concurrent_sqlite_transactions(tmp_path) -> None:
    """SQLite's writer lock is the portable test surrogate for row locking.

    One transaction may fail closed with ``database is locked`` because this
    service intentionally does not retry races.  What must never happen is
    two committed grants both using the same pre-cap total.
    """

    db_path = tmp_path / "coin-cap.sqlite"
    seed = sqlite3.connect(db_path)
    seed.row_factory = sqlite3.Row
    seed.executescript(
        """
        CREATE TABLE user_stats (user_id INTEGER PRIMARY KEY, coins INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE currency_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            delta INTEGER NOT NULL, balance_after INTEGER NOT NULL,
            reason TEXT NOT NULL, created_at TEXT NOT NULL
        );
        INSERT INTO user_stats(user_id, coins) VALUES(1, 490);
        INSERT INTO currency_log(user_id,delta,balance_after,reason,created_at)
            VALUES(1,490,490,'seed','2026-09-11T08:00:00');
        """
    )
    seed.commit()
    seed.close()

    barrier = threading.Barrier(2)
    committed: list[int] = []
    errors: list[Exception] = []
    lock = threading.Lock()

    def worker(name: str) -> None:
        conn = sqlite3.connect(db_path, timeout=0.1)
        try:
            conn.execute("BEGIN")
            barrier.wait(timeout=5)
            result = grant_coins_in_transaction(
                conn,
                user_id=1,
                server_computed_amount=30,
                server_owned_reason=f"reward_sync:stage:concurrent-{name}",
                cap_policy=CAP_POLICY_NORMAL,
                now=FIXED_NOW,
            )
            conn.commit()
            with lock:
                committed.append(result.granted_amount)
        except Exception as exc:  # the no-retry contract permits fail-closed locking
            conn.rollback()
            with lock:
                errors.append(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    verify = sqlite3.connect(db_path)
    coins = verify.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0]
    earned = verify.execute(
        "SELECT COALESCE(SUM(delta),0) FROM currency_log "
        "WHERE user_id=1 AND delta>0 AND created_at>=?",
        ("2026-09-11",),
    ).fetchone()[0]
    verify.close()
    assert len(committed) + len(errors) == 2
    assert committed  # at least one transaction must make progress
    assert sum(committed) <= 10
    assert coins <= DAILY_COIN_CAP
    assert earned <= DAILY_COIN_CAP


def test_friend_challenge_exemption_is_explicit_and_still_logs_currency() -> None:
    conn = _connection()
    _seed_ledger(conn, 490)

    result = grant_coins_in_transaction(
        conn,
        user_id=1,
        server_computed_amount=100,
        server_owned_reason="friend_challenge_reward:challenge:77:user:1",
        cap_policy=CAP_POLICY_EXEMPT_FRIEND_CHALLENGE,
        now=FIXED_NOW,
    )

    assert result.cap_policy == CAP_POLICY_EXEMPT_FRIEND_CHALLENGE
    assert result.granted_amount == 100
    assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 590
    row = conn.execute(
        "SELECT delta,balance_after,reason FROM currency_log "
        "WHERE user_id=1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert tuple(row) == (
        100,
        590,
        f"{FRIEND_CHALLENGE_CURRENCY_REASON_PREFIX}:challenge:77:user:1",
    )


def test_friend_challenge_exemption_does_not_reduce_future_normal_cap_headroom() -> None:
    conn = _connection()
    _seed_ledger(conn, 400)

    friend_result = grant_coins_in_transaction(
        conn,
        user_id=1,
        server_computed_amount=100,
        server_owned_reason="friend_challenge_reward:challenge:78:user:1",
        cap_policy=CAP_POLICY_EXEMPT_FRIEND_CHALLENGE,
        now=FIXED_NOW,
    )
    ordinary_result = grant_coins_in_transaction(
        conn,
        user_id=1,
        server_computed_amount=100,
        server_owned_reason="rewards_sync:stage:after-friend-challenge",
        cap_policy=CAP_POLICY_NORMAL,
        now=FIXED_NOW,
    )

    assert friend_result.granted_amount == 100
    assert ordinary_result.granted_amount == 100
    assert ordinary_result.daily_earned_before == 400
    assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 600
    assert conn.execute(
        "SELECT COALESCE(SUM(delta),0) FROM currency_log "
        "WHERE user_id=1 AND delta>0 AND created_at>=? "
        "AND reason NOT LIKE ?",
        ("2026-09-11", f"{FRIEND_CHALLENGE_CURRENCY_REASON_PREFIX}:%"),
    ).fetchone()[0] == DAILY_COIN_CAP
    assert conn.execute(
        "SELECT COALESCE(SUM(delta),0) FROM currency_log "
        "WHERE user_id=1 AND delta>0 AND created_at>=?",
        ("2026-09-11",),
    ).fetchone()[0] == 600


def test_friend_challenge_settlement_is_exactly_once_and_retry_has_no_detail() -> None:
    conn = _connection()
    callback_calls: list[int] = []

    def apply_other_rewards(db: Any) -> dict[str, Any]:
        callback_calls.append(1)
        db.execute("UPDATE user_stats SET xp=xp+5 WHERE user_id=1")
        return {"result": "win", "treasure_name": "treasure", "coins": 999999}

    first = settle_friend_challenge_reward_in_transaction(
        conn,
        challenge_id=77,
        user_id=1,
        server_computed_coins=25,
        apply_non_coin_rewards=apply_other_rewards,
        now=FIXED_NOW,
    )
    conn.commit()

    retry = settle_friend_challenge_reward_in_transaction(
        conn,
        challenge_id=77,
        user_id=1,
        server_computed_coins=None,
        apply_non_coin_rewards=lambda _db: pytest.fail("duplicate invoked downstream rewards"),
        now=FIXED_NOW,
    )

    assert first.status == FRIEND_CHALLENGE_SETTLED
    assert first.granted_coins == 25
    assert first.first_response_detail == {
        "result": "win",
        "treasure_name": "treasure",
        "coins": 999999,
    }
    assert retry.status == FRIEND_CHALLENGE_ALREADY_SETTLED
    assert retry.detail_status == FRIEND_CHALLENGE_SETTLED_NO_DETAIL
    assert retry.granted_coins is None
    assert retry.first_response_detail is None
    assert len(callback_calls) == 1
    assert tuple(conn.execute("SELECT coins,xp FROM user_stats WHERE user_id=1").fetchone()) == (25, 5)
    assert conn.execute(
        "SELECT COUNT(*) FROM currency_log WHERE user_id=1 "
        "AND reason='friend_challenge_reward:challenge:77:user:1'"
    ).fetchone()[0] == 1
    assert conn.execute(
        f"SELECT COUNT(*) FROM {FRIEND_CLAIM_TABLE} "
        "WHERE challenge_id=77 AND user_id=1 AND settlement_status='SETTLED'"
    ).fetchone()[0] == 1


def test_friend_challenge_failed_downstream_operation_rolls_back_claim_and_coin() -> None:
    conn = _connection()

    def fail_after_coin(_db: Any) -> dict[str, Any]:
        raise RuntimeError("downstream reward failed")

    with pytest.raises(RuntimeError, match="downstream reward failed"):
        settle_friend_challenge_reward_in_transaction(
            conn,
            challenge_id=88,
            user_id=1,
            server_computed_coins=25,
            apply_non_coin_rewards=fail_after_coin,
            now=FIXED_NOW,
        )
    conn.rollback()

    assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM currency_log").fetchone()[0] == 0
    assert conn.execute(
        f"SELECT COUNT(*) FROM {FRIEND_CLAIM_TABLE} WHERE challenge_id=88"
    ).fetchone()[0] == 0


def test_rewards_sync_claim_uses_legacy_stage_key_and_is_idempotent() -> None:
    conn = _connection(with_claims=False)

    first = settle_rewards_sync_claim_in_transaction(
        conn,
        user_id=1,
        stage_key="demo::LV1::1-2",
        server_computed_coins=50,
        server_computed_xp=20,
        now=FIXED_NOW,
    )
    conn.execute("UPDATE user_stats SET xp=xp+? WHERE user_id=1", (first.xp,))
    conn.commit()

    retry = settle_rewards_sync_claim_in_transaction(
        conn,
        user_id=1,
        stage_key="demo::LV1::1-2",
        server_computed_coins=999999,
        server_computed_xp=999999,
        now=FIXED_NOW,
    )

    assert first.status == "GRANTED"
    assert first.granted_coins == 50
    assert retry.status == "ALREADY_CLAIMED"
    assert retry.duplicate is True
    assert tuple(conn.execute("SELECT coins,xp FROM user_stats WHERE user_id=1").fetchone()) == (50, 20)
    assert conn.execute("SELECT COUNT(*) FROM reward_claimed").fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM currency_log WHERE reason='rewards_sync:stage:demo::LV1::1-2'"
    ).fetchone()[0] == 1


def test_rewards_sync_downstream_failure_rolls_back_claim_and_coin() -> None:
    conn = _connection(with_claims=False)

    with pytest.raises(RuntimeError, match="simulated downstream failure"):
        settle_rewards_sync_claim_in_transaction(
            conn,
            user_id=1,
            stage_key="demo::LV1::1-2",
            server_computed_coins=50,
            server_computed_xp=20,
            now=FIXED_NOW,
        )
        raise RuntimeError("simulated downstream failure")
    conn.rollback()

    assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM currency_log").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM reward_claimed").fetchone()[0] == 0


def test_client_shaped_amounts_are_rejected_and_callback_detail_cannot_set_coins() -> None:
    conn = _connection()
    with pytest.raises(CoinRewardValidationError):
        grant_coins_in_transaction(
            conn,
            user_id=1,
            server_computed_amount="50",  # JSON/client-shaped, not a server integer
            server_owned_reason="friend_challenge_reward:challenge:90:user:1",
            cap_policy=CAP_POLICY_EXEMPT_FRIEND_CHALLENGE,
            now=FIXED_NOW,
        )

    result = settle_friend_challenge_reward_in_transaction(
        conn,
        challenge_id=90,
        user_id=1,
        server_computed_coins=7,
        apply_non_coin_rewards=lambda _db: {"coins": 1000000},
        now=FIXED_NOW,
    )
    assert result.granted_coins == 7
    assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 7


def test_ledger_failure_leaves_balance_rollback_to_caller() -> None:
    conn = _connection()
    conn.fail_currency_log = True

    with pytest.raises(RuntimeError, match="simulated ledger failure"):
        grant_coins_in_transaction(
            conn,
            user_id=1,
            server_computed_amount=12,
            server_owned_reason="reward_sync:stage:ledger-failure",
            cap_policy=CAP_POLICY_NORMAL,
            now=FIXED_NOW,
        )
    conn.rollback()

    assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM currency_log").fetchone()[0] == 0
