"""W1_03 first-session journey onboarding spine contracts."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = "d6afb957a12891e69f4709b3909cf41f13cfbcd9"
CONTENT = ROOT / "js" / "e9" / "journey_onboarding_content.js"
SPINE = ROOT / "js" / "e9" / "journey_onboarding_spine.js"
VIEW = ROOT / "js" / "e9" / "journey_onboarding_view.js"
FRAGMENT = ROOT / "components" / "adventure" / "journey_onboarding.html"
CSS = ROOT / "css" / "e9" / "journey_onboarding.css"
PLAN = ROOT / "docs" / "planning" / "w1_03_journey_onboarding_spine_001.md"
RUNNER = ROOT / "tests" / "e2e" / "run_w1_03_journey_onboarding_spine.mjs"


def read(path: Path) -> str:
    assert path.is_file(), f"missing required W1_03 file: {path}"
    return path.read_text(encoding="utf-8")


def test_required_lanefiles_exist():
    for path in (CONTENT, SPINE, VIEW, FRAGMENT, CSS, PLAN, RUNNER):
        assert path.is_file()


def test_step_order_covers_the_requested_spine():
    content = read(CONTENT)
    expected = [
        "opening",
        "world_reveal",
        "hero_companion",
        "first_adventure",
        "first_question",
        "answer_feedback",
        "attack_hit",
        "first_victory",
        "reward_reveal",
        "growth_feedback",
        "next_action",
        "zone_progression",
        "zone3_arrival",
    ]
    positions = [content.index(f"'{step}'") for step in expected]
    assert positions == sorted(positions)


def test_authority_boundaries_are_explicit():
    content = read(CONTENT)
    spine = read(SPINE)
    for marker in (
        "existing_onboarding_session",
        "existing_shell_state",
        "canonical_adventure_entry",
        "canonical_question_runtime",
        "committed_review_result",
        "canonical_battle_result",
        "committed_server_reward_projection",
        "committed_server_growth_projection",
        "server_primary_action",
        "adventure_bootstrap_state",
    ):
        assert marker in content
    for marker in (
        "authoritySource === 'existing_onboarding'",
        "source === 'canonical_adventure'",
        "source === 'canonical_question_runtime'",
        "source === 'canonical_srs_review'",
        "source === 'map_battle_v1'",
        "source === 'battlefield_reward_consumer'",
        "source === 'committed_review_presentation'",
        "source === 'adventure_bootstrap'",
    ):
        assert marker in spine


def test_controller_has_no_network_storage_or_authority_writes():
    spine = read(SPINE)
    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "localStorage",
        "sessionStorage",
        "document.",
        "reward.create",
        "equipItem",
        "/api/",
    ):
        assert forbidden not in spine


def test_reward_and_replay_guards_are_present():
    spine = read(SPINE)
    assert "duplicate_reward_event" in spine
    assert "rewardEventIds" in spine
    assert "replay !== true" in spine
    assert "skipHint" in spine and "advancesJourney: false" in spine
    assert "replayHint" in spine and "presentationOnly" in spine


def test_zone_three_is_a_style_lock_boundary_without_authored_details():
    content = read(CONTENT)
    spine = read(SPINE)
    plan = read(PLAN)
    assert "deferred_until_world_style_lock" in content
    assert "visualDetails: null" in content
    assert "authoredCopy: null" in content
    assert "BLOCKED_BY_STYLE_LOCK" in spine
    assert "No Zone 3–10 art/style/story invention" in plan


def test_fragment_is_a_short_contextual_noncritical_surface():
    fragment = read(FRAGMENT)
    assert 'id="journey-onboarding"' in fragment
    assert 'data-e9-component="journey_onboarding"' in fragment
    assert 'data-journey-action="skip"' in fragment
    assert 'data-journey-action="replay"' in fragment
    assert 'hidden aria-hidden="true"' in fragment
    assert "fetch" not in fragment.lower()


def test_responsive_reduced_motion_styles_exist():
    css = read(CSS)
    assert "@media (max-width: 767px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "position: fixed" not in css


def test_view_is_root_scoped_and_presentation_only():
    view = read(VIEW)
    assert "journey:onboarding-event" in view
    assert "data-e9-journey-mounted" in view
    assert "global.E9.on" in view
    assert "global.E9.registerCleanup" in view
    assert "controller.skipHint()" in view
    assert "controller.replayHint()" in view
    assert "fetch(" not in view
    assert "localStorage" not in view
    assert "sessionStorage" not in view


def test_protected_backend_and_cinematic_boundaries_untouched():
    # This follow-on task owns the authorized index/i18n shell-writer slot.
    # Keep the gameplay backend and generic cinematic replay contract locked.
    for relative in ("js/game/cinematic_replay.js", "app.py"):
        result = subprocess.run(
            ["git", "diff", "--quiet", BASE, "--", relative],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"protected scope changed: {relative}\n{result.stderr}"


def test_behavioral_runner_is_green():
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
    assert '"status":"PASS"' in result.stdout, output
    assert '"failures":0' in result.stdout, output
