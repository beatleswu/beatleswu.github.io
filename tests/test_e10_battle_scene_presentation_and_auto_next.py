from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def _function_block(name: str, end_name: str | None = None) -> str:
    start = INDEX.index(f"function {name}")
    end = INDEX.index(f"function {end_name}", start) if end_name else len(INDEX)
    return INDEX[start:end]


def test_e10_entry_hydrates_canonical_avatar_and_companion_before_question_render():
    load_question = _function_block("loadQuestion", "onBoardClick")
    hydration = _function_block("_hydrateE10BattlePresentation", "updateQuizPetStatusBadge")

    assert "await _hydrateE10BattlePresentation();" in load_question
    assert load_question.index("await _hydrateE10BattlePresentation();") < load_question.index("currentQ=q;")
    assert "loadPlayerAvatar()" in hydration
    assert "loadQuizPet()" in hydration
    assert "window.__GO_E9_ACTIVE_SHELL__ === 'e9'" in INDEX
    assert "document.body?.dataset.adventureShellActive === 'e9'" in INDEX
    assert "syncHeroCharacterFromAppearance(appearRes.character_key)" in INDEX
    assert "document.getElementById('player-avatar-name')" in INDEX
    assert "document.getElementById('player-avatar-title')" in INDEX
    assert "document.getElementById('quiz-pet')" in INDEX
    assert "document.getElementById('quiz-pet-img')" in INDEX


def test_v1_correct_answer_reuses_feedback_callback_and_next_question_orchestration():
    submit = _function_block("_submitMapBattleV1IfActive", "isBeginnerVillageAdventureResult")

    assert "response.duplicate !== true" in submit
    assert "response.result === 'CORRECT'" in submit
    assert "response.next_action === 'continue'" in submit
    assert "onAnimationComplete" in submit
    assert "updateSRSProgress();" in submit
    assert "nextQuestion();" in submit
    assert submit.index("adapter.submit") < submit.index("_mapBattleV1RenderAuthoritative")
    assert submit.index("onAnimationComplete") < submit.index("nextQuestion();")


def test_v1_defeat_is_completion_flow_and_not_another_combat_attempt():
    submit = _function_block("_submitMapBattleV1IfActive", "isBeginnerVillageAdventureResult")

    assert "response.next_action === 'monster_defeated'" in submit
    assert "showBeginnerVillageEncounterContinuation()" in submit
    assert "returnToAdventureMapAfterEncounter()" in submit
    defeat_branch = submit[submit.index("response.next_action === 'monster_defeated'"):]
    assert defeat_branch.index("showBeginnerVillageEncounterContinuation()") < defeat_branch.index("nextQuestion();") if "nextQuestion();" in defeat_branch else True


def test_v1_non_success_responses_do_not_schedule_auto_next():
    submit = _function_block("_submitMapBattleV1IfActive", "isBeginnerVillageAdventureResult")

    assert "response.duplicate !== true && response.result === 'INCORRECT'" in submit
    assert "response.result === 'CORRECT'" in submit
    assert "response.next_action === 'continue'" in submit
    assert "response.next_action === 'monster_defeated'" in submit
    assert "if (response && response.duplicate !== true && response.result === 'CORRECT')" in submit


def test_damage_authority_and_srs_boundary_remain_unchanged():
    render = _function_block("_mapBattleV1RenderAuthoritative", "_prepareMapBattleV1ForQuestion")
    board_flow = _function_block("onBoardClick", "resetProblem")

    assert "state.monsterHp" in render
    assert "state.playerHp" in render
    assert "response.damage_to_monster" in render
    assert "response.damage_to_player" in render
    assert board_flow.index("_mapBattleV1IsActive()") < board_flow.index("/api/srs/review")
    assert "no battle fallback was used" in board_flow
