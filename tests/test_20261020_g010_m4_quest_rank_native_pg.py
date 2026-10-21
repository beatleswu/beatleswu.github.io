"""G010 M4: server-scored gameplay -> Quest V2 claim in real Tavern UI
-> lifetime XP leaderboard updates, weekly/monthly correct counts unchanged.
Native disposable PostgreSQL, real Flask, Chrome mouse/tablet (emulated).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import threading

import pytest
from werkzeug.serving import make_server

from test_20261019_monthly_postgres import local_postgres, runtime as native_runtime
from test_20261020_zone2_first_play_native_pg import (
    zone2_player, ZONE2, ZONE2_QUESTION, ZONE2_EXTRA_QUESTIONS,
)
from test_20261020_g010_m1_zone2_monster_lord_native_pg import judge
import test_20261019_lord_full_journey_native_pg as lord
from test_20261019_lord_full_journey_native_pg import lord_player
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from migrations.quest_progress_v2 import upgrade as upgrade_progress
from migrations.quest_claim_v1 import upgrade as upgrade_claim
from migrations.login_journey_v1 import upgrade as upgrade_login


def new_session(app):
    client=app.app.test_client()
    with client.session_transaction() as s:
        s["user_id"]=lord.UID
        s["username"]="p1-lord-disposable"
    return client


def fetch(client,route):
    r=client.get(route)
    assert r.status_code==200,(route,r.status_code,r.get_json())
    return r.get_json()


def my_score(board,key):
    player=next((r for r in board[key] if r["is_you"]),None)
    return int(player["score"]) if player else None


@pytest.mark.parametrize("mode",["desktop_mouse","chrome_tablet_touch"])
def test_m4_zone2_v2_quest_chrome_claim_refreshes_real_leaderboard(
    zone2_player, monkeypatch, mode
):
    app,initial=zone2_player
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE","global")
    # The release feature defaults OFF, and no claims can be made in that state.
    inactive=initial.get("/api/quests/v2")
    assert inactive.status_code==404 and inactive.get_json()["enabled"] is False
    disabled_claim=initial.post("/api/quests/v2/claim",json={
        "quest_id":"daily:streak_correct",
        "claim_operation_id":"g010-m4-disabled",
    })
    assert disabled_claim.status_code==404
    # Real unmodified Chrome proves the public Quest V2 panel cannot show
    # buttons or issue claims while server capability is OFF.
    off_cookie=initial.get_cookie("session")
    assert off_cookie and off_cookie.value
    off_server=make_server("127.0.0.1",0,app.app.wsgi_app,threaded=True)
    off_thread=threading.Thread(target=off_server.serve_forever,daemon=True)
    off_thread.start()
    try:
        off_script=Path(__file__).parent/"e2e"/"run_20261020_g010_m4_quest_off_real_browser.mjs"
        off_check=subprocess.run(
            ["node",str(off_script)],
            input=json.dumps({
                "origin":f"http://127.0.0.1:{off_server.server_port}",
                "sessionCookie":off_cookie.value,
            }),capture_output=True,text=True,encoding="utf-8",timeout=65,
            cwd=Path(__file__).resolve().parents[1],env=dict(os.environ))
        assert off_check.returncode==0,off_check.stderr[-2800:]+off_check.stdout[-850:]
        assert json.loads(off_check.stdout)["verdict"]=="G010_M4_QUEST_OFF_REAL_BROWSER_FAIL_CLOSED_PASS"
    finally:
        off_server.shutdown()
        off_thread.join(timeout=9)
        off_server.server_close()

    with app.get_db() as conn:
        assert upgrade_outbox(conn)["table"]=="domain_event_outbox"
        assert upgrade_progress(conn)["valid"]
        assert upgrade_claim(conn)["valid"]
        assert upgrade_login(conn)["valid"]
    monkeypatch.setenv("QUEST_V2_RUNTIME_ENABLED","true")

    lord.seed_lord_eligibility(initial)
    trial=lord.checked_json(initial.post(
        "/api/adventure/boss/start",json={"zone_key":lord.ZONE}))
    assert len(trial["question_ids"])==20
    for qid in trial["question_ids"]:
        q=lord.QUESTION_BY_ID[qid]
        score=lord.checked_json(initial.post("/api/srs/review",json={
            "question_id":qid,"grade":5,
            "source_context":f"boss_trial:{trial['attempt_id']}",
            "boss_answer":{"moves":[dict(q["accepted_moves"][0])]},
        }))
        assert score["ok"]
    finish=lord.checked_json(initial.post(
        "/api/adventure/boss/finish",json={"correct":0,"total":0}))
    assert finish["passed"] and finish["reward"]["first_clear"]

    client=new_session(app)
    for q in [ZONE2_QUESTION,*ZONE2_EXTRA_QUESTIONS[:2]]:
        answer,_=judge(client,q)
        assert answer.status_code==200,(answer.status_code,answer.get_json())
        assert answer.get_json()["accepted"]
        assert answer.get_json()["result"]=="CORRECT"
        assert not answer.get_json()["duplicate"]

    state=fetch(client,"/api/quests/v2")
    assert state["client_calculates_completion"] is False
    quest=next(q for q in state["quests"]
               if q["quest_id"]=="daily:streak_correct")
    assert quest["claimable"] is True
    assert quest["status"]=="CLAIMABLE"
    assert quest["claimed"] is False
    assert quest["progress"]>=3
    period=quest["period_key"]

    xp_before=fetch(client,"/api/xp/status")["xp"]
    coins_before=fetch(client,"/api/shop/catalog")["coins"]
    board_before=fetch(client,"/api/community/leaderboard")
    assert my_score(board_before,"alltime")==xp_before
    rules=fetch(client,"/api/community/leaderboard/reward-rules")
    assert rules["ok"] and rules["rules"]["monthly"]["minimum_score"]==150
    notif=fetch(client,"/api/community/leaderboard/reward-notifications")
    assert notif["ok"] and notif["notifications"]==[]

    one=client.get_cookie("session")
    two=new_session(app).get_cookie("session")
    assert one and two and one.value and two.value

    server=make_server("127.0.0.1",0,app.app.wsgi_app,threaded=True)
    worker=threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    try:
        runner=Path(__file__).parent/"e2e"/"run_20261020_g010_m4_quest_rank_real_browser.mjs"
        proc=subprocess.run(["node",str(runner)],
            input=json.dumps({
                "origin":f"http://127.0.0.1:{server.server_port}",
                "sessionCookie":one.value,"reloginCookie":two.value,
                "questId":quest["quest_id"],
                "beforeXp":xp_before,"afterXp":xp_before+20,
                "coinsAfter":coins_before+15,
            }),capture_output=True,text=True,encoding="utf-8",
            timeout=130,cwd=Path(__file__).resolve().parents[1],
            env={**os.environ,"GO_G010_M4_TOUCH":
                 "1" if mode=="chrome_tablet_touch" else "0"})
        assert proc.returncode==0,proc.stderr[-4600:]+proc.stdout[-1600:]
        report=json.loads(proc.stdout)
        assert report["verdict"]=="G010_M4_REAL_CHROME_QUEST_RANKING_RELOGIN_PASS"
        assert report["serverScoredWeeklyUnchanged"]
        assert report["serverScoredMonthlyUnchanged"]
        assert report["writes"]==["POST /api/quests/v2/claim"]
    finally:
        server.shutdown()
        worker.join(timeout=9)
        server.server_close()

    returned=new_session(app)
    xp_after=fetch(returned,"/api/xp/status")["xp"]
    assert xp_after-xp_before==20
    coins_after=fetch(returned,"/api/shop/catalog")["coins"]
    assert coins_after-coins_before==15
    final=fetch(returned,"/api/community/leaderboard")
    assert my_score(final,"alltime")==xp_after
    for board in ("weekly","monthly"):
        assert my_score(final,board)==my_score(board_before,board)
    quest_after=fetch(returned,"/api/quests/v2")
    completed=next(q for q in quest_after["quests"] if q["quest_id"]=="daily:streak_correct")
    assert completed["claimed"] and completed["status"]=="CLAIMED"
    assert not completed["claimable"]
    # Explicit independent post-UI retry must return duplicate with zero delta.
    replay=returned.post("/api/quests/v2/claim",json={
        "quest_id":"daily:streak_correct",
        "period_key":period,
        "claim_operation_id":"g010-m4-second-operation-dedupe",
    })
    assert replay.status_code==200 and replay.get_json()["duplicate"] is True
    assert fetch(returned,"/api/xp/status")["xp"]==xp_after
    assert fetch(returned,"/api/shop/catalog")["coins"]==coins_after
    with app.get_db() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM quest_claims_v2 "
            "WHERE user_id=? AND quest_id='daily:streak_correct'",
            (str(lord.UID),)).fetchone()["n"]==1
    # No leaderboard rewards may be minted simply for being listed on a
    # board or claiming a separate Quest V2 reward.
    assert fetch(returned,"/api/community/leaderboard/reward-notifications")["notifications"]==[]
