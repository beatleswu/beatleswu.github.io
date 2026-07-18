import json
import pathlib
import subprocess
import time

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
BUILD_RELEASE = ROOT / "scripts" / "release" / "build-release-image.ps1"
BUILD_PRODUCTION = ROOT / "scripts" / "build-production-image.ps1"


def run_powershell(script, timeout=30):
    utf8_preamble = (
        "$OutputEncoding = [Console]::OutputEncoding = "
        "New-Object System.Text.UTF8Encoding($false);\n"
    )
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            utf8_preamble + script,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )


def ps_quote(path):
    return str(path).replace("'", "''")


def parse_last_json(stdout):
    return json.loads(stdout.strip().splitlines()[-1])


def test_bounded_child_uses_explicit_worktree_not_ambient_current_directory(tmp_path):
    ambient = tmp_path / "unrelated ambient"
    worktree = tmp_path / "synthetic worktree"
    ambient.mkdir()
    worktree.mkdir()
    module = ps_quote(MODULE)
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{module}' -Force -DisableNameChecking
$old = [Environment]::CurrentDirectory
try {{
    [Environment]::CurrentDirectory = '{ps_quote(ambient)}'
    $result = Invoke-BoundedNativeCommand -FileName 'powershell.exe' -ArgumentList @('-NoProfile','-Command','[Environment]::CurrentDirectory') -WorkingDirectory '{ps_quote(worktree)}' -RequireWorkingDirectory -TimeoutSeconds 15 -OperationLabel 'synthetic isolated build child'
    [ordered]@{{ child_cwd=$result.output; ambient=[Environment]::CurrentDirectory }} | ConvertTo-Json -Compress
}}
finally {{ [Environment]::CurrentDirectory = $old }}
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = parse_last_json(result.stdout)
    assert pathlib.Path(payload["child_cwd"]) == worktree
    assert pathlib.Path(payload["ambient"]) == ambient


@pytest.mark.parametrize("directory_name", ("worktree with spaces", "工作樹-unicode"))
def test_valid_absolute_working_directory_supports_spaces_and_unicode(
    tmp_path, directory_name
):
    worktree = tmp_path / directory_name
    worktree.mkdir()
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
$result = Invoke-BoundedNativeCommand -FileName 'powershell.exe' -ArgumentList @('-NoProfile','-Command','[Environment]::CurrentDirectory') -WorkingDirectory '{ps_quote(worktree)}' -RequireWorkingDirectory -TimeoutSeconds 15 -OperationLabel 'path compatibility probe'
$result | ConvertTo-Json -Compress
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = parse_last_json(result.stdout)
    assert pathlib.Path(payload["output"]) == worktree


@pytest.mark.parametrize(
    "case",
    ("missing", "blank", "relative", "nonexistent", "file"),
)
def test_invalid_required_working_directory_fails_before_child_execution(
    tmp_path, case
):
    valid_dir = tmp_path / "valid"
    valid_dir.mkdir()
    file_path = tmp_path / "not-a-directory.txt"
    file_path.write_text("synthetic", encoding="utf-8")
    marker = tmp_path / "child-executed.txt"
    child = tmp_path / "child.ps1"
    child.write_text(
        f"Set-Content -LiteralPath '{ps_quote(marker)}' -Value executed",
        encoding="utf-8",
    )
    working_directory_argument = {
        "missing": "",
        "blank": "-WorkingDirectory ''",
        "relative": "-WorkingDirectory 'relative-path'",
        "nonexistent": f"-WorkingDirectory '{ps_quote(tmp_path / 'missing')}'",
        "file": f"-WorkingDirectory '{ps_quote(file_path)}'",
    }[case]
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
try {{
    Invoke-BoundedNativeCommand -FileName 'powershell.exe' -ArgumentList @('-NoProfile','-File','{ps_quote(child)}') {working_directory_argument} -RequireWorkingDirectory -TimeoutSeconds 15 -OperationLabel 'working directory validation probe' | Out-Null
    [ordered]@{{ failed_closed=$false; message='' }} | ConvertTo-Json -Compress
}}
catch {{
    [ordered]@{{ failed_closed=$true; message=$_.Exception.Message }} | ConvertTo-Json -Compress
}}
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = parse_last_json(result.stdout)
    assert payload["failed_closed"] is True
    assert "working directory" in payload["message"].lower()
    assert not marker.exists()


