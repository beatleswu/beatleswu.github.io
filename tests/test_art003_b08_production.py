"""Focused structural and protection tests for ART003 B08 production candidates."""

import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = "786b9f2335b42f777c03a0c6e604d4784dc7ec5b"
IDS = ["M078", "M079", "M080", "M081", "M082", "M083", "M085", "M086", "M087", "M088"]
NAMES = {
    "M078": "Potion Gob",
    "M079": "Prism Gecko",
    "M080": "Gravity Crab",
    "M081": "Scrollback Turtle",
    "M082": "Astrolabe Beetle",
    "M083": "Cloudstep Ram",
    "M085": "Blackgate Hound",
    "M086": "Breakshield Beetle",
    "M087": "Bannerbreak Stonebeast",
    "M088": "Stringwing Bat",
}
ZONES = {"M078": "Z7", "M079": "Z7", "M080": "Z7", "M081": "Z7", "M082": "Z7", "M083": "Z7", "M085": "Z8", "M086": "Z8", "M087": "Z8", "M088": "Z2"}
ASSETS = {
    "M078": "art/monsters/M078_potion_gob.png",
    "M079": "art/monsters/M079_prism_gecko.png",
    "M080": "art/monsters/M080_gravity_crab.png",
    "M081": "art/monsters/M081_scrollback_turtle.png",
    "M082": "art/monsters/M082_astrolabe_beetle.png",
    "M083": "art/monsters/M083_cloudstep_ram.png",
    "M085": "art/monsters/M085_blackgate_hound.png",
    "M086": "art/monsters/M086_breakshield_beetle.png",
    "M087": "art/monsters/M087_bannerbreak_stonebeast.png",
    "M088": "art/monsters/M088_stringwing_bat.png",
}
HASHES = {
    "M078": "1DF9FD02FF8935035F09C2DE091B3BA275622F28515CA8DBEB53A99DA9CD2ABE",
    "M079": "0FCA459B3F511F846A67EF6D67D2A14699169C27B3BD34F0C52127B37E6505B0",
    "M080": "1EB3748FB5DEF14D2FC7D48E95126176453A45AE62BAC7D74C631C704FD432EC",
    "M081": "77338CB53EC6426A2137FA4DBFD65BAED90FAB84C19122AF9CCA99B39FC7D15C",
    "M082": "E0C423770A86FD3054A747DD4FFD03187B7D26327BAA28C7AD6051287C1C58B4",
    "M083": "595B29E90C127CFDE01D92359AF3FE1CF284343E8719BFF4D6496D8CCEDC415C",
    "M085": "A4D565CEB543D7C99460049DD0DD94CC9767F46EC108AF63C205948381490BE9",
    "M086": "66E7C42844D98969DC966F878BCC429B5E05D2D62E013F11261A8ECE5B3F1491",
    "M087": "77B87471DD39D108D6587FD75934FBAD5B3C0F735A6AC131B515595B850EE444",
    "M088": "46F31E88FEDE01967BA060DC28AAD3BABD01EFCA08F8C6C1F79C7DFEDCD75C99",
}
MANIFEST_PATH = ROOT / "docs/planning/art_003_batch_008_manifest.json"
PACK_PATH = ROOT / "docs/planning/art_003_batch_008_owner_visual_review_pack.md"
ALLOWED_PATHS = set(ASSETS.values()) | {
    "docs/planning/art_003_batch_008_manifest.json",
    "docs/planning/art_003_batch_008_owner_visual_review_pack.md",
    "tests/test_art003_b08_production.py",
}


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def manifest_entries() -> list[dict]:
    return load_manifest()["assets"]


def test_b08_exact_id_set_and_m084_absent():
    manifest = load_manifest()
    assert manifest["batch"] == "ART003_B08"
    assert manifest["id_set"]["expected_ids"] == IDS
    assert manifest["id_set"]["count"] == 10
    assert manifest["id_set"]["id_set_exact"] == "YES"
    assert manifest["id_set"]["m084_present"] == "NO"
    assert [entry["monster_id"] for entry in manifest_entries()] == IDS
    assert all(entry["monster_id"] != "M084" for entry in manifest_entries())


def test_b08_manifest_identity_and_zone_contract():
    entries = manifest_entries()
    assert {entry["monster_id"] for entry in entries} == set(IDS)
    for entry in entries:
        monster_id = entry["monster_id"]
        assert entry["canonical_name"] == NAMES[monster_id]
        assert entry["planning_zone"] == ZONES[monster_id]
        assert entry["asset_path"] == ASSETS[monster_id]
        assert entry["identity_source"] == "F035_ASSIGNMENT_ARTIFACT_AND_ART002_IDENTITY_BASELINE"
        assert entry["production_status"] == "PRODUCTION_CANDIDATE"
        assert entry["owner_visual_review_status"] == "PENDING"
    assert load_manifest()["planning_semantics"]["zone_distribution"] == {"Z2": 1, "Z7": 6, "Z8": 3}
    assert load_manifest()["authoritative_lineage"]["f035_head"] == "195f3376e107559817e054476b076e471c211731"
    assert load_manifest()["authoritative_lineage"]["f036_head"] == "36eec98e972e5ed5e40acda83795ac1569e6eb1e"


