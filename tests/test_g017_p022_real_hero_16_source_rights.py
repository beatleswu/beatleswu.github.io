"""G017 evidence: 16 original P022 assets are exact byte-identical to
G011-converted QA GLBs and static 29-hero WebGL screenshots, no release claim.
All source rights remain NOT_ADMITTED; no official item registry mutation.
"""
from pathlib import Path
from collections import Counter
import json,hashlib
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"docs/handoffs/G017_P022_16_QA_SOURCE_AND_ATTACHMENT_20261021.json"
RESULT=ROOT/"docs/handoffs/G017_P022_16_29_HERO_AND_RELEASE_MATRIX_20261021.json"
EVID=Path(r"D:\go-odyssey-g010-3d-activation-evidence-20261021")
def read(p):return json.loads(p.read_text(encoding="utf8"))
def test_source_catalog_belongs_only_to_qa_and_types_are_honest():
 d=read(SRC)
 assert d["schema"]=="G017_P022_16_SOURCED_QA_V1"
 assert d["release_status"]=="NOT_ADMITTED"
 assert d["all_shopping_disabled"] is True
 assert d["production_server_item_id_mapping"] is False
 assert d["copyright_release_evidence_verified"] is False
 assert len(d["models"])==d["total"]==16
 assert Counter(x["functional_class"] for x in d["models"])=={
  "MAIN_HAND_STATIC_QA":13,"PROJECTILE_PROP_ONLY":3}
 assert Counter(x["category"] for x in d["models"])=={
  "MAGIC_WEAPON":2,"TWO_HAND_WEAPON":4,"ONE_HAND_WEAPON":4,
  "RANGED_WEAPON":3,"PROJECTILE":3}
 assert all(x["formal_item_id"] is None and not x["equip_enabled"]
  and not x["shop_enabled"] and not x["legal_admission_proven"]
  and x["formal_product_release"]=="NOT_ADMITTED" for x in d["models"])
def test_sha_matches_all_16_original_fbx_files_and_glb_derived_files():
 source=read(SRC)
 original=read(ROOT/"docs/handoffs/G011_P022_P038_QA_MODEL_RECOVERY_20261021.json")
 converted=read(EVID/"G011_P022_16_PRIVATE_QA_GLB_EXPORT_20261021.json")
 assert source["total"]==converted["success"]==16
 for row in source["models"]:
  old=next(x for x in original["remaining_source_only"] if x["code"]==row["code"])
  conv=next(x for x in converted["results"] if x["code"]==row["code"])
  assert row["source_path"]==old["source_file"]==conv["source_path"]
  assert hashlib.sha256(Path(row["source_path"]).read_bytes()).hexdigest()==row["fbx_source_sha256"]==conv["source_sha256"]
  glb=ROOT/row["runtime_glb"]
  assert glb.is_file()
  assert hashlib.sha256(glb.read_bytes()).hexdigest()==row["runtime_sha256"]==conv["sha256"]
  assert glb.stat().st_size==row["runtime_bytes"]
def test_real_chrome_all_496_webgl_case_evidence_and_3_source_pictures():
 final=read(RESULT);raw=Path(final["raw_receipt"])
 assert final["verdict"]=="G017_ALL16_31_POSES_STATIC_MAINHAND_QA_PASS"
 assert final["real_hero_characters"]==29 and final["real_hero_pose_states"]==31
 assert final["real_webgl_cases"]==496
 assert final["handheld_static_cases"]==403
 assert final["projectile_props_static_cases"]==93
 assert final["all_original_fbx_shas_verified"]==16
 assert final["all_exported_glb_shas_verified"]==16
 assert final["max_renderers"]==1 and final["errors"]==[]
 assert final["bone_delta"]["maximum"]==0
 assert final["weapon_center_to_hand_normalized"]["maximum"]<0.38
 assert final["weapon_scale_to_hero_normalized"]["maximum"]<0.65
 assert hashlib.sha256(raw.read_bytes()).hexdigest()==final["raw_receipt_sha256"]
 d=read(raw)
 assert d["verdict"]=="G017_P022_16_REAL_SHARED_HERO_STATIC_WEBGL_QA_PASS"
 assert d["case_count"]==len(d["cases"])==496
 assert len({(z["key"],z["pose"],z["code"]) for z in d["cases"]})==496
 assert len({z["code"] for z in d["cases"]})==16
 assert len({z["key"] for z in d["cases"]})==29
 assert len({(z["key"],z["pose"]) for z in d["cases"]})==31
 assert len(d["screenshot_paths"])==3 and all(Path(x).is_file() for x in d["screenshot_paths"])
 assert all(x["metric"]["boneMatrixDelta"]==0 and x["metric"]["childCount"]==1
  and x["metric"]["attachStatus"]=="attached" for x in d["cases"])
def test_license_provenance_distinct_from_formal_release():
 d=read(RESULT)
 assert d["directly_verified_official_pages_in_stage"] is False
 assert d["rights_release_admitted"] is False
 assert d["original_hero_player_pg_item_equips"]==0
 assert d["dual_hand_interaction_tested"] is False
 assert d["ranged_bow_and_arrow_animation_tested"] is False
 assert len(d["per_item_release_matrix"])==16
 assert set(d["exact_license_pack_recitations"])=={
  "Adventure","Elf","Fantasy Army","Fantasy Heroes","Goblin"}
 assert all(x["formal_sku"] is None and x["release_admitted"] is False
  and not x["verified_official_license_current_turn"]
  and not x["bow_firing_tested"] and not x["twohand_rig_certified"]
  for x in d["per_item_release_matrix"])
 assert all(x["historical_game_use_claim"]=="YES" for x in d["per_item_release_matrix"])
 assert any(x["raw_asset_redistribution_limit"].startswith("UNRESOLVED")
  for x in d["per_item_release_matrix"])
def test_loopback_fail_closed_and_no_go_product_ship_changes():
 fixture=(ROOT/"tests/e2e/fixtures/g017_p022_16_real_hero_qa.html").read_text(encoding="utf8")
 browser=(ROOT/"tests/e2e/g017_p022_16_29_hero_webgl.mjs").read_text(encoding="utf8")
 assert 'location.hostname==="127.0.0.1"' in fixture
 assert 'get("g017_qa")==="1"' in fixture
 assert 'G017_P022_QA_NOT_AUTHORIZED_FOR_THIS_ORIGIN' in fixture
 assert 'G017_SOURCE_GATE_FAILED' in fixture
 assert "SHA_MISMATCH" in fixture
 assert "attachG017Main" in fixture
 assert 'projectileProps:3' in fixture
 assert "ranged_bow_and_arrow_animation_tested" not in browser
 assert "g017_qa" not in (ROOT/"hero.html").read_text(encoding="utf8")
 assert "G017_P022" not in (ROOT/"app.py").read_text(encoding="utf8")
 assert "g017_p022_16_real_hero_qa.html" not in (ROOT/"Dockerfile").read_text(encoding="utf8")
 assert "G017_P022" not in (ROOT/"shop.html").read_text(encoding="utf8")
