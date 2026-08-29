"""Focused ART003 B04 production, identity, and authority-firewall checks."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "planning" / "art_003_batch_004_manifest.json"
REVIEW_PACK_PATH = ROOT / "docs" / "planning" / "art_003_batch_004_owner_visual_review_pack.md"
BASE_SHA = "701d4de5992ccf008b4071ee0de0c0cfcbc1382d"
B03_R1_HEAD = BASE_SHA
CURRENT_ORIGIN_MASTER = "c4568d5664f632d1cfa1e77ba39b00efa437f8a5"
CURRENT_ORIGIN_MASTER_TREE = "4046fdd9efcbab9db1b21b95478b17886cd60da0"
F035_HEAD = "195f3376e107559817e054476b076e471c211731"
F035_ASSIGNMENT_HASH = "49e704f0c9935056c5614e91feff28d4775c6f98d4b38f1b068639f7d72d5e00"
F036_HEAD = "36eec98e972e5ed5e40acda83795ac1569e6eb1e"
B01_HEAD = "0b2f4c7ec65f845918bd96a2daec21551d27ff34"
B02_SOURCE_HEAD = "d3ccac1565b6c5bbe3f357164777f256136d2dc2"
B02_PUBLICATION_HEAD = "bc729d5bcc21a36e90724c921115c2e51f1efdcd"
M022_PATH = "assets/monsters/orc_grunt_chibi.png"
IDS = [f"M{i:03d}" for i in range(35, 45)]
SLUGS = {
    "M035": "mist_tail_fox",
    "M036": "moonleaf_moth",
    "M037": "vineclaw_beast",
    "M038": "mossback_turtle",
    "M039": "dewdrop_spider",
    "M040": "twig_deer",
    "M041": "fogwhistle_frog",
    "M042": "bloomcrown_caterpillar",
    "M043": "shadowstep_cat",
    "M044": "hollowtree_cub",
}
NAMES = {
    "M035": "Mist-tail Fox",
    "M036": "Moonleaf Moth",
    "M037": "Vineclaw Beast",
    "M038": "Mossback Turtle",
    "M039": "Dewdrop Spider",
    "M040": "Twig Deer",
    "M041": "Fogwhistle Frog",
    "M042": "Bloomcrown Caterpillar",
    "M043": "Shadowstep Cat",
    "M044": "Hollowtree Cub",
}
OWNER_EXPECTED_HASHES = {
    "M035": "2139DD735189B7EE620470A0ADAB1A8B3171617CB9FF518310B4B85C4EF06B48",
    "M036": "1EEED20F6A18F602364DC62AB457920050B364EAA5760D789659D49E365F277A",
    "M037": "2B0FA587B9C1469AB4239E955D646B9635C8DC7C141E1B9E84D19757C70071F2",
    "M038": "8DBF1A3B3AC64159F42E1B3C1B27C67437A4B964254C9D96D3F4C320BDD896EF",
    "M039": "43AF530C228551E9F91E430A4159D0ECB91716DE356D41A1762AEC9A8AF36C2E",
    "M040": "0ADEE00D4858DFE66FFB28F7FA6DB70EBA3C91743513CE1168C3D1ABB73BC379",
    "M041": "418F3240A9F0E50DCAFEE11485B4471EFFC744C293963BFA397A916E2563C635",
    "M042": "1F054B4CF4B66758BC72A38713F92FB16F4ABF64D94114DAF657E2694D4EB4A2",
    "M043": "FC92B7D3A9FD343BDCF6AC065342913D1E8D596FC7E852B8627E036717695181",
    "M044": "920159D38C2A3C72575CD9B227D959FFF6C4F76E4E635CF95E061EB1956D736E",
}
B01_PATHS = [f"art/monsters/M{i:03d}_{slug}.png" for i, slug in {
    2: "gate_sprout", 3: "barrel_bouncer", 4: "strawhat_mole", 5: "chime_chick",
    6: "pebble_beetle", 7: "well_bubble", 8: "paddy_hopper", 9: "signpost_fox",
    10: "dumpling_gnome", 12: "mudball_otter",
}.items()]
B02_PATHS = [f"art/monsters/M{i:03d}_{slug}.png" for i, slug in {
    13: "bubble_frog", 14: "kite_dragonfly", 15: "grassseed_lamb", 16: "puddle_crab",
    17: "spring_grasshopper", 18: "jellyfish", 19: "parasol_funglet", 20: "whirl_vole",
    21: "dewdrop_fawn", 23: "coppercap_goblin",
}.items()]
B03_SLUGS = {
    "M024": "echo_bat",
    "M025": "pickaxe_moleworker",
    "M026": "fungus_lantern_imp",
    "M027": "rope_ladder_lizard",
    "M028": "ironbucket_beetle",
    "M029": "crevice_snake",
    "M030": "cartcap_crawler",
    "M031": "crystal_ore_gob",
    "M032": "cavern_slinger",
    "M033": "stalactite_tortoise",
}


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _blob(ref: str, path: str) -> str:
    return _git("rev-parse", f"{ref}:{path}")


def _changed_paths() -> set[str]:
    tracked = _git("diff", "--name-only", BASE_SHA)
    untracked = _git("ls-files", "--others", "--exclude-standard")
    return {line for line in (tracked + "\n" + untracked).splitlines() if line}


def test_b04_exact_id_set_and_manifest_completeness() -> None:
    data = _manifest()
    rows = data["assets"]
    assert [row["M_ID"] for row in rows] == IDS
    assert [row["CANONICAL_NAME"] for row in rows] == [NAMES[mid] for mid in IDS]
    assert data["id_set"]["B04_ID_COUNT"] == 10
    assert data["id_set"]["B04_ID_SET_EXACT"] == "YES"
    assert data["id_set"]["UNKNOWN_IDENTITY_COUNT"] == 0
    assert data["id_set"]["DUPLICATE_ID_COUNT"] == 0
    assert len(rows) == 10
    assert len({row["M_ID"] for row in rows}) == 10
    assert all(row["IDENTITY_SOURCE"] == "F035_ASSIGNMENT_ARTIFACT_AND_ART002_IDENTITY_BASELINE" for row in rows)
    assert all(row["EXISTING_REFERENCE_SOURCE"] == "F035_ASSIGNMENT_ARTIFACT_AND_ART002_IDENTITY_BASELINE" for row in rows)
    assert data["authoritative_lineage"]["F036_HEAD"] == F036_HEAD
    assert data["authoritative_lineage"]["F035_HEAD"] == F035_HEAD
    assert data["authoritative_lineage"]["F035_ASSIGNMENT_HASH"] == F035_ASSIGNMENT_HASH


def test_b04_assets_are_valid_unique_and_manifest_bound() -> None:
    data = _manifest()
    hashes = []
    for row in data["assets"]:
        path = ROOT / row["FINAL_ASSET_PATH"]
        assert path.exists()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest().upper()
        hashes.append(digest)
        assert digest == row["SHA256"]
        assert digest == OWNER_EXPECTED_HASHES[row["M_ID"]]
        with Image.open(path) as image:
            assert image.format == "PNG"
            image.load()
            assert image.mode == "RGBA"
            assert image.width == row["WIDTH"]
            assert image.height == row["HEIGHT"]
            assert min(image.size) >= 1024
            assert max(image.size) <= 1536
            assert not image.info
            alpha = image.getchannel("A")
            assert alpha.getbbox() is not None
            assert alpha.getextrema()[1] > 0
            threshold_bbox = alpha.point(lambda value: 255 if value > 16 else 0).getbbox()
            assert threshold_bbox is not None
            left, top, right, bottom = threshold_bbox
            assert left >= 8
            assert top >= 8
            assert image.width - right >= 8
            assert image.height - bottom >= 8
        assert row["F035_ZONE"] == "Z4"
        assert row["PLANNING_ZONE"] == "Z4"
        assert row["PRODUCTION_STATUS"] == "FINAL_PRODUCTION_CANDIDATE_READY_FOR_OWNER_REVIEW"
        assert row["OWNER_REVIEW_STATUS"] == "PENDING"
        assert row["RUNTIME_MAPPING_STATUS"] == "NOT_MAPPED"
        assert row["technical_qa"] == {
            "PNG_READABLE": "PASS",
            "NON_EMPTY_IMAGE": "PASS",
            "EXPECTED_COLOR_MODE": "PASS",
            "DIMENSION_POLICY": "PASS",
            "ALPHA_POLICY": "PASS",
            "NO_CORRUPT_ASSET": "PASS",
            "NO_DUPLICATE_FILE_HASH": "PASS",
        }
    assert len(hashes) == 10
    assert len(set(hashes)) == 10
    assert data["qa_summary"]["FINAL_ASSET_COUNT"] == 10
    assert data["qa_summary"]["UNIQUE_SHA256_COUNT"] == 10
    assert data["qa_summary"]["DUPLICATE_HASH_COUNT"] == 0
    assert data["continuity"]["DISTINCT_IDENTITY_COUNT"] == 10


def test_fresh_master_and_b03_lineage_are_locked() -> None:
    data = _manifest()
    reconciliation = data["fresh_master_reconciliation"]
    assert reconciliation["CURRENT_ORIGIN_MASTER"] == CURRENT_ORIGIN_MASTER
    assert reconciliation["CURRENT_ORIGIN_MASTER_TREE"] == CURRENT_ORIGIN_MASTER_TREE
    assert reconciliation["PRODUCTION_BASE_SHA"] == B03_R1_HEAD
    assert reconciliation["FRESH_MASTER_RECONCILIATION"] == "PASS"
    assert reconciliation["ART_GOVERNANCE_CONFLICT"] == "NO"
    assert data["authoritative_lineage"]["ART003_B03_R1_HEAD"] == B03_R1_HEAD
    assert data["authoritative_lineage"]["B03_R1_HEAD_AVAILABLE"] == "YES"
    assert data["authoritative_lineage"]["B03_R1_REMOTE_HEAD_EXACT"] == "YES"


def test_f035_zone_lock_and_planning_authority_firewall() -> None:
    data = _manifest()
    assert data["planning_semantics"]["B04_F035_ZONE_DISTRIBUTION"] == {"Z4": 10}
    assert data["planning_semantics"]["F035_ZONE_USED_FOR_GAMEPLAY"] == "NO"
    assert data["planning_semantics"]["RUNTIME_ZONE_MAPPING_CHANGED"] == "NO"
    assert data["planning_semantics"]["COMBAT_ZONE_AUTHORITY_CHANGED"] == "NO"
    assert data["planning_semantics"]["F035_ZONE_ASSIGNMENT_MUTATED"] == "NO"
    assert data["planning_semantics"]["F036_BATCH_PLAN_MUTATED"] == "NO"
    assert all(row["F035_ZONE"] == "Z4" for row in data["assets"])


def test_b01_b02_b03_and_m022_protection() -> None:
    changed = _changed_paths()
    protected = set(B01_PATHS + B02_PATHS)
    assert not changed.intersection(protected)
    assert not any(path.startswith("art/monsters/M022") for path in changed)
    for path in B01_PATHS:
        assert _blob(B01_HEAD, path) == _blob(B02_PUBLICATION_HEAD, path)
    for path in B02_PATHS:
        assert _blob(B02_SOURCE_HEAD, path) == _blob(B02_PUBLICATION_HEAD, path)
    b03_paths = [f"art/monsters/{mid}_{B03_SLUGS[mid]}.png" for mid in B03_SLUGS]
    for path in b03_paths:
        assert _blob(B03_R1_HEAD, path) == _blob("HEAD", path)
    assert _blob(B03_R1_HEAD, M022_PATH) == _blob("HEAD", M022_PATH)
    data = _manifest()
    for key in (
        "B01_ASSETS_CHANGED", "B02_ASSETS_CHANGED", "B03_ASSETS_CHANGED",
        "M022_CHANGED", "M022_REGENERATED", "M022_RUNTIME_REFERENCE_CHANGED",
    ):
        assert data["protected_lineages"][key] == "NO"


def test_runtime_catalog_gameplay_and_release_firewalls() -> None:
    data = _manifest()
    changed = _changed_paths()
    forbidden_fragments = (
        "app.py", "catalog", "monster_catalog", "runtime", "battle", "combat", "f009",
        "schema", "migration", "release", "deploy", "b063", "B063", "B064", "Dockerfile",
    )
    assert all(not any(fragment in path for fragment in forbidden_fragments) for path in changed)
    assert all(row["RUNTIME_MAPPING_STATUS"] == "NOT_MAPPED" for row in data["assets"])
    for key in (
        "APP_PY_CHANGED", "RUNTIME_SOURCE_CHANGED", "GAMEPLAY_SOURCE_CHANGED",
        "MONSTER_STATS_CHANGED", "COMBAT_MAPPING_CHANGED", "HP_CHANGED", "ATK_CHANGED",
        "DROP_CHANGED", "REWARD_CHANGED", "MONSTER_CATALOG_RUNTIME_MAPPING_CHANGED",
        "MONSTER_CATALOG_GAMEPLAY_AUTHORITY_CHANGED", "E049_SCOPE_TOUCHED",
        "E051_SCOPE_TOUCHED", "E052_SCOPE_TOUCHED", "E053_SCOPE_TOUCHED",
        "F009_ENABLED", "F009_CHANGED", "BOSS_INCLUDED", "LORD_INCLUDED",
        "B063_SCOPE_TOUCHED", "B064_SCOPE_TOUCHED",
        "ART003_B04_INCLUDED_IN_CURRENT_RPG_V1_DEPLOYMENT", "A043_SCOPE_TOUCHED",
        "A046_SCOPE_TOUCHED", "A047_SCOPE_TOUCHED", "LC_SCOPE_TOUCHED",
        "GENESIS_BOOTSTRAP_EXECUTED", "SCHEMA_CHANGED", "MIGRATION_CHANGED",
        "DATA_CHANGED", "PRODUCTION_QUERY", "PRODUCTION_MUTATION", "DEPLOY",
    ):
        assert data["firewalls"][key] == "NO"


def test_owner_review_pack_is_exact_and_still_pending() -> None:
    data = _manifest()
    pack = REVIEW_PACK_PATH.read_text(encoding="utf-8")
    assert data["owner_review"]["OWNER_REVIEW_PACK_ENTRY_COUNT"] == 10
    assert data["owner_review"]["OWNER_REVIEW_PACK_ID_SET_EXACT"] == "YES"
    assert data["owner_review"]["OWNER_VISUAL_REVIEW_STATUS"] == "PENDING"
    assert data["owner_review"]["OWNER_PASS_COUNT"] == 0
    assert data["owner_review"]["REVIEW_PACK_BYTES_EQUAL_FINAL_ASSETS"] == "YES"
    for row in data["assets"]:
        assert f"{row['M_ID']} — {row['CANONICAL_NAME']}" in pack
        assert f"![{row['M_ID']} {row['CANONICAL_NAME']}]" in pack
        assert row["FINAL_ASSET_PATH"] in pack
        assert row["SHA256"] in pack
        assert f"| {row['M_ID']} | {row['CANONICAL_NAME']} | Z4 |" in pack
        assert "| PASS | PENDING |" in pack
        assert row["OWNER_REVIEW_STATUS"] == "PENDING"
    image_paths = set(re.findall(r"!\[[^\]]+\]\((\.\./\.\./art/monsters/[^)]+\.png)\)", pack))
    expected_paths = {f"../../{row['FINAL_ASSET_PATH']}" for row in data["assets"]}
    assert image_paths == expected_paths
    assert data["owner_review"]["review_matrix"] == "docs/planning/art_003_batch_004_owner_visual_review_pack.md"


def test_only_allowed_b04_files_changed_and_secret_is_untouched() -> None:
    changed = _changed_paths()
    allowed = {f"art/monsters/{mid}_{SLUGS[mid]}.png" for mid in IDS} | {
        "docs/planning/art_003_batch_004_manifest.json",
        "docs/planning/art_003_batch_004_owner_visual_review_pack.md",
        "tests/test_art003_b04_production.py",
    }
    assert changed <= allowed
    assert "secret_key.txt" not in changed
    assert len(changed.intersection({f"art/monsters/{mid}_{SLUGS[mid]}.png" for mid in IDS})) == 10
