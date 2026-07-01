from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = (
    REPO_ROOT / "docs" / "planning" / "teacher_admin_mvp_readiness_baseline.md"
)


@pytest.fixture(scope="module")
def doc_text():
    return DOC_PATH.read_text(encoding="utf-8")


def test_mvp_doc_exists_and_marks_docs_only_baseline(doc_text):
    assert "Teacher Admin MVP Readiness Baseline" in doc_text
    assert "This is not an implementation spec." in doc_text
    assert "This document is docs-only groundwork." in doc_text


def test_mvp_doc_explicitly_defers_runtime_and_schema_work(doc_text):
    assert "This PR does not implement teacher admin MVP." in doc_text
    assert "This PR does not add DB, API, backend, or frontend UI." in doc_text
    assert "This PR does not add formal schemas." in doc_text
    assert "This PR does not define or implement final canonical puzzle identity." in doc_text
    assert "This PR does not implement feedback queue." in doc_text
    assert "This PR does not change runtime behavior." in doc_text
    assert "This PR does not activate overrides." in doc_text
    assert "This PR does not promote READY." in doc_text


def test_mvp_doc_lists_visibility_and_risk_boundaries(doc_text):
    assert "The future MVP must not hide:" in doc_text
    assert "- candidate-only" in doc_text
    assert "- disabled" in doc_text
    assert "- excluded" in doc_text
    assert "- needs review" in doc_text
    assert "- owner decision pending" in doc_text
    assert "- canonical answer" in doc_text
    assert "- proposed candidate answer" in doc_text
    assert "### Low-Risk Future Operations" in doc_text
    assert "### Medium-Risk Future Operations" in doc_text
    assert "### High-Risk Or C-Level Future Operations" in doc_text
    assert "- READY promotion" in doc_text
    assert "- production override activation" in doc_text


def test_mvp_doc_lists_readiness_gates(doc_text):
    assert "teacher admin UX flow" in doc_text
    assert "permission model" in doc_text
    assert "status transition rules" in doc_text
    assert "review queue behavior" in doc_text
    assert "domain taxonomy initial tag list" in doc_text
    assert "difficulty-level final grouping" in doc_text
    assert "feedback issue reason list" in doc_text
    assert "WGo.js review UI integration details" in doc_text
    assert "API payload shape" in doc_text
    assert "DB schema" in doc_text
    assert "canonical puzzle identity contract" in doc_text


def test_mvp_doc_explains_skip_skeleton_purpose(doc_text):
    assert "pytest.mark.skip" in doc_text
    assert "future C-level" in doc_text
    assert "do not create shadow APIs, shadow workflows, or shadow schemas" in doc_text


@pytest.mark.skip(reason="Pending C-level implementation: teacher admin MVP API")
def test_future_teacher_admin_mvp_payload_exposes_review_queue_without_runtime_activation():
    """Future review queue payload should expose review metadata without activating READY or production overrides."""


@pytest.mark.skip(reason="Pending C-level implementation: WGo.js visual review UI")
def test_future_visual_sgf_review_card_renders_canonical_and_candidate_answers():
    """Future visual SGF review UI should show canonical and candidate answers without making candidates active."""


@pytest.mark.skip(reason="Pending C-level implementation: teacher-admin risk confirmation flow")
def test_future_high_risk_teacher_admin_operations_require_explicit_confirmation():
    """Future high-risk actions should require explicit confirmation before READY or override activation."""
