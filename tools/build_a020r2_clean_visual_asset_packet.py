from __future__ import annotations

"""Build deterministic, non-generative A020-R2 presentation extracts.

The corrected Owner clean-source is the only visual source for the nine new
forms. It is a 3x3 checkerboard-backed sheet. This script removes only the
checkerboard background, crops each supplied form, and composes review sheets.
It does not generate, redraw, recolor, or reinterpret any Spirit.
"""

from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "review" / "a020r2"
FORMS = EVIDENCE / "clean_forms"
SOURCE_PATH = EVIDENCE / "A020R2_OWNER_CLEAN_SOURCE.jpg"
EXISTING = ROOT / "assets" / "pets"

CANVAS = (10, 24, 33, 255)
GOLD = (218, 164, 87, 255)
CREAM = (246, 229, 198, 255)
MUTED = (177, 191, 189, 255)
TEAL = (73, 171, 166, 255)

FONT_PATH = Path("C:/Windows/Fonts/NotoSansTC-VF.ttf")


# The corrected Owner source is a 3x3 presentation grid in native 1254x1254
# space. The visible character rows do not occupy mathematically equal thirds;
# these boxes follow the actual supplied character extents and leave the
# inter-row whitespace out of each clean cut. Columns likewise stop before the
# adjacent form begins so no neighboring fragments enter the alpha matte.
FORM_SPECS = {
    "spirit4_stage1": {"box": (0, 0, 405, 370)},
    "spirit4_stage2": {"box": (405, 0, 830, 370)},
    "spirit4_stage3": {"box": (830, 0, 1254, 370)},
    "spirit5_stage1": {"box": (0, 375, 405, 780)},
    "spirit5_stage2": {"box": (405, 375, 810, 780)},
    "spirit5_stage3": {"box": (810, 375, 1254, 780)},
    "spirit6_stage1": {"box": (0, 790, 405, 1254)},
    "spirit6_stage2": {"box": (405, 790, 810, 1254)},
    "spirit6_stage3": {"box": (810, 790, 1254, 1254)},
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


def checkerboard_background_mask(source: Image.Image) -> Image.Image:
    """Keep foreground pixels and clear light-gray pixels connected to edges."""
    source = source.convert("RGB")
    width, height = source.size
    pixels = source.load()
    candidate = bytearray(width * height)

    for y in range(height):
        row = y * width
        for x in range(width):
            red, green, blue = pixels[x, y]
            # The supplied checkerboard is near-neutral and light. Keeping the
            # color-range test protects white dog/mech details enclosed by dark
            # outlines while allowing JPEG edge noise around the checkerboard.
            if min(red, green, blue) >= 210 and max(red, green, blue) - min(red, green, blue) <= 18:
                candidate[row + x] = 1

    visited = bytearray(width * height)
    queue: deque[int] = deque()

    def seed(index: int):
        if candidate[index] and not visited[index]:
            visited[index] = 1
            queue.append(index)

    for x in range(width):
        seed(x)
        seed((height - 1) * width + x)
    for y in range(height):
        seed(y * width)
        seed(y * width + width - 1)

    while queue:
        index = queue.popleft()
        x = index % width
        y = index // width
        if x:
            seed(index - 1)
        if x + 1 < width:
            seed(index + 1)
        if y:
            seed(index - width)
        if y + 1 < height:
            seed(index + width)

    mask = Image.new("L", (width, height), 255)
    mask_pixels = mask.load()
    for index, is_background in enumerate(visited):
        if is_background:
            mask_pixels[index % width, index // width] = 0
    return mask.filter(ImageFilter.GaussianBlur(radius=0.8))


def extracted_form(source: Image.Image, background_mask: Image.Image, spec: dict) -> Image.Image:
    """Return a transparent clean cut from the supplied Owner pixels."""
    x1, y1, x2, y2 = spec["box"]
    crop = source.crop((x1, y1, x2, y2)).convert("RGBA")
    mask = background_mask.crop((x1, y1, x2, y2))
    crop.putalpha(mask)

    trim_mask = mask.point(lambda value: 255 if value > 32 else 0)
    bbox = trim_mask.getbbox()
    if bbox is None:
        raise ValueError(f"empty extraction mask for {spec}")

    pad = 14
    bx1, by1, bx2, by2 = bbox
    bx1 = max(0, bx1 - pad)
    by1 = max(0, by1 - pad)
    bx2 = min(crop.width, bx2 + pad)
    by2 = min(crop.height, by2 + pad)
    result = crop.crop((bx1, by1, bx2, by2))

    # Keep the asset corners transparent after trimming. This prevents any
    # residual checkerboard edge from reading as a rectangular screenshot.
    final_mask = result.getchannel("A")
    edge = 6
    edge_draw = ImageDraw.Draw(final_mask)
    edge_draw.rectangle((0, 0, result.width - 1, edge - 1), fill=0)
    edge_draw.rectangle((0, result.height - edge, result.width - 1, result.height - 1), fill=0)
    edge_draw.rectangle((0, 0, edge - 1, result.height - 1), fill=0)
    edge_draw.rectangle((result.width - edge, 0, result.width - 1, result.height - 1), fill=0)
    result.putalpha(final_mask)
    return result


def save_form_images(source: Image.Image, background_mask: Image.Image) -> dict[str, Image.Image]:
    FORMS.mkdir(parents=True, exist_ok=True)
    result = {}
    for form_id, spec in FORM_SPECS.items():
        image = extracted_form(source, background_mask, spec)
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
    header(canvas, "A020-R2 — CLEAN THREE-STAGE MASTER SHEET", "Owner-selected forms extracted from the corrected clean-source; no redesign")
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
        stage_key = {"I": "1", "II": "2", "III": "3"}[stage]
        place(canvas, forms[f"{spirit}_stage{stage_key}"], (x + 20, 186, x + 550, 760))
    canvas.convert("RGB").save(EVIDENCE / filename, quality=95)


def build_final_trio(forms: dict[str, Image.Image]):
    canvas = Image.new("RGBA", (1840, 820), CANVAS)
    header(canvas, "A020-R2 — CLEAN STAGE III FINAL TRIO", "Same baseline and presentation scale; corrected Owner clean-source")
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
        raise SystemExit(f"missing corrected Owner clean-source: {SOURCE_PATH}")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    source = Image.open(SOURCE_PATH).convert("RGB")
    if source.size != (1254, 1254):
        raise SystemExit(f"unexpected corrected source size: {source.size}")
    background_mask = checkerboard_background_mask(source)
    forms = save_form_images(source, background_mask)
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
