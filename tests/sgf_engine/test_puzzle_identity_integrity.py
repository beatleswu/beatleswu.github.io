import hashlib
import json
from pathlib import Path

from sgf_engine.override.override_schema import validate_override_record


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "sgf_engine" / "data" / "gold_fixtures"
MANIFEST_PATH = FIXTURE_DIR / "fixtures.json"
OVERRIDES_PATH = REPO_ROOT / "puzzle_variation_overrides.json"


def _manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _fixture_bytes(record):
    return (REPO_ROOT / record["fixture_path"]).read_bytes()


def test_ready_active_set_uses_unique_fixture_move_identity_and_excludes_candidate_fields():
    manifest = _manifest()
    ready_records = manifest["fixtures"]

    ready_ids = [record["gf_id"] for record in ready_records]
    ready_identity_keys = [
        (record["fixture_path"], record["player_move_sgf"]) for record in ready_records
    ]

    assert len(ready_ids) == len(set(ready_ids))
    assert len(ready_identity_keys) == len(set(ready_identity_keys))

    for record in ready_records:
        assert record["owner_status"] == "READY"
        assert record["ready_for_next_test_commit"] is True
        assert "disabled_override_metadata" not in record
        assert "proposed_override" not in record
        assert "status" not in record
        assert "gold_fixture_id" not in record
        assert "puzzle_id" not in record
        assert "puzzle_version_id" not in record
        assert "runtime_override_active" not in record


def test_candidate_fixture_metadata_round_trips_to_manifest_fixture_and_bytes():
    manifest = _manifest()
    excluded_by_id = {
        record["gf_id"]: record for record in manifest["excluded_fixtures"]
    }
    gf003 = excluded_by_id["GF-003"]
    metadata = gf003["disabled_override_metadata"]
    proposed_override = gf003["proposed_override"]

    validated = validate_override_record(
        {
            "puzzle_id": metadata["puzzle_id"],
            "puzzle_version_id": metadata["puzzle_version_id"],
            "sgf_sha256": metadata["sgf_sha256"],
            "equivalent_moves": metadata["equivalent_moves"],
            "runtime_status": metadata["runtime_status"],
            "apply_automatically": metadata["apply_automatically"],
            "gold_fixture_id": metadata["gold_fixture_id"],
            "source_path": metadata["source_path"],
        }
    )

    assert gf003["status"] == "CANDIDATE_REQUIRES_OVERRIDE"
    assert gf003["ready_for_next_test_commit"] is False
    assert metadata["gold_fixture_id"] == gf003["gf_id"] == "GF-003"
    assert metadata["source_path"] == gf003["fixture_path"]
    assert metadata["player_move_sgf"] == gf003["player_move_sgf"] == "B[sd]"
    assert metadata["canonical_move_sgf"] == gf003["canonical_move_sgf"] == "B[sf]"
    assert metadata["runtime_status"] == "disabled"
    assert metadata["apply_automatically"] is False
    assert metadata["runtime_override_active"] is False
    assert metadata["ready_activation"] is False
    assert metadata["override_required"] is True
    assert proposed_override["source_key"] == gf003["fixture_path"]
    assert proposed_override["equivalent_moves"] == metadata["equivalent_moves"]

    fixture_bytes = _fixture_bytes(gf003)
    assert hashlib.sha256(fixture_bytes).hexdigest().upper() == gf003["sha256"]
    assert gf003["sha256"] == metadata["sgf_sha256"]

    assert validated.puzzle_id == "gf-003"
    assert validated.puzzle_version_id == "2026-06-30-gf-003"
    assert validated.sgf_sha256 == metadata["sgf_sha256"].lower()
    assert validated.external_ref == "GF-003"
    assert validated.source_path == gf003["fixture_path"]


def test_candidate_fixture_identity_does_not_leak_into_ready_active_set():
    manifest = _manifest()
    ready_records = manifest["fixtures"]
    excluded_by_id = {
        record["gf_id"]: record for record in manifest["excluded_fixtures"]
    }
    gf003 = excluded_by_id["GF-003"]
    metadata = gf003["disabled_override_metadata"]

    ready_ids = {record["gf_id"] for record in ready_records}
    ready_identity_keys = {
        (record["fixture_path"], record["player_move_sgf"]) for record in ready_records
    }

    assert metadata["gold_fixture_id"] not in ready_ids
    assert (metadata["source_path"], metadata["player_move_sgf"]) not in ready_identity_keys
    assert "GF-003" not in ready_ids


def test_repository_override_config_remains_empty_candidate_safe_document():
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))

    assert overrides == {}
