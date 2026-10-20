"""G010 M1b/M1c: Zone2 Monster defeat, Quest, real Lord and unlock.

Synthetic questions and player. ALL database writes in temporary localhost PG.
No real player/release admission is claimed.
"""
from __future__ import annotations
from copy import deepcopy
import pytest

import test_20261019_lord_full_journey_native_pg as lord
from test_20261019_lord_full_journey_native_pg import lord_player
from test_20261019_monthly_postgres import local_postgres, runtime as native_runtime
from test_20261020_zone2_first_play_native_pg import ZONE2, ZONE2_QUESTION, HEADERS
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from migrations.quest_progress_v2 import upgrade as upgrade_progress
from migrations.quest_claim_v1 import upgrade as upgrade_claim
from adventure_zone1_2_monster_runtime_provider import DEFERRED_REWARD_DROP_POLICY

ZONE3 = "k16_20"
ZONE2_POOL = []
for idx in range(26):
    q = deepcopy(ZONE2_QUESTION)
    qid = 972000 + idx
    q.update({
        "id":qid, "source":f"disposable-g010-zone2/q{qid}.sgf",
        "display_name":f"G010 Zone2 M1 q{idx+1:02}",
        "content": ZONE2_QUESTION["content"].replace(
            "Unique zone two player map battle answer",
            f"G010 unique Zone2 q{idx+1:02}"),
    })
    ZONE2_POOL.append(q)
BY_ID = {x["id"]:x for x in ZONE2_POOL}


@pytest.fixture
def g010_player(monkeypatch, request):
    # Must extend before Lord fixture builds frozen disposable puzzle identity.
    monkeypatch.setattr(lord,"CORPUS",lord.CORPUS+ZONE2_POOL)
    return request.getfixturevalue("lord_player")


def login(app):
    c=app.app.test_client()
    with c.session_transaction() as s:
        s["user_id"]=lord.UID
        s["username"]="p1-lord-disposable"
    return c


def judge(c, q):
    issued=lord.checked_json(c.post(
        "/api/adventure/map-battles/v1/attempts",
        json={"zone_key":ZONE2,"question_id":q["id"]},headers=HEADERS))
    response=c.post("/api/adventure/map-battles/v1/answers",json={
        "battle_id":issued["battle_id"],
        "attempt_id":issued["attempt_id"],
        "submission_nonce":issued["submission_nonce"],
        "battle_revision":issued["battle"]["battle_revision"],
        "question_revision":issued["question_revision"],
        "player_color":issued["player_color"],
        "transform_id":issued["transform_id"],
        "transform_version":issued["transform_version"],
        "moves":[dict(q["accepted_moves"][0])],
    },headers=HEADERS)
    return response, issued


