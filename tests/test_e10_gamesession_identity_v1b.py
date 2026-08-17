"""B4 GameSession + Question Identity characterization contracts.

Preparation-only. The unchanged assertions in this file lock down *existing*
observable behaviour of the real, currently-committed source
(``index.html``, ``srs.js``, ``js/game/lord_trial_controller.js``,
``js/game/presentation_dispatcher.js``) at the B2 base
(``de3194bd1a45a990466959a04db0a3d63daa3631``). The corrected C2/C3 seam
assertions encode the B4 ``GameSession`` integration contract expected when
``index.html`` adopts it. This test-only lane changes no Product file.

These are source-structural characterization tests, not runtime/browser
tests: they freeze the exact code patterns that currently implement
question-identity/staleness handling across the B4 ``GameSession`` seam,
``LordTrialController``'s separate in-flight and last-settled keys, and
``_createB2PresentationScope``'s live isCurrent() check. DEDUP_KEYS_MERGED=NO:
the GameSession review-request guard is distinct from Lord's settlement keys;
``inFlightKey`` is cleared in ``finally`` while ``lastSettledKey`` survives to
reject a duplicate settlement. On this pre-integration D base, C2/C3 are
expected-red until ``index.html`` adopts GameSession; the remaining
characterization checks retain their existing preparation boundary.

The two future-seam cases (C12/C13) remain deliberately uncommitted as
failing tests; see
``docs/planning/e10_frontend_v1b_b4_gamesession_question_identity_packet.md``
section 13.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "index.html"
SRS_PATH = ROOT / "srs.js"
LORD_CONTROLLER_PATH = ROOT / "js" / "game" / "lord_trial_controller.js"
PRESENTATION_DISPATCHER_PATH = ROOT / "js" / "game" / "presentation_dispatcher.js"

INDEX = INDEX_PATH.read_text(encoding="utf-8")
SRS = SRS_PATH.read_text(encoding="utf-8")
LORD_CONTROLLER = LORD_CONTROLLER_PATH.read_text(encoding="utf-8")
PRESENTATION_DISPATCHER = PRESENTATION_DISPATCHER_PATH.read_text(encoding="utf-8")


def _function_block(source: str, name: str, end_name: str) -> str:
    start = source.index(f"function {name}")
    end = source.index(f"function {end_name}", start)
    return source[start:end]


# ---------------------------------------------------------------------------
# C1 -- current question replacement semantics: the generation + object-
# identity double-check exists at every stale-guard call site in
# loadQuestion()/_runQuestionBoardSetup().
# ---------------------------------------------------------------------------

def test_c1_question_replacement_stale_guard_pattern_present_at_all_sites():
    load_question = _function_block(INDEX, "loadQuestion", "onBoardClick")
    stale_guard_occurrences = re.findall(
        r"generation\s*!==\s*_mapBattleV1LifecycleGeneration\s*(?:\|\|\s*currentQ\s*!==\s*q(?:uestion)?)?",
        load_question,
    )
    # loadQuestion itself contains at least 3 generation checks (post-
    # hydration, pre-parse, post-prepare); _runQuestionBoardSetup contains a
    # 4th. Both the generation counter AND the currentQ object-identity
    # check must appear together at least once -- an id-only check would be
    # a real behavioural change, not a rename.
    assert len(stale_guard_occurrences) >= 3
    assert "currentQ !== q" in load_question or "currentQ !== question" in load_question

    board_setup = INDEX[INDEX.index("function _runQuestionBoardSetup"):]
    board_setup = board_setup[: board_setup.index("\n\n\n") if "\n\n\n" in board_setup else 4000]
    assert "generation !== _mapBattleV1LifecycleGeneration" in board_setup
    assert "currentQ !== question" in board_setup


def test_c1_lifecycle_generation_increments_exactly_in_loadquestion():
    load_question = _function_block(INDEX, "loadQuestion", "onBoardClick")
    assert "const generation = ++_mapBattleV1LifecycleGeneration;" in load_question
    # currentQ is assigned exactly once, after the post-hydration stale check
    # and before the pre-parse stale check re-reads it.
    assign_index = load_question.index("currentQ=q;")
    first_guard_index = load_question.index("stale_after_hydration")
    second_guard_index = load_question.index("stale_before_parse")
    assert first_guard_index < assign_index < second_guard_index


# ---------------------------------------------------------------------------
# C2 -- submitSRS adopts a bounded GameSession identity, snapshots review
# metadata once, and preserves the current question-id/metadata semantics.
# ---------------------------------------------------------------------------

def test_c2_submit_srs_adopts_bounded_identity_and_reuses_review_metadata():
    submit_srs = _function_block(INDEX, "submitSRS", "loadQuestion")
    metadata_snapshot = "const reviewMetadata = _currentReviewMetadata();"
    identity_adoption = "const identity = _gameSession.adoptQuestion(currentQ, {"
    review_call = "SRS.review(currentQ.id,grade,unit,unitDone,reviewMetadata)"

    assert metadata_snapshot in submit_srs
    assert submit_srs.count("_currentReviewMetadata()") == 1
    assert identity_adoption in submit_srs
    identity_start = submit_srs.index(identity_adoption)
    identity_end = submit_srs.index("});", identity_start) + len("});")
    assert "reviewMetadata," in submit_srs[identity_start:identity_end]
    assert review_call in submit_srs
    assert submit_srs.index(metadata_snapshot) < identity_start < submit_srs.index(review_call)


def test_c2_srs_review_posts_question_id_verbatim():
    assert "question_id: qid" in SRS or "question_id:qid" in SRS


# ---------------------------------------------------------------------------
# C3 -- GameSession owns submitSRS's review-request guard, distinct from
# Lord's settlement markers, and releases it in finally.
# ---------------------------------------------------------------------------

def test_c3_submit_srs_uses_gamesession_review_guard_distinct_from_lord_settlement():
    submit_srs = _function_block(INDEX, "submitSRS", "loadQuestion")
    begin_guard = "if (!_gameSession.beginReview(identity)) return;"
    end_guard = "})().finally(() => _gameSession.endReview(identity));"

    assert begin_guard in submit_srs
    assert end_guard in submit_srs
    assert "let inFlightKey = null;" in LORD_CONTROLLER
    assert "let lastSettledKey = null;" in LORD_CONTROLLER
    assert "inFlightKey" not in submit_srs
    assert "lastSettledKey" not in submit_srs
    # The legacy key is no longer the active B4 submit review-request guard.
    assert "_reviewRequestInFlightKey" not in submit_srs
    assert "reviewRequestKey" not in submit_srs

    begin_index = submit_srs.index(begin_guard)
    async_index = submit_srs.index("return (async () => {")
    finally_index = submit_srs.index(".finally(() =>", async_index)
    assert begin_index < async_index < finally_index


# ---------------------------------------------------------------------------
# C4 / C6 -- stale callback cannot mutate newer question/session, and a
# duplicate settlement is rejected. Both live in LordTrialController.
# ---------------------------------------------------------------------------

def test_c4_lord_controller_rejects_stale_review_identity():
    assert "reason: 'stale_review_identity'" in LORD_CONTROLLER
    handle = LORD_CONTROLLER[LORD_CONTROLLER.index("async function handleCommittedReview"):]
    stale_check = handle[: handle.index("stale_review_identity") + 40]
    assert "submittedIndex !== Number(context.index)" in stale_check
    assert "submittedQuestionId !== currentQuestionId" in stale_check


def test_c6_lord_controller_rejects_duplicate_settlement():
    assert "reason: 'duplicate_review_identity'" in LORD_CONTROLLER
    # Lord keeps two semantically distinct markers even though both are set
    # from this settlement identity when a transition starts.
    assert "let inFlightKey = null;" in LORD_CONTROLLER
    assert "let lastSettledKey = null;" in LORD_CONTROLLER
    assert "const settlementKey = `${attemptId || 'active'}:${submittedIndex}:${submittedQuestionId}`;" in LORD_CONTROLLER
    assert "inFlightKey = settlementKey;" in LORD_CONTROLLER
    assert "lastSettledKey = settlementKey;" in LORD_CONTROLLER
    assert "inFlightKey === settlementKey || lastSettledKey === settlementKey" in LORD_CONTROLLER
    finally_block = LORD_CONTROLLER[LORD_CONTROLLER.index("finally {", LORD_CONTROLLER.index("inFlightKey = settlementKey;")):]
    assert "inFlightKey = null;" in finally_block
    assert "lastSettledKey = settlementKey;" not in finally_block


def test_c4_c6_lord_controller_owns_no_dom_transport_or_board():
    # GameSession/LordTrialController boundary: no fetch, no document, no
    # WGo/board reference anywhere in the controller module.
    for forbidden in ("fetch(", "document.", "WGo", "board.", "initBoard"):
        assert forbidden not in LORD_CONTROLLER, forbidden


# ---------------------------------------------------------------------------
# C5 -- Lord question identity/attempt association: _bossAttemptId /
# _bossIndex / _bossQueue wiring into the controller's context.
# ---------------------------------------------------------------------------

def test_c5_lord_context_carries_attempt_index_and_question_identity():
    get_lord_controller = _function_block(INDEX, "_getLordTrialController", "_recordLordPresentationFailure")
    assert "attemptId: _bossAttemptId" in get_lord_controller
    assert "index: _bossIndex" in get_lord_controller
    assert "questionId: Number(currentQ?.id)" in get_lord_controller
    assert "queue: _bossQueue" in get_lord_controller
    assert "applyProgress: ({ index, correct }) => {" in get_lord_controller
    assert "_bossIndex = index;" in get_lord_controller
    assert "_bossCorrect = correct;" in get_lord_controller


def test_c5_boss_start_resumes_index_and_correct_from_server():
    start_boss = _function_block(INDEX, "_startBossBattleNow", "hideBossCinematic")
    assert "_bossAttemptId = data.attempt_id;" in start_boss
    assert "_bossQueue = data.question_ids || [];" in start_boss
    assert "serverResumeIndex = Number(data.resume_index);" in start_boss
    assert "if (_lordTrialController) _lordTrialController.reset();" in start_boss


# ---------------------------------------------------------------------------
# C7 -- normal-mode identity: nextQuestion's Boss-guard-then-generic-advance
# shape is unchanged.
# ---------------------------------------------------------------------------

def test_c7_next_question_guards_boss_then_falls_through_to_generic_advance():
    next_question = _function_block(INDEX, "nextQuestion", "loadQuestion") \
        if "function loadQuestion" in INDEX[INDEX.index("function nextQuestion"):] \
        else INDEX[INDEX.index("function nextQuestion({"):INDEX.index("function nextQuestion({") + 6000]
    boss_guard = next_question[next_question.index("if (_bossMode)"):]
    boss_guard = boss_guard[: boss_guard.index("if (mapBattleV1Transition)")]
    assert "_syncBossNextButton();" in boss_guard
    assert "return;" in boss_guard
    assert "loadQuestion" not in boss_guard


# ---------------------------------------------------------------------------
# C8 -- Adventure identity: _pickNextAdventureTarget excludes the
# just-answered id and prefers unseen over seen-but-undefeated.
# ---------------------------------------------------------------------------

def test_c8_pick_next_adventure_target_excludes_current_and_prefers_unseen():
    fn = _function_block(INDEX, "_pickNextAdventureTarget", "_resolveMapBattleV1Resume")
    assert "Number(q.id) !== Number(currentId)" in fn
    assert "!_adventureQuestionSeen(q.id)" in fn
    assert "!_adventureQuestionDefeated(q.id)" in fn


# ---------------------------------------------------------------------------
# C9 -- presentation context does not become session authority: the
# committed Lord transition runs and is awaited BEFORE presentation
# dispatch is attempted, and a presentation failure cannot roll it back
# (separate try/catch, no shared state mutation across the boundary).
# ---------------------------------------------------------------------------

def test_c9_lord_authority_runs_and_is_awaited_before_presentation_dispatch():
    submit_srs = _function_block(INDEX, "submitSRS", "loadQuestion")
    boss_branch = submit_srs[submit_srs.index("if (_bossMode) {"):]
    boss_branch = boss_branch[: boss_branch.index("_todayTotal++")]
    handle_call = boss_branch.index("await _handleBossAnswer(grade, bossAnswerContext);")
    dispatch_call = submit_srs.index("_dispatchCommittedReviewPresentation(committedPresentation, grade, lordController);")
    handle_call_abs = submit_srs.index("if (_bossMode) {") + handle_call
    assert handle_call_abs < dispatch_call
    # Separate try/catch blocks -- a presentation exception must not unwind
    # into (or appear to roll back) the already-awaited Lord transition.
    between = submit_srs[handle_call_abs:dispatch_call]
    assert between.count("try {") >= 1
    assert between.count("catch (error) {") >= 1


def test_c9_presentation_scope_is_current_reads_live_globals_not_snapshot():
    scope_fn = _function_block(INDEX, "_createB2PresentationScope", "_createB2PresentationDependencies")
    is_current = scope_fn[scope_fn.index("isCurrent: () =>"):]
    is_current = is_current[: is_current.index("};") + 2]
    assert "currentQ === question" in is_current
    assert "_mapBattleV1LifecycleGeneration === generation" in is_current
    # The snapshot's own lifecycleGeneration field is captured for
    # description purposes but must not be what isCurrent() compares
    # against -- it must re-read the live counter.
    assert "answerLifecycleGeneration" not in is_current


# ---------------------------------------------------------------------------
# C10 -- ReviewTransport/B3 does not become GameSession owner: neither the
# Lord controller nor the presentation dispatcher ever calls
# /api/srs/review or owns a raw fetch to it.
# ---------------------------------------------------------------------------

def test_c10_lord_controller_never_calls_review_transport():
    assert "/api/srs/review" not in LORD_CONTROLLER
    assert "fetch(" not in LORD_CONTROLLER


def test_c10_presentation_dispatcher_never_calls_review_transport():
    assert "/api/srs/review" not in PRESENTATION_DISPATCHER
    # The only fetch target inside the dispatcher is the non-authoritative
    # badge-seen acknowledgement.
    fetch_targets = re.findall(r"fetchImpl\(\s*'([^']+)'", PRESENTATION_DISPATCHER)
    assert fetch_targets == ["/api/badges/seen"]


# ---------------------------------------------------------------------------
# C11 -- Friend Challenge's dual-transport fact: a correct answer goes
# through submitSRS (real ReviewTransport call) AND a separate challenge
# endpoint; a wrong answer calls the challenge handler immediately and
# fires a separate (non-submitSRS) ReviewTransport request in parallel.
# This characterizes an existing fact, not a new assertion of correctness.
# ---------------------------------------------------------------------------

def test_c11_friend_challenge_uses_a_second_review_transport():
    assert "/api/challenges/friend/${cid}/answer" in INDEX or \
        "/api/challenges/friend/${_challengeId}/answer" in INDEX


def test_c11_friend_challenge_correct_path_still_calls_submit_srs():
    on_board_click = _function_block(INDEX, "onBoardClick", "resetProblem")
    correct_branch = on_board_click[on_board_click.index("if (_mapBattleV1IsActive()) _mapBattleV1Moves.push"):]
    first_solved_branch = correct_branch[: correct_branch.index("answering=true;")]
    assert "submitSRS(3)" in first_solved_branch
    assert "window._challengeCorrectHandler" in first_solved_branch
    # submitSRS is not awaited before the challenge handler fires -- an
    # existing fact this test freezes, not a recommendation.
    assert "await submitSRS(3)" not in first_solved_branch


def test_c11_friend_challenge_wrong_path_bypasses_submit_srs_with_separate_transport():
    on_board_click = _function_block(INDEX, "onBoardClick", "resetProblem")
    # Narrow to the generic (non-MapBattle, non-Boss) wrong-answer branch
    # specifically -- the earlier MapBattle-active and Boss-mode branches in
    # the same if(!matched){...} block each call submitSRS(0) themselves
    # and must not leak into this slice.
    generic_wrong_start = on_board_click.index("if(_challengeId&&window._challengeWrongHandler)")
    wrong_branch = on_board_click[generic_wrong_start:]
    wrong_branch = wrong_branch[: wrong_branch.index("if (_mapBattleV1IsActive()) _mapBattleV1Moves.push")]
    assert "window._challengeWrongHandler" in wrong_branch
    # B3 ReviewTransport remains the sole review HTTP authority. This is the
    # existing Friend Challenge second transport fact, not a B4 migration.
    assert "window.ReviewTransport.review(observerCommand)" in wrong_branch
    # This separate ReviewTransport call does not go through submitSRS --
    # confirmed by absence of a submitSRS( call anywhere in the generic
    # wrong-answer branch.
    assert "submitSRS(" not in wrong_branch


# ---------------------------------------------------------------------------
# Rating test is confirmed out of scope: a separate page, not shared
# runtime. This is a documentation assertion, not a behavioural one.
# ---------------------------------------------------------------------------

def test_rating_test_is_a_separate_page_not_shared_runtime():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "@app.route('/rating_test')" in app_source
    assert (ROOT / "rating_test.html").is_file()
    # index.html only ever navigates to it via a full-page redirect, never
    # an in-page mode switch comparable to _bossMode/_dailyMode/_challengeId.
    assert "window.location.href = `/rating_test" in INDEX or \
        "/rating_test?placement=1" in INDEX
