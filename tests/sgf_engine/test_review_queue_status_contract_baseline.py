from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "planning" / "review_queue_status_contract_baseline.md"


def _text() -> str:
    return DOC.read_text(encoding="utf-8").lower()


def test_review_queue_status_contract_doc_exists() -> None:
    assert DOC.exists()


def test_status_model_markers_exist() -> None:
    text = _text()
    for marker in [
        "needs_review",
        "owner_decision_pending",
        "feedback_reported",
        "visual_validation_needed",
        "candidate_only_disabled",
        "ready_readonly",
        "blocked_high_risk_change",
        "resolved_no_action",
        "resolved_owner_approved",
    ]:
        assert marker in text


def test_identity_binding_is_documented() -> None:
    text = _text()
    assert "every future review queue item must bind to `canonical_puzzle_id`" in text
    assert "`review_queue_item_id` identifies the workflow item only" in text
    assert "it does not replace `canonical_puzzle_id`" in text


def test_guardrails_and_high_risk_flows_are_documented() -> None:
    text = _text()
    for marker in [
        "activate production overrides",
        "promote ready",
        "modify sgf bytes",
        "change sgf engine judging semantics",
        "migrate canonical identity",
        "ready promotion",
        "production override activation",
        "canonical identity migration",
    ]:
        assert marker in text


def test_non_goals_are_documented() -> None:
    text = _text()
    for marker in [
        "db schema",
        "db migration",
        "api routes",
        "frontend ui",
        "queue storage",
        "runtime status mutation",
    ]:
        assert marker in text
