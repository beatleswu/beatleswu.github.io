from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

import pytest

from migrations.quest_progress_v2 import (
    APPLICATION_TABLE_NAME,
    PROGRESS_TABLE_NAME,
    downgrade_for_isolated_test,
    upgrade,
    validate_schema,
)
from quest_catalog import CANONICAL_QUEST_CATALOG, QuestDefinition, build_catalog
from quest_period_authority import (
    FutureTimestampRejected,
    MalformedTimestamp,
    PERIOD_TIMEZONE,
    PeriodResolutionError,
    QuestPeriodResolver,
)
from quest_progress_authority import (
    EventOrderingConflict,
    ProgressApplicationConflict,
    UnknownQuestProgress,
    apply_authoritative_event,
    apply_progress_deltas,
)
from quest_progress_evaluator import AuthoritativeEvent, ProgressDelta, evaluate_quest_set_completion


RESOLVER = QuestPeriodResolver()
SERVER_NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    upgrade(conn)
    return conn


def _definition(
    quest_id: str,
    *,
    family: str = "daily",
    period: str = "daily",
    condition: str = "QUESTION_CORRECT",
    target: int = 3,
    filters=None,
    enabled: bool = True,
    version: int = 1,
    availability=None,
):
    _, quest_type = quest_id.split(":", 1)
    return QuestDefinition(
        quest_id=quest_id,
        quest_family=family,
        quest_type=quest_type,
        period=period,
        condition=condition,
        target=target,
        filters=filters or {"correct": True},
        reward_profile_id=f"fixture:{quest_id}",
        availability=availability or {"catalog_status": "planned"},
        enabled=enabled,
        version=version,
        aliases=(),
    )


def _event(
    event_id: str,
    occurred_at: str,
    *,
    event_type: str = "QUESTION_CORRECT",
    payload=None,
    source_operation_id: str | None = None,
    user_id: int | str = 7,
):
    return AuthoritativeEvent.from_server(
        event_id=event_id,
        event_type=event_type,
        user_id=user_id,
        source_authority="server:test",
        source_operation_id=source_operation_id or f"op-{event_id}",
        occurred_at=occurred_at,
        payload=payload if payload is not None else {"correct": True},
    )


def _catalog(*definitions: QuestDefinition):
    return build_catalog(definitions)


def _progress(conn, user_id=7, quest_id="daily:answer", period_key=None):
    if period_key is None:
        return conn.execute(
            f"SELECT * FROM {PROGRESS_TABLE_NAME} WHERE user_id=? AND quest_id=? ORDER BY period_key",
            (str(user_id), quest_id),
        ).fetchall()
    return conn.execute(
        f"SELECT * FROM {PROGRESS_TABLE_NAME} WHERE user_id=? AND quest_id=? AND period_key=?",
        (str(user_id), quest_id, period_key),
    ).fetchone()


def test_schema_is_additive_valid_and_rerunnable():
    conn = _db()
    try:
        status = validate_schema(conn)
        assert status["valid"] is True
        assert status["progress"]["table"] == PROGRESS_TABLE_NAME
        assert status["applications"]["table"] == APPLICATION_TABLE_NAME
        assert upgrade(conn)["valid"] is True
    finally:
        downgrade_for_isolated_test(conn)
        assert validate_schema(conn)["valid"] is False
        conn.close()


def test_daily_same_period_and_different_events_apply_once():
    conn = _db()
    catalog = _catalog(_definition("daily:answer"))
    try:
        first = _event("evt-1", "2026-08-24T01:00:00Z")
        second = _event("evt-2", "2026-08-24T02:00:00Z")
        assert apply_authoritative_event(conn, event=first, catalog=catalog, server_now=SERVER_NOW)[0].resulting_progress == 1
        replay = apply_authoritative_event(conn, event=first, catalog=catalog, server_now=SERVER_NOW)
        assert replay[0].duplicate is True
        assert apply_authoritative_event(conn, event=second, catalog=catalog, server_now=SERVER_NOW)[0].resulting_progress == 2
        row = _progress(conn, quest_id="daily:answer", period_key="2026-08-24")
        assert (row["progress"], row["completed"]) == (2, 0)
        assert conn.execute(f"SELECT COUNT(*) FROM {APPLICATION_TABLE_NAME}").fetchone()[0] == 2
    finally:
        conn.close()


