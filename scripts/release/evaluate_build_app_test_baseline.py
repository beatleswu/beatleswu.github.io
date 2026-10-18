"""Evaluate the BUILD_APP deployment-suite result against an exact baseline.

The release gate may carry explicitly recorded historical failures, but only
when the JUnit failure identity and signature match this tracked baseline.
Every other failure, runner error, collection error, malformed report, or
unrelated source history is rejected closed.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from types import FunctionType


SCHEMA = "go-odyssey-build-app-known-failure-baseline-v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TREE_RE = re.compile(r"^[0-9a-f]{40}$")
SIGNATURE_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_BASELINE_NODEIDS = frozenset(
    {
        "tests/deployment/test_e9_runtime_asset_packaging.py::test_e9_css_inventory_exactly_matches_source_directory",
        "tests/deployment/test_runtime_dependency_provenance.py::test_working_tree_matches_recorded_content_sha256",
        "tests/deployment/test_runtime_dependency_provenance.py::test_working_tree_matches_recorded_source_commit_blob",
    }
)


class JUnitEvidenceError(ValueError):
    """Raised when JUnit evidence is malformed or ambiguous."""


class BaselineValidationError(ValueError):
    """Raised when the tracked baseline or its source binding is invalid."""


def _normalized(value: str | None) -> str:
    return (value or "").replace("\r\n", "\n").strip()


class _CanonicalSetOrder(ast.NodeTransformer):
    """Canonicalize only Python set member ordering in an assertion AST."""

    def visit_Set(self, node: ast.Set) -> ast.AST:
        node.elts = [self.visit(element) for element in node.elts]
        node.elts.sort(key=lambda element: ast.dump(element, include_attributes=False))
        return node


def _canonicalize_set_assertion(line: str) -> str:
    """Normalize set ordering without erasing assertion semantics."""

    match = re.search(r"\bassert\s+(.+)$", line)
    if not match:
        return line
    expression = match.group(1).strip()
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return line
    if not any(isinstance(node, ast.Set) for node in ast.walk(tree.body)):
        return line
    canonical = _CanonicalSetOrder().visit(tree.body)
    ast.fix_missing_locations(canonical)
    return f"{line[:match.start(1)]}{ast.unparse(canonical)}"


def _stable_failure_text(value: str | None, *, traceback: bool = False) -> str:
    """Normalize pytest's unordered set-diff rendering without hiding content."""

    lines = _normalized(value).splitlines()
    normalized: list[str] = []
    index = 0
    while index < len(lines):
        # Pytest prefixes traceback assertion lines with a variable-width
        # ``E `` marker. Remove that presentation prefix before recognizing
        # and sorting unordered set-diff items.
        line = re.sub(r"^E\s+", "", lines[index])
        if traceback:
            line = re.sub(
                r"(?:WindowsPath|PosixPath)\((['\"])[^'\"]*\1\)",
                "Path('<path>')",
                line,
            )
            line = re.sub(
                r"((?:[A-Za-z]:[\\/]|tests[\\/])[^:\r\n]+\.py):\d+:",
                r"\1:<line>:",
                line,
            )
        line = _canonicalize_set_assertion(line)
        stripped = line.strip()
        if stripped in {
            "Extra items in the right set:",
            "Extra items in the left set:",
        }:
            normalized.append(stripped)
            index += 1
            items: list[str] = []
            while index < len(lines):
                item = re.sub(r"^E\s+", "", lines[index]).strip()
                if not (item.startswith("'") and item.endswith("'")):
                    break
                items.append(item)
                index += 1
            normalized.extend(sorted(items))
            continue
        normalized.append(line.rstrip())
        index += 1
    return "\n".join(normalized).strip()


def failure_signature(nodeid: str, failure: ET.Element) -> str:
    """Return the exact auditable signature for one JUnit failure element."""

    basis = {
        "nodeid": nodeid,
        "type": _normalized(failure.attrib.get("type")),
        "message": _stable_failure_text(failure.attrib.get("message")),
        "text": _stable_failure_text(failure.text, traceback=True),
    }
    encoded = json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise BaselineValidationError(
            f"git {' '.join(args)} failed with exit code {result.returncode}: "
            f"{result.stderr.strip()}"
        )
    return result.stdout.strip()


