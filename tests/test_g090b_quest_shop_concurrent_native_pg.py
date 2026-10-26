"""G090 P0-B: Cross-SOURCE transaction race, audit and retry.
Disposable PostgreSQL and actual Flask endpoints ONLY. No product edits.
G089/G090A existing tests are imported as fixtures, not re-executed.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import json
import pytest

from test_g090_quest_outbox_replay_native_pg import (
    zone2_player, lord_player, local_postgres, native_runtime,
    _client, _ok, _snapshot, ZONE2, ZONE2_QUESTION,
    ZONE2_EXTRA_QUESTIONS, HEADERS, lord, UID, QUEST,
    upgrade_outbox, upgrade_progress, upgrade_claim, upgrade_login,
)
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_coin
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_slot

SKU="wooden_sword"
SHOP_OPERATION="g090b-cross-source-shop-001"
QUEST_OPERATION="g090b-cross-source-quest-001"


def _additional(app):
    with app.get_db() as conn:
        ledger=[dict(row) for row in conn.execute(
            "SELECT id,delta,balance_after,reason FROM currency_log "
            "WHERE user_id=? ORDER BY id",(UID,)).fetchall()]
        purchases=[dict(row) for row in conn.execute(
            "SELECT purchase_operation_id,offer_id,resolved_price,operation_status,lineage_event_id "
            "FROM coin_purchase_operations WHERE user_id=? ORDER BY purchase_operation_id",
            (UID,)).fetchall()]
        gear=[dict(row) for row in conn.execute(
            "SELECT equip_id,equipped,source FROM player_inventory WHERE user_id=? ORDER BY equip_id",
            (UID,)).fetchall()]
        claims=[dict(row) for row in conn.execute(
            "SELECT claim_id,quest_id,period_key,claim_operation_id,claim_status "
            "FROM quest_claims_v2 WHERE user_id=? ORDER BY claim_id",
            (str(UID),)).fetchall()]
        event_rows=[dict(row) for row in conn.execute(
            "SELECT event_id,event_type,player_id,lineage_id,source_event_id,"
            "idempotency_key,outcome,payload FROM domain_event_outbox "
            "WHERE player_id=? ORDER BY event_id",
            (str(UID),)).fetchall()]
    for ev in event_rows:
        if isinstance(ev["payload"],str):
            ev["payload"]=json.loads(ev["payload"])
    return dict(purchases=purchases,gear=gear,claims=claims,events=event_rows,ledger=ledger)


def _both(app):
    return {"base":_snapshot(app),"detail":_additional(app)}


def _assert_exact_new_lineage(before,after):
    old={ev["event_id"] for ev in before["detail"]["events"]}
    delta=[ev for ev in after["detail"]["events"] if ev["event_id"] not in old]
    assert len(delta)==2,delta
    assert all(ev["event_type"]=="ITEM_ACQUISITION" and ev["outcome"]=="SUCCESS" for ev in delta)
    assert all(ev["source_event_id"] for ev in delta),"lineage must have source event identity"
    keys=[(ev["player_id"],ev["event_type"],ev["idempotency_key"]) for ev in after["detail"]["events"]]
    assert len(keys)==len(set(keys))
    by_source={ev["payload"].get("source") or ev["payload"].get("acquisition_source"):ev for ev in delta}
    assert set(by_source)=={"SHOP","QUEST"},by_source
    shop=by_source["SHOP"]; quest=by_source["QUEST"]
    assert shop["source_event_id"]==f"purchase:{UID}:{SHOP_OPERATION}"
    assert shop["idempotency_key"]==f"coin-purchase-acquisition:{SHOP_OPERATION}"
    assert shop["payload"]["item_id"]==SKU
    assert int(shop["payload"]["quantity"])==1
    assert int(shop["payload"]["coins_spent"])==300
    assert int(shop["payload"]["resolved_price"])==300
    assert quest["idempotency_key"].startswith("quest-item-acquisition:")
    assert quest["payload"]["quest_id"]==QUEST
    assert quest["payload"]["item_id"]=="go_spirit_candy"
    assert int(quest["payload"]["quantity"])==1
    assert quest["payload"]["claim_id"]==after["detail"]["claims"][0]["claim_id"]
    assert quest["source_event_id"]==quest["payload"]["completion_source_event_id"]
    assert shop["event_id"]==after["detail"]["purchases"][0]["lineage_event_id"]
    return {"shop":shop,"quest":quest}


def test_two_different_reward_sources_race_and_emit_two_reconciled_events(zone2_player,monkeypatch,tmp_path):
    app,initial_player=zone2_player
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE","global")
    assert app._canonical_coin_shop_purchase_enabled() is False
    with app.get_db() as conn:
        upgrade_coin(conn)
        upgrade_outbox(conn)
        upgrade_slot(conn,equipment_defs=app.EQUIPMENT_DEFS)
        conn.execute("UPDATE user_stats SET coins=1000 WHERE user_id=?",(UID,))
    monkeypatch.setenv(app.CANONICAL_COIN_SHOP_PURCHASE_FLAG,"1")
    monkeypatch.setenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,"1")
    assert app._canonical_coin_shop_purchase_enabled() is True

    lord.seed_lord_eligibility(initial_player)
    trial=_ok(initial_player.post("/api/adventure/boss/start",json={"zone_key":lord.ZONE}))
    assert len(trial["question_ids"])==20
    for n,qid in enumerate(trial["question_ids"]):
        q=lord.QUESTION_BY_ID[qid]
        answer=_ok(initial_player.post("/api/srs/review",json={
            "question_id":qid,"grade":5,"response_ms":900+n,
            "source_context":f"boss_trial:{trial['attempt_id']}",
            "boss_answer":{"moves":[dict(q["accepted_moves"][0])]}
        }))
        assert answer["ok"]
    finished=_ok(initial_player.post("/api/adventure/boss/finish",json={"correct":0,"total":0}))
    assert finished["passed"] and finished["first_clear_projection"]["status"]=="COMPLETED"
    with app.get_db() as conn:
        for upgrade in (upgrade_progress,upgrade_claim,upgrade_login):
            assert upgrade(conn).get("valid",True) is True
    monkeypatch.setenv("QUEST_V2_RUNTIME_ENABLED","true")

    signed=_client(app)
    original_battle=None
    for q in [ZONE2_QUESTION,*ZONE2_EXTRA_QUESTIONS[:2]]:
        issued=_ok(signed.post("/api/adventure/map-battles/v1/attempts",
                              json={"zone_key":ZONE2,"question_id":q["id"]},headers=HEADERS))
        payload={
          "battle_id":issued["battle_id"],"attempt_id":issued["attempt_id"],
          "submission_nonce":issued["submission_nonce"],
          "battle_revision":issued["battle"]["battle_revision"],
          "question_revision":issued["question_revision"],
          "player_color":issued["player_color"],
          "transform_id":issued["transform_id"],
          "transform_version":issued["transform_version"],
          "moves":[dict(q["accepted_moves"][0])]
        }
        verdict=_ok(signed.post("/api/adventure/map-battles/v1/answers",
                                json=payload,headers=HEADERS))
        assert verdict["accepted"] and verdict["result"]=="CORRECT" and not verdict["duplicate"]
        original_battle=payload
    assert original_battle is not None
    before=_both(app)
    assert before["base"]["stats"]["coins"]==1000
    assert not before["detail"]["purchases"]
    assert not before["detail"]["claims"]
    completed=[r for r in before["base"]["quest_progress"] if r["quest_id"]==QUEST and r["completed"]]
    assert len(completed)==1
    period=completed[0]["period_key"]
    shop_offer=_ok(signed.get("/api/shop/catalog"))
    assert shop_offer["purchase_enabled"]
    assert any(x["item_id"]==SKU and x["price"]==300 for x in shop_offer["equipment_offers"])

    barrier=Barrier(2)
    def settle(source):
        session=_client(app)
        barrier.wait(timeout=20)
        if source=="quest":
            resp=session.post("/api/quests/v2/claim",json={
                "quest_id":QUEST,"period_key":period,"claim_operation_id":QUEST_OPERATION})
        else:
            resp=session.post("/api/shop/buy",json={
                "item_id":SKU,"purchase_operation_id":SHOP_OPERATION,
                "coins":999999,"price":1,"owned":True})
        return source,resp.status_code,resp.get_json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(settle,("quest","shop")))
    assert all(status==200 for _,status,_ in results),results
    assert all(data and (data.get("ok") is True if typ=="quest" else data.get("replayed") is not True)
               for typ,_,data in results),results

    after=_both(app)
    assert after["base"]["stats"]["xp"]-before["base"]["stats"]["xp"]==20
    assert after["base"]["stats"]["coins"]==715
    assert after["base"]["candies"]-before["base"]["candies"]==1
    assert len(after["detail"]["claims"])==1
    assert len(after["detail"]["purchases"])==1
    assert after["detail"]["purchases"][0]["resolved_price"]==300
    assert after["detail"]["purchases"][0]["operation_status"]=="COMMITTED"
    # Zone 1 first-clear legitimately awarded bamboo_shadow_blade earlier;
    # cross-source settlement must add exactly one new unique Shop weapon.
    before_gear={x["equip_id"] for x in before["detail"]["gear"]}
    after_gear={x["equip_id"] for x in after["detail"]["gear"]}
    assert after_gear-before_gear=={SKU},(before_gear,after_gear)
    assert after_gear & before_gear==before_gear
    baseline_ledger_ids={r["id"] for r in before["detail"]["ledger"]}
    posted_ledger=[r for r in after["detail"]["ledger"] if r["id"] not in baseline_ledger_ids]
    assert len(posted_ledger)==2,posted_ledger
    assert sorted(int(r["delta"]) for r in posted_ledger)==[-300,15],posted_ledger
    credits=[r for r in posted_ledger if int(r["delta"])==15]
    debits=[r for r in posted_ledger if int(r["delta"])==-300]
    assert len(credits)==len(debits)==1
    assert credits[0]["reason"]==f"quest_claim:{QUEST}:{period}",posted_ledger
    assert debits[0]["reason"]==f"coin_purchase:shop.static.{SKU}:{SHOP_OPERATION}",posted_ledger
    balance=1000
    for entry in posted_ledger:
        balance+=int(entry["delta"])
        assert balance==int(entry["balance_after"]),posted_ledger
    assert balance==715
    assert len(after["base"]["outbox"])-len(before["base"]["outbox"])==2
    events=_assert_exact_new_lineage(before,after)

    # Test-client response-loss simulation, NOT an actual network disconnect:
    # fresh authenticated sessions resend committed request payloads.
    again=_client(app)
    quest_retry=_ok(again.post("/api/quests/v2/claim",json={
        "quest_id":QUEST,"period_key":period,"claim_operation_id":QUEST_OPERATION}))
    assert quest_retry.get("duplicate") is True
    shop_retry=_ok(again.post("/api/shop/buy",json={
        "item_id":SKU,"purchase_operation_id":SHOP_OPERATION,
        "coins":999999,"price":1,"owned":True}))
    assert shop_retry.get("replayed") is True
    battle_retry=_ok(again.post("/api/adventure/map-battles/v1/answers",
                                json=original_battle,headers=HEADERS))
    assert battle_retry["duplicate"] is True
    assert _both(app)==after,"Any retry changed outbox, currency, claim, inventory, XP or progression"
    assert _ok(again.get("/api/shop/catalog"))["coins"]==715
    assert any(x["key"]=="go_spirit_candy" and x["qty"]>=1
               for x in _ok(again.get("/api/pet/status"))["inventory"])
    receipt={
        "schema":"G090_P0B_CROSS_SOURCE_CONCURRENT_PG_V1",
        "sources":["QUEST_V2","COIN_SHOP"],"http_codes":{a:b for a,b,_ in results},
        "starting_coins":before["base"]["stats"]["coins"],"final_coins":715,
        "quest_xp_delta":20,"quest_coin_delta":15,"shop_coin_delta":-300,
        "quest_candy_delta":1,"shop_weapon_delta":1,
        "outbox_before":len(before["base"]["outbox"]),
        "outbox_after":len(after["base"]["outbox"]),
        "new_events":[events["quest"],events["shop"]],
        "currency_ledger_new_rows":posted_ledger,
        "currency_ledger_delta_total":sum(int(r["delta"]) for r in posted_ledger),
        "currency_log_negative_300_count":1,"claim_count":1,"purchase_count":1,
        "cross_session_claim_replay":True,"cross_session_shop_replay":True,
        "battle_replay":True,"durable_snapshot_unchanged_after_retry":True,
        "synthetic_test_flag_only":True,"native_postgresql":True,
        "flask_test_client":True,"production_data_write":False
    }
    (tmp_path/"G090_P0B_CROSS_SOURCE_PG_RECEIPT.json").write_text(
        json.dumps(receipt,ensure_ascii=False,indent=2,default=str),encoding="utf8")
