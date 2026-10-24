"""G011 unique stage goal: PG-owned Shop purchase + Backpack Equip -> genuine
3D Hero hand.R GLB and a second independent login. Only disposable native PG.
The historical M3 reward/shop tests are not rerun; this adds NEW real Hero GLB proof.
"""
from pathlib import Path
import json,subprocess,threading,os
from werkzeug.serving import make_server
from test_20261019_monthly_postgres import runtime, local_postgres
from test_20261020_g010_m3_shop_player_native_pg import _activate_preview_only_in_memory
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_coin
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_slot
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
USER=983011
BASE=Path(__file__).resolve().parents[1]
def _receipt_path(tmp_path, filename):
 root=Path(os.environ.get("GO_E2E_EVIDENCE_ROOT") or tmp_path)
 if "GO_E2E_EVIDENCE_ROOT" in os.environ:
  assert root.is_absolute() and root.drive.upper()=="D:", "Evidence root must be isolated on D:"
  assert "go-odyssey-g010-3d-activation-evidence-20261021" not in str(root).lower(), "Refuse historical receipt overwrite"
 root.mkdir(parents=True,exist_ok=True)
 return root/filename

def client(app):
 c=app.app.test_client()
 with c.session_transaction() as s:
  s["user_id"]=USER;s["username"]="g011-synthetic-hero-e2e"
 return c
