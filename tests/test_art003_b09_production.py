"""Focused structural and protection checks for ART003 B09 production."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "planning" / "art_003_batch_009_manifest.json"
BASE_SHA = "af179e79407eb563ded840609fd3a7026fc6a09f"
EXPECTED_IDS = [
    "M089",
    "M090",
    "M091",
    "M092",
    "M093",
    "M094",
    "M095",
    "M096",
    "M097",
    "M099",
]
EXPECTED_NAMES = {
    "M089": "Steelfang Hyena",
    "M090": "Battlement Lizard",
    "M091": "Smokescreen Weasel",
    "M092": "Ironwheel Rhino",
    "M093": "Beacon Scorpion",
    "M094": "Shieldshell Crab",
    "M095": "Obsidian Automaton",
    "M096": "Wallbreak Bear",
    "M097": "Scout Hawkbeast",
    "M099": "Aurora Serpent",
}
EXPECTED_ZONES = {
    "M089": "Z8",
    "M090": "Z8",
    "M091": "Z2",
    "M092": "Z8",
    "M093": "Z8",
    "M094": "Z2",
    "M095": "Z8",
    "M096": "Z8",
    "M097": "Z8",
    "M099": "Z9",
}
EXPECTED_ASSETS = {
    "M089": "art/monsters/M089_steelfang_hyena.png",
    "M090": "art/monsters/M090_battlement_lizard.png",
    "M091": "art/monsters/M091_smokescreen_weasel.png",
    "M092": "art/monsters/M092_ironwheel_rhino.png",
    "M093": "art/monsters/M093_beacon_scorpion.png",
    "M094": "art/monsters/M094_shieldshell_crab.png",
    "M095": "art/monsters/M095_obsidian_automaton.png",
    "M096": "art/monsters/M096_wallbreak_bear.png",
    "M097": "art/monsters/M097_scout_hawkbeast.png",
    "M099": "art/monsters/M099_aurora_serpent.png",
}
EXPECTED_HASHES = {
    "M089": "ADD1C7F743CF80F1D6BD4CFD1EFEBE7263152243B7FE327D94A98255BEA2E12F",
    "M090": "6ED5304B2A388D9E1382554E12CF6D0715171255647AFC0CC66C629BD1A658AE",
    "M091": "0AFB9573B7C4134CA4A94E210991162CEB68225B5C946C76F52A06DC0C3C3C1A",
    "M092": "704B057D9299237606A52E754DF22100AB553DA6672B145A282481B4DB193591",
    "M093": "415DD802D33407B8E551284F17F705CFD5358605E2BAA43DCD5D608E4F26ABF9",
    "M094": "75FCC20164AB7DAB93510EC235E078C9B021E9EB4E8200D2FB79FA0890EC291A",
    "M095": "205A804651D3316C595996A201B98270FFDA44CE6E2265930ABBB2FAF894E1A7",
    "M096": "98A0AC843410749FAE756A4C0775A823B4351DB48593649B188F5D006CD1452A",
    "M097": "BF629CE24EE845DE1D947C172796F9BF927C5745A358E1CAC5D1E7ED00A08A61",
    "M099": "8FA97913D98207DA46C81BE60A0C0D5CF8AAFF1203BEA74D71BAD2FFE65E675F",
}
EXPECTED_DIMENSIONS = {
    "M089": [1536, 1024],
    "M090": [1536, 1024],
    "M091": [1536, 1024],
    "M092": [1536, 1024],
    "M093": [1536, 1024],
    "M094": [1536, 1024],
    "M095": [1224, 1285],
    "M096": [1536, 1024],
    "M097": [1536, 1024],
    "M099": [1207, 1303],
}
SOURCE_BRANCH = "codex/art003-b09-m089-m099-canonical-monster-art-production"
ALLOWED_CHANGED_PATHS = {
    *EXPECTED_ASSETS.values(),
    "docs/planning/art_003_batch_009_manifest.json",
    "docs/planning/art_003_batch_009_owner_visual_review_pack.md",
    "tests/test_art003_b09_production.py",
}


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_b09_exact_id_set_and_manifest_completeness() -> None:
    manifest = load_manifest()
    assert manifest["batch"] == "ART003_B09"
    assert manifest["source_branch"] == SOURCE_BRANCH
    assert manifest["status"] == "READY_FOR_OWNER_VISUAL_REVIEW"
    assert manifest["owner_visual_review_status"] == "PENDING"
    assert manifest["owner_pass_count"] == "0/10"
    assert manifest["id_set"]["expected_ids"] == EXPECTED_IDS
    assert manifest["id_set"]["count"] == 10
    assert manifest["id_set"]["id_set_exact"] == "YES"
    assert manifest["id_set"]["m098_present_in_b09"] == "NO"
    assert [item["monster_id"] for item in manifest["assets"]] == EXPECTED_IDS
    assert len(manifest["assets"]) == 10
    assert "M084" not in {item["monster_id"] for item in manifest["assets"]}
    assert "M098" not in {item["monster_id"] for item in manifest["assets"]}
    assert len({item["monster_id"] for item in manifest["assets"]}) == 10


def test_b09_identity_and_zone_lock() -> None:
    manifest = load_manifest()
    assets = manifest["assets"]
    for item, monster_id in zip(assets, EXPECTED_IDS):
        assert item["monster_id"] == monster_id
        assert item["canonical_name"] == EXPECTED_NAMES[monster_id]
        assert item["planning_zone"] == EXPECTED_ZONES[monster_id]
        assert item["identity_source"] == "F035_ASSIGNMENT_ARTIFACT_AND_ART002_IDENTITY_BASELINE"
        assert item["prior_identity_collision"] == "NO"
    assert manifest["planning_semantics"]["zone_distribution"] == {"Z2": 2, "Z8": 7, "Z9": 1}
    assert manifest["planning_semantics"]["f035_zone_assignment_mutated"] == "NO"
    assert manifest["planning_semantics"]["f035_zone_used_for_gameplay"] == "NO"
    assert manifest["planning_semantics"]["f036_batch_plan_mutated"] == "NO"


def test_assets_are_readable_rgba_nonempty_and_hash_locked() -> None:
    manifest = load_manifest()
    hashes = []
    for item, monster_id in zip(manifest["assets"], EXPECTED_IDS):
        assert item["asset_path"] == EXPECTED_ASSETS[monster_id]
        path = ROOT / item["asset_path"]
        assert path.is_file()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest().upper()
        hashes.append(digest)
        assert digest == EXPECTED_HASHES[monster_id] == item["sha256"]
        with Image.open(path) as image:
            image.load()
            assert image.format == "PNG"
            assert image.mode == "RGBA"
            assert [image.width, image.height] == EXPECTED_DIMENSIONS[monster_id]
            alpha = image.getchannel("A")
            assert alpha.getbbox() is not None
            assert alpha.getextrema()[0] == 0
            assert alpha.getextrema()[1] > 0
        assert item["dimensions"] == EXPECTED_DIMENSIONS[monster_id]
        assert item["width"] == EXPECTED_DIMENSIONS[monster_id][0]
        assert item["height"] == EXPECTED_DIMENSIONS[monster_id][1]
        assert item["mode"] == "RGBA"
        assert item["format"] == "PNG"
        assert item["alpha_status"] == "PASS"
        assert item["technical_validation"] == "PASS"
        assert item["owner_visual_review_status"] == "PENDING"
    assert len(hashes) == 10
    assert len(set(hashes)) == 10


def test_source_head_contains_exact_candidate_bytes() -> None:
    manifest = load_manifest()
    source_head = manifest["source_head"]
    assert len(source_head) == 40
    assert git("cat-file", "-e", f"{source_head}^{{commit}}") == ""
    for monster_id in EXPECTED_IDS:
        path = EXPECTED_ASSETS[monster_id]
        source_bytes = subprocess.check_output(
            ["git", "show", f"{source_head}:{path}"], cwd=ROOT
        )
        assert source_bytes == (ROOT / path).read_bytes()


def test_prior_art_and_runtime_firewalls() -> None:
    changed = set(git("diff", "--name-only", f"{BASE_SHA}..HEAD").splitlines())
    untracked = set(git("ls-files", "--others", "--exclude-standard").splitlines())
    assert changed <= ALLOWED_CHANGED_PATHS
    assert untracked == set()
    assert not any("secret_key.txt" in path.lower() for path in changed | untracked)
    assert not any("M084" in path or "M098" in path for path in changed | untracked)
    assert not any(path.startswith("app.py") for path in changed)
    assert not any(path.endswith((".js", ".css", ".html")) for path in changed)
    manifest = load_manifest()
    for key, value in manifest["firewalls"].items():
        if key.endswith("_changed") or key.endswith("_enabled") or key.endswith("_run"):
            assert value == "NO"
    assert manifest["protection"]["f035_zone_assignment_mutated"] == "NO"
    for batch in ("b01", "b02", "b03", "b04", "b05", "b06", "b07", "b08"):
        assert manifest["protection"][f"{batch}_assets_changed"] == "NO"
    assert manifest["protection"]["m022_changed"] == "NO"


def test_review_pack_exact_order_and_pending_gate() -> None:
    pack = (ROOT / "docs" / "planning" / "art_003_batch_009_owner_visual_review_pack.md").read_text(
        encoding="utf-8"
    )
    positions = [pack.index(f"### {index}. {monster_id} —") for index, monster_id in enumerate(EXPECTED_IDS, 1)]
    assert positions == sorted(positions)
    assert "M098" in pack and "intentionally excluded" in pack
    assert "Owner visual review status: **PENDING** (`0/10`)" in pack
    assert "Review-pack bytes equal staged final assets: **YES**" in pack
