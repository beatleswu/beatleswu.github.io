"""G089: actual adventure/lord => authoritative quest => concurrent claim API.
Test ONLY, deliberately reuses existing server flows, true disposable PG.
No product, live user, Oracle, or V2/V4 writes.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import json

from test_20261020_g010_zone2_quest_claim_native_pg import (
    zone2_player, _client, ZONE2, ZONE2_QUESTION,
    ZONE2_EXTRA_QUESTIONS, HEADERS, lord,
    upgrade_outbox, upgrade_progress, upgrade_claim, upgrade_login,
)
from test_20261019_monthly_postgres import local_postgres, runtime as native_runtime
from test_20261019_lord_full_journey_native_pg import lord_player

UID=lord.UID
QUEST="daily:streak_correct"

def _ok(resp):
    assert resp.status_code==200, (resp.status_code,resp.get_json())
    return resp.get_json()

def _snapshot(app):
    with app.get_db() as conn:
        u=dict(conn.execute("SELECT xp,coins FROM user_stats WHERE user_id=?",(UID,)).fetchone())
        rows=int(conn.execute(
            "SELECT COUNT(*) AS n FROM review_log WHERE user_id=?",(UID,)).fetchone()["n"])
        claims=[dict(x) for x in conn.execute(
            "SELECT quest_id,period_key FROM quest_claims_v2 WHERE user_id=? ORDER BY quest_id,period_key",
            (str(UID),)).fetchall()]
        row=conn.execute(
            "SELECT qty FROM pet_inventory WHERE user_id=? AND item_key='go_spirit_candy'",(UID,)
        ).fetchone()
        candies=int(row["qty"]) if row else 0
        debits=[dict(x) for x in conn.execute(
            "SELECT delta FROM currency_log WHERE user_id=? ORDER BY id",(UID,)
        ).fetchall()]
        progress=[dict(x) for x in conn.execute(
            "SELECT quest_id,progress,completed,period_key FROM quest_progress_v2 WHERE user_id=? ORDER BY quest_id",
            (str(UID),)).fetchall()]
    return dict(stats=u,reviews=rows,claims=claims,candies=candies,
                currency_log=debits,quest_progress=progress)

def test_g089_cross_mode_two_distinct_quest_claim_operations_exactly_once(zone2_player,monkeypatch,tmp_path):
    app,player=zone2_player
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE","global")
    # 1. Genuine server-judged first-clear lord, no fake unlock or direct DB completion.
    lord.seed_lord_eligibility(player)
    started=_ok(player.post("/api/adventure/boss/start",json={"zone_key":lord.ZONE}))
    for i,qid in enumerate(started["question_ids"]):
        q=lord.QUESTION_BY_ID[qid]
        ans=_ok(player.post("/api/srs/review",json={
          "question_id":qid,"grade":5,"response_ms":800+i,
          "source_context":f"boss_trial:{started['attempt_id']}",
          "boss_answer":{"moves":[dict(q["accepted_moves"][0])]}
        }))
        assert ans["ok"]
    finish=_ok(player.post("/api/adventure/boss/finish",json={"correct":0,"total":0}))
    assert finish["passed"] is True
    with app.get_db() as conn:
        for fn in (upgrade_outbox,upgrade_progress,upgrade_claim,upgrade_login):
            result=fn(conn)
            assert result.get("valid",True) is True,result
    monkeypatch.setenv("QUEST_V2_RUNTIME_ENABLED","true")

    # 2. Exactly 3 genuine Zone 2 Map Battle settlements.
    client=_client(app)
    real_requests=[]
    for q in [ZONE2_QUESTION]+ZONE2_EXTRA_QUESTIONS[:2]:
        issued=_ok(client.post("/api/adventure/map-battles/v1/attempts",
           json={"zone_key":ZONE2,"question_id":q["id"]},headers=HEADERS))
        request={
          "battle_id":issued["battle_id"],"attempt_id":issued["attempt_id"],
          "submission_nonce":issued["submission_nonce"],
          "battle_revision":issued["battle"]["battle_revision"],
          "question_revision":issued["question_revision"],
          "player_color":issued["player_color"],
          "transform_id":issued["transform_id"],
          "transform_version":issued["transform_version"],
          "moves":[dict(q["accepted_moves"][0])]
        }
        verdict=_ok(client.post("/api/adventure/map-battles/v1/answers",
                                 json=request,headers=HEADERS))
        assert verdict["accepted"] and verdict["result"]=="CORRECT"
        assert not verdict["duplicate"]
        real_requests.append(request)
    initial=_snapshot(app)
    progress=next(r for r in initial["quest_progress"]
       if r["quest_id"]==QUEST and r["completed"])
    period=progress["period_key"]
    assert not any(r["quest_id"]==QUEST for r in initial["claims"])

    # 3. Cross-session distinct operation IDs RACE for same earned quest.
    barrier=Barrier(2)
    def claim(which):
        c=_client(app)
        barrier.wait(timeout=20)
        resp=c.post("/api/quests/v2/claim",json={
           "quest_id":QUEST,"period_key":period,
           "claim_operation_id":f"g089-race-different-{which}"})
        return resp.status_code,resp.get_json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(claim,("a","b")))
    assert all(code==200 for code,_ in results),results
    assert all((data or {}).get("ok") is True for _,data in results),results
    assert sum((data or {}).get("duplicate") is True for _,data in results)==1,results

    after=_snapshot(app)
    assert after["stats"]["coins"]-initial["stats"]["coins"]==15,(initial,after,results)
    # Canonical daily:streak_correct grants 20 XP as well as 15 coins and one candy.
    assert after["stats"]["xp"]-initial["stats"]["xp"]==20,(initial,after)
    assert after["candies"]-initial["candies"]==1,(initial,after)
    assert after["reviews"]==initial["reviews"]
    assert len([row for row in after["claims"] if row["quest_id"]==QUEST])==1
    # One fresh independently authenticated session, new Operation ID,
    # and one original server-judged battle replay. Neither can mint value.
    fresh=_client(app)
    again=_ok(fresh.post("/api/quests/v2/claim",json={
       "quest_id":QUEST,"period_key":period,
       "claim_operation_id":"g089-third-independent-operation"}))
    assert again.get("duplicate") is True,again
    battle_retry=_ok(fresh.post("/api/adventure/map-battles/v1/answers",
                  json=real_requests[-1],headers=HEADERS))
    assert battle_retry["duplicate"] is True,battle_retry
    assert _snapshot(app)==after,"Replay mutated XP, coins, candy, claims, quests or reviews"
    assert _ok(fresh.get("/api/shop/catalog"))["coins"]==after["stats"]["coins"]
    pet=_ok(fresh.get("/api/pet/status"))["inventory"]
    assert any(x["key"]=="go_spirit_candy" and x["qty"]>=after["candies"] for x in pet)
    # Evidence is confined to disposable pytest output; no production secrets.
    receipt={
      "schema":"G089_CROSS_MODE_NATIVE_PG_REWARD_ONCE_V1",
      "synthetic_player":True,"real_product_api":True,
      "real_disposable_postgresql":True,
      "zone1_lord_finish":"PASSED","zone2_server_judged_answers":3,
      "distinct_claim_operation_ids":2,
      "parallel_claim_http_statuses":[status for status,_ in results],
      "parallel_claim_duplicates":sum(body.get("duplicate") is True for _,body in results),
      "coins_before":initial["stats"]["coins"],
      "coins_after":after["stats"]["coins"],
      "xp_before":initial["stats"]["xp"],
      "xp_after":after["stats"]["xp"],
      "candy_before":initial["candies"],
      "candy_after":after["candies"],
      "claim_count":len([row for row in after["claims"] if row["quest_id"]==QUEST]),
      "reviews_before":initial["reviews"],
      "reviews_after":after["reviews"],
      "cross_session_new_operation_duplicate":True,
      "adventure_answer_replay_duplicate":True,
      "durable_snapshot_unchanged_after_replay":True,
      "shop_and_pet_projections_match":True,
      "production_write":False,
      "physical_ipad_safari":False
    }
    (tmp_path/"G089_CROSS_MODE_REWARD_PG_RECEIPT.json").write_text(
         json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf-8")
