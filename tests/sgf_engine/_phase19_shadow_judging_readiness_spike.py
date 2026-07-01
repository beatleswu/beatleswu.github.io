"""Test-local shadow judging readiness helpers.

This module has no production runtime integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID, uuid4


SOURCE_JUDGEMENTS = frozenset({"accept", "reject", "unknown"})
SHADOW_JUDGEMENTS = frozenset(
    {
        "accept",
        "reject",
        "off_tree",
        "unsupported",
        "error",
        "candidate_only",
        "gf003_blocked",
    }
)

COMPARISON_CLASSIFICATIONS = frozenset(
    {
        "agreement_accept",
        "agreement_reject",
        "legacy_accepts_shadow_rejects",
        "legacy_rejects_shadow_accepts",
        "legacy_accepts_shadow_off_tree",
        "legacy_rejects_shadow_off_tree",
        "shadow_unsupported",
        "shadow_error",
        "legacy_unknown",
        "candidate_only_blocked",
        "gf003_safety_blocked",
    }
)

REVIEW_RECOMMENDED_CLASSIFICATIONS = frozenset(
    {
        "legacy_accepts_shadow_rejects",
        "legacy_rejects_shadow_accepts",
        "legacy_accepts_shadow_off_tree",
        "legacy_rejects_shadow_off_tree",
        "shadow_unsupported",
        "shadow_error",
        "legacy_unknown",
        "candidate_only_blocked",
        "gf003_safety_blocked",
    }
)

OWNER_DECISION_REQUIRED_CLASSIFICATIONS = frozenset(
    {
        "legacy_rejects_shadow_accepts",
        "candidate_only_blocked",
        "gf003_safety_blocked",
    }
)

GF003_CANONICAL_SGF_ANSWER = "B[sf]"
GF003_CANONICAL_BOARD_COORDINATE = "T14"
GF003_CANDIDATE_ONLY_SGF = "B[sd]"
GF003_CANDIDATE_ONLY_BOARD_COORDINATE = "T16"


@dataclass(frozen=True)
class JudgementResult:
    judgement: str
    reason: str = ""


@dataclass(frozen=True)
class ShadowJudgingInput:
    player_color: str
    player_move_sgf: str
    legacy_question_id: Optional[int] = None
    canonical_puzzle_id: Optional[str] = None
    player_move_board_coordinate: str = ""
    puzzle_id_hint: str = ""


@dataclass(frozen=True)
class ShadowComparisonDecision:
    classification: str
    review_recommended: bool
    owner_decision_required: bool
    candidate_only_detected: bool
    gf003_related: bool
    invalid_identity: bool
    legacy_unknown: bool
    user_facing_judgement_changed: bool = False


@dataclass(frozen=True)
class ShadowJudgingEvent:
    event_id: str
    legacy_question_id: Optional[int]
    canonical_puzzle_id: Optional[str]
    source_judgement: str
    shadow_judgement: str
    classification: str
    player_color: str
    player_move_sgf: str
    player_move_board_coordinate: str
    legacy_reason: str
    shadow_reason: str
    review_recommended: bool
    owner_decision_required: bool
    candidate_only_detected: bool
    gf003_related: bool
    invalid_identity: bool
    legacy_unknown: bool
    user_facing_judgement_changed: bool
    created_at: str


def _valid_uuid_v4(value: Optional[str]) -> bool:
    if value in {None, ""}:
        return True

    try:
        parsed = UUID(str(value), version=4)
    except (TypeError, ValueError, AttributeError):
        return False

    return str(parsed) == value and parsed.version == 4


def _valid_legacy_question_id(value: Optional[int]) -> bool:
    return value is None or (isinstance(value, int) and value > 0)


def _has_any_identity(input_data: ShadowJudgingInput) -> bool:
    return bool(input_data.canonical_puzzle_id) or input_data.legacy_question_id is not None


def _identity_is_valid(input_data: ShadowJudgingInput) -> bool:
    return (
        _has_any_identity(input_data)
        and _valid_uuid_v4(input_data.canonical_puzzle_id)
        and _valid_legacy_question_id(input_data.legacy_question_id)
    )


def is_gf003_related(input_data: ShadowJudgingInput) -> bool:
    return input_data.puzzle_id_hint == "GF-003"


def is_gf003_candidate_only_move(input_data: ShadowJudgingInput) -> bool:
    if not is_gf003_related(input_data):
        return False

    return (
        input_data.player_move_sgf == GF003_CANDIDATE_ONLY_SGF
        or input_data.player_move_board_coordinate == GF003_CANDIDATE_ONLY_BOARD_COORDINATE
    )


def _candidate_only_detected(
    shadow: JudgementResult,
    input_data: ShadowJudgingInput,
) -> bool:
    return shadow.judgement == "candidate_only" or is_gf003_candidate_only_move(input_data)


def _decision(
    classification: str,
    *,
    candidate_only_detected: bool = False,
    gf003_related: bool = False,
    invalid_identity: bool = False,
    legacy_unknown: bool = False,
) -> ShadowComparisonDecision:
    if classification == "gf003_safety_blocked":
        gf003_related = True

    return ShadowComparisonDecision(
        classification=classification,
        review_recommended=classification in REVIEW_RECOMMENDED_CLASSIFICATIONS,
        owner_decision_required=classification in OWNER_DECISION_REQUIRED_CLASSIFICATIONS,
        candidate_only_detected=candidate_only_detected,
        gf003_related=gf003_related,
        invalid_identity=invalid_identity,
        legacy_unknown=legacy_unknown,
        user_facing_judgement_changed=False,
    )


def classify_shadow_comparison(
    legacy: JudgementResult,
    shadow: JudgementResult,
    input_data: ShadowJudgingInput,
) -> ShadowComparisonDecision:
    gf003_related = is_gf003_related(input_data)
    candidate_only = _candidate_only_detected(shadow, input_data)

    if not _identity_is_valid(input_data):
        return _decision(
            "shadow_error",
            candidate_only_detected=candidate_only,
            gf003_related=gf003_related,
            invalid_identity=True,
        )

    if legacy.judgement not in SOURCE_JUDGEMENTS or legacy.judgement == "unknown":
        return _decision(
            "legacy_unknown",
            candidate_only_detected=candidate_only,
            gf003_related=gf003_related,
            legacy_unknown=True,
        )

    if shadow.judgement not in SHADOW_JUDGEMENTS:
        return _decision(
            "shadow_error",
            candidate_only_detected=candidate_only,
            gf003_related=gf003_related,
        )

    if gf003_related and candidate_only:
        classification = "gf003_safety_blocked"
    elif candidate_only:
        classification = "candidate_only_blocked"
    elif shadow.judgement == "gf003_blocked":
        classification = "gf003_safety_blocked"
    elif shadow.judgement == "unsupported":
        classification = "shadow_unsupported"
    elif shadow.judgement == "error":
        classification = "shadow_error"
    elif legacy.judgement == "accept" and shadow.judgement == "accept":
        classification = "agreement_accept"
    elif legacy.judgement == "reject" and shadow.judgement == "reject":
        classification = "agreement_reject"
    elif legacy.judgement == "accept" and shadow.judgement == "reject":
        classification = "legacy_accepts_shadow_rejects"
    elif legacy.judgement == "reject" and shadow.judgement == "accept":
        classification = "legacy_rejects_shadow_accepts"
    elif legacy.judgement == "accept" and shadow.judgement == "off_tree":
        classification = "legacy_accepts_shadow_off_tree"
    elif legacy.judgement == "reject" and shadow.judgement == "off_tree":
        classification = "legacy_rejects_shadow_off_tree"
    else:
        classification = "shadow_error"

    return _decision(
        classification,
        candidate_only_detected=candidate_only,
        gf003_related=gf003_related,
    )


def build_shadow_judging_event(
    legacy: JudgementResult,
    shadow: JudgementResult,
    input_data: ShadowJudgingInput,
    *,
    created_at: str,
    event_id: Optional[str] = None,
) -> ShadowJudgingEvent:
    decision = classify_shadow_comparison(legacy, shadow, input_data)

    return ShadowJudgingEvent(
        event_id=event_id or str(uuid4()),
        legacy_question_id=input_data.legacy_question_id,
        canonical_puzzle_id=input_data.canonical_puzzle_id or None,
        source_judgement=legacy.judgement,
        shadow_judgement=shadow.judgement,
        classification=decision.classification,
        player_color=input_data.player_color,
        player_move_sgf=input_data.player_move_sgf,
        player_move_board_coordinate=input_data.player_move_board_coordinate,
        legacy_reason=legacy.reason,
        shadow_reason=shadow.reason,
        review_recommended=decision.review_recommended,
        owner_decision_required=decision.owner_decision_required,
        candidate_only_detected=decision.candidate_only_detected,
        gf003_related=decision.gf003_related,
        invalid_identity=decision.invalid_identity,
        legacy_unknown=decision.legacy_unknown,
        user_facing_judgement_changed=decision.user_facing_judgement_changed,
        created_at=created_at,
    )
