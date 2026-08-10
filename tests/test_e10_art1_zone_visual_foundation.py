"""E10-ART-1 regression contract: presentation-only World Stage themes.

The zone keys are the current canonical Adventure identities used by the
existing intro-film flow.  This test deliberately guards CSS presentation
only: it must not create a second cinematic, progression state, or audio
contract.
"""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "css" / "e9" / "world_stage.css").read_text(encoding="utf-8")
WORLD_STAGE = (ROOT / "js" / "e9" / "world_stage.js").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")

CANONICAL_ZONE_KEYS = (
    "k26_30", "k21_25", "k16_20", "k11_15", "k6_10",
    "k1_5", "d1_2", "d3_4", "d5_6", "d7_plus",
)


def _theme_rule(key):
    match = re.search(rf'\.e9-zone\[data-zone="{re.escape(key)}"\]\s*\{{([^}}]+)\}}', CSS)
    assert match, f"missing presentation theme for canonical zone {key}"
    return match.group(1)


def test_all_canonical_intro_zone_keys_have_a_presentation_theme():
    assert len(CANONICAL_ZONE_KEYS) == 10
    for key in CANONICAL_ZONE_KEYS:
        rule = _theme_rule(key)
        assert "--zone-bg-base:" in rule
        assert "--zone-accent:" in rule
        assert f"zone.key === '{key}'" in INDEX


def test_zone_identity_tokens_do_not_encode_gameplay_state():
    forbidden = ("locked", "completed", "selected", "recommended", "unlocked", "skipped")
    for key in CANONICAL_ZONE_KEYS:
        assert not any(token in _theme_rule(key).lower() for token in forbidden)
    assert ".e9-zone--locked" in CSS
    assert ".e9-zone--completed" in CSS
    assert '.e9-zone[aria-pressed="true"]' in CSS


def test_decorative_atmosphere_is_noninteractive_and_reduced_motion_safe():
    assert ".e9-zone::before," in CSS
    assert "pointer-events: none;" in CSS
    assert "@media (prefers-reduced-motion: reduce)" in CSS
    assert "transition: none;" in CSS


def test_existing_intro_and_audio_contracts_are_not_reimplemented_here():
    assert "ADVENTURE_INTRO_STORAGE_KEY" not in INDEX
    assert "adventure_intro_seen_v2" not in INDEX
    assert "function adventureIntroSeen(zone)" in INDEX
    assert "function markAdventureIntroSeen(zone)" in INDEX
    assert "'/api/adventure/cinematics/seen'" in INDEX
    assert "_adventureCinematicState" in INDEX
    assert "function _stopIntroFilm()" in INDEX
    assert "function skipIntroFilm()" in INDEX
    assert "audioSrc: '/assets/storyboards/" in INDEX
    assert "localStorage" not in WORLD_STAGE
    assert "new Audio" not in WORLD_STAGE
    assert "boss-cinematic" not in WORLD_STAGE
