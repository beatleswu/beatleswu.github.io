from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

import pytest

from login_journey_authority import (
    LoginEventIdentityConflict,
    LoginEventValidationError,
    get_login_state,
    record_authenticated_login,
)
from migrations.login_journey_v1 import (
    JOURNEY_TABLE_NAME,
    LOGIN_DAYS_TABLE_NAME,
    STREAK_TABLE_NAME,
    downgrade_for_isolated_test,
    upgrade,
    validate_schema,
)


SERVER_NOW = datetime(2026, 12, 31, 12, 0, tzinfo=timezone.utc)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    assert upgrade(conn)["valid"] is True
    conn.commit()
    return conn


def _stamp(day: str, *, hour: int = 1) -> str:
    return f"{day}T{hour:02d}:00:00Z"


def _login(
    conn: sqlite3.Connection,
    day: str,
    *,
    user_id: int = 7,
    event_id: str | None = None,
    occurred_at: str | None = None,
    server_now: datetime = SERVER_NOW,
):
    return record_authenticated_login(
        conn,
        user_id=user_id,
        occurred_at=occurred_at or _stamp(day),
        source_authority="auth:test",
        source_event_id=event_id,
        source_operation_id=f"op-{event_id}" if event_id else None,
        server_now=server_now,
    )


def test_schema_is_additive_valid_and_rerunnable():
    conn = _db()
    try:
        status = validate_schema(conn)
        assert status["valid"] is True
        assert upgrade(conn)["valid"] is True
        assert {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {
            LOGIN_DAYS_TABLE_NAME,
            STREAK_TABLE_NAME,
            JOURNEY_TABLE_NAME,
        }
    finally:
        downgrade_for_isolated_test(conn)
        assert validate_schema(conn)["valid"] is False
        conn.close()


def test_first_login_initializes_all_separate_state():
    conn = _db()
    try:
        result = _login(conn, "2026-08-01", event_id="first")
        assert (result.outcome, result.local_login_date) == ("RECORDED", "2026-08-01")
        assert (result.current_streak_days, result.best_streak_days, result.total_login_days) == (1, 1, 1)
        assert (result.journey_day_completed, result.journey_completed) == (1, False)
        state = get_login_state(conn, user_id=7)
        assert state.current_streak_days == 1
        assert state.total_login_days == 1
        assert state.journey_day_completed == 1
        assert state.journey_completed is False
    finally:
        conn.close()


def test_same_day_repeated_logins_count_once_even_with_different_events():
    conn = _db()
    try:
        results = [_login(conn, "2026-08-01", event_id=f"event-{index}") for index in range(10)]
        assert sum(result.is_new_login_day for result in results) == 1
        assert all(result.journey_day_completed == 1 for result in results)
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {LOGIN_DAYS_TABLE_NAME}").fetchone()["n"] == 1
        assert conn.execute(f"SELECT total_login_days FROM {STREAK_TABLE_NAME}").fetchone()[0] == 1
    finally:
        conn.close()


def test_journey_pauses_but_streak_resets_after_a_gap():
    conn = _db()
    try:
        _login(conn, "2026-08-01", event_id="aug-1")
        _login(conn, "2026-08-03", event_id="aug-3")
        result = _login(conn, "2026-08-04", event_id="aug-4")
        assert result.journey_day_completed == 3
        assert (result.current_streak_days, result.best_streak_days, result.total_login_days) == (2, 2, 3)
    finally:
        conn.close()


def test_best_streak_is_not_current_streak_or_total_days():
    conn = _db()
    try:
        days = ["2026-01-01", "2026-01-02", "2026-01-03"]
        days += ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
        days += ["2026-01-11", "2026-01-12"]
        for index, day in enumerate(days):
            result = _login(conn, day, event_id=f"best-{index}")
        assert (result.current_streak_days, result.best_streak_days, result.total_login_days) == (2, 5, 10)
    finally:
        conn.close()


def test_seven_distinct_days_complete_journey_and_never_restart():
    conn = _db()
    try:
        for index in range(7):
            result = _login(conn, f"2026-02-{index + 1:02d}", event_id=f"journey-{index}")
        assert (result.journey_day_completed, result.journey_completed) == (7, True)
        after = _login(conn, "2026-02-08", event_id="journey-after")
        repeat = _login(conn, "2026-02-08", event_id="journey-after-repeat")
        assert (after.journey_day_completed, after.journey_completed) == (7, True)
        assert after.journey_advanced is False
        assert repeat.journey_day_completed == 7
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {LOGIN_DAYS_TABLE_NAME}").fetchone()["n"] == 8
    finally:
        conn.close()


def test_source_event_replay_is_safe_but_cross_day_reuse_fails_closed():
    conn = _db()
    try:
        first = _login(conn, "2026-03-01", event_id="source-1")
        replay = _login(conn, "2026-03-01", event_id="source-1")
        assert first.is_new_login_day is True
        assert (replay.duplicate, replay.source_event_replayed, replay.total_login_days) == (True, True, 1)
        with pytest.raises(LoginEventValidationError):
            _login(
                conn,
                "2026-03-01",
                event_id="source-1",
                occurred_at="2026-03-01T02:00:00Z",
            )
        with pytest.raises(LoginEventIdentityConflict):
            _login(conn, "2026-03-02", event_id="source-1")
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {LOGIN_DAYS_TABLE_NAME}").fetchone()["n"] == 1
    finally:
        conn.close()


def test_out_of_order_event_recomputes_from_durable_dates():
    conn = _db()
    try:
        _login(conn, "2026-08-05", event_id="late-5")
        delayed = _login(conn, "2026-08-04", event_id="late-4")
        final = _login(conn, "2026-08-06", event_id="late-6")
        assert delayed.local_login_date == "2026-08-04"
        assert (final.current_streak_days, final.best_streak_days, final.total_login_days) == (3, 3, 3)
        assert final.journey_day_completed == 3
    finally:
        conn.close()


def test_timezone_boundary_uses_taipei_calendar_date_not_utc_date():
    conn = _db()
    try:
        before = _login(conn, "2026-08-24", event_id="taipei-before", occurred_at="2026-08-24T15:59:59Z")
        after = _login(conn, "2026-08-25", event_id="taipei-after", occurred_at="2026-08-24T16:00:01Z")
        same_local_day = _login(
            conn,
            "2026-08-25",
            event_id="taipei-same",
            occurred_at="2026-08-25T15:59:59Z",
        )
        assert (before.local_login_date, after.local_login_date) == ("2026-08-24", "2026-08-25")
        assert same_local_day.duplicate is True
        assert same_local_day.total_login_days == 2
    finally:
        conn.close()


def test_malformed_naive_and_unreasonable_future_timestamps_fail_closed():
    conn = _db()
    try:
        with pytest.raises(LoginEventValidationError):
            _login(conn, "2026-08-01", event_id="naive", occurred_at="2026-08-01T01:00:00")
        with pytest.raises(LoginEventValidationError):
            _login(conn, "2026-08-01", event_id="malformed", occurred_at="not-a-timestamp")
        with pytest.raises(LoginEventValidationError):
            _login(
                conn,
                "2027-01-01",
                event_id="future",
                occurred_at="2026-12-31T12:06:00Z",
            )
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {LOGIN_DAYS_TABLE_NAME}").fetchone()["n"] == 0
    finally:
        conn.close()


def test_transaction_rollback_removes_ledger_and_both_projections():
    conn = _db()
    try:
        _login(conn, "2026-08-01", event_id="rollback")
        conn.rollback()
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {LOGIN_DAYS_TABLE_NAME}").fetchone()["n"] == 0
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {STREAK_TABLE_NAME}").fetchone()["n"] == 0
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {JOURNEY_TABLE_NAME}").fetchone()["n"] == 0
    finally:
        conn.close()


def test_cross_user_state_isolated_and_no_rewards_or_quest_rows_are_created():
    conn = _db()
    try:
        one = _login(conn, "2026-08-01", user_id=7, event_id="u7")
        two = _login(conn, "2026-08-01", user_id=8, event_id="u8")
        assert (one.total_login_days, two.total_login_days) == (1, 1)
        assert get_login_state(conn, user_id=7).user_id != get_login_state(conn, user_id=8).user_id
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert tables == {LOGIN_DAYS_TABLE_NAME, STREAK_TABLE_NAME, JOURNEY_TABLE_NAME}
    finally:
        conn.close()
