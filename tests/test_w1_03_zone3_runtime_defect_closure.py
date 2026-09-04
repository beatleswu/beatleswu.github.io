"""Quality-owned regression contracts for the W1-03 Zone 3 browser debts.

These checks stay at the narrow source seam owned by this amendment.  The
real-browser runners provide the behavioral evidence; this file prevents a
future edit from silently removing the ownership, locked-zone, or replay
cleanup contracts that make those browser checks meaningful.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
WORLD_STAGE = ROOT / "js" / "e9" / "world_stage.js"
ACTIVITY_STATE = ROOT / "js" / "e9" / "adapters" / "activity_state.js"
SRS = ROOT / "srs.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    paren = source.index("(", start)
    depth = 0
    close = paren
    for index in range(paren, len(source)):
        if source[index] == "(":
            depth += 1
        elif source[index] == ")":
            depth -= 1
            if depth == 0:
                close = index
                break
    brace = source.index("{", close)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace : index + 1]
    raise AssertionError(f"unbalanced braces for {signature}")


def test_locked_zone_and_completed_zone_guards_are_runtime_owned():
    source = read(WORLD_STAGE)
    entry = function_body(source, "function dispatchZone1Entry")
    activate = function_body(source, "var activate = function")
    key_activate = function_body(source, "var keyActivate = function")
    suppress = function_body(source, "function suppressAdventureButton")

    assert "zone.cleared === true || zone.status === 'completed'" in entry
    assert "if (zone.locked || zone.canEnter === false) return;" in activate
    assert "if (zone.locked) return;" in key_activate
    assert "button.hidden = true;" in suppress
    assert "button.disabled = true;" in suppress
    assert "button.setAttribute('aria-disabled', 'true');" in suppress
    assert "button.removeAttribute('data-challenge-target-zone');" in suppress
    assert "if (zone.key === ACTIVE_INTRO_ZONE_KEY) suppressAdventureButton(cta);" in source


def test_e9_activity_data_has_one_refresh_owner_and_invalidation():
    activity = read(ACTIVITY_STATE)
    index = read(INDEX)
    srs = read(SRS)

    assert "var srsDueCached = null;" in activity
    assert "var srsDueInFlight = null;" in activity
    assert "var mistakesCached = null;" in activity
    assert "var mistakesInFlight = null;" in activity
    assert "srsDueCached = null;" in activity
    assert "mistakesCached = null;" in activity
    assert "if (!fetchImpl && srsDueInFlight) return srsDueInFlight;" in activity
    assert "if (!fetchImpl && mistakesInFlight) return mistakesInFlight;" in activity
    assert "raw: body" in activity

    e9_init = index[index.index("if (needsImmediatePracticeState || e9ShellRequested)") :]
    e9_init = e9_init[: e9_init.index("} else if (legacyWelcomeShellActive)")]
    assert "const e9ActivityState" in e9_init
    assert "{ activityState: e9ActivityState }" in e9_init
    assert "e9ActivityState.fetchMistakes()" in e9_init
    assert "fetch('/api/mistakes/stats')" in e9_init  # legacy fallback remains intact

    assert "async function init(onBadgeCallback, onMonsterCallback, onQuestCallback, options = {})" in srs
    init = function_body(srs, "async function init")
    assert "activityState.fetchSrsDue()" in init
    assert "result.raw" in init


def test_replay_terminator_clears_presentation_continuation_before_return():
    source = read(INDEX)
    finish = function_body(source, "function _finishZoneCinematicReplay")

    assert "_zoneCinematicPresentationOnly = false;" in finish
    assert "_zoneCinematicAdvanceSegment = null;" in finish
    assert "hideBossCinematic();" in finish
    assert "window.E9.showAdventureZoneCard(zone.key);" in finish
