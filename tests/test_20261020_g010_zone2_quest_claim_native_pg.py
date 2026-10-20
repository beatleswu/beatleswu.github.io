"""G010 M1: real Zone1 boss unlock -> Zone2 authoritative Map Battle -> Quest V2 claim.

Disposable native PostgreSQL only. Quest V2 opt-in is local to this test;
no production feature flag, player, Monster roster or reward gate is changed.
"""
from __future__ import annotations

import datetime
import pytest

from test_20261019_monthly_postgres import local_postgres, runtime as native_runtime
from test_20261020_zone2_first_play_native_pg import (
    zone2_player, ZONE2, ZONE2_QUESTION, ZONE2_EXTRA_QUESTIONS, HEADERS,
)
import test_20261019_lord_full_journey_native_pg as lord
from test_20261019_lord_full_journey_native_pg import lord_player
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from migrations.quest_progress_v2 import upgrade as upgrade_progress
from migrations.quest_claim_v1 import upgrade as upgrade_claim
from migrations.login_journey_v1 import upgrade as upgrade_login


def _client(app):
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = lord.UID
        session["username"] = "p1-lord-disposable"
    return client


def _state(app, client):
    r = client.get("/api/quests/v2")
    assert r.status_code == 200, (r.status_code, r.get_json())
    return r.get_json()


def test_g010_zone2_server_judged_answers_quest_reward_new_session(
    zone2_player, monkeypatch
):
    app, client = zone2_player
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "global")

    # Legacy Quest feature must be OFF unless explicitly enabled.
    disabled = client.get("/api/quests/v2")
    assert disabled.status_code == 404
    assert disabled.get_json()["enabled"] is False

    lord.seed_lord_eligibility(client)
    started = lord.checked_json(client.post(
        "/api/adventure/boss/start", json={"zone_key": lord.ZONE}))
    for i, qid in enumerate(started["question_ids"]):
        q = lord.QUESTION_BY_ID[qid]
        answer = lord.checked_json(client.post(
            "/api/srs/review",
            json={"question_id":qid, "grade":5,
                  "source_context":f"boss_trial:{started['attempt_id']}",
                  "response_ms":800+i,
                  "boss_answer":{"moves":[dict(q["accepted_moves"][0])]}}
        ))
        assert answer["ok"]
    assert lord.checked_json(client.post("/api/adventure/boss/finish",
                                        json={"correct":0,"total":0}))["passed"]

    with app.get_db() as conn:
        assert upgrade_outbox(conn)["table"] == "domain_event_outbox"
        assert upgrade_progress(conn)["valid"] is True
        assert upgrade_claim(conn)["valid"] is True
        assert upgrade_login(conn)["valid"] is True
    monkeypatch.setenv("QUEST_V2_RUNTIME_ENABLED", "true")

    returner = _client(app)
    initial = _state(app, returner)
    assert initial["client_calculates_completion"] is False
    assert initial["tabs"]["Daily"] is not None

    submissions = []
    for q in [ZONE2_QUESTION] + ZONE2_EXTRA_QUESTIONS[:2]:
        issued = lord.checked_json(returner.post(
            "/api/adventure/map-battles/v1/attempts",
            json={"zone_key": ZONE2, "question_id":q["id"]},
            headers=HEADERS,
        ))
        verdict = lord.checked_json(returner.post(
            "/api/adventure/map-battles/v1/answers",
            json={
                "battle_id":issued["battle_id"],
                "attempt_id":issued["attempt_id"],
                "submission_nonce":issued["submission_nonce"],
                "battle_revision":issued["battle"]["battle_revision"],
                "question_revision":issued["question_revision"],
                "player_color":issued["player_color"],
                "transform_id":issued["transform_id"],
                "transform_version":issued["transform_version"],
                "moves":[dict(q["accepted_moves"][0])],
            },
            headers=HEADERS,
        ))
        assert verdict["accepted"] is True and verdict["result"] == "CORRECT", verdict
        assert verdict["duplicate"] is False
        assert verdict.get("progression",{}).get("status") != "pending", verdict
        submissions.append(verdict)

    # The server judge (not player-reported grade) must be source of V2 quest.
    before = _state(app, returner)
    with app.get_db() as conn:
        rows = conn.execute(
            "SELECT quest_id, progress, completed, period_key FROM quest_progress_v2 "
            "WHERE user_id=? ORDER BY quest_id", (str(lord.UID),)
        ).fetchall()
    assert any(row["quest_id"] == "daily:streak_correct"
               and row["progress"] >= 3 and row["completed"]
               for row in rows), [dict(row) for row in rows]

    with app.get_db() as conn:
        before_coins = int(conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=?", (lord.UID,)
        ).fetchone()["coins"])
        before_candy = conn.execute(
            "SELECT qty FROM pet_inventory WHERE user_id=? AND item_key='go_spirit_candy'",
            (lord.UID,)
        ).fetchone()
        qty_before = int(before_candy["qty"]) if before_candy else 0

    fresh = _client(app)
    persisted = _state(app, fresh)
    assert persisted["tabs"]["Daily"] is not None
    period_key = next(row["period_key"] for row in rows
                      if row["quest_id"] == "daily:streak_correct")
    claim_payload = {
        "quest_id":"daily:streak_correct",
        "period_key":period_key,
        "claim_operation_id":"g010-zone2-quest-one-time",
    }
    earned = lord.checked_json(fresh.post(
        "/api/quests/v2/claim",json=claim_payload))
    assert earned["ok"] is True, earned
    replay = lord.checked_json(fresh.post(
        "/api/quests/v2/claim",json=claim_payload))
    assert replay["duplicate"] is True, replay

    with app.get_db() as conn:
        after_coins = int(conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=?", (lord.UID,)
        ).fetchone()["coins"])
        candy = conn.execute(
            "SELECT qty FROM pet_inventory WHERE user_id=? AND item_key='go_spirit_candy'",
            (lord.UID,)
        ).fetchone()
        assert after_coins - before_coins == 15
        assert int(candy["qty"]) - qty_before == 1
        claim_count = conn.execute(
            "SELECT COUNT(*) AS n FROM quest_claims_v2 "
            "WHERE user_id=? AND quest_id='daily:streak_correct'",
            (str(lord.UID),)
        ).fetchone()
        assert int(claim_count["n"]) == 1

    # The real player-facing Backpack reads Pet inventory and the Shop
    # reads canonical Coins. Confirm both now see the newly settled reward.
    return_session = _client(app)
    pet_status = return_session.get("/api/pet/status")
    assert pet_status.status_code == 200, pet_status.get_json()
    visible_pet_items = pet_status.get_json()["inventory"]
    assert any(item["key"] == "go_spirit_candy" and item["qty"] >= 1
               for item in visible_pet_items), visible_pet_items
    catalog = return_session.get("/api/shop/catalog")
    assert catalog.status_code == 200, catalog.get_json()
    assert catalog.get_json()["coins"] == after_coins
    final = _state(app, return_session)
    assert final["tabs"]["Daily"] is not None
