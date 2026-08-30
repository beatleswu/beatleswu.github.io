"""Focused ART003 B03 production, identity, and authority-firewall checks."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "planning" / "art_003_batch_003_manifest.json"
REVIEW_PACK_PATH = ROOT / "docs" / "planning" / "art_003_batch_003_owner_visual_review_pack.md"
BASE_SHA = "3f98c204a2b249763ad3d8d0730e5d3a0764622b"
F035_HEAD = "195f3376e107559817e054476b076e471c211731"
F035_ASSIGNMENT_HASH = "49e704f0c9935056c5614e91feff28d4775c6f98d4b38f1b068639f7d72d5e00"
F036_HEAD = "36eec98e972e5ed5e40acda83795ac1569e6eb1e"
B03_SOURCE_HEAD = "fb2e7449065a462911002eee98068e76fdc5434b"
B01_HEAD = "0b2f4c7ec65f845918bd96a2daec21551d27ff34"
B02_SOURCE_HEAD = "d3ccac1565b6c5bbe3f357164777f256136d2dc2"
B02_PUBLICATION_HEAD = "bc729d5bcc21a36e90724c921115c2e51f1efdcd"
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
M022_PATH = "assets/monsters/orc_grunt_chibi.png"
IDS = [f"M{i:03d}" for i in range(24, 34)]
SLUGS = {
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
NAMES = {
    "M024": "Echo Bat",
    "M025": "Pickaxe Moleworker",
    "M026": "Fungus Lantern Imp",
    "M027": "Rope-Ladder Lizard",
    "M028": "Ironbucket Beetle",
    "M029": "Crevice Snake",
    "M030": "Cartcap Crawler",
    "M031": "Crystal Ore Gob",
    "M032": "Cavern Slinger",
    "M033": "Stalactite Tortoise",
}
OWNER_HASHES = {
    "M024": "3990A6BADF07EE720A5EAF5F18A434B9442F4552D909FCA948E9E3DAD5B78920",
    "M025": "4A57F144E79EAE94D2C372F5D913E7673F61E1813D2D593D42ABD1D456D60CC9",
    "M026": "7E6789D2964026A7424A627D7AC21D290F493C9A03D12619C33C1B2DB4B44EBF",
    "M027": "5A6186946F8987C323090E634C7C597495696A96EE6CF5F89563D7BDFEBB9C49",
    "M028": "D1225D8DBE29AB96C66B9C4A0CA1C6E65D1C475EFA11465DD071E1C2C2B262E4",
    "M029": "8A9D99D1B2CA98B6223B3FB3EBFBD340E9B5C0A5C0456221062B42D3DA6E7E50",
    "M030": "BF68D5C6204B9CCB4E02C117D21C0E5C6621524E655B9F3D7EC420284AAFE2C3",
    "M031": "36C2792F9F5FD4E76C9058271B3B6F634AC01CF7645990E81CC118F293C95E74",
    "M032": "E584E5B56119EC877D5515E37493B8BFC307BD967AA65575AE9EDAD61E798F87",
    "M033": "A1A6BCB629359C5D780817BDD55D002F2CEE32D8C2EB81C35FADFC0C8B850F30",
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
        - F043_B09_ADMISSION_FILES
    )


def test_b03_exact_id_set_and_manifest_completeness() -> None:
    data = _manifest()
    rows = data["assets"]
    assert [row["M_ID"] for row in rows] == IDS
    assert [row["CANONICAL_NAME"] for row in rows] == [NAMES[mid] for mid in IDS]
    assert data["status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
    assert data["authoritative_planning"]["B03_SOURCE_HEAD"] == B03_SOURCE_HEAD
    assert data["owner_authorization"] == {
        "OWNER_DECISION": "B03_ALL_PASS",
        "OWNER_VISUAL_REVIEW_STATUS": "PASS",
        "OWNER_PASS_COUNT": "10/10",
        "REVISE_COUNT": 0,
        "REJECT_COUNT": 0,
    }
    assert data["id_set"]["ART003_B03_ID_COUNT"] == 10
    assert data["id_set"]["ART003_B03_ID_SET_EXACT"] == "YES"
    assert len({row["M_ID"] for row in rows}) == 10
    assert len(rows) == 10
    assert all(row["CANONICAL_NAME"] for row in rows)
    assert all(row["IDENTITY_SOURCE"] == "F035_ASSIGNMENT_ARTIFACT_AND_ART002_IDENTITY_BASELINE" for row in rows)
    assert all(row["EXISTING_REFERENCE_SOURCE"] == "F035_ASSIGNMENT_ARTIFACT_AND_ART002_IDENTITY_BASELINE" for row in rows)
    assert data["id_set"]["UNKNOWN_IDENTITY_COUNT"] == 0
    assert data["id_set"]["DUPLICATE_ID_COUNT"] == 0


def test_b03_assets_are_valid_unique_and_manifest_bound() -> None:
    data = _manifest()
    rows = data["assets"]
    hashes = []
    for row in rows:
        path = ROOT / row["FINAL_ASSET_PATH"]
        assert path.exists()
        raw = path.read_bytes()
        hashes.append(hashlib.sha256(raw).hexdigest().upper())
        with Image.open(path) as image:
            assert image.format == "PNG"
            image.load()
            assert image.mode == "RGBA"
            assert image.width == row["WIDTH"]
            assert image.height == row["HEIGHT"]
            assert min(image.size) >= 1024
            assert max(image.size) <= 1536
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
        assert hashes[-1] == row["SHA256"]
        assert hashes[-1] == OWNER_HASHES[row["M_ID"]]
        assert row["SOURCE_B03_HEAD"] == B03_SOURCE_HEAD
        assert _blob(B03_SOURCE_HEAD, row["FINAL_ASSET_PATH"]) == _blob("HEAD", row["FINAL_ASSET_PATH"])
        assert row["COLOR_MODE"] == "RGBA"
        assert row["PRODUCTION_STATUS"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
        assert row["PUBLICATION_STATUS"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
        assert row["OWNER_REVIEW_STATUS"] == "PASS"
        assert row["RUNTIME_MAPPING_STATUS"] == "NOT_MAPPED"
    assert len(hashes) == 10
    assert len(set(hashes)) == 10
    assert len(OWNER_HASHES) == 10
    assert len(set(OWNER_HASHES.values())) == 10
    assert data["qa_summary"]["UNIQUE_SHA256_COUNT"] == 10
    assert data["owner_visual_review"]["OWNER_PASS_COUNT"] == "10/10"
    assert data["owner_visual_review"]["REVISE_COUNT"] == 0
    assert data["owner_visual_review"]["REJECT_COUNT"] == 0


def test_f035_zone_lock_and_planning_authority_firewall() -> None:
    data = _manifest()
    assert data["authoritative_planning"]["F035_HEAD"] == F035_HEAD
    assert data["authoritative_planning"]["F035_ASSIGNMENT_HASH"] == F035_ASSIGNMENT_HASH
    assert data["authoritative_planning"]["F036_HEAD"] == F036_HEAD
    assert data["zone_semantics"]["B03_F035_ZONE_DISTRIBUTION"] == {"Z3": 10}
    assert all(row["F035_ZONE"] == "Z3" for row in data["assets"])
    assert data["zone_semantics"]["F035_ZONE_USED_FOR_GAMEPLAY"] == "NO"
    assert data["zone_semantics"]["RUNTIME_ZONE_MAPPING_CHANGED"] == "NO"
    assert data["zone_semantics"]["F035_ZONE_ASSIGNMENT_MUTATED"] == "NO"
    assert data["protected_lineages"]["F036_BATCH_PLAN_MUTATED"] == "NO"


def test_b01_b02_and_m022_protection() -> None:
    changed = _changed_paths()
    protected = set(B01_PATHS + B02_PATHS)
    assert not changed.intersection(protected)
    assert not any(path.startswith("art/monsters/M022") for path in changed)
    for path in B01_PATHS:
        assert _blob(B01_HEAD, path) == _blob(B02_PUBLICATION_HEAD, path)
    for path in B02_PATHS:
        assert _blob(B02_SOURCE_HEAD, path) == _blob(B02_PUBLICATION_HEAD, path)
    assert _blob(F039_BASE_HEAD, M022_PATH) == _blob("HEAD", M022_PATH)
    data = _manifest()
    assert data["protected_lineages"]["B01_ASSETS_CHANGED"] == "NO"
    assert data["protected_lineages"]["B02_ASSETS_CHANGED"] == "NO"
    assert data["protected_lineages"]["M022_CHANGED"] == "NO"
    assert data["protected_lineages"]["M022_REGENERATED"] == "NO"
    assert data["protected_lineages"]["M022_RUNTIME_REFERENCE_CHANGED"] == "NO"


def test_runtime_catalog_gameplay_and_release_firewalls() -> None:
    data = _manifest()
    changed = _changed_paths()
    forbidden_fragments = (
        "app.py", "catalog", "monster_catalog", "runtime", "battle", "combat", "f009",
        "schema", "migration", "release", "deploy", "b063", "B063", "Dockerfile",
    )
    assert all(not any(fragment in path for fragment in forbidden_fragments) for path in changed)
    assert all(row["RUNTIME_MAPPING_STATUS"] == "NOT_MAPPED" for row in data["assets"])
    for key in (
        "GAMEPLAY_AUTHORITY_CHANGED", "MONSTER_STATS_CHANGED", "HP_CHANGED", "ATK_CHANGED",
        "DROP_CHANGED", "REWARD_CHANGED", "COMBAT_MAPPING_CHANGED",
        "MONSTER_CATALOG_RUNTIME_MAPPING_CHANGED", "E049_SCOPE_TOUCHED", "F009_ENABLED",
        "F009_CHANGED", "BOSS_INCLUDED", "LORD_INCLUDED", "APP_PY_CHANGED",
        "RUNTIME_SOURCE_CHANGED", "GAMEPLAY_SOURCE_CHANGED", "SCHEMA_CHANGED",
        "MIGRATION_CHANGED", "DATA_CHANGED", "B063_SCOPE_TOUCHED",
        "ART003_B03_INCLUDED_IN_B063", "RPG_V1_RELEASE_ARTIFACT_SCOPE_TOUCHED",
        "ART003_B03_INCLUDED_IN_CURRENT_RPG_V1_DEPLOYMENT", "E051_SCOPE_TOUCHED",
        "E052_SCOPE_TOUCHED", "B064_SCOPE_TOUCHED", "LC_SCOPE_TOUCHED",
        "LC_IDENTITY_WIRING_CHANGED", "GENESIS_BOOTSTRAP_EXECUTED", "BOOTSTRAP_HOT_CHANGED",
        "PRODUCTION_QUERY", "PRODUCTION_MUTATION", "PRODUCTION_DB_MIGRATION", "DEPLOY",
    ):
        assert data["firewalls"][key] == "NO"
    assert all(row["RUNTIME_MAPPING_STATUS"] == "NOT_MAPPED" for row in data["assets"])


def test_review_pack_is_exactly_associated_and_owner_pass() -> None:
    data = _manifest()
    pack = REVIEW_PACK_PATH.read_text(encoding="utf-8")
    assert data["owner_visual_review"]["OWNER_VISUAL_REVIEW_ASSET_COUNT"] == 10
    assert data["owner_visual_review"]["OWNER_REVIEW_STATUS"] == "PASS"
    assert data["owner_visual_review"]["OWNER_PASS_COUNT"] == "10/10"
    assert data["owner_visual_review"]["REVIEW_PACK_EQUALS_STAGED_ASSET_BYTES"] == "YES"
    for row in data["assets"]:
        assert f"{row['M_ID']} — {row['CANONICAL_NAME']}" in pack
        assert f"![{row['M_ID']} {row['CANONICAL_NAME']}]" in pack
        assert row["FINAL_ASSET_PATH"] in pack
        assert row["OWNER_REVIEW_STATUS"] == "PASS"
        assert f"| {row['M_ID']} | {row['CANONICAL_NAME']} | Z3 |" in pack


def test_only_allowed_b03_files_changed_and_secret_is_untouched() -> None:
    changed = _changed_paths()
    assert changed <= F039_R1_TEST_FILES
    assert "secret_key.txt" not in changed
    assert not any(path.startswith(("art/", "assets/")) for path in changed)
