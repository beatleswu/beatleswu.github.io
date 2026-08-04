from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE_NAV = (ROOT / "site-nav.js").read_text(encoding="utf-8")


def test_navigation_ownership_requires_active_e9_shell():
    """The global static marker must not suppress Legacy navigation by itself."""
    assert "function ownsE10Navigation()" in SITE_NAV
    assert "marker?.getAttribute('content') === E10_VS1F_STATIC_CONTRACT" in SITE_NAV
    assert "window.__GO_E9_ACTIVE_SHELL__" in SITE_NAV
    assert "document.body?.getAttribute('data-adventure-shell-active')" in SITE_NAV
    assert "return activeShell === 'e9';" in SITE_NAV


def test_navigation_contract_has_one_accessible_legacy_surface_and_e9_strip():
    """The shared builder keeps one legacy nav surface and strips it only for E9."""
    assert SITE_NAV.count('class="cg-nav-links"') == 1
    assert 'aria-label="主要導覽"' in SITE_NAV
    assert 'header.querySelector(\'.cg-nav-links\')?.remove()' in SITE_NAV
    assert 'header.dataset.e10SessionStrip = \'1\';' in SITE_NAV
    assert 'data-nav-key' in SITE_NAV


def test_marker_only_ownership_is_explicitly_rejected():
    guard = SITE_NAV.split("function ownsE10Navigation()", 1)[1].split(
        "function normalize", 1
    )[0]
    assert "if (!hasStaticContract) return false;" in guard
    assert "const activeShell = window.__GO_E9_ACTIVE_SHELL__" in guard
    assert "return activeShell === 'e9';" in guard


def test_runtime_shell_ownership_is_initialized_before_shared_nav_runs():
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    assert index.index("window.__GO_E9_ACTIVE_SHELL__") < index.index(
        '<script src="/site-nav.js?v=20260804e10navcache1"></script>'
    )
    assert "window.__GO_E9_OWNERSHIP_INITIALIZED__ = true;" in index


def test_legacy_navigation_surface_preserves_keyboard_and_accessibility_contract():
    nav_markup = SITE_NAV.split('<nav class="cg-nav-links"', 1)[1].split(
        "</nav>", 1
    )[0]
    assert 'aria-label="主要導覽"' in nav_markup
    assert "data-i18n-aria-label=\"common.nav.aria\"" in nav_markup
    assert "class=\"cg-nav-link" in nav_markup
    assert "data-nav-key" in nav_markup


def test_e9_session_strip_has_one_explicit_ownership_branch():
    build_nav = SITE_NAV.split("function buildNav()", 1)[1].split(
        "function reconcileNavigation()", 1
    )[0]
    assert build_nav.count("if (ownsE10Navigation())") == 1
    assert "header.dataset.e10SessionStrip = '1';" in SITE_NAV
