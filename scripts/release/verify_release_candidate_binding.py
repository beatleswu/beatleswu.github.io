#!/usr/bin/env python3
"""Gate / Product candidate binding for the G009 BUILD_APP gate.

  check     Before tests: both checkouts are git worktrees exactly at the given full SHAs, completely clean
            (tracked and untracked), the Product commit is an ancestor of the Gate commit, every path changed between
            them is release control plane (same rule as ReleaseTooling.psm1 Test-ReleaseControlPlanePath), and the
            runtime files the Frozen test and the image depend on (app.py, Dockerfile, the six E10 assets, the provenance
            manifest) are byte-identical in Gate and Product and equal to the Product commit's blobs. Records the
            control-plane bytes that will judge the run (evaluator, policy, plugin, Frozen test, these tools).
  identity  Diagnostic only; always REJECTED until an external trusted runner host is integrated. After tests:
            the record written by g009_release_identity_plugin carries the expected fresh nonce, the
            run executed from the Gate root, the imported ``app`` module is <gate>/app.py with the same bytes as the
            Product app.py, the Frozen Zone4 test module executed has the pinned bytes, and bytecode came from a
            pycache prefix outside both checkouts (no stale __pycache__ inside the candidate).

The parent must independently govern --expected-common-dir and the exact expected commits.
Candidate records, collection and JUnit cross-checks alone do not authenticate execution.
Exit 0 = BOUND (check only), 1 = REJECTED, 2 = usage error. Writes only --out.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

TOOL_VERSION = "1.0.0"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
FROZEN_REL = "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py"
FROZEN_SHA = "c3aed0e03a24fc6ad9182624cb92f8d8de282b4dce0e997b13425ca1af5365da"
RUNTIME_FILES = (
    "app.py", "Dockerfile", "deploy/runtime-source-provenance.json",
    "js/e10/zone4_owner_story_runtime.js", "css/e10/zone4_owner_story_runtime.css", "js/e10/zone4_cinematic_content.js",
    "css/e10/encounter_presentation_framework_v1.css", "css/e10/go_combat_owner_reference_v1.css", "css/e10/backpack.css",
)
CONTROL_PLANE_FILES = (
    "scripts/release/evaluate_build_app_test_baseline.py", "scripts/release/zone4_owner_b_policy.py",
    "scripts/release/zone4_owner_b_contract_conflict_policy.json", "scripts/release/g009_release_identity_plugin.py",
    "scripts/release/verify_e10_six_route_contract.py", "scripts/release/verify_release_candidate_binding.py",
    "scripts/release/verify_release_image_backpack.py",
    "scripts/release/build-release-image.ps1", "deploy/build-app-known-failure-baseline.json", FROZEN_REL,
)
CONTROL_PLANE_EXACT = ("scripts/build-production-image.ps1", "tools/questions_corpus_validation.py", "tests/test_questions_corpus_validation.py", "github/workflows/g009-source-snapshot.yml")
CONTROL_PLANE_PREFIXES = ("scripts/release/", "tests/deployment/", "tests/release/", "docs/deployment/")


def is_control_plane(path: str) -> bool:
    """Python port of ReleaseTooling.psm1 Test-ReleaseControlPlanePath (keep in sync)."""
    # PowerShell: ($Path -replace '\\','/').TrimStart('./') trims any leading '.' and '/' characters;
    # '-eq' and the OrdinalIgnoreCase StartsWith are both case-insensitive.
    normalized = path.replace("\\", "/").lstrip("./").lower()
    if normalized in {p.lower() for p in CONTROL_PLANE_EXACT}:
        return True
    return any(normalized.startswith(prefix) for prefix in CONTROL_PLANE_PREFIXES)


def sha_file(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def git(root: Path, *args: str, binary: bool = False):
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    return p.returncode, (p.stdout if binary else p.stdout.decode("utf-8", "replace").strip())


def checkout_facts(root: Path, expected_sha: str, label: str, problems: list) -> dict:
    facts = {"root": str(root)}
    if not root.is_dir():
        problems.append(f"{label}: root does not exist")
        return facts
    rc, top = git(root, "rev-parse", "--show-toplevel")
    if rc != 0:
        problems.append(f"{label}: not a git worktree")
        return facts
    facts["toplevel"] = top
    if Path(top).resolve() != root.resolve():
        problems.append(f"{label}: root is not the worktree top level ({top})")
    values = {}
    for key, argv in (
        ("head", ("rev-parse", "HEAD")), ("tree", ("rev-parse", "HEAD^{tree}")),
        ("status", ("status", "--porcelain=v1", "--untracked-files=all")),
        ("common", ("rev-parse", "--git-common-dir")),
    ):
        code, value = git(root, *argv)
        if code != 0:
            problems.append(f"{label}: git {' '.join(argv)} failed (exit {code})")
        values[key] = value if code == 0 else None
    head, tree, status, common = (values[k] for k in ("head", "tree", "status", "common"))
    if common:
        common = str((root / common).resolve())
    facts.update({"head": head, "tree": tree, "clean": status == "", "dirty_entries": (status or "").splitlines()[:50], "git_common_dir": common})
    if not HEX40.fullmatch(expected_sha or ""):
        problems.append(f"{label}: expected SHA is not a full lowercase 40-hex commit id")
    elif head != expected_sha:
        problems.append(f"{label}: HEAD {head} != expected {expected_sha}")
    if status != "":
        problems.append(f"{label}: worktree is not clean")
    return facts


def bind_repository(g: dict, p: dict, expected_common, problems: list) -> None:
    # The expected identity must come from the governing parent, never from
    # either candidate's remote URL or a comparison of candidates to each other.
    if not expected_common:
        problems.append("trusted parent expected Git common directory is required")
        return
    if not Path(expected_common).is_absolute():
        problems.append("trusted parent expected Git common directory must be absolute")
        return
    expected = Path(expected_common).resolve()
    for label, facts in (("gate", g), ("product", p)):
        actual = facts.get("git_common_dir")
        if not actual or Path(actual).resolve() != expected:
            problems.append(f"{label}: Git repository differs from trusted parent identity")


def cmd_check(args) -> dict:
    problems: list[str] = []
    gate, product = args.gate_root.resolve(), args.product_root.resolve()
    g = checkout_facts(gate, args.gate_sha, "gate", problems)
    p = checkout_facts(product, args.product_sha, "product", problems)
    bind_repository(g, p, getattr(args, "expected_common_dir", None), problems)
    rel = {}
    if not problems or ("head" in g and "head" in p):
        rc, _ = git(gate, "cat-file", "-e", f"{args.product_sha}^{{commit}}")
        rel["product_commit_in_gate_repo"] = rc == 0
        if rc != 0:
            problems.append("product commit is not present in the gate repository")
        else:
            rc, _ = git(gate, "merge-base", "--is-ancestor", args.product_sha, args.gate_sha)
            rel["product_is_ancestor_of_gate"] = rc == 0
            if rc != 0:
                problems.append("GATE_PRODUCT_ANCESTRY_REQUIRED: product is not an ancestor of gate")
            diff_rc, changed = git(gate, "diff", "--name-only", f"{args.product_sha}..{args.gate_sha}")
            if diff_rc != 0:
                problems.append(f"git diff failed (exit {diff_rc}); changed paths are unknown")
            changed_paths = sorted({c.strip() for c in changed.splitlines() if c.strip()})
            unapproved = [c for c in changed_paths if not is_control_plane(c)]
            rel.update({"changed_paths": changed_paths, "unapproved_product_paths": unapproved})
            if unapproved:
                problems.append("UNAPPROVED_PRODUCT_DIFF_DETECTED: " + ", ".join(unapproved[:20]))
    runtime = {}
    for relpath in RUNTIME_FILES:
        gs, ps = sha_file(gate / relpath), sha_file(product / relpath)
        rc, blob = git(product, "cat-file", "blob", f"{args.product_sha}:{relpath}", binary=True)
        bs = hashlib.sha256(blob).hexdigest() if rc == 0 else None
        if rc != 0:
            problems.append(f"product git cat-file failed (exit {rc}): {relpath}")
        runtime[relpath] = {"gate": gs, "product": ps, "product_commit_blob": bs}
        if gs is None or ps is None or not (gs == ps == bs):
            problems.append(f"runtime file not identical across gate/product/product commit: {relpath}")
    control = {relpath: sha_file(gate / relpath) for relpath in CONTROL_PLANE_FILES}
    for relpath, digest in control.items():
        if digest is None:
            problems.append(f"control-plane file missing in gate: {relpath}")
    if control.get(FROZEN_REL) != FROZEN_SHA:
        problems.append("Frozen Zone4 test bytes in gate differ from the pinned original")
    return {"mode": "check", "gate": g, "product": p, "relation": rel, "runtime_files_sha256": runtime,
            "control_plane_sha256": control, "problems": problems}


def junit_case_nodeid(case, gate: Path) -> str:
    """Map pytest's JUnit classname to an actual tracked test module plus classes.

    E.g. tests.deployment.test_mod.TestClass -> tests/deployment/test_mod.py::TestClass.
    Never interpret TestClass as a directory or invent an untracked module.
    """
    classname, name = case.get("classname", ""), case.get("name", "")
    tokens = classname.split(".")
    if not name or not tokens or any(
        not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token) for token in tokens
    ):
        raise ValueError("JUnit testcase has malformed module/class/name")
    for cut in range(len(tokens), 0, -1):
        path = Path(*tokens[:cut]).with_suffix(".py")
        if path.as_posix().startswith("tests/deployment/") and (gate / path).is_file():
            return path.as_posix() + "::" + "::".join(tokens[cut:] + [name])
    raise ValueError("JUnit classname cannot resolve to a test module in Gate")


def cmd_identity(args) -> dict:
    problems: list[str] = []
    gate, product = args.gate_root.resolve(), args.product_root.resolve()
    if not getattr(args, "gate_sha", None) or not getattr(args, "product_sha", None):
        problems.append("trusted parent exact Gate/Product commits are required")
    else:
        check = cmd_check(args)
        problems.extend(check["problems"])
    # Candidate pytest code can replace sys.modules, collection hooks, its own
    # plugin record and JUnit. Cross-checks below detect drift but authenticate
    # none of those. Until a trusted runner outside that interpreter attests the
    # execution/collection and frozen JUnit bytes, this mode must reject.
    # The default external-attestation mode remains fail-closed. An explicit
    # Owner-approved simplified release checks source bytes, collection, JUnit
    # and module imports locally; it is NOT a cryptographic external attestation.
    simplified = bool(getattr(args, "owner_simplified_policy", False))
    if not simplified:
        problems.append("EXTERNAL_RUNNER_ATTESTATION_REQUIRED: candidate plugin and nonce are diagnostic only")
    try:
        rec = json.loads(args.record.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"mode": "identity", "problems": [f"identity record unreadable: {exc}"]}
    if rec.get("schema") != "g009-release-identity-record-v1":
        problems.append("identity record schema unsupported")
    if not args.nonce or rec.get("nonce") != args.nonce:
        problems.append("identity record nonce does not match this run (stale or replayed record)")
    if Path(rec.get("rootdir", "")).resolve() != gate:
        problems.append(f"pytest rootdir {rec.get('rootdir')} is not the gate root")
    modules = rec.get("modules", {})
    junit_path = getattr(args, "junitxml", None)
    try:
        if junit_path is None:
            raise ValueError("parent JUnit path missing")
        junit_bytes = Path(junit_path).read_bytes()
        junit_root = ET.fromstring(junit_bytes)
        if rec.get("junit_sha256") != hashlib.sha256(junit_bytes).hexdigest():
            problems.append("plugin JUnit digest differs from parent snapshot")
        xml_nodes = []
        for case in junit_root.iter("testcase"):
            xml_nodes.append(junit_case_nodeid(case, gate))
        collected = rec.get("collection", [])
        collected_nodes = [item["nodeid"] for item in collected]
        if len(xml_nodes) != len(set(xml_nodes)) or set(xml_nodes) != set(collected_nodes):
            problems.append("JUnit and runner collection node identities differ or duplicate")
        if len(collected_nodes) != len(set(collected_nodes)):
            problems.append("duplicate runner collection nodes")
        calls = [r for r in rec.get("reports", []) if r.get("when") == "call"]
        frozen_calls = [r["nodeid"] for r in calls if r["nodeid"].startswith(FROZEN_REL + "::")]
        frozen_xml = {n for n in xml_nodes if n.startswith(FROZEN_REL + "::")}
        if len(frozen_calls) != 19 or set(frozen_calls) != frozen_xml:
            problems.append("Frozen 19-node actual call reports differ from JUnit")
        for item in collected:
            if item["nodeid"].startswith(FROZEN_REL + "::"):
                expected = (gate / FROZEN_REL).resolve()
                if Path(item["path"]).resolve() != expected or Path(item["code_file"]).resolve() != expected:
                    problems.append("Frozen collection object/code provenance differs from gate")
    except (OSError, ValueError, TypeError, KeyError, ET.ParseError) as exc:
        problems.append(f"runner/collection/JUnit cross-check unavailable: {exc}")
    app_entries = [v for k, v in modules.items() if k == "app"]
    if len(app_entries) != 1 or not app_entries[0].get("file"):
        problems.append("the run did not import exactly one top-level 'app' module")
    else:
        loaded = Path(app_entries[0]["file"]).resolve()
        if loaded != (gate / "app.py").resolve():
            problems.append(f"imported app from {loaded}, not the gate's app.py")
        app_digest = app_entries[0].get("sha256")
        if not (isinstance(app_digest, str) and re.fullmatch(r"[0-9a-f]{64}", app_digest)
                and app_digest == sha_file(gate / "app.py") == sha_file(product / "app.py")):
            problems.append("imported app bytes differ from gate/product app.py")
    frozen = [v for k, v in modules.items() if k.rsplit(".", 1)[-1] == "test_p0_zone4_cinematic_content_route_corrective"]
    if len(frozen) != 1:
        problems.append("the Frozen Zone4 test module was not executed exactly once")
    else:
        if Path(frozen[0]["file"]).resolve() != (gate / FROZEN_REL).resolve():
            problems.append("executed Frozen Zone4 module is not the gate's file")
        if (frozen[0].get("sha256") != FROZEN_SHA
                or sha_file(gate / FROZEN_REL) != FROZEN_SHA):
            problems.append("executed Frozen Zone4 module bytes differ from the pinned original")
    py = rec.get("python", {})
    prefix = py.get("pycache_prefix")
    if not prefix:
        problems.append("run did not use a pycache prefix (stale __pycache__ inside the checkout could be loaded)")
    else:
        pp = Path(prefix).resolve()
        if pp == gate or gate in pp.parents or pp == product or product in pp.parents:
            problems.append("pycache prefix lies inside a candidate checkout")
    return {"mode": "identity", "record": str(args.record), "record_sha256": sha_file(args.record), "problems": problems,
            "assurance": "OWNER_SIMPLIFIED_LOCAL_SOURCE_CHECK_NOT_EXTERNAL_ATTESTATION" if simplified else "EXTERNAL_RUNNER_REQUIRED",
            "observed": {"app": app_entries, "frozen": frozen, "python": py, "rootdir": rec.get("rootdir")}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--gate-root", required=True, type=Path)
    c.add_argument("--product-root", required=True, type=Path)
    c.add_argument("--gate-sha", required=True)
    c.add_argument("--product-sha", required=True)
    c.add_argument("--expected-common-dir", type=Path)
    c.add_argument("--out", required=True, type=Path)
    i = sub.add_parser("identity")
    i.add_argument("--record", required=True, type=Path)
    i.add_argument("--nonce", required=True)
    i.add_argument("--gate-root", required=True, type=Path)
    i.add_argument("--product-root", required=True, type=Path)
    i.add_argument("--gate-sha")
    i.add_argument("--product-sha")
    i.add_argument("--expected-common-dir", type=Path)
    i.add_argument("--junitxml", type=Path)
    i.add_argument("--owner-simplified-policy", action="store_true",
                   help="Local source-verified diagnostic release identity; no independent signer is claimed")
    i.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        result = cmd_check(args) if args.cmd == "check" else cmd_identity(args)
    except Exception as exc:
        result = {"mode": args.cmd, "problems": [f"binding evidence invalid: {type(exc).__name__}: {exc}"]}
    result.update({"tool": "verify_release_candidate_binding.py", "tool_version": TOOL_VERSION,
                   "tool_sha256": sha_file(Path(__file__)), "status": "BOUND" if not result["problems"] else "REJECTED"})
    args.out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({"mode": result["mode"], "status": result["status"], "problems": result["problems"][:12]}, indent=1))
    return 0 if result["status"] == "BOUND" else 1


if __name__ == "__main__":
    sys.exit(main())
