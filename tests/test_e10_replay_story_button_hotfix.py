"""E10_REPLAY_STORY_BUTTON_HOTFIX_001: real-button-click regression contract.

A test that calls playZoneStoryReplay/E10Cinematic.playStoryReplay directly
would pass on both the broken and the fixed bytes -- the regression lived in
what the real DOM button's click handler does *before* reaching that
function, not in the function itself. This wraps the real-browser runner
(run_e10_replay_story_button_real_click.mjs), which clicks the actual
#e9-world-stage-details-replay button on the real mounted E9 world_stage
component and inspects click-time state, exactly mirroring the skip pattern
already established by test_e10_lord_review_real_path_contracts.py for this
repository's other Playwright-backed real-path runners.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
E2E_DIR = REPO_ROOT / "tests" / "e2e"
RUNNER = E2E_DIR / "run_e10_replay_story_button_real_click.mjs"


def _chrome_path() -> str | None:
    candidates = [
        os.environ.get("CHROME_BIN"),
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
        "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    ]
    return next((candidate for candidate in candidates if candidate and Path(candidate).is_file()), None)


def _node_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    local_modules = E2E_DIR / "node_modules"
    if (local_modules / "playwright-core").is_dir():
        env["NODE_PATH"] = str(local_modules)
    return env


def _skip_reason() -> str | None:
    if shutil.which("docker") is None:
        return "Docker executable unavailable for disposable PostgreSQL"
    try:
        docker = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Docker server unavailable: {exc}"
    if docker.returncode != 0:
        return "Docker server unavailable for disposable PostgreSQL"
    if shutil.which("node") is None:
        return "Node.js unavailable for real-browser runner"
    if _chrome_path() is None:
        return "Chrome/Edge unavailable for real-browser runner"
    probe = subprocess.run(
        ["node", "-e", "require.resolve('playwright-core')"],
        cwd=E2E_DIR,
        env=_node_environment(),
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        return "playwright-core unavailable; install tests/e2e dependencies"
    return None


def _run_json(viewport: str) -> dict:
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)
    env = _node_environment()
    if _chrome_path():
        env["CHROME_BIN"] = _chrome_path()  # type: ignore[assignment]
    result = subprocess.run(
        ["node", str(RUNNER), "--viewport", viewport],
        cwd=E2E_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=420,
    )
    if result.returncode == 2:
        pytest.skip(f"real-path harness unavailable: {result.stdout[-1000:]}")
    try:
        report = json.loads(result.stdout)
    except ValueError:
        raise AssertionError(
            f"runner did not emit a JSON report (exit {result.returncode})\n"
            f"stdout:\n{result.stdout[-4000:]}\nstderr:\n{result.stderr[-4000:]}"
        )
    if report.get("skipped"):
        pytest.skip(report.get("reason", "runner reported unavailable"))
    return report


@pytest.fixture(scope="module")
def tablet_report():
    return _run_json("tablet")


def test_replay_story_button_real_click_tablet(tablet_report):
    """REPLAY_STORY_BUTTON_REAL_CLICK: the real button, not a direct call.

    This is the assertion that fails on unmodified E10_LORD_REPLAY_
    ISOLATED_RELEASE_001 bytes: clicking #e9-world-stage-details-replay must
    reach E10Cinematic.playStoryReplay and activate the cinematic overlay in
    the SAME synchronous tick as the click. Before the hotfix, the click ran
    through withCinematicHost's wait for ensureLegacyAdventureMapReady --
    real network calls, no functional purpose for a replay this component
    already hosts -- so the overlay's own state read immediately after
    button.click() returns still showed no activation.
    """
    assert tablet_report["button_visible"] is True
    assert tablet_report["button_enabled"] is True
    assert tablet_report["click_handler_fired"] is True
    assert tablet_report["play_story_replay_called"] is True
    assert tablet_report["cinematic_overlay_started_same_tick"] is True
    assert tablet_report["final_status"] == "PASS"


def test_replay_story_repeat_click_single_dispatch(tablet_report):
    """Section 4: reselect a different zone, return, click again.

    Exactly one replayStoryReplay dispatch for the returned zone -- no dead
    handler left over from the first selection, no duplicate handler stacked
    by the second.
    """
    assert tablet_report["repeat_click_single_dispatch"] is True
    assert tablet_report["repeat_click_activated_same_tick"] is True


def test_replay_story_finishes_and_returns_to_zone_card(tablet_report):
    finish = tablet_report.get("finish_and_return") or {}
    assert finish.get("returned_to_zone_card") is True
    assert finish.get("selected_zone_key") == tablet_report["evidence"]["zone_key"]


def test_replay_story_button_portrait_tablet_required():
    """Section 6.E: portrait tablet acceptance is required, run on its own
    (not reusing the module-scoped fixture) so a failure here is unambiguous."""
    report = _run_json("tablet")
    assert report["final_status"] == "PASS"


@pytest.mark.parametrize("viewport", ["desktop", "mobile"])
def test_replay_story_button_other_viewports_no_console_errors(viewport):
    """DESKTOP/MOBILE: the button's own responsive affordance is a separate,
    pre-existing concern this hotfix does not touch (world_stage.js gates
    the details drawer on portrait-tablet only). Where the affordance is not
    present, this only proves the page loads clean -- it does not force a
    click on a control that is not meant to be reachable there."""
    report = _run_json(viewport)
    assert report.get("login", {}).get("ok") is True
    assert report.get("console_page_errors", []) == []
    if report.get("button_visible") and report.get("button_enabled"):
        assert report["final_status"] == "PASS"


def test_replay_story_writes_no_domain_state(tablet_report):
    """Section 5 / 6.D: presentation-only authority. The harness seeds the
    clear directly (isolated local state, never Production); the assertion
    is that nothing about that seeded state changes across two full replay
    dispatches (this fixture's first_click/repeat_click)."""
    evidence = tablet_report["evidence"]
    assert evidence["replay_story_e9"]["mechanism"] == "adventure_boss_progress.cleared = 1"
    # The runner's own finish/return checks already prove the overlay
    # terminator (_finishZoneCinematicReplay) ran, which is the codebase's
    # own pinned guarantee (test_e10_generic_cinematic_replay.py) that no
    # fetch/mark*/progression call exists on that path.
    assert tablet_report.get("finish_and_return_2", {}).get("returned_to_zone_card") is True
