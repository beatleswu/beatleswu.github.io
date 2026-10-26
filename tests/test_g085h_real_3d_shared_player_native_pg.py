"""G085H: unified G008/G009 server-owned 3D across Hero Backpack and Shop.

Unmodified Flask game APIs, fresh disposable *native PostgreSQL* and real Chrome.
Bamboo has Owner-authorized preview GLB; Cloth Robe deliberately does not.
This is a VISUAL preview contract, not production asset admission or enablement.
"""
import json,os,subprocess,threading,hashlib,tempfile
from pathlib import Path
from werkzeug.serving import make_server
from test_20261019_monthly_postgres import runtime,local_postgres
from test_20261020_g010_m3_shop_player_native_pg import _activate_preview_only_in_memory
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_slot

ROOT=Path(__file__).resolve().parents[1]
USER=983585
def test_shared_g008_g009_backpack_shop_real3d_server_only(runtime,monkeypatch,tmp_path):
 app=runtime
 assert os.environ.get("PRODUCTION")!="1"
 assert not app._canonical_coin_shop_purchase_enabled()
 assert not app._equipment_canonical_loadout_enabled()
 rights=json.loads((ROOT/"schemas/g009_formal9_rights_cleared_replacement_v1.json")
                  .read_text(encoding="utf8"))
 assert rights["rights"]["PUBLIC_3D_PREVIEW_ADMITTED"] is True
 assert rights["rights"]["PRODUCTION_ASSET_ADMISSION"] is False
 bamboo=next(row for row in rights["items"] if row["server_item_id"]=="bamboo_shadow_blade")
 with app.get_db() as conn:
  upgrade_slot(conn,equipment_defs=app.CANONICAL_EQUIPMENT_DEFS)
  conn.execute("INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at) VALUES(?,?,?,?,?,?,?)",
    (USER,"g085h-3d-preview-only","3D Preview Test","unused",0,"free","2026-10-24T00:00:00"))
  conn.execute("INSERT INTO user_stats(user_id,coins,rank_level,xp) VALUES(?,?,?,?)",
    (USER,777,"LV1",0))
  conn.execute("INSERT INTO player_appearance(user_id,character_key) VALUES(?,'apprentice')",(USER,))
  blade=app.grant_equipment_ownership(conn,USER,"bamboo_shadow_blade",
    "adventure_first_clear",equipment_defs=app.CANONICAL_EQUIPMENT_DEFS)
  robe=app.grant_equipment_ownership(conn,USER,"cloth_robe",
    "adventure_first_clear",equipment_defs=app.CANONICAL_EQUIPMENT_DEFS)
  assert not blade.equipped and not robe.equipped
 monkeypatch.setenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,"1")
 def client():
  c=app.app.test_client()
  with c.session_transaction() as sess:
   sess["user_id"]=USER;sess["username"]="g085h-3d-preview-only"
  return c
 c=client()
 fresh=client()
 with fresh.session_transaction() as sess:
  sess["g085i_independent_fresh_session"]="distinct signed browser context"
 assert c.get_cookie("session").value != fresh.get_cookie("session").value
 assert c.get("/api/player/appearance").get_json()["character_entitled"] is True
 outcome=c.post("/api/player/inventory/equip",json={"inv_id":blade.row_id,"action":"equip"})
 assert outcome.status_code==200,outcome.get_json()
 assert outcome.get_json()["equipped"] is True
 monkeypatch.delenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,raising=False)
 assert not app._equipment_canonical_loadout_enabled()
 source=c.get("/api/player/inventory").get_json()
 assert next(x for x in source if x["item_id"]=="bamboo_shadow_blade")["equipped"] is True
 assert next(x for x in source if x["item_id"]=="cloth_robe")["equipped"] is False
 with app.get_db() as conn:
  before=[
    tuple(row) for row in conn.execute("SELECT equip_id,equipped,canonical_slot,source "
       "FROM player_inventory WHERE user_id=? ORDER BY equip_id",(USER,)).fetchall()
  ]
  initial_coins=int(conn.execute("SELECT coins FROM user_stats WHERE user_id=?",(USER,)).fetchone()["coins"])
  debit_count=int(conn.execute("SELECT COUNT(*) n FROM currency_log WHERE user_id=? AND delta<0",
      (USER,)).fetchone()["n"])
 assert initial_coins==777 and debit_count==0
 # Independent original test must be repeatable without overwriting any
 # existing evidence; mkdtemp atomically allocates a fresh isolated receipt.
 artifact_parent=Path(r"D:\g079-artifacts")
 assert artifact_parent.is_dir(),"Existing QA artifacts root required"
 artifacts=Path(tempfile.mkdtemp(prefix="g085i-native-pg-3d-",dir=artifact_parent))
 assert artifacts.parent.resolve()==artifact_parent.resolve()
 server=make_server("127.0.0.1",0,
   _activate_preview_only_in_memory(app.app.wsgi_app),threaded=True)
 thread=threading.Thread(target=server.serve_forever,daemon=True)
 thread.start()
 evidence=None
 try:
  payload={"origin":f"http://127.0.0.1:{server.server_port}",
   "sessionCookie":c.get_cookie("session").value,
   "freshSessionCookie":fresh.get_cookie("session").value,
   "bambooInvId":blade.row_id,"clothInvId":robe.row_id,
   "bambooAssetId":bamboo["asset_id"]}
  cmd=["node",str(ROOT/"tests/e2e/g085h_shared_hero_backpack_shop_browser.mjs")]
  run=subprocess.run(cmd,cwd=ROOT,input=json.dumps(payload),text=True,
    capture_output=True,encoding="utf8",errors="replace",timeout=280,
    env={**os.environ,"G085H_EVIDENCE_ROOT":str(artifacts)})
  (artifacts/"browser.log").write_text(run.stdout+"\n"+run.stderr,encoding="utf8")
  assert run.returncode==0,run.stdout[-1600:]+run.stderr[-6200:]
  evidence=json.loads(run.stdout.strip())
  assert evidence["verdict"]=="G085H_SHARED_G008_G009_BACKPACK_SHOP_REAL_CHROME_PG_PASS"
  assert evidence["backpack"]["main_hand_id"]==bamboo["asset_id"]
  assert evidence["afterReload"]["main_hand_id"]==bamboo["asset_id"]
  assert evidence["cloth"]["status"]=="unsupported"
  assert evidence["shop"]["visual_only"] is True
  assert evidence["shop"]["clothUnavailableNoFake"] is True
  assert len(evidence["shop"]["allFourExactMappedPreview"]) == 4
  assert all(entry["child_count"] == 1
             for entry in evidence["shop"]["allFourExactMappedPreview"])
  assert evidence["freshContextAfterRelogin"]["main_hand_id"]==bamboo["asset_id"]
  assert evidence["freshContextAfterRelogin"]["main_hand_child_count"]==1
  assert evidence["apiWrites"]==[]
 finally:
  server.shutdown();thread.join(timeout=10);server.server_close()
 with app.get_db() as conn:
  after=[
    tuple(row)for row in conn.execute("SELECT equip_id,equipped,canonical_slot,source "
      "FROM player_inventory WHERE user_id=? ORDER BY equip_id",(USER,)).fetchall()
  ]
  assert after==before
  assert int(conn.execute("SELECT coins FROM user_stats WHERE user_id=?",(USER,)).fetchone()["coins"])==777
  assert int(conn.execute("SELECT COUNT(*) n FROM currency_log WHERE user_id=? AND delta<0",
    (USER,)).fetchone()["n"])==0
 assert not app._canonical_coin_shop_purchase_enabled()
 assert not app._equipment_canonical_loadout_enabled()
 record={"schema":"G085H_REAL_CHROME_TRUE_PG_SHARED_HERO_BACKPACK_SHOP",
 "git_source":subprocess.check_output(["git","rev-parse","HEAD"],
    cwd=ROOT,text=True,encoding="utf8").strip(),
 "disposable_native_pg":True,"synthetic_grants":2,
 "bamboo_asset":bamboo["asset_id"],"bamboo_sha_authority":bamboo["runtime_sha256"],
 "cloth_robe_3d_status":"UNMAPPED_CLEARLY_DISCLOSED",
 "browser":evidence,"coins_before":777,"coins_after":777,
 "inventory_snapshot_unchanged":True,"no_purchase_or_equip_during_previews":True,
 "production_admission":False,"formal_merge":False,"deploy":False}
 result=artifacts/"G085H_REAL_3D_CHROME_POSTGRES_PLAYER_RECEIPT.json"
 result.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf8")
 print("G085H_REAL_PG_3D_PLAYER_LOOP_PASS",str(result),flush=True)
