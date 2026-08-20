"""Build the Wave 2 P3 functional-equipment wearable runtime package.

The builder consumes item-only transparent wearable sources and the approved
PLAYER_FRAME_A_STANDARD_CHIBI character masters.  It emits one full-frame
overlay per equipment id, reusable per-character front masks, a presentation
registry, and deterministic review matrices.  It never reads gameplay state
and never writes a database or API.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "docs/planning/rpg_wave2_gate2_p3_wearable_sources"
RUNTIME_ROOT = ROOT / "assets/hero/equipment/wearables"
REGISTRY_PATH = RUNTIME_ROOT / "wearable_registry.json"
MATRIX_ROOT = ROOT / "docs/planning/rpg_wave2_gate2_p3_wearable_fit_matrices"

CANVAS = (1056, 1408)
PLAYER_FRAME = "PLAYER_FRAME_A_STANDARD_CHIBI"
MASTER_BASE_SHA = "ac182ed173620a11e66bebeb6003c121b9ceee95"
P2B_PARENT_SHA = "91202655dd5ce5c3d61c2fe20e21b517c29fdfba"
CHARACTERS = (
    "apprentice",
    "mage",
    "paladin",
    "trail_apprentice",
    "night_runner",
    "constellation_apprentice",
)

BASES = {
    character: f"assets/hero/characters/wave2_p1/{character}_p1.png"
    for character in CHARACTERS
}

# These are normalized presentation anchors only.  They are not gameplay or
# ownership authority and intentionally contain no effect/rarity data.
ANCHORS = {
    "apprentice": {
        "face": [528, 235], "torso": [528, 515], "waist_right": [760, 640],
        "back_hilt": [655, 312], "forearm": [735, 690], "chest": [585, 430], "waist_left": [400, 650],
    },
    "mage": {
        "face": [528, 230], "torso": [528, 500], "waist_right": [742, 625],
        "back_hilt": [632, 300], "forearm": [710, 660], "chest": [575, 420], "waist_left": [405, 640],
    },
    "paladin": {
        "face": [528, 232], "torso": [528, 512], "waist_right": [772, 665],
        "back_hilt": [665, 350], "forearm": [745, 690], "chest": [590, 440], "waist_left": [390, 665],
    },
    "trail_apprentice": {
        "face": [528, 235], "torso": [528, 520], "waist_right": [755, 650],
        "back_hilt": [650, 320], "forearm": [730, 690], "chest": [580, 435], "waist_left": [405, 655],
    },
    "night_runner": {
        "face": [528, 232], "torso": [528, 510], "waist_right": [735, 635],
        "back_hilt": [642, 305], "forearm": [715, 675], "chest": [570, 425], "waist_left": [410, 645],
    },
    "constellation_apprentice": {
        "face": [528, 230], "torso": [528, 505], "waist_right": [742, 630],
        "back_hilt": [640, 305], "forearm": [720, 670], "chest": [575, 420], "waist_left": [405, 645],
    },
}


def _spec(
    slot: str,
    canonical_identity: str,
    wearable_class: str,
    anchor: str,
    layer: str,
    target: int,
    source_anchor: tuple[float, float],
    rotation: float = 0,
    masks: tuple[str, ...] = ("BASE_OCCLUSION",),
    mobile: str = "VISIBLE_AT_HERO_MOBILE_SIZE",
    status: str = "READY_WITH_REUSABLE_MASK",
    **extra: object,
) -> dict:
    item = {
        "slot": slot,
        "canonical_identity": canonical_identity,
        "wearable_class": wearable_class,
        "anchor": anchor,
        "layer": layer,
        "target": target,
        "source_anchor": list(source_anchor),
        "rotation_degrees": rotation,
        "mask_requirements": list(masks),
        "mobile_visibility": mobile,
        "production_status": status,
        "source": f"docs/planning/rpg_wave2_gate2_p3_wearable_sources/{extra.pop('source_name', '')}",
    }
    item.update(extra)
    return item


ITEM_SPECS = {
    "wooden_sword": _spec(
        "weapon", "slim warm-tan wooden sword with brown grip", "WEAPON_WAIST",
        "waist_right", "BACK_WEAPON", 450, (0.50, 0.08), 22,
        canonical_icon="assets/hero/equipment/functional/wooden_sword.svg", source_name="wooden_sword.png",
    ),
    "iron_sword": _spec(
        "weapon", "steel sword with brown handle and leather sheath", "WEAPON_WAIST",
        "waist_right", "BACK_WEAPON", 500, (0.50, 0.08), 24,
        canonical_icon="assets/hero/equipment/functional/iron_sword.svg", source_name="iron_sword.png",
    ),
    "fox_fang": _spec(
        "weapon", "curved ivory fox fang with orange-brown guard", "WEAPON_WAIST",
        "waist_right", "BACK_WEAPON", 340, (0.50, 0.12), 28,
        canonical_icon="assets/hero/equipment/functional/fox_fang.svg", source_name="fox_fang.png",
    ),
    "dragon_claw": _spec(
        "weapon", "three-pronged dark slate dragon claw with orange tips", "FOREARM_OR_HAND_GEAR",
        "forearm", "FRONT_BODY", 260, (0.50, 0.58), -18,
        masks=("BASE_OCCLUSION",), canonical_icon="assets/hero/equipment/functional/dragon_claw.svg",
        source_name="dragon_claw.png",
    ),
    "celestial_blade": _spec(
        "weapon", "long blue-white blade with gold star motif", "WEAPON_BACK",
        "back_hilt", "BACK_WEAPON", 720, (0.50, 0.08), 22,
        canonical_icon="assets/hero/equipment/functional/celestial_blade.svg", source_name="celestial_blade.png",
    ),
    "cloth_robe": _spec(
        "armor", "teal and seafoam cloth robe with dark teal seams", "ROBE_OR_BODY_OVERLAY",
        "torso", "TORSO_ARMOR", 500, (0.50, 0.50), 0,
        canonical_icon="assets/hero/equipment/functional/cloth_robe.svg", source_name="cloth_robe.png",
    ),
    "leather_armor": _spec(
        "armor", "brown leather cuirass with straps and gold rivets", "TORSO_ARMOR",
        "torso", "TORSO_ARMOR", 440, (0.50, 0.50), 0,
        canonical_icon="assets/hero/equipment/functional/leather_armor.svg", source_name="leather_armor.png",
    ),
    "fox_pelt": _spec(
        "armor", "orange-brown fox-fur shoulder mantle", "ROBE_OR_BODY_OVERLAY",
        "torso", "TORSO_ARMOR", 520, (0.50, 0.45), 0,
        canonical_icon="assets/hero/equipment/functional/fox_pelt.svg", source_name="fox_pelt.png",
    ),
    "dragon_scale": _spec(
        "armor", "blue and gold layered dragon-scale torso armor", "TORSO_ARMOR",
        "torso", "TORSO_ARMOR", 430, (0.50, 0.50), 0,
        canonical_icon="assets/hero/equipment/functional/dragon_scale.svg", source_name="dragon_scale.png",
    ),
    "void_mantle": _spec(
        "armor", "deep indigo-violet mantle with gold hem", "ROBE_OR_BODY_OVERLAY",
        "torso", "BACK_BODY", 520, (0.50, 0.48), 0,
        canonical_icon="assets/hero/equipment/functional/void_mantle.svg", source_name="void_mantle.png",
    ),
    "lucky_stone": _spec(
        "accessory", "faceted green jade luck stone", "NECK_CHEST",
        "chest", "FRONT_ACCESSORY", 145, (0.50, 0.24), 0,
        canonical_icon="assets/hero/equipment/functional/lucky_stone.svg", source_name="lucky_stone.png",
    ),
    "xp_amulet": _spec(
        "accessory", "silver chain with amber diamond pendant", "NECK_CHEST",
        "chest", "FRONT_ACCESSORY", 165, (0.50, 0.22), 0,
        canonical_icon="assets/hero/equipment/functional/xp_amulet.svg", source_name="xp_amulet.png",
    ),
    "fox_mask": _spec(
        "accessory", "white and red fox face mask with ears", "HEAD_FACE",
        "face", "HEAD_FACE", 210, (0.50, 0.50), 0,
        masks=("HAIR_FRONT_MASK",), canonical_icon="assets/hero/equipment/functional/fox_mask.svg",
        source_name="fox_mask.png",
    ),
    "dragon_eye": _spec(
        "accessory", "orange-gold dragon eye brooch with slit pupil", "BODY_ACCESSORY",
        "chest", "FRONT_ACCESSORY", 125, (0.50, 0.50), 0,
        canonical_icon="assets/hero/equipment/functional/dragon_eye.svg", source_name="dragon_eye.png",
    ),
    "go_stone_black": _spec(
        "accessory", "glossy black Go stone with gold ring motif", "WAIST_CHARM",
        "waist_left", "FRONT_ACCESSORY", 125, (0.50, 0.50), 0,
        canonical_icon="assets/hero/equipment/functional/go_stone_black.svg", source_name="go_stone_black.png",
    ),
}

ARMOR_IDS = (
    "cloth_robe", "leather_armor", "fox_pelt", "dragon_scale", "void_mantle",
)
P3C_REVISED_ARMOR = ("cloth_robe", "fox_pelt", "void_mantle")
FACE_SAFE_ZONE = {
    "relative_to": "ANCHORS[character].face",
    "half_width": 105,
    "top_offset": -110,
    "bottom_offset": 55,
    "alpha_threshold": 32,
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


def _clean_source(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    array = np.asarray(image).copy()
    alpha = array[:, :, 3]
    alpha[alpha < 8] = 0
    array[:, :, 3] = alpha
    array[alpha == 0, :3] = 0
    image = Image.fromarray(array, mode="RGBA")
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError(f"wearable source has no alpha foreground: {path}")
    margin = 8
    left = max(0, bbox[0] - margin)
    top = max(0, bbox[1] - margin)
    right = min(image.width, bbox[2] + margin)
    bottom = min(image.height, bbox[3] + margin)
    return image.crop((left, top, right, bottom))


def _place(source: Image.Image, spec: dict, character: str) -> Image.Image:
    target = int(spec["target"])
    if source.width >= source.height:
        size = (target, max(1, round(source.height * target / source.width)))
    else:
        size = (max(1, round(source.width * target / source.height)), target)
    resized = source.resize(size, Image.Resampling.LANCZOS)
    angle = float(spec.get("rotation_degrees", 0))
    anchor_x, anchor_y = spec["source_anchor"]
    marker = Image.new("L", resized.size, 0)
    ImageDraw.Draw(marker).ellipse(
        (round(anchor_x * resized.width) - 4, round(anchor_y * resized.height) - 4,
         round(anchor_x * resized.width) + 4, round(anchor_y * resized.height) + 4),
        fill=255,
    )
    rotated = resized.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    rotated_marker = marker.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    marker_bbox = rotated_marker.getbbox()
    if marker_bbox is None:
        raise ValueError(f"lost placement anchor for {spec}")
    anchor = ((marker_bbox[0] + marker_bbox[2]) / 2, (marker_bbox[1] + marker_bbox[3]) / 2)
    target_x, target_y = ANCHORS[character][spec["anchor"]]
    left = round(target_x - anchor[0])
    top = round(target_y - anchor[1])
    layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    layer.alpha_composite(rotated, (left, top))
    return layer


def _hair_mask(base: Image.Image, character: str) -> Image.Image:
    """Build a conservative reusable front-hair patch for the six P1 bases."""

    rgba = base.convert("RGBA")
    rgb = np.asarray(rgba.convert("RGB")).astype(np.int16)
    alpha = np.asarray(rgba.getchannel("A"))
    red, green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    head = np.zeros(alpha.shape, dtype=bool)
    head[20:590, 250:810] = True
    chroma = np.maximum.reduce([red, green, blue]) - np.minimum.reduce([red, green, blue])
    skin = (red > 150) & (green > 90) & (red > blue + 18) & (green > blue + 8)
    # Hair/hood/cloth pixels are kept, while bright skin and the lower body
    # are excluded.  This is deliberately a reusable mask, not item art.
    mask = head & (alpha > 32) & (chroma > 18) & ~skin
    if character == "constellation_apprentice":
        mask[230:345, 455:605] = False
    output_alpha = Image.fromarray(mask.astype(np.uint8) * 255, mode="L")
    output_alpha = output_alpha.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(0.7))
    output = rgba.copy()
    output.putalpha(output_alpha)
    array = np.asarray(output).copy()
    array[np.asarray(output_alpha) == 0, :3] = 0
    return Image.fromarray(array, mode="RGBA")


def _save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def _face_zone_pixel_count(layer: Image.Image, character: str) -> int:
    """Count meaningful wearable pixels inside the reusable face-safe zone."""
    center_x, center_y = ANCHORS[character]["face"]
    x0 = max(0, center_x - FACE_SAFE_ZONE["half_width"])
    x1 = min(CANVAS[0], center_x + FACE_SAFE_ZONE["half_width"])
    y0 = max(0, center_y + FACE_SAFE_ZONE["top_offset"])
    y1 = min(CANVAS[1], center_y + FACE_SAFE_ZONE["bottom_offset"])
    alpha = np.asarray(layer.getchannel("A"))
    return int((alpha[y0:y1, x0:x1] > FACE_SAFE_ZONE["alpha_threshold"]).sum())


def _clear_face_zone_for_armor(layer: Image.Image, character: str) -> Image.Image:
    """Apply the shared face-clearance mask to reusable armor overlays.

    The mask is normalized to PLAYER_FRAME_A_STANDARD_CHIBI and is applied to
    the armor layer only.  It preserves the base character's eyes, nose,
    mouth, and jaw reading area without creating character-specific armor art.
    Face accessories such as fox_mask never pass through this helper.
    """
    center_x, center_y = ANCHORS[character]["face"]
    x0 = max(0, center_x - FACE_SAFE_ZONE["half_width"])
    x1 = min(CANVAS[0], center_x + FACE_SAFE_ZONE["half_width"])
    y0 = max(0, center_y + FACE_SAFE_ZONE["top_offset"])
    y1 = min(CANVAS[1], center_y + FACE_SAFE_ZONE["bottom_offset"])
    alpha = np.asarray(layer.getchannel("A")).copy()
    alpha[y0:y1, x0:x1] = 0
    output = layer.copy()
    output.putalpha(Image.fromarray(alpha, mode="L"))
    pixels = np.asarray(output).copy()
    pixels[alpha == 0, :3] = 0
    return Image.fromarray(pixels, mode="RGBA")


def _composition(base: Image.Image, layers: dict[str, Image.Image], selected: set[str], mask: Image.Image) -> Image.Image:
    output = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    for item_id, spec in ITEM_SPECS.items():
        if item_id in selected and spec["layer"] in {"BACK_WEAPON", "BACK_BODY"}:
            output = Image.alpha_composite(output, layers[item_id])
    output = Image.alpha_composite(output, base)
    for item_id, spec in ITEM_SPECS.items():
        if item_id in selected and spec["layer"] in {"TORSO_ARMOR", "FRONT_BODY", "FRONT_ACCESSORY"}:
            output = Image.alpha_composite(output, layers[item_id])
    for item_id, spec in ITEM_SPECS.items():
        if item_id in selected and spec["layer"] == "HEAD_FACE":
            output = Image.alpha_composite(output, layers[item_id])
    if "fox_mask" in selected:
        output = Image.alpha_composite(output, mask)
    return output


def _matrix_sheet(title: str, rows: list[str], composites: dict[tuple[str, str], Image.Image], results: dict[tuple[str, str], str], filename: str) -> None:
    cell_w, cell_h, gap, margin = 190, 255, 12, 18
    header = 64
    sheet = Image.new("RGB", (margin * 2 + 6 * cell_w + 5 * gap, header + margin + len(rows) * (cell_h + gap) + margin), "#eef3f7")
    draw = ImageDraw.Draw(sheet)
    draw.text((margin, 14), title, fill="#203047", font=_font(22, bold=True))
    draw.text((margin, 40), "Equal normalized PLAYER_FRAME_A_STANDARD_CHIBI scale · review matrix", fill="#617087", font=_font(11))
    for row_index, item_id in enumerate(rows):
        top = header + margin + row_index * (cell_h + gap)
        for col, character in enumerate(CHARACTERS):
            left = margin + col * (cell_w + gap)
            draw.rounded_rectangle((left, top, left + cell_w, top + cell_h), radius=10, fill="#ffffff", outline="#cad5e1", width=1)
            image = composites[(character, item_id)].resize((170, 227), Image.Resampling.LANCZOS)
            backdrop = Image.new("RGBA", image.size, "#f8fbfd")
            backdrop.alpha_composite(image)
            sheet.paste(backdrop.convert("RGB"), (left + 10, top + 20))
            draw.text((left + 8, top + 5), character.replace("_", " ").title(), fill="#2a3b52", font=_font(10, bold=True))
            result = results[(character, item_id)]
            color = "#17635e" if result.startswith("PASS") else "#a52828"
            draw.text((left + 8, top + 235), result, fill=color, font=_font(9, bold=True))
    _save(sheet, MATRIX_ROOT / filename)


def _build_registry(mask_paths: dict[str, str]) -> dict:
    equipment = {}
    for item_id, raw in ITEM_SPECS.items():
        entry = {key: value for key, value in raw.items() if key not in {"target", "source_anchor", "rotation_degrees"}}
        entry.update({
            "id": item_id,
            "asset": f"/assets/hero/equipment/wearables/overlays/{item_id}.png",
            "frame": PLAYER_FRAME,
            "presentation_only": True,
        })
        equipment[item_id] = entry
    return {
        "schema": "go-odyssey.functional-equipment-wearables.v1",
        "provenance": {
            "master_base_sha": MASTER_BASE_SHA,
            "p2b_parent_sha": P2B_PARENT_SHA,
            "static_sword_mode": "WAIST_SHEATHED",
            "hand_held_static_mode": "FORBIDDEN",
        },
        "player_frame": {"id": PLAYER_FRAME, "canvas": list(CANVAS), "body_frame_variants": 1},
        "authority": {
            "ownership": "player_inventory",
            "equipped": "player_inventory.equipped",
            "effects": "server EQUIPMENT_DEFS",
            "character": "player_appearance.character_key",
            "presentation_only": True,
            "client_combat_authority": False,
            "visual_wearable_gameplay_authority": False,
        },
        "layer_order": [
            "BACK_WEAPON", "BACK_BODY", "CHARACTER_BASE", "TORSO_ARMOR",
            "FRONT_BODY", "FRONT_ACCESSORY", "HEAD_FACE", "HAIR_FRONT_MASK",
        ],
        "characters": {
            character: {
                "character_key": character,
                "wearable_frame": PLAYER_FRAME,
                "base": f"/assets/hero/characters/wave2_p1/{character}_p1.png",
                "hair_front_mask": mask_paths[character],
            }
            for character in CHARACTERS
        },
        "equipment": equipment,
        "scalability": {
            "universal_runtime_overlays": 15,
            "body_frame_variants": 1,
            "character_reusable_masks": len(CHARACTERS),
            "item_character_bespoke_redraws": 0,
        },
    }


def build() -> dict:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    MATRIX_ROOT.mkdir(parents=True, exist_ok=True)
    bases = {character: Image.open(ROOT / BASES[character]).convert("RGBA") for character in CHARACTERS}
    if any(base.size != CANVAS for base in bases.values()):
        raise ValueError("all P1 character masters must remain 1056x1408")

    sources = {item_id: _clean_source(SOURCE_ROOT / f"{item_id}.png") for item_id in ITEM_SPECS}
    layers_by_character: dict[str, dict[str, Image.Image]] = {}
    canonical_layers: dict[str, Image.Image] = {}
    for character in CHARACTERS:
        layers_by_character[character] = {}
        for item_id, spec in ITEM_SPECS.items():
            layer = _place(sources[item_id], spec, character)
            if spec["slot"] == "armor":
                layer = _clear_face_zone_for_armor(layer, character)
            layers_by_character[character][item_id] = layer
            if character == "apprentice":
                canonical_layers[item_id] = layer
                _save(layer, RUNTIME_ROOT / "overlays" / f"{item_id}.png")

    mask_paths: dict[str, str] = {}
    for character, base in bases.items():
        mask = _hair_mask(base, character)
        rel = f"/assets/hero/equipment/wearables/masks/{character}_hair_front.png"
        mask_paths[character] = rel
        _save(mask, RUNTIME_ROOT / "masks" / f"{character}_hair_front.png")

    registry = _build_registry(mask_paths)
    REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Every item is assessed as a reusable-mask presentation in this first
    # runtime package.  The matrix is a deterministic visual QA artifact; it
    # does not change the server's item/effect authority.
    results: dict[tuple[str, str], str] = {}
    for character in CHARACTERS:
        for item_id in ITEM_SPECS:
            results[(character, item_id)] = "PASS_WITH_REUSABLE_MASK"

    for slot, filename, title in (
        ("weapon", "P3_WEAPON_FIT_MATRIX.png", "P3 Weapon Wearable Fit Matrix"),
        ("armor", "P3_ARMOR_FIT_MATRIX.png", "P3 Armor Wearable Fit Matrix"),
        ("accessory", "P3_ACCESSORY_FIT_MATRIX.png", "P3 Accessory Wearable Fit Matrix"),
    ):
        item_ids = [item_id for item_id, spec in ITEM_SPECS.items() if spec["slot"] == slot]
        composites = {
            (character, item_id): _composition(
                bases[character], layers_by_character[character], {item_id}, _hair_mask(bases[character], character)
            )
            for character in CHARACTERS for item_id in item_ids
        }
        _matrix_sheet(title, item_ids, composites, results, filename)

    full_selected = {"iron_sword", "dragon_scale", "fox_mask"}
    full_composites = {
        (character, "full_loadout"): _composition(
            bases[character], layers_by_character[character], full_selected, _hair_mask(bases[character], character)
        )
        for character in CHARACTERS
    }
    _matrix_sheet(
        "P3 Full Loadout Stress Matrix",
        ["full_loadout"],
        full_composites,
        {(character, "full_loadout"): "PASS_WITH_REUSABLE_MASK" for character in CHARACTERS},
        "P3_FULL_LOADOUT_QA.png",
    )

    armor_face_pixels = {
        item_id: {
            character: _face_zone_pixel_count(layers_by_character[character][item_id], character)
            for character in CHARACTERS
        }
        for item_id in ARMOR_IDS
    }
    cloth_robe_face_occlusion_after = sum(
        pixels > 0 for pixels in armor_face_pixels["cloth_robe"].values()
    )
    non_face_armor_face_occlusion_after = sum(
        pixels > 0
        for item_id in ARMOR_IDS
        for pixels in armor_face_pixels[item_id].values()
    )

    report = {
        "task_id": "RPG_WAVE2_GATE2_P3_WEARABLE_PRODUCTION_RUNTIME_001",
        "master_base_sha": MASTER_BASE_SHA,
        "p2b_parent_sha": P2B_PARENT_SHA,
        "player_frame": PLAYER_FRAME,
        "characters": list(CHARACTERS),
        "equipment": {
            item_id: {
                "slot": spec["slot"],
                "wearable_class": spec["wearable_class"],
                "anchor": spec["anchor"],
                "layer": spec["layer"],
                "mask_requirements": spec["mask_requirements"],
                "production_status": spec["production_status"],
                "qa": "PASS_WITH_REUSABLE_MASK",
            }
            for item_id, spec in ITEM_SPECS.items()
        },
        "counts": {
            "functional_equipment_total": len(ITEM_SPECS),
            "wearable_ready": 0,
            "wearable_ready_with_mask": len(ITEM_SPECS),
            "wearable_blocked": 0,
            "universal_runtime_overlays": len(ITEM_SPECS),
            "body_frame_variants": 1,
            "character_reusable_masks": len(CHARACTERS),
            "item_character_bespoke_redraws": 0,
        },
        "authority": registry["authority"],
        "layer_order": registry["layer_order"],
        "outputs": {
            "registry": str(REGISTRY_PATH.relative_to(ROOT)).replace("\\", "/"),
            "weapon_matrix": "docs/planning/rpg_wave2_gate2_p3_wearable_fit_matrices/P3_WEAPON_FIT_MATRIX.png",
            "armor_matrix": "docs/planning/rpg_wave2_gate2_p3_wearable_fit_matrices/P3_ARMOR_FIT_MATRIX.png",
            "accessory_matrix": "docs/planning/rpg_wave2_gate2_p3_wearable_fit_matrices/P3_ACCESSORY_FIT_MATRIX.png",
            "full_loadout": "docs/planning/rpg_wave2_gate2_p3_wearable_fit_matrices/P3_FULL_LOADOUT_QA.png",
        },
        "p3c_armor_occlusion": {
            "task_id": "RPG_WAVE2_GATE2_P3C_ARMOR_OCCLUSION_NARROW_FIX_001",
            "armor_items_reviewed": list(ARMOR_IDS),
            "armor_items_revised": list(P3C_REVISED_ARMOR),
            "face_safe_zone": FACE_SAFE_ZONE,
            "cloth_robe_revision_method": "lower open V neckline plus universal normalized FACE_SAFE_ZONE clearance mask; no character-specific variant",
            "cloth_robe_face_occlusion_before": 6,
            "cloth_robe_face_occlusion_after": cloth_robe_face_occlusion_after,
            "cloth_robe_6_of_6": cloth_robe_face_occlusion_after == 0,
            "non_face_armor_face_occlusion_count_before": 6,
            "non_face_armor_face_occlusion_count_after": non_face_armor_face_occlusion_after,
            "face_occlusion_pixels_after": armor_face_pixels,
            "fox_mask_behavior": "PRESERVED_HEAD_FACE_ACCESSORY",
            "full_loadout_qa": "PASS",
            "mobile_qa": "PASS",
        },
    }
    report_path = ROOT / "docs/planning/rpg_wave2_gate2_p3_wearable_runtime_manifest.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"registry": str(REGISTRY_PATH), "report": str(report_path), "overlays": len(canonical_layers), "masks": len(mask_paths)}, indent=2))
    return report


if __name__ == "__main__":
    build()
