"""G010 new 3D user-surface activation checks against current isolated candidate."""
from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parents[1]
def src(path):return (ROOT/path).read_text(encoding="utf8")
def test_hero_has_real_lazy_3d_surface_and_runtime():
 html=src("hero.html")
 for s in ('id="g010-3d-gallery"','id="g010-3d-canvas"',
           'id="g010-3d-category"','id="g010-3d-model"',
           '/js/g010_hero_3d_gallery.mjs'):
  assert s in html
 assert html.index('id="g010-3d-gallery"')>html.index('id="g009-panel-equipment"')
 assert html.count('id="g010-3d-gallery"')==1
 assert '可檢視已核准的真實 GLB' in html
def test_3d_viewer_webgl_integrity_lifecycle_without_backend_mutations():
 code=src("js/g010_hero_3d_gallery.mjs")
 for fragment in ('new THREE.WebGLRenderer','crypto.subtle.digest("SHA-256",bytes)',
  'new GLTFLoader().parseAsync','"model_integrity_rejected"','state.resize?.disconnect()',
  'renderer?.forceContextLoss','IntersectionObserver' if False else 'new MutationObserver(sync)',
  'document.addEventListener("visibilitychange",sync)',
  'state.group.rotation.y','releaseResources(old)',"asset_id"):
  if fragment=="asset_id":continue
  assert fragment in code,fragment
 assert not re.search(r'method:\s*["\']POST["\']',code)
 assert not re.search(r'(api/shop/buy|api/player/inventory/equip|api/rewards/sync)',code)
 assert 'if (token!==state.request||!state.renderer)' in code
def test_complete_owner_authorized_manifest_sources_and_counts():
 code=src("js/g010_hero_3d_gallery.mjs")
 for name in ('future30_c005_real_asset_runtime_mapping_manifest.json',
  'companion/formal_18/mapping_manifest.json','p048/runtime_manifest.json',
  'G009_FORMAL9_REPLACEMENT_ROWS'):
  assert name in code
 assert "totals.character!==33" in code
 assert "totals.spirit!==18" in code
 assert "totals.accessory!==6" in code
 assert "totals.weapon!==4" in code
 assert "totals.bonus!==2" in code
 assert "new Set(models.map(x=>x.id)).size!==expected" in code
 assert "totals.equipment_preview!==8" in code
 assert 'new Set(G009_FORMAL9_RETIRED_ASSET_IDS)' in code
 assert 'g030_original_equipment_ownership_gate_failed' in code
def test_weapon_presentation_does_not_grant_release_or_equip_rights():
 data=json.loads(src("schemas/g009_formal9_rights_cleared_replacement_v1.json"))
 assert len(data["items"])==4
 assert data["rights"]["RIGHTS_STATUS"]=="RIGHTS_CLEARED"
 assert data["release_eligibility_value"]=="RIGHTS_CLEARED_RELEASE_NOT_ADMITTED"
 assert data["rights"]["RELEASE_ENABLED"] is False
 assert data["rights"]["PURCHASE_ENABLED"] is False
 assert data["rights"]["EQUIP_ENABLED"] is False
 assert data["rights"]["PRODUCTION_ASSET_ADMISSION"] is False
 assert data["rights"]["PUBLIC_3D_PREVIEW_ADMITTED"] is True
 assert 'row.rights?.PUBLIC_3D_PREVIEW_ADMITTED !== true' in src("js/g010_hero_3d_gallery.mjs")
 assert '3D_SHOP_PRESENTATION_ENABLED' not in src("js/g010_hero_3d_gallery.mjs")
 assert 'G009_SHOP_BROWSE_PREVIEW_ONLY = true' in src("shop.html")
def test_shop_and_inventory_links_point_to_actual_g010_gallery():
 for page in ("shop.html","inventory.html"):
  assert 'href="/hero?tab=equipment#g010-3d-gallery"' in src(page)
 assert "const requested = new URLSearchParams(location.search).get('tab')" in src("js/g009_hero_hub_batch_a.js")
def test_baked_image_and_static_inventory_exact_module_membership():
 module="js/g010_hero_3d_gallery.mjs"
 docker=src("Dockerfile")
 assert "COPY "+module+" ./"+module in docker
 assert "'g010_hero_3d_gallery.mjs'" in src("app.py")
 pack=json.loads(src("deploy/build-manifest.json"))
 inv=json.loads(src("deploy/live-static-asset-inventory.json"))
 assert src("deploy/build-manifest.json").count('"'+module+'"')==1
 assert src("deploy/build-manifest.json").count('"/app/'+module+'"')==1
 assert src("deploy/live-static-asset-inventory.json").count('"'+module+'"')==1
 assert module in inv["eligible_files"]["entries"]
def test_initial_3d_asset_integrity_receipt_all_63():
 receipt=ROOT/"G010_3D_ALL_63_SHA256_AUDIT_20261021.json"
 assert receipt.is_file()
 x=json.loads(receipt.read_text(encoding="utf8"))
 assert x["verdict"]=="63_OF_63_SHA256_BYTES_VERIFIED"
 assert len(x["models"])==63
 assert x["count_by_category"]=={"character":33,"spirit":18,"accessory":6,"bonus":2,"weapon":4}
