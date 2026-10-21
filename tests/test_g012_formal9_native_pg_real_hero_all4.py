"""G012: genuine server-authoritative synthetic inventory and G008 real-GLB
3D Hero for every Formal9 rights-cleared NOT-ADMITTED replacement weapon.
No Shop/Release/Production authority is granted; credits are not debited.
"""
import json,os,subprocess,threading
from pathlib import Path
from werkzeug.serving import make_server
from test_20261019_monthly_postgres import runtime,local_postgres
from test_20261020_g010_m3_shop_player_native_pg import _activate_preview_only_in_memory
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_slot

ROOT=Path(__file__).resolve().parents[1]
EVID=Path(r"D:\go-odyssey-g010-3d-activation-evidence-20261021")
USER=983120
SECOND_USER=983121
def test_all_four_rights_cleared_formal9_synthetic_owned_3d_relogin(runtime,monkeypatch):
 app=runtime
 assert os.environ.get("PRODUCTION")!="1"
 assert app._canonical_coin_shop_purchase_enabled() is False
 assert app._equipment_canonical_loadout_enabled() is False
 rights=json.loads((ROOT/"schemas/g009_formal9_rights_cleared_replacement_v1.json").read_text(encoding="utf8"))
 assert len(rights["items"])==4
 assert rights["rights"]["RIGHTS_STATUS"]=="RIGHTS_CLEARED"
 assert rights["release_eligibility_value"]=="RIGHTS_CLEARED_RELEASE_NOT_ADMITTED"
 for k in ("RELEASE_ENABLED","EQUIP_ENABLED","PURCHASE_ENABLED","PRODUCTION_ASSET_ADMISSION"):
  assert rights["rights"][k] is False,k
 with app.get_db() as conn:
  upgrade_slot(conn,equipment_defs=app.CANONICAL_EQUIPMENT_DEFS)
  for uid in (USER,SECOND_USER):
   conn.execute("INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at) VALUES(?,?,?,?,?,?,?)",
    (uid,f"g012-only-{uid}","G012 Synthetic","unused",0,"free","2026-10-21T00:00:00"))
   conn.execute("INSERT INTO user_stats(user_id,coins,rank_level,xp) VALUES(?,?,?,?)",
    (uid,777,"LV1",0))
   conn.execute("INSERT INTO player_appearance(user_id,character_key) VALUES(?,'apprentice')",(uid,))
  received=[]
  for row in rights["items"]:
   assert row["slot"]=="MAIN_HAND" and row["socket"]=="hand.R"
   result=app.grant_equipment_ownership(conn,USER,row["server_item_id"],"admin",
    equipment_defs=app.CANONICAL_EQUIPMENT_DEFS)
   assert result.equipped is False
   received.append({"item_id":row["server_item_id"],"asset_id":row["asset_id"],
     "runtime_sha256":row["runtime_sha256"],"runtime_asset":row["runtime_asset"],
     "inv_id":result.row_id})
 def new_client(uid=USER,mark=""):
  c=app.app.test_client()
  with c.session_transaction() as session:
   session["user_id"]=uid
   session["username"]=f"g012-only-{uid}"
   session["independent_session_marker"]=mark
  return c
 c=new_client(mark="original")
 fresh=new_client(mark="fresh-independently-signed")
 assert c.get_cookie("session").value!=fresh.get_cookie("session").value
 stranger=new_client(uid=SECOND_USER,mark="different-player")
 assert c.get("/api/player/appearance").get_json()["character_entitled"] is True
 assert c.get("/api/player/appearance").get_json()["character_key"]=="A1"
 initial=c.get("/api/player/inventory").get_json()
 assert len([x for x in initial if x.get("item_id") in {r["server_item_id"] for r in rights["items"]}])==4
 assert not any(x["equipped"] for x in initial if x.get("item_id") in {r["server_item_id"] for r in rights["items"]})
 before=c.post("/api/player/inventory/equip",json={"inv_id":received[0]["inv_id"],"action":"equip"})
 assert before.status_code==409 and before.get_json()["error"]=="LOADOUT_DISABLED"
 assert stranger.post("/api/player/inventory/equip",json={
  "inv_id":received[0]["inv_id"],"action":"equip"}).status_code==404
 monkeypatch.setenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,"1")
 assert app._canonical_coin_shop_purchase_enabled() is False
 server=make_server("127.0.0.1",0,
  _activate_preview_only_in_memory(app.app.wsgi_app),threaded=True)
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  payload={"origin":f"http://127.0.0.1:{server.server_port}",
    "sessionCookie":c.get_cookie("session").value,
    "secondSessionCookie":fresh.get_cookie("session").value,
    "items":received}
  process=subprocess.run(["node",str(ROOT/"tests/e2e/g012_formal9_true_player_3d_browser.mjs")],
   input=json.dumps(payload),capture_output=True,text=True,encoding="utf8",errors="replace",
   cwd=ROOT,timeout=280,env={**os.environ,"GO_G010_M3_TOUCH":"0"})
  assert process.returncode==0,process.stdout[-2800:]+process.stderr[-6200:]
  data=json.loads(process.stdout)
  assert data["verdict"]=="G012_FORMAL9_4_REAL_PG_HERO_WEBGL_RELOGIN_PASS"
  assert len(data["cases"])==4
  assert data["postEquipCount"]==4 and data["shopPurchases"]==0
  assert [case["item_id"] for case in data["cases"]]==[r["item_id"] for r in received]
  assert all(case["relogin"] and case["rendered3d"] for case in data["cases"])
 finally:
  server.shutdown();thread.join(timeout=8);server.server_close()
 with app.get_db() as conn:
  all_rows=conn.execute("SELECT id,equip_id,equipped,canonical_slot FROM player_inventory WHERE user_id=?",(USER,)).fetchall()
  assert len(all_rows)==4
  assert sum(int(x["equipped"]) for x in all_rows)==1
  assert next(x["equip_id"] for x in all_rows if x["equipped"])=="bamboo_shadow_blade"
  assert all(x["canonical_slot"]=="weapon" for x in all_rows)
  assert conn.execute("SELECT COUNT(*) AS n FROM player_inventory WHERE user_id=?",(SECOND_USER,)).fetchone()["n"]==0
  assert conn.execute("SELECT coins,xp FROM user_stats WHERE user_id=?",(USER,)).fetchone()["coins"]==777
  assert conn.execute("SELECT COUNT(*) AS n FROM currency_log WHERE user_id=? AND delta<0",(USER,)).fetchone()["n"]==0
 assert stranger.post("/api/player/inventory/equip",json={"inv_id":received[0]["inv_id"],"action":"equip"}).status_code==404
 monkeypatch.delenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,raising=False)
 assert app._equipment_canonical_loadout_enabled() is False
 assert app._canonical_coin_shop_purchase_enabled() is False
 assert c.post("/api/player/inventory/equip",json={"inv_id":received[0]["inv_id"],"action":"equip"}).status_code==409
 output={"schema":"G012_FORMAL9_4_PLAYER_TRUE_3D_NATIVE_PG_V1",
  "verdict":data["verdict"],"rights":"CC0-1.0_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED",
  "new_disposable_pg":True,"qa_grants":4,"shop_buys":0,
  "coins_unchanged":777,"unauthorized_user_rejected":True,"default_off_rejected":True,
  "after_test_default_off":True,"real_chrome_webgl":True,
  "model_sha_verified":4,"fresh_session_3d":4,"unique_equip_writer_calls":4,
  "server_exact_single_equipped":True,"cases":data["cases"],
  "page_errors":data["browserErrors"],"api_errors":data["httpErrors"],
  "production_admission":False,"go_merge":False,"go_deploy":False,
  "formal_player_writes":False}
 EVID.mkdir(exist_ok=True)
 out=EVID/"G012_FORMAL9_ALL4_NATIVE_PG_TRUE_HERO_20261021.json"
 out.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf8")
 print("G012_FORMAL9_4_TRUE_HERO_PG_PASS",str(out),flush=True)
