"""G011 QA-only 28-item legacy 3D equipment recovery contracts."""
from pathlib import Path
import json,hashlib,subprocess
ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"docs/handoffs/G011_P022_P038_QA_MODEL_RECOVERY_20261021.json"
SRC=ROOT/"js/g010_hero_3d_gallery.mjs"
def source():
 return json.loads(MANIFEST.read_text(encoding="utf8"))
def test_exact_p022_28_12_p038_16_blender_qa_only():
 d=source()
 assert d["schema"]=="G011_3D_P022_P038_RECOVERY_V1"
 assert d["task"]=="NON_PRODUCTION_VISUAL_TEST_ONLY"
 assert d["release_status"]=="NOT_ADMITTED"
 assert d["qa_preview_total"]==28 and len(d["models"])==12
 assert len(d["p022_qa_derived_models"])==16
 assert len({x["code"] for x in d["models"]+d["p022_qa_derived_models"]})==28
 assert sum(x["slot"]=="MAIN_HAND" for x in d["models"])==8
 assert sum(x["slot"]=="OFF_HAND" for x in d["models"])==4
 assert all(x["real_player_equip_enabled"] is False for x in d["models"]+d["p022_qa_derived_models"])
 assert all(x["release_admitted"] is False for x in d["p022_qa_derived_models"])
def test_all_28_qa_glb_sha_match_and_no_traversal():
 d=source()
 for item in d["models"]+d["p022_qa_derived_models"]:
  rel=item["runtime_glb"]
  assert rel.startswith(("assets/3d_shop/formal_character_equipment_v1/weapons/",
    "tests/e2e/g011_private_qa_assets/"))
  assert ".." not in rel and "\\" not in rel
  file=ROOT/rel
  assert file.is_file()
  raw=file.read_bytes()
  assert raw[:4]==b"glTF"
  assert hashlib.sha256(raw).hexdigest()==item["runtime_sha256"]
def test_localhost_and_explicit_optin_only_release_not_mutated():
 code=SRC.read_text(encoding="utf8")
 assert '["localhost","127.0.0.1"].includes(location.hostname)' in code
 assert 'new URLSearchParams(location.search).get("g011_qa")==="1"' in code
 assert 'location.protocol==="http:"' in code
 assert 'model.real_player_equip_enabled!==false' in code
 assert 'model.release_admitted!==false' in code
 assert 'models.length!==91' in code
 assert 'new Set(models.map(x=>x.id)).size!==63' in code
 assert "G009_SHOP_BROWSE_PREVIEW_ONLY = true" in (ROOT/"shop.html").read_text(encoding="utf8")
 assert "CANONICAL_COIN_SHOP_PURCHASE_ENABLED" not in code
 assert (ROOT/".gitignore").read_text(encoding="utf8").count("tests/e2e/g011_private_qa_assets/")==1
def test_legacy_qa_glbs_do_not_become_tracked_release_assets():
 proc=subprocess.run(["git","-C",str(ROOT),"ls-files","--","tests/e2e/g011_private_qa_assets"],
                     capture_output=True,text=True,timeout=15)
 assert proc.returncode==0 and not proc.stdout.strip()
 docker=(ROOT/"Dockerfile").read_text(encoding="utf8")
 assert "g011_private_qa_assets" not in docker
 assert "G011_P022_P038_QA_MODEL_RECOVERY" not in docker
def test_real_webgl_91_model_receipt_pass():
 receipt=json.loads((ROOT/"tests/e2e/G011_3D_QA_91_REAL_WEBGL_BROWSER_20261021.json").read_text())
 assert receipt["verdict"]=="G011_91_REAL_GLBS_QA_ONLY_PASS"
 assert receipt["pass"]==105 and len(receipt["selected"])==91
 assert len([x for x in receipt["selected"] if x["category"]=="p038_qa"])==28
 assert receipt["errors"]==[] and receipt["httpFail"]==[]
