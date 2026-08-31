import hashlib
import json
import re
import subprocess
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_BASE = "16548803a62c9fc76a459cb247a026187e644c5c"
MANIFEST_PATH = ROOT / "docs" / "planning" / "art_003_batch_011_manifest.json"
PACK_PATH = ROOT / "docs" / "planning" / "art_003_batch_011_owner_visual_review_pack.md"

EXPECTED = [
    ("M110", "Dawnwing Serpent", "Z1", "art/monsters/M110_dawnwing_serpent.png", "8CE6A97421B1FEC08843D439C0BCBC70C70708DDBF246FDAD6B783DB0D8DAED7", 1024, 1536),
    ("M111", "Starshard Rhino", "Z9", "art/monsters/M111_starshard_rhino.png", "8797C8B3C6C03F05E487FA6E32171FB9F9928054231617E557FA2C1090329469", 1536, 1024),
    ("M113", "Timeworn Stone Turtle", "Z10", "art/monsters/M113_timeworn_stone_turtle.png", "C9DF5490326B94CD81F7AB959CDB36B7A702DC897F3036D0CF3C465C3241BA4F", 1536, 1024),
    ("M114", "Endgate Beast", "Z10", "art/monsters/M114_endgate_beast.png", "D5ED74E8B0107D103F7BC058E400D11FD88216D8C41FB32188BCF3A9EB8739A0", 1536, 1024),
    ("M115", "Ancient Bell Crawler", "Z10", "art/monsters/M115_ancient_bell_crawler.png", "C60476E4D531E4901F589955ED2479AB7655CEFFE901123D49127A6118085D0B", 1536, 1024),
    ("M116", "Ivorylight Beetle", "Z10", "art/monsters/M116_ivorylight_beetle.png", "5D2FEAEC1E8E7F1C31384D58476F35C72809B62C3C221AF0398DB1D203802245", 1536, 1024),
    ("M117", "Blacksand Hound", "Z10", "art/monsters/M117_blacksand_hound.png", "6F64B3152D4E45216C07D7B98946BBD8E68B432FFAD800065CC0401C78F5D50D", 1312, 1199),
    ("M118", "Relic Shellbeast", "Z10", "art/monsters/M118_relic_shellbeast.png", "F159A42E67BE06664B61DD96F2C690935003EE5E96A01360E9342CCA6BBB1DCF", 1536, 1024),
    ("M119", "Silent Tabletling", "Z10", "art/monsters/M119_silent_tabletling.png", "D732AC3BFD501B33A829CF28B53E08A036DBB83781C0BEDAB5521F4E98A97B64", 1214, 1295),
    ("M120", "Evergreen Rootbeast", "Z10", "art/monsters/M120_evergreen_rootbeast.png", "D57B6A24AD2374EA5C6E899A9AD119F4D416709727E18A88A49B67B7B1592E85", 1536, 1024),
]
EXPECTED_IDS = [row[0] for row in EXPECTED]
EXPECTED_PATHS = [row[3] for row in EXPECTED]
ADMISSION_PATHS = set(EXPECTED_PATHS) | {
    "docs/planning/art_003_batch_011_manifest.json",
    "docs/planning/art_003_batch_011_owner_visual_review_pack.md",
    "tests/test_art003_b11_production.py",
    "tests/test_art003_b11_r1_publication.py",
}


def read_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def git_succeeds(*args):
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def admission_base():
    """Use fresh canonical master for synthetic admissions, with a narrow
    historical fallback for validating the reviewed publication branch.
    """
    if git_succeeds("merge-base", "--is-ancestor", "origin/master", "HEAD"):
        return "origin/master"
    if git_succeeds("merge-base", "--is-ancestor", HISTORICAL_BASE, "HEAD"):
        return HISTORICAL_BASE
    raise AssertionError("no valid canonical or reviewed B11 admission base")


