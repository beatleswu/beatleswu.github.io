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
        if "A" in image.getbands():
            rgba = image.convert("RGBA")
            converted = Image.new("RGB", rgba.size, BG)
            converted.paste(rgba, mask=rgba.getchannel("A"))
        else:
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
    sheet(p("owner-reference-vs-final-desktop-contact-sheet.png"), "Owner reference vs final Desktop", [
        ("Owner reference", opened(args.reference)),
        ("Final Desktop 1920", desktop),
        ("Final Desktop 1440", desktop_1440),
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
    sheet(p("final-desktop-closed-contact-sheet.png"), "Final Desktop closed: English and Traditional Chinese", [
        ("Desktop 1440 English", desktop_1440),
        ("Desktop 1920 Traditional Chinese", desktop),
    ])
    sheet(p("panel-state-language-contact-sheet.png"), "Right Zone Panel states in English and Traditional Chinese", [
        ("Current / English", desktop_current.crop((1390, 135, 1920, 850))),
        ("Current / Traditional Chinese", desktop_current_zh.crop((1390, 135, 1920, 850))),
        ("Selected / English", desktop_open.crop((1390, 135, 1920, 850))),
        ("Selected / Traditional Chinese", desktop_selected_zh.crop((1390, 135, 1920, 850))),
        ("Locked / English", desktop_locked_en.crop((1390, 135, 1920, 850))),
        ("Locked / Traditional Chinese", desktop_locked.crop((1390, 135, 1920, 850))),
    ], columns=3)
    sheet(p("player-identity-avatar-contact-sheet.png"), "Runtime player identity and stable fallback", [
        ("Runtime head-and-shoulders crop", desktop.crop((20, 20, 520, 170))),
        ("Project fallback avatar", opened(p("desktop-1440x900-avatar-fallback-zh.png"), (20, 45, 430, 175))),
    ])
    sheet(p("player-plaque-zh-en-fallback-contact-sheet.png"), "Text-safe player plaque", [
        ("Traditional Chinese runtime", desktop.crop((20, 20, 520, 170))),
        ("English runtime", desktop_1440.crop((20, 35, 430, 175))),
        ("Project fallback avatar", opened(p("desktop-1440x900-avatar-fallback-zh.png"), (20, 35, 430, 175))),
    ], columns=3)
    sheet(p("title-plaque-closeup.png"), "Live localized central title plaque", [
        ("Desktop title plaque", desktop.crop((590, 20, 1410, 170))),
    ], columns=1)
    sheet(p("utility-group-art-closeup.png"), "Coins, Pass, Messages, and Settings", [
        ("Desktop utility medallions", desktop.crop((1440, 20, 1900, 170))),
        ("Landscape iPad compact utilities", opened(p("tablet-1180x820-closed-zh.png"), (800, 10, 1170, 125))),
    ])
    sheet(p("left-badge-interaction-states-contact-sheet.png"), "Left badge interaction states", [
        (state.title(), opened(p(f"left-rail-state-{state}.png")))
        for state in ("default", "hover", "focus", "pressed", "active", "disabled")
    ], columns=3)
    sheet(p("bottom-dock-interaction-states-contact-sheet.png"), "Bottom medallion interaction states", [
        (state.title(), opened(p(f"bottom-dock-state-{state}.png")))
        for state in ("default", "hover", "focus", "pressed", "active", "disabled")
    ], columns=3)
    sheet(p("bottom-dock-final-closeup.png"), "Final carved dock silhouette", [
        ("Transparent frame outside the carved silhouette", desktop.crop((340, 870, 1510, 1080))),
    ], columns=1)
    sheet(p("primary-cta-closeup.png"), "Dynamic Adventure primary CTA", [
        ("Continue Adventure / current zone", desktop.crop((1450, 880, 1900, 1060))),
        ("Start Challenge / selected zone", desktop_open.crop((1450, 880, 1900, 1060))),
    ])
    sheet(p("primary-cta-interaction-states-contact-sheet.png"), "Primary CTA interaction states", [
        (state.title(), opened(p(f"primary-cta-state-{state}.png")))
        for state in ("default", "hover", "focus", "pressed", "active", "disabled")
    ], columns=3)
    sheet(p("right-zone-panel-art-closeup.png"), "Parchment Right Zone Panel art", [
        ("Current", desktop_current.crop((1450, 145, 1900, 850))),
        ("Selected", desktop_open.crop((1450, 145, 1900, 850))),
        ("Locked", desktop_locked.crop((1450, 145, 1900, 850))),
    ], columns=3)
    sheet(p("zone-10-safe-boundary-contact-sheet.png"), "Zone 10 remains below the title HUD", [
        ("Desktop 1920 Zone 10", desktop.crop((650, 125, 1050, 360))),
        ("Landscape iPad Zone 10", opened(p("tablet-1180x820-closed-zh.png"), (350, 90, 690, 310))),
    ])
    sheet(p("all-features-responsive-contact-sheet.png"), "All Features: Desktop, iPad, and Mobile", [
        ("Desktop", opened(p("desktop-1440x900-all-features-zh.png"))),
        ("Portrait iPad", opened(p("tablet-820x1180-all-features-en.png"))),
        ("Mobile 430", opened(p("mobile-430x932-all-features-en.png"))),
    ], columns=3)
    sheet(p("settings-responsive-contact-sheet.png"), "Settings: Desktop, iPad, and Mobile", [
        ("Desktop", opened(p("desktop-1440x900-settings-en.png"))),
        ("Portrait iPad", opened(p("tablet-820x1180-settings-zh.png"))),
        ("Mobile 430", opened(p("mobile-430x932-settings-zh.png"))),
    ], columns=3)

    desktop.save(p("desktop-1920-closed-zh.png"), "PNG", optimize=True)
    desktop_open.save(p("desktop-1920-panel-open-en.png"), "PNG", optimize=True)
    desktop_1440.save(p("desktop-1440-closed-en.png"), "PNG", optimize=True)
    placement_high.crop((1120, 260, 1560, 570)).save(
        p("placement-zone6-player-marker.png"), "PNG", optimize=True
    )
    sheet(p("ipad-landscape-final-contact-sheet.png"), "Final iPad landscape", [
        ("1180 x 820", opened(p("tablet-1180x820-closed-zh.png"))),
        ("1024 x 768 panel open", opened(p("tablet-1024x768-drawer-open-zh.png"))),
    ])
    opened(p("mobile-430x932-closed-en.png")).save(p("mobile-430-regression.png"), "PNG", optimize=True)

    representative_assets = [
        "assets/e10/ui/plaques/player-identity-plaque.webp",
        "assets/e10/ui/plaques/title-plaque.webp",
        "assets/e10/ui/medallions/navigation-badge-frame.webp",
        "assets/e10/ui/medallions/utility-medallion-frame.webp",
        "assets/e10/ui/frames/legacy-dock-frame.webp",
        "assets/e10/ui/panels/zone-panel-frame.webp",
        "assets/e10/ui/cta/adventure-primary-frame.webp",
        "assets/e10/ui/ornaments/outer-frame-corner.webp",
        "assets/e10/ui/states/player-location-pin.webp",
        "assets/e10/ui/states/selected-halo.webp",
        "assets/e10/ui/states/locked-ring.webp",
        "assets/e10/ui/icons/adventure.webp",
    ]
    sheet(p("runtime-art-kit-contact-sheet.png"), "Bespoke modular E10 runtime art kit", [
        (Path(asset).stem.replace("-", " ").title(), opened(repo / asset))
        for asset in representative_assets
    ], columns=4)
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

    asset_inventory = json.loads((repo / "assets/e10/ui/e10-ui-assets.json").read_text(encoding="utf-8"))
    p("e10-runtime-ui-asset-inventory.json").write_text(
        json.dumps(asset_inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    requirements = [
        (1, "Owner reference vs final Desktop 1920", ["owner-reference-comparison-contact-sheet.png"]),
        (2, "Owner reference vs final Desktop 1440", ["owner-reference-comparison-contact-sheet.png"]),
        (3, "Final Desktop closed English", ["desktop-1440x900-closed-en.png"]),
        (4, "Final Desktop closed Traditional Chinese", ["desktop-1920x1080-closed-zh.png"]),
        (5, "Current Zone panel English", ["desktop-1920x1080-current-zone-en.png"]),
        (6, "Current Zone panel Traditional Chinese", ["desktop-1920x1080-current-zone-zh.png"]),
        (7, "Selected Zone panel English", ["desktop-1920x1080-drawer-open-en.png"]),
        (8, "Selected Zone panel Traditional Chinese", ["desktop-1920x1080-selected-zone-zh.png"]),
        (9, "Locked Zone panel English", ["desktop-1920x1080-locked-zone-en.png"]),
        (10, "Locked Zone panel Traditional Chinese", ["desktop-1920x1080-locked-zone-zh.png"]),
        (11, "Right Zone Panel collision close-up", ["phase-a-panel-collision-contact-sheet.png"]),
        (12, "Desktop 1440 immersive-stage proof", ["phase-a-desktop-1440-immersive-contact-sheet.png"]),
        (13, "Player identity plaque close-up", ["player-identity-avatar-contact-sheet.png"]),
        (14, "Avatar runtime and fallback close-up", ["player-identity-avatar-contact-sheet.png"]),
        (15, "Central title plaque close-up", ["title-plaque-closeup.png"]),
        (16, "Utility group close-up", ["utility-group-art-closeup.png"]),
        (17, "Five left RPG badges close-up", ["left-floating-badges-closeup.png"]),
        (18, "Left badge default", ["left-rail-state-default.png"]),
        (19, "Left badge hover", ["left-rail-state-hover.png"]),
        (20, "Left badge focus", ["left-rail-state-focus.png"]),
        (21, "Left badge pressed", ["left-rail-state-pressed.png"]),
        (22, "Left badge active", ["left-rail-state-active.png"]),
        (23, "Left badge disabled", ["left-rail-state-disabled.png"]),
        (24, "Five bottom medallions close-up", ["bottom-medallion-dock-closeup.png"]),
        (25, "Bottom default", ["bottom-dock-state-default.png"]),
        (26, "Bottom hover", ["bottom-dock-state-hover.png"]),
        (27, "Bottom focus", ["bottom-dock-state-focus.png"]),
        (28, "Bottom pressed", ["bottom-dock-state-pressed.png"]),
        (29, "Bottom active", ["bottom-dock-state-active.png"]),
        (30, "Bottom disabled", ["bottom-dock-state-disabled.png"]),
        (31, "Primary CTA close-up", ["primary-cta-closeup.png"]),
        (32, "Primary CTA interaction states", ["primary-cta-interaction-states-contact-sheet.png"]),
        (33, "Right Zone Panel art close-up", ["right-zone-panel-art-closeup.png"]),
        (34, "Dotted route close-up", ["dotted-route-closeup.png"]),
        (35, "Route-node states", ["route-node-states-contact-sheet.png"]),
        (36, "Zone 1 safe boundary", ["zone-1-safe-boundary-contact-sheet.png"]),
        (37, "Zone 10 safe boundary", ["zone-10-safe-boundary-contact-sheet.png"]),
        (38, "Single player marker before and after selection", ["player-marker-before-after-selection-contact-sheet.png"]),
        (39, "High-skill placement", ["placement-high-skill-current-location-contact-sheet.png"]),
        (40, "Skipped by placement", ["skipped-by-placement-contact-sheet.png"]),
        (41, "Dual CTA target identity", ["dual-cta-identity-contact-sheet.png"]),
        (42, "All Features Desktop iPad Mobile", ["all-features-responsive-contact-sheet.png"]),
        (43, "Settings Desktop iPad Mobile", ["settings-responsive-contact-sheet.png"]),
        (44, "iPad landscape", ["tablet-1180x820-closed-zh.png"]),
        (45, "iPad portrait", ["tablet-768x1024-portrait-drawer-open-zh.png"]),
        (46, "Mobile 430", ["mobile-430x932-all-features-en.png"]),
        (47, "Mobile 390", ["mobile-390x844-long-label-en.png"]),
        (48, "Mobile 360", ["mobile-360x800-safe-area-zh.png"]),
        (49, "Long-label Mobile English", ["mobile-390x844-long-label-en.png"]),
        (50, "Mobile Traditional Chinese safe area", ["mobile-360x800-safe-area-zh.png"]),
        (51, "Missing-marker VS1D fallback", ["compatibility-missing-vs1d-fallback-1440x900-en.png"]),
        (52, "Wrong-marker VS1D fallback", ["compatibility-wrong-vs1d-fallback-1440x900-en.png"]),
        (53, "Exact-v209 VS1D fallback", ["compatibility-current-v209-vs1d-fallback-1440x900-en.png"]),
        (54, "Non-allowlisted Legacy", ["legacy-nonallowlisted-1440x900-zh.png"]),
        (55, "Visual contract JSON", ["e10-vs1f-visual-contract.json"]),
        (56, "Asset inventory", ["e10-runtime-ui-asset-inventory.json"]),
        (57, "SHA256 sums", ["SHA256SUMS.txt"]),
        (58, "Owner reference vs final Desktop", ["owner-reference-vs-final-desktop-contact-sheet.png"]),
        (59, "Player plaque Traditional Chinese English fallback", ["player-plaque-zh-en-fallback-contact-sheet.png"]),
        (60, "Desktop 1920 closed Traditional Chinese", ["desktop-1920-closed-zh.png"]),
        (61, "Desktop 1920 panel open English", ["desktop-1920-panel-open-en.png"]),
        (62, "Desktop 1440 closed English", ["desktop-1440-closed-en.png"]),
        (63, "Bottom dock final closeup", ["bottom-dock-final-closeup.png"]),
        (64, "Placement Zone 6 player marker", ["placement-zone6-player-marker.png"]),
        (65, "iPad landscape final", ["ipad-landscape-final-contact-sheet.png"]),
        (66, "Mobile 430 regression", ["mobile-430-regression.png"]),
    ]
    assert [item[0] for item in requirements] == list(range(1, 67))
    evidence_index = {
        "contract": "e10-owner-evidence-index-v1",
        "requirements": [
            {"id": number, "requirement": requirement, "files": files}
            for number, requirement, files in requirements
        ],
    }
    p("e10-owner-evidence-index.json").write_text(
        json.dumps(evidence_index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    governed = sorted(path for path in evidence.iterdir() if path.is_file() and path.name != "SHA256SUMS.txt")
    sums = "".join(f"{sha256(path)}  {path.name}\n" for path in governed)
    p("SHA256SUMS.txt").write_text(sums, encoding="ascii")


if __name__ == "__main__":
    main()
