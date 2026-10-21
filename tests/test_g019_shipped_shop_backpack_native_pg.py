"""G019 stage: REAL shipped /shop + /inventory HTML (no WSGI substitutions)
once both existing canonical Shop/Loadout and new separate release presentation
flag are explicitly set in a disposable native PostgreSQL pytest process.
Default production false; no private G011/P038 asset is admitted to Product.
"""
from pathlib import Path
import json,os,threading,subprocess
import pytest
from werkzeug.serving import make_server
from test_20261019_monthly_postgres import runtime,local_postgres
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_coin
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_slot
ROOT=Path(__file__).resolve().parents[1]
EV=Path(r"D:\go-odyssey-g010-3d-activation-evidence-20261021")
UID=983190
SKU="wooden_sword"
def _session(app,tag):
 client=app.app.test_client()
 with client.session_transaction() as s:
  s["user_id"]=UID
  s["username"]="g019-actual-product-isolate"
  s["g019_unique_session"]=tag
 return client
@pytest.mark.parametrize('mode',['desktop_mouse','chrome_tablet_touch'])
def test_G019_actual_shipped_shop_backpack_canonical_purchase_to_hero(runtime,monkeypatch,mode):
 app=runtime
 assert os.environ.get("PRODUCTION")!="1"
 assert app._canonical_coin_shop_purchase_enabled() is False
 assert app._equipment_canonical_loadout_enabled() is False
 assert not any("g018_qa_" in x["id"] or "g014_qa_" in x["id"]
                for x in app.CANONICAL_EQUIPMENT_DEFS)
 with app.get_db() as db:
  upgrade_coin(db)
  upgrade_outbox(db)
  upgrade_slot(db,equipment_defs=app.EQUIPMENT_DEFS)
  db.execute("INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at) VALUES(?,?,?,?,?,?,?)",
   (UID,"g019-actual-product-isolate","G019 synthetic","unused",0,"free","2026-10-21T00:00:00"))
  db.execute("INSERT INTO user_stats(user_id,coins,rank_level,xp) VALUES(?,?,?,?)",
   (UID,900,"LV1",0))
 main=_session(app,"original");fresh=_session(app,"fresh-signature")
 assert main.get_cookie("session").value!=fresh.get_cookie("session").value
 def catalog():return main.get("/api/shop/catalog").get_json()
 off=catalog()
 assert off["purchase_enabled"] is False
 assert off["approved_equipment_purchase_ui_enabled"] is False
 assert main.get("/api/auth/me").get_json()["g019_equipment_actions_ui_enabled"] is False
 assert main.post("/api/shop/buy",json={"item_key":SKU,"purchase_operation_id":"g019-failclosed"}).status_code==409
 monkeypatch.setenv(app.CANONICAL_COIN_SHOP_PURCHASE_FLAG,"1")
 monkeypatch.setenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,"1")
 # New UI release flag must stay independently OFF, even with backend writes ON.
 flag_off=catalog()
 assert flag_off["purchase_enabled"] is True
 assert flag_off["approved_equipment_purchase_ui_enabled"] is False
 assert main.get("/api/auth/me").get_json()["g019_equipment_actions_ui_enabled"] is False
 offers=flag_off["equipment_offers"]
 assert len(offers)==9
 assert not any(str(x["item_id"]).startswith(("g014_qa_","g018_qa_"))
                for x in offers)
 offer=next(x for x in offers if x["item_id"]==SKU)
 assert offer["price"]==300
 monkeypatch.setenv(app.G019_APPROVED_EQUIPMENT_SHOP_UI_FLAG,"1")
 enabled=catalog()
 assert enabled["purchase_enabled"] is True
 assert enabled["approved_equipment_purchase_ui_enabled"] is True
 assert main.get("/api/auth/me").get_json()["g019_equipment_actions_ui_enabled"] is True
 assert len(enabled["equipment_offers"])==9
 server=make_server("127.0.0.1",0,app.app.wsgi_app,threaded=True)
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  runner=ROOT/"tests/e2e/g019_shipped_shop_backpack_purchase_equip_relogin.mjs"
  p=subprocess.run(["node",str(runner)],input=json.dumps({
   "origin":f"http://127.0.0.1:{server.server_port}",
   "sessionCookie":main.get_cookie("session").value,
   "reloginCookie":fresh.get_cookie("session").value,
   "offerId":offer["offer_id"],"itemId":SKU,
   "price":offer["price"],"startingCoins":900
  }),capture_output=True,text=True,encoding="utf8",errors="replace",
  timeout=180,cwd=ROOT,env={**os.environ,"GO_G010_M3_TOUCH":"1" if mode=="chrome_tablet_touch" else "0"})
  assert p.returncode==0,p.stderr[-6600:]+p.stdout[-2700:]
  result=json.loads(p.stdout)
  assert result["verdict"]=="G019_SHIPPED_SHOP_BACKPACK_REAL_PG_EQUIP_RELOGIN_PASS"
  assert result["renderedPageIsTestOnlyActivatedVariant"] is False
  assert result["writes"].count("POST /api/shop/buy")==1
  assert result["writes"].count("POST /api/player/inventory/equip")==1
  assert result["coinsAfter"]==600
 finally:
  server.shutdown();thread.join(timeout=8);server.server_close()
 with app.get_db() as db:
  row=db.execute("SELECT coins FROM user_stats WHERE user_id=?",(UID,)).fetchone()
  assert row["coins"]==600
  equipped=db.execute("SELECT equip_id,equipped FROM player_inventory WHERE user_id=?",(UID,)).fetchall()
  assert len(equipped)==1 and equipped[0]["equip_id"]==SKU and equipped[0]["equipped"]==1
  assert db.execute("SELECT COUNT(*) AS n FROM coin_purchase_operations WHERE user_id=?",(UID,)).fetchone()["n"]==1
  assert db.execute("SELECT COUNT(*) AS n FROM currency_log WHERE user_id=? AND delta<0",(UID,)).fetchone()["n"]==1
 monkeypatch.delenv(app.G019_APPROVED_EQUIPMENT_SHOP_UI_FLAG,raising=False)
 monkeypatch.delenv(app.CANONICAL_COIN_SHOP_PURCHASE_FLAG,raising=False)
 monkeypatch.delenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,raising=False)
 assert catalog()["purchase_enabled"] is False
 assert catalog()["approved_equipment_purchase_ui_enabled"] is False
 assert main.get("/api/auth/me").get_json()["g019_equipment_actions_ui_enabled"] is False
 output={"schema":"G019_SHIPPED_PUBLIC_UI_CANONICAL_EQUIPMENT_PURCHASE_REAL_PG_V1",
  "verdict":result["verdict"],"actual_original_shop_and_backpack":True,
  "in_memory_HTML_overrides":False,"canonical_server_offer_count":9,
  "purchased_item":SKU,"coins_spent":300,"coin_debit_operations":1,
  "native_pg_synthetic_owner":True,
  "real_chrome_shop_buy":1,"real_chrome_backpack_equip":1,
  "relogin_signed_session":True,"backend_default_off_409":True,
  "UI_release_flag_independent_default_off":True,
  "posttest_all_flags_restored_off":True,
  "unadmitted_P022_or_P038_saleable":False,
  "original_shop_browse_design_stays_default":True,
  "oracle_deployed":False,"github_master_merged":False,
  "real_player_writes":False,
  "browser":result}
 EV.mkdir(exist_ok=True)
 dest=EV/("G019_SHIPPED_SHOP_BACKPACK_REAL_PG_20261021.json" if mode=="desktop_mouse" else "G019_SHIPPED_SHOP_BACKPACK_REAL_PG_TABLET_20261021.json")
 dest.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf8")
 print("G019_ORIGINAL_SHOP_BACKPACK_REAL_PURCHASE_PASS",dest,flush=True)
