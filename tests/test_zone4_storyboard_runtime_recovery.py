"""Zone4 storyboard, Lord visual, and installed-PWA parity contracts."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE_TEST = ROOT / "tests" / "e9_node_tests" / "run_zone4_storyboard_runtime_recovery_tests.js"


def test_zone4_storyboard_lord_and_pwa_contracts():
    result = subprocess.run(
        ["node", str(NODE_TEST)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "12/12 passed" in result.stdout
