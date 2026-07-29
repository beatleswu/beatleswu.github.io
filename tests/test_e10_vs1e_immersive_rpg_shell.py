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


def test_navigation_uses_decorative_repo_native_svg_without_emoji():
    assert NAV_HTML.count('class="e9-nav__icon"') == 6
    assert NAV_HTML.count('aria-hidden="true"') == 6
    assert NAV_HTML.count('focusable="false"') == 6
    for route in (
        'href="#"',
        'href="/hero?tab=hero"',
        'href="/hero?tab=equipment"',
        'href="/inventory"',
        'href="/daily_challenge"',
        'href="/shop"',
    ):
        assert route in NAV_HTML
    assert not re.search(r"[\U0001F300-\U0001FAFF]", NAV_HTML)


def test_hud_has_no_fabricated_avatar_or_placeholder_resource():
    assert "top-hud-avatar" not in TOP_HTML
    assert "e10-hud-brand__crest" in TOP_HTML
    assert 'aria-hidden="true"' in TOP_HTML
    assert 'id="top-hud-level" hidden' in TOP_HTML
    assert 'id="top-hud-coins" hidden' in TOP_HTML
    assert "🪙" not in TOP_HTML
    assert "🪙" not in TOP_JS
    assert "data.coins !== null" in TOP_JS
    assert "e10.rpg.coins_label" in TOP_JS


def test_i18n_and_cache_versions_are_coupled():
    assert "'e10.rpg.world_stage_label'" in I18N
    assert "'e10.rpg.coins_label'" in I18N
    assert "ASSET_VERSION = 'e10-vs1e-immersive-rpg-shell'" in FLAGS
    assert "const VERSION     = 'v210-e10-vs1e-immersive-rpg-shell'" in SW
    assert "/css/e9/immersive_rpg.css?v=20260729e10vs1e" in INDEX
    assert "/js/e9/feature_flags.js?v=20260729e10vs1e" in INDEX
    assert "/js/e9/top_hud.js?v=20260729e10vs1e" in INDEX
    assert "/js/e9/world_stage.js?v=20260729e10vs1e" in INDEX


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


def test_boss_anchor_visibility_and_state_non_color_cues_remain():
    assert ".e9-map-stage__boss-anchors" in CSS
    assert "visibility: hidden" in CSS
    assert ".e9-zone__number" in CSS
    assert '.e9-zone__state' in CSS
    assert ".e9-zone--completed" in CSS
    assert ".e9-zone[disabled]" in CSS
    assert '.e9-zone[aria-pressed="true"]' in CSS
