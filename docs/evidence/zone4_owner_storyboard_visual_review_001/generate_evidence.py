from __future__ import annotations

import hashlib
import json
import math
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
FONT_PATH = Path(r"C:\Windows\Fonts\NotoSansTC-VF.ttf")
FONT_BOLD_PATH = Path(r"C:\Windows\Fonts\NotoSansTC-VF.ttf")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD_PATH if bold else FONT_PATH), size)


def load_image(relative: str) -> Image.Image:
    image = Image.open(ROOT / relative).convert("RGB")
    return image


def fit_image(image: Image.Image, size: tuple[int, int], fill=(18, 22, 31)) -> Image.Image:
    canvas = Image.new("RGB", size, fill)
    fitted = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
    x = (size[0] - fitted.width) // 2
    y = (size[1] - fitted.height) // 2
    canvas.paste(fitted, (x, y))
    return canvas


def wrap_by_pixels(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text).splitlines() or [""]:
        current = ""
        for char in paragraph:
            candidate = current + char
            if current and draw.textlength(candidate, font=face) > width:
                lines.append(current)
                current = char
            else:
                current = candidate
        lines.append(current)
    return lines or [""]


def draw_wrapped(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, face: ImageFont.FreeTypeFont,
                 fill, width: int, spacing: int = 3, max_lines: int | None = None) -> int:
    lines = wrap_by_pixels(draw, text, face, width)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines:
            lines[-1] = lines[-1].rstrip("。！？… ") + "…"
    draw.multiline_text(xy, "\n".join(lines), font=face, fill=fill, spacing=spacing)
    return len(lines) * (face.size + spacing)


