from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
READINESS_DOC = ROOT / "docs" / "planning" / "phase13_teacher_admin_review_queue_readiness_map.md"
RISK_DOC = ROOT / "docs" / "planning" / "phase13_canonical_identity_migration_risk_register.md"


def _readiness_text() -> str:
    return READINESS_DOC.read_text(encoding="utf-8").lower()


def _risk_text() -> str:
    return RISK_DOC.read_text(encoding="utf-8").lower()


def test_phase13_readiness_and_risk_docs_exist() -> None:
    assert READINESS_DOC.exists()
    assert RISK_DOC.exists()


def test_readiness_map_records_phase_and_non_implementation_scope() -> None:
    text = _readiness_text()

    assert "phase: 13a" in text
    assert "status: readiness contract baseline" in text
    assert "scope: planning / contract baseline only" in text
    assert "phase 13a is not an implementation phase" in text


def test_readiness_map_preserves_phase12_identity_and_transition_baseline() -> None:
    text = _readiness_text()

    assert "canonical_puzzle_id = ingestion-generated stable uuid v4" in text
    assert "candidate_only_disabled -> ready_readonly = blocked direct transition" in text


def test_readiness_map_requires_expected_gates() -> None:
    text = _readiness_text()

    gates = [
        "owner_approval_gate",
        "db_schema_design_gate",
        "uuid_backfill_plan_gate",
        "uniqueness_constraint_plan_gate",
        "foreign_key_reference_plan_gate",
        "rollback_plan_gate",
        "post_migration_verification_gate",
        "api_contract_review_gate",
        "frontend_review_flow_safety_gate",
        "sgf_engine_non_regression_gate",
        "gf003_candidate_only_safety_gate",
    ]

    for gate in gates:
        assert gate in text


def test_readiness_map_records_entry_points_and_allowed_actions() -> None:
    text = _readiness_text()

    entry_points = [
        "passive_backend_review_queue",
        "active_frontend_answer_page_admin_triage",
    ]
    allowed_actions = [
        "report_issue",
        "mark_visual_validation_needed",
        "send_to_review",
        "close_as_resolved_no_action",
        "add_review_note",
        "route_high_risk_request_to_owner_decision",
    ]

    for entry_point in entry_points:
        assert entry_point in text

    for action in allowed_actions:
        assert action in text


def test_readiness_map_blocks_unsafe_teacher_admin_actions() -> None:
    text = _readiness_text()

    blocked_actions = [
        "directly_activate_candidate_only_variation",
        "directly_promote_disabled_item_to_ready",
        "directly_modify_sgf_bytes",
        "directly_create_runtime_override",
        "directly_create_production_override",
        "directly_change_sgf_engine_judging_semantics",
    ]

    for action in blocked_actions:
        assert action in text


def test_readiness_map_declares_non_implementation_scope() -> None:
    text = _readiness_text()

    non_goals = [
        "runtime behavior",
        "db schema",
        "db migration",
        "sqlalchemy model",
        "alembic migration",
        "api endpoint",
        "backend queue model",
        "frontend component",
        "wgo.js review ui",
        "production model",
        "teacher_admin runtime package",
        "production override activation",
        "runtime override activation",
        "ready promotion",
        "sgf byte editing",
        "sgf engine judging semantic changes",
    ]

    for non_goal in non_goals:
        assert non_goal in text


def test_risk_register_protects_owner_identity_decision() -> None:
    text = _risk_text()

    assert "canonical_puzzle_id = ingestion-generated stable uuid v4" in text or (
        "canonical_puzzle_id is defined as an ingestion-generated stable uuid v4" in text
    )

    rejected_identity_sources = [
        "source_path",
        "fixture_path",
        "gold_fixture_id",
        "frontend temporary id",
        "runtime state",
        "content hash",
        "auto-increment integer",
    ]

    for source in rejected_identity_sources:
        assert source in text


def test_risk_register_covers_expected_migration_risks() -> None:
    text = _risk_text()

    risks = [
        "r1 uuid backfill collision risk",
        "r2 unique constraint rollout risk",
        "r3 foreign key / reference integrity risk",
        "r4 source path identity regression risk",
        "r5 fixture identity regression risk",
        "r6 content hash identity regression risk",
        "r7 auto-increment identity regression risk",
        "r8 review queue unsafe transition risk",
        "r9 gf-003 accidental activation risk",
        "r10 rollback ambiguity risk",
        "r11 api / frontend coupling risk",
        "r12 sgf engine semantic regression risk",
    ]

    for risk in risks:
        assert risk in text


def test_risk_register_requires_future_migration_gates() -> None:
    text = _risk_text()

    gates = [
        "owner_approval_gate",
        "migration_design_review",
        "uuid_backfill_dry_run",
        "uuid_uniqueness_check",
        "orphan_reference_check",
        "rollback_or_forward_fix_plan",
        "post_migration_verification",
        "sgf_engine_non_regression_check",
        "gf003_candidate_only_safety_check",
    ]

    for gate in gates:
        assert gate in text


def test_risk_register_declares_non_implementation_scope() -> None:
    text = _risk_text()

    non_goals = [
        "runtime behavior",
        "db schema",
        "db migration",
        "sqlalchemy model",
        "alembic migration",
        "api endpoint",
        "backend queue model",
        "frontend component",
        "wgo.js review ui",
        "production model",
        "teacher_admin runtime package",
        "production override activation",
        "runtime override activation",
        "ready promotion",
        "sgf byte editing",
        "sgf engine judging semantic changes",
    ]

    for non_goal in non_goals:
        assert non_goal in text
