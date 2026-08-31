"""Build the A053-R3 apprentice true-handle-grip review pack.

R3 is a localized visual refinement of the A053-R2 Paper Doll prototype.
The new hand/forearm layer is independent from the wooden sword, while the
existing three-layer composition and server-owned presentation contract stay
unchanged.  This module is static review tooling only; it does not wire Hero,
modify app.py, or change equipment authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import shutil
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "docs/planning/a053_r3_true_handle_grip_anatomy"
ASSET_ROOT = OUT_ROOT / "assets"
MASK_ROOT = OUT_ROOT / "masks"
REVIEW_ROOT = OUT_ROOT / "review"
CONTRACT_PATH = OUT_ROOT / "a053_r3_contract.json"

R2_REVIEW_ROOT = ROOT / "docs/planning/a053_r2_grip_hand_forearm_integration/review"
CHARACTER_BASE_PATH = ROOT / "assets/hero/characters/wave2_p1/apprentice_p1.png"
R2_GRIP_LAYER_PATH = ROOT / "docs/planning/a053_r2_grip_hand_forearm_integration/assets/apprentice_grip_forearm_r2.png"
R2_MASK_PATH = ROOT / "docs/planning/a053_r2_grip_hand_forearm_integration/masks/apprentice_open_hand_suppression_r2.png"
R3_GRIP_LAYER_PATH = ASSET_ROOT / "apprentice_grip_forearm_r3.png"
R3_MASK_PATH = MASK_ROOT / "apprentice_open_hand_suppression_r3.png"
WEAPON_ROOT = ROOT / "docs/planning/a053_r1_paper_doll_lite_main_hand/sources/weapon_only"

CANVAS = (1056, 1408)
FRAME_ID = "PLAYER_FRAME_A_STANDARD_CHIBI"
CHARACTER_KEY = "apprentice"
POSE_FAMILY = "ONE_HAND_SWORD"
IMPLEMENTED_SLOT = "MAIN_HAND"

R2_HEAD = "8650b23ee98ae896f44a4dd9544bcd222a999df7"
R2_TREE = "3716516d789c58162ab94bb996fa8ff6c9a44014"
FRESH_MASTER_HEAD = "f19f57f6c80fc7f3ba9c33817395c06284c879d1"
FRESH_MASTER_TREE = "aa5f3192c4c5e382dd87f990b39c5e3e789b06b1"

# The character anchor and weapon transform are deliberately unchanged from
# R2.  R3 corrects the local grip anatomy rather than solving the visual
# problem with another screen-space or weapon-specific anchor.
GRIP_ANCHOR = (760.0, 800.0)
GRIP_ANCHOR_NORMALIZED = (GRIP_ANCHOR[0] / CANVAS[0], GRIP_ANCHOR[1] / CANVAS[1])
R3_PATCH_POSITION = (610, 570)
R3_PATCH_SIZE = (340, 380)
R3_ROTATION = -8.0


WEAPON_SPECS: dict[str, dict[str, Any]] = {
    "wooden_sword": {
        "asset": WEAPON_ROOT / "wooden_sword.png",
        "source_asset": "assets/hero/equipment/wearables/overlays/wooden_sword.png",
        "grip_point": (0.78, 0.18),
        "rotation_deg": R3_ROTATION,
        "scale": 0.48,
    },
    "iron_sword": {
        "asset": WEAPON_ROOT / "iron_sword.png",
        "source_asset": "assets/hero/equipment/wearables/overlays/iron_sword.png",
        "grip_point": (0.75, 0.14),
        "rotation_deg": R3_ROTATION,
        "scale": 0.36,
    },
    "fox_fang": {
        "asset": WEAPON_ROOT / "fox_fang.png",
        "source_asset": "assets/hero/equipment/wearables/overlays/fox_fang.png",
        "grip_point": (0.72, 0.15),
        "rotation_deg": R3_ROTATION,
        "scale": 0.48,
    },
}


@dataclass(frozen=True)
class TransformNode:
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


def _rgba(path: Path) -> Image.Image:
    if not path.is_file():
        raise FileNotFoundError(path)
    image = Image.open(path).convert("RGBA")
    if image.getchannel("A").getbbox() is None:
        raise ValueError(f"transparent image has no visible pixels: {path}")
    return image


def _rotate_point(x: float, y: float, degrees: float) -> tuple[float, float]:
    radians = math.radians(degrees)
    return (x * math.cos(radians) - y * math.sin(radians), x * math.sin(radians) + y * math.cos(radians))


def _compose_transform(parent: WorldTransform, local: TransformNode) -> WorldTransform:
    local_position = _rotate_point(local.x * parent.scale, local.y * parent.scale, parent.rotation_deg)
    return WorldTransform(
        parent.x + local_position[0],
        parent.y + local_position[1],
        parent.rotation_deg + local.rotation_deg,
        parent.scale * local.scale,
    )


def resolve_world_transform(nodes: dict[str, TransformNode], node_id: str) -> WorldTransform:
    if node_id not in nodes:
        raise KeyError(node_id)
    visiting: set[str] = set()

    def resolve(current: str) -> WorldTransform:
        if current in visiting:
            raise ValueError(f"transform cycle at {current}")
        visiting.add(current)
        node = nodes[current]
        if node.parent is None:
            result = WorldTransform(node.x, node.y, node.rotation_deg, node.scale)
        else:
            result = _compose_transform(resolve(node.parent), node)
        visiting.remove(current)
        return result

    return resolve(node_id)


def transform_point(transform: WorldTransform, point: tuple[float, float]) -> tuple[float, float]:
    scaled = (point[0] * transform.scale, point[1] * transform.scale)
    rotated = _rotate_point(scaled[0], scaled[1], transform.rotation_deg)
    return (transform.x + rotated[0], transform.y + rotated[1])


def prototype_transform_nodes(*, right_hand_delta: tuple[float, float] = (0.0, 0.0), right_hand_rotation: float = 0.0) -> dict[str, TransformNode]:
    return {
        "CHARACTER_ROOT": TransformNode("CHARACTER_ROOT", None),
        "BODY": TransformNode("BODY", "CHARACTER_ROOT"),
        "RIGHT_ARM": TransformNode("RIGHT_ARM", "BODY"),
        "RIGHT_HAND": TransformNode(
            "RIGHT_HAND",
            "RIGHT_ARM",
            GRIP_ANCHOR[0] + right_hand_delta[0],
            GRIP_ANCHOR[1] + right_hand_delta[1],
            right_hand_rotation,
        ),
        "GRIP_ANCHOR": TransformNode("GRIP_ANCHOR", "RIGHT_HAND"),
        "MAIN_HAND_WEAPON": TransformNode("MAIN_HAND_WEAPON", "GRIP_ANCHOR"),
        "FRONT_GRIP_HAND": TransformNode("FRONT_GRIP_HAND", "RIGHT_HAND"),
    }


def _suppress_base() -> Image.Image:
    base = _rgba(CHARACTER_BASE_PATH)
    mask = Image.open(R3_MASK_PATH).convert("L")
    if mask.size != CANVAS:
        raise ValueError(f"unexpected R3 mask size: {mask.size}")
    output = base.copy()
    output.putalpha(ImageChops.multiply(base.getchannel("A"), ImageOps.invert(mask)))
    return output


def _front_grip_layer() -> Image.Image:
    patch = _rgba(R3_GRIP_LAYER_PATH)
    if patch.size != R3_PATCH_SIZE:
        raise ValueError(f"unexpected R3 patch size: {patch.size}")
    layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    layer.alpha_composite(patch, R3_PATCH_POSITION)
    return layer


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
    return rotated, ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def weapon_layer_and_grip(weapon_id: str) -> tuple[Image.Image, tuple[float, float]]:
    if weapon_id not in WEAPON_SPECS:
        raise KeyError(weapon_id)
    spec = WEAPON_SPECS[weapon_id]
    source = _rgba(spec["asset"])
    resized = source.resize(
        (round(source.width * float(spec["scale"])), round(source.height * float(spec["scale"]))),
        Image.Resampling.LANCZOS,
    )
    grip_ratio = spec["grip_point"]
    grip = (float(grip_ratio[0]) * resized.width, float(grip_ratio[1]) * resized.height)
    rotated, tracked = _rotate_with_tracked_point(resized, grip, float(spec["rotation_deg"]))
    left = round(GRIP_ANCHOR[0] - tracked[0])
    top = round(GRIP_ANCHOR[1] - tracked[1])
    layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    layer.alpha_composite(rotated, (left, top))
    bbox = layer.getchannel("A").getbbox()
    if bbox is None or bbox[0] < 0 or bbox[1] < 0 or bbox[2] > CANVAS[0] or bbox[3] > CANVAS[1]:
        raise ValueError(f"{weapon_id} clips PLAYER_FRAME: {bbox}")
    return layer, GRIP_ANCHOR


def resolve_presentation(equipped_item_id: str | None) -> dict[str, str | None]:
    if equipped_item_id in WEAPON_SPECS:
        return {"pose_family": POSE_FAMILY, "weapon_id": equipped_item_id}
    return {"pose_family": "DEFAULT_POSE", "weapon_id": None}


def compose_layers(equipped_item_id: str | None) -> dict[str, Image.Image]:
    presentation = resolve_presentation(equipped_item_id)
    if presentation["weapon_id"] is None:
        return {"CHARACTER_BASE": _rgba(CHARACTER_BASE_PATH)}
    weapon_id = str(presentation["weapon_id"])
    return {
        "CHARACTER_BASE": _suppress_base(),
        "MAIN_HAND_WEAPON": weapon_layer_and_grip(weapon_id)[0],
        "FRONT_GRIP_HAND": _front_grip_layer(),
    }


def compose(equipped_item_id: str | None) -> Image.Image:
    layers = compose_layers(equipped_item_id)
    output = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    for layer_id in ("CHARACTER_BASE", "MAIN_HAND_WEAPON", "FRONT_GRIP_HAND"):
        if layer_id in layers:
            output = Image.alpha_composite(output, layers[layer_id])
    return output


def _flatten(image: Image.Image, background: tuple[int, int, int] = (248, 246, 241)) -> Image.Image:
    backdrop = Image.new("RGBA", image.size, background + (255,))
    return Image.alpha_composite(backdrop, image).convert("RGB")


def _save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def _full_view(image: Image.Image, title: str, subtitle: str) -> Image.Image:
    canvas = Image.new("RGB", (700, 970), (239, 243, 247))
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 18), title, fill=(28, 47, 70), font=_font(25, bold=True))
    draw.text((24, 54), subtitle, fill=(87, 105, 125), font=_font(14))
    frame = _flatten(image)
    frame.thumbnail((640, 820), Image.Resampling.LANCZOS)
    left = (canvas.width - frame.width) // 2
    top = 103 + (820 - frame.height) // 2
    canvas.paste(frame, (left, top))
    draw.rectangle((24, 103, canvas.width - 24, 923), outline=(190, 202, 214), width=2)
    draw.text((24, 934), "R3 LOCAL ART REFINEMENT · Owner visual review pending · runtime inactive", fill=(112, 78, 34), font=_font(12, bold=True))
    return canvas


def _grip_crop(image: Image.Image, title: str, subtitle: str = "enlarged forearm / wrist / palm / thumb / four fingers / handle") -> Image.Image:
    crop = _flatten(image.crop((600, 550, 960, 990)), (250, 250, 250)).resize((720, 880), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (780, 1035), (239, 243, 247))
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 18), title, fill=(28, 47, 70), font=_font(23, bold=True))
    draw.text((24, 53), subtitle, fill=(87, 105, 125), font=_font(13))
    canvas.paste(crop, (30, 100))
    draw.rectangle((30, 100, 750, 980), outline=(190, 202, 214), width=2)
    draw.text((30, 995), "GRIP_ANCHOR = (760, 800) · unchanged from R2 · rotation = -8°", fill=(30, 99, 92), font=_font(12, bold=True))
    return canvas


def _extreme_grip_crop(image: Image.Image) -> Image.Image:
    crop = _flatten(image.crop((635, 590, 900, 900)), (250, 250, 250)).resize((900, 1050), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (960, 1130), (239, 243, 247))
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 16), "A053-R3 · true handle grip close-up", fill=(28, 47, 70), font=_font(25, bold=True))
    draw.text((24, 51), "forearm → wrist → palm → thumb/fingers → handle", fill=(87, 105, 125), font=_font(14))
    canvas.paste(crop, (30, 82))
    draw.rectangle((30, 82, 930, 1132), outline=(190, 202, 214), width=2)
    return canvas


def _side_by_side_three(images: list[Image.Image], title: str, labels: list[str]) -> Image.Image:
    width = 700
    height = max(image.height for image in images)
    canvas = Image.new("RGB", (width * len(images), height + 110), (231, 237, 243))
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 16), title, fill=(28, 47, 70), font=_font(25, bold=True))
    draw.text((24, 54), "static visual comparison only · Owner acceptance remains pending", fill=(87, 105, 125), font=_font(13))
    for index, (image, label) in enumerate(zip(images, labels)):
        canvas.paste(image, (index * width, 100))
        draw.text((index * width + 10, 76), label, fill=(30, 99, 92) if index == 2 else (142, 73, 50), font=_font(13, bold=True))
    return canvas


def _side_by_side_two(left: Image.Image, right: Image.Image, title: str, left_label: str, right_label: str) -> Image.Image:
    height = max(left.height, right.height)
    canvas = Image.new("RGB", (left.width + right.width + 40, height + 100), (231, 237, 243))
    draw = ImageDraw.Draw(canvas)
    draw.text((20, 14), title, fill=(28, 47, 70), font=_font(24, bold=True))
    draw.text((20, 48), "R2 vs R3 localized grip comparison · static evidence only", fill=(87, 105, 125), font=_font(13))
    canvas.paste(left, (0, 90))
    canvas.paste(right, (left.width + 40, 90))
    draw.text((10, 66), left_label, fill=(142, 73, 50), font=_font(13, bold=True))
    draw.text((left.width + 50, 66), right_label, fill=(30, 99, 92), font=_font(13, bold=True))
    return canvas


def _layer_panel(image: Image.Image, title: str, subtitle: str) -> Image.Image:
    canvas = Image.new("RGB", (270, 410), (239, 243, 247))
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 8), title, fill=(28, 47, 70), font=_font(15, bold=True))
    draw.text((10, 30), subtitle, fill=(87, 105, 125), font=_font(10))
    frame = _flatten(image)
    frame.thumbnail((240, 330), Image.Resampling.LANCZOS)
    canvas.paste(frame, ((canvas.width - frame.width) // 2, 64))
    draw.rectangle((14, 64, 256, 394), outline=(190, 202, 214), width=1)
    return canvas


def _exploded_view(layers: dict[str, Image.Image], final: Image.Image) -> Image.Image:
    canvas = Image.new("RGB", (1120, 465), (231, 237, 243))
    draw = ImageDraw.Draw(canvas)
    draw.text((18, 12), "A053-R3 Paper Doll · true-handle-grip composition", fill=(28, 47, 70), font=_font(24, bold=True))
    draw.text((18, 46), "L10 base + L20 independent weapon + L30 localized true grip hand = final", fill=(87, 105, 125), font=_font(13))
    panels = [
        _layer_panel(layers["CHARACTER_BASE"], "L10 CHARACTER_BASE", "localized R3 suppression"),
        _layer_panel(layers["MAIN_HAND_WEAPON"], "L20 MAIN_HAND_WEAPON", "child of GRIP_ANCHOR"),
        _layer_panel(layers["FRONT_GRIP_HAND"], "L30 FRONT_GRIP_HAND", "reusable R3 anatomy"),
        _layer_panel(final, "FINAL COMPOSITE", "wooden_sword"),
    ]
    for index, panel in enumerate(panels):
        canvas.paste(panel, (18 + index * 276, 78))
        if index < 3:
            draw.text((261 + index * 276, 235), "+" if index < 2 else "=", fill=(30, 99, 92), font=_font(28, bold=True))
    return canvas


def _responsive_view(image: Image.Image) -> Image.Image:
    canvas = Image.new("RGB", (1040, 620), (231, 237, 243))
    draw = ImageDraw.Draw(canvas)
    draw.text((22, 16), "Static responsive contract proof", fill=(28, 47, 70), font=_font(25, bold=True))
    draw.text((22, 50), "one shared local frame; character, hand and weapon scale as a unit", fill=(87, 105, 125), font=_font(13))
    widths = (300, 250, 190, 145)
    labels = ("DESKTOP", "IPAD LANDSCAPE", "IPAD PORTRAIT", "IPHONE PORTRAIT")
    x = 22
    for width, label in zip(widths, labels):
        frame_height = round(width * CANVAS[1] / CANVAS[0])
        frame = _flatten(image).resize((width, frame_height), Image.Resampling.LANCZOS)
        draw.text((x, 88), label, fill=(30, 99, 92), font=_font(12, bold=True))
        canvas.paste(frame, (x, 115))
        draw.rectangle((x, 115, x + width, 115 + frame_height), outline=(190, 202, 214), width=2)
        x += width + 35
    return canvas


def _motion_diagram() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1050" height="620" viewBox="0 0 1050 620">
  <rect width="1050" height="620" fill="#eef3f7"/>
  <text x="32" y="44" font-family="Segoe UI,Arial,sans-serif" font-size="28" font-weight="700" fill="#1c2f46">A053-R3 motion-ready proof</text>
  <text x="32" y="76" font-family="Segoe UI,Arial,sans-serif" font-size="16" fill="#57697d">Static hierarchy only · no animation implemented · R3 grip anatomy remains local to RIGHT_HAND</text>
  <g font-family="Segoe UI,Arial,sans-serif" font-size="18" text-anchor="middle">
    <rect x="370" y="106" width="310" height="54" rx="12" fill="#203047"/><text x="525" y="140" fill="#fff">CHARACTER_ROOT</text>
    <line x1="525" y1="160" x2="525" y2="195" stroke="#2f6f68" stroke-width="4" marker-end="url(#arrow)"/>
    <rect x="400" y="198" width="250" height="54" rx="12" fill="#55738e"/><text x="525" y="232" fill="#fff">RIGHT_ARM</text>
    <line x1="525" y1="252" x2="525" y2="287" stroke="#2f6f68" stroke-width="4" marker-end="url(#arrow)"/>
    <rect x="400" y="290" width="250" height="54" rx="12" fill="#55738e"/><text x="525" y="324" fill="#fff">RIGHT_HAND</text>
    <line x1="525" y1="344" x2="525" y2="379" stroke="#2f6f68" stroke-width="4" marker-end="url(#arrow)"/>
    <rect x="365" y="382" width="320" height="54" rx="12" fill="#2f8b7d"/><text x="525" y="416" fill="#fff">GRIP_ANCHOR (760,800)</text>
    <line x1="525" y1="436" x2="525" y2="471" stroke="#2f6f68" stroke-width="4" marker-end="url(#arrow)"/>
    <rect x="350" y="474" width="350" height="54" rx="12" fill="#b87837"/><text x="525" y="508" fill="#fff">MAIN_HAND_WEAPON</text>
  </g>
  <g font-family="Segoe UI,Arial,sans-serif" font-size="16" fill="#203047">
    <rect x="742" y="178" width="260" height="168" rx="14" fill="#fff" stroke="#c4d0dc" stroke-width="2"/>
    <text x="764" y="211" font-weight="700">PARENT TRANSFORM</text><text x="764" y="244">RIGHT_HAND Δx / Δy</text><text x="764" y="273">→ GRIP_ANCHOR follows</text><text x="764" y="302">→ weapon follows</text><text x="764" y="331">local contact preserved</text>
    <rect x="45" y="178" width="260" height="168" rx="14" fill="#fff" stroke="#c4d0dc" stroke-width="2"/>
    <text x="67" y="211" font-weight="700">LOCAL CHILD TRANSFORM</text><text x="67" y="244">weapon grip point</text><text x="67" y="273">rotation / scale</text><text x="67" y="302">relative to anchor</text><text x="67" y="331">not viewport CSS</text>
  </g>
  <defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#2f6f68"/></marker></defs>
</svg>
"""


