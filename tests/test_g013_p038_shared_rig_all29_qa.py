"""G013 QA-only: 12 recovered P038 rigid GLBs on current G009 shared Hero
hand bones. All 29 P038 active characters, 8 MAIN_HAND + 4 OFF_HAND combos.
NOT a Player/Shop release admission or full 29 Owner Safari visual UAT.
"""
from pathlib import Path
import json,hashlib,collections
ROOT=Path(__file__).resolve().parents[1]
REC=ROOT/"docs/handoffs/G011_P022_P038_QA_MODEL_RECOVERY_20261021.json"
SUMMARY=ROOT/"docs/handoffs/G013_P038_ALL29_DUAL_HAND_AGGREGATE_20261021.json"
def test_exact_12_p038_authoritative_sha_no_player_release():
 j=json.loads(REC.read_text(encoding="utf8"))
 assert j["release_status"]=="NOT_ADMITTED"
 assert j["task"]=="NON_PRODUCTION_VISUAL_TEST_ONLY"
 assert len(j["models"])==12
 assert collections.Counter(x["slot"] for x in j["models"])=={"MAIN_HAND":8,"OFF_HAND":4}
 for x in j["models"]:
  assert x["formal_product_release"]=="NOT_ADMITTED"
  assert x["real_player_equip_enabled"] is False
  assert x["prior_29_character_attachment_tested"] is True
  path=ROOT/x["runtime_glb"]
  assert path.is_file(),x["qa_id"]
  assert hashlib.sha256(path.read_bytes()).hexdigest()==x["runtime_sha256"]
def test_current_real_hero_shared_host_not_second_renderer():
 t=(ROOT/"tests/e2e/fixtures/g013_p038_dual_hand_qa.html").read_text(encoding="utf8")
 assert 'createG009SharedHeroAttachmentHost' in t
 assert 'createHeroEquipmentAttachmentAdapter' in t
 assert 'new THREE.WebGLRenderer' in t
 assert t.count('new THREE.WebGLRenderer')==1
 assert 'adapter.setHand("MAIN_HAND"' in t
 assert 'adapter.setHand("OFF_HAND"' in t
 assert 'model.position.sub(pivot)' in t
 assert 'handBone(descriptor.slot==="MAIN_HAND"?"R":"L")' in t
 assert 'inheritedScale' in t
 assert 'handr' in (ROOT/"js/g009_shared_hero_attachment_host.js").read_text(encoding="utf8")
def test_strict_loopback_qa_gate_and_fails_closed():
 t=(ROOT/"tests/e2e/fixtures/g013_p038_dual_hand_qa.html").read_text(encoding="utf8")
 for snippet in ('location.hostname==="127.0.0.1"',
  'location.protocol==="http:"','get("g013_qa")==="1"',
  'G013_P038_QA_NOT_AUTHORIZED_FOR_THIS_ORIGIN',
  'manifest.release_status!=="NOT_ADMITTED"',
  'x.real_player_equip_enabled!==false',
  'x.formal_product_release!=="NOT_ADMITTED"',
  'G013_SHA_MISMATCH','G013_QA_MODEL_NOT_ALLOWED'):
  assert snippet in t,snippet
 assert '"/api/player/inventory/equip"' not in t
 assert '"/api/shop/buy"' not in t
 assert 'G013_P038' not in (ROOT/"Dockerfile").read_text(encoding="utf8")
 assert 'G013_P038' not in (ROOT/"app.py").read_text(encoding="utf8")
def test_all29_real_webgl_raw_evidence_fresh_smoke_and_full():
 s=json.loads(SUMMARY.read_text(encoding="utf8"))
 assert s["verdict"]=="29_HERO_8_MAIN_4_OFF_HAND_REAL_GL_B_DUAL_ATTACH_PASS"
 assert s["active_characters"]==29 and len(set(s["active_character_ids"]))==29
 assert {"A2","R2"}.isdisjoint(s["active_character_ids"])
 assert s["pose_states"]==31 and s["combinations"]==992
 assert s["individual_attached_hand_checks"]==1984
 assert s["unique_mainhand_assets"]==8 and s["unique_offhand_assets"]==4
 assert s["sha_verified_p038_models"]==12
 assert s["max_simultaneous_webgl_renderers"]==1
 assert s["javascript_errors"]==[]
 assert s["bone_follow_and_scale_bounds"]["boneMatrixDelta"]["max"]<1e-3
 assert s["bone_follow_and_scale_bounds"]["centerHandRatio"]["max"]<0.38
 assert s["bone_follow_and_scale_bounds"]["maxDimensionRatio"]["max"]<0.65
 assert s["server_inventory_equip_closure"] is False
 assert s["formal_asset_release_admitted"] is False
 raw=Path(s["raw_receipt"])
 assert raw.is_file()
 assert hashlib.sha256(raw.read_bytes()).hexdigest()==s["raw_sha256"]
 r=json.loads(raw.read_text(encoding="utf8"))
 assert r["status"]=="G013_P038_12_REAL_DUAL_HANDS_HERO_WEBGL_PASS"
 assert r["case_count"]==992 and r["real_pose_count"]==31
 assert len(r["cases"])==992 and r["browser_errors"]==[]
 assert len(r["screen_paths"])==4
 assert len({(x["key"],x["pose"],x["mainId"],x["offId"]) for x in r["cases"]})==992
def test_not_admitted_files_absent_from_product_shipping_manifest():
 assert not any("G013" in p for p in json.loads((ROOT/"deploy/build-manifest.json").read_text(encoding="utf8")).get("post_build_verification_files",[]))
 assert "G009_SHOP_BROWSE_PREVIEW_ONLY = true" in (ROOT/"shop.html").read_text(encoding="utf8")
 rights=json.loads((ROOT/"schemas/g009_formal9_rights_cleared_replacement_v1.json").read_text(encoding="utf8"))
 assert rights["rights"]["PRODUCTION_ASSET_ADMISSION"] is False
