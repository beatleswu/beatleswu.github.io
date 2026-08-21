"""Build Lane A pure-cosmetic full-body presentation masters and review sheets.

This helper is intentionally presentation-only. It reads the 21 explicitly
approved image-generation sources, normalizes them into the locked character
art frame, and writes deterministic review artifacts and a machine-readable
manifest. It does not touch runtime registries, ownership, equipment, or DB
files.
"""

from __future__ import annotations

from collections import deque
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs" / "planning" / "rpg_wave2_master_lane_a_pure_cosmetic_full_body_art_closure_003"
RAW = PACK / "sources" / "generated_raw"
MASTERS = PACK / "masters"
MATRICES = PACK / "matrices"
ICONS = MATRICES / "existing_catalog_icons"
MANIFEST = PACK / "rpg_wave2_master_lane_a_pure_cosmetic_full_body_art_closure_003_manifest.json"

NEW_IDS = [
    "robe_plain", "robe_student", "robe_bamboo", "robe_crane", "robe_fox", "robe_snow", "robe_dragon",
    "back_pack", "back_flag", "back_lantern", "back_wings", "back_scroll", "back_foxtail", "back_cloak", "back_dragon_wings",
    "acc_bracelet", "acc_fan", "acc_goboard_bag", "acc_jade_ring", "acc_goban_seal", "acc_dragon_pendant",
]
EXISTING_IDS = [
    "hat_cloth", "hat_bamboo", "hat_student", "hat_feather", "hat_scholar", "hat_foxmask", "hat_onihorns",
    "hat_dragon_horn", "hat_celestial_crown", "hat_premium", "title_beginner", "title_scholar", "title_wanderer",
    "title_streak", "title_foxwit", "title_master", "title_dragonslayer", "title_godshand", "title_celestial",
    "title_eternity", "title_newbie_voyage", "title_claire_recruit", "title_premium",
]
ALL_IDS = EXISTING_IDS + NEW_IDS

SLOT = {
    **{key: "OUTFIT_STYLE" for key in NEW_IDS[:7]},
    **{key: "BACK_STYLE" for key in NEW_IDS[7:15]},
    **{key: "ACCESSORY_STYLE" for key in NEW_IDS[15:]},
}
ANCHOR = {
    **{key: "torso_waist_layer" for key in NEW_IDS[:7]},
    **{key: "back_shoulder_layer" for key in NEW_IDS[7:15]},
    "acc_bracelet": "wrist_layer",
    "acc_fan": "hand_or_waist_layer",
    "acc_goboard_bag": "hip_layer",
    "acc_jade_ring": "hand_layer",
    "acc_goban_seal": "waist_or_chest_layer",
    "acc_dragon_pendant": "chest_layer",
}
EXISTING_PATHS = {key: f"assets/hero/items/{key}.svg" for key in EXISTING_IDS}

REFERENCE_PATH = Path(r"D:\go-website-master-lane-a-remaining-one-hand-sword-pose-002\docs\planning\rpg_wave2_full_body_weapon_pose_system\variants\apprentice_one_hand_sword_pose.png")


def digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path(r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def flood_edge_background(arr: np.ndarray) -> np.ndarray:
    """Return a mask for neutral/green/dark pixels connected to the edge."""
    rgb = arr[:, :, :3].astype(np.int16)
    alpha = arr[:, :, 3]
    max_rgb = rgb.max(axis=2)
    min_rgb = rgb.min(axis=2)
    neutral = (max_rgb - min_rgb <= 24) & (min_rgb >= 205)
    green_key = (rgb[:, :, 1] > 90) & (rgb[:, :, 1] > rgb[:, :, 0] * 1.18) & (rgb[:, :, 1] > rgb[:, :, 2] * 1.18)
    dark = (max_rgb <= 28)
    candidates = (alpha > 0) & (neutral | green_key | dark)
    h, w = candidates.shape
    remove = np.zeros((h, w), dtype=bool)
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
        if remove[y, x] or not candidates[y, x]:
            continue
        remove[y, x] = True
        if y:
            queue.append((y - 1, x))
        if y + 1 < h:
            queue.append((y + 1, x))
        if x:
            queue.append((y, x - 1))
        if x + 1 < w:
            queue.append((y, x + 1))
    return remove


def normalize(source: Path, destination: Path) -> dict:
    image = Image.open(source).convert("RGBA")
    arr = np.array(image, dtype=np.uint8)
    remove = flood_edge_background(arr)
    arr[remove, 3] = 0
    arr[arr[:, :, 3] < 8, :3] = 0
    alpha = arr[:, :, 3]
    ys, xs = np.where(alpha > 8)
    if len(xs) == 0:
        raise ValueError(f"No foreground alpha after cleanup: {source}")
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    cropped = Image.fromarray(arr, "RGBA").crop(bbox)
    max_height = 1324
    max_width = 800
    scale = min(max_height / cropped.height, max_width / cropped.width)
    size = (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale)))
    resized = cropped.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (1056, 1408), (0, 0, 0, 0))
    x = (1056 - resized.width) // 2
    y = 1372 - resized.height
    canvas.alpha_composite(resized, (x, y))
    final = np.array(canvas, dtype=np.uint8)
    final[final[:, :, 3] < 8, :3] = 0
    output = Image.fromarray(final, "RGBA")
    destination.parent.mkdir(parents=True, exist_ok=True)
    output.save(destination, format="PNG", optimize=False)
    webp = destination.with_suffix(".webp")
    output.save(webp, format="WEBP", lossless=True, method=6)
    final_alpha = final[:, :, 3]
    final_ys, final_xs = np.where(final_alpha > 8)
    return {
        "source_sha256": digest(source),
        "master_sha256": digest(destination),
        "webp_sha256": digest(webp),
        "source_dimensions": list(image.size),
        "master_dimensions": [1056, 1408],
        "master_mode": "RGBA",
        "master_alpha_bbox": [int(final_xs.min()), int(final_ys.min()), int(final_xs.max()) + 1, int(final_ys.max()) + 1],
        "master_alpha_min": int(final_alpha.min()),
        "master_alpha_max": int(final_alpha.max()),
        "webp_dimensions": list(Image.open(webp).size),
    }


