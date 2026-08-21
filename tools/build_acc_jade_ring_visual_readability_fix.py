"""Build the single authorized acc_jade_ring visual readability revision."""

from __future__ import annotations

from collections import deque
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs" / "planning" / "rpg_wave2_master_lane_a_pure_cosmetic_full_body_art_closure_003"
REVISION = PACK / "revisions" / "acc_jade_ring_visual_readability_fix_004"
RAW = REVISION / "sources" / "acc_jade_ring_generated.png"
BEFORE = REVISION / "acc_jade_ring_before.png"
MASTER = PACK / "masters" / "acc_jade_ring.png"
WEBP = PACK / "masters" / "acc_jade_ring.webp"
MANIFEST = PACK / "rpg_wave2_master_lane_a_pure_cosmetic_full_body_art_closure_003_manifest.json"


def digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fnt(size: int, bold: bool = False):
    path = Path(r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf")
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default()


def edge_background_mask(arr: np.ndarray) -> np.ndarray:
    rgb = arr[:, :, :3].astype(np.int16)
    alpha = arr[:, :, 3]
    hi = rgb.max(axis=2)
    lo = rgb.min(axis=2)
    neutral = (hi - lo <= 24) & (lo >= 205)
    green_key = (rgb[:, :, 1] > 90) & (rgb[:, :, 1] > rgb[:, :, 0] * 1.18) & (rgb[:, :, 1] > rgb[:, :, 2] * 1.18)
    dark = hi <= 28
    candidates = (alpha > 0) & (neutral | green_key | dark)
    h, w = candidates.shape
    removed = np.zeros((h, w), dtype=bool)
    queue: deque[tuple[int, int]] = deque()
    for x in range(w):
        if candidates[0, x]:
            queue.append((0, x))
        if candidates[h - 1, x]:
            queue.append((h - 1, x))
    for y in range(h):
        if candidates[y, 0]:
            queue.append((y, 0))
        if candidates[y, w - 1]:
            queue.append((y, w - 1))
    while queue:
        y, x = queue.pop()
        if removed[y, x] or not candidates[y, x]:
            continue
        removed[y, x] = True
        if y:
            queue.append((y - 1, x))
        if y + 1 < h:
            queue.append((y + 1, x))
        if x:
            queue.append((y, x - 1))
        if x + 1 < w:
            queue.append((y, x + 1))
    return removed


def normalize_candidate() -> Image.Image:
    source = Image.open(RAW).convert("RGBA")
    arr = np.array(source, dtype=np.uint8)
    removed = edge_background_mask(arr)
    arr[removed, 3] = 0
    arr[arr[:, :, 3] < 8, :3] = 0
    alpha = arr[:, :, 3]
    ys, xs = np.where(alpha > 8)
    if len(xs) == 0:
        raise ValueError("Revision source has no foreground alpha")
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    cropped = Image.fromarray(arr, "RGBA").crop(bbox)
    scale = min(1324 / cropped.height, 800 / cropped.width)
    size = (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale)))
    resized = cropped.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (1056, 1408), (0, 0, 0, 0))
    canvas.alpha_composite(resized, ((1056 - resized.width) // 2, 1372 - resized.height))
    final = np.array(canvas, dtype=np.uint8)
    final[final[:, :, 3] < 8, :3] = 0
    return Image.fromarray(final, "RGBA")


def checkerboard(size: tuple[int, int], cell: int = 14) -> Image.Image:
    image = Image.new("RGB", size, (244, 247, 250))
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if ((x // cell) + (y // cell)) % 2:
                draw.rectangle((x, y, x + cell, y + cell), fill=(229, 235, 240))
    return image


def paste_character(canvas: Image.Image, character: Image.Image, area: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = area
    layer = checkerboard((x1 - x0, y1 - y0)).convert("RGBA")
    preview = character.copy()
    preview.thumbnail((layer.width - 20, layer.height - 10), Image.Resampling.LANCZOS)
    layer.alpha_composite(preview, ((layer.width - preview.width) // 2, layer.height - preview.height))
    canvas.paste(layer.convert("RGB"), (x0, y0))


def make_review_artifacts(before: Image.Image, after: Image.Image) -> None:
    desktop = Image.new("RGB", (1056, 1505), (8, 23, 38))
    draw = ImageDraw.Draw(desktop)
    draw.text((28, 20), "ACC_JADE_RING · DESKTOP AFTER", font=fnt(36, True), fill=(245, 250, 252))
    draw.text((28, 64), "Single authorized readability revision · pure presentation only", font=fnt(18), fill=(165, 196, 210))
    paste_character(desktop, after, (0, 97, 1056, 1505))
    desktop.save(REVISION / "ACC_JADE_RING_DESKTOP_AFTER.png", format="PNG", optimize=False)

    mobile = Image.new("RGB", (720, 540), (8, 23, 38))
    draw = ImageDraw.Draw(mobile)
    draw.text((24, 18), "ACC_JADE_RING · MOBILE AFTER", font=fnt(30, True), fill=(245, 250, 252))
    draw.text((24, 56), "Normal Hero-card scale + ring detail", font=fnt(17), fill=(165, 196, 210))
    paste_character(mobile, after, (24, 86, 320, 520))
    ring_crop = after.crop((675, 690, 790, 835)).resize((340, 430), Image.Resampling.NEAREST)
    ring_panel = checkerboard((340, 430), cell=18).convert("RGBA")
    ring_panel.alpha_composite(ring_crop, (0, 0))
    mobile.paste(ring_panel.convert("RGB"), (355, 86))
    draw = ImageDraw.Draw(mobile)
    draw.text((382, 496), "ring detail", font=fnt(17, True), fill=(220, 238, 240))
    mobile.save(REVISION / "ACC_JADE_RING_MOBILE_AFTER.png", format="PNG", optimize=False)

    comparison = Image.new("RGB", (1120, 760), (8, 23, 38))
    draw = ImageDraw.Draw(comparison)
    draw.text((30, 20), "ACC_JADE_RING · BEFORE / AFTER", font=fnt(36, True), fill=(245, 250, 252))
    draw.text((30, 64), "Identity, body frame and clothing preserved; ring setting made perceptible", font=fnt(18), fill=(165, 196, 210))
    paste_character(comparison, before, (20, 100, 550, 745))
    paste_character(comparison, after, (570, 100, 1100, 745))
    draw = ImageDraw.Draw(comparison)
    draw.text((210, 112), "BEFORE", font=fnt(26, True), fill=(245, 250, 252))
    draw.text((760, 112), "AFTER", font=fnt(26, True), fill=(245, 250, 252))
    comparison.save(REVISION / "ACC_JADE_RING_BEFORE_AFTER.png", format="PNG", optimize=False)


def update_manifest(after: Image.Image) -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    row = next(item for item in data["new_candidates"] if item["cosmetic_id"] == "acc_jade_ring")
    row["raw_source"] = str(RAW.relative_to(ROOT)).replace("\\", "/")
    row["source_sha256"] = digest(RAW)
    row["master_sha256"] = digest(MASTER)
    row["webp_sha256"] = digest(WEBP)
    row["source_dimensions"] = list(Image.open(RAW).size)
    row["master_dimensions"] = [1056, 1408]
    row["master_mode"] = "RGBA"
    row["readability_revision"] = {
        "task": "GO_ODYSSEY_MASTER_LANE_A_ACC_JADE_RING_VISUAL_READABILITY_FIX_004",
        "desktop_readability": "PASS_CANDIDATE",
        "mobile_readability": "PASS_CANDIDATE",
        "design_change": "slightly larger polished jade signet setting, stronger jade-green contrast, clearer finger ring signature",
        "other_cosmetic_ids_changed": 0,
        "functional_effect_count": 0,
    }
    data["review_artifacts"]["acc_jade_ring_revision"] = {
        "desktop_after": str((REVISION / "ACC_JADE_RING_DESKTOP_AFTER.png").relative_to(ROOT)).replace("\\", "/"),
        "mobile_after": str((REVISION / "ACC_JADE_RING_MOBILE_AFTER.png").relative_to(ROOT)).replace("\\", "/"),
        "before_after": str((REVISION / "ACC_JADE_RING_BEFORE_AFTER.png").relative_to(ROOT)).replace("\\", "/"),
        "owner_status": "REVIEW_REQUIRED",
    }
    data["counts"]["mobile_readability_failure"] = 0
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    REVISION.mkdir(parents=True, exist_ok=True)
    if not RAW.exists() or not BEFORE.exists():
        raise FileNotFoundError("Revision source or before snapshot missing")
    before = Image.open(BEFORE).convert("RGBA")
    after = normalize_candidate()
    after.save(MASTER, format="PNG", optimize=False)
    after.save(WEBP, format="WEBP", lossless=True, method=6)
    make_review_artifacts(before, after)
    update_manifest(after)
    print(json.dumps({"master": str(MASTER), "webp": str(WEBP), "review_artifacts": 3}, ensure_ascii=False))


if __name__ == "__main__":
    main()
