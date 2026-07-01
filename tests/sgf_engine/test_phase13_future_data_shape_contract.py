from dataclasses import dataclass
from typing import FrozenSet
from uuid import UUID, uuid4


ALLOWED_REVIEW_QUEUE_STATES: FrozenSet[str] = frozenset(
    {
        "needs_review",
        "feedback_reported",
        "visual_validation_needed",
        "candidate_only_disabled",
        "owner_decision_pending",
        "blocked_high_risk_change",
        "resolved_no_action",
        "resolved_owner_approved",
        "resolved_rejected",
        "ready_readonly",
    }
)

ALLOWED_LOW_RISK_TRANSITIONS: FrozenSet[tuple[str, str]] = frozenset(
    {
        ("feedback_reported", "needs_review"),
        ("feedback_reported", "resolved_no_action"),
        ("visual_validation_needed", "needs_review"),
        ("needs_review", "owner_decision_pending"),
        ("needs_review", "resolved_no_action"),
    }
)

ALLOWED_GUARDED_HIGH_RISK_TRANSITIONS: FrozenSet[tuple[str, str]] = frozenset(
    {
        ("owner_decision_pending", "resolved_owner_approved"),
        ("owner_decision_pending", "resolved_rejected"),
        ("blocked_high_risk_change", "owner_decision_pending"),
    }
)

BLOCKED_DIRECT_TRANSITIONS: FrozenSet[tuple[str, str]] = frozenset(
    {
        ("candidate_only_disabled", "ready_readonly"),
        ("feedback_reported", "ready_readonly"),
        ("needs_review", "ready_readonly"),
        ("visual_validation_needed", "ready_readonly"),
    }
)


@dataclass(frozen=True)
class FutureReviewQueueItemContract:
    """Test-only contract stub.

    This is not a production model.
    This is not a DB schema.
    This is not imported by runtime code.
    This is not a SQLAlchemy model.
    """

    canonical_puzzle_id: UUID
    status: str
    owner_decision_required: bool
    source: str


@dataclass(frozen=True)
class FutureOwnerDecisionTraceContract:
    """Test-only contract stub for future decision trace shape."""

    canonical_puzzle_id: UUID
    from_status: str
    to_status: str
    owner_approved: bool
    reason: str


def _is_low_risk_transition(from_status: str, to_status: str) -> bool:
    return (from_status, to_status) in ALLOWED_LOW_RISK_TRANSITIONS


def _is_guarded_high_risk_transition(from_status: str, to_status: str) -> bool:
    return (from_status, to_status) in ALLOWED_GUARDED_HIGH_RISK_TRANSITIONS


def _is_blocked_direct_transition(from_status: str, to_status: str) -> bool:
    return (from_status, to_status) in BLOCKED_DIRECT_TRANSITIONS


def test_future_data_shape_contract_is_test_local_only() -> None:
    assert FutureReviewQueueItemContract.__module__ == __name__
    assert FutureOwnerDecisionTraceContract.__module__ == __name__


def test_future_review_queue_item_uses_uuid_canonical_puzzle_id() -> None:
    item = FutureReviewQueueItemContract(
        canonical_puzzle_id=uuid4(),
        status="needs_review",
        owner_decision_required=False,
        source="passive_backend_review_queue",
    )

    assert isinstance(item.canonical_puzzle_id, UUID)
    assert item.canonical_puzzle_id.version == 4


def test_future_review_queue_status_must_be_explicit_allowed_state() -> None:
    item = FutureReviewQueueItemContract(
        canonical_puzzle_id=uuid4(),
        status="candidate_only_disabled",
        owner_decision_required=True,
        source="active_frontend_answer_page_admin_triage",
    )

    assert item.status in ALLOWED_REVIEW_QUEUE_STATES


def test_phase12_allowed_low_risk_transitions_are_preserved() -> None:
    assert _is_low_risk_transition("feedback_reported", "needs_review")
    assert _is_low_risk_transition("feedback_reported", "resolved_no_action")
    assert _is_low_risk_transition("visual_validation_needed", "needs_review")
    assert _is_low_risk_transition("needs_review", "owner_decision_pending")
    assert _is_low_risk_transition("needs_review", "resolved_no_action")


def test_phase12_guarded_high_risk_transitions_are_preserved() -> None:
    assert _is_guarded_high_risk_transition(
        "owner_decision_pending",
        "resolved_owner_approved",
    )
    assert _is_guarded_high_risk_transition(
        "owner_decision_pending",
        "resolved_rejected",
    )
    assert _is_guarded_high_risk_transition(
        "blocked_high_risk_change",
        "owner_decision_pending",
    )


def test_candidate_only_disabled_cannot_directly_become_ready_readonly() -> None:
    assert _is_blocked_direct_transition("candidate_only_disabled", "ready_readonly")
    assert not _is_low_risk_transition("candidate_only_disabled", "ready_readonly")
    assert not _is_guarded_high_risk_transition("candidate_only_disabled", "ready_readonly")


def test_unresolved_review_states_cannot_directly_become_ready_readonly() -> None:
    assert _is_blocked_direct_transition("feedback_reported", "ready_readonly")
    assert _is_blocked_direct_transition("needs_review", "ready_readonly")
    assert _is_blocked_direct_transition("visual_validation_needed", "ready_readonly")


def test_high_risk_decision_trace_requires_owner_approval_marker() -> None:
    trace = FutureOwnerDecisionTraceContract(
        canonical_puzzle_id=uuid4(),
        from_status="owner_decision_pending",
        to_status="resolved_owner_approved",
        owner_approved=True,
        reason="owner approved future guarded high-risk decision",
    )

    assert isinstance(trace.canonical_puzzle_id, UUID)
    assert trace.from_status == "owner_decision_pending"
    assert trace.to_status == "resolved_owner_approved"
    assert trace.owner_approved is True
    assert "owner approved" in trace.reason


def test_gf003_equivalent_candidate_must_remain_candidate_only_by_contract() -> None:
    item = FutureReviewQueueItemContract(
        canonical_puzzle_id=uuid4(),
        status="candidate_only_disabled",
        owner_decision_required=True,
        source="GF-003 / 431.sgf / B[sd] / T16",
    )

    assert item.status == "candidate_only_disabled"
    assert item.owner_decision_required is True
    assert _is_blocked_direct_transition(item.status, "ready_readonly")
    assert "B[sd] / T16" in item.source
