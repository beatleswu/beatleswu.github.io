"""W1-D5 server-side malformed-answer safety contract.

These tests use local service fixtures and source-level ordering checks only.
They do not query the live corpus or a Production database.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys
import types

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from guild_quest_answer_service import (  # noqa: E402
    GuildQuestAnswerError,
    build_guild_quest_answer_context,
    judge_guild_quest_answer,
)
import guild_quest_answer_service as guild_service  # noqa: E402
from lord_trial_answer_service import (  # noqa: E402
    LordTrialAnswerError,
    build_lord_trial_attempt_context,
    judge_lord_trial_answer,
)
import lord_trial_answer_service as lord_service  # noqa: E402
from map_battle_runtime import JudgeOutcome, JudgeUnavailable, RequestRejected  # noqa: E402


QUEST_KEY = "whole_board::LV2"
EXAM = {"zone_key": "k26_30", "attempt_id": "w1-d5-attempt"}
QUESTION = {
    "id": 431,
    "content": "(;GM[1]FF[4]CA[UTF-8]SZ[19]PL[B]AB[dp]AW[pd](;B[dd]C[answer]))",
}
TRUNCATED_QUESTION = {
    "id": 431,
    "content": "(;GM[1]FF[4]CA[UTF-8]SZ[19]PL[B]AB[dp]AW[pd](;B[dd]",
}


def _install_app_import_stubs() -> None:
    """Keep this test's optional app import local and side-effect free."""

    if "katago_explain" not in sys.modules:
        module = types.ModuleType("katago_explain")
        module.KataGoExplainer = type("KataGoExplainer", (), {})
        sys.modules["katago_explain"] = module
    if "explain_overrides" not in sys.modules:
        module = types.ModuleType("explain_overrides")
        module.get_override = lambda *args, **kwargs: None
        sys.modules["explain_overrides"] = module
    if "grimoire_api" not in sys.modules:
        from flask import Blueprint

        module = types.ModuleType("grimoire_api")
        module.grimoire_bp = Blueprint("w1_d5_grimoire_stub", __name__)
        sys.modules["grimoire_api"] = module
    if "question_taxonomy" not in sys.modules:
        module = types.ModuleType("question_taxonomy")
        module.get_taxonomy = lambda *args, **kwargs: {}
        sys.modules["question_taxonomy"] = module
    if "monster_taxonomy" not in sys.modules:
        module = types.ModuleType("monster_taxonomy")
        module.get_monster_taxonomy = lambda *args, **kwargs: {}
        module.mark_encounters = lambda *args, **kwargs: None
        sys.modules["monster_taxonomy"] = module
    if "chapter_i18n" not in sys.modules:
        module = types.ModuleType("chapter_i18n")
        module.localize_topic = lambda *args, **kwargs: ""
        module.localize_level = lambda *args, **kwargs: ""
        sys.modules["chapter_i18n"] = module
    if "backend_i18n" not in sys.modules:
        module = types.ModuleType("backend_i18n")
        module.badge_en = lambda *args, **kwargs: ""
        module.skill_node_en = lambda *args, **kwargs: ""
        module.title_en = lambda *args, **kwargs: ""
        sys.modules["backend_i18n"] = module


@pytest.fixture(scope="module")
def app_module():
    _install_app_import_stubs()
    import app as app_module

    return app_module


def test_malformed_guild_answer_is_structured_and_fail_closed():
    with pytest.raises(GuildQuestAnswerError) as excinfo:
        judge_guild_quest_answer(
            {"moves": [{"action": "teleport", "x": 1, "y": 1}]},
            question=QUESTION,
            quest_key=QUEST_KEY,
        )

    error = excinfo.value
    assert error.code == "malformed_answer"
    assert error.failure_class == "CLIENT_ANSWER_INVALID"
    assert error.reason_code == "malformed_move_action"
    assert error.retryable is False


def test_malformed_lord_answer_is_structured_and_fail_closed():
    with pytest.raises(LordTrialAnswerError) as excinfo:
        judge_lord_trial_answer(
            {"moves": [{"action": "teleport", "x": 1, "y": 1}]},
            question=QUESTION,
            exam=EXAM,
        )

    error = excinfo.value
    assert error.code == "malformed_answer"
    assert error.failure_class == "CLIENT_ANSWER_INVALID"
    assert error.reason_code == "malformed_move_action"
    assert error.retryable is False


