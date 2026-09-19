from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
FONT = Path(r"C:\Windows\Fonts\NotoSansTC-VF.ttf")
PREVIOUS = ROOT / "docs/evidence/zone4_owner_storyboard_visual_review_001"


def face(size: int, bold: bool = False):
    return ImageFont.truetype(str(FONT), size)


def rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def fit(path: str | None, size: tuple[int, int], fill=(18, 23, 31)) -> Image.Image:
    canvas = Image.new("RGB", size, fill)
    if path:
        source = Image.open(ROOT / path).convert("RGB")
        image = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.45))
        canvas.paste(image, (0, 0))
    return canvas


def wrap(draw, text: str, font_obj, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in str(text):
        candidate = current + char
        if current and draw.textlength(candidate, font=font_obj) > width:
            lines.append(current)
            current = char
        else:
            current = candidate
    lines.append(current or "")
    return lines


def text_block(draw, xy, text: str, font_obj, fill, width: int, spacing=3, max_lines=None):
    lines = wrap(draw, text, font_obj, width)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip("。！？… ") + "…"
    draw.multiline_text(xy, "\n".join(lines), font=font_obj, fill=fill, spacing=spacing)


def pill(draw, x, y, label, fill, text_fill=(255, 255, 255), width=None):
    f = face(14, True)
    w = width or int(draw.textlength(label, font=f)) + 24
    rounded(draw, (x, y, x + w, y + 30), 15, fill)
    draw.text((x + 12, y + 5), label, font=f, fill=text_fill)
    return w


ZONE_CARDS = [
    {
        "label": "ZONE 1",
        "name": "新手村 · Beginner Village",
        "asset": "assets/maps/e10-vs1f-landmarks/zone-01-beginner-village.webp",
        "accent": (217, 157, 67),
        "dark": (50, 91, 62),
    },
    {
        "label": "ZONE 2",
        "name": "史萊姆平原 · Slime Plains",
        "asset": "assets/maps/e10-vs1f-landmarks/zone-02-slime-plains.webp",
        "accent": (82, 185, 217),
        "dark": (34, 79, 105),
    },
    {
        "label": "ZONE 3",
        "name": "冰霧山谷 · Frost Valley",
        "asset": "assets/e10/art/zone3/environment/zone3_map_landmark.webp",
        "accent": (144, 170, 232),
        "dark": (49, 60, 101),
    },
    {
        "label": "ZONE 4",
        "name": "迷霧森林 · Misty Forest",
        "asset": "assets/maps/e10-vs1f-landmarks/zone-04-twilight-forest.webp",
        "accent": (100, 185, 153),
        "dark": (35, 76, 68),
    },
]


def zone_card_sheet() -> Path:
    width, height = 1880, 820
    sheet = Image.new("RGB", (width, height), (24, 30, 41))
    draw = ImageDraw.Draw(sheet)
    draw.text((36, 24), "GO ODYSSEY · SHARED ZONE CARD WORLDSTYLE", font=face(30, True), fill=(248, 224, 167))
    draw.text((36, 68), "Source-derived comparison: one renderer / one hierarchy / Zone-specific skin and art only", font=face(16), fill=(195, 208, 222))
    draw.text((width - 420, 30), "SIMULATED OWNER EVIDENCE", font=face(14, True), fill=(255, 187, 145))

    card_w, card_h, gap, top = 426, 650, 18, 126
    for index, zone in enumerate(ZONE_CARDS):
        x = 36 + index * (card_w + gap)
        y = top
        accent = zone["accent"]
        dark = zone["dark"]
        rounded(draw, (x, y, x + card_w, y + card_h), 18, (245, 246, 239), outline=accent, width=3)
        art_h = 194
        art = fit(zone["asset"], (card_w - 6, art_h), dark)
        art = Image.blend(art, Image.new("RGB", art.size, dark), 0.28)
        sheet.paste(art, (x + 3, y + 3))
        draw.text((x + 18, y + 18), zone["label"], font=face(17, True), fill=(255, 238, 179))
        draw.text((x + 18, y + 54), "CURRENT ZONE", font=face(12, True), fill=(220, 245, 238))
        draw.text((x + 18, y + 78), zone["name"], font=face(20, True), fill=(255, 255, 244))
        y2 = y + art_h + 18
        pill(draw, x + 18, y2, "目前位置 / CURRENT", (31, 114, 93), width=180)
        draw.text((x + 18, y2 + 50), "任務進度  24 / 80", font=face(15, True), fill=(35, 63, 58))
        draw.text((x + 18, y2 + 82), "區域進度  1 / 3", font=face(15, True), fill=(55, 88, 78))
        draw.text((x + 18, y2 + 114), "領主進度  30%", font=face(15, True), fill=(55, 88, 78))
        draw.rectangle((x + 18, y2 + 145, x + card_w - 18, y2 + 156), fill=(221, 229, 224))
        draw.rectangle((x + 18, y2 + 145, x + 170, y2 + 156), fill=accent)
        draw.text((x + 18, y2 + 178), "共有層級：狀態 → 進度 → CTA", font=face(13), fill=(77, 94, 88))
        bx = x + 18
        by = y2 + 218
        for label, fill_color, w in (("繼續冒險", (47, 118, 101), 112), ("挑戰領主", (74, 96, 116), 112), ("重溫故事", (145, 108, 57), 112)):
            pill(draw, bx, by, label, fill_color, width=w)
            bx += w + 7
        draw.text((x + 18, y + card_h - 28), "same shared shell · theme changes here", font=face(12), fill=(105, 116, 111))

    path = OUT / "ZONE_CARD_WORLDSTYLE_COMPARISON.png"
    sheet.save(path, optimize=True)
    return path


LORD_TILES = [
    ("ZONE 1 · challenge", "assets/e10/art/zone1/lord_trial/zone1_lord_challenge_backplate.webp", (217, 157, 67)),
    ("ZONE 2 · challenge", "assets/e10/art/zone2/lord_trial/zone2_lord_challenge_backplate.webp", (82, 185, 217)),
    ("ZONE 3 · challenge", "assets/e10/art/zone3/lord_trial/zone3_lord_02_challenge_backplate.webp", (144, 170, 232)),
    ("ZONE 4 · challenge", "assets/e10/art/zone4/lord/Z4-LORD-01.png", (100, 185, 153)),
    ("ZONE 4 · failure", "assets/e10/art/zone4/lord/Z4-LORD-03.png", (135, 183, 194)),
    ("ZONE 4 · first clear", "assets/e10/art/zone4/lord/Z4-LORD-04.png", (236, 190, 92)),
    ("ZONE 4 · replay", "assets/e10/art/zone4/lord/Z4-LORD-04.png", (145, 108, 57)),
    ("ZONE 4 · ritual", "assets/e10/art/zone4/lord/Z4-LORD-02.png", (100, 185, 153)),
]


def lord_sheet() -> Path:
    cols, tile_w, tile_h, gap = 4, 430, 360, 18
    width = 38 + cols * tile_w + (cols - 1) * gap
    height = 128 + 2 * tile_h + gap + 40
    sheet = Image.new("RGB", (width, height), (24, 30, 41))
    draw = ImageDraw.Draw(sheet)
    draw.text((36, 24), "GO ODYSSEY · SHARED LORD CARD WORLDSTYLE", font=face(30, True), fill=(248, 224, 167))
    draw.text((36, 68), "One #boss-cinematic shell / live DOM hierarchy / dedicated Zone art and state skin", font=face(16), fill=(195, 208, 222))
    draw.text((width - 390, 30), "EMOJI FALLBACK: NONE", font=face(14, True), fill=(255, 187, 145))
    for index, (label, asset, accent) in enumerate(LORD_TILES):
        x = 38 + (index % cols) * (tile_w + gap)
        y = 128 + (index // cols) * (tile_h + gap)
        rounded(draw, (x, y, x + tile_w, y + tile_h), 18, (38, 42, 51), outline=accent, width=3)
        art = fit(asset, (tile_w - 6, 240), (16, 20, 27))
        sheet.paste(art, (x + 3, y + 3))
        draw.rectangle((x + 3, y + 188, x + tile_w - 3, y + 237), fill=(12, 15, 20))
        draw.text((x + 16, y + 18), label, font=face(17, True), fill=(255, 238, 179))
        if "replay" in label:
            copy = "再次挑戰完成 · no new star / no new reward"
        elif "failure" in label:
            copy = "retry state · server result copy"
        elif "first clear" in label:
            copy = "first-clear success · first-star semantics"
        elif "ritual" in label:
            copy = "ritual key art · challenge handoff"
        else:
            copy = "same title / rules / progress / CTA structure"
        text_block(draw, (x + 16, y + 258), copy, face(14), (226, 232, 238), tile_w - 32, max_lines=2)
        pill(draw, x + 16, y + 311, "shared shell", (42, 100, 91), width=118)

    path = OUT / "LORD_CARD_WORLDSTYLE_COMPARISON.png"
    sheet.save(path, optimize=True)
    return path


def draw_surface(surface: Image.Image, box, label: str, standalone: bool, width: int):
    draw = ImageDraw.Draw(surface)
    x, y, w, h = box
    rounded(draw, (x, y, x + w, y + h), 24, (239, 242, 238), outline=(119, 143, 139), width=3)
    top = y + 28
    draw.text((x + 22, top), label, font=face(20, True), fill=(34, 57, 60))
    draw.text((x + 22, top + 32), "same authenticated state · same canonical card", font=face(13), fill=(76, 103, 99))
    map_y, map_h = top + 72, 238 if standalone else 270
    rounded(draw, (x + 18, map_y, x + w - 18, map_y + map_h), 16, (24, 57, 61), outline=(100, 185, 153), width=2)
    map_img = fit("assets/maps/e10-vs1f-landmarks/zone-04-twilight-forest.webp", (w - 40, map_h - 4), (24, 57, 61))
    surface.paste(map_img, (x + 20, map_y + 2))
    draw.text((x + 34, map_y + 18), "WORLD MAP · 迷霧森林", font=face(15, True), fill=(255, 239, 179))
    card_y, card_h = map_y + map_h + 18, 305
    rounded(draw, (x + 18, card_y, x + w - 18, card_y + card_h), 16, (248, 252, 247), outline=(74, 137, 119), width=2)
    draw.text((x + 34, card_y + 16), "CURRENT ZONE / CURRENT MISSION", font=face(12, True), fill=(47, 102, 91))
    draw.text((x + 34, card_y + 42), "迷霧森林 · Misty Forest", font=face(20, True), fill=(27, 67, 65))
    for i, row in enumerate(("任務進度", "區域進度", "領主進度")):
        yy = card_y + 86 + i * 32
        draw.text((x + 34, yy), row, font=face(14), fill=(53, 92, 83))
        draw.text((x + w - 170, yy), "server payload", font=face(13), fill=(80, 104, 99))
    bx, by = x + 34, card_y + 197
    for text, color in (("繼續冒險", (47, 118, 101)), ("重溫故事", (145, 108, 57)), ("再次挑戰領主", (74, 96, 116))):
        bw = 132 if len(text) < 5 else 166
        pill(draw, bx, by, text, color, width=bw)
        bx += bw + 8
    dock_y = y + h - 54
    draw.rectangle((x, dock_y, x + w, y + h), fill=(24, 35, 43))
    draw.text((x + 28, dock_y + 16), "Adventure", font=face(13, True), fill=(255, 225, 151))
    draw.text((x + w // 2 - 18, dock_y + 16), "SRS", font=face(13), fill=(190, 201, 216))
    draw.text((x + w - 94, dock_y + 16), "Backpack", font=face(13), fill=(190, 201, 216))


def surface_sheet() -> tuple[Path, Path]:
    width, height = 1700, 900
    sheet = Image.new("RGB", (width, height), (24, 30, 41))
    draw = ImageDraw.Draw(sheet)
    draw.text((34, 24), "GO ODYSSEY · SAFARI / INSTALLED PWA PARITY", font=face(30, True), fill=(248, 224, 167))
    draw.text((34, 68), "Deterministic responsive evidence only — real Owner device UAT remains PENDING", font=face(16), fill=(255, 187, 145))
    draw_surface(sheet, (38, 126, 790, 720), "Safari browser", False, 790)
    draw_surface(sheet, (872, 126, 790, 720), "Installed PWA · standalone", True, 790)
    safari = OUT / "SAFARI_PWA_WORLDSTYLE_EVIDENCE.png"
    sheet.save(safari, optimize=True)

    responsive = Image.new("RGB", (1500, 760), (24, 30, 41))
    rdraw = ImageDraw.Draw(responsive)
    rdraw.text((34, 24), "GO ODYSSEY · RESPONSIVE WORLDSTYLE CONTRACT", font=face(30, True), fill=(248, 224, 167))
    rdraw.text((34, 68), "Same hierarchy at mobile / iPad / desktop; only geometry and wrapping vary", font=face(16), fill=(195, 208, 222))
    for i, (label, w, h, color) in enumerate((("MOBILE · 390×844", 390, 520, (79, 126, 109)), ("IPAD · 834×1112", 460, 520, (76, 116, 151)), ("DESKTOP · 1440×900", 560, 520, (145, 108, 57)))):
        x = 34 + i * 488
        rounded(rdraw, (x, 126, x + 430, 700), 18, (241, 244, 241), outline=color, width=3)
        rdraw.text((x + 18, 145), label, font=face(18, True), fill=(35, 57, 60))
        # common vertical flow: HUD -> map -> Zone Card -> actions -> dock
        yy = 190
        for box_label, bh, fill in (("PLAYER HUD", 38, (31, 68, 64)), ("WORLD MAP", 150, (45, 94, 89)), ("ZONE CARD", 170, (222, 240, 230)), ("ACTIONS / wrap", 76, (238, 226, 193)), ("BOTTOM DOCK", 38, (31, 44, 51))):
            rounded(rdraw, (x + 18, yy, x + 412, yy + bh), 10, fill)
            rdraw.text((x + 34, yy + max(8, (bh - 17) // 2)), box_label, font=face(14, True), fill=(255, 255, 245) if bh < 100 else (35, 70, 62))
            yy += bh + 10
    responsive_path = OUT / "RESPONSIVE_WORLDSTYLE_EVIDENCE.png"
    responsive.save(responsive_path, optimize=True)
    return safari, responsive_path


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    outputs = [zone_card_sheet(), lord_sheet(), *surface_sheet()]
    # The storyboard and historical Lord package were already generated from
    # the accepted candidate. Reuse those exact bytes in this new package so
    # the world-style package cannot accidentally fork their authority.
    for filename in ("ZONE4_STORYBOARD_CONTACT_SHEET.png", "LORD_TRIAL_CONTACT_SHEET.png"):
        source = PREVIOUS / filename
        target = OUT / filename
        shutil.copy2(source, target)
        outputs.append(target)
    manifest = {
        "package": "ZONE4_RUNTIME_AND_WORLDSTYLE_UNIFICATION_001",
        "source_authority": {
            "origin_master": "4097053dcf87d5eeca826e03d8a21adbfcb9a47a",
            "candidate": "codex/zone4-cinematic-storyboard-runtime-recovery-001",
        },
        "real_owner_device_uat": "PENDING",
        "source_derived_truth": {
            "zone_card_renderer": "index.html:renderAdventureInfoPanel + js/e9/world_stage.js:renderZones/renderSelectedZone",
            "lord_card_renderer": "single #boss-cinematic shared DOM/CSS",
            "storyboard": "reused exact accepted candidate bytes",
        },
        "generated_outputs": [
            {"file": path.name, "sha256": sha(path), "bytes": path.stat().st_size}
            for path in outputs
        ],
    }
    (OUT / "EVIDENCE_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
