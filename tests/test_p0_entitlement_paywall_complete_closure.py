"""Static acceptance contracts for the P0 entitlement closure candidate."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
RUNTIME = (ROOT / "map_battle_runtime.py").read_text(encoding="utf-8")
REVIEW_SERVICE = (ROOT / "review_service.py").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def _block(source, start_marker, end_marker):
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_entitlement_authority_and_free_content_boundary_are_server_owned():
    assert "FREE_DAILY_LIMIT = 20" in APP
    assert "FREE_RANK_MAX = '10k'" in APP
    assert "def question_is_free(q):" in APP
    assert "def is_premium(uid=None):" in APP
    assert "_load_current_premium_entitlement(uid)" in APP
    assert "_admit_map_battle_question_entitlement" in APP
    assert "if not is_premium(uid) and not question_is_free(question):" in APP


def test_locked_question_detail_does_not_expose_paid_sgf_or_solution_fields():
    detail = _block(APP, "def get_question(qid):", "@app.route('/api/save-question'")
    assert "locked  = (not premium) and (not question_is_free(q))" in detail
    assert "content = q.get('content', '') if (premium or not locked) else ''" in detail
    assert "comment = q.get('comment', '') if (premium or not locked) else ''" in detail
    assert "accepted_moves = _question_accepted_moves(q) if (premium or not locked) else []" in detail
    assert "katago_best_move = q.get('katago_best_move', '') if (premium or not locked) else ''" in detail
    assert "score_gap = q.get('score_gap') if (premium or not locked) else None" in detail


def test_daily_training_and_mistake_payloads_use_the_same_free_content_authority():
    training = _block(APP, "def training_daily():", "def _training_contaminated_total")
    mistakes = _block(APP, "def get_mistakes():", "def mistake_stats")
    assert "premium = is_premium(uid)" in training
    assert "(premium or question_is_free(q))" in training
    assert "premium = is_premium(uid)" in mistakes
    assert "locked = (not premium) and (not question_is_free(q))" in mistakes
    assert "'content': '' if locked else q.get('content','')" in mistakes


def test_practice_attempt_issue_rejects_premium_question_for_free_user():
    attempt = _block(APP, "def srs_practice_attempt():", "def srs_practice_answer():")
    assert "if not is_premium(uid) and not question_is_free(question):" in attempt
    assert "'error': 'premium_required'" in attempt
    assert "issue_practice_attempt(" in attempt


def test_map_battle_answer_admission_is_before_judge_and_is_not_a_client_claim():
    settle = RUNTIME[RUNTIME.index("def settle_answer("):]
    reservation = settle.index("reservation = reserve_submission_nonce")
    admission = settle.index("entitlement_admitter(conn, user_id, question)")
    judge = settle.index("outcome = (judge or judge_map_battle_answer_v1)")
    assert reservation < admission < judge
    assert "grade" not in settle[admission:judge]
    assert "correct" not in settle[admission:judge]


def test_map_battle_internal_review_is_a_single_server_handoff_after_admission():
    assert REVIEW_SERVICE.count("internal=True") == 1
    assert "ReviewCommand(" in REVIEW_SERVICE
    assert "submission_id" in REVIEW_SERVICE
    map_answers = _block(APP, "def map_battle_v1_answers():", "def _map_battle_progression_submission")
    assert "entitlement_admitter=_admit_map_battle_answer_entitlement" in map_answers
    assert "_run_map_battle_progression" in map_answers


def test_public_quota_is_atomic_and_shared_with_practice():
    review = _block(APP, "def _srs_review_operation(", "def _dispatch_to_srs_review_operation")
    practice = _block(APP, "def srs_practice_answer():", "def _srs_review_operation")
    for block in (review, practice):
        assert "_lock_user_for_daily_quota" in block
        assert "_daily_quota_snapshot_in_transaction" in block
        assert "_daily_quota_rejection" in block
        assert "return jsonify(rejection), 429" in block
    assert "FOR UPDATE" in APP
    assert "today_count = get_today_free_count(uid)" not in review
    assert "premium_entitled = is_premium(uid)" in review
    assert "if not internal and not premium_entitled and not question_is_free(q_info):" in review


def test_rejection_contract_is_zero_progress_and_has_upgrade_destination():
    rejection = _block(APP, "def _daily_quota_rejection", "def _admit_map_battle_answer_entitlement")
    assert "'error': 'daily_limit'" in rejection
    assert "'code': 'daily_limit'" in rejection
    assert "'upgrade_url': '/upgrade'" in rejection
    assert "_map_battle_error_response" in APP
    assert "body.update(details)" in APP


def test_map_battle_frontend_fails_closed_for_quota_and_premium_errors():
    submit = _block(INDEX, "async function _submitMapBattleV1IfActive", "function isBeginnerVillageAdventureResult")
    prepare = _block(INDEX, "async function _prepareMapBattleV1ForQuestion", "function _mapBattleV1IsStaleError")
    for block in (submit, prepare):
        assert "daily_limit" in block
        assert "premium_required" in block
        assert "_blockAdventureProgression" in block
        assert "return null;" in block
    assert "href=\"/upgrade\"" in INDEX


def test_daily_d5b_exclusion_remains_the_only_explicit_count_exception():
    counter = _block(APP, "def _today_free_count_in_transaction", "def _daily_quota_snapshot_in_transaction")
    assert "DAILY_D5B_SOURCE_PREFIX + '%'" in counter
    assert "source_context=('mbv1:' || s.id)" in counter
    assert "settlement_state='SETTLED'" in counter
