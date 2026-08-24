"""D017 runtime boundary, API, and default-off integration proofs."""

from __future__ import annotations

from datetime import datetime, timezone
import os
import sqlite3

import pytest

from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from migrations.login_journey_v1 import upgrade as upgrade_login
from migrations.quest_claim_v1 import upgrade as upgrade_claim
from migrations.quest_progress_v2 import (
    APPLICATION_TABLE_NAME,
    PROGRESS_TABLE_NAME,
    upgrade as upgrade_progress,
)
from quest_catalog import CANONICAL_QUEST_CATALOG
from quest_claim_authority import QuestClaimService
from quest_progress_evaluator import AuthoritativeEvent
from quest_runtime import (
    QuestRuntimeEventIdentityError,
    apply_quest_runtime_event,
    build_monster_defeat_event,
    build_review_settlement_event,
)
from quest_runtime_api import build_quest_v2_read_state
from quest_runtime_config import QUEST_V2_FEATURE_FLAG, quest_v2_runtime_enabled
from quest_reward_adapters import CallableQuestRewardAuthorities


SERVER_NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


class _DbContext:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()


def _db(*, login: bool = True, rewards: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    upgrade_outbox(conn)
    upgrade_progress(conn)
    upgrade_claim(conn)
    if login:
        upgrade_login(conn)
    if rewards:
        conn.executescript(
            """
            CREATE TABLE user_stats(
                user_id TEXT PRIMARY KEY,
                coins INTEGER NOT NULL DEFAULT 0,
                xp INTEGER NOT NULL DEFAULT 0,
                rank_xp INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE reward_sink(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                component TEXT NOT NULL,
                amount INTEGER NOT NULL
            );
            INSERT INTO user_stats(user_id) VALUES ('7');
            """
        )
    conn.commit()
    return conn


def _review(
    submission_id: str,
    occurred_at: str,
    *,
    correct: bool = True,
    monster_family: str | None = None,
) -> AuthoritativeEvent:
    return build_review_settlement_event(
        user_id=7,
        submission_id=submission_id,
        occurred_at=occurred_at,
        correct=correct,
        monster_family=monster_family,
    )


def _reward_authorities() -> CallableQuestRewardAuthorities:
    def grant_xp(conn, user_id, amount, reason, _profile_id):
        conn.execute(
            "INSERT INTO reward_sink(user_id,component,amount) VALUES (?,?,?)",
            (str(user_id), "xp", amount),
        )
        return amount

    def grant_coins(conn, user_id, amount, reason, _profile_id):
        conn.execute(
            "INSERT INTO reward_sink(user_id,component,amount) VALUES (?,?,?)",
            (str(user_id), "coins", amount),
        )
        return amount

    def grant_item(conn, user_id, item_id, quantity, reason, _profile_id):
        conn.execute(
            "INSERT INTO reward_sink(user_id,component,amount) VALUES (?,?,?)",
            (str(user_id), item_id, quantity),
        )
        return {
            "item_id": item_id,
            "granted_quantity": quantity,
            "ownership_authority": "fixture_inventory",
            "ownership_reference": f"fixture_inventory:{user_id}:{item_id}",
        }

    return CallableQuestRewardAuthorities(
        grant_xp=grant_xp,
        grant_coins=grant_coins,
        grant_item=grant_item,
    )


def test_feature_flag_is_server_default_off_and_fail_closed():
    assert quest_v2_runtime_enabled({}) is False
    assert quest_v2_runtime_enabled({QUEST_V2_FEATURE_FLAG: "true"}) is True
    assert quest_v2_runtime_enabled({QUEST_V2_FEATURE_FLAG: "unexpected"}) is False
    assert quest_v2_runtime_enabled({QUEST_V2_FEATURE_FLAG: ""}) is False


def test_server_event_identity_and_correctness_are_not_client_authority():
    with pytest.raises(QuestRuntimeEventIdentityError):
        build_review_settlement_event(
            user_id=7,
            submission_id=None,
            occurred_at="2026-08-24T01:00:00Z",
            correct=True,
        )
    event = _review("d017-answer-1", "2026-08-24T01:00:00Z", correct=True, monster_family="dragon")
    assert event.event_id == "quest:review:d017-answer-1:answer"
    assert event.source_authority == "review_settlement"
    assert event.payload["correct"] is True


def test_one_authoritative_review_event_fans_out_and_replays_without_duplicate_progress():
    conn = _db(login=False, rewards=False)
    try:
        event = _review("d017-dragon-1", "2026-08-24T01:00:00Z", monster_family="dragon")
        first = apply_quest_runtime_event(conn, event=event, server_now=SERVER_NOW)
        replay = apply_quest_runtime_event(conn, event=event, server_now=SERVER_NOW)
        assert {application.quest_id for application in first.applications} == {
            "daily:challenge_dragon",
            "daily:streak_correct",
        }
        assert all(application.duplicate is False for application in first.applications)
        assert all(application.duplicate is True for application in replay.applications)
        rows = conn.execute(
            f"SELECT quest_id, progress FROM {PROGRESS_TABLE_NAME} ORDER BY quest_id"
        ).fetchall()
        assert [(row["quest_id"], row["progress"]) for row in rows] == [
            ("daily:challenge_dragon", 1),
            ("daily:streak_correct", 1),
        ]
        assert conn.execute(f"SELECT COUNT(*) FROM {APPLICATION_TABLE_NAME}").fetchone()[0] == 2
    finally:
        conn.close()


def test_incorrect_dragon_never_progress_challenge_and_resets_streak():
    conn = _db(login=False, rewards=False)
    try:
        result = apply_quest_runtime_event(
            conn,
            event=_review("d017-wrong-dragon", "2026-08-24T02:00:00Z", correct=False, monster_family="dragon"),
            server_now=SERVER_NOW,
        )
        assert {application.quest_id for application in result.applications} == {"daily:streak_correct"}
        assert result.applications[0].operation == "RESET"
        assert conn.execute(
            f"SELECT COUNT(*) FROM {PROGRESS_TABLE_NAME} WHERE quest_id='daily:challenge_dragon'"
        ).fetchone()[0] == 0
        streak = conn.execute(
            f"SELECT progress FROM {PROGRESS_TABLE_NAME} WHERE quest_id='daily:streak_correct'"
        ).fetchone()
        assert streak[0] == 0
    finally:
        conn.close()


def test_monster_defeats_and_primary_completion_derive_all_complete_once():
    conn = _db(login=False, rewards=False)
    try:
        for index in range(5):
            result = apply_quest_runtime_event(
                conn,
                event=build_monster_defeat_event(
                    user_id=7,
                    submission_id=f"d017-kill-{index}",
                    occurred_at=f"2026-08-24T0{index + 1}:00:00Z",
                    monster_family="wolf",
                ),
                server_now=SERVER_NOW,
            )
            assert len(result.applications) == 1
        apply_quest_runtime_event(
            conn,
            event=_review("d017-dragon-complete", "2026-08-24T06:00:00Z", monster_family="dragon"),
            server_now=SERVER_NOW,
        )
        apply_quest_runtime_event(
            conn,
            event=_review("d017-correct-2", "2026-08-24T07:00:00Z"),
            server_now=SERVER_NOW,
        )
        final = apply_quest_runtime_event(
            conn,
            event=_review("d017-correct-3", "2026-08-24T08:00:00Z"),
            server_now=SERVER_NOW,
        )
        assert len(final.derived_applications) == 1
        assert final.derived_applications[0].quest_id == "daily:all_complete"
        assert final.derived_applications[0].resulting_progress == 3
        replay = apply_quest_runtime_event(
            conn,
            event=_review("d017-correct-3", "2026-08-24T08:00:00Z"),
            server_now=SERVER_NOW,
        )
        assert replay.derived_applications == ()
        assert conn.execute(
            f"SELECT progress, completed FROM {PROGRESS_TABLE_NAME} WHERE quest_id='daily:all_complete'"
        ).fetchone()["completed"] in (1, True)
    finally:
        conn.close()


def test_claim_api_authority_direct_service_replays_one_reward_and_one_lineage():
    conn = _db(login=False)
    try:
        event = build_monster_defeat_event(
            user_id=7,
            submission_id="d017-claim-kill",
            occurred_at="2026-08-24T01:00:00Z",
            monster_family="wolf",
        )
        for index in range(5):
            apply_quest_runtime_event(
                conn,
                event=build_monster_defeat_event(
                    user_id=7,
                    submission_id=f"d017-claim-kill-{index}",
                    occurred_at=f"2026-08-24T{index + 1:02d}:00:00Z",
                    monster_family="wolf",
                ),
                server_now=SERVER_NOW,
            )
        service = QuestClaimService(conn, reward_authorities=_reward_authorities())
        first = service.claim(
            7,
            "daily:kill_monsters",
            "2026-08-24",
            claim_operation_id="d017-claim-1",
            now=SERVER_NOW,
        )
        conn.commit()
        replay = service.claim(
            7,
            "daily:kill_monsters",
            "2026-08-24",
            claim_operation_id="d017-claim-1",
            now=SERVER_NOW,
        )
        competing = service.claim(
            7,
            "daily:kill_monsters",
            "2026-08-24",
            claim_operation_id="d017-claim-2",
            now=SERVER_NOW,
        )
        assert first.status == replay.status == competing.status == "GRANTED"
        assert first.created is True
        assert replay.duplicate is True
        assert competing.duplicate is True
        assert first.claim_id == replay.claim_id == competing.claim_id
        assert conn.execute("SELECT COUNT(*) FROM reward_sink").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM domain_event_outbox").fetchone()[0] == 1
    finally:
        conn.close()


def test_read_projection_is_server_owned_and_keeps_login_journey_separate():
    conn = _db()
    try:
        state = build_quest_v2_read_state(conn, user_id=7, now=SERVER_NOW)
        assert set(state["tabs"]) == {"Daily", "Weekly", "Adventure", "Chronicles"}
        assert all(item["claimable"] is False for item in state["quests"])
        assert state["client_calculates_completion"] is False
        assert state["login_journey"]["journey_length"] == 7
        assert state["login_journey"]["reward_count"] == 0
    finally:
        conn.close()


def test_runtime_review_bridge_preserves_incorrect_answer_reset(monkeypatch):
    monkeypatch.setenv(QUEST_V2_FEATURE_FLAG, "true")
    monkeypatch.setenv("SECRET_KEY", "d017-api-test-secret")
    import app as app_module

    conn = _db(login=False, rewards=False)
    try:
        results = app_module._apply_quest_v2_review_events(
            conn,
            uid=7,
            submission_id="d017-bridge-wrong",
            grade=0,
            monster_data={"monster": {"type": "dragon", "defeated": False}},
            occurred_at=SERVER_NOW,
            should_grant_progress=False,
        )
        assert len(results) == 1
        assert results[0].applications[0].operation == "RESET"
    finally:
        conn.close()


def test_feature_off_api_does_not_write_or_expose_v2(monkeypatch):
    monkeypatch.delenv(QUEST_V2_FEATURE_FLAG, raising=False)
    monkeypatch.setenv("SECRET_KEY", "d017-api-test-secret")
    import app as app_module

    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
    response = client.get("/api/quests/v2")
    assert response.status_code == 404
    assert response.get_json()["enabled"] is False


def test_feature_on_claim_api_rejects_client_authority_fields_before_database(monkeypatch):
    monkeypatch.setenv(QUEST_V2_FEATURE_FLAG, "true")
    monkeypatch.setenv("SECRET_KEY", "d017-api-test-secret")
    import app as app_module

    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
    response = client.post(
        "/api/quests/v2/claim",
        json={
            "quest_id": "daily:kill_monsters",
            "claim_operation_id": "d017-api-claim",
            "completed": True,
            "reward_profile_id": "forged",
        },
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "client_authority_field_rejected"


def test_feature_on_read_api_returns_server_projection(monkeypatch):
    monkeypatch.setenv(QUEST_V2_FEATURE_FLAG, "true")
    monkeypatch.setenv("SECRET_KEY", "d017-api-test-secret")
    import app as app_module

    conn = _db()
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(conn))
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
    response = client.get("/api/quests/v2")
    assert response.status_code == 200
    body = response.get_json()
    assert body["client_calculates_completion"] is False
    assert body["login_journey"]["journey_length"] == 7
    assert set(body["tabs"]) == {"Daily", "Weekly", "Adventure", "Chronicles"}
    conn.close()


def test_feature_on_claim_api_settles_and_replays_through_d015(monkeypatch):
    monkeypatch.setenv(QUEST_V2_FEATURE_FLAG, "true")
    monkeypatch.setenv("SECRET_KEY", "d017-api-test-secret")
    import app as app_module

    conn = _db(login=False)
    for index in range(5):
        apply_quest_runtime_event(
            conn,
            event=build_monster_defeat_event(
                user_id=7,
                submission_id=f"d017-api-kill-{index}",
                occurred_at=f"2026-08-24T{index + 1:02d}:00:00Z",
                monster_family="wolf",
            ),
            server_now=SERVER_NOW,
        )
    conn.commit()
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(conn))
    monkeypatch.setattr(app_module, "_quest_v2_reward_authorities", _reward_authorities)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
    first = client.post(
        "/api/quests/v2/claim",
        json={
            "quest_id": "daily:kill_monsters",
            "period_key": "2026-08-24",
            "claim_operation_id": "d017-api-claim-success",
        },
    )
    replay = client.post(
        "/api/quests/v2/claim",
        json={
            "quest_id": "daily:kill_monsters",
            "period_key": "2026-08-24",
            "claim_operation_id": "d017-api-claim-retry",
        },
    )
    assert first.status_code == replay.status_code == 200
    assert first.get_json()["ok"] is True
    assert replay.get_json()["duplicate"] is True
    assert conn.execute("SELECT COUNT(*) FROM reward_sink").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM domain_event_outbox").fetchone()[0] == 1
    conn.close()
