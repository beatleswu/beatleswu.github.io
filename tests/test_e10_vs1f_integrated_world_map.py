import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD_STAGE = (ROOT / "components/adventure/world_stage.html").read_text(encoding="utf-8")
WORLD_JS = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
CSS = (ROOT / "css/e9/immersive_rpg.css").read_text(encoding="utf-8")
LEFT_NAV = (ROOT / "components/adventure/left_nav.html").read_text(encoding="utf-8")
BOTTOM_DOCK = (ROOT / "components/adventure/bottom_dock.html").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
FLAGS = (ROOT / "js/e9/feature_flags.js").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")
LANDMARK_DIR = ROOT / "assets/maps/e10-vs1f-landmarks"
CONTRACT = "e10-vs1f-integrated-world-map"
LANDMARK_NAMES = [
    "zone-01-beginner-village.webp",
    "zone-02-slime-plains.webp",
    "zone-03-goblin-cave.webp",
    "zone-04-twilight-forest.webp",
    "zone-05-sky-tower.webp",
    "zone-06-royal-castle.webp",
    "zone-07-star-sea-passage.webp",
    "zone-08-abyssal-forge.webp",
    "zone-09-eternal-night-shrine.webp",
    "zone-10-ancient-doom-temple.webp",
]
GROUND_ROUTE = (
    "M234 352 C280 315 296 276 327 246 C315 212 297 181 298 149 "
    "C337 137 375 129 414 133 C451 145 482 158 518 165 "
    "C560 164 608 156 643 159 C674 180 698 204 720 226 "
    "C692 258 654 294 633 329 C592 350 548 367 504 376"
)
ASCENSION_ROUTE = "M504 376 C560 310 685 135 763 117"


def _manifest(relative_path):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_exact_v215_static_runtime_version_coupling():
    assert f'content="{CONTRACT}"' in INDEX
    assert f"VS1E_STATIC_CONTRACT = '{CONTRACT}'" in WORLD_JS
    assert f"ASSET_VERSION = '{CONTRACT}'" in FLAGS
    assert "const VERSION     = 'v215-e10-vs1f-integrated-world-map'" in SW
    assert INDEX.count("20260730e10vs1f1") == 5


def test_ten_original_landmarks_are_runtime_referenced_and_governed():
    actual = sorted(path.name for path in LANDMARK_DIR.glob("*.webp"))
    assert actual == LANDMARK_NAMES
    closure = _manifest("deploy/canonical-asset-closure-manifest.json")
    image_pack = _manifest("deploy/canonical-image-pack-manifest.json")
    closure_by_path = {entry["path"]: entry for entry in closure["files"]}
    image_by_path = {entry["path"]: entry for entry in image_pack["files"]}
    for name in LANDMARK_NAMES:
        relative = f"assets/maps/e10-vs1f-landmarks/{name}"
        assert f"/{relative}" in WORLD_JS
        data = (ROOT / relative).read_bytes()
        for governed in (closure_by_path[relative], image_by_path[relative]):
            assert governed["size"] == len(data)
            assert governed["sha256"] == hashlib.sha256(data).hexdigest()
            assert governed["mime"] == "image/webp"
            assert governed["width"] == governed["height"] == 320
            assert governed["provenance"] == "owner-approved-project-created"


def test_landmarks_are_decorative_and_only_created_for_mobile_cards():
    gated_block = re.search(
        r"if \(VS1E_STATIC_CONTRACT_ACTIVE && usesLandmarkCards\(\)\) \{\s*"
        r".*?"
        r"landmark\.setAttribute\('aria-hidden', 'true'\);"
        r".*?tile\.appendChild\(landmark\);\s*\}",
        WORLD_JS,
        re.S,
    )
    assert gated_block
    assert "landmark.alt = ''" in gated_block.group(0)
    assert "landmark.draggable = false" in gated_block.group(0)
    assert "landmark.loading = 'lazy'" in gated_block.group(0)


def test_route_topology_is_exact_and_material_layers_do_not_add_paths():
    route_paths = re.findall(r'<path[^>]+d="([^"]+)"', WORLD_STAGE)
    assert set(route_paths) == {GROUND_ROUTE, ASCENSION_ROUTE}
    assert route_paths.count(GROUND_ROUTE) == 5
    assert route_paths.count(ASCENSION_ROUTE) == 3
    for material in ("locked", "available", "completed", "current"):
        assert f"e9-route__material--{material}" in WORLD_STAGE
        assert f".e9-route__material--{material}" in CSS
    assert 'data-e10-route-progress="completed"' in WORLD_STAGE
    assert 'data-e10-route-progress="current"' in WORLD_STAGE
    assert "pointer-events: none" in CSS
    assert "@media (prefers-reduced-motion: reduce)" in CSS


def test_unified_frame_original_icons_and_four_state_landmark_treatments():
    assert "--e10-integrated-rail: 84px" in CSS
    assert "--e10-integrated-panel:" in CSS
    assert ".e10-zone-landmark" in CSS
    for selector in (
        ".e9-zone--completed .e10-zone-landmark",
        ".e9-zone.is-selected .e10-zone-landmark",
        ".e9-zone[disabled] .e10-zone-landmark",
    ):
        assert selector in CSS
    assert LEFT_NAV.count('class="e9-nav__icon"') == 6
    assert BOTTOM_DOCK.count('class="e9-dock__icon"') == 4
    assert LEFT_NAV.count('aria-hidden="true"') == 6
    assert BOTTOM_DOCK.count('aria-hidden="true"') == 4
    assert "e10-drawer-zone-summary__landmark" in (
        ROOT / "components/adventure/right_cards.html"
    ).read_text(encoding="utf-8")


def test_mobile_keeps_single_row_safe_area_navigation_and_inline_landmarks():
    assert "grid-template-columns: repeat(6, minmax(0, 1fr))" in CSS
    assert "env(safe-area-inset-bottom, 0px)" in CSS
    assert "grid-template-columns: 76px minmax(0, 1fr) 30px" in CSS
    assert ".e9-zone__inline-details" in CSS
    assert ".e10-current-hero" in CSS


def test_player_location_is_progression_owned_and_selection_independent():
    resolver = re.search(
        r"function resolvePlayerLocation\(zones\) \{.*?\n  \}",
        WORLD_JS,
        re.S,
    )
    assert resolver
    assert "selectedZoneKey" in resolver.group(0)
    assert "zone.status === 'unlocked'" in resolver.group(0)
    selected_renderer = re.search(
        r"function renderSelectedZone\(.*?\n  \}",
        WORLD_JS,
        re.S,
    )
    assert selected_renderer
    assert "updatePlayerMarker" not in selected_renderer.group(0)
    assert "data-player-location" in WORLD_JS


def test_base_map_identity_is_unchanged():
    base_map = ROOT / "assets/maps/e10_world_stage_v1_base.webp"
    assert base_map.stat().st_size == 651432
    assert hashlib.sha256(base_map.read_bytes()).hexdigest() == (
        "f092dd37507e1ba5d9a7cfeca2951de8aa9b313ffa7d4ff911d18be123d4256a"
    )
