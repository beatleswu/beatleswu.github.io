from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE_HEAD = "b16362b232c0a5d4a41b1b72a09783b8d29b0cf3"
EVIDENCE = ROOT / "docs" / "review" / "a020r2"
FORMS = EVIDENCE / "clean_forms"

FORM_IDS = [
    "SPIRIT4_STAGE1",
    "SPIRIT4_STAGE2",
    "SPIRIT4_STAGE3",
    "SPIRIT5_STAGE1",
    "SPIRIT5_STAGE2",
    "SPIRIT5_STAGE3",
    "SPIRIT6_STAGE1",
    "SPIRIT6_STAGE2",
    "SPIRIT6_STAGE3",
]

REVIEW_FILES = [
    "A020R2_CLEAN_THREE_STAGE_MASTER_SHEET.png",
    "A020R2_STARPATH_CLEAN_EVOLUTION_STRIP.png",
    "A020R2_FATTY_CLEAN_EVOLUTION_STRIP.png",
    "A020R2_OBSIDIAN_CLEAN_EVOLUTION_STRIP.png",
    "A020R2_CLEAN_STAGE_III_FINAL_TRIO.png",
    "A020R2_CLEAN_SIX_SPIRIT_FOLLOWER_SCALE.png",
]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_source_head_is_a020_r2_ancestor():
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", SOURCE_HEAD, "HEAD"],
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0


def test_all_nine_clean_forms_exist_as_rgba_with_alpha_matte():
    assert len(FORM_IDS) == 9
    for form_id in FORM_IDS:
        path = FORMS / f"A020R2_{form_id}_CLEAN.png"
        assert path.is_file(), path
        with Image.open(path) as image:
            assert image.mode == "RGBA"
            assert image.width >= 200 and image.height >= 140
            alpha = image.getchannel("A")
            low, high = alpha.getextrema()
            assert low == 0 and high == 255
            # The four corners must not retain an opaque poster rectangle.
            corner_alpha = [
                alpha.getpixel((0, 0)),
                alpha.getpixel((image.width - 1, 0)),
                alpha.getpixel((0, image.height - 1)),
                alpha.getpixel((image.width - 1, image.height - 1)),
            ]
            assert max(corner_alpha) <= 128, (path, corner_alpha)


def test_required_review_packet_exists():
    for filename in REVIEW_FILES:
        path = EVIDENCE / filename
        assert path.is_file(), path
        assert path.stat().st_size > 10_000, path


def test_scope_has_no_runtime_asset_or_application_changes():
    changed = set(git("status", "--short").splitlines())
    paths = {line[3:] for line in changed if len(line) >= 4}
    allowed = (
        "docs/planning/e10_six_spirit_clean_visual_asset_review_a020_r2.md",
        "docs/review/a020r2/",
        "tools/build_a020r2_clean_visual_asset_packet.py",
        "tests/test_master_lane_a_e10_six_spirit_clean_visual_asset_review_a020_r2.py",
    )
    assert all(path.startswith(allowed) for path in paths), sorted(paths)
    assert not any(path == "app.py" or path.startswith("assets/") for path in paths)


def test_no_rejected_a020_identities_in_active_r2_artifacts():
    active_files = [
        ROOT / "docs" / "planning" / "e10_six_spirit_clean_visual_asset_review_a020_r2.md",
        ROOT / "tools" / "build_a020r2_clean_visual_asset_packet.py",
    ]
    rejected = ("Trailglow Fawn", "Gridpoint Hedgehog", "Weaveleaf Tortoise")
    for path in active_files:
        text = path.read_text(encoding="utf-8")
        assert not any(name in text for name in rejected), path
