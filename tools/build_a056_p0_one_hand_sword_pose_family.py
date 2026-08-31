"""Build the isolated A056 one-hand sword pose-family visual prototype.

This is static review tooling only.  It deliberately creates a local
composition contract and review pack; it does not wire Hero, touch app.py,
change equipment authority, or enable any product feature.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import html
import json
import math
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageChops, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "docs/planning/a056_p0_one_hand_sword_pose_family"
SOURCE_ROOT = OUT_ROOT / "source_reference"
ASSET_ROOT = OUT_ROOT / "assets"
POSE_ROOT = ASSET_ROOT / "pose"
WEAPON_ROOT = ASSET_ROOT / "weapons"
LAYER_ROOT = ASSET_ROOT / "layers"
REVIEW_ROOT = OUT_ROOT / "review"
CONTRACT_PATH = OUT_ROOT / "a056_p0_contract.json"

CANVAS = (1056, 1408)
CHARACTER = "apprentice"
POSE_ID = "ONE_HAND_SWORD_POSE_V1"
POSE_FAMILY = "ONE_HAND_SWORD"
SLOT = "MAIN_HAND"
SOCKET = (300.0, 650.0)
GRIP_AXIS = (-0.70, -0.7141428429)
GRIP_AXIS_ANGLE = -134.4
GRIP_WIDTH = 42.0

WOOD_SOURCE = SOURCE_ROOT / "apprentice_one_hand_sword_wooden_reference.png"
IRON_SOURCE = SOURCE_ROOT / "apprentice_one_hand_sword_iron_reference.png"
POSE_SOURCE = SOURCE_ROOT / "apprentice_one_hand_sword_weapon_free_reference.png"
DEFAULT_SOURCE = ROOT / "assets/hero/characters/wave2_p1/apprentice_p1.png"

WEAPONS: dict[str, dict[str, Any]] = {
    "wooden_sword": {
        "source": WOOD_SOURCE,
        "display": "wooden_sword",
        "grip_point": (0.47, 0.61),
        "grip_width": 39.0,
        "local_rotation": 0.0,
        "scale": 1.0,
        "color_mode": "warm_brown",
    },
    "iron_sword": {
        "source": IRON_SOURCE,
        "display": "iron_sword",
        "grip_point": (0.47, 0.61),
        "grip_width": 41.0,
        "local_rotation": 0.0,
        "scale": 1.0,
        "color_mode": "silver_steel",
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


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def font(size: int, *, bold: bool = False):
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            from PIL import ImageFont

            return ImageFont.truetype(str(candidate), size=size)
    from PIL import ImageFont

    return ImageFont.load_default()


def rotate_point(x: float, y: float, degrees: float) -> tuple[float, float]:
    r = math.radians(degrees)
    return x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r)


def compose_transform(parent: WorldTransform, local: TransformNode) -> WorldTransform:
    px, py = rotate_point(local.x * parent.scale, local.y * parent.scale, parent.rotation_deg)
    return WorldTransform(
        parent.x + px,
        parent.y + py,
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
        result = (
            WorldTransform(node.x, node.y, node.rotation_deg, node.scale)
            if node.parent is None
            else compose_transform(resolve(node.parent), node)
        )
        visiting.remove(current)
        return result

    return resolve(node_id)


def transform_nodes(*, hand_delta=(0.0, 0.0), hand_rotation=0.0) -> dict[str, TransformNode]:
    """Minimal semantic hierarchy; it is not an animation engine."""

    return {
        "CHARACTER_ROOT": TransformNode("CHARACTER_ROOT", None),
        "BODY": TransformNode("BODY", "CHARACTER_ROOT"),
        "RIGHT_ARM": TransformNode("RIGHT_ARM", "BODY"),
        "RIGHT_HAND": TransformNode(
            "RIGHT_HAND", "RIGHT_ARM", SOCKET[0] + hand_delta[0], SOCKET[1] + hand_delta[1], hand_rotation
        ),
        "RIGHT_HAND_WEAPON_SOCKET": TransformNode("RIGHT_HAND_WEAPON_SOCKET", "RIGHT_HAND"),
        "GRIP_POINT": TransformNode("GRIP_POINT", "RIGHT_HAND_WEAPON_SOCKET"),
        "MAIN_HAND_WEAPON": TransformNode("MAIN_HAND_WEAPON", "GRIP_POINT"),
    }


def _is_background(pixel: tuple[int, int, int]) -> bool:
    r, g, b = pixel
    # Image-generation preview grids are not perfectly neutral; some squares
    # carry a faint warm tint such as (255, 255, 231).  Character skin and
    # cloth remain materially more chromatic than this local background key.
    return max(pixel) - min(pixel) <= 40 and min(pixel) >= 220


def _checkerboard_alpha(rgb: Image.Image) -> Image.Image:
    """Remove only the light neutral checkerboard connected to the frame."""

    rgb = rgb.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    seen = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def push(x: int, y: int) -> None:
        index = y * width + x
        if not seen[index] and _is_background(pixels[x, y]):
            seen[index] = 1
            queue.append((x, y))

    for x in range(width):
        push(x, 0)
        push(x, height - 1)
    for y in range(height):
        push(0, y)
        push(width - 1, y)
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                push(nx, ny)

    alpha = Image.new("L", rgb.size, 255)
    alpha_pixels = alpha.load()
    for index, value in enumerate(seen):
        if value:
            alpha_pixels[index % width, index // width] = 0
    # Keep a small antialias fringe around the rendered character while making
    # the checkerboard genuinely transparent.
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.35))
    output = rgb.convert("RGBA")
    output.putalpha(alpha)
    return output


def load_pose(path: Path) -> Image.Image:
    if not path.is_file():
        raise FileNotFoundError(path)
    source = _checkerboard_alpha(Image.open(path))
    return source.resize(CANVAS, Image.Resampling.LANCZOS)


def _weapon_scope(size: tuple[int, int]) -> Image.Image:
    """Broad sword-only search zone in source coordinates, excluding the torso."""

    width, height = size
    sx, sy = width / 1086.0, height / 1448.0
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    points = [
        (24 * sx, 300 * sy),
        (53 * sx, 292 * sy),
        (317 * sx, 575 * sy),
        (384 * sx, 730 * sy),
        (334 * sx, 754 * sy),
        (251 * sx, 665 * sy),
        (213 * sx, 611 * sy),
    ]
    draw.polygon(points, fill=255)
    return mask


def _skin_mask(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    mask = Image.new("L", rgb.size, 0)
    src = rgb.load()
    dst = mask.load()
    for y in range(rgb.height):
        for x in range(rgb.width):
            r, g, b = src[x, y]
            if r > 145 and r > g + 22 and g > b + 12 and g > 66:
                dst[x, y] = 255
    return mask


def _hand_region(size: tuple[int, int]) -> Image.Image:
    width, height = size
    sx, sy = width / 1086.0, height / 1448.0
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    # Character-right sleeve, forearm, palm and wrapped fingers.  This is a
    # localized source region, not a second screen-space authority.
    points = [
        (320 * sx, 563 * sy),
        (459 * sx, 575 * sy),
        (491 * sx, 692 * sy),
        (451 * sx, 820 * sy),
        (385 * sx, 813 * sy),
        (327 * sx, 768 * sy),
        (256 * sx, 730 * sy),
        (248 * sx, 642 * sy),
    ]
    draw.polygon(points, fill=255)
    return mask


def _sword_color_mask(image: Image.Image, weapon_id: str) -> Image.Image:
    """Extract only the sword silhouette from the generated reference.

    The references are RGB images with a checkerboard preview baked into the
    file.  A broad colour key mistakes that preview for the steel blade and
    can paint a white hand-shaped hole into the result.  The source-local
    silhouette below is intentionally narrow and is used only by this static
    prototype tool; it is not a runtime coordinate table.
    """

    width, height = image.size
    sx, sy = width / 1086.0, height / 1448.0
    out = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(out)
    def points(values: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(x * sx, y * sy) for x, y in values]

    if weapon_id == "wooden_sword":
        draw.polygon(points([(24, 300), (52, 300), (283, 584), (264, 614)]), fill=255)
        draw.polygon(points([(224, 584), (319, 568), (340, 610), (240, 654)]), fill=255)
        draw.polygon(points([(273, 608), (311, 600), (377, 710), (338, 737)]), fill=255)
    else:
        draw.polygon(points([(29, 306), (51, 304), (279, 596), (253, 620)]), fill=255)
        draw.polygon(points([(225, 596), (318, 574), (335, 612), (241, 648)]), fill=255)
        draw.polygon(points([(272, 615), (305, 607), (359, 711), (332, 735)]), fill=255)

    source_alpha = _checkerboard_alpha(image).getchannel("A")
    return ImageChops.multiply(out, source_alpha)


def _broad_sword_mask(image: Image.Image) -> Image.Image:
    """Removal-only mask that covers the entire reference sword silhouette."""

    width, height = image.size
    sx, sy = width / 1086.0, height / 1448.0
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)

    def points(values: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(x * sx, y * sy) for x, y in values]

    draw.polygon(points([(16, 286), (65, 286), (305, 570), (294, 646), (222, 646)]), fill=255)
    draw.polygon(points([(204, 563), (347, 548), (363, 628), (216, 676)]), fill=255)
    draw.polygon(points([(250, 581), (340, 575), (402, 751), (318, 777)]), fill=255)
    return mask


def _source_weapon_layer(source: Image.Image, weapon_id: str) -> Image.Image:
    mask = _sword_color_mask(source, weapon_id)
    layer = source.copy()
    layer.putalpha(mask)
    return layer.resize(CANVAS, Image.Resampling.LANCZOS)


def _localized_grip_layer(
    source: Image.Image, weapon_id: str, *, source_contains_weapon: bool = True
) -> Image.Image:
    region = _hand_region(source.size)
    visible = _checkerboard_alpha(source).getchannel("A")
    # Retain only visible character pixels in the localized sleeve/forearm/
    # hand region.  In particular, do not use the region polygon itself as an
    # alpha channel: the input review image has a visible checkerboard in
    # enclosed transparent gaps.
    keep = ImageChops.multiply(region, visible)
    # Enclosed gaps between the blade/hand/sleeve can isolate a checkerboard
    # island from the frame flood-fill.  They are not character pixels and
    # must never become an opaque white wedge in a layer.
    keep_pixels = keep.load()
    source_pixels = source.convert("RGB").load()
    for y in range(source.height):
        for x in range(source.width):
            if keep_pixels[x, y] and _is_background(source_pixels[x, y]):
                keep_pixels[x, y] = 0
    if source_contains_weapon:
        weapon = _sword_color_mask(source, weapon_id)
        keep = ImageChops.subtract(keep, weapon)
    layer = source.copy()
    layer.putalpha(keep)
    return layer.resize(CANVAS, Image.Resampling.LANCZOS)


def _weapon_free_base(
    source: Image.Image, weapon_id: str, *, source_contains_weapon: bool = True
) -> Image.Image:
    source = source.copy()
    alpha = _checkerboard_alpha(source).getchannel("A")
    if source_contains_weapon:
        # Removal is intentionally broader than the independently extracted
        # weapon layer.  This prevents wooden reference pixels from leaking
        # when the same pose base is recomposed with the iron weapon.
        alpha = ImageChops.subtract(alpha, _broad_sword_mask(source))
    # A neutral checkerboard island can be enclosed by the generated sword
    # and arm, so it may survive the border flood-fill.  The approved pose
    # itself is chromatic; remove those preview pixels before writing the
    # weapon-free character layer.
    alpha_pixels = alpha.load()
    source_pixels = source.convert("RGB").load()
    for y in range(source.height):
        for x in range(source.width):
            if alpha_pixels[x, y] and _is_background(source_pixels[x, y]):
                alpha_pixels[x, y] = 0
    source.putalpha(alpha)
    return source.resize(CANVAS, Image.Resampling.LANCZOS)


def _split_weapon(full: Image.Image) -> tuple[Image.Image, Image.Image]:
    """Use a local contact window; the two pieces still form one weapon."""

    back = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    front = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    source = full.load()
    bpx = back.load()
    fpx = front.load()
    # Contact window around the hand.  It is intentionally broad enough to
    # place the handle behind fingers while leaving one continuous silhouette.
    for y in range(CANVAS[1]):
        for x in range(CANVAS[0]):
            if source[x, y][3] == 0:
                continue
            dx, dy = x - SOCKET[0], y - SOCKET[1]
            projection = dx * GRIP_AXIS[0] + dy * GRIP_AXIS[1]
            perpendicular = abs(dx * (-GRIP_AXIS[1]) + dy * GRIP_AXIS[0])
            if -58 <= projection <= 58 and perpendicular <= 34:
                fpx[x, y] = source[x, y]
            else:
                bpx[x, y] = source[x, y]
    return back, front


def _compose(base: Image.Image, hand: Image.Image, back: Image.Image, front: Image.Image) -> Image.Image:
    result = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    for layer in (base, back, hand, front):
        result.alpha_composite(layer)
    return result


def _on_background(image: Image.Image, size: tuple[int, int], *, bg=(250, 247, 239, 255)) -> Image.Image:
    source = image.convert("RGBA")
    source.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, bg)
    canvas.alpha_composite(source, ((size[0] - source.width) // 2, (size[1] - source.height) // 2))
    return canvas


def _card(image: Image.Image, title: str, subtitle: str, *, body=(360, 480)) -> Image.Image:
    content = _on_background(image, body)
    width, height = content.width + 36, content.height + 92
    card = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=14, outline=(177, 194, 191), width=2)
    draw.text((18, 12), title, font=font(20, bold=True), fill=(27, 61, 72))
    draw.text((18, 40), subtitle, font=font(14), fill=(91, 109, 107))
    card.alpha_composite(content, (18, 72))
    return card


def _grid(cards: list[Image.Image], columns: int, heading: str, *, footer: str | None = None) -> Image.Image:
    gap = 18
    rows = math.ceil(len(cards) / columns)
    cw = max(card.width for card in cards)
    ch = max(card.height for card in cards)
    height = rows * ch + (rows + 1) * gap + 70 + (45 if footer else 0)
    canvas = Image.new("RGBA", (columns * cw + (columns + 1) * gap, height), (243, 239, 230, 255))
    draw = ImageDraw.Draw(canvas)
    draw.text((gap, 19), heading, font=font(28, bold=True), fill=(28, 63, 73))
    for index, card in enumerate(cards):
        x = gap + (index % columns) * (cw + gap)
        y = 70 + gap + (index // columns) * (ch + gap)
        canvas.alpha_composite(card, (x, y))
    if footer:
        draw.text((gap, height - 37), footer, font=font(18, bold=True), fill=(143, 68, 48))
    return canvas


def _grip_crop(image: Image.Image, size=(820, 820)) -> Image.Image:
    crop = image.crop((205, 525, 485, 825))
    return crop.resize(size, Image.Resampling.LANCZOS)


def _full_right_arm(image: Image.Image) -> Image.Image:
    crop = image.crop((175, 410, 535, 860))
    return crop.resize((720, 900), Image.Resampling.LANCZOS)


def _annotated_grip(image: Image.Image, title: str) -> Image.Image:
    canvas = _on_background(_grip_crop(image, (900, 900)), (900, 980), bg=(255, 255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    anchor = ((SOCKET[0] - 205) / 280 * 900, (SOCKET[1] - 525) / 300 * 900)
    draw.ellipse((anchor[0] - 14, anchor[1] - 14, anchor[0] + 14, anchor[1] + 14), fill=(26, 160, 112), outline=(255, 255, 255), width=3)
    draw.line((anchor[0], anchor[1], anchor[0] + GRIP_AXIS[0] * 250, anchor[1] + GRIP_AXIS[1] * 250), fill=(28, 105, 190), width=7)
    draw.text((24, 22), title, font=font(25, bold=True), fill=(27, 84, 83))
    draw.text((24, 58), f"socket={SOCKET} · axis={GRIP_AXIS} · width={GRIP_WIDTH}px", font=font(18), fill=(44, 83, 135))
    return canvas


def _layer_decomposition(layers: dict[str, Image.Image], weapon_id: str) -> Image.Image:
    labels = [
        ("L10 CHARACTER_BASE", "full-limb pose / identity", layers["CHARACTER_BASE"]),
        ("L20 WEAPON_BACK", "blade + rear handle", layers["WEAPON_BACK"]),
        ("L30 GRIP_HAND", "shared palm / fingers / wrist", layers["GRIP_HAND"]),
        ("L40 WEAPON_FRONT", "contact handle segment", layers["WEAPON_FRONT"]),
        ("FINAL COMPOSITE", "same pose family + swapped weapon", layers["FINAL"]),
    ]
    cards = [_card(image, title, subtitle, body=(220, 294)) for title, subtitle, image in labels]
    return _grid(cards, 5, f"A056-P0 · {weapon_id} · independent layer composition", footer="TECHNICAL CANDIDATE · OWNER VISUAL ACCEPTANCE REQUIRED")


def _side_by_side(wooden: Image.Image, iron: Image.Image) -> Image.Image:
    cards = [
        _card(wooden, "WOODEN SWORD", "ONE_HAND_SWORD_POSE_V1", body=(430, 574)),
        _card(iron, "IRON SWORD", "ONE_HAND_SWORD_POSE_V1", body=(430, 574)),
    ]
    return _grid(cards, 2, "A056-P0 · same full-limb pose family · independent weapon swap")


def _pose_default(default: Image.Image, pose: Image.Image) -> Image.Image:
    cards = [
        _card(default, "DEFAULT POSE", "canonical apprentice base", body=(430, 574)),
        _card(pose, "ONE_HAND_SWORD_POSE_V1", "right shoulder → hand action", body=(430, 574)),
    ]
    return _grid(cards, 2, "A056-P0 · pose family vs default presentation")


def _swap_proof(wooden: Image.Image, iron: Image.Image) -> Image.Image:
    image = Image.new("RGBA", (1400, 760), (247, 244, 236, 255))
    draw = ImageDraw.Draw(image)
    draw.text((34, 22), "POSE FAMILY SWAP PROOF", font=font(32, bold=True), fill=(28, 63, 73))
    draw.text((36, 66), "Same apprentice full-limb action · only the independent weapon layer changes", font=font(18), fill=(91, 72, 61))
    for x, item, render in ((56, "wooden_sword", wooden), (730, "iron_sword", iron)):
        body = _on_background(render, (520, 610))
        image.alpha_composite(body, (x, 112))
        draw.text((x + 18, 704), f"{item}  ·  pose_id={POSE_ID}", font=font(18, bold=True), fill=(32, 80, 82))
    draw.rounded_rectangle((430, 724, 970, 752), radius=10, fill=(219, 239, 227, 255), outline=(54, 127, 103), width=2)
    draw.text((463, 729), "SHARED POSE FAMILY / SWAPPABLE WEAPON", font=font(16, bold=True), fill=(37, 95, 77))
    return image


def _architecture_diagram() -> Image.Image:
    width, height = 1600, 720
    image = Image.new("RGBA", (width, height), (247, 244, 236, 255))
    draw = ImageDraw.Draw(image)
    draw.text((38, 22), "A056-P0 · PAPER DOLL LAYER CONTRACT", font=font(34, bold=True), fill=(27, 63, 73))
    draw.text((40, 69), "Static prototype only · weapon identity remains independent from the character pose", font=font(20), fill=(139, 68, 47))
    boxes = [
        ("L10", "CHARACTER_BASE", "full-limb apprentice\npose + identity", (45, 160, 315, 500), (222, 238, 232)),
        ("L20", "WEAPON_BACK", "blade / guard /\nrear handle", (360, 160, 630, 500), (225, 232, 247)),
        ("L30", "GRIP_HAND", "localized palm +\nfingers + wrist", (675, 160, 945, 500), (249, 225, 201)),
        ("L40", "WEAPON_FRONT", "minimal contact\nhandle segment", (990, 160, 1260, 500), (242, 220, 215)),
        ("FINAL", "COMPOSITE", "natural one-hand\nsword action", (1305, 160, 1555, 500), (215, 239, 226)),
    ]
    for idx, (code, title, detail, rect, color) in enumerate(boxes):
        x1, y1, x2, y2 = rect
        draw.rounded_rectangle(rect, radius=18, fill=color, outline=(52, 91, 95), width=3)
        draw.text((x1 + 18, y1 + 18), code, font=font(22, bold=True), fill=(25, 69, 76))
        draw.text((x1 + 18, y1 + 60), title, font=font(18, bold=True), fill=(40, 72, 76))
        draw.multiline_text((x1 + 18, y1 + 112), detail, font=font(18), fill=(70, 83, 80), spacing=6)
        if code in ("L20", "L40"):
            draw.line((x1 + 68, y1 + 302, x1 + 205, y1 + 175), fill=(92, 54, 31), width=18 if code == "L20" else 11)
            draw.ellipse((x1 + 175, y1 + 160, x1 + 224, y1 + 208), fill=(120, 75, 42))
        if code == "L30":
            draw.ellipse((x1 + 100, y1 + 220, x1 + 178, y1 + 320), fill=(237, 150, 110), outline=(104, 68, 53), width=3)
            draw.line((x1 + 139, y1 + 320, x1 + 139, y1 + 374), fill=(104, 68, 53), width=8)
            draw.text((x1 + 30, y1 + 414), "fingers in front", font=font(16, bold=True), fill=(129, 62, 43))
        if idx < len(boxes) - 1:
            draw.line((x2 + 8, 330, x2 + 42, 330), fill=(42, 117, 106), width=5)
            draw.polygon(((x2 + 42, 330), (x2 + 27, 318), (x2 + 27, 342)), fill=(42, 117, 106))
    draw.rounded_rectangle((45, 580, 1555, 668), radius=16, fill=(255, 255, 255, 255), outline=(181, 193, 188), width=2)
    draw.text((78, 604), "SEMANTIC ACTION", font=font(22, bold=True), fill=(26, 85, 83))
    draw.text((78, 638), "CHARACTER_ROOT  →  RIGHT_ARM  →  RIGHT_HAND  →  RIGHT_HAND_WEAPON_SOCKET  →  GRIP_POINT  →  MAIN_HAND_WEAPON", font=font(18, bold=True), fill=(40, 88, 108))
    return image


def _motion_svg(path: Path) -> None:
    path.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720">
<rect width="1200" height="720" fill="#f7f4ec"/>
<text x="40" y="54" font-family="Arial" font-size="32" font-weight="700" fill="#1b3f49">A056-P0 · motion-ready semantic transform proof</text>
<text x="40" y="90" font-family="Arial" font-size="18" fill="#8b442f">Technical evidence only · animation is not implemented · Owner visual acceptance required</text>
<g font-family="Arial" font-size="23" font-weight="700" text-anchor="middle">
<rect x="390" y="130" width="420" height="62" rx="14" fill="#d4e9df" stroke="#2e7a71" stroke-width="3"/><text x="600" y="169" fill="#214c4d">CHARACTER_ROOT</text>
<rect x="430" y="250" width="340" height="62" rx="14" fill="#e4eaf7" stroke="#536e9b" stroke-width="3"/><text x="600" y="289" fill="#31486f">RIGHT_ARM</text>
<rect x="450" y="370" width="300" height="62" rx="14" fill="#f8dfbb" stroke="#ac7049" stroke-width="3"/><text x="600" y="409" fill="#744b32">RIGHT_HAND</text>
<rect x="400" y="490" width="400" height="62" rx="14" fill="#f1d1ca" stroke="#9e5f54" stroke-width="3"/><text x="600" y="529" fill="#713e38">SOCKET / GRIP_POINT</text>
<rect x="350" y="610" width="500" height="62" rx="14" fill="#d9e8f5" stroke="#3b76a8" stroke-width="3"/><text x="600" y="649" fill="#24537d">MAIN_HAND_WEAPON</text>
</g>
<g stroke="#2e7a71" stroke-width="5" fill="none"><path d="M600 192 V250"/><path d="M600 312 V370"/><path d="M600 432 V490"/><path d="M600 552 V610"/></g>
<g font-family="Arial" font-size="19" fill="#3e5556"><text x="885" y="220">PARENT TRANSLATION</text><text x="885" y="250">RIGHT_HAND Δx / Δy</text><text x="885" y="280">→ socket follows</text><text x="885" y="310">→ grip follows</text><text x="885" y="340">→ weapon follows</text><text x="885" y="440">PARENT ROTATION</text><text x="885" y="470">RIGHT_HAND θ</text><text x="885" y="500">→ local grip preserved</text><text x="885" y="530">→ weapon orientation preserved</text></g>
</svg>""",
        encoding="utf-8",
    )


