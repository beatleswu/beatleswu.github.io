"""Governed shop -> canonical equipment ownership -> gated equip -> relogin.

Runs against NEW loopback native PostgreSQL created by monthly native fixture.
Only this Python test process opts into the coin-shop and loadout flags;
it never edits Product defaults, real users, Oracle, or approval policy.
"""
from __future__ import annotations

import pytest
from test_20261019_monthly_postgres import local_postgres, runtime
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_coin
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_slot

UID = 970201
SKU = "wooden_sword"
OP = "isolated-20261020-governed-shop-wooden-sword"


def _login(app):
    client = app.app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = UID
        s["username"] = "isolated-shop-player"
    return client


def test_shop_native_pg_purchase_inventory_equip_relogin(runtime, monkeypatch):
    app = runtime
    # Build missing optional app migration seams *only* on disposable PG.
    with app.get_db() as conn:
        upgrade_coin(conn)
        upgrade_outbox(conn)
        upgrade_slot(conn, equipment_defs=app.EQUIPMENT_DEFS)
        conn.execute(
            "INSERT INTO users (id,username,nickname,password_hash,is_admin,plan,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (UID, "isolated-shop-player", "Isolated Shop", "unused", 0,
             "free", "2026-10-20T00:00:00"),
        )
        conn.execute(
            "INSERT INTO user_stats(user_id,coins,rank_level,xp) VALUES(?,?,?,?)",
            (UID, 1000, "LV1", 0),
        )

    buyer = _login(app)
    closed = buyer.get("/api/shop/catalog")
    assert closed.status_code == 200
    assert closed.get_json()["purchase_enabled"] is False
    assert app._canonical_coin_shop_purchase_enabled() is False
    assert app._equipment_canonical_loadout_enabled() is False

    body = {"item_id": SKU, "purchase_operation_id": OP, "price": 1}
    denied = buyer.post("/api/shop/buy", json=body)
    assert denied.status_code in (400, 409), denied.get_json()
    assert denied.get_json().get("code") in ("SHOP_PURCHASE_DISABLED",
                                            "UNKNOWN_OFFER")
    with app.get_db() as conn:
        assert conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=?", (UID,)
        ).fetchone()["coins"] == 1000
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM player_inventory WHERE user_id=?",
            (UID,),
        ).fetchone()["n"] == 0

    # Authorized only inside this disposable test process.
    monkeypatch.setenv(app.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    opened = buyer.get("/api/shop/catalog")
    assert opened.status_code == 200
    catalog = opened.get_json()
    assert catalog["purchase_enabled"] is True
    offer = next(x for x in catalog["equipment_offers"]
                 if x["item_id"] == SKU)
    assert offer["price"] == 300
    assert catalog["equipment_ownership"][SKU]["owned_quantity"] == 0

    purchased = buyer.post("/api/shop/buy", json=body)
    assert purchased.status_code == 200, purchased.get_json()
    result = purchased.get_json()
    assert result["ok"] is True
    assert result["coins_spent"] == offer["price"]
    assert result["coins_after"] == 700
    assert result["canonical_acquisition_result"]["can_equip"] is True

    inventory = buyer.get("/api/player/inventory")
    assert inventory.status_code == 200, inventory.get_json()
    owned = [x for x in inventory.get_json()
             if x.get("id") == SKU or x.get("item_id") == SKU
             or x.get("equip_id") == SKU]
    assert len(owned) == 1, inventory.get_json()
    inv_id = owned[0].get("inv_id") or owned[0].get("id")
    # Payload id might be item id for presentation; use exact server-owned row id.
    with app.get_db() as conn:
        item = conn.execute(
            "SELECT id,equip_id,equipped FROM player_inventory "
            "WHERE user_id=? AND equip_id=?", (UID, SKU)
        ).fetchone()
        assert item and item["equipped"] == 0
        inv_id = item["id"]

    blocked = buyer.post("/api/player/inventory/equip",
                         json={"inv_id": inv_id, "action": "equip"})
    assert blocked.status_code == 409, blocked.get_json()
    assert blocked.get_json()["error"] == "LOADOUT_DISABLED"

    monkeypatch.setenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG, "1")
    equip = buyer.post("/api/player/inventory/equip",
                       json={"inv_id": inv_id, "action": "equip"})
    assert equip.status_code == 200, equip.get_json()
    assert equip.get_json()["equipped"] is True
    assert equip.get_json()["target_ownership_row_id"] == inv_id

    replay = buyer.post("/api/shop/buy", json=body)
    assert replay.status_code == 200, replay.get_json()
    assert replay.get_json()["replayed"] is True
    duplicate = buyer.post(
        "/api/shop/buy",
        json={"item_id": SKU, "purchase_operation_id": OP + "-different"},
    )
    assert duplicate.status_code == 409
    assert duplicate.get_json()["code"] == "EQUIPMENT_ALREADY_OWNED"

    # Truly independent cookie session must read DB, not JS cache.
    returning = _login(app)
    inventory_again = returning.get("/api/player/inventory")
    assert inventory_again.status_code == 200
    assert any(x.get("equipped") is True
               for x in inventory_again.get_json()
               if x.get("id") == SKU or x.get("item_id") == SKU
               or x.get("equip_id") == SKU)
    catalog_again = returning.get("/api/shop/catalog").get_json()
    assert catalog_again["coins"] == 700
    assert catalog_again["equipment_ownership"][SKU]["owned_quantity"] == 1

    with app.get_db() as conn:
        assert conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=?", (UID,)
        ).fetchone()["coins"] == 700
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM player_inventory WHERE user_id=? "
            "AND equip_id=? AND equipped=1", (UID, SKU)
        ).fetchone()["n"] == 1
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM coin_purchase_operations "
            "WHERE purchase_operation_id=?", (OP,)
        ).fetchone()["n"] == 1
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM currency_log WHERE user_id=? AND delta<0",
            (UID,),
        ).fetchone()["n"] == 1

    # Browser presentation must stay locked and truthful even for an account
    # with existing equipment; a visible page cannot mutate anything.
    monkeypatch.delenv(app.CANONICAL_COIN_SHOP_PURCHASE_FLAG, raising=False)
    monkeypatch.delenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG, raising=False)
    assert app._canonical_coin_shop_purchase_enabled() is False
    assert app._equipment_canonical_loadout_enabled() is False
    cookie = returning.get_cookie("session")
    assert cookie and cookie.value
    import json
    import os
    import subprocess
    import threading
    from pathlib import Path
    from werkzeug.serving import make_server
    server = make_server("127.0.0.1", 0, app.app.wsgi_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        runner = (Path(__file__).parent / "e2e"
                  / "run_20261020_shop_backpack_governed_browser.mjs")
        check = subprocess.run(
            ["node", str(runner)],
            input=json.dumps({
                "origin": f"http://127.0.0.1:{server.server_port}",
                "sessionCookie": cookie.value,
                "expectedInvId": inv_id,
            }),
            capture_output=True, text=True, encoding="utf-8",
            timeout=100, cwd=Path(__file__).resolve().parent.parent,
            env=dict(os.environ),
        )
        assert check.returncode == 0, check.stderr[-2500:] + check.stdout[-1400:]
        assert "REAL_SHOP_BACKPACK_GOVERNED_BROWSER_PASS" in check.stdout
    finally:
        server.shutdown()
        thread.join(timeout=5)
    # Real pages should not have changed either balance or ownership.
    with app.get_db() as conn:
        assert conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=?", (UID,)
        ).fetchone()["coins"] == 700
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM player_inventory "
            "WHERE user_id=? AND equip_id=? AND equipped=1",
            (UID, SKU),
        ).fetchone()["n"] == 1
