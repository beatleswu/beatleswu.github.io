"""Test-local teacher admin review queue service helpers.

This module has no production runtime integration.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import FrozenSet, Optional
from uuid import UUID


REVIEW_STATUSES = frozenset(
    {
        "ready_readonly",
        "needs_review",
        "pending_owner_decision",
        "candidate_only_disabled",
        "feedback_reported",
        "visual_validation_needed",
        "archived",
        "closed",
    }
)


LOW_RISK_TEACHER_ACTIONS = frozenset(
    {
        "add_review_note",
        "add_teacher_tag",
        "set_needs_review",
        "set_visual_validation_needed",
        "escalate_to_owner_decision",
        "archive_without_truth_change",
        "close_without_truth_change",
        "mark_false_positive_without_truth_change",
        "link_feedback_report",
        "create_feedback_report",
    }
)


GUARDED_C_LEVEL_ACTIONS = frozenset(
    {
        "promote_to_ready",
        "activate_candidate_solution",
        "enable_GF003",
        "allow_B_sd_T16_active",
        "modify_SGF_bytes",
        "modify_READY_IDS",
        "modify_puzzle_variation_overrides_json",
        "add_runtime_override",
        "add_production_override",
        "change_judging_semantics",
        "create_production_DB_schema",
        "add_API_or_UI_runtime",
    }
)


TRUTH_CHANGING_ACTIONS = frozenset(
    {
        "promote_to_ready",
        "activate_candidate_solution",
        "enable_GF003",
        "allow_B_sd_T16_active",
        "modify_SGF_bytes",
        "modify_READY_IDS",
        "modify_puzzle_variation_overrides_json",
        "add_runtime_override",
        "add_production_override",
        "change_judging_semantics",
    }
)


ACTIVE_FRONTEND_TRIAGE_ALLOWED = frozenset(
    {
        "create_feedback_report",
        "add_review_note",
        "set_needs_review",
        "set_visual_validation_needed",
        "escalate_to_owner_decision",
        "archive_without_truth_change",
        "close_without_truth_change",
    }
)


BLOCKED_DIRECT_TRANSITIONS = frozenset(
    {
        ("candidate_only_disabled", "ready_readonly"),
        ("pending_owner_decision", "ready_readonly"),
        ("feedback_reported", "ready_readonly"),
    }
)


ACTION_TARGET_STATUS = {
    "set_needs_review": "needs_review",
    "set_visual_validation_needed": "visual_validation_needed",
    "escalate_to_owner_decision": "pending_owner_decision",
    "archive_without_truth_change": "archived",
    "close_without_truth_change": "closed",
    "mark_false_positive_without_truth_change": "closed",
    "create_feedback_report": "feedback_reported",
    "link_feedback_report": "feedback_reported",
}


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    reason: str
    requires_c_level: bool = False
    production_truth_change: bool = False


@dataclass(frozen=True)
class ReviewQueueItem:
    canonical_puzzle_id: str
    status: str
    notes: tuple[str, ...] = ()
    teacher_tags: FrozenSet[str] = frozenset()
    feedback_links: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuditEvent:
    canonical_puzzle_id: str
    action: str
    previous_status: str
    next_status: str
    reason: str
    entry_point: str
    production_truth_change: bool
    requires_c_level: bool


def validate_canonical_puzzle_id(canonical_puzzle_id: str) -> bool:
    try:
        value = UUID(canonical_puzzle_id, version=4)
    except (TypeError, ValueError, AttributeError):
        return False

    return str(value) == canonical_puzzle_id and value.version == 4


def evaluate_teacher_action(
    action: str,
    current_status: str,
    *,
    entry_point: str = "backend_review_queue",
) -> PermissionDecision:
    if current_status not in REVIEW_STATUSES:
        return PermissionDecision(False, "unknown review status")

    if entry_point == "active_frontend_triage" and action not in ACTIVE_FRONTEND_TRIAGE_ALLOWED:
        return PermissionDecision(
            False,
            "action is not allowed from active frontend triage",
            requires_c_level=action in GUARDED_C_LEVEL_ACTIONS,
            production_truth_change=action in TRUTH_CHANGING_ACTIONS,
        )

    if action in GUARDED_C_LEVEL_ACTIONS:
        return PermissionDecision(
            False,
            "future owner-authorized C-level guarded flow required",
            requires_c_level=True,
            production_truth_change=action in TRUTH_CHANGING_ACTIONS,
        )

    if action not in LOW_RISK_TEACHER_ACTIONS:
        return PermissionDecision(False, "unknown teacher action")

    if current_status == "ready_readonly" and action != "set_needs_review":
        return PermissionDecision(False, "ready_readonly is read-only from normal teacher UI")

    return PermissionDecision(True, "low-risk metadata action allowed")


def transition_review_status(
    current_status: str,
    next_status: str,
    *,
    action: str,
) -> PermissionDecision:
    if current_status not in REVIEW_STATUSES:
        return PermissionDecision(False, "unknown current status")

    if next_status not in REVIEW_STATUSES:
        return PermissionDecision(False, "unknown next status")

    if (current_status, next_status) in BLOCKED_DIRECT_TRANSITIONS:
        return PermissionDecision(
            False,
            "direct transition is blocked and requires future C-level guarded flow",
            requires_c_level=True,
            production_truth_change=True,
        )

    if next_status == "ready_readonly" and action != "no_truth_change":
        return PermissionDecision(
            False,
            "teacher action cannot promote to ready_readonly",
            requires_c_level=True,
            production_truth_change=True,
        )

    if current_status in {"archived", "closed"} and next_status == "ready_readonly":
        return PermissionDecision(
            False,
            "archived or closed item cannot be promoted by teacher action",
            requires_c_level=True,
            production_truth_change=True,
        )

    return PermissionDecision(True, "status transition allowed")


def apply_teacher_action(
    item: ReviewQueueItem,
    action: str,
    *,
    reason: str,
    entry_point: str = "backend_review_queue",
    note: Optional[str] = None,
    teacher_tag: Optional[str] = None,
    feedback_id: Optional[str] = None,
) -> tuple[ReviewQueueItem, AuditEvent]:
    if not validate_canonical_puzzle_id(item.canonical_puzzle_id):
        raise ValueError("canonical_puzzle_id must be an ingestion-generated stable UUID v4")

    action_decision = evaluate_teacher_action(
        action,
        item.status,
        entry_point=entry_point,
    )
    if not action_decision.allowed:
        raise PermissionError(action_decision.reason)

    next_status = ACTION_TARGET_STATUS.get(action, item.status)
    transition_decision = transition_review_status(
        item.status,
        next_status,
        action=action,
    )
    if not transition_decision.allowed:
        raise PermissionError(transition_decision.reason)

    notes = item.notes
    if note:
        notes = notes + (note,)

    teacher_tags = item.teacher_tags
    if teacher_tag:
        teacher_tags = frozenset(set(teacher_tags) | {teacher_tag})

    feedback_links = item.feedback_links
    if feedback_id:
        feedback_links = feedback_links + (feedback_id,)

    updated = replace(
        item,
        status=next_status,
        notes=notes,
        teacher_tags=teacher_tags,
        feedback_links=feedback_links,
    )

    event = AuditEvent(
        canonical_puzzle_id=item.canonical_puzzle_id,
        action=action,
        previous_status=item.status,
        next_status=next_status,
        reason=reason,
        entry_point=entry_point,
        production_truth_change=False,
        requires_c_level=False,
    )

    return updated, event