def _write_index(files: Iterable[tuple[str, str]]) -> None:
    rows = []
    for label, name in files:
        rows.append(f'<figure><figcaption>{html.escape(label)}</figcaption><img src="{html.escape(name)}" alt="{html.escape(label)}"></figure>')
    (REVIEW_ROOT / "index.html").write_text(
        """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>A056-P0 one-hand sword pose family</title><style>
body{font-family:Arial,sans-serif;background:#f7f4ec;color:#1b3f49;margin:18px}h1{margin:0 0 6px}p{color:#6f4a3c}.notice{background:#fff0dc;border-left:6px solid #c26b42;padding:14px;border-radius:8px;margin:14px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:16px}figure{background:#fff;border:1px solid #b6c4bf;border-radius:12px;padding:12px;margin:0}figcaption{font-weight:700;margin-bottom:8px}img{max-width:100%;height:auto;display:block}.first{border:3px solid #2f8275}</style></head><body><h1>A056-P0 · Canonical One-Hand Sword Pose Family</h1><div class="notice"><strong>TECHNICAL CANDIDATE · OWNER VISUAL ACCEPTANCE REQUIRED</strong><br>RUNTIME_ACTIVE=NO · SOURCE PROTOTYPE ONLY · app.py and equipment authority unchanged.</div><p>Character: apprentice · Pose: ONE_HAND_SWORD_POSE_V1 · compatible prototype weapons: wooden_sword, iron_sword. The first two images are unannotated normal-size player-facing renders.</p><div class="grid">"""
        + "\n".join(rows)
        + "</div></body></html>",
        encoding="utf-8",
    )


