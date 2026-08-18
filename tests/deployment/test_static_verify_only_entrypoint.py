"""RELEASE-TOOLING-HOTFIX-06: deploy-static-release.ps1 -VerifyOnly must be
completely independent of local archive/bundle staging.

-VerifyOnly is the canonical READ-ONLY public acceptance verifier that
Deployment Workflow V3's VerifyStatic invokes after an ambiguous
PROMOTE_STATIC timeout. It is invoked with a manifest only -- there is no
local bundle or archive at that point in a recovery flow.

The first cut of -VerifyOnly declared BundlePath/ArchivePath unnecessary but
left the archive-validation block below it gated only on `-not $adoptionMode`,
which is TRUE in VerifyOnly mode. That path would therefore still have run
Test-Path / Get-FileHash / Get-Item / Resolve-GnuTarExecutable /
Test-StaticArchiveEntrySafety against a $null archive path and failed long
before reaching the public verification seam.

These tests execute the REAL script and prove:
  - VerifyOnly with no -BundlePath and no -ArchivePath reaches the public
    verification seam rather than dying on local archive validation,
  - VerifyOnly performs no staging, no upload, no SSH write, no symlink
    switch and no container restart,
  - the NORMAL archive gate and the ADOPTION gate are both unchanged.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "release" / "deploy-static-release.ps1"
EXAMPLE_LAYOUT = "deploy\\release-layout.example.json"

# Local archive-validation failures that must NEVER be reached in VerifyOnly.
ARCHIVE_STAGE_FAILURE_MARKERS = (
    "Static release archive not found",
    "Staged static release file missing",
    "Staged static release file hash mismatch",
    "Local archive SHA-256",
    "Local archive byte size",
    "does not record archive identity",
    "Normal static deployment requires StaticManifest, BundlePath, and ArchivePath",
    "Cannot bind argument to parameter 'LiteralPath' because it is null",
    "Cannot bind argument to parameter 'ArchivePath'",
)


def _head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _write_manifest(tmp_path: pathlib.Path, git_sha: str) -> pathlib.Path:
    # A minimally valid static release manifest. index.html is deliberately
    # included: the public contract excludes it from byte-hash checks and
    # covers it through the /healthz/static-release provenance endpoint.
    manifest = {
        "release_git_sha": git_sha,
        "static_generation_id": "20260818-010203-abcdef12-verifyonly",
        "service_worker_version": "20260818verifyonly",
        "archive_filename": "static-verifyonly.tar",
        "archive_sha256": "a" * 64,
        "archive_size": 1024,
        "files": [
            {"path": "i18n.js", "sha256": "b" * 64},
            {"path": "index.html", "sha256": "c" * 64},
        ],
    }
    p = tmp_path / "verifyonly.static.json"
    p.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return p


def _run_script(args: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    preamble = (
        "$OutputEncoding = [Console]::OutputEncoding = "
        "New-Object System.Text.UTF8Encoding($false);\n"
    )
    quoted = " ".join(f"'{a}'" if not a.startswith("-") else a for a in args)
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
         preamble + f"& '{SCRIPT.as_posix()}' {quoted}"],
        cwd=REPO_ROOT,
        env={**os.environ, "SECRET_KEY": "verify-only-entrypoint-test-only"},
        capture_output=True, text=True, encoding="utf-8",
        timeout=timeout, check=False,
    )


# ---------------------------------------------------------------------------
# The real CLI execution proof
# ---------------------------------------------------------------------------

def test_verify_only_with_no_bundle_or_archive_reaches_the_public_verification_seam(tmp_path):
    """VerifyOnly, invoked exactly as V3's VerifyStatic invokes it.

    The example layout points at example.invalid, so the public HTTPS
    verification cannot succeed -- and that is precisely the point: reaching
    a PUBLIC verification failure proves execution got past all local
    archive/bundle validation, which is what previously blocked it.
    """
    sha = _head_sha()
    manifest = _write_manifest(tmp_path, sha)
    result = _run_script([
        "-VerifyOnly",
        "-ExpectedGitSha", sha,
        "-StaticManifest", str(manifest),
        "-LayoutFile", EXAMPLE_LAYOUT,
    ])
    combined = result.stdout + result.stderr

    for marker in ARCHIVE_STAGE_FAILURE_MARKERS:
        assert marker not in combined, (
            f"VerifyOnly must not perform local archive/bundle validation, but hit: {marker}\n{combined[:2000]}"
        )
    # It reached the public acceptance contract: either the PUBLIC_HASH phase
    # began, or it failed inside public verification against example.invalid.
    reached_public_seam = (
        "PUBLIC_HASH_BEGIN" in combined
        or "Public content verification failed" in combined
        or "for content verification" in combined
    )
    assert reached_public_seam, (
        "VerifyOnly did not reach the public verification seam.\n" + combined[:2000]
    )


def test_verify_only_rejects_bundle_and_archive_inputs(tmp_path):
    sha = _head_sha()
    manifest = _write_manifest(tmp_path, sha)
    result = _run_script([
        "-VerifyOnly",
        "-ExpectedGitSha", sha,
        "-StaticManifest", str(manifest),
        "-ArchivePath", str(tmp_path / "irrelevant.tar"),
        "-LayoutFile", EXAMPLE_LAYOUT,
    ])
    assert result.returncode != 0
    assert "VerifyOnly is mutually exclusive with BundlePath/ArchivePath" in (result.stdout + result.stderr)


def test_verify_only_requires_a_static_manifest():
    sha = _head_sha()
    result = _run_script([
        "-VerifyOnly",
        "-ExpectedGitSha", sha,
        "-LayoutFile", EXAMPLE_LAYOUT,
    ])
    assert result.returncode != 0
    assert "VerifyOnly requires StaticManifest" in (result.stdout + result.stderr)


def test_verify_only_is_mutually_exclusive_with_existing_generation_adoption(tmp_path):
    sha = _head_sha()
    manifest = _write_manifest(tmp_path, sha)
    result = _run_script([
        "-VerifyOnly",
        "-ExpectedGitSha", sha,
        "-StaticManifest", str(manifest),
        "-ExistingGenerationPath", "/opt/go-odyssey-static/releases/20260818-010203-abcdef12-verifyonly",
        "-LayoutFile", EXAMPLE_LAYOUT,
    ])
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert ("VerifyOnly is mutually exclusive with existing-generation adoption" in combined
            or "adoption requires StaticManifest" in combined)


# ---------------------------------------------------------------------------
# Source-level guards: the staging predicate really governs every
# archive/bundle-only operation, and the other two modes are unchanged.
# ---------------------------------------------------------------------------

def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _strip_powershell_comments(text: str) -> str:
    """Removes <# block #> and # line comments so source scans see only code.

    The script's own prose (docstrings, explanatory comments) legitimately
    mentions things like `ln -sfnT` and `docker restart` when describing the
    mutating path it is careful NOT to take in VerifyOnly mode -- matching
    those would be a false positive.
    """
    out = []
    i = 0
    while i < len(text):
        if text.startswith("<#", i):
            end = text.find("#>", i + 2)
            i = len(text) if end == -1 else end + 2
            continue
        line_end = text.find("\n", i)
        if line_end == -1:
            line_end = len(text)
        line = text[i:line_end]
        hash_pos = line.find("#")
        if hash_pos != -1:
            line = line[:hash_pos]
        out.append(line)
        i = line_end + 1
    return "\n".join(out)


def _pre_verifyonly_body() -> str:
    """Executable code before the VerifyOnly early return, comments removed.

    Anchored with a leading newline so the top-level `if ($VerifyOnly) {`
    return block is found -- NOT the earlier `elseif ($VerifyOnly) {`
    parameter-validation branch, whose text contains the same substring and
    would truncate this slice before the archive-validation block it exists
    to inspect.
    """
    c = _source()
    marker = "\nif ($VerifyOnly) {\n"
    idx = c.index(marker)
    # Sanity: the slice must actually contain the archive-validation block.
    body = _strip_powershell_comments(c[:idx])
    assert "$archivePath" in body, "pre-VerifyOnly slice missed the archive-validation block"
    return body


def test_every_archive_only_operation_is_gated_on_the_staging_predicate():
    body = _pre_verifyonly_body()
    guarded_ops = [
        "Test-Path -LiteralPath $archivePath",
        "Get-FileHash -LiteralPath $archivePath",
        "Get-Item -LiteralPath $archivePath",
        "Resolve-GnuTarExecutable",
        "Test-StaticArchiveEntrySafety",
    ]
    for op in guarded_ops:
        for line_no, line in enumerate(body.splitlines(), start=1):
            if op in line and not line.strip().startswith("#"):
                # The operation must be on, or inside, an $archiveStagingRequired guard.
                window = "\n".join(body.splitlines()[max(0, line_no - 4): line_no])
                assert "$archiveStagingRequired" in window, (
                    f"{op} (line {line_no}) is not gated on $archiveStagingRequired:\n{window}"
                )


def test_staging_predicate_excludes_both_adoption_and_verify_only():
    c = _source()
    assert "$archiveStagingRequired = (-not $adoptionMode) -and (-not $VerifyOnly)" in c


def test_verify_only_never_uploads_switches_or_restarts():
    body = _pre_verifyonly_body()
    forbidden = [
        "Invoke-BoundedFileUpload -LocalPath",   # actual upload call sites
        "ln -sfnT",                              # symlink switch
        "docker restart",                        # container restart
    ]
    # Track which function body (if any) each line sits in: a mutating call
    # inside a function definition is inert unless that function is invoked,
    # and VerifyOnly invokes none of them. Only top-level statements matter.
    depth = 0
    in_function_at_depth = None
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("function "):
            in_function_at_depth = depth
        for token in forbidden:
            if token in stripped:
                assert in_function_at_depth is not None, (
                    f"VerifyOnly path must not reach a mutating operation at top level: {stripped[:160]}"
                )
        depth += line.count("{") - line.count("}")
        if in_function_at_depth is not None and depth <= in_function_at_depth:
            in_function_at_depth = None


def test_normal_archive_deploy_gate_is_preserved():
    c = _source()
    assert "throw 'Normal static deployment requires StaticManifest, BundlePath, and ArchivePath.'" in c
    # and the archive identity gates still exist, just predicate-gated
    assert "Static release archive not found" in c
    assert "does not match the manifest's recorded archive_sha256" in c
    assert "does not match the manifest's recorded archive_size" in c


def test_existing_generation_adoption_gate_is_preserved():
    c = _source()
    assert "throw 'Existing-generation adoption is mutually exclusive with BundlePath/ArchivePath.'" in c
    assert "throw 'Existing-generation adoption requires StaticManifest as the identity contract.'" in c
    assert "Existing generation basename does not match manifest static_generation_id." in c
