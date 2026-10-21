"""G018: ALL thirteen P022 held objects (but zero arrows) in disposable native
PostgreSQL, original authenticated Backpack UI -> original /hero real WebGL.
No P022 canonical official definitions, purchase flags, licensing admission.
"""
from pathlib import Path
import os,json,subprocess,threading,hashlib
from werkzeug.serving import make_server
from test_20261019_monthly_postgres import runtime,local_postgres
from test_20261020_g010_m3_shop_player_native_pg import _activate_preview_only_in_memory
from test_g014_p038_native_pg_offhand_dual import _client
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_slot
ROOT=Path(__file__).resolve().parents[1]
EV=Path(r"D:\go-odyssey-g010-3d-activation-evidence-20261021")
SYNTHETIC_UID=983160
OTHER_UID=983161
MANIFEST=ROOT/"docs/handoffs/G017_P022_16_QA_SOURCE_AND_ATTACHMENT_20261021.json"
def catalog():
 m=json.loads(MANIFEST.read_text(encoding="utf8"))
 assert m["release_status"]=="NOT_ADMITTED" and m["total"]==16
 handheld=[x for x in m["models"] if x["functional_class"]=="MAIN_HAND_STATIC_QA"]
 projectiles=[x for x in m["models"] if x["functional_class"]=="PROJECTILE_PROP_ONLY"]
 assert len(handheld)==13 and len(projectiles)==3
 assert all(not x["shop_enabled"] and not x["equip_enabled"]
   and x["formal_item_id"] is None and not x["legal_admission_proven"] for x in m["models"])
 definitions=[]
 for x in handheld:
  path=ROOT/x["runtime_glb"]
  assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==x["runtime_sha256"]
  definitions.append({
    "id":"g018_qa_"+x["code"].lower().replace("-","_"),
    "name":"QA P022 NONRELEASE "+x["name"],"slot":"weapon",
    "rarity":"common","icon":"🧪","desc":"Synthetic test fixture, NOT_ADMITTED",
    "effects":{},"qa_source_id":x["qa_id"],
    "qa_sha":x["runtime_sha256"],"release_admitted":False})
 assert len({x["id"] for x in definitions})==13
 assert set(x["id"] for x in definitions).isdisjoint(
    {"g018_qa_"+x["code"].lower().replace("-","_") for x in projectiles})
 return definitions,handheld,projectiles
def _qa_wsgi(app,source):
 """EXACT local-only allowlist; no path prefix catch-all, no real origin writes."""
 qa={
  "/tests/e2e/g018_p022_original_hero_qa.mjs":
     ROOT/"tests/e2e/g018_p022_original_hero_qa.mjs",
  "/docs/handoffs/G017_P022_16_QA_SOURCE_AND_ATTACHMENT_20261021.json":MANIFEST,
 }
 for x in source:
  route="/"+x["runtime_glb"]
  assert route not in qa
  qa[route]=ROOT/x["runtime_glb"]
 wrapped=_activate_preview_only_in_memory(app)
 def handler(env,start):
  path=env.get("PATH_INFO","")
  if path in qa:
   if env.get("REMOTE_ADDR") not in ("127.0.0.1","::1"):
    start("403 Forbidden",[("Content-Type","text/plain")])
    return [b"loopback only"]
   candidate=qa[path]
   if not candidate.is_file():
    start("404 Not Found",[("Content-Type","text/plain")])
    return [b"missing exact fixture"]
   blob=candidate.read_bytes()
   suffix=candidate.suffix.lower()
   mime={".mjs":"text/javascript; charset=utf-8",
    ".json":"application/json",".glb":"model/gltf-binary"}[suffix]
   start("200 OK",[("Content-Type",mime),("Content-Length",str(len(blob))),
     ("Cache-Control","no-store"),("X-Content-Type-Options","nosniff")])
   return [blob]
  return wrapped(env,start)
 return handler

