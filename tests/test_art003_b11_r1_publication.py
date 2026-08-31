import hashlib
import json
import re
import subprocess
from pathlib import Path

from tests.art003_admission_scope import (
    ART003_B11_SCOPE_TIP,
    changed_paths as admission_changed_paths,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_HEAD = "36ff4d411443bd3a5d1728054bc5ca82ca8ea6bd"
HISTORICAL_BASE = "16548803a62c9fc76a459cb247a026187e644c5c"
EXPECTED = [
    ("M110", "Dawnwing Serpent", "Z1", "art/monsters/M110_dawnwing_serpent.png", "8CE6A97421B1FEC08843D439C0BCBC70C70708DDBF246FDAD6B783DB0D8DAED7"),
    ("M111", "Starshard Rhino", "Z9", "art/monsters/M111_starshard_rhino.png", "8797C8B3C6C03F05E487FA6E32171FB9F9928054231617E557FA2C1090329469"),
    ("M113", "Timeworn Stone Turtle", "Z10", "art/monsters/M113_timeworn_stone_turtle.png", "C9DF5490326B94CD81F7AB959CDB36B7A702DC897F3036D0CF3C465C3241BA4F"),
    ("M114", "Endgate Beast", "Z10", "art/monsters/M114_endgate_beast.png", "D5ED74E8B0107D103F7BC058E400D11FD88216D8C41FB32188BCF3A9EB8739A0"),
    ("M115", "Ancient Bell Crawler", "Z10", "art/monsters/M115_ancient_bell_crawler.png", "C60476E4D531E4901F589955ED2479AB7655CEFFE901123D49127A6118085D0B"),
    ("M116", "Ivorylight Beetle", "Z10", "art/monsters/M116_ivorylight_beetle.png", "5D2FEAEC1E8E7F1C31384D58476F35C72809B62C3C221AF0398DB1D203802245"),
    ("M117", "Blacksand Hound", "Z10", "art/monsters/M117_blacksand_hound.png", "6F64B3152D4E45216C07D7B98946BBD8E68B432FFAD800065CC0401C78F5D50D"),
    ("M118", "Relic Shellbeast", "Z10", "art/monsters/M118_relic_shellbeast.png", "F159A42E67BE06664B61DD96F2C690935003EE5E96A01360E9342CCA6BBB1DCF"),
    ("M119", "Silent Tabletling", "Z10", "art/monsters/M119_silent_tabletling.png", "D732AC3BFD501B33A829CF28B53E08A036DBB83781C0BEDAB5521F4E98A97B64"),
    ("M120", "Evergreen Rootbeast", "Z10", "art/monsters/M120_evergreen_rootbeast.png", "D57B6A24AD2374EA5C6E899A9AD119F4D416709727E18A88A49B67B7B1592E85"),
]
EXPECTED_IDS = [row[0] for row in EXPECTED]
EXPECTED_PATHS = [row[3] for row in EXPECTED]
ADMISSION_PATHS = set(EXPECTED_PATHS) | {
    "docs/planning/art_003_batch_011_manifest.json",
    "docs/planning/art_003_batch_011_owner_visual_review_pack.md",
    "tests/test_art003_b11_production.py",
    "tests/test_art003_b11_r1_publication.py",
}


def manifest():
    return json.loads((ROOT / "docs/planning/art_003_batch_011_manifest.json").read_text(encoding="utf-8"))


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_owner_pass_exact_set_and_hash_lock():
    data = manifest()
    assert data["batch"] == "ART003_B11"
    assert data["source_head"] == SOURCE_HEAD
    assert data["expected_ids"] == EXPECTED_IDS
    assert data["id_set_exact"] == "YES"
    entries = data["entries"]
    assert len(entries) == 10
    assert [entry["monster_id"] for entry in entries] == EXPECTED_IDS
    assert "M112" not in [entry["monster_id"] for entry in entries]
    for expected, entry in zip(EXPECTED, entries):
        mid, name, zone, path, sha = expected
        assert (entry["monster_id"], entry["canonical_name"], entry["zone"], entry["asset_path"], entry["sha256"]) == (mid, name, zone, path, sha)
        assert entry["owner_visual_review_status"] == "PASS"
        assert entry["publication_status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
        assert entry["source_head"] == SOURCE_HEAD
        actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest().upper()
        assert actual == sha
    assert len({entry["sha256"] for entry in entries}) == 10


def test_publication_and_owner_gate_metadata():
    data = manifest()
    assert data["status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
    assert data["owner_visual_review_status"] == "PASS"
    assert data["owner_pass_count"] == "10/10"
    assert data["visual_rework_required"] == "NO"
    assert data["publication"] == {
        "canonical_art_status": "OWNER_PASS_FROZEN_AND_PUBLISHED",
        "canonical_art_published_count": 10,
        "canonical_art_id_set_exact": "YES",
        "owner_hash_match_count": 10,
        "owner_hash_drift_count": 0,
        "owner_approved_bytes_match": "YES",
        "pixel_mutation": "NO",
        "byte_mutation": "NO",
        "image_regeneration": "NO",
        "reencoding": "NO",
        "resizing": "NO",
        "m112_included": "NO",
    }
    assert data["owner_gate"]["owner_visual_review_status"] == "PASS"
    assert data["owner_gate"]["owner_pass_count"] == "10/10"
    assert data["owner_gate"]["owner_rejected_ids"] == []
    assert data["owner_gate"]["visual_rework_required"] == "NO"


def test_planning_authority_and_f035_f036_validation():
    data = manifest()
    assert data["f035"]["head"] == "195f3376e107559817e054476b076e471c211731"
    assert data["f035"]["assignment_sha256"] == "49e704f0c9935056c5614e91feff28d4775c6f98d4b38f1b068639f7d72d5e00"
    assert data["f036"]["head"] == "36eec98e972e5ed5e40acda83795ac1569e6eb1e"
    assert data["planning_semantics"]["zone_distribution"] == {"Z1": 1, "Z9": 1, "Z10": 8}
    assert data["planning_semantics"]["f035_zone_assignment_mutated"] == "NO"
    assert data["planning_semantics"]["f035_zone_used_for_gameplay"] == "NO"
    assert data["planning_semantics"]["f036_batch_plan_mutated"] == "NO"


def test_owner_review_pack_exact_pass_order():
    pack = (ROOT / "docs/planning/art_003_batch_011_owner_visual_review_pack.md").read_text(encoding="utf-8")
    assert "OWNER_VISUAL_REVIEW_STATUS=PASS" in pack
    assert "Owner pass count: `10/10`" in pack
    assert "Asset-bearing source head: `" + SOURCE_HEAD + "`" in pack
    ids = re.findall(r"^\|\s*\d+\s*\|\s*(M\d+)\s*\|", pack, flags=re.MULTILINE)
    assert ids == EXPECTED_IDS
    assert "M112" not in ids
    assert pack.count("Owner review: `PASS`") == 10
    assert pack.count("| PASS |") == 10
    for mid, _, _, path, sha in EXPECTED:
        assert mid in pack
        assert f"../../{path}" in pack
        assert sha in pack


def test_owner_approved_bytes_are_unchanged_from_source_head():
    data = manifest()
    for entry in data["entries"]:
        path = entry["asset_path"]
        committed = subprocess.check_output(["git", "show", f"{SOURCE_HEAD}:{path}"], cwd=ROOT)
        assert committed == (ROOT / path).read_bytes()
        assert hashlib.sha256(committed).hexdigest().upper() == entry["sha256"]


def test_publication_scope_has_no_prior_art_or_runtime_changes():
    changed = admission_changed_paths(
        canonical_tip=ART003_B11_SCOPE_TIP,
        candidate_base=HISTORICAL_BASE,
    )
    assert changed == ADMISSION_PATHS
    assert git("status", "--porcelain=v1", "--untracked-files=all") == ""
    assert data_paths_unchanged("art/monsters")


def data_paths_unchanged(prefix):
    changed = {
        path
        for path in admission_changed_paths(
            canonical_tip=ART003_B11_SCOPE_TIP,
            candidate_base=HISTORICAL_BASE,
        )
        if path.startswith(prefix)
    }
    return changed <= set(EXPECTED_PATHS)
