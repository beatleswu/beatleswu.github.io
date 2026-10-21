"""G010 mainline current UI acceptance checks.

These are additive, non-retroactive checks for the later G009 A1/Future30,
five-medallion navigation and scoped recommended-entry styles. Original
historical 62-case JUnit remains unchanged and must keep its real failures.
Owner real-iPad UAT is still pending.
"""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
REF=(ROOT/"css/e9/reference_world_map.css").read_text(encoding="utf-8")
STAGE=(ROOT/"css/e9/world_stage.css").read_text(encoding="utf-8")
ADAPTER=(ROOT/"js/e9/adapters/player_state.js").read_text(encoding="utf-8")
WORLD=(ROOT/"js/e9/world_stage.js").read_text(encoding="utf-8")
HTML=(ROOT/"components/adventure/world_stage.html").read_text(encoding="utf-8")


def test_recommended_entry_three_rules_have_reference_skin_scope():
    for suffix in ("", "[hidden]", ":focus-visible"):
        pattern = re.compile(
            r'(?m)^body\[data-e10-visual-skin="immersive-rpg"\] '
            r'#e9-adventure-shell #e9-world-stage-recommended-entry'
            + re.escape(suffix) + r"\s*\{"
        )
        assert len(pattern.findall(REF)) == 1, suffix


def test_no_unscoped_recommended_entry_rules():
    rules = re.findall(r'(?m)^([^@/\n][^{]+)\s*\{', REF)
    relevant = [rule for rule in rules if "#e9-world-stage-recommended-entry" in rule]
    assert len(relevant) == 3
    assert all('body[data-e10-visual-skin="immersive-rpg"]' in rule for rule in relevant)


def test_recommended_entry_touch_keyboard_hidden_contract_preserved():
    block = re.search(r'#e9-world-stage-recommended-entry\s*\{([^}]+)\}', REF, re.S)
    assert block
    assert "min-height: 44px" in block.group(1)
    assert "cursor: pointer" in block.group(1)
    assert '#e9-world-stage-recommended-entry:focus-visible' in REF
    assert "outline: 3px solid #16747b" in REF
    assert '#e9-world-stage-recommended-entry[hidden]' in REF
    assert "display: none !important" in REF
    assert 'id="e9-world-stage-recommended-entry"' in HTML


def test_world_map_recommendation_remains_navigation_not_mutation():
    assert "function configureRecommendedEntry(" in WORLD
    assert "function recommendedEntryZone(" in WORLD
    assert "configureRecommendedEntry(root, state);" in WORLD


def test_five_medallion_mobile_dock_is_current_code_not_stale_six():
    assert "grid-template-columns: repeat(5" in REF
    assert "grid-template-rows: repeat(5" in REF
    assert "grid-template-columns: repeat(5,minmax(0,1fr))" in REF
    assert "repeat(6,minmax(0,1fr))" not in REF
    assert "-webkit-line-clamp: 2" in REF
    assert "min-height: 96px" in REF


def test_a1_current_avatar_default_not_legacy_apprentice_promotion():
    assert "var DEFAULT_CHARACTER_KEY = 'A1';" in ADAPTER
    assert "var DEFAULT_VISUAL_MODEL_ID = 'FUTURE30_MODEL_A1_RED';" in ADAPTER
    assert "DEFAULT_CHARACTER_KEY = 'apprentice'" not in ADAPTER
    assert "function resolveDefaultA1Presentation(manifestIndex)" in ADAPTER
    assert "return resolveDefaultA1Presentation(manifestIndex)" in ADAPTER
    assert "derived84_visual_identity_unmapped" in ADAPTER
    assert "LEGACY_CHARACTER_KEYS" in ADAPTER
    assert "apprentice: { id: 'apprentice'" in ADAPTER


def test_player_marker_consumes_provider_without_own_character_registry():
    assert "fetchAvatarPresentation" in WORLD
    assert "state.avatarPresentation" in WORLD
    assert "presentation.asset" in WORLD
    assert "presentation.fallbackAsset" in WORLD
    assert "CHARACTER_PRESENTATIONS" not in WORLD
    assert "CHARACTER_ASSETS" not in WORLD
    assert "localStorage" not in WORLD
