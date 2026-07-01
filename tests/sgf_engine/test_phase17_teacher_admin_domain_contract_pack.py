import unicodedata
from pathlib import Path


DOC_PATH = Path("docs/planning/phase17_teacher_admin_domain_contract_pack.md")
TEST_PATH = Path("tests/sgf_engine/test_phase17_teacher_admin_domain_contract_pack.py")


EXPLICIT_BIDI_CONTROLS = {
    "\u061c",
    "\u200e",
    "\u200f",
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
    "\u2066",
    "\u2067",
    "\u2068",
    "\u2069",
}


REVIEW_QUEUE_STATES = {
    "ready_readonly",
    "needs_review",
    "pending_owner_decision",
    "candidate_only_disabled",
    "feedback_reported",
    "visual_validation_needed",
    "archived",
    "closed",
}


BLOCKED_DIRECT_TRANSITIONS = {
    ("candidate_only_disabled", "ready_readonly"),
    ("pending_owner_decision", "ready_readonly"),
    ("feedback_reported", "ready_readonly"),
}


LOW_RISK_TEACHER_ACTIONS = {
    "add_review_note",
    "add_teacher_tag",
    "set_needs_review",
    "set_visual_validation_needed",
    "escalate_to_owner_decision",
    "archive_without_truth_change",
    "close_without_truth_change",
    "mark_false_positive_without_truth_change",
    "link_feedback_report",
}


