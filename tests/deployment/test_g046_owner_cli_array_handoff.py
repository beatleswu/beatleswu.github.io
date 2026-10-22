"""G046: Owner-simplified singleton arguments must splat as arrays."""
from __future__ import annotations
import pathlib,platform,shutil,subprocess
import pytest

ROOT=pathlib.Path(__file__).resolve().parents[2]
BUILD=ROOT/"scripts/release/build-release-image.ps1"
FLAGS=("identityModeArgs","ownerConflictArgs")

@pytest.mark.parametrize("variable",FLAGS)
def test_optional_singleton_is_explicitly_typed_array(variable):
    body=BUILD.read_text(encoding="utf8")
    assert "[string[]]$"+variable+" = @()" in body
    assert ("$"+variable+" = @('--owner-simplified-policy')" in body or
            "$"+variable+' = @("--owner-simplified-policy")' in body)
    assert "@"+variable+" 2>&1" in body
    assert "$"+variable+" = if (" not in body

def test_owner_flag_unset_keeps_external_review_path_fail_closed():
    body=BUILD.read_text(encoding="utf8")
    assert "if ($OwnerSimplifiedPolicy) { $identityModeArgs" in body
    assert "if ($OwnerSimplifiedPolicy) { $ownerConflictArgs" in body
    assert "EXTERNAL_GOVERNANCE_ATTESTATION_REQUIRED" in body
    assert "EXTERNAL_GOVERNANCE_AUTHORITY_REQUIRED" in body

@pytest.mark.skipif(platform.system()!="Windows" or shutil.which("pwsh") is None,
                    reason="PowerShell CLI integration needs an authorized Windows runner")
def test_actual_pwsh_singleton_splat_reaches_both_real_python_parsers():
    identity=str(ROOT/"scripts/release/verify_release_candidate_binding.py")
    evaluator=str(ROOT/"scripts/release/evaluate_build_app_test_baseline.py")
    script=r"""
$ErrorActionPreference='Stop'
[string[]]$identityModeArgs=@()
[string[]]$ownerConflictArgs=@()
$identityModeArgs=@("--owner-simplified-policy")
$ownerConflictArgs=@('--owner-simplified-policy')
if ($identityModeArgs.Count -ne 1 -or $ownerConflictArgs.Count -ne 1) {throw 'array count changed'}
$identity=@(& python '"""+identity+r"""' identity --help @identityModeArgs 2>&1)
if($LASTEXITCODE -ne 0 -or (($identity -join ' ') -notlike '*--owner-simplified-policy*')) {throw 'identity parser rejected flag'}
$evaluator=@(& python '"""+evaluator+r"""' --help @ownerConflictArgs 2>&1)
if($LASTEXITCODE -ne 0 -or (($evaluator -join ' ') -notlike '*--owner-simplified-policy*')) {throw 'baseline parser rejected flag'}
Write-Output 'G046_TWO_REAL_OWNER_FLAGS_REACHED_BOTH_PARSERS_AS_ATOMIC_ARGS_PASS'
"""
    p=subprocess.run(["pwsh","-NoProfile","-Command",script],
         text=True,capture_output=True,encoding="utf8",errors="replace",timeout=60)
    assert p.returncode==0,(p.stdout[-700:],p.stderr[-850:])
    assert "G046_TWO_REAL_OWNER_FLAGS_REACHED_BOTH_PARSERS_AS_ATOMIC_ARGS_PASS" in p.stdout
