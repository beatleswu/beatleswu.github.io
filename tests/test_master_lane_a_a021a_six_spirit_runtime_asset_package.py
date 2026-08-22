from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "planning" / "e10_six_spirit_canonical_runtime_asset_manifest_a021a.json"
NEW_IDS = ("starpath_antlerling", "fatty", "obsidian_bastion")
EXISTING_IDS = ("ink_drop_kelpie", "whispering_void_kit", "star_shell_hatchling")
REJECTED = ("Trailglow Fawn", "Gridpoint Hedgehog", "Weaveleaf Tortoise")


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_manifest_is_complete_and_presentation_only():
    data = load_manifest()
    assert data["schema"] == "go_odyssey.six_spirit_runtime_presentation_assets"
    assert data["presentation_manifest_is_ownership_authority"] is False
    assert data["counts"] == {
        "canonical_spirit_count": 6,
        "existing_spirit_count": 3,
        "new_spirit_count": 3,
        "new_runtime_form_count": 9,
        "runtime_stage_record_count": 18,
    }
    spirits = data["spirits"]
    assert [spirit["slot"] for spirit in spirits] == [1, 2, 3, 4, 5, 6]
    assert [spirit["spirit_id"] for spirit in spirits] == [
        "ink_drop_kelpie",
        "whispering_void_kit",
        "star_shell_hatchling",
        "starpath_antlerling",
        "fatty",
        "obsidian_bastion",
    ]
    assert all(spirit["stage_count"] == 3 for spirit in spirits)
    assert all(set(spirit["stages"]) == {"I", "II", "III"} for spirit in spirits)


def test_nine_new_runtime_forms_are_exact_and_decode():
    data = load_manifest()
    new_records = [
        (spirit["spirit_id"], stage, record)
        for spirit in data["spirits"]
        if spirit["spirit_id"] in NEW_IDS
        for stage, record in spirit["stages"].items()
    ]
    assert len(new_records) == 9
    paths = []
    for spirit_id, stage, record in new_records:
        runtime_path = ROOT / record["runtime_asset"]
        paths.append(runtime_path)
        assert runtime_path.is_file(), runtime_path
        assert runtime_path.suffix == ".webp"
        assert record["source_kind"] == "A020_R2_APPROVED_FORM_NORMALIZED"
        assert record["source_art"]["redrawn"] is False
        assert "docs/review" in record["source_art"]["path"]
        assert "docs/review" not in record["runtime_asset"]
        assert record["hero_portrait_asset"] == record["runtime_asset"]
        assert record["world_map_follower_asset"] == record["runtime_asset"]
        with Image.open(runtime_path) as image:
            image.load()
            assert image.format == "WEBP"
            assert image.mode == "RGBA"
            assert image.size == (512, 512)
            assert image.getchannel("A").getextrema() == (0, 255)
            assert all(
                image.getpixel(point)[3] == 0
                for point in ((0, 0), (511, 0), (0, 511), (511, 511))
            )
            # WebP may canonicalize hidden RGB values on fully transparent
            # pixels during decode.  The visible contract is alpha plus the
            # dark-background composite QA sheet, not hidden RGB bytes.
    assert len(paths) == len(set(paths)) == 9


def test_existing_three_reuse_canonical_runtime_authority_without_duplication():
    data = load_manifest()
    expected = {
        "ink_drop_kelpie": {
            "I": "assets/pets/pet_ink_drop_kelpie_lv1.webp",
            "II": "assets/pets/horse_anim_lv2/01_idle.webp",
            "III": "assets/pets/horse_anim_lv3/01_idle.webp",
        },
        "whispering_void_kit": {
            "I": "assets/pets/pet_whispering_void_kit_lv1.webp",
            "II": "assets/pets/cat_anim_lv2/01_idle.webp",
            "III": "assets/pets/cat_anim_lv3/01_idle.webp",
        },
        "star_shell_hatchling": {
            "I": "assets/pets/pet_star_shell_hatchling_lv1.webp",
            "II": "assets/pets/dragon_anim_lv2/01_idle.webp",
            "III": "assets/pets/dragon_anim_lv3/01_idle.webp",
        },
    }
    by_id = {spirit["spirit_id"]: spirit for spirit in data["spirits"]}
    assert set(by_id) == set(EXISTING_IDS) | set(NEW_IDS)
    for spirit_id, stages in expected.items():
        spirit = by_id[spirit_id]
        assert spirit["duplicated"] is False
        assert {stage: spirit["stages"][stage]["runtime_asset"] for stage in stages} == stages
        for record in spirit["stages"].values():
            assert (ROOT / record["runtime_asset"]).is_file()


