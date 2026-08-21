"""Build the Lane A remaining one-hand sword pose review pack.

This is an art-only deterministic normalizer/compositor.  It does not register
poses, change runtime authority, or create functional equipment state.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont


REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = (
    REPO_ROOT
    / "docs"
    / "planning"
    / "rpg_wave2_master_lane_a_remaining_one_hand_sword_pose_002"
)
SOURCE_ROOT = PACK_ROOT / "sources" / "generated_raw"
MASTER_ROOT = PACK_ROOT / "masters"
MATRIX_ROOT = PACK_ROOT / "matrices"
FRAME = (1056, 1408)
CONTENT_TOP = 49
CONTENT_BOTTOM = 1373
CONTENT_HEIGHT = CONTENT_BOTTOM - CONTENT_TOP

REMAINING_IDS = [
    "apprentice_girl",
    "swordsman",
    "rogue",
    "ranger",
    "berserker",
    "guardian",
    "sage",
    "river_wayfinder",
    "stone_caretaker",
    "duelist_scout",
    "bastion_warden",
    "forest_pathfinder",
    "archive_scholar",
    "worldkeeper",
]

APPROVED_SIX = [
    (
        "apprentice",
        REPO_ROOT
        / "docs/planning/rpg_wave2_full_body_weapon_pose_system/variants/apprentice_one_hand_sword_pose.png",
    ),
    (
        "mage",
        REPO_ROOT
        / "docs/planning/rpg_wave2_full_body_weapon_pose_system/variants/mage_one_hand_sword_pose.png",
    ),
    (
        "paladin",
        REPO_ROOT
        / "docs/planning/rpg_wave2_full_body_weapon_pose_system/variants/paladin_one_hand_sword_pose.png",
    ),
    (
        "trail_apprentice",
        REPO_ROOT
        / "docs/planning/rpg_wave2_full_body_weapon_pose_batch2/variants/trail_apprentice_one_hand_sword_pose.png",
    ),
    (
        "night_runner",
        REPO_ROOT
        / "docs/planning/rpg_wave2_full_body_weapon_pose_batch2/variants/night_runner_one_hand_sword_pose.png",
    ),
    (
        "constellation_apprentice",
        REPO_ROOT
        / "docs/planning/rpg_wave2_full_body_weapon_pose_batch2/variants/constellation_apprentice_one_hand_sword_pose.png",
    ),
]

IDENTITY_SOURCES = {
    "apprentice_girl": {
        "branch": "codex/rpg-wave2-default-pose-batch2-001",
        "head": "69d3d27d48faab78c6e185b0dc35edfd239774df",
        "path": "assets/hero/characters/wave2_batch2_default_pose_v1/apprentice_girl_default_pose_v1.png",
    },
    "swordsman": {
        "branch": "codex/rpg-wave2-default-pose-batch2-001",
        "head": "69d3d27d48faab78c6e185b0dc35edfd239774df",
        "path": "assets/hero/characters/wave2_batch2_default_pose_v1/swordsman_default_pose_v1.png",
    },
    "rogue": {
        "branch": "codex/rpg-wave2-default-pose-batch2-001",
        "head": "69d3d27d48faab78c6e185b0dc35edfd239774df",
        "path": "assets/hero/characters/wave2_batch2_default_pose_v1/rogue_default_pose_v1.png",
    },
    "ranger": {
        "branch": "codex/rpg-wave2-default-pose-batch2-001",
        "head": "69d3d27d48faab78c6e185b0dc35edfd239774df",
        "path": "assets/hero/characters/wave2_batch2_default_pose_v1/ranger_default_pose_v1.png",
    },
    "berserker": {
        "branch": "codex/rpg-wave2-default-pose-batch3a-002",
        "head": "e1d9d50cb7e9e05ddb4fbfc1eb087b5aa92a94e6",
        "path": "assets/hero/characters/wave2_batch3a_default_pose_v2/berserker_default_pose_v2.png",
    },
    "guardian": {
        "branch": "codex/rpg-wave2-default-pose-batch3a-002",
        "head": "e1d9d50cb7e9e05ddb4fbfc1eb087b5aa92a94e6",
        "path": "assets/hero/characters/wave2_batch3a_default_pose_v2/guardian_default_pose_v2.png",
    },
    "sage": {
        "branch": "codex/rpg-wave2-default-pose-batch3a-002",
        "head": "e1d9d50cb7e9e05ddb4fbfc1eb087b5aa92a94e6",
        "path": "assets/hero/characters/wave2_batch3a_default_pose_v2/sage_default_pose_v2.png",
    },
    "river_wayfinder": {
        "branch": "codex/master-lane-a-final7-default-pose-001",
        "head": "546fce85e27f1a6dbbdbf983e6374950f8df44a6",
        "path": "assets/hero/characters/wave2_final7_default_pose_v1/river_wayfinder_default_pose_v1.png",
    },
    "stone_caretaker": {
        "branch": "codex/master-lane-a-final7-default-pose-001",
        "head": "546fce85e27f1a6dbbdbf983e6374950f8df44a6",
        "path": "assets/hero/characters/wave2_final7_default_pose_v1/stone_caretaker_default_pose_v1.png",
    },
    "duelist_scout": {
        "branch": "codex/master-lane-a-final7-default-pose-001",
        "head": "546fce85e27f1a6dbbdbf983e6374950f8df44a6",
        "path": "assets/hero/characters/wave2_final7_default_pose_v1/duelist_scout_default_pose_v1.png",
    },
    "bastion_warden": {
        "branch": "codex/master-lane-a-final7-default-pose-001",
        "head": "546fce85e27f1a6dbbdbf983e6374950f8df44a6",
        "path": "assets/hero/characters/wave2_final7_default_pose_v1/bastion_warden_default_pose_v1.png",
    },
    "forest_pathfinder": {
        "branch": "codex/master-lane-a-final7-default-pose-001",
        "head": "546fce85e27f1a6dbbdbf983e6374950f8df44a6",
        "path": "assets/hero/characters/wave2_final7_default_pose_v1/forest_pathfinder_default_pose_v1.png",
    },
    "archive_scholar": {
        "branch": "codex/master-lane-a-final7-default-pose-001",
        "head": "546fce85e27f1a6dbbdbf983e6374950f8df44a6",
        "path": "assets/hero/characters/wave2_final7_default_pose_v1/archive_scholar_default_pose_v1.png",
    },
    "worldkeeper": {
        "branch": "codex/master-lane-a-final7-default-pose-001",
        "head": "546fce85e27f1a6dbbdbf983e6374950f8df44a6",
        "path": "assets/hero/characters/wave2_final7_default_pose_v1/worldkeeper_default_pose_v1.png",
    },
}


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    ):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _edge_connected_background(rgb: np.ndarray) -> np.ndarray:
    """Return the checkerboard-like background connected to the canvas edge."""

    low = rgb.min(axis=2)
    high = rgb.max(axis=2)
    candidate = (low >= 235) & ((high - low) <= 18)
    height, width = candidate.shape
    reachable = np.zeros_like(candidate, dtype=bool)
    queue: deque[int] = deque()
    for x in range(width):
        for y in (0, height - 1):
            if candidate[y, x] and not reachable[y, x]:
                reachable[y, x] = True
                queue.append(y * width + x)
    for y in range(height):
        for x in (0, width - 1):
            if candidate[y, x] and not reachable[y, x]:
                reachable[y, x] = True
                queue.append(y * width + x)
    while queue:
        index = queue.popleft()
        y, x = divmod(index, width)
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < height and 0 <= nx < width:
                if candidate[ny, nx] and not reachable[ny, nx]:
                    reachable[ny, nx] = True
                    queue.append(ny * width + nx)
    return reachable


def _normalize_source(source: Path, target: Path) -> dict[str, object]:
    source_image = Image.open(source).convert("RGB")
    rgb = np.asarray(source_image, dtype=np.uint8)
    background = _edge_connected_background(rgb)
    alpha = np.where(background, 0, 255).astype(np.uint8)
    rgba = Image.fromarray(np.dstack((rgb, alpha)), mode="RGBA")
    bbox = rgba.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError(f"No foreground detected in {source}")
    content = rgba.crop(bbox)
    scale = CONTENT_HEIGHT / content.height
    width = max(1, round(content.width * scale))
    content = content.resize((width, CONTENT_HEIGHT), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", FRAME, (0, 0, 0, 0))
    x = (FRAME[0] - width) // 2
    canvas.alpha_composite(content, (x, CONTENT_TOP))
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, format="PNG", optimize=True)
    return {
        "source_sha256": _sha256(source),
        "source_dimensions": list(source_image.size),
        "source_mode": source_image.mode,
        "foreground_bbox_before_normalization": list(bbox),
        "master_dimensions": list(canvas.size),
        "master_mode": canvas.mode,
        "master_alpha_extrema": list(canvas.getchannel("A").getextrema()),
        "master_sha256": _sha256(target),
    }


def _fit(image: Image.Image, max_size: tuple[int, int]) -> Image.Image:
    image = image.convert("RGBA")
    scale = min(max_size[0] / image.width, max_size[1] / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def _caption(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, font: ImageFont.ImageFont) -> None:
    x0, y0, x1, y1 = box
    draw.rectangle((x0, y1 - 34, x1, y1), fill=(24, 31, 43, 235))
    draw.text((x0 + 8, y1 - 28), label, fill=(245, 247, 250, 255), font=font)


def _matrix(
    items: Iterable[tuple[str, Path]],
    destination: Path,
    columns: int,
    cell_size: tuple[int, int],
    title: str,
    max_character_size: tuple[int, int],
) -> None:
    items = list(items)
    margin = 24
    title_height = 66
    rows = (len(items) + columns - 1) // columns
    width = margin * 2 + columns * cell_size[0]
    height = margin * 2 + title_height + rows * cell_size[1]
    sheet = Image.new("RGBA", (width, height), (238, 242, 247, 255))
    draw = ImageDraw.Draw(sheet)
    draw.text((margin, margin), title, fill=(25, 38, 57, 255), font=_font(28))
    label_font = _font(17 if cell_size[0] >= 280 else 14)
    for index, (label, path) in enumerate(items):
        row, column = divmod(index, columns)
        x = margin + column * cell_size[0]
        y = margin + title_height + row * cell_size[1]
        draw.rounded_rectangle((x + 4, y + 4, x + cell_size[0] - 4, y + cell_size[1] - 4), radius=12, fill=(255, 255, 255, 235), outline=(204, 214, 226, 255), width=2)
        character = _fit(Image.open(path), max_character_size)
        cx = x + (cell_size[0] - character.width) // 2
        cy = y + 8 + (cell_size[1] - 52 - character.height) // 2
        sheet.alpha_composite(character, (cx, cy))
        _caption(draw, (x + 4, y + 4, x + cell_size[0] - 4, y + cell_size[1] - 4), label, label_font)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(destination, format="PNG", optimize=True)


def main() -> None:
    MASTER_ROOT.mkdir(parents=True, exist_ok=True)
    MATRIX_ROOT.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    master_paths: dict[str, Path] = {}
    for character_id in REMAINING_IDS:
        source = SOURCE_ROOT / f"{character_id}_one_hand_sword_pose_generated.png"
        master = MASTER_ROOT / f"{character_id}_one_hand_sword_pose_v1.png"
        if not source.exists():
            raise FileNotFoundError(source)
        metadata = _normalize_source(source, master)
        webp = master.with_suffix(".webp")
        Image.open(master).save(webp, format="WEBP", lossless=True, quality=100, method=6)
        record = {
            "character_id": character_id,
            "pose_family": "ONE_HAND_SWORD_POSE",
            "method": "FULL_BODY_REDRAW",
            "source": str(source.relative_to(REPO_ROOT)).replace("\\", "/"),
            "master_png": str(master.relative_to(REPO_ROOT)).replace("\\", "/"),
            "runtime_derivative_webp": str(webp.relative_to(REPO_ROOT)).replace("\\", "/"),
            "identity_source": IDENTITY_SOURCES[character_id],
            "presentation_only": True,
            "functional_weapon_baked_in": False,
            "local_hand_patch_used": False,
            "local_forearm_patch_used": False,
            **metadata,
        }
        records.append(record)
        master_paths[character_id] = master

    remaining_items = [(character_id, master_paths[character_id]) for character_id in REMAINING_IDS]
    all_items = APPROVED_SIX + remaining_items
    _matrix(
        remaining_items,
        MATRIX_ROOT / "REMAINING14_ONE_HAND_SWORD_POSE_MATRIX.png",
        columns=4,
        cell_size=(320, 450),
        title="Go Odyssey Lane A — Remaining 14 ONE_HAND_SWORD_POSE candidates",
        max_character_size=(294, 382),
    )
    _matrix(
        remaining_items,
        MATRIX_ROOT / "REMAINING14_ONE_HAND_SWORD_POSE_MOBILE_MATRIX.png",
        columns=2,
        cell_size=(260, 360),
        title="Mobile-card scale — Remaining 14 Sword Pose candidates",
        max_character_size=(226, 295),
    )
    _matrix(
        all_items,
        MATRIX_ROOT / "ALL20_ONE_HAND_SWORD_POSE_SCALE_LINEUP.png",
        columns=5,
        cell_size=(240, 388),
        title="Full roster scale lineup — 6 approved + 14 candidates",
        max_character_size=(214, 320),
    )

    manifest = {
        "task": "GO_ODYSSEY_MASTER_LANE_A_REMAINING_ONE_HAND_SWORD_POSE_002",
        "production_base": "c36ce33763c80de7313922ad4096331ded540c18",
        "production_base_branch": "codex/rpg-wave2-one-hand-sword-pose-batch2-001",
        "dependency_head_final7": "546fce85e27f1a6dbbdbf983e6374950f8df44a6",
        "dependency_head_armor": "1be5d9523ffd9cc874081d343efc0e4bfa69fa1d",
        "pose_family": "ONE_HAND_SWORD_POSE",
        "method": "FULL_BODY_REDRAW",
        "new_candidate_count": len(records),
        "owner_pass_count_before_review": 6,
        "owner_pass_denominator": 20,
        "owner_status": "PRODUCTION_CANDIDATE_OWNER_REVIEW_REQUIRED",
        "player_visual_family_drift_count_self_qa": 0,
        "armor_architecture_regression_count_self_qa": 0,
        "functional_equipment_authority": "player_inventory + server EQUIPMENT_DEFS",
        "character_combat_authority": "NO",
        "client_combat_authority": "NO",
        "local_hand_patch_used": False,
        "local_forearm_patch_used": False,
        "runtime_implementation": False,
        "records": records,
        "review_artifacts": {
            "desktop_matrix": str((MATRIX_ROOT / "REMAINING14_ONE_HAND_SWORD_POSE_MATRIX.png").relative_to(REPO_ROOT)).replace("\\", "/"),
            "mobile_matrix": str((MATRIX_ROOT / "REMAINING14_ONE_HAND_SWORD_POSE_MOBILE_MATRIX.png").relative_to(REPO_ROOT)).replace("\\", "/"),
            "all20_scale_lineup": str((MATRIX_ROOT / "ALL20_ONE_HAND_SWORD_POSE_SCALE_LINEUP.png").relative_to(REPO_ROOT)).replace("\\", "/"),
        },
    }
    (PACK_ROOT / "remaining14_one_hand_sword_pose_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
