"""G014 sandbox-only P038 offhand: native PG 8 mainhand x 4 shield ownership.
No P038 item is admitted to the Product catalog. All ephemeral definitions are
monkeypatched only inside disposable PostgreSQL pytest and removed afterwards.
"""
from pathlib import Path
import json,os
import pytest
from test_20261019_monthly_postgres import runtime,local_postgres
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_slot,CANONICAL_SLOTS
BASE=Path(__file__).resolve().parents[1]
EVID=Path(r"D:\go-odyssey-g010-3d-activation-evidence-20261021")
USER=983140
OTHER=983141
def _source():
 m=json.loads((BASE/"docs/handoffs/G011_P022_P038_QA_MODEL_RECOVERY_20261021.json").read_text(encoding="utf8"))
 assert m["release_status"]=="NOT_ADMITTED" and len(m["models"])==12
 items=[]
 for x in m["models"]:
  assert x["real_player_equip_enabled"] is False
  assert x["formal_product_release"]=="NOT_ADMITTED"
  slot={"MAIN_HAND":"weapon","OFF_HAND":"offhand"}[x["slot"]]
  items.append({"id":"g014_qa_"+x["code"].lower().replace("-","_"),
    "name":"QA ONLY "+x["name"],"slot":slot,"rarity":"common",
    "icon":"🧪","desc":"Nonrelease synthetic QA; not for sale or grant",
    "effects":{},"qa_source_id":x["qa_id"],"qa_sha":x["runtime_sha256"],
    "release_admitted":False})
 assert len({x["id"] for x in items})==12
 assert [x["slot"] for x in items].count("weapon")==8
 assert [x["slot"] for x in items].count("offhand")==4
 return items
def _client(app,uid,mark):
 c=app.app.test_client()
 with c.session_transaction() as s:
  s["user_id"]=uid;s["username"]=f"g014-only-{uid}";s["independent"]=mark
 return c

