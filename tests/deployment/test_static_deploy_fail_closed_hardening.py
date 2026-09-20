"""A017: static-deploy fail-closed hardening -- behavioural proof.

Three gaps observed during the successful A016 static-only promotion, plus the
layout rule the A011 incident proved necessary:

  GAP_1  the uploaded archive's SHA-256 was never checked ON THE REMOTE HOST
         before extraction (extract -> delete staging tar -> verify files);
  GAP_2  the live-symlink target captured near the start (the rollback
         authority) was never re-read/compared immediately before the switch, so
         an external watcher had to compensate;
  GAP_3  the deployment record printed ``public_sw_version_after_switch: null``
         although the service-worker verification passed (function-scoped
         variable);
  P0     a Production -Execute run must never fall back to the example layout.

These tests execute the REAL ``deploy-static-release.ps1`` end to end against a
protocol-level fixture of the remote host (``tests/fixtures/fake_remote``) and a
local HTTP origin -- no real host, no network -- and assert both what happened
and, as important, what did NOT happen (no extraction, no symlink write, no
restart) from the fixture's own command log.
"""

from __future__ import annotations

import hashlib
import http.server
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

import pytest

from process_runner import run_bounded

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "release" / "deploy-static-release.ps1"
MODULE = REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
FAKE_DIR = REPO_ROOT / "tests" / "fixtures" / "fake_remote"
PRODUCTION_LAYOUT = "deploy\\release-layout.production.json"
EXAMPLE_LAYOUT = "deploy\\release-layout.example.json"

REMOTE_ROOT = "/srv/fixture-static"
OLD_GEN = "20260101-000000-aaaaaaaa-fixture-old"
NEW_GEN = "20260102-000000-bbbbbbbb-fixture-new"
OTHER_GEN = "20260103-000000-cccccccc-fixture-other"
OLD_TARGET = f"{REMOTE_ROOT}/releases/{OLD_GEN}"
NEW_TARGET = f"{REMOTE_ROOT}/releases/{NEW_GEN}"
OTHER_TARGET = f"{REMOTE_ROOT}/releases/{OTHER_GEN}"
SW_VERSION = "v-fixture-1"

CONCURRENT = "STATIC_RELEASE_CONCURRENT_MUTATION_DETECTED"
SHA_MISMATCH = "STATIC_RELEASE_REMOTE_ARCHIVE_SHA_MISMATCH"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def _require_windows_powershell() -> None:
    if shutil.which("powershell") is None:
        pytest.skip("powershell not available in this environment")


