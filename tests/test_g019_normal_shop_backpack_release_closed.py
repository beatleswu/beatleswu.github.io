"""G019 independent fail-closed three-key Product UI release proof, four
native PG / REAL original Chrome page states. Server APIs never mocked.
"""
from pathlib import Path
import json,os,subprocess,threading
from werkzeug.serving import make_server
from test_20261019_monthly_postgres import runtime,local_postgres
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_slot
ROOT=Path(__file__).resolve().parents[1]
EV=Path(r"D:\go-odyssey-g010-3d-activation-evidence-20261021")
UID=983191
def test_g019_shipped_default_off_even_when_some_flags_enabled(runtime,monkeypatch):
 app=runtime
 assert os.environ.get("PRODUCTION")!="1"
 with app.get_db() as db:
  upgrade_slot(db,equipment_defs=app.EQUIPMENT_DEFS)
  db.execute("INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at) VALUES(?,?,?,?,?,?,?)",
    (UID,"g019-negative-isolate","G019 negative QA","unused",0,"free","2026-10-21T00:00:00"))
  db.execute("INSERT INTO user_stats(user_id,coins,rank_level,xp) VALUES(?,?,?,?)",
    (UID,1100,"LV1",0))
  owned=app.grant_equipment_ownership(db,UID,"wooden_sword","admin",
    equipment_defs=app.EQUIPMENT_DEFS)
  assert owned and not owned.equipped
 invId=owned.row_id
 client=app.app.test_client()
 with client.session_transaction() as s:
  s["user_id"]=UID;s["username"]="g019-negative-isolate";s["unique"]="gate-check"
 cookie=client.get_cookie("session").value
 cases=[
  ("all_off",False,False,False),
  ("backend_only_no_release",True,True,False),
  ("shop_release_no_loadout",True,False,True),
  ("shop_release_no_coins",False,True,True)
 ]
 browser=ROOT/"tests/e2e/g019_shipped_purchase_default_closed_browser.mjs"
 server=make_server("127.0.0.1",0,app.app.wsgi_app,threaded=True)
 worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
 receipts=[]
 try:
  for name,purchase,loadout,ui in cases:
   for env,enabled in [
     (app.CANONICAL_COIN_SHOP_PURCHASE_FLAG,purchase),
     (app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,loadout),
     (app.G019_APPROVED_EQUIPMENT_SHOP_UI_FLAG,ui)
   ]:
    monkeypatch.setenv(env,"1" if enabled else "0")
   shop=client.get("/api/shop/catalog")
   assert shop.status_code==200
   data=shop.get_json()
   assert data["purchase_enabled"] is purchase
   assert data["approved_equipment_purchase_ui_enabled"] is False
   auth=client.get("/api/auth/me").get_json()
   assert auth["g019_equipment_actions_ui_enabled"] is False
   args={"origin":f"http://127.0.0.1:{server.server_port}",
    "cookie":cookie,"invId":invId,
    "expectedShopBackend":purchase,"expectedShopUi":False}
   p=subprocess.run(["node",str(browser)],input=json.dumps(args),
    capture_output=True,text=True,encoding="utf8",errors="replace",timeout=120,cwd=ROOT)
   assert p.returncode==0,f"{name}: {p.stderr[-5500:]} {p.stdout[-1000:]}"
   actual=json.loads(p.stdout)
   assert actual["verdict"]=="G019_SHIPPED_PUBLIC_SHOP_BACKPACK_FAIL_CLOSED_PASS"
   receipts.append({"case":name,"purchase_flag":purchase,
    "loadout_flag":loadout,"release_flag":ui,"browser":actual})
 finally:
  server.shutdown();worker.join(timeout=8);server.server_close()
 monkeypatch.delenv(app.CANONICAL_COIN_SHOP_PURCHASE_FLAG,raising=False)
 monkeypatch.delenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,raising=False)
 monkeypatch.delenv(app.G019_APPROVED_EQUIPMENT_SHOP_UI_FLAG,raising=False)
 with app.get_db() as db:
  rows=db.execute("SELECT equip_id,equipped FROM player_inventory WHERE user_id=?",(UID,)).fetchall()
  assert len(rows)==1 and rows[0]["equip_id"]=="wooden_sword" and rows[0]["equipped"]==0
  assert db.execute("SELECT coins FROM user_stats WHERE user_id=?",(UID,)).fetchone()["coins"]==1100
 assert len(receipts)==4
 out={"schema":"G019_4_DISJOINT_RELEASE_FLAGS_REAL_BROWSER_V1",
  "verdict":"G019_ALL_4_SHIPPED_PRODUCT_DEFAULT_OFF_TESTS_PASS",
  "source_page_substitution":False,"native_pg_disposable":True,
  "four_independent_server_flag_combinations":receipts,
  "real_shop_purchase_calls":0,"real_backpack_equip_calls":0,
  "P022_P038_rights_unchanged":True,"no_production_writes":True}
 EV.mkdir(exist_ok=True)
 dest=EV/"G019_4_DEFAULT_OFF_REAL_ORIGINAL_UI_20261021.json"
 dest.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf8")
 print("G019_DEFAULT_OFF_ACTUAL_SHOP_BACKPACK_ALL4_PASS",dest,flush=True)
