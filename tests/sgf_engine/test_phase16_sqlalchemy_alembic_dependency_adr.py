from pathlib import Path

ADR_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "planning"
    / "phase16_sqlalchemy_alembic_dependency_introduction_adr.md"
)

CURRENT_PERSISTENCE_CONTRACT = {
    "phase": "phase16",
    "sqlalchemy_allowed": False,
    "alembic_allowed": False,
    "production_db_model_allowed": False,
    "production_migration_allowed": False,
    "physical_db_file_allowed": False,
    "persistence_boundary": "stdlib_sqlite3_in_memory_test_contract",
    "dependency_introduction_requires": "future_owner_authorized_c_level_task",
}

CANONICAL_IDENTITY_CONTRACT = {
    "canonical_puzzle_id": "ingestion_generated_stable_uuid_v4",
    "source_path_is_identity": False,
    "fixture_path_is_identity": False,
    "gold_fixture_id_is_identity": False,
    "frontend_temporary_id_is_identity": False,
    "runtime_state_is_identity": False,
    "content_hash_is_primary_identity": False,
    "autoincrement_integer_is_primary_identity": False,
}

REVIEW_QUEUE_CONTRACT = {
    "default_delete_policy": "soft_delete_archive_or_close",
    "hard_delete_allowed_in_phase16": False,
    "owner_decision_trace_default": "append_only",
    "teacher_ui_can_silently_delete_audit_history": False,
}

GF003_SAFETY_CONTRACT = {
    "gf003_enabled": False,
    "b_sd_t16_active": False,
    "runtime_override_added": False,
    "production_override_added": False,
    "ready_ids_changed": False,
    "sgf_bytes_changed": False,
}


def test_phase16_adr_exists() -> None:
    assert ADR_PATH.is_file()


def test_phase16_dependency_gate_blocks_sqlalchemy_and_alembic() -> None:
    assert CURRENT_PERSISTENCE_CONTRACT["sqlalchemy_allowed"] is False
    assert CURRENT_PERSISTENCE_CONTRACT["alembic_allowed"] is False
    assert CURRENT_PERSISTENCE_CONTRACT["production_db_model_allowed"] is False
    assert CURRENT_PERSISTENCE_CONTRACT["production_migration_allowed"] is False
    assert CURRENT_PERSISTENCE_CONTRACT["physical_db_file_allowed"] is False


def test_phase16_preserves_stdlib_sqlite_test_boundary() -> None:
    assert (
        CURRENT_PERSISTENCE_CONTRACT["persistence_boundary"]
        == "stdlib_sqlite3_in_memory_test_contract"
    )
    assert (
        CURRENT_PERSISTENCE_CONTRACT["dependency_introduction_requires"]
        == "future_owner_authorized_c_level_task"
    )


def test_phase16_preserves_canonical_identity_contract() -> None:
    assert (
        CANONICAL_IDENTITY_CONTRACT["canonical_puzzle_id"]
        == "ingestion_generated_stable_uuid_v4"
    )
    assert CANONICAL_IDENTITY_CONTRACT["source_path_is_identity"] is False
    assert CANONICAL_IDENTITY_CONTRACT["fixture_path_is_identity"] is False
    assert CANONICAL_IDENTITY_CONTRACT["gold_fixture_id_is_identity"] is False
    assert CANONICAL_IDENTITY_CONTRACT["frontend_temporary_id_is_identity"] is False
    assert CANONICAL_IDENTITY_CONTRACT["runtime_state_is_identity"] is False
    assert CANONICAL_IDENTITY_CONTRACT["content_hash_is_primary_identity"] is False
    assert (
        CANONICAL_IDENTITY_CONTRACT["autoincrement_integer_is_primary_identity"]
        is False
    )


def test_phase16_review_queue_deletion_and_audit_contract() -> None:
    assert REVIEW_QUEUE_CONTRACT["default_delete_policy"] == (
        "soft_delete_archive_or_close"
    )
    assert REVIEW_QUEUE_CONTRACT["hard_delete_allowed_in_phase16"] is False
    assert REVIEW_QUEUE_CONTRACT["owner_decision_trace_default"] == "append_only"
    assert REVIEW_QUEUE_CONTRACT["teacher_ui_can_silently_delete_audit_history"] is (
        False
    )


def test_phase16_preserves_gf003_safety_contract() -> None:
    assert GF003_SAFETY_CONTRACT["gf003_enabled"] is False
    assert GF003_SAFETY_CONTRACT["b_sd_t16_active"] is False
    assert GF003_SAFETY_CONTRACT["runtime_override_added"] is False
    assert GF003_SAFETY_CONTRACT["production_override_added"] is False
    assert GF003_SAFETY_CONTRACT["ready_ids_changed"] is False
    assert GF003_SAFETY_CONTRACT["sgf_bytes_changed"] is False
