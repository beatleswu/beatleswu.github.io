import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = REPO_ROOT / "docs" / "planning" / "teacher_review_queue_read_model_contract_baseline.md"
OVERRIDE_PATH = REPO_ROOT / "puzzle_variation_overrides.json"


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8").lower()


def test_teacher_review_queue_read_model_contract_doc_exists():
    assert DOC_PATH.exists()


def test_teacher_review_queue_read_model_core_markers():
    text = _doc_text()

    required_markers = [
        "planning",
        "contract",
        "baseline",
        "passive backend review queue",
        "active frontend answer-page admin triage",
        "canonical_puzzle_id",
        "review_queue_item_id",
        "teacher_facing_status",
        "review_reason",
        "domain_tags",
        "difficulty_band",
        "owner_decision_status",
        "risk_level",
        "allowed_low_risk_actions",
        "blocked_high_risk_actions",
        "visual_sgf_card_ref",
    ]

    for marker in required_markers:
        assert marker in text


def test_review_queue_identity_binding_is_documented():
    text = _doc_text()

    identity_markers = [
        "every future review queue item must point to `canonical_puzzle_id`",
        "source_locator",
        "fixture_reference",
        "must not be the primary identity",
        "does not replace `canonical_puzzle_id`",
    ]

    for marker in identity_markers:
        assert marker in text


def test_active_frontend_admin_triage_guardrails_are_documented():
    text = _doc_text()

    guardrail_markers = [
        "must not",
        "activate candidate-only answers",
        "promote disabled puzzles to ready",
        "activate production overrides",
        "modify sgf bytes",
        "change sgf engine judging semantics",
        "bypass high-risk guarded flow",
    ]

    for marker in guardrail_markers:
        assert marker in text


def test_review_queue_contract_keeps_production_overrides_empty():
    overrides = json.loads(OVERRIDE_PATH.read_text(encoding="utf-8"))
    assert overrides == {}


@pytest.mark.skip(reason="Pending C-level implementation: review queue read model is not implemented in this planning baseline.")
def test_future_review_queue_read_model_acceptance():
    """Future acceptance criteria:
    Passive backend review queue and active frontend answer-page admin triage
    both create/read review items strong-bound to canonical_puzzle_id while keeping
    high-risk actions behind guarded C-level flows.
    """