def _powershell(body: str, *, timeout: int = 120) -> subprocess.CompletedProcess:
    _require_windows_powershell()
    script = (
        "$ErrorActionPreference='Stop'\n"
        f"Import-Module '{MODULE}' -Force -DisableNameChecking\n" + body
    )
    return run_bounded(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Static structure: the gates exist, are wired in the right order, and the
# guarantees the existing suites rely on are untouched.
# ---------------------------------------------------------------------------

def test_remote_archive_sha_gate_sits_between_upload_and_extraction_and_extracted_file_check_survives():
    text = _source()
    upload = text.index("Invoke-BoundedFileUpload -LocalPath $archivePath")
    gate = text.index("Assert-RemoteArchiveShaMatch -ExpectedSha256 $actualArchiveHash")
    extract = text.index("tar -xf")
    file_check = text.index("Batch SHA-256 verification failed")
    assert upload < gate < extract < file_check, (
        "order must be upload -> remote archive SHA gate -> extract -> extracted-file verification"
    )
    # the gate compares the REMOTE-computed hash with the LOCAL authorized one
    assert "sha256sum $(Quote-PosixShellArgument $remoteArchivePath)" in text
    # the second, independent layer is still the batched per-file verification
    assert text.count("New-RemoteBatchShaVerificationScript -RemoteReleaseDir") == 1


def test_pre_switch_recheck_and_atomic_guard_precede_the_symlink_write():
    text = _source()
    manifest_recount = text.index("Final remote file count mismatch after manifest upload")
    recheck = text.index("Start-StaticDeployPhase -Phase 'RECHECK_LIVE_SYMLINK'")
    compare = text.index("Assert-StaticCurrentTargetUnchanged -ExpectedGeneration $previousCurrentTarget")
    switch_phase = text.index("Start-StaticDeployPhase -Phase 'SWITCH_CURRENT'")
    write = text.index("sudo ln -sfnT $quotedRelease current.next")
    restart = text.index("'docker restart app+scheduler'")
    assert manifest_recount < recheck < compare < switch_phase < write < restart
    # layer 2: the write is guarded inside the SAME remote shell, by the captured target
    assert "if [ x`$(readlink -f current 2>/dev/null) = x$quotedPreviousCurrent ]" in text
    assert "exit 73" in text
    # the recorded rollback authority is exactly what the guard compares against
    assert "$previousCurrentTarget = Get-RemoteCurrentTarget" in text


def test_layout_gate_runs_before_any_remote_call_or_archive_work():
    text = _source()
    gate = text.index("PRODUCTION_LAYOUT_EXPLICIT_REQUIRED")
    assert gate < text.index("Invoke-Git -Arguments @('rev-parse', $ExpectedGitSha)")
    assert gate < text.index("Invoke-RemoteText \"if [ -e")
    assert gate < text.index("Get-FileHash -LiteralPath $archivePath")
    assert "Assert-ProductionReleaseLayout -Layout $layout" in text
    # the exception is explicit, opt-in and locked to fixtures under tests/
    assert "[switch]$UseFixtureTransport" in text
    assert "Assert-FixtureTransportInsideRepoTests -RepoRoot $repoRoot" in text
    # the default layout parameter is unchanged so dry runs / -VerifyOnly stay loadable
    assert "[string]$LayoutFile = 'deploy\\release-layout.example.json'" in text


def test_service_worker_record_uses_script_scope_values_not_the_function_local():
    text = _source()
    assert "public_sw_version_after_switch = $script:publicSwVersionVerified" in text
    assert "public_sw_identity_after_switch = $script:publicSwIdentityVerified" in text
    # the old, always-null expression must be gone
    assert "public_sw_version_after_switch = $publicSwVersion" not in text
    # no additional network round trip: identity is parsed from the SAME sw.js response
    assert text.count("Invoke-WebRequest -Uri $Url -UseBasicParsing -MaximumRedirection 0 -TimeoutSec $TimeoutSeconds") >= 1
    assert "Get-SwAssetIdentityFromText -SwText $response.Content" in text


def test_new_module_functions_are_exported():
    module = MODULE.read_text(encoding="utf-8")
    exported = module[module.index("Export-ModuleMember"):]
    for name in (
        "Get-ProductionReleaseLayoutViolations", "Assert-ProductionReleaseLayout",
        "Assert-FixtureTransportInsideRepoTests", "Assert-RemoteArchiveShaMatch",
        "ConvertFrom-RemoteSha256SumOutput", "Assert-StaticCurrentTargetUnchanged",
    ):
        assert f"function {name}" in module
        assert f"'{name}'" in exported


# ---------------------------------------------------------------------------
# Module-level behaviour of the new guards (real PowerShell, no I/O).
# ---------------------------------------------------------------------------

LAYOUT_VARIANTS = r"""
$base = Get-Content -Raw -LiteralPath 'deploy\release-layout.production.json' | ConvertFrom-Json
function Violations($layout) { return @(Get-ProductionReleaseLayoutViolations -Layout $layout) }
function Variant([scriptblock]$mutate) { $c = $base | ConvertTo-Json | ConvertFrom-Json; & $mutate $c; return (Violations $c) }
$result = [ordered]@{}
$result.production = Violations $base
$result.example = Violations (Get-Content -Raw -LiteralPath 'deploy\release-layout.example.json' | ConvertFrom-Json)
$result.http_url = Variant { param($c) $c.homepage_url = 'http://godokoro.com/' }
$result.ip_literal = Variant { param($c) $c.health_url = 'https://127.0.0.1/healthz'; $c.login_url = 'https://127.0.0.1/login'; $c.homepage_url = 'https://127.0.0.1/' }
$result.localhost = Variant { param($c) $c.health_url = 'https://localhost/healthz'; $c.login_url = 'https://localhost/login'; $c.homepage_url = 'https://localhost/' }
$result.mixed_hosts = Variant { param($c) $c.login_url = 'https://other.godokoro.net/login' }
$result.root_slash = Variant { param($c) $c.static_release_root = '/' }
$result.root_traversal = Variant { param($c) $c.static_release_root = '/opt/../etc' }
$result.root_relative = Variant { param($c) $c.static_release_root = 'opt/static' }
$result.asset_path_mismatch = Variant { param($c) $c.asset_source_path = '/opt/elsewhere/current' }
$result.option_like_alias = Variant { param($c) $c.ssh_alias = '-oProxyCommand=x' }
$result.placeholder_alias = Variant { param($c) $c.ssh_alias = 'your-server' }
$result.empty_env_path = Variant { param($c) $c.production_env_path = '' }
$result.missing_login_url = Variant { param($c) $c.PSObject.Properties.Remove('login_url') }
$result | ConvertTo-Json -Depth 4 -Compress
"""


def _violations_by_case() -> dict:
    proc = _powershell(LAYOUT_VARIANTS)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    raw = json.loads(proc.stdout.strip().splitlines()[-1])
    # ConvertTo-Json collapses 0/1-element arrays; normalise
    return {k: ([] if v is None else ([v] if isinstance(v, str) else list(v))) for k, v in raw.items()}


def test_real_production_layout_is_accepted_and_example_layout_is_rejected():  # TEST_8 (module level) / TEST_9
    cases = _violations_by_case()
    assert cases["production"] == [], cases["production"]
    joined = " | ".join(cases["example"])
    assert "example.invalid" in joined
    assert "production_env_path" in joined
    assert len(cases["example"]) >= 4


@pytest.mark.parametrize(
    "case, expected_fragment",
    [
        ("http_url", "must use https"),
        ("ip_literal", "not an IP literal"),
        ("localhost", "not a real public DNS name"),
        ("mixed_hosts", "must share one public host"),
        ("root_slash", "static_release_root"),
        ("root_traversal", "relative segment"),
        ("root_relative", "static_release_root"),
        ("asset_path_mismatch", "asset_source_path must be"),
        ("option_like_alias", "not a plain host alias"),
        ("placeholder_alias", "placeholder/example value in ssh_alias"),
        ("empty_env_path", "production_env_path"),
        ("missing_login_url", "missing required field: login_url"),
    ],
)
def test_each_invalid_layout_shape_is_named_in_the_violations(case, expected_fragment):
    violations = _violations_by_case()[case]
    assert violations, f"{case} must be rejected"
    assert any(expected_fragment in v for v in violations), violations


GUARD_CASES = r"""
function Try-Throw([scriptblock]$body) { try { & $body; return $null } catch { return $_.Exception.Message } }
$sha = 'a' * 64
$other = 'b' * 64
[ordered]@{
    sha_match = Try-Throw { Assert-RemoteArchiveShaMatch -ExpectedSha256 $sha -ObservedSha256 $sha -RemoteArchivePath '/r/.upload-x.tar' }
    sha_match_case_insensitive = Try-Throw { Assert-RemoteArchiveShaMatch -ExpectedSha256 $sha.ToUpper() -ObservedSha256 $sha -RemoteArchivePath '/r/x' }
    sha_mismatch = Try-Throw { Assert-RemoteArchiveShaMatch -ExpectedSha256 $sha -ObservedSha256 $other -RemoteArchivePath '/r/.upload-x.tar' }
    sha_empty_observed = Try-Throw { Assert-RemoteArchiveShaMatch -ExpectedSha256 $sha -ObservedSha256 '' -RemoteArchivePath '/r/x' }
    sha_unverifiable_expected = Try-Throw { Assert-RemoteArchiveShaMatch -ExpectedSha256 'not-a-hash' -ObservedSha256 $sha -RemoteArchivePath '/r/x' }
    cas_equal = Try-Throw { Assert-StaticCurrentTargetUnchanged -ExpectedGeneration '/r/g1' -ActualGeneration '/r/g1' }
    cas_changed = Try-Throw { Assert-StaticCurrentTargetUnchanged -ExpectedGeneration '/r/g1' -ActualGeneration '/r/g2' }
    cas_empty_equal = Try-Throw { Assert-StaticCurrentTargetUnchanged -ExpectedGeneration '' -ActualGeneration '' }
    cas_empty_vs_set = Try-Throw { Assert-StaticCurrentTargetUnchanged -ExpectedGeneration '' -ActualGeneration '/r/g2' }
    parse_ok = ConvertFrom-RemoteSha256SumOutput -Output ("$sha  /r/.upload-x.tar")
    parse_error_text = ConvertFrom-RemoteSha256SumOutput -Output 'sha256sum: /r/x: No such file or directory'
} | ConvertTo-Json -Compress
"""


def test_archive_sha_and_cas_guards_decide_exactly_as_specified():  # TEST_1/2/4/5 at unit level
    proc = _powershell(GUARD_CASES)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    r = json.loads(proc.stdout.strip().splitlines()[-1])
    assert r["sha_match"] is None and r["sha_match_case_insensitive"] is None
    assert r["sha_mismatch"].startswith(SHA_MISMATCH)
    assert "a" * 64 in r["sha_mismatch"] and "b" * 64 in r["sha_mismatch"]      # expected AND observed reported
    assert r["sha_empty_observed"].startswith(SHA_MISMATCH)                        # no digest is never a match
    assert r["sha_unverifiable_expected"].startswith("STATIC_RELEASE_REMOTE_ARCHIVE_SHA_UNVERIFIABLE")
    assert r["cas_equal"] is None and r["cas_empty_equal"] is None
    assert r["cas_changed"].startswith(CONCURRENT)
    assert "EXPECTED_PRE_SWITCH_GENERATION=/r/g1" in r["cas_changed"]
    assert "ACTUAL_PRE_SWITCH_GENERATION=/r/g2" in r["cas_changed"]
    assert r["cas_empty_vs_set"].startswith(CONCURRENT)
    assert r["parse_ok"] == "a" * 64 and r["parse_error_text"] == ""


# ---------------------------------------------------------------------------
# End to end: the real script, a fixture remote host, a local HTTP origin.
# ---------------------------------------------------------------------------

FIXTURE_FILES = {
    "css/e9/reference_world_map.css": b"/* fixture css */\nbody{margin:0}\n",
    "i18n.js": b"window.__I18N__ = {};\n",
    "inventory.html": b"<!doctype html><title>inventory</title>\n",
    "index.html": b"<!doctype html><title>index</title>\n",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _Origin:
    """The public HTTPS origin, as a local HTTP server: raw static bytes, the three
    authenticated routes as 302 -> /login, and /healthz/static-release provenance."""

    def __init__(self, bundle: Path, generation: str, index_sha: str):
        origin = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def do_GET(self):
                path = urllib.parse.urlsplit(self.path).path
                if path == "/healthz/static-release":
                    body = json.dumps({"ok": True, "generation": generation, "index_sha256": index_sha}).encode()
                    self._send(200, body, "application/json")
                elif path in ("/inventory", "/item-journal", "/zone4_owner_story_runtime.html"):
                    self.send_response(302)
                    self.send_header("Location", "/login")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                elif path == "/healthz":
                    self._send(200, b"ok", "text/plain")
                else:
                    target = bundle / path.lstrip("/")
                    if target.is_file():
                        # a text type, like the real origin: Invoke-WebRequest only exposes a
                        # string .Content for text responses (sw.js is parsed from it)
                        ctype = {".js": "application/javascript", ".css": "text/css", ".html": "text/html"}.get(
                            target.suffix, "application/octet-stream"
                        )
                        self._send(200, target.read_bytes(), ctype)
                    else:
                        self._send(404, b"not found", "text/plain")

            def _send(self, code, body, ctype):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self):
        self._server.shutdown()
        self._server.server_close()


@dataclass
class Package:
    root: Path
    bundle: Path
    archive: Path
    manifest: Path
    layout: Path
    archive_sha: str
    sha: str
    origin: _Origin


@dataclass
class Run:
    proc: subprocess.CompletedProcess
    state_dir: Path

    @property
    def state(self) -> dict:
        return json.loads((self.state_dir / "state.json").read_text(encoding="utf-8"))

    @property
    def commands(self) -> list[dict]:
        path = self.state_dir / "commands.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    @property
    def kinds(self) -> list[str]:
        return [c["kind"] for c in self.commands]

    @property
    def stderr(self) -> str:
        return self.proc.stderr or ""

    @property
    def record(self) -> dict:
        return json.loads(self.proc.stdout)

    @property
    def failure(self) -> dict:
        match = re.search(r"STATIC_FAILURE (\{.*\})", self.stderr)
        assert match, "no STATIC_FAILURE record on stderr:\n" + self.stderr[-2000:]
        return json.loads(match.group(1))

    @property
    def phases(self) -> list[tuple[str, str]]:
        found = []
        for line in self.stderr.splitlines():
            if line.startswith("STATIC_PHASE "):
                event = json.loads(line[len("STATIC_PHASE "):])
                found.append((event["phase"], event["status"]))
        return found

    def index_of(self, kind: str, *, contains: str | None = None, start: int = 0) -> int:
        for i, c in enumerate(self.commands):
            if i >= start and c["kind"] == kind and (contains is None or contains in c["command"]):
                return i
        raise AssertionError(f"no {kind} command (contains={contains!r}) in {self.kinds}")


def _build_archive(path: Path, files: dict[str, bytes]) -> None:
    with tarfile.open(path, "w", format=tarfile.USTAR_FORMAT) as tar:
        for name in sorted(files):
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(files[name]), 0, 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(files[name]))