def test_missing_native_command_fails_before_execution_and_redacts_arguments(tmp_path):
    secret_argument = "synthetic-secret-argument"
    secret_stdin = "synthetic-secret-stdin"
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
try {{
    Invoke-BoundedNativeCommand -FileName 'definitely-missing-native-command.exe' -ArgumentList @('{secret_argument}') -StdinText '{secret_stdin}' -WorkingDirectory '{ps_quote(tmp_path)}' -RequireWorkingDirectory -TimeoutSeconds 15 -OperationLabel 'redacted command resolution probe' | Out-Null
    [ordered]@{{ failed_closed=$false; message='' }} | ConvertTo-Json -Compress
}}
catch {{
    [ordered]@{{ failed_closed=$true; message=$_.Exception.Message }} | ConvertTo-Json -Compress
}}
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = parse_last_json(result.stdout)
    assert payload["failed_closed"] is True
    assert "could not be resolved" in payload["message"]
    combined = result.stdout + result.stderr
    assert secret_argument not in combined
    assert secret_stdin not in combined


def test_stdout_stderr_nonzero_exit_and_result_contract_remain_compatible(tmp_path):
    child = tmp_path / "result-contract.ps1"
    child.write_text(
        "[Console]::Out.WriteLine('stdout-marker')\n"
        "[Console]::Error.WriteLine('stderr-marker')\n"
        "exit 7\n",
        encoding="utf-8",
    )
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
$result = Invoke-BoundedNativeCommand -FileName 'powershell.exe' -ArgumentList @('-NoProfile','-File','{ps_quote(child)}') -WorkingDirectory '{ps_quote(tmp_path)}' -RequireWorkingDirectory -TimeoutSeconds 15 -OperationLabel 'result contract probe'
$result | ConvertTo-Json -Compress
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = parse_last_json(result.stdout)
    assert payload == {
        "exit_code": 7,
        "output": "stdout-marker\r\nstderr-marker",
        "timed_out": False,
        "operation": "result contract probe",
    }


