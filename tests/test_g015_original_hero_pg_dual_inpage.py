"""Real authenticated synthetic PG Backpack UI -> dual-hand P038 GLB Hero
on current G009 shared rig, reload in different signed session.
This is an isolated nonrelease QA stream; it does NOT modify production Hero.
"""
from pathlib import Path
import json,os,subprocess,threading
from urllib.parse import unquote
from werkzeug.serving import make_server
from test_20261019_monthly_postgres import runtime,local_postgres
from test_20261020_g010_m3_shop_player_native_pg import _activate_preview_only_in_memory
from test_g014_p038_native_pg_offhand_dual import _source, _client
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_slot
ROOT=Path(__file__).resolve().parents[1]
EVID=Path(r"D:\go-odyssey-g010-3d-activation-evidence-20261021")
UID=983150
def _isolated_qa_wsgi(app):
 """Serve only three tightly allowlisted unreleased QA source paths on loopback.
 No user-controllable arbitrary filesystem or parent traversal.
 Otherwise delegate to actual Flask app without API mocking.
 """
 qa={
  "/tests/e2e/g015_p038_original_hero_qa.mjs":
    ROOT/"tests/e2e/g015_p038_original_hero_qa.mjs",
  "/docs/handoffs/G011_P022_P038_QA_MODEL_RECOVERY_20261021.json":
    ROOT/"docs/handoffs/G011_P022_P038_QA_MODEL_RECOVERY_20261021.json",
  "/tests/e2e/g011_private_qa_assets/lowpo_forging_hammer.glb":
    ROOT/"tests/e2e/g011_private_qa_assets/lowpo_forging_hammer.glb",
  "/tests/e2e/g011_private_qa_assets/lowpo_magic_wand.glb":
    ROOT/"tests/e2e/g011_private_qa_assets/lowpo_magic_wand.glb",
 }
 wrapped=_activate_preview_only_in_memory(app)
 def handle(env,start):
  path=env.get("PATH_INFO","")
  if path in qa:
   if env.get("REMOTE_ADDR") not in ("127.0.0.1","::1"):
    start("403 Forbidden",[("Content-Type","text/plain")])
    return [b"localhost only"]
   target=qa[path]
   if not target.is_file():
    start("404 Not Found",[("Content-Type","text/plain")])
    return [b"unavailable"]
   extension=target.suffix.lower()
   mime={".html":"text/html; charset=utf-8", ".mjs":"text/javascript; charset=utf-8",
     ".json":"application/json",
     ".glb":"model/gltf-binary"}[extension]
   blob=target.read_bytes()
   start("200 OK",[("Content-Type",mime),("Cache-Control","no-store"),
       ("Content-Length",str(len(blob)))])
   return [blob]
  return wrapped(env,start)
 return handle

