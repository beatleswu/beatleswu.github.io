"""Bounded W2-04 contract for the shared mobile navigation rail."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MOBILE_NAV = ROOT / "mobile-nav.js"
APP = ROOT / "app.py"

EXPECTED_ROUTES = (
    "/",
    "/curriculum",
    "/mistakes",
    "/stats",
    "/community",
    "/hero",
    "/inventory",
    "/badges",
    "/rating_test",
    "/play",
    "/shop",
    "/upgrade",
)


def _source() -> str:
    return MOBILE_NAV.read_text(encoding="utf-8")


def _mobile_routes() -> list[str]:
    return re.findall(r"\{ href: '([^']+)'", _source())


def test_mobile_rail_exposes_every_existing_primary_destination():
    assert tuple(_mobile_routes()) == EXPECTED_ROUTES
    assert len(_mobile_routes()) == len(set(_mobile_routes()))


def test_mobile_rail_has_no_placeholder_navigation_targets():
    source = _source()
    assert 'href="#"' not in source
    assert "href: ''" not in source
    assert "href: null" not in source


def test_mobile_rail_is_scrollable_without_page_wide_overflow():
    source = _source()
    assert "overflow-x: auto" in source
    assert "overscroll-behavior-x: contain" in source
    assert "flex: 0 0 58px" in source
    assert "body { padding-bottom: 64px; }" in source


def test_mobile_rail_exposes_keyboard_and_current_page_semantics():
    source = _source()
    assert ".mnb:focus-visible" in source
    assert "aria-current=\"page\"" in source
    assert "aria-label=\"${label}\"" in source
    assert "nav.setAttribute('aria-label'" in source


def test_mobile_destinations_are_existing_server_routes_or_redirects():
    app_source = APP.read_text(encoding="utf-8")
    server_routes = set(re.findall(r"@app\.route\(['\"]([^'\"]+)", app_source))
    missing = [route for route in EXPECTED_ROUTES if route not in server_routes]
    assert not missing, f"mobile nav points at unknown server routes: {missing}"


def test_navigation_change_is_presentation_only():
    source = _source()
    assert "/api/" not in source
    assert "fetch(" not in source
    assert "location.href" not in source