def _validate_source_binding(
    baseline: dict[str, Any], repo_root: Path, gate_source_sha: str
) -> None:
    source_sha = baseline.get("baseline_source_sha")
    source_tree = baseline.get("baseline_source_tree")
    if not isinstance(source_sha, str) or not SHA_RE.fullmatch(source_sha):
        raise BaselineValidationError("baseline_source_sha is not a full lowercase commit SHA")
    if not isinstance(source_tree, str) or not TREE_RE.fullmatch(source_tree):
        raise BaselineValidationError("baseline_source_tree is not a full lowercase tree SHA")
    if not SHA_RE.fullmatch(gate_source_sha):
        raise BaselineValidationError("gate_source_sha is not a full lowercase commit SHA")

    actual_tree = _run_git(repo_root, "rev-parse", f"{source_sha}^{{tree}}")
    if actual_tree != source_tree:
        raise BaselineValidationError(
            "tracked failure baseline source tree does not match its source commit"
        )
    ancestor = subprocess.run(
        ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", source_sha, gate_source_sha],
        capture_output=True,
        check=False,
    )
    if ancestor.returncode != 0:
        raise BaselineValidationError(
            "gate source is not a descendant of the source commit that established "
            "the accepted failure baseline"
        )


def _load_baseline(path: Path, repo_root: Path, gate_source_sha: str) -> dict[str, dict[str, str]]:
    try:
        baseline = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineValidationError(f"cannot load tracked failure baseline: {exc}") from exc
    if not isinstance(baseline, dict) or baseline.get("schema") != SCHEMA:
        raise BaselineValidationError("tracked failure baseline schema is missing or unsupported")
    if baseline.get("signature_algorithm") != "sha256(nodeid,type,normalized_message,normalized_text_v3)":
        raise BaselineValidationError("tracked failure baseline signature algorithm is unsupported")
    _validate_source_binding(baseline, repo_root, gate_source_sha)

    entries = baseline.get("failures")
    if not isinstance(entries, list) or not entries:
        raise BaselineValidationError("tracked failure baseline has no failure identities")
    result: dict[str, dict[str, str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise BaselineValidationError("tracked failure baseline contains a non-object entry")
        nodeid = entry.get("nodeid")
        signature = entry.get("signature")
        if not isinstance(nodeid, str) or not nodeid:
            raise BaselineValidationError("tracked failure baseline entry has no nodeid")
        if not isinstance(signature, str) or not SIGNATURE_RE.fullmatch(signature):
            raise BaselineValidationError(f"invalid failure signature for {nodeid}")
        if nodeid in result:
            raise BaselineValidationError(f"duplicate failure nodeid in baseline: {nodeid}")
        result[nodeid] = {"signature": signature, "description": str(entry.get("description", ""))}
    if len(result) != len(EXPECTED_BASELINE_NODEIDS) or set(result) != EXPECTED_BASELINE_NODEIDS:
        raise BaselineValidationError(
            "tracked failure baseline node set is not the exact accepted three-node baseline"
        )
    return result


def _nodeid_for_testcase(testcase: ET.Element) -> str:
    properties_nodes = testcase.findall("properties")
    if len(properties_nodes) > 1:
        raise JUnitEvidenceError("JUnit testcase has duplicate properties containers")
    if properties_nodes:
        nodeid_values = [
            prop.attrib["value"]
            for prop in properties_nodes[0].findall("property")
            if prop.attrib.get("name") == "nodeid" and prop.attrib.get("value")
        ]
        if len(nodeid_values) > 1:
            raise JUnitEvidenceError("JUnit testcase has duplicate nodeid properties")
        if nodeid_values:
            return nodeid_values[0]

    classname = testcase.attrib.get("classname", "").strip()
    name = testcase.attrib.get("name", "").strip()
    if not classname or not name:
        raise BaselineValidationError("JUnit testcase is missing classname or name")
    module_path = "/".join(classname.split("."))
    if not module_path.endswith(".py"):
        module_path += ".py"
    return f"{module_path}::{name}"


def _parse_junit(path: Path | ET.Element) -> tuple[list[dict[str, str]], dict[str, int]]:
    try:
        root = path if isinstance(path, ET.Element) else ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise JUnitEvidenceError(f"cannot parse pytest JUnit report: {exc}") from exc

    if root.tag not in {"testsuites", "testsuite"}:
        raise JUnitEvidenceError(f"unsupported JUnit root element: {root.tag}")
    suites = [root] if root.tag == "testsuite" else list(root.findall("./testsuite"))
    if not suites:
        raise JUnitEvidenceError("JUnit report contains no testsuite element")
    # Only testsuites -> testsuite -> testcase is admitted. In particular,
    # descendant searches must never silently include orphan result records.
    parents = {child: parent for parent in root.iter() for child in parent}
    if root.tag == "testsuites" and any(child.tag != "testsuite" for child in root):
        raise JUnitEvidenceError("JUnit testsuites contains misplaced child")
    for node in root.iter():
        parent = parents.get(node)
        if node.tag == "testsuite" and node not in suites:
            raise JUnitEvidenceError("JUnit contains misplaced testsuite")
        if node.tag == "testcase" and parent not in suites:
            raise JUnitEvidenceError("JUnit contains misplaced testcase")
        if node.tag in {"error", "failure", "skipped"} and (
            parent is None or parent.tag != "testcase" or parents.get(parent) not in suites
        ):
            raise JUnitEvidenceError("JUnit contains misplaced result element")
    testcases = list(root.findall(".//testcase"))
    if not testcases:
        raise JUnitEvidenceError("JUnit report contains no testcase elements")

    failures: list[dict[str, str]] = []
    seen_nodeids: set[str] = set()
    error_count = 0
    skipped_count = 0
    failure_case_count = 0
    error_case_count = 0
    for suite in suites:
        unsupported_suite_children = {
            child.tag
            for child in suite
            if child.tag not in {"testcase", "properties", "system-out", "system-err"}
        }
        if unsupported_suite_children:
            raise JUnitEvidenceError(
                "JUnit suite contains unsupported result structure: "
                + ", ".join(sorted(unsupported_suite_children))
            )
        suite_testcases = suite.findall("./testcase")
        declared_counts: dict[str, int] = {}
        for attribute in ("tests", "failures", "errors", "skipped"):
            value = suite.attrib.get(attribute)
            if value is None:
                continue
            try:
                declared_counts[attribute] = int(value)
            except ValueError as exc:
                raise JUnitEvidenceError(
                    f"JUnit suite {attribute} attribute is not an integer"
                ) from exc
            if declared_counts[attribute] < 0:
                raise JUnitEvidenceError(f"JUnit suite {attribute} attribute is negative")
        observed_failure_count = sum(len(case.findall("./failure")) for case in suite_testcases)
        observed_error_count = sum(len(case.findall("./error")) for case in suite_testcases)
        observed_skipped_count = sum(len(case.findall("./skipped")) for case in suite_testcases)
        expected_counts = {
            "tests": len(suite_testcases),
            "failures": observed_failure_count,
            "errors": observed_error_count,
            "skipped": observed_skipped_count,
        }
        for attribute, expected in expected_counts.items():
            if attribute in declared_counts and declared_counts[attribute] != expected:
                raise JUnitEvidenceError(
                    f"JUnit suite {attribute} count does not match testcase evidence"
                )
        error_count += max(declared_counts.get("errors", 0), observed_error_count)

    for testcase in testcases:
        nodeid = _nodeid_for_testcase(testcase)
        if nodeid in seen_nodeids:
            raise JUnitEvidenceError(f"duplicate JUnit result record for nodeid: {nodeid}")
        seen_nodeids.add(nodeid)
        unsupported_testcase_children = {
            child.tag
            for child in testcase
            if child.tag not in {"properties", "failure", "error", "skipped", "system-out", "system-err"}
        }
        if unsupported_testcase_children:
            raise JUnitEvidenceError(
                "JUnit testcase contains unsupported result structure: "
                + ", ".join(sorted(unsupported_testcase_children))
            )
        skipped_results = testcase.findall("./skipped")
        testcase_failures = testcase.findall("./failure")
        testcase_errors = testcase.findall("./error")
        if len(skipped_results) > 1 or len(testcase_failures) > 1 or len(testcase_errors) > 1:
            raise JUnitEvidenceError(f"duplicate JUnit result element for nodeid: {nodeid}")
        result_kinds = sum(bool(items) for items in (skipped_results, testcase_failures, testcase_errors))
        if result_kinds > 1:
            raise JUnitEvidenceError(f"ambiguous JUnit result elements for nodeid: {nodeid}")
        if skipped_results:
            skipped_count += 1
        if testcase_failures:
            failure = testcase_failures[0]
            if not any(
                _normalized(value)
                for value in (failure.attrib.get("type"), failure.attrib.get("message"), failure.text)
            ):
                raise JUnitEvidenceError(f"JUnit failure has no identity-bearing detail: {nodeid}")
            failure_case_count += 1
            failures.append(
                {
                    "nodeid": nodeid,
                    "signature": failure_signature(nodeid, failure),
                    "type": _normalized(failure.attrib.get("type")),
                    "message": _stable_failure_text(failure.attrib.get("message")),
                }
            )
        if testcase_errors:
            error_case_count += 1

    if error_count != error_case_count:
        raise JUnitEvidenceError("JUnit errors do not reconcile with testcase evidence")
    if root.tag == "testsuites":
        totals = {"tests": len(testcases), "failures": failure_case_count,
                  "errors": error_case_count, "skipped": skipped_count}
        for attribute, actual in totals.items():
            if attribute in root.attrib:
                try:
                    declared = int(root.attrib[attribute])
                except ValueError as exc:
                    raise JUnitEvidenceError("JUnit aggregate count is not an integer") from exc
                if declared != actual:
                    raise JUnitEvidenceError("JUnit aggregate count does not match testcase evidence")
    passed_count = len(testcases) - skipped_count - failure_case_count - error_case_count
    return failures, {
        "passed": passed_count,
        "skipped": skipped_count,
        "failed": len(failures),
        "errors": error_count,
        "total": len(testcases),
    }


OWNER_CONFLICT_RESULT = "PASS_WITH_OWNER_APPROVED_CONTRACT_CONFLICTS"
PASSING_RESULTS = frozenset({"PASS", OWNER_CONFLICT_RESULT})


def _execution_source_identity(expected_path: Path) -> str:
    """Ordinary imports/CLI cannot recover their originally executed source bytes."""
    raise BaselineValidationError("evaluator was not executed by the source snapshot loader")


class _SourceSnapshotLoader:
    """One read, one compile, one execution; never consult importlib's bytecode cache.

    This is a loader for a trusted Python host, not an external reviewer or a
    sandbox against a host that can replace Python functions/globals. The host
    must trust this bootstrap independently; a candidate receipt cannot do that.
    """

    def __init__(self, path: Path):
        self.path = str(path.resolve(strict=True))
        if path.absolute() != Path(self.path):
            raise BaselineValidationError("source snapshot path is redirected or ambiguous")
        self.source = Path(self.path).read_bytes()
        self.started = False

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        if self.started:
            raise BaselineValidationError("source snapshot cannot be executed twice")
        self.started = True
        # Both compile and digest consume these same immutable bytes, even if
        # the pathname/symlink is changed during or after this load.
        source = self.source
        code = compile(source, self.path, "exec", dont_inherit=True, optimize=0)
        namespace = module.__dict__
        namespace["__file__"] = self.path
        exec(code, namespace)
        functions = {
            name: (value, value.__code__)
            for name, value in namespace.items()
            if isinstance(value, FunctionType) and value.__globals__ is namespace
            and name != "_execution_source_identity"
        }
        digest = hashlib.sha256(source).hexdigest()
        origin = self.path
        spec = module.__spec__

        def executed_identity(expected_path: Path):
            if (module.__dict__ is not namespace or namespace.get("__file__") != origin
                    or Path(expected_path).absolute() != Path(origin)
                    or namespace.get("__spec__") is not spec or spec.origin != origin
                    or spec.loader is not self or namespace.get("__loader__") is not self
                    or any(namespace.get(name) is not fn or fn.__code__ is not fn_code
                           for name, (fn, fn_code) in functions.items())):
                raise BaselineValidationError("executed source namespace/path/code identity changed")
            return digest

        namespace["_execution_source_identity"] = executed_identity


def _load_source_snapshot(path: Path, name: str):
    try:
        loader = _SourceSnapshotLoader(path)
        spec = importlib.util.spec_from_loader(name, loader, origin=loader.path)
        if spec is None:
            raise BaselineValidationError("source snapshot module spec unavailable")
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise BaselineValidationError(f"cannot execute source snapshot: {exc}") from exc


def load_execution_snapshot():
    """Explicit trusted-host entry point returning a fresh evaluator instance.

    No automatic re-execution of an already imported evaluator, no sys.modules
    replacement, and no reviewer authentication is implied. Ordinary imports
    remain usable for baseline evaluation but cannot activate Owner-B conflicts.
    """
    return _load_source_snapshot(Path(__file__), "g009_snapshot_evaluator")


def _load_owner_policy_module():
    """Execute one sibling source snapshot, independent of sys.path and pyc."""
    module = _load_source_snapshot(
        Path(__file__).with_name("zone4_owner_b_policy.py"), "g009_snapshot_owner_policy"
    )
    # This provider belongs to this actual evaluator instance. There is no
    # caller-supplied digest/boolean/provenance argument on evaluate_conflicts.
    module._evaluator_execution_identity = _execution_source_identity
    return module


def _git_returncode(repo_root: Path, *args: str, allow_failure: bool = True) -> int:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args], capture_output=True, check=False
    ).returncode


