from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "components" / "adventure" / "journey_onboarding.html"
VIEW = ROOT / "js" / "e9" / "journey_onboarding_view.js"
CSS = ROOT / "css" / "e9" / "journey_onboarding.css"
RUNNER = ROOT / "tests" / "e2e" / "run_w2_c_f_onboarding_presentation.mjs"


def test_component_has_semantic_guidance_and_controls() -> None:
    source = COMPONENT.read_text(encoding="utf-8")
    assert 'aria-labelledby="journey-onboarding-title"' in source
    assert 'aria-describedby="journey-onboarding-body"' in source
    assert 'data-journey-progress' in source
    assert 'data-journey-status' in source
    assert 'role="status"' in source
    assert 'data-journey-action="skip"' in source
    assert 'data-journey-action="replay"' in source


def test_view_keeps_presentation_only_boundaries() -> None:
    source = VIEW.read_text(encoding="utf-8")
    assert "data-journey-presentation-suppressed" in source
    assert "data-journey-presentation-state" in source
    assert "renderProgress" in source
    assert "controller.skipHint" in source
    assert "controller.replayHint" in source
    assert "fetch(" not in source
    assert "XMLHttpRequest" not in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "document.cookie" not in source


def test_responsive_and_accessible_styles_are_present() -> None:
    source = CSS.read_text(encoding="utf-8")
    assert "min-height: 44px" in source
    assert "overflow-wrap: anywhere" in source
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in source
    assert "prefers-reduced-motion: reduce" in source
    assert "scroll-behavior: auto" in source
    assert "focus-visible" in source


def test_only_authorized_presentation_surfaces_are_changed() -> None:
    diff_result = subprocess.run(
        ["git", "diff", "--name-only", "origin/master...HEAD", "--"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    status_result = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    changed_from_diff = {line.strip().replace("\\", "/") for line in diff_result.stdout.splitlines() if line.strip()}
    assert "secret_key.txt" not in changed_from_diff
    changed = changed_from_diff
    for line in status_result.stdout.splitlines():
        if line.startswith("?? "):
            changed.add(line[3:].replace("\\", "/"))
        elif line[:2].strip():
            changed.add(line[3:].replace("\\", "/"))
    # Preserve the protected local secret if the test environment exposes it
    # in this isolated worktree; it is never part of the candidate diff.
    changed.discard("secret_key.txt")
    assert changed <= {
        "components/adventure/journey_onboarding.html",
        "css/e9/journey_onboarding.css",
        "js/e9/journey_onboarding_view.js",
        "tests/e2e/run_w2_c_f_onboarding_presentation.mjs",
        "tests/test_w2_c_f_onboarding_presentation.py",
        "tests/test_w1_03_journey_onboarding_spine.py",
    }
    assert "app.py" not in changed
    assert "wave2_onboarding_authority.py" not in changed


def test_browserless_presentation_flow() -> None:
    result = subprocess.run(
        ["node", str(RUNNER)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["status"] == "PASS"
    assert payload["failures"] == 0
    assert payload["returningPlayerHidden"] is True
