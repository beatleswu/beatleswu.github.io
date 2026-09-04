"""Static contracts for the bounded W1-03 Zone 3 blocker-repair gate.

The browser runner owns the exact 16-case focused gate and an explicitly
opt-in 24-case regression of the previously passing domains.  These tests
guard that the runner remains bounded and that the product seam still carries
the originating media gesture through the existing Journey path.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
WORLD_STAGE = ROOT / "js" / "e9" / "world_stage.js"
RUNNER = ROOT / "tests" / "e2e" / "run_w1_03_journey_zone3_final_qa_blocker_repair_012.mjs"


def test_runner_keeps_the_default_gate_bounded_and_complete() -> None:
    runner = RUNNER.read_text(encoding="utf-8")

    default_start = runner.index("const CASES = Object.freeze")
    default_end = runner.index("const PREVIOUSLY_PASSING_CASES", default_start)
    default_block = runner[default_start:default_end]
    default_cases = re.findall(
        r"id: '([^']+)', account: '(?:REPLAY|EN)', locale: '(?:zh-TW|en-US)'",
        default_block,
    )
    assert default_cases == [
        "replay",
        "route_exit_cleanup",
        "presentation_failure_noop",
        "final_state_return",
    ]
    assert "const availableCases = INCLUDE_PREVIOUSLY_PASSING" in runner
    assert "const expectedCount = selectedCases.length * selectedViewports.length;" in runner
    assert "E2E_INCLUDE_PREVIOUS_PASSING === '1'" in runner
    assert "E2E_CASE_FILTER" in runner
    assert "E2E_VIEWPORT_FILTER" in runner

    for viewport, width, height in (
        ("desktop", 1920, 1080),
        ("ipad_landscape", 1180, 820),
        ("ipad_portrait", 820, 1180),
        ("mobile_portrait", 390, 844),
    ):
        assert f"{viewport}: Object.freeze({{ width: {width}, height: {height} }})" in runner

    assert "serviceWorkers: 'block'" in runner
    assert "Network.setCacheDisabled" in runner
    assert "zone3PresentationFailsafe === 'reached'" in runner
    assert "const ZONE3_IMAGE_PATTERN = /\\/assets\\/e10\\/art\\/zone3\\/cinematic\\/zone3_shot\\d+\\.webp$/i;" in runner
    assert "page.waitForTimeout" not in runner
    assert "test.skip" not in runner
    assert "xfail" not in runner.lower()


def test_optional_regression_contains_exactly_the_six_previous_passing_domains() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    optional_start = runner.index("const PREVIOUSLY_PASSING_CASES")
    optional_end = runner.index("const INCLUDE_PREVIOUSLY_PASSING", optional_start)
    optional = runner[optional_start:optional_end]
    assert re.findall(r"id: '([^']+)'", optional) == [
        "first_entry_zh_TW",
        "first_entry_en_US",
        "locale_switch",
        "reduced_motion",
        "global_mute",
        "cinematic_lifecycle",
    ]
    assert "[...CASES, ...PREVIOUSLY_PASSING_CASES]" in runner
    assert "[...new Set(selectedCases.map((spec) => spec.account))]" in runner


def test_replay_repair_passes_the_originating_unlock_promise_through_shared_path() -> None:
    world_stage = WORLD_STAGE.read_text(encoding="utf-8")
    index = INDEX.read_text(encoding="utf-8")

    assert "audioUnlockPromise = window._unlockIntroAudioFromGesture();" in world_stage
    assert "api.playStoryReplay(zoneKey, {" in world_stage
    assert "audioUnlockPromise: audioUnlockPromise" in world_stage
    assert "let begun = false;" in index
    assert "const pendingUnlock = opts.audioUnlockPromise;" in index
    assert "void Promise.resolve(pendingUnlock).then(continueAfterPendingUnlock, continueAfterPendingUnlock);" in index
    assert "if (begun) return;" in index


def test_route_cleanup_invalidates_zone3_presentation_only_state() -> None:
    index = INDEX.read_text(encoding="utf-8")
    cleanup_start = index.index("function _registerZone3PresentationLifecycleCleanup()")
    cleanup_end = index.index("\n}\n", cleanup_start) + 3
    cleanup = index[cleanup_start:cleanup_end]
    assert "_stopIntroFilm();" in cleanup
    assert "_zoneCinematicPresentationOnly = false;" in cleanup
    assert "_zoneCinematicAdvanceSegment = null;" in cleanup
    assert "_zoneCinematicSequenceRunId += 1;" in cleanup
