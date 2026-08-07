"""Focused source-contract tests for authoritative E10 answer reveal gating."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def _function_block(name: str, end_name: str) -> str:
    start = INDEX.index(f"function {name}")
    end = INDEX.index(f"function {end_name}", start)
    return INDEX[start:end]


def test_reveal_requires_authoritative_wrong_result_for_same_question_and_attempt():
    gate = _function_block("_isE10BattleRevealAvailable", "_syncE10BattleActions")
    assert "_isE10BattleActionState()" in gate
    assert "state.result === 'INCORRECT'" in gate
    assert "Number(state.questionId) === Number(currentQ?.id)" in gate
    assert "String(state.attemptId) === String(_mapBattleV1State?.attemptId || '')" in gate


def test_authoritative_renderer_is_the_only_result_source_for_reveal_state():
    renderer = _function_block("_mapBattleV1RenderAuthoritative", "_prepareMapBattleV1ForQuestion")
    recorder = _function_block("_recordE10BattleAnswerResult", "_isE10BattleRevealAvailable")
    assert "_recordE10BattleAnswerResult(response);" in renderer
    assert "_syncE10BattleActions(true)" in renderer
    assert "const result = response && response.result;" in recorder
    assert "result !== 'INCORRECT' && result !== 'CORRECT'" in recorder
    assert "_resetE10BattleRevealState();" in recorder


def test_initial_pending_and_correct_states_keep_reveal_unavailable():
    actions = _function_block("_syncE10BattleActions", "showE10BattleExplanation")
    submit = _function_block("_submitMapBattleV1IfActive", "isBeginnerVillageAdventureResult")
    load = _function_block("loadQuestion", "_cancelAutoSolution")
    assert "_syncE10BattleActions(false)" in load
    assert "state.result === 'INCORRECT'" not in load
    assert "_resetE10BattleRevealState();" in submit
    assert "_syncE10BattleActions(true);" in submit
    assert "explain.disabled = !revealVisible" in actions
    assert "explain.hidden = !revealVisible" in actions


def test_next_question_and_new_attempt_reset_wrong_result_state():
    load = _function_block("loadQuestion", "_cancelAutoSolution")
    prepare = _function_block("_prepareMapBattleV1ForQuestion", "_mapBattleV1IsStaleError")
    assert "_resetE10BattleRevealState();" in load
    assert "_resetE10BattleRevealState();" in prepare
    assert "loadQuestion(" in INDEX


def test_battle_exit_clears_reveal_state_and_action_is_not_callable_when_hidden():
    exit_action = _function_block("returnToAdventureMapAfterEncounter", "renderAdventureZoneMonster")
    reveal_action = _function_block("showE10BattleExplanation", "returnToAdventureMapAfterEncounter")
    assert "_resetE10BattleRevealState();" in exit_action
    assert "if (!_isE10BattleRevealAvailable()) return;" in reveal_action
    assert "submitSRS" not in reveal_action
    assert "/api/srs/review" not in reveal_action