def _review_html() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>A053-R3 apprentice true-handle grip visual review</title>
<style>
:root{font-family:Segoe UI,Arial,sans-serif;color:#203047;background:#eef3f7}body{margin:0;padding:16px}main{max-width:1420px;margin:auto}.notice{background:#fff8df;border:1px solid #dec67d;border-radius:12px;padding:14px 16px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:14px}figure{margin:0;background:white;border:1px solid #c5d1dd;border-radius:12px;padding:10px}figure img{display:block;width:100%;height:auto}figcaption{padding:8px 2px 2px;font-weight:700}.wide img{max-width:100%}code{background:#f1f4f7;padding:1px 4px;border-radius:4px}@media(max-width:520px){body{padding:8px}h1{font-size:22px}}
</style></head><body><main>
<h1>A053-R3 · apprentice / MAIN_HAND / wooden_sword</h1>
<p class="notice"><strong>STATIC LOCAL ART REFINEMENT · PENDING OWNER VISUAL REVIEW</strong><br>
R3 refines only the localized grip anatomy so the thumb and four fingers visibly clamp the independent wooden-sword handle. R2 compact proportions, wrist/forearm continuity, the three-layer Paper Doll hierarchy, server-owned <code>player_inventory.equipped</code> presentation contract, and Loadout OFF are preserved. <strong>Owner visual acceptance is not granted.</strong></p>
<h2>R1 → R2 → R3 full-character comparison</h2><figure class="wide"><img src="r3_vs_r1_r2_full.png" alt="A053 R1 R2 R3 full character comparison"><figcaption>R3 changes only the local grip anatomy; no full-character or weapon-specific composite was created.</figcaption></figure>
<h2>Grip anatomy review</h2><div class="grid">
<figure><img src="a053_r2_hand_wrist_after.png" alt="A053 R2 hand wrist before R3"><figcaption>R2 · before refinement</figcaption></figure>
<figure><img src="a053_r3_hand_wrist_after.png" alt="A053 R3 hand wrist after refinement"><figcaption>R3 · after refinement</figcaption></figure>
<figure class="wide"><img src="r2_vs_r3_grip_comparison.png" alt="R2 versus R3 grip comparison"><figcaption>R2 vs R3 enlarged grip comparison</figcaption></figure>
<figure class="wide"><img src="r3_extreme_grip_closeup.png" alt="A053 R3 true handle grip close-up"><figcaption>Close-up: continuous forearm → wrist → palm, thumb opposition, four fingers around handle</figcaption></figure>
<figure><img src="a053_r3_wooden_sword_after.png" alt="A053 R3 final wooden sword composition"><figcaption>Normal-size final character render</figcaption></figure>
</div>
<h2>Paper Doll composition</h2><figure class="wide"><img src="r3_layer_decomposition.png" alt="A053 R3 layer decomposition"><figcaption>L10 CHARACTER_BASE + L20 independent MAIN_HAND_WEAPON + L30 FRONT_GRIP_HAND = final</figcaption></figure>
<figure class="wide"><img src="r3_responsive_proof.png" alt="A053 R3 static responsive proof"><figcaption>Static frame-relative scaling proof; runtime device acceptance is not claimed</figcaption></figure>
<figure class="wide"><img src="r3_motion_ready_transform_diagram.svg" alt="A053 R3 motion-ready hierarchy"><figcaption>Motion-ready semantic parent/child relationship; animation is not implemented</figcaption></figure>
<p>Contract: <a href="../a053_r3_contract.json">a053_r3_contract.json</a></p>
</main></body></html>"""


def _image_record(path: Path, role: str) -> dict[str, Any]:
    with Image.open(path) as image:
        alpha = image.convert("RGBA").getchannel("A")
        return {
            "role": role,
            "path": _relative(path),
            "sha256": _sha256(path),
            "dimensions": [image.width, image.height],
            "color_mode": image.mode,
            "alpha_present": alpha.getbbox() is not None,
            "alpha_bbox": list(alpha.getbbox()) if alpha.getbbox() else None,
        }


def _contract() -> dict[str, Any]:
    nodes = prototype_transform_nodes()
    before_translation = resolve_world_transform(nodes, "MAIN_HAND_WEAPON")
    after_translation = resolve_world_transform(prototype_transform_nodes(right_hand_delta=(17.0, -11.0)), "MAIN_HAND_WEAPON")
    before_rotation = resolve_world_transform(nodes, "MAIN_HAND_WEAPON")
    after_rotation = resolve_world_transform(prototype_transform_nodes(right_hand_rotation=25.0), "MAIN_HAND_WEAPON")
    return {
        "task_id": "A053_R3_PAPER_DOLL_TRUE_HANDLE_GRIP_ANATOMY_VISUAL_REFINEMENT_001",
        "status": "STATIC_VISUAL_REFINEMENT_PENDING_OWNER_VISUAL_REVIEW",
        "runtime_active": False,
        "owner_visual_acceptance": "NOT_GRANTED",
        "base": {
            "a053_r2_head": R2_HEAD,
            "a053_r2_tree": R2_TREE,
            "fresh_master_head": FRESH_MASTER_HEAD,
            "fresh_master_tree": FRESH_MASTER_TREE,
            "master_advanced": True,
            "relevant_master_delta": "NONE",
        },
        "character": {
            "character_id": CHARACTER_KEY,
            "slot": IMPLEMENTED_SLOT,
            "pose_family": POSE_FAMILY,
            "default_pose_asset": _relative(CHARACTER_BASE_PATH),
            "grip_anchor": {
                "node": "GRIP_ANCHOR",
                "parent": "RIGHT_HAND",
                "x": GRIP_ANCHOR[0],
                "y": GRIP_ANCHOR[1],
                "normalized": list(GRIP_ANCHOR_NORMALIZED),
                "one_character_pose_one_grip_anchor": True,
                "r2_value_preserved": True,
            },
            "r2_grip_layer": {
                "path": _relative(R2_GRIP_LAYER_PATH),
                "sha256": _sha256(R2_GRIP_LAYER_PATH),
                "dimensions": list(Image.open(R2_GRIP_LAYER_PATH).size),
            },
            "r3_grip_layer": {
                "path": _relative(R3_GRIP_LAYER_PATH),
                "sha256": _sha256(R3_GRIP_LAYER_PATH),
                "dimensions": list(Image.open(R3_GRIP_LAYER_PATH).size),
                "position": list(R3_PATCH_POSITION),
                "parent": "RIGHT_HAND",
                "semantic_role": "localized true-handle sleeve wrist forearm and front fingers",
                "baked_weapon_pixels": 0,
                "source_provenance": "Owner-directed localized art derivative from A053-R2 grip anatomy; weapon remains independent",
            },
            "r2_mask_sha256": _sha256(R2_MASK_PATH),
            "r3_mask": {
                "path": _relative(R3_MASK_PATH),
                "sha256": _sha256(R3_MASK_PATH),
                "scope": "same small localized original open-hand suppression as R2",
                "visual_seam": "NONE",
            },
        },
        "layers": [
            {"order": 10, "layer_id": "CHARACTER_BASE", "parent": "BODY", "asset": _relative(CHARACTER_BASE_PATH), "mask": _relative(R3_MASK_PATH)},
            {"order": 20, "layer_id": "MAIN_HAND_WEAPON", "parent": "GRIP_ANCHOR", "local_origin": "weapon grip point"},
            {"order": 30, "layer_id": "FRONT_GRIP_HAND", "parent": "RIGHT_HAND", "asset": _relative(R3_GRIP_LAYER_PATH), "semantic_role": "localized true-handle grip anatomy"},
        ],
        "transform_hierarchy": [{"node_id": node.node_id, "parent": node.parent, "transform_fields": ["x", "y", "rotation_deg", "scale"]} for node in nodes.values()],
        "weapons": {
            weapon_id: {
                "slot": IMPLEMENTED_SLOT,
                "pose_family": POSE_FAMILY,
                "asset": _relative(spec["asset"]),
                "asset_sha256": _sha256(spec["asset"]),
                "source_asset": spec["source_asset"],
                "grip_point_normalized": list(spec["grip_point"]),
                "rotation_deg": spec["rotation_deg"],
                "scale": spec["scale"],
                "weapon_independent_grip_layer": True,
            }
            for weapon_id, spec in WEAPON_SPECS.items()
        },
        "authority": {
            "equipment_state": "server-owned player_inventory.equipped + canonical_slot",
            "presentation_only": True,
            "client_equipment_authority": False,
            "acquire_does_not_equip": True,
            "purchase_does_not_equip": True,
            "combat_authority_changed": False,
            "damage": {"baseline": 80, "wooden_sword": 84, "iron_sword": 90},
            "xp_amulet_new_equip": False,
            "xp_amulet_legacy_unequip": True,
            "go_stone_black_combat_power": 0,
        },
        "visual_self_assessment": {
            "r2_proportions_preserved": True,
            "grip_hand_oversized": False,
            "hand_scale_matches_character": True,
            "forearm_to_wrist_contour_continuous": True,
            "wrist_to_hand_direction_natural": True,
            "detached_replacement_hand_appearance": False,
            "weapon_handle_enters_palm": True,
            "front_fingers_occlude_handle": True,
            "thumb_opposes_fingers": True,
            "handle_behind_required_fingers": True,
            "handle_on_back_of_hand": False,
            "floating_fist_appearance": False,
            "pasted_handle_appearance": False,
            "wrist_alignment_plausible": True,
            "weapon_scale_plausible": True,
            "character_identity_preserved": True,
            "frame_clipping": False,
            "original_hand_suppression_used": True,
            "suppression_mask_scope": "localized original hand only; R2 scope retained",
            "mask_visual_seam": "NONE",
            "wooden_sword_baked_into_hand_asset": False,
            "character_grip_structure_reusable_for_other_one_hand_weapons": True,
            "pose_drift": False,
            "identity_drift": False,
        },
        "motion_proof": {
            "translation": {
                "delta": [17.0, -11.0],
                "weapon_before": [before_translation.x, before_translation.y],
                "weapon_after": [after_translation.x, after_translation.y],
                "pass": math.isclose(after_translation.x - before_translation.x, 17.0) and math.isclose(after_translation.y - before_translation.y, -11.0),
            },
            "rotation": {
                "right_hand_rotation_deg": 25.0,
                "weapon_before_rotation_deg": before_rotation.rotation_deg,
                "weapon_after_rotation_deg": after_rotation.rotation_deg,
                "pass": math.isclose(after_rotation.rotation_deg - before_rotation.rotation_deg, 25.0),
            },
        },
        "review_outputs": {name: _relative(REVIEW_ROOT / filename) for name, filename in {
            "r1_r2_r3_full": "r3_vs_r1_r2_full.png",
            "r2_grip_before": "a053_r2_hand_wrist_after.png",
            "r3_grip_after": "a053_r3_hand_wrist_after.png",
            "r2_r3_grip_comparison": "r2_vs_r3_grip_comparison.png",
            "r3_extreme_grip": "r3_extreme_grip_closeup.png",
            "r3_full": "a053_r3_wooden_sword_after.png",
            "layer_decomposition": "r3_layer_decomposition.png",
            "responsive": "r3_responsive_proof.png",
            "motion_diagram": "r3_motion_ready_transform_diagram.svg",
            "owner_review_html": "index.html",
        }.items()},
        "scope": {
            "paper_doll_architecture_preserved": True,
            "animation_implemented": False,
            "minimal_new_art_created": [_relative(R3_GRIP_LAYER_PATH)],
            "app_py_changed": False,
            "runtime_renderer_changed": False,
            "registry_changed": False,
            "combat_authority_changed": False,
            "schema_changed": False,
            "data_changed": False,
            "shop_changed": False,
            "loadout_enablement_changed": False,
        },
    }


def build() -> dict[str, Any]:
    required = (CHARACTER_BASE_PATH, R2_GRIP_LAYER_PATH, R2_MASK_PATH, R3_GRIP_LAYER_PATH, R3_MASK_PATH, *[spec["asset"] for spec in WEAPON_SPECS.values()])
    for path in required:
        if not Path(path).is_file():
            raise FileNotFoundError(path)

    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    reference_copies = (
        "a053_r1_default_pose_reference.png",
        "a053_r1_wooden_sword_before.png",
        "a053_r1_hand_wrist_before.png",
        "a053_r2_hand_wrist_after.png",
    )
    for filename in reference_copies:
        source = R2_REVIEW_ROOT / filename
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copyfile(source, REVIEW_ROOT / filename)

    default = compose(None)
    after = compose("wooden_sword")
    r2_after = _rgba(R2_REVIEW_ROOT / "a053_r2_wooden_sword_after.png")
    r2_grip = _rgba(R2_REVIEW_ROOT / "a053_r2_hand_wrist_after.png")
    r3_full = _full_view(after, "VIEW C · apprentice", "A053-R3 AFTER · wooden_sword · true handle grip")
    r3_grip = _grip_crop(after, "A053-R3 AFTER · true handle grip")

    _save(_full_view(default, "VIEW A · apprentice", "DEFAULT POSE · no equipment"), REVIEW_ROOT / "a053_r3_default_pose_reference.png")
    _save(r3_full, REVIEW_ROOT / "a053_r3_wooden_sword_after.png")
    _save(r3_grip, REVIEW_ROOT / "a053_r3_hand_wrist_after.png")
    _save(
        _side_by_side_three(
            [_rgba(REVIEW_ROOT / "a053_r1_wooden_sword_before.png"), r2_after, r3_full],
            "A053-R1 → A053-R2 → A053-R3 full-character comparison",
            ["R1 · before", "R2 · compact continuity", "R3 · true handle grip"],
        ),
        REVIEW_ROOT / "r3_vs_r1_r2_full.png",
    )
    _save(_side_by_side_two(r2_grip, r3_grip, "R2 → R3 enlarged grip comparison", "R2 · fist above handle", "R3 · fingers and thumb clamp handle"), REVIEW_ROOT / "r2_vs_r3_grip_comparison.png")
    _save(_extreme_grip_crop(after), REVIEW_ROOT / "r3_extreme_grip_closeup.png")
    _save(_exploded_view(compose_layers("wooden_sword"), after), REVIEW_ROOT / "r3_layer_decomposition.png")
    _save(_responsive_view(after), REVIEW_ROOT / "r3_responsive_proof.png")
    (REVIEW_ROOT / "r3_motion_ready_transform_diagram.svg").write_text(_motion_diagram(), encoding="utf-8", newline="\n")
    (REVIEW_ROOT / "index.html").write_text(_review_html(), encoding="utf-8", newline="\n")

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    contract = _contract()
    CONTRACT_PATH.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return contract


if __name__ == "__main__":
    report = build()
    print(json.dumps({"contract": _relative(CONTRACT_PATH), "review": _relative(REVIEW_ROOT / "index.html"), "r3_grip": _relative(R3_GRIP_LAYER_PATH), "r3_mask": _relative(R3_MASK_PATH)}, indent=2))
