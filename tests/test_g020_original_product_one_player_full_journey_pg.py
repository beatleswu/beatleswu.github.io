"""G020 REAL unmodified Product pages full single-player 1-session bridge.
All original G010 M5 progression + G019 NEW server-gated /shop /inventory,
curriculum, guild/quest-board, tavern, hero readbacks, never HTML substitution.


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
import pytest

from werkzeug.serving import make_server
from test_20261019_monthly_postgres import local_postgres, runtime as native_runtime
from test_20261020_g010_m2_reward_closed_loop_native_pg import (
    m2_player, good, quantities,
)
from test_20261020_g010_m1_zone2_monster_lord_native_pg import (
    g010_player, judge, login, ZONE2, ZONE3, ZONE2_POOL, BY_ID,
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


@pytest.mark.parametrize("mode",["desktop_mouse","chrome_tablet_touch"])
def test_g020_same_synthetic_player_full_original_product_vertical_slice(
    m2_player,monkeypatch,mode,tmp_path
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
    monkeypatch.setenv(app.G019_APPROVED_EQUIPMENT_SHOP_UI_FLAG,"1")
    catalog=good(user,"/api/shop/catalog")
    assert catalog["purchase_enabled"] and len(catalog["equipment_offers"])==9
    assert catalog["approved_equipment_purchase_ui_enabled"] is True
    assert good(user,"/api/auth/me")["g019_equipment_actions_ui_enabled"] is True

    offer=next(x for x in catalog["equipment_offers"]
               if x["item_id"]=="wooden_sword")
    assert offer["price"]==300
    session=login(app).get_cookie("session")
    relogin=login(app).get_cookie("session")
    assert session and relogin
    host=make_server("127.0.0.1",0,
                     app.app.wsgi_app,threaded=True)
    worker=threading.Thread(target=host.serve_forever,daemon=True)
    worker.start()
    try:
        origin=f"http://127.0.0.1:{host.server_port}"
        first_real=_chrome(
            app,"g020_original_tavern_quest_ranking_browser.mjs",
            {"origin":origin,"sessionCookie":session.value,
             "reloginCookie":relogin.value,
             "questId":"daily:streak_correct","beforeXp":before_xp,
             "afterXp":before_xp+20,"coinsAfter":1015},
            "G010_M4_REAL_CHROME_QUEST_RANKING_RELOGIN_PASS",
            ("GO_G010_M4_TOUCH","1" if mode=="chrome_tablet_touch" else "0"))
        assert first_real["writes"]==["POST /api/quests/v2/claim"]
        second_real=_chrome(
            app,"g019_shipped_shop_backpack_purchase_equip_relogin.mjs",
            {"origin":origin,"sessionCookie":session.value,
             "reloginCookie":relogin.value,
             "offerId":offer["offer_id"],"itemId":"wooden_sword",
             "price":300,"startingCoins":1015},
            "G019_SHIPPED_SHOP_BACKPACK_REAL_PG_EQUIP_RELOGIN_PASS",
            ("GO_G010_M3_TOUCH","1" if mode=="chrome_tablet_touch" else "0"))
        assert second_real["coinsAfter"]==715
        assert second_real["writes"]==[
            "POST /api/shop/buy",
            "POST /api/player/inventory/equip",
        ]
        assert second_real["renderedPageIsTestOnlyActivatedVariant"] is False
        integrated=_chrome(
            app,"g020_original_player_pages_readback_browser.mjs",
            {"origin":origin,"sessionCookie":session.value,
             "reloginCookie":relogin.value,
             "expectedXp":before_xp+20,"expectedCoins":715,
             "expectedEquipment":"wooden_sword"},
            "G020_FULL_ORIGINAL_PRODUCT_PLAYER_SAME_SESSION_READBACK_PASS",
            ("GO_G020_TOUCH","1" if mode=="chrome_tablet_touch" else "0"))
        assert integrated["writes"]==[] and integrated["errors"]==[]

    finally:
        host.shutdown()
        worker.join(timeout=9)
        host.server_close()

    after_shop=login(app)
    # Preserve the previous M5 proof of the known already-earned potion: it
    # is NOT a Shop-purchased item and must stay an explicit authenticated
    # consumable use. G019 original UI release never opens non-equipment sale.
    used=after_shop.post("/api/shop/use",json={"item_key":"xp_potion"})
    assert used.status_code==200,used.get_json()
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
    monkeypatch.delenv(app.G019_APPROVED_EQUIPMENT_SHOP_UI_FLAG,raising=False)
    assert app._canonical_coin_shop_purchase_enabled() is False
    assert app._equipment_canonical_loadout_enabled() is False
    assert good(login(app),"/api/shop/catalog")["purchase_enabled"] is False
    assert good(login(app),"/api/shop/catalog")[
       "approved_equipment_purchase_ui_enabled"] is False
    # Persistent final synthetic DB and exact shared identity, no fake APIs.
    with app.get_db() as db:
        final_coins=db.execute("SELECT coins FROM user_stats WHERE user_id=?",
            (lord.UID,)).fetchone()["coins"]
        final_xp=good(login(app),"/api/xp/status")["xp"]
        wallet_debits=db.execute("SELECT COUNT(*) AS n FROM currency_log "
          "WHERE user_id=? AND delta<0",(lord.UID,)).fetchone()["n"]
    receipt={"schema":"G020_ONE_REAL_NATIVE_PG_PLAYER_CROSS_FEATURE_E2E_V1",
      "verdict":"G020_ORIGINAL_PAGES_FULL_PLAYER_VERTICAL_SLICE_PASS",
      "real_pg_disposable":True,"player_uid":lord.UID,
      "g019_original_public_HTML":True,"no_html_substitution":True,
      "zone1_lord_real_answers":20,"zone2_monster_quest_questions":20,
      "quest_claim_writes":1,"g019_real_shop_purchase_writes":1,
      "g019_real_backpack_equip_writes":1,
      "g019_cosmetic_shop_opened":False,
      "existing_owned_consumable_use":1,
      "zone2_lord_real_answers":20,"zone3_unlocked":True,
      "tavern_leaderboard_persistent":True,
      "curriculum_quest_board_hero_readback":True,
      "quest_browser":first_real,"shop_browser":second_real,
      "original_pages_browser":integrated,
      "final_coins":final_coins,"final_xp":final_xp,
      "wallet_debit_rows":wallet_debits,
      "source_product_release_p022_p038":False,
      "github_master_merged":False,"oracle_deployed":False,
      "real_player_writes":False}
    assert wallet_debits==1
    evidence_root=Path(os.environ.get("GO_E2E_EVIDENCE_ROOT") or tmp_path)
    if "GO_E2E_EVIDENCE_ROOT" in os.environ:
        assert evidence_root.is_absolute() and evidence_root.drive.upper()=="D:", "Evidence must use isolated D: root"
        assert "go-odyssey-g010-3d-activation-evidence-20261021" not in str(evidence_root).lower(), "Refuse historical evidence overwrite"
    evidence_root.mkdir(parents=True,exist_ok=True)
    dest=evidence_root/("G020_ORIGINAL_PRODUCT_FULL_PLAYER_20261024.json"
                      if mode=="desktop_mouse" else
                      "G020_ORIGINAL_PRODUCT_FULL_PLAYER_TOUCH_20261024.json")
    with dest.open("x",encoding="utf8") as output:
        output.write(json.dumps(receipt,ensure_ascii=False,indent=2))
    print("G020_FULL_ONE_USER_ACTUAL_PRODUCT_PASS",dest,flush=True)
