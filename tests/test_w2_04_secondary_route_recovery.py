"""Bounded W2-04 recovery contract for the premium weekly secondary route."""

from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WEEKLY_PAGE = ROOT / "premium_weekly.html"
APP = ROOT / "app.py"
PARENT_HEAD = "fb2411e79a2220cd8feb101ebb13119e6ef38342"


def _weekly_source() -> str:
    return WEEKLY_PAGE.read_text(encoding="utf-8")


def _parent_weekly_source() -> str:
    result = subprocess.run(
        ["git", "show", f"{PARENT_HEAD}:premium_weekly.html"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout


def test_issue_existed_before_the_secondary_route_recovery_slice():
    before = _parent_weekly_source()

    assert "site-nav.js" in before
    assert not re.search(r"<header\b", before, flags=re.IGNORECASE)
    assert "mobile-nav.js" not in before


def test_weekly_route_has_an_explicit_localized_recovery_shell():
    source = _weekly_source()

    assert '<header class="weekly-recovery-nav" data-weekly-recovery-nav>' in source
    assert 'href="/" data-i18n="common.brand"' in source
    assert 'data-i18n-aria-label="common.brand.home"' in source
    assert 'data-i18n="nav.practice"' in source
    assert 'href="/hero" data-i18n="nav.skills"' in source
    assert 'id="lang-switcher-weekly"' in source
    assert 'href="#"' not in source


def test_recovery_shell_uses_existing_routes_and_shared_mobile_navigation():
    source = _weekly_source()
    app_source = APP.read_text(encoding="utf-8")
    server_routes = set(re.findall(r"@app\.route\(['\"]([^'\"]+)", app_source))

    recovery_routes = re.findall(
        r'<(?:a|area)\b[^>]*href="([^"#?]+)',
        source,
        flags=re.IGNORECASE,
    )
    assert "/" in recovery_routes
    assert "/hero" in recovery_routes
    assert not [route for route in recovery_routes if route not in server_routes]
    assert source.count("mobile-nav.js") == 1
    assert "site-nav.js" in source


def test_recovery_shell_preserves_native_keyboard_and_pointer_actions():
    source = _weekly_source()

    assert "weekly-recovery-nav a:focus-visible" in source
    assert 'href="/"' in source
    assert 'id="start"' in source
    assert "location.href=`/?premium_set=" in source
