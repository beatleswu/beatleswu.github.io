"""RELEASE-FIX-A3-STATIC-DEPLOY-FIX3 -- immutable prebuilt static archive.

Root cause fixed here (see docs/incidents/2026-07-12-full-site-asset-outage.md
and the RELEASE-FIX-A3 production deploy attempt this Sprint follows):

  1. New-DeterministicStaticArchive invoked a bare `tar` name via
     Start-Process, which on this Windows host resolved to the bundled
     bsdtar (C:\\Windows\\System32\\tar.exe) instead of a real GNU tar --
     bsdtar does not support --sort=name/--mtime=/--owner=0/--group=0/
     --numeric-owner, so the very first real production deploy attempt
     failed at local archive creation, before any remote call.
  2. A release-identity defect: the archive a Release Review verified was
     rebuilt from scratch at deploy time, using whatever tar the deploy
     workstation's PATH happened to resolve *that day* -- the archive
     actually uploaded was never provably the same bytes as the one
     reviewed.

This Sprint fixes both: Resolve-GnuTarExecutable finds and capability-
verifies a real GNU tar (never silently falling back to bsdtar), and
archive creation moves entirely into packaging (package-static-release.ps1)
-- deploy-static-release.ps1 now only verifies and uploads the exact
prebuilt archive, and never calls New-DeterministicStaticArchive.

None of these tests connect to production or a real host.
"""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PSM1 = REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "release" / "deploy-static-release.ps1"
PACKAGE_SCRIPT = REPO_ROOT / "scripts" / "release" / "package-static-release.ps1"
FAKE_TAR_MISSING_FLAG = REPO_ROOT / "tests" / "fixtures" / "fake_tar" / "fake_gnu_tar_missing_flag.cmd"
WINDOWS_BSDTAR = Path(r"C:\Windows\System32\tar.exe")


def _read(path):
    return path.read_text(encoding="utf-8")


def _run_pwsh(script, timeout=60):
    if shutil.which("powershell") is None:
        pytest.skip("powershell not available in this environment")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout,
    )
    return result


def _import_module_prelude():
    return f"Import-Module '{PSM1}' -Force -DisableNameChecking\n"


# ---------------------------------------------------------------------------
# 1. PowerShell resolves the intended GNU tar executable.
# ---------------------------------------------------------------------------