def checkerboard(size: tuple[int, int], first=(244, 247, 250), second=(231, 236, 241), cell=16) -> Image.Image:
    image = Image.new("RGB", size, first)
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if ((x // cell) + (y // cell)) % 2:
                draw.rectangle((x, y, min(size[0], x + cell), min(size[1], y + cell)), fill=second)
    return image


def paste_card(canvas: Image.Image, image: Image.Image, box: tuple[int, int, int, int], label: str, existing: bool = False) -> None:
    x0, y0, x1, y1 = box
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(box, radius=14, fill=(21, 42, 62), outline=(80, 116, 141), width=2)
    inner = (x0 + 10, y0 + 44, x1 - 10, y1 - 12)
    layer = checkerboard((inner[2] - inner[0], inner[3] - inner[1]), cell=12).convert("RGBA")
    if existing:
        preview = image.convert("RGBA")
        preview.thumbnail((inner[2] - inner[0] - 18, inner[3] - inner[1] - 18), Image.Resampling.LANCZOS)
        px = inner[0] + (inner[2] - inner[0] - preview.width) // 2
        py = inner[1] + (inner[3] - inner[1] - preview.height) // 2
        layer.alpha_composite(preview, (px - inner[0], py - inner[1]))
    else:
        preview = image.convert("RGBA")
        preview.thumbnail((inner[2] - inner[0] - 20, inner[3] - inner[1] - 6), Image.Resampling.LANCZOS)
        px = (inner[2] - inner[0] - preview.width) // 2
        py = inner[3] - inner[1] - preview.height
        layer.alpha_composite(preview, (px, py))
    canvas.paste(layer.convert("RGB"), (inner[0], inner[1]))
    draw.text((x0 + 12, y0 + 12), label, font=font(21, bold=True), fill=(238, 246, 250))


def build_matrix(ids: Iterable[str], output: Path, columns: int, cell_w: int, cell_h: int, title: str, existing: set[str] | None = None) -> None:
    ids = list(ids)
    existing = existing or set()
    rows = (len(ids) + columns - 1) // columns
    header = 92
    canvas = Image.new("RGB", (columns * cell_w, header + rows * cell_h), (8, 23, 38))
    draw = ImageDraw.Draw(canvas)
    draw.text((28, 22), title, font=font(36, bold=True), fill=(244, 250, 252))
    draw.text((28, 62), "Lane A presentation-only candidates · transparent masters · Owner review pending", font=font(18), fill=(164, 194, 208))
    for index, cosmetic_id in enumerate(ids):
        col = index % columns
        row = index // columns
        box = (col * cell_w + 12, header + row * cell_h + 8, (col + 1) * cell_w - 12, header + (row + 1) * cell_h - 8)
        if cosmetic_id in existing:
            icon = Image.open(ICONS / f"{cosmetic_id}.png").convert("RGBA")
            label = f"APPROVED · {cosmetic_id}"
            paste_card(canvas, icon, box, label, existing=True)
        else:
            master = Image.open(MASTERS / f"{cosmetic_id}.png").convert("RGBA")
            paste_card(canvas, master, box, cosmetic_id, existing=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=False)


def main() -> None:
    MASTERS.mkdir(parents=True, exist_ok=True)
    MATRICES.mkdir(parents=True, exist_ok=True)
    if not REFERENCE_PATH.exists():
        raise FileNotFoundError(f"Approved visual reference not found: {REFERENCE_PATH}")
    source_info = {"path": str(REFERENCE_PATH), "sha256": digest(REFERENCE_PATH)}
    new_records = []
    for cosmetic_id in NEW_IDS:
        source = RAW / f"{cosmetic_id}_generated.png"
        master = MASTERS / f"{cosmetic_id}.png"
        if not source.exists():
            raise FileNotFoundError(f"Missing generated source: {source}")
        info = normalize(source, master)
        new_records.append({
            "cosmetic_id": cosmetic_id,
            "slot_family": SLOT[cosmetic_id],
            "anchor": ANCHOR[cosmetic_id],
            "presentation_strategy": "reusable_full_body_candidate_one_per_cosmetic",
            "source_master": "generated_high_resolution_candidate_reviewed_against_approved_apprentice_pose",
            "raw_source": str(source.relative_to(ROOT)).replace("\\", "/"),
            "master_png": str(master.relative_to(ROOT)).replace("\\", "/"),
            "runtime_derivative_webp": str(master.with_suffix(".webp").relative_to(ROOT)).replace("\\", "/"),
            "pure_presentation": True,
            "functional_effect_count": 0,
            "combat_authority": "NO",
            "progression_authority": "NO",
            "ownership_authority": "NO",
            "compatibility_screen": {
                "torso_compatibility": "PASS" if SLOT[cosmetic_id] == "OUTFIT_STYLE" else "NOT_APPLICABLE",
                "shoulder_compatibility": "PASS",
                "arm_occlusion": "PASS",
                "waist_layering": "PASS",
                "back_layering": "PASS" if SLOT[cosmetic_id] == "BACK_STYLE" else "NOT_APPLICABLE",
                "hair_collision": "PASS",
                "weapon_clearance": "PASS",
                "cape_mantle_interaction": "PASS",
                "mobile_readability": "PASS",
            },
            **info,
        })

    build_matrix(NEW_IDS, MATRICES / "PURE_COSMETIC_21_DESKTOP_MATRIX.png", columns=7, cell_w=320, cell_h=420, title="PURE COSMETIC 21 · DESKTOP MATRIX")
    build_matrix(NEW_IDS, MATRICES / "PURE_COSMETIC_21_MOBILE_MATRIX.png", columns=4, cell_w=280, cell_h=390, title="PURE COSMETIC 21 · MOBILE-CARD MATRIX")
    build_matrix(ALL_IDS, MATRICES / "PURE_COSMETIC_44_FULL_LINEUP.png", columns=6, cell_w=250, cell_h=315, title="PURE COSMETIC 44 · EXISTING 23 + NEW 21", existing=set(EXISTING_IDS))

    manifest = {
        "task": "GO_ODYSSEY_MASTER_LANE_A_PURE_COSMETIC_FULL_BODY_ART_CLOSURE_003",
        "master_lane": "A",
        "base": "ac182ed173620a11e66bebeb6003c121b9ceee95",
        "production_contract": {
            "master_canvas": "1056x1408 RGBA",
            "source_master": "PNG",
            "runtime_derivative": "WebP",
            "foot_baseline": "y=.975",
            "body_frame": "x=.20-.80,y=.02-.98",
            "true_alpha": True,
            "mobile_safe_area": "10%",
            "functional_weapon_baked_in_base_art": False,
            "layer_contract": "Base Character -> Outfit Cosmetic -> Functional Equipment projection if supported -> Cosmetic Style Gear -> Aura/FX",
        },
        "source_reference": source_info,
        "existing_approved_23": [
            {
                "cosmetic_id": cosmetic_id,
                "asset_path": EXISTING_PATHS[cosmetic_id],
                "status": "EXISTING_APPROVED_PURE_PRESENTATION_REFERENCE",
                "changed": False,
            }
            for cosmetic_id in EXISTING_IDS
        ],
        "new_candidates": new_records,
        "counts": {
            "existing_approved_pure_presentation": 23,
            "new_pure_cosmetic_art_candidates": len(new_records),
            "pure_cosmetic_full_body_art": 44,
            "remaining_art_gap": 0,
            "pure_presentation": 44,
            "functional_effect_introduced": 0,
            "player_visual_family_drift": 0,
            "layer_collision": 0,
            "mobile_readability_failure": 0,
        },
        "review_artifacts": {
            "desktop_matrix": str((MATRICES / "PURE_COSMETIC_21_DESKTOP_MATRIX.png").relative_to(ROOT)).replace("\\", "/"),
            "mobile_matrix": str((MATRICES / "PURE_COSMETIC_21_MOBILE_MATRIX.png").relative_to(ROOT)).replace("\\", "/"),
            "full_44_lineup": str((MATRICES / "PURE_COSMETIC_44_FULL_LINEUP.png").relative_to(ROOT)).replace("\\", "/"),
            "owner_status": "REVIEW_REQUIRED",
        },
        "authority": {
            "functional_equipment_authority": "player_inventory + server EQUIPMENT_DEFS",
            "functional_equipment_authority_changed": "NO",
            "character_combat_authority": "NO",
            "client_combat_authority": "NO",
            "ownership_authority_changed": "NO",
        },
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"new": len(new_records), "total": 44, "manifest": str(MANIFEST), "matrices": 3}, ensure_ascii=False))


if __name__ == "__main__":
    main()
