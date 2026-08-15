"""Real-path Lord review contracts and frozen b3cb baseline probes."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
E2E_DIR = REPO_ROOT / "tests" / "e2e"
NATURAL_TRACE = E2E_DIR / "run_e10_lord_autonext_natural_trace.mjs"
ARCHITECTURE_RUNNER = E2E_DIR / "run_e10_lord_review_architecture_contract.mjs"


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
    # A checkout-local npm install is preferred.  NODE_PATH is only a
    # dependency-resolution fallback for this disposable test process.
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


def _run_json(script: Path, *args: str) -> dict:
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)
    env = _node_environment()
    if _chrome_path():
        env["CHROME_BIN"] = _chrome_path()  # type: ignore[assignment]
    result = subprocess.run(
        ["node", str(script), *args],
        cwd=E2E_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=420,
    )
    if result.returncode == 2:
        pytest.skip(f"real-path harness unavailable: {result.stdout[-1000:]}")
    if result.returncode != 0:
        raise AssertionError(
            f"real-path runner failed with exit {result.returncode}\n"
            f"stdout:\n{result.stdout[-4000:]}\n"
            f"stderr:\n{result.stderr[-4000:]}"
        )
    decoder = json.JSONDecoder()
    for index in range(len(result.stdout) - 1, -1, -1):
        if result.stdout[index] != "{":
            continue
        try:
            value, end = decoder.raw_decode(result.stdout[index:])
        except json.JSONDecodeError:
            continue
        if not result.stdout[index + end :].strip():
            return value
    raise AssertionError(f"runner did not emit a final JSON report: {result.stdout[-4000:]}")


@pytest.fixture(scope="module")
def b3cb_baseline_reports():
    return {
        "single_ply": _run_json(NATURAL_TRACE, "--fixture", "single_ply"),
        "multi_ply": _run_json(NATURAL_TRACE, "--fixture", "multi_ply"),
        "badge": _run_json(NATURAL_TRACE, "--fixture", "single_ply", "--badge-priming"),
        "rank_up": _run_json(NATURAL_TRACE, "--fixture", "single_ply", "--rank-priming"),
    }


def _assert_real_foundation(report: dict) -> None:
    verdict = report.get("verdict", {})
    evidence = report.get("evidence", {})
    assert verdict.get("REAL_WGO_CLICK_EXECUTED") is True
    assert verdict.get("SIGNED_BOSS_ATTEMPT_USED") is True
    assert verdict.get("SRS_REVIEW_HTTP_STATUS") == 200
    assert verdict.get("PRODUCTION_SHAPED_RESPONSE") is True
    assert verdict.get("SERVER_REVIEW_COMMITTED") is True
    assert evidence.get("secret_file_access_attempts") == []
    assert evidence.get("katago_cache_access_attempts") == []


@pytest.mark.parametrize(
    ("variant", "expected_depth"),
    [("single_ply", 1), ("multi_ply", 2)],
)
def test_b3cb_real_path_baseline_click_variants(b3cb_baseline_reports, variant, expected_depth):
    report = b3cb_baseline_reports[variant]
    _assert_real_foundation(report)
    assert report["verdict"]["ANSWER_TREE_DEPTH"] >= expected_depth


def test_b3cb_real_path_baseline_badge_variant(b3cb_baseline_reports):
    report = b3cb_baseline_reports["badge"]
    _assert_real_foundation(report)
    assert report["verdict"]["NEW_BADGES_RETURNED"] >= 1


def test_b3cb_real_path_baseline_rank_up_variant(b3cb_baseline_reports):
    report = b3cb_baseline_reports["rank_up"]
    _assert_real_foundation(report)
    assert report["verdict"]["RANK_UP_RETURNED"] is True


def test_release_gate_has_no_ok_true_review_shortcut():
    sources = [
        NATURAL_TRACE.read_text(encoding="utf-8"),
        ARCHITECTURE_RUNNER.read_text(encoding="utf-8"),
    ]
    for source in sources:
        assert not re.search(r"page\.route\s*\(", source)
        assert "/api/srs/review" in source
        assert "response.json()" in source
        assert "PRODUCTION_SHAPED_RESPONSE" in source or "response_key_count" in source


@pytest.mark.expected_red_on_b3cb
def test_q1_q2_q3_real_path_has_one_review_and_one_progress_per_answer():
    report = _run_json(ARCHITECTURE_RUNNER)
    verdict = report["verdict"]
    queue = report["evidence"]["queue_qids"]
    assert verdict["REAL_FLASK"] is True
    assert verdict["REAL_ROUTE"] is True
    assert verdict["REAL_SIGNED_ATTEMPT"] is True
    assert verdict["REAL_WGO_CLICK"] is True
    assert verdict["PRODUCTION_SHAPED_RESPONSE"] is True
    assert verdict["SRS_REVIEW_REQUEST_COUNT"] == 2
    assert verdict["SERVER_ANSWERED_COUNT"] == 2
    assert verdict["CLIENT_BOSS_INDEX"] == 2
    assert verdict["CURRENT_QID"] == queue[2]
    assert str(verdict["VISIBLE_BOARD_QID"]) == str(queue[2])
    assert verdict["DUPLICATE_REVIEW"] is False
    assert verdict["DUPLICATE_PROGRESS"] is False


@pytest.mark.expected_red_on_b3cb
@pytest.mark.parametrize(
    ("fault", "extra"),
    [
        ("BADGE_PRESENTATION_THROW", ("--badge-priming",)),
        ("PET_PRESENTATION_THROW", ()),
        ("MONSTER_PRESENTATION_THROW", ()),
        ("QUEST_PRESENTATION_THROW", ()),
        ("XP_PRESENTATION_THROW", ()),
        ("LOOT_PRESENTATION_THROW", ()),
        ("AUDIO_PRESENTATION_REJECT", ()),
    ],
)
def test_presentation_failure_matrix_keeps_committed_lord_progress(fault, extra):
    report = _run_json(
        ARCHITECTURE_RUNNER,
        "--presentation-failure",
        fault,
        *extra,
    )
    verdict = report["verdict"]
    assert verdict["REAL_FLASK"] is True
    assert verdict["REAL_ROUTE"] is True
    assert verdict["REAL_SIGNED_ATTEMPT"] is True
    assert verdict["REAL_WGO_CLICK"] is True
    assert verdict["PRODUCTION_SHAPED_RESPONSE"] is True
    assert verdict["SRS_REVIEW_REQUEST_COUNT"] == 1
    assert verdict["SERVER_ANSWERED_COUNT"] == 1
    assert verdict["CLIENT_BOSS_INDEX"] == 1
    assert verdict["CURRENT_QID"] is not None
    assert verdict["VISIBLE_BOARD_QID"] is not None
    assert verdict["DUPLICATE_REVIEW"] is False
    assert verdict["DUPLICATE_PROGRESS"] is False
    assert verdict["PRESENTATION_FAILURE_OBSERVED"] is True


@pytest.mark.expected_red_on_b3cb
def test_legitimate_server_rejection_does_not_advance_lord_state():
    report = _run_json(ARCHITECTURE_RUNNER)
    verdict = report["verdict"]
    rejected = report["phases"]["rejected_review"]
    assert rejected["status"] >= 400
    assert verdict["SERVER_REJECTION_COMMITTED"] is False
    assert verdict["CLIENT_ADVANCED_AFTER_REJECTION"] is False
