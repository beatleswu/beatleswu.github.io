import json
import os
import pathlib
import re
import shutil
import subprocess
import time

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
BUILD_RELEASE = ROOT / "scripts" / "release" / "build-release-image.ps1"
BUILD_PRODUCTION = ROOT / "scripts" / "build-production-image.ps1"


def _protected_pattern_contract(path, function_name):
    source = path.read_text(encoding="utf-8")
    start = source.index(f"function {function_name}")
    end = source.index("\n}", start)
    body = source[start:end]
    clauses = re.findall(
        r"if \(\$leaf (?P<operator>-ieq|-like) '(?P<match>[^']+)'\) "
        r"\{ return '(?P<returned>[^']+)' \}",
        body,
    )
    assert clauses, f"no protected-pattern clauses found in {function_name}"
    return clauses


def test_bootstrap_and_module_protected_pattern_contracts_are_identical():
    expected = [
        ("-ieq", "secret_key.txt", "secret_key.txt"),
        ("-like", ".env*", ".env*"),
        ("-like", "*.db", "*.db"),
        ("-like", "*.sqlite*", "*.sqlite*"),
        ("-ieq", "questions.json", "questions.json"),
        ("-like", "*.sgf", "*.sgf"),
        ("-like", "*.pem", "*.pem"),
        ("-like", "*.key", "*.key"),
        ("-like", "*.bak*", "*.bak*"),
    ]
    module_contract = _protected_pattern_contract(
        MODULE, "Get-ProtectedUntrackedPattern"
    )
    bootstrap_contract = _protected_pattern_contract(
        BUILD_PRODUCTION, "Get-BootstrapProtectedPattern"
    )

    assert module_contract == expected
    assert bootstrap_contract == expected
    assert bootstrap_contract == module_contract


def test_safe_first_output_line_normalizes_null_empty_whitespace_and_values():
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
$values = [ordered]@{{
    null = Get-SafeFirstOutputLine -Value $null
    empty = Get-SafeFirstOutputLine -Value ([string]::Empty)
    whitespace = Get-SafeFirstOutputLine -Value '   '
    value = Get-SafeFirstOutputLine -Value "  branch-name  "
}}
$values | ConvertTo-Json -Compress
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    values = parse_last_json(result.stdout)
    assert values == {
        "null": "",
        "empty": "",
        "whitespace": "",
        "value": "branch-name",
    }


def test_invoke_git_failure_is_not_normalized_to_empty_success(tmp_path):
    repo, _sha = create_synthetic_repo(tmp_path)
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
try {{ Invoke-Git -Arguments @('rev-parse', 'refs/does-not-exist') -WorkingDirectory '{ps_quote(repo)}' | Out-Null; $failed=$false }}
catch {{ $failed=$true; $message=$_.Exception.Message }}
[ordered]@{{failed=$failed;message=$message}} | ConvertTo-Json -Compress
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = parse_last_json(result.stdout)
    assert payload["failed"] is True
    assert "failed with exit code" in payload["message"]


def test_actual_bootstrap_accepts_detached_zero_branch_output_and_advances(tmp_path):
    repo, sha = create_governed_build_repo(tmp_path)
    assert git(repo, "branch", "--show-current").stdout == ""
    git(repo, "remote", "add", "origin", str(repo))
    git(repo, "update-ref", "refs/remotes/origin/master", sha)
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(repo / "scripts" / "build-production-image.ps1"),
            "-GitSha", sha,
            "-ExpectedCanonicalWorktreeRoot", str(repo),
            "-ExpectedExactGitSha", sha,
            "-ExpectedGitCommonDirectory", str(repo / ".git"),
            "-ExpectedHeadState", "detached",
        ],
        cwd=repo,
        env={**os.environ, "APP_BUILD_DATE_OVERRIDE": "2026-07-18T00:00:00Z"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "InvokeMethodOnNull" not in combined
    assert "Required tracked build inputs are missing" in combined
    assert "== go-odyssey-app canonical image build" in combined


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


def git(cwd, *arguments, check=True):
    return subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=check,
    )