def test_zone2_monster_defeat_and_twenty_question_lord_unlock(
    g010_player, monkeypatch, caplog
):
    app,c=g010_player
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE","global")
    with app.get_db() as conn:
        upgrade_outbox(conn)
        assert upgrade_progress(conn)["valid"]
        assert upgrade_claim(conn)["valid"]
    monkeypatch.setenv("QUEST_V2_RUNTIME_ENABLED","1")

    lord.seed_lord_eligibility(c)
    z1=lord.checked_json(c.post("/api/adventure/boss/start",json={"zone_key":lord.ZONE}))
    for qid in z1["question_ids"]:
        q=lord.QUESTION_BY_ID[qid]
        r=lord.checked_json(c.post("/api/srs/review",json={
            "question_id":qid,"grade":5,"source_context":f"boss_trial:{z1['attempt_id']}",
            "boss_answer":{"moves":[dict(q["accepted_moves"][0])]},
        }))
        assert r["ok"]
    assert lord.checked_json(c.post("/api/adventure/boss/finish",
                                    json={"correct":0,"total":0}))["passed"]

    fresh=login(app)
    init=lord.checked_json(fresh.get("/api/adventure/bootstrap"))
    assert next(z for z in init["zones"] if z["key"]==ZONE2)["unlocked"]
    assert next(z for z in init["zones"] if z["key"]==ZONE3)["unlocked"] is False

    encountered=[]
    defeated=[]
    defeated_binding=None
    last=None
    for q in ZONE2_POOL[:20]:
        answer,issued=judge(fresh,q)
        payload=answer.get_json()
        if answer.status_code != 200:
            print("G010_DIAG",q["id"], payload, caplog.text[-8500:],flush=True)
        assert answer.status_code==200,(q["id"],answer.status_code,payload)
        assert payload["accepted"] and payload["result"]=="CORRECT",payload
        assert not payload["duplicate"]
        encountered.append(issued["battle"]["monster_hp_max"])
        if payload.get("monster_defeated") is True and payload.get("monster_hp_after") == 0:
            defeated.append(q["id"])
            defeated_binding=(q,issued)
        last=payload
    assert len(encountered)==20
    assert defeated,"20 correct judge results must beat at least one Zone2 Monster"

    with app.get_db() as conn:
        monster = conn.execute(
            "SELECT monster_hp,state,migration_source FROM map_battles "
            "WHERE user_id=? ORDER BY created_at", (lord.UID,)
        ).fetchall()
        progress=conn.execute(
            "SELECT quest_id,progress,completed FROM quest_progress_v2 "
            "WHERE user_id=?",(str(lord.UID),)
        ).fetchall()
    assert any(row["monster_hp"]==0 for row in monster),[dict(r) for r in monster]
    assert all(row["migration_source"] != "legacy-adventure-map" for row in monster)
    # No unpublished Zone1/2 coins/drops: only canonical defeat and Quest event.
    with app.get_db() as conn:
        events=conn.execute(
            "SELECT payload FROM domain_event_outbox "
            "WHERE player_id=? AND event_type='MONSTER_DEFEATED'",
            (str(lord.UID),)
        ).fetchall()
        monster_coins=conn.execute(
            "SELECT COUNT(*) AS n FROM currency_log "
            "WHERE user_id=? AND reason='monster_kill'",(lord.UID,)
        ).fetchone()["n"]
        equipment=conn.execute(
            "SELECT COUNT(*) AS n FROM player_inventory WHERE user_id=?",
            (lord.UID,)
        ).fetchone()["n"]
    assert len(events)==1,events
    evidence=events[0]["payload"]
    assert evidence["reward_drop_policy"] == DEFERRED_REWARD_DROP_POLICY
    assert evidence["monster_id"].startswith("M")
    assert evidence["zone_id"]=="Z2"
    assert evidence["coins_granted"]==0
    assert evidence["functional_drop_id"] is None and evidence["appearance_drop_id"] is None
    assert monster_coins==0 and equipment==0
    # Exact nonce replay must not manufacture a second monster/quest event.
    defeated_q,first_issued=defeated_binding
    replay_payload={
        "battle_id":first_issued["battle_id"],
        "attempt_id":first_issued["attempt_id"],
        "submission_nonce":first_issued["submission_nonce"],
        "battle_revision":first_issued["battle"]["battle_revision"],
        "question_revision":first_issued["question_revision"],
        "player_color":first_issued["player_color"],
        "transform_id":first_issued["transform_id"],
        "transform_version":first_issued["transform_version"],
        "moves":[dict(defeated_q["accepted_moves"][0])],
    }
    retry=fresh.post("/api/adventure/map-battles/v1/answers",
                     json=replay_payload, headers=HEADERS)
    assert retry.status_code==200,(retry.status_code,retry.get_json())
    assert retry.get_json()["duplicate"] is True
    with app.get_db() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM domain_event_outbox "
            "WHERE player_id=? AND event_type='MONSTER_DEFEATED'",
            (str(lord.UID),)
        ).fetchone()["n"]==1
    assert any(row["quest_id"]=="daily:kill_monsters" and row["progress"]>0
               for row in progress),[dict(r) for r in progress]

    ready=lord.checked_json(login(app).get("/api/adventure/bootstrap"))
    state=next(z for z in ready["zones"] if z["key"]==ZONE2)
    assert state["boss_ready"],state
    trial=lord.checked_json(fresh.post("/api/adventure/boss/start",
                                      json={"zone_key":ZONE2}))
    assert len(trial["question_ids"])==20,trial
    assert set(trial["question_ids"]) <= set(BY_ID)
    incomplete=fresh.post("/api/adventure/boss/finish",json={"correct":20,"total":20})
    assert incomplete.status_code!=200
    for qid in trial["question_ids"]:
        q=BY_ID[qid]
        a=lord.checked_json(fresh.post("/api/srs/review",json={
            "question_id":qid, "grade":5,
            "source_context":f"boss_trial:{trial['attempt_id']}",
            "boss_answer":{"moves":[dict(q["accepted_moves"][0])]},
        }))
        assert a["ok"],a
    clear=lord.checked_json(fresh.post("/api/adventure/boss/finish",
                                      json={"correct":0,"total":0}))
    assert clear["passed"] and clear["first_clear_projection"]["status"]=="COMPLETED",clear
    after=lord.checked_json(login(app).get("/api/adventure/bootstrap"))
    zones={z["key"]:z for z in after["zones"]}
    assert zones[ZONE2]["cleared"]
    assert zones[ZONE3]["unlocked"]
    with app.get_db() as conn:
        first=conn.execute(
            "SELECT COUNT(*) AS n FROM adventure_zone_unlocks "
            "WHERE user_id=? AND zone_key=?",(lord.UID,ZONE3)
        ).fetchone()["n"]
        assert first==1

    # Owner-approved replay is a new server-created Lord attempt; the
    # first-clear item/star and Zone3 unlock are strictly once-only.
    redo=login(app)
    new_trial=lord.checked_json(redo.post(
        "/api/adventure/boss/start",json={"zone_key":ZONE2}))
    assert new_trial["attempt_mode"]=="replay" and new_trial["replay"] is True
    for qid in new_trial["question_ids"]:
        q=BY_ID[qid]
        r=lord.checked_json(redo.post("/api/srs/review",json={
            "question_id":qid,"grade":5,
            "source_context":f"boss_trial:{new_trial['attempt_id']}",
            "boss_answer":{"moves":[dict(q["accepted_moves"][0])]},
        }))
        assert r["ok"]
    replay_finish=lord.checked_json(redo.post(
        "/api/adventure/boss/finish",json={"correct":0,"total":0}))
    assert replay_finish["passed"] is True
    assert replay_finish["reward"]["first_clear"] is False
    assert replay_finish["reward"]["replay"] is True
    with app.get_db() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM adventure_zone_unlocks "
            "WHERE user_id=? AND zone_key=?",(lord.UID,ZONE3)
        ).fetchone()["n"]==1
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM adventure_zone_star_earnings "
            "WHERE user_id=? AND zone_key=? AND star_number=1",
            (lord.UID,ZONE2)
        ).fetchone()["n"]==1
    assert next(z for z in lord.checked_json(login(app).get(
        "/api/adventure/bootstrap"))["zones"] if z["key"]==ZONE3)["unlocked"]

