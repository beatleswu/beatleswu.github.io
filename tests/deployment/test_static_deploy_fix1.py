"""RELEASE-FIX-A2 STATIC DEPLOY FIX1.

Root cause: the original deploy-static-release.ps1 only ever created the
top-level generation directory via `mkdir -p`, then scp'd each manifest
file directly to its destination. scp does not create intermediate remote
directories -- fine for the historical flat i18n.js/sw.js-only manifest,
but RELEASE-FIX-A2 introduced nested governed paths under assets/**, and
the first real deploy attempt failed immediately on the first nested file
(`assets/community/panel_wood.webp`: "No such file or directory"). A
temporary per-directory `ssh ... "mkdir -p ..."` fix uploaded 85/182 files
successfully before one such ssh invocation hung for ~15 minutes with an
established TCP connection and near-zero CPU -- confirmed NOT a network,
host, or credential failure (an independent SSH probe succeeded in 0.7s
while the original child remained stuck) -- but the deploy script itself
had no bounded timeout on any native ssh/scp process, so a stalled client
process could not be distinguished from real work in progress.

This suite covers the fix: a single batched remote mkdir (not one ssh
invocation per directory), a hard process-level timeout on every ssh/scp
call (bounded independently of SSH protocol keepalive options), and
preserved fail-closed ordering (manifest.json uploads last, only after
count/size/hash verification; cutover and service restart never run on
any upload/verification failure).

None of these tests connect to production. Fake ssh/scp executables
(tests/fixtures/fake_ssh/{ssh,scp}.cmd) simulate hang/fail/success without
any network access.
"""
import json
import re
import subprocess
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PSM1 = REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "release" / "deploy-static-release.ps1"
ROLLBACK_SCRIPT = REPO_ROOT / "scripts" / "release" / "rollback-static-release.ps1"
PACKAGE_SCRIPT = REPO_ROOT / "scripts" / "release" / "package-static-release.ps1"
HARNESS = REPO_ROOT / "tests" / "deployment" / "static_deploy_fix1_ps_harness.ps1"
REAL_STATIC_MANIFEST = REPO_ROOT / "release-artifacts" / "go-odyssey-app_e5efe34f.static.json"


def _read(path):
    return path.read_text(encoding="utf-8")


def _run_harness(scenario, env=None):
    if shutil.which("powershell") is None:
        pytest.skip("powershell not available in this environment")
    full_env = None
    if env:
        import os
        full_env = dict(os.environ)
        full_env.update(env)
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HARNESS), "-Scenario", scenario],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, env=full_env,
    )
    return result


def _parse_harness_json(result):
    # The harness may print noise (e.g. a thrown-error rethrow) before/after
    # the JSON payload; find the JSON object.
    match = re.search(r"\{.*\}", result.stdout, re.S)
    assert match, f"no JSON found in harness output:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    return json.loads(match.group(0))


# ---------------------------------------------------------------------------
# 1-3: nested parent-directory derivation, dedup, deterministic ordering
# ---------------------------------------------------------------------------

def test_parent_directory_derivation_and_dedup_and_ordering():
    result = _run_harness("RealManifestSingleMkdirOperation")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = _parse_harness_json(result)
    assert payload["file_count"] == 182
    assert payload["unique_directory_count"] == 23
    assert payload["ssh_mkdir_operation_count"] == 1
    assert payload["exit_code"] == 0


def test_nested_path_examples_produce_correct_directories():
    script = f"""
    Import-Module '{PSM1}' -Force -DisableNameChecking
    $dirs = Get-RemoteParentDirectorySet -RelativePaths @(
        'assets/shop/shop_bg.webp',
        'assets/pets/horse_anim_lv3/01_idle.webp',
        'assets/storyboards/zone_1/scene.webp'
    ) -RemoteReleaseDir '/root/gen1'
    $dirs | ConvertTo-Json
    """
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    dirs = json.loads(result.stdout)
    assert set(dirs) == {
        "/root/gen1",
        "/root/gen1/assets/shop",
        "/root/gen1/assets/pets/horse_anim_lv3",
        "/root/gen1/assets/storyboards/zone_1",
    }
    # deterministic ordering: sorted
    assert dirs == sorted(dirs)


