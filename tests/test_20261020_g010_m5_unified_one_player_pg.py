"""G010 M5 unified single-player acceptance: all four milestones, one identity.

A disposable Native PostgreSQL player completes actual Zone1 Lord, Zone2
server-judged answers/Monster, REAL Chrome Quest claim and leaderboard refresh,
REAL Chrome Shop purchase and Backpack equip/use, and Zone2 Lord with
persistent first-star/Zone3 unlock. No Production/Oracle or mock API writes.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import threading

from werkzeug.serving import make_server
from test_20261019_monthly_postgres import local_postgres, runtime as native_runtime
from test_20261020_g010_m2_reward_closed_loop_native_pg import (
    m2_player, good, quantities,
)
from test_20261020_g010_m1_zone2_monster_lord_native_pg import (
    g010_player, judge, login, ZONE2, ZONE3, ZONE2_POOL, BY_ID,
)
from test_20261020_g010_m3_shop_player_native_pg import (
    _activate_preview_only_in_memory,
)
import test_20261019_lord_full_journey_native_pg as lord
from test_20261019_lord_full_journey_native_pg import lord_player
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from migrations.quest_progress_v2 import upgrade as upgrade_progress
from migrations.quest_claim_v1 import upgrade as upgrade_claim
from migrations.login_journey_v1 import upgrade as upgrade_login
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_coin
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_slot
from migrations.item_use_operations_v1 import upgrade as upgrade_item_use
from migrations.companion_operations_v1 import upgrade as upgrade_companion
from migrations.spirit_evolution_events_v1 import upgrade as upgrade_evolution


def _chrome(root,runner,source,target,env):
    result=subprocess.run(
        ["node",str(Path(__file__).parent/"e2e"/runner)],
        input=json.dumps(source),capture_output=True,text=True,
        encoding="utf-8",errors="replace",timeout=155,
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ,env[0]:env[1]})
    assert result.returncode==0, (
        runner+"\n"+result.stderr[-4200:]+"\n"+result.stdout[-900:])
    response=json.loads(result.stdout)
    assert response["verdict"]==target,(runner,response)
    return response


def test_g010_m5_same_disposable_player_all_milestones_and_live_ui(
    m2_player,monkeypatch
):
    app,initial=m2_player
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE","global")
    assert initial.get("/api/quests/v2").status_code==404
    assert app._canonical_coin_shop_purchase_enabled() is False
    assert app._equipment_canonical_loadout_enabled() is False

    with app.get_db() as conn:
        upgrade_outbox(conn)
        assert upgrade_progress(conn)["valid"]
        assert upgrade_claim(conn)["valid"]
        assert upgrade_login(conn)["valid"]
        upgrade_coin(conn)
        upgrade_slot(conn,equipment_defs=app.EQUIPMENT_DEFS)
        assert upgrade_item_use(conn)["table"]=="item_use_operations"
        assert upgrade_companion(conn)["missing"]==[]
        assert upgrade_evolution(conn)["missing"]==[]
        conn.execute("UPDATE user_stats SET coins=? WHERE user_id=?",
                     (1000,lord.UID))
        # Synthetic previously-earned item: RETIRED old potion Shop sale
        # remains disabled; this is a grant fixture, not purchase proof.
        conn.execute("INSERT INTO shop_inventory(user_id,item_key,qty) "
                     "VALUES(?,?,?)",(lord.UID,"xp_potion",1))

    monkeypatch.setenv("QUEST_V2_RUNTIME_ENABLED","true")
    lord.seed_lord_eligibility(initial)
    start=lord.checked_json(initial.post(
        "/api/adventure/boss/start",json={"zone_key":lord.ZONE}))
    assert len(start["question_ids"])==20
    for qid in start["question_ids"]:
        q=lord.QUESTION_BY_ID[qid]
        r=lord.checked_json(initial.post("/api/srs/review",json={
            "question_id":qid,"grade":5,
            "source_context":f"boss_trial:{start['attempt_id']}",
            "boss_answer":{"moves":[dict(q["accepted_moves"][0])]},
        }))
        assert r["ok"]
    cleared=lord.checked_json(initial.post(
        "/api/adventure/boss/finish",json={"correct":0,"total":0}))
    assert cleared["passed"] and cleared["reward"]["first_clear"]
    assert next(z for z in good(initial,"/api/adventure/bootstrap")["zones"]
                if z["key"]==ZONE2)["unlocked"]

    user=login(app)
    defeated=0
    for q in ZONE2_POOL[:20]:
        response,_=judge(user,q)
        assert response.status_code==200,(q["id"],response.status_code,response.get_json())
        item=response.get_json()
        assert item["accepted"] and item["result"]=="CORRECT"
        defeated+=int(bool(item.get("monster_defeated")))
    assert defeated==1
    quest=next(x for x in good(user,"/api/quests/v2")["quests"]
               if x["quest_id"]=="daily:streak_correct")
    assert quest["claimable"] and not quest["claimed"]
    before_xp=good(user,"/api/xp/status")["xp"]
    assert good(user,"/api/shop/catalog")["coins"]==1000

    monkeypatch.setenv(app.CANONICAL_COIN_SHOP_PURCHASE_FLAG,"1")
    monkeypatch.setenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,"1")
    catalog=good(user,"/api/shop/catalog")
    assert catalog["purchase_enabled"] and len(catalog["equipment_offers"])==9
    offer=next(x for x in catalog["equipment_offers"]
               if x["item_id"]=="wooden_sword")
    assert offer["price"]==300
    session=login(app).get_cookie("session")
    relogin=login(app).get_cookie("session")
    assert session and relogin
    host=make_server("127.0.0.1",0,
                     _activate_preview_only_in_memory(app.app.wsgi_app),threaded=True)
    worker=threading.Thread(target=host.serve_forever,daemon=True)
    worker.start()
    try:
        origin=f"http://127.0.0.1:{host.server_port}"
        first_real=_chrome(
            app,"run_20261020_g010_m4_quest_rank_real_browser.mjs",
            {"origin":origin,"sessionCookie":session.value,
             "reloginCookie":relogin.value,
             "questId":"daily:streak_correct","beforeXp":before_xp,
             "afterXp":before_xp+20,"coinsAfter":1015},
            "G010_M4_REAL_CHROME_QUEST_RANKING_RELOGIN_PASS",
            ("GO_G010_M4_TOUCH","0"))
        assert first_real["writes"]==["POST /api/quests/v2/claim"]
        second_real=_chrome(
            app,"run_20261020_g010_m3_shop_purchase_equip_real_browser.mjs",
            {"origin":origin,"sessionCookie":session.value,
             "reloginCookie":relogin.value,
             "offerId":offer["offer_id"],"itemId":"wooden_sword",
             "price":300,"startingCoins":1015},
            "G010_M3_REAL_BROWSER_PURCHASE_EQUIP_RELOGIN_PASS",
            ("GO_G010_M3_TOUCH","0"))
        assert second_real["coinsAfter"]==715
        assert second_real["writes"]==[
            "POST /api/shop/buy",
            "POST /api/player/inventory/equip",
            "POST /api/shop/use",
        ]
    finally:
        host.shutdown()
        worker.join(timeout=9)
        host.server_close()

    after_shop=login(app)
    assert good(after_shop,"/api/shop/catalog")["coins"]==715
    assert good(after_shop,"/api/xp/status")["xp"]==before_xp+20
    with app.get_db() as conn:
        assert quantities(conn,lord.UID)>=1

    boss=lord.checked_json(after_shop.post(
        "/api/adventure/boss/start",json={"zone_key":ZONE2}))
    assert len(boss["question_ids"])==20
    assert set(boss["question_ids"])<=set(BY_ID)
    for qid in boss["question_ids"]:
        q=BY_ID[qid]
        review=lord.checked_json(after_shop.post("/api/srs/review",json={
            "question_id":qid,"grade":5,
            "source_context":f"boss_trial:{boss['attempt_id']}",
            "boss_answer":{"moves":[dict(q["accepted_moves"][0])]},
        }))
        assert review["ok"]
    boss_done=lord.checked_json(after_shop.post(
        "/api/adventure/boss/finish",json={"correct":0,"total":0}))
    assert boss_done["passed"] and boss_done["reward"]["first_clear"]
    final=login(app)
    zones={z["key"]:z for z in good(final,"/api/adventure/bootstrap")["zones"]}
    assert zones[ZONE2]["cleared"] and zones[ZONE2]["zone_authority_stars"]>=1
    assert zones[ZONE3]["unlocked"]
    standings=good(final,"/api/community/leaderboard")
    me=next(r for r in standings["alltime"] if r["is_you"])
    assert me["score"]==good(final,"/api/xp/status")["xp"]
    with app.get_db() as conn:
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=?",
                            (lord.UID,)).fetchone()["coins"]==715
        assert quantities(conn,lord.UID)>=1
        assert conn.execute("SELECT COUNT(*) AS n FROM quest_claims_v2 "
                            "WHERE user_id=?",(str(lord.UID),)).fetchone()["n"]==1
        assert conn.execute("SELECT COUNT(*) AS n FROM coin_purchase_operations "
                            "WHERE user_id=?",(lord.UID,)).fetchone()["n"]==1
        gear=conn.execute("SELECT equip_id,equipped FROM player_inventory "
                          "WHERE user_id=?",(lord.UID,)).fetchall()
        # First-clear rewards may legitimately grant extra equipment.
        # M5 must distinguish one shop acquisition from other owned items.
        bought=[row for row in gear if row["equip_id"]=="wooden_sword"]
        assert len(bought)==1 and bought[0]["equipped"]==1
        assert len({row["equip_id"] for row in gear})==len(gear)
        assert {row["equip_id"] for row in gear}>={"bamboo_shadow_blade",
                                                   "jade_river_bead",
                                                   "wooden_sword"}
        assert conn.execute("SELECT qty FROM shop_inventory WHERE user_id=? "
                            "AND item_key='xp_potion'",(lord.UID,)).fetchone()["qty"]==0
        assert conn.execute("SELECT COUNT(*) AS n FROM item_use_operations "
                            "WHERE player_id=?",(str(lord.UID),)).fetchone()["n"]==1
        assert conn.execute("SELECT COUNT(*) AS n FROM domain_event_outbox "
                            "WHERE player_id=? AND event_type='MONSTER_DEFEATED'",
                            (str(lord.UID),)).fetchone()["n"]==1
        assert conn.execute("SELECT COUNT(*) AS n FROM adventure_zone_star_earnings "
                            "WHERE user_id=? AND zone_key=? AND star_number=1",
                            (lord.UID,ZONE2)).fetchone()["n"]==1
        assert conn.execute("SELECT COUNT(*) AS n FROM adventure_zone_unlocks "
                            "WHERE user_id=? AND zone_key=?",
                            (lord.UID,ZONE3)).fetchone()["n"]==1
    monkeypatch.delenv(app.CANONICAL_COIN_SHOP_PURCHASE_FLAG,raising=False)
    monkeypatch.delenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,raising=False)
    assert app._canonical_coin_shop_purchase_enabled() is False
    assert app._equipment_canonical_loadout_enabled() is False
    assert good(login(app),"/api/shop/catalog")["purchase_enabled"] is False