@pytest.mark.parametrize("input_mode", ["desktop_mouse", "chrome_tablet_touch"])
def test_zone2_lord_full_twenty_real_index_wgo_and_new_session(
    g010_player, monkeypatch, input_mode
):
    """Actual original web UI and WGo, no API-only boss click simulation."""
    import json
    import os
    import subprocess
    import threading
    from pathlib import Path
    from werkzeug.serving import make_server
    from migrations.companion_operations_v1 import upgrade as upgrade_companion
    from migrations.spirit_evolution_events_v1 import upgrade as upgrade_evolution

    app,c=g010_player
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE","global")
    with app.get_db() as conn:
        assert upgrade_companion(conn)["missing"] == []
        assert upgrade_evolution(conn)["missing"] == []

    lord.seed_lord_eligibility(c)
    first=lord.checked_json(c.post(
        "/api/adventure/boss/start",json={"zone_key":lord.ZONE}))
    for qid in first["question_ids"]:
        q=lord.QUESTION_BY_ID[qid]
        a=lord.checked_json(c.post("/api/srs/review",json={
            "question_id":qid,"grade":5,
            "source_context":f"boss_trial:{first['attempt_id']}",
            "boss_answer":{"moves":[dict(q["accepted_moves"][0])]},
        }))
        assert a["ok"]
    assert lord.checked_json(c.post(
        "/api/adventure/boss/finish",json={"correct":0,"total":0}))["passed"]

    auth=login(app)
    assert next(z for z in lord.checked_json(auth.get(
        "/api/adventure/bootstrap"))["zones"] if z["key"]==ZONE2)["unlocked"]
    # 26 zone questions; eight distinct correct Map Battle answers satisfy
    # the unchanged 30% Boss ready gate (ceil(26*0.3) == 8).
    for q in ZONE2_POOL[:8]:
        answer,_=judge(auth,q)
        assert answer.status_code==200,(q["id"],answer.status_code,answer.get_json())
        assert answer.get_json()["result"]=="CORRECT"

    state=lord.checked_json(auth.get("/api/adventure/bootstrap"))
    second=next(z for z in state["zones"] if z["key"]==ZONE2)
    assert second["boss_ready"],second
    cookie=auth.get_cookie("session")
    assert cookie and cookie.value
    server=make_server("127.0.0.1",0,app.app.wsgi_app,threaded=True)
    worker=threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    try:
        runner=Path(__file__).parent/"e2e"/"run_20261020_g010_zone2_lord_20_wgo_browser.mjs"
        browser=subprocess.run(
            ["node",str(runner)],
            input=json.dumps({"origin":f"http://127.0.0.1:{server.server_port}",
                              "sessionCookie":cookie.value}),
            capture_output=True,text=True,encoding="utf-8",timeout=190,
            cwd=Path(__file__).resolve().parent.parent,
            env={**os.environ,"GO_P1_LORD_TOUCH":
                 "1" if input_mode=="chrome_tablet_touch" else "0"},
        )
        assert browser.returncode==0,browser.stderr[-3500:]+browser.stdout[-2000:]
        result=json.loads(browser.stdout)
        assert result["verdict"]=="REAL_ZONE2_LORD_20_WGO_FIRST_CLEAR_PASS"
        assert result["answered"]==20
        assert result["actualIndex"] and result["actualWGoClicks"]
        assert not result["usedMockRoutes"] and not result["realIpad"]
    finally:
        server.shutdown()
        worker.join(timeout=10)
        server.server_close()

    fresh=login(app)
    after=lord.checked_json(fresh.get("/api/adventure/bootstrap"))
    zones={z["key"]:z for z in after["zones"]}
    assert zones[ZONE2]["cleared"] and zones[ZONE3]["unlocked"]
    with app.get_db() as conn:
        rows=conn.execute(
            "SELECT COUNT(*) AS n FROM review_log WHERE user_id=? "
            "AND source_context LIKE ? "
            "AND question_id>=972000 AND question_id<972026",
            (lord.UID, "lord_trial:v1:%")
        ).fetchone()["n"]
        assert rows==20
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM adventure_zone_star_earnings "
            "WHERE user_id=? AND zone_key=? AND star_number=1",
            (lord.UID,ZONE2),
        ).fetchone()["n"]==1
