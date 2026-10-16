"""Owner-approved contract-conflict policy layer for the BUILD_APP evaluator (G009 Zone4, Owner option B).

The Owner admitted the sixth exact E10 stylesheet route ``/css/e10/backpack.css``. Two Frozen tests in
``tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py`` still encode the older five-route
contract and therefore FAIL. They stay FAIL. This module lets the BUILD_APP gate *recognise* exactly those two
failures as ``OWNER_APPROVED_CONTRACT_CONFLICT`` -- never as a pass -- when, and only when, every one of these
holds in the same evaluation:

* the policy file is structurally exact and bound to an ancestor commit of the gate source;
* an authenticated external host attests the real independent reviewer session and the digest of a receipt
  binding this module, the evaluator and the policy file (the CLI has no such host yet and stays inactive);
* the Frozen module executed from the gate tree has the pinned bytes and is unmodified against HEAD;
* the JUnit report contains exactly the pinned 19 nodes of that module: the 17 pinned nodes passed, the two
  pinned nodes failed with the pinned v3 signatures, and their failure text names ``/css/e10/backpack.css``
  as the sole cause (extra route in the set test; 200-instead-of-404 in the sibling test).

Any deviation leaves both failures unexpected, so the unchanged evaluator logic BLOCKs. The three-node
historical baseline is not touched by this module.
"""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable

