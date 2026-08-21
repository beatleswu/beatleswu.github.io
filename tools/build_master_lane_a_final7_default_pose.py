"""Build the Final7 default-pose review pack from imagegen provenance inputs.

This is an asset-packaging helper only. It does not register characters, alter
runtime selection, or change equipment/combat authority.
"""

from __future__ import annotations

from collections import deque
import json
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


CANVAS = (1056, 1408)
TARGET_VISIBLE_HEIGHT = 1324
FOOT_BASELINE = 1373
SAFE_SIDE = 106
PACKAGE_DIR = Path("docs/planning/rpg_wave2_master_lane_a_final7_default_pose")
RAW_DIR = PACKAGE_DIR / "sources/generated_raw"
BUILT_DIR = PACKAGE_DIR / "built"
ASSET_DIR = Path("assets/hero/characters/wave2_final7_default_pose_v1")

CHARACTERS = (
    "river_wayfinder",
    "stone_caretaker",
    "duelist_scout",
    "bastion_warden",
    "forest_pathfinder",
    "archive_scholar",
    "worldkeeper",
)

DISPLAY_NAMES = {
    "river_wayfinder": "River Wayfinder",
    "stone_caretaker": "Stone Caretaker",
    "duelist_scout": "Duelist Scout",
    "bastion_warden": "Bastion Warden",
    "forest_pathfinder": "Forest Pathfinder",
    "archive_scholar": "Archive Scholar",
    "worldkeeper": "Worldkeeper",
}


