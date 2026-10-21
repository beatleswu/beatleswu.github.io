"""G022 pre-release: binary rights differ from production admission;
actual historical OCI swap proof recorded on beatles separately.
"""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def manifest(p):
 return json.loads((ROOT/p).read_text(encoding="utf8"))
def test_formal9_all_four_rights_cleared_but_no_release():
 d=manifest("schemas/g009_formal9_rights_cleared_replacement_v1.json")
 assert d["release_eligibility_value"]=="RIGHTS_CLEARED_RELEASE_NOT_ADMITTED"
 assert len(d["items"])==4 and len(d["mapping"])==4
 assert d["rights"]["RIGHTS_STATUS"]=="RIGHTS_CLEARED"
 assert d["rights"]["LICENSE_TYPE"]=="CC0-1.0"
 for flag in ("EQUIP_ENABLED","SHOP_ENABLED","PURCHASE_ENABLED","DROP_ENABLED",
  "PLAYER_SELECTABLE","RELEASE_ENABLED","PRODUCTION_ASSET_ADMISSION"):
  assert d["rights"][flag] is False,flag
 assert all(x["equip_capability"] is False and
  x["release_eligibility"]=="RIGHTS_CLEARED_RELEASE_NOT_ADMITTED"
  for x in d["items"])
def test_four_formal9_real_binary_source_hashes():
 d=manifest("schemas/g009_formal9_rights_cleared_replacement_v1.json")
 for r in d["items"]:
  path=ROOT/r["runtime_asset"].lstrip("/")
  assert path.is_file(),path
  assert hashlib.sha256(path.read_bytes()).hexdigest()==r["runtime_sha256"]
def test_original_twelve_D007_only_visual_G009_candidate():
 d=manifest("schemas/g009_d007_runtime_prerequisite_v1.json")
 assert d["owner_admission"]["status"]=="APPROVED_FOR_CURRENT_G009_CANDIDATE"
 assert len(d["equipment_catalog"]["items"])==12
 assert all(r["release_eligibility"]=="NOT_CLEARED" and
  r["equip_capability"] is False for r in d["equipment_catalog"]["items"])
def test_28_p022_source_models_remain_QA_not_formal_SKUs():
 d=manifest("docs/handoffs/G011_P022_P038_QA_MODEL_RECOVERY_20261021.json")
 assert d["release_status"]=="NOT_ADMITTED"
 assert d["shop_purchasable"] is False
 assert d["p022_total"]==28
 assert len(d["models"])==12 and len(d["remaining_source_only"])==16
 assert d["duplicate_in_current_repo"]==10
 assert all(m["formal_product_release"]=="NOT_ADMITTED" and
  m["real_player_equip_enabled"] is False for m in d["models"])
 assert all(m["release_admitted"] is False for m in d["remaining_source_only"])
def test_original_prod_shop_nine_server_offers_not_equal_to_3D_rights():
 source=(ROOT/"app.py").read_text(encoding="utf8")
 shop=(ROOT/"shop.html").read_text(encoding="utf8")
 hero=(ROOT/"js/g009_owner_approved_formal_equipment_mapping.js").read_text(encoding="utf8")
 assert "approved_equipment_purchase_ui_enabled" in source
 assert "G019_APPROVED_EQUIPMENT_SHOP_UI_FLAG, default=False" in source
 assert "const G009_SHOP_BROWSE_PREVIEW_ONLY = true" in shop
 assert 'release_eligibility !== "NOT_CLEARED"' in hero
 assert "release_eligibility !== G009_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED" in hero
def test_G022_handoff_has_real_predecessor_and_candidate_sha_and_separate_gate():
 h=(ROOT/"docs/handoffs/G022_CROSS_IMAGE_ROLLBACK_AND_3D_RELEASE_GATES_20261021.md").read_text(encoding="utf8")
 for s in ("246decad0207228f6c9c87f0309610b5d8bbcdb8",
  "15cbcdbe9c28b8f16107387e45cddb7c087f9627",
  "G018", "G019", "GO_MERGE", "GO_DEPLOY",
  "Oracle","G022_RIGHTS_AND_QA_RELEASE_GATES_STAY_NOT_ADMITTED_PASS",
  "G022_REAL_OCI_IMAGE_SWAP_PERSISTENT_PG_PLAYER_READBACK_PASS"):
  assert s in h
