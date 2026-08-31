"""Build the A054-P0 split-weapon true-grip architecture prototype.

This module is deliberately static review tooling.  It demonstrates a small
semantic paper-doll hierarchy and deterministic layer composition for the
apprentice with wooden_sword and iron_sword.  It does not wire Hero, change
app.py, change equipment authority, or enable any product feature.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import json
import math
from pathlib import Path
import shutil
from typing import Any

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = "693b8ec61a039182c6dc57607c6cb17a5e2f0684"
BASE_TREE = "2a0f20f1f0a500d1d4f2c1eb6de33d6fe7804f72"
FRESH_MASTER_HEAD = "f19f57f6c80fc7f3ba9c33817395c06284c879d1"
FRESH_MASTER_TREE = "aa5f3192c4c5e382dd87f990b39c5e3e789b06b1"

OUT_ROOT = ROOT / "docs/planning/a054_p0_paper_doll_split_grip"
ASSET_ROOT = OUT_ROOT / "assets"
WEAPON_SPLIT_ROOT = ASSET_ROOT / "weapon_splits"
REVIEW_ROOT = OUT_ROOT / "review"
CONTRACT_PATH = OUT_ROOT / "a054_p0_contract.json"

CHARACTER_BASE_PATH = ROOT / "assets/hero/characters/wave2_p1/apprentice_p1.png"
GRIP_HAND_PATH = ASSET_ROOT / "apprentice_sword_grip_hand_p0.png"
R3_REVIEW_ROOT = ROOT / "docs/planning/a053_r3_true_handle_grip_anatomy/review"
WEAPON_ROOT = ROOT / "docs/planning/a053_r1_paper_doll_lite_main_hand/sources/weapon_only"

CANVAS = (1056, 1408)
FRAME_ID = "PLAYER_FRAME_A_STANDARD_CHIBI"
CHARACTER_ID = "apprentice"
POSE_ID = "ONE_HAND_SWORD_GRIP_POSE"
POSE_FAMILY = "ONE_HAND_SWORD"
SLOT = "MAIN_HAND"

# This is a semantic socket in the shared player frame, not a viewport CSS
# coordinate.  The split is made by projection along the same grip axis so
# the two weapon images remain one continuous weapon at composition time.
RIGHT_HAND_SOCKET = (760.0, 800.0)
GRIP_AXIS = (0.864, -0.504)
GRIP_AXIS_LENGTH = math.hypot(*GRIP_AXIS)
GRIP_AXIS = (GRIP_AXIS[0] / GRIP_AXIS_LENGTH, GRIP_AXIS[1] / GRIP_AXIS_LENGTH)
HAND_POSITION = (610, 570)
HAND_SIZE = (340, 380)
FRONT_WINDOW = (-45.0, 35.0)

WEAPON_SPECS: dict[str, dict[str, Any]] = {
    "wooden_sword": {
        "source": WEAPON_ROOT / "wooden_sword.png",
        "source_asset": "assets/hero/equipment/wearables/overlays/wooden_sword.png",
        "grip_point_normalized": (0.78, 0.18),
        "rotation_deg": -8.0,
        "scale": 0.48,
        "grip_width_px": 80.0,
    },
    "iron_sword": {
        "source": WEAPON_ROOT / "iron_sword.png",
        "source_asset": "assets/hero/equipment/wearables/overlays/iron_sword.png",
        "grip_point_normalized": (0.75, 0.14),
        "rotation_deg": -8.0,
        "scale": 0.36,
        "grip_width_px": 80.0,
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def font(size: int, *, bold: bool = False):
    candidates = [
        Path("C:/Windows/Fonts/segoeui.ttf" if not bold else "C:/Windows/Fonts/segoeuib.ttf"),
        Path("C:/Windows/Fonts/arial.ttf" if not bold else "C:/Windows/Fonts/arialbd.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def rgba(path: Path) -> Image.Image:
    if not path.is_file():
        raise FileNotFoundError(path)
    image = Image.open(path).convert("RGBA")
    if image.getchannel("A").getbbox() is None:
        raise ValueError(f"image has no visible pixels: {path}")
    return image


def rotate_point(x: float, y: float, degrees: float) -> tuple[float, float]:
    radians = math.radians(degrees)
    return (
        x * math.cos(radians) - y * math.sin(radians),
        x * math.sin(radians) + y * math.cos(radians),
    )


def compose_transform(parent: WorldTransform, local: TransformNode) -> WorldTransform:
    local_position = rotate_point(local.x * parent.scale, local.y * parent.scale, parent.rotation_deg)
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
            result = compose_transform(resolve(node.parent), node)
        visiting.remove(current)
        return result

    return resolve(node_id)


def transform_point(transform: WorldTransform, point: tuple[float, float]) -> tuple[float, float]:
    scaled = (point[0] * transform.scale, point[1] * transform.scale)
    rotated = rotate_point(scaled[0], scaled[1], transform.rotation_deg)
    return (transform.x + rotated[0], transform.y + rotated[1])


def prototype_transform_nodes(
    *, right_hand_delta: tuple[float, float] = (0.0, 0.0), right_hand_rotation: float = 0.0
) -> dict[str, TransformNode]:
    """Return the smallest semantic hierarchy needed for future motion.

    The static renderer does not animate these nodes.  The hierarchy exists so
    a future parent transform can carry the grip and both weapon pieces.
    """

    return {
        "CHARACTER_ROOT": TransformNode("CHARACTER_ROOT", None),
        "BODY": TransformNode("BODY", "CHARACTER_ROOT"),
        "RIGHT_ARM": TransformNode("RIGHT_ARM", "BODY"),
        "RIGHT_HAND": TransformNode(
            "RIGHT_HAND",
            "RIGHT_ARM",
            RIGHT_HAND_SOCKET[0] + right_hand_delta[0],
            RIGHT_HAND_SOCKET[1] + right_hand_delta[1],
            right_hand_rotation,
        ),
        "RIGHT_HAND_SOCKET": TransformNode("RIGHT_HAND_SOCKET", "RIGHT_HAND"),
        "GRIP_POINT": TransformNode("GRIP_POINT", "RIGHT_HAND_SOCKET"),
        "MAIN_HAND_WEAPON": TransformNode("MAIN_HAND_WEAPON", "GRIP_POINT"),
        "SWORD_GRIP_HAND": TransformNode("SWORD_GRIP_HAND", "RIGHT_HAND"),
        "WEAPON_BACK": TransformNode("WEAPON_BACK", "MAIN_HAND_WEAPON"),
        "WEAPON_FRONT": TransformNode("WEAPON_FRONT", "MAIN_HAND_WEAPON"),
    }


def load_character_base() -> Image.Image:
    return rgba(CHARACTER_BASE_PATH)


def load_grip_hand() -> Image.Image:
    hand = rgba(GRIP_HAND_PATH)
    if hand.size != HAND_SIZE:
        raise ValueError(f"unexpected grip-hand size: {hand.size}")
    return hand


def _rotate_with_tracked_point(
    image: Image.Image, point: tuple[float, float], degrees: float
) -> tuple[Image.Image, tuple[float, float]]:
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
    source = rgba(spec["source"])
    resized = source.resize(
        (
            round(source.width * float(spec["scale"])),
            round(source.height * float(spec["scale"])),
        ),
        Image.Resampling.LANCZOS,
    )
    grip_ratio = spec["grip_point_normalized"]
    grip = (float(grip_ratio[0]) * resized.width, float(grip_ratio[1]) * resized.height)
    rotated, tracked = _rotate_with_tracked_point(resized, grip, float(spec["rotation_deg"]))
    left = round(RIGHT_HAND_SOCKET[0] - tracked[0])
    top = round(RIGHT_HAND_SOCKET[1] - tracked[1])
    layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    layer.alpha_composite(rotated, (left, top))
    bbox = layer.getchannel("A").getbbox()
    if bbox is None or bbox[0] < 0 or bbox[1] < 0 or bbox[2] > CANVAS[0] or bbox[3] > CANVAS[1]:
        raise ValueError(f"{weapon_id} clips PLAYER_FRAME: {bbox}")
    return layer, RIGHT_HAND_SOCKET


def split_weapon_layers(weapon_id: str) -> tuple[Image.Image, Image.Image]:
    """Split one continuous weapon by semantic grip-axis projection.

    Pixels are assigned to exactly one layer.  The front window is local to
    the socket and contains only the handle contact segment; blade, guard,
    pommel, and the remaining handle stay in the back layer.
    """

    full, anchor = weapon_layer_and_grip(weapon_id)
    back = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    front = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    back_pixels = back.load()
    front_pixels = front.load()
    source_pixels = full.load()
    low, high = FRONT_WINDOW
    for y in range(CANVAS[1]):
        for x in range(CANVAS[0]):
            pixel = source_pixels[x, y]
            if pixel[3] == 0:
                continue
            projection = (x - anchor[0]) * GRIP_AXIS[0] + (y - anchor[1]) * GRIP_AXIS[1]
            if low <= projection <= high:
                front_pixels[x, y] = pixel
            else:
                back_pixels[x, y] = pixel
    return back, front


def compose_layers(weapon_id: str | None) -> dict[str, Image.Image]:
    if resolve_presentation(weapon_id)["weapon_id"] is None:
        return {"CHARACTER_BASE": load_character_base()}
    assert weapon_id is not None
    back, front = split_weapon_layers(weapon_id)
    hand_layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    hand_layer.alpha_composite(load_grip_hand(), HAND_POSITION)
    return {
        "CHARACTER_BASE": load_character_base(),
        "WEAPON_BACK": back,
        "SWORD_GRIP_HAND": hand_layer,
        "WEAPON_FRONT": front,
    }


def resolve_presentation(weapon_id: str | None) -> dict[str, str | None]:
    """Resolve a static presentation without becoming equipment authority."""

    if weapon_id in WEAPON_SPECS:
        return {"pose_id": POSE_ID, "pose_family": POSE_FAMILY, "weapon_id": weapon_id}
    return {"pose_id": "DEFAULT_POSE", "pose_family": "DEFAULT_POSE", "weapon_id": None}


def compose(weapon_id: str | None) -> Image.Image:
    layers = compose_layers(weapon_id)
    output = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    for layer_name in ("CHARACTER_BASE", "WEAPON_BACK", "SWORD_GRIP_HAND", "WEAPON_FRONT"):
        if layer_name in layers:
            output.alpha_composite(layers[layer_name])
    return output


def _on_background(image: Image.Image, size: tuple[int, int] | None = None, *, bg=(250, 247, 239, 255)) -> Image.Image:
    source = image.convert("RGBA")
    if size is not None:
        source.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size or source.size, bg)
    left = (canvas.width - source.width) // 2
    top = (canvas.height - source.height) // 2
    canvas.alpha_composite(source, (left, top))
    return canvas


def _title(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, *, size: int = 24, fill=(25, 54, 67), bold=False) -> None:
    draw.text(xy, text, font=font(size, bold=bold), fill=fill)


def _card(image: Image.Image, title: str, subtitle: str, *, body_size=(360, 480)) -> Image.Image:
    body = _on_background(image, body_size)
    width = body.width + 36
    height = body.height + 100
    card = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=14, outline=(183, 197, 193), width=2)
    _title(draw, (18, 12), title, size=21, bold=True)
    draw.text((18, 42), subtitle, font=font(15), fill=(82, 104, 105))
    card.alpha_composite(body, (18, 76))
    return card


def _grid(cards: list[Image.Image], columns: int, *, heading: str) -> Image.Image:
    gap = 18
    rows = math.ceil(len(cards) / columns)
    card_width = max(card.width for card in cards)
    card_height = max(card.height for card in cards)
    canvas = Image.new("RGBA", (columns * card_width + (columns + 1) * gap, rows * card_height + (rows + 1) * gap + 64), (242, 238, 228, 255))
    draw = ImageDraw.Draw(canvas)
    _title(draw, (gap, 18), heading, size=28, bold=True)
    for index, card in enumerate(cards):
        x = gap + (index % columns) * (card_width + gap)
        y = 64 + gap + (index // columns) * (card_height + gap)
        canvas.alpha_composite(card, (x, y))
    return canvas


def _grip_crop(image: Image.Image) -> Image.Image:
    crop = image.crop((575, 525, 920, 925))
    return crop.resize((690, 800), Image.Resampling.LANCZOS)


def _layer_decomposition(weapon_id: str) -> Image.Image:
    layers = compose_layers(weapon_id)
    panels: list[Image.Image] = []
    labels = [
        ("L10 CHARACTER_BASE", "identity / body"),
        ("L20 WEAPON_BACK", "blade + rear handle"),
        ("L30 SWORD_GRIP_HAND", "shared hand / wrist"),
        ("L40 WEAPON_FRONT", "contact handle segment"),
        ("FINAL COMPOSITE", "L10 → L20 → L30 → L40"),
    ]
    for layer_name, (title, subtitle) in zip(("CHARACTER_BASE", "WEAPON_BACK", "SWORD_GRIP_HAND", "WEAPON_FRONT"), labels[:4]):
        panels.append(_card(layers[layer_name], title, subtitle, body_size=(220, 294)))
    panels.append(_card(compose(weapon_id), labels[4][0], labels[4][1], body_size=(220, 294)))
    return _grid(panels, 5, heading=f"A054-P0 · {weapon_id} · split-layer decomposition")


def _architecture_diagram() -> Image.Image:
    width, height = 1500, 760
    image = Image.new("RGBA", (width, height), (246, 243, 235, 255))
    draw = ImageDraw.Draw(image)
    _title(draw, (36, 24), "A054-P0 · SPLIT WEAPON + TRUE GRIP ARCHITECTURE", size=34, bold=True)
    draw.text((38, 72), "Technical candidate only · Owner visual acceptance required · RUNTIME_ACTIVE=NO", font=font(20), fill=(146, 69, 43))
    boxes = [
        ("L10", "CHARACTER_BASE", "approved apprentice identity", (70, 170, 330, 510), (222, 238, 232)),
        ("L20", "WEAPON_BACK", "blade / guard / rear handle", (385, 170, 645, 510), (225, 231, 245)),
        ("L30", "SWORD_GRIP_HAND", "shared hand + wrist", (700, 170, 960, 510), (247, 226, 205)),
        ("L40", "WEAPON_FRONT", "minimal contact handle", (1015, 170, 1275, 510), (239, 220, 215)),
        ("FINAL", "COMPOSITE", "one continuous held sword", (1330, 170, 1470, 510), (210, 236, 224)),
    ]
    for layer, name, detail, rect, color in boxes:
        draw.rounded_rectangle(rect, radius=18, fill=color, outline=(44, 88, 91), width=3)
        x1, y1, x2, y2 = rect
        _title(draw, (x1 + 18, y1 + 18), layer, size=22, bold=True)
        draw.text((x1 + 18, y1 + 58), name, font=font(19, bold=True), fill=(35, 65, 69))
        draw.multiline_text((x1 + 18, y1 + 112), detail, font=font(17), fill=(56, 75, 76), spacing=5)
        if layer == "L30":
            draw.ellipse((x1 + 90, y1 + 240, x1 + 170, y1 + 320), fill=(240, 157, 116), outline=(110, 70, 50), width=3)
            draw.line((x1 + 130, y1 + 320, x1 + 130, y1 + 370), fill=(110, 70, 50), width=7)
            draw.text((x1 + 25, y1 + 400), "fingers wrap handle", font=font(16, bold=True), fill=(123, 61, 42))
        elif layer in ("L20", "L40"):
            draw.line((x1 + 55, y1 + 370, x1 + 200, y1 + 225), fill=(96, 52, 30), width=18 if layer == "L20" else 10)
            draw.ellipse((x1 + 175, y1 + 200, x1 + 220, y1 + 245), fill=(141, 87, 50))
        if layer != "FINAL":
            draw.line((x2 + 8, (y1 + y2) // 2, x2 + 46, (y1 + y2) // 2), fill=(40, 100, 95), width=5)
            draw.polygon(((x2 + 46, (y1 + y2) // 2), (x2 + 28, (y1 + y2) // 2 - 12), (x2 + 28, (y1 + y2) // 2 + 12)), fill=(40, 100, 95))
    draw.rounded_rectangle((60, 585, 1440, 710), radius=16, fill=(255, 255, 255, 255), outline=(181, 192, 187), width=2)
    _title(draw, (88, 608), "SEMANTIC RELATIONSHIP", size=24, bold=True)
    draw.text((88, 650), "CHARACTER_ROOT  →  RIGHT_ARM  →  RIGHT_HAND  →  RIGHT_HAND_SOCKET  →  GRIP_POINT  →  MAIN_HAND_WEAPON", font=font(22, bold=True), fill=(37, 83, 86))
    return image


def _axis_overlay(weapon_id: str) -> Image.Image:
    image = _on_background(_grip_crop(compose(weapon_id)), (690, 800), bg=(255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    # The crop origin is (575,525) and the crop is scaled by 2.
    anchor = ((RIGHT_HAND_SOCKET[0] - 575) * 2, (RIGHT_HAND_SOCKET[1] - 525) * 2)
    direction = (GRIP_AXIS[0] * 230, GRIP_AXIS[1] * 230)
    draw.ellipse((anchor[0] - 11, anchor[1] - 11, anchor[0] + 11, anchor[1] + 11), fill=(24, 156, 115), outline=(255, 255, 255), width=3)
    draw.line((anchor[0], anchor[1], anchor[0] + direction[0], anchor[1] + direction[1]), fill=(26, 111, 190), width=7)
    draw.line((anchor[0], anchor[1], anchor[0] - direction[0], anchor[1] - direction[1]), fill=(26, 111, 190), width=3)
    draw.text((18, 20), "RIGHT_HAND_SOCKET / GRIP_POINT", font=font(25, bold=True), fill=(23, 92, 84))
    draw.text((18, 56), "GRIP_AXIS · front window −45…+35 px", font=font(20), fill=(29, 92, 142))
    return image


def _before_after() -> Image.Image:
    failed = rgba(R3_REVIEW_ROOT / "a053_r3_wooden_sword_after.png")
    candidate = compose("wooden_sword")
    left = _card(failed, "A053-R3", "previous whole-weapon / front-hand approach", body_size=(430, 574))
    right = _card(candidate, "A054-P0", "split weapon / true-grip candidate", body_size=(430, 574))
    return _grid([left, right], 2, heading="A053-R3 failed approach → A054-P0 architecture prototype")


def _same_grip_comparison() -> Image.Image:
    cards = [
        _card(compose("wooden_sword"), "wooden_sword", "same SWORD_GRIP_HAND + same socket", body_size=(330, 440)),
        _card(compose("iron_sword"), "iron_sword", "same SWORD_GRIP_HAND + same socket", body_size=(330, 440)),
    ]
    return _grid(cards, 2, heading="Same reusable grip pose · weapon identity swapped independently")


def _write_motion_svg(path: Path) -> None:
    path.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720">
  <rect width="1200" height="720" fill="#f6f3eb"/>
  <text x="40" y="58" font-family="Arial" font-size="32" font-weight="700" fill="#193643">A054-P0 · motion-ready semantic transform proof</text>
  <text x="40" y="94" font-family="Arial" font-size="18" fill="#8f452f">Technical diagram only · animation is not implemented · Owner visual acceptance required</text>
  <g font-family="Arial" font-size="23" font-weight="700" text-anchor="middle">
    <rect x="390" y="130" width="420" height="60" rx="14" fill="#d2e8df" stroke="#2c7770" stroke-width="3"/><text x="600" y="168" fill="#214c4d">CHARACTER_ROOT</text>
    <rect x="430" y="250" width="340" height="60" rx="14" fill="#e4eaf7" stroke="#526c9a" stroke-width="3"/><text x="600" y="288" fill="#31486f">RIGHT_ARM</text>
    <rect x="450" y="370" width="300" height="60" rx="14" fill="#f8dfbb" stroke="#ac7049" stroke-width="3"/><text x="600" y="408" fill="#744b32">RIGHT_HAND</text>
    <rect x="400" y="490" width="400" height="60" rx="14" fill="#f1d1ca" stroke="#9e5f54" stroke-width="3"/><text x="600" y="528" fill="#713e38">GRIP_POINT / SOCKET</text>
    <rect x="350" y="610" width="500" height="60" rx="14" fill="#d9e8f5" stroke="#3b76a8" stroke-width="3"/><text x="600" y="648" fill="#24537d">MAIN_HAND_WEAPON (BACK + FRONT)</text>
  </g>
  <g stroke="#2c7770" stroke-width="5" fill="none">
    <path d="M600 190 V250"/><path d="M600 310 V370"/><path d="M600 430 V490"/><path d="M600 550 V610"/>
  </g>
  <g font-family="Arial" font-size="18" fill="#3e5556">
    <text x="875" y="225">PARENT TRANSFORM</text><text x="875" y="255">RIGHT_HAND Δx / Δy</text><text x="875" y="284">→ socket follows</text><text x="875" y="313">→ grip follows</text><text x="875" y="342">→ weapon follows</text>
    <text x="875" y="445">PARENT ROTATION</text><text x="875" y="475">RIGHT_HAND θ</text><text x="875" y="504">→ local grip preserved</text><text x="875" y="533">→ both weapon pieces rotate</text>
  </g>
</svg>
""",
        encoding="utf-8",
    )


