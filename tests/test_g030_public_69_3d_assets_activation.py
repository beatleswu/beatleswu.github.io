"""G030 genuine public 3D visual activation. No ownership/equip/production mutations."""
from pathlib import Path
import hashlib,json,struct
ROOT=Path(__file__).resolve().parents[1]
def load(path):
    return json.loads((ROOT/path).read_text(encoding="utf8"))
def test_all_69_canonical_glb_bytes_and_rights_separated():
    hero=load("deploy/g009-hero-model-static-pack-manifest.json")
    comp=load("deploy/g009-companion-formal18-static-pack-manifest.json")
    formal=load("deploy/g009-formal9-replacement-static-pack-manifest.json")
    assert len(hero["files"])==47
    assert len([x for x in comp["files"] if x["path"].endswith(".glb")])==18
    assert len(formal["files"])==4
    records=[*hero["files"],*(x for x in comp["files"] if x["path"].endswith(".glb")),*formal["files"]]
    paths=[x["path"] for x in records]
    assert len(paths)==len(set(paths))==69
    assert all(path.startswith("assets/3d_shop/") and path.endswith(".glb") for path in paths)
    for item in records:
        path=ROOT/item["path"]
        assert path.is_file(),item["path"]
        sha=hashlib.sha256()
        with path.open("rb") as reader:
            header=reader.read(12)
            assert len(header)==12 and header[:4]==b"glTF",item["path"]
            magic,version,size=struct.unpack("<III",header)
            assert version==2 and size==item["size"],item["path"]
            sha.update(header)
            for chunk in iter(lambda:reader.read(2*1024*1024),b""):sha.update(chunk)
        assert sha.hexdigest()==item["sha256"],item["path"]
    assert formal["public_3d_preview_admission"] is True
    assert formal["product_release_admission"] is False
    assert formal["production_asset_admission"] is False
    assert all(load("schemas/g009_formal9_rights_cleared_replacement_v1.json")["rights"][k] is False
               for k in ("EQUIP_ENABLED","SHOP_ENABLED","PURCHASE_ENABLED","DROP_ENABLED","PLAYER_SELECTABLE"))
def test_full_69_public_gallery_and_old_private_qa_preserved():
    code=(ROOT/"js/g010_hero_3d_gallery.mjs").read_text(encoding="utf8")
    authority=(ROOT/"schemas/g009_d007_runtime_prerequisite_v1.json")
    data=json.loads(authority.read_text(encoding="utf8"))
    retired=set(load("schemas/g009_formal9_rights_cleared_replacement_v1.json")["retired_asset_ids"])
    original=[x for x in data["equipment_catalog"]["items"] if x["asset_id"] not in retired]
    assert len(original)==8
    assert all(x["release_eligibility"]=="NOT_CLEARED" and x["equip_capability"] is False for x in original)
    required=('const expected = G011_QA_MODE ? 63 : 71',
      'totals.equipment_preview!==8',
      'new Set(G009_FORMAL9_RETIRED_ASSET_IDS)',
      'g030_original_equipment_ownership_gate_failed',
      'PUBLIC_3D_PREVIEW_ADMITTED !== true',
      'G010_3D_GALLERY_CATEGORY_COUNTS=Object.freeze',
      'new GLTFLoader().parseAsync',
      'crypto.subtle.digest("SHA-256",bytes)')
    assert all(x in code for x in required)
    assert 'models.length!==91' in code
    assert not any(word in code for word in ("method: 'POST'","method:\"POST\"","/api/shop/buy","/api/player/inventory/equip"))
    assert "PUBLIC_3D_PREVIEW_ADMITTED: true" in (ROOT/"js/g009_formal9_rights_cleared_replacement_catalog.js").read_text()
    assert "PRODUCTION_ASSET_ADMISSION: false" in (ROOT/"js/g009_formal9_rights_cleared_replacement_catalog.js").read_text()


def test_unrestricted_full_turn_and_safe_zoom_are_wired_without_player_mutation():
    source=(ROOT/"js/g010_hero_3d_gallery.mjs").read_text(encoding="utf8")
    page=(ROOT/"hero.html").read_text(encoding="utf8")
    fixture=(ROOT/"tests/e2e/g010_3d_activation_fixture.html").read_text(encoding="utf8")
    for fragment in ("FULL_TURN_PIXELS = 720",
                     "const ROTATE_RAD_PER_PX = (Math.PI * 2) / FULL_TURN_PIXELS",
                     "function rotateFreely(dx, dy)",
                     "state.group.quaternion.premultiply",
                     "state.group.quaternion.normalize()",
                     "function pinchSpan()",
                     "zoomBy(state.pinchDistance/current)",
                     'canvas.addEventListener("wheel"',
                     "MIN_CAMERA_DISTANCE = 3.0, MAX_CAMERA_DISTANCE = 22.0",
                     "state.group?.quaternion.identity()",
                     "state.pointers.clear();state.pinchDistance = 0"):
        assert fragment in source,fragment
    assert "rotation.x=THREE.MathUtils.clamp" not in source
    for control in ("g010-3d-zoom-in","g010-3d-zoom-out","g010-3d-reset"):
        assert f'id="{control}"' in page
        assert f'id="{control}"' in fixture
    assert "上下左右 360° 自由旋轉" in page
    assert "PUBLIC_3D_PREVIEW_ADMITTED !== true" in source
    assert "G011_QA_MODE ? 63 : 71" in source
    assert not any(x in source for x in ("/api/shop/buy","/api/player/inventory/equip","/api/player/grant"))