@pytest.fixture(scope="module")
def package(tmp_path_factory):
    _require_windows_powershell()
    if shutil.which("sh") is None:
        pytest.skip("a POSIX sh is required by the fixture remote's atomic-switch execution")
    probe = _powershell("(Resolve-GnuTarExecutable).path")
    if probe.returncode != 0:
        pytest.skip(f"could not resolve a GNU tar for this environment: {probe.stderr}")

    root = tmp_path_factory.mktemp("a017_package")
    sha = _head_sha()
    files = dict(FIXTURE_FILES)
    files["sw.js"] = f"const VERSION = '{SW_VERSION}';\nconst ASSET_IDENTITY = 'release-{sha}';\n".encode()
    bundle = root / "bundle"
    for name, data in files.items():
        target = bundle / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    archive = root / "fixture.static.tar"
    _build_archive(archive, files)
    archive_sha = _sha256(archive.read_bytes())

    origin = _Origin(bundle, NEW_GEN, _sha256(files["index.html"]))
    manifest = {
        "release_git_sha": sha, "static_generation_id": NEW_GEN, "static_root": REMOTE_ROOT,
        "service_worker_version": SW_VERSION, "service_worker_asset_identity": f"release-{sha}",
        "asset_count": len(files), "total_bytes": sum(len(d) for d in files.values()),
        "files": [{"path": p, "sha256": _sha256(d), "size": len(d)} for p, d in sorted(files.items())],
        "archive_filename": archive.name, "archive_sha256": archive_sha, "archive_size": archive.stat().st_size,
        "archive_entry_count": len(files), "gnu_tar_executable_path": "fixture", "gnu_tar_version": "fixture",
        "created_at": "2026-01-02T00:00:00Z",
    }
    manifest_path = root / "fixture.static.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    layout = json.loads((REPO_ROOT / "deploy" / "release-layout.example.json").read_text(encoding="utf-8"))
    layout.update({
        "ssh_alias": "fixture-host", "static_release_root": REMOTE_ROOT,
        "asset_source_path": f"{REMOTE_ROOT}/current", "asset_container_mount_destination": f"{REMOTE_ROOT}/current",
        "health_url": f"http://127.0.0.1:{origin.port}/healthz", "login_url": f"http://127.0.0.1:{origin.port}/login",
        "homepage_url": f"http://127.0.0.1:{origin.port}/",
    })
    layout_path = root / "fixture.layout.json"
    layout_path.write_text(json.dumps(layout, indent=2), encoding="utf-8")
    yield Package(root, bundle, archive, manifest_path, layout_path, archive_sha, sha, origin)
    origin.close()


