"""G085E P0 unmocked player CTA -> real Chrome WGo -> native PG judgement
-> XP/progression -> quest coin + item one-time claim -> original request replay.
No mocked API, synthetic questions in disposable native PG fixture ONLY.
"""
from __future__ import annotations
import json,os,subprocess,threading,hashlib
from pathlib import Path
import pytest
from werkzeug.serving import make_server
from test_20261020_zone2_first_play_native_pg import (
    zone2_player, ZONE2, ZONE2_QUESTION, ZONE2_EXTRA_QUESTIONS, HEADERS,
)
import test_20261019_lord_full_journey_native_pg as lord
from test_20261019_lord_full_journey_native_pg import lord_player
from test_20261019_monthly_postgres import local_postgres, runtime as native_runtime
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from migrations.quest_progress_v2 import upgrade as upgrade_progress
from migrations.quest_claim_v1 import upgrade as upgrade_claim
from migrations.login_journey_v1 import upgrade as upgrade_login
from migrations.companion_operations_v1 import upgrade as upgrade_companion
from migrations.spirit_evolution_events_v1 import upgrade as upgrade_evolution

ROOT=Path(__file__).resolve().parents[1]
UID=lord.UID
TABLES=(
    "user_stats","review_log","srs_cards","map_battle_submissions",
    "quest_progress_v2","quest_claims_v2","currency_log","pet_inventory",
    "domain_event_outbox",
)
def _client(app):
    c=app.app.test_client()
    with c.session_transaction() as s:
        s["user_id"]=UID
        s["username"]="p1-lord-disposable"
    return c

def _safeshot(app):
    with app.get_db() as conn:
        state={}
        for table in TABLES:
            rows=[dict(x) for x in conn.execute("SELECT * FROM "+table).fetchall()]
            state[table]=sorted(
                [json.dumps(x,sort_keys=True,default=str) for x in rows])
        return state

def _check(response):
    assert response.status_code==200,(response.status_code,response.get_json())
    return response.get_json()

def _answer(client,q,*,reject_new_forgery=False):
    issued=_check(client.post("/api/adventure/map-battles/v1/attempts",
        json={"zone_key":ZONE2,"question_id":q["id"]},headers=HEADERS))
    request={
        "battle_id":issued["battle_id"],"attempt_id":issued["attempt_id"],
        "submission_nonce":issued["submission_nonce"],
        "battle_revision":issued["battle"]["battle_revision"],
        "question_revision":issued["question_revision"],
        "player_color":issued["player_color"],
        "transform_id":issued["transform_id"],
        "transform_version":issued["transform_version"],
        "moves":[dict(q["accepted_moves"][0])],
    }
    if reject_new_forgery:
        # A NEVER-COMMITTED nonce must refuse all client-owned grade/coins.
        forgery=dict(request, correct=True, grade=5, coins=9999)
        forbidden=client.post("/api/adventure/map-battles/v1/answers",
                              json=forgery,headers=HEADERS)
        assert forbidden.status_code==400,forbidden.get_json()
    verdict=_check(client.post("/api/adventure/map-battles/v1/answers",
        json=request,headers=HEADERS))
    assert verdict["result"]=="CORRECT" and verdict["accepted"] is True
    assert verdict["duplicate"] is False
    assert verdict.get("progression",{}).get("status")=="applied",verdict
    return verdict

