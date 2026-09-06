"""Build and verify the W1-B1 Apprentice held wooden-sword still proof.

This module is deliberately presentation-only.  It consumes the canonical
character, the two committed hand layers, and the canonical sword plus the
recorded transform.  No runtime registry or application code is touched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw


CANVAS = (1056, 1408)
HAND_ROI = (676, 641, 840, 845)
CHARACTER_REL = Path("assets/hero/characters/wave2_p1/apprentice_p1.png")
WEAPON_REL = Path("assets/hero/equipment/wearables/overlays/wooden_sword.png")
BACK_REL = Path("assets/hero/characters/wave2_p1/weapon_pose/hand_grip_back.png")
FRONT_REL = Path("assets/hero/characters/wave2_p1/weapon_pose/hand_grip_front.png")
SOURCE_REL = Path(
    "assets/hero/characters/wave2_p1/weapon_pose/hand_grip_source.png"
)
AXIS_REL = Path("assets/hero/characters/wave2_p1/weapon_pose/grip_axis.json")
TRANSFORM_REL = Path(
    "assets/hero/characters/wave2_p1/weapon_pose/weapon_transform.json"
)
EXPECTED_CHARACTER_SHA256 = (
    "0b03cbc512186fabd49678fd4c0e66e3603176f63b7f948be83493fcd0b288a7"
)
EXPECTED_WEAPON_SHA256 = (
    "12b4bbe4150d05bca39b507787c250f1418c2ad154fafb8d8e2df557186e4523"
)
EXPECTED_HAND_SOURCE_SHA256 = (
    "5bf31ba320e166242ad34c5f470bef272fc648c882a31d0597a718730b0c267f"
)


def repo_root() -> Path:
    """Discover the current Git checkout without a fixed parent depth."""

    probe = Path(__file__).resolve().parent
    try:
        result = subprocess.run(
            ["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        result = None
    if result is not None and result.returncode == 0:
        reported = result.stdout.strip()
        if reported:
            root = Path(reported).expanduser().resolve()
            if root.is_dir():
                return root
    for candidate in (probe, *probe.parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError(f"Unable to discover a Git checkout root from {probe}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rgba(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    if image.size != CANVAS:
        raise AssertionError(f"{path} must be {CANVAS}, got {image.size}")
    return image


def pixel_data(image: Image.Image) -> Any:
    """Use the current Pillow pixel iterator while retaining older compatibility."""

    flattened = getattr(image, "get_flattened_data", None)
    return flattened() if callable(flattened) else image.getdata()


def normalize_transparent_rgb(image: Image.Image) -> Image.Image:
    """Keep transparent pixels deterministic and black for compact PNGs."""

    alpha = image.getchannel("A")
    black = Image.new("RGB", image.size, (0, 0, 0))
    rgb = Image.composite(image.convert("RGB"), black, alpha)
    normalized = rgb.convert("RGBA")
    normalized.putalpha(alpha)
    return normalized


def grip_axis_points(axis: dict[str, Any]) -> tuple[tuple[float, float], tuple[float, float]]:
    p1 = axis["grip_axis"]["p1"]
    p2 = axis["grip_axis"]["p2"]
    return (float(p1["x"]), float(p1["y"])), (float(p2["x"]), float(p2["y"]))


def front_region_mask(axis: dict[str, Any]) -> Image.Image:
    """Return the front/thumb side of the reusable grip axis.

    The image-space cross-product sign is part of the metadata contract: the
    negative side is the foreground thumb/palm side, while the positive side
    remains behind the weapon as the curled-finger mass.
    """

    (x1, y1), (x2, y2) = grip_axis_points(axis)
    vx = x2 - x1
    vy = y2 - y1
    mask = Image.new("L", CANVAS, 0)
    pixels = mask.load()
    for y in range(HAND_ROI[1], HAND_ROI[3]):
        for x in range(HAND_ROI[0], HAND_ROI[2]):
            cross = vx * (y - y1) - vy * (x - x1)
            if cross <= 0:
                pixels[x, y] = 255
    return mask


def canonical_cuff_layer(character: Image.Image) -> Image.Image:
    """Keep only the canonical sleeve/cuff pixels used under the new hand."""

    mask = Image.new("L", CANVAS, 0)
    ImageDraw.Draw(mask).rectangle(
        (HAND_ROI[0], HAND_ROI[1], HAND_ROI[2] - 1, 700), fill=255
    )
    cuff = character.copy()
    cuff.putalpha(ImageChops.multiply(character.getchannel("A"), mask))
    return normalize_transparent_rgb(cuff)


def derive_hand_layers(
    character: Image.Image, source: Image.Image, axis: dict[str, Any]
) -> tuple[Image.Image, Image.Image]:
    """Derive rear and front hand layers solely from committed source pixels."""

    source_alpha = source.getchannel("A")
    front_alpha = ImageChops.multiply(source_alpha, front_region_mask(axis))
    rear_alpha = ImageChops.subtract(source_alpha, front_alpha)

    rear_hand = source.copy()
    rear_hand.putalpha(rear_alpha)
    front_hand = source.copy()
    front_hand.putalpha(front_alpha)

    back = canonical_cuff_layer(character)
    back.alpha_composite(normalize_transparent_rgb(rear_hand))
    return normalize_transparent_rgb(back), normalize_transparent_rgb(front_hand)


def grip_region_mask(axis: dict[str, Any], width: int = 36) -> Image.Image:
    (x1, y1), (x2, y2) = grip_axis_points(axis)
    mask = Image.new("L", CANVAS, 0)
    draw = ImageDraw.Draw(mask)
    radius = width / 2
    draw.line((x1, y1, x2, y2), fill=255, width=width)
    for x, y in ((x1, y1), (x2, y2)):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
    return mask


def alpha_intersection_count(
    left: Image.Image, right: Image.Image, region: Image.Image | None = None
) -> int:
    left_alpha = left.getchannel("A")
    right_alpha = right.getchannel("A")
    intersection = ImageChops.multiply(left_alpha, right_alpha)
    if region is not None:
        intersection = ImageChops.multiply(intersection, region)
    return sum(1 for value in pixel_data(intersection) if value)


def masked_alpha_count(
    image: Image.Image,
    region: Image.Image,
    occluder: Image.Image | None = None,
) -> int:
    alpha = image.getchannel("A")
    region_data = pixel_data(region)
    alpha_data = pixel_data(alpha)
    if occluder is None:
        return sum(1 for value, scope in zip(alpha_data, region_data) if value and scope)
    occluder_data = pixel_data(occluder.getchannel("A"))
    return sum(
        1
        for value, scope, covered in zip(alpha_data, region_data, occluder_data)
        if value and scope and not covered
    )


def alpha_component_areas(
    image: Image.Image, roi: tuple[int, int, int, int], threshold: int = 16
) -> list[int]:
    """Return 8-connected alpha component sizes inside a bounded ROI."""

    x1, y1, x2, y2 = roi
    alpha = image.getchannel("A")
    pixels = alpha.load()
    active = {
        (x, y)
        for y in range(y1, y2)
        for x in range(x1, x2)
        if pixels[x, y] >= threshold
    }
    areas: list[int] = []
    while active:
        start = active.pop()
        stack = [start]
        area = 1
        while stack:
            x, y = stack.pop()
            for nx in range(x - 1, x + 2):
                for ny in range(y - 1, y + 2):
                    point = (nx, ny)
                    if point in active:
                        active.remove(point)
                        stack.append(point)
                        area += 1
        areas.append(area)
    return sorted(areas, reverse=True)


def affine_for_rotation_translation(
    rotation_degrees: float, translate_x: float, translate_y: float
) -> tuple[float, float, float, float, float, float]:
    """Return the inverse PIL affine for a y-down proper rotation + translation."""

    radians = math.radians(rotation_degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    # Forward image-space map is [x', y'] = R [x, y] + [tx, ty],
    # where R = [[cos, -sin], [sin, cos]].
    return (
        cosine,
        sine,
        -cosine * translate_x - sine * translate_y,
        -sine,
        cosine,
        sine * translate_x - cosine * translate_y,
    )


def transform_weapon(
    source: Image.Image,
    *,
    rotation_degrees: float,
    translate_x: float,
    translate_y: float,
) -> Image.Image:
    """Bake the canonical weapon using only rotation and translation.

    Scale, shear, mirror, and perspective are intentionally not parameters of
    this API.  The omission makes an item-specific scale correction
    unrepresentable in the production bake path.
    """

    if source.size != CANVAS:
        raise AssertionError(f"weapon source must be {CANVAS}, got {source.size}")
    return source.transform(
        CANVAS,
        Image.Transform.AFFINE,
        affine_for_rotation_translation(
            rotation_degrees, translate_x, translate_y
        ),
        resample=Image.Resampling.BICUBIC,
    )


def opaque_outside_roi(image: Image.Image, roi: tuple[int, int, int, int]) -> int:
    alpha = image.getchannel("A")
    outside = Image.new("L", image.size, 255)
    outside.paste(0, roi)
    return sum(
        1 for pixel, scope in zip(pixel_data(alpha), pixel_data(outside))
        if scope and pixel
    )


def rgba_diff_count(
    left: Image.Image, right: Image.Image, roi: tuple[int, int, int, int] | None = None
) -> int:
    if left.size != right.size:
        raise AssertionError("pixel comparison requires equal canvases")
    difference = ImageChops.difference(left.convert("RGBA"), right.convert("RGBA"))
    if roi is not None:
        scoped = Image.new("L", difference.size, 0)
        scoped.paste(255, roi)
        return sum(
            1 for pixel, scope in zip(pixel_data(difference), pixel_data(scoped))
            if scope and pixel != (0, 0, 0, 0)
        )
    return sum(1 for pixel in pixel_data(difference) if pixel != (0, 0, 0, 0))


def rgba_diff_count_outside_roi(
    left: Image.Image, right: Image.Image, roi: tuple[int, int, int, int]
) -> int:
    if left.size != right.size:
        raise AssertionError("pixel comparison requires equal canvases")
    difference = ImageChops.difference(left.convert("RGBA"), right.convert("RGBA"))
    scoped = Image.new("L", difference.size, 255)
    scoped.paste(0, roi)
    return sum(
        1 for pixel, scope in zip(pixel_data(difference), pixel_data(scoped))
        if scope and pixel != (0, 0, 0, 0)
    )


def build(output_dir: Path) -> dict[str, Any]:
    root = repo_root()
    output_dir.mkdir(parents=True, exist_ok=True)

    character_path = root / CHARACTER_REL
    weapon_path = root / WEAPON_REL
    back_path = root / BACK_REL
    front_path = root / FRONT_REL
    source_path = root / SOURCE_REL
    axis_path = root / AXIS_REL
    transform_path = root / TRANSFORM_REL

    character_sha = sha256_file(character_path)
    weapon_sha = sha256_file(weapon_path)
    source_sha = sha256_file(source_path)
    if character_sha != EXPECTED_CHARACTER_SHA256:
        raise AssertionError("canonical Apprentice SHA-256 mismatch")
    if weapon_sha != EXPECTED_WEAPON_SHA256:
        raise AssertionError("canonical wooden_sword SHA-256 mismatch")
    if source_sha != EXPECTED_HAND_SOURCE_SHA256:
        raise AssertionError("committed hand-grip source SHA-256 mismatch")

    character = load_rgba(character_path)
    weapon = load_rgba(weapon_path)
    source = load_rgba(source_path)
    back = load_rgba(back_path)
    front = load_rgba(front_path)
    axis = json.loads(axis_path.read_text(encoding="utf-8"))
    transform = json.loads(transform_path.read_text(encoding="utf-8"))

    recorded_roi = axis["hand_roi"]
    if (
        recorded_roi["x1"],
        recorded_roi["y1"],
        recorded_roi["x2"],
        recorded_roi["y2"],
    ) != HAND_ROI:
        raise AssertionError("grip_axis.json hand_roi does not match the locked ROI")
    source_contract = axis["hand_source"]
    if source_contract["path"] != SOURCE_REL.as_posix():
        raise AssertionError("grip_axis.json hand source path is not canonical")
    if source_contract["sha256"] != source_sha:
        raise AssertionError("grip_axis.json hand source SHA-256 mismatch")
    if opaque_outside_roi(source, HAND_ROI):
        raise AssertionError("hand-grip source has opaque pixels outside HAND_ROI")
    if transform["source_sha256"] != EXPECTED_WEAPON_SHA256:
        raise AssertionError("weapon_transform.json source SHA-256 mismatch")
    for field in ("scale_x", "scale_y"):
        if float(transform[field]) != 1.0:
            raise AssertionError(f"{field} must be exactly 1.0")
    if transform["shear"] != 0 or transform["mirrored"] or transform["perspective"]:
        raise AssertionError("weapon transform is not rotation/translation-only")

    derived_back, derived_front = derive_hand_layers(character, source, axis)
    if rgba_diff_count(back, derived_back) != 0:
        raise AssertionError("hand_grip_back.png is not reproducible from source")
    if rgba_diff_count(front, derived_front) != 0:
        raise AssertionError("hand_grip_front.png is not reproducible from source")

    held_weapon = transform_weapon(
        weapon,
        rotation_degrees=float(transform["rotation_degrees"]),
        translate_x=float(transform["translate_x"]),
        translate_y=float(transform["translate_y"]),
    )
    pose = character.copy()
    pose.paste((0, 0, 0, 0), HAND_ROI)
    pose.alpha_composite(back)
    proof = pose.copy()
    proof.alpha_composite(held_weapon)
    proof.alpha_composite(front)

    grip_region = grip_region_mask(axis)
    pivot = axis["grip_pivot"]
    pivot_region = Image.new("L", CANVAS, 0)
    ImageDraw.Draw(pivot_region).ellipse(
        (
            float(pivot["x"]) - 10,
            float(pivot["y"]) - 10,
            float(pivot["x"]) + 10,
            float(pivot["y"]) + 10,
        ),
        fill=255,
    )
    source_component_sizes = alpha_component_areas(source, HAND_ROI)
    handle_pixels = masked_alpha_count(held_weapon, grip_region)
    handle_front_occluded_pixels = alpha_intersection_count(
        held_weapon, front, grip_region
    )
    handle_visible_pixels = masked_alpha_count(held_weapon, grip_region, front)
    hand_handle_intersection_pixels = alpha_intersection_count(
        source, held_weapon, grip_region
    )
    pivot_intersection_pixels = alpha_intersection_count(
        source, held_weapon, pivot_region
    )

    pose_path = output_dir / "pose_base.png"
    held_path = output_dir / "wooden_sword_held.png"
    proof_path = output_dir / "production_static_proof.png"
    zoom_path = output_dir / "grip_zoom_400pct.png"
    pose.save(pose_path)
    held_weapon.save(held_path)
    proof.save(proof_path)
    proof.crop((650, 690, 850, 860)).resize(
        (800, 680), Image.Resampling.NEAREST
    ).save(zoom_path)

    matrix = affine_for_rotation_translation(
        float(transform["rotation_degrees"]),
        float(transform["translate_x"]),
        float(transform["translate_y"]),
    )
    inverse_a, inverse_b, _, inverse_d, inverse_e, _ = matrix
    metrics = {
        "canvas": list(CANVAS),
        "character_sha256": character_sha,
        "weapon_sha256": weapon_sha,
        "hand_source_sha256": source_sha,
        "hand_roi": list(HAND_ROI),
        "source_canvas": list(source.size),
        "back_canvas": list(back.size),
        "front_canvas": list(front.size),
        "proof_canvas": list(proof.size),
        "back_rgba": back.mode == "RGBA",
        "front_rgba": front.mode == "RGBA",
        "proof_rgba": proof.mode == "RGBA",
        "back_opaque_outside_roi": opaque_outside_roi(back, HAND_ROI),
        "front_opaque_outside_roi": opaque_outside_roi(front, HAND_ROI),
        "source_opaque_outside_roi": opaque_outside_roi(source, HAND_ROI),
        "source_component_sizes": source_component_sizes,
        "source_small_component_count": sum(
            1 for area in source_component_sizes if area < 20
        ),
        "derived_back_matches_committed": rgba_diff_count(back, derived_back) == 0,
        "derived_front_matches_committed": rgba_diff_count(front, derived_front) == 0,
        "outside_roi_pixel_diff_count": rgba_diff_count_outside_roi(
            character, pose, HAND_ROI
        ),
        "inside_roi_pixel_diff_count": rgba_diff_count(character, pose, HAND_ROI),
        "back_alpha_bbox": list(back.getchannel("A").getbbox() or ()),
        "front_alpha_bbox": list(front.getchannel("A").getbbox() or ()),
        "weapon_alpha_bbox": list(held_weapon.getchannel("A").getbbox() or ()),
        "proof_alpha_bbox": list(proof.getchannel("A").getbbox() or ()),
        "grip_region_weapon_pixels": handle_pixels,
        "grip_region_front_occluded_weapon_pixels": handle_front_occluded_pixels,
        "grip_region_visible_weapon_pixels": handle_visible_pixels,
        "grip_region_hand_handle_intersection_pixels": hand_handle_intersection_pixels,
        "grip_pivot_intersection_pixels": pivot_intersection_pixels,
        "weapon_transform_matrix": list(matrix),
        "rotation_degrees": float(transform["rotation_degrees"]),
        "translate_x": float(transform["translate_x"]),
        "translate_y": float(transform["translate_y"]),
        "proper_rotation_unit_error": max(
            abs(inverse_a * inverse_a + inverse_b * inverse_b - 1),
            abs(inverse_d * inverse_d + inverse_e * inverse_e - 1),
        ),
        "proper_rotation_orthogonality_error": abs(
            inverse_a * inverse_d + inverse_b * inverse_e
        ),
        "proper_rotation_determinant": inverse_a * inverse_e - inverse_b * inverse_d,
        "resampling_method": transform["resampling_method"],
    }
    (output_dir / "pixel_identity_report.json").write_text(
        json.dumps(
            {
                "outside_roi_pixel_diff_count": metrics["outside_roi_pixel_diff_count"],
                "inside_roi_pixel_diff_count": metrics["inside_roi_pixel_diff_count"],
                "hand_roi": list(HAND_ROI),
                "canonical_character_sha256": character_sha,
                "hand_source_sha256": source_sha,
                "source_opaque_outside_roi": metrics["source_opaque_outside_roi"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "composite_verification_report.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
    )
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("task_scratch/evidence/w1-b1-r4"),
    )
    args = parser.parse_args()
    metrics = build(args.output_dir)
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