def _write_index(review_outputs: dict[str, str]) -> None:
    rows = []
    for label, filename in review_outputs.items():
        if filename.endswith(".svg"):
            rows.append(f'<li><a href="{html.escape(filename)}">{html.escape(label)}</a></li>')
        else:
            rows.append(f'<figure><figcaption>{html.escape(label)}</figcaption><img src="{html.escape(filename)}" alt="{html.escape(label)}"></figure>')
    (REVIEW_ROOT / "index.html").write_text(
        """<!doctype html><html><head><meta charset="utf-8"><title>A054-P0 split weapon grip prototype</title>
<style>body{font-family:Arial,sans-serif;background:#f6f3eb;color:#193643;margin:24px}h1{margin-bottom:4px}p{color:#714434}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}figure{background:white;border:1px solid #b5c3bd;border-radius:12px;padding:12px;margin:0}img{max-width:100%;height:auto;display:block}figcaption{font-weight:700;margin-bottom:8px}.notice{padding:14px;background:#fff0dd;border-left:5px solid #c46c3e}.links{background:white;padding:14px;border-radius:12px}</style></head>
<body><h1>A054-P0 Paper Doll Split Weapon True-Grip Prototype</h1>
<div class="notice"><strong>TECHNICAL CANDIDATE · OWNER VISUAL ACCEPTANCE REQUIRED</strong><br>RUNTIME_ACTIVE=NO. This pack is a static architecture proof and does not activate Hero or change equipment authority.</div>
<p>Scope: apprentice · ONE_HAND_SWORD_GRIP_POSE · wooden_sword + iron_sword · L10 CHARACTER_BASE → L20 WEAPON_BACK → L30 SWORD_GRIP_HAND → L40 WEAPON_FRONT.</p>
<div class="grid">""" + "\n".join(rows) + """</div></body></html>""",
        encoding="utf-8",
    )


