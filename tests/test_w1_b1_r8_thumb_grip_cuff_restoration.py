"""R8 machine support for the localized thumb and cuff restoration.

These checks bind the corrected source, prove that the restored cuff pixels are
canonical, and validate reproducible mask/weapon interaction.  They provide
geometry evidence only; normal-scale anatomy remains subject to independent
R9 visual review.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from tools.hero.build_apprentice_wooden_sword_pose import (
    AXIS_REL,
    BACK_REL,
    CANVAS,
    CHARACTER_REL,
    CUFF_MASK_BOUNDARY,
    EXPECTED_CHARACTER_SHA256,
    EXPECTED_HAND_SOURCE_SHA256,
    EXPECTED_WEAPON_SHA256,
    FRONT_REL,
    HAND_ROI,
    SOURCE_REL,
    TRANSFORM_REL,
    WEAPON_REL,
    alpha_component_areas,
    build,
    load_rgba,
    opaque_outside_roi,
    repo_root,
    sha256_file,
    transform_weapon,
)


ALPHA_THRESHOLD = 16
SIGNIFICANT_COMPONENT_THRESHOLD = 64
THUMB_SUPPORT_REGION = (740, 745, 779, 802)
R8_HAND_SOURCE_SHA256 = (
    "bfa8646b8678e7ff5075d1bef8c5c916903579597206504c152d5b6d6bce4622"
)


def _rectangle_mask(box: tuple[int, int, int, int]) -> Image.Image:
    mask = Image.new("L", CANVAS, 0)
    ImageDraw.Draw(mask).rectangle(box, fill=255)
    return mask


def _alpha_values(image: Image.Image) -> list[int]:
    alpha = image if image.mode == "L" else image.getchannel("A")
    flattened = getattr(alpha, "get_flattened_data", None)
    return list(flattened()) if callable(flattened) else list(alpha.getdata())


def _masked_alpha_count(image: Image.Image, region: Image.Image) -> int:
    return sum(
        1
        for value, scope in zip(_alpha_values(image), _alpha_values(region))
        if value and scope
    )


def _significant_source_components(source: Image.Image) -> tuple[list[int], int]:
    areas = alpha_component_areas(source, HAND_ROI, threshold=ALPHA_THRESHOLD)
    significant = [area for area in areas if area >= SIGNIFICANT_COMPONENT_THRESHOLD]
    return areas, max(0, len(significant) - 1)


def test_r8_hand_source_sha_is_bound_in_builder_and_axis() -> None:
    root = repo_root()
    source_path = root / SOURCE_REL
    axis = json.loads((root / AXIS_REL).read_text(encoding="utf-8"))

    assert R8_HAND_SOURCE_SHA256 == EXPECTED_HAND_SOURCE_SHA256
    assert sha256_file(source_path) == R8_HAND_SOURCE_SHA256
    assert axis["hand_source"]["sha256"] == R8_HAND_SOURCE_SHA256
    assert axis["hand_art_assist_sha256"] == R8_HAND_SOURCE_SHA256
    assert source_path == root / "assets/hero/characters/wave2_p1/weapon_pose/hand_grip_source.png"


def test_r8_source_is_full_frame_rgba_inside_locked_roi_and_connected() -> None:
    root = repo_root()
    source = load_rgba(root / SOURCE_REL)

    assert source.size == CANVAS
    assert source.mode == "RGBA"
    assert opaque_outside_roi(source, HAND_ROI) == 0

    areas, detached = _significant_source_components(source)
    assert areas
    assert max(areas) >= SIGNIFICANT_COMPONENT_THRESHOLD
    assert detached == 0


def test_r8_cuff_boundary_restores_canonical_pixels_without_row_700_cut() -> None:
    root = repo_root()
    character = load_rgba(root / CHARACTER_REL)
    back = load_rgba(root / BACK_REL)
    front = load_rgba(root / FRONT_REL)

    assert CUFF_MASK_BOUNDARY == 722
    localized = ImageChops.lighter(back.getchannel("A"), front.getchannel("A"))
    canonical_alpha = character.getchannel("A")

    x1, y1, x2, y2 = HAND_ROI
    cuff_rows = range(701, 723)
    canonical_pixels = sum(
        1
        for y in cuff_rows
        for x in range(x1, x2)
        if canonical_alpha.getpixel((x, y))
    )
    restored_pixels = sum(
        1
        for y in cuff_rows
        for x in range(x1, x2)
        if canonical_alpha.getpixel((x, y)) and localized.getpixel((x, y))
    )
    assert canonical_pixels > 1000
    assert restored_pixels == canonical_pixels

    row_counts = {
        y: sum(1 for x in range(x1, x2) if localized.getpixel((x, y)))
        for y in (700, 701, 722)
    }
    assert row_counts[700] > 0
    assert row_counts[701] > 0
    assert row_counts[722] > 0
    assert abs(row_counts[701] - row_counts[700]) < 40


def test_r8_grip_axis_and_weapon_transform_remain_frozen() -> None:
    root = repo_root()
    axis = json.loads((root / AXIS_REL).read_text(encoding="utf-8"))
    transform = json.loads((root / TRANSFORM_REL).read_text(encoding="utf-8"))

    assert axis["grip_pivot"] == {"x": 741.0, "y": 785.5}
    assert axis["grip_axis"]["p1"] == {"x": 722.0, "y": 757.0}
    assert axis["grip_axis"]["p2"] == {"x": 760.0, "y": 814.0}
    assert transform["source_sha256"] == EXPECTED_WEAPON_SHA256
    assert transform["translate_x"] == 31.0
    assert transform["translate_y"] == 107.0
    assert transform["rotation_degrees"] == 0.0
    assert transform["scale_x"] == 1.0
    assert transform["scale_y"] == 1.0
    assert transform["shear"] == 0
    assert transform["mirrored"] is False
    assert transform["perspective"] is False


def test_r8_thumb_side_has_supporting_handle_contact_and_front_occlusion() -> None:
    root = repo_root()
    transform = json.loads((root / TRANSFORM_REL).read_text(encoding="utf-8"))
    weapon = transform_weapon(
        load_rgba(root / WEAPON_REL),
        rotation_degrees=float(transform["rotation_degrees"]),
        translate_x=float(transform["translate_x"]),
        translate_y=float(transform["translate_y"]),
    )
    source = load_rgba(root / SOURCE_REL)
    front = load_rgba(root / FRONT_REL)
    region = _rectangle_mask(THUMB_SUPPORT_REGION)

    contact = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    contact.putalpha(ImageChops.multiply(weapon.getchannel("A"), source.getchannel("A")))
    front_occlusion = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    front_occlusion.putalpha(
        ImageChops.multiply(weapon.getchannel("A"), front.getchannel("A"))
    )

    thumb_side_handle_contact = _masked_alpha_count(contact, region)
    thumb_side_front_occlusion = _masked_alpha_count(front_occlusion, region)
    assert thumb_side_handle_contact > 0
    assert thumb_side_front_occlusion > 0


def test_r8_derived_layers_preserve_identity_and_rebuild_deterministically(
    tmp_path: Path,
) -> None:
    root = repo_root()
    assert sha256_file(root / CHARACTER_REL) == EXPECTED_CHARACTER_SHA256
    assert sha256_file(root / WEAPON_REL) == EXPECTED_WEAPON_SHA256

    first = tmp_path / "first"
    second = tmp_path / "second"
    first_metrics = build(first)
    second_metrics = build(second)

    assert first_metrics == second_metrics
    assert first_metrics["outside_roi_pixel_diff_count"] == 0
    assert first_metrics["derived_back_matches_committed"] is True
    assert first_metrics["derived_front_matches_committed"] is True
    assert first_metrics["back_opaque_outside_roi"] == 0
    assert first_metrics["front_opaque_outside_roi"] == 0
    assert first_metrics["proof_canvas"] == list(CANVAS)
    assert first_metrics["proof_rgba"] is True

    for name in (
        "pose_base.png",
        "wooden_sword_held.png",
        "production_static_proof.png",
        "grip_zoom_400pct.png",
        "pixel_identity_report.json",
        "composite_verification_report.json",
    ):
        assert (first / name).read_bytes() == (second / name).read_bytes()