def test_native_pg_backpack_main_shield_true_webgl_fresh_login(runtime,monkeypatch):
 app=runtime
 assert os.environ.get("PRODUCTION")!="1"
 assert app._equipment_canonical_loadout_enabled() is False
 assert app._canonical_coin_shop_purchase_enabled() is False
 entries=_source()
 assert len(entries)==12
 model=json.loads((ROOT/"docs/handoffs/G011_P022_P038_QA_MODEL_RECOVERY_20261021.json").read_text(encoding="utf8"))
 by_code={m["qa_id"]:m for m in model["models"]}
 synthetic=tuple(app.CANONICAL_EQUIPMENT_DEFS)+tuple(entries)
 monkeypatch.setattr(app,"CANONICAL_EQUIPMENT_DEFS",synthetic)
 monkeypatch.setattr(app,"_EQUIP_MAP",{x["id"]:x for x in synthetic})
 with app.get_db() as conn:
  upgrade_slot(conn,equipment_defs=synthetic)
  conn.execute("INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at) VALUES(?,?,?,?,?,?,?)",
   (UID,"g015-e2e-synthetic","G014 Synthetic","unused",0,"free","2026-10-21T00:00:00"))
  conn.execute("INSERT INTO user_stats(user_id,coins,rank_level,xp) VALUES(?,?,?,?)",
   (UID,932,"LV1",0))
  conn.execute("INSERT INTO player_appearance(user_id,character_key) VALUES(?,'apprentice')",(UID,))
  grants=[]
  for item in entries:
   r=app.grant_equipment_ownership(conn,UID,item["id"],"admin",equipment_defs=synthetic)
   assert not r.equipped
   q=by_code[item["qa_source_id"]]
   grants.append({"id":item["id"],"slot":item["slot"],"inv_id":r.row_id,
    "qa_id":q["qa_id"],"hand_slot":q["slot"],"sha":q["runtime_sha256"]})
 original=_client(app,UID,"g015-original")
 fresh=_client(app,UID,"g015-fresh-other-flask-session")
 assert original.get_cookie("session").value!=fresh.get_cookie("session").value
 inventory=original.get("/api/player/inventory").get_json()
 assert len([x for x in inventory if x["item_id"].startswith("g014_qa_")])==12
 blocked=original.post("/api/player/inventory/equip",json={
  "inv_id":grants[0]["inv_id"],"action":"equip"})
 assert blocked.status_code==409 and blocked.get_json()["error"]=="LOADOUT_DISABLED"
 assert original.get("/api/player/appearance").get_json()["character_key"]=="A1"
 monkeypatch.setenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,"1")
 manifest=json.loads((ROOT/"schemas/future30_c005_real_asset_runtime_mapping_manifest.json").read_text(encoding="utf8"))
 hero=next(x for x in manifest["visual_models"] if x["character_id"]=="A1" and x["variant"]=="RED")
 server=make_server("127.0.0.1",0,_isolated_qa_wsgi(app.app.wsgi_app),threaded=True)
 worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
 try:
  args={"origin":f"http://127.0.0.1:{server.server_port}",
   "cookie":original.get_cookie("session").value,
   "freshCookie":fresh.get_cookie("session").value,
   "heroGlb":"/"+hero["runtime_glb"],
   "entries":grants}
  process=subprocess.run(["node",str(ROOT/"tests/e2e/g015_original_hero_dual_pg_browser.mjs")],
   input=json.dumps(args),capture_output=True,text=True,errors="replace",
   encoding="utf8",cwd=ROOT,timeout=220,env={**os.environ,"GO_G010_M3_TOUCH":"0"})
  assert process.returncode==0,process.stdout[-2500:]+process.stderr[-5700:]
  out=json.loads(process.stdout)
  assert out["verdict"]=="G015_ORIGINAL_HERO_DUAL_P038_WEBGL_NATIVE_PG_RELOGIN_PASS"
  assert out["dualRenders"]==4 and len(out["results"])==4
  assert all(row["sameAuthenticatedServerInventory"] and row["originalG008Renderer"] and row["inOriginalHero"] and row["exactSourceManifest"] and len(row["attachedTwoRealGLBs"])==2 for row in out["results"])
  assert out["defaultOffVerified"] is True
  assert out["errorCount"]==0
 finally:
  server.shutdown();worker.join(timeout=8);server.server_close()
 with app.get_db() as conn:
  eq=conn.execute("SELECT equip_id,canonical_slot FROM player_inventory WHERE user_id=? AND equipped=1",(UID,)).fetchall()
  assert len(eq)==2 and {r["canonical_slot"] for r in eq}=={"weapon","offhand"}
  assert conn.execute("SELECT coins,xp FROM user_stats WHERE user_id=?",(UID,)).fetchone()["coins"]==932
  assert conn.execute("SELECT COUNT(*) AS n FROM currency_log WHERE user_id=? AND delta<0",(UID,)).fetchone()["n"]==0
 monkeypatch.delenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,raising=False)
 assert app._equipment_canonical_loadout_enabled() is False
 assert original.post("/api/player/inventory/equip",json={
  "inv_id":grants[0]["inv_id"],"action":"unequip"}).status_code==409
 report={"schema":"G015_NATIVE_PG_ORIGINAL_HERO_DUAL_V1",
  "verdict":out["verdict"],"source_model_count":12,
  "server_authority":True,"real_backpack_ui":True,
  "real_browser":"Chrome WebGL","two_main_two_shields":True,
  "two_independent_signed_sessions":True,"dual_render_count":4,
  "normal_original_hero_no_qa_displays_none":out["defaultOffVerified"],
  "original_hero_html_and_real_g008_canvas":True,
  "models_sha_checked":out["results"],
  "original_inpage_test_only_module":True,
  "equip_writes":4,"coins_before_after":932,
  "original_hero_release_build_contains_qa_assets":False,
  "can_buy_officially":False,"released":False,
  "legal_model_admission":False,"production_player_writes":False,
  "github_merge":False,"oracle_deploy":False}
 EVID.mkdir(exist_ok=True)
 dest=EVID/"G015_P038_ORIGINAL_HERO_PG_REAL_WEBGL_20261021.json"
 dest.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
 print("G015_ORIGINAL_HERO_DUAL_PG_PASS",dest,flush=True)
