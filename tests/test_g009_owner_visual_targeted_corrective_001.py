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


def test_ipad_landscape_uses_shared_drawer_and_hides_duplicate_map_nav_shells():
    media = (
        '@media (max-width: 1024px), '
        '(min-width: 768px) and (max-width: 1279px) and (orientation: landscape)'
    )
    assert media in WORLD_CSS
    landscape = re.search(
        r"@media \(min-width: 768px\) and \(max-width: 1279px\) and "
        r"\(orientation: landscape\) \{.*?\n\}",
        WORLD_CSS,
        re.S,
    )
    assert landscape
    body = landscape.group(0)
    assert '#e9-left-nav-slot { display: none !important; }' in body
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
