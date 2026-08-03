import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE_NAV = (ROOT / "site-nav.js").read_text(encoding="utf-8")
SHELL = (ROOT / "js" / "e9" / "shell.js").read_text(encoding="utf-8")
NODE_TEST = ROOT / "tests" / "e9_node_tests" / "run_site_nav_reconciliation_tests.js"


def test_site_nav_reconciles_only_after_shell_state_changes():
    assert "function reconcileNavigation()" in SITE_NAV
    assert "document.addEventListener('e9:shell-state-changed', reconcileNavigation);" in SITE_NAV
    assert "header.dataset.e10SessionStrip = '1';" in SITE_NAV
    assert "if (header.dataset.e10SessionStrip === '1' && !header.querySelector('.cg-nav-links'))" in SITE_NAV


def test_shell_publishes_the_authoritative_active_shell():
    assert "global.__GO_E9_ACTIVE_SHELL__ = mode;" in SHELL
    assert "document.dispatchEvent(new CustomEvent('e9:shell-state-changed'" in SHELL


def test_real_initialization_timing_and_shell_transitions():
    result = subprocess.run(
        ["node", str(NODE_TEST)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "site-nav reconciliation tests passed" in result.stdout
