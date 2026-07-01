from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = REPO_ROOT / "docs" / "planning" / "canonical_puzzle_identity_contract_baseline.md"


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8").lower()


def test_canonical_puzzle_identity_contract_doc_exists():
    assert DOC_PATH.exists()


def test_canonical_puzzle_identity_contract_core_markers():
    text = _doc_text()

    required_markers = [
        "planning",
        "contract",
        "baseline",
        "canonical_puzzle_id",
        "content_revision_id",
        "source_locator",
        "fixture_reference",
        "review_queue_item_id",
        "feedback_report_id",
        "owner_decision_id",
    ]

    for marker in required_markers:
        assert marker in text


def test_canonical_puzzle_identity_contract_rejects_unstable_identity_sources():
    text = _doc_text()

    unstable_identity_markers = [
        "source_path",
        "fixture_path",
        "gold_fixture_id",
        "frontend temporary id",
        "runtime state",
        "answer attempt id",
    ]

    for marker in unstable_identity_markers:
        assert marker in text

    rejection_markers = [
        "must not be treated as canonical puzzle identity",
        "not a production puzzle identity",
        "not the production db identity",
        "not stable across sessions",
        "not a long-term review anchor",
    ]

    for marker in rejection_markers:
        assert marker in text


def test_canonical_puzzle_identity_contract_non_goals_are_documented():
    text = _doc_text()

    non_goal_markers = [
        "does not",
        "db schema",
        "api routes",
        "frontend ui",
        "sgf bytes",
        "ready_ids",
        "puzzle_variation_overrides.json",
        "sgf engine production code",
        "gf-003",
        "b[sd] / t16",
    ]

    for marker in non_goal_markers:
        assert marker in text


@pytest.mark.skip(reason="Pending C-level implementation: final canonical puzzle identity owner decision is not implemented in this planning baseline.")
def test_future_canonical_puzzle_identity_acceptance():
    """Future acceptance criteria:
    Review queue items, feedback reports, visual SGF cards, and owner decision traces
    can all point to the same stable canonical_puzzle_id without using source_path,
    fixture_path, gold_fixture_id, frontend temporary ID, or runtime state as identity.
    """
