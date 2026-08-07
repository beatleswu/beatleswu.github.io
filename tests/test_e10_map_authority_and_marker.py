"""Focused E10 map authority, CTA arbitration, and marker lifecycle tests."""

import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
WORLD_STAGE = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
ADVENTURE_ADAPTER = (ROOT / "js/e9/adapters/adventure_state.js").read_text(encoding="utf-8")


def _load_app_module():
    from flask import Blueprint

    modules = {
        "katago_explain": {"KataGoExplainer": type("KataGoExplainer", (), {})},
        "explain_overrides": {"get_override": lambda *args, **kwargs: None},
        "question_taxonomy": {"get_taxonomy": lambda *args, **kwargs: {}},
        "monster_taxonomy": {
            "get_monster_taxonomy": lambda *args, **kwargs: {},
            "mark_encounters": lambda *args, **kwargs: None,
        },
        "chapter_i18n": {
            "localize_topic": lambda *args, **kwargs: "",
            "localize_level": lambda *args, **kwargs: "",
        },
        "backend_i18n": {
            "badge_en": lambda *args, **kwargs: "",
            "skill_node_en": lambda *args, **kwargs: "",
            "title_en": lambda *args, **kwargs: "",
        },
        "grimoire_api": {"grimoire_bp": Blueprint("e10_map_authority_stub", __name__)},
    }
    for name, attrs in modules.items():
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module
    import app

    return app


@pytest.fixture(scope="module")
def app_module():
    return _load_app_module()


def _zone(
    key,
    *,
    unlocked=True,
    cleared=False,
    total=10,
    seen=0,
    defeated=0,
    stars=0,
    boss_ready=False,
    effective_start_zone_key=None,
):
    return {
        "key": key,
        "unlocked": unlocked,
        "cleared": cleared,
        "total": total,
        "seen": seen,
        "defeated": defeated,
        "stars": stars,
        "boss_ready": boss_ready,
        "attempts": 0,
        "best_score": 0,
        "effective_start_zone_key": effective_start_zone_key,
    }


def test_current_zone_new_player_uses_effective_start(app_module):
    zones = [_zone("k26_30", effective_start_zone_key="k26_30")]
    assert app_module._adventure_current_zone_key(zones) == "k26_30"


def test_current_zone_uses_first_canonical_unlocked_incomplete_node(app_module):
    zones = [
        _zone("k26_30", cleared=True, effective_start_zone_key="k26_30"),
        _zone("k21_25", seen=2),
        _zone("k16_20", unlocked=False),
    ]
    assert app_module._adventure_current_zone_key(zones) == "k21_25"


def test_current_zone_uses_last_completed_playable_node_when_all_available_complete(app_module):
    zones = [
        _zone("k26_30", cleared=True, effective_start_zone_key="k26_30"),
        _zone("k21_25", cleared=True, stars=3),
        _zone("k16_20", unlocked=False),
    ]
    assert app_module._adventure_current_zone_key(zones) == "k21_25"


def test_current_zone_fails_closed_for_unavailable_or_invalid_authority(app_module):
    assert app_module._adventure_current_zone_key([_zone("k26_30", unlocked=False)]) is None
    assert app_module._adventure_current_zone_key([_zone("k26_30", effective_start_zone_key="not-a-zone")]) is None


def test_selected_and_recommended_display_state_cannot_move_authority(app_module):
    zones = [
        _zone("k26_30", effective_start_zone_key="k26_30"),
        _zone("k21_25"),
    ]
    selected_map = app_module._adventure_map_state_from_zones(zones, selected_stage_key="k21_25")
    default_map = app_module._adventure_map_state_from_zones(zones, selected_stage_key="k26_30")
    assert selected_map["current_zone_key"] == "k26_30"
    assert default_map["current_zone_key"] == "k26_30"
    assert selected_map["selected"]["zone_key"] == "k21_25"
    assert selected_map["recommended"]["zone_key"] == default_map["recommended"]["zone_key"]


