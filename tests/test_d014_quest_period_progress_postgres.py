from __future__ import annotations

from datetime import datetime, timezone
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor
import os
from urllib.parse import urlsplit

import pytest

from migrations.quest_progress_v2 import (
    APPLICATION_TABLE_NAME,
    PROGRESS_TABLE_NAME,
    downgrade_for_isolated_test,
    upgrade,
    validate_schema,
)
from quest_catalog import QuestDefinition, build_catalog
from quest_period_authority import QuestPeriodResolver
from quest_progress_authority import ProgressApplicationConflict, apply_authoritative_event
from quest_progress_evaluator import AuthoritativeEvent


SERVER_NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def _url() -> str:
    url = os.environ.get("D014_QUEST_POSTGRES_URL")
    if not url or os.environ.get("D014_QUEST_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "test" not in database and "d014" not in database:
        pytest.skip("refusing PostgreSQL URL without a disposable test/d014 database")
    return url


def _open(url: str):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def _definition(quest_id: str, *, family="daily", period="daily", target=5, filters=None, version=1):
    _, quest_type = quest_id.split(":", 1)
    return QuestDefinition(
        quest_id=quest_id,
        quest_family=family,
        quest_type=quest_type,
        period=period,
        condition="QUESTION_CORRECT",
        target=target,
        filters=filters or {"correct": True},
        reward_profile_id=f"fixture:{quest_id}",
        availability={"catalog_status": "planned"},
        enabled=True,
        version=version,
        aliases=(),
    )


def _event(event_id: str, occurred_at: str, *, user_id=7, payload=None, source_operation_id=None):
    return AuthoritativeEvent.from_server(
        event_id=event_id,
        event_type="QUESTION_CORRECT",
        user_id=user_id,
        source_authority="server:test",
        source_operation_id=source_operation_id or f"op-{event_id}",
        occurred_at=occurred_at,
        payload=payload if payload is not None else {"correct": True},
    )


def _reset(url: str):
    conn = _open(url)
    downgrade_for_isolated_test(conn)
    conn.commit()
    status = upgrade(conn)
    conn.commit()
    assert status["valid"] is True
    return conn


def test_postgres_migration_preflight_and_rerun():
    url = _url()
    conn = _reset(url)
    try:
        version = conn.execute("SELECT version() AS version").fetchone()["version"]
        assert str(version).startswith("PostgreSQL ")
        assert validate_schema(conn)["valid"] is True
        assert upgrade(conn)["valid"] is True
        conn.commit()
        columns = {
            row["column_name"]: row["data_type"]
            for row in conn.execute(
                """SELECT column_name, data_type
                     FROM information_schema.columns
                    WHERE table_schema='public' AND table_name IN (?, ?)
                 ORDER BY table_name, ordinal_position""",
                (PROGRESS_TABLE_NAME, APPLICATION_TABLE_NAME),
            ).fetchall()
        }
        assert columns["progress"] == "bigint"
        assert columns["source_event_id"] == "text"
        assert columns["target_snapshot"] == "bigint"
    finally:
        downgrade_for_isolated_test(conn)
        conn.commit()
        conn.close()


def test_postgres_same_event_cannot_move_to_a_second_period():
    url = _url()
    conn = _reset(url)
    catalog = build_catalog((_definition("daily:answer", target=5),))
    try:
        original = _event("pg-cross-period", "2026-08-24T15:59:59Z")
        apply_authoritative_event(conn, event=original, catalog=catalog, server_now=SERVER_NOW)
        conn.commit()
        changed = _event("pg-cross-period", "2026-08-24T16:00:00Z")
        with pytest.raises(ProgressApplicationConflict, match="replayed_delta_disagrees_with_application"):
            apply_authoritative_event(conn, event=changed, catalog=catalog, server_now=SERVER_NOW)
        conn.rollback()
        assert conn.execute(
            f"SELECT COUNT(*) AS n FROM {APPLICATION_TABLE_NAME} WHERE source_event_id=?",
            ("pg-cross-period",),
        ).fetchone()["n"] == 1
        assert conn.execute(
            f"SELECT COUNT(*) AS n FROM {PROGRESS_TABLE_NAME}"
        ).fetchone()["n"] == 1
    finally:
        downgrade_for_isolated_test(conn)
        conn.commit()
        conn.close()


def test_postgres_daily_weekly_rollover_and_late_event_replay():
    url = _url()
    conn = _reset(url)
    daily_catalog = build_catalog((_definition("daily:answer", target=5),))
    try:
        before = _event("pg-day-before", "2026-08-24T15:59:59Z")
        after = _event("pg-day-after", "2026-08-24T16:00:00Z")
        late = _event("pg-day-late", "2026-08-23T15:59:59Z")
        assert apply_authoritative_event(conn, event=before, catalog=daily_catalog, server_now=SERVER_NOW)[0].period_key == "2026-08-24"
        conn.commit()
        assert apply_authoritative_event(conn, event=after, catalog=daily_catalog, server_now=SERVER_NOW)[0].period_key == "2026-08-25"
        conn.commit()
        assert apply_authoritative_event(conn, event=late, catalog=daily_catalog, server_now=SERVER_NOW)[0].period_key == "2026-08-23"
        conn.commit()
        replay = apply_authoritative_event(conn, event=late, catalog=daily_catalog, server_now=SERVER_NOW)
        assert replay[0].duplicate is True
        conn.rollback()
        rows = conn.execute(
            f"SELECT period_key, progress FROM {PROGRESS_TABLE_NAME} ORDER BY period_key"
        ).fetchall()
        assert [(row["period_key"], row["progress"]) for row in rows] == [
            ("2026-08-23", 1),
            ("2026-08-24", 1),
            ("2026-08-25", 1),
        ]

        downgrade_for_isolated_test(conn)
        conn.commit()
        upgrade(conn)
        conn.commit()
        weekly_catalog = build_catalog((_definition("weekly:answer", family="weekly", period="weekly", target=5),))
        first = apply_authoritative_event(
            conn,
            event=_event("pg-week-before", "2026-08-30T15:59:59Z"),
            catalog=weekly_catalog,
            server_now=SERVER_NOW,
        )
        second = apply_authoritative_event(
            conn,
            event=_event("pg-week-after", "2026-08-30T16:00:00Z"),
            catalog=weekly_catalog,
            server_now=SERVER_NOW,
        )
        assert (first[0].period_key, second[0].period_key) == ("2026-W35", "2026-W36")
        conn.commit()
        assert QuestPeriodResolver().resolve("weekly", "2021-01-01T00:00:00Z", server_now=SERVER_NOW).period_key == "2020-W53"
    finally:
        downgrade_for_isolated_test(conn)
        conn.commit()
        conn.close()


def test_postgres_streak_increment_reset_increment_is_durable():
    url = _url()
    conn = _reset(url)
    catalog = build_catalog(
        (_definition("daily:streak", target=3, filters={"correct": True, "streak_scope": "daily_consecutive"}),)
    )
    try:
        first = _event("pg-streak-1", "2026-08-24T01:00:00Z", payload={"correct": True, "streak_scope": "daily_consecutive"})
        wrong = _event("pg-streak-w", "2026-08-24T02:00:00Z", payload={"correct": False, "streak_scope": "daily_consecutive"})
        second = _event("pg-streak-2", "2026-08-24T03:00:00Z", payload={"correct": True, "streak_scope": "daily_consecutive"})
        assert apply_authoritative_event(conn, event=first, catalog=catalog, server_now=SERVER_NOW)[0].resulting_progress == 1
        conn.commit()
        assert apply_authoritative_event(conn, event=wrong, catalog=catalog, server_now=SERVER_NOW)[0].resulting_progress == 0
        conn.commit()
        assert apply_authoritative_event(conn, event=second, catalog=catalog, server_now=SERVER_NOW)[0].resulting_progress == 1
        conn.commit()
        row = conn.execute(
            f"SELECT progress, completed FROM {PROGRESS_TABLE_NAME} WHERE quest_id='daily:streak'"
        ).fetchone()
        assert (row["progress"], row["completed"]) == (1, False)
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {APPLICATION_TABLE_NAME}").fetchone()["n"] == 3
    finally:
        downgrade_for_isolated_test(conn)
        conn.commit()
        conn.close()


def test_postgres_concurrent_duplicate_and_distinct_event_progress():
    url = _url()
    setup = _reset(url)
    setup.commit()
    setup.close()
    catalog = build_catalog((_definition("daily:answer", target=5),))
    event = _event("pg-same", "2026-08-24T01:00:00Z")
    barrier = Barrier(2)

    def same_worker(_unused):
        conn = _open(url)
        try:
            barrier.wait(timeout=10)
            result = apply_authoritative_event(conn, event=event, catalog=catalog, server_now=SERVER_NOW)
            conn.commit()
            return result[0]
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        same_results = list(pool.map(same_worker, range(2)))
    assert sorted(result.duplicate for result in same_results) == [False, True]

    check = _open(url)
    try:
        assert check.execute(f"SELECT COUNT(*) AS n FROM {APPLICATION_TABLE_NAME}").fetchone()["n"] == 1
        assert check.execute(f"SELECT progress FROM {PROGRESS_TABLE_NAME}").fetchone()["progress"] == 1
    finally:
        check.close()

    setup = _reset(url)
    setup.commit()
    setup.close()
    events = (
        _event("pg-first", "2026-08-24T01:00:00Z"),
        _event("pg-second", "2026-08-24T02:00:00Z"),
    )
    barrier = Barrier(2)

    def distinct_worker(index):
        conn = _open(url)
        try:
            barrier.wait(timeout=10)
            result = apply_authoritative_event(conn, event=events[index], catalog=catalog, server_now=SERVER_NOW)
            conn.commit()
            return result[0]
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        distinct_results = list(pool.map(distinct_worker, range(2)))
    assert all(result.duplicate is False for result in distinct_results)
    check = _open(url)
    try:
        assert check.execute(f"SELECT COUNT(*) AS n FROM {APPLICATION_TABLE_NAME}").fetchone()["n"] == 2
        assert check.execute(f"SELECT progress FROM {PROGRESS_TABLE_NAME}").fetchone()["progress"] == 2
    finally:
        check.close()


def test_postgres_one_event_many_quests_and_rollback_atomicity():
    url = _url()
    setup = _reset(url)
    setup.commit()
    setup.close()
    catalog = build_catalog(
        (
            _definition("daily:answer", family="daily", period="daily"),
            _definition("weekly:answer", family="weekly", period="weekly"),
            _definition("achievement:answer", family="achievement", period="lifetime"),
        )
    )
    event = _event("pg-many", "2026-08-24T01:00:00Z")
    conn = _open(url)
    try:
        result = apply_authoritative_event(conn, event=event, catalog=catalog, server_now=SERVER_NOW)
        assert len(result) == 3
        conn.commit()
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {APPLICATION_TABLE_NAME}").fetchone()["n"] == 3
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {PROGRESS_TABLE_NAME}").fetchone()["n"] == 3

        rollback_event = _event("pg-rollback", "2026-08-24T02:00:00Z")
        apply_authoritative_event(conn, event=rollback_event, catalog=catalog, server_now=SERVER_NOW)
        conn.rollback()
        assert conn.execute(
            f"SELECT COUNT(*) AS n FROM {APPLICATION_TABLE_NAME} WHERE source_event_id=?",
            (rollback_event.event_id,),
        ).fetchone()["n"] == 0
        assert conn.execute(
            f"SELECT COUNT(*) AS n FROM {PROGRESS_TABLE_NAME} WHERE period_key='2026-08-24'"
        ).fetchone()["n"] == 1
    finally:
        downgrade_for_isolated_test(conn)
        conn.commit()
        conn.close()