def _fixture_state(tmp: Path, scenario: dict | None) -> Path:
    state_dir = tmp
    (state_dir / "fs").mkdir(parents=True, exist_ok=True)
    old = state_dir / "fs" / "srv" / "fixture-static" / "releases" / OLD_GEN
    old.mkdir(parents=True, exist_ok=True)
    (old / "i18n.js").write_bytes(b"old generation\n")
    (state_dir / "state.json").write_text(json.dumps({
        "root": REMOTE_ROOT, "current": OLD_TARGET, "mount_dest": f"{REMOTE_ROOT}/current",
        "health": "healthy", "scenario": scenario or {},
    }), encoding="utf-8")
    return state_dir


def _fixture_env(state_dir: Path, path_prefix: Path | None = None) -> dict:
    env = os.environ.copy()
    env["PATH"] = f"{path_prefix or FAKE_DIR}{os.pathsep}{env.get('PATH', '')}"
    env.update({
        "FAKE_REMOTE_DIR": str(state_dir), "FAKE_REMOTE_PYTHON": sys.executable,
        "FAKE_REMOTE_SH": shutil.which("sh") or "sh", "GO_ODYSSEY_STATIC_DEPLOY_TIMING": "0",
    })
    return env


def _deploy_args(pkg: Package, layout: str | Path | None, *, execute: bool = True, fixture: bool = True, extra=()) -> list[str]:
    args = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
        "-ExpectedGitSha", pkg.sha, "-StaticManifest", str(pkg.manifest),
        "-BundlePath", str(pkg.bundle), "-ArchivePath", str(pkg.archive),
    ]
    if layout is not None:
        args += ["-LayoutFile", str(layout)]
    if execute:
        args += ["-Execute", "-OwnerGate", "GO_DEPLOY"]
    if fixture:
        args += ["-UseFixtureTransport"]
    return args + list(extra)


