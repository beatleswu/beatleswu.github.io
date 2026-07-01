from __future__ import annotations

import sys
import unicodedata
from pathlib import Path
from uuid import uuid4

import pytest

from tests.sgf_engine._phase19_shadow_judging_readiness_spike import (
    GF003_CANDIDATE_ONLY_BOARD_COORDINATE,
    GF003_CANDIDATE_ONLY_SGF,
    GF003_CANONICAL_BOARD_COORDINATE,
    GF003_CANONICAL_SGF_ANSWER,
    JudgementResult,
    ShadowJudgingInput,
    build_shadow_judging_event,
    classify_shadow_comparison,
)


DOC_PATH = Path("docs/planning/phase19_sgf_shadow_judging_readiness_spike.md")
HELPER_PATH = Path("tests/sgf_engine/_phase19_shadow_judging_readiness_spike.py")
TEST_PATH = Path("tests/sgf_engine/test_phase19_shadow_judging_readiness_spike.py")


EXPLICIT_BIDI_CONTROLS = {
    "\u061c",
    "\u200e",
    "\u200f",
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
    "\u2066",
    "\u2067",
    "\u2068",
    "\u2069",
}


def _assert_utf8_lf_only_without_hidden_controls(path: Path) -> None:
    data = path.read_bytes()
    assert data, "File should not be empty"
    assert not data.startswith(b"\xef\xbb\xbf"), "File must not contain UTF-8 BOM"
    assert b"\r" not in data, "File must use LF-only line endings"

    text = data.decode("utf-8")

    for index, char in enumerate(text):
        category = unicodedata.category(char)
        assert char not in EXPLICIT_BIDI_CONTROLS, (
            f"Hidden/bidi Unicode control found at index {index}: U+{ord(char):04X}"
        )
        assert not (
            category.startswith("C") and char not in {"\n", "\t"}
        ), f"Unexpected control character at index {index}: U+{ord(char):04X} {category}"


def _input(
    *,
    move_sgf: str = "B[dd]",
    board_coordinate: str = "D16",
    puzzle_id_hint: str = "",
    legacy_question_id: int | None = 29830,
    canonical_puzzle_id: str | None = None,
) -> ShadowJudgingInput:
    return ShadowJudgingInput(
        legacy_question_id=legacy_question_id,
        canonical_puzzle_id=canonical_puzzle_id,
        player_color="B",
        player_move_sgf=move_sgf,
        player_move_board_coordinate=board_coordinate,
        puzzle_id_hint=puzzle_id_hint,
    )


def _decision(
    legacy: str,
    shadow: str,
    input_data: ShadowJudgingInput | None = None,
):
    return classify_shadow_comparison(
        JudgementResult(legacy, reason=f"legacy {legacy}"),
        JudgementResult(shadow, reason=f"shadow {shadow}"),
        input_data or _input(),
    )


def test_phase19_shadow_files_are_utf8_lf_only_without_hidden_controls():
    assert DOC_PATH.is_file()
    assert HELPER_PATH.is_file()
    assert TEST_PATH.is_file()
    _assert_utf8_lf_only_without_hidden_controls(DOC_PATH)
    _assert_utf8_lf_only_without_hidden_controls(HELPER_PATH)
    _assert_utf8_lf_only_without_hidden_controls(TEST_PATH)


def test_agreement_accept_does_not_recommend_review():
    decision = _decision("accept", "accept")

    assert decision.classification == "agreement_accept"
    assert decision.review_recommended is False
    assert decision.owner_decision_required is False
    assert decision.user_facing_judgement_changed is False


def test_agreement_reject_does_not_recommend_review():
    decision = _decision("reject", "reject")

    assert decision.classification == "agreement_reject"
    assert decision.review_recommended is False
    assert decision.owner_decision_required is False


def test_legacy_accepts_shadow_rejects_recommends_review():
    decision = _decision("accept", "reject")

    assert decision.classification == "legacy_accepts_shadow_rejects"
    assert decision.review_recommended is True
    assert decision.owner_decision_required is False


