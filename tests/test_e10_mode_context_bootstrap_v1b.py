"""Executable characterization of the current B6/B7 extraction surface.

This file records current behavior only.  It intentionally does not require
future ModeContext or Bootstrap modules and does not change Product code.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
LOADER = (ROOT / "js" / "game" / "question_loader.js").read_text(encoding="utf-8")
RENDERER = (ROOT / "js" / "game" / "board_renderer.js").read_text(encoding="utf-8")
GAME_SESSION = (ROOT / "js" / "game" / "game_session.js").read_text(encoding="utf-8")
REVIEW_TRANSPORT = (ROOT / "js" / "game" / "review_transport.js").read_text(encoding="utf-8")
LORD = (ROOT / "js" / "game" / "lord_trial_controller.js").read_text(encoding="utf-8")
MAP_BATTLE = (ROOT / "js" / "map_battle_v1_adapter.js").read_text(encoding="utf-8")
RUNNER = ROOT / "tests" / "e2e" / "run_e10_b6_b7_mode_bootstrap_characterization.mjs"


def _slice(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start + len(start_marker))
    return source[start:end]


def _last_json(stdout: str) -> dict:
    decoder = json.JSONDecoder()
    for index in range(len(stdout) - 1, -1, -1):
        if stdout[index] != "{":
            continue
        try:
            value, end = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if not stdout[index + end :].strip():
            return value
    raise AssertionError(f"characterization runner emitted no final JSON: {stdout[-2000:]}")


def test_executable_b6_b7_characterization_runner_is_green():
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
    report = _last_json(result.stdout)
    assert report["status"] == "PASS", output
    assert report["invariants"]["ACTIVE_QUESTION_BROWSER_AUTHORITY_COUNT"] == 1
    assert report["characterization"]["resize"]["REAL_WINDOW_RESIZE_DISPATCH"] == "PASS"


def test_current_bootstrap_order_and_global_aliases_are_characterized():
    scripts = [
        "/wgo/wgo.min.js",
        "/wgo/stone_skin.js",
        "/i18n.js",
        "/community_reward_notifications.js",
        "/js/game/presentation_dispatcher.js",
        "/js/game/presentation_effects_b2.js",
        "/js/game/review_transport.js",
        "/js/game/question_loader.js",
        "/js/game/board_renderer.js",
        "/js/game/game_session.js",
        "/srs.js",
        "/js/game/lord_trial_controller.js",
        "/js/map_battle_v1_adapter.js",
    ]
    positions = [INDEX.index(script) for script in scripts]
    assert positions == sorted(positions)
    assert "global.GoOdysseyQuestionLoader = api" in LOADER
    assert "global.QuestionLoader = api" in LOADER
    assert "global.GoOdysseyBoardRenderer = api" in RENDERER
    assert "global.BoardRenderer = api" in RENDERER
    assert "const _gameSession = window.GoOdysseyGameSession.create(" in INDEX
    assert "const _questionLoader = window.GoOdysseyQuestionLoader.create(" in INDEX
    assert "const _boardRenderer = window.GoOdysseyBoardRenderer.create(" in INDEX


def test_current_mode_matrix_has_distinct_load_and_answer_paths():
    for symbol in (
        "function loadQuestion(",
        "function startAdventureStage(",
        "async function startDailyTraining(",
        "async function _loadBossQuestion(",
        "function initChallengeMode(",
        "function _loadChallengeQuestion(",
        "async function _prepareMapBattleV1ForQuestion",
        "async function _submitMapBattleV1IfActive",
    ):
        assert symbol in INDEX

    daily = _slice(INDEX, "async function startDailyTraining()", "async function _loadDailyQuestion()")
    daily_load = _slice(INDEX, "async function _loadDailyQuestion()", "function _updateDailyProgressUI")
    friend_load = _slice(INDEX, "function _loadChallengeQuestion(idx)", "async function _submitChallengeAnswer")
    friend_submit = _slice(INDEX, "async function _submitChallengeAnswer(qid, correct)", "function _showChallengeComplete")
    board_answer = _slice(INDEX, "function onBoardClick(bx,by)", "function resetProblem")
    lord_answer = _slice(INDEX, "async function _handleBossAnswer", "async function _finishBossBattle")
    map_load = _slice(INDEX, "async function _prepareMapBattleV1ForQuestion", "async function _submitMapBattleV1IfActive")
    map_submit = _slice(INDEX, "async function _submitMapBattleV1IfActive", "function isBeginnerVillageAdventureResult")

    assert "_loadDailyQuestion(" in daily
    assert "loadQuestion(" in daily_load
    assert "loadQuestion(q)" in friend_load
    assert "/api/challenges/friend/" in friend_submit
    assert "SRS.review" not in friend_submit
    assert "submitSRS(3)" in board_answer
    assert "_challengeCorrectHandler" in board_answer
    assert "_challengeWrongHandler" in board_answer
    assert "handleCommittedReview" in lord_answer
    assert "_questionLoader.adoptIdentity" in map_load
    assert "adapter.submit" in map_submit
    submit = _slice(INDEX, "async function submitSRS(grade)", "// ═")
    assert "_submitMapBattleV1IfActive" in submit
    assert "SRS.review" in submit


def test_authority_boundaries_remain_separate_and_observable():
    assert "generation += 1" in LOADER
    assert "function invalidate(" in LOADER
    assert "gameSession.adoptQuestion" in LOADER
    assert "setCurrentQuestion" in LOADER
    for forbidden in ("fetch(", "ReviewTransport", "SRS.review", "nextQuestion", "_handleBossAnswer", "settle", "reward"):
        assert forbidden not in LOADER

    for required in ("mount", "remount", "resize", "clear", "render", "teardown", "destroy"):
        assert required in RENDERER
    for forbidden in ("fetch(", "ReviewTransport", "SRS.review", "nextQuestion", "_handleBossAnswer", "Lord", "MapBattle"):
        assert forbidden not in RENDERER

    assert "QuestionLoader owns the generic question-load epoch" in INDEX
    assert "_questionLoader.invalidate('navigation')" in INDEX
    assert "_mapBattleV1LifecycleGeneration += 1;" not in INDEX
    assert "getCurrentQuestion: () => currentQ" in INDEX
    assert "_questionLoader.adoptIdentity" in INDEX
    assert "currentQ = question;" in INDEX
    assert INDEX.count("currentQ = question;") == 1

    assert "ReviewTransport" in REVIEW_TRANSPORT
    assert "handleCommittedReview" in LORD
    assert "settle" in MAP_BATTLE or "map_battle" in MAP_BATTLE


def test_real_resize_is_registered_and_cannot_reload_or_submit():
    start = INDEX.index("function _resizeVisibleBoard")
    end = INDEX.index("// ═", start)
    resize = INDEX[start:end]
    assert "_boardRenderer.resize({ width, height: width })" in resize
    assert "loadQuestion(" not in resize
    assert "SRS.review" not in resize
    assert "submitSRS(" not in resize
    assert "window.addEventListener('resize', _scheduleVisibleBoardResize);" in INDEX


def test_bootstrap_listener_timer_and_mode_switch_signals_are_recorded():
    assert re.search(r"document\.addEventListener\('DOMContentLoaded'", INDEX)
    assert "window.onload = async" in INDEX
    assert "window.addEventListener('load'" in INDEX
    assert len(re.findall(r"(?:window|document|[A-Za-z_$][\w$]*)\.addEventListener\(", INDEX)) > 0
    assert len(re.findall(r"(?:window\.)?setTimeout\(", INDEX)) > 0
    assert len(re.findall(r"(?:window\.)?setInterval\(", INDEX)) > 0
    assert "returnToAdventureMapAfterEncounter" in INDEX
    assert "_questionLoader.invalidate('navigation')" in INDEX
    assert "window.addEventListener('resize', _scheduleVisibleBoardResize)" in INDEX


def test_gamesession_identity_and_rating_test_remain_bounded():
    assert "QuestionIdentity" in GAME_SESSION
    for required in ("currentQuestionIdentity", "adoptQuestion", "beginReview", "endReview", "invalidate"):
        assert required in GAME_SESSION
    for forbidden in ("WGo", "document.", "fetch(", "board"):
        assert forbidden not in GAME_SESSION
    assert "/rating_test" in (ROOT / "app.py").read_text(encoding="utf-8")
    assert (ROOT / "rating_test.html").is_file()
    assert "/api/rating_test" not in LOADER


def test_b5_characterization_remains_explicitly_reusable():
    b5_runner = ROOT / "tests" / "e2e" / "run_e10_b5_question_loader_board_renderer_characterization.mjs"
    assert b5_runner.is_file()
    source = b5_runner.read_text(encoding="utf-8")
    assert "STALE_LOAD_SUPPRESSION" in source
    assert "REAL_WINDOW_RESIZE_DISPATCH" in source
    assert "BOARDRENDERER_TEARDOWN_IDEMPOTENT" in source
    assert "pytest.mark.skip" not in source
    assert "pytest.mark.xfail" not in source