def evaluate(
    *,
    junit_path: Path,
    baseline_path: Path,
    repo_root: Path,
    gate_source_sha: str,
    pytest_exit_code: int,
    owner_conflict_policy_path: Path | None = None,
    review_attestor=None,
) -> dict[str, Any]:
    baseline = _load_baseline(baseline_path, repo_root, gate_source_sha)
    try:
        junit_bytes = Path(junit_path).read_bytes()
        junit_root = ET.fromstring(junit_bytes)
    except (OSError, ET.ParseError) as exc:
        raise JUnitEvidenceError(f"cannot parse pytest JUnit report: {exc}") from exc
    failures, counts = _parse_junit(junit_root)
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "junit_sha256": hashlib.sha256(junit_bytes).hexdigest(),
        "pytest_exit_code": pytest_exit_code,
        "passed_test_count": counts["passed"],
        "skipped_test_count": counts["skipped"],
        "failed_test_count": counts["failed"],
        "known_pre_existing_failure_count": 0,
        "candidate_introduced_failure_count": 0,
        "known_pre_existing_failures": [],
        "unexpected_failures": [],
    }

    if counts["errors"]:
        result.update({"result": "BLOCK", "reason": "collection_or_test_runner_error", "error_count": counts["errors"]})
        return result
    if pytest_exit_code not in (0, 1):
        result.update({"result": "BLOCK", "reason": "unexpected_pytest_exit_code"})
        return result
    if pytest_exit_code == 0 and failures:
        result.update({"result": "BLOCK", "reason": "pytest_exit_code_inconsistent_with_junit_failures"})
        return result
    if pytest_exit_code == 1 and not failures:
        result.update({"result": "BLOCK", "reason": "nonzero_pytest_exit_without_test_failures"})
        return result

    for failure in failures:
        expected = baseline.get(failure["nodeid"])
        if expected and expected["signature"] == failure["signature"]:
            result["known_pre_existing_failures"].append(failure["nodeid"])
        else:
            result["unexpected_failures"].append(failure)

    accepted_conflicts: list[dict[str, Any]] = []
    if owner_conflict_policy_path is not None:
        policy_module = _load_owner_policy_module()
        try:
            owner_report = policy_module.evaluate_conflicts(
                policy_path=Path(owner_conflict_policy_path),
                junit_path=Path(junit_path),
                repo_root=Path(repo_root),
                gate_source_sha=gate_source_sha,
                unexpected_failures=result["unexpected_failures"],
                evaluator_path=Path(__file__).resolve(),
                nodeid_for_testcase=_nodeid_for_testcase,
                failure_signature=failure_signature,
                stable_text=_stable_failure_text,
                run_git=_git_returncode,
                junit_root=junit_root,
                review_attestor=review_attestor,
            )
        except policy_module.OwnerConflictPolicyError as exc:
            result.update({"result": "BLOCK", "reason": "owner_conflict_policy_invalid", "detail": str(exc)})
            result["candidate_introduced_failure_count"] = len(result["unexpected_failures"])
            return result
        result["owner_conflict_policy"] = owner_report
        accepted = set(owner_report["accepted"])
        accepted_conflicts = [
            {**failure, "classification": policy_module.LABEL, "counted_as_passed": False}
            for failure in result["unexpected_failures"]
            if failure["nodeid"] in accepted
        ]
        result["unexpected_failures"] = [
            failure for failure in result["unexpected_failures"] if failure["nodeid"] not in accepted
        ]
    result["owner_approved_contract_conflicts"] = accepted_conflicts
    result["owner_approved_contract_conflict_count"] = len(accepted_conflicts)

    result["known_pre_existing_failure_count"] = len(result["known_pre_existing_failures"])
    result["candidate_introduced_failure_count"] = len(result["unexpected_failures"])
    if result["unexpected_failures"]:
        result.update({"result": "BLOCK", "reason": "unrecognized_or_changed_failure"})
        return result

    if accepted_conflicts:
        result.update({"result": OWNER_CONFLICT_RESULT, "reason": "exact_known_baseline_and_owner_approved_contract_conflicts"})
        return result
    result.update({"result": "PASS", "reason": "exact_known_baseline_or_zero_failures"})
    return result


