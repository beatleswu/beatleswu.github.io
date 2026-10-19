"""Real first-zone 1->2->3 star acceptance on disposable Native PostgreSQL.

The canonical 30-puzzle fixture is server-judged through real HTTP endpoints:
practice eligibility, 20-question Lord, and *distinct trusted map battles*.
Only accepted internal Map settlement can write star 2/3; this file never
calls star writers nor inserts fabricated review rows.
"""
from __future__ import annotations
import json
import pytest
from test_20261019_monthly_postgres import local_postgres, runtime as native_runtime
from test_20261019_lord_full_journey_native_pg import (
    lord_player, checked_json, seed_lord_eligibility, CORPUS, QUESTION_BY_ID,
    UID, ZONE,
)

MAP_HEADERS = {"X-Map-Battle-Client-Protocol":"v1"}
NEXT_ZONE = "k21_25"

def zone_state(client):
    state=checked_json(client.get("/api/adventure/bootstrap"))
    return {z["key"]:z for z in state["zones"]}

def star_ledger(app):
    with app.get_db() as conn:
        rows=conn.execute(
            "SELECT star_number,source,event_id FROM adventure_zone_star_earnings "
            "WHERE user_id=? AND zone_key=? ORDER BY star_number",
            (UID,ZONE),
        ).fetchall()
        auth=conn.execute(
            "SELECT earned_stars FROM adventure_zone_star_progress "
            "WHERE user_id=? AND zone_key=?", (UID,ZONE),
        ).fetchone()
        boss=conn.execute(
            "SELECT cleared,attempts,stars FROM adventure_boss_progress "
            "WHERE user_id=? AND zone_key=?", (UID,ZONE),
        ).fetchone()
        return {"ledger":[dict(row) for row in rows],
                "authority":None if auth is None else auth["earned_stars"],
                "boss":None if boss is None else dict(boss)}

def map_answer(client,question):
    started=checked_json(client.post(
        "/api/adventure/map-battles/v1/attempts",
        json={"zone_key":ZONE,"question_id":question["id"]},
        headers=MAP_HEADERS))
    payload={
      "battle_id":started["battle_id"],
      "attempt_id":started["attempt_id"],
      "submission_nonce":started["submission_nonce"],
      "battle_revision":started["battle"]["battle_revision"],
      "question_revision":started["question_revision"],
      "player_color":started["player_color"],
      "transform_id":started["transform_id"],
      "transform_version":started["transform_version"],
      "moves":[dict(question["accepted_moves"][0])],
    }
    settled=checked_json(client.post(
        "/api/adventure/map-battles/v1/answers",
        json=payload,headers=MAP_HEADERS))
    assert settled["result"]=="CORRECT", (question["id"],settled)
    assert settled["accepted"] is True and settled["duplicate"] is False
    assert settled["submission_id"]
    return payload,settled

def clear_lord_through_real_routes(client):
    seed_lord_eligibility(client)
    start=checked_json(client.post("/api/adventure/boss/start",json={"zone_key":ZONE}))
    assert start["total"]==20 and start["pass_score"]==16
    for qid in start["question_ids"]:
        question=QUESTION_BY_ID[qid]
        answer=checked_json(client.post("/api/srs/review",json={
            "question_id":qid, "grade":5,
            "source_context":f'boss_trial:{start["attempt_id"]}',
            "response_ms":1200,
            "boss_answer":{"moves":[dict(question["accepted_moves"][0])]},
        }))
        assert answer["ok"] is True
    end=checked_json(client.post("/api/adventure/boss/finish",
                                 json={"correct":0,"total":0}))
    assert end["passed"] is True and end["correct"]==20
    assert end["first_clear_projection"]["status"]=="COMPLETED"
    assert end["reward"]["first_clear"] is True
    return end