@pytest.mark.parametrize("ui_mode",["desktop_mouse","tablet_touch"])
def test_unmocked_story_ready_cta_real_chrome_pg_battle_answer_xp_quest_claim_once(
        zone2_player,monkeypatch,tmp_path,ui_mode):
    app,player=zone2_player
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE","global")
    assert monkeypatch is not None
    # Complete actual server-judged Zone 1 Boss before permitting Zone 2.
    lord.seed_lord_eligibility(player)
    start=_check(player.post("/api/adventure/boss/start",json={"zone_key":lord.ZONE}))
    assert len(start["question_ids"])==20
    for idx,qid in enumerate(start["question_ids"]):
        q=lord.QUESTION_BY_ID[qid]
        r=_check(player.post("/api/srs/review",json={
            "question_id":qid,"grade":5,
            "source_context":f"boss_trial:{start['attempt_id']}",
            "response_ms":1200+idx,
            "boss_answer":{"moves":[dict(q["accepted_moves"][0])]},
        }))
        assert r["ok"] is True
    completed=_check(player.post("/api/adventure/boss/finish",json={"correct":0,"total":0}))
    assert completed["passed"] is True
    assert completed["first_clear_projection"]["status"]=="COMPLETED"
    zones={x["key"]:x for x in _check(player.get("/api/adventure/bootstrap"))["zones"]}
    assert zones[ZONE2]["unlocked"] is True
    with app.get_db() as conn:
        for upgrade in (upgrade_outbox,upgrade_progress,upgrade_claim,upgrade_login,
                        upgrade_companion,upgrade_evolution):
            result=upgrade(conn)
            assert isinstance(result,dict),result
    monkeypatch.setenv("QUEST_V2_RUNTIME_ENABLED","true")
    c=_client(app)
    assert _check(c.get("/api/quests/v2"))["client_calculates_completion"] is False
    # Two independent genuine answers, then a third *actual WGo pointer*
    # from the visible post-story Adventure CTA triggers streak reward.
    # First answer = 25% (<30% lord threshold). The real map CTA must
    # still be the training CTA, not the legitimately unlocked boss CTA.
    _answer(c,ZONE2_QUESTION)
    before_browser=_safeshot(app)
    with app.get_db() as conn:
        before_xp=int(conn.execute("SELECT xp FROM user_stats WHERE user_id=?",(UID,)).fetchone()["xp"])
    cookie=c.get_cookie("session")
    assert cookie and cookie.value
    server=make_server("127.0.0.1",0,app.app.wsgi_app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    browser_receipt=None
    try:
        js=ROOT/"tests/e2e/g085e_real_zone2_cta_judge_reward_browser.mjs"
        env={**os.environ,"GO_P2_ZONE2_TOUCH":"1" if ui_mode=="tablet_touch" else "0"}
        proc=subprocess.run(["node",str(js)],
            input=json.dumps({"origin":f"http://127.0.0.1:{server.server_port}",
                              "sessionCookie":cookie.value}),
            capture_output=True,text=True,encoding="utf8",errors="replace",
            cwd=ROOT,env=env,timeout=115)
        (tmp_path/"g085e_browser_stdout.txt").write_text(proc.stdout,encoding="utf8")
        (tmp_path/"g085e_browser_stderr.txt").write_text(proc.stderr,encoding="utf8")
        assert proc.returncode==0,proc.stderr[-4000:]+proc.stdout[-1300:]
        browser_receipt=json.loads(proc.stdout.strip())
        assert browser_receipt["verdict"]=="REAL_E9_ZONE2_WGO_ANSWER_PASS"
        assert browser_receipt["stage"]=="durable_bootstrap"
        assert browser_receipt["boardQuestion"]==970032
        assert browser_receipt["mapAnswers"]==[{"status":200,"path":"/api/adventure/map-battles/v1/answers"}]
        assert browser_receipt["exactAnswerRequest"]["submission_nonce"]
        assert browser_receipt["answerReceipt"]["progression"]["status"]=="applied"
        assert browser_receipt["after"]["correctCount"]>=2
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()
    with app.get_db() as conn:
        after_xp=int(conn.execute("SELECT xp FROM user_stats WHERE user_id=?",(UID,)).fetchone()["xp"])
    assert after_xp>before_xp
    snap=_safeshot(app)
    # Replay EXACT bytes from the genuine Chrome WGo POST in a different
    # authenticated session. No second XP, SRS, Quest or coin payout.
    fresh=_client(app)
    exact=browser_receipt["exactAnswerRequest"]
    replay=_check(fresh.post("/api/adventure/map-battles/v1/answers",
                            json=exact,headers=HEADERS))
    assert replay["duplicate"] is True,replay
    assert _safeshot(app)==snap, "duplicate WGo answer mutated durable PG state"
    # A SETTLED nonce intentionally permits stale legacy display fields
    # while replaying the original, already-authoritative answer.  It
    # never judges those client claims or executes a second grant.
    forged=dict(exact,correct=True,grade=5,coins=9999)
    legacy_retry=_check(fresh.post("/api/adventure/map-battles/v1/answers",
                           json=forged,headers=HEADERS))
    assert legacy_retry["duplicate"] is True and legacy_retry["result"]=="CORRECT"
    assert _safeshot(app)==snap,"forged duplicate changed durable PG state"
    # Third original trusted API answer closes the daily streak after the
    # *second*, player-controlled real Chrome/WGo answer. This preserves
    # the mandatory first-entry training CTA instead of silently switching
    # to the boss CTA at >=30% mastery before Chrome is opened.
    third=_answer(fresh,ZONE2_EXTRA_QUESTIONS[1],reject_new_forgery=True)  # 970033
    assert third["progression"]["status"]=="applied"
    with app.get_db() as conn:
        progress=conn.execute(
            "SELECT quest_id,progress,completed,period_key FROM quest_progress_v2 "
            "WHERE user_id=? AND quest_id='daily:streak_correct'",(str(UID),)).fetchone()
        assert progress and progress["completed"] and progress["progress"]>=3,progress
        before_coins=int(conn.execute("SELECT coins FROM user_stats WHERE user_id=?",(UID,)).fetchone()["coins"])
        prev=conn.execute("SELECT qty FROM pet_inventory WHERE user_id=? AND item_key='go_spirit_candy'",
                          (UID,)).fetchone()
        candy_before=int(prev["qty"]) if prev else 0
    claim={"quest_id":"daily:streak_correct","period_key":progress["period_key"],
           "claim_operation_id":"g085e-native-chrome-quest-once"}
    awarded=_check(fresh.post("/api/quests/v2/claim",json=claim))
    assert awarded["ok"] is True
    claimed=_safeshot(app)
    next_session=_client(app)
    duplicate=_check(next_session.post("/api/quests/v2/claim",json=claim))
    assert duplicate["duplicate"] is True
    assert _safeshot(app)==claimed
    with app.get_db() as conn:
        coins_after=int(conn.execute("SELECT coins FROM user_stats WHERE user_id=?",(UID,)).fetchone()["coins"])
        candy=conn.execute("SELECT qty FROM pet_inventory WHERE user_id=? AND item_key='go_spirit_candy'",
                           (UID,)).fetchone()
        assert coins_after-before_coins==15,(before_coins,coins_after)
        assert candy and int(candy["qty"])-candy_before==1
        count=conn.execute("SELECT COUNT(*) n FROM quest_claims_v2 WHERE user_id=? "
            "AND quest_id='daily:streak_correct'",(str(UID),)).fetchone()["n"]
        assert int(count)==1
    catalog=_check(next_session.get("/api/shop/catalog"))
    assert catalog["coins"]==coins_after
    pet=_check(next_session.get("/api/pet/status"))
    assert any(v["key"]=="go_spirit_candy"and v["qty"]>=1 for v in pet["inventory"])
    evidence={"schema":"G085E_UNMOCKED_STORY_CTA_CHROME_REAL_PG_JUDGE_REWARD_ONCE",
              "mode":ui_mode,"real_flask_server":True,
              "real_native_postgres":True,"real_chrome_pointer":True,
              "mocked_endpoints":[],"first_clear":completed["first_clear_projection"]["status"],
              "browser_checks":browser_receipt,
              "original_exact_browser_replay_duplicate":True,
              "new_unsettled_nonce_forgery_rejected":True,
              "committed_nonce_legacy_fields_return_cached_result_no_write":True,
              "db_9_table_snapshot_stable_on_replay":True,
              "xp_gain_from_browser":after_xp-before_xp,
              "claimed_coins_once":coins_after-before_coins,
              "claimed_spirit_candy_once":int(candy["qty"])-candy_before,
              "claim_count":int(count),"fresh_session_reward_visible":True,
              "production_write":False,"native_ipad_safari":False}
    # Durable receipts from synthetic disposable PostgreSQL only.
    # Keep pytest's temporary runtime directories ephemeral.
    receipt_root=Path(os.environ.get("G085E_RECEIPT_ROOT") or tmp_path)
    assert receipt_root.is_absolute()
    receipt_root.mkdir(parents=True,exist_ok=True)
    dest=receipt_root/f"G085E_P0_{ui_mode}_RECEIPT.json"
    with dest.open("x",encoding="utf8") as receipt:
        receipt.write(json.dumps(evidence,ensure_ascii=False,indent=2,default=str))
    print("G085E_REAL_CTA_PG_REWARD_ONCE_PASS",ui_mode,str(dest),flush=True)