def test_b11_exact_identity_and_manifest():
    manifest = read_manifest()
    assert manifest["batch"] == "ART003_B11"
    assert manifest["expected_id_count"] == 10
    assert manifest["expected_ids"] == EXPECTED_IDS
    assert manifest["id_set_exact"] == "YES"
    entries = manifest["entries"]
    assert len(entries) == 10
    assert [entry["monster_id"] for entry in entries] == EXPECTED_IDS
    assert "M112" not in [entry["monster_id"] for entry in entries]
    for expected, entry in zip(EXPECTED, entries):
        mid, name, zone, path, sha, width, height = expected
        assert (entry["monster_id"], entry["canonical_name"], entry["zone"], entry["asset_path"], entry["sha256"], entry["width"], entry["height"]) == (mid, name, zone, path, sha, width, height)
        assert entry["owner_visual_review_status"] == "PASS"


def test_b11_png_technical_qa_and_unique_hashes():
    manifest = read_manifest()
    hashes = []
    for entry in manifest["entries"]:
        path = ROOT / entry["asset_path"]
        assert path.is_file() and path.stat().st_size > 0
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest().upper()
        hashes.append(digest)
        assert digest == entry["sha256"]
        with Image.open(path) as image:
            image.load()
            assert image.format == "PNG"
            assert image.mode == "RGBA"
            assert image.size == (entry["width"], entry["height"])
            alpha = image.getchannel("A")
            assert alpha.getextrema()[1] > 0
            assert alpha.getbbox() is not None
    assert len(hashes) == 10
    assert len(set(hashes)) == 10


def test_b11_planning_and_firewalls():
    manifest = read_manifest()
    assert manifest["planning_semantics"]["zone_distribution"] == {"Z1": 1, "Z9": 1, "Z10": 8}
    assert manifest["planning_semantics"]["f035_zone_assignment_mutated"] == "NO"
    assert manifest["planning_semantics"]["f035_zone_used_for_gameplay"] == "NO"
    assert manifest["planning_semantics"]["f036_batch_plan_mutated"] == "NO"
    assert all(value == "NO" for value in manifest["protection"].values())
    assert all(value == "NO" for value in manifest["runtime_firewall"].values())
    assert all(value == "NO" for value in manifest["production_firewall"].values())
    assert manifest["continuity"]["style_continuity"] == "PASS"
    assert manifest["continuity"]["silhouette_distinction"] == "PASS"
    assert manifest["continuity"]["identity_readability"] == "PASS"
    assert manifest["continuity"]["b11_internal_duplicate_count"] == 0
    assert manifest["continuity"]["prior_batch_identity_collision_count"] == 0


def test_review_pack_exact_order_and_owner_pass_gate():
    pack = PACK_PATH.read_text(encoding="utf-8")
    assert "OWNER_VISUAL_REVIEW_STATUS=PASS" in pack
    assert "Owner pass count: `10/10`" in pack
    assert "SOURCE_HEAD_PENDING_FIRST_B11_ASSET_COMMIT" not in pack
    ids = re.findall(r"^\|\s*\d+\s*\|\s*(M\d+)\s*\|", pack, flags=re.MULTILINE)
    assert ids == EXPECTED_IDS
    assert "M112" not in ids
    for _, _, _, path, sha, _, _ in EXPECTED:
        assert f"`{path}`" in pack
        assert sha in pack
        assert f"../../{path}" in pack


def test_exact_git_scope_and_source_head_bytes():
    manifest = read_manifest()
    source_head = manifest["source_head"]
    assert len(source_head) == 40
    assert git("cat-file", "-e", f"{source_head}^{{commit}}") == ""
    changed = set(git("diff", "--name-only", admission_base(), "HEAD").splitlines())
    assert changed == ADMISSION_PATHS
    assert git("status", "--short", "--untracked-files=all") == ""
    for _, _, _, path, _, _, _ in EXPECTED:
        committed = subprocess.check_output(["git", "show", f"{source_head}:{path}"], cwd=ROOT)
        assert committed == (ROOT / path).read_bytes()


def test_owner_gate_is_pass_and_no_m112_asset_exists():
    manifest = read_manifest()
    assert manifest["owner_gate"] == {
        "owner_visual_review_status": "PASS",
        "owner_pass_count": "10/10",
        "owner_rejected_ids": [],
        "visual_rework_required": "NO",
        "ready_for_owner_visual_review": "YES",
        "self_approval": "NO",
    }
    assert not any((ROOT / "art" / "monsters").glob("M112_*.png"))