def test_timeout_remains_bounded_and_terminates_child_process_tree(tmp_path):
    marker = tmp_path / "orphan-marker.txt"
    grandchild = tmp_path / "grandchild.ps1"
    grandchild.write_text(
        f"Start-Sleep -Seconds 4\nSet-Content -LiteralPath '{ps_quote(marker)}' -Value orphaned\n",
        encoding="utf-8",
    )
    parent = tmp_path / "parent.ps1"
    parent.write_text(
        "$child = Start-Process powershell.exe -ArgumentList "
        f"@('-NoProfile','-File','{ps_quote(grandchild)}') -PassThru\n"
        "$child.WaitForExit()\n",
        encoding="utf-8",
    )
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
$started = Get-Date
try {{
    Invoke-BoundedNativeCommand -FileName 'powershell.exe' -ArgumentList @('-NoProfile','-File','{ps_quote(parent)}') -WorkingDirectory '{ps_quote(tmp_path)}' -RequireWorkingDirectory -TimeoutSeconds 1 -OperationLabel 'process tree timeout probe' | Out-Null
    [ordered]@{{ timed_out=$false; elapsed_ms=[int]((Get-Date)-$started).TotalMilliseconds; message='' }} | ConvertTo-Json -Compress
}}
catch {{
    [ordered]@{{ timed_out=$true; elapsed_ms=[int]((Get-Date)-$started).TotalMilliseconds; message=$_.Exception.Message }} | ConvertTo-Json -Compress
}}
"""
    result = run_powershell(script, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = parse_last_json(result.stdout)
    assert payload["timed_out"] is True
    assert payload["elapsed_ms"] < 8000
    assert "Timed out after 1s" in payload["message"]
    time.sleep(5)
    assert not marker.exists()


@pytest.mark.parametrize("child_exit_code", (0, 7))
def test_local_governed_detached_worktree_uses_exact_sha_and_cleans_up(
    tmp_path, child_exit_code
):
    ambient = tmp_path / "operator ambient"
    ambient.mkdir()
    expected_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
$before = @(git worktree list --porcelain)
$worktree = $null
$old = [Environment]::CurrentDirectory
try {{
    $worktree = New-DetachedWorktree -GitSha '{expected_sha}' -Prefix 'go-odyssey-build-regression'
    $validated = Assert-DetachedWorktreeIdentity -Path $worktree -ExpectedGitSha '{expected_sha}'
    [Environment]::CurrentDirectory = '{ps_quote(ambient)}'
    $result = Invoke-BoundedNativeCommand -FileName 'powershell.exe' -ArgumentList @('-NoProfile','-Command','[Environment]::CurrentDirectory; exit {child_exit_code}') -WorkingDirectory $validated -RequireWorkingDirectory -TimeoutSeconds 15 -OperationLabel 'fully local governed synthetic build'
    $observed = $result.output
    $exitCode = $result.exit_code
}}
finally {{
    [Environment]::CurrentDirectory = $old
    if($worktree){{ Remove-DetachedWorktree -Path $worktree }}
}}
$after = @(git worktree list --porcelain)
[ordered]@{{
    expected_sha = '{expected_sha}'
    child_cwd = $observed
    child_exit_code = $exitCode
    temporary_worktree_removed = -not (Test-Path -LiteralPath $worktree)
    preexisting_worktrees_unchanged = (($before -join "`n") -eq ($after -join "`n"))
}} | ConvertTo-Json -Compress
"""
    result = run_powershell(script, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = parse_last_json(result.stdout)
    assert payload["expected_sha"] == expected_sha
    assert pathlib.Path(payload["child_cwd"]) != ROOT
    assert payload["child_exit_code"] == child_exit_code
    assert payload["temporary_worktree_removed"] is True
    assert payload["preexisting_worktrees_unchanged"] is True


def test_build_orchestration_requires_validated_exact_worktree_and_child_script():
    module = MODULE.read_text(encoding="utf-8")
    release = BUILD_RELEASE.read_text(encoding="utf-8")
    production = BUILD_PRODUCTION.read_text(encoding="utf-8")

    assert "$psi.WorkingDirectory = $resolvedWorkingDirectory" in module
    assert "Assert-DetachedWorktreeIdentity" in release
    assert "-WorkingDirectory $worktree" in release
    assert "-RequireWorkingDirectory" in release
    assert "Test-Path -LiteralPath $childBuildScript -PathType Leaf" in release
    assert "-TimeoutSeconds 3900" in release
    assert "Assert-ImageRevisionMatches" in release
    assert "Remove-DetachedWorktree -Path $worktree" in release
    assert "docker buildx build" in production
    assert "ssh " not in production.lower()


def test_all_bounded_native_callers_are_reviewed_without_unrelated_rewrites():
    module = MODULE.read_text(encoding="utf-8")
    release = BUILD_RELEASE.read_text(encoding="utf-8")
    production = BUILD_PRODUCTION.read_text(encoding="utf-8")
    package_static = (ROOT / "scripts" / "release" / "package-static-release.ps1").read_text(
        encoding="utf-8"
    )

    assert release.count("Invoke-BoundedNativeCommand") == 1
    assert production.count("Invoke-BoundedNativeCommand") == 2
    assert package_static.count("Invoke-BoundedNativeCommand") == 2
    assert module.count("Invoke-BoundedNativeCommand") >= 10
    assert "-WorkingDirectory $worktree" in release
    assert "-RequireWorkingDirectory" not in package_static
