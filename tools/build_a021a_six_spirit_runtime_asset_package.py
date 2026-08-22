"""Build the A021A six-Spirit presentation asset package.

This is a deterministic packaging/normalization step.  It deliberately reads
the Owner-approved A020-R2 clean forms and never generates or redraws a
character.  Runtime files are kept in the established ``assets/pets``
directory; review sheets remain under ``docs/review`` and are never runtime
dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "docs" / "review" / "a020r2" / "clean_forms"
RUNTIME_DIR = ROOT / "assets" / "pets"
MANIFEST_PATH = ROOT / "docs" / "planning" / "e10_six_spirit_canonical_runtime_asset_manifest_a021a.json"
REVIEW_DIR = ROOT / "docs" / "review" / "a021a"
NINE_FORM_REVIEW = REVIEW_DIR / "A021A_NINE_FORM_VISUAL_QA.png"
FOLLOWER_REVIEW = REVIEW_DIR / "A021A_SIX_SPIRIT_FOLLOWER_SCALE_QA.png"

CANVAS_SIZE = (512, 512)
MAX_CONTENT_SIZE = (480, 480)
BASELINE_Y = 496

NEW_FORMS: tuple[tuple[str, str, str, str], ...] = (
    ("starpath_antlerling", "Starpath Antlerling", "EXPLORATION", "4"),
    ("fatty", "Fatty", "PRECISION", "5"),
    ("obsidian_bastion", "Obsidian Bastion", "SUPPORT", "6"),
)

FORM_SOURCES: dict[tuple[str, str], str] = {
    ("starpath_antlerling", "I"): "A020R2_SPIRIT4_STAGE1_CLEAN.png",
    ("starpath_antlerling", "II"): "A020R2_SPIRIT4_STAGE2_CLEAN.png",
    ("starpath_antlerling", "III"): "A020R2_SPIRIT4_STAGE3_CLEAN.png",
    ("fatty", "I"): "A020R2_SPIRIT5_STAGE1_CLEAN.png",
    ("fatty", "II"): "A020R2_SPIRIT5_STAGE2_CLEAN.png",
    ("fatty", "III"): "A020R2_SPIRIT5_STAGE3_CLEAN.png",
    ("obsidian_bastion", "I"): "A020R2_SPIRIT6_STAGE1_CLEAN.png",
    ("obsidian_bastion", "II"): "A020R2_SPIRIT6_STAGE2_CLEAN.png",
    ("obsidian_bastion", "III"): "A020R2_SPIRIT6_STAGE3_CLEAN.png",
}

EXISTING_SPIRITS: tuple[dict[str, Any], ...] = (
    {
        "slot": 1,
        "spirit_id": "ink_drop_kelpie",
        "role": "TRAINING",
        "display_name": {"zh": "墨滴水靈馬", "en": "Ink-Drop Kelpie"},
        "stage_assets": {
            "I": "assets/pets/pet_ink_drop_kelpie_lv1.webp",
            "II": "assets/pets/horse_anim_lv2/01_idle.webp",
            "III": "assets/pets/horse_anim_lv3/01_idle.webp",
        },
        "animation_manifest": {
            "kind": "existing_runtime_frame_sets",
            "source": "hero.html PET_FRAME_SETS",
            "stage_1": "ink_drop_kelpie_lv1",
            "stage_2": "horse_anim_lv2",
            "stage_3": "horse_anim_lv3",
        },
    },
    {
        "slot": 2,
        "spirit_id": "whispering_void_kit",
        "role": "REVIEW",
        "display_name": {"zh": "低語虛空貓", "en": "Whispering Void Kit"},
        "stage_assets": {
            "I": "assets/pets/pet_whispering_void_kit_lv1.webp",
            "II": "assets/pets/cat_anim_lv2/01_idle.webp",
            "III": "assets/pets/cat_anim_lv3/01_idle.webp",
        },
        "animation_manifest": {
            "kind": "existing_runtime_frame_sets",
            "source": "hero.html PET_FRAME_SETS",
            "stage_1": "whispering_void_kit_lv1",
            "stage_2": "cat_anim_lv2",
            "stage_3": "cat_anim_lv3",
        },
    },
    {
        "slot": 3,
        "spirit_id": "star_shell_hatchling",
        "role": "CHALLENGE",
        "display_name": {"zh": "星殼棋罐龍", "en": "Star-Shell Hatchling"},
        "stage_assets": {
            "I": "assets/pets/pet_star_shell_hatchling_lv1.webp",
            "II": "assets/pets/dragon_anim_lv2/01_idle.webp",
            "III": "assets/pets/dragon_anim_lv3/01_idle.webp",
        },
        "animation_manifest": {
            "kind": "existing_runtime_frame_sets",
            "source": "hero.html PET_FRAME_SETS",
            "stage_1": "star_shell_hatchling_lv1",
            "stage_2": "dragon_anim_lv2",
            "stage_3": "dragon_anim_lv3",
        },
    },
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def image_metadata(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        image.load()
        alpha_extrema = image.getchannel("A").getextrema() if "A" in image.getbands() else None
        return {
            "filename": rel(path),
            "sha256": sha256(path),
            "byte_size": path.stat().st_size,
            "dimensions": [image.width, image.height],
            "format": image.format,
            "mode": image.mode,
            "alpha_extrema": list(alpha_extrema) if alpha_extrema else None,
            "alpha_valid": image.mode == "RGBA" and alpha_extrema == (0, 255),
        }


def normalized_form(source: Path) -> Image.Image:
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
        alpha = image.getchannel("A")
        bbox = alpha.getbbox()
        if bbox is None:
            raise ValueError(f"source has no visible pixels: {source}")
        cropped = image.crop(bbox)
        cropped.thumbnail(MAX_CONTENT_SIZE, Image.Resampling.LANCZOS)
        # Fully transparent source pixels may retain checkerboard RGB values.
        # They are not visible, but clearing them prevents viewers/encoders
        # from displaying a baked-looking matte around the character.
        pixels = cropped.load()
        for y in range(cropped.height):
            for x in range(cropped.width):
                r, g, b, alpha = pixels[x, y]
                if alpha == 0:
                    pixels[x, y] = (0, 0, 0, 0)
        canvas = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        x = (CANVAS_SIZE[0] - cropped.width) // 2
        y = BASELINE_Y - cropped.height
        canvas.alpha_composite(cropped, (x, y))
        return canvas


def write_new_asset(spirit_id: str, stage: str, source_name: str, *, force: bool) -> Path:
    source = SOURCE_DIR / source_name
    if not source.is_file():
        raise FileNotFoundError(source)
    output = RUNTIME_DIR / f"pet_{spirit_id}_stage{ {'I': 1, 'II': 2, 'III': 3}[stage] }.webp"
    if output.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing runtime asset: {output}")
    image = normalized_form(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="WEBP", lossless=True, method=6)
    return output


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        Path("C:/Windows/Fonts/msjh.ttc"),
        Path("C:/Windows/Fonts/NotoSansTC-VF.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ):
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def fit_on_canvas(source: Path, box: tuple[int, int], baseline: int) -> Image.Image:
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
        image.thumbnail(box, Image.Resampling.LANCZOS)
        return image


def draw_label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int = 24) -> None:
    draw.text(xy, text, fill=(242, 215, 146, 255), font=font(size), anchor="ma")


def render_review_sheets(manifest: dict[str, Any], *, force: bool) -> None:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    for output in (NINE_FORM_REVIEW, FOLLOWER_REVIEW):
        if output.exists() and not force:
            raise FileExistsError(f"refusing to overwrite existing review evidence: {output}")

    by_id = {spirit["spirit_id"]: spirit for spirit in manifest["spirits"]}
    new_ids = ["starpath_antlerling", "fatty", "obsidian_bastion"]
    titles = {
        "starpath_antlerling": "#4 Starpath Antlerling",
        "fatty": "#5 阿肥 / Fatty",
        "obsidian_bastion": "#6 Obsidian Bastion",
    }

    # Nine-form progression sheet: columns are Spirits and rows are stages.
    card_w, card_h = 460, 390
    sheet = Image.new("RGBA", (card_w * 3, card_h * 3), (8, 23, 35, 255))
    draw = ImageDraw.Draw(sheet)
    for row, stage in enumerate(("I", "II", "III")):
        for col, spirit_id in enumerate(new_ids):
            x0, y0 = col * card_w, row * card_h
            draw.rectangle((x0 + 8, y0 + 8, x0 + card_w - 8, y0 + card_h - 8), outline=(177, 133, 54, 255), width=2)
            draw_label(draw, (x0 + card_w // 2, y0 + 34), f"{titles[spirit_id]}  ·  Stage {stage}", 22)
            asset = ROOT / by_id[spirit_id]["stages"][stage]["runtime_asset"]
            image = fit_on_canvas(asset, (card_w - 44, card_h - 86), card_h - 74)
            px = x0 + (card_w - image.width) // 2
            py = y0 + 54 + (card_h - 86 - image.height) // 2
            sheet.alpha_composite(image, (px, py))
    sheet.save(NINE_FORM_REVIEW, format="PNG", optimize=False)

    # Follower-scale sheet: current three canonical sprites plus new Stage III.
    follower_ids = [
        "ink_drop_kelpie",
        "whispering_void_kit",
        "star_shell_hatchling",
        "starpath_antlerling",
        "fatty",
        "obsidian_bastion",
    ]
    follower_titles = {
        "ink_drop_kelpie": "墨滴水靈馬",
        "whispering_void_kit": "低語虛空貓",
        "star_shell_hatchling": "星殼棋罐龍",
        **titles,
    }
    follower_w, follower_h = 300, 430
    follower = Image.new("RGBA", (follower_w * 6, follower_h), (8, 23, 35, 255))
    draw = ImageDraw.Draw(follower)
    draw_label(draw, (follower.width // 2, 24), "Six-Spirit follower scale · Hero remains the primary world marker", 24)
    for col, spirit_id in enumerate(follower_ids):
        spirit = by_id[spirit_id]
        asset = ROOT / spirit["stages"]["III"]["runtime_asset"] if spirit_id in new_ids else ROOT / spirit["stages"]["I"]["runtime_asset"]
        image = fit_on_canvas(asset, (follower_w - 36, 300), 368)
        x0 = col * follower_w
        px = x0 + (follower_w - image.width) // 2
        py = 64 + (300 - image.height) // 2
        follower.alpha_composite(image, (px, py))
        draw.line((x0 + 22, 374, x0 + follower_w - 22, 374), fill=(177, 133, 54, 255), width=2)
        draw_label(draw, (x0 + follower_w // 2, 397), follower_titles[spirit_id], 18)
    follower.save(FOLLOWER_REVIEW, format="PNG", optimize=False)


def asset_record(
    spirit_id: str,
    stage: str,
    runtime_path: Path,
    *,
    source_path: Path | None = None,
    source_kind: str,
    animation_manifest: Any = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "runtime_asset": rel(runtime_path),
        "hero_portrait_asset": rel(runtime_path),
        "world_map_follower_asset": rel(runtime_path),
        "source_kind": source_kind,
        "presentation_only": True,
        "format": "WEBP",
        "dimensions": list(CANVAS_SIZE) if source_path else None,
        "asset_integrity": image_metadata(runtime_path),
    }
    if source_path is not None:
        record["source_art"] = {
            "path": rel(source_path),
            "authority": "A020-R2_OWNER_APPROVED_CLEAN_FORM",
            "redrawn": False,
        }
    if animation_manifest is not None:
        record["animation_manifest"] = animation_manifest
    return record


def existing_stage_record(spirit: dict[str, Any], stage: str) -> dict[str, Any]:
    runtime_path = ROOT / spirit["stage_assets"][stage]
    if not runtime_path.is_file():
        raise FileNotFoundError(runtime_path)
    return asset_record(
        spirit["spirit_id"],
        stage,
        runtime_path,
        source_kind="EXISTING_CANONICAL_RUNTIME_ASSET",
        animation_manifest=spirit["animation_manifest"],
    )


def fallback_for(stages: dict[str, dict[str, Any]]) -> dict[str, Any]:
    stage_one = stages["I"]["runtime_asset"]
    return {
        "asset": stage_one,
        "policy": "STAGE_I_SAME_SPIRIT_ONLY",
        "when": "missing Stage II or Stage III presentation asset",
        "changes_spirit_identity": False,
        "changes_ownership_or_stage_authority": False,
        "infinite_retry": False,
        "consumer_action": "fail_closed_safe_empty_or_stage_unavailable_state",
    }


def build(*, force: bool = False) -> dict[str, Any]:
    if not SOURCE_DIR.is_dir():
        raise FileNotFoundError(SOURCE_DIR)
    if not RUNTIME_DIR.is_dir():
        raise FileNotFoundError(RUNTIME_DIR)

    new_records: list[dict[str, Any]] = []
    for spirit_id, display_name, role, slot in NEW_FORMS:
        stages: dict[str, dict[str, Any]] = {}
        for stage in ("I", "II", "III"):
            source_name = FORM_SOURCES[(spirit_id, stage)]
            output = write_new_asset(spirit_id, stage, source_name, force=force)
            stages[stage] = asset_record(
                spirit_id,
                stage,
                output,
                source_path=SOURCE_DIR / source_name,
                source_kind="A020_R2_APPROVED_FORM_NORMALIZED",
            )
        new_records.append(
            {
                "slot": int(slot),
                "spirit_id": spirit_id,
                "role": role,
                "display_name": {"zh": "阿肥" if spirit_id == "fatty" else None, "en": display_name},
                "identity_status": "OWNER_SELECTED",
                "stage_count": 3,
                "stages": stages,
                "fallback": fallback_for(stages),
                "status": "RUNTIME_PRESENTATION_PACKAGE_READY",
                "animation_manifest": None,
            }
        )

    existing_records: list[dict[str, Any]] = []
    for spirit in EXISTING_SPIRITS:
        stages = {stage: existing_stage_record(spirit, stage) for stage in ("I", "II", "III")}
        existing_records.append(
            {
                "slot": spirit["slot"],
                "spirit_id": spirit["spirit_id"],
                "role": spirit["role"],
                "display_name": spirit["display_name"],
                "identity_status": "EXISTING_CANONICAL",
                "stage_count": 3,
                "stages": stages,
                "fallback": fallback_for(stages),
                "status": "EXISTING_ASSET_AUTHORITY_REUSED",
                "animation_manifest": spirit["animation_manifest"],
                "duplicated": False,
            }
        )

    spirits = sorted(existing_records + new_records, key=lambda item: item["slot"])
    runtime_records = [
        stage_record["asset_integrity"]
        for spirit in spirits
        for stage_record in spirit["stages"].values()
    ]
    manifest = {
        "schema": "go_odyssey.six_spirit_runtime_presentation_assets",
        "schema_version": "a021a.v1",
        "task": "A021A",
        "base_sha": "2fa78d0d8be90da3c5a01571f8d455c2d2780635",
        "source_authority": {
            "new_forms": "A020-R2 approved clean forms",
            "source_directory": rel(SOURCE_DIR),
            "redesign": False,
            "pixel_content_redesign": False,
            "review_screenshots_are_runtime_dependencies": False,
        },
        "runtime_asset_directory": rel(RUNTIME_DIR),
        "runtime_dimension_policy": {
            "canvas": list(CANVAS_SIZE),
            "content_box": list(MAX_CONTENT_SIZE),
            "baseline_y": BASELINE_Y,
            "format": "WEBP",
            "mode": "RGBA",
            "compression": "lossless",
            "purpose": "shared Hero portrait and World Map follower presentation source",
        },
        "machine_id_policy": {
            "new_ids": ["starpath_antlerling", "fatty", "obsidian_bastion"],
            "stable": True,
            "ownership_authority_created": False,
            "d008_id_authority_observed_at_start": False,
            "collision_policy": "stop if D008 later establishes conflicting IDs",
        },
        "presentation_manifest_is_ownership_authority": False,
        "missing_asset_contract": {
            "changes_spirit_authority": False,
            "infinite_retry": False,
            "fallback_identity_policy": "same Spirit Stage I only; never another Spirit",
            "consumer_owns_retry_and_empty_state": True,
        },
        "spirits": spirits,
        "asset_hash_manifest": runtime_records,
        "counts": {
            "canonical_spirit_count": 6,
            "existing_spirit_count": 3,
            "new_spirit_count": 3,
            "new_runtime_form_count": 9,
            "runtime_stage_record_count": len(runtime_records),
        },
        "hard_boundaries": {
            "spirit_state_authority_changed": False,
            "combat_runtime_changed": False,
            "second_combat_engine_created": False,
            "monster_files_changed": 0,
            "runtime_catalog_changed": False,
            "app_py_changed": False,
            "route_changed": False,
            "db_migration": False,
            "production_mutation": False,
        },
        "rejected_a020_identity_runtime_reference_count": 0,
        "review_evidence": [
            {"path": rel(NINE_FORM_REVIEW), "purpose": "all nine normalized forms and Stage I to III progression"},
            {"path": rel(FOLLOWER_REVIEW), "purpose": "six Spirit follower-scale silhouette and relative-scale study"},
        ],
        "status": "READY_FOR_OWNER_A021A_SIX_SPIRIT_RUNTIME_ASSET_REVIEW",
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    render_review_sheets(manifest, force=force)
    return manifest


def verify() -> None:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    records = data["asset_hash_manifest"]
    assert len(records) == 18
    for record in records:
        path = ROOT / record["filename"]
        assert path.is_file(), path
        current = image_metadata(path)
        assert current == record, (path, current, record)
    assert data["counts"] == {
        "canonical_spirit_count": 6,
        "existing_spirit_count": 3,
        "new_spirit_count": 3,
        "new_runtime_form_count": 9,
        "runtime_stage_record_count": 18,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify()
    else:
        build(force=args.force)
        verify()


if __name__ == "__main__":
    main()