POLICY_SCHEMA = "g009-owner-approved-contract-conflict-policy-v1"
RECEIPT_SCHEMA = "g009-owner-approved-contract-conflict-independent-review-v1"
LABEL = "OWNER_APPROVED_CONTRACT_CONFLICT"
SIGNATURE_ALGORITHM = "sha256(nodeid,type,normalized_message,normalized_text_v3)"
REASON_KINDS = {"EXTRA_ROUTE_ONLY", "STATUS_200_NOT_404"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
POLICY_KEYS = {
    "schema", "policy_id", "label", "author", "owner_decision", "signature_algorithm", "policy_source_sha",
    "frozen_module", "conflicts", "activation",
}
FROZEN_KEYS = {"path", "sha256", "expected_passed_nodeids"}
CONFLICT_KEYS = {"nodeid", "signature", "reason_kind", "route"}
ACTIVATION_KEYS = {"review_receipt_path", "receipt_schema"}
RECEIPT_KEYS = {
    "schema", "policy_id", "verdict", "reviewer_id", "reviewer_kind", "reviewed_at",
    "reviewed_policy_sha256", "reviewed_policy_module_sha256", "reviewed_evaluator_sha256",
}


# Independently pinned original authority; never derive these from the mutable candidate policy.
PINNED_FROZEN = {
  "path": "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py",
  "sha256": "c3aed0e03a24fc6ad9182624cb92f8d8de282b4dce0e997b13425ca1af5365da",
  "expected_passed_nodeids": [
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_source_matches_the_owner_approved_identity[js/e10/zone4_cinematic_content.js]",
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_source_matches_the_owner_approved_identity[css/e10/encounter_presentation_framework_v1.css]",
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_source_matches_the_owner_approved_identity[css/e10/go_combat_owner_reference_v1.css]",
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_url_resolves_and_serves_the_approved_bytes[js/e10/zone4_cinematic_content.js]",
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_url_resolves_and_serves_the_approved_bytes[css/e10/encounter_presentation_framework_v1.css]",
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_url_resolves_and_serves_the_approved_bytes[css/e10/go_combat_owner_reference_v1.css]",
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_url_is_a_registered_rule_not_an_accidental_catch_all[js/e10/zone4_cinematic_content.js]",
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_url_is_a_registered_rule_not_an_accidental_catch_all[css/e10/encounter_presentation_framework_v1.css]",
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_url_is_a_registered_rule_not_an_accidental_catch_all[css/e10/go_combat_owner_reference_v1.css]",
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_no_generic_e10_catchall_was_introduced",
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_sibling_and_generic_e9_surfaces_are_unchanged",
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_baked_copy_is_packaged_in_the_image[js/e10/zone4_cinematic_content.js]",
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_baked_copy_is_packaged_in_the_image[css/e10/encounter_presentation_framework_v1.css]",
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_baked_copy_is_packaged_in_the_image[css/e10/go_combat_owner_reference_v1.css]",
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_index_html_reference_matches_the_served_url[js/e10/zone4_cinematic_content.js]",
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_index_html_reference_matches_the_served_url[css/e10/encounter_presentation_framework_v1.css]",
    "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_index_html_reference_matches_the_served_url[css/e10/go_combat_owner_reference_v1.css]"
  ]
}
PINNED_CONFLICTS = [
  {
    "nodeid": "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_public_route_set_is_exactly_the_three_authorized_additions",
    "signature": "a4a091ab34ae784a47e1f6004cf11a2c33b69de0563923ecab6f9dbf1d195066",
    "reason_kind": "EXTRA_ROUTE_ONLY",
    "route": "/css/e10/backpack.css"
  },
  {
    "nodeid": "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py::test_unrouted_e10_siblings_still_404",
    "signature": "e4d0dc59ab812bca769492ad5b9dedc102f18511e49186f778df631327011de5",
    "reason_kind": "STATUS_200_NOT_404",
    "route": "/css/e10/backpack.css"
  }
]


class OwnerConflictPolicyError(ValueError):
    """The policy file itself is malformed or not bound to the gate history (always BLOCK)."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OwnerConflictPolicyError(message)


def load_policy(policy_path: Path) -> dict[str, Any]:
    return _load_policy_snapshot(policy_path)[0]


def _load_policy_snapshot(policy_path: Path) -> tuple[dict[str, Any], str]:
    """Validate and hash one immutable byte snapshot, never reopen it for attestation."""
    try:
        policy_bytes = Path(policy_path).read_bytes()
        policy = json.loads(policy_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OwnerConflictPolicyError(f"cannot load owner conflict policy: {exc}") from exc
    _require(isinstance(policy, dict) and set(policy) == POLICY_KEYS, "owner conflict policy keys are not exact")
    _require(policy["schema"] == POLICY_SCHEMA, "owner conflict policy schema unsupported")
    _require(policy["label"] == LABEL, "owner conflict policy label must be OWNER_APPROVED_CONTRACT_CONFLICT")
    _require(policy["signature_algorithm"] == SIGNATURE_ALGORITHM, "owner conflict policy signature algorithm unsupported")
    _require(isinstance(policy["author"], str) and policy["author"].strip(), "owner conflict policy author missing")
    _require(isinstance(policy["policy_id"], str) and policy["policy_id"].strip(), "owner conflict policy id missing")
    _require(isinstance(policy["owner_decision"], dict) and policy["owner_decision"], "owner decision record missing")
    _require(isinstance(policy["policy_source_sha"], str) and HEX40.fullmatch(policy["policy_source_sha"]) is not None,
             "policy_source_sha is not a full lowercase commit SHA")
    frozen = policy["frozen_module"]
    _require(isinstance(frozen, dict) and set(frozen) == FROZEN_KEYS, "frozen_module keys are not exact")
    _require(isinstance(frozen["path"], str) and frozen["path"].startswith("tests/deployment/") and frozen["path"].endswith(".py")
             and ".." not in frozen["path"].split("/"), "frozen module path is not a tests/deployment python file")
    _require(isinstance(frozen["sha256"], str) and HEX64.fullmatch(frozen["sha256"]) is not None, "frozen module sha256 malformed")
    passed = frozen["expected_passed_nodeids"]
    _require(isinstance(passed, list) and passed and all(isinstance(n, str) for n in passed), "expected passed node list malformed")
    _require(len(set(passed)) == len(passed), "expected passed node list has duplicates")
    prefix = frozen["path"] + "::"
    _require(all(n.startswith(prefix) for n in passed), "expected passed node outside the frozen module")
    conflicts = policy["conflicts"]
    _require(isinstance(conflicts, list) and len(conflicts) == 2, "policy must name exactly two conflicts")
    seen = set()
    for item in conflicts:
        _require(isinstance(item, dict) and set(item) == CONFLICT_KEYS, "conflict entry keys are not exact")
        _require(item["nodeid"].startswith(prefix), "conflict node outside the frozen module")
        _require(item["nodeid"] not in passed, "conflict node also listed as expected PASS")
        _require(HEX64.fullmatch(item["signature"]) is not None, "conflict signature malformed")
        _require(item["reason_kind"] in REASON_KINDS, "conflict reason kind unsupported")
        _require(item["route"] == "/css/e10/backpack.css", "the only Owner-approved conflict route is /css/e10/backpack.css")
        seen.add(item["nodeid"])
    _require(len(seen) == 2, "conflict node ids are not distinct")
    _require(frozen == PINNED_FROZEN, "Frozen authority differs from original 17 PASS identities/path/SHA")
    _require(conflicts == PINNED_CONFLICTS, "Frozen authority differs from original 2 FAIL identities/signatures")
    activation = policy["activation"]
    _require(isinstance(activation, dict) and set(activation) == ACTIVATION_KEYS, "activation keys are not exact")
    _require(activation["receipt_schema"] == RECEIPT_SCHEMA, "activation receipt schema unsupported")
    _require(isinstance(activation["review_receipt_path"], str) and activation["review_receipt_path"].startswith("scripts/release/")
             and ".." not in activation["review_receipt_path"].split("/"), "review receipt must live under scripts/release/")
    return policy, hashlib.sha256(policy_bytes).hexdigest()


def activation_status(policy: dict[str, Any], policy_sha256: str, repo_root: Path, evaluator_path: Path,
                      review_attestor: Callable | None = None) -> tuple[bool, str]:
    """Return (active, reason). Never raises for a missing/invalid receipt: an inactive policy simply accepts nothing."""
    receipt_path = Path(repo_root) / policy["activation"]["review_receipt_path"]
    if not receipt_path.is_file():
        return False, "PENDING_INDEPENDENT_REVIEW: review receipt absent"
    try:
        receipt_bytes = receipt_path.read_bytes()
        receipt = json.loads(receipt_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False, "INVALID_REVIEW_RECEIPT: unreadable"
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_KEYS:
        return False, "INVALID_REVIEW_RECEIPT: keys are not exact"
    if not all(isinstance(value, str) for value in receipt.values()):
        return False, "INVALID_REVIEW_RECEIPT: values must be strings"
    if receipt["schema"] != RECEIPT_SCHEMA or receipt["policy_id"] != policy["policy_id"]:
        return False, "INVALID_REVIEW_RECEIPT: schema or policy id mismatch"
    if receipt["verdict"] != "ACCEPT" or receipt["reviewer_kind"] != "independent":
        return False, "INVALID_REVIEW_RECEIPT: verdict is not an independent ACCEPT"
    reviewer = str(receipt["reviewer_id"]).strip()
    author = policy["author"].strip()
    author_session = author.split(":", 1)[-1]
    if not reviewer or reviewer == author or author_session in reviewer:
        return False, "INVALID_REVIEW_RECEIPT: reviewer is the policy author (self-review)"
    # A post-import disk read cannot identify the code already running. Only
    # the explicit trusted-host snapshot loader retains the compiled bytes.
    # Ordinary imports, including stale pyc, have no such provenance and reject.
    try:
        policy_identity = globals().get("_execution_source_identity")
        evaluator_identity = globals().get("_evaluator_execution_identity")
        if not callable(policy_identity) or not callable(evaluator_identity):
            raise ValueError("source snapshot provenance absent")
        module_sha = policy_identity(Path(__file__))
        evaluator_sha = evaluator_identity(Path(evaluator_path))
        if not all(isinstance(value, str) and HEX64.fullmatch(value)
                   for value in (module_sha, evaluator_sha)):
            raise ValueError("source snapshot provenance malformed")
    except Exception:
        return False, "EXECUTION_SOURCE_UNPROVEN: trusted snapshot execution required for policy and evaluator"
    bindings = {
        "reviewed_policy_sha256": policy_sha256,
        "reviewed_policy_module_sha256": module_sha,
        "reviewed_evaluator_sha256": evaluator_sha,
    }
    for key, actual in bindings.items():
        if receipt[key] != actual:
            return False, f"INVALID_REVIEW_RECEIPT: {key} does not match the bytes being executed"
    # A name, nonce and byte hashes in a candidate-controlled JSON file do not
    # authenticate a reviewer. Only a separately trusted host may supply this
    # verifier; the production CLI deliberately has no self-attestation option.
    if review_attestor is None:
        return False, "PENDING_EXTERNAL_REVIEW_ATTESTATION: no authenticated reviewer session and receipt digest binding"
    try:
        attested = review_attestor(receipt_bytes, dict(bindings)) is True
    except Exception:
        attested = False
    if not attested:
        return False, "INVALID_REVIEW_RECEIPT: external reviewer attestation rejected"
    return True, "ACTIVE"


def junit_outcomes(root: ET.Element, nodeid_for_testcase: Callable[[ET.Element], str]) -> dict[str, tuple[str, ET.Element | None]]:
    """nodeid -> (outcome, failure element). The evaluator's own parser has already rejected duplicates,
    ambiguous result elements and inconsistent counts before this is called."""
    outcomes: dict[str, tuple[str, ET.Element | None]] = {}
    for testcase in root.iter("testcase"):
        nodeid = nodeid_for_testcase(testcase)
        failure = testcase.find("./failure")
        if testcase.find("./error") is not None:
            outcomes[nodeid] = ("error", None)
        elif testcase.find("./skipped") is not None:
            outcomes[nodeid] = ("skipped", None)
        elif failure is not None:
            outcomes[nodeid] = ("failed", failure)
        else:
            outcomes[nodeid] = ("passed", None)
    return outcomes


def _reason_ok(kind: str, route: str, failure: ET.Element, stable_text: Callable[..., str]) -> tuple[bool, str]:
    message = stable_text(failure.attrib.get("message"))
    text = stable_text(failure.text, traceback=True)
    combined = message + "\n" + text
    quoted_routes = set(re.findall(r"'(/(?:css|js)/e10/[^']*)'", combined))
    if kind == "EXTRA_ROUTE_ONLY":
        if "Extra items in the right set:" in combined:
            return False, "set test reports missing authorised routes"
        lines = message.splitlines()
        if "Extra items in the left set:" not in lines:
            return False, "set test does not report an extra route"
        start = lines.index("Extra items in the left set:") + 1
        extra = []
        for line in lines[start:]:
            item = line.strip()
            if item.startswith("'") and item.endswith("'"):
                extra.append(item.strip("'"))
            else:
                break
        if extra != [route]:
            return False, f"extra routes are {extra}, not exactly [{route}]"
        return True, "sole extra route is " + route
    if kind == "STATUS_200_NOT_404":
        first = message.splitlines()[0] if message else ""
        if first != "AssertionError: assert 200 == 404":
            return False, "sibling test failure is not 200 instead of 404"
        if f"get('{route}')" not in message:
            return False, "200-instead-of-404 is not attributed to " + route
        others = {r for r in quoted_routes if r != route}
        if others:
            return False, f"failure text also names {sorted(others)}"
        return True, "200 instead of 404 for " + route
    return False, "unsupported reason kind"


def evaluate_conflicts(
    *,
    policy_path: Path,
    junit_path: Path,
    repo_root: Path,
    gate_source_sha: str,
    unexpected_failures: list[dict[str, str]],
    evaluator_path: Path,
    nodeid_for_testcase: Callable[[ET.Element], str],
    failure_signature: Callable[[str, ET.Element], str],
    stable_text: Callable[..., str],
    run_git: Callable[..., str],
    junit_root: ET.Element | None = None,
    review_attestor: Callable | None = None,
) -> dict[str, Any]:
    """Decide whether the two pinned Zone4 failures are recognised. Raises OwnerConflictPolicyError for a
    malformed or unbound policy; otherwise returns {'accepted': [...], 'status': ..., 'checks': {...}}."""
    policy, policy_sha256 = _load_policy_snapshot(policy_path)
    conflict_by_node = {item["nodeid"]: item for item in policy["conflicts"]}
    present = [f for f in unexpected_failures if f["nodeid"] in conflict_by_node]
    report: dict[str, Any] = {"policy_id": policy["policy_id"], "label": LABEL, "accepted": [], "checks": {}}
    if not present:
        report["status"] = "NOT_APPLICABLE_NO_CONFLICT_FAILURES"
        return report

    ancestor = run_git(Path(repo_root), "merge-base", "--is-ancestor", policy["policy_source_sha"], gate_source_sha, allow_failure=True)
    _require(ancestor == 0, "gate source does not descend from the commit that established the owner conflict policy")

    active, why = activation_status(policy, policy_sha256, Path(repo_root), Path(evaluator_path),
                                   review_attestor)
    report["activation"] = why
    if not active:
        report["status"] = "REJECTED_" + why.split(":", 1)[0]
        return report

    checks: dict[str, Any] = {}
    frozen = policy["frozen_module"]
    frozen_file = Path(repo_root) / frozen["path"]
    checks["frozen_file_present"] = frozen_file.is_file()
    checks["frozen_sha256_matches"] = checks["frozen_file_present"] and _sha256_file(frozen_file) == frozen["sha256"]
    checks["frozen_unmodified_against_head"] = run_git(Path(repo_root), "diff", "--quiet", "HEAD", "--", frozen["path"], allow_failure=True) == 0
    checks["frozen_tracked"] = run_git(Path(repo_root), "ls-files", "--error-unmatch", frozen["path"], allow_failure=True) == 0

    _require(junit_root is not None, "validated immutable JUnit snapshot is required; reopening its path is forbidden")
    outcomes = junit_outcomes(junit_root, nodeid_for_testcase)
    prefix = frozen["path"] + "::"
    module_nodes = {n for n in outcomes if n.startswith(prefix)}
    expected_nodes = set(frozen["expected_passed_nodeids"]) | set(conflict_by_node)
    checks["module_node_set_exact"] = module_nodes == expected_nodes
    checks["missing_module_nodes"] = sorted(expected_nodes - module_nodes)
    checks["unexpected_module_nodes"] = sorted(module_nodes - expected_nodes)
    not_passed = sorted(n for n in frozen["expected_passed_nodeids"] if outcomes.get(n, ("absent", None))[0] != "passed")
    checks["expected_passed_all_passed"] = not not_passed
    checks["expected_passed_not_passed"] = not_passed

    conflict_checks = {}
    for nodeid, item in conflict_by_node.items():
        outcome, failure = outcomes.get(nodeid, ("absent", None))
        entry = {"outcome": outcome}
        if outcome == "failed" and failure is not None:
            entry["signature"] = failure_signature(nodeid, failure)
            entry["signature_matches"] = entry["signature"] == item["signature"]
            entry["reason_ok"], entry["reason"] = _reason_ok(item["reason_kind"], item["route"], failure, stable_text)
        else:
            entry["signature_matches"] = False
            entry["reason_ok"], entry["reason"] = False, f"outcome is {outcome}, not failed"
        entry["ok"] = entry["signature_matches"] and entry["reason_ok"]
        conflict_checks[nodeid] = entry
    checks["conflicts"] = conflict_checks
    report["checks"] = checks

    all_ok = (
        checks["frozen_file_present"] and checks["frozen_sha256_matches"] and checks["frozen_unmodified_against_head"]
        and checks["frozen_tracked"] and checks["module_node_set_exact"] and checks["expected_passed_all_passed"]
        and all(e["ok"] for e in conflict_checks.values())
        and {f["nodeid"] for f in present} == set(conflict_by_node)
    )
    if all_ok:
        report["accepted"] = sorted(conflict_by_node)
        report["status"] = "ACCEPTED_EXACT_TWO_OWNER_APPROVED_CONTRACT_CONFLICTS"
    else:
        report["status"] = "REJECTED_CONDITIONS_NOT_MET"
    return report
