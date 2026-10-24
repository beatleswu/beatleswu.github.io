"""G090 P0-B failure injection in real canonical Shop transaction.
A test-only late fault fires AFTER real purchase authority mutations but
BEFORE the app.py transaction commits. No production flags or writes.
"""
import json
from test_g088_shop_native_pg_idempotency import (
    shop, runtime, local_postgres, signed_client, snapshot, UID, SKU,
)

OP="g090b-shop-fault-rollback-and-retry"


def _events(app):
    with app.get_db() as conn:
        return [dict(x) for x in conn.execute(
            "SELECT event_id,event_type,player_id,source_event_id,"
            "idempotency_key,outcome,payload FROM domain_event_outbox "
            "WHERE player_id=? ORDER BY event_id",(str(UID),)).fetchall()]


def test_shop_transaction_rolls_back_if_post_acquisition_precommit_fails(shop,monkeypatch,tmp_path):
    client=signed_client(shop)
    before=snapshot(shop)
    outbox_before=_events(shop)
    assert before["stats"]=={"coins":1000,"xp":0}
    assert not before["operations"] and not before["owned"]

    original=shop.purchase_equipment_with_coins
    calls=[]
    def fail_after_real_purchase(*args,**kwargs):
        result=original(*args,**kwargs)
        calls.append(result)
        raise RuntimeError("G090_TEST_ONLY_AFTER_PURCHASE_BEFORE_COMMIT")
    monkeypatch.setattr(shop,"purchase_equipment_with_coins",fail_after_real_purchase)
    denied=client.post("/api/shop/buy",json={
        "item_id":SKU,"purchase_operation_id":OP,"price":1,"coins":999999})
    assert denied.status_code!=200,(denied.status_code,denied.get_json())
    assert len(calls)==1,"The full real purchase did not run before fault"
    assert snapshot(shop)==before,"Late exception leaked a debit, operation or item"
    assert _events(shop)==outbox_before,"Late exception leaked Outbox event"

    monkeypatch.setattr(shop,"purchase_equipment_with_coins",original)
    new_session=signed_client(shop)
    success=new_session.post("/api/shop/buy",json={
        "item_id":SKU,"purchase_operation_id":OP,"price":1,"coins":999999})
    assert success.status_code==200,(success.status_code,success.get_json())
    after=snapshot(shop)
    assert after["stats"]=={"coins":700,"xp":0}
    assert len(after["debits"])==len(after["operations"])==len(after["owned"])==1
    assert after["debits"][0]["delta"]==-300
    events=_events(shop)
    new=[e for e in events if e["event_id"] not in {x["event_id"] for x in outbox_before}]
    assert len(new)==1,new
    assert new[0]["event_type"]=="ITEM_ACQUISITION"
    assert new[0]["outcome"]=="SUCCESS"
    assert new[0]["idempotency_key"]==f"coin-purchase-acquisition:{OP}"
    assert new[0]["source_event_id"]==f"purchase:{UID}:{OP}"
    payload=new[0]["payload"]
    if isinstance(payload,str): payload=json.loads(payload)
    assert payload["item_id"]==SKU and payload["coins_spent"]==300

    replay=signed_client(shop).post("/api/shop/buy",json={
        "item_id":SKU,"purchase_operation_id":OP,"price":1,"coins":999999})
    assert replay.status_code==200 and replay.get_json().get("replayed") is True
    assert snapshot(shop)==after and _events(shop)==events
    receipt={
        "schema":"G090_P0B_SHOP_LATE_FAULT_PG_V1",
        "fault":"after_real_equipment_purchase_before_outer_commit",
        "injection_calls":len(calls),
        "fault_http_status":denied.status_code,
        "snapshot_equal_after_fault":True,
        "successful_retry_status":success.status_code,
        "coins_before":1000,"coins_after":700,
        "operation_count_after":1,"debit_count_after":1,"owned_item_count_after":1,
        "outbox_added_after_retry":1,
        "original_replay_no_write":True,
        "flask_test_client":True,"native_postgresql":True,
        "production_write":False
    }
    (tmp_path/"G090_P0B_SHOP_LATE_FAULT_RECEIPT.json").write_text(
        json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf8")
