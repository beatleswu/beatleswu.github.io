from sgf_engine.override.override_runtime import (
    adapt_override_record_for_engine,
    lookup_active_runtime_override,
)
from sgf_engine.override.override_schema import (
    RUNTIME_DISABLED,
    RUNTIME_ENABLED,
    validate_override_record,
)


GF_003_DISABLED_RECORD = {
    "puzzle_id": "gf-003",
    "puzzle_version_id": "2026-06-30-gf-003",
    "sgf_sha256": "0713176F21C7A23133014A5956D935311B9AA8AA5A483A87CCF8100FEA5C7D29",
    "equivalent_moves": {
        # B[sf] (T14) remains canonical; B[sd] (T16) is the candidate equivalent.
        "sf": ["sd"],
    },
    "runtime_status": RUNTIME_DISABLED,
    "apply_automatically": False,
    "gold_fixture_id": "GF-003",
    "source_path": r"tests\sgf_engine\data\gold_fixtures\431.sgf",
}


def test_adapt_override_record_for_engine_preserves_mapping_shape():
    record = validate_override_record(
        {
            "puzzle_id": "gf-101",
            "puzzle_version_id": "v1",
            "sgf_sha256": "A" * 64,
            "equivalent_moves": {"dd": ["pq", "qp"]},
            "runtime_status": RUNTIME_ENABLED,
            "apply_automatically": True,
        }
    )

    payload = adapt_override_record_for_engine(record)

    assert payload == {"equivalent_moves": {"dd": ["pq", "qp"]}}
    assert payload["equivalent_moves"]["dd"] is not record.equivalent_moves["dd"]


def test_lookup_active_runtime_override_returns_payload_for_enabled_matching_record():
    payload = lookup_active_runtime_override(
        [
            {
                "puzzle_id": "gf-101",
                "puzzle_version_id": "v1",
                "sgf_sha256": "A" * 64,
                "equivalent_moves": {"dd": ["pq"]},
                "runtime_status": RUNTIME_ENABLED,
                "apply_automatically": True,
                "source_path": "SGF/path/101.sgf",
                "external_ref": "GF-101",
            }
        ],
        puzzle_id="gf-101",
        puzzle_version_id="v1",
        sgf_sha256="a" * 64,
    )

    assert payload == {"equivalent_moves": {"dd": ["pq"]}}


def test_lookup_active_runtime_override_rejects_hash_mismatch():
    payload = lookup_active_runtime_override(
        [
            {
                "puzzle_id": "gf-101",
                "puzzle_version_id": "v1",
                "sgf_sha256": "A" * 64,
                "equivalent_moves": {"dd": ["pq"]},
                "runtime_status": RUNTIME_ENABLED,
                "apply_automatically": True,
            }
        ],
        puzzle_id="gf-101",
        puzzle_version_id="v1",
        sgf_sha256="b" * 64,
    )

    assert payload is None


def test_lookup_active_runtime_override_ignores_disabled_gf003_example():
    payload = lookup_active_runtime_override(
        [GF_003_DISABLED_RECORD],
        puzzle_id="gf-003",
        puzzle_version_id="2026-06-30-gf-003",
        sgf_sha256=GF_003_DISABLED_RECORD["sgf_sha256"],
    )

    assert payload is None


def test_lookup_active_runtime_override_requires_apply_automatically():
    payload = lookup_active_runtime_override(
        [
            {
                "puzzle_id": "gf-101",
                "puzzle_version_id": "v1",
                "sgf_sha256": "A" * 64,
                "equivalent_moves": {"dd": ["pq"]},
                "runtime_status": RUNTIME_ENABLED,
                "apply_automatically": False,
            }
        ],
        puzzle_id="gf-101",
        puzzle_version_id="v1",
        sgf_sha256="A" * 64,
    )

    assert payload is None


def test_source_path_is_metadata_only_not_canonical_lookup_key():
    records = [
        {
            "puzzle_id": "gf-101",
            "puzzle_version_id": "v1",
            "sgf_sha256": "A" * 64,
            "equivalent_moves": {"dd": ["pq"]},
            "runtime_status": RUNTIME_ENABLED,
            "apply_automatically": True,
            "source_path": "SGF/shared/101.sgf",
        },
        {
            "puzzle_id": "gf-102",
            "puzzle_version_id": "v2",
            "sgf_sha256": "B" * 64,
            "equivalent_moves": {"pp": ["qq"]},
            "runtime_status": RUNTIME_ENABLED,
            "apply_automatically": True,
            "source_path": "SGF/shared/101.sgf",
        },
    ]

    payload = lookup_active_runtime_override(
        records,
        puzzle_id="gf-102",
        puzzle_version_id="v2",
        sgf_sha256="b" * 64,
    )

    assert payload == {"equivalent_moves": {"pp": ["qq"]}}
    assert (
        lookup_active_runtime_override(
            records,
            puzzle_id="SGF/shared/101.sgf",
            puzzle_version_id="v2",
            sgf_sha256="b" * 64,
        )
        is None
    )


def test_gold_fixture_id_is_metadata_only_not_canonical_lookup_key():
    records = [
        {
            "puzzle_id": "gf-201",
            "puzzle_version_id": "v1",
            "sgf_sha256": "C" * 64,
            "equivalent_moves": {"dd": ["pq"]},
            "runtime_status": RUNTIME_ENABLED,
            "apply_automatically": True,
            "gold_fixture_id": "GF-ALIAS",
        }
    ]

    payload = lookup_active_runtime_override(
        records,
        puzzle_id="gf-201",
        puzzle_version_id="v1",
        sgf_sha256="c" * 64,
    )

    assert payload == {"equivalent_moves": {"dd": ["pq"]}}
    assert (
        lookup_active_runtime_override(
            records,
            puzzle_id="GF-ALIAS",
            puzzle_version_id="v1",
            sgf_sha256="c" * 64,
        )
        is None
    )
