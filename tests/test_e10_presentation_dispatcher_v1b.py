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
BASE_SHA = "f9554b871eec580746b840e5d9df4278a695b464"
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
AUTHORIZED_DISPATCHER_SCRIPT_SRC = "/js/game/presentation_dispatcher.js?v=20260816e10v1bb1"
BASE_SRS_SCRIPT_SRC = "/srs.js?v=20260622i18n1"
B1_SRS_SCRIPT_SRC = "/srs.js?v=20260816e10v1bb1"
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


_EXTERNAL_SCRIPT_TAG_RE = re.compile(
    r"<script\b(?=[^>]*\bsrc\s*=)[^>]*>.*?</script\s*>",
    re.IGNORECASE | re.DOTALL,
)
_SCRIPT_SRC_ATTRIBUTE_RE = re.compile(
    r"\bsrc\s*=\s*(['\"])(?P<src>.*?)\1",
    re.IGNORECASE | re.DOTALL,
)
_JS_IDENTIFIER = r"[A-Za-z_$][A-Za-z0-9_$]*"
_PRESENTATION_ALIAS_DECLARATION_RE = re.compile(
    rf"\b(?:const|let|var)\s+(?P<alias>{_JS_IDENTIFIER})\s*=\s*(?P<initializer>[^;]+);",
    re.DOTALL,
)


def _external_script_tags(source: str) -> list[tuple[str, str]]:
    entries = []
    for match in _EXTERNAL_SCRIPT_TAG_RE.finditer(source):
        tag = match.group(0)
        src_match = _SCRIPT_SRC_ATTRIBUTE_RE.search(tag)
        assert src_match, "HARNESS_FAILURE: external script tag has no src value"
        entries.append((tag, src_match.group("src")))
    return entries


def _replace_script_src(tag: str, old_src: str, new_src: str) -> str:
    match = _SCRIPT_SRC_ATTRIBUTE_RE.search(tag)
    assert match and match.group("src") == old_src, "HARNESS_FAILURE: unexpected script src"
    return tag[: match.start("src")] + new_src + tag[match.end("src") :]


def _remove_external_script_tag(source: str, tag: str) -> str:
    assert source.count(tag) == 1, "HARNESS_FAILURE: expected one authorized script tag"
    whole_line = re.compile(rf"(?m)^[ \t]*{re.escape(tag)}[ \t]*(?:\r?\n|$)")
    match = whole_line.search(source)
    if match:
        return source[: match.start()] + source[match.end() :]
    return source.replace(tag, "", 1)


def _verified_presentation_dispatcher_aliases(source: str) -> set[str]:
    aliases = set()
    for match in _PRESENTATION_ALIAS_DECLARATION_RE.finditer(source):
        initializer = re.sub(r"\s+", "", match.group("initializer"))
        if initializer in {
            "window.PresentationDispatcher",
            "window.PresentationDispatcher||null",
            "typeofwindow!=='undefined'?window.PresentationDispatcher:null",
            "typeofwindow===\"undefined\"?null:window.PresentationDispatcher",
        }:
            aliases.add(match.group("alias"))
    return aliases


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
    direct_calls = re.findall(
        r"(?:\bwindow\s*\.\s*)?\bPresentationDispatcher\s*\.\s*dispatch\s*\(",
        dispatch_body,
    )
    verified_aliases = _verified_presentation_dispatcher_aliases(source)
    alias_call_count = sum(
        len(
            re.findall(
                rf"\b{re.escape(alias)}\s*\.\s*dispatch\s*\(", dispatch_body
            )
        )
        for alias in verified_aliases
    )
    if len(direct_calls) + alias_call_count != 1:
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
    current_scripts = _external_script_tags(current_index)
    base_scripts = _external_script_tags(base_index)
    current_srcs = [src for _, src in current_scripts]
    base_srcs = [src for _, src in base_scripts]

    assert AUTHORIZED_DISPATCHER_SCRIPT_SRC not in base_srcs
    assert current_srcs.count(AUTHORIZED_DISPATCHER_SCRIPT_SRC) == 1
    assert len(current_srcs) == len(base_srcs) + 1
    assert base_srcs.count(BASE_SRS_SCRIPT_SRC) == 1
    assert current_srcs.count(B1_SRS_SCRIPT_SRC) == 1
    assert current_srcs.count(BASE_SRS_SCRIPT_SRC) == 0

    current_without_dispatcher = [
        src for src in current_srcs if src != AUTHORIZED_DISPATCHER_SCRIPT_SRC
    ]
    normalized_current_srcs = [
        BASE_SRS_SCRIPT_SRC if src == B1_SRS_SCRIPT_SRC else src
        for src in current_without_dispatcher
    ]
    assert normalized_current_srcs == base_srcs

    dispatcher_tag = next(
        tag for tag, src in current_scripts if src == AUTHORIZED_DISPATCHER_SCRIPT_SRC
    )
    current_remainder = _remove_external_script_tag(current_index, dispatcher_tag)
    current_srs_tag = next(tag for tag, src in current_scripts if src == B1_SRS_SCRIPT_SRC)
    base_srs_tag = next(tag for tag, src in base_scripts if src == BASE_SRS_SCRIPT_SRC)
    normalized_srs_tag = _replace_script_src(
        current_srs_tag, B1_SRS_SCRIPT_SRC, BASE_SRS_SCRIPT_SRC
    )
    assert normalized_srs_tag == base_srs_tag
    current_remainder = current_remainder.replace(
        current_srs_tag,
        normalized_srs_tag,
        1,
    )
    assert current_remainder == base_index


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
