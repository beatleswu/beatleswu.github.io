"""A_E10_PWA_FULLSCREEN_STORY_AND_BATTLE_LAYOUT_CORRECTIVE_013.

Owner real-iPad PWA evidence (installed PWA: the layout viewport is 2x the physical
screen -- 1640x2360 portrait / 2360x1640 landscape):

  1. the story frame was a 900x560 box (38-55% of the viewport);
  2. in portrait the world map stayed on screen while a question was active (the
     portrait mirror omitted the native ``#welcome-state.hidden`` companion rule),
     pushing the board below the fold -- the Owner had to rotate to answer;
  3. the landscape battle was capped at ~59% of the width / ~50% of the height.

This wrapper pins the corrective at two levels:

  * the static structure (what it is scoped to, what it may scale, what it must never
    touch) -- tests/e9_node_tests/run_pwa_fullscreen_layout_tests.js;
  * the behaviour, in a real engine at the Owner-evidence viewports, booted through the
    Production boot path and the UNMODIFIED iPad classifier --
    tests/e2e/run_a013_pwa_fullscreen_story_battle_contract.mjs.

Chromium is not native iPad WebKit: this proves layout geometry and state, it does not
replace the Owner's real-device acceptance.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NODE_STATIC = ROOT / "tests" / "e9_node_tests" / "run_pwa_fullscreen_layout_tests.js"
E2E_CONTRACT = ROOT / "tests" / "e2e" / "run_a013_pwa_fullscreen_story_battle_contract.mjs"
CSS = (ROOT / "css" / "e9" / "reference_world_map.css").read_text(encoding="utf-8")
SHELL_CSS = (ROOT / "css" / "e9" / "shell.css").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")

CHROME_CANDIDATES = (
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
)


def _node() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not available")
    return node


def _chrome_available() -> bool:
    return any(Path(candidate).exists() for candidate in CHROME_CANDIDATES)


def test_native_and_mirrored_shell_hide_the_map_when_a_question_is_active():
    """The native pair is shell.css:86 (show) + shell.css:101 (hide on .hidden)."""
    assert re.search(
        r'body\[data-adventure-shell-active="e9"\] #main-row #main-left #welcome-state\.hidden\s*\{\s*display:\s*none !important;',
        SHELL_CSS,
    )
    show = 'html[data-go-portrait-tablet-override] body[data-e10-visual-skin="immersive-rpg"][data-adventure-shell-active="e9"] #main-row #main-left #welcome-state {'
    hide = show.replace("#welcome-state {", "#welcome-state.hidden {")
    assert show in CSS, "the A007 mirror show rule moved or was removed"
    assert hide in CSS, "the portrait mirror lost the native companion rule (map stays on screen in a battle)"
    assert CSS.index(hide) > CSS.index(show)


def test_story_frame_no_longer_capped_by_the_fixed_desktop_modal_size():
    """The generic intro-film scene is min(900px, 94vw) x min(560px, 86vh) in index.html; the
    E10 skin now sizes it from the usable viewport instead (safe-area aware, 16:9 kept)."""
    assert "width: min(900px, 94vw);" in INDEX, "the generic contract this override defeats is gone -- re-derive"
    section = CSS[CSS.index("A_E10_PWA_FULLSCREEN_STORY_AND_BATTLE_LAYOUT_CORRECTIVE_013"):]
    assert "#boss-cinematic.intro-film .boss-cinematic-scene" in section
    assert "aspect-ratio: 16 / 9" in section
    assert "env(safe-area-inset-top" in section and "env(safe-area-inset-bottom" in section
    assert "100dvh" in section


def test_corrective_is_frontend_static_only():
    """No app.py / DB / schema / config change is needed or made by this corrective: every
    rule is CSS in a static, governed-elsewhere asset, and index.html keeps its viewport
    meta and standalone classifier untouched."""
    assert '<meta name="viewport" content="width=device-width, initial-scale=1.0">' in INDEX
    assert "function computeOverride() {" in INDEX
    assert "data-go-portrait-tablet-override" in INDEX


def test_static_css_contract_passes():
    result = subprocess.run(
        [_node(), str(NODE_STATIC)], cwd=ROOT, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert re.search(r"(\d+)/\1 passed", result.stdout), result.stdout


@pytest.mark.skipif(not _chrome_available(), reason="no Chrome/Edge executable for the real-engine contract")
def test_real_engine_story_and_battle_contract_at_owner_evidence_viewports():
    result = subprocess.run(
        [_node(), str(E2E_CONTRACT)],
        cwd=E2E_CONTRACT.parent,
        capture_output=True,
        text=True,
        timeout=590,
        env={**__import__("os").environ, "E10_E2E_REPO_ROOT": str(ROOT)},
    )
    assert result.returncode == 0, (result.stdout[-4000:] + result.stderr[-4000:])
    assert "All A013 fullscreen story + battle assertions passed." in result.stdout
    assert "0 failed" in result.stdout
