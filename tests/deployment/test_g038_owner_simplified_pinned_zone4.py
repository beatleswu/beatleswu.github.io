"""G038: explicit OwnerSimplifiedPolicy handles only the two exact Frozen Zone4 failures.
Do not turn errors into PASS or waive any new source/Player/GLB defect.
"""
from __future__ import annotations
import copy
import importlib.util
import json
import pathlib
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/deployment/fixtures/g009_zone4_owner_b/frozen_module_junit_fc550_r1.xml"
POLICY = ROOT / "scripts/release/zone4_owner_b_contract_conflict_policy.json"
EVALUATOR = ROOT / "scripts/release/evaluate_build_app_test_baseline.py"
BASELINE = ROOT / "deploy/build-app-known-failure-baseline.json"


def _engine():
    spec = importlib.util.spec_from_file_location("g038_actual_evaluator", EVALUATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _report(*, simplified, junit=FIXTURE, policy=POLICY, include_policy=True):
    mod = _engine()
    return mod._evaluate_for_cli(
        junit_path=junit,
        baseline_path=BASELINE,
        repo_root=ROOT,
        gate_source_sha=_git_head(),
        pytest_exit_code=1,
        owner_conflict_policy_path=policy if include_policy else None,
        owner_simplified_policy=simplified,
    )


def _git_head():
    import subprocess
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()


def _tamper_one_failure(tmp_path):
    root=ET.parse(FIXTURE)
    fail=next(x for x in root.getroot().iter("failure"))
    fail.set("message", fail.attrib["message"].replace(
        "/css/e10/backpack.css", "/css/e10/unapproved.css"
    ))
    # In case the message text was abbreviated, alter the exact failure text.
    fail.text=(fail.text or "") + "\nInjected unapproved route!"
    destination=tmp_path/"tampered.xml"
    root.write(destination, encoding="utf-8", xml_declaration=True)
    return destination


def test_owner_simplified_requires_all_19_frozen_results_and_preserves_fail_count():
    result=_report(simplified=True)
    assert result["result"]=="PASS_WITH_OWNER_APPROVED_CONTRACT_CONFLICTS"
    assert result["passed_test_count"]==17
    assert result["failed_test_count"]==2
    assert result["known_pre_existing_failure_count"]==0
    assert result["owner_approved_contract_conflict_count"]==2
    assert result["candidate_introduced_failure_count"]==0
    assert result["owner_conflict_policy"]["status"]=="ACCEPTED_EXACT_TWO_OWNER_APPROVED_CONTRACT_CONFLICTS"
    assert result["owner_conflict_policy"]["activation"]=="OWNER_SIMPLIFIED_PINNED_POLICY_ONLY"


def test_original_external_review_mode_remains_blocked_without_independent_receipt():
    result=_report(simplified=False)
    assert result["result"]=="BLOCK"
    assert result["failed_test_count"]==2
    assert result["owner_approved_contract_conflict_count"]==0
    assert result["candidate_introduced_failure_count"]==2
    assert result["owner_conflict_policy"]["status"].startswith("REJECTED_")


def test_owner_simplified_rejects_changed_failure_signature(tmp_path):
    result=_report(simplified=True,junit=_tamper_one_failure(tmp_path))
    assert result["result"]=="BLOCK"
    assert result["candidate_introduced_failure_count"]==2
    assert result["owner_approved_contract_conflict_count"]==0


def test_owner_simplified_rejects_modified_policy_even_if_its_shape_remains_valid(tmp_path):
    policy=json.loads(POLICY.read_text(encoding="utf8"))
    policy["owner_decision"]["decision"]+=" arbitrary amendment"
    path=tmp_path/"fake-policy.json"
    path.write_text(json.dumps(policy),encoding="utf8")
    result=_report(simplified=True,policy=path)
    assert result["result"]=="BLOCK"
    assert result["reason"]=="owner_conflict_policy_invalid"


def test_owner_simplified_requires_exact_tracked_policy_path():
    result=_report(simplified=True,include_policy=False)
    assert result["result"]=="BLOCK"
    assert result["reason"]=="baseline_validation_failed"


def test_owner_simplified_rejects_missing_17_pass_or_added_frozen_node(tmp_path):
    document=ET.parse(FIXTURE)
    suite=next(document.getroot().iter("testsuite"))
    first=next(x for x in suite if x.tag=="testcase")
    suite.remove(first)
    suite.set("tests","18")
    path=tmp_path/"missing.xml"
    document.write(path,encoding="utf8",xml_declaration=True)
    result=_report(simplified=True,junit=path)
    assert result["result"]=="BLOCK"


def test_default_policy_does_not_obtain_blanket_waiver_from_cli_flag():
    engine=_engine()
    report=engine._evaluate_for_cli(
        junit_path=FIXTURE,baseline_path=BASELINE,
        repo_root=ROOT,gate_source_sha=_git_head(),
        pytest_exit_code=1,owner_simplified_policy=True,
        owner_conflict_policy_path=None,
    )
    assert report["result"]=="BLOCK"


def test_runtime_opt_in_reaches_the_exact_evaluator_and_no_frozen_file_changes():
    build=(ROOT/"scripts/release/build-release-image.ps1").read_text(encoding="utf8")
    evaluator=EVALUATOR.read_text(encoding="utf8")
    policy_mod=(ROOT/"scripts/release/zone4_owner_b_policy.py").read_text(encoding="utf8")
    assert "$ownerConflictArgs = if ($OwnerSimplifiedPolicy)" in build
    assert "--owner-conflict-policy $ownerConflictPolicyPath @ownerConflictArgs" in build
    assert 'action="store_true"' in evaluator
    assert 'OWNER_SIMPLIFIED_PINNED_POLICY_SHA256' in policy_mod
    assert "active, why = activation_status(" in policy_mod
    assert "owner_simplified_policy: bool = False" in policy_mod
    assert "OwnerSimplifiedPolicy" not in (ROOT/"tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py").read_text(encoding="utf8")
