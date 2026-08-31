"""Focused ART003 B06 Owner-pass freeze and canonical publication checks."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from tests.art003_admission_scope import ART003_B09_SCOPE_TIP, changed_paths as admission_changed_paths


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "planning" / "art_003_batch_006_manifest.json"
REVIEW_PACK_PATH = ROOT / "docs" / "planning" / "art_003_batch_006_owner_visual_review_pack.md"
BASE_SHA = "edc1b51b45fa96a52f90bf363b7208cc99afbc22"
F039_BASE_HEAD = "c1a55daebc411df46ca4bbfef6c0b814c813ec73"
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
F043_B09_ADMISSION_FILES = {
    "art/monsters/M089_steelfang_hyena.png",
    "art/monsters/M090_battlement_lizard.png",
    "art/monsters/M091_smokescreen_weasel.png",
    "art/monsters/M092_ironwheel_rhino.png",
    "art/monsters/M093_beacon_scorpion.png",
    "art/monsters/M094_shieldshell_crab.png",
    "art/monsters/M095_obsidian_automaton.png",
    "art/monsters/M096_wallbreak_bear.png",
    "art/monsters/M097_scout_hawkbeast.png",
    "art/monsters/M099_aurora_serpent.png",
    "docs/planning/art_003_batch_009_manifest.json",
    "docs/planning/art_003_batch_009_owner_visual_review_pack.md",
    "tests/test_art003_b09_r1_publication.py",
}
CURRENT_ORIGIN_MASTER = "dc5728304a21249c38cd0c234ec4791247ca7fe9"
CURRENT_ORIGIN_MASTER_TREE = "36b2062cd6b8eea68a1e88421a4b56685d9560de"
SOURCE_BRANCH = "codex/art003-b06-m056-m066-canonical-monster-art-production"
F035_HEAD = "195f3376e107559817e054476b076e471c211731"
F035_ASSIGNMENT_SHA256 = "49e704f0c9935056c5614e91feff28d4775c6f98d4b38f1b068639f7d72d5e00"
F036_HEAD = "36eec98e972e5ed5e40acda83795ac1569e6eb1e"
B01_HEAD = "0b2f4c7ec65f845918bd96a2daec21551d27ff34"
B02_SOURCE_HEAD = "d3ccac1565b6c5bbe3f357164777f256136d2dc2"
B02_PUBLICATION_HEAD = "bc729d5bcc21a36e90724c921115c2e51f1efdcd"
B03_R1_HEAD = "701d4de5992ccf008b4071ee0de0c0cfcbc1382d"
B04_R1_HEAD = "acdeed171dc49f0eacae9c49cd9a2db299bd0125"
M022_PATH = "assets/monsters/orc_grunt_chibi.png"

IDS = ["M056", "M057", "M059", "M060", "M061", "M062", "M063", "M064", "M065", "M066"]
NAMES = {
    "M056": "Mudplate Armadillo", "M057": "Drumface Tortoise", "M059": "Lava-wing Drake",
    "M060": "Crystalhorn Lizard", "M061": "Cloudclaw Gryphon", "M062": "Sparkscale Gecko",
    "M063": "Basalt Shellbeast", "M064": "Windspine Serpent", "M065": "Ember-tail Foxdragon",
    "M066": "Cliffskip Goat",
}
ZONES = {"M056": "Z5", "M057": "Z5", "M059": "Z6", "M060": "Z3", "M061": "Z6", "M062": "Z6", "M063": "Z6", "M064": "Z6", "M065": "Z6", "M066": "Z6"}
SLUGS = {
    "M056": "mudplate_armadillo", "M057": "drumface_tortoise", "M059": "lava_wing_drake",
    "M060": "crystalhorn_lizard", "M061": "cloudclaw_gryphon", "M062": "sparkscale_gecko",
    "M063": "basalt_shellbeast", "M064": "windspine_serpent", "M065": "ember_tail_foxdragon",
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
    return admission_changed_paths(canonical_tip=ART003_B09_SCOPE_TIP, candidate_base=F039_BASE_HEAD) - F041_B08_ADMISSION_FILES - F043_B09_ADMISSION_FILES


def test_b06_owner_pass_exact_set_and_manifest() -> None:
    data = _manifest()
    rows = data["assets"]
    assert [row["M_ID"] for row in rows] == IDS
    assert [row["CANONICAL_NAME"] for row in rows] == [NAMES[mid] for mid in IDS]
    assert [row["F035_ZONE"] for row in rows] == [ZONES[mid] for mid in IDS]
    assert len(rows) == 10
    assert len({row["M_ID"] for row in rows}) == 10
    assert data["id_set"]["B06_ID_COUNT"] == 10
    assert data["id_set"]["B06_ID_SET_EXACT"] == "YES"
    assert data["id_set"]["EXPECTED_ID_SET"] == IDS
    assert data["id_set"]["M058_INCLUDED"] == "NO"
    assert data["id_set"]["UNEXPECTED_MONSTER_IDS"] == 0
    assert data["authoritative_lineage"]["B06_SOURCE_HEAD"] == BASE_SHA
    assert data["authoritative_lineage"]["B06_SOURCE_BRANCH"] == SOURCE_BRANCH
    assert data["authoritative_lineage"]["B06_SOURCE_HEAD_AVAILABLE"] == "YES"
    assert data["authoritative_lineage"]["B06_REMOTE_HEAD_EXACT"] == "YES"
    assert data["authoritative_lineage"]["F035_HEAD"] == F035_HEAD
    assert data["authoritative_lineage"]["F035_ASSIGNMENT_SHA256"] == F035_ASSIGNMENT_SHA256
    assert data["authoritative_lineage"]["F036_HEAD"] == F036_HEAD


def test_owner_approved_hash_lock_and_byte_identity() -> None:
    data = _manifest()
    hashes = []
    for row in data["assets"]:
        path = ROOT / row["FINAL_ASSET_PATH"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        hashes.append(digest)
        assert digest == EXPECTED_HASHES[row["M_ID"]]
        assert digest == row["SHA256"] == row["OWNER_APPROVED_SHA256"] == row["PUBLISHED_SHA256"]
        assert row["source_head"] == row["SOURCE_HEAD"] == BASE_SHA
        assert row["review_status"] == "PASS"
        assert row["owner_visual_review_status"] == "PASS"
        assert row["OWNER_REVIEW_STATUS"] == "PASS"
        assert row["OWNER_VISUAL_REVIEW_STATUS"] == "PASS"
        assert row["PRODUCTION_STATUS"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
        assert row["CANONICAL_ART_STATUS"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
        assert row["RUNTIME_MAPPING_STATUS"] == "NOT_MAPPED"
        assert _blob(BASE_SHA, row["FINAL_ASSET_PATH"]) == _blob("HEAD", row["FINAL_ASSET_PATH"])
    assert len(hashes) == 10
    assert len(set(hashes)) == 10
    assert data["owner_review"]["OWNER_APPROVED_HASH_MATCH_COUNT"] == 10
    assert data["owner_review"]["OWNER_APPROVED_BYTES_MATCH"] == "YES"
    assert data["byte_freeze"] == {
        "OWNER_APPROVED_HASH_MATCH_COUNT": 10,
        "OWNER_APPROVED_BYTES_MATCH": "YES",
        "PIXEL_MUTATION": "NO",
        "BYTE_MUTATION": "NO",
        "IMAGE_REGENERATION": "NO",
        "REENCODING": "NO",
        "RESIZING": "NO",
    }
    assert data["protected_lineages"]["OWNER_APPROVED_HASH_MATCH_COUNT"] == 10
    assert data["protected_lineages"]["OWNER_APPROVED_BYTES_MATCH"] == "YES"


def test_canonical_publication_state_and_owner_gate() -> None:
    data = _manifest()
    assert data["status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
    assert data["canonical_art_status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
    assert data["owner_visual_review_status"] == "PASS"
    assert data["owner_pass_count"] == "10/10"
    assert data["owner_review"]["OWNER_VISUAL_REVIEW_STATUS"] == "PASS"
    assert data["owner_review"]["OWNER_PASS_COUNT"] == "10/10"
    assert data["owner_review"]["OWNER_REVISION_REQUIRED"] == "NO"
    assert data["owner_review"]["REVISE_COUNT"] == 0
    assert data["owner_review"]["REJECT_COUNT"] == 0
    assert data["protected_lineages"]["CANONICAL_ART_PUBLISHED_COUNT"] == 10
    assert data["protected_lineages"]["CANONICAL_ART_ID_SET_EXACT"] == "YES"
    assert data["result"]["classification"] == "PASS_ART003_B06_R1_OWNER_PASS_FREEZE_AND_CANONICAL_ART_PUBLICATION"
    assert data["result"]["ART003_B06_CANONICAL_ART_STATUS"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
    assert data["result"]["READY_FOR_NEXT_ART_BATCH"] == "YES"


def test_fresh_master_and_planning_zone_protection() -> None:
    data = _manifest()
    lineage = data["authoritative_lineage"]
    assert lineage["CURRENT_CANONICAL_MASTER"] == CURRENT_ORIGIN_MASTER
    assert lineage["CURRENT_CANONICAL_MASTER_TREE"] == CURRENT_ORIGIN_MASTER_TREE
    assert lineage["FRESH_MASTER_RECONCILIATION"] == "PASS"
    assert lineage["ART_GOVERNANCE_CONFLICT"] == "NO"
    planning = data["planning_semantics"]
    assert planning["B06_F035_ZONE_DISTRIBUTION"] == {"Z3": 1, "Z5": 2, "Z6": 7}
    assert Counter(row["F035_ZONE"] for row in data["assets"]) == Counter({"Z3": 1, "Z5": 2, "Z6": 7})
    assert planning["F035_ZONE_ASSIGNMENT_MUTATED"] == "NO"
    assert planning["F035_ZONE_USED_FOR_GAMEPLAY"] == "NO"
    assert planning["F036_BATCH_PLAN_MUTATED"] == "NO"
    assert planning["RUNTIME_ZONE_MAPPING_CHANGED"] == "NO"
    assert planning["COMBAT_ZONE_AUTHORITY_CHANGED"] == "NO"


def test_prior_art_and_m022_are_byte_protected() -> None:
    changed = _changed_paths()
    assert not any(path.startswith("art/monsters/") for path in changed)
    assert not any(path.startswith("assets/monsters/") for path in changed)
    # B01/B02 are preserved on their historical canonical refs.  The B06
    # source lineage does not carry those legacy paths, so compare the refs
    # that contain them instead of requiring them in the current tree.
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
        assert _blob(F039_BASE_HEAD, path) == _blob("HEAD", path)
    assert _blob(F039_BASE_HEAD, M022_PATH) == _blob("HEAD", M022_PATH)
    for key in ("B01_ASSETS_CHANGED", "B02_ASSETS_CHANGED", "B03_ASSETS_CHANGED", "B04_ASSETS_CHANGED", "B05_ASSETS_CHANGED", "M022_CHANGED", "M022_REGENERATED", "M022_RUNTIME_REFERENCE_CHANGED"):
        assert _manifest()["protected_lineages"][key] == "NO"


def test_runtime_release_and_cross_lane_firewalls() -> None:
    data = _manifest()
    required_no = (
        "APP_PY_CHANGED", "RUNTIME_SOURCE_CHANGED", "GAMEPLAY_SOURCE_CHANGED", "MONSTER_STATS_CHANGED",
        "COMBAT_MAPPING_CHANGED", "HP_CHANGED", "ATK_CHANGED", "DROP_CHANGED", "REWARD_CHANGED",
        "MONSTER_CATALOG_RUNTIME_MAPPING_CHANGED", "MONSTER_CATALOG_GAMEPLAY_AUTHORITY_CHANGED",
        "F009_ENABLED", "F009_CHANGED", "BOSS_INCLUDED", "LORD_INCLUDED", "B063_SCOPE_TOUCHED",
        "B064_SCOPE_TOUCHED", "B065_SCOPE_TOUCHED", "B067_SCOPE_TOUCHED", "B069_SCOPE_TOUCHED",
        "B070_SCOPE_TOUCHED", "B071_SCOPE_TOUCHED", "B071A_SCOPE_TOUCHED", "B071B_SCOPE_TOUCHED",
        "A049_SCOPE_TOUCHED", "E053_SCOPE_TOUCHED", "LC_SCOPE_TOUCHED", "GENESIS_BOOTSTRAP_EXECUTED",
        "SCHEMA_CHANGED", "MIGRATION_CHANGED", "DATA_CHANGED", "PRODUCTION_QUERY", "PRODUCTION_MUTATION",
        "PRODUCTION_DB_MIGRATION", "DEPLOY", "ROLLBACK", "ART003_B06_INCLUDED_IN_CURRENT_RPG_V1_DEPLOYMENT",
    )
    assert all(data["firewalls"][key] == "NO" for key in required_no)
    assert all(row["RUNTIME_MAPPING_STATUS"] == "NOT_MAPPED" for row in data["assets"])
    assert data["firewalls"]["SECRET_KEY_TOUCHED"] == "NO"


def test_publication_pack_and_manifest_are_complete() -> None:
    data = _manifest()
    pack = REVIEW_PACK_PATH.read_text(encoding="utf-8")
    assert data["owner_review"]["OWNER_REVIEW_PACK_ENTRY_COUNT"] == 10
    assert data["owner_review"]["OWNER_REVIEW_PACK_ID_SET_EXACT"] == "YES"
    assert data["owner_review"]["REVIEW_PACK_BYTES_EQUAL_FINAL_ASSETS"] == "YES"
    assert "Owner visual review status: **PASS** (`10/10`)." in pack
    assert "Owner revision required: **NO**" in pack
    headings = re.findall(r"### (M\d+) — [^\n]+", pack)
    assert headings == IDS
    image_paths = re.findall(r"!\[[^\]]+\]\((\.\./\.\./art/monsters/[^)]+\.png)\)", pack)
    assert image_paths == [f"../../{row['FINAL_ASSET_PATH']}" for row in data["assets"]]
    assert len(image_paths) == 10
    for row in data["assets"]:
        assert f"### {row['M_ID']} — {row['CANONICAL_NAME']}" in pack
        assert f"![{row['M_ID']} {row['CANONICAL_NAME']}]" in pack
        assert row["SHA256"] in pack
        assert f"| {row['M_ID']} | {row['CANONICAL_NAME']} | {row['F035_ZONE']} |" in pack
        assert "| PASS | PASS |" in pack


def test_only_publication_scope_changed_and_no_secret() -> None:
    changed = _changed_paths()
    assert changed <= F039_R1_TEST_FILES
    assert "secret_key.txt" not in changed
    assert not any(path.startswith("art/monsters/") for path in changed)
