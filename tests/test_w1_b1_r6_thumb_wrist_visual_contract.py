"""R6 machine support for the localized thumb and wrist closure.

These checks validate source provenance, topology, and opposing-side handle
contact. They intentionally do not self-certify anatomy; the 400% proof still
requires independent human visual review.
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


SIGNIFICANT_COMPONENT_THRESHOLD = 64
ALPHA_THRESHOLD = 16

# Fixed presentation geometry for the opposing thumb side of the locked grip.
# It is deliberately a geometric support region, not a final-image hash.
THUMB_SUPPORT_REGION = (740, 745, 779, 802)

# The R5 defect was the canonical open-hand skin strip left at the cuff edge.
# A few antialias pixels are tolerated; a significant residual is not.
CUFF_RESIDUAL_REGION = (760, 700, 840, 723)
CUFF_RESIDUAL_ANTIALIAS_LIMIT = 32


def _rectangle_mask(box: tuple[int, int, int, int]) -> Image.Image:
    mask = Image.new("L", CANVAS, 0)
    ImageDraw.Draw(mask).rectangle(box, fill=255)
    return mask


def _masked_pixel_count(image: Image.Image, region: Image.Image) -> int:
    alpha = image.getchannel("A")
    return sum(
        1
        for value, scope in zip(alpha.getdata(), region.getdata())
        if value and scope
    )


def _significant_component_count(image: Image.Image) -> tuple[list[int], int]:
    areas = alpha_component_areas(image, HAND_ROI, threshold=ALPHA_THRESHOLD)
    significant = [area for area in areas if area >= SIGNIFICANT_COMPONENT_THRESHOLD]
    detached = max(0, len(significant) - 1)
    return areas, detached


def test_r6_source_is_hash_bound_rgba_and_has_no_detached_component() -> None:
    root = repo_root()
    source_path = root / SOURCE_REL
    axis = json.loads((root / AXIS_REL).read_text(encoding="utf-8"))
    source = load_rgba(source_path)

    assert sha256_file(source_path) == EXPECTED_HAND_SOURCE_SHA256
    assert source.size == CANVAS
    assert source.mode == "RGBA"
    assert axis["hand_source"]["sha256"] == EXPECTED_HAND_SOURCE_SHA256
    assert opaque_outside_roi(source, HAND_ROI) == 0

    areas, detached = _significant_component_count(source)
    assert areas
    assert detached == 0
    assert max(areas) >= SIGNIFICANT_COMPONENT_THRESHOLD


def test_r6_cuff_boundary_has_no_significant_residual_skin_island() -> None:
    root = repo_root()
    back = load_rgba(root / BACK_REL)
    front = load_rgba(root / FRONT_REL)
    localized = ImageChops.lighter(back.getchannel("A"), front.getchannel("A"))
    topology = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    topology.putalpha(localized)

    residual = _masked_pixel_count(topology, _rectangle_mask(CUFF_RESIDUAL_REGION))
    assert residual <= CUFF_RESIDUAL_ANTIALIAS_LIMIT


def test_r6_thumb_side_has_handle_contact_and_front_occlusion() -> None:
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

    thumb_side_handle_contact = _masked_pixel_count(contact, region)
    thumb_side_front_occlusion = _masked_pixel_count(front_occlusion, region)

    assert thumb_side_handle_contact > 0
    assert thumb_side_front_occlusion > 0


def test_r6_builder_contract_remains_frozen_except_source_hash() -> None:
    root = repo_root()
    builder = (root / "tools/hero/build_apprentice_wooden_sword_pose.py").read_text(
        encoding="utf-8"
    )
    transform = json.loads((root / TRANSFORM_REL).read_text(encoding="utf-8"))

    assert "parents[" + "2]" not in builder
    assert '"rev-parse", "--show-toplevel"' in builder
    assert sha256_file(root / CHARACTER_REL) == EXPECTED_CHARACTER_SHA256
    assert sha256_file(root / WEAPON_REL) == EXPECTED_WEAPON_SHA256
    assert transform["source_sha256"] == EXPECTED_WEAPON_SHA256
    assert transform["translate_x"] == 31.0
    assert transform["translate_y"] == 107.0
    assert transform["rotation_degrees"] == 0.0
    assert transform["scale_x"] == 1.0
    assert transform["scale_y"] == 1.0
    assert transform["shear"] == 0
    assert transform["mirrored"] is False
    assert transform["perspective"] is False


def test_r6_two_clean_builds_are_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_metrics = build(first)
    second_metrics = build(second)

    assert first_metrics == second_metrics
    assert first_metrics["outside_roi_pixel_diff_count"] == 0
    assert first_metrics["derived_back_matches_committed"] is True
    assert first_metrics["derived_front_matches_committed"] is True
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
