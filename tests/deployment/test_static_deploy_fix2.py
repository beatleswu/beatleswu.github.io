"""RELEASE-FIX-A2 STATIC DEPLOY FIX2 -- batch static hash verification.

FIX1 solved unbounded native processes and per-directory ssh invocations,
but the real production attempt exposed a second scalability defect: SHA-256
verification still ran one bounded ssh session per manifest file (182 for
the current bundle). One such session -- verifying a small file that
hashes in well under a second -- exceeded its 30s bound while the other 181
succeeded, confirming the one-ssh-per-file architecture itself, not any
single file or a transient network blip, is the reliability problem.

This suite covers the fix: exactly ONE remote `sha256sum --check --strict`
invocation verifies all governed files in one bounded ssh session, fed the
expected hash list via a quoted heredoc embedded in the same script text.
A read-only production diagnostic (see docs/incidents/ note in the PR
description) measured 1.13s wall-clock for this exact operation across the
real 182-file, 53MB bundle -- confirming the batch design is not just safer
but also far faster than 182 sequential sessions.

None of these tests contact production. Corrupted/missing-file detection is
verified by running the exact generated script through a real local `sh`
against a real local temp directory (a genuine "fake remote tree", not a
mock) -- so this exercises the real GNU coreutils sha256sum semantics the
production host also uses, without any network access.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PSM1 = REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "release" / "deploy-static-release.ps1"
HARNESS = REPO_ROOT / "tests" / "deployment" / "static_deploy_fix1_ps_harness.ps1"
REAL_STATIC_MANIFEST = REPO_ROOT / "release-artifacts" / "go-odyssey-app_1b0e5836.static.json"


def _read(path):
    return path.read_text(encoding="utf-8")


def _load_real_manifest():
    text = _read(REAL_STATIC_MANIFEST)
    text = text.lstrip("﻿")
    return json.loads(text)


def _run_ps(command):
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    return result


def _run_harness(scenario, env=None):
    if shutil.which("powershell") is None:
        pytest.skip("powershell not available in this environment")
    full_env = None
    if env:
        full_env = dict(os.environ)
        full_env.update(env)
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HARNESS), "-Scenario", scenario],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, env=full_env,
    )
    return result


def _parse_json(result):
    match = re.search(r"\{.*\}", result.stdout, re.S)
    assert match, f"no JSON found:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    return json.loads(match.group(0))


def _build_deterministic_manifest():
    """Hermetic stand-in for the real production static-release manifest:
    182 files across 22 unique non-root parent directories, matching the
    real bundle's nested/duplicate-parent-prefix shape closely enough to
    exercise genuine ordering/uniqueness/hash-format assertions without
    depending on any pre-existing local, gitignored artifact."""
    directories = [
        "assets/boards", "assets/community", "assets/shop",
        "assets/go_rpg_assets", "assets/go_rpg_assets_v3",
        "assets/guild_bounty_assets", "assets/landing_page_assets",
        "assets/play_page_assets", "assets/rating_test",
        "assets/rating_test/icons", "assets/upgrade_page_assets",
        "assets/monsters", "assets/stats", "assets/storyboards",
        "assets/pets/horse_anim_lv2", "assets/pets/horse_anim_lv3",
        "assets/pets/cat_anim_lv2", "assets/pets/cat_anim_lv3",
        "assets/pets/dragon_anim_lv2", "assets/pets/dragon_anim_lv3",
        "assets/hero/characters", "assets/hero/gear_v2",
    ]
    assert len(directories) == 22
    files = [
        {"path": "i18n.js", "sha256": hashlib.sha256(b"i18n.js-fixture").hexdigest(), "size": 1000},
        {"path": "sw.js", "sha256": hashlib.sha256(b"sw.js-fixture").hexdigest(), "size": 500},
    ]
    remaining = 182 - len(files)
    per_dir, extra = divmod(remaining, len(directories))
    idx = 0
    for d_i, d in enumerate(directories):
        count = per_dir + (1 if d_i < extra else 0)
        for f_i in range(count):
            path = f"{d}/file_{f_i:03d}.webp"
            files.append({
                "path": path,
                "sha256": hashlib.sha256(path.encode()).hexdigest(),
                "size": 1000 + idx,
            })
            idx += 1
    assert len(files) == 182
    return {
        "release_git_sha": "0" * 40,
        "static_generation_id": "hermetic-fixture-generation",
        "asset_count": len(files),
        "files": files,
    }


@pytest.fixture
def real_static_manifest_fixture():
    """Materializes REAL_STATIC_MANIFEST hermetically for the duration of a
    test, replacing the dependency on a pre-existing local, gitignored
    artifact left over from earlier sprints. Backs up and restores any real
    file so this never destroys local data, and leaves no trace in a clean
    worktree."""
    manifest_dir = REAL_STATIC_MANIFEST.parent
    dir_preexisted = manifest_dir.exists()
    file_preexisted = REAL_STATIC_MANIFEST.exists()
    backup = REAL_STATIC_MANIFEST.read_bytes() if file_preexisted else None
    manifest_dir.mkdir(parents=True, exist_ok=True)
    REAL_STATIC_MANIFEST.write_text(json.dumps(_build_deterministic_manifest()), encoding="utf-8")
    try:
        yield REAL_STATIC_MANIFEST
    finally:
        if file_preexisted:
            REAL_STATIC_MANIFEST.write_bytes(backup)
        else:
            REAL_STATIC_MANIFEST.unlink()
            if not dir_preexisted and not any(manifest_dir.iterdir()):
                manifest_dir.rmdir()


# ---------------------------------------------------------------------------
# 1-4: one batch operation, all files exactly once, deterministic order,
# safely validated relative paths
# ---------------------------------------------------------------------------

def test_real_182_file_manifest_produces_one_batch_verification_script(real_static_manifest_fixture):
    manifest = _load_real_manifest()
    command = f"""
    Import-Module '{PSM1}' -Force -DisableNameChecking
    $text = Get-Content -Raw -Encoding UTF8 '{REAL_STATIC_MANIFEST}'
    $text = $text -replace [char]0xFEFF, ''
    $manifest = $text | ConvertFrom-Json
    $script = New-RemoteBatchShaVerificationScript -RemoteReleaseDir '/opt/go-odyssey-static/releases/test-gen' -Files $manifest.files
    # count occurrences of the sha256sum invocation -- must be exactly 1
    $invocationCount = ([regex]::Matches($script, 'sha256sum --check')).Count
    Write-Output "INVOCATIONS=$invocationCount"
    Write-Output "LINES=$((($script -split \"`n\") | Where-Object {{ $_ -match '^[0-9a-f]{{64}}  ' }}).Count)"
    """
    result = _run_ps(command)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "INVOCATIONS=1" in result.stdout
    assert f"LINES={len(manifest['files'])}" in result.stdout


def test_check_input_contains_every_file_exactly_once_in_manifest_order(real_static_manifest_fixture):
    manifest = _load_real_manifest()
    command = f"""
    Import-Module '{PSM1}' -Force -DisableNameChecking
    $text = Get-Content -Raw -Encoding UTF8 '{REAL_STATIC_MANIFEST}'
    $text = $text -replace [char]0xFEFF, ''
    $manifest = $text | ConvertFrom-Json
    $script = New-RemoteBatchShaVerificationScript -RemoteReleaseDir '/root/gen' -Files $manifest.files
    $script | Out-File -FilePath "$env:TEMP\\fix2_script_order.txt" -Encoding utf8 -NoNewline
    """
    result = _run_ps(command)
    assert result.returncode == 0, result.stdout + result.stderr
    script_text = Path(os.environ.get("TEMP", "C:\\Windows\\Temp")) \
        .joinpath("fix2_script_order.txt").read_text(encoding="utf-8")
    lines = [l for l in script_text.split("\n") if re.match(r"^[0-9a-f]{64}  ", l)]
    assert len(lines) == len(manifest["files"])
    expected_order = [f"{f['sha256']}  {f['path']}" for f in manifest["files"]]
    assert lines == expected_order, "check input must preserve exact manifest order"
    paths_seen = [l.split("  ", 1)[1] for l in lines]
    assert len(paths_seen) == len(set(paths_seen)), "every file must appear exactly once"


# ---------------------------------------------------------------------------
# 5-6: filenames with spaces/safe special characters; unsafe paths rejected
# ---------------------------------------------------------------------------

def test_filenames_with_spaces_are_handled_correctly():
    command = f"""
    Import-Module '{PSM1}' -Force -DisableNameChecking
    $files = @([pscustomobject]@{{ path = 'assets/shop/a b (2).webp'; sha256 = 'a'*64 }})
    New-RemoteBatchShaVerificationScript -RemoteReleaseDir '/root/gen' -Files $files
    """
    result = _run_ps(command)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "a b (2).webp" in result.stdout


@pytest.mark.parametrize("bad_path,reason", [
    ("/etc/passwd", "absolute path"),
    ("assets/../../etc/passwd", "traversal"),
    ("", "empty path"),
])
def test_unsafe_paths_rejected_in_verification_script(bad_path, reason):
    escaped = bad_path.replace("'", "''")
    command = f"""
    Import-Module '{PSM1}' -Force -DisableNameChecking
    try {{
        $files = @([pscustomobject]@{{ path = '{escaped}'; sha256 = 'a'*64 }})
        New-RemoteBatchShaVerificationScript -RemoteReleaseDir '/root/gen' -Files $files | Out-Null
        Write-Output 'NOT_REJECTED'
    }} catch {{
        Write-Output 'REJECTED'
    }}
    """
    result = _run_ps(command)
    assert "REJECTED" in result.stdout, f"expected rejection for {reason} ({bad_path!r}): {result.stdout}"


# ---------------------------------------------------------------------------
# 7-9: real sha256sum semantics against a real local temp tree -- corrupted
# file, missing file, and the offending path is identifiable in the output.
# ---------------------------------------------------------------------------

def _sha256_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_fake_remote_tree(tmp_path):
    gen_dir = tmp_path / "gen"
    (gen_dir / "assets" / "shop").mkdir(parents=True)
    files = {
        "i18n.js": b"hello i18n",
        "sw.js": b"service worker content",
        "assets/shop/shop_bg.webp": b"shop background bytes",
    }
    entries = []
    for rel, content in files.items():
        full = gen_dir / rel
        full.write_bytes(content)
        entries.append({"path": rel, "sha256": hashlib.sha256(content).hexdigest()})
    return gen_dir, entries


def _generate_script(remote_dir, entries):
    entries_ps = ",".join(
        f"[pscustomobject]@{{ path = '{e['path']}'; sha256 = '{e['sha256']}' }}" for e in entries
    )
    command = f"""
    Import-Module '{PSM1}' -Force -DisableNameChecking
    $files = @({entries_ps})
    New-RemoteBatchShaVerificationScript -RemoteReleaseDir '{str(remote_dir).replace(chr(92), '/')}' -Files $files
    """
    result = _run_ps(command)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def _run_script_via_real_sh(script_text):
    if shutil.which("sh") is None:
        pytest.skip("sh not available in this environment")
    result = subprocess.run(["sh", "-s"], input=script_text, capture_output=True, text=True, timeout=30)
    return result


def test_success_case_all_files_verify_via_real_sh():
    with tempfile.TemporaryDirectory() as tmp:
        gen_dir, entries = _build_fake_remote_tree(Path(tmp))
        script = _generate_script(gen_dir, entries)
        result = _run_script_via_real_sh(script)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "assets/shop/shop_bg.webp: OK" in result.stdout


def test_corrupted_file_fails_batch_verification_and_identifies_path():
    with tempfile.TemporaryDirectory() as tmp:
        gen_dir, entries = _build_fake_remote_tree(Path(tmp))
        (gen_dir / "assets" / "shop" / "shop_bg.webp").write_bytes(b"CORRUPTED CONTENT")
        script = _generate_script(gen_dir, entries)
        result = _run_script_via_real_sh(script)
        assert result.returncode != 0
        assert "assets/shop/shop_bg.webp: FAILED" in result.stdout


def test_missing_file_fails_batch_verification_and_identifies_path():
    with tempfile.TemporaryDirectory() as tmp:
        gen_dir, entries = _build_fake_remote_tree(Path(tmp))
        (gen_dir / "assets" / "shop" / "shop_bg.webp").unlink()
        script = _generate_script(gen_dir, entries)
        result = _run_script_via_real_sh(script)
        assert result.returncode != 0
        assert "assets/shop/shop_bg.webp" in result.stdout
        assert "FAILED" in result.stdout


# ---------------------------------------------------------------------------
# 10: hung batch verifier is killed by the hard timeout
# ---------------------------------------------------------------------------

def test_hung_batch_verifier_is_killed_by_hard_timeout():
    result = _run_harness("BatchVerificationScriptTextHang", env={"FAKE_SSH_MODE": "hang"})
    payload = _parse_json(result)
    assert payload["result"] == "TIMED_OUT_AS_EXPECTED"
    assert "Timed out after 2s" in payload["error_message"]
    assert payload["elapsed_seconds"] < 5


# ---------------------------------------------------------------------------
# 11-13: hash failure prevents manifest upload, cutover, and service restart
# (structural evidence -- same class of assertion FIX1 used successfully)
# ---------------------------------------------------------------------------

def test_batch_verification_failure_prevents_manifest_upload_cutover_and_restart():
    text = _read(DEPLOY_SCRIPT)
    verify_call = text.index("Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -ScriptText $verificationScript")
    verify_throw = text.index("Batch SHA-256 verification failed")
    manifest_upload = text.index("Invoke-BoundedFileUpload -LocalPath $manifestPath")
    cutover = text.index("sudo ln -sfnT $quotedRelease current.next")
    restart = text.index("'docker restart app+scheduler'")
    assert verify_call < verify_throw < manifest_upload < cutover < restart, (
        "batch verification (and its failure check) must occur, and be able to throw, "
        "strictly before manifest upload, cutover, and restart"
    )


# ---------------------------------------------------------------------------
# 14: flat i18n.js/sw.js release remains compatible
# ---------------------------------------------------------------------------

def test_flat_release_batch_verification_script_covers_both_files():
    command = f"""
    Import-Module '{PSM1}' -Force -DisableNameChecking
    $files = @(
        [pscustomobject]@{{ path = 'i18n.js'; sha256 = 'a'*64 }},
        [pscustomobject]@{{ path = 'sw.js'; sha256 = 'b'*64 }}
    )
    New-RemoteBatchShaVerificationScript -RemoteReleaseDir '/root/gen' -Files $files
    """
    result = _run_ps(command)
    assert result.returncode == 0
    assert result.stdout.count("sha256sum --check") == 1
    assert "  i18n.js" in result.stdout
    assert "  sw.js" in result.stdout


# ---------------------------------------------------------------------------
# 15: no source loop invokes one remote hash command per manifest file
# ---------------------------------------------------------------------------

def test_no_per_file_remote_hash_loop_remains():
    text = _read(DEPLOY_SCRIPT)
    assert 'sha256sum $(Quote-PosixShellArgument $remoteFile)' not in text, (
        "the old per-file `sha256sum <path>` invocation inside a foreach loop must be gone"
    )
    assert "New-RemoteBatchShaVerificationScript" in text
    # exactly one call site for the batch verification per deploy run
    assert text.count("New-RemoteBatchShaVerificationScript -RemoteReleaseDir") == 1


def test_timeout_policy_is_size_aware_with_documented_bounds():
    command = f"""
    Import-Module '{PSM1}' -Force -DisableNameChecking
    Write-Output (Get-BatchVerificationTimeoutSeconds -TotalBytes 100)
    Write-Output (Get-BatchVerificationTimeoutSeconds -TotalBytes 53382238)
    Write-Output (Get-BatchVerificationTimeoutSeconds -TotalBytes (500*1MB))
    """
    result = _run_ps(command)
    assert result.returncode == 0
    values = [int(v) for v in result.stdout.split() if v.strip().isdigit()]
    assert values[0] == 60, "tiny bundle must hit the minimum bound"
    assert 60 <= values[1] <= 300, "real 53MB bundle must fall within documented bounds"
    assert values[2] == 300, "very large bundle must hit the maximum bound"


def test_deploy_script_uses_batch_timeout_not_quick_command_timeout():
    text = _read(DEPLOY_SCRIPT)
    assert "Get-BatchVerificationTimeoutSeconds -TotalBytes $expectedBytes" in text
    assert "-TimeoutSeconds $batchTimeoutSeconds" in text


# ---------------------------------------------------------------------------
# 16-17: existing FIX1 behavior and broader suites remain green
# ---------------------------------------------------------------------------

def test_fix1_directory_batching_still_intact():
    text = _read(DEPLOY_SCRIPT)
    assert "Invoke-RemoteDirectoryBatch -Directories $requiredDirectories" in text
    dir_batch_index = text.index("Invoke-RemoteDirectoryBatch -Directories")
    # RELEASE-FIX-A3: the per-file upload loop was replaced with a single
    # deterministic archive upload -- that's now the first upload.
    upload_index = text.index("Invoke-BoundedFileUpload -LocalPath $archivePath")
    verify_index = text.index("New-RemoteBatchShaVerificationScript")
    assert dir_batch_index < upload_index < verify_index


def test_existing_fix1_and_release_suites_still_pass():
    result = subprocess.run(
        ["python", "-m", "pytest",
         "tests/deployment/test_static_deploy_fix1.py",
         "tests/deployment/test_static_release_tooling.py",
         "-q"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_static_deploy_fixes_pass_in_clean_worktree_without_release_artifacts():
    """EXPAND_DEPLOYMENT_GATE_FIX regression guard: the two fixture-generated
    deployment tests (fix1's directory-derivation test, fix2's two
    real-manifest tests) must pass in a fresh git worktree that starts with
    no release-artifacts/ directory at all -- the exact condition
    build-release-image.ps1's detached worktree is always in, which is what
    exposed the original Category C hermeticity gap."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    holder = Path(tempfile.mkdtemp(prefix="hermeticity-check-"))
    worktree_path = holder / "wt"
    try:
        add = subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree_path), head],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
        assert add.returncode == 0, add.stdout + add.stderr
        assert not (worktree_path / "release-artifacts").exists(), (
            "test setup invariant broken: a fresh worktree must not have release-artifacts/"
        )
        result = subprocess.run(
            [sys.executable, "-m", "pytest",
             "tests/deployment/test_static_deploy_fix1.py::test_parent_directory_derivation_and_dedup_and_ordering",
             "tests/deployment/test_static_deploy_fix2.py::test_real_182_file_manifest_produces_one_batch_verification_script",
             "tests/deployment/test_static_deploy_fix2.py::test_check_input_contains_every_file_exactly_once_in_manifest_order",
             "-q"],
            cwd=str(worktree_path), capture_output=True, text=True, timeout=180,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert not (worktree_path / "release-artifacts").exists(), (
            "fixtures must clean up after themselves, leaving no release-artifacts/ directory behind"
        )
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        shutil.rmtree(holder, ignore_errors=True)


def test_powershell_scripts_still_parse():
    for script in [DEPLOY_SCRIPT, PSM1]:
        ps_check = f"""
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$null, [ref]$errors) | Out-Null
        if ($errors.Count -gt 0) {{ $errors | ForEach-Object {{ Write-Output $_.ToString() }}; exit 1 }}
        """
        result = _run_ps(ps_check)
        assert result.returncode == 0, f"{script} failed to parse:\n{result.stdout}\n{result.stderr}"
