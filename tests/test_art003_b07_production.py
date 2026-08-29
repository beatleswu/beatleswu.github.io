"""Focused ART003 B07 production and review-gate checks."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "planning" / "art_003_batch_007_manifest.json"
REVIEW_PACK_PATH = ROOT / "docs" / "planning" / "art_003_batch_007_owner_visual_review_pack.md"
BASE_SHA = "89733f3985ef8fc526b27d843a52259cf7aeb5bd"
CURRENT_ORIGIN_MASTER = "dc5728304a21249c38cd0c234ec4791247ca7fe9"
CURRENT_ORIGIN_MASTER_TREE = "36b2062cd6b8eea68a1e88421a4b56685d9560de"
F035_HEAD = "195f3376e107559817e054476b076e471c211731"
F035_ASSIGNMENT_SHA256 = "49e704f0c9935056c5614e91feff28d4775c6f98d4b38f1b068639f7d72d5e00"
F036_HEAD = "36eec98e972e5ed5e40acda83795ac1569e6eb1e"

IDS = ["M067", "M068", "M069", "M070", "M072", "M073", "M074", "M075", "M076", "M077"]
NAMES = {
    "M067": "Sulfur Salamander",
    "M068": "Nestling Raptor",
    "M069": "Starflame Bat",
    "M070": "Molten Gold Centipede",
    "M072": "Pagefox",
    "M073": "Brass Golem",
    "M074": "Stardust Moth",
    "M075": "Inkwell Octopus",
    "M076": "Floating Bell Bug",
    "M077": "Rune Owl",
}
ZONES = {
    "M067": "Z6", "M068": "Z6", "M069": "Z6", "M070": "Z6",
    "M072": "Z7", "M073": "Z10", "M074": "Z7", "M075": "Z7",
    "M076": "Z7", "M077": "Z7",
}
SLUGS = {
    "M067": "sulfur_salamander",
    "M068": "nestling_raptor",
    "M069": "starflame_bat",
    "M070": "molten_gold_centipede",
    "M072": "pagefox",
    "M073": "brass_golem",
    "M074": "stardust_moth",
    "M075": "inkwell_octopus",
    "M076": "floating_bell_bug",
    "M077": "rune_owl",
}
CONCEPTS = {
    "M067": "sulfur salamander",
    "M068": "nest raptor",
    "M069": "sky bat",
    "M070": "lava crawler",
    "M072": "library fox",
    "M073": "tower construct",
    "M074": "spell moth",
    "M075": "ink familiar",
    "M076": "tower bell bug",
    "M077": "rune owl",
}
IDENTITY_SOURCE = "F035_ASSIGNMENT_ARTIFACT_AND_ART002_IDENTITY_BASELINE"


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


def test_b07_exact_identity_set_and_planning_authority() -> None:
    data = _manifest()
    rows = data["assets"]
    assert [row["monster_id"] for row in rows] == IDS
    assert [row["canonical_name"] for row in rows] == [NAMES[mid] for mid in IDS]
    assert [row["planning_zone"] for row in rows] == [ZONES[mid] for mid in IDS]
    assert [row["source_description"] for row in rows] == [CONCEPTS[mid] for mid in IDS]
    assert len(rows) == 10
    assert len({row["monster_id"] for row in rows}) == 10
    assert "M071" not in [row["monster_id"] for row in rows]
    assert data["batch"] == "ART003_B07"
    assert data["id_set"]["EXPECTED_ID_SET"] == IDS
    assert data["id_set"]["B07_ID_COUNT"] == 10
    assert data["id_set"]["B07_ID_SET_EXACT"] == "YES"
    assert data["id_set"]["M071_PRESENT"] == "NO"
    assert not list((ROOT / "art" / "monsters").glob("M071_*.png"))
    assert data["id_set"]["UNEXPECTED_MONSTER_IDS"] == 0
    assert data["id_set"]["UNKNOWN_IDENTITY_COUNT"] == 0
    assert data["id_set"]["DUPLICATE_ID_COUNT"] == 0
    lineage = data["authoritative_lineage"]
    assert lineage["CURRENT_ORIGIN_MASTER"] == CURRENT_ORIGIN_MASTER
    assert lineage["CURRENT_ORIGIN_MASTER_TREE"] == CURRENT_ORIGIN_MASTER_TREE
    assert lineage["PRODUCTION_BASE_SHA"] == BASE_SHA
    assert lineage["F035_HEAD"] == F035_HEAD
    assert lineage["F035_ASSIGNMENT_SHA256"] == F035_ASSIGNMENT_SHA256
    assert lineage["F036_HEAD"] == F036_HEAD
    assert lineage["FRESH_MASTER_RECONCILIATION"] == "PASS"
    assert lineage["ART_GOVERNANCE_CONFLICT"] == "NO"
    assert all(row["identity_source"] == IDENTITY_SOURCE for row in rows)


def test_b07_assets_are_readable_unique_and_manifest_complete() -> None:
    data = _manifest()
    hashes: list[str] = []
    for row in data["assets"]:
        path = ROOT / row["asset_path"]
        assert row["asset_path"] == f"art/monsters/{row['monster_id']}_{SLUGS[row['monster_id']]}.png"
        assert path.is_file()
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        hashes.append(digest)
        assert row["sha256"] == digest
        assert row["OWNER_APPROVED_SHA256"] == digest
        assert row["PUBLISHED_SHA256"] == digest
        assert row["source_head"] == "9bd33b9a0628f5983ec9b12afa1a882d4b1b6e69"
        assert row["owner_visual_review_status"] == "PASS"
        assert row["canonical_art_status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.mode == "RGBA"
            assert (image.width, image.height) == (row["width"], row["height"])
            assert image.getchannel("A").getbbox() is not None
    assert len(hashes) == 10
    assert len(set(hashes)) == 10
    assert data["qa_summary"]["B07_ART_CANDIDATE_COUNT"] == 10
    assert data["qa_summary"]["FINAL_ASSET_COUNT"] == 10
    assert data["qa_summary"]["PNG_READABLE_COUNT"] == "10/10"
    assert data["qa_summary"]["UNIQUE_SHA256_COUNT"] == 10
    assert data["qa_summary"]["DUPLICATE_HASH_COUNT"] == 0
    assert data["qa_summary"]["DUPLICATE_ASSET_COUNT"] == 0
    assert data["qa_summary"]["NO_DUPLICATE_FILE_BYTES"] == "YES"


def test_owner_gate_is_published() -> None:
    data = _manifest()
    assert data["status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
    assert data["canonical_art_status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
    assert data["owner_visual_review_status"] == "PASS"
    assert data["owner_pass_count"] == "10/10"
    assert data["owner_review"]["OWNER_VISUAL_REVIEW_STATUS"] == "PASS"
    assert data["owner_review"]["OWNER_PASS_COUNT"] == "10/10"
    assert data["owner_review"]["OWNER_REVISION_REQUIRED"] == "NO"
    assert data["owner_review"]["OWNER_REVIEW_PACK_ENTRY_COUNT"] == 10
    assert data["owner_review"]["OWNER_REVIEW_PACK_ID_SET_EXACT"] == "YES"
    assert data["result"]["classification"] == "PASS_ART003_B07_R1_OWNER_PASS_FREEZE_AND_CANONICAL_ART_PUBLICATION"
    assert data["result"]["OWNER_APPROVED_HASH_MATCH_COUNT"] == 10
    assert data["result"]["OWNER_APPROVED_BYTES_MATCH"] == "YES"
    assert data["result"]["CANONICAL_ART_PUBLISHED_COUNT"] == 10
    assert data["result"]["CANONICAL_ART_ID_SET_EXACT"] == "YES"
    assert data["result"]["READY_FOR_NEXT_ART_BATCH"] == "YES"
    assert data["result"]["NEXT_TASK"] == "ART003_B08_M078_M088_CANONICAL_MONSTER_ART_PRODUCTION_001"
    assert all(row["production_status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED" for row in data["assets"])
    assert all(row["review_status"] == "PASS" for row in data["assets"])


def test_f035_f036_zone_lock_and_visual_contract() -> None:
    data = _manifest()
    planning = data["planning_semantics"]
    assert planning["B07_F035_ZONE_DISTRIBUTION"] == {"Z6": 4, "Z7": 5, "Z10": 1}
    assert Counter(row["planning_zone"] for row in data["assets"]) == Counter({"Z6": 4, "Z7": 5, "Z10": 1})
    assert planning["F035_ZONE_ASSIGNMENT_MUTATED"] == "NO"
    assert planning["F035_ZONE_USED_FOR_GAMEPLAY"] == "NO"
    assert planning["F036_BATCH_PLAN_MUTATED"] == "NO"
    assert planning["F035_ROLE_AUTHORITY"] == "ART_CONTENT_PLANNING_ONLY"
    assert planning["RUNTIME_ZONE_MAPPING_CHANGED"] == "NO"
    continuity = data["continuity"]
    assert continuity["STYLE_CONTINUITY"] == "PASS"
    assert continuity["SILHOUETTE_DISTINCTION"] == "PASS"
    assert continuity["IDENTITY_READABILITY"] == "PASS"
    assert continuity["DISTINCT_IDENTITY_COUNT"] == 10
    assert continuity["BOSS_INCLUDED"] == "NO"
    assert continuity["LORD_INCLUDED"] == "NO"


def test_prior_art_and_m022_are_untouched() -> None:
    changed = _changed_paths()
    prior_paths = {
        f"art/monsters/{mid}_{slug}.png"
        for mid, slug in {
            "M024": "echo_bat", "M025": "pickaxe_moleworker", "M026": "fungus_lantern_imp",
            "M027": "rope_ladder_lizard", "M028": "ironbucket_beetle", "M029": "crevice_snake",
            "M030": "cartcap_crawler", "M031": "crystal_ore_gob", "M032": "cavern_slinger",
            "M033": "stalactite_tortoise", "M035": "mist_tail_fox", "M036": "moonleaf_moth",
            "M037": "vineclaw_beast", "M038": "mossback_turtle", "M039": "dewdrop_spider",
            "M040": "twig_deer", "M041": "fogwhistle_frog", "M042": "bloomcrown_caterpillar",
            "M043": "shadowstep_cat", "M044": "hollowtree_cub", "M045": "mosscap_sapling",
            "M047": "ember_drum_brute", "M048": "hide_shield_rhino", "M049": "redclay_ram",
            "M050": "war_drum_lizard", "M051": "feathercrest_hound", "M052": "mortar_mole",
            "M053": "copperring_boar", "M054": "campfire_skink", "M055": "banner_tail_bison",
            "M056": "mudplate_armadillo", "M057": "drumface_tortoise", "M059": "lava_wing_drake",
            "M060": "crystalhorn_lizard", "M061": "cloudclaw_gryphon", "M062": "sparkscale_gecko",
            "M063": "basalt_shellbeast", "M064": "windspine_serpent", "M065": "ember_tail_foxdragon",
            "M066": "cliffskip_goat",
        }.items()
    }
    assert not changed & prior_paths
    assert "assets/monsters/orc_grunt_chibi.png" not in changed
    assert _blob(BASE_SHA, "art/monsters/M024_echo_bat.png") == _blob("HEAD", "art/monsters/M024_echo_bat.png")
    assert _blob(BASE_SHA, "art/monsters/M066_cliffskip_goat.png") == _blob("HEAD", "art/monsters/M066_cliffskip_goat.png")
    assert _blob(BASE_SHA, "assets/monsters/orc_grunt_chibi.png") == _blob("HEAD", "assets/monsters/orc_grunt_chibi.png")
    protected = _manifest()["protected_lineages"]
    for key in ("B01_ASSETS_CHANGED", "B02_ASSETS_CHANGED", "B03_ASSETS_CHANGED", "B04_ASSETS_CHANGED", "B05_ASSETS_CHANGED", "B06_ASSETS_CHANGED", "M022_CHANGED"):
        assert protected[key] == "NO"


def test_runtime_release_economy_and_lc_firewalls() -> None:
    firewalls = _manifest()["firewalls"]
    required_no = (
        "APP_PY_CHANGED", "RUNTIME_SOURCE_CHANGED", "GAMEPLAY_SOURCE_CHANGED", "MONSTER_STATS_CHANGED",
        "COMBAT_MAPPING_CHANGED", "HP_CHANGED", "ATK_CHANGED", "DROP_CHANGED", "REWARD_CHANGED",
        "MONSTER_CATALOG_RUNTIME_MAPPING_CHANGED", "MONSTER_CATALOG_GAMEPLAY_AUTHORITY_CHANGED",
        "F009_ENABLED", "F009_CHANGED", "BOSS_INCLUDED", "LORD_INCLUDED", "B071_SCOPE_TOUCHED",
        "B071A_SCOPE_TOUCHED", "B071C_SCOPE_TOUCHED", "B071D_SCOPE_TOUCHED", "LC_SCOPE_TOUCHED", "LC019_SCOPE_TOUCHED",
        "GENESIS_BOOTSTRAP_EXECUTED", "BOOTSTRAP_HOT_CHANGED", "B063_SCOPE_TOUCHED", "B064_SCOPE_TOUCHED",
        "B065_SCOPE_TOUCHED", "A049_SCOPE_TOUCHED", "E053_SCOPE_TOUCHED", "SHOP_ENABLED", "LOADOUT_ENABLED",
        "PAYMENTS_CHANGED", "NEWEBPAY_CHANGED", "PAYPAL_CHANGED", "SCHEMA_CHANGED", "DATA_CHANGED",
        "MIGRATION_CHANGED", "MIGRATION_RUN", "PRODUCTION_QUERY", "PRODUCTION_MUTATION", "DEPLOY",
        "ROLLBACK", "ART003_B07_INCLUDED_IN_CURRENT_RPG_V1_DEPLOYMENT", "F035_ZONE_USED_FOR_GAMEPLAY",
        "F035_ZONE_ASSIGNMENT_MUTATED", "F036_BATCH_PLAN_MUTATED", "SECRET_KEY_TOUCHED",
    )
    assert all(firewalls[key] == "NO" for key in required_no)


def test_review_pack_is_complete_and_in_exact_order() -> None:
    data = _manifest()
    pack = REVIEW_PACK_PATH.read_text(encoding="utf-8")
    assert "Owner visual review status: **PASS** (`10/10`)" in pack
    assert "The exact reviewed bytes are frozen and" in pack
    headings = re.findall(r"### (M\d+) — [^\n]+", pack)
    assert headings == IDS
    image_paths = re.findall(r"!\[[^\]]+\]\((\.\./\.\./art/monsters/[^)]+\.png)\)", pack)
    assert image_paths == [f"../../{row['asset_path']}" for row in data["assets"]]
    assert len(image_paths) == 10
    for row in data["assets"]:
        assert f"### {row['monster_id']} — {row['canonical_name']}" in pack
        assert f"![{row['monster_id']} {row['canonical_name']}]" in pack
        assert row["sha256"] in pack
        assert f"| {row['monster_id']} | {row['canonical_name']} | {row['planning_zone']} |" in pack
        assert "| PASS |" in pack


def test_only_b07_scope_changed_and_no_secret() -> None:
    changed = _changed_paths()
    allowed = {
        "docs/planning/art_003_batch_007_manifest.json",
        "docs/planning/art_003_batch_007_owner_visual_review_pack.md",
        "tests/test_art003_b07_production.py",
    } | {f"art/monsters/{mid}_{SLUGS[mid]}.png" for mid in IDS}
    assert changed <= allowed
    assert "secret_key.txt" not in changed
    assert not any(path.startswith("app.py") for path in changed)
    assert not any(path.startswith("assets/") for path in changed)
