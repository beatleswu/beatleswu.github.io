from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
SHELL = (ROOT / "js/e9/shell.js").read_text(encoding="utf-8")
MARKUP = (ROOT / "components/adventure/world_stage.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
HERO = (ROOT / "hero.html").read_text(encoding="utf-8")
LEFT_NAV = (ROOT / "components/adventure/left_nav.html").read_text(encoding="utf-8")


def test_zone_card_selects_before_adventure_entry_and_has_detail_focus_contract():
    assert "e9:zone-selected" in WORLD
    assert "renderSelectedZone(root, zones, zone.key, true)" in WORLD
    assert "startAdventureFromE9(zone.key)" in WORLD  # CTA only; card activation must not call it
    assert "focusTarget.focus({ preventScroll: true })" in WORLD
    assert "scrollIntoView({ behavior: 'smooth'" in WORLD
    assert 'id="e9-world-stage-details"' in MARKUP


def test_locked_zones_do_not_get_selection_or_entry_handlers():
    assert "if (!zone.locked)" in WORLD
    assert "if (!zone || zone.locked) return;" in WORLD


def test_locale_changes_rerender_existing_world_stage_without_new_dictionary():
    assert "e9:i18n-changed" in WORLD
    assert "e9:i18n-ready" in WORLD
    assert "e9:i18n-changed" in I18N
    for key in (
        "adventure.newbie.first_stop_title",
        "adventure.newbie.step_battle",
        "adventure.newbie.cta_begin",
    ):
        assert key in I18N


def test_hero_and_equipment_have_distinct_canonical_tabs_and_history_contract():
    assert 'href="/hero?tab=hero"' in LEFT_NAV
    assert 'href="/hero?tab=equipment"' in LEFT_NAV
    assert "const ALL_TABS = ['hero','equipment','gear','pet','class','badges'];" in HERO
    assert "history.pushState({ heroTab: tab }" in HERO
    assert "window.addEventListener('popstate'" in HERO
    assert 'data-tab="hero"' in HERO
    assert 'data-tab="equipment"' in HERO


def test_c3_does_not_introduce_daily_or_second_adventure_state():
    assert "Daily" not in WORLD
    assert "localStorage" not in WORLD
    assert "/api/adventure/bootstrap" not in WORLD.split("function renderSelectedZone", 1)[1]


def test_canonical_adventure_entry_is_exposed_to_the_e9_adapter():
    assert "window.startAdventureStage = startAdventureStage;" in INDEX
    assert "global.location.href = '/?zone=' + encodeURIComponent(zoneKey) + '&adventure=1&resume=1';" in SHELL