def test_legacy_rejects_shadow_accepts_recommends_review_and_owner_decision():
    decision = _decision("reject", "accept")

    assert decision.classification == "legacy_rejects_shadow_accepts"
    assert decision.review_recommended is True
    assert decision.owner_decision_required is True


def test_legacy_accepts_shadow_off_tree_recommends_review():
    decision = _decision("accept", "off_tree")

    assert decision.classification == "legacy_accepts_shadow_off_tree"
    assert decision.review_recommended is True


def test_legacy_rejects_shadow_off_tree_recommends_review():
    decision = _decision("reject", "off_tree")

    assert decision.classification == "legacy_rejects_shadow_off_tree"
    assert decision.review_recommended is True


def test_shadow_unsupported_recommends_review():
    decision = _decision("accept", "unsupported")

    assert decision.classification == "shadow_unsupported"
    assert decision.review_recommended is True


def test_shadow_error_recommends_review():
    decision = _decision("reject", "error")

    assert decision.classification == "shadow_error"
    assert decision.review_recommended is True


def test_legacy_unknown_is_distinct_from_shadow_unsupported():
    decision = _decision("unknown", "accept")

    assert decision.classification == "legacy_unknown"
    assert decision.legacy_unknown is True
    assert decision.review_recommended is True


def test_unknown_legacy_judgement_becomes_legacy_unknown_without_throwing():
    decision = _decision("maybe", "accept")

    assert decision.classification == "legacy_unknown"
    assert decision.legacy_unknown is True


def test_unknown_shadow_judgement_becomes_shadow_error_without_throwing():
    decision = _decision("accept", "maybe")

    assert decision.classification == "shadow_error"
    assert decision.review_recommended is True


def test_invalid_canonical_puzzle_id_becomes_shadow_error_without_throwing():
    decision = _decision(
        "accept",
        "accept",
        _input(canonical_puzzle_id="GF-003", legacy_question_id=29830),
    )

    assert decision.classification == "shadow_error"
    assert decision.invalid_identity is True
    assert decision.review_recommended is True


def test_missing_all_identity_becomes_shadow_error_without_throwing():
    decision = _decision(
        "accept",
        "accept",
        _input(canonical_puzzle_id=None, legacy_question_id=None),
    )

    assert decision.classification == "shadow_error"
    assert decision.invalid_identity is True


def test_invalid_legacy_question_id_becomes_shadow_error_without_throwing():
    decision = _decision(
        "accept",
        "accept",
        _input(legacy_question_id=0, canonical_puzzle_id=str(uuid4())),
    )

    assert decision.classification == "shadow_error"
    assert decision.invalid_identity is True


def test_legacy_question_id_allows_event_without_canonical_puzzle_id():
    event = build_shadow_judging_event(
        JudgementResult("accept", reason="legacy accepted"),
        JudgementResult("accept", reason="shadow accepted"),
        _input(legacy_question_id=29830, canonical_puzzle_id=None),
        created_at="2026-01-01T00:00:00Z",
        event_id="event-001",
    )

    assert event.legacy_question_id == 29830
    assert event.canonical_puzzle_id is None
    assert event.classification == "agreement_accept"
    assert event.user_facing_judgement_changed is False


def test_candidate_only_shadow_result_is_blocked_and_owner_decision_required():
    decision = _decision(
        "reject",
        "candidate_only",
        _input(move_sgf="B[aa]", board_coordinate="A19"),
    )

    assert decision.classification == "candidate_only_blocked"
    assert decision.review_recommended is True
    assert decision.owner_decision_required is True
    assert decision.candidate_only_detected is True
    assert decision.gf003_related is False


def test_b_sd_t16_on_non_gf003_puzzle_is_not_candidate_only_blocked():
    decision = _decision(
        "accept",
        "reject",
        _input(
            move_sgf=GF003_CANDIDATE_ONLY_SGF,
            board_coordinate=GF003_CANDIDATE_ONLY_BOARD_COORDINATE,
            puzzle_id_hint="",
        ),
    )

    assert decision.classification == "legacy_accepts_shadow_rejects"
    assert decision.candidate_only_detected is False
    assert decision.gf003_related is False


