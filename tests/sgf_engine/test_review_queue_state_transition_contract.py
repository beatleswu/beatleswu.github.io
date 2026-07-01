from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "planning" / "review_queue_state_transition_contract.md"


def _text() -> str:
    return DOC.read_text(encoding="utf-8").lower()


def test_review_queue_state_transition_contract_doc_exists() -> None:
    assert DOC.exists()


def test_state_model_markers_exist() -> None:
    text = _text()
    for marker in [
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
    ]:
        assert marker in text


def test_identity_binding_is_documented() -> None:
    text = _text()
    assert "every future review queue item must bind to `canonical_puzzle_id`" in text
    assert "`review_queue_item_id` identifies the workflow item only" in text
    assert "it does not replace `canonical_puzzle_id`" in text


def test_allowed_low_risk_transitions_are_documented() -> None:
    text = _text()
    for marker in [
        "`feedback_reported` -> `needs_review`",
        "`feedback_reported` -> `resolved_no_action`",
        "`visual_validation_needed` -> `needs_review`",
        "`needs_review` -> `owner_decision_pending`",
        "`needs_review` -> `resolved_no_action`",
    ]:
        assert marker in text


def test_guarded_high_risk_transitions_are_documented() -> None:
    text = _text()
    for marker in [
        "`owner_decision_pending` -> `resolved_owner_approved`",
        "`owner_decision_pending` -> `resolved_rejected`",
        "`blocked_high_risk_change` -> `owner_decision_pending`",
    ]:
        assert marker in text


def test_blocked_direct_transitions_and_candidate_only_guardrail_are_documented() -> None:
    text = _text()
    for marker in [
        "`candidate_only_disabled` -> `ready_readonly` = blocked direct transition",
        "`feedback_reported` -> `ready_readonly` = blocked direct transition",
        "`needs_review` -> `ready_readonly` = blocked direct transition",
        "`visual_validation_needed` -> `ready_readonly` = blocked direct transition",
        "a candidate-only disabled item must not be promoted directly to `ready_readonly`",
        "b[sd] / t16 remains candidate-only",
    ]:
        assert marker in text