def test_real_pg_player_ui_shop_to_3d_hero_persists_on_fresh_session(runtime,monkeypatch,tmp_path):
 app=runtime
 assert os.environ.get("PRODUCTION")!="1"
 assert app._canonical_coin_shop_purchase_enabled() is False
 assert app._equipment_canonical_loadout_enabled() is False
 with app.get_db() as conn:
  upgrade_coin(conn)
  upgrade_outbox(conn)
  upgrade_slot(conn,equipment_defs=app.EQUIPMENT_DEFS)
  conn.execute("INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at) VALUES(?,?,?,?,?,?,?)",
   (USER,"g011-synthetic-hero-e2e","G011 Synthetic","unused",0,"free","2026-10-21T00:00:00"))
  conn.execute("INSERT INTO user_stats(user_id,coins,rank_level,xp) VALUES(?,?,?,?)",
   (USER,1000,"LV1",0))
  conn.execute("INSERT INTO player_appearance(user_id,character_key) VALUES(?,'apprentice')",(USER,))
 c=client(app)
 no_buy=c.post("/api/shop/buy",json={"item_key":"wooden_sword",
  "purchase_operation_id":"g011-disabled-rejected"})
 assert no_buy.status_code==409 and no_buy.get_json()["code"]=="SHOP_PURCHASE_DISABLED"
 with app.get_db() as conn:
  assert conn.execute("SELECT coins FROM user_stats WHERE user_id=?",(USER,)).fetchone()["coins"]==1000
 # Resolve REAL character from server rather than forging a glTF identity.
 cat=c.get("/api/player/character-catalog")
 appearance=c.get("/api/player/appearance")
 assert cat.status_code==200,(cat.status_code,cat.get_json())
 assert appearance.status_code==200,(appearance.status_code,appearance.get_json())
 identity=appearance.get_json()
 assert identity["character_key"]=="A1" and identity["character_entitled"] is True,identity
 assert identity["character_runtime"]["runtime_glb"].startswith("assets/3d_shop/")
 monkeypatch.setenv(app.CANONICAL_COIN_SHOP_PURCHASE_FLAG,"1")
 monkeypatch.setenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,"1")
 offer=next(x for x in c.get("/api/shop/catalog").get_json()["equipment_offers"]
  if x["item_id"]=="wooden_sword")
 assert offer["price"]==300
 cookie=c.get_cookie("session").value
 new_cookie=client(app).get_cookie("session").value
 server=make_server("127.0.0.1",0,
  _activate_preview_only_in_memory(app.app.wsgi_app),threaded=True)
 thread=threading.Thread(target=server.serve_forever,daemon=True)
 thread.start()
 try:
  input_data={"origin":f"http://127.0.0.1:{server.server_port}",
   "sessionCookie":cookie,"reloginCookie":new_cookie,
   "offerId":offer["offer_id"],"itemId":"wooden_sword",
   "price":300,"startingCoins":1000}
  proc=subprocess.run(["node",str(BASE/"tests/e2e/g085f_real_pg_hero_loading_failure_retry.mjs")],
   input=json.dumps(input_data),capture_output=True,text=True,encoding="utf8",
   errors="replace",cwd=BASE,timeout=180,env={**os.environ,"GO_G010_M3_TOUCH":
       "1" if os.environ.get("GO_G085G_TOUCH")=="1" else "0"})
  assert proc.returncode==0,proc.stdout[-1800:]+proc.stderr[-4800:]
  proof=json.loads(proc.stdout)

  ux=proof.get("uxEvidence")
  assert ux and ux["loading"]["shown"]
  assert ux["initialReady"]["noticeHidden"]
  assert ux["failedClosed"]["equipmentStatus"]=="unavailable"
  assert ux["failedClosed"]["retryVisible"]
  assert ux["retryRecovered"]["noticeHidden"]
  assert ux["isolatedTransient503InjectedOnce"] is True
  assert ux["retryTouchTarget"]["height"] >= 44
  assert ux["retryTouchTarget"]["width"] >= 44
  assert ux["lateRegistrationPending"]["equipmentStatus"] == "pending"
  assert ux["lateRegistrationRecovered"]["equipmentStatus"] == "ready"
  assert ux["persistentOutage"]["equipmentStatus"] == "unavailable"
  assert ux["persistentOutage"]["inventoryFailures"] >= 2
  assert ux["persistentOutage"]["hand"] is None
  evidence=Path(os.environ.get("G085F_RECEIPT_ROOT") or tmp_path)
  evidence.mkdir(parents=True,exist_ok=True)
  with (evidence/"G085F_3D_HERO_LOADING_FAILCLOSED_RETRY_RECEIPT.json").open("x",encoding="utf8") as f:
   f.write(json.dumps({"schema":"G085F_REAL_PG_HERO_LOADING_RETRY",
     "ux":ux,"trueHero":proof["hero"],"freshHero":proof["freshHero"],
     "browserWrites":proof["writes"],"noProductionData":True,
     "testOnlyFailureInjection":True},ensure_ascii=False,indent=2))
  assert proof["verdict"]=="G011_REAL_PG_PURCHASE_EQUIP_TRUE_HERO_GL_B_RELOGIN_PASS"
  assert proof["writes"]==["POST /api/shop/buy","POST /api/player/inventory/equip"]
  assert proof["hero"]["diagnostics"]["slots"][3]["presentation_id"]=="WEAPON_628812E9B559"
  assert proof["freshHero"]["diagnostics"]["slots"][3]["presentation_id"]=="WEAPON_628812E9B559"
 finally:
  server.shutdown();thread.join(timeout=8);server.server_close()
 with app.get_db() as conn:
  balance=conn.execute("SELECT coins,xp FROM user_stats WHERE user_id=?",(USER,)).fetchone()
  assert balance["coins"]==700 and balance["xp"]==0
  inv=conn.execute("SELECT id,equip_id,equipped,source FROM player_inventory WHERE user_id=?",(USER,)).fetchall()
  assert len(inv)==1 and inv[0]["equip_id"]=="wooden_sword" and inv[0]["equipped"]==1
  assert conn.execute("SELECT COUNT(*) n FROM coin_purchase_operations WHERE user_id=?",(USER,)).fetchone()["n"]==1
  assert conn.execute("SELECT COUNT(*) n FROM currency_log WHERE user_id=? AND delta<0",(USER,)).fetchone()["n"]==1
 again=client(app)
 assert again.get("/api/shop/catalog").get_json()["coins"]==700
 assert next(x for x in again.get("/api/player/inventory").get_json() if x["item_id"]=="wooden_sword")["equipped"] is True
 monkeypatch.delenv(app.CANONICAL_COIN_SHOP_PURCHASE_FLAG,raising=False)
 monkeypatch.delenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,raising=False)
 assert app._canonical_coin_shop_purchase_enabled() is False
 assert app._equipment_canonical_loadout_enabled() is False
 # Only serializable evidence without session cookies, secrets or raw account info.
 record={"schema":"G011_REAL_NATIVE_PG_HERO_3D_CLOSED_LOOP_V1",
  "verdict":"G011_REAL_PG_PURCHASE_EQUIP_3D_FRESH_SESSION_PASS",
  "git_baseline":"c3428ae0eda3d9cca89f22e825450aae93880e97",
  "pg_type":"fresh_disposable_native_postgresql",
  "browser":"real_Chrome_software_WebGL",
  "sale":{"shop_server_enabled_in_sandbox_only":True,"purchase_count":1,
   "price":300,"coins_start":1000,"coins_end":700,
   "rejected_when_flag_off":True,"currency_debit_rows":1},
  "equipment":{"item":"wooden_sword","server_owned":True,"equipped":True,
   "right_hand_webgl_presentation_id":"WEAPON_628812E9B559",
   "hero_3d_attached_after_buy":True,"fresh_session_3d_attached":True,
   "fresh_session_inventory_equipped":True},
  "browser_writes":proof["writes"],"browser_page_errors":proof["pageErrors"],
  "browser_response_errors":proof["responseErrors"],
  "production_release_rights_admitted":False,
  "environment_restored_shop_off":True,"environment_restored_loadout_off":True,
  "formal_player_writes":False,"oracle_deploy":False,"github_merge":False}
 dest=_receipt_path(tmp_path,"G011_REAL_PG_SHOP_EQUIP_HERO_3D_20261024.json")
 with dest.open("x",encoding="utf8") as output:
  output.write(json.dumps(record,ensure_ascii=False,indent=2))
 print("G011_REAL_PG_HERO_3D_STAGE_PASS",dest,flush=True)
