"""E10 World Map player-avatar marker contracts.

These checks deliberately keep the World Map consumer dependent on one
resolved presentation boundary, not on the current character catalog or
Hero preview implementation.
"""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
PLAYER_STATE = (ROOT / "js/e9/adapters/player_state.js").read_text(encoding="utf-8")
WORLD_CSS = (ROOT / "css/e9/world_stage.css").read_text(encoding="utf-8")
ART_CSS = (ROOT / "css/e9/art_directed_runtime.css").read_text(encoding="utf-8")
WORLD_HTML = (ROOT / "components/adventure/world_stage.html").read_text(encoding="utf-8")
HERO = (ROOT / "hero.html").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")


def _function_body(source, name):
    start = source.index(f"function {name}(")
    next_function = source.find("\n  function ", start + 1)
    return source[start:] if next_function < 0 else source[start:next_function]


def test_world_map_has_one_resolved_avatar_boundary_and_no_catalog_coupling():
    assert "fetchAvatarPresentation" in WORLD
    assert "state.avatarPresentation" in WORLD
    assert "presentation.asset" in WORLD
    assert "presentation.fallbackAsset" in WORLD
    assert "CHARACTER_PRESENTATIONS" not in WORLD
    assert "CHARACTER_ASSETS" not in WORLD
    assert "COMBAT_GEAR" not in WORLD
    assert "hero_combat_gear_v1" not in WORLD
    assert "localStorage" not in WORLD
    assert "character_key" not in WORLD
    assert not re.search(r"chibi_[a-z_]+_normalized\.webp", WORLD)


def test_provider_contract_is_replaceable_and_keeps_registry_private():
    assert "function resolveCurrentPlayerAvatarPresentation(raw)" in PLAYER_STATE
    assert "function fetchAvatarPresentation(fetchImpl)" in PLAYER_STATE
    assert "Preview/local-loadout state is deliberately not an input" in PLAYER_STATE
    assert "preview_character_key" not in PLAYER_STATE
    provider = _function_body(PLAYER_STATE, "resolveCurrentPlayerAvatarPresentation")
    assert "return {" in provider
    for field in ("id:", "asset:", "fallbackAsset:", "presentationType:"):
        assert field in provider
    assert "DEFAULT_CHARACTER_KEY = 'apprentice'" in PLAYER_STATE
    assert "CHARACTER_PRESENTATIONS" not in _function_body(WORLD, "syncPlayerMarkerPresentation")


def test_committed_and_preview_authorities_are_distinct_in_repository():
    assert "character_key: _combatGear.character" in HERO
    assert "COMBAT_STORAGE_KEY = 'hero_combat_gear_v1'" in HERO
    assert "GET /api/player/appearance" in PLAYER_STATE
    assert "Preview/local-loadout state is deliberately not an input" in PLAYER_STATE
    assert "player_appearance" in APP and "character_key" in APP


def test_marker_location_uses_current_zone_only_and_selection_renderer_does_not_move_it():
    resolver = _function_body(WORLD, "resolvePlayerLocation")
    assert "currentZoneKey" in resolver
    assert "findZone(zones, currentZoneKey)" in resolver
    assert "selectedZoneKey" in resolver
    assert "zone.status === 'unlocked'" in resolver
    selected = _function_body(WORLD, "renderSelectedZone")
    assert "state.selectedZoneKey = zone.key" in selected
    assert "reconcilePlayerNodeMarker(root, zone" not in selected
    assert "currentPlayerZoneKey" in WORLD
    assert "selectedZoneKey" in WORLD
    assert "challengeTargetZoneKey" in WORLD
    assert "data-player-location" in WORLD


def test_exactly_one_marker_host_moves_between_responsive_surfaces():
    reconcile = _function_body(WORLD, "reconcilePlayerNodeMarker")
    assert WORLD.count("function reconcilePlayerNodeMarker(") == 1
    assert "markerHosts.slice(1).forEach(function (duplicate) { duplicate.remove(); });" in reconcile
    assert "restorePlayerMarkerHost(root, mapStage);" in reconcile
    assert "var mobileHero = marker;" in reconcile
    assert "document.createElement('span')" not in reconcile
    assert "mobileHero.style.pointerEvents = 'none';" in reconcile
    assert 'id="e9-world-stage-player"' in WORLD_HTML
    assert WORLD_HTML.count('id="e9-world-stage-player"') == 1


def test_invalid_location_fails_closed_without_selected_zone_fallback():
    reconcile = _function_body(WORLD, "reconcilePlayerNodeMarker")
    assert "if (!zone || !anchor)" in reconcile
    assert "marker.hidden = true;" in reconcile
    assert "syncPlayerMarkerPresentation(root, null);" in reconcile
    assert "state.selectedZoneKey" not in reconcile
    assert "zones.filter(function (zone) { return !zone.locked" not in reconcile


def test_marker_is_node_relative_and_touch_transparent_across_rwd_surfaces():
    assert "--anchor-x" in WORLD_CSS and "--anchor-y" in WORLD_CSS
    assert "top: var(--anchor-y)" in ART_CSS
    assert "left: var(--anchor-x)" in ART_CSS
    assert "pointer-events: none" in WORLD_CSS
    assert "pointer-events: none" in ART_CSS
    assert "e10-player-marker-avatar" in ART_CSS
    assert "@media (max-width: 767px)" in ART_CSS
    assert "@media (min-width: 768px) and (max-width: 1279px) and (orientation: portrait)" in ART_CSS
    assert "@media (min-width: 768px) and (max-width: 1279px) and (orientation: landscape)" in ART_CSS
    assert "transform: translate(-50%, -100%)" in ART_CSS
    assert "prefers-reduced-motion" in ART_CSS


def test_default_fallback_is_the_same_character_system_default():
    assert "DEFAULT_CHARACTER_KEY = 'apprentice'" in PLAYER_STATE
    assert "chibi_apprentice_normalized.webp" in PLAYER_STATE
    assert "chibi_reference_normalized.webp" not in PLAYER_STATE
    assert "character:'apprentice'" in HERO or "character: 'apprentice'" in HERO


def test_server_progression_authority_remains_separate_from_map_selection():
    assert "def _adventure_current_zone_key(" in APP
    assert "current_zone_key" in APP
    assert "selected_zone_key" in APP
    assert "active_zone_key" in APP
    assert "server-owned player node; never use selected/recommended" in APP


def test_marker_does_not_reconstruct_current_appearance_or_equipment():
    marker = _function_body(WORLD, "syncPlayerMarkerPresentation")
    assert "presentation.asset" in marker
    assert "presentation.fallbackAsset" in marker
    for forbidden in ("character_key", "equipment", "skin", "unlock", "COMBAT_GEAR", "localStorage"):
        assert forbidden not in marker
    assert "data-player-avatar-presentation" in marker