def test_multiple_files_same_directory_dedup_to_one_entry():
    script = f"""
    Import-Module '{PSM1}' -Force -DisableNameChecking
    $dirs = Get-RemoteParentDirectorySet -RelativePaths @('assets/shop/a.webp','assets/shop/b.webp','assets/shop/c.webp') -RemoteReleaseDir '/root'
    $dirs | ConvertTo-Json
    """
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    dirs = json.loads(result.stdout)
    if isinstance(dirs, str):
        dirs = [dirs]
    assert set(dirs) == {"/root", "/root/assets/shop"}


# ---------------------------------------------------------------------------
# 4-5: directories created before upload; no per-directory SSH loop
# ---------------------------------------------------------------------------

def test_deploy_script_creates_directories_before_first_upload():
    text = _read(DEPLOY_SCRIPT)
    dir_batch_index = text.index("Invoke-RemoteDirectoryBatch -Directories")
    # RELEASE-FIX-A3 replaced the per-file upload loop with a single
    # deterministic-archive upload (see New-DeterministicStaticArchive) --
    # the first upload is now the archive itself, not a per-file $localFile.
    first_upload_index = text.index("Invoke-BoundedFileUpload -LocalPath $localArchivePath")
    assert dir_batch_index < first_upload_index, (
        "all required remote directories must be created before the first file upload begins"
    )


def test_deploy_script_does_not_loop_ssh_mkdir_per_directory():
    text = _read(DEPLOY_SCRIPT)
    assert "foreach ($entry in $manifest.files)" in text  # the upload loop itself still exists
    # the specific per-directory mkdir-in-upload-loop pattern from the
    # original incident and the temporary fix must both be gone
    assert "mkdir -p $(Quote-PosixShellArgument $remoteParentDir)" not in text
    assert "$remoteDirsEnsured" not in text
    assert "Invoke-RemoteDirectoryBatch" in text


def test_directory_batch_uses_single_scripttext_ssh_session():
    text = _read(PSM1)
    func_start = text.index("function New-RemoteMkdirScriptText")
    func_body = text[func_start:func_start + 800]
    assert "mkdir -p" in func_body
    deploy_text = _read(DEPLOY_SCRIPT)
    batch_func_start = deploy_text.index("function Invoke-RemoteDirectoryBatch")
    batch_func_body = deploy_text[batch_func_start:batch_func_start + 800]
    assert "Invoke-BoundedSshCommand" in batch_func_body
    assert "-ScriptText $script" in batch_func_body
    # exactly one Invoke-BoundedSshCommand call inside this function
    assert batch_func_body.count("Invoke-BoundedSshCommand") == 1


# ---------------------------------------------------------------------------
# 6: flat-release compatibility (i18n.js + sw.js only)
# ---------------------------------------------------------------------------

def test_flat_release_still_produces_valid_directory_set():
    script = f"""
    Import-Module '{PSM1}' -Force -DisableNameChecking
    $dirs = Get-RemoteParentDirectorySet -RelativePaths @('i18n.js','sw.js') -RemoteReleaseDir '/root/gen'
    $dirs | ConvertTo-Json
    """
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    dirs = json.loads(result.stdout)
    if isinstance(dirs, str):
        dirs = [dirs]
    assert dirs == ["/root/gen"], "a flat release must need only the generation root directory, no nested mkdir work"


# ---------------------------------------------------------------------------
# 7: path safety
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_path,reason", [
    ("/etc/passwd", "absolute path"),
    ("assets/../../etc/passwd", "traversal"),
    ("", "empty path"),
    ("assets//double/slash.webp", "empty segment / doubled slash"),
    (r"C:\Windows\file.webp", "drive-absolute path"),
])
def test_unsafe_paths_are_rejected(bad_path, reason):
    escaped = bad_path.replace("'", "''")
    script = f"""
    Import-Module '{PSM1}' -Force -DisableNameChecking
    try {{
        Get-RemoteParentDirectorySet -RelativePaths @('{escaped}') -RemoteReleaseDir '/root' | Out-Null
        Write-Output 'NOT_REJECTED'
    }} catch {{
        Write-Output 'REJECTED'
    }}
    """
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert "REJECTED" in result.stdout, f"expected rejection for {reason} ({bad_path!r}): {result.stdout}"


# ---------------------------------------------------------------------------
# 8-9: bounded SSH/SCP options + hard timeout
# ---------------------------------------------------------------------------

