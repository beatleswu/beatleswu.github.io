from __future__ import annotations

"""Build deterministic, non-generative A020-R2 presentation extracts.

The Owner reference is the only visual source.  This script crops the approved
forms, applies hand-authored alpha bounds to remove reference-sheet text and
frames, and composes review sheets from those extracted pixels.  It does not
generate, redraw, recolor, or reinterpret any Spirit.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "review" / "a020r2"
FORMS = EVIDENCE / "clean_forms"
SOURCE_PATH = ROOT / "docs" / "review" / "a020r1" / "A020R1_OWNER_REFERENCE_PRIMARY.jpg"
EXISTING = ROOT / "assets" / "pets"

CANVAS = (1, 11, 20, 255)
PANEL = (18, 39, 49, 255)
GOLD = (218, 164, 87, 255)
CREAM = (246, 229, 198, 255)
MUTED = (177, 191, 189, 255)
TEAL = (73, 171, 166, 255)

FONT_PATH = Path("C:/Windows/Fonts/NotoSansTC-VF.ttf")


# Coordinates are in the Owner reference image's native 1280x853 space.
# Each crop excludes the source poster's title, explanatory copy, separators,
# and outer frame.  The polygon is a presentation matte only; it never paints
# over or changes source pixels.
FORM_SPECS = {
    "spirit4_stage1": {
        "spirit": "starpath",
        "stage": "I",
        "box": (170, 176, 422, 334),
        "polygon": [(181, 181), (226, 178), (280, 188), (338, 205), (395, 230), (418, 260), (419, 328), (183, 333), (170, 307)],
    },
    "spirit4_stage2": {
        "spirit": "starpath",
        "stage": "II",
        "box": (168, 354, 424, 554),
        "polygon": [(179, 354), (226, 354), (292, 356), (356, 369), (410, 397), (423, 443), (421, 548), (177, 552), (168, 511)],
    },
    "spirit4_stage3": {
        "spirit": "starpath",
        "stage": "III",
        "box": (166, 576, 422, 814),
        "polygon": [(173, 579), (224, 576), (290, 581), (354, 590), (410, 614), (421, 657), (420, 805), (179, 810), (166, 774)],
    },
    "spirit5_stage1": {
        "spirit": "fatty",
        "stage": "I",
        "box": (594, 180, 838, 334),
        "polygon": [(601, 204), (651, 190), (712, 194), (770, 208), (818, 231), (836, 270), (835, 330), (598, 333), (590, 286)],
    },
    "spirit5_stage2": {
        "spirit": "fatty",
        "stage": "II",
        "box": (590, 354, 838, 554),
        "polygon": [(594, 354), (643, 354), (700, 356), (759, 368), (811, 392), (836, 434), (836, 548), (592, 552), (588, 493)],
    },
    "spirit5_stage3": {
        "spirit": "fatty",
        "stage": "III",
        "box": (585, 578, 838, 807),
        "polygon": [(587, 584), (637, 579), (701, 584), (762, 598), (815, 624), (836, 669), (836, 800), (588, 805), (580, 735)],
    },
    "spirit6_stage1": {
        "spirit": "obsidian",
        "stage": "I",
        "box": (974, 180, 1202, 334),
        "polygon": [(979, 184), (1032, 176), (1088, 181), (1149, 195), (1196, 223), (1200, 263), (1198, 330), (975, 333), (968, 287)],
    },
    "spirit6_stage2": {
        "spirit": "obsidian",
        "stage": "II",
        "box": (966, 354, 1210, 554),
        "polygon": [(969, 354), (1024, 354), (1085, 356), (1147, 368), (1198, 399), (1208, 444), (1206, 548), (969, 552), (958, 476)],
    },
    "spirit6_stage3": {
        "spirit": "obsidian",
        "stage": "III",
        "box": (990, 578, 1252, 810),
        "polygon": [(995, 582), (1030, 577), (1084, 584), (1147, 598), (1206, 624), (1248, 662), (1248, 800), (994, 805), (986, 738)],
    },
}

DISPLAY_NAMES = {
    "spirit4": "#4 Starpath Antlerling",
    "spirit5": "#5 阿肥 (Fatty)",
    "spirit6": "#6 Obsidian Bastion",
}


def font(size: int):
    return ImageFont.truetype(FONT_PATH, size)


def fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    result = image.copy().convert("RGBA")
    result.thumbnail(size, Image.Resampling.LANCZOS)
    return result


def extracted_form(source: Image.Image, spec: dict) -> Image.Image:
    """Return an alpha-isolated source crop with no poster chrome."""
    x1, y1, x2, y2 = spec["box"]
    crop = source.crop((x1, y1, x2, y2)).convert("RGBA")
    local_polygon = [(x - x1, y - y1) for x, y in spec["polygon"]]
    mask = Image.new("L", crop.size, 0)
    ImageDraw.Draw(mask).polygon(local_polygon, fill=255)
    # A short edge feather avoids a hard poster-edge cut while preserving the
    # approved source pixels inside the matte.
    mask = mask.filter(ImageFilter.GaussianBlur(radius=7.0))
    crop.putalpha(mask)
    bbox = mask.getbbox()
    if bbox is None:
        raise ValueError(f"empty extraction mask for {spec}")
    # Keep a modest transparent breathing room around every form so all nine
    # outputs can be placed consistently without a visible rectangular sheet.
    pad = 18
    bx1, by1, bx2, by2 = bbox
    bx1 = max(0, bx1 - pad)
    by1 = max(0, by1 - pad)
    bx2 = min(crop.width, bx2 + pad)
    by2 = min(crop.height, by2 + pad)
    result = crop.crop((bx1, by1, bx2, by2))
    # Keep the review asset corners transparent even after the soft matte is
    # cropped to its content bounds. The 8 px clear edge is outside the form
    # because the extraction above intentionally keeps 18 px of breathing room.
    final_mask = result.getchannel("A")
    edge = 8
    edge_draw = ImageDraw.Draw(final_mask)
    edge_draw.rectangle((0, 0, result.width - 1, edge - 1), fill=0)
    edge_draw.rectangle((0, result.height - edge, result.width - 1, result.height - 1), fill=0)
    edge_draw.rectangle((0, 0, edge - 1, result.height - 1), fill=0)
    edge_draw.rectangle((result.width - edge, 0, result.width - 1, result.height - 1), fill=0)
    result.putalpha(final_mask)
    return result


def save_form_images(source: Image.Image) -> dict[str, Image.Image]:
    FORMS.mkdir(parents=True, exist_ok=True)
    result = {}
    for form_id, spec in FORM_SPECS.items():
        image = extracted_form(source, spec)
        image.save(FORMS / f"A020R2_{form_id.upper()}_CLEAN.png")
        result[form_id] = image
    return result


def header(canvas: Image.Image, title: str, subtitle: str):
    draw = ImageDraw.Draw(canvas)
    draw.text((40, 24), title, fill=CREAM, font=font(36))
    draw.text((42, 70), subtitle, fill=MUTED, font=font(19))


def label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int = 21, color=CREAM):
    draw.text(xy, text, fill=color, font=font(size))


def place(canvas: Image.Image, image: Image.Image, box: tuple[int, int, int, int]):
    x1, y1, x2, y2 = box
    fitted = fit(image, (x2 - x1, y2 - y1))
    canvas.alpha_composite(fitted, (x1 + (x2 - x1 - fitted.width) // 2, y1 + (y2 - y1 - fitted.height) // 2))


def build_master(forms: dict[str, Image.Image]):
    canvas = Image.new("RGBA", (1740, 1450), CANVAS)
    header(canvas, "A020-R2 — CLEAN THREE-STAGE MASTER SHEET", "Owner-selected forms extracted from the approved reference; no redesign")
    draw = ImageDraw.Draw(canvas)
    columns = [("spirit4", 34), ("spirit5", 590), ("spirit6", 1146)]
    rows = [("I", 120), ("II", 560), ("III", 1000)]
    for spirit, x in columns:
        for stage, y in rows:
            stage_key = {"I": "1", "II": "2", "III": "3"}[stage]
            form_id = f"{spirit}_stage{stage_key}"
            label(draw, (x, y), f"{DISPLAY_NAMES[spirit]}  ·  STAGE {stage}", 21, GOLD)
            draw.line((x, y + 35, x + 500, y + 35), fill=(102, 119, 121, 255), width=1)
            place(canvas, forms[form_id], (x + 18, y + 54, x + 510, y + 380))
    canvas.convert("RGB").save(EVIDENCE / "A020R2_CLEAN_THREE_STAGE_MASTER_SHEET.png", quality=95)


def build_evolution(forms: dict[str, Image.Image], spirit: str, filename: str, title: str, subtitle: str):
    canvas = Image.new("RGBA", (1840, 830), CANVAS)
    header(canvas, title, subtitle)
    draw = ImageDraw.Draw(canvas)
    for index, stage in enumerate(("I", "II", "III")):
        x = 34 + index * 604
        label(draw, (x, 128), f"STAGE {stage}", 24, GOLD)
        draw.line((x, 166, x + 570, 166), fill=(102, 119, 121, 255), width=1)
        stage_key = {'I': '1', 'II': '2', 'III': '3'}[stage]
        place(canvas, forms[f"{spirit}_stage{stage_key}"], (x + 20, 186, x + 550, 760))
    canvas.convert("RGB").save(EVIDENCE / filename, quality=95)


def build_final_trio(forms: dict[str, Image.Image]):
    canvas = Image.new("RGBA", (1840, 820), CANVAS)
    header(canvas, "A020-R2 — CLEAN STAGE III FINAL TRIO", "Same baseline and presentation scale; extracted approved final forms")
    draw = ImageDraw.Draw(canvas)
    for index, spirit in enumerate(("spirit4", "spirit5", "spirit6")):
        x = 34 + index * 604
        label(draw, (x, 128), DISPLAY_NAMES[spirit], 24, GOLD)
        draw.line((x, 166, x + 570, 166), fill=(102, 119, 121, 255), width=1)
        place(canvas, forms[f"{spirit}_stage3"], (x + 20, 188, x + 550, 710))
    canvas.convert("RGB").save(EVIDENCE / "A020R2_CLEAN_STAGE_III_FINAL_TRIO.png", quality=95)


def load_existing(name: str) -> Image.Image:
    return Image.open(EXISTING / name).convert("RGBA")


def build_follower_scale(forms: dict[str, Image.Image]):
    canvas = Image.new("RGBA", (2140, 830), CANVAS)
    header(canvas, "A020-R2 — CLEAN SIX-SPIRIT FOLLOWER SCALE", "Actual clean character cuts; Hero remains primary; no reference-sheet cards")
    draw = ImageDraw.Draw(canvas)
    # Hero marker is intentionally larger and separated from the six followers.
    draw.ellipse((42, 300, 122, 380), fill=(232, 178, 73, 255), outline=CREAM, width=3)
    label(draw, (43, 400), "HERO", 16, GOLD)
    entries = [
        ("INK DROP", load_existing("pet_ink_drop_kelpie_lv1.webp")),
        ("VOID KIT", load_existing("pet_whispering_void_kit_lv1.webp")),
        ("HATCHLING", load_existing("pet_star_shell_hatchling_lv1.webp")),
        ("STARPATH", forms["spirit4_stage3"]),
        ("FATTY", forms["spirit5_stage3"]),
        ("OBSIDIAN", forms["spirit6_stage3"]),
    ]
    for index, (name, image) in enumerate(entries):
        x = 170 + index * 315
        draw.line((x + 18, 520, x + 250, 520), fill=(91, 113, 117, 255), width=1)
        place(canvas, image, (x + 8, 188, x + 262, 510))
        draw.ellipse((x + 110, 548, x + 148, 586), fill=TEAL, outline=CREAM, width=2)
        label(draw, (x + 54, 610), name, 16, CREAM)
    canvas.convert("RGB").save(EVIDENCE / "A020R2_CLEAN_SIX_SPIRIT_FOLLOWER_SCALE.png", quality=95)


def main():
    if not SOURCE_PATH.is_file():
        raise SystemExit(f"missing Owner reference: {SOURCE_PATH}")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    source = Image.open(SOURCE_PATH).convert("RGB")
    forms = save_form_images(source)
    build_master(forms)
    build_evolution(forms, "spirit4", "A020R2_STARPATH_CLEAN_EVOLUTION_STRIP.png", "#4 STARPATH ANTLERLING — CLEAN EVOLUTION", "EXPLORATION · newborn → growing juvenile → mature final form")
    build_evolution(forms, "spirit5", "A020R2_FATTY_CLEAN_EVOLUTION_STRIP.png", "#5 阿肥 (FATTY) — CLEAN EVOLUTION", "PRECISION · newborn puppy → younger juvenile → adult Fatty")
    build_evolution(forms, "spirit6", "A020R2_OBSIDIAN_CLEAN_EVOLUTION_STRIP.png", "#6 OBSIDIAN BASTION — CLEAN EVOLUTION", "SUPPORT · awakened core → growing mech → final guardian form")
    build_final_trio(forms)
    build_follower_scale(forms)
    print("A020R2_CLEAN_FORM_COUNT=9")
    print("A020R2_REVIEW_IMAGE_COUNT=6")


if __name__ == "__main__":
    main()
