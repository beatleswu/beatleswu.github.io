from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "review" / "a020r1"
SOURCE_PATH = EVIDENCE / "A020R1_OWNER_REFERENCE_PRIMARY.jpg"
EXISTING = ROOT / "assets" / "pets"

CANVAS = (11, 25, 34)
PANEL = (18, 38, 48)
GOLD = (215, 158, 85)
CREAM = (247, 230, 199)
MUTED = (176, 191, 188)
TEAL = (73, 170, 165)

FONT_PATH = Path("C:/Windows/Fonts/NotoSansTC-VF.ttf")

# These are source-image rectangles, not regenerated or redrawn forms.
COLS = {
    "starpath": (18, 74, 448, 842),
    "fatty": (463, 74, 856, 842),
    "obsidian": (868, 74, 1265, 842),
}
ROWS = {
    "stage_i": (0, 78, 0, 340),
    "stage_ii": (0, 342, 0, 562),
    "stage_iii": (0, 564, 0, 840),
}

FOCUS = {
    "starpath": (184, 575, 448, 830),
    "fatty": (612, 575, 856, 805),
    "obsidian": (1008, 575, 1265, 830),
}


def font(size: int, bold: bool = False):
    del bold  # The variable font keeps bilingual labels available.
    return ImageFont.truetype(FONT_PATH, size)


def fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    image = image.copy().convert("RGBA")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    return image


def source_crop(source: Image.Image, spirit: str, stage: str) -> Image.Image:
    x1, y1, x2, y2 = COLS[spirit]
    _, row_y1, _, row_y2 = ROWS[stage]
    return source.crop((x1, row_y1, x2, row_y2)).convert("RGB")


def focused_crop(source: Image.Image, spirit: str) -> Image.Image:
    return source.crop(FOCUS[spirit]).convert("RGB")


def card(canvas: Image.Image, box: tuple[int, int, int, int], image: Image.Image, label: str):
    draw = ImageDraw.Draw(canvas)
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=18, fill=PANEL, outline=GOLD, width=2)
    draw.text((x1 + 18, y1 + 14), label, fill=CREAM, font=font(22))
    fitted = fit(image, (x2 - x1 - 28, y2 - y1 - 64))
    px = x1 + (x2 - x1 - fitted.width) // 2
    py = y1 + 52 + (y2 - y1 - 52 - fitted.height) // 2
    canvas.alpha_composite(fitted, (px, py))


def header(canvas: Image.Image, title: str, subtitle: str):
    draw = ImageDraw.Draw(canvas)
    draw.text((40, 24), title, fill=CREAM, font=font(36))
    draw.text((42, 70), subtitle, fill=MUTED, font=font(19))


def build_master_sheet(source: Image.Image):
    canvas = Image.new("RGBA", (1740, 1500), CANVAS + (255,))
    header(canvas, "A020-R1 — OWNER SELECTED THREE-STAGE MASTER SHEET", "Exact visual direction cropped from the Owner primary reference; design packet only")
    names = {
        "starpath": "#4 Starpath Antlerling · EXPLORATION",
        "fatty": "#5 阿肥 (Fatty) · PRECISION",
        "obsidian": "#6 Obsidian Bastion · SUPPORT",
    }
    spirits = ["starpath", "fatty", "obsidian"]
    stages = ["stage_i", "stage_ii", "stage_iii"]
    x_positions = [32, 590, 1148]
    y_positions = [118, 570, 1022]
    for col, spirit in enumerate(spirits):
        for row, stage in enumerate(stages):
            x = x_positions[col]
            y = y_positions[row]
            label = f"{names[spirit]} · {stage.replace('_', ' ').upper()}"
            card(canvas, (x, y, x + 528, y + 405), source_crop(source, spirit, stage), label)
    canvas.convert("RGB").save(EVIDENCE / "A020R1_THREE_STAGE_MASTER_SHEET.png", quality=95)


