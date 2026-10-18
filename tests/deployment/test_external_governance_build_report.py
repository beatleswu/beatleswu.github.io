"""Native report-boundary tests; disposable verifier doubles never authorize Build."""
import json
from pathlib import Path
import shutil
import subprocess
import hashlib

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("fault", [
    "none", "empty", "invalid-json", "array", "status", "build_authorized",
    "evidence_admitted", "release_authorized", "gate_sha", "product_sha",
    "git_common_dir", "challenge", "decision_sha256", "string-boolean", "nonzero",
])
def test_native_report_boundary_in_disposable_harness(tmp_path, fault):
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    assert powershell, "native PowerShell is required"
    common = str(tmp_path.resolve())
    report = dict(status="BUILD_APP_AUTHORIZED", build_authorized=True,
                  evidence_admitted=False, release_authorized=False,
                  gate_sha="b" * 40, product_sha="c" * 40,
                  git_common_dir=common, challenge="d" * 64, decision_sha256="e" * 64)
    if fault in {"status", "gate_sha", "product_sha", "git_common_dir", "challenge", "decision_sha256"}:
        report[fault] = "wrong"
    elif fault == "build_authorized":
        report[fault] = False
    elif fault in {"evidence_admitted", "release_authorized"}:
        report[fault] = True
    elif fault == "string-boolean":
        report["build_authorized"] = "true"
    payload = json.dumps([report] if fault == "array" else report)
    if fault in {"empty", "invalid-json"}:
        payload = "" if fault == "empty" else "broken-json"
    verifier = tmp_path / "synthetic-verifier.ps1"
    verifier.write_text("Write-Output '" + payload.replace("'", "''") + "'\nexit " +
                        ("1" if fault == "nonzero" else "0") + "\n", encoding="utf-8")
    # Execute only the actual preflight/report boundary. Stop before any source,
    # worktree, tests or Docker operation. The synthetic path/pin exist only here.
    source = (ROOT / "scripts/release/build-release-image.ps1").read_text(encoding="utf-8")
    source = source[:source.index("$expectedGitCommonDirectory = $GovernanceExpectedGitCommonDirectory")]
    source = source.replace("(Join-Path $PSScriptRoot 'ReleaseTooling.psm1')",
                            "'" + str(ROOT / "scripts/release/ReleaseTooling.psm1").replace("'", "''") + "'")
    source = source.replace(r"C:\Program Files\Go Odyssey Governance\verify-governance.exe", str(verifier))
    source = source.replace("$governanceVerifierSha256 = ''", "$governanceVerifierSha256 = '" +
                            hashlib.sha256(verifier.read_bytes()).hexdigest() + "'")
    source += "\nWrite-Output 'TEST_REPORT_ACCEPTED_NOT_AUTHORIZED'\n"
    harness = tmp_path / "report-boundary.ps1"
    harness.write_text(source, encoding="utf-8")
    proc = subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness),
                           "-GovernanceExpectedGitCommonDirectory", common,
                           "-GovernanceGateSourceSha", "b" * 40, "-GovernanceProductSourceSha", "c" * 40,
                           "-GovernanceDecision", "synthetic-never-read.json", "-GovernanceChallenge", "d" * 64],
                          capture_output=True, text=True, timeout=30)
    output = proc.stdout + proc.stderr
    if fault == "none":
        assert proc.returncode == 0 and "TEST_REPORT_ACCEPTED_NOT_AUTHORIZED" in output
    else:
        assert proc.returncode != 0 and "TEST_REPORT_ACCEPTED_NOT_AUTHORIZED" not in output
