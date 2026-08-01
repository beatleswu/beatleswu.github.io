"""Compose Owner-review contact sheets from real E10 runtime captures."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


BG = "#24160d"
GOLD = "#e8b94f"
PAPER = "#fff2c8"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/msjh.ttc"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def fitted(image: Image.Image, width: int, height: int) -> Image.Image:
    copy = image.copy()
    copy.thumbnail((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), BG)
    canvas.paste(copy, ((width - copy.width) // 2, (height - copy.height) // 2))
    return canvas


def sheet(output: Path, title: str, items: list[tuple[str, Image.Image]], columns: int = 2) -> None:
    tile_width = 720 if columns <= 2 else 560
    tile_height = 430
    header = 72
    label_height = 42
    rows = (len(items) + columns - 1) // columns
    canvas = Image.new("RGB", (tile_width * columns, header + rows * (tile_height + label_height)), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 18), title, fill=PAPER, font=font(28))
    for index, (label, image) in enumerate(items):
        column = index % columns
        row = index // columns
        x = column * tile_width
        y = header + row * (tile_height + label_height)
        canvas.paste(fitted(image, tile_width, tile_height), (x, y))
        draw.rectangle((x, y, x + tile_width - 1, y + tile_height - 1), outline=GOLD, width=3)
        draw.text((x + 14, y + tile_height + 8), label, fill=PAPER, font=font(20))
    canvas.save(output, "PNG", optimize=True)


def opened(path: Path, crop: tuple[int, int, int, int] | None = None) -> Image.Image:
    with Image.open(path) as image:
        converted = image.convert("RGB")
    return converted.crop(crop) if crop else converted


def image_identity(path: Path) -> dict[str, object]:
    with Image.open(path) as image:
        return {
            "path": str(path),
            "format": image.format,
            "dimensions": [image.width, image.height],
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--clean-source", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()

    evidence = args.evidence.resolve()
    repo = args.repo.resolve()
    p = lambda name: evidence / name

    desktop = opened(p("desktop-1920x1080-closed-zh.png"))
    desktop_open = opened(p("desktop-1920x1080-drawer-open-en.png"))
    desktop_current = opened(p("desktop-1920x1080-current-zone-en.png"))
    desktop_current_zh = opened(p("desktop-1920x1080-current-zone-zh.png"))
    desktop_selected_zh = opened(p("desktop-1920x1080-selected-zone-zh.png"))
    desktop_locked_en = opened(p("desktop-1920x1080-locked-zone-en.png"))
    desktop_locked = opened(p("desktop-1920x1080-locked-zone-zh.png"))
    desktop_completed = opened(p("desktop-1920x1080-completed-zone-en.png"))
    desktop_skipped = opened(p("desktop-1920x1080-skipped-zone-zh.png"))
    placement_high = opened(p("desktop-1920x1080-placement-high-zh.png"))
    desktop_1440 = opened(p("desktop-1440x900-closed-en.png"))

    sheet(p("phase-a-panel-collision-contact-sheet.png"), "Phase A: stable zone information row", [
        ("Current Zone / English", desktop_current.crop((1440, 150, 1920, 800))),
        ("Current Zone / Traditional Chinese", desktop_current_zh.crop((1440, 150, 1920, 800))),
        ("Selected Zone / English", desktop_open.crop((1440, 150, 1920, 800))),
        ("Selected Zone / Traditional Chinese", desktop_selected_zh.crop((1440, 150, 1920, 800))),
        ("Locked / English", desktop_locked_en.crop((1440, 150, 1920, 800))),
        ("Locked / Traditional Chinese", desktop_locked.crop((1440, 150, 1920, 800))),
        ("Completed / replay", desktop_completed.crop((1440, 150, 1920, 800))),
        ("Skipped by placement / review", desktop_skipped.crop((1440, 150, 1920, 800))),
    ], columns=2)
    sheet(p("phase-a-desktop-1440-immersive-contact-sheet.png"), "Phase A: Desktop 1440 immersive stage", [
        ("Closed", desktop_1440),
        ("Panel open", opened(p("desktop-1440x900-panel-open-en.png"))),
        ("All Features", opened(p("desktop-1440x900-all-features-zh.png"))),
        ("Settings", opened(p("desktop-1440x900-settings-en.png"))),
    ], columns=2)

    sheet(p("owner-reference-comparison-contact-sheet.png"), "Owner reference | Runtime 1920 | Runtime 1440", [
        ("Owner reference", opened(args.reference)),
        ("Runtime Desktop 1920", desktop),
        ("Runtime Desktop 1440", desktop_1440),
    ], columns=3)
    sheet(p("desktop-open-closed-contact-sheet.png"), "Desktop immersive map", [
        ("1920 closed zh", desktop),
        ("1920 zone panel open en", desktop_open),
    ])
    sheet(p("left-floating-badges-closeup.png"), "Five floating RPG badges", [
        ("Hero / Equipment / Backpack / Spirit / Shop", desktop.crop((0, 130, 220, 900))),
    ], columns=1)
    sheet(p("bottom-medallion-dock-closeup.png"), "Adventure progress, five-action dock, primary CTA", [
        ("Desktop bottom HUD", desktop.crop((20, 885, 1900, 1080))),
    ], columns=1)
    sheet(p("player-title-utility-closeup.png"), "Player identity, title plaque, utility medallions", [
        ("Desktop top HUD", desktop.crop((20, 20, 1900, 155))),
        ("Runtime avatar fallback", opened(p("desktop-1440x900-avatar-fallback-zh.png"), (20, 20, 420, 155))),
    ])
    sheet(p("right-zone-panel-open-closed-contact-sheet.png"), "Overlay zone panel does not reflow the map", [
        ("Closed handle", desktop.crop((1360, 130, 1920, 900))),
        ("Open selected-zone panel", desktop_open.crop((1360, 130, 1920, 900))),
    ])
    sheet(p("panel-current-selected-contact-sheet.png"), "Current zone and selected zone are distinct", [
        ("Current Zone: Zone 2 / Continue Adventure", desktop_current.crop((1320, 140, 1920, 1080))),
        ("Selected Zone: Zone 6 / Start Challenge", desktop_open.crop((1320, 140, 1920, 1080))),
    ])
    sheet(p("placement-high-skill-current-location-contact-sheet.png"), "Placement frontier: Zone 6 is authoritative", [
        ("Lower zones are reviewable, not completed", placement_high),
    ], columns=1)
    sheet(p("skipped-by-placement-contact-sheet.png"), "Skipped by placement is not completed", [
        ("Zones 1-5 have no completed check or fabricated stars", placement_high.crop((190, 350, 1250, 900))),
        ("Current player marker remains at Zone 6", placement_high.crop((1160, 300, 1540, 540))),
    ])
    sheet(p("dual-cta-identity-contact-sheet.png"), "Panel and bottom CTA share one target", [
        ("Zone 2: Continue Adventure", desktop_current.crop((1320, 520, 1920, 1080))),
        ("Zone 6: Start Challenge", desktop_open.crop((1320, 520, 1920, 1080))),
        ("Locked Zone 7: both disabled", desktop_locked.crop((1320, 520, 1920, 1080))),
    ], columns=3)
    sheet(p("route-node-states-contact-sheet.png"), "Dotted route and compact node states", [
        ("Completed / available / locked", desktop.crop((250, 150, 1640, 900))),
    ], columns=1)
    sheet(p("dotted-route-closeup.png"), "Fine round dotted route", [
        ("Teal completed and warm-gold remaining segments", desktop.crop((240, 390, 1450, 860))),
    ], columns=1)
    sheet(p("zone-1-safe-boundary-contact-sheet.png"), "Zone 1 remains above the bottom HUD", [
        ("Desktop 1920 Zone 1 safe boundary", desktop.crop((180, 700, 720, 1080))),
        ("Landscape iPad Zone 1 safe boundary", opened(p("tablet-1180x820-closed-zh.png"), (80, 530, 520, 820))),
    ])
    sheet(p("current-player-marker-contact-sheet.png"), "Single authoritative current-player marker", [
        ("Current location at zone 2", desktop.crop((300, 610, 730, 900))),
    ], columns=1)
    sheet(p("player-marker-before-after-selection-contact-sheet.png"), "Selection does not move the player marker", [
        ("Before selection: marker at Zone 2", desktop.crop((300, 600, 760, 900))),
        ("After selecting Zone 6: marker still at Zone 2", desktop_open.crop((300, 600, 760, 900))),
    ])
    sheet(p("top-hud-closeup.png"), "Reference-proportioned top HUD", [
        ("Player identity / title plaque / utilities", desktop.crop((20, 20, 1900, 160))),
    ], columns=1)
    sheet(p("ipad-landscape-portrait-contact-sheet.png"), "iPad landscape and portrait", [
        ("1180x820 landscape", opened(p("tablet-1180x820-closed-zh.png"))),
        ("768x1024 portrait panel", opened(p("tablet-768x1024-portrait-drawer-open-zh.png"))),
    ])
    sheet(p("mobile-430-390-360-contact-sheet.png"), "Mobile 430 / 390 / 360", [
        ("430 All Features", opened(p("mobile-430x932-all-features-en.png"))),
        ("390 long English labels", opened(p("mobile-390x844-long-label-en.png"))),
        ("360 safe area", opened(p("mobile-360x800-safe-area-zh.png"))),
    ], columns=3)
    sheet(p("all-features-settings-contact-sheet.png"), "All Features and Settings", [
        ("Desktop All Features", opened(p("desktop-1440x900-all-features-zh.png"))),
        ("Desktop Settings", opened(p("desktop-1440x900-settings-en.png"))),
        ("Portrait iPad Settings", opened(p("tablet-820x1180-settings-zh.png"))),
        ("Mobile All Features", opened(p("mobile-430x932-all-features-en.png"))),
    ])
    sheet(p("compatibility-fallback-contact-sheet.png"), "VS1D compatibility fallbacks", [
        ("Missing marker", opened(p("compatibility-missing-vs1d-fallback-1440x900-en.png"))),
        ("Wrong marker", opened(p("compatibility-wrong-vs1d-fallback-1440x900-en.png"))),
        ("Exact v209 index", opened(p("compatibility-current-v209-vs1d-fallback-1440x900-en.png"))),
    ], columns=3)

    identity = {
        "owner_reference": image_identity(args.reference.resolve()),
        "owner_clean_source": image_identity(args.clean_source.resolve()),
        "v1_base_unchanged": image_identity(repo / "assets/maps/e10_world_stage_v1_base.webp"),
        "v2_clean_derivative": image_identity(repo / "assets/maps/e10_world_stage_v2_clean.webp"),
    }
    p("e10-v2-asset-identity.json").write_text(json.dumps(identity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    governed = sorted(path for path in evidence.iterdir() if path.is_file() and path.name != "SHA256SUMS.txt")
    sums = "".join(f"{sha256(path)}  {path.name}\n" for path in governed)
    p("SHA256SUMS.txt").write_text(sums, encoding="ascii")


if __name__ == "__main__":
    main()
