from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID

import pytest

from tests.sgf_engine._phase14_canonical_identity_spike import (
    CanonicalPuzzleIdentityInput,
    assign_canonical_puzzle_ids,
)
from tests.sgf_engine._phase15a_sqlite_persistence_spike import (
    DEPENDENCY_DECISION,
    PERSISTENCE_POLICY,
    create_memory_connection,
    fetch_review_items_for_puzzle,
    initialize_schema,
    insert_canonical_puzzle,
    insert_review_queue_item,
)


UUID_A = "3a288da5-054f-4fd7-b84a-11e759a7375f"
UUID_B = "b5c48e47-8f95-481b-888f-43825d38c13c"
INVALID_CANONICAL_IDS = [
    "431.sgf",
    "GF-003",
    "source/path/431.sgf",
    "fixtures/gold/GF-003.json",
    "0713176F21C7A23133014A5956D935311B9AA8AA5A483A87CCF8100FEA5C7D29",
]


@pytest.fixture
def connection() -> sqlite3.Connection:
    database = create_memory_connection()
    initialize_schema(database)
    try:
        yield database
    finally:
        database.close()


def test_dependency_decision_is_documented() -> None:
    assert "SQLAlchemy ORM persistence spike is deferred" in DEPENDENCY_DECISION
    assert "SQLAlchemy is not an existing dependency" in DEPENDENCY_DECISION
    assert "Python stdlib sqlite3 only" in DEPENDENCY_DECISION
    assert "does not introduce or imply a production DB stack decision" in (
        DEPENDENCY_DECISION
    )


def test_connection_is_in_memory_with_foreign_keys_enabled() -> None:
    database = create_memory_connection()
    try:
        database_list = database.execute("PRAGMA database_list").fetchall()
        assert database_list == [(0, "main", "")]
        assert database.execute("PRAGMA foreign_keys").fetchone() == (1,)
    finally:
        database.close()


def test_insert_and_read_canonical_puzzle(
    connection: sqlite3.Connection,
) -> None:
    insert_canonical_puzzle(connection, UUID_A)

    row = connection.execute(
        "SELECT id, created_at FROM canonical_puzzles WHERE id = ?",
        (UUID_A,),
    ).fetchone()

    assert row is not None
    assert row[0] == UUID_A
    assert row[1]
    assert UUID(row[0]).version == 4


def test_insert_and_read_related_review_queue_item(
    connection: sqlite3.Connection,
) -> None:
    insert_canonical_puzzle(connection, UUID_A)
    insert_review_queue_item(
        connection,
        item_id="review-001",
        canonical_puzzle_id=UUID_A,
        status="candidate_only",
    )

    rows = fetch_review_items_for_puzzle(connection, UUID_A)

    assert len(rows) == 1
    assert dict(rows[0])["id"] == "review-001"
    assert dict(rows[0])["canonical_puzzle_id"] == UUID_A
    assert dict(rows[0])["status"] == "candidate_only"


def test_orphan_review_queue_item_is_rejected(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        insert_review_queue_item(
            connection,
            item_id="orphan-review",
            canonical_puzzle_id=UUID_A,
            status="needs_owner_decision",
        )


def test_duplicate_canonical_puzzle_id_is_rejected(
    connection: sqlite3.Connection,
) -> None:
    insert_canonical_puzzle(connection, UUID_A)

    with pytest.raises(sqlite3.IntegrityError):
        insert_canonical_puzzle(connection, UUID_A)


def test_duplicate_review_queue_item_id_is_rejected(
    connection: sqlite3.Connection,
) -> None:
    insert_canonical_puzzle(connection, UUID_A)
    insert_canonical_puzzle(connection, UUID_B)
    insert_review_queue_item(
        connection,
        item_id="review-001",
        canonical_puzzle_id=UUID_A,
        status="candidate_only",
    )

    with pytest.raises(sqlite3.IntegrityError):
        insert_review_queue_item(
            connection,
            item_id="review-001",
            canonical_puzzle_id=UUID_B,
            status="ready_readonly",
        )


@pytest.mark.parametrize("invalid_id", INVALID_CANONICAL_IDS)
def test_invalid_canonical_puzzle_id_is_rejected_before_insert(
    connection: sqlite3.Connection,
    invalid_id: str,
) -> None:
    with pytest.raises(ValueError, match="UUID v4 string"):
        insert_canonical_puzzle(connection, invalid_id)

    assert connection.execute(
        "SELECT COUNT(*) FROM canonical_puzzles"
    ).fetchone() == (0,)


def test_phase14_uuid_assignment_output_can_be_inserted(
    connection: sqlite3.Connection,
) -> None:
    mapping = assign_canonical_puzzle_ids(
        [CanonicalPuzzleIdentityInput(record_key="ingestion-row-431")],
        uuid_factory=lambda: UUID(UUID_A),
    )

    insert_canonical_puzzle(connection, mapping["ingestion-row-431"])

    assert connection.execute(
        "SELECT id FROM canonical_puzzles"
    ).fetchone() == (UUID_A,)


@pytest.mark.parametrize(
    "metadata_identity",
    [
        "431.sgf",
        "GF-003",
        "source/path/431.sgf",
        "fixtures/gold/GF-003.json",
    ],
)
def test_metadata_is_not_accepted_as_canonical_identity(
    connection: sqlite3.Connection,
    metadata_identity: str,
) -> None:
    with pytest.raises(ValueError, match="UUID v4 string"):
        insert_canonical_puzzle(connection, metadata_identity)


def test_no_physical_database_file_is_created(
    connection: sqlite3.Connection,
) -> None:
    database_list = connection.execute("PRAGMA database_list").fetchall()

    assert database_list == [(0, "main", "")]
    assert not list(Path(__file__).parents[2].glob("*.db"))


def test_delete_is_restricted_without_implying_production_policy(
    connection: sqlite3.Connection,
) -> None:
    insert_canonical_puzzle(connection, UUID_A)
    insert_review_queue_item(
        connection,
        item_id="review-001",
        canonical_puzzle_id=UUID_A,
        status="candidate_only",
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "DELETE FROM canonical_puzzles WHERE id = ?",
            (UUID_A,),
        )

    assert "test-local SQLite stdlib persistence contract spike" in (
        PERSISTENCE_POLICY
    )
    assert "does not define the final production DB engine" in PERSISTENCE_POLICY
    assert "cascade, or deletion policy" in PERSISTENCE_POLICY
