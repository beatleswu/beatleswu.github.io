import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = (
    REPO_ROOT / "docs" / "planning" / "teacher_admin_mvp_implementation_map.md"
)
OVERRIDES_PATH = REPO_ROOT / "puzzle_variation_overrides.json"
MANIFEST_PATH = (
    REPO_ROOT / "tests" / "sgf_engine" / "data" / "gold_fixtures" / "fixtures.json"
)

FUTURE_REVIEW_FIELDS = {
    "review_queue_item",
    "teacher_review_status",
    "feedback_queue_item",
    "owner_decision_state",
    "teacher_decision_trace",
}


@pytest.fixture(scope="module")
def doc_text():
    return DOC_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def gf003(manifest):
    excluded_by_id = {
        record["gf_id"]: record for record in manifest["excluded_fixtures"]
    }
    return excluded_by_id["GF-003"]


def test_doc_exists_and_marks_docs_only_scope(doc_text):
    assert "Teacher Admin MVP Implementation Map" in doc_text
    assert "This is docs-only groundwork." in doc_text
    assert "This is not an implementation spec." in doc_text


def test_doc_records_absent_current_repo_implementation_surface(doc_text):
    assert "Flask or backend entrypoint: Absent" in doc_text
    assert "frontend or template entrypoint: Absent" in doc_text
    assert "WGo.js integration surface: Absent" in doc_text
    assert "teacher admin route: Absent" in doc_text
    assert "review queue route: Absent" in doc_text
    assert "DB, schema, or migration structure: Absent" in doc_text
    assert "Future C-level implementation must first define the app, API, and UI structure." in doc_text


def test_doc_lists_all_future_mvp_slices(doc_text):
    assert "1. Canonical puzzle identity contract" in doc_text
    assert "2. Teacher review queue data model" in doc_text
    assert "3. Teacher-facing status taxonomy" in doc_text
    assert "4. Visual SGF review card payload" in doc_text
    assert "5. WGo.js review UI integration" in doc_text
    assert "6. Feedback or issue-report ingestion" in doc_text
    assert "7. Teacher decision trace and audit log" in doc_text
    assert "8. Low-risk batch operations" in doc_text
    assert "9. High-risk confirmation flow" in doc_text
    assert "10. Permission and admin role model" in doc_text


def test_doc_lists_dependency_order_and_readiness_gates(doc_text):
    assert "1. Canonical puzzle identity contract" in doc_text
    assert "2. Review queue read model" in doc_text
    assert "3. Visual SGF review card payload" in doc_text
    assert "10. Permission model hardening" in doc_text
    assert "canonical puzzle identity contract" in doc_text
    assert "teacher or admin permission model" in doc_text
    assert "status transition rules" in doc_text
    assert "review queue state model" in doc_text
    assert "feedback issue reason list" in doc_text
    assert "WGo.js integration target" in doc_text


def test_doc_forbids_traceability_fields_as_canonical_identity(doc_text):
    assert "The following are not canonical puzzle identity:" in doc_text
    assert "- `source_path`" in doc_text
    assert "- `fixture_path`" in doc_text
    assert "- `gold_fixture_id`" in doc_text
    assert "traceability metadata" in doc_text


def test_doc_explicitly_marks_non_actions(doc_text):
    assert "This PR does not implement teacher admin." in doc_text
    assert "This PR does not add DB, API, backend, or frontend UI." in doc_text
    assert "This PR does not add fake app.py." in doc_text
    assert "This PR does not implement review queue." in doc_text
    assert "This PR does not implement feedback queue." in doc_text
    assert "This PR does not change runtime behavior." in doc_text


def test_current_manifest_does_not_define_teacher_admin_review_queue_fields(manifest):
    for collection_name in ("fixtures", "excluded_fixtures"):
        for record in manifest[collection_name]:
            for field in FUTURE_REVIEW_FIELDS:
                assert field not in record


def test_production_override_config_remains_empty():
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    assert overrides == {}


def test_gf003_remains_inactive_candidate_only(gf003):
    metadata = gf003["disabled_override_metadata"]

    assert gf003["gf_id"] == "GF-003"
    assert gf003["status"] == "CANDIDATE_REQUIRES_OVERRIDE"
    assert gf003["runtime_override_active"] is False
    assert gf003["ready_activation"] is False
    assert metadata["runtime_status"] == "disabled"
    assert metadata["apply_automatically"] is False
    assert metadata["runtime_override_active"] is False
    assert metadata["ready_activation"] is False


@pytest.mark.skip(reason="Pending C-level implementation: canonical puzzle identity contract")
def test_future_teacher_admin_review_items_bind_to_canonical_puzzle_identity():
    """Future review queue and active answer-page triage must bind to canonical puzzle identity, not paths or temporary IDs."""


@pytest.mark.skip(reason="Pending C-level implementation: active answer-page admin triage")
def test_future_admin_can_mark_issue_from_answer_page_without_runtime_activation():
    """Future admin answer-page triage can mark needs-review without activating READY or production overrides."""


@pytest.mark.skip(reason="Pending C-level implementation: review queue read model")
def test_future_review_queue_lists_feedback_and_owner_decision_items():
    """Future review queue should surface feedback-reported and owner-decision-pending items."""


@pytest.mark.skip(reason="Pending C-level implementation: guarded high-risk actions")
def test_future_high_risk_actions_require_confirmation_and_audit_trace():
    """Future READY promotion, production override activation, and SGF bytes changes require guarded C-level flows."""
