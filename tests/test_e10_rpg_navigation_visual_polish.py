import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = (ROOT / "js/e9/navigation_registry.js").read_text(encoding="utf-8")
LEFT_NAV = (ROOT / "js/e9/left_nav.js").read_text(encoding="utf-8")
DOCK = (ROOT / "js/e9/bottom_dock.js").read_text(encoding="utf-8")
TOP_HTML = (ROOT / "components/adventure/top_hud.html").read_text(encoding="utf-8")
TOP_JS = (ROOT / "js/e9/top_hud.js").read_text(encoding="utf-8")
CARDS_JS = (ROOT / "js/e9/right_cards.js").read_text(encoding="utf-8")
CSS = (ROOT / "css/e9/immersive_rpg.css").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
FLAGS = (ROOT / "js/e9/feature_flags.js").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")


REQUIRED_ICONS = {
    "compass", "hero", "equipment", "backpack", "spirit", "shop",
    "records", "battle_log", "tavern", "hall", "star_chart", "arena",
    "pass", "messages", "settings", "daily", "badge", "game_records",
    "coin", "all_features", "close", "lock",
}


def test_rpg_icon_registry_is_complete_dual_tone_and_exact_marker_gated():
    icon_block = REGISTRY[REGISTRY.index("var ICONS = {"):REGISTRY.index("function exactContract")]
    actual = set(re.findall(r"^\s{4}([a-z_]+): '", icon_block, re.M))
    assert REQUIRED_ICONS <= actual
    assert "e10-icon__body" in icon_block
    assert "e10-icon__accent" in icon_block
    assert "e10-icon__detail" in icon_block
    assert "if (!exactContract()) return '';" in REGISTRY
    assert "data-e10-icon-id" in REGISTRY
    assert "<text" not in icon_block.lower()


def test_formal_icons_have_no_emoji_remote_or_external_dependency():
    source = REGISTRY + TOP_JS + CARDS_JS
    assert not re.search(r"[\U0001F300-\U0001FAFF]", source)
    assert "http://" not in REGISTRY and "https://" not in REGISTRY
    assert "cdn" not in REGISTRY.lower()
    assert "url(" not in REGISTRY.lower()


def test_every_navigation_surface_uses_registry_icons_and_i18n_names():
    for source in (LEFT_NAV, DOCK, TOP_JS):
        assert "registry.icon(" in source
        assert "data-i18n" in source
    assert "registry.icon('coin'" in TOP_JS
    assert "registry.icon('close'" in TOP_JS
    assert "registry.icon('close'" in CARDS_JS
    assert "registry.icon('lock'" in LEFT_NAV


def test_button_state_contract_covers_all_six_states():
    assert "data-e10-state', 'default'" in LEFT_NAV
    assert "data-e10-state', 'active'" in LEFT_NAV
    assert "data-e10-state', 'locked'" in LEFT_NAV
    assert "aria-current', 'page'" in LEFT_NAV
    for selector in (
        ".e9-nav__item:hover:not(:disabled)",
        ".e9-nav__item:active:not(:disabled)",
        ".e9-nav__item.is-active",
        '.e9-nav__item[aria-disabled="true"]',
        ".e9-dock__item.is-active",
        '.e9-dock__item[data-e10-state="locked"]',
        ".e9-nav__item:focus-visible",
    ):
        assert selector in CSS


def test_avatar_frame_crop_and_mobile_name_contract_are_explicit():
    assert "object-fit: cover" in CSS
    assert "object-position: center 16%" in CSS
    assert "word-break: keep-all" in CSS
    assert "text-overflow: ellipsis" in CSS
    assert "avatarFallbackSrc" in TOP_JS


def test_mobile_labels_keep_words_and_two_line_capacity():
    assert "word-break: normal" in CSS
    assert "overflow-wrap: normal" in CSS
    assert "-webkit-line-clamp: 2" in CSS
    assert "grid-template-columns: repeat(6, minmax(0, 1fr))" in CSS
    assert "min-height: 44px" in CSS


def test_settings_uses_segmented_language_and_custom_semantic_sound_toggle():
    assert 'id="e10-settings-sound" type="checkbox"' in TOP_HTML
    assert "e10-settings-switch__track" in TOP_HTML
    assert "e10-settings-toggle__state" in TOP_HTML
    assert "appearance: none" in CSS
    assert "input:checked + .e10-settings-switch__track" in CSS
    assert "input:focus-visible + .e10-settings-switch__track" in CSS
    for key, en, zh in (
        ("e10.nav.sound_on", "On", "開啟"),
        ("e10.nav.sound_off", "Off", "關閉"),
    ):
        assert f"'{key}'" in I18N
        assert f"en: '{en}'" in I18N
        assert f"zh: '{zh}'" in I18N


def test_all_features_and_material_skin_are_responsive_and_exact_scoped():
    assert ".e10-more-grid" in CSS
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in CSS
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in CSS
    assert "--e10-b2-brass" in CSS
    assert "--e10-b2-enamel" in CSS
    assert "--e10-b2-parchment" in CSS
    assert "--e10-b2-wood" in CSS
    for selector in re.findall(r"(?m)^([^@/\n][^{]+)\s*\{", CSS):
        if "e10-b2" in selector or "e10-rpg-icon" in selector or "e10-settings-switch" in selector:
            assert 'data-e10-visual-skin="immersive-rpg"' in selector


def test_reduced_motion_and_cache_coupling_are_current():
    assert "@media (prefers-reduced-motion: reduce)" in CSS
    assert "transition-duration: .001ms" in CSS
    assert "animation: none" in CSS
    assert "ASSET_VERSION = 'e10-art-directed-runtime-ui'" in FLAGS
    assert "const VERSION     = 'v227-e10-canonical-layout-contract-recovery'" in SW
    assert INDEX.count("20260801e10art1") >= 8
