"""R11: dangerous direct child invocation must stop before Git/import/Docker."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build-production-image.ps1"
GATE_MESSAGE = "EXTERNAL_DOCKER_BUILD_BROKER_REQUIRED"

def test_child_docker_path_is_after_fail_closed_exit():
    text = SCRIPT.read_text(encoding="utf-8")
    kill = text.index('Fail-Bootstrap "EXTERNAL_DOCKER_BUILD_BROKER_REQUIRED:')
    assert "function Fail-Bootstrap" in text[:kill]
    assert kill < text.index("Import-Module $bootstrapModule")
    assert kill < text.index("Get-BootstrapCanonicalPath")
    assert kill < text.index("# 9. Build with buildx")
    assert "No candidate-controlled CLI arg" in text[:kill]
    assert "OS-isolated build broker" in text[:kill]

def test_direct_child_invocation_fails_closed_without_touching_docker():
    pwsh = shutil.which("powershell.exe") or shutil.which("pwsh")
    assert pwsh is not None
    root = SCRIPT.parents[1]
    env = os.environ.copy()
    # Spoof both tempting local authorization knobs: the child must ignore them.
    env["GO_ODYSSEY_HOST_APPROVED_BUILD_INVOCATION"] = "true"
    env["GO_ODYSSEY_RELEASE_GATE_SOURCE_SHA"] = "a" * 40
    env["GO_ODYSSEY_RELEASE_PRODUCT_SOURCE_SHA"] = "b" * 40
    args = [pwsh, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(SCRIPT), "-ExpectedCanonicalWorktreeRoot", str(root),
            "-ExpectedExactGitSha", "1ed084b40f9c8c82907334194bf182247331f2a7",
            "-ExpectedGitCommonDirectory", str(root / ".git"),
            "-ExpectedHeadState", "branch", "-SkipCleanCheck"]
    result = subprocess.run(args, cwd=root, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", env=env, timeout=20)
    assert result.returncode != 0, "DIRECT_DOCKER_CHILD_MUST_FAIL_CLOSED"
    output = result.stdout + result.stderr
    assert GATE_MESSAGE in output, output[-1500:]
    assert "canonical image build" not in output
    assert "docker buildx" not in output
