"""Build the A053-R2 apprentice wooden-sword grip refinement review pack.

This is an isolated static visual-art refinement.  It preserves the A053-R1
semantic Paper Doll hierarchy and creates no live Hero, app.py, registry,
equipment, combat, or feature-gate behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "docs/planning/a053_r2_grip_hand_forearm_integration"
ASSET_ROOT = OUT_ROOT / "assets"
MASK_ROOT = OUT_ROOT / "masks"
REVIEW_ROOT = OUT_ROOT / "review"
CONTRACT_PATH = OUT_ROOT / "a053_r2_contract.json"

CANVAS = (1056, 1408)
FRAME_ID = "PLAYER_FRAME_A_STANDARD_CHIBI"
CHARACTER_KEY = "apprentice"
POSE_FAMILY = "ONE_HAND_SWORD"
IMPLEMENTED_SLOT = "MAIN_HAND"

CHARACTER_BASE_PATH = ROOT / "assets/hero/characters/wave2_p1/apprentice_p1.png"
R1_GRIP_LAYER_PATH = ROOT / (
    "docs/planning/rpg_wave2_modular_2d_handheld_sword_prototype/"
    "pose_layers/apprentice_grip_forearm.png"
)
R1_MASK_PATH = ROOT / (
    "docs/planning/rpg_wave2_modular_2d_handheld_sword_prototype/"
    "masks/apprentice_open_hand_suppression.png"
)
R2_GRIP_LAYER_PATH = ASSET_ROOT / "apprentice_grip_forearm_r2.png"
R2_MASK_PATH = MASK_ROOT / "apprentice_open_hand_suppression_r2.png"
WEAPON_ROOT = ROOT / "docs/planning/a053_r1_paper_doll_lite_main_hand/sources/weapon_only"

R1_HEAD = "776afd24093b91b3e6ca561cc374ce585c472da0"
R1_TREE = "ce5f4d6faa6f083a873b88ff53254fdd28d3d7a5"
FRESH_MASTER_HEAD = "f19f57f6c80fc7f3ba9c33817395c06284c879d1"
FRESH_MASTER_TREE = "aa5f3192c4c5e382dd87f990b39c5e3e789b06b1"

# The smaller, localized R2 patch is positioned in the same PLAYER_FRAME as
# the base.  The x shift is a minimal contact correction, not a new model.
GRIP_ANCHOR = (760.0, 800.0)
GRIP_ANCHOR_NORMALIZED = (GRIP_ANCHOR[0] / CANVAS[0], GRIP_ANCHOR[1] / CANVAS[1])
R2_PATCH_POSITION = (665, 580)
R2_PATCH_SIZE = (170, 380)
R2_ROTATION = -8.0


WEAPON_SPECS: dict[str, dict[str, Any]] = {
    "wooden_sword": {
        "asset": WEAPON_ROOT / "wooden_sword.png",
        "source_asset": "assets/hero/equipment/wearables/overlays/wooden_sword.png",
        "grip_point": (0.78, 0.18),
        "rotation_deg": R2_ROTATION,
        "scale": 0.48,
    },
    "iron_sword": {
        "asset": WEAPON_ROOT / "iron_sword.png",
        "source_asset": "assets/hero/equipment/wearables/overlays/iron_sword.png",
        "grip_point": (0.75, 0.14),
        "rotation_deg": R2_ROTATION,
        "scale": 0.36,
    },
    "fox_fang": {
        "asset": WEAPON_ROOT / "fox_fang.png",
        "source_asset": "assets/hero/equipment/wearables/overlays/fox_fang.png",
        "grip_point": (0.72, 0.15),
        "rotation_deg": R2_ROTATION,
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
    alpha = image.getchannel("A")
    if alpha.getbbox() is None:
        raise ValueError(f"transparent image has no visible pixels: {path}")
    return image


def _normalize(image: Image.Image) -> Image.Image:
    return image.convert("RGBA")


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
            "RIGHT_HAND", "RIGHT_ARM", GRIP_ANCHOR[0] + right_hand_delta[0], GRIP_ANCHOR[1] + right_hand_delta[1], right_hand_rotation
        ),
        "GRIP_ANCHOR": TransformNode("GRIP_ANCHOR", "RIGHT_HAND"),
        "MAIN_HAND_WEAPON": TransformNode("MAIN_HAND_WEAPON", "GRIP_ANCHOR"),
        "FRONT_GRIP_HAND": TransformNode("FRONT_GRIP_HAND", "RIGHT_HAND"),
    }


def _suppress_base() -> Image.Image:
    base = _rgba(CHARACTER_BASE_PATH)
    mask = Image.open(R2_MASK_PATH).convert("L")
    output = base.copy()
    output.putalpha(ImageChops.multiply(base.getchannel("A"), ImageOps.invert(mask)))
    return _normalize(output)


def _front_grip_layer() -> Image.Image:
    patch = _rgba(R2_GRIP_LAYER_PATH)
    if patch.size != R2_PATCH_SIZE:
        raise ValueError(f"unexpected R2 patch size: {patch.size}")
    layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    layer.alpha_composite(patch, R2_PATCH_POSITION)
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
    scale = float(spec["scale"])
    resized = source.resize((round(source.width * scale), round(source.height * scale)), Image.Resampling.LANCZOS)
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


def _full_view(image: Image.Image, title: str, subtitle: str, footer: str = "STATIC ART REFINEMENT · Owner review pending · runtime inactive") -> Image.Image:
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
    draw.text((24, 934), footer, fill=(112, 78, 34), font=_font(12, bold=True))
    return canvas


def _grip_crop(image: Image.Image, title: str) -> Image.Image:
    crop = _flatten(image.crop((610, 570, 970, 1030)), (250, 250, 250)).resize((700, 720), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (780, 875), (239, 243, 247))
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 18), title, fill=(28, 47, 70), font=_font(23, bold=True))
    draw.text((24, 53), "enlarged forearm / wrist / palm / handle continuity crop", fill=(87, 105, 125), font=_font(13))
    canvas.paste(crop, (40, 100))
    draw.rectangle((40, 100, 740, 820), outline=(190, 202, 214), width=2)
    draw.text((40, 835), "R2 GRIP_ANCHOR = (760, 800) · rotation = -8°", fill=(30, 99, 92), font=_font(12, bold=True))
    return canvas


def _side_by_side(left: Image.Image, right: Image.Image, title: str, left_label: str, right_label: str) -> Image.Image:
    canvas = Image.new("RGB", (1420, max(left.height, right.height) + 110), (231, 237, 243))
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 16), title, fill=(28, 47, 70), font=_font(25, bold=True))
    draw.text((24, 54), "left = A053-R1 · right = A053-R2 · visual comparison only", fill=(87, 105, 125), font=_font(13))
    canvas.paste(left, (20, 100))
    canvas.paste(right, (700, 100))
    draw.text((30, 76), left_label, fill=(142, 73, 50), font=_font(13, bold=True))
    draw.text((710, 76), right_label, fill=(30, 99, 92), font=_font(13, bold=True))
    return canvas


def _layer_panel(image: Image.Image, title: str, subtitle: str) -> Image.Image:
    canvas = Image.new("RGB", (270, 400), (239, 243, 247))
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 8), title, fill=(28, 47, 70), font=_font(15, bold=True))
    draw.text((10, 30), subtitle, fill=(87, 105, 125), font=_font(10))
    frame = _flatten(image)
    frame.thumbnail((240, 320), Image.Resampling.LANCZOS)
    canvas.paste(frame, ((canvas.width - frame.width) // 2, 64))
    draw.rectangle((14, 64, 256, 384), outline=(190, 202, 214), width=1)
    return canvas


def _exploded_view(layers: dict[str, Image.Image], final: Image.Image) -> Image.Image:
    canvas = Image.new("RGB", (1120, 455), (231, 237, 243))
    draw = ImageDraw.Draw(canvas)
    draw.text((18, 12), "A053-R2 Paper Doll Lite · localized grip continuity", fill=(28, 47, 70), font=_font(25, bold=True))
    draw.text((18, 46), "L10 base + L20 weapon + L30 localized sleeve/wrist/hand = final", fill=(87, 105, 125), font=_font(13))
    panels = [
        _layer_panel(layers["CHARACTER_BASE"], "L10 CHARACTER_BASE", "R2 localized suppression"),
        _layer_panel(layers["MAIN_HAND_WEAPON"], "L20 MAIN_HAND_WEAPON", "child of GRIP_ANCHOR"),
        _layer_panel(layers["FRONT_GRIP_HAND"], "L30 FRONT_GRIP_HAND", "reusable local anatomy"),
        _layer_panel(final, "FINAL COMPOSITE", "wooden_sword"),
    ]
    for index, panel in enumerate(panels):
        canvas.paste(panel, (18 + index * 276, 78))
        if index < 3:
            draw.text((261 + index * 276, 230), "+" if index < 2 else "=", fill=(30, 99, 92), font=_font(28, bold=True))
    return canvas


def _continuity_view(image: Image.Image) -> Image.Image:
    crop = _flatten(image.crop((635, 590, 885, 930)), (250, 250, 250)).resize((750, 1020), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (810, 1085), (239, 243, 247))
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 16), "A053-R2 · continuity / silhouette inspection", fill=(28, 47, 70), font=_font(23, bold=True))
    draw.text((24, 51), "forearm → wrist → palm → handle → front fingers", fill=(87, 105, 125), font=_font(13))
    canvas.paste(crop, (30, 85))
    draw.rectangle((30, 85, 780, 1105), outline=(190, 202, 214), width=2)
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
  <text x="32" y="44" font-family="Segoe UI,Arial,sans-serif" font-size="28" font-weight="700" fill="#1c2f46">A053-R2 motion-ready proof</text>
  <text x="32" y="76" font-family="Segoe UI,Arial,sans-serif" font-size="16" fill="#57697d">Static hierarchy only · no animation implemented · R2 visual patch remains a child of RIGHT_HAND</text>
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
<title>A053-R2 apprentice grip / forearm refinement</title>
<style>
:root{font-family:Segoe UI,Arial,sans-serif;color:#203047;background:#eef3f7}body{margin:0;padding:16px}main{max-width:1140px;margin:auto}.notice{background:#fff8df;border:1px solid #dec67d;border-radius:12px;padding:14px 16px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:14px}figure{margin:0;background:white;border:1px solid #c5d1dd;border-radius:12px;padding:10px}figure img{display:block;width:100%;height:auto}figcaption{padding:8px 2px 2px;font-weight:700}.wide img{max-width:100%}code{background:#f1f4f7;padding:1px 4px;border-radius:4px}@media(max-width:520px){body{padding:8px}h1{font-size:22px}}
</style></head><body><main>
<h1>A053-R2 · apprentice / MAIN_HAND / wooden_sword</h1>
<p class="notice"><strong>STATIC VISUAL REFINEMENT · PENDING OWNER VISUAL REVIEW</strong><br>
R2 reduces the R1 grip-hand scale and adds only a localized sleeve/wrist/forearm continuity patch. It preserves the semantic Paper Doll hierarchy and is not live Hero runtime wiring. The static input contract is server-owned <code>player_inventory.equipped</code>; Loadout remains OFF; Owner visual acceptance is not granted.</p>
<h2>Before / after</h2><div class="grid">
<figure><img src="a053_r1_default_pose_reference.png" alt="A053-R1 default apprentice reference"><figcaption>A · Default Pose reference</figcaption></figure>
<figure><img src="a053_r1_wooden_sword_before.png" alt="A053-R1 wooden sword before refinement"><figcaption>B · A053-R1 BEFORE</figcaption></figure>
<figure><img src="a053_r2_wooden_sword_after.png" alt="A053-R2 wooden sword after refinement"><figcaption>C · A053-R2 AFTER</figcaption></figure>
<figure><img src="before_after_full.png" alt="Full character before and after"><figcaption>Full-character comparison</figcaption></figure>
</div>
<h2>Hand / wrist acceptance inspection</h2><div class="grid">
<figure><img src="a053_r1_hand_wrist_before.png" alt="A053-R1 hand wrist before"><figcaption>D · R1 hand / wrist BEFORE</figcaption></figure>
<figure><img src="a053_r2_hand_wrist_after.png" alt="A053-R2 hand wrist after"><figcaption>E · R2 hand / wrist AFTER</figcaption></figure>
<figure class="wide"><img src="before_after_hand_proportion.png" alt="Before and after hand proportion"><figcaption>F · Hand proportion and wrist continuity comparison</figcaption></figure>
<figure class="wide"><img src="continuity_crop.png" alt="Forearm wrist palm handle continuity"><figcaption>H · Forearm → wrist → palm → handle → fingers</figcaption></figure>
</div>
<h2>Composition contract</h2><figure class="wide"><img src="exploded_layer_view.png" alt="Exploded Paper Doll layers"><figcaption>G · L10 CHARACTER_BASE + L20 MAIN_HAND_WEAPON + L30 localized FRONT_GRIP_HAND</figcaption></figure>
<figure class="wide"><img src="responsive_proof.png" alt="Static responsive proof"><figcaption>I · Static frame-relative scaling proof; runtime device acceptance not claimed</figcaption></figure>
<figure class="wide"><img src="motion_ready_transform_diagram.svg" alt="Motion-ready semantic hierarchy"><figcaption>Motion-ready parent/child relationship; animation is not implemented</figcaption></figure>
<p>Contract: <a href="../a053_r2_contract.json">a053_r2_contract.json</a></p>
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
        "task_id": "A053_R2_PAPER_DOLL_GRIP_HAND_FOREARM_INTEGRATION_VISUAL_REFINEMENT_001",
        "status": "STATIC_VISUAL_REFINEMENT_PENDING_OWNER_VISUAL_REVIEW",
        "runtime_active": False,
        "owner_visual_acceptance": "NOT_GRANTED",
        "base": {"a053_r1_head": R1_HEAD, "a053_r1_tree": R1_TREE, "fresh_master_head": FRESH_MASTER_HEAD, "fresh_master_tree": FRESH_MASTER_TREE},
        "character": {
            "character_id": CHARACTER_KEY,
            "slot": IMPLEMENTED_SLOT,
            "pose_family": POSE_FAMILY,
            "default_pose_asset": _relative(CHARACTER_BASE_PATH),
            "grip_anchor": {"node": "GRIP_ANCHOR", "parent": "RIGHT_HAND", "x": GRIP_ANCHOR[0], "y": GRIP_ANCHOR[1], "normalized": list(GRIP_ANCHOR_NORMALIZED), "one_character_pose_one_grip_anchor": True},
            "r2_grip_layer": {"path": _relative(R2_GRIP_LAYER_PATH), "position": list(R2_PATCH_POSITION), "dimensions": list(R2_PATCH_SIZE), "parent": "RIGHT_HAND", "semantic_role": "localized sleeve wrist forearm and front fingers"},
            "r1_grip_layer_sha256": _sha256(R1_GRIP_LAYER_PATH),
            "r1_mask_sha256": _sha256(R1_MASK_PATH),
            "r2_mask": {"path": _relative(R2_MASK_PATH), "scope": "small localized original open-hand suppression only", "visual_seam": "NONE"},
        },
        "layers": [
            {"order": 10, "layer_id": "CHARACTER_BASE", "parent": "BODY", "asset": _relative(CHARACTER_BASE_PATH), "mask": _relative(R2_MASK_PATH)},
            {"order": 20, "layer_id": "MAIN_HAND_WEAPON", "parent": "GRIP_ANCHOR", "local_origin": "weapon grip point"},
            {"order": 30, "layer_id": "FRONT_GRIP_HAND", "parent": "RIGHT_HAND", "asset": _relative(R2_GRIP_LAYER_PATH), "semantic_role": "localized sleeve/wrist/forearm continuity"},
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
            "grip_hand_oversized": False,
            "hand_scale_matches_character": True,
            "forearm_to_wrist_contour_continuous": True,
            "wrist_to_hand_direction_natural": True,
            "detached_replacement_hand_appearance": False,
            "weapon_handle_enters_palm": True,
            "front_fingers_occlude_handle": True,
            "handle_on_back_of_hand": False,
            "wrist_alignment_plausible": True,
            "weapon_scale_plausible": True,
            "character_identity_preserved": True,
            "frame_clipping": False,
            "original_hand_suppression_used": True,
            "wooden_sword_baked_into_hand_asset": False,
            "character_grip_structure_reusable_for_other_one_hand_weapons": True,
        },
        "motion_proof": {
            "translation": {"delta": [17.0, -11.0], "weapon_before": [before_translation.x, before_translation.y], "weapon_after": [after_translation.x, after_translation.y], "pass": math.isclose(after_translation.x - before_translation.x, 17.0) and math.isclose(after_translation.y - before_translation.y, -11.0)},
            "rotation": {"right_hand_rotation_deg": 25.0, "weapon_before_rotation_deg": before_rotation.rotation_deg, "weapon_after_rotation_deg": after_rotation.rotation_deg, "pass": math.isclose(after_rotation.rotation_deg - before_rotation.rotation_deg, 25.0)},
        },
        "review_outputs": {name: _relative(REVIEW_ROOT / filename) for name, filename in {
            "default_reference": "a053_r1_default_pose_reference.png",
            "before_full": "a053_r1_wooden_sword_before.png",
            "after_full": "a053_r2_wooden_sword_after.png",
            "before_after_full": "before_after_full.png",
            "before_grip": "a053_r1_hand_wrist_before.png",
            "after_grip": "a053_r2_hand_wrist_after.png",
            "before_after_hand": "before_after_hand_proportion.png",
            "continuity_crop": "continuity_crop.png",
            "exploded_layers": "exploded_layer_view.png",
            "responsive": "responsive_proof.png",
            "motion_diagram": "motion_ready_transform_diagram.svg",
            "owner_review_html": "index.html",
        }.items()},
        "scope": {
            "paper_doll_architecture_preserved": True,
            "animation_implemented": False,
            "minimal_new_art_created": [_relative(R2_GRIP_LAYER_PATH), _relative(R2_MASK_PATH)],
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
    for path in (CHARACTER_BASE_PATH, R1_GRIP_LAYER_PATH, R1_MASK_PATH, R2_GRIP_LAYER_PATH, R2_MASK_PATH, *[spec["asset"] for spec in WEAPON_SPECS.values()]):
        if not Path(path).is_file():
            raise FileNotFoundError(path)
    default = compose(None)
    after = compose("wooden_sword")
    _save(_full_view(default, "VIEW A · apprentice", "DEFAULT POSE · no equipment"), REVIEW_ROOT / "a053_r1_default_pose_reference.png")
    after_review = _full_view(after, "VIEW C · apprentice", "A053-R2 AFTER · wooden_sword · compact grip continuity")
    _save(after_review, REVIEW_ROOT / "a053_r2_wooden_sword_after.png")
    before = _rgba(REVIEW_ROOT / "a053_r1_wooden_sword_before.png")
    before_grip = _rgba(REVIEW_ROOT / "a053_r1_hand_wrist_before.png")
    after_grip = _grip_crop(after, "A053-R2 AFTER · hand / wrist")
    _save(after_grip, REVIEW_ROOT / "a053_r2_hand_wrist_after.png")
    _save(_side_by_side(before, after_review, "Full character comparison", "A053-R1 BEFORE", "A053-R2 AFTER"), REVIEW_ROOT / "before_after_full.png")
    _save(_side_by_side(before_grip, after_grip, "Hand proportion and wrist continuity", "R1 · oversized / discontinuous", "R2 · compact / continuous"), REVIEW_ROOT / "before_after_hand_proportion.png")
    _save(_continuity_view(after), REVIEW_ROOT / "continuity_crop.png")
    _save(_exploded_view(compose_layers("wooden_sword"), after), REVIEW_ROOT / "exploded_layer_view.png")
    _save(_responsive_view(after), REVIEW_ROOT / "responsive_proof.png")
    (REVIEW_ROOT / "motion_ready_transform_diagram.svg").write_text(_motion_diagram(), encoding="utf-8", newline="\n")
    (REVIEW_ROOT / "index.html").write_text(_review_html(), encoding="utf-8", newline="\n")
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    contract = _contract()
    CONTRACT_PATH.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return contract


if __name__ == "__main__":
    report = build()
    print(json.dumps({"contract": _relative(CONTRACT_PATH), "review": _relative(REVIEW_ROOT / "index.html"), "r2_grip": _relative(R2_GRIP_LAYER_PATH), "r2_mask": _relative(R2_MASK_PATH)}, indent=2))
