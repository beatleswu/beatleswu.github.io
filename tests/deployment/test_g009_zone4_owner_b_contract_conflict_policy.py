"""G009 Zone4 Owner option B: the BUILD_APP evaluator may recognise exactly two Frozen route-contract failures
as OWNER_APPROVED_CONTRACT_CONFLICT (never PASS). Every deviation must BLOCK.

Positive and negative controls run against a disposable git repository built in tmp_path (the real Frozen file
bytes, a real-evidence JUnit fixture, a test-only review receipt and a synthetic external attestor), so no test writes into this checkout. One test
evaluates the shipped policy against this checkout itself.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import py_compile
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
EVALUATOR_PATH = REPO_ROOT / "scripts" / "release" / "evaluate_build_app_test_baseline.py"
POLICY_MODULE_PATH = REPO_ROOT / "scripts" / "release" / "zone4_owner_b_policy.py"
POLICY_PATH = REPO_ROOT / "scripts" / "release" / "zone4_owner_b_contract_conflict_policy.json"
BASELINE_PATH = REPO_ROOT / "deploy" / "build-app-known-failure-baseline.json"
FIXTURE = REPO_ROOT / "tests" / "deployment" / "fixtures" / "g009_zone4_owner_b" / "frozen_module_junit_fc550_r1.xml"
FROZEN_REL = "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py"
FROZEN_SHA = "c3aed0e03a24fc6ad9182624cb92f8d8de282b4dce0e997b13425ca1af5365da"
SET_NODE = FROZEN_REL + "::test_public_route_set_is_exactly_the_three_authorized_additions"
SIBLING_NODE = FROZEN_REL + "::test_unrouted_e10_siblings_still_404"
SET_SIG = "a4a091ab34ae784a47e1f6004cf11a2c33b69de0563923ecab6f9dbf1d195066"
SIBLING_SIG = "e4d0dc59ab812bca769492ad5b9dedc102f18511e49186f778df631327011de5"
OWNER_RESULT = "PASS_WITH_OWNER_APPROVED_CONTRACT_CONFLICTS"
REVIEWER = "codex:independent-reviewer-fixture"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


EVALUATOR_BOOTSTRAP = _load("g009_owner_b_test_evaluator", EVALUATOR_PATH)
# Synthetic trusted-host loader bootstrap; this is not production attestation.
EVALUATOR = EVALUATOR_BOOTSTRAP.load_execution_snapshot()
POLICY = _load("g009_owner_b_test_policy_module", POLICY_MODULE_PATH)


def _sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def _git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(cwd), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


# ---------------------------------------------------------------------------------------------- fixtures


def _cases():
    root = ET.parse(FIXTURE).getroot()
    return [copy.deepcopy(tc) for tc in root.iter("testcase")]


def _case(cases, nodeid):
    for tc in cases:
        if EVALUATOR._nodeid_for_testcase(tc) == nodeid:
            return tc
    raise KeyError(nodeid)


def _write_junit(path, cases):
    suites = ET.Element("testsuites")
    suite = ET.SubElement(suites, "testsuite", name="pytest")
    for tc in cases:
        suite.append(tc)
    ET.ElementTree(suites).write(path, encoding="utf-8", xml_declaration=True)
    return path


class Gate:
    """Disposable gate repository with the real Frozen bytes, a baseline bound to it and a policy copy."""

    def __init__(self, tmp_path, *, receipt="valid"):
        self.root = tmp_path / "gate"
        (self.root / "tests" / "deployment").mkdir(parents=True)
        (self.root / "scripts" / "release").mkdir(parents=True)
        _git(tmp_path, "init", "-q", str(self.root))
        shutil.copyfile(REPO_ROOT / FROZEN_REL, self.root / FROZEN_REL)
        _git(self.root, "add", FROZEN_REL)
        _git(self.root, "commit", "-q", "-m", "gate")
        self.head = _git(self.root, "rev-parse", "HEAD")
        self.tree = _git(self.root, "rev-parse", "HEAD^{tree}")
        self.known_failure = ("tests/deployment/test_runtime_dependency_provenance.py",
                              "test_working_tree_matches_recorded_content_sha256")
        self.known_failure_elem = ET.Element("failure", type="AssertionError", message="known baseline failure")
        self.known_failure_elem.text = "known baseline failure text"
        known_sig = EVALUATOR.failure_signature("::".join(self.known_failure), self.known_failure_elem)
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        baseline["baseline_source_sha"] = self.head
        baseline["baseline_source_tree"] = self.tree
        for entry in baseline["failures"]:
            entry["signature"] = known_sig if entry["nodeid"] == "::".join(self.known_failure) else "0" * 64
        self.baseline = tmp_path / "baseline.json"
        self.baseline.write_text(json.dumps(baseline), encoding="utf-8")
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        policy["policy_source_sha"] = self.head
        self.policy = self.root / "scripts" / "release" / "zone4_owner_b_contract_conflict_policy.json"
        self.write_policy(policy)
        if receipt == "valid":
            self.write_receipt()

    def write_policy(self, policy):
        self.policy.write_text(json.dumps(policy, indent=2), encoding="utf-8")

    def policy_data(self):
        return json.loads(self.policy.read_text(encoding="utf-8"))

    def write_receipt(self, **overrides):
        receipt = {
            "schema": POLICY.RECEIPT_SCHEMA,
            "policy_id": self.policy_data()["policy_id"],
            "verdict": "ACCEPT",
            "reviewer_id": REVIEWER,
            "reviewer_kind": "independent",
            "reviewed_at": "2026-10-16T00:00:00+08:00",
            "reviewed_policy_sha256": _sha(self.policy),
            "reviewed_policy_module_sha256": _sha(POLICY_MODULE_PATH),
            "reviewed_evaluator_sha256": _sha(EVALUATOR_PATH),
        }
        receipt.update(overrides)
        path = self.root / self.policy_data()["activation"]["review_receipt_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt), encoding="utf-8")
        # Synthetic trusted-host fixture only, held outside the candidate file.
        self.attested_receipt_digest = _sha(path)
        return path

    def attest(self, receipt_bytes, bindings):
        receipt = json.loads(receipt_bytes)
        return (hashlib.sha256(receipt_bytes).hexdigest() == self.attested_receipt_digest
                and receipt["reviewer_id"] == REVIEWER)

    def evaluate(self, tmp_path, cases, *, exit_code=1, policy=True, attest=True, evaluator=None):
        junit = _write_junit(tmp_path / "results.xml", cases)
        return (evaluator or EVALUATOR)._evaluate_for_cli(
            junit_path=junit,
            baseline_path=self.baseline,
            repo_root=self.root,
            gate_source_sha=self.head,
            pytest_exit_code=exit_code,
            owner_conflict_policy_path=self.policy if policy else None,
            review_attestor=self.attest if attest else None,
        )

    def known_failure_case(self):
        tc = ET.Element("testcase", classname=self.known_failure[0].replace("/", ".").removesuffix(".py"), name=self.known_failure[1])
        tc.append(copy.deepcopy(self.known_failure_elem))
        return tc


def _extra_failure(name="test_brand_new_failure"):
    tc = ET.Element("testcase", classname="tests.deployment.test_other", name=name)
    f = ET.SubElement(tc, "failure", type="AssertionError", message="AssertionError: new")
    f.text = "new failure"
    return tc


def _assert_block(report, reason=None):
    assert report["result"] == "BLOCK", report
    if reason:
        assert report["reason"] == reason, report


# ---------------------------------------------------------------------------------------------- the shipped policy


def test_shipped_policy_is_structurally_exact_and_matches_the_real_evidence():
    policy = POLICY.load_policy(POLICY_PATH)
    assert policy["label"] == "OWNER_APPROVED_CONTRACT_CONFLICT"
    assert policy["frozen_module"]["sha256"] == FROZEN_SHA == _sha(REPO_ROOT / FROZEN_REL)
    conflicts = {c["nodeid"]: c["signature"] for c in policy["conflicts"]}
    assert conflicts == {SET_NODE: SET_SIG, SIBLING_NODE: SIBLING_SIG}
    fixture_nodes = {EVALUATOR._nodeid_for_testcase(tc) for tc in _cases()}
    assert fixture_nodes == set(policy["frozen_module"]["expected_passed_nodeids"]) | set(conflicts)
    for tc in _cases():
        nodeid = EVALUATOR._nodeid_for_testcase(tc)
        failure = tc.find("failure")
        if nodeid in conflicts:
            assert EVALUATOR.failure_signature(nodeid, failure) == conflicts[nodeid]
        else:
            assert failure is None and tc.find("skipped") is None and tc.find("error") is None
    assert subprocess.run(["git", "-C", str(REPO_ROOT), "merge-base", "--is-ancestor", policy["policy_source_sha"], "HEAD"]).returncode == 0


def test_shipped_policy_on_this_checkout_accepts_nothing_until_independently_reviewed(tmp_path):
    receipt = REPO_ROOT / json.loads(POLICY_PATH.read_text(encoding="utf-8"))["activation"]["review_receipt_path"]
    head = _git(REPO_ROOT, "rev-parse", "HEAD")
    report = EVALUATOR._evaluate_for_cli(
        junit_path=_write_junit(tmp_path / "r.xml", _cases()), baseline_path=BASELINE_PATH, repo_root=REPO_ROOT,
        gate_source_sha=head, pytest_exit_code=1, owner_conflict_policy_path=POLICY_PATH)
    _assert_block(report, "unrecognized_or_changed_failure")
    assert report["owner_conflict_policy"]["status"].startswith("REJECTED_PENDING_INDEPENDENT_REVIEW")
    assert report["owner_approved_contract_conflict_count"] == 0


# ---------------------------------------------------------------------------------------------- positive


def test_exact_two_conflicts_are_recognised_but_never_counted_as_pass(tmp_path):
    gate = Gate(tmp_path)
    report = gate.evaluate(tmp_path, _cases())
    assert report["result"] == OWNER_RESULT
    assert report["reason"] == "exact_known_baseline_and_owner_approved_contract_conflicts"
    assert report["failed_test_count"] == 2 and report["passed_test_count"] == 17
    assert report["owner_approved_contract_conflict_count"] == 2
    assert {c["nodeid"] for c in report["owner_approved_contract_conflicts"]} == {SET_NODE, SIBLING_NODE}
    assert all(c["classification"] == "OWNER_APPROVED_CONTRACT_CONFLICT" and c["counted_as_passed"] is False
               for c in report["owner_approved_contract_conflicts"])
    assert report["candidate_introduced_failure_count"] == 0
    assert report["owner_conflict_policy"]["status"] == "ACCEPTED_EXACT_TWO_OWNER_APPROVED_CONTRACT_CONFLICTS"


def test_self_declared_receipt_without_external_attestor_rejects(tmp_path):
    gate = Gate(tmp_path)  # receipt exists and matches all candidate hashes
    report = gate.evaluate(tmp_path, _cases(), attest=False)
    _assert_block(report)
    assert report["owner_approved_contract_conflict_count"] == 0
    assert report["owner_conflict_policy"]["status"] == "REJECTED_PENDING_EXTERNAL_REVIEW_ATTESTATION"


def _copy_execution_sources(tmp_path):
    directory = tmp_path / "execution"
    directory.mkdir()
    evaluator = directory / EVALUATOR_PATH.name
    policy = directory / POLICY_MODULE_PATH.name
    shutil.copyfile(EVALUATOR_PATH, evaluator)
    shutil.copyfile(POLICY_MODULE_PATH, policy)
    return evaluator, policy


@pytest.mark.parametrize("target", ["evaluator", "policy"])
@pytest.mark.parametrize("receipt_version", ["A", "B"])
def test_loaded_source_mutation_binds_executed_snapshot_not_later_disk(
        tmp_path, monkeypatch, target, receipt_version):
    gate = Gate(tmp_path)
    evaluator_path, policy_path = _copy_execution_sources(tmp_path)
    target_path = evaluator_path if target == "evaluator" else policy_path
    source_a = target_path.read_bytes() + b"\nSOURCE_MARKER = 'A'\n"
    source_b = source_a.replace(b"SOURCE_MARKER = 'A'", b"SOURCE_MARKER = 'B'")
    target_path.write_bytes(source_a)
    binding = "reviewed_evaluator_sha256" if target == "evaluator" else "reviewed_policy_module_sha256"
    gate.write_receipt(**{binding: hashlib.sha256(source_a if receipt_version == "A" else source_b).hexdigest()})
    loaded = None
    if target == "policy":
        loaded = EVALUATOR._load_source_snapshot(evaluator_path, "mutation_evaluator")
    loader_class = (loaded or EVALUATOR)._SourceSnapshotLoader
    original_exec = loader_class.exec_module
    observations = []

    def mutate_after_execution(loader, module):
        original_exec(loader, module)  # exercise the real loader API exactly once
        if loader.path == str(target_path.resolve()):
            observations.append(module.SOURCE_MARKER)
            target_path.write_bytes(source_b)

    monkeypatch.setattr(loader_class, "exec_module", mutate_after_execution)
    if target == "evaluator":
        loaded = EVALUATOR._load_source_snapshot(evaluator_path, "mutation_evaluator")
    report = gate.evaluate(tmp_path, _cases(), evaluator=loaded)
    assert observations == ["A"]
    assert target_path.read_bytes() == source_b
    assert report["failed_test_count"] == 2 and report["passed_test_count"] == 17
    if receipt_version == "B":
        _assert_block(report)
        assert report["owner_approved_contract_conflict_count"] == 0
        assert binding in report["owner_conflict_policy"]["activation"]
    else:
        # Only the synthetic trusted-host fixture attests A; disk B cannot
        # change which exact bytes were compiled/executed or make failures PASS.
        assert report["result"] == OWNER_RESULT
        assert all(c["counted_as_passed"] is False for c in report["owner_approved_contract_conflicts"])


def test_ordinary_evaluator_import_cannot_claim_executed_source_identity(tmp_path):
    gate = Gate(tmp_path)
    calls = []
    gate.attest = lambda *args: calls.append(args) or True
    report = gate.evaluate(tmp_path, _cases(), evaluator=EVALUATOR_BOOTSTRAP)
    _assert_block(report)
    assert report["owner_conflict_policy"]["status"] == "REJECTED_EXECUTION_SOURCE_UNPROVEN"
    assert report["owner_approved_contract_conflict_count"] == 0 and not calls


def test_ordinary_policy_import_cannot_claim_executed_source_identity(tmp_path):
    gate = Gate(tmp_path)
    active, reason = POLICY.activation_status(
        gate.policy_data(), _sha(gate.policy), gate.root, EVALUATOR_PATH,
        gate.attest)
    assert active is False and reason.startswith("EXECUTION_SOURCE_UNPROVEN:")


def test_stale_pyc_cannot_supply_snapshot_execution_or_its_identity(tmp_path):
    gate = Gate(tmp_path)
    evaluator_path, _ = _copy_execution_sources(tmp_path)
    source_a = evaluator_path.read_bytes() + b"\nSOURCE_MARKER = 1\n"
    source_b = source_a.replace(b"SOURCE_MARKER = 1", b"SOURCE_MARKER = 2")
    evaluator_path.write_bytes(source_a)
    stamp = int(evaluator_path.stat().st_mtime)
    os.utime(evaluator_path, (stamp, stamp))
    py_compile.compile(str(evaluator_path), doraise=True,
                       invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
    evaluator_path.write_bytes(source_b)
    os.utime(evaluator_path, (stamp, stamp))
    stale = _load("g009_stale_evaluator_fixture", evaluator_path)
    assert stale.SOURCE_MARKER == 1  # prove that stale bytecode really was admitted
    gate.write_receipt(reviewed_evaluator_sha256=hashlib.sha256(source_b).hexdigest())
    report = gate.evaluate(tmp_path, _cases(), evaluator=stale)
    _assert_block(report)
    assert report["owner_conflict_policy"]["status"] == "REJECTED_EXECUTION_SOURCE_UNPROVEN"
    fresh = stale.load_execution_snapshot()
    assert fresh.SOURCE_MARKER == 2
    assert fresh._execution_source_identity(evaluator_path) == hashlib.sha256(source_b).hexdigest()
    # No external attestor still unconditionally blocks even on this fresh path.
    report = gate.evaluate(tmp_path, _cases(), evaluator=fresh, attest=False)
    _assert_block(report)
    assert report["owner_conflict_policy"]["status"] == "REJECTED_PENDING_EXTERNAL_REVIEW_ATTESTATION"


@pytest.mark.parametrize("target", ["evaluator", "policy"])
def test_source_snapshot_read_errors_fail_closed(tmp_path, monkeypatch, target):
    gate = Gate(tmp_path)
    evaluator_path, policy_path = _copy_execution_sources(tmp_path)
    loaded = EVALUATOR._load_source_snapshot(evaluator_path, "read_error_evaluator")
    denied = evaluator_path if target == "evaluator" else policy_path
    original_read = pathlib.Path.read_bytes

    def deny_source(path):
        if path == denied:
            raise OSError("injected source read failure")
        return original_read(path)

    monkeypatch.setattr(pathlib.Path, "read_bytes", deny_source)
    if target == "evaluator":
        with pytest.raises(EVALUATOR.BaselineValidationError, match="source snapshot"):
            EVALUATOR._load_source_snapshot(evaluator_path, "denied_evaluator")
    else:
        report = gate.evaluate(tmp_path, _cases(), evaluator=loaded)
        _assert_block(report, "baseline_validation_failed")
        assert "source snapshot" in report["detail"]


@pytest.mark.parametrize("mismatch", ["file", "origin", "expected-path"])
def test_snapshot_module_path_ambiguity_cannot_claim_identity(tmp_path, mismatch):
    evaluator_path, _ = _copy_execution_sources(tmp_path)
    loaded = EVALUATOR._load_source_snapshot(evaluator_path, "path_mismatch_evaluator")
    expected_path = evaluator_path
    if mismatch == "file":
        loaded.__file__ = str(tmp_path / "other.py")
    elif mismatch == "origin":
        loaded.__spec__.origin = str(tmp_path / "other.py")
    else:
        expected_path = tmp_path / "other.py"
    with pytest.raises(EVALUATOR.BaselineValidationError, match="identity changed"):
        loaded._execution_source_identity(expected_path)


def test_snapshot_loader_refuses_reexecution(tmp_path):
    evaluator_path, _ = _copy_execution_sources(tmp_path)
    loaded = EVALUATOR._load_source_snapshot(evaluator_path, "single_execution_evaluator")
    with pytest.raises(EVALUATOR.BaselineValidationError, match="twice"):
        loaded.__loader__.exec_module(loaded)


def test_replaced_evaluator_function_cannot_attest_original_executable_bytes(tmp_path, monkeypatch):
    gate = Gate(tmp_path)
    evaluator_path, _ = _copy_execution_sources(tmp_path)
    loaded = EVALUATOR._load_source_snapshot(evaluator_path, "replaced_function_evaluator")
    original_signature = loaded.failure_signature
    monkeypatch.setattr(loaded, "failure_signature", lambda *args: original_signature(*args))
    report = gate.evaluate(tmp_path, _cases(), evaluator=loaded)
    _assert_block(report)
    assert report["owner_conflict_policy"]["status"] == "REJECTED_EXECUTION_SOURCE_UNPROVEN"
    assert report["owner_approved_contract_conflict_count"] == 0


def test_policy_snapshot_ignores_stale_pyc_and_cached_module(tmp_path, monkeypatch):
    gate = Gate(tmp_path)
    evaluator_path, policy_path = _copy_execution_sources(tmp_path)
    source_a = policy_path.read_bytes() + b"\nSOURCE_MARKER = 1\n"
    source_b = source_a.replace(b"SOURCE_MARKER = 1", b"SOURCE_MARKER = 2")
    policy_path.write_bytes(source_a)
    stamp = int(policy_path.stat().st_mtime)
    os.utime(policy_path, (stamp, stamp))
    py_compile.compile(str(policy_path), doraise=True,
                       invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
    policy_path.write_bytes(source_b)
    os.utime(policy_path, (stamp, stamp))
    stale = _load("g009_stale_policy_fixture", policy_path)
    assert stale.SOURCE_MARKER == 1
    monkeypatch.setitem(sys.modules, "g009_snapshot_owner_policy", stale)
    loaded = EVALUATOR._load_source_snapshot(evaluator_path, "fresh_policy_evaluator")
    fresh = loaded._load_owner_policy_module()
    assert fresh is not stale and fresh.SOURCE_MARKER == 2
    assert fresh._execution_source_identity(policy_path) == hashlib.sha256(source_b).hexdigest()
    # Receipt A must not recognise conflicts executed from source B, even if
    # both importlib's cache and sys.modules contain the formerly loaded A.
    gate.write_receipt(reviewed_policy_module_sha256=hashlib.sha256(source_a).hexdigest())
    report = gate.evaluate(tmp_path, _cases(), evaluator=loaded)
    _assert_block(report)
    assert report["owner_approved_contract_conflict_count"] == 0
    assert "reviewed_policy_module_sha256" in report["owner_conflict_policy"]["activation"]


def test_policy_replacement_cannot_attest_different_bytes_than_evaluation(tmp_path, monkeypatch):
    gate = Gate(tmp_path)
    original_bytes = gate.policy.read_bytes()
    replacement = gate.policy_data()
    replacement["owner_decision"]["date"] = "2026-10-17"
    gate.write_policy(replacement)
    gate.write_receipt()  # synthetic host fixture binds B, never the evaluated A
    replacement_bytes = gate.policy.read_bytes()
    gate.policy.write_bytes(original_bytes)
    original_read = pathlib.Path.read_bytes
    reads = []

    def replace_after_read(path):
        data = original_read(path)
        if path == gate.policy:
            reads.append(data)
            path.write_bytes(replacement_bytes)
        return data

    monkeypatch.setattr(pathlib.Path, "read_bytes", replace_after_read)
    report = gate.evaluate(tmp_path, _cases())
    _assert_block(report)
    assert report["owner_conflict_policy"]["status"] == "REJECTED_INVALID_REVIEW_RECEIPT"
    assert "reviewed_policy_sha256" in report["owner_conflict_policy"]["activation"]
    assert reads == [original_bytes]
    assert report["owner_approved_contract_conflict_count"] == 0


def test_attestor_receives_single_policy_and_receipt_snapshot(tmp_path, monkeypatch):
    gate = Gate(tmp_path)
    policy_bytes = gate.policy.read_bytes()
    receipt_path = gate.root / gate.policy_data()["activation"]["review_receipt_path"]
    receipt_bytes = receipt_path.read_bytes()
    original_read = pathlib.Path.read_bytes
    reads = []
    calls = []

    def read_once(path):
        data = original_read(path)
        if path in (gate.policy, receipt_path):
            reads.append(path)
            path.write_bytes(b"invalid replacement after snapshot")
        return data

    def reject_snapshot(receipt, bindings):
        calls.append((receipt, bindings))
        assert receipt == receipt_bytes
        assert bindings["reviewed_policy_sha256"] == hashlib.sha256(policy_bytes).hexdigest()
        return False  # synthetic host rejection must never activate the policy

    gate.attest = reject_snapshot
    monkeypatch.setattr(pathlib.Path, "read_bytes", read_once)
    report = gate.evaluate(tmp_path, _cases())
    _assert_block(report)
    assert report["owner_conflict_policy"]["status"] == "REJECTED_INVALID_REVIEW_RECEIPT"
    assert reads.count(gate.policy) == reads.count(receipt_path) == len(calls) == 1


@pytest.mark.parametrize("malformed", [b"\xff", b"{not json", b"null", b"[]", b'"receipt"'])
def test_malformed_receipt_bytes_fail_closed(tmp_path, malformed):
    gate = Gate(tmp_path)
    receipt_path = gate.root / gate.policy_data()["activation"]["review_receipt_path"]
    receipt_path.write_bytes(malformed)
    report = gate.evaluate(tmp_path, _cases())
    _assert_block(report)
    assert report["owner_conflict_policy"]["status"] == "REJECTED_INVALID_REVIEW_RECEIPT"


@pytest.mark.parametrize("field", sorted(POLICY.RECEIPT_KEYS))
def test_receipt_non_string_values_fail_closed(tmp_path, field):
    gate = Gate(tmp_path)
    gate.write_receipt(**{field: None})
    report = gate.evaluate(tmp_path, _cases())
    _assert_block(report)
    assert report["owner_conflict_policy"]["status"] == "REJECTED_INVALID_REVIEW_RECEIPT"


@pytest.mark.parametrize("malformation", [
    "orphan-error-case", "nested-case", "nested-error", "suite-error", "nested-suite",
    "suite-tests", "suite-errors", "aggregate-tests", "aggregate-errors", "duplicate-case",
])
def test_junit_misplaced_results_and_counts_fail_closed(tmp_path, malformation):
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite", tests="1", errors="0", failures="0", skipped="0")
    case = ET.SubElement(suite, "testcase", classname="tests.unit", name="test_ok")
    if malformation == "orphan-error-case":
        ET.SubElement(ET.SubElement(root, "testcase", classname="tests.other", name="test_error"), "error")
    elif malformation == "nested-case":
        ET.SubElement(ET.SubElement(case, "properties"), "testcase", classname="tests.other", name="test_hidden")
    elif malformation == "nested-error":
        ET.SubElement(ET.SubElement(case, "properties"), "error")
    elif malformation == "suite-error":
        ET.SubElement(suite, "error")
    elif malformation == "nested-suite":
        ET.SubElement(suite, "testsuite")
    elif malformation == "suite-tests":
        suite.set("tests", "2")
    elif malformation == "suite-errors":
        suite.set("errors", "1")
    elif malformation == "aggregate-tests":
        root.set("tests", "2")
    elif malformation == "aggregate-errors":
        root.set("errors", "1")
    else:
        suite.append(copy.deepcopy(case))
        suite.set("tests", "2")
    with pytest.raises(EVALUATOR.JUnitEvidenceError):
        EVALUATOR._parse_junit(root)


def test_junit_error_case_counts_reconcile_without_becoming_pass():
    root = ET.Element("testsuites", tests="1", errors="1", failures="0", skipped="0")
    suite = ET.SubElement(root, "testsuite", tests="1", errors="1", failures="0", skipped="0")
    ET.SubElement(ET.SubElement(suite, "testcase", classname="tests.unit", name="test_error"), "error")
    failures, counts = EVALUATOR._parse_junit(root)
    assert failures == []
    assert counts == {"passed": 0, "skipped": 0, "failed": 0, "errors": 1, "total": 1}


def test_three_node_baseline_still_works_next_to_the_conflicts(tmp_path):
    gate = Gate(tmp_path)
    report = gate.evaluate(tmp_path, _cases() + [gate.known_failure_case()])
    assert report["result"] == OWNER_RESULT
    assert report["known_pre_existing_failure_count"] == 1
    assert report["owner_approved_contract_conflict_count"] == 2


def test_without_policy_argument_behaviour_is_unchanged(tmp_path):
    gate = Gate(tmp_path)
    _assert_block(gate.evaluate(tmp_path, _cases(), policy=False), "unrecognized_or_changed_failure")


def test_policy_is_inert_when_the_conflicts_do_not_fail(tmp_path):
    gate = Gate(tmp_path)
    cases = _cases()
    for node in (SET_NODE, SIBLING_NODE):
        tc = _case(cases, node)
        tc.remove(tc.find("failure"))
    report = gate.evaluate(tmp_path, cases, exit_code=0)
    assert report["result"] == "PASS"
    assert report["owner_conflict_policy"]["status"] == "NOT_APPLICABLE_NO_CONFLICT_FAILURES"


def test_cli_exit_codes(tmp_path):
    gate = Gate(tmp_path)
    junit = _write_junit(tmp_path / "cli.xml", _cases())
    argv = ["--junitxml", str(junit), "--baseline", str(gate.baseline), "--repo-root", str(gate.root),
            "--gate-source-sha", gate.head, "--pytest-exit-code", "1", "--owner-conflict-policy", str(gate.policy)]
    # CLI has no authenticated external reviewer host yet; a matching receipt
    # is deliberately insufficient, even for the original 17 PASS / 2 FAIL.
    assert EVALUATOR.main(argv) == 1
    gate.write_receipt(verdict="REJECT")
    assert EVALUATOR.main(argv) == 1
    assert EVALUATOR.main(argv[:-2]) == 1


# ---------------------------------------------------------------------------------------------- negative: test evidence


def test_third_failure_blocks(tmp_path):
    gate = Gate(tmp_path)
    report = gate.evaluate(tmp_path, _cases() + [_extra_failure()])
    _assert_block(report, "unrecognized_or_changed_failure")
    assert [f["nodeid"] for f in report["unexpected_failures"]] == ["tests/deployment/test_other.py::test_brand_new_failure"]


def test_changed_failure_reason_blocks(tmp_path):
    gate = Gate(tmp_path)
    cases = _cases()
    f = _case(cases, SIBLING_NODE).find("failure")
    f.set("message", "AssertionError: assert 500 == 404")
    _assert_block(gate.evaluate(tmp_path, cases), "unrecognized_or_changed_failure")


def test_changed_message_that_still_mentions_backpack_blocks(tmp_path):
    gate = Gate(tmp_path)
    cases = _cases()
    f = _case(cases, SET_NODE).find("failure")
    f.set("message", f.get("message").replace("'/css/e10/backpack.css'", "'/css/e10/backpack.css'\n'/css/e10/evil.css'"))
    report = gate.evaluate(tmp_path, cases)
    _assert_block(report, "unrecognized_or_changed_failure")


def test_reworded_text_with_backpack_substring_blocks(tmp_path):
    gate = Gate(tmp_path)
    cases = _cases()
    f = _case(cases, SIBLING_NODE).find("failure")
    f.text = (f.text or "") + "\n(note: /css/e10/backpack.css)"
    _assert_block(gate.evaluate(tmp_path, cases), "unrecognized_or_changed_failure")


def test_changed_failure_type_blocks(tmp_path):
    gate = Gate(tmp_path)
    cases = _cases()
    _case(cases, SET_NODE).find("failure").set("type", "RuntimeError")
    _assert_block(gate.evaluate(tmp_path, cases), "unrecognized_or_changed_failure")


def test_renamed_conflict_node_blocks(tmp_path):
    gate = Gate(tmp_path)
    cases = _cases()
    _case(cases, SET_NODE).set("name", "test_public_route_set_is_exactly_the_three_authorized_additions_v2")
    _assert_block(gate.evaluate(tmp_path, cases), "unrecognized_or_changed_failure")


def test_only_one_of_the_pair_failing_blocks(tmp_path):
    gate = Gate(tmp_path)
    cases = _cases()
    tc = _case(cases, SIBLING_NODE)
    tc.remove(tc.find("failure"))
    report = gate.evaluate(tmp_path, cases)
    _assert_block(report, "unrecognized_or_changed_failure")
    assert report["owner_approved_contract_conflict_count"] == 0


def test_replacing_one_of_the_seventeen_passes_blocks(tmp_path):
    gate = Gate(tmp_path)
    cases = _cases()
    victim = next(tc for tc in cases if tc.find("failure") is None)
    victim.set("name", "test_some_unrelated_passing_test")
    report = gate.evaluate(tmp_path, cases)
    _assert_block(report, "unrecognized_or_changed_failure")
    assert report["owner_conflict_policy"]["checks"]["module_node_set_exact"] is False


def test_missing_one_of_the_seventeen_passes_blocks(tmp_path):
    gate = Gate(tmp_path)
    cases = _cases()
    cases.remove(next(tc for tc in cases if tc.find("failure") is None))
    _assert_block(gate.evaluate(tmp_path, cases), "unrecognized_or_changed_failure")


def test_extra_node_in_the_frozen_module_blocks(tmp_path):
    gate = Gate(tmp_path)
    cases = _cases()
    extra = ET.Element("testcase", classname="tests.deployment.test_p0_zone4_cinematic_content_route_corrective", name="test_injected")
    _assert_block(gate.evaluate(tmp_path, cases + [extra]), "unrecognized_or_changed_failure")


def test_skipped_required_pass_blocks(tmp_path):
    gate = Gate(tmp_path)
    cases = _cases()
    ET.SubElement(next(tc for tc in cases if tc.find("failure") is None), "skipped")
    _assert_block(gate.evaluate(tmp_path, cases), "unrecognized_or_changed_failure")


def test_error_element_blocks(tmp_path):
    gate = Gate(tmp_path)
    cases = _cases()
    ET.SubElement(next(tc for tc in cases if tc.find("failure") is None), "error", message="boom").text = "boom"
    _assert_block(gate.evaluate(tmp_path, cases), "collection_or_test_runner_error")


def test_duplicate_junit_record_blocks(tmp_path):
    gate = Gate(tmp_path)
    cases = _cases()
    _assert_block(gate.evaluate(tmp_path, cases + [copy.deepcopy(_case(cases, SET_NODE))]), "malformed_or_ambiguous_junit")


def test_inconsistent_exit_code_blocks(tmp_path):
    gate = Gate(tmp_path)
    _assert_block(gate.evaluate(tmp_path, _cases(), exit_code=0), "pytest_exit_code_inconsistent_with_junit_failures")


# ---------------------------------------------------------------------------------------------- negative: Frozen source


def test_modified_frozen_file_blocks(tmp_path):
    gate = Gate(tmp_path)
    frozen = gate.root / FROZEN_REL
    frozen.write_bytes(frozen.read_bytes() + b"\n# tampered\n")
    report = gate.evaluate(tmp_path, _cases())
    _assert_block(report, "unrecognized_or_changed_failure")
    checks = report["owner_conflict_policy"]["checks"]
    assert checks["frozen_sha256_matches"] is False and checks["frozen_unmodified_against_head"] is False


def test_committed_change_to_frozen_file_blocks(tmp_path):
    gate = Gate(tmp_path)
    frozen = gate.root / FROZEN_REL
    frozen.write_bytes(frozen.read_bytes().replace(b"backpack.css", b"backpack2.css"))
    _git(gate.root, "commit", "-q", "-am", "rewrite frozen")
    report = EVALUATOR._evaluate_for_cli(
        junit_path=_write_junit(tmp_path / "r.xml", _cases()), baseline_path=gate.baseline, repo_root=gate.root,
        gate_source_sha=_git(gate.root, "rev-parse", "HEAD"), pytest_exit_code=1, owner_conflict_policy_path=gate.policy,
        review_attestor=gate.attest)
    _assert_block(report, "unrecognized_or_changed_failure")
    assert report["owner_conflict_policy"]["checks"]["frozen_sha256_matches"] is False


def test_missing_frozen_file_blocks(tmp_path):
    gate = Gate(tmp_path)
    (gate.root / FROZEN_REL).unlink()
    _assert_block(gate.evaluate(tmp_path, _cases()), "unrecognized_or_changed_failure")


# ---------------------------------------------------------------------------------------------- negative: review / policy


def test_missing_independent_review_blocks(tmp_path):
    gate = Gate(tmp_path, receipt=None)
    report = gate.evaluate(tmp_path, _cases())
    _assert_block(report, "unrecognized_or_changed_failure")
    assert report["owner_conflict_policy"]["status"] == "REJECTED_PENDING_INDEPENDENT_REVIEW"


@pytest.mark.parametrize("override", [
    {"reviewer_id": "claude:dd0fc0f0-7539-450c-8a85-0330514abf27"},
    {"reviewer_id": "someone-reusing-dd0fc0f0-7539-450c-8a85-0330514abf27"},
    {"verdict": "REJECT"},
    {"reviewer_kind": "author"},
    {"reviewed_policy_sha256": "0" * 64},
    {"reviewed_policy_module_sha256": "0" * 64},
    {"reviewed_evaluator_sha256": "0" * 64},
    {"policy_id": "SOME_OTHER_POLICY"},
], ids=["self-review", "author-session-id", "verdict-reject", "not-independent", "policy-sha", "module-sha", "evaluator-sha", "policy-id"])
def test_invalid_review_receipt_blocks(tmp_path, override):
    gate = Gate(tmp_path)
    gate.write_receipt(**override)
    report = gate.evaluate(tmp_path, _cases())
    _assert_block(report, "unrecognized_or_changed_failure")
    assert report["owner_conflict_policy"]["status"].startswith("REJECTED_INVALID_REVIEW_RECEIPT")


def test_receipt_with_extra_field_blocks(tmp_path):
    gate = Gate(tmp_path)
    path = gate.write_receipt()
    data = json.loads(path.read_text(encoding="utf-8"))
    data["waive_everything"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    _assert_block(gate.evaluate(tmp_path, _cases()), "unrecognized_or_changed_failure")


def test_policy_edited_after_review_blocks(tmp_path):
    gate = Gate(tmp_path)
    policy = gate.policy_data()
    policy["owner_decision"]["date"] = "2026-10-17"
    gate.write_policy(policy)  # receipt still binds the old bytes
    _assert_block(gate.evaluate(tmp_path, _cases()), "unrecognized_or_changed_failure")


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(label="PASS"),
    lambda p: p["conflicts"].append(dict(p["conflicts"][0], nodeid=p["conflicts"][0]["nodeid"] + "_x")),
    lambda p: p["conflicts"][0].update(route="/css/e10/other.css"),
    lambda p: p["conflicts"][0].update(signature="z" * 64),
    lambda p: p["conflicts"][1].update(reason_kind="ANYTHING"),
    lambda p: p["frozen_module"].update(path="tests/../app.py"),
    lambda p: p.update(extra_key=True),
    lambda p: p["activation"].update(review_receipt_path="deploy/receipt.json"),
    lambda p: p["frozen_module"]["expected_passed_nodeids"].append(p["conflicts"][0]["nodeid"]),
], ids=["label-pass", "third-conflict", "other-route", "bad-signature", "reason-kind", "path-escape", "extra-key", "receipt-outside-control-plane", "conflict-also-pass"])
def test_malformed_policy_blocks(tmp_path, mutate):
    gate = Gate(tmp_path)
    policy = gate.policy_data()
    mutate(policy)
    gate.write_policy(policy)
    gate.write_receipt()  # even a matching review of a malformed policy must not help
    _assert_block(gate.evaluate(tmp_path, _cases()), "owner_conflict_policy_invalid")


def test_policy_not_bound_to_gate_history_blocks(tmp_path):
    gate = Gate(tmp_path)
    policy = gate.policy_data()
    policy["policy_source_sha"] = "1" * 40
    gate.write_policy(policy)
    gate.write_receipt()
    _assert_block(gate.evaluate(tmp_path, _cases()), "owner_conflict_policy_invalid")


def test_unreadable_policy_blocks(tmp_path):
    gate = Gate(tmp_path)
    gate.policy.write_text("{not json", encoding="utf-8")
    _assert_block(gate.evaluate(tmp_path, _cases()), "owner_conflict_policy_invalid")


@pytest.mark.parametrize("mutation", ["truncate-pass", "replace-pass", "replace-signature", "replace-node", "replace-sha"])
def test_candidate_policy_cannot_redefine_original_frozen_authority(tmp_path, mutation):
    gate = Gate(tmp_path)
    policy = gate.policy_data()
    if mutation == "truncate-pass":
        policy["frozen_module"]["expected_passed_nodeids"].pop()
    elif mutation == "replace-pass":
        policy["frozen_module"]["expected_passed_nodeids"][0] = FROZEN_REL + "::test_forged_pass"
    elif mutation == "replace-signature":
        policy["conflicts"][0]["signature"] = "0" * 64
    elif mutation == "replace-node":
        policy["conflicts"][0]["nodeid"] = FROZEN_REL + "::test_forged_failure"
    else:
        policy["frozen_module"]["sha256"] = "0" * 64
    gate.write_policy(policy)
    gate.write_receipt()
    _assert_block(gate.evaluate(tmp_path, _cases()), "owner_conflict_policy_invalid")


def test_matching_receipt_and_fake_reviewer_without_host_attestation_block(tmp_path):
    gate = Gate(tmp_path)
    report = gate.evaluate(tmp_path, _cases(), attest=False)
    _assert_block(report)
    assert report["owner_conflict_policy"]["status"] == "REJECTED_PENDING_EXTERNAL_REVIEW_ATTESTATION"
    gate.write_receipt(reviewer_id="codex:invented-reviewer-with-correct-byte-hashes")
    _assert_block(gate.evaluate(tmp_path, _cases()))


@pytest.mark.parametrize("attestor", [lambda *_: False, lambda *_: "true"])
def test_external_review_requires_exact_true(tmp_path, attestor):
    gate = Gate(tmp_path)
    gate.attest = attestor
    _assert_block(gate.evaluate(tmp_path, _cases()))


def test_junit_replacement_after_single_read_cannot_hide_a_new_failure(tmp_path, monkeypatch):
    gate = Gate(tmp_path)
    cases = _cases() + [_extra_failure()]
    replacement = _write_junit(tmp_path / "replacement.xml", _cases()).read_bytes()
    original_read = pathlib.Path.read_bytes
    observed = []

    def read_once(path):
        data = original_read(path)
        if path == tmp_path / "results.xml":
            observed.append(data)
            path.write_bytes(replacement)
        return data

    monkeypatch.setattr(pathlib.Path, "read_bytes", read_once)
    report = gate.evaluate(tmp_path, cases)
    _assert_block(report, "unrecognized_or_changed_failure")
    assert len(observed) == 1
    assert report["junit_sha256"] == hashlib.sha256(observed[0]).hexdigest()
    assert report["failed_test_count"] == 3
    assert report["unexpected_failures"][0]["nodeid"].endswith("::test_brand_new_failure")