def test_daily_midnight_rollover_isolated_and_late_event_keeps_original_day():
    conn = _db()
    catalog = _catalog(_definition("daily:answer", target=5))
    try:
        before = _event("evt-before", "2026-08-24T15:59:59Z")
        after = _event("evt-after", "2026-08-24T16:00:00Z")
        late = _event("evt-late", "2026-08-23T15:59:59Z")
        apply_authoritative_event(conn, event=before, catalog=catalog, server_now=SERVER_NOW)
        apply_authoritative_event(conn, event=after, catalog=catalog, server_now=SERVER_NOW)
        result = apply_authoritative_event(conn, event=late, catalog=catalog, server_now=SERVER_NOW)
        assert result[0].period_key == "2026-08-23"
        assert [row["period_key"] for row in _progress(conn, quest_id="daily:answer")] == [
            "2026-08-23",
            "2026-08-24",
            "2026-08-25",
        ]
        replay = apply_authoritative_event(conn, event=late, catalog=catalog, server_now=SERVER_NOW)
        assert replay[0].duplicate is True
        assert conn.execute(
            f"SELECT progress FROM {PROGRESS_TABLE_NAME} WHERE quest_id='daily:answer' AND period_key='2026-08-23'"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_same_event_cannot_be_reapplied_under_a_different_period():
    conn = _db()
    catalog = _catalog(_definition("daily:answer", target=5))
    try:
        original = _event("evt-cross-period", "2026-08-24T15:59:59Z")
        apply_authoritative_event(conn, event=original, catalog=catalog, server_now=SERVER_NOW)
        changed = _event("evt-cross-period", "2026-08-24T16:00:00Z")
        with pytest.raises(ProgressApplicationConflict, match="replayed_delta_disagrees_with_application"):
            apply_authoritative_event(conn, event=changed, catalog=catalog, server_now=SERVER_NOW)
        assert conn.execute(
            f"SELECT COUNT(*) FROM {APPLICATION_TABLE_NAME} WHERE source_event_id='evt-cross-period'"
        ).fetchone()[0] == 1
        assert conn.execute(
            f"SELECT COUNT(*) FROM {PROGRESS_TABLE_NAME} WHERE quest_id='daily:answer'"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_same_event_payload_conflict_and_forged_delta_fail_closed():
    conn = _db()
    catalog = _catalog(_definition("daily:answer", target=5))
    try:
        original = _event("evt-payload-conflict", "2026-08-24T01:00:00Z")
        apply_authoritative_event(conn, event=original, catalog=catalog, server_now=SERVER_NOW)
        changed_payload = _event(
            "evt-payload-conflict",
            "2026-08-24T01:00:00Z",
            payload={"correct": True, "authoritative_answer_ref": "different"},
        )
        with pytest.raises(ProgressApplicationConflict, match="replayed_delta_disagrees_with_application"):
            apply_authoritative_event(conn, event=changed_payload, catalog=catalog, server_now=SERVER_NOW)

        forged = ProgressDelta(
            quest_id="daily:answer",
            operation="INCREMENT",
            amount=99,
            source_event_id="evt-forged",
            condition="QUESTION_CORRECT",
            reason="forged",
            quest_family="daily",
            period="daily",
        )
        with pytest.raises(ProgressApplicationConflict, match="delta_not_authoritative"):
            apply_progress_deltas(
                conn,
                event=_event("evt-forged", "2026-08-24T02:00:00Z"),
                deltas=(forged,),
                catalog=catalog,
                server_now=SERVER_NOW,
            )
        assert conn.execute(
            f"SELECT progress FROM {PROGRESS_TABLE_NAME} WHERE quest_id='daily:answer' AND period_key='2026-08-24'"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_weekly_monday_boundary_and_iso_year_rollover():
    assert RESOLVER.resolve("weekly", "2026-08-30T15:59:59Z", server_now=SERVER_NOW).period_key == "2026-W35"
    assert RESOLVER.resolve("weekly", "2026-08-30T16:00:00Z", server_now=SERVER_NOW).period_key == "2026-W36"
    assert RESOLVER.resolve("weekly", "2020-12-27T16:00:00Z", server_now=SERVER_NOW).period_key == "2020-W53"
    assert RESOLVER.resolve("weekly", "2021-01-03T16:00:00Z", server_now=SERVER_NOW).period_key == "2021-W01"


def test_lifetime_and_one_time_never_roll_over():
    future_server_now = datetime(2030, 1, 2, tzinfo=timezone.utc)
    for period, expected in (("lifetime", "lifetime"), ("one_time", "once")):
        first = RESOLVER.resolve(period, "2020-01-01T00:00:00Z", server_now=future_server_now)
        second = RESOLVER.resolve(period, "2030-01-01T00:00:00Z", server_now=future_server_now)
        assert first.period_key == expected
        assert second.period_key == expected


def test_event_window_is_authoritative_and_malformed_window_fails_closed():
    window = {
        "catalog_status": "planned",
        "event_window": {
            "start": "2026-09-01T00:00:00+08:00",
            "end": "2026-10-01T00:00:00+08:00",
            "timezone": "Asia/Taipei",
        },
    }
    inside = RESOLVER.resolve("event_window", "2026-09-10T00:00:00+08:00", availability=window, server_now=datetime(2026, 9, 10, tzinfo=PERIOD_TIMEZONE))
    outside = RESOLVER.resolve("event_window", "2026-08-31T15:59:59Z", availability=window, server_now=datetime(2026, 9, 10, tzinfo=timezone.utc))
    assert inside is not None
    assert inside.period_key.startswith("event_window:")
    assert outside is None
    with pytest.raises(PeriodResolutionError):
        RESOLVER.resolve("event_window", "2026-09-10T00:00:00+08:00", availability={"event_window": {"start": "bad", "end": "later"}}, server_now=SERVER_NOW)
    with pytest.raises(PeriodResolutionError):
        RESOLVER.resolve("event_window", "2026-09-10T00:00:00+08:00", availability={"event_window": {"start": "2026-09-01T00:00:00+08:00", "end": "2026-10-01T00:00:00+08:00", "timezone": "UTC"}}, server_now=SERVER_NOW)


def test_event_window_uses_exact_half_open_microsecond_bounds():
    first_window = {
        "event_window": {
            "start": "2026-09-10T00:00:00.000001+08:00",
            "end": "2026-09-10T00:00:01.000001+08:00",
            "timezone": "Asia/Taipei",
        }
    }
    second_window = {
        "event_window": {
            "start": "2026-09-10T00:00:00.000002+08:00",
            "end": "2026-09-10T00:00:01.000002+08:00",
            "timezone": "Asia/Taipei",
        }
    }
    first = RESOLVER.resolve(
        "event_window",
        "2026-09-09T16:00:00.500000Z",
        availability=first_window,
        server_now=datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
    )
    second = RESOLVER.resolve(
        "event_window",
        "2026-09-09T16:00:00.500000Z",
        availability=second_window,
        server_now=datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
    )
    assert first is not None and second is not None
    assert first.period_key != second.period_key
    assert first.period_start_utc.microsecond == 1
    assert first.period_end_exclusive_utc.microsecond == 1
    assert RESOLVER.resolve(
        "event_window",
        "2026-09-09T16:00:01.000001Z",
        availability=first_window,
        server_now=datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
    ) is None


def test_timestamp_malformed_and_future_fail_closed():
    with pytest.raises(MalformedTimestamp):
        RESOLVER.resolve("daily", "not-a-timestamp", server_now=SERVER_NOW)
    with pytest.raises(MalformedTimestamp):
        RESOLVER.resolve("daily", "2026-08-24T10:00:00", server_now=SERVER_NOW)
    with pytest.raises(FutureTimestampRejected):
        RESOLVER.resolve("daily", "2026-09-10T00:00:00Z", server_now=SERVER_NOW)


def test_streak_increment_reset_increment_is_ordered_and_terminal_completion_preserved():
    conn = _db()
    catalog = _catalog(
        _definition(
            "daily:streak",
            target=3,
            filters={"correct": True, "streak_scope": "daily_consecutive"},
        )
    )
    try:
        streak_correct = {"correct": True, "streak_scope": "daily_consecutive"}
        correct_1 = _event("evt-c1", "2026-08-24T01:00:00Z", payload=streak_correct)
        wrong = _event("evt-w", "2026-08-24T02:00:00Z", payload={"correct": False, "streak_scope": "daily_consecutive"})
        correct_2 = _event("evt-c2", "2026-08-24T03:00:00Z", payload=streak_correct)
        assert apply_authoritative_event(conn, event=correct_1, catalog=catalog, server_now=SERVER_NOW)[0].resulting_progress == 1
        assert apply_authoritative_event(conn, event=wrong, catalog=catalog, server_now=SERVER_NOW)[0].resulting_progress == 0
        assert apply_authoritative_event(conn, event=correct_2, catalog=catalog, server_now=SERVER_NOW)[0].resulting_progress == 1

        for index in range(2):
            event = _event(f"evt-c{index + 3}", f"2026-08-24T0{4 + index}:00:00Z", payload=streak_correct)
            apply_authoritative_event(conn, event=event, catalog=catalog, server_now=SERVER_NOW)
        completed = _progress(conn, quest_id="daily:streak", period_key="2026-08-24")
        assert (completed["progress"], completed["completed"]) == (3, 1)
        late_wrong = _event("evt-w-late", "2026-08-24T07:00:00Z", payload={"correct": False, "streak_scope": "daily_consecutive"})
        result = apply_authoritative_event(conn, event=late_wrong, catalog=catalog, server_now=SERVER_NOW)
        assert result[0].resulting_progress == 3
        assert _progress(conn, quest_id="daily:streak", period_key="2026-08-24")["progress"] == 3

        older = _event("evt-older", "2026-08-24T06:00:00Z", payload={"correct": False, "streak_scope": "daily_consecutive"})
        with pytest.raises(EventOrderingConflict):
            apply_authoritative_event(conn, event=older, catalog=catalog, server_now=SERVER_NOW)
        assert conn.execute(f"SELECT COUNT(*) FROM {APPLICATION_TABLE_NAME}").fetchone()[0] == 6
    finally:
        conn.close()


def test_one_event_matches_many_quests_and_applies_each_once():
    conn = _db()
    catalog = _catalog(
        _definition("daily:answer", family="daily", period="daily", target=2),
        _definition("weekly:answer", family="weekly", period="weekly", target=2),
        _definition("achievement:answer", family="achievement", period="lifetime", target=2),
    )
    event = _event("evt-many", "2026-08-24T01:00:00Z")
    try:
        first = apply_authoritative_event(conn, event=event, catalog=catalog, server_now=SERVER_NOW)
        replay = apply_authoritative_event(conn, event=event, catalog=catalog, server_now=SERVER_NOW)
        assert len(first) == len(replay) == 3
        assert all(item.duplicate is False for item in first)
        assert all(item.duplicate is True for item in replay)
        assert conn.execute(f"SELECT COUNT(*) FROM {APPLICATION_TABLE_NAME}").fetchone()[0] == 3
        assert conn.execute(f"SELECT COUNT(*) FROM {PROGRESS_TABLE_NAME}").fetchone()[0] == 3
    finally:
        conn.close()


def test_dragon_and_disabled_quest_fail_closed_without_progress():
    conn = _db()
    catalog = _catalog(
        _definition("daily:dragon", target=1, filters={"correct": True, "monster_family": "dragon"}),
        _definition("daily:disabled", target=1, enabled=False),
    )
    try:
        incorrect = _event("evt-bad-dragon", "2026-08-24T01:00:00Z", payload={"correct": False, "monster_family": "dragon"})
        assert apply_authoritative_event(conn, event=incorrect, catalog=catalog, server_now=SERVER_NOW) == ()
        correct = _event("evt-good-dragon", "2026-08-24T02:00:00Z", payload={"correct": True, "monster_family": "dragon"})
        result = apply_authoritative_event(conn, event=correct, catalog=catalog, server_now=SERVER_NOW)
        assert [item.quest_id for item in result] == ["daily:dragon"]
        assert not _progress(conn, quest_id="daily:disabled")
    finally:
        conn.close()


def test_unknown_alias_delta_creates_no_row_and_version_is_recorded():
    conn = _db()
    catalog = _catalog(_definition("daily:answer", version=7))
    event = _event("evt-version", "2026-08-24T01:00:00Z")
    try:
        delta = ProgressDelta(
            quest_id="answer",
            operation="INCREMENT",
            amount=1,
            source_event_id=event.event_id,
            condition="QUESTION_CORRECT",
            reason="test",
            quest_family="daily",
            period="daily",
        )
        with pytest.raises(UnknownQuestProgress):
            apply_progress_deltas(conn, event=event, deltas=(delta,), catalog=catalog, server_now=SERVER_NOW)
        assert conn.execute(f"SELECT COUNT(*) FROM {PROGRESS_TABLE_NAME}").fetchone()[0] == 0

        result = apply_authoritative_event(conn, event=event, catalog=catalog, server_now=SERVER_NOW)
        assert result[0].definition_version == 7
        row = _progress(conn, quest_id="daily:answer", period_key="2026-08-24")
        assert row["definition_version"] == 7
        assert row["target_snapshot"] == 3
    finally:
        conn.close()


def test_progress_definition_version_and_target_lineage_is_immutable():
    conn = _db()
    event = _event("evt-lineage-1", "2026-08-24T01:00:00Z")
    try:
        original_catalog = _catalog(_definition("daily:answer", target=3, version=1))
        first = apply_authoritative_event(conn, event=event, catalog=original_catalog, server_now=SERVER_NOW)
        assert first[0].duplicate is False

        revised_catalog = _catalog(_definition("daily:answer", target=5, version=2))
        with pytest.raises(ProgressApplicationConflict, match="quest_definition_lineage_changed"):
            apply_authoritative_event(
                conn,
                event=_event("evt-lineage-2", "2026-08-24T02:00:00Z"),
                catalog=revised_catalog,
                server_now=SERVER_NOW,
            )
        replay = apply_authoritative_event(conn, event=event, catalog=revised_catalog, server_now=SERVER_NOW)
        assert replay[0].duplicate is True
        row = _progress(conn, quest_id="daily:answer", period_key="2026-08-24")
        assert (row["progress"], row["definition_version"], row["target_snapshot"]) == (1, 1, 3)
        assert conn.execute(
            f"SELECT COUNT(*) FROM {APPLICATION_TABLE_NAME} WHERE quest_id='daily:answer'"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_current_daily_catalog_durable_compatibility_without_live_runtime_cutover():
    conn = _db()
    try:
        kill = _event("evt-kill", "2026-08-24T01:00:00Z", event_type="MONSTER_DEFEATED", payload={"source_scope": "daily_battlefield", "monster_id": "slime"})
        dragon = _event("evt-dragon", "2026-08-24T02:00:00Z", payload={"correct": True, "monster_family": "dragon", "source_scope": "daily_battlefield"})
        assert [item.quest_id for item in apply_authoritative_event(conn, event=kill, catalog=CANONICAL_QUEST_CATALOG, server_now=SERVER_NOW)] == ["daily:kill_monsters"]
        assert [item.quest_id for item in apply_authoritative_event(conn, event=dragon, catalog=CANONICAL_QUEST_CATALOG, server_now=SERVER_NOW)] == ["daily:challenge_dragon"]
        assert _progress(conn, quest_id="daily:kill_monsters", period_key="2026-08-24")["progress"] == 1
        assert _progress(conn, quest_id="daily:challenge_dragon", period_key="2026-08-24")["completed"] == 1

        source = _event("evt-daily-set", "2026-08-24T03:00:00Z")
        set_deltas = evaluate_quest_set_completion(
            source_event=source,
            completed_quest_ids=(
                "daily:kill_monsters",
                "daily:streak_correct",
                "daily:challenge_dragon",
            ),
            catalog=CANONICAL_QUEST_CATALOG,
        )
        assert [delta.quest_id for delta in set_deltas] == ["daily:all_complete"]
        derived_event = AuthoritativeEvent.from_server(
            event_id="evt-daily-set:quest-set:daily_primary",
            event_type="QUEST_SET_COMPLETED",
            user_id=source.user_id,
            source_authority="quest_evaluator:derived",
            source_operation_id="op-evt-daily-set:quest-set:daily_primary",
            occurred_at=source.occurred_at,
            payload={
                "quest_group": "daily_primary",
                "completed_quest_ids": (
                    "daily:challenge_dragon",
                    "daily:kill_monsters",
                    "daily:streak_correct",
                ),
            },
        )
        set_result = apply_progress_deltas(
            conn,
            event=derived_event,
            deltas=set_deltas,
            catalog=CANONICAL_QUEST_CATALOG,
            server_now=SERVER_NOW,
        )
        assert set_result[0].quest_id == "daily:all_complete"
        assert set_result[0].amount == 3
        assert _progress(conn, quest_id="daily:all_complete", period_key="2026-08-24")["completed"] == 1
    finally:
        conn.close()