@pytest.mark.parametrize(
    ("judge", "kwargs", "error_type"),
    [
        (judge_guild_quest_answer, {"quest_key": QUEST_KEY}, GuildQuestAnswerError),
        (judge_lord_trial_answer, {"exam": EXAM}, LordTrialAnswerError),
    ],
)
def test_deterministic_parser_failure_keeps_content_provenance(
    judge, kwargs, error_type
):
    with pytest.raises(error_type) as excinfo:
        judge(
            {"moves": [{"x": 3, "y": 3}]},
            question=TRUNCATED_QUESTION,
            **kwargs,
        )

    error = excinfo.value
    assert error.code == "judge_unavailable"
    assert error.failure_class == "DETERMINISTIC_PARSER_FAILURE"
    assert error.reason_code == "question_content_parser_failure"
    assert error.retryable is False


def test_client_canonicalization_exception_is_not_content_failure(monkeypatch):
    def reject_request(*args, **kwargs):
        raise RequestRejected("client-shaped request rejected")

    monkeypatch.setattr(guild_service, "canonicalize_answer", reject_request)
    with pytest.raises(GuildQuestAnswerError) as excinfo:
        judge_guild_quest_answer(
            {"moves": [{"x": 3, "y": 3}]},
            question=QUESTION,
            quest_key=QUEST_KEY,
        )

    error = excinfo.value
    assert error.code == "malformed_answer"
    assert error.failure_class == "CLIENT_ANSWER_INVALID"
    assert error.reason_code == "invalid_map_battle_request"
    assert error.retryable is False


def test_judge_invalid_has_explicit_deterministic_provenance(monkeypatch):
    monkeypatch.setattr(
        guild_service,
        "judge_map_battle_answer_v1",
        lambda *args, **kwargs: JudgeOutcome(
            "INVALID", None, "map-battle-v1", "authoritative_content_invalid"
        ),
    )
    with pytest.raises(GuildQuestAnswerError) as excinfo:
        judge_guild_quest_answer(
            {"moves": [{"x": 3, "y": 3}]},
            question=QUESTION,
            quest_key=QUEST_KEY,
        )

    error = excinfo.value
    assert error.failure_class == "DETERMINISTIC_JUDGE_INPUT_INVALID"
    assert error.retryable is False


def test_special_move_judge_rejection_is_client_invalid_not_content_failure(monkeypatch):
    monkeypatch.setattr(
        guild_service,
        "judge_map_battle_answer_v1",
        lambda *args, **kwargs: JudgeOutcome(
            "INVALID", None, "map-battle-v1", "special_move_not_judged"
        ),
    )
    with pytest.raises(GuildQuestAnswerError) as excinfo:
        judge_guild_quest_answer(
            {"moves": [{"x": 3, "y": 3}]},
            question=QUESTION,
            quest_key=QUEST_KEY,
        )

    error = excinfo.value
    assert error.failure_class == "CLIENT_ANSWER_INVALID"
    assert error.reason_code == "special_move_not_judged"
    assert error.retryable is False


def test_unresolvable_question_is_question_failure_not_transient_retry():
    broken = {"id": 431, "content": "(;GM[1]SZ[19]AB[dp]AW[pd])"}

    with pytest.raises(GuildQuestAnswerError) as guild_exc:
        build_guild_quest_answer_context(broken, QUEST_KEY)
    assert guild_exc.value.code == "judge_unavailable"
    assert guild_exc.value.failure_class == "QUESTION_OR_CONTENT_INVALID"
    assert guild_exc.value.reason_code == "player_to_move_unavailable"
    assert guild_exc.value.retryable is False

    with pytest.raises(LordTrialAnswerError) as lord_exc:
        build_lord_trial_attempt_context(broken, EXAM)
    assert lord_exc.value.code == "judge_unavailable"
    assert lord_exc.value.failure_class == "QUESTION_OR_CONTENT_INVALID"
    assert lord_exc.value.reason_code == "player_to_move_unavailable"
    assert lord_exc.value.retryable is False


