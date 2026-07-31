"""Structural acceptance for the scoped E10 VS1E visual skin.

These tests deliberately protect rollout/lifecycle boundaries in addition to
checking the visual tokens. Browser acceptance covers computed geometry and
real runtime rendering; this module keeps the source contract fail-closed.
"""

from hashlib import sha256
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "css/e9/immersive_rpg.css").read_text(encoding="utf-8")
WORLD_JS = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
TOP_JS = (ROOT / "js/e9/top_hud.js").read_text(encoding="utf-8")
TOP_HTML = (ROOT / "components/adventure/top_hud.html").read_text(encoding="utf-8")
NAV_HTML = (ROOT / "components/adventure/left_nav.html").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
FLAGS = (ROOT / "js/e9/feature_flags.js").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")


def test_skin_is_activated_only_after_real_world_stage_data_renders():
    render_call = "renderZones(root, result.data.zones);"
    enable_call = "enableImmersiveRpgSkin(root, generation);"
    assert WORLD_JS.index(render_call) < WORLD_JS.index(enable_call)
    assert "if (!result.data.zones.length)" in WORLD_JS
    assert "data-e10-visual-skin" in WORLD_JS
    assert "window.E9.registerCleanup" in WORLD_JS
    assert "shell.removeAttribute('data-e10-visual-skin')" in WORLD_JS
    assert "document.body.removeAttribute('data-e10-visual-skin')" in WORLD_JS


def test_visual_rules_are_scoped_to_the_successful_e10_skin_marker():
    assert '#e9-adventure-shell[data-e10-visual-skin="immersive-rpg"]' in CSS
    assert 'body[data-e10-visual-skin="immersive-rpg"]' in CSS
    assert "body[data-adventure-shell-active=\"legacy\"]" not in CSS
    assert "#skill-map" not in CSS

    # Every ordinary rule that targets an E9 component must carry the E10
    # marker. @keyframes and the shared marker declaration are exempt.
    for selector in re.findall(r"(?m)^([^@/\n][^{]+)\s*\{", CSS):
        if ".e9-" not in selector:
            continue
        assert "data-e10-visual-skin" in selector, selector


def test_visual_direction_tokens_and_touch_targets_are_explicit():
    for token in (
        "--e10-parchment",
        "--e10-gold",
        "--e10-metal",
        "--e10-wood",
        "--e10-teal",
        "--e10-focus",
    ):
        assert token in CSS
    assert "min-height: 44px" in CSS
    assert "min-height: 46px" in CSS
    assert "@media (prefers-reduced-motion: reduce)" in CSS
    assert "transition-duration: .001ms" in CSS


def test_navigation_keeps_vs1d_markup_base_safe_and_builds_vs1f_icons_after_marker():
    nav_js = (ROOT / "js/e9/left_nav.js").read_text(encoding="utf-8")
    registry = (ROOT / "js/e9/navigation_registry.js").read_text(encoding="utf-8")
    assert 'class="e9-nav__icon"' not in NAV_HTML
    assert "registry.exactContract()" in nav_js
    assert "data-e10-vs1f-icon" in registry
    for route in ('/hero?tab=hero', '/hero?tab=equipment', '/hero?tab=pet', '/shop', '/daily-challenge'):
        assert route in registry
    assert "target: null" in registry
    assert not re.search(r"[\U0001F300-\U0001FAFF]", NAV_HTML)


def test_hud_restores_vs1d_fallback_and_builds_vs1f_brand_after_marker():
    assert "top-hud-avatar" in TOP_HTML
    assert "e10-hud-brand__crest" not in TOP_HTML
    assert "if (!marker || marker.getAttribute('content') !== VS1F_STATIC_CONTRACT) return;" in TOP_JS
    assert "data-e10-vs1f-brand" in TOP_JS
    assert "e10.world_stage.title" in TOP_JS
    assert "if (avatar) avatar.remove();" not in TOP_JS
    assert 'id="top-hud-level" hidden' in TOP_HTML
    assert 'id="top-hud-coins" hidden' in TOP_HTML
    assert "🪙" not in TOP_HTML
    assert "🪙" not in TOP_JS
    assert "data.coins !== null" in TOP_JS
    assert "e10.rpg.coins_label" in TOP_JS