def test_g014_12_real_pg_server_equip_with_four_shield_switches(runtime,monkeypatch):
 app=runtime
 assert os.environ.get("PRODUCTION")!="1"
 assert "offhand" in CANONICAL_SLOTS
 assert app._equipment_canonical_loadout_enabled() is False
 assert app._canonical_coin_shop_purchase_enabled() is False
 assert not any(x["slot"]=="offhand" for x in app.CANONICAL_EQUIPMENT_DEFS)
 entries=_source()
 original=app.CANONICAL_EQUIPMENT_DEFS
 assert all(not x["id"].startswith("g014_qa_") for x in original)
 synthetic=tuple(original)+tuple(entries)
 monkeypatch.setattr(app,"CANONICAL_EQUIPMENT_DEFS",synthetic)
 monkeypatch.setattr(app,"_EQUIP_MAP",{x["id"]:x for x in synthetic})
 with app.get_db() as conn:
  upgrade_slot(conn,equipment_defs=synthetic)
  for uid in (USER,OTHER):
   conn.execute("INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at) VALUES(?,?,?,?,?,?,?)",
    (uid,f"g014-only-{uid}","G014 Synthetic","unused",0,"free","2026-10-21T00:00:00"))
   conn.execute("INSERT INTO user_stats(user_id,coins,rank_level,xp) VALUES(?,?,?,?)",
    (uid,987,"LV1",0))
   conn.execute("INSERT INTO player_appearance(user_id,character_key) VALUES(?,'apprentice')",(uid,))
  grants={}
  for item in entries:
   r=app.grant_equipment_ownership(conn,USER,item["id"],"admin",equipment_defs=synthetic)
   assert r.equipped is False
   grants[item["id"]]=r.row_id
 main=next(x for x in entries if x["slot"]=="weapon")
 shield=next(x for x in entries if x["slot"]=="offhand")
 client=_client(app,USER,"first")
 alt=_client(app,USER,"different-session")
 stranger=_client(app,OTHER,"stranger")
 assert client.get_cookie("session").value!=alt.get_cookie("session").value
 assert client.get("/api/player/appearance").get_json()["character_entitled"] is True
 inv=client.get("/api/player/inventory").get_json()
 assert len([x for x in inv if x["item_id"].startswith("g014_qa_")])==12
 assert all(x["canonical_equippable"] is True for x in inv if x["item_id"].startswith("g014_qa_"))
 for name in (main["id"],shield["id"]):
  r=client.post("/api/player/inventory/equip",json={"inv_id":grants[name],"action":"equip"})
  assert r.status_code==409 and r.get_json()["error"]=="LOADOUT_DISABLED"
 assert stranger.post("/api/player/inventory/equip",json={
   "inv_id":grants[shield["id"]],"action":"equip"}).status_code==404
 monkeypatch.setenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,"1")
 def equip(item):
  r=client.post("/api/player/inventory/equip",json={"inv_id":grants[item["id"]],"action":"equip"})
  assert r.status_code==200,(item["id"],r.status_code,r.get_json())
  assert r.get_json()["canonical_slot"]==item["slot"]
  return r.get_json()
 assert equip(main)["changed"] is True
 assert equip(shield)["changed"] is True
 again=equip(main)
 assert again["changed"] is False
 def state(testclient):
  current=testclient.get("/api/player/inventory").get_json()
  selected=[x for x in current if x.get("equipped") is True and x["item_id"].startswith("g014_qa_")]
  assert len(selected)==2
  assert {x["slot"] for x in selected}=={"weapon","offhand"}
  return {x["slot"]:x["item_id"] for x in selected}
 assert state(client)==state(alt)=={"weapon":main["id"],"offhand":shield["id"]}
 mainrows=[x for x in entries if x["slot"]=="weapon"]
 offrows=[x for x in entries if x["slot"]=="offhand"]
 for a in mainrows:
  equip(a)
  for b in offrows:
   equip(b)
   assert state(client)==state(alt)=={"weapon":a["id"],"offhand":b["id"]}
 with app.get_db() as conn:
  rows=conn.execute("SELECT id,equip_id,equipped,canonical_slot FROM player_inventory WHERE user_id=?",(USER,)).fetchall()
  assert len(rows)==12
  assert sum(int(x["equipped"]) for x in rows)==2
  assert {x["canonical_slot"] for x in rows if x["equipped"]}=={"weapon","offhand"}
  assert conn.execute("SELECT COUNT(*) AS n FROM player_inventory WHERE user_id=?",(OTHER,)).fetchone()["n"]==0
  assert conn.execute("SELECT coins,xp FROM user_stats WHERE user_id=?",(USER,)).fetchone()["coins"]==987
  assert conn.execute("SELECT COUNT(*) AS n FROM currency_log WHERE user_id=? AND delta<0",(USER,)).fetchone()["n"]==0
 monkeypatch.delenv(app.EQUIPMENT_CANONICAL_LOADOUT_FLAG,raising=False)
 assert app._equipment_canonical_loadout_enabled() is False
 assert client.post("/api/player/inventory/equip",json={
  "inv_id":grants[shield["id"]],"action":"unequip"}).status_code==409
 output={"schema":"G014_P038_DUAL_SLOT_NATIVE_PG_V1",
 "verdict":"G014_8_MAIN_4_OFFHAND_32_SERVER_STATES_PASS",
 "native_postgres_disposable":True,"source_catalog_size":12,"mainhand":8,"shields":4,
 "main_offhand_pairings":32,"exact_inventory_owner":True,"fresh_cookie_readback":True,
 "equipped_per_slot":1,"repeated_equips_idempotent":True,"other_user_404":True,
 "default_disabled_409":True,"restored_disabled_409":True,"coins_unchanged":987,
 "server_allowlist_only_in_pytest":True,"no_production_asset_admission":True,
 "formal_release":False,"real_hero_webgl_3d_attached":False,
 "github_merge":False,"oracle_deploy":False,"formal_player_writes":False}
 EVID.mkdir(exist_ok=True)
 path=EVID/"G014_P038_NATIVE_PG_32_DUAL_EQUIP_20261021.json"
 path.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf8")
 print("G014_NATIVE_PG_ALL_32_DUAL_EQUIP_PASS",path,flush=True)