def test_hash_manifest_matches_every_stage_asset():
    data = load_manifest()
    records = data["asset_hash_manifest"]
    assert len(records) == 18
    assert len({record["filename"] for record in records}) == 18
    for record in records:
        path = ROOT / record["filename"]
        assert path.is_file(), path
        with Image.open(path) as image:
            image.load()
            assert image.width > 0 and image.height > 0
            assert image.mode == "RGBA"
            assert image.getchannel("A").getextrema() == (0, 255)
            assert record["alpha_valid"] is True
            assert record["dimensions"] == [image.width, image.height]
            assert record["byte_size"] == path.stat().st_size
            assert record["sha256"] == sha256(path)


def test_fallback_is_same_identity_and_never_ownership_authority():
    data = load_manifest()
    for spirit in data["spirits"]:
        fallback = spirit["fallback"]
        assert fallback["asset"] == spirit["stages"]["I"]["runtime_asset"]
        assert fallback["policy"] == "STAGE_I_SAME_SPIRIT_ONLY"
        assert fallback["changes_spirit_identity"] is False
        assert fallback["changes_ownership_or_stage_authority"] is False
        assert fallback["infinite_retry"] is False
    assert data["missing_asset_contract"]["changes_spirit_authority"] is False
    assert data["missing_asset_contract"]["infinite_retry"] is False


def test_review_evidence_and_rejected_identities_are_closed():
    data = load_manifest()
    for evidence in data["review_evidence"]:
        path = ROOT / evidence["path"]
        assert path.is_file(), path
        assert path.stat().st_size > 10_000
        with Image.open(path) as image:
            assert image.width > 0 and image.height > 0
    active_text = json.dumps(data, ensure_ascii=False)
    assert not any(name in active_text for name in REJECTED)
    assert data["rejected_a020_identity_runtime_reference_count"] == 0
    for spirit in data["spirits"]:
        for stage in spirit["stages"].values():
            assert "docs/review" not in stage["runtime_asset"]


def test_presentation_and_authority_boundaries_are_unchanged():
    data = load_manifest()
    boundaries = data["hard_boundaries"]
    assert boundaries["spirit_state_authority_changed"] is False
    assert boundaries["combat_runtime_changed"] is False
    assert boundaries["second_combat_engine_created"] is False
    assert boundaries["monster_files_changed"] == 0
    assert boundaries["runtime_catalog_changed"] is False
    assert boundaries["app_py_changed"] is False
    assert boundaries["route_changed"] is False
    assert boundaries["db_migration"] is False
    assert boundaries["production_mutation"] is False


def test_worktree_scope_contains_no_runtime_code_or_protected_scope_change():
    status = subprocess.check_output(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    )
    changed = {line[3:] for line in status.splitlines() if len(line) >= 4}
    allowed_prefixes = (
        "assets/pets/pet_starpath_antlerling_stage",
        "assets/pets/pet_fatty_stage",
        "assets/pets/pet_obsidian_bastion_stage",
        "docs/planning/e10_six_spirit_canonical_runtime_asset_manifest_a021a.json",
        "docs/review/a021a/",
        "tools/build_a021a_six_spirit_runtime_asset_package.py",
        "tests/test_master_lane_a_a021a_six_spirit_runtime_asset_package.py",
        "docs/planning/e10_six_spirit_canonical_runtime_asset_package_a021a.md",
    )
    assert all(path.startswith(allowed_prefixes) for path in changed), sorted(changed)
    assert "app.py" not in changed
    assert not any(path.startswith(".env") or path == "secret_key.txt" for path in changed)
