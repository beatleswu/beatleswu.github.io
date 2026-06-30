import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = (
    REPO_ROOT / "tests" / "sgf_engine" / "data" / "gold_fixtures" / "fixtures.json"
)
OVERRIDES_PATH = REPO_ROOT / "puzzle_variation_overrides.json"

READY = "READY"
EXCLUDED = "EXCLUDED"
CANDIDATE_ONLY = "CANDIDATE_ONLY"
DISABLED = "DISABLED"
NEEDS_REVIEW = "NEEDS_REVIEW"
OWNER_DECISION_PENDING = "OWNER_DECISION_PENDING"
PRODUCTION_OVERRIDE_INACTIVE = "PRODUCTION_OVERRIDE_INACTIVE"


def _manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_current_manifest_status_literals_support_teacher_facing_taxonomy():
    manifest = _manifest()
    ready_records = manifest["fixtures"]
    excluded_records = manifest["excluded_fixtures"]

    ready_owner_statuses = {record["owner_status"] for record in ready_records}
    excluded_statuses = {record["status"] for record in excluded_records}

    assert READY == "READY"
    assert EXCLUDED == "EXCLUDED"
    assert CANDIDATE_ONLY == "CANDIDATE_ONLY"
    assert DISABLED == "DISABLED"
    assert NEEDS_REVIEW == "NEEDS_REVIEW"
    assert OWNER_DECISION_PENDING == "OWNER_DECISION_PENDING"
    assert PRODUCTION_OVERRIDE_INACTIVE == "PRODUCTION_OVERRIDE_INACTIVE"

    assert ready_owner_statuses == {"READY"}
    assert excluded_statuses == {"CANDIDATE_REQUIRES_OVERRIDE", "PENDING"}


def test_ready_active_records_remain_free_of_candidate_and_disabled_metadata():
    manifest = _manifest()

    for record in manifest["fixtures"]:
        assert record["owner_status"] == "READY"
        assert record["ready_for_next_test_commit"] is True
        assert "status" not in record
        assert "disabled_override_metadata" not in record
        assert "proposed_override" not in record
        assert "runtime_override_active" not in record
        assert "apply_automatically" not in record
        assert "puzzle_id" not in record
        assert "gold_fixture_id" not in record


def test_candidate_only_identity_stays_outside_ready_active_identity_set():
    manifest = _manifest()
    ready_identity_keys = {
        (record["fixture_path"], record["player_move_sgf"])
        for record in manifest["fixtures"]
    }
    ready_ids = {record["gf_id"] for record in manifest["fixtures"]}
    excluded_by_id = {
        record["gf_id"]: record for record in manifest["excluded_fixtures"]
    }
    gf003 = excluded_by_id["GF-003"]
    metadata = gf003["disabled_override_metadata"]

    assert gf003["status"] == "CANDIDATE_REQUIRES_OVERRIDE"
    assert gf003["gf_id"] not in ready_ids
    assert metadata["gold_fixture_id"] not in ready_ids
    assert (gf003["fixture_path"], gf003["player_move_sgf"]) not in ready_identity_keys
    assert (metadata["source_path"], metadata["player_move_sgf"]) not in ready_identity_keys


def test_disabled_candidate_metadata_remains_runtime_inactive():
    manifest = _manifest()
    excluded_by_id = {
        record["gf_id"]: record for record in manifest["excluded_fixtures"]
    }
    gf003 = excluded_by_id["GF-003"]
    metadata = gf003["disabled_override_metadata"]

    assert metadata["runtime_status"] == "disabled"
    assert metadata["apply_automatically"] is False
    assert metadata["runtime_override_active"] is False
    assert metadata["ready_activation"] is False
    assert gf003["runtime_override_active"] is False
    assert gf003["ready_activation"] is False


def test_proposed_override_metadata_does_not_mean_active_production_override():
    manifest = _manifest()
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    excluded_by_id = {
        record["gf_id"]: record for record in manifest["excluded_fixtures"]
    }
    gf003 = excluded_by_id["GF-003"]

    assert gf003["proposed_override"]["source_key"] == gf003["fixture_path"]
    assert gf003["proposed_override"]["equivalent_moves"] == {"sf": ["sd"]}
    assert overrides == {}


def test_gf003_remains_candidate_only_disabled_and_without_production_override():
    manifest = _manifest()
    excluded_by_id = {
        record["gf_id"]: record for record in manifest["excluded_fixtures"]
    }
    gf003 = excluded_by_id["GF-003"]

    assert gf003["status"] == "CANDIDATE_REQUIRES_OVERRIDE"
    assert gf003["test_only_override_validation"] is True
    assert gf003["runtime_override_active"] is False
    assert gf003["ready_for_next_test_commit"] is False
    assert gf003["disabled_override_metadata"]["runtime_status"] == "disabled"
    assert gf003["disabled_override_metadata"]["apply_automatically"] is False


def test_manifest_metadata_references_stay_consistent_for_teacher_review_context():
    manifest = _manifest()
    excluded_by_id = {
        record["gf_id"]: record for record in manifest["excluded_fixtures"]
    }
    gf003 = excluded_by_id["GF-003"]
    metadata = gf003["disabled_override_metadata"]

    assert metadata["gold_fixture_id"] == gf003["gf_id"] == "GF-003"
    assert metadata["source_path"] == gf003["fixture_path"]
    assert metadata["player_move_sgf"] == gf003["player_move_sgf"] == "B[sd]"
    assert metadata["canonical_move_sgf"] == gf003["canonical_move_sgf"] == "B[sf]"


def test_pending_records_remain_review_items_not_runtime_or_ready_items():
    manifest = _manifest()
    pending_records = [
        record
        for record in manifest["excluded_fixtures"]
        if record["status"] == "PENDING"
    ]

    assert {record["gf_id"] for record in pending_records} == {"GF-004", "GF-006", "GF-007"}

    for record in pending_records:
        assert "fixture_path" not in record
        assert "disabled_override_metadata" not in record
        assert "proposed_override" not in record
        assert "runtime_override_active" not in record
        assert "ready_for_next_test_commit" not in record


def test_repository_override_document_stays_globally_inactive():
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))

    assert overrides == {}
