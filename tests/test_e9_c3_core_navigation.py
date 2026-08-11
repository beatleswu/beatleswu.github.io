from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
SHELL = (ROOT / "js/e9/shell.js").read_text(encoding="utf-8")
MARKUP = (ROOT / "components/adventure/world_stage.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
HERO = (ROOT / "hero.html").read_text(encoding="utf-8")
LEFT_NAV = (ROOT / "components/adventure/left_nav.html").read_text(encoding="utf-8")
NAV_REGISTRY = (ROOT / "js/e9/navigation_registry.js").read_text(encoding="utf-8")


def test_zone_card_selects_before_adventure_entry_and_has_detail_focus_contract():
    assert "e9:zone-selected" in WORLD
    assert "renderSelectedZone(root, zones, zone.key, true)" in WORLD
    # CTA-only, via the shared dispatcher; card activation must not call it.
    assert "dispatchAdventureAction(contract);" in WORLD
    activate_body = WORLD[WORLD.index("var activate = function ()"):WORLD.index("var keyActivate")]
    assert "startAdventureFromE9" not in activate_body
    assert "dispatchAdventureAction" not in activate_body
    assert "cta.addEventListener('click', cta.__e9AdventureHandler)" in WORLD
    assert "cta.removeEventListener('click', cta.__e9AdventureHandler)" in WORLD
    assert "focusTarget.focus({ preventScroll: true })" in WORLD
    assert "behavior: isMobile || reduced ? 'auto' : 'smooth'" in WORLD
    assert "block: isMobile ? 'center' : 'start'" in WORLD
    assert 'id="e9-world-stage-details"' in MARKUP
    assert 'id="e9-newbie-mainline-cta"' in MARKUP
    assert "onclick=" not in MARKUP


def test_locked_zones_allow_detail_selection_but_never_get_an_entry_target():
    assert "data-zone-locked" in WORLD
    assert "enabled: false, targetZoneKey: null" in WORLD
    assert "button.disabled = !contract.enabled" in WORLD


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
    assert "key: 'hero', target: '/hero?tab=hero'" in NAV_REGISTRY
    assert "key: 'equipment', target: '/hero?tab=equipment'" in NAV_REGISTRY
    assert "key: 'backpack', target: '/inventory'" in NAV_REGISTRY
    assert "data-e10-navigation-list" in LEFT_NAV
    assert "const ALL_TABS = ['hero','equipment','appearance','pet','honors'];" in HERO
    assert "const LEGACY_TAB_ALIASES = { gear:'equipment', class:'hero', badges:'honors' };" in HERO
    assert "history.pushState({ heroTab: canonical }" in HERO
    assert "window.addEventListener('popstate'" in HERO
    for tab in ("hero", "equipment", "appearance", "pet", "honors"):
        assert f'data-tab="{tab}"' in HERO
        assert f'id="tab-{tab}"' in HERO


def test_c3_does_not_introduce_daily_or_second_adventure_state():
    assert "Daily" not in WORLD
    assert "localStorage" not in WORLD
    assert "/api/adventure/bootstrap" not in WORLD.split("function renderSelectedZone", 1)[1]


def test_canonical_adventure_entry_is_exposed_to_the_e9_adapter():
    assert "window.startAdventureStage = startAdventureStage;" in INDEX
    assert "global.enterAdventureZoneInPage({ key: zoneKey })" in SHELL
    assert "global.location.href = '/?zone='" not in SHELL


def test_map_primary_cta_preserves_selected_zone_identity_through_gameplay_handoff():
    sync = WORLD[WORLD.index("function syncInteractionState"):WORLD.index("function ctaContract")]
    primary = WORLD[WORLD.index("function configurePrimaryCta"):WORLD.index("function updateSelectedZoneCopy")]

    assert "resolveChallengeTargetZoneKey(selected)" in sync
    assert "activeMandatoryEncounterAction(state, selected && selected.key)" in sync
    assert "var targetZone = zone;" in primary
    assert "configureAdventureButton(primary, targetZone, contract);" in primary
    assert "var primaryAction = resolvePrimaryCta" not in primary
