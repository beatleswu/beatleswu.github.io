import pytest

from sgf_engine.override.override_identity import build_override_index, find_override
from sgf_engine.override.override_schema import (
    RUNTIME_DISABLED,
    RUNTIME_ENABLED,
    validate_override_record,
    validate_override_records,
)


GF_003_DISABLED_RECORD = {
    "puzzle_id": "gf-003",
    "puzzle_version_id": "2026-06-30-gf-003",
    "sgf_sha256": "0713176F21C7A23133014A5956D935311B9AA8AA5A483A87CCF8100FEA5C7D29",
    "equivalent_moves": {
        # B[sf] (T14) remains canonical; B[sd] (T16) is the candidate equivalent.
        "sf": ["sd"],
    },
    "runtime_status": "disabled",
    "apply_automatically": False,
    "gold_fixture_id": "GF-003",
    "source_path": r"tests\sgf_engine\data\gold_fixtures\431.sgf",
}


def test_validate_override_record_accepts_disabled_gf_003_schema_example():
    record = validate_override_record(GF_003_DISABLED_RECORD)

    assert record.puzzle_id == "gf-003"
    assert record.puzzle_version_id == "2026-06-30-gf-003"
    assert record.sgf_sha256 == GF_003_DISABLED_RECORD["sgf_sha256"].lower()
    assert record.equivalent_moves == {"sf": ("sd",)}
    assert record.runtime_status == RUNTIME_DISABLED
    assert record.apply_automatically is False
    assert record.external_ref == "GF-003"
    assert record.source_path == "tests/sgf_engine/data/gold_fixtures/431.sgf"


def test_validate_override_records_requires_list_document():
    with pytest.raises(ValueError, match="must be a list"):
        validate_override_records({"puzzle_id": "gf-003"})


@pytest.mark.parametrize(
    ("field_name", "value", "error_match"),
    [
        ("puzzle_id", "", "puzzle_id must be a non-empty string"),
        ("puzzle_version_id", "", "puzzle_version_id must be a non-empty string"),
        ("sgf_sha256", "not-a-hash", "sgf_sha256 must be a 64-character hex string"),
        ("runtime_status", "candidate", "runtime_status must be 'enabled' or 'disabled'"),
        ("apply_automatically", "false", "apply_automatically must be a boolean"),
    ],
)
def test_validate_override_record_rejects_invalid_required_fields(
    field_name,
    value,
    error_match,
):
    payload = dict(GF_003_DISABLED_RECORD)
    payload[field_name] = value

    with pytest.raises(ValueError, match=error_match):
        validate_override_record(payload)


def test_validate_override_record_rejects_conflicting_external_refs():
    payload = dict(GF_003_DISABLED_RECORD)
    payload["external_ref"] = "NOT-GF-003"

    with pytest.raises(ValueError, match="must match"):
        validate_override_record(payload)


def test_build_override_index_uses_canonical_identity_only():
    enabled_record = {
        "puzzle_id": "gf-101",
        "puzzle_version_id": "v1",
        "sgf_sha256": "A" * 64,
        "equivalent_moves": {"dd": ["pq"]},
        "runtime_status": RUNTIME_ENABLED,
        "apply_automatically": True,
        "source_path": "SGF/path/101.sgf",
        "external_ref": "GF-101",
    }
    same_alias_different_identity = {
        "puzzle_id": "gf-102",
        "puzzle_version_id": "v2",
        "sgf_sha256": "B" * 64,
        "equivalent_moves": {"pp": ["qq"]},
        "runtime_status": RUNTIME_ENABLED,
        "apply_automatically": True,
        "source_path": "SGF/path/101.sgf",
        "external_ref": "GF-101",
    }

    index = build_override_index([enabled_record, same_alias_different_identity])

    assert set(index) == {("gf-101", "v1"), ("gf-102", "v2")}


def test_build_override_index_rejects_duplicate_canonical_identity():
    duplicate = {
        "puzzle_id": "gf-101",
        "puzzle_version_id": "v1",
        "sgf_sha256": "B" * 64,
        "equivalent_moves": {"pp": ["qq"]},
        "runtime_status": RUNTIME_ENABLED,
        "apply_automatically": False,
    }

    with pytest.raises(ValueError, match="duplicate override canonical identity"):
        build_override_index([GF_003_DISABLED_RECORD, duplicate, dict(duplicate)])


def test_find_override_requires_canonical_identity_and_hash_match():
    enabled_record = {
        "puzzle_id": "gf-101",
        "puzzle_version_id": "v1",
        "sgf_sha256": "A" * 64,
        "equivalent_moves": {"dd": ["pq"]},
        "runtime_status": RUNTIME_ENABLED,
        "apply_automatically": True,
        "source_path": "SGF/path/101.sgf",
        "external_ref": "GF-101",
    }

    record = find_override(
        [enabled_record],
        puzzle_id="gf-101",
        puzzle_version_id="v1",
        sgf_sha256="a" * 64,
    )

    assert record is not None
    assert record.puzzle_id == "gf-101"
    assert record.source_path == "SGF/path/101.sgf"

    assert (
        find_override(
            [enabled_record],
            puzzle_id="GF-101",
            puzzle_version_id="v1",
            sgf_sha256="a" * 64,
        )
        is None
    )
    assert (
        find_override(
            [enabled_record],
            puzzle_id="gf-101",
            puzzle_version_id="v1",
            sgf_sha256="b" * 64,
        )
        is None
    )


def test_find_override_ignores_disabled_records():
    assert (
        find_override(
            [GF_003_DISABLED_RECORD],
            puzzle_id="gf-003",
            puzzle_version_id="2026-06-30-gf-003",
            sgf_sha256=GF_003_DISABLED_RECORD["sgf_sha256"],
        )
        is None
    )
