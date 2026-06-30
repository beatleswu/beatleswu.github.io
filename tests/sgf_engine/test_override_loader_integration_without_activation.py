import pytest

from sgf_engine.override.override_loader_integration import (
    build_loader_override_index,
    lookup_loader_runtime_override,
)
from sgf_engine.override.override_schema import RUNTIME_DISABLED, RUNTIME_ENABLED


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


def test_build_loader_override_index_validates_document_and_indexes_canonically():
    index = build_loader_override_index(
        [
            {
                "puzzle_id": "gf-101",
                "puzzle_version_id": "v1",
                "sgf_sha256": "A" * 64,
                "equivalent_moves": {"dd": ["pq"]},
                "runtime_status": RUNTIME_ENABLED,
                "apply_automatically": True,
                "source_path": r"SGF\shared\101.sgf",
                "gold_fixture_id": "GF-101",
            },
            GF_003_DISABLED_RECORD,
        ]
    )

    assert set(index) == {("gf-101", "v1"), ("gf-003", "2026-06-30-gf-003")}
    assert index[("gf-101", "v1")].source_path == "SGF/shared/101.sgf"
    assert index[("gf-101", "v1")].external_ref == "GF-101"


def test_build_loader_override_index_requires_list_document():
    with pytest.raises(ValueError, match="must be a list"):
        build_loader_override_index({"puzzle_id": "gf-101"})


def test_lookup_loader_runtime_override_validates_raw_document_and_returns_payload():
    payload = lookup_loader_runtime_override(
        [
            {
                "puzzle_id": "gf-101",
                "puzzle_version_id": "v1",
                "sgf_sha256": "A" * 64,
                "equivalent_moves": {"dd": ["pq"]},
                "runtime_status": RUNTIME_ENABLED,
                "apply_automatically": True,
                "source_path": "SGF/path/101.sgf",
                "gold_fixture_id": "GF-101",
            }
        ],
        puzzle_id="gf-101",
        puzzle_version_id="v1",
        sgf_sha256="a" * 64,
    )

    assert payload == {"equivalent_moves": {"dd": ["pq"]}}


def test_lookup_loader_runtime_override_rejects_source_path_keyed_mapping():
    wrong_shape_mapping = {
        "tests/sgf_engine/data/gold_fixtures/431.sgf": {
            "puzzle_id": "gf-003",
            "puzzle_version_id": "2026-06-30-gf-003",
            "sgf_sha256": GF_003_DISABLED_RECORD["sgf_sha256"],
            "equivalent_moves": {"sf": ["sd"]},
            "runtime_status": RUNTIME_DISABLED,
            "apply_automatically": False,
        }
    }

    with pytest.raises(ValueError, match="must be a list"):
        lookup_loader_runtime_override(
            wrong_shape_mapping,
            puzzle_id="gf-003",
            puzzle_version_id="2026-06-30-gf-003",
            sgf_sha256=GF_003_DISABLED_RECORD["sgf_sha256"],
        )


def test_lookup_loader_runtime_override_uses_canonical_identity_only():
    records = [
        {
            "puzzle_id": "gf-101",
            "puzzle_version_id": "v1",
            "sgf_sha256": "A" * 64,
            "equivalent_moves": {"dd": ["pq"]},
            "runtime_status": RUNTIME_ENABLED,
            "apply_automatically": True,
            "source_path": "SGF/shared/101.sgf",
            "gold_fixture_id": "GF-ALIAS",
        },
        {
            "puzzle_id": "gf-102",
            "puzzle_version_id": "v2",
            "sgf_sha256": "B" * 64,
            "equivalent_moves": {"pp": ["qq"]},
            "runtime_status": RUNTIME_ENABLED,
            "apply_automatically": True,
            "source_path": "SGF/shared/101.sgf",
            "gold_fixture_id": "GF-ALIAS",
        },
    ]

    payload = lookup_loader_runtime_override(
        records,
        puzzle_id="gf-102",
        puzzle_version_id="v2",
        sgf_sha256="b" * 64,
    )

    assert payload == {"equivalent_moves": {"pp": ["qq"]}}
    assert (
        lookup_loader_runtime_override(
            records,
            puzzle_id="SGF/shared/101.sgf",
            puzzle_version_id="v2",
            sgf_sha256="b" * 64,
        )
        is None
    )
    assert (
        lookup_loader_runtime_override(
            records,
            puzzle_id="GF-ALIAS",
            puzzle_version_id="v2",
            sgf_sha256="b" * 64,
        )
        is None
    )


def test_lookup_loader_runtime_override_rejects_hash_mismatch():
    payload = lookup_loader_runtime_override(
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


def test_lookup_loader_runtime_override_ignores_disabled_records():
    payload = lookup_loader_runtime_override(
        [GF_003_DISABLED_RECORD],
        puzzle_id="gf-003",
        puzzle_version_id="2026-06-30-gf-003",
        sgf_sha256=GF_003_DISABLED_RECORD["sgf_sha256"],
    )

    assert payload is None


def test_lookup_loader_runtime_override_requires_apply_automatically():
    payload = lookup_loader_runtime_override(
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


def test_lookup_loader_runtime_override_does_not_treat_arbitrary_mapping_as_index():
    arbitrary_mapping = {
        ("gf-101", "v1"): {
            "puzzle_id": "gf-101",
            "puzzle_version_id": "v1",
            "sgf_sha256": "A" * 64,
            "equivalent_moves": {"dd": ["pq", "qp"]},
            "runtime_status": RUNTIME_ENABLED,
            "apply_automatically": True,
        }
    }

    with pytest.raises(ValueError, match="must be a list"):
        lookup_loader_runtime_override(
            arbitrary_mapping,
            puzzle_id="gf-101",
            puzzle_version_id="v1",
            sgf_sha256="a" * 64,
        )
