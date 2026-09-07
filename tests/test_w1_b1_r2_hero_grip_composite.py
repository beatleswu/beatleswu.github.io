"""Focused W1-B1 deterministic held-weapon asset checks."""

from __future__ import annotations

import inspect
import json
import math
from pathlib import Path

from PIL import Image

from tools.hero.build_apprentice_wooden_sword_pose import (
    AXIS_REL,
    BACK_REL,
    CANVAS,
    CHARACTER_REL,
    EXPECTED_CHARACTER_SHA256,
    EXPECTED_WEAPON_SHA256,
    FRONT_REL,
    HAND_ROI,
    TRANSFORM_REL,
    WEAPON_REL,
    build,
    repo_root,
    sha256_file,
    transform_weapon,
)


def test_canonical_input_hashes_are_exact() -> None:
    root = repo_root()
    assert sha256_file(root / CHARACTER_REL) == EXPECTED_CHARACTER_SHA256
    assert sha256_file(root / WEAPON_REL) == EXPECTED_WEAPON_SHA256


def test_hand_layers_and_canonical_inputs_are_full_frame_rgba() -> None:
    root = repo_root()
    for relative in (CHARACTER_REL, WEAPON_REL, BACK_REL, FRONT_REL):
        image = Image.open(root / relative)
        assert image.size == CANVAS
        assert image.mode == "RGBA"


def test_transform_contract_is_rotation_translation_only() -> None:
    signature = inspect.signature(transform_weapon)
    assert {"scale", "shear", "perspective", "fit"}.isdisjoint(signature.parameters)
    transform = json.loads((repo_root() / TRANSFORM_REL).read_text(encoding="utf-8"))
    assert transform["source_sha256"] == EXPECTED_WEAPON_SHA256
    assert transform["scale_x"] == 1.0
    assert transform["scale_y"] == 1.0
    assert transform["shear"] == 0
    assert transform["mirrored"] is False
    assert transform["perspective"] is False


def test_grip_axis_is_reusable_and_inside_roi() -> None:
    axis = json.loads((repo_root() / AXIS_REL).read_text(encoding="utf-8"))
    assert axis["canvas_width"] == CANVAS[0]
    assert axis["canvas_height"] == CANVAS[1]
    pivot = axis["grip_pivot"]
    p1 = axis["grip_axis"]["p1"]
    p2 = axis["grip_axis"]["p2"]
    x1, y1, x2, y2 = HAND_ROI
    for point in (pivot, p1, p2):
        assert x1 <= point["x"] <= x2
        assert y1 <= point["y"] <= y2
    length = math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])
    assert length > 0
    assert length >= 0.01 * math.hypot(*CANVAS)


def test_build_is_deterministic_and_preserves_character_outside_roi(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_metrics = build(first)
    second_metrics = build(second)

    assert first_metrics == second_metrics
    assert first_metrics["outside_roi_pixel_diff_count"] == 0
    assert first_metrics["inside_roi_pixel_diff_count"] > 0
    assert first_metrics["back_opaque_outside_roi"] == 0
    assert first_metrics["front_opaque_outside_roi"] == 0
    assert first_metrics["back_canvas"] == list(CANVAS)
    assert first_metrics["front_canvas"] == list(CANVAS)
    assert first_metrics["back_rgba"] is True
    assert first_metrics["front_rgba"] is True
    assert first_metrics["proof_rgba"] is True
    assert first_metrics["proof_canvas"] == list(CANVAS)
    assert first_metrics["proper_rotation_unit_error"] <= 1e-6
    assert first_metrics["proper_rotation_orthogonality_error"] <= 1e-6
    assert abs(first_metrics["proper_rotation_determinant"] - 1) <= 1e-6

    for name in (
        "pose_base.png",
        "wooden_sword_held.png",
        "production_static_proof.png",
        "grip_zoom_400pct.png",
    ):
        assert (first / name).read_bytes() == (second / name).read_bytes()
