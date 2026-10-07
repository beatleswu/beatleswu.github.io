from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HERO_CSS = (ROOT / "css/g009_hero_hub_batch_a.css").read_text(encoding="utf-8")
WORLD_JS = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
WORLD_CSS = (ROOT / "css/e9/reference_world_map.css").read_text(encoding="utf-8")
WORLD_STAGE = (ROOT / "components/adventure/world_stage.html").read_text(encoding="utf-8")
SITE_NAV = (ROOT / "site-nav.js").read_text(encoding="utf-8")


def test_hero_page_head_resets_legacy_generic_header_presentation():
    block = re.search(
        r'body\[data-g009-hero-hub="batch-a"\] \.g009-page-head \{.*?\n\}',
        HERO_CSS,
        re.S,
    )
    assert block
    body = block.group(0)
    assert "background: transparent;" in body
    assert "border: 0;" in body
    assert "box-shadow: none;" in body
    assert "text-align: left;" in body


def test_ipad_portrait_does_not_create_inline_zone_landmark_cards():
    fn = re.search(r"function usesLandmarkCards\(\) \{.*?\n  \}", WORLD_JS, re.S)
    assert fn
    body = fn.group(0)
    assert "viewportClass === 'MOBILE_480'" in body
    assert "IPAD_PORTRAIT_820" not in body
    # The lower selected-zone/current-mission card remains the canonical host.
    assert 'id="e9-world-stage-details-landmark"' in WORLD_STAGE
    assert "#e9-world-stage-details-landmark" in WORLD_JS


def test_ipad_landscape_keeps_visible_seven_link_rail_in_shared_shell_style():
    landscape = re.search(
        r"@media \(min-width: 768px\) and \(max-width: 1279px\) and "
        r"\(orientation: landscape\) \{.*?\n\}",
        WORLD_CSS,
        re.S,
    )
    assert landscape
    body = landscape.group(0)
    assert '.cg-nav[data-e10-session-strip="1"]' in body
    assert 'display: none !important;' in body
    assert '#e9-left-nav-slot {' in body
    assert 'display: block !important;' in body
    assert 'grid-template-rows: repeat(7, minmax(0, 1fr));' in body
    assert 'background: rgba(5, 10, 12, .90);' in body
    assert 'border: 1px solid rgba(251, 191, 36, .22);' in body
    assert '#e9-bottom-dock-slot { display: none !important; }' in body
    assert 'data-g009-global-drawer' in SITE_NAV
    assert 'class="cg-nav-hamburger"' in SITE_NAV


def test_global_navigation_contract_stays_exactly_seven_without_world_map_item():
    nav = SITE_NAV.split("const NAV_ITEMS = [", 1)[1].split("];", 1)[0]
    assert nav.count("href:") == 7
    assert "href: '/curriculum'" in nav
    assert "href: '/play'" in nav
    assert "href: '/community'" in nav
    assert "href: '/hero'" in nav
    assert "href: '/inventory'" in nav
    assert "href: '/shop'" in nav
    assert "href: '/upgrade'" in nav
    assert "href: '/'" not in nav


def test_shared_global_drawer_matches_dark_g009_app_shell_without_restyling_settings():
    assert ".cg-nav-drawer__panel {" in SITE_NAV
    assert "linear-gradient(180deg, #17213f 0%, #101832 48%, #070d24 100%)" in SITE_NAV
    assert "border-right: 1px solid rgba(251,191,36,.24);" in SITE_NAV
    assert ".cg-nav-drawer__header h2 {" in SITE_NAV
    assert ".cg-nav-drawer__links .cg-nav-link.active {" in SITE_NAV
    # Settings remains a separate surface; the dark override is drawer-scoped.
    dark_block = SITE_NAV.split("/* Owner real-iPad corrective: the global drawer", 1)[1]
    assert ".cg-nav-settings__panel {" not in dark_block.split(".cg-nav-settings__panel", 1)[0]
