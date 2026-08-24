from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
import os
from urllib.parse import urlsplit

import pytest

from login_journey_authority import (
    LoginEventIdentityConflict,
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


def _url() -> str:
    url = os.environ.get("D016_LOGIN_POSTGRES_URL")
    if not url or os.environ.get("D016_LOGIN_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "test" not in database and "d016" not in database:
        pytest.skip("refusing PostgreSQL URL without a disposable test/d016 database")
    return url


def _open(url: str):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def _reset(url: str):
    conn = _open(url)
    downgrade_for_isolated_test(conn)
    conn.commit()
    assert upgrade(conn)["valid"] is True
    conn.commit()
    return conn


def _record(url: str, *, user_id: int, occurred_at: str, event_id: str):
    conn = _open(url)
    try:
        result = record_authenticated_login(
            conn,
            user_id=user_id,
            occurred_at=occurred_at,
            source_authority="auth:postgres-test",
            source_event_id=event_id,
            source_operation_id=f"op-{event_id}",
            server_now=SERVER_NOW,
        )
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_postgres_preflight_migration_rerun_and_transaction_sanity():
    url = _url()
    conn = _reset(url)
    try:
        version = conn.execute("SELECT version() AS version").fetchone()["version"]
        assert str(version).startswith("PostgreSQL 16.")
        assert validate_schema(conn)["valid"] is True
        assert upgrade(conn)["valid"] is True
        conn.commit()
        conn.execute(f"SELECT 1 FROM {LOGIN_DAYS_TABLE_NAME}")
        conn.execute("BEGIN")
        conn.execute(
            f"INSERT INTO {LOGIN_DAYS_TABLE_NAME} "
            "(user_id, local_login_date, source_event_id, source_authority, occurred_at, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (901, "2026-08-01", "rollback-preflight", "test", SERVER_NOW, SERVER_NOW),
        )
        conn.rollback()
        assert conn.execute(
            f"SELECT COUNT(*) AS n FROM {LOGIN_DAYS_TABLE_NAME} WHERE user_id=?", (901,)
        ).fetchone()["n"] == 0
    finally:
        downgrade_for_isolated_test(conn)
        conn.commit()
        conn.close()


def test_postgres_ten_same_day_events_commit_one_login_day():
    url = _url()
    setup = _reset(url)
    setup.commit()
    setup.close()
    barrier = Barrier(10)

    def worker(index: int):
        conn = _open(url)
        try:
            barrier.wait(timeout=20)
            result = record_authenticated_login(
                conn,
                user_id=7,
                occurred_at="2026-08-24T01:00:00Z",
                source_authority="auth:postgres-test",
                source_event_id=f"same-day-{index}",
                source_operation_id=f"same-op-{index}",
                server_now=SERVER_NOW,
            )
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    try:
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(worker, range(10)))
        assert sum(result.is_new_login_day for result in results) == 1
        verify = _open(url)
        try:
            state = get_login_state(verify, user_id=7)
            assert (state.total_login_days, state.current_streak_days, state.journey_day_completed) == (1, 1, 1)
            assert verify.execute(
                f"SELECT COUNT(*) AS n FROM {LOGIN_DAYS_TABLE_NAME} WHERE user_id=?", (7,)
            ).fetchone()["n"] == 1
        finally:
            verify.close()
    finally:
        cleanup = _open(url)
        downgrade_for_isolated_test(cleanup)
        cleanup.commit()
        cleanup.close()


def test_postgres_same_operation_replay_and_different_users_are_isolated():
    url = _url()
    conn = _reset(url)
    conn.close()
    barrier = Barrier(2)

    def worker(user_id: int):
        connection = _open(url)
        try:
            barrier.wait(timeout=20)
            result = record_authenticated_login(
                connection,
                user_id=user_id,
                occurred_at="2026-08-24T01:00:00Z",
                source_authority="auth:postgres-test",
                source_event_id="same-source-user-scoped",
                source_operation_id="same-operation",
                server_now=SERVER_NOW,
            )
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, (7, 8)))
        assert all(result.is_new_login_day for result in results)
        verify = _open(url)
        try:
            assert verify.execute(f"SELECT COUNT(*) AS n FROM {LOGIN_DAYS_TABLE_NAME}").fetchone()["n"] == 2
        finally:
            verify.close()
    finally:
        cleanup = _open(url)
        downgrade_for_isolated_test(cleanup)
        cleanup.commit()
        cleanup.close()


