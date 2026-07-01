import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = (
    REPO_ROOT
    / "docs"
    / "planning"
    / "teacher_admin_active_review_entrypoints_baseline.md"
)
OVERRIDES_PATH = REPO_ROOT / "puzzle_variation_overrides.json"
MANIFEST_PATH = (
    REPO_ROOT / "tests" / "sgf_engine" / "data" / "gold_fixtures" / "fixtures.json"
)

FUTURE_ACTIVE_REVIEW_FIELDS = {
    "active_review_entrypoint",
    "answer_page_admin_triage",
    "teacher_review_note",
    "candidate_issue",
    "owner_decision_queue_item",
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


def test_doc_exists_and_records_two_review_entrypoints(doc_text):
    assert "Teacher Admin Active Review Entry Points Baseline" in doc_text
    assert "### Passive backend review queue" in doc_text
    assert "### Active frontend answer-page admin triage" in doc_text
    assert "- issue enters a passive backend review queue" in doc_text
    assert "- admin or teacher account is on the frontend answer page" in doc_text


def test_doc_records_active_admin_actions_backlog(doc_text):
    assert "- mark needs review" in doc_text
    assert "- add teacher review note" in doc_text
    assert "- mark false alarm" in doc_text
    assert "- mark candidate issue" in doc_text
    assert "- propose canonical answer correction" in doc_text
    assert "- propose candidate answer" in doc_text
    assert "- view current production override status" in doc_text


def test_doc_requires_safety_boundaries_and_wgo_continuity(doc_text):
    assert "candidate-only actions may be active" in doc_text
    assert "READY promotion requires a future C-level guarded flow" in doc_text
    assert "production override activation requires a future C-level guarded flow" in doc_text
    assert "SGF bytes changes require a future C-level guarded flow" in doc_text
    assert "Future implementation should likely reuse the existing WGo.js basis." in doc_text
    assert "This PR does not implement WGo.js UI." in doc_text


def test_doc_requires_canonical_identity_and_rejects_path_fields(doc_text):
    assert "Any future active review action or passive review queue item must bind strongly to a" in doc_text
    assert "The formal canonical puzzle identity definition remains a future C-level identity and" in doc_text
    assert "- `source_path`" in doc_text
    assert "- `fixture_path`" in doc_text
    assert "- `gold_fixture_id`" in doc_text
    assert "traceability metadata" in doc_text


def test_doc_explicitly_marks_no_ui_api_db_or_runtime_change(doc_text):
    assert "This PR does not implement frontend answer-page admin triage." in doc_text
    assert "This PR does not add UI buttons." in doc_text
    assert "This PR does not add API routes." in doc_text
    assert "This PR does not add DB tables." in doc_text
    assert "This PR does not add fake app.py." in doc_text
    assert "This PR does not change runtime behavior." in doc_text


def test_current_manifest_does_not_define_active_review_entrypoint_fields(manifest, gf003):
    for collection_name in ("fixtures", "excluded_fixtures"):
        for record in manifest[collection_name]:
            for field in FUTURE_ACTIVE_REVIEW_FIELDS:
                assert field not in record

    for field in FUTURE_ACTIVE_REVIEW_FIELDS:
        assert field not in gf003["disabled_override_metadata"]
        assert field not in gf003["proposed_override"]


def test_production_override_config_remains_empty():
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    assert overrides == {}


def test_gf003_remains_disabled_candidate_only_and_not_ready(gf003):
    metadata = gf003["disabled_override_metadata"]

    assert gf003["gf_id"] == "GF-003"
    assert gf003["status"] == "CANDIDATE_REQUIRES_OVERRIDE"
    assert gf003["runtime_override_active"] is False
    assert gf003["ready_activation"] is False
    assert gf003["ready_for_next_test_commit"] is False
    assert metadata["runtime_status"] == "disabled"
    assert metadata["apply_automatically"] is False
    assert metadata["runtime_override_active"] is False
    assert metadata["ready_activation"] is False


@pytest.mark.skip(reason="Pending C-level implementation: canonical puzzle identity for active review")
def test_future_active_review_items_bind_to_canonical_puzzle_identity():
    """Future active review and feedback entry points must bind to canonical puzzle identity, not paths or temporary IDs."""


@pytest.mark.skip(reason="Pending C-level implementation: answer-page admin triage")
def test_future_answer_page_admin_can_mark_needs_review_without_runtime_activation():
    """Future answer-page admin triage can mark needs-review without activating READY or production overrides."""


@pytest.mark.skip(reason="Pending C-level implementation: passive backend review queue")
def test_future_review_queue_surfaces_feedback_and_owner_decision_pending_items():
    """Future review queue should surface feedback-reported and owner-decision-pending items."""
