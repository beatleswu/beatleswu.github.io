"""G018 rights/equipment non-release hardening: exact 13 held-object namespace
plus 3 projectile-prop excluded; localhost only. No Product official grants.
"""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"docs/handoffs/G017_P022_16_QA_SOURCE_AND_ATTACHMENT_20261021.json"
def test_P022_13_3_distinction_and_original_sources():
 m=json.loads(SOURCE.read_text(encoding="utf8"))
 assert m["release_status"]=="NOT_ADMITTED"
 assert len(m["models"])==16
 handheld=[x for x in m["models"] if x["functional_class"]=="MAIN_HAND_STATIC_QA"]
 arrow=[x for x in m["models"] if x["functional_class"]=="PROJECTILE_PROP_ONLY"]
 assert len(handheld)==13 and len(arrow)==3
 for row in m["models"]:
  assert row["formal_item_id"] is None
  assert row["equip_enabled"] is False and row["shop_enabled"] is False
  assert row["formal_product_release"]=="NOT_ADMITTED"
  assert row["legal_admission_proven"] is False
  assert hashlib.sha256((ROOT/row["runtime_glb"]).read_bytes()).hexdigest()==row["runtime_sha256"]
def test_original_hero_qa_bridge_is_failclosed_by_default():
 source=(ROOT/"js/g009_d_r2_shared_host_bootstrap.js").read_text(encoding="utf8")
 assert 'globalThis.location?.hostname === "127.0.0.1"' in source
 assert 'get("g018_qa") === "1"' in source
 assert 'void import("/tests/e2e/g018_p022_original_hero_qa.mjs")' in source
 assert "G018 P022 localhost QA remains fail-closed" in source
 assert 'get("g015_qa") === "1"' in source
 assert 'void import("/tests/e2e/g015_p038_original_hero_qa.mjs")' in source
 assert 'void registerEquipmentAdapter().catch' in source
 module=(ROOT/"tests/e2e/g018_p022_original_hero_qa.mjs").read_text(encoding="utf8")
 for phrase in ('location.hostname==="127.0.0.1"',
  'get("g018_qa")==="1"','manifest.release_status!=="NOT_ADMITTED"',
  'x.functional_class==="PROJECTILE_PROP_ONLY"', # checked below as exact runtime skip
  'function fromManifest(x)','const all=manifest.models.map(fromManifest)',
  'all.filter(x=>x===null).length!==3',
  'if(sha!==desc.runtime_sha256)fail("source_SHA")',
  'projectServerEquippedHandItems(inventory',
  'fetch("/api/player/inventory",{credentials:"include",cache:"no-store"})',
  'registerHeroPresentationRehydrator',
  'allowTestOnlyDescriptors:true'):
  if phrase=='x.functional_class==="PROJECTILE_PROP_ONLY"':
   assert 'x.functional_class==="PROJECTILE_PROP_ONLY"' in module
  else:assert phrase in module,phrase
 assert "/api/shop/buy" not in module
 assert "grant_equipment_ownership" not in module
 assert "EQUIPMENT_CANONICAL_LOADOUT_ENABLED" not in module
def test_never_ship_private_QA_binary_or_registry_grants():
 image=(ROOT/"Dockerfile").read_text(encoding="utf8")
 assert "COPY tests/e2e" not in image
 assert "g018_p022_original_hero_qa.mjs" not in image
 assert "g011_private_qa_assets" not in image
 assert "g018_qa_" not in (ROOT/"app.py").read_text(encoding="utf8")
 assert "g018_qa_" not in (ROOT/"hero.html").read_text(encoding="utf8")
 assert "G018" not in (ROOT/"shop.html").read_text(encoding="utf8")
 assert "G018" not in (ROOT/"inventory.html").read_text(encoding="utf8")
def test_authored_browser_locks_orig_Hero_and_default_off():
 t=(ROOT/"tests/e2e/g018_p022_13_original_hero_pg_browser.mjs").read_text(encoding="utf8")
 for phrase in ('/hero?g018_qa=1&tab=equipment','/hero?tab=equipment',
  'data-functional-inv-id','/api/player/inventory/equip',
  'independentFreshSignedSessions','projectilesExcluded:3',
  'defaultOffVerified','/api/shop/buy'):
  assert phrase in t