GUARDED_C_LEVEL_ACTIONS = {
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


FORBIDDEN_LOW_RISK_EFFECTS = {
    "modify_SGF_bytes",
    "modify_READY_IDS",
    "modify_puzzle_variation_overrides_json",
    "activate_runtime_override",
    "activate_production_override",
    "change_judging_semantics",
    "promote_candidate_only_to_ready",
    "enable_GF003",
    "allow_B_sd_T16_active",
}


AUDIT_TRACE_CONTRACT = {
    "owner_decision_trace_default": "append_only",
    "audit_history_default": "append_only",
    "archive_deletes_history": False,
    "close_deletes_history": False,
    "teacher_ui_can_silently_delete_history": False,
    "phase17_creates_production_schema": False,
    "phase17_implements_auth": False,
    "phase17_implements_api": False,
    "phase17_implements_ui": False,
}


FUTURE_AUDIT_EVENT_FIELDS = {
    "event_id",
    "canonical_puzzle_id",
    "actor_id",
    "actor_role",
    "action",
    "previous_status",
    "next_status",
    "reason",
    "entry_point",
    "created_at",
    "related_feedback_id",
    "related_owner_decision_id",
}


ACTIVE_FRONTEND_TRIAGE_ALLOWED = {
    "create_feedback_report",
    "add_review_note",
    "set_needs_review",
    "set_visual_validation_needed",
    "escalate_to_owner_decision",
    "archive_without_truth_change",
    "close_without_truth_change",
}


ACTIVE_FRONTEND_TRIAGE_FORBIDDEN = {
    "promote_to_ready",
    "activate_candidate_solution",
    "enable_GF003",
    "allow_B_sd_T16_active",
    "write_puzzle_variation_overrides_json",
    "modify_SGF_bytes",
    "modify_READY_IDS",
    "change_judging_semantics",
    "add_runtime_override",
    "add_production_override",
}


CANONICAL_IDENTITY_CONTRACT = {
    "canonical_puzzle_id": "ingestion_generated_stable_uuid_v4",
    "review_queue_refs_canonical_puzzle_id": True,
    "active_triage_preserves_canonical_puzzle_id": True,
    "source_path_is_identity": False,
    "fixture_path_is_identity": False,
    "gold_fixture_id_is_identity": False,
    "frontend_temporary_id_is_identity": False,
    "runtime_state_is_identity": False,
    "content_hash_is_primary_identity": False,
    "autoincrement_integer_is_primary_identity": False,
}


GF003_SAFETY_CONTRACT = {
    "gf003_enabled": False,
    "b_sd_t16_active": False,
    "b_sf_t14_is_canonical_sgf_answer": True,
    "runtime_override_added": False,
    "production_override_added": False,
    "ready_ids_changed": False,
    "sgf_bytes_changed": False,
    "judging_semantics_changed": False,
}


PHASE17_NON_GOALS = {
    "sqlalchemy_dependency_added": False,
    "alembic_dependency_added": False,
    "alembic_migration_added": False,
    "production_db_model_added": False,
    "physical_db_file_added": False,
    "api_added": False,
    "backend_runtime_added": False,
    "frontend_ui_added": False,
    "wgojs_changed": False,
    "production_sgf_engine_changed": False,
}


def _assert_utf8_lf_only_without_hidden_controls(path: Path) -> None:
    data = path.read_bytes()
    assert data, "File should not be empty"
    assert not data.startswith(b"\xef\xbb\xbf"), "File must not contain UTF-8 BOM"
    assert b"\r" not in data, "File must use LF-only line endings"

    text = data.decode("utf-8")

    for index, char in enumerate(text):
        category = unicodedata.category(char)
        assert char not in EXPLICIT_BIDI_CONTROLS, (
            f"Hidden/bidi Unicode control found at index {index}: U+{ord(char):04X}"
        )
        assert not (
            category.startswith("C") and char not in {"\n", "\t"}
        ), f"Unexpected control character at index {index}: U+{ord(char):04X} {category}"


def test_phase17_contract_files_exist_and_are_utf8_lf_only_without_hidden_controls():
    assert DOC_PATH.is_file()
    assert TEST_PATH.is_file()
    _assert_utf8_lf_only_without_hidden_controls(DOC_PATH)
    _assert_utf8_lf_only_without_hidden_controls(TEST_PATH)


def test_phase17_review_queue_states_and_blocked_transitions():
    assert "candidate_only_disabled" in REVIEW_QUEUE_STATES
    assert "pending_owner_decision" in REVIEW_QUEUE_STATES
    assert "ready_readonly" in REVIEW_QUEUE_STATES
    assert ("candidate_only_disabled", "ready_readonly") in BLOCKED_DIRECT_TRANSITIONS
    assert ("pending_owner_decision", "ready_readonly") in BLOCKED_DIRECT_TRANSITIONS
    assert ("feedback_reported", "ready_readonly") in BLOCKED_DIRECT_TRANSITIONS


def test_phase17_teacher_actions_split_low_risk_from_c_level():
    assert "add_review_note" in LOW_RISK_TEACHER_ACTIONS
    assert "set_needs_review" in LOW_RISK_TEACHER_ACTIONS
    assert "escalate_to_owner_decision" in LOW_RISK_TEACHER_ACTIONS
    assert LOW_RISK_TEACHER_ACTIONS.isdisjoint(GUARDED_C_LEVEL_ACTIONS)
    assert "promote_to_ready" in GUARDED_C_LEVEL_ACTIONS
    assert "activate_candidate_solution" in GUARDED_C_LEVEL_ACTIONS
    assert "enable_GF003" in GUARDED_C_LEVEL_ACTIONS
    assert "allow_B_sd_T16_active" in GUARDED_C_LEVEL_ACTIONS


def test_phase17_low_risk_actions_cannot_change_production_truth():
    assert "modify_SGF_bytes" in FORBIDDEN_LOW_RISK_EFFECTS
    assert "modify_READY_IDS" in FORBIDDEN_LOW_RISK_EFFECTS
    assert "modify_puzzle_variation_overrides_json" in FORBIDDEN_LOW_RISK_EFFECTS
    assert "activate_runtime_override" in FORBIDDEN_LOW_RISK_EFFECTS
    assert "activate_production_override" in FORBIDDEN_LOW_RISK_EFFECTS
    assert "change_judging_semantics" in FORBIDDEN_LOW_RISK_EFFECTS
    assert "promote_candidate_only_to_ready" in FORBIDDEN_LOW_RISK_EFFECTS


def test_phase17_audit_trace_is_append_only_and_not_deleted_by_queue_actions():
    assert AUDIT_TRACE_CONTRACT["owner_decision_trace_default"] == "append_only"
    assert AUDIT_TRACE_CONTRACT["audit_history_default"] == "append_only"
    assert AUDIT_TRACE_CONTRACT["archive_deletes_history"] is False
    assert AUDIT_TRACE_CONTRACT["close_deletes_history"] is False
    assert AUDIT_TRACE_CONTRACT["teacher_ui_can_silently_delete_history"] is False
    assert AUDIT_TRACE_CONTRACT["phase17_creates_production_schema"] is False


def test_phase17_future_audit_event_fields_are_conceptual_only():
    assert "canonical_puzzle_id" in FUTURE_AUDIT_EVENT_FIELDS
    assert "actor_role" in FUTURE_AUDIT_EVENT_FIELDS
    assert "previous_status" in FUTURE_AUDIT_EVENT_FIELDS
    assert "next_status" in FUTURE_AUDIT_EVENT_FIELDS
    assert "entry_point" in FUTURE_AUDIT_EVENT_FIELDS
    assert AUDIT_TRACE_CONTRACT["phase17_implements_auth"] is False
    assert AUDIT_TRACE_CONTRACT["phase17_implements_api"] is False
    assert AUDIT_TRACE_CONTRACT["phase17_implements_ui"] is False


def test_phase17_active_frontend_triage_allowed_actions_are_metadata_only():
    assert "create_feedback_report" in ACTIVE_FRONTEND_TRIAGE_ALLOWED
    assert "add_review_note" in ACTIVE_FRONTEND_TRIAGE_ALLOWED
    assert "set_needs_review" in ACTIVE_FRONTEND_TRIAGE_ALLOWED
    assert "escalate_to_owner_decision" in ACTIVE_FRONTEND_TRIAGE_ALLOWED
    assert ACTIVE_FRONTEND_TRIAGE_ALLOWED.isdisjoint(ACTIVE_FRONTEND_TRIAGE_FORBIDDEN)


def test_phase17_active_frontend_triage_forbids_direct_truth_changes():
    assert "promote_to_ready" in ACTIVE_FRONTEND_TRIAGE_FORBIDDEN
    assert "activate_candidate_solution" in ACTIVE_FRONTEND_TRIAGE_FORBIDDEN
    assert "enable_GF003" in ACTIVE_FRONTEND_TRIAGE_FORBIDDEN
    assert "allow_B_sd_T16_active" in ACTIVE_FRONTEND_TRIAGE_FORBIDDEN
    assert "write_puzzle_variation_overrides_json" in ACTIVE_FRONTEND_TRIAGE_FORBIDDEN
    assert "modify_SGF_bytes" in ACTIVE_FRONTEND_TRIAGE_FORBIDDEN
    assert "modify_READY_IDS" in ACTIVE_FRONTEND_TRIAGE_FORBIDDEN
    assert "change_judging_semantics" in ACTIVE_FRONTEND_TRIAGE_FORBIDDEN


def test_phase17_preserves_canonical_puzzle_identity_boundary():
    assert (
        CANONICAL_IDENTITY_CONTRACT["canonical_puzzle_id"]
        == "ingestion_generated_stable_uuid_v4"
    )
    assert CANONICAL_IDENTITY_CONTRACT["review_queue_refs_canonical_puzzle_id"] is True
    assert CANONICAL_IDENTITY_CONTRACT["active_triage_preserves_canonical_puzzle_id"] is True
    assert CANONICAL_IDENTITY_CONTRACT["source_path_is_identity"] is False
    assert CANONICAL_IDENTITY_CONTRACT["fixture_path_is_identity"] is False
    assert CANONICAL_IDENTITY_CONTRACT["gold_fixture_id_is_identity"] is False
    assert CANONICAL_IDENTITY_CONTRACT["content_hash_is_primary_identity"] is False
    assert CANONICAL_IDENTITY_CONTRACT["autoincrement_integer_is_primary_identity"] is False


def test_phase17_preserves_gf003_and_override_safety_boundary():
    assert GF003_SAFETY_CONTRACT["gf003_enabled"] is False
    assert GF003_SAFETY_CONTRACT["b_sd_t16_active"] is False
    assert GF003_SAFETY_CONTRACT["b_sf_t14_is_canonical_sgf_answer"] is True
    assert GF003_SAFETY_CONTRACT["runtime_override_added"] is False
    assert GF003_SAFETY_CONTRACT["production_override_added"] is False
    assert GF003_SAFETY_CONTRACT["ready_ids_changed"] is False
    assert GF003_SAFETY_CONTRACT["sgf_bytes_changed"] is False
    assert GF003_SAFETY_CONTRACT["judging_semantics_changed"] is False


def test_phase17_remains_docs_tests_only_without_dependencies_or_runtime():
    assert PHASE17_NON_GOALS["sqlalchemy_dependency_added"] is False
    assert PHASE17_NON_GOALS["alembic_dependency_added"] is False
    assert PHASE17_NON_GOALS["alembic_migration_added"] is False
    assert PHASE17_NON_GOALS["production_db_model_added"] is False
    assert PHASE17_NON_GOALS["physical_db_file_added"] is False
    assert PHASE17_NON_GOALS["api_added"] is False
    assert PHASE17_NON_GOALS["backend_runtime_added"] is False
    assert PHASE17_NON_GOALS["frontend_ui_added"] is False
    assert PHASE17_NON_GOALS["wgojs_changed"] is False
    assert PHASE17_NON_GOALS["production_sgf_engine_changed"] is False
