"""Zone4 shared world-style and presentation-boundary contracts.

These are source-level acceptance guards for the bounded frontend candidate.
They deliberately do not exercise or replace Adventure/Lord server authority.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
WORLD_STAGE = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
WORLD_STAGE_CSS = (ROOT / "css/e9/world_stage.css").read_text(encoding="utf-8")
ZONE4_CONTENT = (ROOT / "js/e10/zone4_cinematic_content.js").read_text(encoding="utf-8")


def _function_body(source: str, signature: str, end_marker: str) -> str:
    start = source.index(signature)
    end = source.index(end_marker, start)
    return source[start:end]


def test_legacy_zone_card_uses_one_shared_renderer_with_zone4_skin_hook():
    body = _function_body(INDEX, "function renderAdventureInfoPanel", "\nfunction renderAdventureMap")

    assert INDEX.count('id="adventure-map-panel"') == 1
    assert "panel.dataset.worldstyleFamily = 'go-odyssey';" in body
    assert "panel.dataset.zoneKey = selectedZone.key;" in body
    assert "data-zone-key=\"k11_15\"" in INDEX
    assert "_adventureStoryReplayAvailable(selectedZone)" in body
    assert "e10.world_stage.replay_story" in body
    assert "_replayAdventureStoryFromZoneCard" in body
    # Zone4 is data/skin inside the existing renderer, not a copied renderer.
    assert "function renderZone4" not in INDEX
    assert "zone4-card-v2" not in INDEX


def test_e9_zone_card_shell_is_shared_and_zone4_is_a_data_skin():
    assert "function renderZones(" in WORLD_STAGE
    assert "function renderSelectedZone(" in WORLD_STAGE
    assert "tile.className = 'e9-zone e9-zone--'" in WORLD_STAGE
    assert "data-zone" in WORLD_STAGE
    assert 'k11_15:' in WORLD_STAGE
    assert '.e9-zone[data-zone="k11_15"]' in WORLD_STAGE_CSS
    assert ".e9-zone-details" in WORLD_STAGE_CSS
    assert ".e9-zone-details__story-replay" in WORLD_STAGE_CSS
    assert "function renderZone4" not in WORLD_STAGE


def test_zone4_lord_states_use_the_shared_overlay_and_generic_state_contract():
    assert INDEX.count('id="boss-cinematic"') == 1
    assert 'data-worldstyle-family="go-odyssey"' in INDEX
    challenge = _function_body(INDEX, "function showZone4LordChallengeCard", "\nfunction startZone4LordRitual")
    ritual = _function_body(INDEX, "function startZone4LordRitual", "\n// ============================================================")
    result = _function_body(INDEX, "function showZone4LordResultCard", "\nfunction _hideZone3ResultPortrait")

    assert "phase-lord-card phase-zone4-lord-card" in challenge
    assert "phase-lord-ritual phase-zone4-lord-ritual" in ritual
    assert "result-win result-zone4-win" in result
    assert "result-lose result-zone4-fail" in result
    for shared_class in (
        "boss-cinematic-kicker",
        "boss-cinematic-title",
        "boss-cinematic-books",
        "boss-cinematic-rules",
        "boss-cinematic-actions",
        "boss-cinematic-btn",
        "boss-cinematic-cancel-btn",
    ):
        assert shared_class in INDEX

    assert "Z4-LORD-01.png" in challenge
    assert "Z4-LORD-02.png" in ritual
    assert "Z4-LORD-03.png" in result
    assert "Z4-LORD-04.png" in result
    assert "Z4-LORD-05.png" in result
    assert "result-zone4-replay" in result
    assert "successPortrait.hidden = !firstClear" in result
    assert "🐇" not in result
    assert "⭐" not in result


def test_zone4_css_changes_skin_not_shared_lord_geometry():
    start = INDEX.index("/* Zone 4 Lord Trial presentation.")
    zone4_css = INDEX[start : INDEX.index(".adventure-ritual-toast", start)]

    assert "width: min(760px, 92vw);" in zone4_css
    assert "left: 6%;" in zone4_css
    assert "right: 6%;" in zone4_css
    assert "max-width: 88%;" in zone4_css
    assert "box-sizing: border-box;" in zone4_css
    assert "background-image: url('/assets/e10/art/zone4/lord/Z4-LORD-01.png')" in zone4_css
    assert "background-image: url('/assets/e10/art/zone4/lord/Z4-LORD-03.png')" in zone4_css
    assert "background-image: url('/assets/e10/art/zone4/lord/Z4-LORD-04.png')" in zone4_css
    assert "zone4-card-v2" not in zone4_css


def test_zone4_story_boundary_and_replay_remain_presentation_only():
    manifest = json.loads((ROOT / "ZONE4_RUNTIME_MANIFEST.json").read_text(encoding="utf-8"))
    main = [beat["beat_id"] for beat in manifest["beats"] if beat.get("track") == "main_story"]
    assert len(main) == 22
    assert main[15] == "Z4_S2_08"
    assert main[16] == "Z4_S3_01"
    assert "LORD_GATE_BEAT_ID = 'Z4_S2_08'" in ZONE4_CONTENT
    assert "POST_LORD_FIRST_BEAT_ID = 'Z4_S3_01'" in ZONE4_CONTENT
    assert "presentationOnly: true" in INDEX
    assert "function _replayAdventureStoryFromZoneCard" in INDEX
    assert "_triggerZone4PostClearFromBossWin" in INDEX
    assert "if (!zone4Cleared) return false;" in INDEX


def test_pwa_parity_remains_a_single_shell_path():
    assert "data-go-display-mode" in INDEX
    assert "display-mode: standalone" in INDEX
    assert "same product surface as" in INDEX
    assert "e9-adventure-shell" in INDEX
    assert "#skill-map" in INDEX
    assert "v242-zone4-storyboard-pwa-parity" in (ROOT / "sw.js").read_text(encoding="utf-8")
