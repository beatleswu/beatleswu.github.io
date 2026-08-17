"""Executable E10 V1B B4 GameSession identity contracts.

The contract is intentionally browser-free: the Node runner loads only the
future static module in a synthetic VM, while these checks inspect integration
source for load order and authority boundaries.  No Flask app, database,
network, secrets, or Product-file mutation is involved.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "js" / "game" / "game_session.js"
RUNNER = ROOT / "tests" / "e2e" / "run_e10_b4_gamesession_identity_contract.mjs"
INDEX = ROOT / "index.html"
SRS = ROOT / "srs.js"


def test_b4_contract_runner_has_no_skip_or_expected_red_escape_hatches():
    source = RUNNER.read_text(encoding="utf-8")
    assert "pytest.mark.skip" not in source
    assert "pytest.mark.xfail" not in source
    assert "EXPECTED_RED" not in source
    assert "process.exitCode = 2" not in source


def test_b4_module_is_a_static_browser_module_with_required_integration_inputs():
    assert MODULE.name == "game_session.js"
    assert RUNNER.exists()
    assert INDEX.exists()
    assert SRS.exists()


def test_b4_node_contract_runner():
    result = subprocess.run(
        ["node", str(RUNNER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    output = f"stdout={result.stdout}\nstderr={result.stderr}"
    assert result.returncode == 0, output
    assert '"status":"PASS"' in result.stdout, output


def test_b4_files_do_not_expand_write_scope():
    allowed = {
        Path("tests/e2e/run_e10_b4_gamesession_identity_contract.mjs"),
        Path("tests/test_e10_gamesession_identity_contract_v1b.py"),
    }
    changed = subprocess.run(
        ["git", "diff", "HEAD", "--name-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.splitlines()
    assert {Path(path) for path in changed} <= allowed