def test_ssh_commands_include_required_bounded_options():
    script = f"""
    Import-Module '{PSM1}' -Force -DisableNameChecking
    Get-BoundedSshOptionArguments | ConvertTo-Json
    """
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    options = " ".join(json.loads(result.stdout))
    assert "BatchMode=yes" in options
    assert re.search(r"ConnectTimeout=\d+", options)
    assert "ConnectionAttempts=1" in options
    assert re.search(r"ServerAliveInterval=\d+", options)
    assert re.search(r"ServerAliveCountMax=\d+", options)


def test_scp_upload_uses_the_same_bounded_options():
    text = _read(PSM1)
    func_start = text.index("function Invoke-BoundedScpUpload")
    func_body = text[func_start:func_start + 1200]
    assert "Get-BoundedSshOptionArguments" in func_body
    assert "TimeoutSeconds" in func_body


def test_bounded_native_command_requires_positive_timeout():
    script = f"""
    Import-Module '{PSM1}' -Force -DisableNameChecking
    try {{
        Invoke-BoundedNativeCommand -FileName 'cmd' -ArgumentList @('/c','echo hi') -TimeoutSeconds 0 -OperationLabel 'test' | Out-Null
        Write-Output 'NOT_REJECTED'
    }} catch {{
        Write-Output 'REJECTED'
    }}
    """
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert "REJECTED" in result.stdout


def test_hard_timeout_kills_hung_native_process_real_execution():
    result = _run_harness("TimeoutKillsHungProcess")
    payload = _parse_harness_json(result)
    assert payload["result"] == "TIMED_OUT_AS_EXPECTED"
    assert "Timed out after 2s" in payload["error_message"]
    assert payload["elapsed_seconds"] < 5, "must not wait anywhere near the process's own 999s sleep"


def test_bounded_ssh_command_success_via_fake_executable():
    result = _run_harness("BoundedSshSuccess")
    payload = _parse_harness_json(result)
    assert payload["exit_code"] == 0
    assert "fake ssh: ok" in payload["output"]


def test_bounded_ssh_command_failure_via_fake_executable():
    result = _run_harness("BoundedSshFail", env={"FAKE_SSH_MODE": "fail"})
    payload = _parse_harness_json(result)
    assert payload["exit_code"] != 0
    assert "simulated remote command failure" in payload["output"]


def test_bounded_ssh_scripttext_stdin_delivery_via_fake_executable():
    result = _run_harness("BoundedSshScriptTextSuccess")
    payload = _parse_harness_json(result)
    assert payload["exit_code"] == 0
    assert payload["script_sent"].startswith("mkdir -p ")
    assert "'/root/gen1'" in payload["script_sent"]


def test_bounded_scp_upload_success_and_failure_via_fake_executable():
    ok = _parse_harness_json(_run_harness("BoundedScpSuccess"))
    assert ok["exit_code"] == 0
    fail = _parse_harness_json(_run_harness("BoundedScpFail", env={"FAKE_SCP_MODE": "fail"}))
    assert fail["exit_code"] != 0


# ---------------------------------------------------------------------------
# 10: simulated hung SSH must stop the deployment before any downstream step
# (the core mechanism is proven directly above; here we assert the deploy
# script's structural ordering guarantees no downstream step is reachable
# once any upload-phase step throws).
# ---------------------------------------------------------------------------

def test_deploy_script_structural_ordering_prevents_downstream_work_on_failure():
    text = _read(DEPLOY_SCRIPT)
    # every phase must appear, in this exact order, inside the same try block.
    # RELEASE-FIX-A3 replaced the per-file upload loop with one deterministic
    # archive build + upload + remote extract (New-DeterministicStaticArchive
    # / "tar -xf"), so those two markers replace the old $localFile loop --
    # everything downstream of the upload phase is otherwise unchanged.
    markers = [
        "Invoke-RemoteDirectoryBatch -Directories",
        "New-DeterministicStaticArchive -BundlePath $bundlePath",
        "Invoke-BoundedFileUpload -LocalPath $localArchivePath",
        "tar -xf",
        "Uploaded file count mismatch",
        "Uploaded byte size mismatch",
        "Batch SHA-256 verification failed",
        "Invoke-BoundedFileUpload -LocalPath $manifestPath",
        "Final remote file count mismatch after manifest upload",
        "sudo ln -sfnT $quotedRelease current.next",
        "'docker restart app+scheduler'",
    ]
    positions = [text.index(m) for m in markers]
    assert positions == sorted(positions), (
        "deploy sequence must be: directories -> archive build -> archive upload -> "
        "remote extract -> count check -> size check -> hash check -> manifest upload -> "
        "final recount -> cutover -> restart, with no step reachable before an earlier one throws"
    )


