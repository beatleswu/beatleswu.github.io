"""Machine contract for the R4 localized articulated-grip correction.

These assertions prove provenance, geometry, occlusion, and rebuildability.  They
do not replace independent visual anatomy review.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from tools.hero.build_apprentice_wooden_sword_pose import (
    AXIS_REL,
    BACK_REL,
    CANVAS,
    EXPECTED_HAND_SOURCE_SHA256,
    FRONT_REL,
    HAND_ROI,
    SOURCE_REL,
    alpha_component_areas,
    build,
    derive_hand_layers,
    load_rgba,
    repo_root,
    rgba_diff_count,
    sha256_file,
)


def test_committed_hand_source_is_hash_bound_and_inside_roi() -> None:
    root = repo_root()
    source_path = root / SOURCE_REL
    axis = json.loads((root / AXIS_REL).read_text(encoding="utf-8"))
    source = Image.open(source_path)

    assert source_path.is_file()
    assert sha256_file(source_path) == EXPECTED_HAND_SOURCE_SHA256
    assert source.size == CANVAS
    assert source.mode == "RGBA"
    assert axis["hand_source"]["path"] == SOURCE_REL.as_posix()
    assert axis["hand_source"]["sha256"] == EXPECTED_HAND_SOURCE_SHA256

    alpha = source.getchannel("A")
    x1, y1, x2, y2 = HAND_ROI
    outside = 0
    pixels = alpha.load()
    for y in range(CANVAS[1]):
        for x in range(CANVAS[0]):
            if not (x1 <= x < x2 and y1 <= y < y2) and pixels[x, y]:
                outside += 1
    assert outside == 0


def test_back_and_front_are_reproducible_from_committed_source() -> None:
    root = repo_root()
    character = load_rgba(root / "assets/hero/characters/wave2_p1/apprentice_p1.png")
    source = load_rgba(root / SOURCE_REL)
    axis = json.loads((root / AXIS_REL).read_text(encoding="utf-8"))
    derived_back, derived_front = derive_hand_layers(character, source, axis)

    assert rgba_diff_count(load_rgba(root / BACK_REL), derived_back) == 0
    assert rgba_diff_count(load_rgba(root / FRONT_REL), derived_front) == 0
    assert all(area >= 20 for area in alpha_component_areas(source, HAND_ROI))


def test_grip_has_machine_visible_and_occluded_handle_segments(tmp_path: Path) -> None:
    metrics = build(tmp_path / "proof")

    assert metrics["source_opaque_outside_roi"] == 0
    assert metrics["back_opaque_outside_roi"] == 0
    assert metrics["front_opaque_outside_roi"] == 0
    assert metrics["derived_back_matches_committed"] is True
    assert metrics["derived_front_matches_committed"] is True
    assert metrics["source_small_component_count"] == 0
    assert metrics["grip_region_weapon_pixels"] > 0
    assert metrics["grip_region_front_occluded_weapon_pixels"] > 0
    assert metrics["grip_region_visible_weapon_pixels"] > 0
    assert metrics["grip_region_hand_handle_intersection_pixels"] > 0
    assert metrics["grip_pivot_intersection_pixels"] > 0


def test_root_discovery_is_git_based_not_fixed_depth() -> None:
    root = repo_root()
    source = (root / "tools/hero/build_apprentice_wooden_sword_pose.py").read_text(
        encoding="utf-8"
    )

    assert "parents[" + "2]" not in source
    assert '"rev-parse", "--show-toplevel"' in source
    assert root == Path(repo_root()).resolve()


def test_two_clean_builds_are_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_metrics = build(first)
    second_metrics = build(second)

    assert first_metrics == second_metrics
    for name in (
        "pose_base.png",
        "wooden_sword_held.png",
        "production_static_proof.png",
        "grip_zoom_400pct.png",
        "pixel_identity_report.json",
        "composite_verification_report.json",
    ):
        assert (first / name).read_bytes() == (second / name).read_bytes()
