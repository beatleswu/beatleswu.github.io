import hashlib
import json
import re
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "assets/e10/ui"
INVENTORY = json.loads((ASSET_ROOT / "e10-ui-assets.json").read_text(encoding="utf-8"))
REGISTRY = (ROOT / "js/e9/navigation_registry.js").read_text(encoding="utf-8")
WORLD = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
TOP = (ROOT / "js/e9/top_hud.js").read_text(encoding="utf-8")
RIGHT = (ROOT / "js/e9/right_cards.js").read_text(encoding="utf-8")
CSS = (ROOT / "css/e9/art_directed_runtime.css").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")
FLAGS = (ROOT / "js/e9/feature_flags.js").read_text(encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(name: str) -> dict:
    return json.loads((ROOT / "deploy" / name).read_text(encoding="utf-8"))


def test_asset_inventory_is_complete_small_and_identity_locked():
    assert INVENTORY["contract"] == "e10-art-directed-runtime-ui-v1"
    assert INVENTORY["owner_reference_sha256"] == "d8040aa9f43e8792e572b3cea1056e6be431eb3916da53872a7393c0965fed60"
    assert INVENTORY["total_assets"] == 41
    assert INVENTORY["total_bytes"] == sum(asset["bytes"] for asset in INVENTORY["assets"])
    assert INVENTORY["total_bytes"] < 1_500_000
    assert len({asset["path"] for asset in INVENTORY["assets"]}) == 41
    for asset in INVENTORY["assets"]:
        path = ROOT / asset["path"]
        assert path.is_file()
        assert path.stat().st_size == asset["bytes"]
        assert digest(path) == asset["sha256"]
        with Image.open(path) as image:
            assert image.format == "WEBP"
            assert list(image.size) == asset["dimensions"]
            assert "A" in image.mode
            assert image.getchannel("A").getextrema() == (0, 255)
            assert image.width <= 1280 and image.height <= 640


def test_all_runtime_art_is_covered_by_both_governed_manifests():
    inventory_paths = {asset["path"]: asset for asset in INVENTORY["assets"]}
    for name in ("canonical-image-pack-manifest.json", "canonical-asset-closure-manifest.json"):
        governed = {entry["path"]: entry for entry in manifest(name)["files"]}
        assert inventory_paths.keys() <= governed.keys()
        for path, asset in inventory_paths.items():
            assert governed[path]["size"] == asset["bytes"]
            assert governed[path]["sha256"] == asset["sha256"]
            assert governed[path]["mime"] == "image/webp"
            assert [governed[path]["width"], governed[path]["height"]] == asset["dimensions"]


def test_icon_registry_uses_local_art_only_inside_exact_contract():
    required = {
        "compass", "hero", "equipment", "backpack", "spirit", "shop",
        "records", "battle_log", "tavern", "hall", "star_chart", "arena",
        "pass", "messages", "settings", "daily", "badge", "game_records",
        "coin", "all_features", "close", "lock",
    }
    block = REGISTRY[REGISTRY.index("var ICON_ASSETS = {"):REGISTRY.index("function exactContract")]
    actual = set(re.findall(r"^\s{4}([a-z_]+): '[^']+\.webp'", block, re.M))
    assert required == actual
    assert "if (!exactContract()) return '';" in REGISTRY
    assert "data-e10-art-asset" in REGISTRY
    assert '<img src="' in REGISTRY
    assert "ART_ICON_ROOT = '/assets/e10/ui/icons/'" in REGISTRY
    assert "http://" not in block and "https://" not in block and "cdn" not in block.lower()


def test_art_stylesheet_uses_every_non_icon_asset_and_is_exact_scoped():
    non_icons = [asset["path"] for asset in INVENTORY["assets"] if "/icons/" not in asset["path"]]
    assert all(path.replace("assets/", "/assets/") in CSS for path in non_icons)
    assert 'body[data-e10-visual-skin="immersive-rpg"][data-e10-art-kit="runtime-v1"]' in CSS
    assert "#000" not in CSS.lower()
    assert "http://" not in CSS and "https://" not in CSS
    for line in CSS.splitlines():
        if "/assets/e10/ui/" in line:
            assert line.lstrip().startswith("--e10-art-")


def test_bespoke_assets_cover_every_required_runtime_component():
    required_tokens = (
        "--e10-art-player-plaque", "--e10-art-title-plaque", "--e10-art-utility-frame",
        "--e10-art-nav-frame", "--e10-art-dock-frame", "--e10-art-panel-frame",
        "--e10-art-cta-frame", "--e10-art-corner", "--e10-art-player-pin",
        "--e10-art-selected-halo", "--e10-art-available-halo", "--e10-art-completed-seal",
        "--e10-art-locked-ring", "--e10-art-skipped-ring", "--e10-art-star",
        "--e10-art-progress",
    )
    assert all(token in CSS for token in required_tokens)
    assert "data-e10-art-kit', 'runtime-v1'" in WORLD
    assert "removeAttribute('data-e10-art-kit')" in WORLD


def test_live_avatar_and_star_dom_remain_dynamic_and_accessible():
    assert "e9:player-avatar-updated" in TOP
    assert "syncPlayerMarkerPortrait" in WORLD
    assert "e10-player-marker-portrait" in WORLD
    assert "detail.stars" in RIGHT and "zone.stars" in WORLD
    assert "e10-art-star" in RIGHT and "e10-art-star" in WORLD
    assert "index.adv.stars_label" in RIGHT and "index.adv.stars_label" in WORLD
    assert "aria-hidden" in RIGHT and "aria-label" in RIGHT


def test_interaction_and_responsive_state_contracts_are_explicit():
    for token in (
        ":hover", ":active", ":focus-visible", ":disabled", '[aria-disabled="true"]',
        "is-current", "is-selected", "skipped_by_placement", 'data-zone-state="completed"',
        "@media (prefers-reduced-motion: reduce)", "transition-duration: .001ms", "animation: none",
        "orientation: landscape", "orientation: portrait", "max-width: 600px",
    ):
        assert token in CSS
    assert "min-height: 48px" in CSS
    assert "word-break: normal" in CSS and "overflow-wrap: normal" in CSS


def test_final_visual_refinement_contracts_are_explicit_and_asset_preserving():
    player = CSS[CSS.index('#e9-adventure-shell .e9-hud__player {'):]
    player = player[:player.index('}')]
    assert "display: grid" in player
    assert "grid-template-columns: 90px minmax(0, 1fr) 26px" in player
    assert "clamp(40px, 13.6%, 57px)" in player

    dock = CSS[CSS.index('#e9-adventure-shell .e9-dock {'):]
    dock = dock[:dock.index('}')]
    for declaration in (
        "background-color: transparent", "background-image: var(--e10-art-dock-frame)",
        "overflow: visible", "filter: none", "backdrop-filter: none", "box-shadow: none",
    ):
        assert declaration in dock

    assert ".e9-zone.is-current::before" in CSS
    assert "background-image: none" in CSS
    assert "width: 31px" in CSS and "height: 38px" in CSS
    assert "margin: -16px 0 0 18px" in CSS
    assert "player-location-pin.webp" in CSS


def test_bottom_dock_badge_slot_alignment_uses_one_shared_five_column_contract():
    dock = CSS[CSS.index('#e9-adventure-shell .e9-dock {'):]
    dock = dock[:dock.index('}')]
    assert "padding: 6px 12.890625%" in dock

    dock_list = CSS[CSS.index('#e9-adventure-shell .e9-dock__list {'):]
    dock_list = dock_list[:dock_list.index('}')]
    assert "grid-template-columns: repeat(5, minmax(0, 1fr))" in dock_list
    assert "gap: 0" in dock_list
    assert "height: 100%" in dock_list

    dock_item = CSS[CSS.index('#e9-adventure-shell .e9-dock__item {'):]
    dock_item = dock_item[:dock_item.index('}')]
    assert "display: grid" in dock_item
    assert 'grid-template: "dock-stack" 100% / 100%' in dock_item
    assert "justify-items: center" in dock_item

    assert "grid-area: dock-stack" in CSS
    assert "width: 50% !important" in CSS
    assert "width: 51.5% !important" in CSS
    assert "transform: translateX(-50%)" in CSS
    assert ".e9-dock__item:nth-child" not in CSS


def test_dynamic_cta_and_zone_identity_contracts_are_unchanged():
    assert "registry.icon('compass', 'e10-map-primary-cta__icon')" in WORLD
    assert "dispatchAdventureAction(contract);" in WORLD
    assert "window.E9.dispatchAdventureAction(" in RIGHT
    assert "targetZoneKey: root.__e10ChallengeTargetZoneKey" in RIGHT
    for identity in ("currentPlayerZoneKey", "selectedZoneKey", "challengeTargetZoneKey"):
        assert identity in WORLD


def test_final_cache_identity_and_stylesheet_order_are_single_bump():
    assert "const VERSION     = 'v229-e10-z1-prod-integration'" in SW
    assert "ASSET_VERSION = 'e10-art-directed-runtime-ui'" in FLAGS
    assert INDEX.count("20260801e10art1") >= 9
    assert "/css/e9/art_directed_runtime.css?v=20260801e10art1" in INDEX
    assert INDEX.index("/css/e9/reference_world_map.css") < INDEX.index("/css/e9/art_directed_runtime.css")


def test_authoritative_maps_remain_byte_identical():
    v1 = ROOT / "assets/maps/e10_world_stage_v1_base.webp"
    v2 = ROOT / "assets/maps/e10_world_stage_v2_clean.webp"
    assert v1.stat().st_size == 651432
    assert digest(v1) == "f092dd37507e1ba5d9a7cfeca2951de8aa9b313ffa7d4ff911d18be123d4256a"
    assert v2.stat().st_size == 754206
    assert digest(v2) == "32c6b137422a3b897677564d1f4e11002308b96807e0b27e2d3a3c3243d6ceb5"
