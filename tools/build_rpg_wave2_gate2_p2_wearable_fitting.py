"""Build the review-only Wave 2 Gate 2 P2 wearable fitting prototype.

The renderer consumes the approved 1056x1408 P1 character masters and three
wearable-only source drawings.  It never reads gameplay state and never writes
runtime assets, APIs, or databases.  All generated output stays under the
planning/review paths declared in the manifest.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    ROOT / "docs/planning/rpg_wave2_gate2_p2_wearable_fitting_manifest.json"
)
ASSET_DIR = (
    ROOT / "docs/planning/rpg_wave2_gate2_p2_wearable_fitting_assets"
)
CONTACT_SHEET = (
    ROOT / "docs/planning/rpg_wave2_gate2_p2_wearable_fitting_contact_sheet.png"
)


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


def _center_component(mask: np.ndarray) -> np.ndarray:
    """Keep the connected foreground component nearest the image centre."""

    binary = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
    binary = binary.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    array = np.asarray(binary) > 0
    ys, xs = np.nonzero(array)
    if not len(xs):
        raise ValueError("generated source did not yield a foreground component")
    centre_x = array.shape[1] / 2
    centre_y = array.shape[0] / 2
    nearest = np.argmin((xs - centre_x) ** 2 + (ys - centre_y) ** 2)
    seed = (int(xs[nearest]), int(ys[nearest]))

    labelled = binary.copy()
    ImageDraw.floodfill(labelled, seed, 128, thresh=0)
    component = np.asarray(labelled) == 128

    # Fill accidental matte-colour holes inside the object silhouette.  True
    # wearable openings are punched explicitly below.
    # ``Image.fromarray`` may share a read-only NumPy buffer; copy so Pillow's
    # flood fill can mutate the exterior mask on every supported version.
    inverse = Image.fromarray(
        (~component).astype(np.uint8) * 255, mode="L"
    ).copy()
    ImageDraw.floodfill(inverse, (0, 0), 128, thresh=0)
    return np.asarray(inverse) != 128


def _extract_cutout(source: Path, item_id: str) -> Image.Image:
    """Remove the generated checker matte and return neutral-alpha RGBA art."""

    source_image = Image.open(source).convert("RGB")
    rgb = np.asarray(source_image).astype(np.int16)
    maximum = rgb.max(axis=2)
    minimum = rgb.min(axis=2)
    mean = rgb.mean(axis=2)
    chroma = maximum - minimum

    # Generated preview mattes are near-neutral and brighter than the object.
    # The large central object is then isolated by connected-component fill,
    # preserving light steel and ivory pixels enclosed by its outline.
    # Use a deliberately strict seed so tiny colour noise in the baked preview
    # checker cannot bridge into one giant rectangular component.  Bright
    # steel/ivory interiors are recovered by the silhouette hole fill below.
    seed = (chroma > 12) | (mean < 228)
    height, width = seed.shape
    crop_fractions = {
        "iron_sword": (0.30, 0.05, 0.72, 0.95),
        "dragon_scale": (0.04, 0.08, 0.96, 0.92),
        "fox_mask": (0.16, 0.06, 0.84, 0.92),
    }
    left, top, right, bottom = crop_fractions[item_id]
    allowed = np.zeros_like(seed)
    allowed[
        int(top * height) : int(bottom * height),
        int(left * width) : int(right * width),
    ] = True
    silhouette = _center_component(seed & allowed)

    alpha = Image.fromarray(silhouette.astype(np.uint8) * 255, mode="L")
    draw = ImageDraw.Draw(alpha)
    if item_id == "fox_mask":
        # Preserve the two true eye openings instead of filling them with the
        # generated checker preview.
        draw.polygon(
            [
                (int(width * 0.255), int(height * 0.515)),
                (int(width * 0.345), int(height * 0.525)),
                (int(width * 0.438), int(height * 0.625)),
                (int(width * 0.405), int(height * 0.650)),
                (int(width * 0.315), int(height * 0.625)),
                (int(width * 0.245), int(height * 0.555)),
            ],
            fill=0,
        )
        draw.polygon(
            [
                (int(width * 0.745), int(height * 0.515)),
                (int(width * 0.655), int(height * 0.525)),
                (int(width * 0.562), int(height * 0.625)),
                (int(width * 0.595), int(height * 0.650)),
                (int(width * 0.685), int(height * 0.625)),
                (int(width * 0.755), int(height * 0.555)),
            ],
            fill=0,
        )
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.7))

    rgba = source_image.convert("RGBA")
    rgba.putalpha(alpha)
    array = np.asarray(rgba).copy()
    array[array[:, :, 3] == 0, :3] = 0
    rgba = Image.fromarray(array, mode="RGBA")
    bbox = rgba.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError(f"empty cutout for {item_id}")
    margin = 8
    left = max(0, bbox[0] - margin)
    top = max(0, bbox[1] - margin)
    right = min(rgba.width, bbox[2] + margin)
    bottom = min(rgba.height, bbox[3] + margin)
    return rgba.crop((left, top, right, bottom))


def _build_hair_front_mask(base: Image.Image, character_id: str) -> Image.Image:
    """Extract one reusable hair-front patch for each approved character."""

    rgba = base.convert("RGBA")
    rgb = np.asarray(rgba.convert("RGB")).astype(np.int16)
    alpha = np.asarray(rgba.getchannel("A"))
    red, green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    allowed = np.zeros(alpha.shape, dtype=bool)
    allowed_boxes = {
        "apprentice": [(300, 35, 760, 215), (330, 175, 455, 315), (600, 175, 730, 315)],
        "mage": [(325, 35, 735, 260), (330, 145, 475, 560), (580, 145, 735, 560)],
        "paladin": [(315, 35, 750, 295)],
    }[character_id]
    for x0, y0, x1, y1 in allowed_boxes:
        allowed[y0:y1, x0:x1] = True

    if character_id == "apprentice":
        # Brown/copper hair; exclude the brighter peach face palette.
        hair_colour = (
            (red < 235)
            & (green < 175)
            & (blue < 120)
            & (red > green + 18)
            & (green > blue + 12)
        )
    elif character_id == "mage":
        # Lavender hair has blue above both red and green; the navy/purple robe
        # is excluded by a minimum red-channel brightness.
        hair_colour = (
            (red > 105)
            & (blue > red + 4)
            & (blue > green + 4)
            & (green > 90)
        )
        # Keep the eye/face opening clear while retaining the centre fringe.
        hair_colour[210:315, 455:605] = False
    else:
        # Gold hair; the paladin's peach face is bluer and the costume is below
        # the allowed head region.
        hair_colour = (
            (red > 180)
            & (green > 125)
            & (blue < 190)
            & (red > green + 8)
            & (green > blue + 18)
        )

    mask = hair_colour & allowed & (alpha > 32)
    mask_image = Image.fromarray(mask.astype(np.uint8) * 255, mode="L")
    mask_image = mask_image.filter(ImageFilter.MaxFilter(5)).filter(
        ImageFilter.GaussianBlur(0.75)
    )
    mask_array = np.asarray(mask_image).astype(np.uint16)
    combined_alpha = ((mask_array * alpha.astype(np.uint16)) // 255).astype(np.uint8)

    output = rgba.copy()
    output.putalpha(Image.fromarray(combined_alpha, mode="L"))
    output_array = np.asarray(output).copy()
    output_array[output_array[:, :, 3] == 0, :3] = 0
    return Image.fromarray(output_array, mode="RGBA")


def _transform_cutout(
    cutout: Image.Image,
    item: dict,
    character: dict,
) -> Image.Image:
    canvas_width, canvas_height = (1056, 1408)
    scale = character["wearable_scale"][item["id"]]
    if item.get("target_height"):
        target_height = round(item["target_height"] * scale)
        target_width = round(cutout.width * target_height / cutout.height)
    else:
        target_width = round(item["target_width"] * scale)
        target_height = round(cutout.height * target_width / cutout.width)

    transformed = cutout.resize(
        (target_width, target_height), Image.Resampling.LANCZOS
    )
    anchor_x, anchor_y = item["source_anchor"]
    if item.get("mirror_for_viewer_right_hand"):
        transformed = ImageOps.mirror(transformed)
        anchor_x = 1.0 - anchor_x

    if item["slot"] == "weapon":
        target_x, target_y = character["anchors"]["viewer_right_hand"]
    elif item["slot"] == "armor":
        target_x, target_y = character["anchors"]["torso"]
    else:
        target_x, target_y = character["anchors"]["face"]

    left = round(target_x - anchor_x * transformed.width)
    top = round(target_y - anchor_y * transformed.height)
    layer = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    layer.alpha_composite(transformed, (left, top))
    return layer


def _compose(
    base: Image.Image,
    overlays: dict[str, Image.Image],
    hair_front: Image.Image,
    loadout: str,
) -> Image.Image:
    enabled = (
        {"iron_sword", "dragon_scale", "fox_mask"}
        if loadout == "full"
        else {loadout}
    )
    output = Image.new("RGBA", base.size, (0, 0, 0, 0))
    if "iron_sword" in enabled:
        output = Image.alpha_composite(output, overlays["iron_sword"])
    output = Image.alpha_composite(output, base)
    if "dragon_scale" in enabled:
        output = Image.alpha_composite(output, overlays["dragon_scale"])
    if "fox_mask" in enabled:
        output = Image.alpha_composite(output, overlays["fox_mask"])
    if enabled & {"dragon_scale", "fox_mask"}:
        output = Image.alpha_composite(output, hair_front)
    return output


def _save_rgba(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def _build_contact_sheet(manifest: dict, composites: dict[tuple[str, str], Image.Image]) -> None:
    characters = ["apprentice", "mage", "paladin"]
    rows = [
        ("Original / no equipment", None),
        ("iron_sword", "iron_sword"),
        ("dragon_scale", "dragon_scale"),
        ("fox_mask", "fox_mask"),
        ("Full loadout", "full"),
    ]
    cell_width = 350
    cell_height = 475
    gap = 18
    margin = 28
    header_height = 100
    sheet_width = margin * 2 + cell_width * 3 + gap * 2
    sheet_height = header_height + margin + cell_height * 5 + gap * 4 + margin
    sheet = Image.new("RGB", (sheet_width, sheet_height), "#eef3f7")
    draw = ImageDraw.Draw(sheet)
    draw.text(
        (margin, 25),
        "Wave 2 Gate 2 P2 — Wearable Fitting Contact Sheet",
        fill="#223047",
        font=_font(30, bold=True),
    )
    draw.text(
        (margin, 64),
        "Identical 300×400 render scale · PLAYER_FRAME_A_STANDARD_CHIBI · review only",
        fill="#617087",
        font=_font(17),
    )

    for row_index, (row_label, loadout) in enumerate(rows):
        top = header_height + margin + row_index * (cell_height + gap)
        for column, character_id in enumerate(characters):
            left = margin + column * (cell_width + gap)
            draw.rounded_rectangle(
                (left, top, left + cell_width, top + cell_height),
                radius=18,
                fill="#ffffff",
                outline="#cad5e1",
                width=2,
            )
            if loadout is None:
                image = Image.open(_path(manifest["characters"][character_id]["base"])).convert("RGBA")
            else:
                image = composites[(character_id, loadout)]
            scaled = image.resize((300, 400), Image.Resampling.LANCZOS)
            backdrop = Image.new("RGBA", (300, 400), "#f8fbfd")
            backdrop.alpha_composite(scaled)
            sheet.paste(backdrop.convert("RGB"), (left + 25, top + 42))
            draw.text(
                (left + 18, top + 12),
                f"{character_id.replace('_', ' ').title()} · {row_label}",
                fill="#2a3b52",
                font=_font(15, bold=True),
            )
            result = "BASE" if loadout is None else next(
                entry["result"]
                for entry in manifest["qa_matrix"]
                if entry["character"] == character_id and entry["loadout"] == loadout
            )
            draw.text(
                (left + 18, top + 449),
                result,
                fill="#17635e" if result != "FAIL" else "#a52828",
                font=_font(13, bold=True),
            )
    CONTACT_SHEET.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(CONTACT_SHEET, format="PNG", optimize=True)


def build() -> None:
    manifest = _manifest()
    if tuple(manifest["player_frame"]["canvas"]) != (1056, 1408):
        raise ValueError("prototype must preserve the canonical 1056x1408 frame")

    cutouts: dict[str, Image.Image] = {}
    equipment: dict[str, dict] = {}
    for item_id, source_item in manifest["equipment"].items():
        item = dict(source_item)
        item["id"] = item_id
        cutout = _extract_cutout(_path(item["generated_source"]), item_id)
        _save_rgba(cutout, _path(item["normalized_cutout"]))
        cutouts[item_id] = cutout
        equipment[item_id] = item

    composites: dict[tuple[str, str], Image.Image] = {}
    for character_id, character in manifest["characters"].items():
        base = Image.open(_path(character["base"])).convert("RGBA")
        if base.size != (1056, 1408):
            raise ValueError(f"unexpected base size for {character_id}: {base.size}")
        hair_front = _build_hair_front_mask(base, character_id)
        _save_rgba(
            hair_front,
            _path(manifest["occlusion"]["masks"][character_id]),
        )
        overlays = {
            item_id: _transform_cutout(cutout, equipment[item_id], character)
            for item_id, cutout in cutouts.items()
        }
        if character_id == "apprentice":
            for item_id, overlay in overlays.items():
                _save_rgba(overlay, _path(equipment[item_id]["canonical_overlay"]))

        for loadout in ("iron_sword", "dragon_scale", "fox_mask", "full"):
            composite = _compose(base, overlays, hair_front, loadout)
            composites[(character_id, loadout)] = composite
            _save_rgba(
                composite,
                ASSET_DIR / "composites" / f"{character_id}_{loadout}.png",
            )

    _build_contact_sheet(manifest, composites)
    print(
        json.dumps(
            {
                "player_frame": manifest["player_frame"]["id"],
                "universal_overlays": len(cutouts),
                "character_reusable_masks": len(manifest["occlusion"]["masks"]),
                "single_item_composites": 9,
                "full_loadout_composites": 3,
                "contact_sheet": str(CONTACT_SHEET.relative_to(ROOT)),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    build()
