"""G088 P0: synthetic real-PostgreSQL canonical Shop ledger idempotency.

Exercises the unmodified Flask /api/shop/buy and real Coin/Equipment authority;
never enables a formal product flag or touches Oracle/real player accounts.
This deliberately does NOT claim Hero/V2/V4 or production Shop admission.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest

from test_20261019_monthly_postgres import local_postgres, runtime
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_coin
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_slot

UID = 970388
SKU = "wooden_sword"

@pytest.fixture
def shop(runtime, monkeypatch):
    app = runtime
    monkeypatch.setenv(app.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    monkeypatch.setenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG, "1")
    with app.get_db() as conn:
        upgrade_coin(conn)
        upgrade_outbox(conn)
        upgrade_slot(conn, equipment_defs=app.EQUIPMENT_DEFS)
        conn.execute(
            "INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at) VALUES(?,?,?,?,?,?,?)",
            (UID, "g088-shop-disposable-player", "G088 Synthetic",
             "not-a-real-password", 0, "free", "2026-10-24T00:00:00"))
        conn.execute("INSERT INTO user_stats(user_id,coins,rank_level,xp) VALUES(?,?,?,?)",
                     (UID, 1000, "LV1", 0))
    assert app._canonical_coin_shop_purchase_enabled()
    return app

def signed_client(app):
    c = app.app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = UID
        s["username"] = "g088-shop-disposable-player"
    return c

def snapshot(app):
    with app.get_db() as conn:
        stats = dict(conn.execute(
            "SELECT coins,xp FROM user_stats WHERE user_id=?", (UID,)).fetchone())
        purchases = [dict(row) for row in conn.execute(
            "SELECT purchase_operation_id,offer_id FROM coin_purchase_operations WHERE user_id=? ORDER BY purchase_operation_id",
            (UID,)).fetchall()]
        debit = [dict(row) for row in conn.execute(
            "SELECT delta FROM currency_log WHERE user_id=? AND delta<0 ORDER BY id",
            (UID,)).fetchall()]
        inventory = [dict(row) for row in conn.execute(
            "SELECT equip_id,equipped,source FROM player_inventory WHERE user_id=? ORDER BY equip_id",
            (UID,)).fetchall()]
    return {"stats": stats, "operations": purchases, "debits": debit, "owned": inventory}

def request_payload(operation_id):
    return {"item_id": SKU, "purchase_operation_id": operation_id,
            "price": 1, "owned": True, "coins": 999999}

def test_same_purchase_operation_across_independent_sessions_never_double_debits(shop):
    first_client = signed_client(shop)
    offer = first_client.get("/api/shop/catalog")
    assert offer.status_code == 200
    data = offer.get_json()
    assert data["purchase_enabled"] is True
    assert any(e["item_id"] == SKU and e["price"] == 300 for e in data["equipment_offers"])
    first = first_client.post("/api/shop/buy", json=request_payload("g088-same-operation-001"))
    assert first.status_code == 200, first.get_json()
    after_first = snapshot(shop)
    assert after_first["stats"] == {"coins": 700, "xp": 0}
    assert len(after_first["operations"]) == len(after_first["debits"]) == len(after_first["owned"]) == 1
    assert after_first["debits"][0]["delta"] == -300
    fresh = signed_client(shop)
    second = fresh.post("/api/shop/buy", json=request_payload("g088-same-operation-001"))
    assert second.status_code == 200, second.get_json()
    assert second.get_json().get("replayed") is True
    assert snapshot(shop) == after_first, "Cross-session replay changed accounting or ownership"

def test_four_parallel_replays_of_one_purchase_do_not_double_debit(shop):
    id_ = "g088-parallel-operation-002"
    barrier = Barrier(4)
    def buy(_):
        c = signed_client(shop)
        barrier.wait(timeout=15)
        response = c.post("/api/shop/buy", json=request_payload(id_))
        return response.status_code, response.get_json()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(buy, range(4)))
    assert all(code == 200 for code, _ in results), results
    assert sum((response or {}).get("replayed") is not True for _,response in results) == 1, results
    after = snapshot(shop)
    assert after["stats"] == {"coins": 700, "xp": 0}, after
    assert len(after["operations"]) == len(after["debits"]) == len(after["owned"]) == 1, after
    assert after["debits"][0]["delta"] == -300
    replay = signed_client(shop).post("/api/shop/buy", json=request_payload(id_))
    assert replay.status_code == 200 and replay.get_json().get("replayed") is True
    assert snapshot(shop) == after

def test_disabled_shop_cannot_write_even_with_valid_operation(shop, monkeypatch):
    before=snapshot(shop)
    monkeypatch.delenv(shop.CANONICAL_COIN_SHOP_PURCHASE_FLAG, raising=False)
    response=signed_client(shop).post("/api/shop/buy",json=request_payload("g088-disabled-003"))
    assert response.status_code in (403,409,503),response.get_json()
    assert snapshot(shop)==before


def test_two_distinct_operations_racing_same_unique_equipment(shop):
    # More adversarial than replaying one operation id. Two *distinct* valid
    # purchase requests must not double charge for a single unique weapon.
    barrier=Barrier(2)
    def purchase(n):
        c=signed_client(shop)
        barrier.wait(timeout=15)
        r=c.post("/api/shop/buy",json=request_payload(f"g088-distinct-{n}"))
        return r.status_code,r.get_json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(purchase,range(2)))
    assert sorted(code for code,_ in results)[0]==200,results
    after=snapshot(shop)
    assert after["stats"]=={"coins":700,"xp":0},(results,after)
    assert len(after["debits"])==1,(results,after)
    assert len(after["owned"])==1,(results,after)
    assert len(after["operations"])==1,(results,after)
