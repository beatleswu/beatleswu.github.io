from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")


def test_lord_transition_has_bounded_observability_and_real_board_gate():
    required_events = {
        "BOSS_TRANSITION_FROM_INDEX",
        "BOSS_TRANSITION_FROM_QID",
        "BOSS_TRANSITION_TO_INDEX",
        "BOSS_TRANSITION_TO_QID",
        "LOAD_BOSS_QUESTION_ENTER",
        "LOAD_BOSS_QUESTION_RESOLVED_QID",
        "LOADQUESTION_ENTER_QID",
        "LOADQUESTION_GENERATION",
        "HYDRATION_BEGIN",
        "HYDRATION_END",
        "GENERATION_VALID_AFTER_HYDRATION",
        "CURRENT_Q_ASSIGNED",
        "SGF_PARSE_OK",
        "BOARD_INIT_BEGIN",
        "BOARD_INIT_END",
        "CURRENT_NODE_READY",
        "BOARD_RENDER_FINGERPRINT",
        "LOADQUESTION_RETURN_VALUE",
        "BOSS_TRANSITION_EXCEPTION",
    }
    for event in required_events:
        assert f"'{event}'" in INDEX
    assert "__GO_E10_ACCEPTANCE_DIAGNOSTIC__" in INDEX
    assert "trace.length > 300" in INDEX


def test_boss_load_waits_for_actual_board_setup_and_fails_closed():
    # currentQ/currentProblem/currentNode/board being correct is necessary
    # but was proven insufficient on real iPad Safari (JS state can be right
    # while the visible canvas is still the previous question) -- the visible-
    # board contract added in e10-lord-trial-one-shot-safari-recovery-001
    # additionally requires an actual, correctly-stamped, non-zero-rect
    # canvas before a Boss transition is allowed to declare success, with one
    # bounded automatic recovery remount and an explicit fail-closed UI if
    # that still does not hold.
    assert ": await loadQuestion(q, { attemptNumber });" in INDEX
    assert "const boardReady = loaded === true" in INDEX
    assert "&& !!currentProblem" in INDEX
    assert "&& !!currentNode" in INDEX
    assert "&& !!board" in INDEX
    assert "setMsg(I18n.t('index.boss.question_load_fail'), 'err');" in INDEX
    assert "const _setupReady = await _runQuestionBoardSetup" in INDEX
    assert "function _runQuestionBoardSetup" in INDEX
    assert "function _verifyVisibleQuestionBoard(question, attemptNumber)" in INDEX
    assert "function _settleVisibleBossQuestionBoard(q)" in INDEX
    assert "function _failCloseBossQuestionBoard(q, diagnostics = {})" in INDEX
    assert "_questionBoardFailedClosed = true;" in INDEX
    assert "'index.boss.board_transition_failed'" in INDEX
    assert "'index.boss.board_transition_failed'" in I18N


def test_boss_transition_does_not_create_a_second_next_authority():
    assert "if (_bossMode) {" in INDEX
    assert "_syncBossNextButton();" in INDEX
    assert "next.disabled = _bossMode;" in INDEX
    assert "next.hidden = _bossMode;" in INDEX
    assert "if (loaded !== true) return false;" in INDEX
    assert "function nextQuestion({ mapBattleV1Transition = false } = {})" in INDEX


def test_daily_limit_is_not_the_boss_transition_authority():
    assert "function _dailyLimitBlocksCurrentFlow()" in INDEX
    assert "return _dailyLimitReached && !_challengeId && !_bossMode;" in INDEX
    assert "if (_bossMode) {" in INDEX
    assert "console.warn('[BOSS] daily_limit review rejected; no progress recorded');" in INDEX


def test_zone2_entry_primes_reusable_audio_from_user_gesture():
    assert "if (zone.key === 'k21_25'" in INDEX
    assert "await _unlockIntroAudioFromGesture();" in INDEX


