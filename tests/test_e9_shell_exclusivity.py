import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "index.html"
SHELL_JS = REPO_ROOT / "js" / "e9" / "shell.js"
SHELL_CSS = REPO_ROOT / "css" / "e9" / "shell.css"
NODE_TEST = REPO_ROOT / "tests" / "e9_node_tests" / "run_shell_exclusivity_tests.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_index_resolves_shell_ownership_before_legacy_home_init():
    html = _read(INDEX_HTML)
    assert "resolveInitialE9Flags" in html
    assert "window.__GO_E9_ACTIVE_SHELL__" in html
    assert "window.__GO_E9_LEGACY_HOME_INIT_SKIPPED__" in html
    assert "const legacyWelcomeShellActive = !e9ShellRequested || needsImmediatePracticeState;" in html


def test_index_gates_legacy_home_runtime_when_e9_owns_shell():
    html = _read(INDEX_HTML)
    assert "if (legacyWelcomeShellActive) {" in html
    assert "if (legacyWelcomeShellActive) renderAdventureMap();" in html
    assert "if (window.__GO_E9_ACTIVE_SHELL__ === 'e9') return;" in html


def test_authenticated_rollout_handoff_reinitializes_shell_after_dom_ready():
    html = _read(INDEX_HTML)
    handoff = html.index("window.__GO_E9_SERVER_FLAGS__ = Object.assign")
    reinit = html.index("window.E9.initShell();", handoff)
    assert reinit > handoff
    assert "typeof window.E9.initShell === 'function'" in html


def test_shell_js_defines_exclusive_shell_contract():
    shell_js = _read(SHELL_JS)
    for selector in [
        "#welcome-state > .guild-hall-hero",
        "#welcome-state > .guild-entry-grid",
        "#skill-map",
        "#welcome-state > .home-left-col",
        "#welcome-state > .home-report",
    ]:
        assert selector in shell_js
    assert "function applyShellState(nextState)" in shell_js
    assert "setAttribute('aria-hidden', 'true')" in shell_js
    assert "setAttribute('inert', '')" in shell_js
    assert "data-e9-prev-tabindex" in shell_js
    assert "global.E9.applyShellState = applyShellState;" in shell_js
    assert "global.E9.resolveRequestedShellMode = resolveRequestedShellMode;" in shell_js


def test_shell_css_enforces_hidden_state_with_specificity():
    css = _read(SHELL_CSS)
    assert "#e9-adventure-shell[hidden]" in css
    assert "display: none !important;" in css
    for marker in [
        "#skill-map[hidden]",
        "#welcome-state > .guild-hall-hero[hidden]",
        "#welcome-state > .guild-entry-grid[hidden]",
        "#welcome-state > .home-left-col[hidden]",
        "#welcome-state > .home-report[hidden]",
    ]:
        assert marker in css


def test_node_shell_exclusivity_contract():
    result = subprocess.run(
        ["node", str(NODE_TEST)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "passed" in result.stdout.lower()
