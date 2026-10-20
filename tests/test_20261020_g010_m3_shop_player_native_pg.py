"""G010 M3: real Chrome Shop purchase => server inventory => equip => relogin.

The release HTML remains G009 browse/read-only. Only an IN-MEMORY HTML
test variant is activated by loopback-only WSGI for this synthetic user,
while native PG and /api routes are REAL, unmocked. No Product changes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import threading

import pytest
from werkzeug.serving import make_server
from test_20261019_monthly_postgres import local_postgres, runtime
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_coin
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_slot
from migrations.item_use_operations_v1 import upgrade as upgrade_item_use

UID=970311
SKU="wooden_sword"


def _login(app):
    client=app.app.test_client()
    with client.session_transaction() as s:
        s["user_id"]=UID
        s["username"]="g010-m3-synthetic-player"
    return client


def _activate_preview_only_in_memory(real_app):
    root=Path(__file__).resolve().parents[1]
    source={
        "/shop":(root/"shop.html",
                 "const G009_SHOP_BROWSE_PREVIEW_ONLY = true;",
                 "const G009_SHOP_BROWSE_PREVIEW_ONLY = false;"),
        "/inventory":(root/"inventory.html",
                      "const G009_BACKPACK_READ_ONLY = true;",
                      "const G009_BACKPACK_READ_ONLY = false;"),
    }
    html={}
    for key,(path,closed,open_) in source.items():
        content=path.read_text(encoding="utf-8")
        assert content.count(closed)==1,f"original {key} preview lock changed!"
        activated=content.replace(closed,open_)
        if key=="/inventory":
            # The E10 manual-use button exists but E10 is normally not the
            # public Backpack mode. Activate it only in this loopback copy.
            e10_default="const E10_BACKPACK_MODE = window.__GO_E10_BACKPACK_MODE__ === true;"
            assert activated.count(e10_default)==1
            activated=activated.replace(e10_default,"const E10_BACKPACK_MODE = true;")
            # Shipped G009 presentation CSS hides the action via the
            # body[data-g009-surface="backpack"] selector at !important.
            # Only this in-memory, loopback HTTP copy releases that
            # *visual* latch; original source and server gate stay intact.
            locked_body='<body data-g009-surface="backpack"'
            assert activated.count(locked_body)==1
            activated=activated.replace(
                locked_body,
                '<body data-g009-surface="g010-m3-isolated"')
        html[key]=activated.encode("utf-8")
        assert closed in path.read_text(encoding="utf-8"),"shipped lock must be kept"

    def isolated_wsgi(environ,start_response):
        path=environ.get("PATH_INFO","")
        if path in html and environ.get("REQUEST_METHOD")=="GET":
            assert environ.get("REMOTE_ADDR") in ("127.0.0.1","::1")
            body=html[path]
            start_response("200 OK",[
                ("Content-Type","text/html; charset=utf-8"),
                ("Content-Length",str(len(body))),
                ("Cache-Control","no-store"),
                ("X-G010-Isolated-Page-Variant","test-only"),
            ])
            return [body]
        return real_app(environ,start_response)
    return isolated_wsgi


@pytest.mark.parametrize("mode",["desktop_mouse","chrome_tablet_touch"])
def test_m3_shop_real_ui_purchase_backpack_equip_relogin(runtime,monkeypatch,mode):
    app=runtime
    assert os.environ.get("PRODUCTION","").lower()!="true"
    with app.get_db() as conn:
        upgrade_coin(conn)
        upgrade_outbox(conn)
        upgrade_slot(conn,equipment_defs=app.EQUIPMENT_DEFS)
        # D5C item-use durable operation schema is an explicit, additive
        # candidate migration; init_db does not implicitly apply it.
        assert upgrade_item_use(conn)["table"]=="item_use_operations"
        conn.execute(
            "INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (UID,"g010-m3-synthetic-player","Shop M3","unused",0,"free","2026-10-20T00:00:00"),
        )
        conn.execute("INSERT INTO user_stats(user_id,coins,rank_level,xp) VALUES(?,?,?,?)",
                     (UID,1000,"LV1",0))
        # A separate synthetic, already-earned consumable. Legacy retail
        # purchase of this item is retired; this is NOT a claimed store sale.
        conn.execute("INSERT INTO shop_inventory(user_id,item_key,qty) "
                     "VALUES(?,?,?)",(UID,"xp_potion",1))

    logged=_login(app)
    first=logged.get("/api/shop/catalog")
    assert first.status_code==200
    assert first.get_json()["purchase_enabled"] is False
    assert app._canonical_coin_shop_purchase_enabled() is False
    assert app._equipment_canonical_loadout_enabled() is False
    denied=logged.post("/api/shop/buy",json={
        "item_key":SKU,"purchase_operation_id":"g010-m3-disabled-operation"
    })
    assert denied.status_code!=200
    with app.get_db() as conn:
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=?",
                            (UID,)).fetchone()["coins"]==1000

    # Test-only, and the browser still cannot bypass server purchase rules.
    monkeypatch.setenv(app.CANONICAL_COIN_SHOP_PURCHASE_FLAG,"1")
    monkeypatch.setenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,"1")
    catalog=logged.get("/api/shop/catalog").get_json()
    assert catalog["purchase_enabled"] is True
    offer=next(x for x in catalog["equipment_offers"] if x["item_id"]==SKU)
    assert len(catalog["equipment_offers"])==9
    price=offer["price"]
    assert price==300
    assert catalog["equipment_ownership"][SKU]["owned_quantity"]==0
    me=logged.get("/api/auth/me")
    assert me.status_code==200
    assert me.get_json()["equipment_loadout_enabled"] is True

    current=logged.get_cookie("session")
    fresh=_login(app).get_cookie("session")
    assert current and fresh and current.value and fresh.value
    server=make_server("127.0.0.1",0,_activate_preview_only_in_memory(app.app.wsgi_app),
                       threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        runner=(Path(__file__).parent/"e2e"/
                "run_20261020_g010_m3_shop_purchase_equip_real_browser.mjs")
        result=subprocess.run(
            ["node",str(runner)],
            input=json.dumps({
                "origin":f"http://127.0.0.1:{server.server_port}",
                "sessionCookie":current.value,
                "reloginCookie":fresh.value,
                "offerId":offer["offer_id"],
                "itemId":SKU,
                "price":price,
                "startingCoins":1000,
            }),
            capture_output=True,text=True,encoding="utf-8",timeout=150,
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ,"GO_G010_M3_TOUCH":
                 "1" if mode=="chrome_tablet_touch" else "0"},
        )
        assert result.returncode==0,result.stderr[-5000:]+result.stdout[-1500:]
        output=json.loads(result.stdout)
        assert output["verdict"]=="G010_M3_REAL_BROWSER_PURCHASE_EQUIP_RELOGIN_PASS"
        assert output["originalReleasePreviewLocked"] is True
        assert output["renderedPageIsTestOnlyActivatedVariant"] is True
        assert output["price"]==price
        assert output["writes"].count("POST /api/shop/buy")==1
        assert output["writes"].count("POST /api/player/inventory/equip")==1
    finally:
        server.shutdown()
        thread.join(timeout=8)
        server.server_close()

    # Server writer, no localStorage/JS counter can spoof these.
    with app.get_db() as conn:
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=?",
                            (UID,)).fetchone()["coins"]==1000-price
        rows=conn.execute("SELECT id,equip_id,equipped,source "
                          "FROM player_inventory WHERE user_id=?",(UID,)).fetchall()
        assert len(rows)==1 and rows[0]["equip_id"]==SKU
        assert rows[0]["equipped"]==1
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM currency_log WHERE user_id=? AND delta<0",
            (UID,)).fetchone()["n"]==1
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM coin_purchase_operations "
            "WHERE user_id=?",(UID,)).fetchone()["n"]==1
    assert _login(app).get("/api/shop/catalog").get_json()["coins"]==1000-price
    with app.get_db() as conn:
        stock=conn.execute("SELECT qty FROM shop_inventory WHERE user_id=? "
                           "AND item_key='xp_potion'",(UID,)).fetchone()
        assert stock and stock["qty"]==0
        effect=conn.execute("SELECT value FROM active_effects "
                            "WHERE user_id=? AND effect_key='xp_potion'",(UID,)).fetchone()
        assert effect is not None and float(effect["value"])>=1.5
        # D5C stores one successful use operation; a click cannot apply the
        # boost and consume stock twice even if a response were replayed.
        use_ops=conn.execute(
            "SELECT COUNT(*) AS n FROM item_use_operations "
            "WHERE player_id=? AND item_id='xp_potion' "
            "AND operation_status='SUCCESS'",(str(UID),)
        ).fetchone()["n"]
        assert use_ops==1
        assert conn.execute(
            "SELECT xp FROM user_stats WHERE user_id=?",(UID,)
        ).fetchone()["xp"]==0

    # Restore gate: shipped source still locked and server rejects fresh buys.
    monkeypatch.delenv(app.CANONICAL_COIN_SHOP_PURCHASE_FLAG,raising=False)
    monkeypatch.delenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,raising=False)
    assert app._canonical_coin_shop_purchase_enabled() is False
    assert app._equipment_canonical_loadout_enabled() is False
    assert _login(app).get("/api/shop/catalog").get_json()["purchase_enabled"] is False
