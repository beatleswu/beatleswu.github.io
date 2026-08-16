"""Independent B1B contracts for the future PresentationDispatcher.

This file intentionally runs against the pre-implementation canonical base.
The expected red is limited to missing future asset/delegation/packaging
requirements.  It never imports app.py or contacts a backend.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = "e892932a046d4c1b88262b4e8adbc5f7824be8c2"
PRESENTATION_PATH = ROOT / "js" / "game" / "presentation_dispatcher.js"
NODE_CONTRACT = ROOT / "tests" / "e2e" / "run_e10_presentation_dispatcher_contract.mjs"
SRS_PATH = ROOT / "srs.js"
INDEX_PATH = ROOT / "index.html"
LORD_CONTROLLER_PATH = ROOT / "js" / "game" / "lord_trial_controller.js"
APP_PATH = ROOT / "app.py"
DOCKERFILE_PATH = ROOT / "Dockerfile"
BUILD_MANIFEST_PATH = ROOT / "deploy" / "build-manifest.json"
STATIC_INVENTORY_PATH = ROOT / "deploy" / "live-static-asset-inventory.json"
SW_PATH = ROOT / "sw.js"
DISPATCHER_ASSET = "js/game/presentation_dispatcher.js"
SYNTHETIC_SECRET = "e10-v1b-b1b-contract-test-secret"

FROZEN_INDEX_FUNCTIONS = (
    "_dispatchCommittedReviewPresentation",
    "submitSRS",
    "_handleBossAnswer",
    "_loadBossQuestion",
    "_finishBossBattle",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _git_show(path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{BASE_SHA}:{path}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, f"HARNESS_FAILURE: git show failed for {path}"
    return result.stdout


def _extract_function(source: str, name: str) -> str:
    match = re.search(
        rf"(?:async\s+)?function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{",
        source,
    )
    assert match, f"HARNESS_FAILURE: function {name} not found"
    opening = source.find("{", match.start(), match.end())
    depth = 0
    quote = None
    escaped = False
    line_comment = False
    block_comment = False
    index = opening
    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            if char in "\r\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                index += 2
            else:
                index += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char == "/" and next_char == "/":
            line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            block_comment = True
            index += 2
            continue
        if char in "'\"`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[match.start() : index + 1]
        index += 1
    raise AssertionError(f"HARNESS_FAILURE: unterminated function {name}")


def _stable_js(source: str) -> str:
    return re.sub(r"\s+", " ", source).strip()


def _mask_external_script_tags(source: str) -> str:
    pattern = re.compile(
        r"<script\b(?=[^>]*\bsrc\s*=)[^>]*>.*?</script\s*>",
        re.IGNORECASE | re.DOTALL,
    )
    return pattern.sub("<EXTERNAL_SCRIPT_TAG>", source)


def _contains_exact_json_value(value, expected: str) -> bool:
    if isinstance(value, str):
        return value == expected
    if isinstance(value, dict):
        return any(_contains_exact_json_value(item, expected) for item in value.values())
    if isinstance(value, list):
        return any(_contains_exact_json_value(item, expected) for item in value)
    return False


def _sw_identity(source: str) -> tuple[str, str]:
    version = re.search(r"const\s+VERSION\s*=\s*['\"]([^'\"]+)", source)
    asset = re.search(r"const\s+ASSET_IDENTITY\s*=\s*['\"]([^'\"]+)", source)
    assert version and asset, "HARNESS_FAILURE: SW identity constants not found"
    return version.group(1), asset.group(1)


def _run_node_contract() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.fail("HARNESS_FAILURE: node executable is unavailable")
    environment = os.environ.copy()
    environment["SECRET_KEY"] = SYNTHETIC_SECRET
    result = subprocess.run(
        [node, str(NODE_CONTRACT)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode in {0, 2}, (
        "HARNESS_FAILURE: Node contract crashed\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, f"HARNESS_FAILURE: Node contract emitted no JSON: {result.stderr!r}"
    report = json.loads(lines[-1])
    report["process_returncode"] = result.returncode
    return report


def test_node_contract_runner_reports_expected_base_state_or_validates_module():
    report = _run_node_contract()

    assert report["contract"] == "E10_FRONTEND_V1B_PRESENTATION_DISPATCHER_B1B"
    assert set(report["cases"]) == {
        "missing_data",
        "data_not_ok",
        "all_effects_succeed",
        "badge_callback_throws",
        "badge_state_dependency_throws",
        "badge_seen_sync_throws",
        "badge_seen_promise_rejects",
        "monster_callback_throws",
        "quest_callback_throws",
        "on_error_throws",
        "deterministic_result",
        "never_calls_review_transport",
        "never_calls_progression",
    }
    if report["status"] == "missing_asset":
        pytest.fail("EXPECTED_RED:PRESENTATION_DISPATCHER_ASSET_MISSING")
    assert report["status"] == "ready", report
    assert report["process_returncode"] == 0, report
    assert report["failures"] == [], report


def test_srs_review_is_the_only_review_transport_and_private_state_stays_in_srs():
    source = _read(SRS_PATH)
    assert source.count("/api/srs/review") == 1
    assert _read(INDEX_PATH).count("SRS.review(") == 1
    for private_name in (
        "_earned",
        "_badgeDefs",
        "_lsMerge",
        "_onBadge",
        "_onMonster",
        "_onQuest",
    ):
        assert private_name in source

    dispatch_body = _extract_function(source, "dispatchReviewPresentation")
    if "PresentationDispatcher" not in dispatch_body or ".dispatch" not in dispatch_body:
        pytest.fail("EXPECTED_RED:SRS_NOT_YET_DELEGATING_TO_PRESENTATION_DISPATCHER")
    assert "/api/srs/review" not in dispatch_body


def test_presentation_dispatcher_has_no_transport_or_progression_authority():
    if not PRESENTATION_PATH.is_file():
        pytest.fail("EXPECTED_RED:PRESENTATION_DISPATCHER_ASSET_MISSING")
    source = _read(PRESENTATION_PATH)
    forbidden = (
        "/api/srs/review",
        "SRS.review",
        "nextQuestion",
        "_handleBossAnswer",
        "_loadBossQuestion",
        "_finishBossBattle",
        "LordReviewController",
        "GoOdysseyLordTrialController",
        "MapBattleV1",
        "settle",
    )
    for token in forbidden:
        assert token not in source, f"PresentationDispatcher contains forbidden authority: {token}"


def test_index_html_effect_bodies_and_lord_controller_are_frozen():
    current_index = _read(INDEX_PATH)
    base_index = _git_show("index.html")
    for name in FROZEN_INDEX_FUNCTIONS:
        assert _stable_js(_extract_function(current_index, name)) == _stable_js(
            _extract_function(base_index, name)
        ), f"B1 changed frozen index function body: {name}"

    assert _read(LORD_CONTROLLER_PATH) == _git_show("js/game/lord_trial_controller.js")


def test_b1_index_html_changes_are_script_loading_only():
    current_index = _read(INDEX_PATH)
    base_index = _git_show("index.html")
    assert _mask_external_script_tags(current_index) == _mask_external_script_tags(base_index)


def test_b0_exact_route_remains_narrow_and_app_py_is_not_a_generic_static_bridge():
    app_source = _read(APP_PATH)
    assert "@app.route('/js/game/presentation_dispatcher.js')" in app_source
    assert "@app.route('/js/game/<path:" not in app_source
    assert "@app.route('/js/<path:" not in app_source


def test_future_dispatcher_is_explicitly_packaged_and_versioned():
    missing = []
    index_source = _read(INDEX_PATH)
    if not re.search(
        r"<script\b[^>]*\bsrc\s*=\s*['\"][^'\"]*js/game/presentation_dispatcher\.js(?:\?[^'\"]*)?['\"]",
        index_source,
        re.IGNORECASE,
    ):
        missing.append("PRESENTATION_DISPATCHER_NOT_SCRIPT_LOADED")

    dockerfile = _read(DOCKERFILE_PATH)
    if "COPY js/game/presentation_dispatcher.js ./js/game/presentation_dispatcher.js" not in dockerfile:
        missing.append("PRESENTATION_DISPATCHER_NOT_PACKAGED")

    build_manifest = json.loads(_read(BUILD_MANIFEST_PATH))
    if not _contains_exact_json_value(build_manifest, DISPATCHER_ASSET):
        missing.append("PRESENTATION_DISPATCHER_NOT_IN_BUILD_MANIFEST")

    inventory = json.loads(_read(STATIC_INVENTORY_PATH))
    eligible = set(inventory["eligible_files"]["entries"])
    required = set(inventory["required_in_generation"]["entries"])
    if DISPATCHER_ASSET not in eligible:
        missing.append("PRESENTATION_DISPATCHER_NOT_IN_STATIC_INVENTORY")
    if DISPATCHER_ASSET not in required:
        missing.append("PRESENTATION_DISPATCHER_NOT_REQUIRED_IN_GENERATION")

    if _sw_identity(_read(SW_PATH)) == _sw_identity(_git_show("sw.js")):
        missing.append("SW_IDENTITY_NOT_YET_BUMPED_FOR_B1")

    if missing:
        pytest.fail("EXPECTED_RED:" + ",".join(missing))
