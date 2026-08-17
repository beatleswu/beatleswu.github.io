from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
E9_SHELL = (ROOT / "css" / "e9" / "shell.css").read_text(encoding="utf-8")


def _function_block(name: str, end_name: str | None = None) -> str:
    start = INDEX.index(f"function {name}")
    end = INDEX.index(f"function {end_name}", start) if end_name else len(INDEX)
    return INDEX[start:end]


def test_e10_entry_hydrates_canonical_avatar_and_companion_before_question_render():
    load_question = _function_block("_loadQuestionImplementation", "onBoardClick")
    hydration = _function_block("_hydrateE10BattlePresentation", "updateQuizPetStatusBadge")

    assert "await _hydrateE10BattlePresentation();" in load_question
    assert load_question.index("await _hydrateE10BattlePresentation();") < load_question.index("commit()")
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
    assert "nextQuestion({ mapBattleV1Transition: true });" in submit
    assert submit.index("adapter.submit") < submit.index("_mapBattleV1RenderAuthoritative")
    assert submit.index("onAnimationComplete") < submit.index("nextQuestion({ mapBattleV1Transition: true });")


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
    submit = _function_block("submitSRS", "loadQuestion")

    assert "state.monsterHp" in render
    assert "state.playerHp" in render
    assert "response.damage_to_monster" in render
    assert "response.damage_to_player" in render
    assert board_flow.index("_mapBattleV1IsActive()") < board_flow.index("submitSRS(0)")
    assert "_submitMapBattleV1IfActive" in submit
    assert "SRS.review(" in submit
    assert "no battle fallback was used" in board_flow


def test_v1_transition_is_generation_scoped_and_has_bounded_idempotent_fallback():
    submit = _function_block("_submitMapBattleV1IfActive", "isBeginnerVillageAdventureResult")
    load_question = _function_block("loadQuestion", "onBoardClick")

    assert "submissionGeneration" in submit
    assert "submittedAttemptId" in submit
    assert "transition.generation !== _mapBattleV1LifecycleGeneration" in submit
    assert "transition.questionId !== Number(currentQ?.id)" in submit
    assert "_mapBattleV1TransitionTimer = setTimeout(onAnimationComplete, fallbackMs);" in submit
    assert "_mapBattleV1Transition = null" in submit
    assert "_clearMapBattleV1Transition();" in load_question
    assert "return _questionLoader.load(q, options);" in load_question
    assert "currentQ !== question" in INDEX


def test_v1_resume_is_one_server_validated_session_record_and_excludes_completed_fallback():
    resume = _function_block("_resolveMapBattleV1Resume", "enterAdventureZoneInPage")

    assert "sessionStorage" in INDEX
    assert "_MAP_BATTLE_V1_RESUME_STORAGE_KEY" in INDEX
    assert "/api/adventure/bootstrap?selected_stage_key=" in resume
    assert "adapter.validateResume" in _function_block("_prepareMapBattleV1ForQuestion", "_mapBattleV1IsStaleError")
    # E10_MAP_BATTLE_V1_RESUME_MASTERY_GUARD_CORRECTION: historical SRS mastery
    # (_adventureQuestionSeen/_adventureQuestionDefeated) is a NEW-target
    # selection preference, not an active-attempt validity gate -- an
    # otherwise-valid, still-ISSUED, unsettled attempt must resume even when
    # its question was mastered long ago (confirmed live in production; see
    # tests/test_e10_map_battle_v1_resume_mastery_guard_correction.py for the
    # full contract). The predicate is intentionally no longer present here;
    # it remains in _pickAdventureTarget/_pickNextAdventureTarget below.
    assert "_adventureQuestionDefeated(target.id)" not in resume
    assert "|| null;" in _function_block("_pickAdventureTarget", "_pickNextAdventureTarget")
    assert "qs[0]" not in _function_block("_pickAdventureTarget", "_resolveMapBattleV1Resume")


def test_principal_battle_contract_is_true_v1_and_never_legacy_srs_review():
    adapter = (ROOT / "js" / "map_battle_v1_adapter.js").read_text(encoding="utf-8")
    submit = _function_block("_submitMapBattleV1IfActive", "isBeginnerVillageAdventureResult")

    assert "POST" in adapter
    assert "/api/adventure/map-battles/v1/attempts" in adapter
    assert "/api/adventure/map-battles/v1/answers" in adapter
    assert "_mapBattleV1IsActive()" in submit
    assert "no battle fallback was used" in submit or "no battle fallback was used" in INDEX
    assert "if (!_bossMode && _mapBattleV1Mode === 'active' && _mapBattleV1State)" in INDEX


def test_automatic_answer_feedback_renders_without_scrolling_the_viewport():
    explanation = _function_block("showExplanation", "_drawCoordOverlay")
    explicit_reveal = _function_block("showE10BattleExplanation", "returnToAdventureMapAfterEncounter")
    load_question = _function_block("loadQuestion", "_cancelAutoSolution")
    board_flow = _function_block("onBoardClick", "resetProblem")

    assert "function showExplanation(wrongMove, { reveal = false } = {})" in explanation
    assert "if (reveal) _revealExplanationPanel(panel);" in explanation
    assert "showExplanation(_lastWrongMove || null, { reveal: true });" in explicit_reveal
    assert "scrollIntoView" not in explicit_reveal
    assert board_flow.count("showExplanation({x, y});") == 3
    assert "showExplanation();submitSRS(3)" in board_flow
    assert "showExplanation(null, { reveal: true });" in _function_block("showAnswer", "_renderShopStatus")
    assert "hideExplanation();" in load_question


def test_windowed_desktop_keeps_combat_panel_beside_board():
    assert "(pointer: coarse) and (hover: none) and (any-hover: none)" in INDEX
    assert "(any-pointer: fine)" in INDEX
    assert "@media (max-width: 1024px) and (any-hover: hover)" in INDEX
    compact = INDEX.split(
        "@media (max-width: 1024px) and (any-hover: hover)", 1
    )[1].split("@media (max-width: 768px)", 1)[0]
    assert "#main-row" in compact
    assert "display: grid" in compact
    assert "minmax(260px, 320px)" in compact
    assert (
        'body[data-adventure-shell-active="e9"]:not(:has(#welcome-state.hidden)) #main-row'
        in E9_SHELL
    )
    assert 'body[data-adventure-shell-active="e9"] #main-row {' not in E9_SHELL