def rounded(draw: ImageDraw.ImageDraw, box, radius: int, fill, outline=None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def badge(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, fill, text_fill=(255, 255, 255)) -> None:
    face = font(15, True)
    w = int(draw.textlength(label, font=face)) + 24
    rounded(draw, (x, y, x + w, y + 30), 14, fill)
    draw.text((x + 12, y + 5), label, font=face, fill=text_fill)


def load_story() -> list[dict]:
    manifest = json.loads((ROOT / "ZONE4_RUNTIME_MANIFEST.json").read_text(encoding="utf-8"))
    rows = []
    for beat in manifest["beats"]:
        if beat.get("track") != "main_story":
            continue
        dialogue = (beat.get("dialogue") or [{}])[0]
        voice = (dialogue.get("voice_by_locale") or {}).get("zh-TW") or {}
        rows.append({
            "beat_id": beat["beat_id"],
            "shot_id": beat["visual"]["asset_id"],
            "section": beat.get("section", ""),
            "phase": "PRE_LORD" if len(rows) < 16 else "POST_LORD",
            "image": beat["visual"]["path"],
            "voice": voice.get("path", "MISSING"),
            "duration_ms": voice.get("duration_ms"),
            "speaker": dialogue.get("speaker", "Unknown"),
            "copy": (dialogue.get("text") or {}).get("zh-TW", ""),
        })
    return rows


def make_storyboard() -> Path:
    rows = load_story()
    cols = 4
    tile_w, tile_h = 420, 350
    margin, gap = 32, 16
    header_h, section_h, divider_h = 124, 48, 92
    pre_rows = math.ceil(16 / cols)
    post_rows = math.ceil(6 / cols)
    width = margin * 2 + cols * tile_w + (cols - 1) * gap
    height = header_h + section_h + pre_rows * tile_h + divider_h + section_h + post_rows * tile_h + 36
    sheet = Image.new("RGB", (width, height), (20, 25, 35))
    draw = ImageDraw.Draw(sheet)
    draw.text((margin, 24), "GO ODYSSEY · ZONE 4 STORYBOARD CONTACT SHEET", font=font(28, True), fill=(248, 224, 167))
    draw.text((margin, 67), "22 canonical runtime shots · image / dialogue / zh-TW voice pairing · source-derived Owner review evidence", font=font(16), fill=(191, 205, 220))

    def section_bar(y: int, label: str, detail: str, color) -> None:
        rounded(draw, (margin, y, width - margin, y + section_h - 8), 12, color)
        draw.text((margin + 16, y + 8), label, font=font(21, True), fill=(255, 255, 255))
        draw.text((margin + 235, y + 11), detail, font=font(15), fill=(255, 247, 222))

    def tile(row: dict, index: int, x: int, y: int) -> None:
        rounded(draw, (x, y, x + tile_w, y + tile_h), 12, (35, 42, 55), outline=(91, 111, 137), width=2)
        picture = fit_image(load_image(row["image"]), (tile_w - 4, 218), (14, 18, 25))
        sheet.paste(picture, (x + 2, y + 2))
        draw.rectangle((x + 2, y + 2, x + 2 + 94, y + 34), fill=(12, 16, 24))
        draw.text((x + 12, y + 9), f"{index:02d}  {row['shot_id']}", font=font(15, True), fill=(255, 228, 153))
        meta_y = y + 229
        draw.text((x + 12, meta_y), f"{row['section']} · {row['speaker']}", font=font(15, True), fill=(171, 224, 255))
        draw_wrapped(draw, (x + 12, meta_y + 24), row["copy"], font(15), (245, 245, 245), tile_w - 24, max_lines=2)
        voice_name = row["voice"].split("/")[-1]
        draw_wrapped(draw, (x + 12, y + 303), f"VOICE_FILE {voice_name} · {row['duration_ms']} ms", font(12), (179, 190, 205), tile_w - 24, max_lines=2)

    y = header_h
    section_bar(y, "PRE_LORD", "Z4_S1_01 – Z4_S2_08 · first-entry story", (64, 94, 118))
    y += section_h
    for index, row in enumerate(rows[:16], 1):
        x = margin + ((index - 1) % cols) * (tile_w + gap)
        row_y = y + ((index - 1) // cols) * tile_h
        tile(row, index, x, row_y)
    y += pre_rows * tile_h
    rounded(draw, (margin, y + 16, width - margin, y + divider_h - 12), 18, (117, 46, 42), outline=(255, 191, 102), width=3)
    draw.text((margin + 24, y + 29), "=== LORD CHALLENGE CHECKPOINT ===", font=font(25, True), fill=(255, 236, 189))
    draw.text((margin + 24, y + 62), "Z4_S2_08 ends PRE_LORD; POST_LORD is unlocked only by authoritative Lord clear", font=font(15), fill=(255, 222, 213))
    y += divider_h
    section_bar(y, "POST_LORD", "Z4_S3_01 – Z4_S3_06 · authoritative clear continuation", (91, 87, 54))
    y += section_h
    for index, row in enumerate(rows[16:], 17):
        x = margin + ((index - 17) % cols) * (tile_w + gap)
        row_y = y + ((index - 17) // cols) * tile_h
        tile(row, index, x, row_y)
    path = OUT / "ZONE4_STORYBOARD_CONTACT_SHEET.png"
    sheet.save(path, format="PNG", optimize=True)
    return path


def make_lord_sheet() -> Path:
    package = json.loads((ROOT / "assets/e10/art/zone1/lord_trial/zone1-lord-trial-art-package.json").read_text(encoding="utf-8"))
    mappings = {
        "LORD_CHALLENGE_BACKPLATE": ("assets/e10/art/zone4/lord/Z4-LORD-01.png", "challenge card / entry"),
        "FIRST_STAR_SUCCESS_BACKPLATE": ("assets/e10/art/zone4/lord/Z4-LORD-04.png", "success background"),
        "FIRST_STAR_ICON": ("assets/e10/art/zone4/lord/Z4-LORD-05.png", "first-clear success portrait; no standalone star icon"),
        "LORD_RITUAL_KEY_ART": ("assets/e10/art/zone4/lord/Z4-LORD-02.png", "Lord ritual / domain"),
        "LORD_FAILURE_BACKPLATE": ("assets/e10/art/zone4/lord/Z4-LORD-03.png", "failure / retraining"),
        "VILLAGE_ELDER_REFERENCE": (None, "no direct Zone4 selection; reference-only"),
    }
    width, row_h, header_h = 1840, 248, 138
    height = header_h + row_h * len(package["assets"]) + 40
    sheet = Image.new("RGB", (width, height), (22, 25, 34))
    draw = ImageDraw.Draw(sheet)
    draw.text((34, 24), "GO ODYSSEY · LORD TRIAL VISUAL PACKAGE", font=font(28, True), fill=(248, 224, 167))
    draw.text((34, 68), "Historical 6/6 WebP package · current Zone4 selected presentation shown beside each role · no emoji fallback", font=font(16), fill=(191, 205, 220))
    draw.text((34, 101), "Historical package is Zone1-named; Zone4 uses its own current owner-final lord assets, never cinematic shots.", font=font(14), fill=(255, 190, 154))
    x_hist, x_z4, x_text = 400, 830, 1260
    for index, entry in enumerate(package["assets"], 1):
        y = header_h + (index - 1) * row_h
        draw.line((34, y, width - 34, y), fill=(67, 79, 98), width=1)
        key = entry["key"]
        runtime = entry["runtime_webp"]
        z4_path, z4_role = mappings[key]
        draw.text((34, y + 16), f"{index}. {key}", font=font(17, True), fill=(255, 228, 153))
        draw_wrapped(draw, (34, y + 48), runtime["path"].split("/")[-1], font(14), (223, 231, 240), 330, max_lines=3)
        draw_wrapped(draw, (34, y + 116), f"role: {key}", font(13), (161, 196, 222), 330, max_lines=3)
        hist = fit_image(load_image(runtime["path"]), (380, 190), (12, 15, 22))
        sheet.paste(hist, (x_hist, y + 12))
        draw.text((x_hist + 8, y + 207), "historical WebP", font=font(12), fill=(181, 192, 205))
        if z4_path:
            current = fit_image(load_image(z4_path), (380, 190), (12, 15, 22))
            sheet.paste(current, (x_z4, y + 12))
            draw.text((x_z4 + 8, y + 207), "current Zone4 selected asset", font=font(12), fill=(181, 192, 205))
        else:
            rounded(draw, (x_z4, y + 12, x_z4 + 380, y + 202), 8, (43, 48, 58), outline=(109, 121, 139), width=2)
            draw.text((x_z4 + 36, y + 91), "NO DIRECT ZONE4 SELECTION", font=font(16, True), fill=(198, 207, 218))
        draw_wrapped(draw, (x_text, y + 16), f"INTENDED MAPPING\nZone1 / Lord Trial package role\n\nACTUAL ZONE4 SELECTION\n{z4_path or 'NONE'}\n{z4_role}", font(15), (235, 239, 245), 520, spacing=5, max_lines=9)
        draw.text((x_text, y + 208), f"SHA256 {runtime['sha256']}", font=font(11), fill=(150, 164, 183))
    path = OUT / "LORD_TRIAL_CONTACT_SHEET.png"
    sheet.save(path, format="PNG", optimize=True)
    return path


def draw_mock_shell(width: int, height: int, mode: str, state: str, output: Path) -> None:
    map_path = ROOT / "assets/maps/e10-vs1f-landmarks/zone-04-twilight-forest.webp"
    lord_path = ROOT / "assets/e10/art/zone4/lord/Z4-LORD-01.png"
    shell = Image.new("RGB", (width, height), (30, 35, 48))
    draw = ImageDraw.Draw(shell)
    safari = mode == "Safari"
    top = 72 if safari else 44
    draw.rectangle((0, 0, width, top), fill=(18, 23, 33))
    if safari:
        draw.text((24, 20), "Safari browser · authenticated Adventure", font=font(18, True), fill=(238, 242, 248))
    else:
        draw.text((24, 12), "installed PWA · display-mode: standalone", font=font(18, True), fill=(238, 242, 248))
    if not safari:
        draw.rectangle((0, top, width, top + 20), fill=(62, 45, 35))
        draw.text((24, top + 2), "safe-area inset preserved · vertical flow enabled", font=font(12), fill=(246, 217, 171))
        top += 20
    draw.text((24, top + 18), "GO ODYSSEY", font=font(19, True), fill=(248, 224, 167))
    draw.text((width - 280, top + 20), "HUD  ·  Coins  ·  Level", font=font(14), fill=(201, 214, 228))
    map_y = top + 58
    map_h = 340 if safari else 305
    rounded(draw, (24, map_y, width - 24, map_y + map_h), 18, (17, 20, 26), outline=(111, 126, 149), width=2)
    map_img = fit_image(Image.open(map_path).convert("RGB"), (width - 28, map_h - 4), (17, 20, 26))
    shell.paste(map_img, (26, map_y + 2))
    draw.rectangle((42, map_y + 20, 310, map_y + 62), fill=(20, 24, 32,))
    draw.text((58, map_y + 29), "WORLD MAP · Zone 4", font=font(16, True), fill=(255, 238, 187))
    card_y = map_y + map_h + 22
    card_h = 388 if state == "replay" else 358
    rounded(draw, (24, card_y, width - 24, card_y + card_h), 18, (45, 42, 55), outline=(198, 155, 83), width=2)
    card_label = "FIRST-CLEAR / NORMAL ZONE4 CARD" if state == "normal" else "REPLAY-CAPABLE ZONE4 CARD"
    draw.text((48, card_y + 13), card_label, font=font(13, True), fill=(151, 203, 232))
    draw.text((48, card_y + 39), "迷霧森林 · Misty Forest", font=font(22, True), fill=(255, 231, 170))
    draw.text((48, card_y + 75), "CURRENT ZONE / CURRENT MISSION", font=font(13, True), fill=(151, 203, 232))
    status = "PRE_LORD CHECKPOINT · server state" if state == "normal" else "CLEARED · replay available · server state"
    draw.text((48, card_y + 101), status, font=font(15), fill=(239, 241, 244))
    rows = ["任務進度  Mission progress", "區域進度  Region progress", "領主進度  Lord progress"]
    for idx, label in enumerate(rows):
        yy = card_y + 136 + idx * 34
        draw.text((48, yy), label, font=font(14), fill=(205, 212, 224))
        draw.text((360, yy), "server payload", font=font(14), fill=(177, 191, 210))
    # A small actual Zone4 Lord asset keeps this evidence tied to the selected runtime package.
    portrait = fit_image(Image.open(lord_path).convert("RGB"), (112, 92), (24, 25, 34))
    shell.paste(portrait, (width - 160, card_y + 39))
    button_y = card_y + 240
    labels = ["繼續冒險", "挑戰領主" if state == "normal" else "再次挑戰領主"]
    if state == "replay":
        labels.insert(1, "重溫故事")
    labels.append("補星修行")
    bx = 48
    for label in labels:
        bw = 170 if label != "重溫故事" else 190
        fill = (148, 103, 50) if label == "重溫故事" else (63, 88, 115)
        rounded(draw, (bx, button_y, bx + bw, button_y + 46), 10, fill, outline=(235, 204, 135), width=1)
        draw.text((bx + 16, button_y + 11), label, font=font(16, True), fill=(255, 255, 255))
        bx += bw + 12
    note_y = button_y + 62
    note = "Replay Story is presentation-only · no progression/reward mutation" if state == "replay" else "Same shared E9 Zone Card renderer · normal Adventure actions"
    draw_wrapped(draw, (48, note_y), note, font(13), (190, 201, 216), width - 96, max_lines=2)
    dock_y = height - 78
    draw.rectangle((0, dock_y, width, height), fill=(18, 23, 33))
    draw.text((42, dock_y + 23), "Adventure", font=font(14, True), fill=(255, 225, 151))
    draw.text((width // 2 - 55, dock_y + 23), "SRS", font=font(14), fill=(190, 201, 216))
    draw.text((width - 145, dock_y + 23), "Backpack", font=font(14), fill=(190, 201, 216))
    draw.text((24, height - 24), "SIMULATED RESPONSIVE CAPTURE · REAL_OWNER_DEVICE_UAT=PENDING", font=font(12, True), fill=(255, 184, 149))
    shell.save(output, format="PNG", optimize=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    outputs = [
        make_storyboard(),
        make_lord_sheet(),
    ]
    first = OUT / "ZONE4_CARD_EVIDENCE_FIRST_CLEAR_MOCK.png"
    replay = OUT / "ZONE4_CARD_EVIDENCE_REPLAY_MOCK.png"
    safari = OUT / "SAFARI_RESPONSIVE_EVIDENCE_MOCK.png"
    pwa = OUT / "PWA_RESPONSIVE_EVIDENCE_MOCK.png"
    draw_mock_shell(834, 1194, "Safari", "normal", first)
    draw_mock_shell(834, 1194, "Safari", "replay", replay)
    draw_mock_shell(834, 1194, "Safari", "replay", safari)
    draw_mock_shell(834, 1194, "PWA", "replay", pwa)
    outputs.extend([first, replay, safari, pwa])
    manifest = {
        "package": "ZONE4_OWNER_STORYBOARD_VISUAL_REVIEW_PACKAGE_001",
        "source": "current accepted ZONE4_CINEMATIC_STORYBOARD_RUNTIME_RECOVERY_001 candidate",
        "real_owner_device_uat": "PENDING",
        "generated_outputs": [],
    }
    for path in outputs:
        with Image.open(path) as image:
            manifest["generated_outputs"].append({
                "file": path.name,
                "sha256": sha256(path),
                "width": image.width,
                "height": image.height,
            })
    (OUT / "EVIDENCE_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
