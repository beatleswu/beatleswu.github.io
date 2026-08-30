"""Build the A053 Paper Doll Lite main-hand static prototype.

This module is deliberately outside the live Hero renderer.  It provides a
small, data-driven composition model for review and deterministic tests:

    CHARACTER_ROOT -> RIGHT_ARM -> RIGHT_HAND -> GRIP_ANCHOR
                                      -> MAIN_HAND_WEAPON

The source character, grip layer, suppression mask, and weapon-only inputs
are existing review/planning assets.  The generated images are static review
evidence; no inventory, equip, combat, API, or feature-gate code is changed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "docs/planning/a053_r1_paper_doll_lite_main_hand"
REVIEW_ROOT = OUT_ROOT / "review"
WEAPON_ROOT = OUT_ROOT / "sources/weapon_only"
CONTRACT_PATH = OUT_ROOT / "paper_doll_lite_contract.json"

FRAME_ID = "PLAYER_FRAME_A_STANDARD_CHIBI"
CANVAS = (1056, 1408)

CHARACTER_BASE_PATH = ROOT / "assets/hero/characters/wave2_p1/apprentice_p1.png"
GRIP_LAYER_PATH = ROOT / (
    "docs/planning/rpg_wave2_modular_2d_handheld_sword_prototype/"
    "pose_layers/apprentice_grip_forearm.png"
)
SUPPRESSION_MASK_PATH = ROOT / (
    "docs/planning/rpg_wave2_modular_2d_handheld_sword_prototype/"
    "masks/apprentice_open_hand_suppression.png"
)

CANONICAL_MASTER_HEAD = "799dbf42919946319c5735975a83ecbc38b9d9a2"
R1D_SOURCE_HEAD = "691f47d3dc4654d2696127b43b0912f1a04be23e"

CHARACTER_KEY = "apprentice"
POSE_FAMILY = "ONE_HAND_SWORD"
IMPLEMENTED_SLOT = "MAIN_HAND"

# This is one semantic grip for the character.  The coordinates are derived
# from the existing reusable grip layer and the current PLAYER_FRAME canvas;
# they are not viewport-specific CSS positions.
GRIP_ANCHOR = (800.0, 800.0)
GRIP_ANCHOR_NORMALIZED = (GRIP_ANCHOR[0] / CANVAS[0], GRIP_ANCHOR[1] / CANVAS[1])
FRONT_GRIP_TARGET_HEIGHT = 240
FRONT_GRIP_ASSET_ANCHOR = (0.80, 0.58)


@dataclass(frozen=True)
class TransformNode:
    """A minimal local transform node used by the prototype and tests."""

    node_id: str
    parent: str | None
    x: float = 0.0
    y: float = 0.0
    rotation_deg: float = 0.0
    scale: float = 1.0


@dataclass(frozen=True)
class WorldTransform:
    x: float
    y: float
    rotation_deg: float
    scale: float


def _rotate_point(x: float, y: float, degrees: float) -> tuple[float, float]:
    radians = math.radians(degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return (x * cosine - y * sine, x * sine + y * cosine)


def _compose_transform(parent: WorldTransform, local: TransformNode) -> WorldTransform:
    local_position = _rotate_point(local.x * parent.scale, local.y * parent.scale, parent.rotation_deg)
    return WorldTransform(
        x=parent.x + local_position[0],
        y=parent.y + local_position[1],
        rotation_deg=parent.rotation_deg + local.rotation_deg,
        scale=parent.scale * local.scale,
    )


def resolve_world_transform(nodes: dict[str, TransformNode], node_id: str) -> WorldTransform:
    """Resolve a node through its parents without requiring an animation engine."""

    if node_id not in nodes:
        raise KeyError(f"unknown transform node: {node_id}")
    visiting: set[str] = set()

    def resolve(current_id: str) -> WorldTransform:
        if current_id in visiting:
            raise ValueError(f"transform cycle at {current_id}")
        visiting.add(current_id)
        current = nodes[current_id]
        if current.parent is None:
            result = WorldTransform(current.x, current.y, current.rotation_deg, current.scale)
        else:
            if current.parent not in nodes:
                raise KeyError(f"unknown parent: {current.parent}")
            result = _compose_transform(resolve(current.parent), current)
        visiting.remove(current_id)
        return result

    return resolve(node_id)


def transform_point(transform: WorldTransform, point: tuple[float, float]) -> tuple[float, float]:
    scaled = (point[0] * transform.scale, point[1] * transform.scale)
    rotated = _rotate_point(scaled[0], scaled[1], transform.rotation_deg)
    return (transform.x + rotated[0], transform.y + rotated[1])


def prototype_transform_nodes(*, right_hand_delta: tuple[float, float] = (0.0, 0.0), right_hand_rotation: float = 0.0) -> dict[str, TransformNode]:
    """Return the semantic hierarchy with optional proof-only hand motion."""

    return {
        "CHARACTER_ROOT": TransformNode("CHARACTER_ROOT", None),
        "BODY": TransformNode("BODY", "CHARACTER_ROOT"),
        "RIGHT_ARM": TransformNode("RIGHT_ARM", "BODY"),
        "RIGHT_HAND": TransformNode(
            "RIGHT_HAND",
            "RIGHT_ARM",
            x=GRIP_ANCHOR[0] + right_hand_delta[0],
            y=GRIP_ANCHOR[1] + right_hand_delta[1],
            rotation_deg=right_hand_rotation,
        ),
        # The grip anchor is the hand pivot.  The weapon node's local origin
        # is the weapon-specific grip point, so the child follows the pivot.
        "GRIP_ANCHOR": TransformNode("GRIP_ANCHOR", "RIGHT_HAND"),
        "MAIN_HAND_WEAPON": TransformNode("MAIN_HAND_WEAPON", "GRIP_ANCHOR"),
        "FRONT_GRIP_HAND": TransformNode("FRONT_GRIP_HAND", "RIGHT_HAND"),
    }


def resolve_presentation(equipped_item_id: str | None) -> dict[str, str | None]:
    """Resolve only a presentation result from authoritative equipped state.

    `equipped_item_id` represents the server-owned equipped item.  Ownership,
    purchase, legality, and combat effects are intentionally not inputs here.
    """

    if equipped_item_id in WEAPON_SPECS:
        return {"pose_family": POSE_FAMILY, "weapon_id": equipped_item_id}
    return {"pose_family": "DEFAULT_POSE", "weapon_id": None}


WEAPON_SPECS: dict[str, dict[str, object]] = {
    "wooden_sword": {
        "slot": IMPLEMENTED_SLOT,
        "pose_family": POSE_FAMILY,
        "asset": WEAPON_ROOT / "wooden_sword.png",
        "source_asset": "assets/hero/equipment/wearables/overlays/wooden_sword.png",
        "source_head": R1D_SOURCE_HEAD,
        "source_worktree": "codex/a052-r1d-r1-frame-clipping-remediation",
        "grip_point": (0.78, 0.18),
        "rotation_deg": -8.0,
        "scale": 0.48,
    },
    "iron_sword": {
        "slot": IMPLEMENTED_SLOT,
        "pose_family": POSE_FAMILY,
        "asset": WEAPON_ROOT / "iron_sword.png",
        "source_asset": "assets/hero/equipment/wearables/overlays/iron_sword.png",
        "source_head": R1D_SOURCE_HEAD,
        "source_worktree": "codex/a052-r1d-r1-frame-clipping-remediation",
        "grip_point": (0.75, 0.14),
        "rotation_deg": -8.0,
        "scale": 0.36,
    },
    "fox_fang": {
        "slot": IMPLEMENTED_SLOT,
        "pose_family": POSE_FAMILY,
        "asset": WEAPON_ROOT / "fox_fang.png",
        "source_asset": "assets/hero/equipment/wearables/overlays/fox_fang.png",
        "source_head": R1D_SOURCE_HEAD,
        "source_worktree": "codex/a052-r1d-r1-frame-clipping-remediation",
        "grip_point": (0.72, 0.15),
        "rotation_deg": -8.0,
        "scale": 0.48,
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _font(size: int, *, bold: bool = False):
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _normalize_rgba(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            if pixels[x, y][3] == 0:
                pixels[x, y] = (0, 0, 0, 0)
    return rgba


def _load_rgba(path: Path) -> Image.Image:
    if not path.is_file():
        raise FileNotFoundError(path)
    return _normalize_rgba(Image.open(path))


def _suppress_open_hand(base: Image.Image) -> Image.Image:
    mask = Image.open(SUPPRESSION_MASK_PATH).convert("L")
    inverse = ImageOps.invert(mask)
    alpha = ImageChops.multiply(base.getchannel("A"), inverse)
    output = base.copy()
    output.putalpha(alpha)
    return _normalize_rgba(output)


def _front_grip_layer() -> Image.Image:
    source = _load_rgba(GRIP_LAYER_PATH)
    target_height = FRONT_GRIP_TARGET_HEIGHT
    target_width = round(source.width * target_height / source.height)
    resized = source.resize((target_width, target_height), Image.Resampling.LANCZOS)
    left = round(GRIP_ANCHOR[0] - FRONT_GRIP_ASSET_ANCHOR[0] * target_width)
    top = round(GRIP_ANCHOR[1] - FRONT_GRIP_ASSET_ANCHOR[1] * target_height)
    layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    layer.alpha_composite(resized, (left, top))
    return _normalize_rgba(layer)


def _rotate_with_tracked_point(image: Image.Image, point: tuple[float, float], degrees: float) -> tuple[Image.Image, tuple[float, float]]:
    marker = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(marker)
    x, y = point
    draw.ellipse((round(x) - 3, round(y) - 3, round(x) + 3, round(y) + 3), fill=255)
    rotated = image.rotate(degrees, expand=True, resample=Image.Resampling.BICUBIC)
    rotated_marker = marker.rotate(degrees, expand=True, resample=Image.Resampling.BICUBIC)
    bbox = rotated_marker.getbbox()
    if bbox is None:
        raise ValueError("weapon grip point was lost during rotation")
    tracked = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
    return rotated, tracked


def weapon_layer_and_grip(weapon_id: str) -> tuple[Image.Image, tuple[float, float]]:
    if weapon_id not in WEAPON_SPECS:
        raise KeyError(weapon_id)
    spec = WEAPON_SPECS[weapon_id]
    source = _load_rgba(spec["asset"])
    scale = float(spec["scale"])
    resized = source.resize((round(source.width * scale), round(source.height * scale)), Image.Resampling.LANCZOS)
    grip_ratio = spec["grip_point"]
    grip_point = (float(grip_ratio[0]) * resized.width, float(grip_ratio[1]) * resized.height)
    rotated, tracked = _rotate_with_tracked_point(resized, grip_point, float(spec["rotation_deg"]))
    left = round(GRIP_ANCHOR[0] - tracked[0])
    top = round(GRIP_ANCHOR[1] - tracked[1])
    layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    layer.alpha_composite(rotated, (left, top))
    # The visible frame is part of the contract.  A weapon that cannot fit
    # is not silently cropped by the prototype.
    bbox = layer.getchannel("A").getbbox()
    if bbox is None or bbox[0] < 0 or bbox[1] < 0 or bbox[2] > CANVAS[0] or bbox[3] > CANVAS[1]:
        raise ValueError(f"{weapon_id} does not fit the PLAYER_FRAME canvas: {bbox}")
    return _normalize_rgba(layer), (GRIP_ANCHOR[0], GRIP_ANCHOR[1])


def compose_layers(equipped_item_id: str | None) -> dict[str, Image.Image]:
    presentation = resolve_presentation(equipped_item_id)
    if presentation["weapon_id"] is None:
        return {"CHARACTER_BASE": _load_rgba(CHARACTER_BASE_PATH)}
    weapon_id = str(presentation["weapon_id"])
    return {
        "CHARACTER_BASE": _suppress_open_hand(_load_rgba(CHARACTER_BASE_PATH)),
        "MAIN_HAND_WEAPON": weapon_layer_and_grip(weapon_id)[0],
        "FRONT_GRIP_HAND": _front_grip_layer(),
    }


def compose(equipped_item_id: str | None) -> Image.Image:
    layers = compose_layers(equipped_item_id)
    output = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    for layer_id in ("CHARACTER_BASE", "MAIN_HAND_WEAPON", "FRONT_GRIP_HAND"):
        if layer_id in layers:
            output = Image.alpha_composite(output, layers[layer_id])
    return _normalize_rgba(output)


def _flatten(image: Image.Image, background: tuple[int, int, int] = (248, 246, 241)) -> Image.Image:
    backdrop = Image.new("RGBA", image.size, background + (255,))
    return Image.alpha_composite(backdrop, image).convert("RGB")


def _save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def _full_view(image: Image.Image, title: str, subtitle: str) -> Image.Image:
    width, height = 650, 930
    canvas = Image.new("RGB", (width, height), (239, 243, 247))
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 18), title, fill=(28, 47, 70), font=_font(25, bold=True))
    draw.text((24, 53), subtitle, fill=(87, 105, 125), font=_font(14))
    frame = _flatten(image)
    frame.thumbnail((600, 800), Image.Resampling.LANCZOS)
    left = (width - frame.width) // 2
    top = 100 + (800 - frame.height) // 2
    canvas.paste(frame, (left, top))
    draw.rectangle((24, 100, width - 24, 900), outline=(190, 202, 214), width=2)
    draw.text((24, 905), "STATIC PROTOTYPE · Owner review pending · runtime inactive", fill=(112, 78, 34), font=_font(12, bold=True))
    return canvas


def _grip_crop(image: Image.Image, title: str) -> Image.Image:
    crop_box = (610, 570, 970, 1030)
    crop = _flatten(image.crop(crop_box), (250, 250, 250))
    canvas = Image.new("RGB", (760, 850), (239, 243, 247))
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 18), title, fill=(28, 47, 70), font=_font(23, bold=True))
    draw.text((24, 53), "enlarged hand / handle region · frame-relative composition", fill=(87, 105, 125), font=_font(13))
    crop = crop.resize((680, 690), Image.Resampling.LANCZOS)
    canvas.paste(crop, (40, 100))
    draw.rectangle((40, 100, 720, 790), outline=(190, 202, 214), width=2)
    draw.text((40, 805), "GRIP_ANCHOR = (800, 800) in PLAYER_FRAME_A_STANDARD_CHIBI", fill=(30, 99, 92), font=_font(12, bold=True))
    return canvas


def _layer_panel(image: Image.Image, title: str, subtitle: str) -> Image.Image:
    canvas = Image.new("RGB", (250, 370), (239, 243, 247))
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 8), title, fill=(28, 47, 70), font=_font(15, bold=True))
    draw.text((10, 30), subtitle, fill=(87, 105, 125), font=_font(10))
    frame = _flatten(image)
    frame.thumbnail((220, 294), Image.Resampling.LANCZOS)
    canvas.paste(frame, ((250 - frame.width) // 2, 58))
    draw.rectangle((14, 58, 236, 352), outline=(190, 202, 214), width=1)
    return canvas


def _exploded_view(layers: dict[str, Image.Image], final: Image.Image) -> Image.Image:
    canvas = Image.new("RGB", (1030, 420), (231, 237, 243))
    draw = ImageDraw.Draw(canvas)
    draw.text((18, 12), "A053 Paper Doll Lite · semantic layer composition", fill=(28, 47, 70), font=_font(25, bold=True))
    draw.text((18, 46), "same local PLAYER_FRAME · base + weapon + reusable grip hand = final", fill=(87, 105, 125), font=_font(13))
    panels = [
        _layer_panel(layers["CHARACTER_BASE"], "L10 CHARACTER_BASE", "localized hand suppression"),
        _layer_panel(layers["MAIN_HAND_WEAPON"], "L20 MAIN_HAND_WEAPON", "child of GRIP_ANCHOR"),
        _layer_panel(layers["FRONT_GRIP_HAND"], "L30 FRONT_GRIP_HAND", "shared apprentice layer"),
        _layer_panel(final, "COMPOSITED RESULT", "review-only output"),
    ]
    for index, panel in enumerate(panels):
        canvas.paste(panel, (18 + index * 254, 82))
        if index < len(panels) - 1:
            draw.text((246 + index * 254, 230), "+" if index < 2 else "=", fill=(30, 99, 92), font=_font(28, bold=True))
    return canvas


def _responsive_view(image: Image.Image) -> Image.Image:
    canvas = Image.new("RGB", (980, 620), (231, 237, 243))
    draw = ImageDraw.Draw(canvas)
    draw.text((22, 16), "Unit-scaled responsive contract", fill=(28, 47, 70), font=_font(25, bold=True))
    draw.text((22, 50), "one shared local frame; body, hand and weapon scale together", fill=(87, 105, 125), font=_font(13))
    widths = (300, 230, 170)
    labels = ("DESKTOP", "IPAD / TABLET", "IPHONE / MOBILE")
    x = 22
    for width, label in zip(widths, labels):
        frame_height = round(width * CANVAS[1] / CANVAS[0])
        frame = _flatten(image).resize((width, frame_height), Image.Resampling.LANCZOS)
        draw.text((x, 88), label, fill=(30, 99, 92), font=_font(13, bold=True))
        canvas.paste(frame, (x, 115))
        draw.rectangle((x, 115, x + width, 115 + frame_height), outline=(190, 202, 214), width=2)
        x += width + 95
    return canvas


def _motion_diagram() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1050" height="620" viewBox="0 0 1050 620">
  <rect width="1050" height="620" fill="#eef3f7"/>
  <text x="32" y="44" font-family="Segoe UI,Arial,sans-serif" font-size="28" font-weight="700" fill="#1c2f46">A053 Motion-ready transform proof</text>
  <text x="32" y="76" font-family="Segoe UI,Arial,sans-serif" font-size="16" fill="#57697d">Static data model only · no animation implemented · children inherit parent transforms</text>
  <g font-family="Segoe UI,Arial,sans-serif" font-size="18" text-anchor="middle">
    <rect x="370" y="106" width="310" height="54" rx="12" fill="#203047"/>
    <text x="525" y="140" fill="#fff">CHARACTER_ROOT</text>
    <line x1="525" y1="160" x2="525" y2="195" stroke="#2f6f68" stroke-width="4" marker-end="url(#arrow)"/>
    <rect x="400" y="198" width="250" height="54" rx="12" fill="#55738e"/>
    <text x="525" y="232" fill="#fff">RIGHT_ARM</text>
    <line x1="525" y1="252" x2="525" y2="287" stroke="#2f6f68" stroke-width="4" marker-end="url(#arrow)"/>
    <rect x="400" y="290" width="250" height="54" rx="12" fill="#55738e"/>
    <text x="525" y="324" fill="#fff">RIGHT_HAND</text>
    <line x1="525" y1="344" x2="525" y2="379" stroke="#2f6f68" stroke-width="4" marker-end="url(#arrow)"/>
    <rect x="365" y="382" width="320" height="54" rx="12" fill="#2f8b7d"/>
    <text x="525" y="416" fill="#fff">GRIP_ANCHOR (shared)</text>
    <line x1="525" y1="436" x2="525" y2="471" stroke="#2f6f68" stroke-width="4" marker-end="url(#arrow)"/>
    <rect x="350" y="474" width="350" height="54" rx="12" fill="#b87837"/>
    <text x="525" y="508" fill="#fff">MAIN_HAND_WEAPON</text>
  </g>
  <g font-family="Segoe UI,Arial,sans-serif" font-size="16" fill="#203047">
    <rect x="742" y="178" width="260" height="168" rx="14" fill="#fff" stroke="#c4d0dc" stroke-width="2"/>
    <text x="764" y="211" font-weight="700">PARENT TRANSFORM</text>
    <text x="764" y="244">RIGHT_HAND Δx / Δy</text>
    <text x="764" y="273">→ GRIP_ANCHOR follows</text>
    <text x="764" y="302">→ weapon follows</text>
    <text x="764" y="331">local grip stays aligned</text>
    <rect x="45" y="178" width="260" height="168" rx="14" fill="#fff" stroke="#c4d0dc" stroke-width="2"/>
    <text x="67" y="211" font-weight="700">LOCAL CHILD TRANSFORM</text>
    <text x="67" y="244">weapon grip point</text>
    <text x="67" y="273">rotation / scale</text>
    <text x="67" y="302">relative to anchor</text>
    <text x="67" y="331">data-driven, not viewport CSS</text>
  </g>
  <defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#2f6f68"/></marker></defs>
</svg>
"""


