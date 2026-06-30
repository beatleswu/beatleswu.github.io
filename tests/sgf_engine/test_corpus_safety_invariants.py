import json
from pathlib import Path

import pytest

from sgf_engine.override import override_loader
from sgf_engine.override.override_schema import validate_override_record


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = (
    REPO_ROOT / "tests" / "sgf_engine" / "data" / "gold_fixtures" / "fixtures.json"
)
OVERRIDES_PATH = REPO_ROOT / "puzzle_variation_overrides.json"

OVERRIDE_ONLY_FIELDS = {
    "gold_fixture_id",
    "puzzle_id",
    "puzzle_version_id",
    "runtime_status",
    "apply_automatically",
    "source_path",
}


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ready_records(manifest):
    return manifest["fixtures"]


@pytest.fixture(scope="module")
def excluded_records(manifest):
    return manifest["excluded_fixtures"]


def test_ready_and_excluded_sets_remain_disjoint_with_expected_status_buckets(
    ready_records,
    excluded_records,
):
    ready_ids = {record["gf_id"] for record in ready_records}
    excluded_ids = {record["gf_id"] for record in excluded_records}
    excluded_statuses = {record["gf_id"]: record["status"] for record in excluded_records}

    assert ready_ids.isdisjoint(excluded_ids)
    assert excluded_statuses == {
        "GF-003": "CANDIDATE_REQUIRES_OVERRIDE",
        "GF-004": "PENDING",
        "GF-006": "PENDING",
        "GF-007": "PENDING",
    }


def test_ready_records_do_not_expose_override_only_metadata_fields(ready_records):
    for record in ready_records:
        assert record["owner_status"] == "READY"
        assert record["ready_for_next_test_commit"] is True
        assert OVERRIDE_ONLY_FIELDS.isdisjoint(record)
        assert "disabled_override_metadata" not in record
        assert "proposed_override" not in record
        assert "override_required" not in record
        assert "runtime_override_active" not in record
        assert "ready_activation" not in record


def test_only_gf003_candidate_record_carries_disabled_override_metadata(excluded_records):
    excluded_by_id = {record["gf_id"]: record for record in excluded_records}

    assert "disabled_override_metadata" in excluded_by_id["GF-003"]
    assert "proposed_override" in excluded_by_id["GF-003"]

    for gf_id in ("GF-004", "GF-006", "GF-007"):
        assert "fixture_path" not in excluded_by_id[gf_id]
        assert "disabled_override_metadata" not in excluded_by_id[gf_id]
        assert "proposed_override" not in excluded_by_id[gf_id]


def test_real_production_override_file_is_empty_and_loads_no_manifest_fixture_override(
    manifest,
):
    overrides_document = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    manifest_records = manifest["fixtures"] + manifest["excluded_fixtures"]

    assert overrides_document == {}

    for record in manifest_records:
        fixture_path = record.get("fixture_path")
        if fixture_path is None:
            continue
        assert override_loader.load_override(fixture_path) is None


def test_gf003_candidate_metadata_stays_schema_valid_but_runtime_inactive(
    excluded_records,
):
    excluded_by_id = {record["gf_id"]: record for record in excluded_records}
    gf003 = excluded_by_id["GF-003"]
    metadata = gf003["disabled_override_metadata"]
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
    assert gf003["runtime_override_active"] is False
    assert gf003["ready_for_next_test_commit"] is False
    assert gf003["proposed_override"]["source_key"] == gf003["fixture_path"]
    assert override_loader.load_override(gf003["fixture_path"]) is None

    assert validated.external_ref == "GF-003"
    assert validated.source_path == gf003["fixture_path"]
    assert validated.runtime_status == "disabled"
    assert validated.apply_automatically is False