def build() -> dict[str, Any]:
    for required in (POSE_SOURCE, WOOD_SOURCE, IRON_SOURCE, DEFAULT_SOURCE):
        if not required.is_file():
            raise FileNotFoundError(required)
    for directory in (POSE_ROOT, WEAPON_ROOT, LAYER_ROOT, REVIEW_ROOT):
        directory.mkdir(parents=True, exist_ok=True)

    pose_source = Image.open(POSE_SOURCE).convert("RGB")
    wood_source = Image.open(WOOD_SOURCE).convert("RGB")
    iron_source = Image.open(IRON_SOURCE).convert("RGB")
    default = Image.open(DEFAULT_SOURCE).convert("RGBA")

    # The weapon-free full-limb render is the pose source.  The grip-hand
    # layer is extracted once and reused for both weapons, while weapon layers
    # are independently extracted from their respective references.  Keeping
    # the pose source weapon-free avoids exposing a wood-shaped hole when the
    # same character structure is recomposed with the iron weapon.
    base = _weapon_free_base(pose_source, "wooden_sword", source_contains_weapon=False)
    hand = _localized_grip_layer(pose_source, "wooden_sword", source_contains_weapon=False)
    wood_full = _source_weapon_layer(wood_source, "wooden_sword")
    iron_full = _source_weapon_layer(iron_source, "iron_sword")
    wood_back, wood_front = _split_weapon(wood_full)
    iron_back, iron_front = _split_weapon(iron_full)
    wooden = _compose(base, hand, wood_back, wood_front)
    iron = _compose(base, hand, iron_back, iron_front)

    # Materialize only prototype-scoped assets.  No canonical runtime files
    # are overwritten.
    base_path = POSE_ROOT / "apprentice_one_hand_sword_pose_v1_base.png"
    hand_path = POSE_ROOT / "apprentice_one_hand_sword_pose_v1_grip_hand.png"
    base.save(base_path, format="PNG")
    hand.save(hand_path, format="PNG")
    layer_paths: dict[str, dict[str, str]] = {}
    for weapon_id, back, front, final in (
        ("wooden_sword", wood_back, wood_front, wooden),
        ("iron_sword", iron_back, iron_front, iron),
    ):
        weapon_dir = WEAPON_ROOT / weapon_id
        weapon_dir.mkdir(parents=True, exist_ok=True)
        full_path = weapon_dir / f"{weapon_id}_prototype_full.png"
        back_path = weapon_dir / f"{weapon_id}_prototype_back.png"
        front_path = weapon_dir / f"{weapon_id}_prototype_front.png"
        full = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        full.alpha_composite(back)
        full.alpha_composite(front)
        full.save(full_path, format="PNG")
        back.save(back_path, format="PNG")
        front.save(front_path, format="PNG")
        layer_paths[weapon_id] = {
            "full": rel(full_path),
            "back": rel(back_path),
            "front": rel(front_path),
            "full_sha256": sha256(full_path),
            "back_sha256": sha256(back_path),
            "front_sha256": sha256(front_path),
        }

    final_paths = {
        "wooden": REVIEW_ROOT / "01_apprentice_one_hand_sword_wooden_normal.png",
        "iron": REVIEW_ROOT / "02_apprentice_one_hand_sword_iron_normal.png",
        "side": REVIEW_ROOT / "03_wooden_vs_iron_side_by_side.png",
        "wood_close": REVIEW_ROOT / "04_true_grip_closeup_wooden.png",
        "iron_close": REVIEW_ROOT / "05_true_grip_closeup_iron.png",
        "arm": REVIEW_ROOT / "06_full_right_arm_pose.png",
        "default_compare": REVIEW_ROOT / "07_pose_vs_default_comparison.png",
        "swap": REVIEW_ROOT / "08_pose_family_swap_proof.png",
        "layers": REVIEW_ROOT / "09_layer_decomposition.png",
        "axis": REVIEW_ROOT / "10_grip_semantic_overlay.png",
        "motion": REVIEW_ROOT / "11_motion_ready_transform_proof.svg",
    }
    # Keep the two primary review images opaque and presentation-ready so a
    # transparent PNG is not rendered as a black silhouette by a browser or
    # tablet previewer.  The underlying prototype layers remain transparent.
    _on_background(wooden, (840, 1120)).save(final_paths["wooden"], format="PNG")
    _on_background(iron, (840, 1120)).save(final_paths["iron"], format="PNG")
    _side_by_side(wooden, iron).save(final_paths["side"], format="PNG")
    _on_background(_grip_crop(wooden), (900, 900)).save(final_paths["wood_close"], format="PNG")
    _on_background(_grip_crop(iron), (900, 900)).save(final_paths["iron_close"], format="PNG")
    _on_background(_full_right_arm(wooden), (720, 900)).save(final_paths["arm"], format="PNG")
    _pose_default(default, wooden).save(final_paths["default_compare"], format="PNG")
    _swap_proof(wooden, iron).save(final_paths["swap"], format="PNG")
    _layer_decomposition(
        {"CHARACTER_BASE": base, "WEAPON_BACK": wood_back, "GRIP_HAND": hand, "WEAPON_FRONT": wood_front, "FINAL": wooden},
        "wooden_sword",
    ).save(final_paths["layers"], format="PNG")
    _annotated_grip(wooden, "RIGHT_HAND_WEAPON_SOCKET / GRIP_POINT / GRIP_AXIS").save(final_paths["axis"], format="PNG")
    _architecture_diagram().save(REVIEW_ROOT / "12_layer_architecture.png", format="PNG")
    _motion_svg(final_paths["motion"])

    review_files = [
        ("01 · wooden sword · unannotated normal player-facing render", final_paths["wooden"].name),
        ("02 · iron sword · unannotated normal player-facing render", final_paths["iron"].name),
        ("03 · wooden vs iron · same pose family", final_paths["side"].name),
        ("04 · wooden sword · true-grip close-up", final_paths["wood_close"].name),
        ("05 · iron sword · true-grip close-up", final_paths["iron_close"].name),
        ("06 · full right-arm pose", final_paths["arm"].name),
        ("07 · default vs pose family", final_paths["default_compare"].name),
        ("08 · pose-family weapon swap proof", final_paths["swap"].name),
        ("09 · independent layer decomposition", final_paths["layers"].name),
        ("10 · grip semantic overlay", final_paths["axis"].name),
        ("11 · motion-ready transform proof", final_paths["motion"].name),
        ("12 · paper-doll layer architecture", "12_layer_architecture.png"),
    ]
    _write_index(review_files)

    nodes = transform_nodes()
    translated = resolve_world_transform(transform_nodes(hand_delta=(23.0, -17.0)), "MAIN_HAND_WEAPON")
    rotated = resolve_world_transform(transform_nodes(hand_rotation=19.0), "MAIN_HAND_WEAPON")
    contract = {
        "task": "A056_P0_CANONICAL_ONE_HAND_SWORD_POSE_FAMILY_VISUAL_PROTOTYPE_001",
        "character": CHARACTER,
        "pose_id": POSE_ID,
        "pose_family": POSE_FAMILY,
        "slot": SLOT,
        "runtime_active": False,
        "visual_acceptance": "OWNER_REQUIRED",
        "character_pose_asset": rel(base_path),
        "grip_hand_asset": rel(hand_path),
        "character_pose_source": rel(POSE_SOURCE),
        "character_pose_source_sha256": sha256(POSE_SOURCE),
        "default_pose_asset": rel(DEFAULT_SOURCE),
        "right_hand_weapon_socket": list(SOCKET),
        "grip_axis": list(GRIP_AXIS),
        "grip_axis_angle_deg": GRIP_AXIS_ANGLE,
        "grip_width_px": GRIP_WIDTH,
        "layers": ["L10_CHARACTER_BASE", "L20_WEAPON_BACK", "L30_SWORD_GRIP_HAND", "L40_WEAPON_FRONT"],
        "weapon_baked_into_character": False,
        "same_pose_family_used": True,
        "weapons": {
            weapon_id: {
                "slot": SLOT,
                "pose_family": POSE_FAMILY,
                "grip_point_normalized": list(spec["grip_point"]),
                "grip_width_px": spec["grip_width"],
                "local_rotation_deg": spec["local_rotation"],
                "scale": spec["scale"],
                "independent_layer": layer_paths[weapon_id],
                "compatible": True,
            }
            for weapon_id, spec in WEAPONS.items()
        },
        "transform_proof": {
            "base_main_hand_weapon": resolve_world_transform(nodes, "MAIN_HAND_WEAPON").__dict__,
            "translated_main_hand_weapon": translated.__dict__,
            "rotated_main_hand_weapon": rotated.__dict__,
            "translation_proof": translated.x != SOCKET[0] and translated.y != SOCKET[1],
            "rotation_proof": rotated.rotation_deg == 19.0,
        },
        "authority": {
            "equipment_authority": "server-owned equipped state",
            "client_equipment_authority": False,
            "acquire_triggers_pose": False,
            "purchase_triggers_pose": False,
            "owned_but_unequipped_hidden": True,
            "unsupported_equipment_safe": True,
        },
        "combat_authority_changed": False,
        "source_reference_sha256": {
            "wooden_reference": sha256(WOOD_SOURCE),
            "iron_reference": sha256(IRON_SOURCE),
        },
        "review_pack": [name for _, name in review_files],
    }
    CONTRACT_PATH.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return contract


if __name__ == "__main__":
    build()
