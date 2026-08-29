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
B01_HEAD = "0b2f4c7ec65f845918bd96a2daec21551d27ff34"
B02_SOURCE_HEAD = "d3ccac1565b6c5bbe3f357164777f256136d2dc2"
B02_PUBLICATION_HEAD = "bc729d5bcc21a36e90724c921115c2e51f1efdcd"
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


def test_b03_exact_id_set_and_manifest_completeness() -> None:
    data = _manifest()
    rows = data["assets"]
    assert [row["M_ID"] for row in rows] == IDS
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
        assert row["COLOR_MODE"] == "RGBA"
        assert row["PRODUCTION_STATUS"] == "FINAL_PRODUCTION_CANDIDATE_READY_FOR_OWNER_REVIEW"
        assert row["OWNER_REVIEW_STATUS"] == "PENDING"
        assert row["RUNTIME_MAPPING_STATUS"] == "NOT_MAPPED"
    assert len(hashes) == 10
    assert len(set(hashes)) == 10
    assert data["qa_summary"]["UNIQUE_SHA256_COUNT"] == 10


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


def test_b01_b02_and_m022_protection() -> None:
    changed = _changed_paths()
    protected = set(B01_PATHS + B02_PATHS)
    assert not changed.intersection(protected)
    assert not any(path.startswith("art/monsters/M022") for path in changed)
    for path in B01_PATHS:
        assert _blob(B01_HEAD, path) == _blob(B02_PUBLICATION_HEAD, path)
    for path in B02_PATHS:
        assert _blob(B02_SOURCE_HEAD, path) == _blob(B02_PUBLICATION_HEAD, path)
    assert _blob(BASE_SHA, M022_PATH) == _blob("HEAD", M022_PATH)
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
        "PRODUCTION_QUERY", "PRODUCTION_MUTATION", "PRODUCTION_DB_MIGRATION", "DEPLOY",
    ):
        assert data["firewalls"][key] == "NO"


def test_review_pack_is_exactly_associated_and_pending() -> None:
    data = _manifest()
    pack = REVIEW_PACK_PATH.read_text(encoding="utf-8")
    assert data["owner_visual_review"]["OWNER_VISUAL_REVIEW_ASSET_COUNT"] == 10
    assert data["owner_visual_review"]["OWNER_REVIEW_STATUS"] == "PENDING"
    assert data["owner_visual_review"]["REVIEW_PACK_EQUALS_STAGED_ASSET_BYTES"] == "YES"
    for row in data["assets"]:
        assert f"{row['M_ID']} — {row['CANONICAL_NAME']}" in pack
        assert f"![{row['M_ID']} {row['CANONICAL_NAME']}]" in pack
        assert row["FINAL_ASSET_PATH"] in pack
        assert row["OWNER_REVIEW_STATUS"] == "PENDING"


def test_only_allowed_b03_files_changed_and_secret_is_untouched() -> None:
    changed = _changed_paths()
    allowed = {
        f"art/monsters/{mid}_{SLUGS[mid]}.png" for mid in IDS
    } | {
        "docs/planning/art_003_batch_003_manifest.json",
        "docs/planning/art_003_batch_003_owner_visual_review_pack.md",
        "tests/test_art003_b03_production.py",
    }
    assert changed <= allowed
    assert "secret_key.txt" not in changed
    assert len(changed.intersection({f"art/monsters/{mid}_{SLUGS[mid]}.png" for mid in IDS})) == 10