def _source_record(path: Path, *, role: str, provenance: dict[str, object] | None = None) -> dict[str, object]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        return {
            "role": role,
            "path": _relative(path),
            "sha256": _sha256(path),
            "dimensions": [image.width, image.height],
            "color_mode": image.mode,
            "alpha_present": alpha.getbbox() is not None,
            "alpha_bbox": list(alpha.getbbox()) if alpha.getbbox() else None,
            "provenance": provenance or {},
        }


def _contract() -> dict[str, object]:
    nodes = [
        {"node_id": "CHARACTER_ROOT", "parent": None, "transform_fields": ["x", "y", "rotation_deg", "scale"]},
        {"node_id": "BODY", "parent": "CHARACTER_ROOT", "transform_fields": ["x", "y", "rotation_deg", "scale"]},
        {"node_id": "RIGHT_ARM", "parent": "BODY", "transform_fields": ["x", "y", "rotation_deg", "scale"]},
        {"node_id": "RIGHT_HAND", "parent": "RIGHT_ARM", "transform_fields": ["x", "y", "rotation_deg", "scale"]},
        {"node_id": "GRIP_ANCHOR", "parent": "RIGHT_HAND", "transform_fields": ["x", "y", "rotation_deg", "scale"]},
        {"node_id": "MAIN_HAND_WEAPON", "parent": "GRIP_ANCHOR", "transform_fields": ["x", "y", "rotation_deg", "scale"]},
        {"node_id": "FRONT_GRIP_HAND", "parent": "RIGHT_HAND", "transform_fields": ["x", "y", "rotation_deg", "scale"]},
    ]
    weapons: dict[str, object] = {}
    for weapon_id, spec in WEAPON_SPECS.items():
        asset = spec["asset"]
        weapons[weapon_id] = {
            "slot": spec["slot"],
            "pose_family": spec["pose_family"],
            "asset": _relative(asset),
            "asset_sha256": _sha256(asset),
            "weapon_only": True,
            "baked_character_pixels": False,
            "grip_point_normalized": list(spec["grip_point"]),
            "rotation_deg": spec["rotation_deg"],
            "scale": spec["scale"],
            "source_provenance": {
                "reference_asset": spec["source_asset"],
                "reference_sha256": _sha256(ROOT / spec["source_asset"]),
                "source_head": spec["source_head"],
                "source_worktree": spec["source_worktree"],
                "copy_into_prototype": "BYTE_PRESERVING",
            },
        }
    proof_before = resolve_world_transform(prototype_transform_nodes(), "MAIN_HAND_WEAPON")
    proof_after_translation = resolve_world_transform(
        prototype_transform_nodes(right_hand_delta=(17.0, -11.0)), "MAIN_HAND_WEAPON"
    )
    proof_before_rotation = resolve_world_transform(prototype_transform_nodes(), "MAIN_HAND_WEAPON")
    proof_after_rotation = resolve_world_transform(
        prototype_transform_nodes(right_hand_rotation=25.0), "MAIN_HAND_WEAPON"
    )
    return {
        "$schema": "go-odyssey.paper-doll-lite-prototype.v1",
        "task_id": "A053_R1_PAPER_DOLL_LITE_MOTION_READY_MAIN_HAND_VERTICAL_SLICE_001",
        "status": "STATIC_PROTOTYPE_PENDING_OWNER_VISUAL_REVIEW",
        "runtime_active": False,
        "owner_visual_acceptance": "NOT_GRANTED",
        "canonical_master_reference": CANONICAL_MASTER_HEAD,
        "authority": {
            "equipment_ownership": "server-owned player_inventory",
            "equipped_state": "server-owned player_inventory.equipped + canonical_slot",
            "equipment_effects": "server-owned EQUIPMENT_DEFS",
            "presentation": "PRESENTATION_ONLY",
            "client_equipment_authority": False,
            "acquire_does_not_equip": True,
            "purchase_does_not_equip": True,
            "no_client_combat_authority": True,
            "combat_damage_unchanged": {"baseline": 80, "wooden_sword": 84, "iron_sword": 90},
            "xp_amulet_new_equip": False,
            "xp_amulet_legacy_unequip": True,
            "go_stone_black_combat_power": 0,
        },
        "frame": {
            "id": FRAME_ID,
            "width": CANVAS[0],
            "height": CANVAS[1],
            "coordinate_space": "single_shared_local_frame",
            "responsive_rule": "scale_composition_as_unit",
        },
        "implemented_slots": [IMPLEMENTED_SLOT],
        "future_slots_documented_only": ["OFF_HAND", "HEAD", "BODY", "FEET"],
        "character": {
            "character_id": CHARACTER_KEY,
            "pose_family": POSE_FAMILY,
            "character_identity_preserved": True,
            "default_pose_asset": _relative(CHARACTER_BASE_PATH),
            "current_hand_region_source": _relative(GRIP_LAYER_PATH),
            "hand_suppression_mask": _relative(SUPPRESSION_MASK_PATH),
            "grip_anchor": {
                "node": "GRIP_ANCHOR",
                "parent": "RIGHT_HAND",
                "coordinate_space": f"{FRAME_ID}_PIXELS",
                "x": GRIP_ANCHOR[0],
                "y": GRIP_ANCHOR[1],
                "normalized": list(GRIP_ANCHOR_NORMALIZED),
                "one_character_pose_one_grip_anchor": True,
            },
            "front_grip_hand": {
                "asset": _relative(GRIP_LAYER_PATH),
                "asset_anchor_normalized": list(FRONT_GRIP_ASSET_ANCHOR),
                "target_height": FRONT_GRIP_TARGET_HEIGHT,
                "parent": "RIGHT_HAND",
                "semantic_role": "FRONT_GRIP_HAND_WITH_LOCAL_CUFF",
            },
        },
        "transform_hierarchy": nodes,
        "layers": [
            {
                "order": 10,
                "layer_id": "CHARACTER_BASE",
                "parent": "BODY",
                "asset": _relative(CHARACTER_BASE_PATH),
                "mask": _relative(SUPPRESSION_MASK_PATH),
                "mask_semantics": "localized open-hand suppression only when supported weapon is equipped",
            },
            {
                "order": 20,
                "layer_id": "MAIN_HAND_WEAPON",
                "parent": "GRIP_ANCHOR",
                "local_origin": "weapon grip point",
            },
            {
                "order": 30,
                "layer_id": "FRONT_GRIP_HAND",
                "parent": "RIGHT_HAND",
                "asset": _relative(GRIP_LAYER_PATH),
                "semantic_role": "shared apprentice grip/forearm layer",
            },
        ],
        "weapons": weapons,
        "fallbacks": {
            "no_weapon_equipped": "DEFAULT_POSE_NO_WEAPON_OVERLAY",
            "owned_but_not_equipped": "DEFAULT_POSE_NO_WEAPON_OVERLAY",
            "unknown_equipment": "DEFAULT_POSE_KEEP_AUTHORITATIVE_EQUIPMENT",
            "unsupported_visual": "DEFAULT_POSE_KEEP_AUTHORITATIVE_EQUIPMENT",
            "missing_asset": "DEFAULT_POSE_KEEP_AUTHORITATIVE_EQUIPMENT",
        },
        "motion_proof": {
            "translation": {
                "right_hand_delta": [17.0, -11.0],
                "before_weapon_origin": [proof_before.x, proof_before.y],
                "after_weapon_origin": [proof_after_translation.x, proof_after_translation.y],
                "preserved_delta": [proof_after_translation.x - proof_before.x, proof_after_translation.y - proof_before.y],
            },
            "rotation": {
                "right_hand_rotation_deg": 25.0,
                "before_weapon_rotation_deg": proof_before_rotation.rotation_deg,
                "after_weapon_rotation_deg": proof_after_rotation.rotation_deg,
                "preserved_local_relationship": True,
            },
        },
        "review_outputs": {
            "view_a_default_no_weapon": _relative(REVIEW_ROOT / "view_a_default_no_weapon.png"),
            "view_b_wooden_sword": _relative(REVIEW_ROOT / "view_b_wooden_sword.png"),
            "view_c_iron_sword": _relative(REVIEW_ROOT / "view_c_iron_sword.png"),
            "view_d_fox_fang": _relative(REVIEW_ROOT / "view_d_fox_fang.png"),
            "wooden_grip_crop": _relative(REVIEW_ROOT / "wooden_sword_hand_grip_crop.png"),
            "iron_grip_crop": _relative(REVIEW_ROOT / "iron_sword_hand_grip_crop.png"),
            "fox_grip_crop": _relative(REVIEW_ROOT / "fox_fang_hand_grip_crop.png"),
            "exploded_layers": _relative(REVIEW_ROOT / "exploded_layer_view.png"),
            "responsive_proof": _relative(REVIEW_ROOT / "responsive_scaling_proof.png"),
            "motion_diagram": _relative(REVIEW_ROOT / "motion_ready_transform_diagram.svg"),
            "owner_review_html": _relative(REVIEW_ROOT / "index.html"),
        },
        "scope": {
            "full_character_per_weapon_assets_created": 0,
            "grip_hand_per_weapon_assets_created": 0,
            "shared_character_grip_structure": True,
            "animation_implemented": False,
            "app_py_changed": False,
            "runtime_renderer_changed": False,
            "registry_changed": False,
            "schema_changed": False,
            "data_changed": False,
        },
    }


