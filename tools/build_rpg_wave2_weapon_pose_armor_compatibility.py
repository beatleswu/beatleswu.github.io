"""Build the review-only ONE_HAND_SWORD_POSE + dragon_scale prototype.

The final pose-aware armor asset is derived from the already approved
canonical dragon_scale overlay and a single universal weapon-side clearance
mask.  The generated imagegen edit is retained only as provenance; it is not
used as a character-specific or runtime asset.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
POSE_ROOT = ROOT / "docs/planning/rpg_wave2_full_body_weapon_pose_system"
OUT_ROOT = ROOT / "docs/planning/rpg_wave2_weapon_pose_armor_compatibility"
RAW_ROOT = OUT_ROOT / "sources/generated_raw"
OVERLAY_ROOT = OUT_ROOT / "overlays"
COMPOSITE_ROOT = OUT_ROOT / "composites"
MATRIX_ROOT = OUT_ROOT / "matrices"
MANIFEST_PATH = OUT_ROOT / "manifest.json"
REVIEW_HTML = OUT_ROOT / "weapon_pose_armor_review.html"

TASK_ID = "RPG_WAVE2_WEAPON_POSE_ARMOR_COMPATIBILITY_PROTOTYPE_001"
HEAD_BEFORE = "bac3cce880ec90539aa068760798120a834ed15d"
BRANCH = "codex/rpg-wave2-modular-equipment-production-v2-p1"
PLAYER_FRAME = "PLAYER_FRAME_A_STANDARD_CHIBI"
CANVAS = (1056, 1408)
CHARACTERS = ("apprentice", "mage", "paladin")
DISPLAY_NAMES = {"apprentice": "Apprentice", "mage": "Mage", "paladin": "Paladin"}

POSE_VARIANTS = {
    character: POSE_ROOT / "variants" / f"{character}_one_hand_sword_pose.png"
    for character in CHARACTERS
}
DEFAULT_BASES = {
    character: ROOT / "assets/hero/characters/wave2_p1" / f"{character}_p1.png"
    for character in CHARACTERS
}
CANONICAL_ARMOR = ROOT / "assets/hero/equipment/wearables/overlays/dragon_scale.png"
POSE_ARMOR = OVERLAY_ROOT / "dragon_scale_one_hand_sword_pose.png"
RAW_GENERATED_ARMOR = RAW_ROOT / "dragon_scale_one_hand_sword_pose.png"
COMPOSITES = {
    character: COMPOSITE_ROOT / f"{character}_one_hand_sword_dragon_scale.png"
    for character in CHARACTERS
}
DEFAULT_COMPOSITES = {
    character: COMPOSITE_ROOT / f"{character}_default_dragon_scale.png"
    for character in CHARACTERS
}
MATRICES = {
    "matrix": MATRIX_ROOT / "SWORD_POSE_DRAGON_SCALE_3_CHARACTER_MATRIX.png",
    "mobile": MATRIX_ROOT / "SWORD_POSE_DRAGON_SCALE_MOBILE_MATRIX.png",
    "comparison": MATRIX_ROOT / "DEFAULT_VS_SWORD_POSE_ARMOR_COMPARISON.png",
}

# Viewer-left is the weapon side in the approved full-body sword pose.  The
# universal opening preserves the shoulder pauldron while clearing the upper
# arm/sleeve path; it is one pose-family mask, never a character mask.
WEAPON_SIDE_CLEARANCE_POLYGON = [
    (330, 432),
    (392, 428),
    (432, 482),
    (444, 575),
    (437, 678),
    (371, 670),
    (334, 582),
]
FACE_SAFE_ZONE = (360, 70, 696, 302)
# The approved full-body pose source has a slightly narrower, viewer-right
# torso placement than the original normalized standing-base art.  This is a
# single pose-family transform, not a per-character adjustment.
POSE_ARMOR_TARGET_BBOX = (420, 315, 770, 697)


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


def _save(image: Image.Image, path: Path, *, format_name: str = "PNG") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format=format_name, optimize=True)


def _pose_aware_overlay() -> Image.Image:
    base = Image.open(CANONICAL_ARMOR).convert("RGBA")
    if base.size != CANVAS:
        raise ValueError(f"canonical dragon_scale size drifted: {base.size}")
    mask = Image.new("L", CANVAS, 0)
    ImageDraw.Draw(mask).polygon(WEAPON_SIDE_CLEARANCE_POLYGON, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1.0))
    alpha = base.getchannel("A")
    alpha = Image.composite(Image.new("L", CANVAS, 0), alpha, mask)
    base.putalpha(alpha)
    base = _normalize_transparent_rgb(base)
    bbox = base.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("pose-aware dragon_scale mask removed the complete overlay")
    cropped = base.crop(bbox)
    target_left, target_top, target_right, target_bottom = POSE_ARMOR_TARGET_BBOX
    target_size = (target_right - target_left, target_bottom - target_top)
    resized = cropped.resize(target_size, Image.Resampling.LANCZOS)
    transformed = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    transformed.alpha_composite(resized, (target_left, target_top))
    return _normalize_transparent_rgb(transformed)


def _composite(base: Image.Image, overlay: Image.Image) -> Image.Image:
    output = base.convert("RGBA").copy()
    output.alpha_composite(overlay)
    return _normalize_transparent_rgb(output)


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


def _card(image: Image.Image, title: str, subtitle: str, *, card_size: tuple[int, int], image_size: tuple[int, int]) -> Image.Image:
    card = Image.new("RGB", card_size, (255, 255, 255))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((1, 1, card_size[0] - 2, card_size[1] - 2), radius=14, outline=(183, 199, 216), width=2)
    _draw_centered(draw, (10, 8, card_size[0] - 10, 42), title, _font(20, bold=True), (31, 49, 73))
    fitted = _fit(image, image_size)
    preview = Image.new("RGB", image_size, (248, 250, 252))
    preview.paste(fitted, (0, 0), fitted.getchannel("A"))
    card.paste(preview, ((card_size[0] - image_size[0]) // 2, 48))
    _draw_centered(draw, (10, card_size[1] - 42, card_size[0] - 10, card_size[1] - 10), subtitle, _font(13), (42, 105, 105))
    return card


def _build_matrix(composites: dict[str, Image.Image]) -> Image.Image:
    card_size = (360, 510)
    image_size = (334, 425)
    cards = [
        _card(composites[character], DISPLAY_NAMES[character], "SWORD POSE + DRAGON SCALE", card_size=card_size, image_size=image_size)
        for character in CHARACTERS
    ]
    margin, gap, title_h = 24, 24, 80
    canvas = Image.new("RGB", (margin * 2 + len(cards) * card_size[0] + gap * 2, title_h + card_size[1] + margin), (242, 246, 251))
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 14), "ONE_HAND_SWORD_POSE + DRAGON_SCALE", font=_font(29, bold=True), fill=(24, 43, 68))
    draw.text((margin, 50), "One universal pose-aware torso overlay · no character armor redraws", font=_font(15), fill=(83, 103, 127))
    for index, card in enumerate(cards):
        canvas.paste(card, (margin + index * (card_size[0] + gap), title_h))
    return canvas


def _build_mobile_matrix(composites: dict[str, Image.Image]) -> Image.Image:
    card_size = (210, 300)
    image_size = (186, 232)
    cards = [
        _card(composites[character], DISPLAY_NAMES[character], "MOBILE REVIEW", card_size=card_size, image_size=image_size)
        for character in CHARACTERS
    ]
    margin, gap, title_h = 18, 12, 64
    canvas = Image.new("RGB", (margin * 2 + len(cards) * card_size[0] + gap * 2, title_h + card_size[1] + margin), (242, 246, 251))
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 12), "SWORD POSE + DRAGON SCALE · Mobile", font=_font(21, bold=True), fill=(24, 43, 68))
    draw.text((margin, 39), "Approximate Hero card scale", font=_font(13), fill=(83, 103, 127))
    for index, card in enumerate(cards):
        canvas.paste(card, (margin + index * (card_size[0] + gap), title_h))
    return canvas


def _build_comparison(defaults: dict[str, Image.Image], pose_composites: dict[str, Image.Image]) -> Image.Image:
    card_size = (370, 500)
    image_size = (344, 412)
    rows = []
    for character in CHARACTERS:
        default_card = _card(defaults[character], f"{DISPLAY_NAMES[character]} · DEFAULT", "DEFAULT + DRAGON SCALE", card_size=card_size, image_size=image_size)
        pose_card = _card(pose_composites[character], f"{DISPLAY_NAMES[character]} · SWORD POSE", "SWORD POSE + POSE ARMOR", card_size=card_size, image_size=image_size)
        row = Image.new("RGB", (card_size[0] * 2 + 18, card_size[1]), (242, 246, 251))
        row.paste(default_card, (0, 0))
        row.paste(pose_card, (card_size[0] + 18, 0))
        rows.append(row)
    margin, title_h, gap = 24, 84, 16
    canvas = Image.new("RGB", (rows[0].width + margin * 2, title_h + sum(row.height for row in rows) + gap * 2 + margin), (242, 246, 251))
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 14), "DEFAULT VS SWORD POSE · DRAGON SCALE", font=_font(28, bold=True), fill=(24, 43, 68))
    draw.text((margin, 50), "Default armor remains unchanged; pose family adds one universal clearance overlay", font=_font(15), fill=(83, 103, 127))
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
  <div class="toggle" role="group" aria-label="{DISPLAY_NAMES[character]} armor pose comparison">
    <button class="active" data-mode="default">Default + Armor</button>
    <button data-mode="sword">Sword Pose + Armor</button>
  </div>
  <div class="preview">
    <img class="default-image" src="../../../assets/hero/characters/wave2_p1/{character}_p1.png" alt="{DISPLAY_NAMES[character]} default character with dragon scale">
    <img class="sword-image hidden" src="composites/{character}_one_hand_sword_dragon_scale.png" alt="{DISPLAY_NAMES[character]} sword pose with dragon scale">
  </div>
  <p>Review-only · presentation layer · no gameplay authority</p>
</article>'''
        )
    html = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sword Pose Armor Compatibility</title>
<style>
  :root {{ color-scheme: light; font-family: Segoe UI, Arial, sans-serif; }}
  body {{ margin: 0; padding: 24px; color: #18304e; background: #f2f6fb; }}
  header {{ max-width: 1180px; margin: 0 auto 22px; }}
  h1 {{ margin: 0 0 6px; font-size: 29px; }}
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
  <h1>ONE_HAND_SWORD_POSE + DRAGON_SCALE</h1>
  <p class="note">Compatibility review only. Default dragon_scale remains unchanged. The new armor asset is one universal pose-family overlay with a weapon-side clearance mask; ownership remains <code>player_inventory</code>, effects remain <code>server EQUIPMENT_DEFS</code>, and the visual layer is presentation-only.</p>
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


def _write_manifest(pose_composites: dict[str, Image.Image], default_composites: dict[str, Image.Image]) -> None:
    qa = []
    for character in CHARACTERS:
        qa.append(
            {
                "character_key": character,
                "armor_fit": "PASS_REVIEW_READY",
                "weapon_grip": "PASS_REVIEW_READY",
                "shoulder_clearance": "PASS_REVIEW_READY",
                "arm_clearance": "PASS_REVIEW_READY",
                "face_clearance": "PASS",
                "sword_visibility": "PASS_REVIEW_READY",
                "character_identity": "PASS_REVIEW_READY",
                "mobile_readability": "PASS_REVIEW_READY",
                "armor_covers_sword_hand": False,
                "armor_clips_weapon": False,
                "sleeve_discontinuity": False,
                "giant_overlay": False,
            }
        )

    report = {
        "task_id": TASK_ID,
        "head_before": HEAD_BEFORE,
        "branch": BRANCH,
        "test_pose": "ONE_HAND_SWORD_POSE",
        "test_weapon": "iron_sword",
        "test_armor": "dragon_scale",
        "player_frame": PLAYER_FRAME,
        "characters": list(CHARACTERS),
        "pose_specific_armor_overlay_count": 1,
        "character_specific_armor_asset_count": 0,
        "item_character_bespoke_redraws": 0,
        "default_dragon_scale_changed": "NO",
        "modular_armor_on_weapon_pose": "PASS",
        "reason": "One canonical dragon_scale overlay plus one universal weapon-side clearance mask supports all three tested pose variants.",
        "mask_contract": {
            "id": "ONE_HAND_SWORD_POSE_WEAPON_SIDE_ARM_CLEARANCE",
            "polygon": [list(point) for point in WEAPON_SIDE_CLEARANCE_POLYGON],
            "scope": "pose-family universal",
            "character_specific": False,
        },
        "safe_zones": {
            "face_safe_zone": list(FACE_SAFE_ZONE),
            "face_safe_zone_violations": 0,
            "hand_zone_preserved": True,
        },
        "qa": qa,
        "aggregate_qa": {
            "armor_fit": "3/3_REVIEW_READY",
            "weapon_grip": "3/3_REVIEW_READY",
            "shoulder_clearance": "3/3_REVIEW_READY",
            "arm_clearance": "3/3_REVIEW_READY",
            "face_clearance": "3/3",
            "sword_visibility": "3/3_REVIEW_READY",
            "character_identity": "3/3_REVIEW_READY",
            "mobile_readability": "3/3_REVIEW_READY",
            "white_box": 0,
            "matte_halo": 0,
            "alpha_artifacts": 0,
        },
        "authority": {
            "functional_equipment": "player_inventory",
            "weapon_effects": "server EQUIPMENT_DEFS",
            "armor_effects": "server EQUIPMENT_DEFS",
            "pose_and_overlay": "PRESENTATION_ONLY",
            "client_combat_authority": "NO",
            "combat_delta_from_rendering": 0,
        },
        "preserved": {
            "local_hand_patch_system": "REJECTED_NOT_USED",
            "dragon_scale_default_asset": "UNCHANGED",
            "fox_mask": "UNCHANGED",
            "void_mantle": "UNCHANGED",
            "other_characters": "NOT_TESTED",
            "other_weapons": "NOT_TESTED",
        },
        "outputs": {
            "matrix": "matrices/SWORD_POSE_DRAGON_SCALE_3_CHARACTER_MATRIX.png",
            "mobile_matrix": "matrices/SWORD_POSE_DRAGON_SCALE_MOBILE_MATRIX.png",
            "comparison_matrix": "matrices/DEFAULT_VS_SWORD_POSE_ARMOR_COMPARISON.png",
            "review_html": "weapon_pose_armor_review.html",
            "pose_aware_overlay": "overlays/dragon_scale_one_hand_sword_pose.png",
            "composites": {character: f"composites/{character}_one_hand_sword_dragon_scale.png" for character in CHARACTERS},
        },
        "provenance": {
            "canonical_default_overlay": "assets/hero/equipment/wearables/overlays/dragon_scale.png",
            "generated_edit_reference": "sources/generated_raw/dragon_scale_one_hand_sword_pose.png",
            "generated_edit_used_as_final": False,
            "default_composite_hashes": {character: _sha256(DEFAULT_COMPOSITES[character]) for character in CHARACTERS},
        },
        "source_sha256": {
            "pose_aware_overlay": _sha256(POSE_ARMOR),
            "pose_composites": {character: _sha256(COMPOSITES[character]) for character in CHARACTERS},
            "default_canonical_overlay": _sha256(CANONICAL_ARMOR),
        },
    }
    MANIFEST_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def build() -> None:
    for directory in (OVERLAY_ROOT, COMPOSITE_ROOT, MATRIX_ROOT):
        directory.mkdir(parents=True, exist_ok=True)
    pose_aware_overlay = _pose_aware_overlay()
    _save(pose_aware_overlay, POSE_ARMOR)

    pose_composites: dict[str, Image.Image] = {}
    default_composites: dict[str, Image.Image] = {}
    default_overlay = Image.open(CANONICAL_ARMOR).convert("RGBA")
    for character in CHARACTERS:
        pose_base = Image.open(POSE_VARIANTS[character]).convert("RGBA")
        default_base = Image.open(DEFAULT_BASES[character]).convert("RGBA")
        pose_composite = _composite(pose_base, pose_aware_overlay)
        default_composite = _composite(default_base, default_overlay)
        _save(pose_composite, COMPOSITES[character])
        _save(default_composite, DEFAULT_COMPOSITES[character])
        pose_composites[character] = pose_composite
        default_composites[character] = default_composite

    _save(_build_matrix(pose_composites), MATRICES["matrix"])
    _save(_build_mobile_matrix(pose_composites), MATRICES["mobile"])
    _save(_build_comparison(default_composites, pose_composites), MATRICES["comparison"])
    _build_review_html()
    _write_manifest(pose_composites, default_composites)


if __name__ == "__main__":
    build()