def _run_fixture_deploy(pkg: Package, tmp_path_factory, name: str, scenario: dict | None) -> Run:
    state_dir = _fixture_state(tmp_path_factory.mktemp(name), scenario)
    proc = run_bounded(
        _deploy_args(pkg, pkg.layout), cwd=REPO_ROOT, env=_fixture_env(state_dir),
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=420,
    )
    return Run(proc, state_dir)


@pytest.fixture(scope="module")
def success_run(package, tmp_path_factory) -> Run:
    return _run_fixture_deploy(package, tmp_path_factory, "a017_success", None)


@pytest.fixture(scope="module")
def mismatch_run(package, tmp_path_factory) -> Run:
    return _run_fixture_deploy(package, tmp_path_factory, "a017_mismatch", {"corrupt_archive_on_upload": True})


@pytest.fixture(scope="module")
def changed_before_recheck_run(package, tmp_path_factory) -> Run:
    # another deployer switches the live symlink while this run is still uploading
    hook = {"on": "scp_upload", "occurrence": 1, "set_current": OTHER_TARGET}
    return _run_fixture_deploy(package, tmp_path_factory, "a017_changed_before", {"hooks": [hook]})


@pytest.fixture(scope="module")
def changed_after_recheck_run(package, tmp_path_factory) -> Run:
    # ...or in the sliver AFTER the early re-read (readlink #1 = capture, #2 = the re-read)
    hook = {"on": "readlink", "occurrence": 2, "set_current": OTHER_TARGET}
    return _run_fixture_deploy(package, tmp_path_factory, "a017_changed_after", {"hooks": [hook]})


# --- TEST_1 / TEST_4: matching remote archive hash, unchanged symlink -> promotion permitted -------------

