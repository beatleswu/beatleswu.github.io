import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
SITE_NAV = (ROOT / "site-nav.js").read_text(encoding="utf-8")
NODE_TEST = ROOT / "tests" / "e9_node_tests" / "run_site_nav_reconciliation_tests.js"


def test_e10_battle_owner_is_separate_from_legacy_renderer_shell():
    assert "const E10_BATTLE_SHELL_OWNER = 'e10-battle';" in INDEX
    assert "const e10BattleShellOwner = e9ShellRequested && adventureResume;" in INDEX
    assert "publishAdventureShellOwner(e10BattleShellOwner ? E10_BATTLE_SHELL_OWNER : null);" in INDEX
    assert "window.__GO_E9_ACTIVE_SHELL__ = legacyWelcomeShellActive ? 'legacy' : 'e9';" in INDEX


def test_owner_marker_reconciles_after_delayed_authentication_and_bootstrap():
    assert "window.__GO_ADVENTURE_SHELL_OWNER__ = nextOwner;" in INDEX
    assert "data-adventure-shell-owner" in INDEX
    assert "new CustomEvent('e10:adventure-shell-owner-changed'" in INDEX
    assert "document.addEventListener('e10:adventure-shell-owner-changed', reconcileNavigation);" in SITE_NAV
    assert INDEX.index("publishAdventureShellOwner") < INDEX.index(
        '<script src="/site-nav.js?v=20260804e10navcache1"></script>'
    )


def test_site_nav_preserves_legacy_and_generic_navigation_surfaces():
    result = subprocess.run(
        ["node", str(NODE_TEST)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "site-nav reconciliation tests passed" in result.stdout
