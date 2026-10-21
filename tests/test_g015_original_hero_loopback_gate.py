"""G015: original Product Hero must remain fail-closed by default.
The P038 renderer is a localhost-only and nonreleased test resource.
"""
from pathlib import Path
import json,re,hashlib
ROOT=Path(__file__).resolve().parents[1]
def test_original_hero_html_unmodified_and_orig_bootstrap():
 html=(ROOT/"hero.html").read_text(encoding="utf8")
 assert '<script type="module" src="/js/g008_future30_hero_renderer.js"></script>' in html
 assert '<script type="module" src="/js/g009_d_r2_shared_host_bootstrap.js"></script>' in html
 assert "g015_qa" not in html
 assert "g014_qa_" not in html
def test_default_mode_uses_old_exact_authority_not_unreleased_equipment():
 source=(ROOT/"js/g009_d_r2_shared_host_bootstrap.js").read_text(encoding="utf8")
 assert 'globalThis.location?.protocol === "http:"' in source
 assert 'globalThis.location?.hostname === "127.0.0.1"' in source
 assert 'get("g015_qa") === "1"' in source
 assert 'import("/tests/e2e/g015_p038_original_hero_qa.mjs")' in source
 assert 'void registerEquipmentAdapter().catch' in source
 assert 'console.warn("G015 P038 localhost-only QA remains fail-closed"' in source
 assert 'PRESENTABLE_RELEASE_STATES' in source
 assert "NOT_CLEARED" in source
def test_source_based_staging_qa_requires_authenticated_exact_pg_rows():
 qa=(ROOT/"tests/e2e/g015_p038_original_hero_qa.mjs").read_text(encoding="utf8")
 for value in ('location.hostname==="127.0.0.1"',
  'get("g015_qa")==="1"', 'manifest.release_status!=="NOT_ADMITTED"',
  'x.formal_product_release!=="NOT_ADMITTED"',
  'x.real_player_equip_enabled!==false',
  'if(sha!==desc.runtime_sha256)fail("source_SHA")',
  'projectServerEquippedHandItems(inventory',
  'fetch("/api/player/inventory",{credentials:"include",cache:"no-store"})',
  'server_item_id:id','registerHeroPresentationResolver',
  'registerHeroPresentationRehydrator','allowTestOnlyDescriptors:true'):
  assert value in qa,value
 assert "/api/shop/buy" not in qa
 assert "/api/player/inventory/equip" not in qa
 assert "PRODUCTION_ASSET_ADMISSION=true" not in qa
def test_twelve_exact_original_asset_hashes_still_unreleased():
 m=json.loads((ROOT/"docs/handoffs/G011_P022_P038_QA_MODEL_RECOVERY_20261021.json").read_text(encoding="utf8"))
 assert m["release_status"]=="NOT_ADMITTED"
 assert len(m["models"])==12
 for entry in m["models"]:
  assert entry["real_player_equip_enabled"] is False
  assert entry["formal_product_release"]=="NOT_ADMITTED"
  file=ROOT/entry["runtime_glb"]
  assert file.is_file()
  assert hashlib.sha256(file.read_bytes()).hexdigest()==entry["runtime_sha256"]
def test_shared_host_adds_only_read_only_hand_scale_information():
 source=(ROOT/"js/g009_shared_hero_attachment_host.js").read_text(encoding="utf8")
 assert 'hand_world_scale: boneScale ? Object.freeze([...boneScale]) : null' in source
 assert 'getWorldScale(new THREE.Vector3())' in source
 assert 'createG009SharedHeroAttachmentHost' in source
 assert 'hero_attachment_hand_bone' not in source
def test_release_image_explicitly_not_carrying_test_only_3d_asset_paths():
 docker=(ROOT/"Dockerfile").read_text(encoding="utf8")
 assert "COPY tests/e2e" not in docker
 assert "g015_p038_original_hero_qa.mjs" not in docker
 assert "g011_private_qa_assets" not in docker
 assert "g014_qa_" not in (ROOT/"app.py").read_text(encoding="utf8")
 assert "g014_qa_" not in (ROOT/"equipment_loadout_service.py").read_text(encoding="utf8")
def test_original_hero_actual_browser_receipt_exists():
 # Receipt produced by full native PostgreSQL + original Hero /hero E2E.
 p=Path(r"D:\go-odyssey-g010-3d-activation-evidence-20261021\G015_P038_ORIGINAL_HERO_PG_REAL_WEBGL_20261021.json")
 assert p.is_file()
 evidence=json.loads(p.read_text(encoding="utf8"))
 assert evidence["verdict"]=="G015_ORIGINAL_HERO_DUAL_P038_WEBGL_NATIVE_PG_RELOGIN_PASS"
 assert evidence["dual_render_count"]==4
 assert evidence["two_independent_signed_sessions"] is True
 assert evidence["original_hero_html_and_real_g008_canvas"] is True
 assert evidence["legal_model_admission"] is False
 assert evidence["normal_original_hero_no_qa_displays_none"] is True