def test_matching_remote_archive_sha_permits_extraction_and_the_deploy_completes(success_run):  # TEST_1
    assert success_run.proc.returncode == 0, success_run.stderr[-3000:] + success_run.proc.stdout[-500:]
    record = success_run.record
    assert record["result"] == "STATIC RELEASE SWITCH SUCCEEDED", json.dumps(
        {k: record.get(k) for k in ("result", "original_local_failure", "reconciliation_state")}, indent=2
    )[:3000] + "\n" + success_run.stderr[-2500:]
    assert record["remote_archive_sha_match"] is True
    upload = success_run.index_of("scp_upload")
    sha_check = success_run.index_of("sha256sum_file", contains=".upload-")
    extract = success_run.index_of("tar_extract")
    file_check = success_run.index_of("batch_sha_verify")
    assert upload < sha_check < extract < file_check, success_run.kinds
    assert success_run.state["extractions"], "the archive must have been extracted"


def test_the_remote_hash_is_the_hash_of_the_bytes_the_remote_actually_holds(success_run, package):
    record = success_run.record
    assert record["remote_archive_sha256"] == package.archive_sha
    assert record["archive_sha256"] == package.archive_sha


def test_unchanged_preflight_symlink_permits_promotion_and_records_the_evidence(success_run):  # TEST_4
    record = success_run.record
    assert record["previous_current_target"] == OLD_TARGET
    assert record["expected_pre_switch_generation"] == OLD_TARGET
    assert record["actual_pre_switch_generation"] == OLD_TARGET
    assert record["pre_switch_compare_and_swap"] == "ENFORCED"
    assert record["new_current_target"] == NEW_TARGET
    writes = success_run.state["symlink_writes"]
    assert len(writes) == 1 and writes[0]["exit"] == 0
    assert [w.split()[0] for w in writes[0]["writes"]] == ["ln", "mv"]
    assert success_run.state["current"] == NEW_TARGET
    assert len(success_run.state["restarts"]) == 1
    phases = [p for p, s in success_run.phases if s == "BEGIN"]
    assert phases.index("REMOTE_ARCHIVE_SHA") < phases.index("RECHECK_LIVE_SYMLINK") < phases.index("SWITCH_CURRENT")
    # the early re-read happened between capture and switch (two readlinks before the write)
    switch = success_run.index_of("switch")
    assert sum(1 for c in success_run.commands[:switch] if c["kind"] == "readlink") == 2


def test_existing_layers_are_preserved_extracted_file_count_bytes_and_hash_checks_ran(success_run):
    kinds = success_run.kinds
    for kind in ("find_count", "find_bytes", "batch_sha_verify", "docker_inspect_health", "docker_exec_sha"):
        assert kind in kinds, kinds
    # manifest uploaded last, after the extracted-file verification and before the switch
    assert success_run.index_of("batch_sha_verify") < [i for i, c in enumerate(success_run.commands) if c["kind"] == "scp_upload"][1] < success_run.index_of("switch")
    assert not any(c["kind"] == "unhandled" for c in success_run.commands)


# --- TEST_2 / TEST_3: remote archive hash mismatch -> nothing extracted, nothing switched -------------------

def test_remote_archive_sha_mismatch_forbids_extraction(mismatch_run, package):  # TEST_2
    assert mismatch_run.proc.returncode != 0
    assert mismatch_run.state["uploads"][0]["corrupted"] is True
    assert "tar_extract" not in mismatch_run.kinds
    assert not mismatch_run.state.get("extractions")
    # the failure names both hashes
    failure = mismatch_run.failure
    message = failure["failure_message"]
    assert message.startswith(SHA_MISMATCH), message
    assert f"authorized archive SHA-256 is '{package.archive_sha}'" in message
    observed = re.search(r"remote SHA-256 '([0-9a-f]{64})'", message)
    assert observed and observed.group(1) != package.archive_sha
    assert failure["failure_phase"] == "REMOTE_ARCHIVE_SHA"
    assert failure["gate_failure"] == SHA_MISMATCH
    # nothing downstream of the gate was even attempted (no count/bytes/verify/manifest/switch/restart)
    gate = mismatch_run.index_of("sha256sum_file", contains=".upload-")
    after = mismatch_run.kinds[gate + 1:]
    assert set(after) <= {"readlink"}, after


def test_remote_archive_sha_mismatch_leaves_symlink_containers_and_manifest_untouched(mismatch_run):  # TEST_3
    state = mismatch_run.state
    assert state["current"] == OLD_TARGET
    assert not state.get("symlink_writes")
    assert not state.get("restarts")
    assert "switch" not in mismatch_run.kinds and "docker_restart" not in mismatch_run.kinds
    assert [c for c in mismatch_run.commands if c["kind"] == "scp_upload"][1:] == [], "release manifest must not be uploaded"
    failure = mismatch_run.failure
    assert failure["rollback_required"] is False and failure["rollback_result"] == "not_required"
    assert failure["final_current_generation"] == OLD_TARGET
    # a deterministic gate decision is not reconciled like an ambiguous timeout
    assert failure["reconciliation_state"] == "NOT_APPLICABLE_DEFINITIVE_GATE_FAILURE"
    assert failure["remote_archive_sha_match"] is None


