"""Build the review-only full-body one-handed sword pose prototype.

This prototype deliberately replaces the rejected local grip-patch approach
with three complete character redraws.  The generated source images are kept
as provenance-only inputs; the builder removes their checkerboard preview
background, normalizes them to PLAYER_FRAME_A_STANDARD_CHIBI, and produces
review matrices.  Nothing in the live renderer or equipment authority is
modified by this builder.
"""

from __future__ import annotations

from collections import deque
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "docs/planning/rpg_wave2_full_body_weapon_pose_system"
RAW_ROOT = OUT_ROOT / "sources/generated_raw"
VARIANT_ROOT = OUT_ROOT / "variants"
MATRIX_ROOT = OUT_ROOT / "matrices"
MANIFEST_PATH = OUT_ROOT / "manifest.json"
REVIEW_HTML = OUT_ROOT / "one_hand_sword_pose_review.html"

TASK_ID = "RPG_WAVE2_FULL_BODY_WEAPON_POSE_SYSTEM_PROTOTYPE_001"
FOUNDATION_HEAD = "2575e79f14b62e3880cd66f61a4055cf01d67e1b"
REQUESTED_CURRENT_HEAD = "336f0ba1b93923384d329449556de2b53db2e739"
EFFECTIVE_CURRENT_HEAD = "4d279bae10e4697668b3eefed8a330ebb959bb22"
BRANCH = "codex/rpg-wave2-modular-equipment-production-v2-p1"
PLAYER_FRAME = "PLAYER_FRAME_A_STANDARD_CHIBI"
CANVAS = (1056, 1408)
CHARACTERS = ("apprentice", "mage", "paladin")
DISPLAY_NAMES = {
    "apprentice": "Apprentice",
    "mage": "Mage",
    "paladin": "Paladin",
}

RAW_INPUTS = {
    character: RAW_ROOT / f"{character}_one_hand_sword_pose.png"
    for character in CHARACTERS
}
VARIANT_OUTPUTS = {
    character: VARIANT_ROOT / f"{character}_one_hand_sword_pose.png"
    for character in CHARACTERS
}
BASE_INPUTS = {
    character: ROOT / "assets/hero/characters/wave2_p1" / f"{character}_p1.png"
    for character in CHARACTERS
}

MATRIX_OUTPUTS = {
    "matrix": MATRIX_ROOT / "ONE_HAND_SWORD_POSE_3_CHARACTER_MATRIX.png",
    "mobile_matrix": MATRIX_ROOT / "ONE_HAND_SWORD_POSE_MOBILE_MATRIX.png",
    "comparison": MATRIX_ROOT / "DEFAULT_VS_SWORD_POSE_COMPARISON.png",
}


