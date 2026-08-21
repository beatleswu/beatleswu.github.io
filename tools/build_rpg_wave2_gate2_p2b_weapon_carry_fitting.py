"""Build the review-only Wave 2 P2B weapon-carry fitting prototype.

This builder keeps the existing hand-held composites as a failure reference and
derives waist/back presentations from one universal sheathed iron_sword source.
The unchanged character base is composited over the carried weapon so hands,
hair, robe, and armor remain reusable occlusion authority.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs/planning/rpg_wave2_gate2_p2b_weapon_carry_manifest.json"
ASSET_DIR = ROOT / "docs/planning/rpg_wave2_gate2_p2_wearable_fitting_assets/p2b_weapon_carry"
COMPOSITE_DIR = ASSET_DIR / "composites"
CONTACT_SHEET = ROOT / "docs/planning/rpg_wave2_gate2_p2b_weapon_carry_contact_sheet.png"

# Reuse the already-reviewed matte-removal implementation for the new
# imagegen source. This keeps the new source extraction deterministic and does
# not duplicate a second alpha-cleaning contract.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.build_rpg_wave2_gate2_p2_wearable_fitting import _extract_cutout  # noqa: E402


CHARACTERS = ("apprentice", "mage", "paladin")
MODES = ("current_held", "waist_sheathed", "back_mounted")


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _path(relative: str) -> Path:
    return ROOT / relative


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _save_rgba(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def _transform_carry(cutout: Image.Image, mode: dict, character: str) -> Image.Image:
    target_height = mode["target_height"]
    target_width = round(cutout.width * target_height / cutout.height)
    resized = cutout.resize((target_width, target_height), Image.Resampling.LANCZOS)
    rotated = resized.rotate(
        mode["rotation_degrees"],
        expand=True,
        resample=Image.Resampling.BICUBIC,
    )

    # Track the hilt anchor through the exact same resize/rotation operation as
    # the art instead of guessing a post-rotation bounding-box ratio.
    anchor_x, anchor_y = mode["source_hilt_anchor_ratio"]
    marker = Image.new("L", resized.size, 0)
    marker_draw = ImageDraw.Draw(marker)
    marker_x = round(anchor_x * resized.width)
    marker_y = round(anchor_y * resized.height)
    marker_draw.ellipse(
        (marker_x - 5, marker_y - 5, marker_x + 5, marker_y + 5),
        fill=255,
    )
    rotated_marker = marker.rotate(
        mode["rotation_degrees"],
        expand=True,
        resample=Image.Resampling.BICUBIC,
    )
    marker_bbox = rotated_marker.getbbox()
    if marker_bbox is None:
        raise ValueError("carry hilt anchor was lost during transform")
    rotated_anchor_x = (marker_bbox[0] + marker_bbox[2]) / 2
    rotated_anchor_y = (marker_bbox[1] + marker_bbox[3]) / 2
    target_x, target_y = mode["hilt_anchor_positions"][character]
    left = round(target_x - rotated_anchor_x)
    top = round(target_y - rotated_anchor_y)

    layer = Image.new("RGBA", (1056, 1408), (0, 0, 0, 0))
    layer.alpha_composite(rotated, (left, top))
    return layer


def _compose_carried(base: Image.Image, carry_layer: Image.Image) -> Image.Image:
    # The character base is intentionally above the carry layer. This is the
    # reusable body/hair/hand/robe/armor occlusion rule for static projection.
    return Image.alpha_composite(carry_layer, base)


def _build_contact_sheet(manifest: dict, composites: dict[tuple[str, str], Image.Image]) -> None:
    rows = (
        ("CURRENT_HAND_HELD · reference / FAIL", "current_held"),
        ("WAIST_SHEATHED", "waist_sheathed"),
        ("BACK_MOUNTED", "back_mounted"),
    )
    cell_width = 350
    cell_height = 475
    gap = 18
    margin = 28
    header_height = 100
    sheet_width = margin * 2 + cell_width * 3 + gap * 2
    sheet_height = header_height + margin + cell_height * 3 + gap * 2 + margin
    sheet = Image.new("RGB", (sheet_width, sheet_height), "#eef3f7")
    draw = ImageDraw.Draw(sheet)
    draw.text(
        (margin, 25),
        "Wave 2 Gate 2 P2B — Weapon Carry Fitting",
        fill="#223047",
        font=_font(30, bold=True),
    )
    draw.text(
        (margin, 64),
        "Equal 300×400 render scale · one sheathed overlay · PLAYER_FRAME_A_STANDARD_CHIBI",
        fill="#617087",
        font=_font(17),
    )

    for row_index, (row_label, mode_id) in enumerate(rows):
        top = header_height + margin + row_index * (cell_height + gap)
        for column, character in enumerate(CHARACTERS):
            left = margin + column * (cell_width + gap)
            draw.rounded_rectangle(
                (left, top, left + cell_width, top + cell_height),
                radius=18,
                fill="#ffffff",
                outline="#cad5e1",
                width=2,
            )
            image = composites[(character, mode_id)].resize((300, 400), Image.Resampling.LANCZOS)
            backdrop = Image.new("RGBA", (300, 400), "#f8fbfd")
            backdrop.alpha_composite(image)
            sheet.paste(backdrop.convert("RGB"), (left + 25, top + 42))
            draw.text(
                (left + 18, top + 12),
                f"{character.title()} · {row_label}",
                fill="#2a3b52",
                font=_font(15, bold=True),
            )
            if mode_id == "current_held":
                result = "FAIL · OPEN HAND"
                fill = "#a52828"
            elif mode_id == "waist_sheathed":
                result = "PASS"
                fill = "#17635e"
            else:
                result = "PASS · MINOR OFFSET"
                fill = "#8a5b15"
            draw.text((left + 18, top + 449), result, fill=fill, font=_font(13, bold=True))

    CONTACT_SHEET.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(CONTACT_SHEET, format="PNG", optimize=True)


def build() -> None:
    manifest = _manifest()
    if tuple(manifest["player_frame"]["canvas"]) != (1056, 1408):
        raise ValueError("P2B must preserve the canonical 1056x1408 frame")

    source = _path(manifest["weapon"]["carry_source"])
    cutout_path = _path(manifest["weapon"]["carry_cutout"])
    cutout = _extract_cutout(source, "iron_sword")
    _save_rgba(cutout, cutout_path)

    composites: dict[tuple[str, str], Image.Image] = {}
    for character in CHARACTERS:
        base = Image.open(_path(manifest["characters"][character])).convert("RGBA")
        if base.size != (1056, 1408):
            raise ValueError(f"unexpected base size for {character}: {base.size}")

        held_path = _path(manifest["weapon"]["held_reference"].format(character=character))
        held = Image.open(held_path).convert("RGBA")
        composites[(character, "current_held")] = held
        _save_rgba(held, COMPOSITE_DIR / f"{character}_current_held.png")

        for mode_id in ("waist_sheathed", "back_mounted"):
            carry_layer = _transform_carry(cutout, manifest["modes"][mode_id], character)
            composite = _compose_carried(base, carry_layer)
            composites[(character, mode_id)] = composite
            _save_rgba(composite, COMPOSITE_DIR / f"{character}_{mode_id}.png")

    _build_contact_sheet(manifest, composites)
    print(
        json.dumps(
            {
                "player_frame": manifest["player_frame"]["id"],
                "characters": len(CHARACTERS),
                "modes": len(MODES),
                "review_composites": len(CHARACTERS) * len(MODES),
                "contact_sheet": str(CONTACT_SHEET.relative_to(ROOT)),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    build()
