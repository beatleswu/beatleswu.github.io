"""Build the governed modular E10 runtime UI kit from approved alpha atlases."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


SOURCE_ATLASES = {
    "frames": {
        "filename": "e10-ui-frame-kit-alpha.png",
        "sha256": "ed84b5301ebbd8372d8ecd35020c5cf142bccdc81097e05189291945b2ff4ff3",
        "dimensions": (1254, 1254),
    },
    "icons": {
        "filename": "e10-ui-icon-atlas-alpha.png",
        "sha256": "4102db995c1cd4b42236637884f08b7c74358371dc9882a03e9a4d8232854d24",
        "dimensions": (1570, 1002),
    },
    "states": {
        "filename": "e10-ui-state-atlas-alpha.png",
        "sha256": "d17792e5b5b9a1369328a0d17eb798c3407b63395cbaf591ad7798ddbab89409",
        "dimensions": (1672, 941),
    },
    "supplement": {
        "filename": "e10-ui-supplement-atlas-alpha.png",
        "sha256": "007840a97b01d93ec6af49575aed4be498218bf5d2dc00842c5c5cb487fcb639",
        "dimensions": (1254, 1254),
    },
}


@dataclass(frozen=True)
class AssetSpec:
    atlas: str
    region: tuple[int, int, int, int]
    relative_path: str
    dimensions: tuple[int, int]
    purpose: str
    runtime_component: str
    responsive_relationship: str = "shared"
    occupancy: float = 0.92


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def icon_specs() -> list[AssetSpec]:
    names = [
        ("hero", "Hero navigation symbol", "left badge and All Features"),
        ("equipment", "Equipment navigation symbol", "left badge and mobile dock"),
        ("backpack", "Locked Backpack navigation symbol", "left badge and mobile dock"),
        ("go-spirit", "Go Spirit Companion symbol", "left badge and mobile dock"),
        ("shop", "Fantasy Shop navigation symbol", "left badge and mobile dock"),
        ("soul-records", "Soul Records scroll symbol", "legacy dock and All Features"),
        ("battle-log", "Battle Log banner symbol", "legacy dock and All Features"),
        ("tavern", "Child-friendly Tavern mug symbol", "legacy dock and All Features"),
        ("star-chart", "Star Chart astrolabe symbol", "legacy dock and All Features"),
        ("arena", "Arena navigation symbol", "legacy dock and All Features"),
        ("coins", "Gold coin counter symbol", "top HUD Coins counter"),
        ("pass", "Gem Pass symbol", "top HUD and All Features"),
        ("messages", "Sealed message envelope symbol", "top HUD and All Features"),
        ("settings", "Brass Settings gear symbol", "top HUD, Settings, and All Features"),
        ("adventure", "Adventure compass and crossed-swords symbol", "progress, CTA, and mobile dock"),
        ("all-features", "All Features tool-grid symbol", "compact HUD and All Features trigger"),
        ("daily-challenge", "Daily Challenge sun-scroll symbol", "All Features"),
        ("badges", "Badges medal symbol", "All Features"),
        ("game-records", "Game Records book symbol", "All Features"),
        ("lock", "Brass lock symbol", "locked navigation and map states"),
    ]
    x_edges = [0, 314, 628, 942, 1256, 1570]
    y_edges = [0, 260, 500, 725, 1002]
    specs: list[AssetSpec] = []
    for index, (name, purpose, component) in enumerate(names):
        row, column = divmod(index, 5)
        specs.append(
            AssetSpec(
                "icons",
                (x_edges[column], y_edges[row], x_edges[column + 1], y_edges[row + 1]),
                f"icons/{name}.webp",
                (256, 256),
                purpose,
                component,
            )
        )
    return specs


ASSETS = [
    AssetSpec("frames", (0, 0, 627, 250), "plaques/player-identity-plaque.webp", (768, 240), "Ivory player identity plaque with portrait socket", "Desktop and compact player identity"),
    AssetSpec("frames", (627, 0, 1254, 250), "plaques/title-plaque.webp", (1024, 270), "Carved central title plaque", "Desktop world-stage title"),
    AssetSpec("frames", (627, 0, 1254, 250), "plaques/navigation-label.webp", (384, 104), "Compact carved live-text label plaque", "Left badges and legacy medallion labels", occupancy=0.96),
    AssetSpec("frames", (0, 250, 627, 580), "medallions/navigation-badge-frame.webp", (320, 336), "Double-layer teal and gold navigation badge frame", "Left badges and bottom legacy medallions"),
    AssetSpec("frames", (627, 250, 1254, 580), "medallions/utility-medallion-frame.webp", (256, 260), "Compact teal and gold utility medallion frame", "Pass, Messages, Settings, and compact controls"),
    AssetSpec("supplement", (627, 627, 1254, 1254), "medallions/zone-number-frame.webp", (224, 224), "Empty live-number medallion frame", "Map nodes and Right Zone Panel number"),
    AssetSpec("frames", (0, 580, 627, 780), "frames/legacy-dock-frame.webp", (1280, 384), "Five-socket carved legacy dock base", "Desktop bottom legacy dock"),
    AssetSpec("frames", (627, 580, 1254, 780), "cta/adventure-primary-frame.webp", (1024, 288), "Teal enamel and gold primary CTA frame", "Desktop primary CTA and panel CTA"),
    AssetSpec("frames", (0, 780, 627, 1254), "panels/zone-panel-frame.webp", (640, 640), "Parchment panel with layered gold corners", "Right Zone Panel, All Features, and Settings"),
    AssetSpec("frames", (627, 780, 1005, 1080), "ornaments/outer-frame-corner.webp", (384, 384), "Carved gold outer-frame corner ornament", "Desktop and landscape world-stage frame", occupancy=0.96),
    AssetSpec("supplement", (0, 627, 627, 1254), "ornaments/dropdown-chevron.webp", (160, 112), "Gold dropdown chevron with teal jewel", "Player identity menu trigger"),
    AssetSpec("supplement", (0, 0, 627, 627), "icons/heroes-hall.webp", (256, 256), "Crowned laurel Hero's Hall symbol", "All Features Hero's Hall"),
    AssetSpec("supplement", (627, 0, 1254, 627), "icons/close.webp", (192, 192), "Gold close symbol on teal medallion", "Dialog and zone-panel close controls"),
    AssetSpec("states", (0, 0, 418, 470), "states/player-location-pin.webp", (256, 320), "Authoritative player-location portrait pin", "Single world-stage player marker"),
    AssetSpec("states", (418, 0, 836, 470), "states/selected-halo.webp", (320, 256), "Teal selected-zone magical halo", "Selected and current map nodes"),
    AssetSpec("states", (836, 0, 1254, 470), "states/available-halo.webp", (320, 240), "Warm-gold available-zone halo", "Available map nodes"),
    AssetSpec("states", (1254, 0, 1672, 470), "states/completed-seal.webp", (256, 256), "Completed-zone brass seal", "Completed map-node state"),
    AssetSpec("states", (0, 470, 418, 941), "states/locked-ring.webp", (288, 272), "Muted brass locked-zone ring", "Locked map-node state"),
    AssetSpec("states", (418, 470, 836, 941), "states/skipped-review-ring.webp", (288, 272), "Placement-skipped review ring", "skipped_by_placement map-node state"),
    AssetSpec("states", (836, 470, 1155, 941), "states/star.webp", (224, 224), "Polished gold progress star", "Zone stars and completion display"),
    AssetSpec("states", (1155, 470, 1672, 941), "states/progress-rail.webp", (512, 160), "Teal enamel progress-rail frame", "Adventure and zone progress meters"),
] + icon_specs()


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    mask = image.getchannel("A").point(lambda value: 255 if value > 2 else 0)
    bbox = mask.getbbox()
    if not bbox:
        raise SystemExit("Asset region contains no visible pixels")
    return bbox


def crop_with_padding(image: Image.Image, region: tuple[int, int, int, int]) -> Image.Image:
    cell = image.crop(region)
    left, top, right, bottom = alpha_bbox(cell)
    padding = max(4, round(max(right - left, bottom - top) * 0.025))
    return cell.crop((max(0, left - padding), max(0, top - padding), min(cell.width, right + padding), min(cell.height, bottom + padding)))


def fit_transparent(image: Image.Image, size: tuple[int, int], occupancy: float) -> Image.Image:
    max_width = max(1, round(size[0] * occupancy))
    max_height = max(1, round(size[1] * occupancy))
    scale = min(max_width / image.width, max_height / image.height)
    resized_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    premultiplied = image.convert("RGBa").resize(resized_size, Image.Resampling.LANCZOS).convert("RGBA")
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.alpha_composite(premultiplied, ((size[0] - premultiplied.width) // 2, (size[1] - premultiplied.height) // 2))
    return canvas


def validate_output(image: Image.Image, relative_path: str) -> None:
    alpha = image.getchannel("A")
    if not alpha.getbbox() or alpha.getextrema()[0] != 0 or alpha.getextrema()[1] != 255:
        raise SystemExit(f"Invalid transparent edge contract: {relative_path}")
    visible = sum(alpha.histogram()[9:])
    if visible < image.width * image.height * 0.025:
        raise SystemExit(f"Unexpectedly sparse asset canvas: {relative_path}")
    chroma = sum(1 for red, green, blue, opacity in image.get_flattened_data() if opacity > 96 and red > 180 and blue > 150 and green < 120)
    if chroma > 8:
        raise SystemExit(f"Chroma-key spill remains in {relative_path}: {chroma} pixels")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--replace-generated", action="store_true")
    args = parser.parse_args()

    sources: dict[str, Image.Image] = {}
    source_records = []
    for key, contract in SOURCE_ATLASES.items():
        path = args.source_dir / contract["filename"]
        if sha256(path) != contract["sha256"]:
            raise SystemExit(f"Approved {key} atlas SHA-256 mismatch")
        with Image.open(path) as opened:
            if opened.format != "PNG" or opened.mode != "RGBA" or opened.size != contract["dimensions"]:
                raise SystemExit(f"Approved {key} atlas image identity mismatch")
            sources[key] = opened.copy()
        source_records.append({
            "role": key,
            "filename": contract["filename"],
            "dimensions": list(contract["dimensions"]),
            "bytes": path.stat().st_size,
            "sha256": contract["sha256"],
        })

    output_root = args.output_root.resolve()
    expected_outputs = {output_root / spec.relative_path for spec in ASSETS}
    expected_outputs.add(output_root / "e10-ui-assets.json")
    if output_root.exists():
        unexpected = [path for path in output_root.rglob("*") if path.is_file() and path not in expected_outputs]
        if unexpected:
            raise SystemExit(f"Refusing to touch unexpected file under output root: {unexpected[0]}")
    records = []
    for spec in ASSETS:
        output = output_root / spec.relative_path
        if output.exists() and not args.replace_generated:
            raise SystemExit(f"Refusing to overwrite existing runtime asset: {output}")
        artwork = fit_transparent(crop_with_padding(sources[spec.atlas], spec.region), spec.dimensions, spec.occupancy)
        validate_output(artwork, spec.relative_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        artwork.save(output, "WEBP", quality=92, method=6, exact=True)
        with Image.open(output) as derivative:
            if derivative.format != "WEBP" or derivative.size != spec.dimensions or "A" not in derivative.mode:
                raise SystemExit(f"Generated derivative identity mismatch: {spec.relative_path}")
        records.append({
            "path": f"assets/e10/ui/{spec.relative_path}",
            "purpose": spec.purpose,
            "format": "WEBP",
            "dimensions": list(spec.dimensions),
            "bytes": output.stat().st_size,
            "sha256": sha256(output),
            "runtime_component": spec.runtime_component,
            "responsive_relationship": spec.responsive_relationship,
            "source_atlas": spec.atlas,
        })

    manifest = {
        "contract": "e10-art-directed-runtime-ui-v1",
        "owner_reference_sha256": "d8040aa9f43e8792e572b3cea1056e6be431eb3916da53872a7393c0965fed60",
        "source_atlases": source_records,
        "post_processing": "Flat chroma key removed with soft matte and despill; fixed semantic crops; premultiplied-alpha Lanczos resize; WebP quality=92 method=6 exact alpha.",
        "total_assets": len(records),
        "total_bytes": sum(record["bytes"] for record in records),
        "assets": sorted(records, key=lambda record: record["path"]),
    }
    manifest_path = output_root / "e10-ui-assets.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(f"Built {manifest['total_assets']} assets ({manifest['total_bytes']} bytes)")
    print(manifest_path)


if __name__ == "__main__":
    main()