def test_shadow_gf003_blocked_result_is_safety_blocked_and_gf003_related():
    decision = _decision(
        "reject",
        "gf003_blocked",
        _input(
            move_sgf="B[aa]",
            board_coordinate="A19",
            puzzle_id_hint="",
        ),
    )

    assert decision.classification == "gf003_safety_blocked"
    assert decision.review_recommended is True
    assert decision.owner_decision_required is True
    assert decision.gf003_related is True
    assert decision.candidate_only_detected is False


def test_gf003_candidate_only_t16_is_safety_blocked():
    decision = _decision(
        "reject",
        "reject",
        _input(
            move_sgf=GF003_CANDIDATE_ONLY_SGF,
            board_coordinate=GF003_CANDIDATE_ONLY_BOARD_COORDINATE,
            puzzle_id_hint="GF-003",
        ),
    )

    assert decision.classification == "gf003_safety_blocked"
    assert decision.review_recommended is True
    assert decision.owner_decision_required is True
    assert decision.gf003_related is True
    assert decision.candidate_only_detected is True


def test_gf003_canonical_t14_is_related_but_not_candidate_only():
    decision = _decision(
        "accept",
        "accept",
        _input(
            move_sgf=GF003_CANONICAL_SGF_ANSWER,
            board_coordinate=GF003_CANONICAL_BOARD_COORDINATE,
            puzzle_id_hint="GF-003",
        ),
    )

    assert decision.classification == "agreement_accept"
    assert decision.gf003_related is True
    assert decision.candidate_only_detected is False


def test_gf003_safety_blocked_always_sets_gf003_related_true():
    decision = _decision(
        "reject",
        "gf003_blocked",
        _input(puzzle_id_hint=""),
    )

    assert decision.classification == "gf003_safety_blocked"
    assert decision.gf003_related is True


def test_shadow_event_preserves_legacy_user_facing_judgement():
    event = build_shadow_judging_event(
        JudgementResult("accept", reason="legacy accepted"),
        JudgementResult("reject", reason="shadow rejected"),
        _input(),
        created_at="2026-01-01T00:00:00Z",
        event_id="event-001",
    )

    assert event.event_id == "event-001"
    assert event.source_judgement == "accept"
    assert event.shadow_judgement == "reject"
    assert event.classification == "legacy_accepts_shadow_rejects"
    assert event.user_facing_judgement_changed is False


def test_shadow_event_preserves_legacy_question_id_canonical_puzzle_id_and_move_context():
    canonical_id = str(uuid4())
    input_data = _input(
        move_sgf="W[qp]",
        board_coordinate="Q4",
        legacy_question_id=29830,
        canonical_puzzle_id=canonical_id,
    )
    event = build_shadow_judging_event(
        JudgementResult("reject", reason="legacy rejected"),
        JudgementResult("accept", reason="shadow accepted"),
        input_data,
        created_at="2026-01-01T00:00:00Z",
    )

    assert event.legacy_question_id == 29830
    assert event.canonical_puzzle_id == canonical_id
    assert event.player_move_sgf == "W[qp]"
    assert event.player_move_board_coordinate == "Q4"
    assert event.review_recommended is True
    assert event.owner_decision_required is True


def test_build_shadow_event_is_total_for_invalid_identity():
    event = build_shadow_judging_event(
        JudgementResult("accept", reason="legacy accepted"),
        JudgementResult("accept", reason="shadow accepted"),
        _input(legacy_question_id=None, canonical_puzzle_id=None),
        created_at="2026-01-01T00:00:00Z",
        event_id="event-invalid-identity",
    )

    assert event.classification == "shadow_error"
    assert event.invalid_identity is True
    assert event.event_id == "event-invalid-identity"


def test_phase19_shadow_readiness_remains_test_local_without_dependencies_or_db():
    assert "sqlalchemy" not in sys.modules
    assert "alembic" not in sys.modules
    assert HELPER_PATH.parts[:2] == ("tests", "sgf_engine")
    assert TEST_PATH.parts[:2] == ("tests", "sgf_engine")
