"""Executable B6/B7 Product contracts.

These tests exercise the two new pure lifecycle/context modules and verify
that their integration leaves the established authority boundaries intact.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = "3e4a5503fd19bc38b9a51081df51c732683f2228"
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
MODE_CONTEXT = (ROOT / "js" / "game" / "mode_context.js").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "js" / "game" / "game_bootstrap.js").read_text(encoding="utf-8")
RUNNER = ROOT / "tests" / "e2e" / "run_e10_b6_b7_product_contract.mjs"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_b6_b7_product_node_contract_is_green():
    result = subprocess.run(
        ["node", str(RUNNER)], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["status"] == "PASS"
    assert report["MODECONTEXT_CONTRACT"] == "PASS"
    assert report["GAMEBOOTSTRAP_CONTRACT"] == "PASS"
    assert report["INDEX_INTEGRATION"] == "PASS"


def test_mode_context_is_read_only_and_has_one_mode_resolver():
    assert "currentMode" in MODE_CONTEXT
    assert "identityOptions" in MODE_CONTEXT
    assert "presentationMode" in MODE_CONTEXT
    for forbidden in ("fetch(", "ReviewTransport", "SRS", "nextQuestion", "finishTrial", "settle("):
        assert forbidden not in MODE_CONTEXT
    assert MODE_CONTEXT.count("function modeFrom") == 1
    assert "lordIndex" in MODE_CONTEXT
    assert "'daily'" in MODE_CONTEXT
    assert "'friend_challenge'" in MODE_CONTEXT
    assert "'map_battle'" in MODE_CONTEXT


def test_game_bootstrap_owns_lifecycle_without_business_authority():
    for required in (
        "init",
        "destroy",
        "remount",
        "invalidate",
        "registerListener",
        "scheduleTimeout",
        "scheduleInterval",
        "capture",
        "isCurrent",
    ):
        assert required in BOOTSTRAP
    for forbidden in ("fetch(", "ReviewTransport", "SRS", "nextQuestion", "finishTrial", "settle("):
        assert forbidden not in BOOTSTRAP


def test_index_uses_authoritative_mode_and_lifecycle_adapters():
    assert "window.GoOdysseyModeContext.create(" in INDEX
    assert "window.GoOdysseyGameBootstrap.create(" in INDEX
    assert "_modeContext.identityOptions(currentQ)" in INDEX
    assert "_gameBootstrap.registerListener(window, 'resize', _scheduleVisibleBoardResize);" in INDEX
    assert "computerReplyGuard" in INDEX
    assert "replayIsCurrent" in INDEX
    submit_start = INDEX.index("async function submitSRS(grade)")
    submit = INDEX[submit_start : INDEX.index("// ═", submit_start)]
    identity_start = submit.index("const identity =")
    identity_end = submit.index("if (!_gameSession.beginReview", identity_start)
    assert "index: _bossIndex" not in submit[identity_start:identity_end]
    assert "_modeContext.identityOptions(currentQ)" in submit


def test_protected_authority_files_are_unchanged_from_canonical_base():
    # UI-NAV-063 (narrow, owner-authorised): sw.js was released from this
    # byte-freeze and ONLY sw.js. Every static release the project performs
    # must bump the canonical sw.js VERSION, so an indefinite byte-freeze on
    # it would block any future release rather than protect an authority
    # boundary. sw.js is now guarded by
    # test_e9_multi_zone_adventure_cta.py::test_sw_diff_is_version_line_only,
    # which proves the ONLY thing that may change in it is the cache-identity
    # declaration line. BASE is unchanged and every Architecture authority
    # file below stays frozen exactly as before.
    for path in ("js/game/lord_trial_controller.js",):
        assert _git("diff", "--quiet", BASE, "--", path) == ""


def test_b6_b7_packaging_closure_is_explicit():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    build = json.loads((ROOT / "deploy" / "build-manifest.json").read_text(encoding="utf-8"))
    inventory = json.loads((ROOT / "deploy" / "live-static-asset-inventory.json").read_text(encoding="utf-8"))
    for path in ("js/game/mode_context.js", "js/game/game_bootstrap.js"):
        assert f"@app.route('/{path}')" in app
        assert f"COPY {path} ./{path}" in docker
        assert path in build["build_inputs"]["tracked_in_canonical_branch_this_sprint"]
        assert f"/app/{path}" in build["post_build_verification_files"]
        assert path in inventory["eligible_files"]["entries"]
        assert path in inventory["required_in_generation"]["entries"]
    assert len(inventory["required_in_generation"]["entries"]) == 16


def test_control_plane_and_product_scope_are_bounded():
    changed = _git("diff", "--name-only", BASE).splitlines()
    assert not any(path.startswith("scripts/release/") for path in changed)
    assert not any(path.startswith("docs/deployment/") for path in changed)
    assert "questions.json" not in changed