def build_evolution(source: Image.Image, spirit: str, filename: str, title: str, subtitle: str):
    canvas = Image.new("RGBA", (1840, 830), CANVAS + (255,))
    header(canvas, title, subtitle)
    stages = ["stage_i", "stage_ii", "stage_iii"]
    for index, stage in enumerate(stages):
        x = 34 + index * 604
        card(canvas, (x, 125, x + 570, 790), source_crop(source, spirit, stage), stage.replace("_", " ").upper())
    canvas.convert("RGB").save(EVIDENCE / filename, quality=95)


def build_final_trio(source: Image.Image):
    canvas = Image.new("RGBA", (1840, 760), CANVAS + (255,))
    header(canvas, "A020-R1 — STAGE III FINAL TRIO", "Owner reference final forms; no Stage IV escalation or reinterpretation")
    labels = [
        ("starpath", "#4 Starpath Antlerling"),
        ("fatty", "#5 阿肥 (Fatty)"),
        ("obsidian", "#6 Obsidian Bastion"),
    ]
    for index, (spirit, label) in enumerate(labels):
        x = 34 + index * 604
        card(canvas, (x, 125, x + 570, 730), source_crop(source, spirit, "stage_iii"), label)
    canvas.convert("RGB").save(EVIDENCE / "A020R1_STAGE_III_FINAL_TRIO.png", quality=95)


def load_existing(name: str) -> Image.Image:
    return Image.open(EXISTING / name).convert("RGBA")


def build_follower_scale(source: Image.Image):
    canvas = Image.new("RGBA", (2040, 820), CANVAS + (255,))
    header(canvas, "A020-R1 — SIX-SPIRIT FOLLOWER SCALE", "Three existing Spirits remain faithful; new final forms use the Owner reference; Hero remains primary")
    labels = [
        ("INK DROP", load_existing("pet_ink_drop_kelpie_lv1.webp")),
        ("VOID KIT", load_existing("pet_whispering_void_kit_lv1.webp")),
        ("HATCHLING", load_existing("pet_star_shell_hatchling_lv1.webp")),
        ("STARPATH", focused_crop(source, "starpath")),
        ("FATTY", focused_crop(source, "fatty")),
        ("OBSIDIAN", focused_crop(source, "obsidian")),
    ]
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((54, 300, 124, 370), fill=(232, 178, 73), outline=CREAM, width=3)
    draw.text((52, 385), "HERO", fill=GOLD, font=font(15))
    for index, (label, image) in enumerate(labels):
        x = 160 + index * 305
        draw.rounded_rectangle((x, 178, x + 260, 570), radius=16, fill=PANEL, outline=TEAL, width=2)
        fitted = fit(image, (220, 280))
        canvas.alpha_composite(fitted, (x + (260 - fitted.width) // 2, 218 + (280 - fitted.height) // 2))
        draw.ellipse((x + 112, 600, x + 148, 636), fill=TEAL, outline=CREAM, width=2)
        draw.text((x + 82, 650), label, fill=CREAM, font=font(16))
    canvas.convert("RGB").save(EVIDENCE / "A020R1_SIX_SPIRIT_FOLLOWER_SCALE.png", quality=95)


def main():
    if not SOURCE_PATH.is_file():
        raise SystemExit(f"missing Owner reference: {SOURCE_PATH}")
    source = Image.open(SOURCE_PATH).convert("RGB")
    build_master_sheet(source)
    build_evolution(source, "starpath", "A020R1_STARPATH_EVOLUTION_STRIP.png", "#4 STARPATH ANTLERLING — EVOLUTION", "EXPLORATION · newborn → growing juvenile → mature final form")
    build_evolution(source, "fatty", "A020R1_FATTY_EVOLUTION_STRIP.png", "#5 阿肥 (FATTY) — EVOLUTION", "PRECISION · newborn puppy → younger juvenile → adult Fatty")
    build_evolution(source, "obsidian", "A020R1_OBSIDIAN_EVOLUTION_STRIP.png", "#6 OBSIDIAN BASTION — EVOLUTION", "SUPPORT · awakened core → growing mech → final guardian form")
    build_final_trio(source)
    build_follower_scale(source)
    print("A020R1_REFERENCE_PACKET_BUILT=6")


if __name__ == "__main__":
    main()