# --- TEST_5 / TEST_6: concurrent mutation -> refused before any symlink write -------------------------------

def test_symlink_changed_since_preflight_forbids_promotion(changed_before_recheck_run):  # TEST_5
    run = changed_before_recheck_run
    assert run.proc.returncode != 0
    failure = run.failure
    assert failure["failure_message"].startswith(CONCURRENT)
    assert f"EXPECTED_PRE_SWITCH_GENERATION={OLD_TARGET}" in failure["failure_message"]
    assert f"ACTUAL_PRE_SWITCH_GENERATION={OTHER_TARGET}" in failure["failure_message"]
    assert failure["failure_phase"] == "RECHECK_LIVE_SYMLINK"
    assert failure["gate_failure"] == CONCURRENT
    # the other deployer's symlink is what remains -- this run did not overwrite it
    assert run.state["current"] == OTHER_TARGET
    assert failure["final_current_generation"] == OTHER_TARGET
    assert failure["rollback_required"] is False


def test_concurrent_mutation_is_refused_before_any_symlink_write_or_restart(changed_before_recheck_run):  # TEST_6a
    run = changed_before_recheck_run
    assert "switch" not in run.kinds
    assert not run.state.get("symlink_writes")
    assert "docker_restart" not in run.kinds and not run.state.get("restarts")
    # everything up to and including the (fully verified) generation had already happened: the guard, not
    # an earlier failure, is what stopped the deploy
    assert "batch_sha_verify" in run.kinds and run.kinds.count("scp_upload") == 2


def test_mutation_in_the_window_after_the_early_recheck_is_caught_by_the_atomic_guard(changed_after_recheck_run):  # TEST_6b
    run = changed_after_recheck_run
    assert run.proc.returncode != 0
    # the early re-read (readlink #2) still saw the captured target; the change came after it
    assert run.state["hook_events"] == [{"on": "readlink", "occurrence": 2, "set_current": OTHER_TARGET}]
    switch = run.state["symlink_writes"]
    assert len(switch) == 1 and switch[0]["exit"] == 73
    assert switch[0]["writes"] == [], "the guard must refuse BEFORE any ln/mv"
    failure = run.failure
    assert failure["failure_message"].startswith(CONCURRENT)
    assert f"ACTUAL_PRE_SWITCH_GENERATION={OTHER_TARGET}" in failure["failure_message"]
    assert failure["failure_phase"] == "SWITCH_CURRENT"
    assert run.state["current"] == OTHER_TARGET
    assert "docker_restart" not in run.kinds


# --- TEST_7: the verified service-worker values are persisted ---------------------------------------------

def test_verified_service_worker_version_and_identity_are_persisted_in_the_record(success_run, package):  # TEST_7
    record = success_run.record
    assert record["public_sw_version_after_switch"] == SW_VERSION
    assert record["public_sw_identity_after_switch"] == f"release-{package.sha}"
    # ...and the public acceptance contract really ran (this is not a stub value)
    begins = [p for p, s in success_run.phases if s == "BEGIN"]
    assert begins.index("PUBLIC_HASH_BEGIN") < begins.index("PUBLIC_SW") < begins.index("PUBLIC_INDEX_PROVENANCE")


def test_verify_only_reports_the_observed_service_worker_values(package):
    _require_windows_powershell()
    proc = run_bounded(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
            "-ExpectedGitSha", package.sha, "-StaticManifest", str(package.manifest),
            "-LayoutFile", str(package.layout), "-VerifyOnly",
        ],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    payload = json.loads(proc.stdout)
    assert payload["result"] == "PUBLIC_STATIC_ACCEPTANCE_VERIFIED" and payload["mutated"] is False
    assert payload["public_sw_version_observed"] == SW_VERSION
    assert payload["public_sw_identity_observed"] == f"release-{package.sha}"


# --- TEST_8 / TEST_9 / TEST_10: the production-layout rule --------------------------------------------------