def test_i18n_and_cache_versions_are_coupled():
    assert "'e10.rpg.world_stage_label'" in I18N
    assert "'e10.rpg.coins_label'" in I18N
    for key in (
        "e10.world_stage.state_locked",
        "e10.world_stage.state_completed",
        "e10.world_stage.state_current",
        "e10.world_stage.state_available",
        "e10.world_stage.continue_adventure",
        "e10.world_stage.selected_quest",
        "e10.world_stage.select_zone",
        "e10.world_stage.select_zone_hint",
        "e10.world_stage.zone_progress",
    ):
        assert f"'{key}'" in I18N
    assert "ASSET_VERSION = 'e10-reference-world-map'" in FLAGS
    assert "const VERSION     = 'v219-e10-reference-world-map'" in SW
    assert "/i18n.js?v=20260731e10reference1" in INDEX
    assert "/css/e9/immersive_rpg.css?v=20260731e10reference1" in INDEX
    assert "/js/e9/feature_flags.js?v=20260731e10reference1" in INDEX
    assert "/js/e9/right_cards.js?v=20260731e10reference1" in INDEX
    assert "/js/e9/world_stage.js?v=20260731e10reference1" in INDEX


def test_skin_does_not_embed_art_or_text_in_image_assets():
    lowered = CSS.lower()
    assert "url(" not in lowered
    assert "data:image" not in lowered
    assert "base64" not in lowered


def test_map_asset_bytes_are_unchanged():
    base = ROOT / "assets/maps/e10_world_stage_v1_base.webp"
    assert base.stat().st_size == 651432
    assert sha256(base.read_bytes()).hexdigest() == (
        "f092dd37507e1ba5d9a7cfeca2951de8aa9b313ffa7d4ff911d18be123d4256a"
    )


def test_responsive_navigation_and_details_follow_orientation_contract():
    assert "@media (min-width: 768px) and (max-width: 1279px) and (orientation: landscape)" in CSS
    assert 'grid-template-areas: "nav stage"' in CSS
    assert "@media (min-width: 768px) and (max-width: 1279px) and (orientation: portrait)" in CSS
    assert "grid-template-columns: repeat(6, minmax(0, 1fr))" in CSS
    assert "position: fixed" in CSS
    assert "env(safe-area-inset-bottom, 0px)" in CSS
    assert "#e9-right-drawer-panel:not([hidden])" in CSS
    assert "@media (max-width: 767px)" in CSS
    assert "grid-template-columns: 30px minmax(0, 1fr) 28px" in CSS
    assert ".e9-zone__inline-details" in CSS
    assert "max-height: calc(100% - 112px)" in CSS
    assert "inlineIsNewbie" in WORLD_JS
    assert "newbieCtaText(zone)" in WORLD_JS
    assert "isMobile || zone.key !== 'k26_30'" in WORLD_JS
    assert "scrollWidth" not in CSS  # no runtime geometry mutation
    assert "--e10-safe-area-bottom: env(safe-area-inset-bottom, 0px)" in CSS
    assert "white-space: nowrap" in CSS
    assert "text-overflow: ellipsis" in CSS
    assert "padding-top: 242px" in CSS
    assert "position: relative" in CSS
    assert "min-height: 1100px" not in CSS


def test_boss_anchor_visibility_and_state_non_color_cues_remain():
    assert ".e9-map-stage__boss-anchors" in CSS
    assert "visibility: hidden" in CSS
    assert ".e9-zone__number" in CSS
    assert '.e9-zone__state' in CSS
    assert ".e9-zone--completed" in CSS
    assert ".e9-zone[disabled]" in CSS
    assert '.e9-zone[aria-pressed="true"]' in CSS


def test_owner_correction_keeps_map_ui_persistent_and_drawer_structural():
    world_html = (ROOT / "components/adventure/world_stage.html").read_text(encoding="utf-8")
    cards_html = (ROOT / "components/adventure/right_cards.html").read_text(encoding="utf-8")
    cards_js = (ROOT / "js/e9/right_cards.js").read_text(encoding="utf-8")
    for required in (
        "e9-world-stage-primary-cta",
        "e9-world-stage-details-progress",
        "e9-zone__plaque",
        "e9-zone__status-text",
        "configurePrimaryCta",
        "dispatchZoneSelection",
    ):
        assert required in (world_html + WORLD_JS)
    assert "e10-drawer-zone-summary" in cards_html
    assert "updateDrawerZoneSummary" in cards_js
    assert "latestZoneSelection" in WORLD_JS
    assert "latestZoneSelection" in cards_js
    assert "delete window.E9.latestZoneSelection" in WORLD_JS


def test_live_language_switch_relocalizes_progress_and_selected_drawer_state():
    cards_js = (ROOT / "js/e9/right_cards.js").read_text(encoding="utf-8")
    assert "root.__e9CompactProgress" in cards_js
    assert "setCompactProgress(root, progress.cleared, progress.total)" in cards_js
    assert "window.E9.latestZoneSelection" in cards_js
    assert "window.E9.on(document, 'e9:i18n-changed', onI18nChanged" in cards_js
    assert "delete root.__e9CompactProgress" in cards_js
    selected_rerender = "renderSelectedZone(root, zones, selected.key, false);"
    localized_dispatch = "dispatchZoneSelection(root, selected);"
    assert WORLD_JS.index(selected_rerender) < WORLD_JS.index(localized_dispatch)