def _evaluate_for_cli(
    *,
    junit_path: Path,
    baseline_path: Path,
    repo_root: Path,
    gate_source_sha: str,
    pytest_exit_code: int,
    owner_conflict_policy_path: Path | None = None,
    review_attestor=None,
) -> dict[str, Any]:
    try:
        return evaluate(
            junit_path=junit_path,
            baseline_path=baseline_path,
            repo_root=repo_root,
            gate_source_sha=gate_source_sha,
            pytest_exit_code=pytest_exit_code,
            owner_conflict_policy_path=owner_conflict_policy_path,
            review_attestor=review_attestor,
        )
    except JUnitEvidenceError as exc:
        return {
            "schema": SCHEMA,
            "result": "BLOCK",
            "reason": "malformed_or_ambiguous_junit",
            "detail": str(exc),
            "candidate_introduced_failure_count": 0,
        }
    except BaselineValidationError as exc:
        return {
            "schema": SCHEMA,
            "result": "BLOCK",
            "reason": "baseline_validation_failed",
            "detail": str(exc),
            "candidate_introduced_failure_count": 0,
        }
    except Exception as exc:  # pragma: no cover - exercised through the CLI guard test
        return {
            "schema": SCHEMA,
            "result": "BLOCK",
            "reason": "evaluator_internal_error",
            "detail": f"{type(exc).__name__}: {exc}",
            "candidate_introduced_failure_count": 0,
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junitxml", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--gate-source-sha", required=True)
    parser.add_argument("--pytest-exit-code", required=True, type=int)
    parser.add_argument(
        "--owner-conflict-policy",
        type=Path,
        default=None,
        help="Owner-approved contract-conflict policy (inactive until independently reviewed)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = _evaluate_for_cli(
        junit_path=args.junitxml,
        baseline_path=args.baseline,
        repo_root=args.repo_root,
        gate_source_sha=args.gate_source_sha,
        pytest_exit_code=args.pytest_exit_code,
        owner_conflict_policy_path=args.owner_conflict_policy,
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("result") in PASSING_RESULTS else 1


if __name__ == "__main__":
    sys.exit(main())
