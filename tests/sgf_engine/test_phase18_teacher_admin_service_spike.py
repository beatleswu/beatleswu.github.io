from __future__ import annotations

import sys
import unicodedata
from pathlib import Path
from uuid import uuid4

import pytest

from tests.sgf_engine._phase18_teacher_admin_service_spike import (
    ACTIVE_FRONTEND_TRIAGE_ALLOWED,
    GUARDED_C_LEVEL_ACTIONS,
    LOW_RISK_TEACHER_ACTIONS,
    ReviewQueueItem,
    apply_teacher_action,
    evaluate_teacher_action,
    transition_review_status,
    validate_canonical_puzzle_id,
)


HELPER_PATH = Path("tests/sgf_engine/_phase18_teacher_admin_service_spike.py")
TEST_PATH = Path("tests/sgf_engine/test_phase18_teacher_admin_service_spike.py")


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


def _item(status: str = "needs_review") -> ReviewQueueItem:
    return ReviewQueueItem(canonical_puzzle_id=str(uuid4()), status=status)


def test_phase18_files_are_utf8_lf_only_without_hidden_controls():
    assert HELPER_PATH.is_file()
    assert TEST_PATH.is_file()
    _assert_utf8_lf_only_without_hidden_controls(HELPER_PATH)
    _assert_utf8_lf_only_without_hidden_controls(TEST_PATH)


def test_validate_canonical_puzzle_id_accepts_uuid_v4():
    assert validate_canonical_puzzle_id(str(uuid4())) is True


@pytest.mark.parametrize(
    "bad_id",
    [
        "docs/testing/example.sgf",
        "fixtures/GF-003",
        "GF-003",
        "0713176F21C7A23133014A5956D935311B9AA8AA5A483A87CCF8100FEA5C7D29",
        "1",
        "",
        "not-a-uuid",
    ],
)
def test_validate_canonical_puzzle_id_rejects_paths_hashes_and_bad_ids(bad_id):
    assert validate_canonical_puzzle_id(bad_id) is False


@pytest.mark.parametrize(
    "action",
    sorted(LOW_RISK_TEACHER_ACTIONS - {"archive_without_truth_change", "close_without_truth_change"}),
)
def test_low_risk_teacher_actions_are_allowed_for_review_metadata(action):
    decision = evaluate_teacher_action(action, "needs_review")
    assert decision.allowed is True
    assert decision.requires_c_level is False
    assert decision.production_truth_change is False


@pytest.mark.parametrize("action", sorted(GUARDED_C_LEVEL_ACTIONS))
def test_guarded_c_level_actions_are_denied_and_marked_c_level(action):
    decision = evaluate_teacher_action(action, "needs_review")
    assert decision.allowed is False
    assert decision.requires_c_level is True


def test_candidate_only_disabled_cannot_transition_directly_to_ready():
    decision = transition_review_status(
        "candidate_only_disabled",
        "ready_readonly",
        action="promote_to_ready",
    )
    assert decision.allowed is False
    assert decision.requires_c_level is True
    assert decision.production_truth_change is True


def test_pending_owner_decision_cannot_transition_directly_to_ready():
    decision = transition_review_status(
        "pending_owner_decision",
        "ready_readonly",
        action="promote_to_ready",
    )
    assert decision.allowed is False
    assert decision.requires_c_level is True
    assert decision.production_truth_change is True


def test_feedback_reported_cannot_transition_directly_to_ready():
    decision = transition_review_status(
        "feedback_reported",
        "ready_readonly",
        action="promote_to_ready",
    )
    assert decision.allowed is False
    assert decision.requires_c_level is True
    assert decision.production_truth_change is True


def test_apply_teacher_action_adds_note_without_truth_change():
    updated, event = apply_teacher_action(
        _item("needs_review"),
        "add_review_note",
        reason="teacher observed board context issue",
        note="needs board context review",
    )

    assert updated.status == "needs_review"
    assert updated.notes == ("needs board context review",)
    assert event.previous_status == "needs_review"
    assert event.next_status == "needs_review"
    assert event.production_truth_change is False
    assert event.requires_c_level is False


def test_apply_teacher_action_adds_tag_without_truth_change():
    updated, event = apply_teacher_action(
        _item("needs_review"),
        "add_teacher_tag",
        reason="categorize issue",
        teacher_tag="visual-check",
    )

    assert updated.status == "needs_review"
    assert updated.teacher_tags == frozenset({"visual-check"})
    assert event.production_truth_change is False


def test_apply_teacher_action_links_feedback_and_updates_status():
    updated, event = apply_teacher_action(
        _item("needs_review"),
        "link_feedback_report",
        reason="user reported issue",
        feedback_id="feedback-001",
    )

    assert updated.status == "feedback_reported"
    assert updated.feedback_links == ("feedback-001",)
    assert event.previous_status == "needs_review"
    assert event.next_status == "feedback_reported"
    assert event.production_truth_change is False


@pytest.mark.parametrize("action", sorted(ACTIVE_FRONTEND_TRIAGE_ALLOWED))
def test_active_frontend_triage_allows_metadata_actions(action):
    item = _item("needs_review")
    kwargs = {}
    if action == "add_review_note":
        kwargs["note"] = "front page review note"
    if action in {"link_feedback_report", "create_feedback_report"}:
        kwargs["feedback_id"] = "feedback-frontend-001"

    updated, event = apply_teacher_action(
        item,
        action,
        reason="active frontend triage",
        entry_point="active_frontend_triage",
        **kwargs,
    )

    assert updated.canonical_puzzle_id == item.canonical_puzzle_id
    assert event.entry_point == "active_frontend_triage"
    assert event.production_truth_change is False


@pytest.mark.parametrize("action", sorted(GUARDED_C_LEVEL_ACTIONS))
def test_active_frontend_triage_forbids_truth_changing_actions(action):
    decision = evaluate_teacher_action(
        action,
        "needs_review",
        entry_point="active_frontend_triage",
    )
    assert decision.allowed is False


def test_ready_readonly_is_readonly_except_marking_needs_review():
    note_decision = evaluate_teacher_action("add_review_note", "ready_readonly")
    review_decision = evaluate_teacher_action("set_needs_review", "ready_readonly")

    assert note_decision.allowed is False
    assert review_decision.allowed is True


@pytest.mark.parametrize("status", ["archived", "closed"])
def test_archived_and_closed_preserve_trace_and_do_not_promote_to_ready(status):
    decision = transition_review_status(
        status,
        "ready_readonly",
        action="promote_to_ready",
    )
    assert decision.allowed is False
    assert decision.requires_c_level is True
    assert decision.production_truth_change is True


def test_phase18_remains_test_local_without_dependencies_or_db():
    assert "sqlalchemy" not in sys.modules
    assert "alembic" not in sys.modules
    assert HELPER_PATH.parts[:2] == ("tests", "sgf_engine")
    assert TEST_PATH.parts[:2] == ("tests", "sgf_engine")