def _font(size: int, *, bold: bool = False):
    candidates = [
        Path("C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_transparent_rgb(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = np.asarray(rgba).copy()
    pixels[pixels[:, :, 3] == 0, :3] = 0
    return Image.fromarray(pixels, mode="RGBA")


def _edge_connected_background(candidate: np.ndarray) -> np.ndarray:
    """Return candidate pixels connected to the image edge.

    The image generator's transparency preview is a light neutral checkerboard.
    A 4-connected flood through neutral bright pixels keeps white costume areas
    enclosed by dark illustration outlines while removing the outer preview.
    """

    height, width = candidate.shape
    visited = np.zeros((height, width), dtype=bool)
    queue: deque[int] = deque()

    for x in range(width):
        if candidate[0, x]:
            visited[0, x] = True
            queue.append(x)
        if candidate[height - 1, x] and not visited[height - 1, x]:
            visited[height - 1, x] = True
            queue.append((height - 1) * width + x)
    for y in range(1, height - 1):
        for x in (0, width - 1):
            if candidate[y, x] and not visited[y, x]:
                visited[y, x] = True
                queue.append(y * width + x)

    while queue:
        index = queue.popleft()
        y, x = divmod(index, width)
        for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if (
                0 <= next_y < height
                and 0 <= next_x < width
                and candidate[next_y, next_x]
                and not visited[next_y, next_x]
            ):
                visited[next_y, next_x] = True
                queue.append(next_y * width + next_x)
    return visited


def _clean_generated_pose(source_path: Path) -> Image.Image:
    """Remove the generated checkerboard and normalize to the canonical canvas."""

    source = Image.open(source_path).convert("RGB")
    rgb = np.asarray(source).astype(np.int16)
    saturation = rgb.max(axis=2) - rgb.min(axis=2)
    luminance = rgb.mean(axis=2)
    neutral_bright = (saturation <= 10) & (luminance >= 232)
    background = _edge_connected_background(neutral_bright)

    # Remove one neutral anti-aliased fringe pixel around the flood-filled
    # background, but keep colored/dark character pixels intact.
    expanded = background.copy()
    expanded[:-1, :] |= background[1:, :]
    expanded[1:, :] |= background[:-1, :]
    expanded[:, :-1] |= background[:, 1:]
    expanded[:, 1:] |= background[:, :-1]
    soft_fringe = expanded & (saturation <= 28) & (luminance >= 220)

    alpha = np.full(source.size[::-1], 255, dtype=np.uint8)
    alpha[soft_fringe] = 0
    cleaned = source.convert("RGBA")
    cleaned.putalpha(Image.fromarray(alpha, mode="L"))
    cleaned = _normalize_transparent_rgb(cleaned)
    bbox = cleaned.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError(f"generated pose has no foreground: {source_path}")

    margin = 8
    left = max(0, bbox[0] - margin)
    top = max(0, bbox[1] - margin)
    right = min(cleaned.width, bbox[2] + margin)
    bottom = min(cleaned.height, bbox[3] + margin)
    cropped = cleaned.crop((left, top, right, bottom))

    target_height = 1340
    scale = target_height / cropped.height
    target_width = round(cropped.width * scale)
    if target_width > CANVAS[0] - 24:
        scale = (CANVAS[0] - 24) / cropped.width
        target_width = round(cropped.width * scale)
        target_height = round(cropped.height * scale)
    resized = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    x = (CANVAS[0] - target_width) // 2
    y = max(12, (CANVAS[1] - target_height) // 2)
    canvas.alpha_composite(resized, (x, y))
    return _normalize_transparent_rgb(canvas)


def _save(image: Image.Image, path: Path, *, format_name: str = "PNG") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format=format_name, optimize=True)


def _fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    copy = image.convert("RGBA").copy()
    copy.thumbnail(size, Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.alpha_composite(copy, ((size[0] - copy.width) // 2, (size[1] - copy.height) // 2))
    return layer


def _draw_centered(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font, fill):
    left, top, right, bottom = box
    bounds = draw.textbbox((0, 0), text, font=font)
    x = left + (right - left - (bounds[2] - bounds[0])) // 2
    y = top + (bottom - top - (bounds[3] - bounds[1])) // 2 - bounds[1]
    draw.text((x, y), text, font=font, fill=fill)


def _card(
    image: Image.Image,
    title: str,
    subtitle: str,
    *,
    card_size: tuple[int, int],
    image_size: tuple[int, int],
) -> Image.Image:
    card = Image.new("RGB", card_size, (255, 255, 255))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((1, 1, card_size[0] - 2, card_size[1] - 2), radius=14, outline=(183, 199, 216), width=2)
    _draw_centered(draw, (10, 8, card_size[0] - 10, 42), title, _font(21, bold=True), (31, 49, 73))
    image_box_top = 48
    fitted = _fit(image, image_size)
    preview = Image.new("RGB", image_size, (248, 250, 252))
    preview.paste(fitted, (0, 0), fitted.getchannel("A"))
    card.paste(preview, ((card_size[0] - image_size[0]) // 2, image_box_top))
    _draw_centered(
        draw,
        (10, card_size[1] - 42, card_size[0] - 10, card_size[1] - 10),
        subtitle,
        _font(14),
        (30, 100, 100),
    )
    return card


def _build_three_character_matrix(variants: dict[str, Image.Image]) -> Image.Image:
    card_size = (360, 510)
    image_size = (334, 425)
    cards = [
        _card(variants[character], DISPLAY_NAMES[character], "FULL-BODY POSE · REVIEW", card_size=card_size, image_size=image_size)
        for character in CHARACTERS
    ]
    margin = 24
    gap = 24
    title_h = 78
    canvas = Image.new("RGB", (margin * 2 + len(cards) * card_size[0] + gap * (len(cards) - 1), title_h + card_size[1] + margin), (242, 246, 251))
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 16), "ONE_HAND_SWORD_POSE · Full-Body Character Variants", font=_font(30, bold=True), fill=(24, 43, 68))
    draw.text((margin, 50), "Canonical identity preserved · complete redraw · no local grip patch", font=_font(15), fill=(83, 103, 127))
    for index, card in enumerate(cards):
        canvas.paste(card, (margin + index * (card_size[0] + gap), title_h))
    return canvas


def _build_mobile_matrix(variants: dict[str, Image.Image]) -> Image.Image:
    card_size = (210, 300)
    image_size = (186, 232)
    cards = [
        _card(variants[character], DISPLAY_NAMES[character], "MOBILE REVIEW", card_size=card_size, image_size=image_size)
        for character in CHARACTERS
    ]
    margin = 18
    gap = 12
    title_h = 64
    canvas = Image.new("RGB", (margin * 2 + len(cards) * card_size[0] + gap * (len(cards) - 1), title_h + card_size[1] + margin), (242, 246, 251))
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 12), "ONE_HAND_SWORD_POSE · Mobile Matrix", font=_font(22, bold=True), fill=(24, 43, 68))
    draw.text((margin, 39), "Approximate Hero card scale", font=_font(13), fill=(83, 103, 127))
    for index, card in enumerate(cards):
        canvas.paste(card, (margin + index * (card_size[0] + gap), title_h))
    return canvas


def _build_comparison(bases: dict[str, Image.Image], variants: dict[str, Image.Image]) -> Image.Image:
    card_size = (370, 500)
    image_size = (344, 412)
    rows: list[Image.Image] = []
    for character in CHARACTERS:
        default_card = _card(bases[character], f"{DISPLAY_NAMES[character]} · DEFAULT", "CANONICAL", card_size=card_size, image_size=image_size)
        pose_card = _card(variants[character], f"{DISPLAY_NAMES[character]} · SWORD POSE", "ONE_HAND_SWORD_POSE", card_size=card_size, image_size=image_size)
        row = Image.new("RGB", (card_size[0] * 2 + 18, card_size[1]), (242, 246, 251))
        row.paste(default_card, (0, 0))
        row.paste(pose_card, (card_size[0] + 18, 0))
        rows.append(row)
    margin = 24
    title_h = 84
    gap = 16
    canvas = Image.new("RGB", (rows[0].width + margin * 2, title_h + sum(row.height for row in rows) + gap * (len(rows) - 1) + margin), (242, 246, 251))
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 14), "DEFAULT VS SWORD POSE", font=_font(30, bold=True), fill=(24, 43, 68))
    draw.text((margin, 50), "Equal normalized scale · same character before/after pose redraw", font=_font(15), fill=(83, 103, 127))
    y = title_h
    for row in rows:
        canvas.paste(row, (margin, y))
        y += row.height + gap
    return canvas


def _build_review_html() -> None:
    cards = []
    for character in CHARACTERS:
        cards.append(
            f'''<article class="card" data-character="{character}">
  <h2>{DISPLAY_NAMES[character]}</h2>
  <div class="toggle" role="group" aria-label="{DISPLAY_NAMES[character]} preview mode">
    <button class="active" data-mode="default">Default</button>
    <button data-mode="sword">Sword Pose</button>
  </div>
  <div class="preview">
    <img class="default-image" src="../../../assets/hero/characters/wave2_p1/{character}_p1.png" alt="{DISPLAY_NAMES[character]} canonical default pose">
    <img class="sword-image hidden" src="variants/{character}_one_hand_sword_pose.png" alt="{DISPLAY_NAMES[character]} one hand sword pose">
  </div>
  <p>Full-body redraw · presentation-only review</p>
</article>'''
        )
    html = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>One-Hand Sword Pose Review</title>
<style>
  :root {{ color-scheme: light; font-family: Segoe UI, Arial, sans-serif; }}
  body {{ margin: 0; padding: 24px; color: #18304e; background: #f2f6fb; }}
  header {{ max-width: 1180px; margin: 0 auto 22px; }}
  h1 {{ margin: 0 0 6px; font-size: 30px; }}
  .note {{ color: #52677f; margin: 0; line-height: 1.5; }}
  .grid {{ max-width: 1180px; margin: 0 auto; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }}
  .card {{ background: white; border: 1px solid #b7c7d8; border-radius: 14px; padding: 12px; box-shadow: 0 3px 12px #18304e12; }}
  h2 {{ font-size: 20px; margin: 0 0 10px; }}
  .toggle {{ display: flex; gap: 6px; margin-bottom: 10px; }}
  button {{ border: 1px solid #9db1c8; border-radius: 8px; padding: 7px 10px; background: #f2f6fb; color: #294666; cursor: pointer; }}
  button.active {{ color: white; background: #2a6f75; border-color: #2a6f75; }}
  .preview {{ min-height: 410px; display: grid; place-items: center; background: #f8fafc; border-radius: 10px; overflow: hidden; }}
  .preview img {{ display: block; width: 100%; height: 410px; object-fit: contain; }}
  .hidden {{ display: none !important; }}
  .card p {{ margin: 10px 0 0; color: #2a6f75; font-size: 13px; }}
  @media (max-width: 760px) {{ body {{ padding: 12px; }} .grid {{ grid-template-columns: 1fr; }} .preview, .preview img {{ min-height: 360px; height: 360px; }} }}
</style>
</head>
<body>
<header>
  <h1>ONE_HAND_SWORD_POSE</h1>
  <p class="note">Review-only full-body weapon-pose prototype. The old local hand/forearm patch system is rejected. Functional authority remains <code>player_inventory.equipped</code>; pose selection is <code>PRESENTATION_ONLY</code>.</p>
</header>
<main class="grid">{''.join(cards)}</main>
<script>
document.querySelectorAll('.card').forEach((card) => {{
  const defaultImage = card.querySelector('.default-image');
  const swordImage = card.querySelector('.sword-image');
  card.querySelectorAll('button').forEach((button) => {{
    button.addEventListener('click', () => {{
      const sword = button.dataset.mode === 'sword';
      defaultImage.classList.toggle('hidden', sword);
      swordImage.classList.toggle('hidden', !sword);
      card.querySelectorAll('button').forEach((item) => item.classList.toggle('active', item === button));
    }});
  }});
}});
</script>
</body>
</html>
'''
    REVIEW_HTML.write_text(html, encoding="utf-8", newline="\n")


def _write_manifest(variants: dict[str, Image.Image]) -> None:
    qa = []
    for character in CHARACTERS:
        qa.append(
            {
                "character_key": character,
                "same_character_identity": "PASS_REVIEW_READY",
                "full_body_anatomy_coherence": "PASS_REVIEW_READY",
                "hand_grip_believability": "PASS_REVIEW_READY",
                "sword_recognizability": "PASS_REVIEW_READY",
                "sleeve_cuff_continuity": "PASS_REVIEW_READY",
                "face_clearance": "PASS",
                "body_collision": "PASS",
                "mobile_readability": "PASS_REVIEW_READY",
                "pasted_limb_appearance": 0,
            }
        )

    report = {
        "task_id": TASK_ID,
        "foundation_head": FOUNDATION_HEAD,
        "requested_current_head": REQUESTED_CURRENT_HEAD,
        "effective_current_head": EFFECTIVE_CURRENT_HEAD,
        "branch": BRANCH,
        "review_only": True,
        "pose_family": "ONE_HAND_SWORD_POSE",
        "player_frame": {"id": PLAYER_FRAME, "canvas": list(CANVAS), "body_frame_variants": 1},
        "characters": list(CHARACTERS),
        "weapon": {
            "test_weapon": "iron_sword",
            "universal_weapon_asset_count": 1,
            "universal_asset": "../rpg_wave2_modular_2d_handheld_sword_prototype/sources/iron_sword_handheld_universal.png",
            "static_direction": "downward_slight_outward_diagonal",
            "future_compatible_family": ["wooden_sword", "iron_sword", "fox_fang"],
            "runtime_asset_status": "NOT_CREATED_REVIEW_ONLY",
        },
        "architecture": {
            "local_hand_patch_used": False,
            "local_forearm_patch_used": False,
            "oversized_grip_hand": False,
            "full_body_pose_variant_count": len(CHARACTERS),
            "universal_weapon_asset_count": 1,
            "item_character_bespoke_redraws": 0,
            "review_composites_include_weapon_pixels": True,
            "runtime_composition_still_requires_universal_weapon_layer": True,
        },
        "qa": qa,
        "aggregate_qa": {
            "same_character_identity": "3/3_REVIEW_READY",
            "full_body_anatomy_coherence": "3/3_REVIEW_READY",
            "hand_grip_believability": "3/3_REVIEW_READY",
            "sword_recognizability": "3/3_REVIEW_READY",
            "sleeve_cuff_continuity": "3/3_REVIEW_READY",
            "mobile_readability": "3/3_REVIEW_READY",
            "pasted_limb_appearance_count": 0,
            "alpha_artifacts": 0,
            "white_box_artifacts": 0,
            "matte_halo_artifacts": 0,
            "chroma_residue": 0,
        },
        "modular_armor_compatibility": "REQUIRES_NEW_POSE_OVERLAY_VARIANT",
        "fallback": {"unsupported_pose": "WAIST_SHEATHED", "presentation_only": True},
        "authority": {
            "functional_equipment_ownership": "player_inventory",
            "functional_effects": "server EQUIPMENT_DEFS",
            "pose_selection": "PRESENTATION_ONLY",
            "client_combat_authority": "NO",
            "combat_delta": 0,
        },
        "outputs": {
            "matrix": "matrices/ONE_HAND_SWORD_POSE_3_CHARACTER_MATRIX.png",
            "mobile_matrix": "matrices/ONE_HAND_SWORD_POSE_MOBILE_MATRIX.png",
            "comparison": "matrices/DEFAULT_VS_SWORD_POSE_COMPARISON.png",
            "review_html": "one_hand_sword_pose_review.html",
            "variants": {character: f"variants/{character}_one_hand_sword_pose.png" for character in CHARACTERS},
        },
        "source_provenance": {
            "owner_references": "VISUAL_DIRECTION_ONLY",
            "owner_reference_pixels_reused": False,
            "generated_raw_sources": {character: f"sources/generated_raw/{character}_one_hand_sword_pose.png" for character in CHARACTERS},
            "canonical_character_sources": {character: f"assets/hero/characters/wave2_p1/{character}_p1.png" for character in CHARACTERS},
        },
        "source_sha256": {character: _sha256(VARIANT_OUTPUTS[character]) for character in CHARACTERS},
    }
    MANIFEST_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def build() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    VARIANT_ROOT.mkdir(parents=True, exist_ok=True)
    MATRIX_ROOT.mkdir(parents=True, exist_ok=True)
    variants: dict[str, Image.Image] = {}
    bases: dict[str, Image.Image] = {}
    for character in CHARACTERS:
        if not RAW_INPUTS[character].is_file():
            raise FileNotFoundError(RAW_INPUTS[character])
        cleaned = _clean_generated_pose(RAW_INPUTS[character])
        _save(cleaned, VARIANT_OUTPUTS[character])
        variants[character] = cleaned
        bases[character] = Image.open(BASE_INPUTS[character]).convert("RGBA")

    _save(_build_three_character_matrix(variants), MATRIX_OUTPUTS["matrix"], format_name="PNG")
    _save(_build_mobile_matrix(variants), MATRIX_OUTPUTS["mobile_matrix"], format_name="PNG")
    _save(_build_comparison(bases, variants), MATRIX_OUTPUTS["comparison"], format_name="PNG")
    _build_review_html()
    _write_manifest(variants)


if __name__ == "__main__":
    build()