def test_zone2_automatic_phases_require_explicit_audio_gesture_when_unprimed():
    helper = INDEX[INDEX.index("function _startZone2CinematicWithGesture"):INDEX.index("function playZone2BossReadyFilm")]
    assert "if (_introAudioUnlocked)" in helper
    assert "dataset.zone2AudioGesturePending" in helper
    assert "I18n.t('index.film.audio_gesture_required')" in helper
    assert "btn.onclick = async () =>" in helper
    assert "await _unlockIntroAudioFromGesture();" in helper
    assert "void playNewbieVillageIntroFilm(zone" in helper
    assert "'index.film.audio_gesture_required'" in I18N


def test_all_shared_question_modes_keep_the_same_return_map_control():
    audited_modes = (
        "ordinary practice",
        "Adventure zone practice",
        "Map Battle",
        "Lord first-clear",
        "Lord replay",
        "challenge",
        "daily training",
        "mistake/review",
        "guild",
        "premium",
    )
    e2e = (ROOT / "tests" / "e2e" / "run_e10_owner_ipad_acceptance_hotfix_002.mjs").read_text(encoding="utf-8")
    assert "async function runReturnMapModeMatrix(browser, origin)" in e2e
    assert "returnMapModeMatrix" in e2e
    assert "forbiddenRequests" in e2e
    assert "page.waitForURL(/\\/\\?adventure=1/" in e2e
    for mode in audited_modes:
        assert f"name: '{mode}'" in e2e
    assert 'id="btn-return-map"' in INDEX
    assert 'onclick="returnToAdventureMap()"' in INDEX
    assert "window.location.href = '/?adventure=1';" in INDEX
    assert "void _unlockIntroAudioFromGesture();" in INDEX
    assert "function replayIntroFilm()" in INDEX
    assert "await _unlockIntroAudioFromGesture();" in INDEX


def test_zone2_audio_contract_keeps_silent_shot_and_recorded_voice_only():
    assert "if (!beat.audioSrc)" in INDEX
    assert "finishSilently();" in INDEX
    # The runtime's browser voice path is explicit opt-in only; no shipped
    # Zone 2 beat opts into it.
    zone2_start = INDEX.index("zone.key === 'k21_25'")
    zone2_end = INDEX.find("zone.key === 'k16_20'", zone2_start)
    zone2_slice = INDEX[zone2_start:zone2_end if zone2_end != -1 else zone2_start + 60000]
    assert "allowTtsFallback: true" not in zone2_slice


def test_shared_return_map_control_is_localized_and_history_independent():
    assert 'id="btn-return-map"' in INDEX
    assert 'onclick="returnToAdventureMap()"' in INDEX
    assert 'data-i18n="index.boss.back_to_map"' in INDEX
    assert "function returnToAdventureMap()" in INDEX
    assert "returnToAdventureMapAfterEncounter();" in INDEX
    assert "window.location.href = '/?adventure=1';" in INDEX
    assert "history.back()" not in INDEX
    assert "function _setDailyLimitNavLocked(locked)" in INDEX
    assert "if (btn.id === 'btn-return-map' || btn.id === 'btn-adventure-return') return;" in INDEX
    assert "'index.boss.back_to_map'" in I18N


def test_return_map_does_not_clear_boss_attempt_or_submit_gameplay():
    start = INDEX.index("function returnToAdventureMapAfterEncounter()")
    end = INDEX.find("function renderAdventureZoneMonster", start)
    body = INDEX[start:end]
    assert "window.location.href = '/?adventure=1';" in body
    assert "_bossMode = false" not in body
    assert "/api/srs/review" not in body
    assert "/api/adventure/boss/finish" not in body
    assert "localStorage.removeItem" not in body


def test_i18n_contains_english_and_traditional_return_map_contract():
    marker = "'index.boss.back_to_map'"
    start = I18N.index(marker)
    row = I18N[start:I18N.find("\n", start)]
    assert "Back to Map" in row
    assert "返回地圖" in row