def create_synthetic_repo(
    tmp_path, *, detached=True, include_child_script=True, child_contents=None
):
    repo = tmp_path / "synthetic-repository"
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Release Boundary Test")
    git(repo, "config", "user.email", "release-boundary@example.invalid")
    (repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    if include_child_script:
        (repo / "child.ps1").write_text(
            child_contents or "'child-script' | Out-Null\n", encoding="utf-8"
        )
    tracked_paths = ["tracked.txt"]
    if include_child_script:
        tracked_paths.append("child.ps1")
    git(repo, "add", *tracked_paths)
    git(repo, "commit", "-q", "-m", "synthetic governed source")
    sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    if detached:
        git(repo, "checkout", "-q", "--detach", sha)
    return repo, sha


def make_junction(link, target):
    result = subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert link.exists()


def create_governed_build_repo(tmp_path):
    repo = tmp_path / "governed-build-repository"
    (repo / "scripts" / "release").mkdir(parents=True)
    shutil.copy2(BUILD_PRODUCTION, repo / "scripts" / "build-production-image.ps1")
    shutil.copy2(MODULE, repo / "scripts" / "release" / "ReleaseTooling.psm1")
    (repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Governed Child Test")
    git(repo, "config", "user.email", "governed-child@example.invalid")
    git(
        repo,
        "add",
        "scripts/build-production-image.ps1",
        "scripts/release/ReleaseTooling.psm1",
        "tracked.txt",
    )
    git(repo, "commit", "-q", "-m", "governed child bootstrap")
    sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "-q", "--detach", sha)
    return repo, sha


def invoke_identity(
    path, expected_sha, *, child=False, script_path=None, current=None, expected_common=None
):
    expected_common = expected_common or (pathlib.Path(path) / ".git")
    function_call = (
        "Assert-GovernedBuildChildIdentity "
        f"-ExpectedCanonicalWorktreeRoot '{ps_quote(path)}' "
        f"-ExpectedGitSha '{expected_sha}' "
        f"-ExpectedGitCommonDirectory '{ps_quote(expected_common)}' "
        f"-ExecutingBuildScriptPath '{ps_quote(script_path)}' "
        "-ExpectedHeadState detached"
        if child
        else f"Assert-DetachedWorktreeIdentity -Path '{ps_quote(path)}' -ExpectedGitSha '{expected_sha}'"
    )
    set_current = f"[Environment]::CurrentDirectory = '{ps_quote(current)}'" if current else ""
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
$old = [Environment]::CurrentDirectory
try {{
    {set_current}
    try {{ {function_call} | Out-Null; [ordered]@{{failed_closed=$false;message=''}} | ConvertTo-Json -Compress }}
    catch {{ [ordered]@{{failed_closed=$true;message=$_.Exception.Message}} | ConvertTo-Json -Compress }}
}}
finally {{ [Environment]::CurrentDirectory = $old }}
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    return parse_last_json(result.stdout)


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


def test_required_working_directory_is_validated_before_executable_resolution(tmp_path):
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
try {{
    Invoke-BoundedNativeCommand -FileName 'definitely-missing-native-command.exe' -ArgumentList @('--synthetic') -WorkingDirectory 'relative-path' -RequireWorkingDirectory -TimeoutSeconds 15 -OperationLabel 'validation order probe' | Out-Null
    $failed=$false
}}
catch {{ $failed=$true; $message=$_.Exception.Message }}
[ordered]@{{failed_closed=$failed;message=$message}} | ConvertTo-Json -Compress
"""
    result = run_powershell(script)
    payload = parse_last_json(result.stdout)
    assert payload["failed_closed"] is True
    assert "working directory" in payload["message"].lower()
    assert "could not be resolved" not in payload["message"].lower()


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
    assert payload["exit_code"] == 7
    assert payload["output"] == "stdout-marker\r\nstderr-marker"
    assert payload["stdout"] == "stdout-marker"
    assert payload["stderr"] == "stderr-marker"
    assert payload["elapsed_seconds"] >= 0
    assert payload["timed_out"] is False
    assert payload["operation"] == "result contract probe"


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
    assert "Assert-GeneratedDetachedWorktreeIdentity" in release
    assert "-WorkingDirectory $worktree" in release
    assert "-RequireWorkingDirectory" in release
    assert "Assert-GovernedBuildScriptPath" in release
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


def test_wrong_expected_sha_fails_before_build_action(tmp_path):
    repo, _sha = create_synthetic_repo(tmp_path)
    marker = repo / "build-started"
    payload = invoke_identity(repo, "0" * 40)
    assert payload["failed_closed"] is True
    assert not marker.exists()


def test_non_detached_head_fails_before_build_action(tmp_path):
    repo, sha = create_synthetic_repo(tmp_path, detached=False)
    payload = invoke_identity(repo, sha)
    assert payload["failed_closed"] is True
    assert "detached" in payload["message"].lower()


def test_tracked_dirty_worktree_fails_before_build_action(tmp_path):
    repo, sha = create_synthetic_repo(tmp_path)
    (repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    payload = invoke_identity(repo, sha)
    assert payload["failed_closed"] is True
    assert "clean" in payload["message"].lower()


def test_ordinary_untracked_file_fails_before_build_action(tmp_path):
    repo, sha = create_synthetic_repo(tmp_path)
    (repo / "ordinary-untracked.txt").write_text("synthetic\n", encoding="utf-8")
    payload = invoke_identity(repo, sha)
    assert payload["failed_closed"] is True
    assert "untracked" in payload["message"].lower()


def test_protected_untracked_filename_fails_without_content_read(tmp_path):
    repo, sha = create_synthetic_repo(tmp_path)
    protected = repo / "secret_key.txt"
    protected.touch()
    payload = invoke_identity(repo, sha)
    assert payload["failed_closed"] is True
    assert "secret_key.txt" in payload["message"]
    assert "pattern 'secret_key.txt'" in payload["message"]


def test_ignored_protected_filename_fails_without_content_read(tmp_path):
    repo, _sha = create_synthetic_repo(tmp_path, detached=False)
    (repo / ".gitignore").write_text(".env*\n", encoding="utf-8")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-q", "-m", "ignore synthetic environment files")
    sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "-q", "--detach", sha)
    (repo / ".env.synthetic").touch()
    payload = invoke_identity(repo, sha)
    assert payload["failed_closed"] is True
    assert ".env.synthetic" in payload["message"]
    assert "pattern '.env*'" in payload["message"]


def test_wrong_git_repository_fails(tmp_path):
    first, first_sha = create_synthetic_repo(tmp_path / "first")
    second, _second_sha = create_synthetic_repo(
        tmp_path / "second", child_contents="'different-repository' | Out-Null\n"
    )
    payload = invoke_identity(
        second,
        first_sha,
        child=True,
        script_path=second / "child.ps1",
        current=second,
        expected_common=first / ".git",
    )
    assert payload["failed_closed"] is True


def test_different_valid_worktree_is_not_a_generated_identity(tmp_path):
    other = tmp_path / "other-valid-worktree"
    sha = git(ROOT, "rev-parse", "HEAD").stdout.strip()
    git(ROOT, "worktree", "add", "--detach", str(other), sha)
    try:
        script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
try {{ Assert-GeneratedDetachedWorktreeIdentity -Path '{ps_quote(other)}' -ExpectedGitSha '{sha}' | Out-Null; $failed=$false }}
catch {{ $failed=$true; $message=$_.Exception.Message }}
[ordered]@{{failed_closed=$failed;message=$message}} | ConvertTo-Json -Compress
"""
        result = run_powershell(script)
        assert result.returncode == 0, result.stdout + result.stderr
        payload = parse_last_json(result.stdout)
        assert payload["failed_closed"] is True
        assert "not registered" in payload["message"]
    finally:
        git(ROOT, "worktree", "remove", "--force", str(other))


def test_sibling_prefix_confusion_is_rejected(tmp_path):
    root = tmp_path / "repo"
    sibling = tmp_path / "repo-evil"
    root.mkdir()
    sibling.mkdir()
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
try {{ Assert-PathInsideCanonicalRoot -Path '{ps_quote(sibling)}' -CanonicalRoot '{ps_quote(root)}' | Out-Null; $failed=$false }}
catch {{ $failed=$true; $message=$_.Exception.Message }}
[ordered]@{{failed_closed=$failed;message=$message}} | ConvertTo-Json -Compress
"""
    result = run_powershell(script)
    payload = parse_last_json(result.stdout)
    assert payload["failed_closed"] is True


def test_junction_worktree_is_functionally_rejected(tmp_path):
    repo, sha = create_synthetic_repo(tmp_path)
    junction = tmp_path / "junction-worktree"
    make_junction(junction, repo)
    try:
        payload = invoke_identity(junction, sha)
        assert payload["failed_closed"] is True
        assert "reparse point" in payload["message"].lower()
    finally:
        os.rmdir(junction)


def test_junction_build_script_path_is_functionally_rejected(tmp_path):
    root = tmp_path / "canonical-root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "child.ps1").write_text("exit 0\n", encoding="utf-8")
    junction = root / "redirected"
    make_junction(junction, outside)
    try:
        script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
try {{ Assert-GovernedBuildScriptPath -Path '{ps_quote(junction / 'child.ps1')}' -CanonicalWorktreeRoot '{ps_quote(root)}' | Out-Null; $failed=$false }}
catch {{ $failed=$true; $message=$_.Exception.Message }}
[ordered]@{{failed_closed=$failed;message=$message}} | ConvertTo-Json -Compress
"""
        result = run_powershell(script)
        payload = parse_last_json(result.stdout)
        assert payload["failed_closed"] is True
        assert "reparse point" in payload["message"].lower()
    finally:
        os.rmdir(junction)


def test_child_side_validation_catches_wrong_cwd(tmp_path):
    repo, sha = create_synthetic_repo(tmp_path)
    other = tmp_path / "wrong-current-directory"
    other.mkdir()
    payload = invoke_identity(repo, sha, child=True, script_path=repo / "child.ps1", current=other)
    assert payload["failed_closed"] is True
    assert "current directory" in payload["message"].lower()


def test_child_side_validation_catches_wrong_sha(tmp_path):
    repo, _sha = create_synthetic_repo(tmp_path)
    payload = invoke_identity(repo, "0" * 40, child=True, script_path=repo / "child.ps1", current=repo)
    assert payload["failed_closed"] is True


def test_child_side_validation_catches_dirty_state(tmp_path):
    repo, sha = create_synthetic_repo(tmp_path)
    (repo / "untracked.txt").touch()
    payload = invoke_identity(repo, sha, child=True, script_path=repo / "child.ps1", current=repo)
    assert payload["failed_closed"] is True
    assert "untracked" in payload["message"].lower()


def test_functional_child_validation_succeeds_from_unrelated_ambient_directory(tmp_path):
    child_contents = f"""
param([string]$Root,[string]$Sha,[string]$Common)
$ErrorActionPreference='Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
$validated = Assert-GovernedBuildChildIdentity -ExpectedCanonicalWorktreeRoot $Root -ExpectedGitSha $Sha -ExpectedGitCommonDirectory $Common -ExecutingBuildScriptPath $PSCommandPath -ExpectedHeadState detached
[ordered]@{{validated=$validated;cwd=[Environment]::CurrentDirectory}} | ConvertTo-Json -Compress
"""
    repo, sha = create_synthetic_repo(tmp_path, child_contents=child_contents)
    script = f"""
$ErrorActionPreference='Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
$old=[Environment]::CurrentDirectory
try {{
    [Environment]::CurrentDirectory='C:\\Windows'
    $result=Invoke-BoundedNativeCommand -FileName 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File','{ps_quote(repo / 'child.ps1')}','-Root','{ps_quote(repo)}','-Sha','{sha}','-Common','{ps_quote(repo / '.git')}') -WorkingDirectory '{ps_quote(repo)}' -RequireWorkingDirectory -TimeoutSeconds 20 -OperationLabel 'governed child identity success'
    $result | ConvertTo-Json -Compress
}}
finally {{ [Environment]::CurrentDirectory=$old }}
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    bounded = parse_last_json(result.stdout)
    child = json.loads(bounded["output"])
    assert pathlib.Path(child["validated"]) == repo
    assert pathlib.Path(child["cwd"]) == repo


def test_child_bootstrap_rejects_junction_substitution_after_parent_validation(tmp_path):
    repo, sha = create_governed_build_repo(tmp_path)

    parent_validation = invoke_identity(repo, sha)
    assert parent_validation["failed_closed"] is False

    substituted = tmp_path / "substituted-worktree"
    make_junction(substituted, repo)
    marker = repo / "docker-or-build-started"
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(substituted / "scripts" / "build-production-image.ps1"),
                "-GitSha", sha,
                "-ExpectedCanonicalWorktreeRoot", str(repo),
                "-ExpectedExactGitSha", sha,
                "-ExpectedGitCommonDirectory", str(repo / ".git"),
                "-ExpectedHeadState", "detached",
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        assert result.returncode != 0
        assert "reparse point" in (result.stdout + result.stderr).lower()
        assert not marker.exists()
    finally:
        os.rmdir(substituted)


@pytest.mark.parametrize("failure_case", ("wrong_cwd", "wrong_sha", "dirty"))
def test_actual_build_child_bootstrap_fails_before_build_mutation(tmp_path, failure_case):
    repo, sha = create_governed_build_repo(tmp_path)
    expected_sha = sha
    cwd = repo
    if failure_case == "wrong_cwd":
        cwd = tmp_path
    elif failure_case == "wrong_sha":
        expected_sha = "0" * 40
    else:
        (repo / "ordinary-untracked.txt").touch()
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(repo / "scripts" / "build-production-image.ps1"),
            "-GitSha", sha,
            "-ExpectedCanonicalWorktreeRoot", str(repo),
            "-ExpectedExactGitSha", expected_sha,
            "-ExpectedGitCommonDirectory", str(repo / ".git"),
            "-ExpectedHeadState", "detached",
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "== go-odyssey-app canonical image build" not in combined
    assert "Image tag:" not in combined
    assert "docker buildx" not in combined.lower()


def test_cleanup_refuses_unregistered_protected_and_arbitrary_paths(tmp_path):
    arbitrary = tmp_path / "arbitrary-directory"
    arbitrary.mkdir()
    filesystem_root = pathlib.Path(ROOT.anchor)
    paths = [ROOT, ROOT.parent, arbitrary, filesystem_root]
    quoted = ",".join(f"'{ps_quote(path)}'" for path in paths)
    script = f"""
$ErrorActionPreference='Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
$results=@()
foreach($path in @({quoted})) {{
    try {{ Remove-DetachedWorktree -Path $path; $results += [ordered]@{{path=$path;refused=$false}} }}
    catch {{ $results += [ordered]@{{path=$path;refused=$true;message=$_.Exception.Message}} }}
}}
$results | ConvertTo-Json -Compress
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = parse_last_json(result.stdout)
    assert all(item["refused"] for item in payload)
    assert arbitrary.exists()
    assert ROOT.exists()


def test_cleanup_refuses_another_registered_worktree(tmp_path):
    other = tmp_path / "other-registered-worktree"
    sha = git(ROOT, "rev-parse", "HEAD").stdout.strip()
    git(ROOT, "worktree", "add", "--detach", str(other), sha)
    try:
        script = f"""
$ErrorActionPreference='Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
try {{ Remove-DetachedWorktree -Path '{ps_quote(other)}'; $refused=$false }}
catch {{ $refused=$true; $message=$_.Exception.Message }}
[ordered]@{{refused=$refused;message=$message;exists=(Test-Path -LiteralPath '{ps_quote(other)}')}} | ConvertTo-Json -Compress
"""
        result = run_powershell(script)
        payload = parse_last_json(result.stdout)
        assert payload["refused"] is True
        assert payload["exists"] is True
    finally:
        git(ROOT, "worktree", "remove", "--force", str(other))


def test_cleanup_refuses_registered_reparse_substitution_and_then_recovers(tmp_path):
    script = f"""
$ErrorActionPreference='Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
$sha=(git rev-parse HEAD).Trim()
$worktree=New-DetachedWorktree -GitSha $sha -Prefix 'go-odyssey-build-reparse-cleanup'
$moved=$worktree + '-moved'
Move-Item -LiteralPath $worktree -Destination $moved
$junctionOutput = cmd /d /c mklink /J $worktree $moved
try {{
    try {{ Remove-DetachedWorktree -Path $worktree; $refused=$false }}
    catch {{ $refused=$true; $message=$_.Exception.Message }}
    $targetStillExists=Test-Path -LiteralPath $moved
}}
finally {{
    [System.IO.Directory]::Delete($worktree)
    Move-Item -LiteralPath $moved -Destination $worktree
    Remove-DetachedWorktree -Path $worktree
}}
[ordered]@{{refused=$refused;message=$message;target_still_exists=$targetStillExists;final_removed=(-not (Test-Path -LiteralPath $worktree))}} | ConvertTo-Json -Compress
"""
    result = run_powershell(script, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = parse_last_json(result.stdout)
    assert payload["refused"] is True
    assert "reparse point" in payload["message"].lower()
    assert payload["target_still_exists"] is True
    assert payload["final_removed"] is True


def test_failed_git_worktree_removal_leaves_exact_directory_for_review(tmp_path):
    script = f"""
$ErrorActionPreference='Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
$sha=(git rev-parse HEAD).Trim()
$worktree=New-DetachedWorktree -GitSha $sha -Prefix 'go-odyssey-build-locked-cleanup'
git worktree lock $worktree
try {{
    try {{ Remove-DetachedWorktree -Path $worktree; $refused=$false }}
    catch {{ $refused=$true; $message=$_.Exception.Message }}
    $leftForReview=Test-Path -LiteralPath $worktree
}}
finally {{
    git worktree unlock $worktree
    Remove-DetachedWorktree -Path $worktree
}}
[ordered]@{{refused=$refused;message=$message;left_for_review=$leftForReview;final_removed=(-not (Test-Path -LiteralPath $worktree))}} | ConvertTo-Json -Compress
"""
    result = run_powershell(script, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = parse_last_json(result.stdout)
    assert payload["refused"] is True
    assert payload["left_for_review"] is True
    assert payload["final_removed"] is True


def test_ast_caller_inventory_has_no_unclassified_bounded_native_command():
    parser_script = r"""
$records=@()
Get-ChildItem -LiteralPath scripts -Recurse -File | Where-Object { $_.Extension -in @('.ps1','.psm1') } | ForEach-Object {
    $tokens=$null;$errors=$null
    $ast=[System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$tokens,[ref]$errors)
    if($errors.Count){throw "Parser failure: $($_.FullName)"}
    $commands=$ast.FindAll({param($node) $node -is [System.Management.Automation.Language.CommandAst] -and $node.GetCommandName() -eq 'Invoke-BoundedNativeCommand'},$true)
    foreach($command in $commands){
        $parent=$command.Parent;$function='<script>'
        while($parent){if($parent -is [System.Management.Automation.Language.FunctionDefinitionAst]){$function=$parent.Name;break};$parent=$parent.Parent}
        $records += [ordered]@{path=$_.FullName.Substring((Resolve-Path '.').Path.Length+1).Replace('\','/');function=$function;text=$command.Extent.Text}
    }
}
$records | ConvertTo-Json -Compress
"""
    result = run_powershell(parser_script)
    assert result.returncode == 0, result.stdout + result.stderr
    records = parse_last_json(result.stdout)
    inventory = {
        ("scripts/release/build-release-image.ps1", "<script>"): (1, "isolated_worktree_required"),
        ("scripts/build-production-image.ps1", "<script>"): (2, "explicit_local_context"),
        ("scripts/release/package-static-release.ps1", "<script>"): (2, "directory_independent"),
        ("scripts/release/ReleaseTooling.psm1", "Invoke-BoundedSshCommand"): (2, "remote_context"),
        ("scripts/release/ReleaseTooling.psm1", "Invoke-BoundedScpUpload"): (1, "remote_context"),
        ("scripts/release/deploy-release-image.ps1", "Get-RemoteCandidateFailureEvidence"): (1, "remote_context"),
        ("scripts/release/deploy-release-image.ps1", "Invoke-ProductionVerificationSeries"): (1, "explicit_local_context"),
        ("scripts/release/deploy-release-image.ps1", "<script>"): (1, "explicit_local_context"),
        ("scripts/release/rollback-release.ps1", "<script>"): (1, "explicit_local_context"),
        ("scripts/release/ReleaseTooling.psm1", "Test-GnuTarExecutableCapability"): (2, "directory_independent"),
        ("scripts/release/ReleaseTooling.psm1", "New-DeterministicStaticArchive"): (1, "directory_independent"),
        ("scripts/release/ReleaseTooling.psm1", "Test-StaticArchiveEntrySafety"): (1, "directory_independent"),
    }
    actual = {}
    for record in records:
        key = (record["path"], record["function"])
        actual.setdefault(key, []).append(record["text"])
    assert set(actual) == set(inventory)
    for key, (expected_count, classification) in inventory.items():
        assert len(actual[key]) == expected_count, (key, classification, actual[key])

    isolated = actual[("scripts/release/build-release-image.ps1", "<script>")][0]
    assert "-WorkingDirectory $worktree" in isolated
    assert "-RequireWorkingDirectory" in isolated
    production = BUILD_PRODUCTION.read_text(encoding="utf-8")
    assert production.index("Assert-GovernedBuildChildIdentity") < production.index("Invoke-BoundedNativeCommand")
    package = (ROOT / "scripts" / "release" / "package-static-release.ps1").read_text(encoding="utf-8")
    assert "'-C', ($verifyExtractPath" in package
    module = MODULE.read_text(encoding="utf-8")
    assert "@('--version')" in module
    assert "@($script:TarForceLocalFlag, '-tvf', $ArchivePath)" in module
    assert "Invoke-BoundedSshCommand" in module and "Invoke-BoundedScpUpload" in module
    for key in (
        ("scripts/release/deploy-release-image.ps1", "Invoke-ProductionVerificationSeries"),
        ("scripts/release/deploy-release-image.ps1", "<script>"),
        ("scripts/release/rollback-release.ps1", "<script>"),
    ):
        assert "-WorkingDirectory $repoRoot" in actual[key][0]
        assert "-RequireWorkingDirectory" in actual[key][0]
