"""Prepare the approved right-arm plates as transparent skeletal textures.

This is a technical preparation utility only.  It never paints, fills, or
generates pixels.  The two hand outputs are deliberately selected from the
existing warm hand pixels; the ART_05 front layer therefore cannot carry the
wooden sword pixels shown in that reference plate.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFilter


RGBA = tuple[int, int, int, int]


def _alpha_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    return image.getchannel("A").getbbox()


def _crop_alpha(image: Image.Image) -> Image.Image:
    bbox = _alpha_bbox(image)
    if bbox is None:
        raise ValueError("technical extraction produced no non-transparent pixels")
    return image.crop(bbox)


def _near_white(rgb: Sequence[int]) -> bool:
    return min(rgb) >= 238 and max(rgb) - min(rgb) <= 24


def _loose_white(rgb: Sequence[int]) -> bool:
    return min(rgb) >= 185 and max(rgb) - min(rgb) <= 48


def remove_white_background(image: Image.Image) -> Image.Image:
    """Remove only the border-connected white plate background.

    Keeping the connectivity check prevents pale costume pixels inside the
    subject from being treated as background.  Edge pixels that are visibly a
    white JPEG blend retain a small alpha value; their original RGB values are
    not repainted.
    """

    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    background = bytearray(width * height)
    queue: list[tuple[int, int]] = []

    def enqueue(x: int, y: int) -> None:
        index = y * width + x
        if not background[index]:
            background[index] = 1
            queue.append((x, y))

    for x in range(width):
        for y in (0, height - 1):
            if _near_white(pixels[x, y]) or _loose_white(pixels[x, y]):
                enqueue(x, y)
    for y in range(height):
        for x in (0, width - 1):
            if _near_white(pixels[x, y]) or _loose_white(pixels[x, y]):
                enqueue(x, y)

    cursor = 0
    while cursor < len(queue):
        x, y = queue[cursor]
        cursor += 1
        for next_x, next_y in (
            (x - 1, y),
            (x + 1, y),
            (x, y - 1),
            (x, y + 1),
        ):
            if not (0 <= next_x < width and 0 <= next_y < height):
                continue
            index = next_y * width + next_x
            if not background[index] and _loose_white(pixels[next_x, next_y]):
                background[index] = 1
                queue.append((next_x, next_y))

    output = Image.new("RGBA", rgb.size, (0, 0, 0, 0))
    output_pixels = output.load()
    for y in range(height):
        for x in range(width):
            red, green, blue = pixels[x, y]
            index = y * width + x
            alpha = 0 if background[index] else 255
            if not background[index] and min(red, green, blue) >= 130 and max(red, green, blue) - min(red, green, blue) <= 55:
                adjacent_background = any(
                    0 <= next_x < width
                    and 0 <= next_y < height
                    and background[next_y * width + next_x]
                    for next_x, next_y in (
                        (x - 1, y),
                        (x + 1, y),
                        (x, y - 1),
                        (x, y + 1),
                    )
                )
                if adjacent_background:
                    average = (red + green + blue) / 3
                    alpha = max(1, min(255, round((255 - average) * 3.4)))
            output_pixels[x, y] = (red, green, blue, alpha)
    return _crop_alpha(output)


def _warm_hand_pixel(rgb: Sequence[int], *, relaxed: bool = False) -> bool:
    red, green, blue = rgb
    blue_ratio = blue / max(green, 1)
    if relaxed:
        return (
            red >= 145
            and green >= 95
            and blue >= 55
            and red - green >= 25
            and green - blue >= 8
            and blue_ratio >= 0.56
            and blue_ratio <= 0.80
        )
    return (
        red >= 175
        and green >= 105
        and blue >= 65
        and red - green >= 35
        and green - blue >= 25
        and blue_ratio >= 0.64
        and blue_ratio <= 0.82
    )


def _hand_from_plate(
    image: Image.Image,
    polygons: Iterable[Iterable[tuple[int, int]]],
    *,
    relaxed: bool,
    outline_radius: int,
    forbidden_polygons: Iterable[Iterable[tuple[int, int]]] | None = None,
) -> Image.Image:
    rgb = image.convert("RGB")
    width, height = rgb.size
    region = Image.new("L", rgb.size, 0)
    region_draw = ImageDraw.Draw(region)
    for polygon in polygons:
        region_draw.polygon(list(polygon), fill=255)
    forbidden = Image.new("L", rgb.size, 0)
    forbidden_draw = ImageDraw.Draw(forbidden)
    for polygon in forbidden_polygons or []:
        forbidden_draw.polygon(list(polygon), fill=255)
    region_pixels = region.load()
    forbidden_pixels = forbidden.load()
    skin = Image.new("L", rgb.size, 0)
    skin_pixels = skin.load()
    source_pixels = rgb.load()

    for y in range(height):
        for x in range(width):
            if (
                region_pixels[x, y]
                and not forbidden_pixels[x, y]
                and _warm_hand_pixel(source_pixels[x, y], relaxed=relaxed)
            ):
                skin_pixels[x, y] = 255

    if outline_radius:
        dilated = skin.filter(ImageFilter.MaxFilter(outline_radius * 2 + 1))
        dilated_pixels = dilated.load()
    else:
        dilated_pixels = skin_pixels

    output = Image.new("RGBA", rgb.size, (0, 0, 0, 0))
    output_pixels = output.load()
    for y in range(height):
        for x in range(width):
            if not dilated_pixels[x, y] or forbidden_pixels[x, y]:
                continue
            red, green, blue = source_pixels[x, y]
            if skin_pixels[x, y]:
                output_pixels[x, y] = (red, green, blue, 255)
            elif (
                outline_radius
                and max(red, green, blue) < 145
                and region_pixels[x, y]
            ):
                # Hand contour only.  ART_05 intentionally uses no outline
                # expansion so a dark wooden pixel cannot enter the front
                # attachment.
                output_pixels[x, y] = (red, green, blue, 255)
    return _crop_alpha(output)


def prepare(art01: Path, art02: Path, art03: Path, art04: Path, art05: Path, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)

    upper_arm = remove_white_background(Image.open(art01))
    forearm = remove_white_background(Image.open(art02))
    open_hand = _hand_from_plate(
        Image.open(art03),
        [[
            (585, 735),
            (660, 715),
            (800, 700),
            (1020, 725),
            (1180, 755),
            (1250, 800),
            (1248, 910),
            (1220, 1010),
            (1140, 1110),
            (1020, 1190),
            (880, 1225),
            (740, 1180),
            (625, 1080),
            (535, 950),
            (585, 820),
        ],
        ],
        relaxed=True,
        outline_radius=0,
    )
    grip_back = remove_white_background(Image.open(art04))
    grip_front = _hand_from_plate(
        Image.open(art05),
        [
            [(850, 745), (920, 752), (1000, 775), (1045, 805), (1045, 842), (1010, 865), (950, 850), (900, 825), (860, 800)],
            [(820, 795), (920, 800), (1015, 825), (1045, 860), (1035, 890), (995, 905), (930, 880), (855, 850), (820, 825)],
            [(790, 840), (930, 855), (1020, 885), (1035, 925), (1008, 952), (955, 955), (875, 920), (810, 890), (790, 865)],
            [(770, 895), (915, 915), (1005, 948), (1005, 982), (975, 1015), (900, 1008), (820, 970), (780, 940)],
            [(760, 950), (890, 980), (965, 1015), (955, 1055), (910, 1080), (840, 1045), (785, 1010)],
        ],
        relaxed=True,
        outline_radius=3,
        forbidden_polygons=[
            [(840, 590), (1040, 620), (1050, 740), (980, 790), (840, 740), (795, 665)],
            [(880, 730), (980, 770), (920, 1110), (750, 1085), (805, 950)],
        ],
    )

    outputs = {
        "upper_arm_R": upper_arm,
        "forearm_R": forearm,
        "hand_R_open": open_hand,
        "hand_R_grip_back": grip_back,
        "hand_R_grip_front": grip_front,
    }
    for name, image in outputs.items():
        image.save(output_dir / f"{name}.png", format="PNG", optimize=False, compress_level=9)

    return {
        "output_dir": str(output_dir),
        "assets": {
            name: {
                "path": str(output_dir / f"{name}.png"),
                "dimensions": list(image.size),
                "has_alpha": image.mode == "RGBA" and image.getchannel("A").getextrema()[0] == 0,
            }
            for name, image in outputs.items()
        },
        "art_05_front_policy": "warm hand/finger pixels selected from source polygons; wooden sword pixels excluded",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for index in range(1, 6):
        parser.add_argument(f"--art-{index:02d}", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    report = prepare(
        args.art_01,
        args.art_02,
        args.art_03,
        args.art_04,
        args.art_05,
        args.output_dir,
    )
    print(report)


if __name__ == "__main__":
    main()