def _blocked_transport(directory: Path) -> Path:
    """ssh/scp stand-ins OUTSIDE the repo tests dir that log the call and fail: they guarantee that a
    Production-mode run in these tests can never reach a real host, and count remote contacts."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("ssh", "scp"):
        (directory / f"{name}.cmd").write_text(
            "@echo off\r\necho CALL >> \"%BLOCKED_TRANSPORT_LOG%\"\r\necho FIXTURE_BLOCKED_TRANSPORT 1>&2\r\nexit /b 99\r\n",
            encoding="ascii",
        )
    return directory


def _blocked_env(directory: Path, log: Path) -> dict:
    env = os.environ.copy()
    env["PATH"] = f"{directory}{os.pathsep}{env.get('PATH', '')}"
    env["BLOCKED_TRANSPORT_LOG"] = str(log)
    return env


def _assert_transport_resolves_to_the_blocker(directory: Path, env: dict) -> None:
    """Safety net: prove, under the exact environment the deploy will run in, that ssh and scp resolve to
    the blocker -- otherwise a Production-mode test could contact a real host. Fail instead of running."""
    for name in ("ssh", "scp"):
        probe = run_bounded(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-Command -Name {name} -CommandType Application | Select-Object -First 1).Source"],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
        )
        resolved = probe.stdout.strip()
        assert resolved.lower() == str(directory / f"{name}.cmd").lower(), (
            f"refusing to run: '{name}' resolves to {resolved!r}, not the blocker in {directory}"
        )


def _contacts(log: Path) -> int:
    return len([line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]) if log.exists() else 0


def _run_production_mode(package, tmp_path, *, layout, fixture_flag=False, execute=True):
    blocked = _blocked_transport(tmp_path / "blocked")
    log = tmp_path / "blocked.log"
    env = _blocked_env(blocked, log)
    _assert_transport_resolves_to_the_blocker(blocked, env)
    proc = run_bounded(
        _deploy_args(package, layout, execute=execute, fixture=fixture_flag),
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    return proc, _contacts(log)


def test_explicit_real_production_layout_is_accepted_in_execute_mode(package, tmp_path):  # TEST_8
    proc, contacts = _run_production_mode(package, tmp_path, layout=PRODUCTION_LAYOUT)
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "PRODUCTION_LAYOUT" not in combined and "FIXTURE_TRANSPORT_REQUIRED" not in combined, combined[-1500:]
    # accepted: the run got past every local gate and issued its first remote command (which the blocker refused)
    assert contacts == 1, combined[-1500:]
    assert "FIXTURE_BLOCKED_TRANSPORT" in combined
    assert proc.returncode != 0


def test_default_layout_is_rejected_in_execute_mode_before_any_remote_contact(package, tmp_path):  # TEST_9a
    proc, contacts = _run_production_mode(package, tmp_path, layout=None)
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode != 0
    assert "PRODUCTION_LAYOUT_EXPLICIT_REQUIRED" in combined, combined[-1500:]
    assert contacts == 0


def test_explicit_example_layout_is_rejected_in_execute_mode_before_any_remote_contact(package, tmp_path):  # TEST_9b
    proc, contacts = _run_production_mode(package, tmp_path, layout=EXAMPLE_LAYOUT)
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode != 0
    assert "PRODUCTION_LAYOUT_INVALID" in combined and "example.invalid" in combined, combined[-1500:]
    assert contacts == 0


def test_a_fixture_layout_can_never_be_combined_with_a_real_transport(package, tmp_path):  # TEST_9c
    proc, contacts = _run_production_mode(package, tmp_path, layout=package.layout, fixture_flag=True)
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode != 0
    assert "FIXTURE_TRANSPORT_REQUIRED" in combined, combined[-1500:]
    assert contacts == 0
    # without the fixture switch the same non-production layout is refused as an invalid Production layout
    proc2, contacts2 = _run_production_mode(package, tmp_path / "again", layout=package.layout)
    assert "PRODUCTION_LAYOUT_INVALID" in (proc2.stdout or "") + (proc2.stderr or "")
    assert contacts2 == 0


def test_dry_run_still_works_with_the_default_example_layout_and_reports_the_execute_verdict(package):  # TEST_10
    _require_windows_powershell()
    default_layout = run_bounded(
        _deploy_args(package, None, execute=False, fixture=False),
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    assert default_layout.returncode == 0, default_layout.stderr[-1500:]
    payload = json.loads(default_layout.stdout)
    assert payload["dry_run"] is True and payload["result"] == "DRY_RUN_COMPLETE"
    assert payload["remote_preflight"] is False and payload["owner_gate_validated"] is False
    assert payload["layout_explicit"] is False
    assert payload["production_layout_valid"] is False
    assert any("example.invalid" in v for v in payload["production_layout_violations"])

    production = run_bounded(
        _deploy_args(package, PRODUCTION_LAYOUT, execute=False, fixture=False),
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    assert production.returncode == 0, production.stderr[-1500:]
    payload = json.loads(production.stdout)
    assert payload["layout_explicit"] is True and payload["production_layout_valid"] is True
    assert payload["production_layout_violations"] == []


def test_fixture_execute_mode_remains_usable_where_explicitly_intended(success_run):  # TEST_10 (fixture mode)
    assert success_run.proc.returncode == 0
    assert success_run.record["fixture_transport"] is True