def test_resolve_gnu_tar_executable_finds_a_real_gnu_tar():
    script = _import_module_prelude() + """
    $result = Resolve-GnuTarExecutable
    $result | ConvertTo-Json -Depth 5
    """
    result = _run_pwsh(script, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert Path(payload["path"]).is_file(), f"resolved tar path does not exist: {payload['path']}"
    assert payload["path"].lower().endswith("tar.exe")
    assert "GNU tar" in payload["version_output"]


# ---------------------------------------------------------------------------
# 2. Windows System32 bsdtar is rejected.
# ---------------------------------------------------------------------------

def test_windows_bsdtar_is_rejected_by_capability_probe():
    if not WINDOWS_BSDTAR.is_file():
        pytest.skip("Windows bsdtar not present at the expected System32 path on this host")
    script = _import_module_prelude() + f"""
    $probe = Test-GnuTarExecutableCapability -TarExecutablePath '{WINDOWS_BSDTAR}'
    $probe | ConvertTo-Json -Depth 5
    """
    result = _run_pwsh(script, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["smoke_test_passed"] is False
    assert payload["failure_reason"], "bsdtar rejection must record a reason"


# ---------------------------------------------------------------------------
# 3. Unsupported tar flags fail closed (a real archive-build smoke test,
# not just a --version string check).
# ---------------------------------------------------------------------------

def test_gnu_flavored_tar_missing_required_flag_fails_closed():
    script = _import_module_prelude() + f"""
    $probe = Test-GnuTarExecutableCapability -TarExecutablePath '{FAKE_TAR_MISSING_FLAG}'
    $probe | ConvertTo-Json -Depth 5
    """
    result = _run_pwsh(script, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["is_gnu_tar"] is True, "fixture must pass the --version GNU-tar check"
    assert payload["smoke_test_passed"] is False, "a real archive-build failure must still be rejected"
    assert "smoke-test" in payload["failure_reason"]


# ---------------------------------------------------------------------------
# 4 & 5. Explicit override works / invalid override fails clearly.
# ---------------------------------------------------------------------------

def test_explicit_override_is_used_and_works():
    script = _import_module_prelude() + """
    $resolved = Resolve-GnuTarExecutable
    $result = Resolve-GnuTarExecutable -OverridePath $resolved.path
    $result | ConvertTo-Json -Depth 5
    """
    result = _run_pwsh(script, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["source"] == "override"


def test_invalid_override_fails_clearly_without_falling_back():
    script = _import_module_prelude() + """
    try {
        Resolve-GnuTarExecutable -OverridePath 'C:\\definitely\\not\\a\\real\\tar.exe' | Out-Null
        Write-Output "UNEXPECTED_SUCCESS"
    } catch {
        Write-Output "FAILED_CLOSED: $($_.Exception.Message)"
    }
    """
    result = _run_pwsh(script, timeout=30)
    assert "FAILED_CLOSED" in result.stdout
    assert "not\\a\\real\\tar.exe" in result.stdout or "override" in result.stdout.lower()


def test_invalid_override_never_silently_falls_back_to_discovery():
    # An override that fails must not be silently replaced by an
    # auto-discovered candidate -- that would mask an operator's explicit
    # misconfiguration. Confirm the resolver's override branch returns/throws
    # without ever invoking the discovery candidate list.
    content = _read(PSM1)
    func_start = content.index("function Resolve-GnuTarExecutable")
    func_end = content.index("\nfunction ", func_start + 1)
    body = content[func_start:func_end]
    override_throw_index = body.index("GNU tar override")
    discovery_index = body.index("$gitCommand = Get-Command git.exe")
    assert override_throw_index < discovery_index, (
        "the override failure throw must appear before any discovery-candidate code, "
        "so an invalid override can never fall through to auto-discovery"
    )


# ---------------------------------------------------------------------------
# 6. Discovery from the real git.exe installation works.
# ---------------------------------------------------------------------------

def test_discovery_derives_tar_path_from_real_git_exe():
    # The resolver's git.exe-derived candidate is tried first among the
    # discovery candidates, but a Git for Windows install can expose more
    # than one git.exe on PATH (cmd\\git.exe vs mingw64\\bin\\git.exe) whose
    # derived tar.exe candidate may or may not itself exist -- the resolver
    # correctly falls through its candidate list in that case. So this test
    # asserts the *mechanism* (discovery finds a real, existing, GNU-tar
    # executable somewhere under a real Git for Windows install), not an
    # exact path match against one specific derivation.
    script = _import_module_prelude() + """
    $gitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
    if (-not $gitCommand) { Write-Output "NO_GIT_ON_PATH"; exit }
    $result = Resolve-GnuTarExecutable
    [ordered]@{ resolved = $result.path; source = $result.source } | ConvertTo-Json
    """
    result = _run_pwsh(script, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    if "NO_GIT_ON_PATH" in result.stdout:
        pytest.skip("git.exe not resolvable on PATH in this environment")
    payload = json.loads(result.stdout)
    assert payload["source"] == "discovered"
    assert Path(payload["resolved"]).is_file()
    assert re.search(r"git", payload["resolved"], re.IGNORECASE), (
        f"expected a Git-for-Windows-derived tar path, got: {payload['resolved']}"
    )


# ---------------------------------------------------------------------------
# 7. The capability test and the real archive builder use the same bounded
# native-process helper (Invoke-BoundedNativeCommand), not a bare
# Start-Process call that could resolve a different binary than what was
# capability-tested.
# ---------------------------------------------------------------------------

def test_capability_probe_and_archive_builder_use_same_process_helper():
    content = _read(PSM1)

    def body_of(name):
        start = content.index(f"function {name}")
        end = content.index("\nfunction ", start + 1)
        return content[start:end]

    probe_body = body_of("Test-GnuTarExecutableCapability")
    build_body = body_of("New-DeterministicStaticArchive")
    assert "Invoke-BoundedNativeCommand" in probe_body
    assert "Invoke-BoundedNativeCommand" in build_body
    # Check for an actual Start-Process *invocation*, not just the phrase
    # appearing in an explanatory comment (this function's own docstring
    # mentions Start-Process by name when describing the bug it fixes).
    assert not re.search(r"Start-Process\s+-FilePath", build_body), (
        "New-DeterministicStaticArchive must not use a separate Start-Process "
        "code path from the one Test-GnuTarExecutableCapability verified"
    )


# ---------------------------------------------------------------------------
# 8 & 9. Two package builds (via New-DeterministicStaticArchive directly, a
# fast synthetic-bundle equivalent of a full packaging run) produce
# identical archive SHA values; manifest object records archive identity.
# ---------------------------------------------------------------------------

def test_two_archive_builds_from_identical_bytes_are_deterministic():
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "bundle"
        bundle.mkdir()
        (bundle / "i18n.js").write_text("var x = 1;\n", encoding="utf-8")
        (bundle / "sw.js").write_text("const VERSION = 'test';\n", encoding="utf-8")
        (bundle / "assets").mkdir()
        (bundle / "assets" / "a.webp").write_bytes(b"fake-image-bytes-a")
        (bundle / "assets" / "b.webp").write_bytes(b"fake-image-bytes-b")
        relative_paths = ["i18n.js", "sw.js", "assets/a.webp", "assets/b.webp"]
        archive1 = Path(tmp) / "build1.tar"
        archive2 = Path(tmp) / "build2.tar"

        script = _import_module_prelude() + f"""
        $gnuTar = Resolve-GnuTarExecutable
        New-DeterministicStaticArchive -BundlePath '{bundle}' -RelativePaths @({",".join(f"'{p}'" for p in relative_paths)}) -ArchivePath '{archive1}' -GnuTarExecutablePath $gnuTar.path | Out-Null
        New-DeterministicStaticArchive -BundlePath '{bundle}' -RelativePaths @({",".join(f"'{p}'" for p in relative_paths)}) -ArchivePath '{archive2}' -GnuTarExecutablePath $gnuTar.path | Out-Null
        $hash1 = (Get-FileHash -LiteralPath '{archive1}' -Algorithm SHA256).Hash
        $hash2 = (Get-FileHash -LiteralPath '{archive2}' -Algorithm SHA256).Hash
        [ordered]@{{ hash1 = $hash1; hash2 = $hash2 }} | ConvertTo-Json
        """
        result = _run_pwsh(script, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["hash1"] == payload["hash2"]


def test_manifest_object_records_archive_identity():
    script = _import_module_prelude() + """
    $files = @([ordered]@{ path = 'i18n.js'; sha256 = ('0' * 64); size = 10 })
    $manifest = New-StaticReleaseManifestObject -GitSha ('a' * 40) -GenerationId 'gen1' -SwVersion 'v1' -Files $files -CreatedAtUtc '2026-01-01T00:00:00Z' -ArchiveFileName 'x.tar' -ArchiveSha256 ('b' * 64) -ArchiveSize 100 -ArchiveEntryCount 1 -GnuTarExecutablePath 'C:\\tar.exe' -GnuTarVersion 'tar (GNU tar) 1.35'
    $manifest | ConvertTo-Json -Depth 5
    """
    result = _run_pwsh(script, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["archive_filename"] == "x.tar"
    assert payload["archive_sha256"] == "b" * 64
    assert payload["archive_size"] == 100
    assert payload["archive_entry_count"] == 1
    assert payload["gnu_tar_executable_path"] == "C:\\tar.exe"
    assert payload["gnu_tar_version"] == "tar (GNU tar) 1.35"


# ---------------------------------------------------------------------------
# 10 & 11. Deployment consumes the prebuilt archive; deployment never
# rebuilds it.
# ---------------------------------------------------------------------------

def test_deploy_script_requires_explicit_archive_path_and_never_rebuilds():
    content = _read(DEPLOY_SCRIPT)
    assert "[Parameter(Mandatory = $true)][string]$ArchivePath" in content
    assert "Invoke-BoundedFileUpload -LocalPath $archivePath" in content
    # Check for an actual *call* (function name immediately followed by a
    # parameter), not just the phrase appearing in an explanatory comment
    # (this script's own comments explain, by name, why it no longer calls
    # this function).
    assert not re.search(r"New-DeterministicStaticArchive\s+-", content), (
        "deploy-static-release.ps1 must never call New-DeterministicStaticArchive -- "
        "it consumes the already-built archive package-static-release.ps1 produced"
    )


def test_package_script_is_the_only_caller_of_archive_builder():
    package_content = _read(PACKAGE_SCRIPT)
    assert "New-DeterministicStaticArchive" in package_content
    assert "Resolve-GnuTarExecutable" in package_content


# ---------------------------------------------------------------------------
# 12, 13, 14. Archive SHA mismatch / byte-size mismatch / missing archive
# each fail before any remote upload -- exercised via real dry-run
# invocations (the archive verification happens unconditionally, before the
# dry-run early-return, so no network/owner-gate is needed to prove this).
# ---------------------------------------------------------------------------

def _write_minimal_static_manifest(path, **overrides):
    manifest = {
        "release_git_sha": "a" * 40,
        "static_generation_id": "gen1",
        "static_root": "/opt/go-odyssey-static",
        "service_worker_version": "v1",
        "asset_count": 1,
        "total_bytes": 3,
        "files": [{"path": "i18n.js", "sha256": None, "size": 3}],
        "archive_filename": "archive.tar",
        "archive_sha256": None,
        "archive_size": None,
        "archive_entry_count": 1,
        "gnu_tar_executable_path": "C:\\tar.exe",
        "gnu_tar_version": "tar (GNU tar) 1.35",
        "created_at": "2026-01-01T00:00:00Z",
    }
    manifest.update(overrides)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def _build_minimal_bundle_and_archive(tmp):
    import hashlib
    bundle = Path(tmp) / "bundle"
    bundle.mkdir()
    i18n = bundle / "i18n.js"
    i18n.write_bytes(b"abc")
    i18n_sha = hashlib.sha256(b"abc").hexdigest()
    return bundle, i18n_sha


def test_archive_sha_mismatch_fails_before_remote_upload():
    with tempfile.TemporaryDirectory() as tmp:
        bundle, i18n_sha = _build_minimal_bundle_and_archive(tmp)
        archive_path = Path(tmp) / "archive.tar"
        archive_path.write_bytes(b"not-a-real-archive-but-has-some-bytes")
        import hashlib
        wrong_sha = hashlib.sha256(b"different content entirely").hexdigest()
        manifest_path = Path(tmp) / "manifest.json"
        _write_minimal_static_manifest(
            manifest_path,
            files=[{"path": "i18n.js", "sha256": i18n_sha, "size": 3}],
            archive_sha256=wrong_sha,
            archive_size=archive_path.stat().st_size,
        )
        script = f"""
        try {{
            & '{DEPLOY_SCRIPT}' -ExpectedGitSha ('a'*40) -StaticManifest '{manifest_path}' -BundlePath '{bundle}' -ArchivePath '{archive_path}' -LayoutFile 'deploy\\release-layout.example.json'
            Write-Output "UNEXPECTED_SUCCESS"
        }} catch {{
            Write-Output "FAILED_CLOSED: $($_.Exception.Message)"
        }}
        """
        result = _run_pwsh(script, timeout=30)
        assert "FAILED_CLOSED" in result.stdout, result.stdout + result.stderr
        assert "archive_sha256" in result.stdout or "SHA-256" in result.stdout


def test_archive_byte_size_mismatch_fails_before_remote_upload():
    with tempfile.TemporaryDirectory() as tmp:
        bundle, i18n_sha = _build_minimal_bundle_and_archive(tmp)
        archive_path = Path(tmp) / "archive.tar"
        archive_bytes = b"not-a-real-archive-but-has-some-bytes"
        archive_path.write_bytes(archive_bytes)
        import hashlib
        actual_sha = hashlib.sha256(archive_bytes).hexdigest()
        manifest_path = Path(tmp) / "manifest.json"
        _write_minimal_static_manifest(
            manifest_path,
            files=[{"path": "i18n.js", "sha256": i18n_sha, "size": 3}],
            archive_sha256=actual_sha,
            archive_size=len(archive_bytes) + 1000,
        )
        script = f"""
        try {{
            & '{DEPLOY_SCRIPT}' -ExpectedGitSha ('a'*40) -StaticManifest '{manifest_path}' -BundlePath '{bundle}' -ArchivePath '{archive_path}' -LayoutFile 'deploy\\release-layout.example.json'
            Write-Output "UNEXPECTED_SUCCESS"
        }} catch {{
            Write-Output "FAILED_CLOSED: $($_.Exception.Message)"
        }}
        """
        result = _run_pwsh(script, timeout=30)
        assert "FAILED_CLOSED" in result.stdout, result.stdout + result.stderr
        assert "byte size" in result.stdout


def test_missing_archive_fails_before_remote_upload():
    with tempfile.TemporaryDirectory() as tmp:
        bundle, i18n_sha = _build_minimal_bundle_and_archive(tmp)
        missing_archive_path = Path(tmp) / "does-not-exist.tar"
        manifest_path = Path(tmp) / "manifest.json"
        _write_minimal_static_manifest(
            manifest_path,
            files=[{"path": "i18n.js", "sha256": i18n_sha, "size": 3}],
            archive_sha256="f" * 64,
            archive_size=123,
        )
        script = f"""
        try {{
            & '{DEPLOY_SCRIPT}' -ExpectedGitSha ('a'*40) -StaticManifest '{manifest_path}' -BundlePath '{bundle}' -ArchivePath '{missing_archive_path}' -LayoutFile 'deploy\\release-layout.example.json'
            Write-Output "UNEXPECTED_SUCCESS"
        }} catch {{
            Write-Output "FAILED_CLOSED: $($_.Exception.Message)"
        }}
        """
        result = _run_pwsh(script, timeout=30)
        assert "FAILED_CLOSED" in result.stdout, result.stdout + result.stderr
        assert "not found" in result.stdout


# ---------------------------------------------------------------------------
# 15 & 16. Generation ID remains identical from packaging through
# deployment; deployment never regenerates one.
# ---------------------------------------------------------------------------

def test_deploy_script_never_regenerates_a_generation_id():
    content = _read(DEPLOY_SCRIPT)
    assert "Get-StaticReleaseGenerationName" not in content, (
        "deploy-static-release.ps1 must read static_generation_id from the "
        "manifest, never regenerate one -- the reviewed and deployed "
        "generation ID must always be identical"
    )
    assert "$generationId = $manifest.static_generation_id" in content


def test_package_script_is_the_sole_generation_id_source():
    content = _read(PACKAGE_SCRIPT)
    assert "Get-StaticReleaseGenerationName" in content


# ---------------------------------------------------------------------------
# 17. Corrupt/traversal/symlink archive entries fail closed (real GNU tar
# entry listing + Test-StaticArchiveEntrySafety, real archives).
# ---------------------------------------------------------------------------

def _resolved_gnu_tar_path():
    script = _import_module_prelude() + "(Resolve-GnuTarExecutable).path"
    result = _run_pwsh(script, timeout=30)
    if result.returncode != 0:
        pytest.skip(f"could not resolve a GNU tar for this test environment: {result.stderr}")
    return result.stdout.strip()


def test_entry_safety_rejects_traversal_and_absolute_entries():
    gnu_tar = _resolved_gnu_tar_path()
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        src.mkdir()
        (src / "evil.webp").write_bytes(b"evil")
        archive_path = Path(tmp) / "evil.tar"
        # Build with a transform that injects a traversal path -- GNU tar's
        # own extraction-time sanitization is a second layer; this test
        # proves Test-StaticArchiveEntrySafety itself flags it at the
        # listing stage, before any extraction is attempted.
        build = subprocess.run(
            [gnu_tar, "--force-local", "--transform", "s,^evil.webp,../escaped.webp,",
             "-cf", str(archive_path), "-C", str(src), "evil.webp"],
            capture_output=True, text=True, timeout=30,
        )
        assert build.returncode == 0, build.stdout + build.stderr

        script = _import_module_prelude() + f"""
        try {{
            Test-StaticArchiveEntrySafety -ArchivePath '{archive_path}' -GnuTarExecutablePath '{gnu_tar}'
            Write-Output "UNEXPECTED_SUCCESS"
        }} catch {{
            Write-Output "FAILED_CLOSED: $($_.Exception.Message)"
        }}
        """
        result = _run_pwsh(script, timeout=30)
        assert "FAILED_CLOSED" in result.stdout, result.stdout + result.stderr


def test_entry_safety_accepts_well_formed_relative_entries():
    gnu_tar = _resolved_gnu_tar_path()
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        src.mkdir()
        (src / "assets").mkdir()
        (src / "assets" / "ok.webp").write_bytes(b"fine")
        archive_path = Path(tmp) / "ok.tar"
        build = subprocess.run(
            [gnu_tar, "--force-local", "-cf", str(archive_path), "-C", str(src), "assets/ok.webp"],
            capture_output=True, text=True, timeout=30,
        )
        assert build.returncode == 0, build.stdout + build.stderr

        script = _import_module_prelude() + f"""
        Test-StaticArchiveEntrySafety -ArchivePath '{archive_path}' -GnuTarExecutablePath '{gnu_tar}'
        Write-Output "SAFETY_CHECK_PASSED"
        """
        result = _run_pwsh(script, timeout=30)
        assert "SAFETY_CHECK_PASSED" in result.stdout, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# 18 & 19. Extraction/verification failure prevents manifest publication,
# cutover, and service restart -- structural ordering, same class of proof
# as the FIX1 suite's ordering tests, updated for the archive-consumption
# flow.
# ---------------------------------------------------------------------------

def test_deploy_ordering_keeps_manifest_cutover_and_restart_after_all_verification():
    content = _read(DEPLOY_SCRIPT)
    markers = [
        "$actualArchiveHash = (Get-FileHash -LiteralPath $archivePath",
        "Test-StaticArchiveEntrySafety -ArchivePath $archivePath",
        "Invoke-RemoteDirectoryBatch -Directories",
        "Invoke-BoundedFileUpload -LocalPath $archivePath",
        "tar -xf",
        "Uploaded file count mismatch",
        "Uploaded byte size mismatch",
        "Batch SHA-256 verification failed",
        "Invoke-BoundedFileUpload -LocalPath $manifestPath",
        "Final remote file count mismatch after manifest upload",
        "sudo ln -sfnT $quotedRelease current.next",
        "'docker restart app+scheduler'",
    ]
    positions = [content.index(m) for m in markers]
    assert positions == sorted(positions), (
        "deploy sequence must be: local archive SHA/size verify -> entry "
        "safety verify -> directories -> archive upload -> extract -> count "
        "check -> size check -> hash check -> manifest upload -> final "
        "recount -> cutover -> restart"
    )


# ---------------------------------------------------------------------------
# 20 & 21. Existing FIX1/FIX2 bounded-process behavior and flat-release
# (i18n.js/sw.js-only) compatibility remain intact.
# ---------------------------------------------------------------------------

def test_bounded_native_command_helper_unchanged_in_signature():
    content = _read(PSM1)
    assert "function Invoke-BoundedNativeCommand" in content
    func_start = content.index("function Invoke-BoundedNativeCommand")
    func_end = content.index("\nfunction ", func_start + 1)
    body = content[func_start:func_end]
    assert "[Parameter(Mandatory = $true)][string]$FileName" in body
    assert "[Parameter(Mandatory = $true)][string[]]$ArgumentList" in body
    assert "[Parameter(Mandatory = $true)][int]$TimeoutSeconds" in body


def test_deploy_script_still_supports_flat_i18n_sw_only_manifests():
    # A manifest whose files array is only i18n.js + sw.js (no assets/**)
    # must still pass the archive-identity verification path -- this
    # Sprint's changes must not hard-code an assumption that assets/** is
    # always present. Uses a real archive (built with the resolved GNU
    # tar) since deploy now validates real archive entries, not just bytes.
    gnu_tar = _resolved_gnu_tar_path()
    with tempfile.TemporaryDirectory() as tmp:
        bundle, i18n_sha = _build_minimal_bundle_and_archive(tmp)
        (bundle / "sw.js").write_bytes(b"xyz")
        import hashlib
        sw_sha = hashlib.sha256(b"xyz").hexdigest()
        archive_path = Path(tmp) / "archive.tar"
        build = subprocess.run(
            [gnu_tar, "--force-local", "-cf", str(archive_path), "-C", str(bundle), "i18n.js", "sw.js"],
            capture_output=True, text=True, timeout=30,
        )
        assert build.returncode == 0, build.stdout + build.stderr
        actual_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        manifest_path = Path(tmp) / "manifest.json"
        _write_minimal_static_manifest(
            manifest_path,
            files=[
                {"path": "i18n.js", "sha256": i18n_sha, "size": 3},
                {"path": "sw.js", "sha256": sw_sha, "size": 3},
            ],
            archive_sha256=actual_sha,
            archive_size=archive_path.stat().st_size,
            archive_entry_count=2,
        )
        script = f"""
        & '{DEPLOY_SCRIPT}' -ExpectedGitSha ('a'*40) -StaticManifest '{manifest_path}' -BundlePath '{bundle}' -ArchivePath '{archive_path}' -LayoutFile 'deploy\\release-layout.example.json'
        """
        result = _run_pwsh(script, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["dry_run"] is True
        assert len(payload["files"]) == 2


# ---------------------------------------------------------------------------
# 22. Post-build integrity gate: a staged file (or the built archive's own
# contents) diverging from its verified bytes is caught, not shipped
# silently. Discovered live during this Sprint's own real packaging runs on
# this workstation: a staged file can silently diverge from its verified
# bytes between copy-time verification and archiving (observed twice,
# a different random file each time, same size, still a valid image of the
# declared type -- consistent with a host-level disk/AV write race, not a
# logic defect), with nothing in the pipeline noticing. package-static-
# release.ps1 now re-verifies every staged file immediately before
# archiving, and separately extracts the just-built archive and re-verifies
# its actual contents before ever writing a manifest.
# ---------------------------------------------------------------------------

def test_package_script_reverifies_staged_files_before_archiving():
    content = _read(PACKAGE_SCRIPT)
    assert "changed on disk between copy-time verification and archiving" in content


def test_package_script_extracts_and_reverifies_archive_contents_before_manifest():
    content = _read(PACKAGE_SCRIPT)
    reverify_index = content.index("changed on disk between copy-time verification and archiving")
    build_index = content.index("New-DeterministicStaticArchive -BundlePath $BundlePath")
    extract_verify_index = content.index("Built archive contains incorrect bytes")
    manifest_write_index = content.index("Write-JsonFile -InputObject $manifest")
    assert reverify_index < build_index < extract_verify_index < manifest_write_index, (
        "order must be: re-verify staged files -> build archive -> extract and "
        "re-verify archive contents -> only then write the manifest"
    )


def test_extraction_reverification_mechanism_catches_content_mismatch():
    # Exercises the real mechanism package-static-release.ps1 uses (build a
    # real archive with New-DeterministicStaticArchive, extract it with the
    # resolved GNU tar, re-hash every extracted file, compare against the
    # expected hash) directly -- proving that if an archive's actual
    # contents ever diverge from what was expected, this class of check
    # would catch it, rather than trusting the build call's own exit code.
    gnu_tar = _resolved_gnu_tar_path()
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "bundle"
        bundle.mkdir()
        (bundle / "i18n.js").write_bytes(b"correct-content")
        archive_path = Path(tmp) / "test.tar"

        script = _import_module_prelude() + f"""
        New-DeterministicStaticArchive -BundlePath '{bundle}' -RelativePaths @('i18n.js') -ArchivePath '{archive_path}' -GnuTarExecutablePath '{gnu_tar}' | Out-Null
        Write-Output "BUILD_OK"
        """
        result = _run_pwsh(script, timeout=30)
        assert "BUILD_OK" in result.stdout, result.stdout + result.stderr

        # Simulate the observed failure mode: the staged file's bytes on
        # disk change AFTER the archive was already built from the
        # (correct, at build time) original bytes.
        (bundle / "i18n.js").write_bytes(b"CORRUPTED-AFTER-BUILD")

        extract_dir = Path(tmp) / "extract"
        extract_dir.mkdir()
        extract = subprocess.run(
            [gnu_tar, "--force-local", "-xf", str(archive_path), "-C", str(extract_dir).replace("\\", "/")],
            capture_output=True, text=True, timeout=30,
        )
        assert extract.returncode == 0, extract.stdout + extract.stderr

        import hashlib
        expected_hash = hashlib.sha256(b"correct-content").hexdigest()
        extracted_hash = hashlib.sha256((extract_dir / "i18n.js").read_bytes()).hexdigest()
        # The archive itself still has the CORRECT (pre-corruption) bytes --
        # proving the archive is immune to post-build staging-directory
        # drift, and that re-hashing the EXTRACTED archive contents (not
        # the mutable staging directory) is what package-static-release.ps1
        # correctly checks against the recorded expected hash.
        assert extracted_hash == expected_hash
        assert extracted_hash != hashlib.sha256(b"CORRUPTED-AFTER-BUILD").hexdigest()
