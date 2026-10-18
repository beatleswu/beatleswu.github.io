#!/usr/bin/env python3
"""Exact six-route E10 public contract acceptance (G009 Zone4 Owner option B successor).

Checks, against the app imported from --root (never a cached or foreign module):
  * the /js/e10/ + /css/e10/ Flask rules are exactly the six admitted routes, with no converter/catch-all rule;
  * each source file has the pinned SHA-256 and size;
  * GET 200 with body bytes == source bytes, exact MIME (text/javascript or text/css);
  * HEAD 200 with empty body and Content-Length == size; POST/PUT/DELETE 405;
  * unauthorised E10 paths (unrouted files, case/extension/traversal/prefix variants) 404;
  * the Dockerfile copies each of the six files exactly once to the same path and has no directory or wildcard
    COPY of css/e10 or js/e10.

Every case records what was observed, not only a boolean. --verify-receipt re-runs everything and rejects a receipt
whose tool, candidate identity, case set or any observation differs (stale, replayed or fabricated receipts).

Exit codes: 0 PASS (all cases pass and, with --require-clean, the root is a clean checkout at --expected-head);
1 FAIL / RECEIPT_REJECTED; 3 PENDING_CLEAN_CANDIDATE (all cases pass but the root is not a clean pinned candidate);
2 usage or import error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TOOL_VERSION = "1.0.0"
E10_PREFIXES = ("/js/e10/", "/css/e10/")
# url -> (repo path, sha256, size, mimetype, authority of the pin)
CONTRACT = {
    "/js/e10/zone4_owner_story_runtime.js": ("js/e10/zone4_owner_story_runtime.js", "99cf6644e6b6a5761cedbb89a095a35a9b0efd0a5025496d4966001afc898704", 26541, "text/javascript", "fc550 base blob (pre-existing route; no separate Owner identity record located)"),
    "/css/e10/zone4_owner_story_runtime.css": ("css/e10/zone4_owner_story_runtime.css", "870189510613b7f8830cacce70f2f68a32d695ffb8a0f7ab54d235d76a4deea2", 3153, "text/css", "fc550 base blob (pre-existing route; no separate Owner identity record located)"),
    "/js/e10/zone4_cinematic_content.js": ("js/e10/zone4_cinematic_content.js", "081154d6142212eaa0b7fe732b6e49f7dffe999938377a8a6f6f9967513598c3", 14081, "text/javascript", "Owner-approved identity pinned in the Frozen Zone4 test"),
    "/css/e10/encounter_presentation_framework_v1.css": ("css/e10/encounter_presentation_framework_v1.css", "80e9acdb2977b1e624336456452193f8f86ae1ce4e1ff0609add7c01e609f1ad", 10963, "text/css", "Owner-approved identity pinned in the Frozen Zone4 test"),
    "/css/e10/go_combat_owner_reference_v1.css": ("css/e10/go_combat_owner_reference_v1.css", "8ce6ca68de39d3e175c7382bf6b71c9e04bc2bda9a8de8ceead88ab23e8debbe", 19507, "text/css", "Owner-approved identity pinned in the Frozen Zone4 test"),
    "/css/e10/backpack.css": ("css/e10/backpack.css", "a7bb0e14a24f8845c79f4850c36f37f7c69c49452d3699a93bbbfdd2fe93c888", 25459, "text/css", "Owner Gate G009_OWNER_N13_BACKPACK_CSS_ROUTE_A_ONE_USE_20261014_001"),
}
FIXED_UNKNOWN_PROBES = (
    "/css/e10/not_a_real_stylesheet.css", "/js/e10/not_a_real_zone4_file.js", "/css/e10/Backpack.css",
    "/css/e10/BACKPACK.CSS", "/css/e10/backpack.css.map", "/css/e10/backpack.min.css", "/css/e10/backpack",
    "/css/e10/sub/backpack.css", "/css/e10/backpack.css/", "/css/e10/%2e%2e/app.py", "/css/e10/..%2fapp.py",
    "/js/e10/backpack.css", "/css/e10/zone4_cinematic_content.js", "/js/e10/zone4_owner_story_runtime.css",
    "/css/e10/", "/js/e10/", "/css/e10/.hidden.css", "/js/e10/app.py",
)
REJECTING_METHODS = ("post", "put", "delete")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _logical_dockerfile_lines(text: str) -> list[str]:
    lines, buf = [], ""
    for raw in text.splitlines():
        if raw.rstrip().endswith("\\"):
            buf += raw.rstrip()[:-1] + " "
        else:
            lines.append((buf + raw).strip())
            buf = ""
    return lines


def dockerfile_cases(dockerfile_text: str) -> list[dict]:
    cases = []
    copies = []
    for line in _logical_dockerfile_lines(dockerfile_text):
        if not line.upper().startswith("COPY "):
            continue
        tokens = [t for t in line.split()[1:] if not t.startswith("--")]
        if len(tokens) >= 2:
            copies.append((tokens[:-1], tokens[-1], line))
    for url, (rel, *_rest) in CONTRACT.items():
        exact = [c for c in copies if c[0] == [rel] and c[1] in (f"./{rel}", f"/app/{rel}")]
        cases.append({"name": f"dockerfile_exact_copy:{rel}", "pass": len(exact) == 1,
                      "observed": [c[2] for c in copies if rel in c[2]], "expected": f"exactly one 'COPY {rel} ./{rel}'"})
    wide = []
    for sources, _dest, line in copies:
        for src in sources:
            norm = src.rstrip("/")
            if norm in {".", "css", "js", "css/e10", "js/e10"} or ("*" in src or "?" in src) and (src.startswith(("css", "js")) or src in {"*", "./*"}):
                wide.append(line)
    cases.append({"name": "dockerfile_no_directory_or_wildcard_e10_copy", "pass": not wide, "observed": wide, "expected": []})
    return cases


def route_cases(flask_app, root: Path) -> list[dict]:
    cases: list[dict] = []
    rules = sorted({r.rule for r in flask_app.url_map.iter_rules() if r.rule.startswith(E10_PREFIXES)})
    cases.append({"name": "exact_six_e10_rules", "pass": rules == sorted(CONTRACT), "observed": rules, "expected": sorted(CONTRACT)})
    converters = sorted(r for r in rules if "<" in r)
    cases.append({"name": "no_e10_converter_or_catch_all_rule", "pass": not converters, "observed": converters, "expected": []})
    client = flask_app.test_client()
    for url, (rel, want_sha, want_size, want_mime, _auth) in CONTRACT.items():
        src = root / rel
        data = src.read_bytes() if src.is_file() else None
        cases.append({"name": f"source_sha:{rel}", "pass": data is not None and sha256(data) == want_sha and len(data) == want_size,
                      "observed": {"sha256": sha256(data) if data is not None else None, "size": len(data) if data is not None else None},
                      "expected": {"sha256": want_sha, "size": want_size}})
        resp = client.get(url)
        body = resp.get_data()
        cases.append({"name": f"get_200:{url}", "pass": resp.status_code == 200, "observed": resp.status_code, "expected": 200})
        cases.append({"name": f"get_body_sha:{url}", "pass": sha256(body) == want_sha and (data is None or body == data),
                      "observed": sha256(body), "expected": want_sha})
        cases.append({"name": f"get_mime:{url}", "pass": resp.mimetype == want_mime, "observed": resp.headers.get("Content-Type"), "expected": want_mime})
        resp.close()
        head = client.head(url)
        cases.append({"name": f"head_200_empty:{url}", "pass": head.status_code == 200 and head.get_data() == b"" and head.headers.get("Content-Length") == str(want_size),
                      "observed": {"status": head.status_code, "body_len": len(head.get_data()), "content_length": head.headers.get("Content-Length")},
                      "expected": {"status": 200, "body_len": 0, "content_length": str(want_size)}})
        head.close()
        for method in REJECTING_METHODS:
            r = getattr(client, method)(url)
            cases.append({"name": f"{method}_405:{url}", "pass": r.status_code == 405, "observed": r.status_code, "expected": 405})
            r.close()
    contract_paths = {rel for rel, *_ in CONTRACT.values()}
    probes = list(FIXED_UNKNOWN_PROBES)
    for sub in ("css/e10", "js/e10"):
        d = root / sub
        if d.is_dir():
            probes += ["/" + f"{sub}/{p.name}" for p in sorted(d.iterdir()) if p.is_file() and f"{sub}/{p.name}" not in contract_paths]
    for url in probes:
        r = client.get(url)
        cases.append({"name": f"unknown_404:{url}", "pass": r.status_code == 404, "observed": r.status_code, "expected": 404})
        r.close()
    return cases


def all_cases(flask_app, root: Path) -> list[dict]:
    dockerfile = root / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8") if dockerfile.is_file() else ""
    cases = route_cases(flask_app, root) + dockerfile_cases(text)
    names = [c["name"] for c in cases]
    if len(names) != len(set(names)):
        raise RuntimeError("duplicate case names")
    return cases


def _git(root: Path, *args: str) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                       env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    return p.returncode, p.stdout.strip()


def candidate_identity(root: Path) -> dict:
    rc, head = _git(root, "rev-parse", "HEAD")
    tree_rc, tree = _git(root, "rev-parse", "HEAD^{tree}")
    status_rc, status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    git_ok = rc == tree_rc == status_rc == 0
    files = {rel: sha256((root / rel).read_bytes()) if (root / rel).is_file() else None
             for rel in ["app.py", "Dockerfile"] + [v[0] for v in CONTRACT.values()]}
    return {"git_ok": git_ok, "git_return_codes": {"head": rc, "tree": tree_rc, "status": status_rc},
            "head": head if rc == 0 else None, "tree": tree if tree_rc == 0 else None,
            "clean": git_ok and status == "", "dirty_entries": status.splitlines()[:50], "files_sha256": files}


def import_app_from(root: Path):
    """Import app strictly from root: refuses a pre-imported module or any file other than root/app.py."""
    if "app" in sys.modules:
        raise RuntimeError("module 'app' already imported in this interpreter; refuse to reuse it")
    os.environ.setdefault("SECRET_KEY", "e10-six-route-acceptance-only")
    os.environ.pop("GO_ODYSSEY_LIVE_STATIC_ROOT", None)  # serve the checkout's baked files, not a live-static override
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root))
    os.chdir(root)
    import app as app_module  # noqa: PLC0415

    loaded = Path(app_module.__file__).resolve()
    if loaded != (root / "app.py").resolve():
        raise RuntimeError(f"imported app from {loaded}, not {root / 'app.py'}")
    return app_module


def build_receipt(root: Path, args, cases: list[dict], app_file: str) -> dict:
    ident = candidate_identity(root)
    failed = [c["name"] for c in cases if not c["pass"]]
    clean_ok = ident["clean"] and (not args.expected_head or ident["head"] == args.expected_head)
    if failed or not ident["git_ok"] or any(v is None for v in ident["files_sha256"].values()):
        status = "FAIL"
    elif args.require_clean and not clean_ok:
        status = "PENDING_CLEAN_CANDIDATE"
    else:
        status = "PASS"
    return {
        "schema": "g009-e10-six-route-acceptance-v1", "tool_version": TOOL_VERSION,
        "tool_sha256": sha256(Path(__file__).read_bytes()), "root": str(root), "candidate": ident,
        "expected_head": args.expected_head, "require_clean": bool(args.require_clean),
        "python": {"executable": sys.executable, "version": sys.version.split()[0],
                   "dont_write_bytecode": sys.dont_write_bytecode, "pycache_prefix": getattr(sys, "pycache_prefix", None)},
        "app_file": app_file, "contract": {u: {"path": v[0], "sha256": v[1], "size": v[2], "mime": v[3], "authority": v[4]} for u, v in CONTRACT.items()},
        "cases": cases, "counts": {"total": len(cases), "passed": len(cases) - len(failed), "failed": len(failed)},
        "failed_cases": failed, "status": status,
    }


def compare_receipts(old: dict, new: dict) -> list[str]:
    problems = []
    for key in ("schema", "tool_version", "tool_sha256", "app_file"):
        if old.get(key) != new.get(key):
            problems.append(f"{key} differs")
    for key in ("head", "tree", "clean", "files_sha256"):
        if old.get("candidate", {}).get(key) != new["candidate"].get(key):
            problems.append(f"candidate.{key} differs")
    old_cases = {c.get("name"): c for c in old.get("cases", []) if isinstance(c, dict)}
    new_cases = {c["name"]: c for c in new["cases"]}
    if len(old_cases) != len(old.get("cases", [])):
        problems.append("receipt has duplicate or malformed cases")
    if set(old_cases) != set(new_cases):
        problems.append(f"case set differs (missing {sorted(set(new_cases) - set(old_cases))[:5]}, extra {sorted(set(old_cases) - set(new_cases))[:5]})")
    for name in set(old_cases) & set(new_cases):
        if old_cases[name] != new_cases[name]:
            problems.append(f"case {name} differs from re-execution")
    if old.get("status") != new["status"] or old.get("counts") != new["counts"]:
        problems.append("status/counts differ from re-execution")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--require-clean", action="store_true")
    ap.add_argument("--expected-head")
    ap.add_argument("--verify-receipt", type=Path, help="re-run and compare against this receipt")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    try:
        app_module = import_app_from(root)
        cases = all_cases(app_module.app, root)
    except Exception as exc:  # import failure is never a pass
        args.out.write_text(json.dumps({"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}, indent=1), encoding="utf-8")
        print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    receipt = build_receipt(root, args, cases, str(Path(app_module.__file__).resolve()))
    if args.verify_receipt:
        try:
            old = json.loads(args.verify_receipt.read_text(encoding="utf-8"))
        except Exception as exc:
            old, problems = {}, [f"receipt unreadable: {exc}"]
        else:
            problems = compare_receipts(old, receipt)
        verdict = {"schema": "g009-e10-six-route-receipt-verification-v1", "verified_receipt": str(args.verify_receipt),
                   "verified_receipt_sha256": sha256(args.verify_receipt.read_bytes()) if args.verify_receipt.is_file() else None,
                   "status": "RECEIPT_REJECTED" if problems else "RECEIPT_MATCHES_RE_EXECUTION", "problems": problems, "re_execution": receipt}
        args.out.write_text(json.dumps(verdict, indent=1), encoding="utf-8")
        print(json.dumps({"status": verdict["status"], "problems": problems[:10]}, indent=1))
        return 1 if problems else {"PASS": 0, "PENDING_CLEAN_CANDIDATE": 3}.get(receipt["status"], 1)
    args.out.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "counts": receipt["counts"], "failed_cases": receipt["failed_cases"],
                      "head": receipt["candidate"]["head"], "clean": receipt["candidate"]["clean"], "app_file": receipt["app_file"]}, indent=1))
    return {"PASS": 0, "PENDING_CLEAN_CANDIDATE": 3}.get(receipt["status"], 1)


if __name__ == "__main__":
    sys.exit(main())