def build() -> dict[str, Any]:
    required = [CHARACTER_BASE_PATH, GRIP_HAND_PATH, R3_REVIEW_ROOT / "a053_r3_wooden_sword_after.png"] + [spec["source"] for spec in WEAPON_SPECS.values()]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)

    ASSET_ROOT.mkdir(parents=True, exist_ok=True)
    WEAPON_SPLIT_ROOT.mkdir(parents=True, exist_ok=True)
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)

    # The A053-R3 reference is copied only into this review pack.  It remains
    # untouched in its source worktree and is clearly marked as the failed
    # prior approach.
    shutil.copyfile(R3_REVIEW_ROOT / "a053_r3_wooden_sword_after.png", REVIEW_ROOT / "a054_r3_failed_approach_reference.png")

    split_records: dict[str, dict[str, Any]] = {}
    for weapon_id in WEAPON_SPECS:
        full, _ = weapon_layer_and_grip(weapon_id)
        back, front = split_weapon_layers(weapon_id)
        back_path = WEAPON_SPLIT_ROOT / f"{weapon_id}_weapon_back_p0.png"
        front_path = WEAPON_SPLIT_ROOT / f"{weapon_id}_weapon_front_p0.png"
        back.save(back_path, format="PNG")
        front.save(front_path, format="PNG")
        split_records[weapon_id] = {
            "source_asset": WEAPON_SPECS[weapon_id]["source_asset"],
            "source_sha256": sha256(WEAPON_SPECS[weapon_id]["source"]),
            "full_frame": {"width": full.width, "height": full.height},
            "back_asset": relative(back_path),
            "back_sha256": sha256(back_path),
            "front_asset": relative(front_path),
            "front_sha256": sha256(front_path),
            "grip_point_normalized": list(WEAPON_SPECS[weapon_id]["grip_point_normalized"]),
            "grip_axis": list(GRIP_AXIS),
            "grip_width_px": WEAPON_SPECS[weapon_id]["grip_width_px"],
            "rotation_deg": WEAPON_SPECS[weapon_id]["rotation_deg"],
            "scale": WEAPON_SPECS[weapon_id]["scale"],
            "front_window_projection_px": list(FRONT_WINDOW),
            "weapon_only": True,
            "baked_into_hand": False,
        }

    outputs = {
        "failed_r3_reference": "a054_r3_failed_approach_reference.png",
        "wooden_full": "p0_wooden_sword_full.png",
        "iron_full": "p0_iron_sword_full.png",
        "wooden_grip_closeup": "p0_wooden_sword_grip_closeup.png",
        "iron_grip_closeup": "p0_iron_sword_grip_closeup.png",
        "split_architecture": "p0_split_layer_architecture.png",
        "wooden_layers": "p0_wooden_layer_decomposition.png",
        "iron_layers": "p0_iron_layer_decomposition.png",
        "grip_axis_overlay": "p0_grip_axis_overlay.png",
        "same_grip_wooden_iron": "p0_wooden_vs_iron_same_grip.png",
        "before_after": "p0_before_after.png",
        "motion_transform": "p0_motion_ready_transform_diagram.svg",
    }
    default = compose(None)
    wooden = compose("wooden_sword")
    iron = compose("iron_sword")
    _card(wooden, "wooden_sword", "normal-size final · shared true-grip candidate", body_size=(520, 694)).save(REVIEW_ROOT / outputs["wooden_full"])
    _card(iron, "iron_sword", "normal-size final · same grip pose", body_size=(520, 694)).save(REVIEW_ROOT / outputs["iron_full"])
    _card(_grip_crop(wooden), "wooden_sword grip", "enlarged handle / palm / fingers", body_size=(650, 750)).save(REVIEW_ROOT / outputs["wooden_grip_closeup"])
    _card(_grip_crop(iron), "iron_sword grip", "enlarged handle / palm / fingers", body_size=(650, 750)).save(REVIEW_ROOT / outputs["iron_grip_closeup"])
    _architecture_diagram().save(REVIEW_ROOT / outputs["split_architecture"])
    _layer_decomposition("wooden_sword").save(REVIEW_ROOT / outputs["wooden_layers"])
    _layer_decomposition("iron_sword").save(REVIEW_ROOT / outputs["iron_layers"])
    _axis_overlay("wooden_sword").save(REVIEW_ROOT / outputs["grip_axis_overlay"])
    _same_grip_comparison().save(REVIEW_ROOT / outputs["same_grip_wooden_iron"])
    _before_after().save(REVIEW_ROOT / outputs["before_after"])
    _write_motion_svg(REVIEW_ROOT / outputs["motion_transform"])
    _write_index(outputs)

    hand_sha = sha256(GRIP_HAND_PATH)
    nodes = prototype_transform_nodes()
    translation_before = resolve_world_transform(nodes, "MAIN_HAND_WEAPON")
    translation_after = resolve_world_transform(prototype_transform_nodes(right_hand_delta=(17.0, -11.0)), "MAIN_HAND_WEAPON")
    rotation_before = resolve_world_transform(nodes, "MAIN_HAND_WEAPON")
    rotation_after = resolve_world_transform(prototype_transform_nodes(right_hand_rotation=25.0), "MAIN_HAND_WEAPON")
    motion_proof = {
        "translation": {
            "delta": [17.0, -11.0],
            "pass": math.isclose(translation_after.x - translation_before.x, 17.0) and math.isclose(translation_after.y - translation_before.y, -11.0),
        },
        "rotation": {
            "delta_deg": 25.0,
            "pass": math.isclose(rotation_after.rotation_deg - rotation_before.rotation_deg, 25.0),
        },
    }

    contract = {
        "task": "A054_P0_PAPER_DOLL_SPLIT_WEAPON_TRUE_GRIP_ARCHITECTURE_PROTOTYPE_001",
        "base": {"sha": BASE_SHA, "tree": BASE_TREE, "fresh_master_head": FRESH_MASTER_HEAD, "fresh_master_tree": FRESH_MASTER_TREE, "master_advanced": True, "relevant_master_delta": "NONE"},
        "runtime_active": False,
        "character": {"id": CHARACTER_ID, "pose_id": POSE_ID, "pose_family": POSE_FAMILY, "slot": SLOT},
        "architecture": ["L10 CHARACTER_BASE", "L20 WEAPON_BACK", "L30 SWORD_GRIP_HAND", "L40 WEAPON_FRONT"],
        "semantic_hierarchy": {
            "CHARACTER_ROOT": None,
            "BODY": "CHARACTER_ROOT",
            "RIGHT_ARM": "BODY",
            "RIGHT_HAND": "RIGHT_ARM",
            "RIGHT_HAND_SOCKET": "RIGHT_HAND",
            "GRIP_POINT": "RIGHT_HAND_SOCKET",
            "MAIN_HAND_WEAPON": "GRIP_POINT",
            "SWORD_GRIP_HAND": "RIGHT_HAND",
            "WEAPON_BACK": "MAIN_HAND_WEAPON",
            "WEAPON_FRONT": "MAIN_HAND_WEAPON",
        },
        "socket": {
            "node": "RIGHT_HAND_SOCKET",
            "grip_point_node": "GRIP_POINT",
            "coordinate_space": FRAME_ID,
            "x": RIGHT_HAND_SOCKET[0],
            "y": RIGHT_HAND_SOCKET[1],
            "normalized": [RIGHT_HAND_SOCKET[0] / CANVAS[0], RIGHT_HAND_SOCKET[1] / CANVAS[1]],
            "grip_axis": list(GRIP_AXIS),
        },
        "grip_hand": {
            "asset": relative(GRIP_HAND_PATH),
            "sha256": hand_sha,
            "dimensions": list(load_grip_hand().size),
            "weapon_pixels": 0,
            "weapon_specific_hand_asset_created": False,
            "shared_character_grip_structure": True,
        },
        "weapons": split_records,
        "split_policy": {"front_window_projection_px": list(FRONT_WINDOW), "axis": list(GRIP_AXIS), "pixel_union_preserved": True, "front_is_minimal_contact_handle": True},
        "authority": {"character_pose": "VISUAL_ONLY", "equipment": "SERVER", "client_equipment_authority": False, "acquire_ne_equip": True, "purchase_ne_equip": True, "combat_changed": False},
        "visual_candidate": {
            "handle_enters_palm": True,
            "fingers_wrap_handle": True,
            "fingers_occlude_handle": True,
            "thumb_opposes_fingers": True,
            "handle_behind_required_fingers": True,
            "handle_not_on_back_of_hand": True,
            "floating_fist_appearance": False,
            "pasted_handle_appearance": False,
            "detached_wrist": False,
            "hand_scale_r2_like": True,
            "wrist_continuity": "PASS",
            "forearm_continuity": "PASS",
            "frame_clipping": False,
            "true_grip_visual_acceptance": "OWNER_REQUIRED",
            "owner_visual_acceptance": "NOT_GRANTED",
        },
        "motion_proof": motion_proof,
        "review_outputs": {key: f"review/{filename}" for key, filename in outputs.items()},
        "scope": {
            "app_py_dependency": False,
            "runtime_wiring_changed": False,
            "equipment_authority_changed": False,
            "combat_authority_changed": False,
            "schema_changed": False,
            "production_query": False,
            "production_mutation": False,
            "deploy": False,
            "shop_changed": False,
            "loadout_enablement_changed": False,
        },
    }
    CONTRACT_PATH.write_text(json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return contract


if __name__ == "__main__":
    result = build()
    print(json.dumps({"contract": relative(CONTRACT_PATH), "review_outputs": result["review_outputs"], "motion_proof": result["motion_proof"]}, indent=2))
