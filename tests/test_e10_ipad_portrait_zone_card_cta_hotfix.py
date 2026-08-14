from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")


def _render_selected_zone_body():
    start = WORLD.index("function renderSelectedZone(root, zones, zoneKey, focusDetails)")
    end = WORLD.index("\n  function renderZones(", start)
    return WORLD[start:end]


def test_portrait_detail_cta_is_always_refreshed_from_selected_zone_contract():
    body = _render_selected_zone_body()
    assert "configureAdventureButton(cta, zone, ctaContract(zone, state));" in body
    assert "if (zone.key === 'k26_30'" not in body
    # The sole hide is the valid no-zone guard; selecting Zone 1 must not add
    # another responsive/special-case hide after state selection begins.
    assert body.count("cta.hidden = true;") == 1
    assert body.index("cta.hidden = true;") < body.index("state.selectedZoneKey = zone.key;")


def test_completed_zone_semantics_are_not_orientation_derived():
    start = WORLD.index("function ctaContract(zone, state)")
    end = WORLD.index("\n  function usesLandmarkCards(", start)
    contract = WORLD[start:end]
    assert "zone.status === 'completed'" in contract
    assert "kind: 'replay_completed'" in contract
    assert "targetZoneKey: target" in contract
    assert "matchMedia" not in contract


def test_cleared_zone_has_replay_primary_and_star_training_secondary_surface():
    start = WORLD.index("function secondaryCtaContract(zone, state)")
    end = WORLD.index("\n  function usesLandmarkCards(", start)
    contract = WORLD[WORLD.index("function ctaContract(zone, state)"):end]
    assert "zone.cleared === true || zone.status === 'completed'" in contract
    assert "kind: 'replay_completed'" in contract
    assert "function secondaryCtaContract(zone, state)" in contract
    assert "zone.cleared === true && Number(zone.stars || 0) < 3" in contract
    assert "kind: 'replenish_stars'" in contract
    assert "#e9-world-stage-details-secondary-cta" in WORLD


def test_current_mainline_continue_semantics_remain_scoped_to_current_zone():
    start = WORLD.index("function ctaContract(zone, state)")
    end = WORLD.index("\n  function usesLandmarkCards(", start)
    contract = WORLD[start:end]
    assert "target === state.currentPlayerZoneKey" in contract
    assert "t('e10.world_stage.continue_adventure', 'Continue Adventure')" in contract
