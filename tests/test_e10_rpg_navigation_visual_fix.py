from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE_NAV = (ROOT / "site-nav.js").read_text(encoding="utf-8")
TOP_HTML = (ROOT / "components/adventure/top_hud.html").read_text(encoding="utf-8")
TOP_JS = (ROOT / "js/e9/top_hud.js").read_text(encoding="utf-8")
PLAYER_STATE = (ROOT / "js/e9/adapters/player_state.js").read_text(encoding="utf-8")
CARDS_HTML = (ROOT / "components/adventure/right_cards.html").read_text(encoding="utf-8")
CARDS_JS = (ROOT / "js/e9/right_cards.js").read_text(encoding="utf-8")
NAV_JS = (ROOT / "js/e9/left_nav.js").read_text(encoding="utf-8")
CSS = (ROOT / "css/e9/immersive_rpg.css").read_text(encoding="utf-8")


def test_exact_marker_owns_feature_navigation_but_preserves_session_controls():
    assert "function ownsE10Navigation()" in SITE_NAV
    assert "marker?.getAttribute('content') === E10_VS1F_STATIC_CONTRACT" in SITE_NAV
    assert "header.querySelector('.cg-nav-links')?.remove()" in SITE_NAV
    assert "data-nav-key" in SITE_NAV
    for control in ("cg-nav-presence", "cg-nav-lang", "cg-nav-logout"):
        assert control in SITE_NAV


def test_runtime_avatar_uses_existing_appearance_contract_and_neutral_fallback():
    assert "/api/player/appearance" in PLAYER_STATE
    assert "character_key" in PLAYER_STATE
    assert "chibi_reference_normalized.webp" in PLAYER_STATE
    assert "chibi_mage_normalized.webp" in PLAYER_STATE
    assert 'id="top-hud-avatar"' in TOP_HTML
    assert "function applyVs1fAvatar(root)" in TOP_JS
    assert "image.id = 'top-hud-avatar-image'" in TOP_JS
    assert "marker.getAttribute('content') !== VS1F_STATIC_CONTRACT" in TOP_JS
    assert "avatarEl.onerror" in TOP_JS
    assert "data-e10-avatar-fallback" in TOP_JS
    assert "playerEl.setAttribute('aria-label'" in TOP_JS


def test_identity_and_utility_groups_have_distinct_left_and_right_ownership():
    assert 'class="e9-hud__player"' in TOP_HTML
    assert 'class="e10-hud__right"' in TOP_HTML
    assert TOP_HTML.index('class="e9-hud__player"') < TOP_HTML.index('class="e10-hud__right"')
    assert "grid-template-columns: minmax(190px, auto) minmax(120px, 1fr) minmax(420px, auto)" in CSS
    assert "justify-self: start" in CSS
    assert "justify-content: flex-end" in CSS


def test_drawer_collapses_desktop_column_and_portrait_uses_overlay_controls():
    assert 'id="e10-right-drawer-close"' in CARDS_HTML
    assert "e10-drawer-backdrop" in CARDS_JS
    assert "shell.classList.toggle('is-right-drawer-open', open)" in CARDS_JS
    assert "setOpen(false, true)" in CARDS_JS
    assert "root.__e9DrawerTrigger.focus()" in CARDS_JS
    assert ".e9-body.is-right-drawer-open" in CSS
    assert "grid-template-areas: \"nav stage\"" in CSS
    assert "grid-template-areas: \"nav stage cards\"" in CSS
    assert "(orientation: portrait)" in CSS
    assert "position: fixed" in CSS
    assert ".e10-drawer-backdrop:not([hidden])" in CSS


def test_mobile_labels_do_not_break_words_and_backpack_status_is_separate():
    assert "word-break: normal" in CSS
    assert "overflow-wrap: normal" in CSS
    assert "-webkit-line-clamp: 2" in CSS
    assert "min-width: 44px" in CSS
    assert "e10-nav-status-lock" in NAV_JS
    assert "aria-describedby" in NAV_JS
    assert "e9-visually-hidden" in NAV_JS
    primary_label = "'<span data-i18n=\"' + item.labelKey + '\"></span>'"
    assert primary_label in NAV_JS
    assert "<small data-i18n=\"inv.comingSoon\"></small>" not in NAV_JS
