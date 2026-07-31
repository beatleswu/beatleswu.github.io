import hashlib
import json
import re
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "assets/maps/e10_world_stage_v1_base.webp"
V2 = ROOT / "assets/maps/e10_world_stage_v2_clean.webp"
WORLD = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
RIGHT = (ROOT / "js/e9/right_cards.js").read_text(encoding="utf-8")
TOP = (ROOT / "js/e9/top_hud.js").read_text(encoding="utf-8")
CSS = (ROOT / "css/e9/reference_world_map.css").read_text(encoding="utf-8")
HTML = (ROOT / "components/adventure/world_stage.html").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(name: str) -> dict:
    return json.loads((ROOT / "deploy" / name).read_text(encoding="utf-8"))


def entry(manifest: dict, path: str) -> dict:
    return next(item for item in manifest["files"] if item["path"] == path)


def test_v1_asset_identity_is_unchanged():
    assert V1.stat().st_size == 651432
    assert digest(V1) == "f092dd37507e1ba5d9a7cfeca2951de8aa9b313ffa7d4ff911d18be123d4256a"


def test_v2_clean_map_identity_and_dimensions():
    assert V2.stat().st_size == 754206
    assert digest(V2) == "32c6b137422a3b897677564d1f4e11002308b96807e0b27e2d3a3c3243d6ceb5"
    with Image.open(V2) as image:
        assert image.format == "WEBP"
        assert image.size == (2048, 1152)


def test_v2_build_script_pins_owner_source_and_encoder():
    script = (ROOT / "tools/build_e10_world_stage_v2_asset.py").read_text(encoding="utf-8")
    assert "f735798ad1e072fad57ca5d9286facea0656dee5d409ad9ddabf39e96b961b4d" in script
    assert "EXPECTED_SIZE = (2048, 1152)" in script
    assert 'quality=90, method=6, exact=True' in script


def test_governed_manifests_contain_v2_identity():
    expected = {
        "path": "assets/maps/e10_world_stage_v2_clean.webp",
        "size": 754206,
        "sha256": "32c6b137422a3b897677564d1f4e11002308b96807e0b27e2d3a3c3243d6ceb5",
        "mime": "image/webp",
        "width": 2048,
        "height": 1152,
        "provenance": "owner-approved-project-created",
    }
    for name in ("canonical-image-pack-manifest.json", "canonical-asset-closure-manifest.json"):
        assert entry(load_manifest(name), expected["path"]) | expected == entry(load_manifest(name), expected["path"])


def test_exact_marker_selects_v2_and_fallback_selects_v1():
    assert "if (VS1E_STATIC_CONTRACT_ACTIVE)" in WORLD
    assert "base.src = '/assets/maps/e10_world_stage_v2_clean.webp'" in WORLD
    assert "base.getAttribute('data-vs1d-src')" in WORLD
    assert 'data-vs1d-src="/assets/maps/e10_world_stage_v1_base.webp"' in HTML
    assert re.search(r'\ssrc="/assets/maps/e10_world_stage_v1_base.webp"', HTML) is None


def test_reference_css_is_exact_skin_scoped():
    selectors = [line.strip() for line in CSS.splitlines() if line.strip().startswith(("body", "#e9"))]
    assert selectors
    assert all('data-e10-visual-skin="immersive-rpg"' in selector for selector in selectors)


def test_desktop_full_bleed_map_and_zero_grid_dead_space_contract():
    assert "aspect-ratio: 16 / 9" in CSS
    assert re.search(r"#e9-world-stage-slot,[\s\S]+?position: absolute;[\s\S]+?inset: 0;", CSS)
    assert ".e9-body.is-right-drawer-open" in CSS
    assert "display: block !important" in CSS


def test_reference_silhouette_structures_are_present():
    for token in (
        ".e9-hud__player", ".e10-hud-brand", ".e10-hud__right",
        "#e9-left-nav-slot", "#e9-bottom-dock-slot", ".e10-adventure-progress",
    ):
        assert token in CSS
    assert "e10.world_stage.title" in TOP


def test_floating_badges_and_five_medallion_dock_contract():
    assert "grid-template-rows: repeat(5" in CSS
    assert "border-radius: 50%" in CSS
    assert "grid-template-columns: repeat(5" in CSS


def test_overlay_zone_panel_does_not_own_grid_width():
    assert re.search(r"#e9-right-cards-slot \{[\s\S]+?position: absolute", CSS)
    assert ".e9-drawer-panel:not([hidden])" in CSS
    assert "data-e10-vs1f-zone-panel" in RIGHT


def test_dynamic_primary_and_panel_ctas_share_runtime_adapter():
    assert "root.__e10SelectedZoneKey" in RIGHT
    assert "window.E9.startAdventureFromE9(root.__e10SelectedZoneKey)" in RIGHT
    assert "window.E9.startAdventureFromE9(zone.key)" in WORLD
    assert "e10-map-primary-cta__copy" in WORLD


def test_dotted_routes_compact_nodes_and_single_player_marker_contract():
    assert "stroke-dasharray: 1 6" in CSS
    assert "width: 44px" in CSS and "height: 44px" in CSS
    assert "updatePlayerMarker" in WORLD
    assert "VS1F_ZONE_ANCHORS" in WORLD


def test_selection_and_player_location_remain_separate():
    assert "zone.__e10PlayerLocation" in WORLD
    assert "selectedZoneKey" in WORLD
    assert "updatePlayerMarker(root, playerLocation)" in WORLD


def test_official_ten_zone_names_are_runtime_authority():
    names = [
        "圍棋新手村", "史萊姆平原", "哥布林洞穴", "迷霧森林", "獸人部落",
        "龍之谷", "賢者之塔", "魔王城前線", "諸神黃昏", "上古終焉神殿",
    ]
    assert all(name in APP for name in names)


def test_landscape_and_portrait_ipad_have_distinct_contracts():
    assert "orientation: landscape" in CSS
    assert "orientation: portrait" in CSS
    assert "height: 100dvh !important" in CSS
    assert "position: fixed" in CSS


def test_mobile_keeps_six_action_dock_and_readable_cards():
    assert "repeat(6,minmax(0,1fr))" in CSS
    assert "min-height: 96px" in CSS
    assert "-webkit-line-clamp: 2" in CSS


def test_accessibility_and_reduced_motion_contracts_remain_present():
    right_html = (ROOT / "components/adventure/right_cards.html").read_text(encoding="utf-8")
    assert "aria-controls" in right_html
    assert "data-i18n-aria-label" in HTML
    assert "prefers-reduced-motion: reduce" in CSS


def test_service_worker_and_query_cache_identity_are_current():
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    flags = (ROOT / "js/e9/feature_flags.js").read_text(encoding="utf-8")
    assert "v219-e10-reference-world-map" in sw
    assert "ASSET_VERSION = 'e10-reference-world-map'" in flags
    assert INDEX.count("20260731e10reference1") >= 8


def test_reference_stylesheet_is_loaded_after_immersive_base():
    assert INDEX.index("/css/e9/immersive_rpg.css") < INDEX.index("/css/e9/reference_world_map.css")


def test_no_remote_or_text_baked_reference_assets():
    assert "http://" not in CSS and "https://" not in CSS
    assert "<text" not in TOP and "<text" not in WORLD


def test_reference_css_does_not_define_oversized_black_svg():
    assert "#000" not in CSS.lower()
    assert "rgb(0, 0, 0)" not in CSS.lower()
