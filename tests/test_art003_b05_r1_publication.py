"""Focused ART003 B05-R1 Owner-pass freeze and publication checks."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "planning" / "art_003_batch_005_manifest.json"
REVIEW_PACK_PATH = ROOT / "docs" / "planning" / "art_003_batch_005_owner_visual_review_pack.md"
B05_SOURCE_HEAD = "72dcc5c4f693b9c1e456011de74df5608ce20bd1"
B05_SOURCE_BRANCH = "codex/art003-b05-m045-m055-canonical-monster-art-production"
BASE_SHA = B05_SOURCE_HEAD
F039_BASE_HEAD = "62cd841a3af78a66c4c5aba16cdfebb7814513da"
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
CURRENT_ORIGIN_MASTER = "3ace7c748b5f2b5b8b4d4ebb65827b6987ad1e6a"
CURRENT_ORIGIN_MASTER_TREE = "377afa276cc09a8c5786bdc5eecf4bf7d3201814"
B04_R1_HEAD = "acdeed171dc49f0eacae9c49cd9a2db299bd0125"
F035_HEAD = "195f3376e107559817e054476b076e471c211731"
F035_ASSIGNMENT_SHA256 = "49e704f0c9935056c5614e91feff28d4775c6f98d4b38f1b068639f7d72d5e00"
F036_HEAD = "36eec98e972e5ed5e40acda83795ac1569e6eb1e"
B01_HEAD = "0b2f4c7ec65f845918bd96a2daec21551d27ff34"
B02_SOURCE_HEAD = "d3ccac1565b6c5bbe3f357164777f256136d2dc2"
B02_PUBLICATION_HEAD = "bc729d5bcc21a36e90724c921115c2e51f1efdcd"
B03_R1_HEAD = "701d4de5992ccf008b4071ee0de0c0cfcbc1382d"
M022_PATH = "assets/monsters/orc_grunt_chibi.png"
IDS = ["M045", "M047", "M048", "M049", "M050", "M051", "M052", "M053", "M054", "M055"]
SLUGS = {
    "M045": "mosscap_sapling",
    "M047": "ember_drum_brute",
    "M048": "hide_shield_rhino",
    "M049": "redclay_ram",
    "M050": "war_drum_lizard",
    "M051": "feathercrest_hound",
    "M052": "mortar_mole",
    "M053": "copperring_boar",
    "M054": "campfire_skink",
    "M055": "banner_tail_bison",
}
NAMES = {
    "M045": "Mosscap Sapling",
    "M047": "Ember Drum Brute",
    "M048": "Hide-shield Rhino",
    "M049": "Redclay Ram",
    "M050": "War Drum Lizard",
    "M051": "Feathercrest Hound",
    "M052": "Mortar Mole",
    "M053": "Copperring Boar",
    "M054": "Campfire Skink",
    "M055": "Banner-tail Bison",
}
ZONES = {
    "M045": "Z4",
    "M047": "Z5",
    "M048": "Z5",
    "M049": "Z5",
    "M050": "Z5",
    "M051": "Z5",
    "M052": "Z5",
    "M053": "Z5",
    "M054": "Z5",
    "M055": "Z5",
}
EXPECTED_HASHES = {
    "M045": "F6C892BEB99EFE739C07B3211C9FDFB76E22286A4A29939AB5E3B43E13CAE23D",
    "M047": "E8AC3D50ADA48770C0E63243810A1D4D3C9373C72AD7DF44F96CE31685512544",
    "M048": "58939FBCB802DCD52C436686163FF5B3AC3CFEE4CB677C197E82212C95A0760B",
    "M049": "8939766175F0CDC9C7221F9726FD6842273361A5A355B9A31BEFA1B049061B37",
    "M050": "45F2401FE8FECA9A0B9A034358F5F7C380A2A1486FD1691DCDB09770FB3E5B4C",
    "M051": "1A77D71CAC2758B10C794004F1F98D15D819918935CC8C7000133A9A4AA77A56",
    "M052": "52754CA054F70E7C433B5F1D49A1319586444B8F2488F26A9AFA5D653787B697",
    "M053": "C78A7BD674E52AD151B6E2541B4CFA6E35FE4734F63CFC7B66350EEEDE61AD52",
    "M054": "A6E350097A9390CC6A156AAC3BEA004E17732E0535C1E84305D40B73A4B0519C",
    "M055": "E3B029FF892A0A7016D48D34F18B7F38887AABC8B38214E18D89A988C80A2870",
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


def test_b05_owner_pass_count_and_exact_id_set() -> None:
    data = _manifest()
    rows = data["assets"]
    assert [row["M_ID"] for row in rows] == IDS
    assert [row["CANONICAL_NAME"] for row in rows] == [NAMES[mid] for mid in IDS]
    assert data["id_set"]["B05_ID_COUNT"] == 10
    assert data["id_set"]["B05_ID_SET_EXACT"] == "YES"
    assert data["id_set"]["EXPECTED_ID_SET"] == IDS
    assert data["id_set"]["M046_INCLUDED"] == "NO"
    assert len({row["M_ID"] for row in rows}) == 10
    assert all(row["owner_visual_review_status"] == "PASS" for row in rows)
    assert all(row["OWNER_VISUAL_REVIEW_STATUS"] == "PASS" for row in rows)
    assert data["owner_authorization"]["OWNER_VISUAL_REVIEW_STATUS"] == "PASS"
    assert data["owner_authorization"]["OWNER_PASS_COUNT"] == "10/10"
    assert data["owner_authorization"]["OWNER_REVISION_REQUIRED"] == "NO"
    assert data["owner_review"]["OWNER_VISUAL_REVIEW_STATUS"] == "PASS"
    assert data["owner_review"]["OWNER_PASS_COUNT"] == "10/10"
    assert data["owner_review"]["OWNER_REVISION_REQUIRED"] == "NO"


def test_owner_approved_hash_lock_and_byte_identity() -> None:
    data = _manifest()
    hashes = []
    for row in data["assets"]:
        path_text = row["FINAL_ASSET_PATH"]
        path = ROOT / path_text
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest().upper()
        hashes.append(digest)
        assert digest == EXPECTED_HASHES[row["M_ID"]]
        assert digest == row["SHA256"] == row["OWNER_APPROVED_SHA256"] == row["PUBLISHED_SHA256"]
        assert row["source_head"] == B05_SOURCE_HEAD
        assert row["SOURCE_HEAD"] == B05_SOURCE_HEAD
        assert _blob(B05_SOURCE_HEAD, path_text) == _git("hash-object", path_text)
        with Image.open(path) as image:
            image.load()
            assert image.format == "PNG"
            assert image.mode == "RGBA"
            assert image.width == row["WIDTH"] == row["width"]
            assert image.height == row["HEIGHT"] == row["height"]
            assert min(image.size) >= 1024
            assert max(image.size) <= 1536
            assert not image.info
            alpha = image.getchannel("A")
            assert alpha.getbbox() is not None
            assert alpha.getextrema()[1] > 0
            left, top, right, bottom = alpha.point(lambda value: 255 if value > 16 else 0).getbbox()
            assert left >= 8
            assert top >= 8
            assert image.width - right >= 8
            assert image.height - bottom >= 8
    assert len(hashes) == 10
    assert len(set(hashes)) == 10
    assert data["protected_lineages"]["OWNER_APPROVED_HASH_MATCH_COUNT"] == 10
    assert data["protected_lineages"]["OWNER_APPROVED_BYTES_MATCH"] == "YES"
    assert data["protected_lineages"]["CANONICAL_ART_PUBLISHED_COUNT"] == 10
    assert data["protected_lineages"]["CANONICAL_ART_ID_SET_EXACT"] == "YES"


def test_fresh_master_and_source_lineage_lock() -> None:
    data = _manifest()
    lineage = data["authoritative_lineage"]
    assert lineage["B05_SOURCE_HEAD"] == B05_SOURCE_HEAD
    assert lineage["B05_SOURCE_BRANCH"] == B05_SOURCE_BRANCH
    assert lineage["B05_SOURCE_STATUS"] == "TECHNICAL_PASS_OWNER_VISUAL_PASS"
    assert lineage["B05_SOURCE_HEAD_AVAILABLE"] == "YES"
    assert lineage["B05_REMOTE_HEAD_EXACT"] == "YES"
    assert lineage["CURRENT_ORIGIN_MASTER"] == CURRENT_ORIGIN_MASTER
    assert lineage["CURRENT_ORIGIN_MASTER_TREE"] == CURRENT_ORIGIN_MASTER_TREE
    assert lineage["FRESH_MASTER_RECONCILIATION"] == "PASS"
    assert lineage["ART_GOVERNANCE_CONFLICT"] == "NO"
    assert lineage["B04_R1_HEAD"] == B04_R1_HEAD
    assert lineage["F035_HEAD"] == F035_HEAD
    assert lineage["F035_ASSIGNMENT_SHA256"] == F035_ASSIGNMENT_SHA256
    assert lineage["F036_HEAD"] == F036_HEAD


def test_prior_batches_and_m022_are_byte_protected() -> None:
    changed = _changed_paths()
    b05_paths = {f"art/monsters/{mid}_{SLUGS[mid]}.png" for mid in IDS}
    assert not changed.intersection(b05_paths)
    assert not any(path.startswith("art/monsters/M046") for path in changed)
    assert not changed.intersection(set(B01_PATHS + B02_PATHS))
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
    assert _blob(B04_R1_HEAD, M022_PATH) == _blob("HEAD", M022_PATH)
    data = _manifest()
    for key in (
        "B01_ASSETS_CHANGED", "B02_ASSETS_CHANGED", "B03_ASSETS_CHANGED", "B04_ASSETS_CHANGED",
        "M022_CHANGED", "M022_REGENERATED", "M022_RUNTIME_REFERENCE_CHANGED",
    ):
        assert data["protected_lineages"][key] == "NO"


def test_f035_f036_and_runtime_release_firewalls() -> None:
    data = _manifest()
    assert data["planning_semantics"]["B05_F035_ZONE_DISTRIBUTION"] == {"Z4": 1, "Z5": 9}
    assert data["planning_semantics"]["F035_ZONE_ASSIGNMENT_MUTATED"] == "NO"
    assert data["planning_semantics"]["F035_ZONE_USED_FOR_GAMEPLAY"] == "NO"
    assert data["planning_semantics"]["F036_BATCH_PLAN_MUTATED"] == "NO"
    assert Counter(row["F035_ZONE"] for row in data["assets"]) == Counter({"Z4": 1, "Z5": 9})
    changed = _changed_paths()
    forbidden_fragments = (
        "app.py", "catalog", "monster_catalog", "runtime", "battle", "combat", "f009",
        "schema", "migration", "release", "deploy", "b063", "B063", "B064", "B065",
        "B067", "B069", "B070", "Dockerfile",
    )
    assert all(not any(fragment in path for fragment in forbidden_fragments) for path in changed)
    for key in (
        "APP_PY_CHANGED", "RUNTIME_SOURCE_CHANGED", "GAMEPLAY_SOURCE_CHANGED", "MONSTER_STATS_CHANGED",
        "COMBAT_MAPPING_CHANGED", "HP_CHANGED", "ATK_CHANGED", "DROP_CHANGED", "REWARD_CHANGED",
        "MONSTER_CATALOG_RUNTIME_MAPPING_CHANGED", "MONSTER_CATALOG_GAMEPLAY_AUTHORITY_CHANGED",
        "E051_SCOPE_TOUCHED", "E052_SCOPE_TOUCHED", "E053_SCOPE_TOUCHED", "F009_ENABLED", "F009_CHANGED",
        "BOSS_INCLUDED", "LORD_INCLUDED", "B063_SCOPE_TOUCHED", "B064_SCOPE_TOUCHED", "B065_SCOPE_TOUCHED",
        "B067_SCOPE_TOUCHED", "B069_SCOPE_TOUCHED", "B070_SCOPE_TOUCHED",
        "ART003_B05_INCLUDED_IN_CURRENT_RPG_V1_DEPLOYMENT", "A049_SCOPE_TOUCHED", "LC_SCOPE_TOUCHED",
        "GENESIS_BOOTSTRAP_EXECUTED", "BOOTSTRAP_HOT_CHANGED", "SCHEMA_CHANGED", "MIGRATION_CHANGED",
        "DATA_CHANGED", "PRODUCTION_QUERY", "PRODUCTION_MUTATION", "PRODUCTION_DB_MIGRATION", "DEPLOY",
        "ROLLBACK",
    ):
        assert data["firewalls"][key] == "NO"


def test_manifest_and_owner_pack_are_complete_and_published() -> None:
    data = _manifest()
    pack = REVIEW_PACK_PATH.read_text(encoding="utf-8")
    assert data["status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
    assert data["canonical_art_status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
    assert data["owner_review"]["REVIEW_PACK_BYTES_EQUAL_FINAL_ASSETS"] == "YES"
    assert data["owner_review"]["review_matrix"] == "docs/planning/art_003_batch_005_owner_visual_review_pack.md"
    assert len(data["assets"]) == 10
    for row in data["assets"]:
        assert row["owner_visual_review_status"] == "PASS"
        assert row["canonical_art_status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
        assert row["publication_status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
        assert f"### {row['M_ID']} — {row['CANONICAL_NAME']}" in pack
        assert f"![{row['M_ID']} {row['CANONICAL_NAME']}]" in pack
        assert row["FINAL_ASSET_PATH"] in pack
        assert row["SHA256"] in pack
        assert f"| {row['M_ID']} | {row['CANONICAL_NAME']} | {row['F035_ZONE']} |" in pack
        assert f"| PASS | PASS |" in pack
    image_paths = set(re.findall(r"!\[[^\]]+\]\((\.\./\.\./art/monsters/[^)]+\.png)\)", pack))
    assert image_paths == {f"../../{row['FINAL_ASSET_PATH']}" for row in data["assets"]}
    assert "OWNER_VISUAL_REVIEW_STATUS=PASS" in pack
    assert "OWNER_PASS_COUNT=10/10" in pack
    assert "OWNER_REVISION_REQUIRED=NO" in pack


def test_only_publication_files_changed_and_secret_is_untouched() -> None:
    changed = _changed_paths()
    assert changed <= F039_R1_TEST_FILES
    assert "secret_key.txt" not in changed
    assert not any(path.startswith(("art/", "assets/")) for path in changed)