def test_postgres_same_source_event_concurrent_replay_is_one_and_cross_day_conflicts():
    url = _url()
    setup = _reset(url)
    setup.commit()
    setup.close()
    barrier = Barrier(2)

    def replay_worker(_index: int):
        conn = _open(url)
        try:
            barrier.wait(timeout=20)
            result = record_authenticated_login(
                conn,
                user_id=7,
                occurred_at="2026-08-24T01:00:00Z",
                source_authority="auth:postgres-test",
                source_event_id="concurrent-source-replay",
                source_operation_id="concurrent-source-operation",
                server_now=SERVER_NOW,
            )
            conn.commit()
            return ("result", result)
        except Exception as exc:
            conn.rollback()
            return ("error", exc)
        finally:
            conn.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            replay_results = list(pool.map(replay_worker, (0, 1)))
        assert [kind for kind, _value in replay_results] == ["result", "result"]
        assert sum(value.is_new_login_day for _kind, value in replay_results) == 1
        assert sum(value.source_event_replayed for _kind, value in replay_results) == 1

        barrier = Barrier(2)

        def cross_day_worker(occurred_at: str):
            conn = _open(url)
            try:
                barrier.wait(timeout=20)
                result = record_authenticated_login(
                    conn,
                    user_id=7,
                    occurred_at=occurred_at,
                    source_authority="auth:postgres-test",
                    source_event_id="cross-day-source-race",
                    source_operation_id="cross-day-operation",
                    server_now=SERVER_NOW,
                )
                conn.commit()
                return ("result", result)
            except Exception as exc:
                conn.rollback()
                return ("error", exc)
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            cross_day_results = list(
                pool.map(cross_day_worker, ("2026-08-25T15:59:59Z", "2026-08-25T16:00:01Z"))
            )
        assert sum(kind == "result" for kind, _value in cross_day_results) == 1
        errors = [value for kind, value in cross_day_results if kind == "error"]
        assert len(errors) == 1
        assert isinstance(errors[0], LoginEventIdentityConflict)
        verify = _open(url)
        try:
            assert verify.execute(
                f"SELECT COUNT(*) AS n FROM {LOGIN_DAYS_TABLE_NAME} WHERE user_id=?", (7,)
            ).fetchone()["n"] == 2
            assert verify.execute(
                f"SELECT COUNT(*) AS n FROM {LOGIN_DAYS_TABLE_NAME} WHERE source_event_id=?",
                ("cross-day-source-race",),
            ).fetchone()["n"] == 1
        finally:
            verify.close()
    finally:
        cleanup = _open(url)
        downgrade_for_isolated_test(cleanup)
        cleanup.commit()
        cleanup.close()


def test_postgres_adjacent_dates_race_and_delayed_date_recompute_streak():
    url = _url()
    setup = _reset(url)
    setup.commit()
    setup.close()
    barrier = Barrier(2)

    def worker(item):
        day, event_id = item
        conn = _open(url)
        try:
            barrier.wait(timeout=20)
            result = record_authenticated_login(
                conn,
                user_id=7,
                occurred_at=day,
                source_authority="auth:postgres-test",
                source_event_id=event_id,
                source_operation_id=f"op-{event_id}",
                server_now=SERVER_NOW,
            )
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(worker, (("2026-08-24T15:59:59Z", "adjacent-1"), ("2026-08-24T16:00:01Z", "adjacent-2"))))
        delayed = _record(
            url,
            user_id=7,
            occurred_at="2026-08-23T01:00:00Z",
            event_id="delayed-before",
        )
        assert delayed.local_login_date == "2026-08-23"
        verify = _open(url)
        try:
            state = get_login_state(verify, user_id=7)
            assert (state.total_login_days, state.current_streak_days, state.best_streak_days) == (3, 3, 3)
            assert state.journey_day_completed == 3
        finally:
            verify.close()
    finally:
        cleanup = _open(url)
        downgrade_for_isolated_test(cleanup)
        cleanup.commit()
        cleanup.close()


def test_postgres_journey_day_six_to_seven_race_caps_completion():
    url = _url()
    conn = _reset(url)
    for index in range(6):
        _record(url, user_id=7, occurred_at=f"2026-09-{index + 1:02d}T01:00:00Z", event_id=f"seed-{index}")
    conn.close()
    barrier = Barrier(2)

    def worker(event_id: str):
        connection = _open(url)
        try:
            barrier.wait(timeout=20)
            result = record_authenticated_login(
                connection,
                user_id=7,
                occurred_at="2026-09-07T01:00:00Z",
                source_authority="auth:postgres-test",
                source_event_id=event_id,
                source_operation_id=f"op-{event_id}",
                server_now=SERVER_NOW,
            )
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, ("day-seven-a", "day-seven-b")))
        assert sum(result.is_new_login_day for result in results) == 1
        verify = _open(url)
        try:
            state = get_login_state(verify, user_id=7)
            assert (state.journey_day_completed, state.journey_completed, state.total_login_days) == (7, True, 7)
        finally:
            verify.close()
    finally:
        cleanup = _open(url)
        downgrade_for_isolated_test(cleanup)
        cleanup.commit()
        cleanup.close()