def test_b08_assets_readable_and_hash_unique():
    entries = manifest_entries()
    observed_hashes = []
    for entry in entries:
        monster_id = entry["monster_id"]
        path = ROOT / ASSETS[monster_id]
        assert path.is_file()
        file_bytes = path.read_bytes()
        assert file_bytes
        digest = hashlib.sha256(file_bytes).hexdigest().upper()
        observed_hashes.append(digest)
        assert digest == HASHES[monster_id]
        assert entry["sha256"] == digest
        with Image.open(path) as image:
            image.load()
            assert image.format == "PNG"
            assert image.mode == "RGBA"
            assert image.width > 0 and image.height > 0
            assert image.width <= 2048 and image.height <= 2048
            alpha = image.getchannel("A")
            assert alpha.getbbox() is not None
            assert alpha.getextrema()[1] > 0
            assert [image.width, image.height] == entry["dimensions"]
            assert entry["mode"] == image.mode
            assert entry["format"] == image.format
            assert entry["alpha_status"] == "PASS"
    assert len(observed_hashes) == 10
    assert len(set(observed_hashes)) == 10


def test_b08_review_pack_exact_order_and_pending_gate():
    pack = PACK_PATH.read_text(encoding="utf-8")
    headings = [line.split(" — ", 1)[0].split(". ", 1)[1] for line in pack.splitlines() if line.startswith("### ")]
    assert headings == IDS
    assert "M084 —" not in pack
    assert "Owner visual review status: **PENDING** (`0/10`)" in pack
    assert "Review-pack bytes equal final candidate assets: **YES**" in pack
    assert pack.count("Owner review: **PENDING**") == 10
    for monster_id, asset_path in ASSETS.items():
        assert f"../../{asset_path}" in pack
        assert HASHES[monster_id] in pack


def test_prior_art_and_m022_protection():
    changed_paths = set(git("diff", "--name-only", BASE_SHA, "HEAD").splitlines())
    changed_paths.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    assert changed_paths <= ALLOWED_PATHS
    assert not any("M022" in path for path in changed_paths)
    prior_paths = [path for path in git("ls-tree", "-r", "--name-only", BASE_SHA, "art/monsters").splitlines() if path.lower().endswith(".png")]
    for path in prior_paths:
        assert git("rev-parse", f"{BASE_SHA}:{path}") == git("rev-parse", f"HEAD:{path}")


def test_runtime_and_cross_lane_firewalls():
    firewalls = load_manifest()["firewalls"]
    required_no = [
        "app_py_changed", "runtime_source_changed", "gameplay_source_changed",
        "monster_stats_changed", "combat_mapping_changed", "monster_catalog_gameplay_authority_changed",
        "f009_enabled", "f009_changed", "boss_included", "lord_included",
        "b071_scope_touched", "lc019_scope_touched", "a050_scope_touched", "e054_scope_touched",
        "f037_scope_touched", "b063_scope_touched", "b064_scope_touched", "b065_scope_touched",
        "schema_changed", "data_changed", "migration_changed", "migration_run",
        "production_query", "production_mutation", "deploy", "rollback", "shop_enabled",
        "loadout_enabled", "payments_changed", "f035_zone_used_for_gameplay",
        "f035_zone_assignment_mutated", "f036_batch_plan_mutated", "secret_key_touched",
    ]
    assert all(firewalls[key] == "NO" for key in required_no)


def test_protected_lineage_and_result_state():
    manifest = load_manifest()
    protected = manifest["protected_lineages"]
    assert all(value == "NO" for value in protected.values())
    assert manifest["owner_visual_review_status"] == "PENDING"
    assert manifest["owner_pass_count"] == "0/10"
    assert manifest["result"]["ready_for_owner_visual_review"] == "YES"
    assert manifest["result"]["next_task"] == "OWNER_VISUAL_REVIEW_ART003_B08"
    assert manifest["result"]["master_merge"] == "NO"
    assert manifest["result"]["deploy"] == "NO"


def test_only_expected_artifact_files_exist_in_scope():
    assert len(manifest_entries()) == 10
    assert sorted(path for path in ASSETS.values()) == sorted(entry["asset_path"] for entry in manifest_entries())
    unexpected = set(git("ls-files", "--others", "--exclude-standard").splitlines()) - ALLOWED_PATHS
    assert not unexpected
