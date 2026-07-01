import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = (
    REPO_ROOT / "tests" / "sgf_engine" / "data" / "gold_fixtures" / "fixtures.json"
)
OVERRIDES_PATH = REPO_ROOT / "puzzle_variation_overrides.json"
DOC_PATH = (
    REPO_ROOT
    / "docs"
    / "planning"
    / "teacher_admin_domain_taxonomy_feedback_baseline.md"
)

FUTURE_RUNTIME_CONTROL_FIELDS = {
    "domain_tags",
    "difficulty_label",
    "teacher_custom_tags",
    "student_report_count",
    "issue_reason",
    "review_queue_status",
    "teacher_review_notes",
    "confirmed_issue",
    "false_alarm",
    "review_priority",
    "student_report_context",
}


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def gf003(manifest):
    excluded_by_id = {
        record["gf_id"]: record for record in manifest["excluded_fixtures"]
    }
    return excluded_by_id["GF-003"]


@pytest.fixture(scope="module")
def doc_text():
    return DOC_PATH.read_text(encoding="utf-8")


def test_production_override_document_remains_empty():
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))

    assert overrides == {}


def test_gf003_remains_disabled_candidate_only_without_production_override(gf003):
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


def test_current_manifest_does_not_define_active_formal_taxonomy_or_feedback_schema(
    manifest, gf003
):
    for record in manifest["fixtures"]:
        for field in FUTURE_RUNTIME_CONTROL_FIELDS:
            assert field not in record

    for record in manifest["excluded_fixtures"]:
        for field in FUTURE_RUNTIME_CONTROL_FIELDS:
            assert field not in record

    for field in FUTURE_RUNTIME_CONTROL_FIELDS:
        assert field not in gf003["disabled_override_metadata"]
        assert field not in gf003["proposed_override"]


def test_current_tag_like_and_report_like_metadata_remains_non_runtime(gf003):
    metadata = gf003["disabled_override_metadata"]

    assert gf003["reason"]
    assert gf003["proposed_override"]["source_key"] == gf003["fixture_path"]
    assert gf003["proposed_override"]["equivalent_moves"] == {"sf": ["sd"]}
    assert metadata["gold_fixture_id"] == "GF-003"
    assert metadata["source_path"] == gf003["fixture_path"]
    assert metadata["runtime_status"] == "disabled"
    assert metadata["apply_automatically"] is False
    assert gf003["runtime_override_active"] is False
    assert gf003["ready_activation"] is False


def test_doc_marks_future_c_level_requirements_and_non_actions(doc_text):
    assert "[Future C-level Requirement]" in doc_text
    assert "This PR does not add a formal domain tag schema." in doc_text
    assert "This PR does not add a formal feedback or report queue." in doc_text
    assert "This PR does not modify `fixtures.json`." in doc_text
    assert "This PR does not add DB, API, backend, or frontend UI." in doc_text


def test_doc_requires_feedback_binding_to_future_canonical_puzzle_identity(doc_text):
    assert "must bind strongly to a future canonical puzzle identity" in doc_text
    assert "The following are not canonical puzzle identity:" in doc_text
    assert "- `source_path`" in doc_text
    assert "- `fixture_path`" in doc_text
    assert "- `gold_fixture_id`" in doc_text
    assert "traceability metadata only" in doc_text


def test_doc_includes_corrected_dan_grouping(doc_text):
    assert "- 1D-2D" in doc_text
    assert "- 3D-4D" in doc_text
    assert "- 5D-6D" in doc_text
    assert "- 7D+" in doc_text


@pytest.mark.skip(reason="Pending C-level implementation: formal domain taxonomy schema")
def test_future_domain_tag_filtering_acceptance_criteria():
    """Future teacher admin should filter puzzles by Go domain tags without changing runtime status."""


@pytest.mark.skip(
    reason="Pending C-level implementation: feedback queue and canonical puzzle identity"
)
def test_future_feedback_queue_binds_reports_to_canonical_puzzle_identity():
    """Future issue reports must bind to canonical puzzle identity, not source_path, fixture_path, or gold_fixture_id."""


@pytest.mark.skip(reason="Pending C-level implementation: teacher-admin feedback queue")
def test_future_teacher_feedback_review_states_preserve_non_runtime_boundaries():
    """Future review states should expose issue triage without activating READY or production overrides."""