def _font(size: int, bold: bool = False):
    candidates = (
        Path("C:/Windows/Fonts/segoeuib.ttf"),
        Path("C:/Windows/Fonts/seguisb.ttf"),
    ) if bold else (
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/seguis.ttf"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def _is_checkerboard_pixel(pixel: tuple[int, int, int]) -> bool:
    low = min(pixel)
    high = max(pixel)
    return low >= 220 and high - low <= 28


def _edge_connected_checkerboard_mask(image: Image.Image) -> bytearray:
    """Return pixels reachable from the canvas edge through checkerboard-like pixels."""

    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    mask = bytearray(width * height)
    queue: deque[int] = deque()

    def seed(x: int, y: int) -> None:
        index = y * width + x
        if not mask[index] and _is_checkerboard_pixel(pixels[x, y]):
            mask[index] = 1
            queue.append(index)

    for x in range(width):
        seed(x, 0)
        seed(x, height - 1)
    for y in range(height):
        seed(0, y)
        seed(width - 1, y)

    while queue:
        index = queue.popleft()
        x = index % width
        y = index // width
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            neighbour = ny * width + nx
            if mask[neighbour]:
                continue
            if _is_checkerboard_pixel(pixels[nx, ny]):
                mask[neighbour] = 1
                queue.append(neighbour)
    return mask


def _transparent_master(source: Path) -> Image.Image:
    source_image = Image.open(source).convert("RGB")
    width, height = source_image.size
    background = _edge_connected_checkerboard_mask(source_image)
    alpha = Image.new("L", source_image.size, 255)
    alpha_pixels = alpha.load()
    for index, value in enumerate(background):
        if value:
            alpha_pixels[index % width, index // width] = 0
        else:
            x = index % width
            y = index // width
            touches_background = any(
                0 <= nx < width
                and 0 <= ny < height
                and background[ny * width + nx]
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
            )
            if touches_background:
                # Generated RGB inputs contain a neutral checkerboard matte.
                # Only attenuate bright neutral boundary pixels; saturated
                # costume edges and dark outlines remain untouched.
                pixel = source_image.getpixel((x, y))
                low = min(pixel)
                high = max(pixel)
                if low >= 205 and high - low <= 40:
                    alpha_pixels[x, y] = max(0, min(255, (235 - low) * 6))
    source_image.putalpha(alpha)

    # Normalize the visible body to the same production frame used by P1.
    bbox = source_image.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError(f"No visible pixels after alpha cleanup: {source}")
    cropped = source_image.crop(bbox)
    scale = TARGET_VISIBLE_HEIGHT / cropped.height
    visible_width = max(1, round(cropped.width * scale))
    visible_height = TARGET_VISIBLE_HEIGHT
    if visible_width > CANVAS[0] - 2 * SAFE_SIDE:
        scale = (CANVAS[0] - 2 * SAFE_SIDE) / cropped.width
        visible_width = CANVAS[0] - 2 * SAFE_SIDE
        visible_height = max(1, round(cropped.height * scale))
    cropped = cropped.resize((visible_width, visible_height), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    left = (CANVAS[0] - visible_width) // 2
    top = FOOT_BASELINE - visible_height
    canvas.alpha_composite(cropped, (left, top))
    return canvas


def _fit(image: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    copy = image.copy()
    copy.thumbnail((width, height), Image.Resampling.LANCZOS)
    return copy


def _paste_centered(base: Image.Image, image: Image.Image, box: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = box
    fitted = _fit(image, box)
    x = left + (right - left - fitted.width) // 2
    y = top + (bottom - top - fitted.height) // 2
    base.alpha_composite(fitted, (x, y))


def _card(base: Image.Image, image: Image.Image, name: str, box: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = box
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle((left, top, right, bottom), radius=18, fill=(31, 52, 72), outline=(100, 151, 180), width=2)
    draw.text((left + 18, top + 13), DISPLAY_NAMES[name], font=_font(24, True), fill=(246, 231, 183))
    draw.text((left + 18, bottom - 38), name, font=_font(16), fill=(166, 207, 218))
    _paste_centered(base, image, (left + 14, top + 54, right - 14, bottom - 50))


def _desktop_matrix(images: dict[str, Image.Image]) -> Image.Image:
    width, height = 1760, 1080
    base = Image.new("RGBA", (width, height), (14, 28, 44, 255))
    draw = ImageDraw.Draw(base)
    draw.text((40, 24), "FINAL7 DEFAULT POSE · OWNER REVIEW", font=_font(38, True), fill=(246, 231, 183))
    draw.text((42, 70), "Seven approved identities · unified player visual family · presentation only", font=_font(18), fill=(166, 207, 218))
    card_w, card_h = 400, 450
    margin_x, gap_x, top = 40, 28, 122
    for index, name in enumerate(CHARACTERS):
        row, col = divmod(index, 4)
        x = margin_x + col * (card_w + gap_x)
        y = top + row * (card_h + 26)
        _card(base, images[name], name, (x, y, x + card_w, y + card_h))
    draw.rounded_rectangle((40, 1010, width - 40, 1056), radius=14, fill=(22, 58, 72), outline=(51, 205, 198), width=2)
    draw.text((60, 1021), "DEFAULT POSE · IDENTITY PRESERVED · EMPTY HANDS · NO FUNCTIONAL WEAPON BAKED IN", font=_font(18, True), fill=(181, 244, 224))
    return base


def _mobile_matrix(images: dict[str, Image.Image]) -> Image.Image:
    width, card_w, card_h, gap, top = 1000, 465, 386, 18, 112
    height = top + 4 * card_h + 3 * gap + 72
    base = Image.new("RGBA", (width, height), (14, 28, 44, 255))
    draw = ImageDraw.Draw(base)
    draw.text((30, 22), "FINAL7 DEFAULT POSE · MOBILE SCALE", font=_font(34, True), fill=(246, 231, 183))
    draw.text((32, 68), "Approximate Hero-card presentation", font=_font(17), fill=(166, 207, 218))
    for index, name in enumerate(CHARACTERS):
        row, col = divmod(index, 2)
        x = 22 + col * (card_w + gap)
        y = top + row * (card_h + gap)
        _card(base, images[name], name, (x, y, x + card_w, y + card_h))
    return base


def _scale_lineup(images: dict[str, Image.Image]) -> Image.Image:
    width, height = 2240, 520
    base = Image.new("RGBA", (width, height), (14, 28, 44, 255))
    draw = ImageDraw.Draw(base)
    draw.text((36, 20), "FINAL7 DEFAULT POSE · SCALE LINEUP", font=_font(30, True), fill=(246, 231, 183))
    card_w = 300
    for index, name in enumerate(CHARACTERS):
        x = 28 + index * 316
        draw.rounded_rectangle((x, 76, x + card_w, 488), radius=16, fill=(31, 52, 72), outline=(100, 151, 180), width=2)
        _paste_centered(base, images[name], (x + 12, 90, x + card_w - 12, 432))
        label = DISPLAY_NAMES[name]
        text_width = draw.textbbox((0, 0), label, font=_font(17, True))[2]
        draw.text((x + (card_w - text_width) // 2, 445), label, font=_font(17, True), fill=(246, 231, 183))
    return base


def build() -> None:
    BUILT_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    images: dict[str, Image.Image] = {}
    manifest_records = []
    for name in CHARACTERS:
        source = RAW_DIR / f"{name}_generated_raw.png"
        image = _transparent_master(source)
        images[name] = image
        png = ASSET_DIR / f"{name}_default_pose_v1.png"
        webp = ASSET_DIR / f"{name}_default_pose_v1.webp"
        image.save(png, "PNG", optimize=True)
        image.save(webp, "WEBP", lossless=True, quality=100, method=6)
        bbox = image.getchannel("A").getbbox()
        manifest_records.append({
            "character_id": name,
            "display_name": DISPLAY_NAMES[name],
            "source": str(source).replace("\\", "/"),
            "png": str(png).replace("\\", "/"),
            "webp": str(webp).replace("\\", "/"),
            "canvas": {"width": CANVAS[0], "height": CANVAS[1], "format": "RGBA"},
            "visible_bbox": list(bbox) if bbox else None,
            "foot_baseline_y": FOOT_BASELINE,
            "functional_weapon_baked_in": False,
            "authority": "presentation_only",
            "status": "PRODUCTION_CANDIDATE_OWNER_REVIEW",
        })

    _desktop_matrix(images).save(BUILT_DIR / "FINAL7_DEFAULT_POSE_MATRIX.png", "PNG", optimize=True)
    _mobile_matrix(images).save(BUILT_DIR / "FINAL7_DEFAULT_POSE_MOBILE_MATRIX.png", "PNG", optimize=True)
    _scale_lineup(images).save(BUILT_DIR / "FINAL7_DEFAULT_POSE_SCALE_LINEUP.png", "PNG", optimize=True)

    manifest = {
        "package": "GO_ODYSSEY_MASTER_LANE_A_FINAL7_DEFAULT_POSE_V1",
        "status": "PRODUCTION_CANDIDATE_OWNER_REVIEW",
        "characters": manifest_records,
        "master_canvas": "1056x1408 RGBA",
        "source_master": "PNG",
        "runtime_derivative": "WebP",
        "foot_baseline": "y=.975",
        "functional_weapon_baked_in_base_art": False,
        "character_combat_authority": "NO",
        "runtime_registration": "NOT_CHANGED",
        "owner_gate": "PENDING_OWNER_VISUAL_REVIEW",
        "review_artifacts": [
            str(BUILT_DIR / "FINAL7_DEFAULT_POSE_MATRIX.png").replace("\\", "/"),
            str(BUILT_DIR / "FINAL7_DEFAULT_POSE_MOBILE_MATRIX.png").replace("\\", "/"),
            str(BUILT_DIR / "FINAL7_DEFAULT_POSE_SCALE_LINEUP.png").replace("\\", "/"),
        ],
    }
    (PACKAGE_DIR / "final7_default_pose_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