def test_all_remote_calls_in_try_block_are_bounded_not_raw_native_calls():
    text = _read(DEPLOY_SCRIPT)
    try_start = text.index("try {")
    catch_start = text.index("catch {")
    try_block = text[try_start:catch_start]
    assert "& scp " not in try_block, "no raw unbounded `& scp` call may remain in the deploy try block"
    assert "& ssh " not in try_block, "no raw unbounded `& ssh` call may remain in the deploy try block"


# ---------------------------------------------------------------------------
# 11-12: simulated failed directory creation / failed scp stop before
# downstream work (structural evidence + real fail-closed bundle re-verify
# behavior, already covered by test_static_release_tooling.py's fail-closed
# tests for New-StaticReleaseBundle -- this suite adds the deploy-script-
# level ordering guarantee).
# ---------------------------------------------------------------------------

def test_directory_batch_failure_raises_before_any_upload_attempted():
    text = _read(DEPLOY_SCRIPT)
    batch_call = text.index("Invoke-RemoteDirectoryBatch -Directories $requiredDirectories")
    # RELEASE-FIX-A3: the first upload is the single deterministic archive,
    # not a per-file loop.
    first_upload = text.index("Invoke-BoundedFileUpload -LocalPath $localArchivePath")
    assert batch_call < first_upload
    # Invoke-RemoteDirectoryBatch itself throws on nonzero exit code
    func_text = _read(DEPLOY_SCRIPT)
    func_start = func_text.index("function Invoke-RemoteDirectoryBatch")
    func_end = func_text.index("\nfunction ", func_start + 1)
    func_body = func_text[func_start:func_end]
    assert "throw" in func_body


def test_scp_failure_raises_before_manifest_upload():
    text = _read(DEPLOY_SCRIPT)
    func_start = text.index("function Invoke-BoundedFileUpload")
    func_end = text.index("\nfunction ", func_start + 1)
    func_body = text[func_start:func_end]
    assert "throw" in func_body
    # RELEASE-FIX-A3: the governed files travel inside the single archive
    # upload, not a per-file loop -- the archive upload must still precede
    # the manifest upload.
    archive_upload = text.index("Invoke-BoundedFileUpload -LocalPath $localArchivePath")
    manifest_upload = text.index("Invoke-BoundedFileUpload -LocalPath $manifestPath")
    assert archive_upload < manifest_upload


# ---------------------------------------------------------------------------
# 13-14: partial generation safety + manifest-last behavior
# ---------------------------------------------------------------------------

def test_manifest_uploaded_only_after_count_size_hash_verification():
    text = _read(DEPLOY_SCRIPT)
    count_check = text.index("Uploaded file count mismatch")
    size_check = text.index("Uploaded byte size mismatch")
    hash_check = text.index("Batch SHA-256 verification failed")
    manifest_upload = text.index("Invoke-BoundedFileUpload -LocalPath $manifestPath")
    assert count_check < manifest_upload
    assert size_check < manifest_upload
    assert hash_check < manifest_upload


def test_rollback_and_preflight_treat_manifest_as_sole_generation_truth():
    rollback_text = _read(ROLLBACK_SCRIPT)
    assert "manifest.json" in rollback_text
    preflight_text = _read(REPO_ROOT / "scripts" / "release" / "preflight-production.ps1")
    assert "manifest.json" in preflight_text or "StaticManifest" in preflight_text


# ---------------------------------------------------------------------------
# 15: existing release behavior unaffected
# ---------------------------------------------------------------------------

def test_existing_static_release_tooling_tests_still_pass():
    result = subprocess.run(
        ["python", "-m", "pytest", "tests/deployment/test_static_release_tooling.py", "-q"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_powershell_scripts_still_parse():
    for script in [DEPLOY_SCRIPT, ROLLBACK_SCRIPT, PACKAGE_SCRIPT, PSM1]:
        ps_check = f"""
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$null, [ref]$errors) | Out-Null
        if ($errors.Count -gt 0) {{ $errors | ForEach-Object {{ Write-Output $_.ToString() }}; exit 1 }}
        """
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_check],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"{script} failed to parse:\n{result.stdout}\n{result.stderr}"
