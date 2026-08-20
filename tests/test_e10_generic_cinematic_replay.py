"""Zone 1-10 generic cinematic replay contract (E10_ZONE_GENERIC_CINEMATIC_REPLAY_001).

Owner product rule under test:

    Story cinematics may be replayed once legitimately unlocked, and a repeat
    Lord Trial success replays the post-victory story. Replay may repeat the
    presentation but never progression, reward, unlock, or player position.

The previous rule -- "Lord replay must not re-show POST_CLEAR" -- is superseded,
so this file also pins the superseded suppression as *absent*.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
MODEL = (ROOT / "js" / "game" / "cinematic_replay.js").read_text(encoding="utf-8")
WORLD_STAGE = (ROOT / "js" / "e9" / "world_stage.js").read_text(encoding="utf-8")
RUNNER = ROOT / "tests" / "e2e" / "run_e10_generic_cinematic_replay.mjs"

ZONE_KEYS = ("k26_30", "k21_25", "k16_20", "k11_15", "k6_10", "k1_5")


def _last_json(stdout: str) -> dict:
    decoder = json.JSONDecoder()
    for index in range(len(stdout) - 1, -1, -1):
        if stdout[index] != "{":
            continue
        try:
            value, end = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if not stdout[index + end :].strip():
            return value
    raise AssertionError(f"replay runner emitted no final JSON: {stdout[-2000:]}")


def _strip_line_comments(source: str) -> str:
    """Drop // line comments so a contract never matches its own rationale."""
    return "\n".join(re.sub(r"(^|\s)//.*$", "", line) for line in source.splitlines())


def _function_body(source: str, signature: str) -> str:
    """Extract a top-level function body by brace matching.

    The opening brace is located after the parameter list closes, so a default
    parameter value such as ``options = {}`` is not mistaken for the body.
    """
    start = source.index(signature)
    depth = 0
    cursor = source.index("(", start)
    for index in range(cursor, len(source)):
        char = source[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                cursor = index
                break
    brace = source.index("{", cursor)
    depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace : index + 1]
    raise AssertionError(f"unbalanced braces for {signature}")


# --------------------------------------------------------------------------
# Executable model contract
# --------------------------------------------------------------------------


