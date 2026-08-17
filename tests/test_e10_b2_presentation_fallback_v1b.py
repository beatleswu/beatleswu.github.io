"""Architecture V1 Wave 5 failsafe-execution closure.

Wires tests/e2e/run_e10_b2_presentation_effects_characterization.mjs into the
enforced suite (it previously ran nowhere) and requires the two scenarios
this task added to it:

  Test 1 -- Review Presentation Fallback (_dispatchCommittedReviewPresentation
  falls through to its manual/legacy branch when window.PresentationDispatcher
  or window.GoOdysseyPresentationEffectsB2 is unavailable).

  Test 2 -- Rank-up Ritual -> Legacy Popup Fallback (showRankUpPopup falls
  through to showRankUpLegacyPopup when the canonical reduced-motion guard,
  _rankupIsReducedMotion(), reads true).

Both are exercised by real vm.runInContext execution of the extracted
canonical source, not source-text inspection.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "e2e" / "run_e10_b2_presentation_effects_characterization.mjs"


def _run_runner() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(RUNNER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_b2_presentation_effects_characterization_runner_is_green():
    result = _run_runner()
    output = f"stdout={result.stdout}\nstderr={result.stderr}"
    assert result.returncode == 0, output
    assert "E10_B2_PRESENTATION_EFFECTS_CHARACTERIZATION: PASS" in result.stdout, output


def test_review_presentation_fallback_and_rankup_fallback_are_real_executed():
    """Gate 4 executable-fault-injection proof for the two previously
    INTENTIONAL_FAILSAFE-but-unproven fallbacks from Wave 5 final closure."""
    result = _run_runner()
    output = f"stdout={result.stdout}\nstderr={result.stderr}"
    assert result.returncode == 0, output
    assert (
        "E10_ARCHITECTURE_V1_WAVE5_FAILSAFE_EXECUTION_CLOSURE_046: PASS" in result.stdout
    ), output


def test_runner_source_asserts_the_required_fallback_deltas():
    """Characterizes the runner's own assertions so a future edit cannot
    silently drop the required-proof coverage without this test noticing --
    scoped to the two new scenarios this task added, not the whole file."""
    source = RUNNER.read_text(encoding="utf-8")

    review_start = source.index("async function characterizeDispatcherEffects")
    review_end = source.index(
        "async function characterizeRankUpReducedMotionFallback", review_start
    )
    review_scenario = source[review_start:review_end]
    assert "context.window.PresentationDispatcher, undefined" in review_scenario
    assert "context.window.GoOdysseyPresentationEffectsB2, undefined" in review_scenario
    assert "REVIEW_HTTP_DELTA=0" in review_scenario
    assert "REVIEW_RETRY_DELTA=0" in review_scenario
    assert "PROGRESSION_DELTA=0" in review_scenario
    assert "LORD_ADVANCEMENT_DELTA=0" in review_scenario
    assert "MAPBATTLE_SETTLEMENT_DELTA=0" in review_scenario
    assert "STALE_SESSION_MUTATION=NO" in review_scenario
    assert "FALLBACK_EXECUTED=YES" in review_scenario

    rankup_start = review_end
    rankup_end = source.index("async function characterizeHpSpAndMapBattleSharedHelpers", rankup_start)
    rankup_scenario = source[rankup_start:rankup_end]
    assert "isReducedMotion(), true" in rankup_scenario
    assert "FALLBACK_EXECUTED=YES" in rankup_scenario
    assert "RANKUP_DUPLICATE_PRESENTATION=NO" in rankup_scenario
    assert "RANKUP_DUPLICATE_REWARD=NO" in rankup_scenario
    assert "RANKUP_DUPLICATE_PROGRESSION=NO" in rankup_scenario
    assert "RANKUP_REVIEW_HTTP_DELTA=0" in rankup_scenario
    assert "RANKUP_STALE_MUTATION=NO" in rankup_scenario
    assert "pytest.mark.skip" not in rankup_scenario
    assert "pytest.mark.xfail" not in rankup_scenario