def test_eligible_lord_wins_over_replenish_stars(app_module):
    zones = [
        _zone("k26_30", effective_start_zone_key="k26_30", stars=1),
        _zone("k21_25", seen=3, stars=1, boss_ready=True),
    ]
    result = app_module._adventure_map_state_from_zones(zones)
    assert result["primary_action"]["kind"] == "challenge_lord"
    assert result["primary_action"]["zone_key"] == "k21_25"


def test_completed_lord_never_emits_incorrect_challenge_action(app_module):
    zones = [
        _zone("k26_30", effective_start_zone_key="k26_30", seen=2),
        _zone("k21_25", seen=10, cleared=True, stars=1, boss_ready=False),
    ]
    result = app_module._adventure_map_state_from_zones(zones)
    assert result["primary_action"]["kind"] != "challenge_lord"


def test_marker_reconciliation_is_single_authoritative_pipeline():
    assert WORLD_STAGE.count("function reconcilePlayerNodeMarker(") == 1
    assert "function updatePlayerMarker(" not in WORLD_STAGE
    assert "resolvePlayerLocation(zones, currentZoneKey)" in WORLD_STAGE
    assert "data-e10-shell-generation" in WORLD_STAGE
    assert "root.querySelectorAll('.e10-current-hero').forEach(function (hero) { hero.remove(); });" in WORLD_STAGE
    assert "marker.style.pointerEvents = 'none';" in WORLD_STAGE
    assert "mobileCards ? '.e10-current-hero' : '#e9-world-stage-player'" in WORLD_STAGE
    assert "reconcilePlayerNodeMarker(root, playerLocation, state.generation);" in WORLD_STAGE


def test_current_zone_null_fails_closed_and_reconciliation_removes_stale_markers():
    marker_start = WORLD_STAGE.index("function reconcilePlayerNodeMarker(")
    marker_end = WORLD_STAGE.index("\n  function newbieCtaText(", marker_start)
    marker = WORLD_STAGE[marker_start:marker_end]
    assert "if (!zone || !anchor)" in marker
    assert "marker.hidden = true;" in marker
    assert "markerHosts.slice(1).forEach(function (duplicate) { duplicate.remove(); });" in marker
    assert "document.querySelectorAll('.e10-current-hero').forEach(function (hero)" in marker


def test_battle_return_path_force_refreshes_shared_adventure_bootstrap():
    assert "function refreshAdventureState(fetchImpl)" in ADVENTURE_ADAPTER
    assert "requestInit.cache = 'no-store'" in ADVENTURE_ADAPTER
    assert "adapter.refreshAdventureState()" in WORLD_STAGE
    assert "adapter.fetchAdventureState(null, { forceRefresh: true })" in WORLD_STAGE


def test_fresh_bootstrap_authority_is_passed_to_the_map_render_boundary():
    assert "authority = result.data;" in WORLD_STAGE
    assert "authority.generation = generation;" in WORLD_STAGE
    assert "renderZones(root, result.data.zones, authority);" in WORLD_STAGE
    assert "renderZones(root, result.data.zones);" not in WORLD_STAGE


def test_authoritative_primary_action_precedes_legacy_skipped_presentation():
    cta_start = WORLD_STAGE.index("function ctaContract(zone, state)")
    cta_end = WORLD_STAGE.index("\n  function usesLandmarkCards(", cta_start)
    cta = WORLD_STAGE[cta_start:cta_end]
    assert cta.index("var primary = resolvePrimaryCta") < cta.index("zone.status === 'skipped_by_placement'")
    assert "primary.kind !== 'replay_completed'" in cta
    assert "kind: 'replenish_stars'" in cta


def test_marker_hosts_remain_non_clickable_and_current_key_is_not_selection_derived():
    assert "mobileHero.style.pointerEvents = 'none';" in WORLD_STAGE
    assert "state.currentPlayerZoneKey = current ? current.key : null;" in WORLD_STAGE
    assert "selectedZoneKey, currentZoneKey" not in WORLD_STAGE
    assert "zones.filter(function (zone) {\n      return !zone.locked && zone.status === 'unlocked';" not in WORLD_STAGE
