"""Focused ART003 B06 production and authority-firewall checks."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "planning" / "art_003_batch_006_manifest.json"
REVIEW_PACK_PATH = ROOT / "docs" / "planning" / "art_003_batch_006_owner_visual_review_pack.md"
BASE_SHA = "ac3d1abecd8a552aaf38cb99fdd3677f77fc2e57"
F039_BASE_HEAD = "c83cd4077d87fab9274b3a09fd22ca2d43c5a89d"
F039_R1_TEST_FILES = {
    "tests/test_art003_b02_owner_pass_freeze_publication.py",
    "tests/test_art003_b03_production.py",
    "tests/test_art003_b04_production.py",
    "tests/test_art003_b05_production.py",
    "tests/test_art003_b05_r1_publication.py",
    "tests/test_art003_b06_production.py",
    "tests/test_art003_b06_r1_publication.py",
    "tests/test_art003_b07_production.py",
}
F041_B08_ADMISSION_FILES = {
    "art/monsters/M078_potion_gob.png",
    "art/monsters/M079_prism_gecko.png",
    "art/monsters/M080_gravity_crab.png",
    "art/monsters/M081_scrollback_turtle.png",
    "art/monsters/M082_astrolabe_beetle.png",
    "art/monsters/M083_cloudstep_ram.png",
    "art/monsters/M085_blackgate_hound.png",
    "art/monsters/M086_breakshield_beetle.png",
    "art/monsters/M087_bannerbreak_stonebeast.png",
    "art/monsters/M088_stringwing_bat.png",
    "docs/planning/art_003_batch_008_manifest.json",
    "docs/planning/art_003_batch_008_owner_visual_review_pack.md",
    "tests/test_art003_b08_production.py",
}
PUBLISHED_CANONICAL_MASTER = "dc5728304a21249c38cd0c234ec4791247ca7fe9"
PUBLISHED_CANONICAL_MASTER_TREE = "36b2062cd6b8eea68a1e88421a4b56685d9560de"
F035_HEAD = "195f3376e107559817e054476b076e471c211731"
F035_ASSIGNMENT_SHA256 = "49e704f0c9935056c5614e91feff28d4775c6f98d4b38f1b068639f7d72d5e00"
F036_HEAD = "36eec98e972e5ed5e40acda83795ac1569e6eb1e"
B01_HEAD = "0b2f4c7ec65f845918bd96a2daec21551d27ff34"
B02_SOURCE_HEAD = "d3ccac1565b6c5bbe3f357164777f256136d2dc2"
B02_PUBLICATION_HEAD = "bc729d5bcc21a36e90724c921115c2e51f1efdcd"
B03_R1_HEAD = "701d4de5992ccf008b4071ee0de0c0cfcbc1382d"
B04_R1_HEAD = "acdeed171dc49f0eacae9c49cd9a2db299bd0125"
B05_PUBLICATION_HEAD = BASE_SHA
M022_PATH = "assets/monsters/orc_grunt_chibi.png"

IDS = ["M056", "M057", "M059", "M060", "M061", "M062", "M063", "M064", "M065", "M066"]
NAMES = {
    "M056": "Mudplate Armadillo",
    "M057": "Drumface Tortoise",
    "M059": "Lava-wing Drake",
    "M060": "Crystalhorn Lizard",
    "M061": "Cloudclaw Gryphon",
    "M062": "Sparkscale Gecko",
    "M063": "Basalt Shellbeast",
    "M064": "Windspine Serpent",
    "M065": "Ember-tail Foxdragon",
    "M066": "Cliffskip Goat",
}
CONCEPTS = {
    "M056": "clay burrower",
    "M057": "clan tortoise",
    "M059": "lava drake",
    "M060": "crystal lizard",
    "M061": "sky gryphon",
    "M062": "spark gecko",
    "M063": "basalt beast",
    "M064": "wind serpent",
    "M065": "foxdragon",
    "M066": "cliff goat",
}
ZONES = {
    "M056": "Z5",
    "M057": "Z5",
    "M059": "Z6",
    "M060": "Z3",
    "M061": "Z6",
    "M062": "Z6",
    "M063": "Z6",
    "M064": "Z6",
    "M065": "Z6",
    "M066": "Z6",
}
SLUGS = {
    "M056": "mudplate_armadillo",
    "M057": "drumface_tortoise",
    "M059": "lava_wing_drake",
    "M060": "crystalhorn_lizard",
    "M061": "cloudclaw_gryphon",
    "M062": "sparkscale_gecko",
    "M063": "basalt_shellbeast",
    "M064": "windspine_serpent",
    "M065": "ember_tail_foxdragon",
    "M066": "cliffskip_goat",
}
EXPECTED_HASHES = {
    "M056": "06FBD5891FB6BB70F00679677F1DD1334E106F2934A522D5DB3758BCAC08E589",
    "M057": "62D492E76496168B747DAAC957825B1EE23C8ACB9FE09A7CBC59337B15EB2439",
    "M059": "C17BA3942280FAB2DF587BA78DA77673AFAE65BDED6B6618FA5AD2C5B86CDB2E",
    "M060": "B523807D9D4BEC9ED85298FD41E8EFB9C81E4C409DFF88CF40FBA14AC66753D5",
    "M061": "7A7C658757B7CB2F81A3BD549B375F49EC4D756D94FF36D8A58A991273EC872B",
    "M062": "71206DFB482138B723119D6E27A1F5CE013C467818BB1F09B0D7E604FF1C60B1",
    "M063": "28436C001B30C91B07AE51EB07D1DD3A63FF8E58CFAF922A3B725DDD3DDF2AFF",
    "M064": "7B6B4F9A4C9D1EC01527130C409541341CEED1AF1E72144DC80D01443CDCD63A",
    "M065": "E2332D28F2B5867A3949BFD7BCC321D81F12236219A700F2616B43E74E1900A4",
    "M066": "58A9AF404274347B16765C4D675F6D4559D31DC13A6DEEA058639A4AAE0E81E7",
}
B01_PATHS = [
    "art/monsters/M002_gate_sprout.png", "art/monsters/M003_barrel_bouncer.png",
    "art/monsters/M004_strawhat_mole.png", "art/monsters/M005_chime_chick.png",
    "art/monsters/M006_pebble_beetle.png", "art/monsters/M007_well_bubble.png",
    "art/monsters/M008_paddy_hopper.png", "art/monsters/M009_signpost_fox.png",
    "art/monsters/M010_dumpling_gnome.png", "art/monsters/M012_mudball_otter.png",
]
B02_PATHS = [
    "art/monsters/M013_bubble_frog.png", "art/monsters/M014_kite_dragonfly.png",
    "art/monsters/M015_grassseed_lamb.png", "art/monsters/M016_puddle_crab.png",
    "art/monsters/M017_spring_grasshopper.png", "art/monsters/M018_jellyfish.png",
    "art/monsters/M019_parasol_funglet.png", "art/monsters/M020_whirl_vole.png",
    "art/monsters/M021_dewdrop_fawn.png", "art/monsters/M023_coppercap_goblin.png",
]
B03_SLUGS = {
    "M024": "echo_bat", "M025": "pickaxe_moleworker", "M026": "fungus_lantern_imp",
    "M027": "rope_ladder_lizard", "M028": "ironbucket_beetle", "M029": "crevice_snake",
    "M030": "cartcap_crawler", "M031": "crystal_ore_gob", "M032": "cavern_slinger",
    "M033": "stalactite_tortoise",
}
B04_SLUGS = {
    "M035": "mist_tail_fox", "M036": "moonleaf_moth", "M037": "vineclaw_beast",
    "M038": "mossback_turtle", "M039": "dewdrop_spider", "M040": "twig_deer",
    "M041": "fogwhistle_frog", "M042": "bloomcrown_caterpillar", "M043": "shadowstep_cat",
    "M044": "hollowtree_cub",
}
B05_SLUGS = {
    "M045": "mosscap_sapling", "M047": "ember_drum_brute", "M048": "hide_shield_rhino",
    "M049": "redclay_ram", "M050": "war_drum_lizard", "M051": "feathercrest_hound",
    "M052": "mortar_mole", "M053": "copperring_boar", "M054": "campfire_skink",
    "M055": "banner_tail_bison",
}


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _blob(ref: str, path: str) -> str:
    return _git("rev-parse", f"{ref}:{path}")


def _changed_paths() -> set[str]:
    outputs = (
        _git("diff", "--name-only", F039_BASE_HEAD),
        _git("diff", "--cached", "--name-only", F039_BASE_HEAD),
        _git("ls-files", "--others", "--exclude-standard"),
    )
    return (
        {line.replace("\\", "/") for output in outputs for line in output.splitlines() if line}
        - F041_B08_ADMISSION_FILES
    )


def test_b06_exact_id_set_and_manifest_completeness() -> None:
    data = _manifest()
    rows = data["assets"]
    assert [row["M_ID"] for row in rows] == IDS
    assert [row["CANONICAL_NAME"] for row in rows] == [NAMES[mid] for mid in IDS]
    assert [row["F035_ZONE"] for row in rows] == [ZONES[mid] for mid in IDS]
    assert [row["CONCEPT"] for row in rows] == [CONCEPTS[mid] for mid in IDS]
    assert data["id_set"]["EXPECTED_ID_SET"] == IDS
    assert data["id_set"]["B06_ID_COUNT"] == 10
    assert data["id_set"]["B06_ID_SET_EXACT"] == "YES"
    assert data["id_set"]["M058_INCLUDED"] == "NO"
    assert data["id_set"]["UNEXPECTED_MONSTER_IDS"] == 0
    assert data["id_set"]["UNKNOWN_IDENTITY_COUNT"] == 0
    assert data["id_set"]["DUPLICATE_ID_COUNT"] == 0
    assert len(rows) == 10
    assert len({row["M_ID"] for row in rows}) == 10
    assert all(row["IDENTITY_SOURCE"] == "F035_ASSIGNMENT_ARTIFACT_AND_ART002_IDENTITY_BASELINE" for row in rows)
    assert all(row["ROLE"] == "NORMAL_MONSTER_ART_CONTENT_PLANNING_ONLY" for row in rows)
    assert data["authoritative_lineage"]["F035_HEAD"] == F035_HEAD
    assert data["authoritative_lineage"]["F035_ASSIGNMENT_SHA256"] == F035_ASSIGNMENT_SHA256
    assert data["authoritative_lineage"]["F036_HEAD"] == F036_HEAD


def test_b06_assets_are_valid_unique_and_manifest_bound() -> None:
    data = _manifest()
    hashes = []
    expected_technical_qa = {
        "PNG_READABLE": "PASS",
        "NON_EMPTY_IMAGE": "PASS",
        "EXPECTED_COLOR_MODE": "PASS",
        "DIMENSION_POLICY": "PASS",
        "ALPHA_POLICY": "PASS",
        "NO_CORRUPT_ASSET": "PASS",
        "NO_DUPLICATE_FILE_HASH": "PASS",
    }
    for row in data["assets"]:
        path = ROOT / row["FINAL_ASSET_PATH"]
        assert path.is_file()
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        hashes.append(digest)
        assert digest == row["SHA256"] == EXPECTED_HASHES[row["M_ID"]]
        assert row["asset_path"] == row["FINAL_ASSET_PATH"]
        with Image.open(path) as image:
            image.load()
            assert image.format == "PNG"
            assert image.mode == "RGBA"
            assert image.width == row["WIDTH"] == row["width"]
            assert image.height == row["HEIGHT"] == row["height"]
            assert 1024 <= min(image.size) <= 1536
            assert 1024 <= max(image.size) <= 1536
            assert not image.info
            alpha = image.getchannel("A")
            assert alpha.getbbox() is not None
            assert alpha.getextrema()[1] > 0
            bbox = alpha.point(lambda value: 255 if value > 16 else 0).getbbox()
            assert bbox is not None
            left, top, right, bottom = bbox
            assert left >= 8
            assert top >= 8
            assert image.width - right >= 8
            assert image.height - bottom >= 8
        assert row["PLANNING_ZONE"] == ZONES[row["M_ID"]]
        assert row["review_status"] == "PASS"
        assert row["OWNER_REVIEW_STATUS"] == "PASS"
        assert row["PRODUCTION_STATUS"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
        assert row["RUNTIME_MAPPING_STATUS"] == "NOT_MAPPED"
        assert row["technical_qa"] == expected_technical_qa
    assert len(hashes) == 10
    assert len(set(hashes)) == 10
    assert data["qa_summary"]["B06_ART_CANDIDATE_COUNT"] == 10
    assert data["qa_summary"]["PNG_READABLE_COUNT"] == "10/10"
    assert data["qa_summary"]["UNIQUE_SHA256_COUNT"] == 10
    assert data["qa_summary"]["DUPLICATE_HASH_COUNT"] == 0
    assert data["qa_summary"]["DUPLICATE_ASSET_COUNT"] == 0


def test_fresh_master_and_b05_lineage_are_locked() -> None:
    data = _manifest()
    lineage = data["authoritative_lineage"]
    # These fields are immutable publication provenance, not the live F039
    # admission branch's current origin/master identity.
    assert lineage["CURRENT_CANONICAL_MASTER"] == PUBLISHED_CANONICAL_MASTER
    assert lineage["CURRENT_CANONICAL_MASTER_TREE"] == PUBLISHED_CANONICAL_MASTER_TREE
    assert lineage["B05_CANONICAL_PUBLICATION_HEAD"] == B05_PUBLICATION_HEAD
    assert lineage["B05_STATUS"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
    assert lineage["PRODUCTION_BASE_SHA"] == BASE_SHA
    assert lineage["FRESH_MASTER_RECONCILIATION"] == "PASS"
    assert lineage["ART_GOVERNANCE_CONFLICT"] == "NO"


def test_f035_zone_lock_and_planning_authority_firewall() -> None:
    data = _manifest()
    assert data["planning_semantics"]["B06_F035_ZONE_DISTRIBUTION"] == {"Z3": 1, "Z5": 2, "Z6": 7}
    assert Counter(row["F035_ZONE"] for row in data["assets"]) == Counter({"Z3": 1, "Z5": 2, "Z6": 7})
    assert data["planning_semantics"]["F035_ZONE_ASSIGNMENT_MUTATED"] == "NO"
    assert data["planning_semantics"]["F035_ZONE_USED_FOR_GAMEPLAY"] == "NO"
    assert data["planning_semantics"]["F036_BATCH_PLAN_MUTATED"] == "NO"
    assert data["planning_semantics"]["F035_ROLE_AUTHORITY"] == "ART_CONTENT_PLANNING_ONLY"
    assert data["planning_semantics"]["RUNTIME_ZONE_MAPPING_CHANGED"] == "NO"
    assert data["planning_semantics"]["COMBAT_ZONE_AUTHORITY_CHANGED"] == "NO"


def test_b01_b02_b03_b04_b05_and_m022_protection() -> None:
    changed = _changed_paths()
    protected = set(B01_PATHS + B02_PATHS)
    assert not changed.intersection(protected)
    assert not any(path.startswith("art/monsters/M024_") for path in changed)
    assert not any(path.startswith("art/monsters/M035_") for path in changed)
    assert not any(path.startswith("art/monsters/M045_") for path in changed)
    assert not any(path.startswith("art/monsters/M058") for path in changed)
    for path in B01_PATHS:
        assert _blob(B01_HEAD, path) == _blob(B02_PUBLICATION_HEAD, path)
    for path in B02_PATHS:
        assert _blob(B02_SOURCE_HEAD, path) == _blob(B02_PUBLICATION_HEAD, path)
    for mid, slug in B03_SLUGS.items():
        path = f"art/monsters/{mid}_{slug}.png"
        assert _blob(B03_R1_HEAD, path) == _blob("HEAD", path)
    for mid, slug in B04_SLUGS.items():
        path = f"art/monsters/{mid}_{slug}.png"
        assert _blob(B04_R1_HEAD, path) == _blob("HEAD", path)
    for mid, slug in B05_SLUGS.items():
        path = f"art/monsters/{mid}_{slug}.png"
        assert _blob(B05_PUBLICATION_HEAD, path) == _blob("HEAD", path)
    assert _blob(B05_PUBLICATION_HEAD, M022_PATH) == _blob("HEAD", M022_PATH)
    for key in ("B01_ASSETS_CHANGED", "B02_ASSETS_CHANGED", "B03_ASSETS_CHANGED", "B04_ASSETS_CHANGED", "B05_ASSETS_CHANGED", "M022_CHANGED", "M022_REGENERATED", "M022_RUNTIME_REFERENCE_CHANGED"):
        assert _manifest()["protected_lineages"][key] == "NO"


def test_runtime_release_cross_lane_and_database_firewalls() -> None:
    data = _manifest()
    changed = _changed_paths()
    forbidden_fragments = (
        "app.py", "catalog", "monster_catalog", "runtime", "battle", "combat", "f009",
        "schema", "migration", "release", "deploy", "b063", "B063", "B064", "B065",
        "B067", "B069", "B070", "B071", "leaderboard", "companion", "Dockerfile",
    )
    assert all(not any(fragment in path for fragment in forbidden_fragments) for path in changed)
    assert all(row["RUNTIME_MAPPING_STATUS"] == "NOT_MAPPED" for row in data["assets"])
    required_no_keys = (
        "APP_PY_CHANGED", "RUNTIME_SOURCE_CHANGED", "GAMEPLAY_SOURCE_CHANGED", "MONSTER_STATS_CHANGED",
        "COMBAT_MAPPING_CHANGED", "HP_CHANGED", "ATK_CHANGED", "DROP_CHANGED", "REWARD_CHANGED",
        "MONSTER_CATALOG_RUNTIME_MAPPING_CHANGED", "MONSTER_CATALOG_GAMEPLAY_AUTHORITY_CHANGED",
        "F009_ENABLED", "F009_CHANGED", "BOSS_INCLUDED", "LORD_INCLUDED", "A049_SCOPE_TOUCHED",
        "E051_SCOPE_TOUCHED", "E052_SCOPE_TOUCHED", "E053_SCOPE_TOUCHED", "B063_SCOPE_TOUCHED",
        "B064_SCOPE_TOUCHED", "B065_SCOPE_TOUCHED", "B067_SCOPE_TOUCHED", "B069_SCOPE_TOUCHED",
        "B070_SCOPE_TOUCHED", "B071_SCOPE_TOUCHED", "ART003_B06_INCLUDED_IN_CURRENT_RPG_V1_DEPLOYMENT",
        "LC_SCOPE_TOUCHED", "LC_IDENTITY_WIRING_CHANGED", "GENESIS_BOOTSTRAP_EXECUTED",
        "BOOTSTRAP_HOT_CHANGED", "LEADERBOARD_SCOPE_TOUCHED", "COMPANION_SCOPE_TOUCHED",
        "PLAYER_APPEARANCE_AUTHORITY_CHANGED", "F035_ZONE_USED_FOR_GAMEPLAY", "RUNTIME_ZONE_MAPPING_CHANGED",
        "COMBAT_ZONE_AUTHORITY_CHANGED", "SCHEMA_CHANGED", "MIGRATION_CHANGED", "DATA_CHANGED",
        "PRODUCTION_QUERY", "PRODUCTION_MUTATION", "PRODUCTION_DB_MIGRATION", "DEPLOY", "ROLLBACK",
    )
    assert all(data["firewalls"][key] == "NO" for key in required_no_keys)


def test_owner_gate_and_review_pack_are_exact_and_published() -> None:
    data = _manifest()
    pack = REVIEW_PACK_PATH.read_text(encoding="utf-8")
    assert data["status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
    assert data["canonical_art_status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
    assert data["owner_review"]["OWNER_VISUAL_REVIEW_STATUS"] == "PASS"
    assert data["owner_review"]["OWNER_PASS_COUNT"] == "10/10"
    assert data["owner_review"]["OWNER_REVIEW_PACK_ENTRY_COUNT"] == 10
    assert data["owner_review"]["OWNER_REVIEW_PACK_ID_SET_EXACT"] == "YES"
    assert data["owner_review"]["REVIEW_PACK_BYTES_EQUAL_FINAL_ASSETS"] == "YES"
    assert "Owner visual review status: **PASS** (`10/10`)." in pack
    assert "OWNER_PASS" in pack
    assert "### M058" not in pack
    assert [re.search(r"### (M\d+)", heading).group(1) for heading in re.findall(r"### M\d+ — [^\n]+", pack)] == IDS
    image_paths = re.findall(r"!\[[^\]]+\]\((\.\./\.\./art/monsters/[^)]+\.png)\)", pack)
    expected_paths = [f"../../{row['FINAL_ASSET_PATH']}" for row in data["assets"]]
    assert image_paths == expected_paths
    assert len(image_paths) == 10
    for row in data["assets"]:
        assert f"### {row['M_ID']} — {row['CANONICAL_NAME']}" in pack
        assert f"![{row['M_ID']} {row['CANONICAL_NAME']}]" in pack
        assert row["FINAL_ASSET_PATH"] in pack
        assert row["SHA256"] in pack
        assert f"| {row['M_ID']} | {row['CANONICAL_NAME']} | {row['F035_ZONE']} |" in pack
        assert "| PASS | PASS |" in pack


def test_only_allowed_b06_files_changed_and_secret_is_untouched() -> None:
    changed = _changed_paths()
    assert changed <= F039_R1_TEST_FILES
    assert "secret_key.txt" not in changed
    assert not any(path.startswith(("art/", "assets/")) for path in changed)
