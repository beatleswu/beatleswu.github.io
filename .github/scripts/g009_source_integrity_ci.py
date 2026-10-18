#!/usr/bin/env python3
"""GitHub-hosted source integrity only; this NEVER authorizes BUILD_APP."""
import datetime, hashlib, json, os, subprocess, sys
from pathlib import Path

REPO = "beatleswu/beatleswu.github.io"
BRANCH = "candidate/g009-governance-source-intake-20261018-r1"
MASTER = "0f14f95c4fd9f70fcbdaa929b8fed3a4a9316463"
PRODUCT = "69dbe57aa535112b1759e3f3bdcf9ecbe1680efb"
BRIDGE = "5672d5cf494aeaa140c71920db5befd3ae194af2"
GATE = "e4a16813fc38e84891bbcfca77dbab7d291b61bc"
ADDITIONS = {".github/scripts/g009_source_integrity_ci.py", ".github/workflows/g009-source-admission-proof.yml"}
GOVERNANCE = {
  "docs/deployment/EXTERNAL_GOVERNANCE_BRIDGE_REPORT.md": "b49ebcf764ec73b78963cc3a35819d44348af9a5f4ffa14bbe66163e3ac57660",
  "docs/deployment/EXTERNAL_GOVERNANCE_OPERATOR_RUNBOOK.md": "0855317623d6ff164818ec6e3196435c58c19a2cc5202a4719f72f47f8dbb08d",
  "scripts/release/build-release-image.ps1": "e44e178bb781c8f93622303b5bf97851038e34e3cb59ee44dac74c1ec1ea0502",
  "scripts/release/verify_external_governance.py": "ab39785ed7a6c72c46b07a8d2ad4bad3e0da2e26d23d859191d82ee95d062911",
  "scripts/release/verify_release_candidate_binding.py": "78efa9e06dbde51f02010b5c246446d346525249959dabccfd951a242b2db7fc",
  "tests/deployment/test_external_governance_bridge.py": "0394a7ed499f92e11b2c56c08b4736812bb0adb704004f8901eae53651b05616",
  "tests/deployment/test_external_governance_build_report.py": "7ada01a89af8568b906113a496228cd5fd084192475019035bad0757f75588a8",
  "tests/deployment/test_g009_release_candidate_tooling.py": "7698a084467c07bb126da09f2271c4aef3f0fe9eb1ceb6d2cd2f1446016dcf92"
}
R4_REPORT_SHA256 = "aa3d6e6fd57000d578a5162471ee4182954bc9692b46c3fdb4e84bdb9db98b2b"

def git(*args):
    p = subprocess.run(["git", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=40)
    if p.returncode:
        raise RuntimeError("git " + repr(args) + ": " + p.stderr[-350:])
    return p.stdout.strip()

def main():
    ref = "refs/heads/" + BRANCH
    if (os.getenv("GITHUB_REPOSITORY") != REPO
            or os.getenv("GITHUB_REF") != ref or os.getenv("GITHUB_EVENT_NAME") != "push"):
        raise RuntimeError("WRONG_REPOSITORY_REF_OR_EVENT")
    head = git("rev-parse", "HEAD")
    if head != os.getenv("GITHUB_SHA"):
        raise RuntimeError("CHECKOUT_HEAD_DOES_NOT_MATCH_GITHUB_SHA")
    if git("rev-parse", "HEAD^") != GATE or git("rev-parse", GATE+"^") != BRIDGE:
        raise RuntimeError("GATE_PARENT_MISMATCH")
    if git("rev-parse", GATE+"^^") != PRODUCT:
        raise RuntimeError("PRODUCT_ANCESTRY_MISMATCH")
    if git("rev-parse", "refs/remotes/origin/master") != MASTER:
        raise RuntimeError("OFFICIAL_MASTER_DRIFT")
    if git("status", "--porcelain=v1", "--untracked-files=normal"):
        raise RuntimeError("CHECKOUT_NOT_CLEAN")
    ci_delta = set(git("diff", "--name-only", GATE, "HEAD").splitlines())
    if ci_delta != ADDITIONS:
        raise RuntimeError("NEW_SOURCE_SCOPE_MISMATCH " + repr(sorted(ci_delta)))
    gov_delta = set(git("diff", "--name-only", PRODUCT, GATE).splitlines())
    if gov_delta != set(GOVERNANCE):
        raise RuntimeError("GOVERNANCE_EIGHT_SCOPE_MISMATCH")
    if git("diff", "--check", PRODUCT, "HEAD"):
        raise RuntimeError("WHITESPACE_ERROR")
    for rel, expected in GOVERNANCE.items():
        f = Path(rel)
        if not f.is_file() or f.is_symlink() or hashlib.sha256(f.read_bytes()).hexdigest() != expected:
            raise RuntimeError("GOVERNANCE_BYTES_MISMATCH:" + rel)
    receipt = {
        "schema": "g009-github-source-integrity-v1",
        "repository": REPO, "github_ref": ref, "head_commit": head,
        "github_run_id": os.environ["GITHUB_RUN_ID"],
        "github_run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "master": MASTER, "product_commit": PRODUCT, "governance_gate": GATE,
        "governance_file_sha256": GOVERNANCE, "new_paths": sorted(ADDITIONS),
        "prior_r4_407_receipt_sha256": R4_REPORT_SHA256,
        "407_test_suite_rerun": False, "build_authorized": False,
        "evidence_admitted": False, "release_authorized": False,
        "source_merged": False, "deployed": False,
        "state": "SOURCE_INTEGRITY_VERIFIED_TEST_EVIDENCE_ONLY",
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    out = Path(os.environ["RUNNER_TEMP"]) / "G009_GITHUB_SOURCE_SNAPSHOT_RECEIPT.json"
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write("receipt=" + out.as_posix() + "\n")
    print(json.dumps({"state": receipt["state"], "sha": head, "no_build": True, "receipt": str(out)}))

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("G009_SOURCE_INTEGRITY_REJECTED: " + str(exc), file=sys.stderr)
        sys.exit(1)
