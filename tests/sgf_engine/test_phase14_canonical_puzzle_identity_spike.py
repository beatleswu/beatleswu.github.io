from pathlib import Path
from uuid import UUID

import pytest

from tests.sgf_engine._phase14_canonical_identity_spike import (
    CanonicalPuzzleIdentityInput,
    assign_canonical_puzzle_ids,
    dump_identity_mapping,
    load_identity_mapping,
)


UUID_A = UUID("3a288da5-054f-4fd7-b84a-11e759a7375f")
UUID_B = UUID("b5c48e47-8f95-481b-888f-43825d38c13c")


def test_new_records_receive_unique_uuid_v4_ids() -> None:
    records = [
        CanonicalPuzzleIdentityInput(
            record_key="ingestion-row-431",
            source_path="source/path/431.sgf",
            fixture_path="fixtures.json",
            gold_fixture_id="GF-003",
            content_sha256=(
                "0713176F21C7A23133014A5956D935311B9AA8AA5A483A87CCF8100FEA5C7D29"
            ),
        ),
        CanonicalPuzzleIdentityInput(record_key="ingestion-row-432"),
    ]

    mapping = assign_canonical_puzzle_ids(records)

    assert set(mapping) == {"ingestion-row-431", "ingestion-row-432"}
    assert len(set(mapping.values())) == 2
    assert all(UUID(value).version == 4 for value in mapping.values())
    assert mapping["ingestion-row-431"] not in {
        records[0].record_key,
        records[0].source_path,
        records[0].fixture_path,
        records[0].gold_fixture_id,
        records[0].content_sha256,
    }


def test_existing_mapping_is_preserved_without_calling_uuid_factory() -> None:
    def unexpected_uuid_factory() -> UUID:
        raise AssertionError("uuid_factory must not run for an existing record")

    mapping = assign_canonical_puzzle_ids(
        [CanonicalPuzzleIdentityInput(record_key="stable-row")],
        existing_mapping={"stable-row": str(UUID_A)},
        uuid_factory=unexpected_uuid_factory,
    )

    assert mapping == {"stable-row": str(UUID_A)}


def test_source_path_is_metadata_not_identity() -> None:
    original = assign_canonical_puzzle_ids(
        [
            CanonicalPuzzleIdentityInput(
                record_key="stable-row",
                source_path="old/path/431.sgf",
            )
        ],
        uuid_factory=lambda: UUID_A,
    )

    moved = assign_canonical_puzzle_ids(
        [
            CanonicalPuzzleIdentityInput(
                record_key="stable-row",
                source_path="new/path/431.sgf",
            )
        ],
        existing_mapping=original,
    )

    assert moved["stable-row"] == original["stable-row"]


@pytest.mark.parametrize(
    ("field_name", "old_value", "new_value"),
    [
        ("fixture_path", "old/fixtures.json", "new/fixtures.json"),
        ("gold_fixture_id", "GF-003", "GF-999"),
        ("content_sha256", "a" * 64, "b" * 64),
    ],
)
def test_fixture_and_content_metadata_are_not_identity(
    field_name: str,
    old_value: str,
    new_value: str,
) -> None:
    original_record = CanonicalPuzzleIdentityInput(
        record_key="stable-row",
        **{field_name: old_value},
    )
    changed_record = CanonicalPuzzleIdentityInput(
        record_key="stable-row",
        **{field_name: new_value},
    )
    original = assign_canonical_puzzle_ids(
        [original_record],
        uuid_factory=lambda: UUID_A,
    )

    changed = assign_canonical_puzzle_ids(
        [changed_record],
        existing_mapping=original,
    )

    assert changed["stable-row"] == str(UUID_A)


def test_duplicate_record_keys_are_rejected() -> None:
    records = [
        CanonicalPuzzleIdentityInput(record_key="duplicate"),
        CanonicalPuzzleIdentityInput(
            record_key="duplicate",
            source_path="different/metadata/431.sgf",
        ),
    ]

    with pytest.raises(ValueError, match="duplicate record_key"):
        assign_canonical_puzzle_ids(records)


@pytest.mark.parametrize(
    "invalid_id",
    [
        "431.sgf",
        "GF-003",
        "source/path/431.sgf",
        "0713176F21C7A23133014A5956D935311B9AA8AA5A483A87CCF8100FEA5C7D29",
        "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    ],
)
def test_invalid_existing_canonical_ids_are_rejected(invalid_id: str) -> None:
    with pytest.raises(ValueError, match="valid UUID v4"):
        assign_canonical_puzzle_ids(
            [CanonicalPuzzleIdentityInput(record_key="stable-row")],
            existing_mapping={"stable-row": invalid_id},
        )


def test_duplicate_existing_canonical_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate canonical_puzzle_id"):
        assign_canonical_puzzle_ids(
            [],
            existing_mapping={
                "first-row": str(UUID_A),
                "second-row": str(UUID_A),
            },
        )


def test_duplicate_generated_canonical_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate canonical_puzzle_id"):
        assign_canonical_puzzle_ids(
            [
                CanonicalPuzzleIdentityInput(record_key="first-row"),
                CanonicalPuzzleIdentityInput(record_key="second-row"),
            ],
            uuid_factory=lambda: UUID_A,
        )


def test_json_persistence_round_trip_is_stable_utf8_and_lf_only(
    tmp_path: Path,
) -> None:
    path = tmp_path / "canonical-puzzle-identities.json"
    mapping = {
        "second-row": str(UUID_B),
        "first-row": str(UUID_A),
    }

    dump_identity_mapping(mapping, path)
    first_bytes = path.read_bytes()
    loaded = load_identity_mapping(path)
    dump_identity_mapping(loaded, path)

    assert loaded == mapping
    assert path.read_bytes() == first_bytes
    assert first_bytes.startswith(b"{")
    assert not first_bytes.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in first_bytes
    assert b"\n" in first_bytes
    assert first_bytes.index(b'"first-row"') < first_bytes.index(b'"second-row"')
