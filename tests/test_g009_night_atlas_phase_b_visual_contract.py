"""G009 Night Atlas Phase B — task-specific visual contract (non-frozen).

Source-level checks for the Owner-authorized (D1-D6) visual-only refactor:
one shared token/component layer, a dark shared shell, the Navigator's Rail,
gold-for-selected, and the retirement of the page-private skins. Product
semantics (seven destinations, Shop browse-preview, read-only Backpack) are
asserted unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


SITE_NAV = read("site-nav.js")
ART_CSS = read("css/e9/art_directed_runtime.css")
WORLD_CSS = read("css/e9/reference_world_map.css")
HERO_CSS = read("css/g009_hero_hub_batch_a.css")

LANDSCAPE_MEDIA = (
    r"@media \(min-width: 768px\) and \(max-width: 1279px\) and "
    r"\(orientation: landscape\) \{.*?\n\}"
)
RAIL_MARKER = "G009 Owner real-iPad final landscape navigation corrective"


def test_shared_token_layer_is_defined_once_in_the_shared_shell():
    assert "const NIGHT_ATLAS_CSS = `" in SITE_NAV
    assert "style.textContent = NIGHT_ATLAS_CSS + `" in SITE_NAV
    for token in (
        "--na-navy-950: #070d22;",
        "--na-gold-300: #e3b457;",
        "--na-cyan-300: #45d6c0;",
        "--na-text: #f7f1df;",
        "--na-radius-md: 16px;",
        "--na-shadow-1:",
        "--na-space-4: 16px;",
    ):
        assert SITE_NAV.count(token) == 1, token


def test_shared_components_are_each_defined_for_every_ledger_surface():
    layer = SITE_NAV.split("const NIGHT_ATLAS_CSS = `", 1)[1].split("`;", 1)[0]
    for component in (
        ".na-panel", ".na-card", ".na-btn", ".na-btn--primary", ".na-tag",
        ".na-tabs", ".na-tab", ".na-kicker", ".na-title", ".na-stat__value",
        ".na-empty", ".na-field",
    ):
        assert component in layer, component
    for surface in ("NA_PROGRESS", "NA_TAVERN", "NA_SHOP", "NA_BACKPACK"):
        assert f"const {surface} = 'body[data-g009-surface=" in SITE_NAV
        assert "${" + surface + "}" in layer


def test_shell_bar_and_settings_modal_are_dark_night_atlas():
    # The black-teal bar and the cream settings/drawer base are gone.
    assert "rgba(5,10,12,.94)" not in SITE_NAV
    assert "#fff8e7" not in SITE_NAV
    settings = SITE_NAV.split("/* D6: the settings modal is a dark Night Atlas dialog", 1)[1]
    settings = settings.split(".g009-learning-secondary {", 1)[0]
    assert ".cg-nav-settings__panel {" in settings
    assert "linear-gradient(180deg, #17213f 0%, #101832 48%, #070d24 100%)" in settings
    assert "var(--na-gold-100)" in settings


def test_gold_marks_the_selected_item_across_shell_and_hero():
    active = re.search(r"\.cg-nav-link\.active \{.*?\}", SITE_NAV, re.S).group(0)
    assert "var(--na-gold-100)" in active
    assert "inset 0 -2px 0 var(--na-gold-300)" in active
    hero_active = re.search(
        r'body\[data-g009-hero-hub="batch-a"\] \.g009-subtab\.is-active \{.*?\n\}',
        HERO_CSS,
        re.S,
    ).group(0)
    assert "cyan" not in hero_active
    # D4: non-live action controls carry no cyan.
    for selector in (".g009-inline-action {\n  padding", ".g009-action-button {\n  display: inline-flex;"):
        block = HERO_CSS.split('body[data-g009-hero-hub="batch-a"] ' + selector, 1)[1].split("}", 1)[0]
        assert "cyan" not in block and "69, 214, 192" not in block, selector
    active_chip = HERO_CSS.split('body[data-g009-hero-hub="batch-a"] .g009-active-chip {\n  color:', 1)[1].split("}", 1)[0]
    assert "var(--g009-cyan-300)" in active_chip  # live state keeps cyan
    assert "var(--g009-gold-300)" in hero_active
    # Cyan survives only as live character state.
    assert "var(--g009-cyan-300)" in HERO_CSS


def test_ipad_landscape_shell_keeps_readable_labels_and_the_text_floor():
    compact = re.search(r"@media \(max-width: 1023px\) \{.*?\n      \}", SITE_NAV, re.S)
    assert compact and ".cg-nav-link span { display: none; }" in compact.group(0)
    # Labels are no longer hidden across the whole <= 1200px range.
    assert "@media (max-width: 1200px)" not in SITE_NAV
    assert "font-size: 10.5px" not in SITE_NAV
    assert "width: 44px; height: 44px; min-width: 44px; min-height: 44px;" in SITE_NAV


def test_navigators_rail_has_a_single_owner_and_keeps_seven_links():
    structural = re.search(LANDSCAPE_MEDIA, WORLD_CSS, re.S).group(0)
    assert '.cg-nav[data-e10-session-strip="1"]' in structural
    assert "#e9-bottom-dock-slot { display: none !important; }" in structural
    assert ".e9-nav__item" not in structural
    assert ".e9-nav__icon" not in structural

    rail = ART_CSS.split(RAIL_MARKER, 1)[1]
    # One skin block; two small structural blocks extend its reach to large
    # touch-primary iPads and the doubled installed-app viewport.
    assert rail.count("@media") == 3
    touch = "(min-width: 1280px) and (orientation: landscape) and (hover: none) and (pointer: coarse)"
    assert rail.count(touch) == 2
    reach = rail.split("@media " + touch + " {", 1)[1]
    assert "#e9-bottom-dock-slot {" in reach and "display: none !important;" in reach
    # A fine-pointer desktop is never matched: every >=1280px rule is touch-gated.
    for query in re.findall(r"@media ([^{]+)\{", rail):
        for part in query.split(","):
            if "min-width: 1280px" in part or "min-width: 1900px" in part:
                assert "(hover: none)" in part and "(pointer: coarse)" in part, part
    assert "width: 168px !important;" in rail
    assert "grid-template-rows: repeat(7, minmax(44px, 1fr)) !important;" in rail
    assert "border-radius: 50% !important;" in rail
    assert "font-size: 13px !important;" in rail
    assert "min-height: 52px !important;" in rail
    assert "li:nth-child(3)::after" in rail
    assert "li:nth-child(5)::after" in rail
    assert "white-space: nowrap !important;" in rail
    assert "writing-mode: horizontal-tb !important;" in rail

    nav = SITE_NAV.split("const NAV_ITEMS = [", 1)[1].split("];", 1)[0]
    assert nav.count("href:") == 7
    assert "href: '/'" not in nav


def test_page_private_skins_are_retired_and_pages_declare_night_atlas_tokens():
    stats = read("stats.html")
    for retired in ("panel_wood.webp", "rgba(252,240,211", "stats_bg", "frame_scroll_cream"):
        assert retired not in stats, retired
    assert "--cream:    var(--na-navy-950, #070d22);" in stats

    tavern = read("community.html")
    for retired in ("btn_plank.webp", "tavern_bg.webp", "scroll_board.webp", "panel_wood.webp"):
        assert retired not in tavern, retired
    assert "podium_top3.webp" in tavern  # the one illustrated focal area

    # Curriculum Map no longer restyles the shared shell and sits on the
    # shared navy ground (its inner guild cards are not migrated in Phase B).
    curriculum = read("curriculum.html")
    assert ".cg-nav-link.active" not in curriculum
    assert ".cg-brand-text {" not in curriculum
    assert "linear-gradient(180deg, #0b1430 0%, #070d22 62%)" in curriculum

    backpack = read("inventory.html")
    assert "--cream:    var(--na-navy-950, #070d22);" in backpack
    # Theming no longer lives in the navigation script as a token inversion.
    assert "--cream: #070d24" not in SITE_NAV


def test_locked_product_semantics_are_untouched():
    shop = read("shop.html")
    assert 'data-g009-shop-mode="browse-preview"' in shop
    assert "const G009_SHOP_BROWSE_PREVIEW_ONLY = true;" in shop
    assert 'data-g009-shop-preview-status="coming-soon"' in shop
    assert "body[data-g009-shop-mode=\"browse-preview\"] .price," in shop
    assert "/assets/shop/shop_bg.webp" in shop

    backpack = read("inventory.html")
    assert "const G009_BACKPACK_READ_ONLY = true;" in backpack
    assert 'data-g009-equipment-write="false" hidden' in backpack
    assert 'body[data-g009-surface="backpack"] .backpack-use,' in SITE_NAV

    assert 'body[data-g009-surface="learning-progress"] .stats-col-weak' in SITE_NAV
    assert "data-g009-global-nav=\"7\"" in SITE_NAV


def test_rail_restores_locked_route_order_and_portrait_chrome_has_a_pwa_mirror():
    rail = ART_CSS.split(RAIL_MARKER, 1)[1]
    assert "order: 0 !important;" in rail
    chrome = ART_CSS.split("G009 Night Atlas — World Map portrait chrome", 1)[1].split(RAIL_MARKER, 1)[0]
    plain = 'body[data-e10-visual-skin="immersive-rpg"] #e9-adventure-shell #e9-world-stage-details {'
    mirror = "html[data-go-portrait-tablet-override] " + plain
    assert chrome.count(mirror) == 1
    assert chrome.count(plain) == 2  # media block + mirror
    # Colour-only: the mission card's grid and placement stay owned elsewhere.
    for geometry in ("grid-template", "grid-area", "position:"):
        assert geometry not in chrome, geometry


def test_shell_overlays_are_viewport_anchored_and_language_switch_is_dark():
    bar = re.search(r"\n      \.cg-nav \{.*?\n      \}", SITE_NAV, re.S).group(0)
    # A filtered bar would become the containing block of the fixed drawer/dialog.
    assert "backdrop-filter" not in bar
    assert ".cg-nav-presence[hidden], .cg-nav-presence-count[hidden] { display: none; }" in SITE_NAV
    assert ".cg-nav-settings__panel .i18n-switcher-btn.active-lang" in SITE_NAV
    assert not re.search(r"font-size: (?:8|9|10|10\.5|11)px", SITE_NAV)
    mobile = read("mobile-nav.js")
    assert "rgba(17,12,8,.96)" not in mobile and "font-size: 12px" in mobile
    assert mobile.count("href: '/") == 5


def test_curriculum_and_hero_honors_use_night_atlas_surfaces():
    curriculum = read("curriculum.html")
    assert "--cream:    var(--na-navy-950, #070d22);" in curriculum
    for retired in ("guild_wood_bg", "qb_board_bg", "qb_parchment", "quest_card.png",
                    "daily_scroll", "guild_side_panel", "guild_left_banner"):
        assert retired not in curriculum, retired
    assert "npc_sage.png" in curriculum  # the elder's band: the one warm accent
    assert 'body[data-g009-hero-hub="batch-a"] .title-item {' in HERO_CSS
    shop_tag = 'body[data-g009-surface="shop"][data-g009-shop-mode="browse-preview"] .btn[data-equipment-purchase]'
    assert shop_tag in SITE_NAV

def test_owner_ipad_world_map_nodes_keep_three_star_progression_slots():
    root = Path(__file__).resolve().parents[1]
    js = (root / "js" / "e9" / "world_stage.js").read_text(encoding="utf-8")
    css = (root / "css" / "e9" / "art_directed_runtime.css").read_text(encoding="utf-8")

    assert "OWNER_REAL_IPAD_NIGHT_ATLAS_STAR_STRIP_CORRECTIVE_001" in css
    assert "top: calc(100% + 5px);" in css
    assert "width: 20px;" in css
    assert "background: rgba(12, 18, 31, .48);" in css
    assert "grayscale(.38) opacity(.62)" in css
    assert "for (var starIndex = 0; starIndex < 3; starIndex += 1)" in js
    assert "if (!zone.locked && (zone.cleared || zone.stars > 0))" not in js