def test_g018_all_13_P022_native_pg_backpack_original_hero_webgl(runtime,monkeypatch):
 app=runtime
 assert os.environ.get("PRODUCTION")!="1"
 assert app._equipment_canonical_loadout_enabled() is False
 assert app._canonical_coin_shop_purchase_enabled() is False
 assert not any(x["id"].startswith("g018_qa_") for x in app.CANONICAL_EQUIPMENT_DEFS)
 entries,handheld,arrows=catalog()
 original_defs=app.CANONICAL_EQUIPMENT_DEFS
 synthetic=tuple(original_defs)+tuple(entries)
 monkeypatch.setattr(app,"CANONICAL_EQUIPMENT_DEFS",synthetic)
 monkeypatch.setattr(app,"_EQUIP_MAP",{x["id"]:x for x in synthetic})
 with app.get_db() as db:
  upgrade_slot(db,equipment_defs=synthetic)
  for uid in [SYNTHETIC_UID,OTHER_UID]:
   db.execute("INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at) VALUES(?,?,?,?,?,?,?)",
    (uid,f"g018-isolated-{uid}","G018 disposable","unused",0,"free","2026-10-21T00:00:00"))
   db.execute("INSERT INTO user_stats(user_id,coins,rank_level,xp) VALUES(?,?,?,?)",
    (uid,1049,"LV1",0))
   db.execute("INSERT INTO player_appearance(user_id,character_key) VALUES(?,'apprentice')",(uid,))
  by={x["qa_source_id"]:x for x in entries}
  grants=[]
  for item in handheld:
   definition=by[item["qa_id"]]
   row=app.grant_equipment_ownership(db,SYNTHETIC_UID,definition["id"],"admin",
     equipment_defs=synthetic)
   assert not row.equipped
   grants.append({"id":definition["id"],"inv_id":row.row_id,
     "qa_id":item["qa_id"],"code":item["code"],
     "sha":item["runtime_sha256"],"slot":"weapon"})
 owner=_client(app,SYNTHETIC_UID,"g018-owner")
 fresh=_client(app,SYNTHETIC_UID,"g018-independent-flask-session")
 other=_client(app,OTHER_UID,"g018-intruder")
 assert owner.get_cookie("session").value!=fresh.get_cookie("session").value
 iv=owner.get("/api/player/inventory").get_json()
 assert len([x for x in iv if x["item_id"].startswith("g018_qa_")])==13
 assert all(x["canonical_equippable"] is True for x in iv if x["item_id"].startswith("g018_qa_"))
 assert owner.get("/api/player/appearance").get_json()["character_key"]=="A1"
 assert other.post("/api/player/inventory/equip",json={
  "inv_id":grants[0]["inv_id"],"action":"equip"}).status_code==404
 r=owner.post("/api/player/inventory/equip",json={
  "inv_id":grants[0]["inv_id"],"action":"equip"})
 assert r.status_code==409 and r.get_json()["error"]=="LOADOUT_DISABLED"
 for arrow in arrows:
  arrow_id="g018_qa_"+arrow["code"].lower().replace("-","_")
  assert arrow_id not in {x["id"] for x in entries}
  assert not any(x["item_id"]==arrow_id for x in iv)
 monkeypatch.setenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,"1")
 server=make_server("127.0.0.1",0,_qa_wsgi(app.app.wsgi_app,
   json.loads(MANIFEST.read_text(encoding="utf8"))["models"]),threaded=True)
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  command=["node",str(ROOT/"tests/e2e/g018_p022_13_original_hero_pg_browser.mjs")]
  args={"origin":f"http://127.0.0.1:{server.server_port}",
   "cookie":owner.get_cookie("session").value,
   "freshCookie":fresh.get_cookie("session").value,
   "entries":grants,"projectiles":[x["code"] for x in arrows]}
  p=subprocess.run(command,input=json.dumps(args),capture_output=True,
   text=True,encoding="utf8",errors="replace",cwd=ROOT,timeout=280,
   env={**os.environ,"GO_G010_M3_TOUCH":"0"})
  assert p.returncode==0, p.stdout[-2000:]+p.stderr[-6700:]
  proof=json.loads(p.stdout)
  assert proof["verdict"]=="G018_P022_13_ORIGINAL_HERO_NATIVE_PG_ALL_RELOGIN_PASS"
  assert proof["realBackpackEquipPOST"]==13
  assert proof["originalHeroWebGL"]==13
  assert proof["independentFreshSignedSessions"]==3
  assert proof["defaultOffVerified"] is True
  assert proof["projectilesExcluded"]==3
  assert len(proof["renders"])==13 and len(proof["relogins"])==3
  assert all(x["heroIsOriginal"] and x["serverAuthoritative"] for x in proof["renders"])
  assert proof["errors"]==[]
 finally:
  server.shutdown();thread.join(timeout=8);server.server_close()
 with app.get_db() as db:
  rows=db.execute("SELECT equip_id,canonical_slot FROM player_inventory WHERE user_id=? AND equipped=1",
   (SYNTHETIC_UID,)).fetchall()
  assert len(rows)==1 and rows[0]["canonical_slot"]=="weapon"
  assert rows[0]["equip_id"]==grants[-1]["id"]
  count=db.execute("SELECT COUNT(*) AS n FROM player_inventory WHERE user_id=?",
    (SYNTHETIC_UID,)).fetchone()["n"]
  assert count==13
  assert db.execute("SELECT coins FROM user_stats WHERE user_id=?",
    (SYNTHETIC_UID,)).fetchone()["coins"]==1049
  assert db.execute("SELECT COUNT(*) AS n FROM currency_log WHERE user_id=? AND delta<0",
    (SYNTHETIC_UID,)).fetchone()["n"]==0
  assert db.execute("SELECT COUNT(*) AS n FROM player_inventory WHERE user_id=?",
    (OTHER_UID,)).fetchone()["n"]==0
 monkeypatch.delenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,raising=False)
 assert app._equipment_canonical_loadout_enabled() is False
 assert owner.post("/api/player/inventory/equip",json={
  "inv_id":grants[-1]["inv_id"],"action":"unequip"}).status_code==409
 out={"schema":"G018_P022_13_ORIGINAL_HERO_REAL_PG_V1",
  "verdict":proof["verdict"],"source_P022_model_count":16,
  "canonical_QA_handheld_only":13,"arrows_not_items":3,
  "real_backpack_equip_writes":13,"real_original_Hero_3d":13,
  "fresh_flask_session_relogin":3,"default_nonQA_page_fail_closed":True,
  "owned_rows":13,"native_pg_disposable":True,
  "no_player_currency_debit":True,"initial_loadout_off_409":True,
  "after_loadout_off_409":True,"other_player_404":True,
  "no_product_catalog_defs":True,"license_release_admitted":False,
  "two_hand_ik_certified":False,"arrow_projectile_firing_certified":False,
  "shop_purchases":0,"formal_player_data":False,
  "go_merge":False,"go_deploy":False,
  "browser_proof":proof}
 EV.mkdir(exist_ok=True)
 destination=EV/"G018_P022_13_NATIVE_PG_ORIGINAL_HERO_20261021.json"
 destination.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf8")
 print("G018_13_ORIGINAL_HERO_REAL_PG_PASS",destination,flush=True)
