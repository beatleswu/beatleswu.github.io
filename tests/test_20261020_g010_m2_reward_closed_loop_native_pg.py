"""G010 M2: authoritative rewards persisted and visible across shipped UI.

Uses synthetic Zone1/Zone2 corpus and disposable native PG.  No production
player/price/drop/feature flag or deployment mutation.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import threading

import pytest
from werkzeug.serving import make_server
import test_20261019_lord_full_journey_native_pg as lord
from test_20261019_lord_full_journey_native_pg import lord_player
from test_20261019_monthly_postgres import local_postgres, runtime as native_runtime
from test_20261020_g010_m1_zone2_monster_lord_native_pg import (
    g010_player, login, judge, ZONE2, ZONE3, ZONE2_POOL, BY_ID,
)
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from migrations.quest_progress_v2 import upgrade as upgrade_progress
from migrations.quest_claim_v1 import upgrade as upgrade_claim
from migrations.login_journey_v1 import upgrade as upgrade_login
from migrations.companion_operations_v1 import upgrade as upgrade_companion
from migrations.spirit_evolution_events_v1 import upgrade as upgrade_evolution


@pytest.fixture
def m2_player(monkeypatch, request):
    """Admit exactly one synthetic Zone3 playable target for Map UI tests.

    G010 M1 fixtures populate only Zone1+Zone2, intentionally.  The shipped
    /api/adventure/bootstrap map fail-closes unlocked zones with no questions.
    Supply one properly typed Zone3 Puzzle before the disposable identity
    bootstrap so reward/unlock presentation can be truthfully verified.
    """
    zone3_question = deepcopy(ZONE2_POOL[0])
    zone3_question.update({
        "id":973010,
        "rank":"20k","difficulty":"20k",
        "topic":"5哥布林洞穴",
        "stage":"LV3","level":"LV3",
        "source":"disposable-g010-m2-zone3/q973010.sgf",
        "display_name":"G010 M2 first unlocked Zone3 real playable target",
        "content":ZONE2_POOL[0]["content"].replace(
            "G010 unique Zone2 q01",
            "G010 M2 unique Zone3 playable q973010"),
    })
    monkeypatch.setattr(lord, "CORPUS", lord.CORPUS + [zone3_question])
    return request.getfixturevalue("g010_player")


def good(client, path):
    reply = client.get(path)
    assert reply.status_code == 200, (path, reply.status_code, reply.get_json())
    return reply.get_json()


def quantities(conn, uid):
    row = conn.execute(
        "SELECT qty FROM pet_inventory WHERE user_id=? "
        "AND item_key='go_spirit_candy'", (uid,),
    ).fetchone()
    return int(row["qty"]) if row else 0


@pytest.mark.parametrize("mode", ["desktop_mouse", "chrome_tablet_touch"])
def test_m2_reward_all_authorities_new_session_and_real_player_surfaces(
    m2_player, monkeypatch, mode
):
    app, old = m2_player
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "global")
    assert old.get("/api/quests/v2").status_code == 404
    with app.get_db() as conn:
        assert upgrade_outbox(conn)["table"] == "domain_event_outbox"
        assert upgrade_progress(conn)["valid"]
        assert upgrade_claim(conn)["valid"]
        assert upgrade_login(conn)["valid"]
        assert upgrade_companion(conn)["missing"] == []
        assert upgrade_evolution(conn)["missing"] == []
    monkeypatch.setenv("QUEST_V2_RUNTIME_ENABLED", "true")

    lord.seed_lord_eligibility(old)
    first = lord.checked_json(old.post(
        "/api/adventure/boss/start", json={"zone_key": lord.ZONE}))
    assert len(first["question_ids"]) == 20
    for qid in first["question_ids"]:
        question = lord.QUESTION_BY_ID[qid]
        review = lord.checked_json(old.post("/api/srs/review", json={
            "question_id": qid, "grade": 5,
            "source_context": f"boss_trial:{first['attempt_id']}",
            "boss_answer": {"moves":[dict(question["accepted_moves"][0])]},
        }))
        assert review["ok"]
    z1finish = lord.checked_json(old.post("/api/adventure/boss/finish",
                                         json={"correct": 0, "total": 0}))
    assert z1finish["passed"] and z1finish["reward"]["first_clear"]

    player = login(app)
    initial = good(player, "/api/adventure/bootstrap")
    assert next(z for z in initial["zones"] if z["key"] == ZONE2)["unlocked"]
    assert not next(z for z in initial["zones"] if z["key"] == ZONE3)["unlocked"]

    with app.get_db() as conn:
        before_coins = int(conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=?", (lord.UID,),
        ).fetchone()["coins"])
        before_candy = quantities(conn, lord.UID)

    monster_defeats=[]
    for q in ZONE2_POOL[:20]:
        response, issued = judge(player, q)
        data = response.get_json()
        assert response.status_code == 200, (q["id"], response.status_code, data)
        assert data["accepted"] and data["result"] == "CORRECT" and not data["duplicate"]
        if data.get("monster_defeated"):
            assert data["monster_hp_before"] > 0
            assert data["monster_hp_after"] == 0
            monster_defeats.append(data)
    assert len(monster_defeats) == 1,monster_defeats

    with app.get_db() as conn:
        # The entire battle yielded no as-yet-unapproved monster drops/coins.
        after_combat_coins = int(conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=?", (lord.UID,),
        ).fetchone()["coins"])
        assert after_combat_coins == before_coins
        assert quantities(conn, lord.UID) == before_candy
        kills = conn.execute(
            "SELECT payload FROM domain_event_outbox "
            "WHERE player_id=? AND event_type='MONSTER_DEFEATED'",
            (str(lord.UID),),
        ).fetchall()
        assert len(kills) == 1
        assert kills[0]["payload"]["coins_granted"] == 0
        assert kills[0]["payload"]["functional_drop_id"] is None
        quest = conn.execute(
            "SELECT progress, completed, period_key FROM quest_progress_v2 "
            "WHERE user_id=? AND quest_id='daily:streak_correct'",
            (str(lord.UID),),
        ).fetchone()
        assert quest and quest["completed"] and quest["progress"]>=3
        period_key = quest["period_key"]

    xp_before = good(player, "/api/xp/status")["xp"]
    # Client must not smuggle XP, Coins or an owned item as 'reward'.
    forged = player.post("/api/quests/v2/claim", json={
        "quest_id": "daily:streak_correct",
        "period_key": period_key,
        "claim_operation_id": "g010-m2-forged",
        "coins": 999999, "xp": 999999,
    })
    assert forged.status_code == 400
    assert forged.get_json()["error"] == "client_authority_field_rejected"
    claim = {
        "quest_id":"daily:streak_correct",
        "period_key":period_key,
        "claim_operation_id":"g010-m2-real-reward-once",
    }
    claimer = login(app)
    earned=claimer.post("/api/quests/v2/claim", json=claim)
    assert earned.status_code == 200,earned.get_json()
    assert earned.get_json()["ok"] and not earned.get_json()["duplicate"]
    xp_after_claim = good(claimer, "/api/xp/status")["xp"]
    assert xp_after_claim - xp_before == 20

    # A response-loss replay and a second logical ID cannot mint more reward.
    again=claimer.post("/api/quests/v2/claim",json=claim)
    assert again.status_code == 200 and again.get_json()["duplicate"] is True
    alt=claimer.post("/api/quests/v2/claim",json={
        **claim, "claim_operation_id":"g010-m2-independent-retry"
    })
    assert alt.status_code == 200 and alt.get_json()["duplicate"] is True
    assert good(claimer, "/api/xp/status")["xp"] == xp_after_claim

    with app.get_db() as conn:
        after_claim_coins=int(conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=?", (lord.UID,),
        ).fetchone()["coins"])
        after_claim_candy=quantities(conn,lord.UID)
        assert after_claim_coins-before_coins == 15
        assert after_claim_candy-before_candy == 1
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM quest_claims_v2 WHERE user_id=? "
            "AND quest_id='daily:streak_correct'",
            (str(lord.UID),),
        ).fetchone()["n"]==1

    # Zone2 Lord full real server-evidence trial and next-zone first star.
    ready=good(claimer,"/api/adventure/bootstrap")
    assert next(z for z in ready["zones"] if z["key"]==ZONE2)["boss_ready"]
    trial=lord.checked_json(claimer.post("/api/adventure/boss/start",
                                        json={"zone_key":ZONE2}))
    assert len(trial["question_ids"]) == 20
    for qid in trial["question_ids"]:
        question=BY_ID[qid]
        review=lord.checked_json(claimer.post("/api/srs/review",json={
            "question_id":qid,"grade":5,
            "source_context":f"boss_trial:{trial['attempt_id']}",
            "boss_answer":{"moves":[dict(question["accepted_moves"][0])]},
        }))
        assert review["ok"]
    finish=lord.checked_json(claimer.post(
        "/api/adventure/boss/finish",json={"correct":0,"total":0}))
    assert finish["passed"]
    assert finish["reward"]["first_clear"]
    assert finish["first_clear_projection"]["status"]=="COMPLETED"

    # API projection coherence across newly authenticated sessions.
    relogged = login(app)
    xp = good(relogged, "/api/xp/status")
    profile = good(relogged, "/api/skills/profile")
    hero = good(relogged, "/api/player/presentation")
    shop = good(relogged, "/api/shop/catalog")
    pet = good(relogged, "/api/pet/status")
    wardrobe = good(relogged, "/api/player/wardrobe")
    assert wardrobe["total"] >= 1
    assert any(item.get("id") == "back_pack"
               for items in wardrobe["by_slot"].values() for item in items)
    zones = good(relogged, "/api/adventure/bootstrap")
    src = {z["key"]: z for z in zones["zones"]}
    assert hero["progression"]["xp"] == xp["xp"] == profile["total_xp"]
    assert hero["progression"]["rank_xp"] == xp["rank_xp"] == profile["lv_xp"]
    assert hero["progression"]["level"] == xp["lv"] == profile["level"]
    assert shop["coins"] == after_claim_coins
    assert shop["purchase_enabled"] is False
    assert next(item for item in pet["inventory"]
                if item["key"]=="go_spirit_candy")["qty"]==after_claim_candy
    assert src[ZONE2]["cleared"] and src[ZONE2]["zone_authority_stars"]>=1
    assert src[ZONE3]["unlocked"]

    with app.get_db() as conn:
        stars=conn.execute(
            "SELECT COUNT(*) AS n FROM adventure_zone_star_earnings "
            "WHERE user_id=? AND zone_key=? AND star_number=1",
            (lord.UID, ZONE2),
        ).fetchone()["n"]
        unlock=conn.execute(
            "SELECT COUNT(*) AS n FROM adventure_zone_unlocks "
            "WHERE user_id=? AND zone_key=?", (lord.UID, ZONE3),
        ).fetchone()["n"]
        assert stars==unlock==1
        count_before=conn.execute(
            "SELECT COUNT(*) AS n FROM player_wardrobe WHERE user_id=?",
            (lord.UID,),
        ).fetchone()["n"]
    # A new-session read alone must have no mutating side effects.
    last=login(app)
    assert good(last,"/api/shop/catalog")["coins"]==after_claim_coins
    with app.get_db() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM player_wardrobe WHERE user_id=?",
            (lord.UID,),
        ).fetchone()["n"]==count_before

    cookie = last.get_cookie("session")
    assert cookie and cookie.value
    srv=make_server("127.0.0.1",0,app.app.wsgi_app,threaded=True)
    worker=threading.Thread(target=srv.serve_forever,daemon=True)
    worker.start()
    try:
        script=(Path(__file__).parent/"e2e"/
                "run_20261020_g010_m2_reward_readback_browser.mjs")
        result=subprocess.run(
            ["node",str(script)],
            input=json.dumps({
                "origin":f"http://127.0.0.1:{srv.server_port}",
                "sessionCookie":cookie.value,
                "coins":after_claim_coins,
                "totalXp":hero["progression"]["xp"],
                "rankXp":hero["progression"]["rank_xp"],
                "candyQty":after_claim_candy,
                "zone2":ZONE2,"zone3":ZONE3,
            }),capture_output=True,text=True,encoding="utf-8",
            timeout=115,cwd=Path(__file__).resolve().parent.parent,
            env={**os.environ,"GO_G010_M2_TOUCH":
                 "1" if mode=="chrome_tablet_touch" else "0"},
        )
        assert result.returncode==0,result.stderr[-3000:]+result.stdout[-900:]
        report=json.loads(result.stdout)
        assert report["verdict"]=="G010_M2_REAL_PLAYER_REWARD_SURFACES_PASS"
        assert report["production"] is False and report["mockApis"] is False
        assert report["writes"]==[]
    finally:
        srv.shutdown()
        worker.join(timeout=10)
        srv.server_close()
    # All real pages were pure read-only. Recheck durable economy afterward.
    with app.get_db() as conn:
        assert conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=?",(lord.UID,)
        ).fetchone()["coins"]==after_claim_coins
        assert quantities(conn,lord.UID)==after_claim_candy
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM quest_claims_v2 WHERE user_id=? "
            "AND quest_id='daily:streak_correct'",(str(lord.UID),)
        ).fetchone()["n"]==1
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM domain_event_outbox WHERE player_id=? "
            "AND event_type='MONSTER_DEFEATED'",(str(lord.UID),)
        ).fetchone()["n"]==1
