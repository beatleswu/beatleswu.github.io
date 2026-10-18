"""G009 release tooling for Zone4 Owner option B: six-route acceptance, Gate/Product binding, imported-module identity,
post-Build image verification and the BUILD_APP wiring. Every negative must fail closed.

All repositories, apps and docker interactions here are disposable doubles in tmp_path; a double run is never an
acceptance of the real candidate or a real image."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import textwrap
import types

import pytest
from flask import Flask, send_file

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
RELEASE = REPO_ROOT / "scripts" / "release"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SIX = _load("g009_test_six_route", RELEASE / "verify_e10_six_route_contract.py")
BIND = _load("g009_test_binding", RELEASE / "verify_release_candidate_binding.py")
IMG = _load("g009_test_image", RELEASE / "verify_release_image_backpack.py")
FROZEN_REL = "tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py"


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(cwd), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


# =============================================================================================== six-route tool


def _six_root(tmp_path, dockerfile_extra="", drop_copy=None):
    root = tmp_path / "site"
    for url, (rel, *_rest) in SIX.CONTRACT.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / rel, root / rel)
    lines = ["FROM python:3.12-slim", "WORKDIR /app"]
    for url, (rel, *_rest) in SIX.CONTRACT.items():
        if rel != drop_copy:
            lines.append(f"COPY {rel} ./{rel}")
    (root / "Dockerfile").write_text("\n".join(lines) + "\n" + dockerfile_extra, encoding="utf-8")
    return root


def _stub_app(root, *, mime_override=None, body_override=None, extra_rules=(), methods=("GET",)):
    app = Flask("stub_e10")
    for url, (rel, _sha, _size, mime, _auth) in SIX.CONTRACT.items():
        def view(rel=rel, mime=mime, url=url):
            if body_override and url in body_override:
                return app.response_class(body_override[url], mimetype=mime)
            return send_file(root / rel, mimetype=(mime_override or {}).get(url, mime))
        app.add_url_rule(url, endpoint=url, view_func=view, methods=list(methods))
    for rule in extra_rules:
        app.add_url_rule(rule, endpoint="extra" + rule, view_func=lambda **_: "x")
    return app


def _failed(cases):
    return sorted(c["name"] for c in cases if not c["pass"])


def test_six_route_cases_pass_for_an_exact_surface(tmp_path):
    root = _six_root(tmp_path)
    cases = SIX.all_cases(_stub_app(root), root)
    assert _failed(cases) == []
    assert len(cases) >= 54


def test_six_route_wrong_js_mime_fails(tmp_path):
    root = _six_root(tmp_path)
    cases = SIX.all_cases(_stub_app(root, mime_override={"/js/e10/zone4_cinematic_content.js": "application/javascript"}), root)
    assert _failed(cases) == ["get_mime:/js/e10/zone4_cinematic_content.js"]


def test_six_route_wrong_served_bytes_fail(tmp_path):
    root = _six_root(tmp_path)
    cases = SIX.all_cases(_stub_app(root, body_override={"/css/e10/backpack.css": b"/* not the approved stylesheet */"}), root)
    assert "get_body_sha:/css/e10/backpack.css" in _failed(cases)


def test_six_route_tampered_source_fails(tmp_path):
    root = _six_root(tmp_path)
    (root / "css/e10/backpack.css").write_bytes(b"tampered")
    failed = _failed(SIX.all_cases(_stub_app(root), root))
    assert "source_sha:css/e10/backpack.css" in failed and "get_body_sha:/css/e10/backpack.css" in failed


def test_six_route_seventh_route_and_catch_all_fail(tmp_path):
    root = _six_root(tmp_path)
    failed = _failed(SIX.all_cases(_stub_app(root, extra_rules=("/css/e10/Backpack.css", "/js/e10/<path:sub>")), root))
    assert "exact_six_e10_rules" in failed
    assert "no_e10_converter_or_catch_all_rule" in failed
    assert "unknown_404:/css/e10/Backpack.css" in failed


def test_six_route_post_allowed_fails(tmp_path):
    root = _six_root(tmp_path)
    failed = _failed(SIX.all_cases(_stub_app(root, methods=("GET", "POST")), root))
    assert all(f"post_405:{u}" in failed for u in SIX.CONTRACT)


@pytest.mark.parametrize("kind", ["missing-backpack-copy", "wildcard-dir-copy", "duplicate-copy", "wrong-destination"])
def test_six_route_dockerfile_errors_fail(tmp_path, kind):
    if kind == "missing-backpack-copy":
        root, expect = _six_root(tmp_path, drop_copy="css/e10/backpack.css"), "dockerfile_exact_copy:css/e10/backpack.css"
    elif kind == "wildcard-dir-copy":
        root, expect = _six_root(tmp_path, dockerfile_extra="COPY css/e10 ./css/e10\n"), "dockerfile_no_directory_or_wildcard_e10_copy"
    elif kind == "duplicate-copy":
        root, expect = _six_root(tmp_path, dockerfile_extra="COPY css/e10/backpack.css ./css/e10/backpack.css\n"), "dockerfile_exact_copy:css/e10/backpack.css"
    else:
        root = _six_root(tmp_path, drop_copy="css/e10/backpack.css", dockerfile_extra="COPY css/e10/backpack.css ./static/backpack.css\n")
        expect = "dockerfile_exact_copy:css/e10/backpack.css"
    assert expect in _failed(SIX.all_cases(_stub_app(root), root))


def _receipt(tmp_path):
    root = _six_root(tmp_path)
    cases = SIX.all_cases(_stub_app(root), root)
    args = types.SimpleNamespace(require_clean=False, expected_head=None)
    return SIX.build_receipt(root, args, cases, str(root / "app.py"))


def test_receipt_reexecution_identical_has_no_problems(tmp_path):
    receipt = _receipt(tmp_path)
    assert SIX.compare_receipts(copy.deepcopy(receipt), receipt) == []


@pytest.mark.parametrize("forge", [
    lambda r: r["cases"][0].update(observed="forged"),
    lambda r: r["cases"].append(dict(r["cases"][0], name="fabricated_extra_case")),
    lambda r: r["cases"].pop(3),
    lambda r: r["cases"].append(copy.deepcopy(r["cases"][0])),
    lambda r: r.update(tool_sha256="0" * 64),
    lambda r: r["candidate"].update(head="1" * 40),
    lambda r: r["candidate"]["files_sha256"].update({"app.py": "2" * 64}),
    lambda r: r.update(status="PASS", counts={"total": 54, "passed": 54, "failed": 0}),
], ids=["observed", "extra-case", "missing-case", "duplicate-case", "tool-sha", "stale-head", "file-sha", "fabricated-54-pass"])
def test_forged_or_stale_receipt_is_rejected(tmp_path, forge):
    receipt = _receipt(tmp_path)
    forged = copy.deepcopy(receipt)
    forge(forged)
    if forged == receipt:  # the fabricated-54 forge only matters when it changes something
        forged["counts"] = {"total": 54, "passed": 54, "failed": 0}
    assert SIX.compare_receipts(forged, receipt)


def _python(code, cwd):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, cwd=str(cwd), env=env)


def test_six_route_refuses_preimported_app(tmp_path):
    code = textwrap.dedent(f"""
        import sys, types, importlib.util
        sys.modules['app'] = types.ModuleType('app')
        spec = importlib.util.spec_from_file_location('six', r'{RELEASE / "verify_e10_six_route_contract.py"}')
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        try:
            m.import_app_from(__import__('pathlib').Path(r'{tmp_path}'))
        except RuntimeError as e:
            print('REFUSED', e)
    """)
    assert "REFUSED" in _python(code, tmp_path).stdout


def test_six_route_refuses_foreign_app_module(tmp_path):
    root = tmp_path / "candidate"
    root.mkdir()
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "app.py").write_text("app = None\n", encoding="utf-8")
    code = textwrap.dedent(f"""
        import sys, importlib.util
        sys.path.insert(0, r'{other}')
        spec = importlib.util.spec_from_file_location('six', r'{RELEASE / "verify_e10_six_route_contract.py"}')
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        try:
            m.import_app_from(__import__('pathlib').Path(r'{root}'))
            print('ACCEPTED')
        except RuntimeError as e:
            print('REFUSED', e)
    """)
    out = _python(code, tmp_path).stdout
    assert "REFUSED" in out and "ACCEPTED" not in out


# =============================================================================================== Gate/Product binding

RUNTIME_SOURCES = {rel: (REPO_ROOT / rel) for rel in BIND.RUNTIME_FILES}
CONTROL_SOURCES = {rel: (REPO_ROOT / rel) for rel in BIND.CONTROL_PLANE_FILES}


class Repo:
    def __init__(self, tmp_path):
        self.root = tmp_path / "gate"
        self.root.mkdir()
        _git(tmp_path, "init", "-q", str(self.root))
        # mirror the real repository's line-ending contract (* text=auto eol=lf); without it a Windows
        # core.autocrlf=true checkout of the product worktree would rewrite bytes and the binding would reject
        shutil.copyfile(REPO_ROOT / ".gitattributes", self.root / ".gitattributes")
        for rel, src in {**RUNTIME_SOURCES, **CONTROL_SOURCES}.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, self.root / rel)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "product")
        self.product_sha = _git(self.root, "rev-parse", "HEAD")
        (self.root / "tests/deployment/test_new_control_plane.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "gate-only control plane")
        self.gate_sha = _git(self.root, "rev-parse", "HEAD")
        self.product = tmp_path / "product"
        _git(self.root, "worktree", "add", "-q", "--detach", str(self.product), self.product_sha)

    def check(self, tmp_path, **kw):
        out = tmp_path / "binding.json"
        argv = ["check", "--gate-root", str(kw.get("gate_root", self.root)), "--product-root", str(kw.get("product_root", self.product)),
                "--gate-sha", kw.get("gate_sha", self.gate_sha), "--product-sha", kw.get("product_sha", self.product_sha),
                "--expected-common-dir", str(kw.get("expected_common_dir", self.root / ".git")), "--out", str(out)]
        rc = BIND.main(argv)
        return rc, json.loads(out.read_text(encoding="utf-8"))


def test_binding_bound_for_clean_separated_candidate(tmp_path):
    repo = Repo(tmp_path)
    rc, report = repo.check(tmp_path)
    assert rc == 0 and report["status"] == "BOUND", report["problems"]
    assert report["relation"]["changed_paths"] == ["tests/deployment/test_new_control_plane.py"]


def test_binding_rejects_wrong_gate_sha(tmp_path):
    repo = Repo(tmp_path)
    assert repo.check(tmp_path, gate_sha=repo.product_sha)[0] == 1


def test_binding_rejects_short_sha(tmp_path):
    repo = Repo(tmp_path)
    assert repo.check(tmp_path, product_sha=repo.product_sha[:9])[0] == 1


def test_binding_rejects_dirty_gate_untracked(tmp_path):
    repo = Repo(tmp_path)
    (repo.root / "stray.txt").write_text("x", encoding="utf-8")
    rc, report = repo.check(tmp_path)
    assert rc == 1 and any("gate: worktree is not clean" in p for p in report["problems"])


def test_binding_rejects_dirty_product(tmp_path):
    repo = Repo(tmp_path)
    (repo.product / "app.py").write_bytes((repo.product / "app.py").read_bytes() + b"\n# drift\n")
    rc, report = repo.check(tmp_path)
    assert rc == 1 and any("product: worktree is not clean" in p for p in report["problems"])


def test_binding_rejects_product_runtime_change_in_gate(tmp_path):
    repo = Repo(tmp_path)
    (repo.root / "app.py").write_bytes((repo.root / "app.py").read_bytes() + b"\n# gate-side product change\n")
    _git(repo.root, "commit", "-q", "-am", "product drift in gate")
    rc, report = repo.check(tmp_path, gate_sha=_git(repo.root, "rev-parse", "HEAD"))
    assert rc == 1 and any(p.startswith("UNAPPROVED_PRODUCT_DIFF_DETECTED") for p in report["problems"])


def test_binding_rejects_product_not_ancestor(tmp_path):
    repo = Repo(tmp_path)
    _git(repo.root, "checkout", "-q", "--orphan", "other")
    _git(repo.root, "commit", "-q", "-m", "unrelated")
    unrelated = _git(repo.root, "rev-parse", "HEAD")
    _git(repo.root, "checkout", "-q", repo.gate_sha)
    rc, report = repo.check(tmp_path, product_sha=unrelated)
    assert rc == 1


def test_binding_rejects_changed_frozen_bytes_in_gate(tmp_path):
    repo = Repo(tmp_path)
    frozen = repo.root / FROZEN_REL
    frozen.write_bytes(frozen.read_bytes() + b"\n# rewritten\n")
    _git(repo.root, "commit", "-q", "-am", "rewrite frozen (control-plane path)")
    rc, report = repo.check(tmp_path, gate_sha=_git(repo.root, "rev-parse", "HEAD"))
    assert rc == 1 and any("Frozen Zone4 test bytes" in p for p in report["problems"])


def test_binding_rejects_missing_root(tmp_path):
    repo = Repo(tmp_path)
    assert repo.check(tmp_path, product_root=tmp_path / "does-not-exist")[0] == 1


def _identity(tmp_path, repo, **overrides):
    record = {
        "schema": "g009-release-identity-record-v1", "nonce": "nonce-1", "rootdir": str(repo.root), "cwd": str(repo.root), "exitstatus": 1,
        "python": {"executable": sys.executable, "version": "3", "dont_write_bytecode": True, "pycache_prefix": str(tmp_path / "pycache")},
        "modules": {"app": {"file": str(repo.root / "app.py"), "sha256": _sha((repo.root / "app.py").read_bytes())},
                    "test_p0_zone4_cinematic_content_route_corrective": {"file": str(repo.root / FROZEN_REL), "sha256": BIND.FROZEN_SHA}},
    }
    for key, value in overrides.items():
        if callable(value):
            value(record)
        else:
            record[key] = value
    path = tmp_path / "identity.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    out = tmp_path / "identity-report.json"
    rc = BIND.main(["identity", "--record", str(path), "--nonce", "nonce-1", "--gate-root", str(repo.root),
                    "--product-root", str(repo.product), "--out", str(out)])
    return rc, json.loads(out.read_text(encoding="utf-8"))


def test_identity_fabricated_modules_and_fresh_nonce_cannot_self_attest(tmp_path):
    repo = Repo(tmp_path)
    rc, report = _identity(tmp_path, repo)
    assert rc == 1, report
    assert any("EXTERNAL_RUNNER_ATTESTATION_REQUIRED" in p for p in report["problems"])


@pytest.mark.parametrize("override", [
    {"nonce": "stale-nonce"},
    {"rootdir": "C:/elsewhere"},
    {"modules": {}},
    "foreign-app",
    "app-bytes",
    "frozen-bytes",
    "no-pycache-prefix",
    "pycache-inside-gate",
], ids=lambda o: o if isinstance(o, str) else next(iter(o)))
def test_identity_rejects(tmp_path, override):
    repo = Repo(tmp_path)
    mutations = {
        "foreign-app": lambda r: r["modules"]["app"].update(file=str(tmp_path / "elsewhere" / "app.py")),
        "app-bytes": lambda r: r["modules"]["app"].update(sha256="0" * 64),
        "frozen-bytes": lambda r: r["modules"]["test_p0_zone4_cinematic_content_route_corrective"].update(sha256="0" * 64),
        "no-pycache-prefix": lambda r: r["python"].update(pycache_prefix=None),
        "pycache-inside-gate": lambda r: r["python"].update(pycache_prefix=str(repo.root / "__pycache__")),
    }
    kwargs = {"mutate": mutations[override]} if isinstance(override, str) else override
    rc, report = _identity(tmp_path, repo, **kwargs)
    assert rc == 1 and report["status"] == "REJECTED"


def test_identity_plugin_records_modules_and_nonce(tmp_path):
    proj = tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    # A worktree-local basetemp must not inherit the real repository's
    # collection boundary or import its app instead of this disposable app.
    (proj / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (proj / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (proj / "tests" / "test_p0_zone4_cinematic_content_route_corrective.py").write_text("import app\n\ndef test_a():\n    assert app.VALUE == 1\n", encoding="utf-8")
    record = tmp_path / "record.json"
    env = dict(os.environ, PYTHONPATH=str(RELEASE), G009_RELEASE_IDENTITY_RECORD=str(record), G009_RELEASE_IDENTITY_NONCE="n-42",
               PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(tmp_path / "pyc"))
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "g009_release_identity_plugin", "-p", "no:cacheprovider",
                        "--junitxml", str(tmp_path / "plugin-junit.xml"), "tests"],
                       cwd=str(proj), env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    data = json.loads(record.read_text(encoding="utf-8"))
    assert data["nonce"] == "n-42"
    assert pathlib.Path(data["modules"]["app"]["file"]) == (proj / "app.py").resolve()
    assert data["python"]["pycache_prefix"]
    assert data["evidence_trust"] == "CANDIDATE_CONTROLLED_DIAGNOSTIC_ONLY"
    assert data["junit_sha256"] == _sha((tmp_path / "plugin-junit.xml").read_bytes())
    assert data["collection"][0]["nodeid"].endswith("::test_a")
    assert any(r["when"] == "call" and r["outcome"] == "passed" for r in data["reports"])


@pytest.mark.parametrize("operation", ["status", "diff", "rev-parse", "cat-file", "merge-base"])
def test_binding_git_errors_cannot_look_clean(tmp_path, monkeypatch, operation):
    repo = Repo(tmp_path)
    original = BIND.git

    def failed(root, *argv, **kw):
        if argv[0] == operation:
            return 128, b"" if kw.get("binary") else ""
        return original(root, *argv, **kw)

    monkeypatch.setattr(BIND, "git", failed)
    rc, report = repo.check(tmp_path)
    assert rc == 1 and report["problems"], report


def test_binding_alternate_repository_is_rejected_even_with_matching_candidates(tmp_path):
    repo = Repo(tmp_path)
    rc, report = repo.check(tmp_path, expected_common_dir=tmp_path / "trusted-repo" / ".git")
    assert rc == 1
    assert any("trusted parent identity" in p for p in report["problems"])


def test_binding_requires_repository_authority_from_parent(tmp_path):
    repo = Repo(tmp_path)
    args = types.SimpleNamespace(gate_root=repo.root, product_root=repo.product,
                                 gate_sha=repo.gate_sha, product_sha=repo.product_sha)
    assert any("trusted parent expected Git common directory" in p for p in BIND.cmd_check(args)["problems"])


@pytest.mark.parametrize("relative", [".", ".git", "gate/.git", "../gate/.git"])
def test_binding_rejects_relative_authority_even_when_it_resolves_to_repository(tmp_path, monkeypatch, relative):
    repo = Repo(tmp_path)
    # Include a formerly passing relative path: cwd gate + .git points exactly
    # at the real common directory. It still is not absolute external authority.
    monkeypatch.chdir(repo.root if relative in {".", ".git"} else tmp_path)
    rc, report = repo.check(tmp_path, expected_common_dir=relative)
    assert rc == 1 and report["status"] == "REJECTED"
    assert "trusted parent expected Git common directory must be absolute" in report["problems"]


@pytest.mark.parametrize("relative", [".", "repo/.git", "../repo/.git", "C:repo/.git", r"\repo\.git"])
def test_binding_relative_authority_is_rejected_before_path_resolution(relative, monkeypatch):
    def forbidden_resolution(*_args, **_kwargs):
        raise AssertionError("relative authority must not be resolved")

    monkeypatch.setattr(pathlib.Path, "resolve", forbidden_resolution)
    problems = []
    BIND.bind_repository({}, {}, pathlib.Path(relative), problems)
    assert problems == ["trusted parent expected Git common directory must be absolute"]


def test_identity_null_app_digest_and_absent_files_are_rejected(tmp_path):
    repo = Repo(tmp_path)
    (repo.root / "app.py").unlink()
    (repo.product / "app.py").unlink()
    # Avoid the fixture's own attempt to read the absent file.
    record = {"schema": "g009-release-identity-record-v1", "nonce": "fresh", "rootdir": str(repo.root),
              "modules": {"app": {"file": str(repo.root / "app.py"), "sha256": None}}, "python": {}}
    path = tmp_path / "null-record.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    args = types.SimpleNamespace(gate_root=repo.root, product_root=repo.product, record=path, nonce="fresh")
    report = BIND.cmd_identity(args)
    assert any("imported app bytes differ" in p for p in report["problems"])


def test_identity_rehashes_frozen_source_even_if_record_claims_pinned_bytes(tmp_path):
    repo = Repo(tmp_path)
    (repo.root / FROZEN_REL).write_text("# replaced after run\n", encoding="utf-8")
    rc, report = _identity(tmp_path, repo)
    assert rc == 1
    assert any("executed Frozen Zone4 module bytes differ" in p for p in report["problems"])


@pytest.mark.parametrize("operation", ["status", "tree"])
def test_six_route_git_error_never_means_clean(tmp_path, monkeypatch, operation):
    def failed(root, *argv):
        fail = argv[0] == "status" if operation == "status" else argv == ("rev-parse", "HEAD^{tree}")
        return (128, "") if fail else (0, "a" * 40)

    monkeypatch.setattr(SIX, "_git", failed)
    identity = SIX.candidate_identity(tmp_path)
    assert identity["git_ok"] is False and identity["clean"] is False


@pytest.mark.parametrize("path", [
    "scripts/release/x.py", "./scripts/release/x.py", "Scripts/Release/x.py", "tests/deployment/a.py", "tests/release/a.py",
    "docs/deployment/a.md", "scripts/build-production-image.ps1", "SCRIPTS/BUILD-PRODUCTION-IMAGE.PS1",
    "tools/questions_corpus_validation.py", "tests/test_questions_corpus_validation.py",
    "app.py", "deploy/runtime-source-provenance.json", "deploy/build-app-known-failure-baseline.json", "Dockerfile",
    "tools/other.py", "scripts/other.ps1", "tests/test_other.py", ".scripts/release/x.py", "/scripts/release/x.py",
])
def test_control_plane_rule_matches_powershell(path):
    psm1 = RELEASE / "ReleaseTooling.psm1"
    if shutil.which("powershell") is None:
        pytest.skip("powershell not available: parity NOT_EXECUTED")
    # Test-ReleaseControlPlanePath is module-private: invoke it inside the module's own scope
    cmd = (f"$m = Import-Module '{psm1}' -Force -DisableNameChecking -PassThru; "
           f"if (& $m {{ param($p) Test-ReleaseControlPlanePath -Path $p }} '{path}') {{ 'True' }} else {{ 'False' }}")
    p = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert (p.stdout.strip().splitlines()[-1] == "True") == BIND.is_control_plane(path)


# =============================================================================================== image verifier

IMAGE_ID = "sha256:" + "a" * 64
BACKPACK = (REPO_ROOT / "css/e10/backpack.css").read_bytes()


def _tar(name, data, *, extra=None, symlink=False):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name)
        if symlink:
            info.type = tarfile.SYMTYPE
            info.linkname = "/tmp/other"
            tar.addfile(info)
        else:
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        if extra:
            e = tarfile.TarInfo(extra)
            e.size = 1
            tar.addfile(e, io.BytesIO(b"x"))
    return buf.getvalue()


class FakeDocker:
    def __init__(self, **faults):
        self.faults = faults
        self.calls = []
        self.removed = []
        self.containers = {}

    def run(self, args, timeout=120):
        self.calls.append(args)
        f = self.faults
        if args[:2] == ["container", "ls"]:
            if f.get("list_fail"):
                return 1, b"", b"daemon unavailable"
            name = args[args.index("--filter") + 1][7:-1]
            if f.get("existing_name"):
                return 0, ("e" * 64).encode(), b""
            ids = [cid for cid, info in self.containers.items() if info["Name"] == "/" + name]
            return 0, "\n".join(ids).encode(), b""
        if args[0] == "inspect":
            ref = args[-1]
            for cid, cinfo in self.containers.items():
                if ref in (cid, cinfo["Name"][1:]):
                    return 0, json.dumps(cinfo).encode(), b""
            if ref.startswith("g009-imgverify"):
                info = {"Image": f.get("container_image", IMAGE_ID), "Mounts": f.get("mounts", []), "HostConfig": {"Binds": f.get("binds")}}
                return 0, json.dumps(info).encode(), b""
            if f.get("inspect_fail"):
                return 1, b"", b"No such image"
            image = {"Id": f.get("image_id", IMAGE_ID), "RepoDigests": f.get("digests", ["repo@sha256:" + "d" * 64]),
                     "Config": {"Labels": {"org.opencontainers.image.revision": f.get("revision", "f" * 40)}}}
            return 0, json.dumps(image).encode(), b""
        if args[0] == "create":
            self._create(args)
            if f.get("create_timeout"):
                raise subprocess.TimeoutExpired("docker create", timeout)
            return (1, b"", b"create failed") if f.get("create_fail") else (0, b"cid", b"")
        if args[0] == "cp":
            if f.get("cp_fail"):
                return 1, b"", b"Could not find the file"
            return 0, f.get("tar", _tar("backpack.css", BACKPACK)), b""
        if args[0] == "run":
            self._create(args)
            if f.get("run_timeout"):
                raise subprocess.TimeoutExpired("docker run", timeout)
            return (125, b"", b"cannot start") if f.get("run_fail") else (0, b"cid2", b"")
        if args[0] == "port":
            return 0, f.get("port", "127.0.0.1:49153").encode(), b""
        if args[0] == "rm":
            self.removed.append(self.containers.pop(args[-1])["Name"][1:])
            return 0, b"", b""
        raise AssertionError(args)

    def _create(self, args):
        operation = args[0]
        if self.faults.get(operation + "_fail") and not self.faults.get("partial"):
            return
        name = args[args.index("--name") + 1]
        token = args[args.index("--label") + 1].split("=", 1)[1]
        cid = ("1" if operation == "create" else "2") * 64
        self.containers[cid] = {
            "Id": cid, "Name": "/" + name, "Image": self.faults.get("container_image", IMAGE_ID),
            "Mounts": self.faults.get("mounts", []), "HostConfig": {"Binds": self.faults.get("binds")},
            "Config": {"Labels": {"g009.verifier.owner": "other" if self.faults.get("wrong_owner") else token}},
        }


def _http(status=200, ctype="text/css; charset=utf-8", body=BACKPACK, head=None):
    def fake(url, method="GET", timeout=10):
        if method == "HEAD":
            return head or (status, {"Content-Type": ctype}, b"")
        return status, {"Content-Type": ctype}, body
    return fake


def _verify(docker, http=None, **argover):
    argv = ["--image", "go-odyssey-app:test", "--expected-image-id", IMAGE_ID, "--out", "unused.json",
            "--expected-repo-digest", "repo@sha256:" + "d" * 64, "--expected-revision", "f" * 40, "--ready-timeout", "0"]
    args = IMG.parser().parse_args(argv)
    for k, v in argover.items():
        setattr(args, k, v)
    return IMG.verify(args, docker=docker, http=http or _http(), sleep=lambda _s: None)


def test_image_verifier_accepts_only_the_exact_image_file_and_route():
    docker = FakeDocker()
    result = _verify(docker)
    assert result["status"] == "IMAGE_BACKPACK_VERIFIED", result
    assert len(docker.removed) == 2
    assert all("-v" not in c and "--volume" not in c and "--mount" not in c for c in docker.calls)


@pytest.mark.parametrize("faults,http,argover", [
    ({"image_id": "sha256:" + "b" * 64}, None, {}),
    ({"digests": ["repo@sha256:" + "e" * 64]}, None, {}),
    ({"revision": "0" * 40}, None, {}),
    ({"inspect_fail": True}, None, {}),
    ({"create_fail": True}, None, {}),
    ({"container_image": "sha256:" + "c" * 64}, None, {}),
    ({"mounts": [{"Type": "bind", "Source": "C:/host/backpack.css", "Destination": "/app/css/e10/backpack.css"}]}, None, {}),
    ({"mounts": [{"Type": "volume", "Destination": "/app/css"}]}, None, {}),
    ({"binds": ["C:/host:/app"]}, None, {}),
    ({"cp_fail": True}, None, {}),
    ({"tar": _tar("backpack.css", b"forged bytes")}, None, {}),
    ({"tar": _tar("backpack.css", BACKPACK, extra="other.css")}, None, {}),
    ({"tar": _tar("backpack.css", b"", symlink=True)}, None, {}),
    ({"run_fail": True}, None, {}),
    ({"port": "0.0.0.0:49153"}, None, {}),
    ({}, _http(status=404), {}),
    ({}, _http(ctype="text/plain"), {}),
    ({}, _http(body=b"other"), {}),
    ({}, _http(head=(200, {"Content-Type": "text/css"}, b"body-on-head")), {}),
    ({}, None, {"expected_image_id": "latest"}),
], ids=["image-id", "digest", "revision", "inspect-fail", "create-fail", "container-image", "bind-mount", "covering-volume", "binds",
        "file-absent", "wrong-bytes", "extra-member", "symlink", "start-fail", "non-loopback", "http-404", "mime", "body-sha", "head-body", "malformed-id"])
def test_image_verifier_rejects(faults, http, argover):
    docker = FakeDocker(**faults)
    result = _verify(docker, http=http, **argover)
    assert result["status"] == "REJECT_DEPLOY", result
    assert result["reason"]
    # every container that was actually created is removed, also on the failure path
    started = {c[c.index("--name") + 1] for c in docker.calls if c[0] in ("create", "run")
               and not (c[0] == "create" and faults.get("create_fail")) and not (c[0] == "run" and faults.get("run_fail"))}
    if faults.get("container_image"):
        assert not docker.removed  # mismatched identity is never ours to delete
        assert result["cleanup_errors"]
    else:
        assert started == set(docker.removed)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_image_redirect_is_immediate_rejection_for_both_methods(status, method):
    calls = []

    def redirect(url, requested="GET", timeout=10):
        calls.append((url, requested))
        if requested == method:
            return status, {"Location": "http://off-loopback.invalid/decoy", "Content-Type": "text/css"}, b""
        return _http()(url, requested)

    docker = FakeDocker()
    result = _verify(docker, http=redirect, ready_timeout=60)
    assert result["status"] == "REJECT_DEPLOY"
    assert f"HTTP {method} redirect {status}" in result["reason"]
    assert sum(m == method for _, m in calls) == 1
    assert len(docker.removed) == 2


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_real_urllib_redirect_handler_never_opens_location(monkeypatch, status, method):
    # Real urllib processing with an in-memory HTTP transport: no socket,
    # Docker image, network permission or live acceptance is involved.
    import email.message
    import urllib.response

    requested = []
    original_builder = IMG.urllib.request.build_opener

    class Transport(IMG.urllib.request.HTTPHandler):
        def http_open(self, req):
            requested.append(req.full_url)
            headers = email.message.Message()
            headers["Location"] = "http://off-loopback.invalid/decoy"
            response = urllib.response.addinfourl(io.BytesIO(b""), headers, req.full_url, status)
            response.msg = "Redirect"
            return response

    def opener(*handlers):
        assert any(isinstance(h, IMG.urllib.request.ProxyHandler) and h.proxies == {} for h in handlers)
        return original_builder(*handlers, Transport())

    monkeypatch.setenv("HTTP_PROXY", "http://off-loopback.invalid:8080")
    monkeypatch.setattr(IMG.urllib.request, "build_opener", opener)
    url = "http://127.0.0.1:49153/css/e10/backpack.css"
    with pytest.raises(IMG.Rejected, match="redirect"):
        IMG.http_request(url, method)
    assert requested == [url]


@pytest.mark.parametrize("url", [
    "http://example.com:1234/css/e10/backpack.css", "http://localhost:1234/css/e10/backpack.css",
    "http://127.0.0.1.evil:1234/css/e10/backpack.css", "http://127.0.0.1:1234/decoy.css",
    "http://user@127.0.0.1:1234/css/e10/backpack.css", "https://127.0.0.1:1234/css/e10/backpack.css",
    "http://127.0.0.1:1234/css/e10/backpack.css?decoy=1",
])
def test_http_rejects_foreign_host_or_route_before_open(url):
    with pytest.raises(IMG.Rejected):
        IMG.http_request(url)


@pytest.mark.parametrize("mapping", [
    "127.0.0.1:49153\n0.0.0.0:49153", "127.0.0.1:49153@evil", "127.0.0.1:99999", "127.0.0.1:0",
])
def test_image_rejects_ambiguous_or_invalid_loopback_mapping(mapping):
    result = _verify(FakeDocker(port=mapping))
    assert result["status"] == "REJECT_DEPLOY" and "loopback_port_mapping" in result["reason"]


@pytest.mark.parametrize("override", [
    {"route": "/decoy.css"}, {"asset_path": "/app/decoy.css"}, {"expected_sha": "0" * 64}, {"expected_size": 0},
])
def test_image_cannot_redefine_original_asset(override):
    docker = FakeDocker()
    result = _verify(docker, **override)
    assert result["status"] == "REJECT_DEPLOY" and not docker.calls


def test_cleanup_failure_rejects_without_claiming_containers_removed():
    class FailedCleanup(FakeDocker):
        def run(self, argv, timeout=120):
            if argv[0] == "rm":
                return 1, b"", b"cleanup failed"
            return super().run(argv, timeout)

    result = _verify(FailedCleanup())
    assert result["status"] == "REJECT_DEPLOY" and result["cleanup_errors"]
    assert result["containers_removed"] == []


@pytest.mark.parametrize("operation", ["create", "run"])
@pytest.mark.parametrize("failure", ["fail", "timeout"])
def test_partial_docker_creation_is_cleaned_by_proven_id(operation, failure):
    docker = FakeDocker(**{operation + "_" + failure: True, "partial": True})
    result = _verify(docker)
    assert result["status"] == "REJECT_DEPLOY"
    assert not docker.containers
    assert len(docker.removed) == (1 if operation == "create" else 2)
    assert not result["cleanup_errors"]
    for call in docker.calls:
        if call[0] == "rm":
            assert call == ["rm", "-f", call[-1]]
            assert len(call[-1]) == 64 and call[-1] in {"1" * 64, "2" * 64}


@pytest.mark.parametrize("fault", ["existing_name", "list_fail"])
def test_unproven_absence_never_creates_or_cleans_container(fault):
    docker = FakeDocker(**{fault: True})
    result = _verify(docker)
    assert result["status"] == "REJECT_DEPLOY"
    assert not any(c[0] in {"create", "run", "rm"} for c in docker.calls)
    assert result["containers_removed"] == []


def test_partial_creation_with_unknown_owner_never_removes_it():
    docker = FakeDocker(create_fail=True, partial=True, wrong_owner=True)
    result = _verify(docker)
    assert result["status"] == "REJECT_DEPLOY"
    assert result["cleanup_errors"] and not docker.removed
    assert not any(c[0] == "rm" for c in docker.calls)


class DelayedDocker(FakeDocker):
    """Daemon creation completes only after the timed-out CLI has exited."""

    def __init__(self, operation, *, appear_after=2, cleanup_fault=None):
        super().__init__()
        self.operation = operation
        self.appear_after = appear_after
        self.cleanup_fault = cleanup_fault
        self.pending = None
        self.absence_checks = 0
        self.cleanup_timeouts = []

    def run(self, argv, timeout=120):
        if argv[0] == self.operation:
            self.calls.append(argv)
            self._create(argv)
            cid = ("1" if self.operation == "create" else "2") * 64
            self.pending = (cid, self.containers.pop(cid))
            raise subprocess.TimeoutExpired("docker " + self.operation, timeout)
        if self.pending is not None:
            self.cleanup_timeouts.append(timeout)
            cid, info = self.pending
            if (argv[:2] == ["container", "ls"]
                    and argv[argv.index("--filter") + 1][7:-1] == info["Name"][1:]):
                self.absence_checks += 1
                if self.cleanup_fault == "list-timeout":
                    self.calls.append(argv)
                    raise subprocess.TimeoutExpired("docker container ls", timeout)
                if self.absence_checks >= self.appear_after:
                    self.containers[cid] = copy.deepcopy(info)
                    if self.cleanup_fault == "multiple-ids":
                        self.calls.append(argv)
                        return 0, (cid + "\n" + "e" * 64).encode(), b""
                    # Return the listed ID before corrupting inspect metadata,
                    # so each ownership check is reached independently.
                    if self.cleanup_fault in {"missing-owner", "name-mismatch", "id-mismatch", "wrong-image"}:
                        current = self.containers[cid]
                        if self.cleanup_fault == "missing-owner":
                            current["Config"]["Labels"] = {}
                        elif self.cleanup_fault == "name-mismatch":
                            current["Name"] = "/unrelated-container"
                        elif self.cleanup_fault == "id-mismatch":
                            current["Id"] = "e" * 64
                        else:
                            current["Image"] = "sha256:" + "e" * 64
                        self.calls.append(argv)
                        return 0, cid.encode(), b""
            if ((argv[0] == "inspect" and argv[-1] == cid and self.cleanup_fault == "inspect-timeout")
                    or (argv[0] == "rm" and self.cleanup_fault == "remove-timeout")):
                self.calls.append(argv)
                raise subprocess.TimeoutExpired("docker " + argv[0], timeout)
        return super().run(argv, timeout)


@pytest.mark.parametrize("operation", ["create", "run"])
def test_delayed_creation_after_timeout_is_polled_then_cleaned_by_proven_id(operation):
    docker = DelayedDocker(operation)
    result = _verify(docker)
    assert result["status"] == "REJECT_DEPLOY"  # cleanup cannot erase timeout
    assert "TimeoutExpired" in result["reason"]
    assert docker.absence_checks == 2
    assert len(docker.removed) == (1 if operation == "create" else 2)
    assert not docker.containers and not result["cleanup_errors"]
    assert all(0 < timeout <= IMG.CLEANUP_COMMAND_TIMEOUT for timeout in docker.cleanup_timeouts)
    assert all(c == ["rm", "-f", c[-1]] and len(c[-1]) == 64 for c in docker.calls if c[0] == "rm")


@pytest.mark.parametrize("operation", ["create", "run"])
def test_unresolved_late_creation_requires_manual_followup(operation):
    docker = DelayedDocker(operation, appear_after=IMG.CLEANUP_ABSENCE_CHECKS + 1)
    result = _verify(docker)
    assert result["status"] == "REJECT_DEPLOY"
    assert docker.absence_checks == IMG.CLEANUP_ABSENCE_CHECKS
    assert any("unresolved late container creation" in error and "manual follow-up required" in error
               for error in result["cleanup_errors"])
    assert len(docker.removed) == (0 if operation == "create" else 1)
    assert docker.pending[1]["Name"][1:] not in result["containers_removed"]


@pytest.mark.parametrize("fault", [
    "multiple-ids", "missing-owner", "name-mismatch", "id-mismatch", "wrong-image",
    "list-timeout", "inspect-timeout", "remove-timeout",
])
def test_delayed_cleanup_unproven_identity_or_timeout_is_explicit_failure(fault):
    docker = DelayedDocker("create", cleanup_fault=fault)
    result = _verify(docker)
    assert result["status"] == "REJECT_DEPLOY"
    assert result["cleanup_errors"] and "manual follow-up required" in result["cleanup_errors"][0]
    assert not docker.removed and result["containers_removed"] == []
    if fault != "remove-timeout":
        assert not any(c[0] == "rm" for c in docker.calls)
    assert all(0 < timeout <= IMG.CLEANUP_COMMAND_TIMEOUT for timeout in docker.cleanup_timeouts)


def test_cleanup_deadline_stops_checks_and_records_manual_followup(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(IMG.time, "monotonic", lambda: clock[0])

    class DeadlineDocker(DelayedDocker):
        def run(self, argv, timeout=120):
            result = super().run(argv, timeout)
            if self.pending is not None and argv[:2] == ["container", "ls"]:
                clock[0] += IMG.CLEANUP_TIMEOUT + 1
            return result

    docker = DeadlineDocker("create", appear_after=99)
    result = _verify(docker)
    assert result["status"] == "REJECT_DEPLOY"
    assert docker.absence_checks == 1 and not docker.removed
    assert any("cleanup deadline exceeded" in error and "manual follow-up required" in error
               for error in result["cleanup_errors"])


def test_build_governance_authority_is_external_and_unavailable_attestor_blocks():
    content = (RELEASE / "build-release-image.ps1").read_text(encoding="utf-8")
    assert "$expectedGitCommonDirectory = Get-GitCommonDirectory" not in content
    assert "else { Get-CurrentGitSha }" not in content
    for param in ("GovernanceExpectedGitCommonDirectory", "GovernanceGateSourceSha", "GovernanceProductSourceSha"):
        assert "[string]$" + param in content
    assert "$expectedGitCommonDirectory = $GovernanceExpectedGitCommonDirectory" in content
    assert "-cne $GovernanceGateSourceSha" in content
    assert "-cne $GovernanceProductSourceSha" in content
    # No candidate-supplied root, fake signer, or receipt can reach build setup.
    assert content.index("Fail 'EXTERNAL_GOVERNANCE_AUTHORITY_REQUIRED") < content.index("$gateWorktree = Get-RepoRoot")
    assert content.index("Fail 'EXTERNAL_GOVERNANCE_ATTESTATION_REQUIRED") < content.index("$gateWorktree = Get-RepoRoot")


# =============================================================================================== BUILD_APP wiring


def test_build_script_wires_binding_identity_six_route_and_policy():
    content = (RELEASE / "build-release-image.ps1").read_text(encoding="utf-8")
    for needle in (
        "verify_release_candidate_binding.py", "verify_e10_six_route_contract.py", "zone4_owner_b_contract_conflict_policy.json",
        "--owner-conflict-policy $ownerConflictPolicyPath", "-p g009_release_identity_plugin", "$env:PYTHONPYCACHEPREFIX",
        "--root $productWorktree", "--require-clean", "--expected-head $productSha", "identity `",
        "BUILD_APP Gate/Product candidate binding failed closed", "BUILD_APP exact six-route E10 contract failed closed",
        "BUILD_APP imported-module identity failed closed", "BUILD_APP deployment test gate failed closed",
    ):
        assert needle in content, needle
    # ordering: binding and six-route before the suite, identity and evaluator after it
    order = [content.index(n) for n in ("candidateBindingToolPath check", "$sixRouteToolPath `", "-m pytest -q tests/deployment/",
                                         "candidateBindingToolPath identity", "--owner-conflict-policy $ownerConflictPolicyPath")]
    assert order == sorted(order)
    for name in ("'PYTHONPYCACHEPREFIX'", "'PYTHONPATH'", "'G009_RELEASE_IDENTITY_RECORD'", "'G009_RELEASE_IDENTITY_NONCE'"):
        assert name in content  # restored by the existing finally block


def test_build_script_dry_run_contract_is_unchanged():
    content = (RELEASE / "build-release-image.ps1").read_text(encoding="utf-8")
    start = content.index("if ($DryRun) {")
    block = content[start:content.index("return", start)]
    assert "owner" not in block.lower() and "six" not in block.lower()