def test_generic_replay_model_runner_is_green():
    result = subprocess.run(
        ["node", str(RUNNER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    output = f"stdout={result.stdout}\nstderr={result.stderr}"
    assert result.returncode == 0, output
    report = _last_json(result.stdout)
    assert report["status"] == "PASS", output
    assert report["failures"] == 0, output
    assert report["checks"] >= 14, output


# --------------------------------------------------------------------------
# The superseded rule is gone
# --------------------------------------------------------------------------


def test_lord_replay_success_no_longer_suppresses_the_post_victory_cinematic():
    # This exact guard was the old product rule. Its presence anywhere would
    # reinstate the bug: a repeat Lord win with no story ending.
    code = _strip_line_comments(INDEX)
    assert "if (!result.replay) setTimeout" not in code
    assert not re.search(r"if\s*\(\s*!\s*result\.replay\s*\)", code)


def test_post_victory_trigger_receives_the_replay_flag_at_both_call_sites():
    calls = re.findall(
        r"_triggerZone[12]PostClearFromBossWin\(zone,\s*\{\s*replay:\s*result\.replay === true\s*\}\)",
        INDEX,
    )
    assert len(calls) == 2, calls


# --------------------------------------------------------------------------
# Generic, not zone-hardcoded
# --------------------------------------------------------------------------


def test_replay_model_module_is_zone_agnostic():
    for key in ZONE_KEYS:
        assert key not in MODEL, f"{key} leaked into the generic replay model"
    assert "zone1" not in MODEL.lower().replace("zone 1-10", "")
    assert "GoOdysseyCinematicReplay" in MODEL


def test_canonical_segment_order_supports_more_than_three_acts():
    order = re.search(r"var SEGMENT_ORDER = \[(.*?)\];", MODEL, re.S)
    assert order, MODEL[:400]
    phases = re.findall(r"'([a-z_]+)'", order.group(1))
    assert phases == [
        "pre_play",
        "mid_play",
        "boss_ready",
        "post_clear",
        "post_clear_hook",
        "ending",
    ], phases


def test_generic_playback_helpers_carry_no_zone_branch():
    for signature in (
        "function playZoneStoryReplay(zoneKey)",
        "function _triggerZonePostClearFromBossWin(zone, options = {})",
        "function _replayActiveCinematicPhase(zone, phase, onComplete)",
    ):
        body = _function_body(INDEX, signature)
        for key in ZONE_KEYS:
            assert key not in body, f"{signature} hardcodes {key}"


def test_zone_specific_post_clear_triggers_delegate_to_the_generic_one():
    for signature in (
        "function _triggerZone1PostClearFromBossWin(zone, options = {})",
        "function _triggerZone2PostClearFromBossWin(zone, options = {})",
    ):
        body = _function_body(INDEX, signature)
        assert "_triggerZonePostClearFromBossWin(zone, options)" in body, signature
        # The one-time write semantics now live in the generic function only.
        assert "markAdventurePostClearPending" not in body, signature


def test_overlay_replay_dispatch_is_no_longer_a_zone_key_ternary():
    body = _function_body(INDEX, "async function replayIntroFilm()")
    assert "playZone2PostClearFilm(zone)" not in body
    assert "playZone2BossReadyFilm(zone)" not in body
    assert "_replayActiveCinematicPhase(zone, 'post_clear'" in body
    assert "_replayActiveCinematicPhase(zone, 'boss_ready'" in body


def test_replay_story_button_availability_is_model_driven_not_allowlisted():
    body = _function_body(WORLD_STAGE, "function replayAdventureIntro(zoneKey)")
    assert "zoneStoryReplayAvailable(zoneKey)" in body
    assert "k21_25" not in body, "replay is still gated on a zone-key allowlist"
    assert "playStoryReplay" in body
    configure = _function_body(WORLD_STAGE, "function configureStoryReplayButton(button, zone)")
    # E10_REPLAY_STORY_CROSS_SURFACE_IPAD_HOTFIX_002 added an optional second
    # argument (the authoritative zone record the surface already holds), so
    # match the call prefix rather than the exact arity. The property this test
    # actually guards -- availability comes from the shared model-driven
    # predicate and never from a zone-key allowlist -- is unchanged.
    assert "zoneStoryReplayAvailable(zone.key" in configure
    assert "k26_30" not in configure, "button visibility is still allowlisted"


# --------------------------------------------------------------------------
# Replay is presentation only
# --------------------------------------------------------------------------


def test_replay_terminator_writes_no_progression_or_seen_state():
    body = _function_body(INDEX, "function _finishZoneCinematicReplay(zone)")
    forbidden = (
        "markAdventurePostClearSeen",
        "markAdventurePostClearPending",
        "markAdventureIntroSeen",
        "markAdventureBossReadyFilmSeen",
        "showZone1UnlockReveal",
        "showZone2UnlockReveal",
        "fetch(",
    )
    for token in forbidden:
        assert token not in body, f"replay terminator performs {token}"


def test_replay_branch_of_the_post_victory_trigger_writes_nothing():
    body = _function_body(INDEX, "function _triggerZonePostClearFromBossWin(zone, options = {})")
    replay_branch = body[body.index("if (replay) {") : body.index("// First clear")]
    for token in ("markAdventurePostClear", "finishPostClearFilm", "fetch("):
        assert token not in replay_branch, f"replay branch performs {token}"
    assert "presentationOnly: true" in replay_branch


def test_story_replay_is_presentation_only():
    body = _function_body(INDEX, "function playZoneStoryReplay(zoneKey)")
    assert "presentationOnly: true" in body
    for token in ("markAdventure", "fetch(", "finishPostClearFilm"):
        assert token not in body, f"story replay performs {token}"


def test_first_clear_still_marks_pending_and_uses_the_established_finisher():
    body = _function_body(INDEX, "function _triggerZonePostClearFromBossWin(zone, options = {})")
    first_clear = body[body.index("// First clear") :]
    assert "adventurePostClearSeen(zone)" in first_clear
    assert "markAdventurePostClearPending(zone)" in first_clear
    assert "finishPostClearFilm(zone)" in first_clear
    assert "presentationOnly: false" in first_clear


def test_skipping_a_replay_never_falls_through_to_a_first_clear_terminator():
    body = _function_body(INDEX, "function skipIntroFilm()")
    guard = body.index("_zoneCinematicPresentationOnly")
    post_clear_finish = body.index("finishPostClearFilm(zone)")
    # The presentation-only branch must be reached BEFORE the first-clear
    # terminators, and must return.
    assert guard < post_clear_finish
    assert "_finishZoneCinematicReplay(zone)" in body
    assert "_zoneCinematicAdvanceSegment()" in body


def test_presentation_only_flag_is_cleared_by_every_terminator():
    for signature in (
        "function finishPostClearFilm(zone)",
        "function finishBossReadyFilm(zone)",
        "async function finishIntroFilm(zone)",
        "function _finishZoneCinematicReplay(zone)",
        "async function startAdventureStage(zoneKey, options = {})",
    ):
        body = _function_body(INDEX, signature)
        assert "_zoneCinematicPresentationOnly = false" in body, signature


# --------------------------------------------------------------------------
# Unlock authority
# --------------------------------------------------------------------------


def test_unlock_authority_reads_server_state_not_client_claims():
    body = _function_body(INDEX, "function _cinematicReplay()")
    assert "zone?.cleared === true" in body
    assert "_adventureBossReady(zone)" in body
    assert "_adventureCanEnter(zone)" in body
    # No client-declared replay/unlock hint may participate.
    for token in ("options.replay", "post_clear_allowed", "data.replay"):
        assert token not in body, f"unlock authority reads client-supplied {token}"


def test_post_clear_and_later_require_an_authoritative_clear():
    body = _function_body(MODEL, "function defaultUnlock(phase, zone)")
    tail = body[body.index("// POST_CLEAR") :]
    assert "return isCleared(zone);" in tail
    assert "hasSeen" not in tail, "a seen marker must not unlock POST_CLEAR or later"


def test_cleared_zone_keeps_earlier_segments_unlocked():
    body = _function_body(MODEL, "function defaultUnlock(phase, zone)")
    boss_ready = body[body.index("if (phase === 'boss_ready')") :]
    assert "isCleared(zone)" in boss_ready.split("}")[0]


# --------------------------------------------------------------------------
# Asset and scope governance
# --------------------------------------------------------------------------


def test_replay_module_is_loaded_by_the_page():
    assert re.search(r'<script src="/js/game/cinematic_replay\.js\?v=[^"]+"></script>', INDEX)


def test_replay_model_has_no_network_storage_or_dom_authority():
    for token in ("fetch(", "localStorage", "XMLHttpRequest", "document.", "navigator."):
        assert token not in MODEL, f"generic replay model reaches for {token}"
