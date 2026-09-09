"""Fail-closed regression tests for the BUILD_APP failure baseline."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import xml.etree.ElementTree as ET

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
EVALUATOR_PATH = REPO_ROOT / "scripts" / "release" / "evaluate_build_app_test_baseline.py"
BASELINE_PATH = REPO_ROOT / "deploy" / "build-app-known-failure-baseline.json"
BUILD_SCRIPT_PATH = REPO_ROOT / "scripts" / "release" / "build-release-image.ps1"
BASE_SHA = "0861d72cc6e5621179c01f931bcec3af510226b5"
BASE_TREE = "149ae7e5e5befc9ea6e89306e14c5b44577b5d06"


def _load_evaluator():
    spec = importlib.util.spec_from_file_location("build_app_baseline", EVALUATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


EVALUATOR = _load_evaluator()


KNOWN_FAILURES = [
    (
        "tests/deployment/test_e9_runtime_asset_packaging.py",
        "test_e9_css_inventory_exactly_matches_source_directory",
        "AssertionError",
        "E9 CSS inventory mismatch",
        "source directory contains three files absent from E9_CSS_FILES",
    ),
    (
        "tests/deployment/test_runtime_dependency_provenance.py",
        "test_working_tree_matches_recorded_content_sha256",
        "AssertionError",
        "index.html content drifted from recorded provenance",
        "recorded content_sha256 differs from the working tree",
    ),
    (
        "tests/deployment/test_runtime_dependency_provenance.py",
        "test_working_tree_matches_recorded_source_commit_blob",
        "AssertionError",
        "index.html does not raw-byte-match its recorded source commit",
        "working tree bytes differ from the recorded source blob",
    ),
]


def _testcase(parent, module_path, name, *, failure=None, error=False, skipped=False):
    testcase = ET.SubElement(parent, "testcase", classname=module_path.replace("/", ".").removesuffix(".py"), name=name)
    if failure is not None:
        failure_type, message, text = failure
        ET.SubElement(testcase, "failure", type=failure_type, message=message).text = text
    if error:
        ET.SubElement(testcase, "error", type="RunnerError", message="collection failed").text = "collection failed"
    if skipped:
        ET.SubElement(testcase, "skipped")
    return testcase


def _write_junit(path, failures=(), *, extra_failure=None, error=False, skipped=0):
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite", errors="1" if error else "0")
    for module_path, name, failure_type, message, text in failures:
        _testcase(suite, module_path, name, failure=(failure_type, message, text))
    if extra_failure is not None:
        _testcase(suite, "tests/deployment/test_new_failure.py", "test_new_failure", failure=extra_failure)
    if error:
        _testcase(suite, "tests/deployment/test_runner.py", "test_collection", error=True)
    for index in range(skipped):
        _testcase(suite, "tests/deployment/test_skipped.py", f"test_skipped_{index}", skipped=True)
    if not failures and extra_failure is None and not error and not skipped:
        _testcase(suite, "tests/deployment/test_clean.py", "test_clean")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _baseline_for(tmp_path):
    entries = []
    for module_path, name, failure_type, message, text in KNOWN_FAILURES:
        testcase = ET.Element(
            "testcase",
            classname=module_path.replace("/", ".").removesuffix(".py"),
            name=name,
        )
        failure = ET.SubElement(testcase, "failure", type=failure_type, message=message)
        failure.text = text
        nodeid = f"{module_path}::{name}"
        entries.append(
            {
                "nodeid": nodeid,
                "signature": EVALUATOR.failure_signature(nodeid, failure),
                "description": "test fixture",
            }
        )
    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps(
            {
                "schema": EVALUATOR.SCHEMA,
                "baseline_source_sha": BASE_SHA,
                "baseline_source_tree": BASE_TREE,
                "signature_algorithm": "sha256(nodeid,type,normalized_message,normalized_text_v2)",
                "failures": entries,
            }
        ),
        encoding="utf-8",
    )
    return path


def _evaluate(tmp_path, failures=(), *, extra_failure=None, error=False, skipped=0, exit_code=1):
    junit = tmp_path / "results.xml"
    _write_junit(junit, failures, extra_failure=extra_failure, error=error, skipped=skipped)
    return EVALUATOR.evaluate(
        junit_path=junit,
        baseline_path=_baseline_for(tmp_path),
        repo_root=REPO_ROOT,
        gate_source_sha=BASE_SHA,
        pytest_exit_code=exit_code,
    )


def test_tracked_baseline_is_identity_bound_and_contains_exact_three_entries():
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert baseline["schema"] == EVALUATOR.SCHEMA
    assert baseline["baseline_source_sha"] == BASE_SHA
    assert baseline["baseline_source_tree"] == BASE_TREE
    assert len(baseline["failures"]) == 3
    assert len({entry["nodeid"] for entry in baseline["failures"]}) == 3
    assert all(len(entry["signature"]) == 64 for entry in baseline["failures"])


def test_exact_three_known_failures_are_visible_but_non_blocking(tmp_path):
    report = _evaluate(tmp_path, KNOWN_FAILURES)
    assert report["result"] == "PASS"
    assert report["passed_test_count"] == 0
    assert report["skipped_test_count"] == 0
    assert report["failed_test_count"] == 3
    assert report["known_pre_existing_failure_count"] == 3
    assert report["candidate_introduced_failure_count"] == 0


def test_known_failures_plus_one_new_failure_blocks(tmp_path):
    report = _evaluate(
        tmp_path,
        KNOWN_FAILURES,
        extra_failure=("AssertionError", "new failure", "candidate introduced"),
    )
    assert report["result"] == "BLOCK"
    assert report["reason"] == "unrecognized_or_changed_failure"
    assert report["known_pre_existing_failure_count"] == 3
    assert report["candidate_introduced_failure_count"] == 1


def test_known_node_with_changed_signature_blocks(tmp_path):
    changed = list(KNOWN_FAILURES)
    changed[1] = (
        changed[1][0],
        changed[1][1],
        changed[1][2],
        "index.html missing from the release payload",
        changed[1][4],
    )
    report = _evaluate(tmp_path, changed)
    assert report["result"] == "BLOCK"
    assert report["reason"] == "unrecognized_or_changed_failure"
    assert report["candidate_introduced_failure_count"] == 1


def test_collection_or_runner_error_blocks(tmp_path):
    report = _evaluate(tmp_path, error=True, exit_code=2)
    assert report["result"] == "BLOCK"
    assert report["reason"] == "collection_or_test_runner_error"


def test_zero_failures_pass(tmp_path):
    report = _evaluate(tmp_path, failures=(), exit_code=0)
    assert report["result"] == "PASS"
    assert report["failed_test_count"] == 0
    assert report["known_pre_existing_failure_count"] == 0


def test_known_failures_may_be_fixed_without_recreating_them(tmp_path):
    report = _evaluate(tmp_path, failures=(), skipped=1, exit_code=0)
    assert report["result"] == "PASS"
    assert report["skipped_test_count"] == 1
    assert report["known_pre_existing_failure_count"] == 0


def test_unordered_pytest_set_diff_does_not_change_signature():
    first = ET.Element(
        "failure",
        type="AssertionError",
        message="assert {'a', 'b'} == {'b', 'a'}\nExtra items in the right set:\n'x'\n'y'",
    )
    first.text = "assert {'a', 'b'} == {'b', 'a'}\nExtra items in the right set:\n'x'\n'y'"
    second = ET.Element(
        "failure",
        type="AssertionError",
        message="assert {'b', 'a'} == {'a', 'b'}\nExtra items in the right set:\n'y'\n'x'",
    )
    second.text = "assert {'b', 'a'} == {'a', 'b'}\nExtra items in the right set:\n'y'\n'x'"
    assert EVALUATOR.failure_signature("tests/deployment/test_sets.py::test_sets", first) == EVALUATOR.failure_signature(
        "tests/deployment/test_sets.py::test_sets", second
    )


def test_build_script_invokes_identity_bound_evaluator_and_junit_report():
    content = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "build-app-known-failure-baseline.json" in content
    assert "evaluate_build_app_test_baseline.py" in content
    assert "--junitxml" in content
    assert "--pytest-exit-code" in content
    assert "BUILD_APP deployment test gate failed closed" in content
    assert "pytest failed with exit code $LASTEXITCODE" not in content
