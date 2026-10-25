#!/usr/bin/env python3
"""G110 local, NOT-ADOPTED fail-closed source-admission proposal.

This is not a substitute for the existing G027 GitHub check, not an Owner
release policy, and cannot authorize GO_MERGE/GO_DEPLOY. The reviewed 283
source blobs are pinned byte-for-byte and new G110 files are separately
bounded. An actual trusted Hosted runner must pin the full expected candidate
commit OUTSIDE the branch it verifies before admission can be authoritative.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
from pathlib import Path

MASTER = "b39b35481de43ee5de6f3dc70e215d2cf291c56b"
REVIEWED_PR445 = "aca38a85f1d407303ef3957ad864b583e2ffa0ac"
REVIEWED_MANIFEST_SHA256 = "f5edab377f1b8446684c3acdfb465ea3ba2d5d7e4087b82ffae2f76d640f4209"
PROPOSED_SQL_SHA256 = "bb897a7e1275209f2160965bc6dd98b265581ebde00d1e6be4dceaf05c030251"
PINNED_PATHS = frozenset({
    "deploy/g110-pr445-frozen-source-inventory.json",
    "migrations/g110_step_ledger_atomic_v1.py",
    "migrations/g110_step_ledger_atomic_v1.sql",
    "scripts/release/g110_local_admission_candidate.py",
    "tests/test_g110_migration_and_admission_contract.py",
    "docs/deployment/G110_source_and_migration_local_proposal.md",
})


class AdmissionRejected(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _must(condition, code):
    if not condition:
        raise AdmissionRejected(code)


def _git(root, *args):
    p = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=70,
    )
    _must(p.returncode == 0, "GIT_READ_FAILED")
    return p.stdout


def _base_verified(root, expected_new_head):
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    _must(head == expected_new_head, "UNPINNED_NEW_HEAD")
    _must(len(expected_new_head) == 40, "INVALID_NEW_SHA")
    _must(not _git(root, "status", "--porcelain=v1").strip(), "DIRTY_WORKTREE")
    for ancestor in (MASTER, REVIEWED_PR445):
        _must(_git(root, "merge-base", ancestor, head).decode().strip() == ancestor,
              "HISTORICAL_ANCESTRY_MISMATCH")
    _must(_git(root, "show", MASTER + ":.github/workflows/g009-source-snapshot.yml") ==
          _git(root, "show", head + ":.github/workflows/g009-source-snapshot.yml"),
          "HISTORICAL_G027_WORKFLOW_MUTATED")
    _must(_git(root, "rev-list", "--count", MASTER + ".." + REVIEWED_PR445).strip() == b"73",
          "REVIEWED_COMMIT_COUNT_CHANGED")
    new_names = set(
        x.decode("utf8") for x in _git(
            root, "diff", "--name-only", "-z", REVIEWED_PR445, head
        ).split(b"\0") if x
    )
    _must(new_names == PINNED_PATHS, "UNAPPROVED_G110_DELTA_PATHS")
    _must(not _git(root, "diff", "--check", MASTER, head).strip(),
          "GIT_DIFF_CHECK_ERROR")
    return {"head": head, "new_file_count": len(new_names)}


def _load_reviewed(root):
    manifest = root / "deploy" / "g110-pr445-frozen-source-inventory.json"
    payload = manifest.read_bytes()
    _must(hashlib.sha256(payload).hexdigest() == REVIEWED_MANIFEST_SHA256,
          "REVIEWED_MANIFEST_TAMPERED")
    return json.loads(payload)


def _actual_reviewed_source(root):
    changed = {
        p.decode("utf8") for p in _git(
            root, "diff", "--name-only", "-z", MASTER, REVIEWED_PR445
        ).split(b"\0") if p
    }
    _must(len(changed) == 283, "REVIEWED_GIT_PATH_SET_CHANGED")
    entries = {}
    total = 0
    for path in sorted(changed):
        tree = _git(root, "ls-tree", REVIEWED_PR445, "--", path).decode().strip()
        if not tree:
            entries[path] = {"status": "DELETED_FROM_HEAD"}
            continue
        parts = tree.split(None, 3)
        _must(len(parts) == 4 and parts[1] == "blob", "UNEXPECTED_GIT_TREE_KIND")
        mode, _, oid, _ = parts
        blob = _git(root, "cat-file", "blob", oid)
        entries[path] = {
            "status": "PRESENT",
            "mode": mode,
            "git_blob_oid": oid,
            "canonical_sha256": hashlib.sha256(blob).hexdigest(),
            "byte_size": len(blob),
        }
        total += len(blob)
    return {"entries": entries, "total": total, "paths": changed}


def validate_reviewed_payload(manifest, actual):
    _must(manifest.get("schema") == "G108_EXACT_283_PATH_CANDIDATE_INTAKE_NOT_OWNER_APPROVED_V1",
          "MANIFEST_SCHEMA")
    _must(manifest.get("origin_master_base") == MASTER and
          manifest.get("candidate_ci_only_head") == REVIEWED_PR445, "BASE_OR_HEAD")
    items = manifest.get("entries")
    _must(isinstance(items, list) and
          manifest.get("changed_paths_count") == 283 and len(items) == 283, "CARDINALITY")
    paths = [x.get("path") for x in items]
    _must(len(paths) == len(set(paths)), "DUPLICATE_PATH")
    _must(set(paths) == actual["paths"], "PATH_SET")
    _must(manifest.get("ahead_commits") == 73, "COMMIT_COUNT")
    total = 0
    for item in items:
        real = actual["entries"][item["path"]]
        _must(item.get("status") == real["status"], "GIT_ENTRY_STATUS")
        if real["status"] == "DELETED_FROM_HEAD":
            continue
        _must(item.get("mode") == real["mode"], "GIT_MODE")
        _must(item.get("git_blob_oid") == real["git_blob_oid"], "GIT_OID")
        _must(item.get("canonical_sha256") == real["canonical_sha256"], "GIT_BLOB_SHA256")
        _must(item.get("byte_size") == real["byte_size"], "GIT_BLOB_SIZE")
        total += item["byte_size"]
    _must(manifest.get("changed_git_blob_bytes") == total == actual["total"],
          "BLOB_TOTAL_BYTES")
    return len(items)


def _negative_tests(manifest, actual):
    controls = [
        ("corrupt_blob_sha", "GIT_BLOB_SHA256",
         lambda x:x["entries"][0].update(canonical_sha256="0"*64)),
        ("corrupt_head", "BASE_OR_HEAD",
         lambda x:x.update(candidate_ci_only_head="0"*40)),
        ("corrupt_base", "BASE_OR_HEAD",
         lambda x:x.update(origin_master_base="0"*40)),
        ("add_unapproved_path", "CARDINALITY",
         lambda x:x["entries"].append({"path":"hidden.txt","status":"PRESENT"})),
        ("remove_reviewed_path", "CARDINALITY",
         lambda x:x["entries"].pop()),
        ("duplicate_path", "DUPLICATE_PATH",
         lambda x:x["entries"][1].update(path=x["entries"][0]["path"])),
        ("wrong_commit_count", "COMMIT_COUNT",
         lambda x:x.update(ahead_commits=72)),
        ("tampered_file_mode", "GIT_MODE",
         lambda x:x["entries"][0].update(mode="100755" if x["entries"][0]["mode"]=="100644" else "100644")),
        ("wrong_blob_total", "BLOB_TOTAL_BYTES",
         lambda x:x.update(changed_git_blob_bytes=1)),
    ]
    results = []
    for name, expected, mutate in controls:
        candidate = copy.deepcopy(manifest)
        mutate(candidate)
        try:
            validate_reviewed_payload(candidate, actual)
        except AdmissionRejected as ex:
            _must(ex.code == expected, "WRONG_NEGATIVE_ERROR_CODE:" + name)
            results.append({"case": name, "rejected_with_exact_code": expected})
        else:
            raise AdmissionRejected("FORGED_SOURCE_ACCEPTED:" + name)
    return results


def verify(root, expected_new_head):
    expected = _base_verified(root, expected_new_head)
    raw = _load_reviewed(root)
    actual = _actual_reviewed_source(root)
    matches = validate_reviewed_payload(raw, actual)
    forged = _negative_tests(raw, actual)
    sql_path = root / "migrations" / "g110_step_ledger_atomic_v1.sql"
    _must(hashlib.sha256(sql_path.read_bytes()).hexdigest() == PROPOSED_SQL_SHA256,
          "MIGRATION_SQL_SOURCE_CHANGED")
    return {
        "status": "LOCAL_SOURCE_AND_NEGATIVE_CONTROLS_PASS_NOT_ADOPTED",
        "new_head": expected["head"],
        "historical_reviewed_files": matches,
        "allowed_g110_delta_paths": sorted(PINNED_PATHS),
        "negative_cases_exact_rejection": forged,
        "old_G027_Hosted_status": "FAIL_UNCHANGED",
        "G110_new_Hosted_workflow": "NOT_INSTALLED_OR_AUTHORIZED",
        "owner_source_policy_adopted": False,
        "formal_merge_authorized": False,
        "formal_deploy_authorized": False,
        "product_release": "NO_GO",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    _must(len(args.expected_head) == 40, "EXPECTED_SHA_REQUIRED")
    result = verify(args.root, args.expected_head)
    _must(not args.receipt.exists(), "RECEIPT_ALREADY_EXISTS")
    args.receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({
        "result":result["status"],
        "reviewed_files":result["historical_reviewed_files"],
        "new_delta":len(result["allowed_g110_delta_paths"]),
        "negative_controls":len(result["negative_cases_exact_rejection"]),
        "G027":"FAIL_UNCHANGED","formal_release":"NO_GO",
    }))


if __name__ == "__main__":
    main()