def _review_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>A053 Paper Doll Lite V1 · apprentice MAIN_HAND</title>
  <style>
    :root { color-scheme: light; font-family: Segoe UI, Arial, sans-serif; color: #203047; background: #eef3f7; }
    body { margin: 0; padding: 18px; }
    main { max-width: 1080px; margin: 0 auto; }
    .notice { background: #fff8df; border: 1px solid #dec67d; border-radius: 12px; padding: 14px 16px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }
    figure { margin: 0; background: white; border: 1px solid #c5d1dd; border-radius: 12px; padding: 10px; }
    figure img { display: block; width: 100%; height: auto; }
    figcaption { padding: 8px 2px 2px; font-weight: 700; }
    .wide img { max-width: 100%; }
    code { background: #f1f4f7; padding: 1px 4px; border-radius: 4px; }
    @media (max-width: 520px) { body { padding: 8px; } h1 { font-size: 22px; } }
  </style>
</head>
<body><main>
  <h1>A053 Paper Doll Lite V1 · apprentice / MAIN_HAND</h1>
  <p class="notice"><strong>STATIC PROTOTYPE · PENDING OWNER VISUAL REVIEW</strong><br>
  This pack is not live Hero runtime wiring. It composes the existing apprentice character with a reusable grip-hand layer and one weapon-only child selected from server-owned <code>player_inventory.equipped</code>. Loadout remains OFF; no app.py, registry, API, schema, data, or combat source was changed.</p>
  <h2>Primary compositions</h2>
  <div class="grid">
    <figure><img src="view_a_default_no_weapon.png" alt="apprentice default pose without weapon"><figcaption>VIEW A · Default Pose / no weapon</figcaption></figure>
    <figure><img src="view_b_wooden_sword.png" alt="apprentice holding wooden sword"><figcaption>VIEW B · MAIN_HAND / wooden_sword</figcaption></figure>
    <figure><img src="view_c_iron_sword.png" alt="apprentice holding iron sword"><figcaption>VIEW C · MAIN_HAND / iron_sword</figcaption></figure>
    <figure><img src="view_d_fox_fang.png" alt="apprentice holding fox fang"><figcaption>VIEW D · MAIN_HAND / fox_fang</figcaption></figure>
  </div>
  <h2>Grip inspection</h2>
  <div class="grid">
    <figure><img src="wooden_sword_hand_grip_crop.png" alt="wooden sword hand grip crop"><figcaption>wooden_sword · enlarged grip</figcaption></figure>
    <figure><img src="iron_sword_hand_grip_crop.png" alt="iron sword hand grip crop"><figcaption>iron_sword · enlarged grip</figcaption></figure>
    <figure><img src="fox_fang_hand_grip_crop.png" alt="fox fang hand grip crop"><figcaption>fox_fang · enlarged grip</figcaption></figure>
  </div>
  <h2>Composition and motion-ready contract</h2>
  <figure class="wide"><img src="exploded_layer_view.png" alt="exploded paper doll layers"><figcaption>CHARACTER_BASE + MAIN_HAND_WEAPON + FRONT_GRIP_HAND = composed character</figcaption></figure>
  <figure class="wide"><img src="responsive_scaling_proof.png" alt="unit-scaled responsive paper doll proof"><figcaption>One shared local frame · unit scaling only</figcaption></figure>
  <figure class="wide"><img src="motion_ready_transform_diagram.svg" alt="motion-ready transform hierarchy"><figcaption>Transform hierarchy proof; animation is not implemented</figcaption></figure>
  <p>Contract: <a href="../paper_doll_lite_contract.json">paper_doll_lite_contract.json</a></p>
</main></body></html>
"""


def build() -> dict[str, object]:
    required = [CHARACTER_BASE_PATH, GRIP_LAYER_PATH, SUPPRESSION_MASK_PATH]
    required.extend(spec["asset"] for spec in WEAPON_SPECS.values())
    for path in required:
        if not Path(path).is_file():
            raise FileNotFoundError(path)

    default = compose(None)
    _save(_full_view(default, "VIEW A · apprentice", "DEFAULT_POSE · no weapon equipped"), REVIEW_ROOT / "view_a_default_no_weapon.png")

    composites: dict[str, Image.Image] = {}
    for weapon_id in WEAPON_SPECS:
        final = compose(weapon_id)
        composites[weapon_id] = final
        title = f"VIEW {'B' if weapon_id == 'wooden_sword' else 'C' if weapon_id == 'iron_sword' else 'D'} · apprentice"
        view_filename = {
            "wooden_sword": "view_b_wooden_sword.png",
            "iron_sword": "view_c_iron_sword.png",
            "fox_fang": "view_d_fox_fang.png",
        }[weapon_id]
        _save(_full_view(final, title, f"MAIN_HAND · {weapon_id} · authoritative equipped-state prototype"), REVIEW_ROOT / view_filename)
        _save(_grip_crop(final, f"{weapon_id} · grip inspection"), REVIEW_ROOT / f"{weapon_id}_hand_grip_crop.png")

    layers = compose_layers("wooden_sword")
    _save(_exploded_view(layers, composites["wooden_sword"]), REVIEW_ROOT / "exploded_layer_view.png")
    _save(_responsive_view(composites["wooden_sword"]), REVIEW_ROOT / "responsive_scaling_proof.png")
    (REVIEW_ROOT / "motion_ready_transform_diagram.svg").write_text(_motion_diagram(), encoding="utf-8", newline="\n")
    (REVIEW_ROOT / "index.html").write_text(_review_html(), encoding="utf-8", newline="\n")

    contract = _contract()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    CONTRACT_PATH.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return contract


if __name__ == "__main__":
    report = build()
    print(json.dumps({
        "task_id": report["task_id"],
        "contract": _relative(CONTRACT_PATH),
        "review": _relative(REVIEW_ROOT / "index.html"),
        "weapons": list(WEAPON_SPECS),
    }, ensure_ascii=False, indent=2))