def test_judge_unavailable_remains_retryable_and_is_not_question_quarantine():
    def unavailable(*args, **kwargs):
        raise JudgeUnavailable("do not expose this message")

    original = guild_service.judge_map_battle_answer_v1
    guild_service.judge_map_battle_answer_v1 = unavailable
    try:
        with pytest.raises(GuildQuestAnswerError) as excinfo:
            judge_guild_quest_answer(
                {"moves": [{"x": 3, "y": 3}]},
                question=QUESTION,
                quest_key=QUEST_KEY,
            )
    finally:
        guild_service.judge_map_battle_answer_v1 = original

    error = excinfo.value
    assert error.code == "judge_unavailable"
    assert error.failure_class == "TRANSIENT_SERVER_FAILURE"
    assert error.reason_code == "judge_unavailable"
    assert error.retryable is True


def test_structured_failure_response_is_safe_and_revision_bound(app_module):
    error = GuildQuestAnswerError(
        "malformed_answer",
        failure_class="CONTENT_SIDE_CANONICALIZATION_FAILURE",
        reason_code="malformed_move_action",
    )
    question = dict(QUESTION)

    with app_module.app.app_context():
        response, status = app_module._answer_failure_response(
            error,
            qid=QUESTION["id"],
            question=question,
        )

    payload = response.get_json()
    assert status == 400
    assert payload == {
        "error": "malformed_answer",
        "code": "malformed_answer",
        "failure_class": "CONTENT_SIDE_CANONICALIZATION_FAILURE",
        "reason_code": "malformed_move_action",
        "retryable": False,
        "question_id": 431,
        "question_revision": hashlib.sha256(
            QUESTION["content"].encode("utf-8")
        ).hexdigest(),
        "session_question_fingerprint": app_module._session_question_fingerprint(question),
    }
    assert "teleport" not in response.get_data(as_text=True)
    assert "do not expose this message" not in response.get_data(as_text=True)


def test_missing_revision_gets_opaque_session_fingerprint_without_raw_content(app_module):
    broken = {"id": 431, "content": ""}
    error = GuildQuestAnswerError(
        "judge_unavailable",
        status=503,
        retryable=False,
        failure_class="QUESTION_OR_CONTENT_INVALID",
        reason_code="question_content_unavailable",
    )

    with app_module.app.app_context():
        response, status = app_module._answer_failure_response(
            error,
            qid=broken["id"],
            question=broken,
        )

    payload = response.get_json()
    assert status == 503
    assert payload["question_revision"] is None
    fingerprint = payload["session_question_fingerprint"]
    assert isinstance(fingerprint, str)
    assert len(fingerprint) == 64
    assert all(character in "0123456789abcdef" for character in fingerprint)
    assert "session_question_fingerprint" in response.get_data(as_text=True)
    assert '"content"' not in response.get_data(as_text=True)

    changed = {**broken, "content": "new-runtime-payload"}
    with app_module.app.app_context():
        changed_response, _ = app_module._answer_failure_response(
            error,
            qid=changed["id"],
            question=changed,
        )
    assert changed_response.get_json()["session_question_fingerprint"] != fingerprint


def test_review_operation_judges_before_the_first_durable_review_write():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    operation_start = source.index("def _srs_review_operation")
    operation_end = source.index("def _dispatch_to_srs_review_operation", operation_start)
    operation = source[operation_start:operation_end]

    judge_positions = [
        operation.index("judge_lord_trial_answer("),
        operation.index("judge_guild_quest_answer("),
    ]
    first_review_insert = operation.index("insert_review_log_with_identity(")
    assert all(position < first_review_insert for position in judge_positions)
    assert "return _answer_failure_response(exc, qid=qid, question=q_info)" in operation


def test_failed_answer_has_no_fake_progress_or_success_contract():
    index_source = (ROOT / "index.html").read_text(encoding="utf-8")
    srs_source = (ROOT / "srs.js").read_text(encoding="utf-8")
    review_position = index_source.index("data = await SRS.review")
    rejection_position = index_source.index("if(!data.ok)", review_position)
    commit_position = index_source.index("_e10AcceptanceTrace('REVIEW_COMMITTED'", review_position)

    assert review_position < rejection_position < commit_position
    rejection_region = index_source[review_position:rejection_position]
    assert "SRS.reportUnitProgress" not in rejection_region
    assert "if (data.ok) SRS.markSeen(currentQ.id)" in rejection_region
    srs_review = srs_source[srs_source.index("async function review"):srs_source.index("function dispatchReviewPresentation")]
    assert "_quarantineRejectedAnswer(qid, data" in srs_review
    assert "_quarantineRejectedAnswer(qid, error && error.payload" in srs_review
