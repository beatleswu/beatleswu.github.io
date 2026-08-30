"""Focused freeze/publication checks for ART003 B09 Owner PASS."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "planning" / "art_003_batch_009_manifest.json"
SOURCE_HEAD = "49daf4d2660ff72e227bb66d0fc317472e45f6d8"
TECHNICAL_SOURCE_HEAD = "075d3174bf144ae48a9afa4dac6fba457794cfd5"
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
ALLOWED_R1_PATHS = {
    "docs/planning/art_003_batch_009_manifest.json",
    "docs/planning/art_003_batch_009_owner_visual_review_pack.md",
    "tests/test_art003_b09_r1_publication.py",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_owner_pass_and_exact_hash_lock() -> None:
    manifest = load_manifest()
    assert manifest["status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
    assert manifest["canonical_art_status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
    assert manifest["owner_visual_review_status"] == "PASS"
    assert manifest["owner_pass_count"] == "10/10"
    assert manifest["owner_rejected_ids"] == "NONE"
    assert manifest["redraw_required"] == "NONE"
    assert manifest["source_head"] == SOURCE_HEAD
    assert manifest["technical_source_head"] == TECHNICAL_SOURCE_HEAD
    assets = manifest["assets"]
    assert [item["monster_id"] for item in assets] == EXPECTED_IDS
    assert len(assets) == 10
    assert len({item["monster_id"] for item in assets}) == 10
    assert len({item["sha256"] for item in assets}) == 10
    for item in assets:
        monster_id = item["monster_id"]
        path = ROOT / item["asset_path"]
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest().upper()
        assert digest == EXPECTED_HASHES[monster_id] == item["sha256"]
        assert item["owner_visual_review_status"] == "PASS"
        assert item["production_status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
        assert item["canonical_art_status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
        assert item["publication_status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
        assert item["runtime_mapping_status"] == "NOT_MAPPED"
    assert manifest["qa"]["canonical_art_published_count"] == 10
    assert manifest["qa"]["canonical_art_id_set_exact"] == "YES"
    assert manifest["qa"]["owner_approved_hash_match_count"] == 10
    assert manifest["qa"]["owner_approved_bytes_match"] == "YES"
    assert manifest["qa"]["owner_approved_byte_drift_count"] == 0


def test_source_head_bytes_are_unchanged_and_exact() -> None:
    manifest = load_manifest()
    assert git("cat-file", "-e", f"{SOURCE_HEAD}^{{commit}}") == ""
    for item in manifest["assets"]:
        asset_path = item["asset_path"]
        source_bytes = subprocess.check_output(["git", "show", f"{SOURCE_HEAD}:{asset_path}"], cwd=ROOT)
        assert source_bytes == (ROOT / asset_path).read_bytes()
        assert hashlib.sha256(source_bytes).hexdigest().upper() == item["sha256"]


def test_exact_publication_scope_and_prior_art_protection() -> None:
    manifest = load_manifest()
    changed = set(git("diff", "--name-only", f"{SOURCE_HEAD}..HEAD").splitlines())
    untracked = set(git("ls-files", "--others", "--exclude-standard").splitlines())
    assert changed <= ALLOWED_R1_PATHS
    assert untracked == set()
    assert not any("secret_key.txt" in path.lower() for path in changed | untracked)
    assert not any(path.startswith("art/monsters/") for path in changed)
    assert "M098" not in {item["monster_id"] for item in manifest["assets"]}
    assert manifest["id_set"]["m098_present_in_b09"] == "NO"
    assert manifest["protection"]["m098_changed"] == "NO"
    for batch in ("b01", "b02", "b03", "b04", "b05", "b06", "b07", "b08"):
        assert manifest["protection"][f"{batch}_assets_changed"] == "NO"
    assert manifest["protection"]["m022_changed"] == "NO"


def test_governance_boundaries_and_review_pack() -> None:
    manifest = load_manifest()
    assert manifest["planning_semantics"]["f035_zone_assignment_mutated"] == "NO"
    assert manifest["planning_semantics"]["f035_zone_used_for_gameplay"] == "NO"
    assert manifest["planning_semantics"]["f036_batch_plan_mutated"] == "NO"
    for key, value in manifest["firewalls"].items():
        if key.endswith("_changed") or key.endswith("_enabled") or key.endswith("_run"):
            assert value == "NO"
    pack_path = ROOT / "docs/planning/art_003_batch_009_owner_visual_review_pack.md"
    pack = pack_path.read_text(encoding="utf-8")
    assert "Owner visual review status: **PASS** (`10/10`)" in pack
    assert "Owner rejected IDs: `NONE`" in pack
    assert "Redraw required: `NONE`" in pack
    assert "Production source head: `49daf4d2660ff72e227bb66d0fc317472e45f6d8`" in pack
    assert "Technical source head: `075d3174bf144ae48a9afa4dac6fba457794cfd5`" in pack
    positions = [pack.index(f"### {index}. {monster_id} —") for index, monster_id in enumerate(EXPECTED_IDS, 1)]
    assert positions == sorted(positions)
    assert pack.count("Owner review: **PASS**") == 10
    assert "Owner review: **PENDING**" not in pack