def test_three_stars_from_lord_and_thirty_trusted_map_answers(lord_player,monkeypatch):
    app,client=lord_player
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE","global")

    before=zone_state(client)[ZONE]
    assert before["zone_authority_stars"]==0
    assert before["second_star_required_correct"]==18
    assert before["third_star_required_correct"]==30

    lord_result=clear_lord_through_real_routes(client)
    after_lord=zone_state(client)
    assert after_lord[ZONE]["zone_authority_stars"]==1
    assert after_lord[NEXT_ZONE]["unlocked"] is True
    assert [r["star_number"] for r in star_ledger(app)["ledger"]]==[1]

    # Lord answers / practice credits are NOT enough for Map stars under
    # HOLD retroactive policy. Only trusted mbv1 correct map submissions count.
    one=after_lord[ZONE]
    assert one["zone_authority_stars"]==1

    first_replay=None
    for i,question in enumerate(CORPUS,1):
        payload,answer=map_answer(client,question)
        if i==1:
            first_replay=(payload,answer)
        if i in (1,17,18,19,29,30):
            state=zone_state(client)
            zone=state[ZONE]
            expected=1 if i<18 else (2 if i<30 else 3)
            assert zone["zone_authority_stars"]==expected, (
                i,zone["zone_authority_stars"],star_ledger(app))
            assert zone["stars"]==expected
            assert state[NEXT_ZONE]["unlocked"] is True
            assert zone["second_star_required_correct"]==18
            assert zone["third_star_required_correct"]==30
            actual=star_ledger(app)
            assert actual["authority"]==expected
            assert [r["star_number"] for r in actual["ledger"]]==list(range(1,expected+1))
            print("TRUSTED_MAP_COVERAGE_STAR",json.dumps({
                "accepted_distinct":i,"zone_stars":expected,
                "ledger_entries":len(actual["ledger"]),
                "progress_correct":zone["seen"]},
                ensure_ascii=True))

    final=star_ledger(app)
    assert final["authority"]==3
    assert len(final["ledger"])==3
    assert final["ledger"][0]["source"]=="authoritative_boss_clear"
    assert [row["source"] for row in final["ledger"][1:]]==[
        "authoritative_adventure_answer","authoritative_adventure_answer"]
    assert len({r["event_id"] for r in final["ledger"]})==3
    assert final["boss"]["attempts"]==1

    # Same accepted nonce is repeatable, but no additional star authority.
    duplicate_payload,original=first_replay
    duplicate=checked_json(client.post(
        "/api/adventure/map-battles/v1/answers",
        json=duplicate_payload,headers=MAP_HEADERS))
    assert duplicate["duplicate"] is True,duplicate
    assert star_ledger(app)==final

    # Reload with *fresh* Flask session cookie; all 3 stars are durable.
    second_client=app.app.test_client()
    with second_client.session_transaction() as s:
        s["user_id"]=UID
        s["username"]="p1-lord-disposable"
    fresh=zone_state(second_client)
    assert fresh[ZONE]["zone_authority_stars"]==3
    assert fresh[ZONE]["stars"]==3
    assert fresh[ZONE]["cleared"] is True
    assert fresh[NEXT_ZONE]["unlocked"] is True
    assert star_ledger(app)==final

    # Original E9 map must visually render the same three durable stars;
    # reading the API alone does not establish the user's actual UI state.
    import os
    import subprocess
    import threading
    from pathlib import Path
    from werkzeug.serving import make_server
    from migrations.companion_operations_v1 import upgrade as upgrade_companion
    from migrations.spirit_evolution_events_v1 import upgrade as upgrade_spirit_evolution
    with app.get_db() as conn:
        assert upgrade_companion(conn)["missing"]==[]
        assert upgrade_spirit_evolution(conn)["missing"]==[]
    session_cookie=second_client.get_cookie("session")
    assert session_cookie and session_cookie.value
    server=make_server("127.0.0.1",0,app.app.wsgi_app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        runner=(Path(__file__).resolve().parent / "e2e" /
                "run_20261019_three_star_world_map_browser.mjs")
        browser=subprocess.run(
            ["node",str(runner)],
            input=json.dumps({"origin":f"http://127.0.0.1:{server.server_port}",
                              "sessionCookie":session_cookie.value}),
            capture_output=True,text=True,encoding="utf-8",timeout=85,
            cwd=Path(__file__).resolve().parent.parent,
            env=dict(os.environ),
        )
        assert browser.returncode==0,browser.stderr[-2800:]+browser.stdout[-1200:]
        browser_report=json.loads(browser.stdout)
        assert browser_report["verdict"]=="REAL_INDEX_WORLD_MAP_THREE_AUTHORITY_STARS_PASS"
        assert browser_report["stage"]["earned"]==3
        assert browser_report["stage"]["server"]==3
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()

    print("P2_THREE_STARS_NATIVE_PG",json.dumps({
      "result":"THREE_STARS_PASS",
      "lord":{"score":lord_result["correct"],"pass_score":16,"star":1},
      "second_star_at_distinct":18,
      "third_star_at_distinct":30,
      "authority_stars":final["authority"],
      "physical_ledger":[{"star":r["star_number"],"source":r["source"]}
                         for r in final["ledger"]],
      "duplicate_no_award":True,
      "new_session_rehydrated":True,
      "zone2_unlocked":True,
      "production":False,
    },ensure_ascii=True))
