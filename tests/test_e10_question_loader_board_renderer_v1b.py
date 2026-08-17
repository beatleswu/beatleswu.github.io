"""B5 QuestionLoader/BoardRenderer product contracts."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
MANIFEST = json.loads((ROOT / "deploy" / "build-manifest.json").read_text(encoding="utf-8"))
INVENTORY = json.loads((ROOT / "deploy" / "live-static-asset-inventory.json").read_text(encoding="utf-8"))
LOADER = (ROOT / "js" / "game" / "question_loader.js").read_text(encoding="utf-8")
RENDERER = (ROOT / "js" / "game" / "board_renderer.js").read_text(encoding="utf-8")
GAME_SESSION = (ROOT / "js" / "game" / "game_session.js").read_text(encoding="utf-8")
RUNNER = ROOT / "tests" / "e2e" / "run_e10_b5_question_loader_board_renderer_characterization.mjs"


def _block(source: str, name: str, next_name: str) -> str:
    start = source.index(f"function {name}")
    end = source.index(f"function {next_name}", start)
    return source[start:end]


def test_question_loader_is_real_generic_owner_and_has_no_gameplay_authority():
    assert "global.GoOdysseyQuestionLoader = api" in LOADER
    assert "generation += 1" in LOADER
    assert "isCurrent" in LOADER
    assert "setCurrentQuestion" in LOADER
    assert "gameSession.adoptQuestion" in LOADER
    assert "adoptIdentity" in LOADER
    for forbidden in ("fetch(", "ReviewTransport", "SRS.review", "nextQuestion", "_handleBossAnswer", "settle", "reward"):
        assert forbidden not in LOADER


def test_board_renderer_owns_visual_lifecycle_only():
    assert "global.GoOdysseyBoardRenderer = api" in RENDERER
    for required in ("mount", "remount", "resize", "clear", "teardown", "destroy", "render"):
        assert required in RENDERER
    for forbidden in ("fetch(", "ReviewTransport", "SRS.review", "nextQuestion", "_handleBossAnswer", "Lord", "MapBattle"):
        assert forbidden not in RENDERER


def test_question_loader_and_board_renderer_global_aliases_are_present():
    assert "global.GoOdysseyQuestionLoader = api" in LOADER
    assert "global.QuestionLoader = api" in LOADER
    assert "global.GoOdysseyBoardRenderer = api" in RENDERER
    assert "global.BoardRenderer = api" in RENDERER


def test_load_question_is_compatibility_adapter_only():
    load = _block(INDEX, "loadQuestion", "_loadQuestionImplementation")
    assert "_questionLoader.load(q, options)" in load
    assert "fetch(" not in load
    assert "currentQ=q" not in load
    assert "SRS.review" not in load


def test_currentq_is_a_single_loader_projection_and_gamesession_adopts_on_load():
    assert INDEX.count("currentQ = question;") == 1
    assert "setCurrentQuestion: (question, context)" in INDEX
    assert "gameSession: _gameSession" in INDEX
    assert "adoptQuestion" in LOADER
    assert "_questionLoader.adoptIdentity" in INDEX
    assert "getCurrentQuestion: () => currentQ" in INDEX
    assert "getLifecycleGeneration: () => _mapBattleV1LifecycleGeneration" in INDEX


def test_legacy_load_question_and_generic_generation_do_not_duplicate_authority():
    assert "LEGACY_LOADQUESTION_AUTHORITY" not in INDEX or "adapter" in INDEX.lower()
    assert "QuestionLoader owns the generic question-load epoch" in INDEX
    assert "_questionLoader.invalidate('navigation')" in INDEX
    assert "_mapBattleV1LifecycleGeneration += 1;" not in INDEX
    assert "_questionLoader.generation()" in INDEX


def test_real_resize_handler_routes_to_renderer_and_never_reloads_question():
    resize_start = INDEX.index("function _resizeVisibleBoard")
    resize_end = INDEX.index("// ═", resize_start)
    resize = INDEX[resize_start:resize_end]
    assert "_boardRenderer.resize({ width, height: width })" in resize
    assert "loadQuestion(" not in resize
    assert "SRS.review" not in resize
    assert "window.addEventListener('resize', _scheduleVisibleBoardResize);" in INDEX
    assert "window.addEventListener('orientationchange', _scheduleVisibleBoardResize);" in INDEX


def test_question_loader_handoff_preserves_mapbattle_and_lord_boundaries():
    assert "MAPBATTLE" not in LOADER.upper()
    assert "_submitMapBattleV1IfActive" in INDEX
    assert "await _submitMapBattleV1IfActive(_mapBattleV1Moves);" in INDEX
    assert "if (_bossMode)" in _block(INDEX, "nextQuestion", "prevQuestion")
    assert "loadNextQuestion: () => _loadBossQuestion()" in INDEX
    assert "MapBattle" in INDEX


def test_gamesession_remains_identity_only_and_separate_from_rendering():
    assert "QuestionIdentity" in GAME_SESSION
    assert "currentQuestionIdentity()" in GAME_SESSION
    assert "adoptQuestion" in GAME_SESSION
    assert "beginReview" in GAME_SESSION
    assert "invalidate" in GAME_SESSION
    for forbidden in ("WGo", "document.", "fetch(", "board"):
        assert forbidden not in GAME_SESSION


def test_six_mode_paths_remain_present_and_rating_test_is_separate():
    for symbol in (
        "function nextQuestion",
        "function _loadDailyQuestion",
        "function _loadChallengeQuestion",
        "function _loadBossQuestion",
        "function enterAdventureZoneInPage",
        "_prepareMapBattleV1ForQuestion",
    ):
        assert symbol in INDEX
    assert "@app.route('/rating_test')" in APP
    assert (ROOT / "rating_test.html").is_file()
    assert "/api/rating_test" not in LOADER


def test_packaging_has_explicit_runtime_module_closure():
    for module in ("js/game/question_loader.js", "js/game/board_renderer.js"):
        assert f"COPY {module} ./{module}" in DOCKERFILE
        assert module in MANIFEST["build_inputs"]["tracked_in_canonical_branch_this_sprint"]
        assert module in INVENTORY["eligible_files"]["entries"]
        assert module in INVENTORY["required_in_generation"]["entries"]
    assert "@app.route('/js/game/question_loader.js')" in APP
    assert "@app.route('/js/game/board_renderer.js')" in APP


def test_real_characterization_runner_has_no_skip_or_xfail_and_passes():
    source = RUNNER.read_text(encoding="utf-8")
    assert "pytest.mark.skip" not in source
    assert "pytest.mark.xfail" not in source
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
    assert '"REAL_WINDOW_RESIZE_DISPATCH":"PASS"' in result.stdout, output
