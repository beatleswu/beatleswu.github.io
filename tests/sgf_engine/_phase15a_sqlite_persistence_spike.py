"""Test-local SQLite stdlib persistence contract helpers.

This module has no production runtime integration.
"""

from __future__ import annotations

import datetime
import sqlite3
import uuid


DEPENDENCY_DECISION = (
    "SQLAlchemy ORM persistence spike is deferred because SQLAlchemy is not "
    "an existing dependency.\n"
    "Phase 15A uses Python stdlib sqlite3 only.\n"
    "This does not introduce or imply a production DB stack decision."
)

PERSISTENCE_POLICY = (
    "This is a test-local SQLite stdlib persistence contract spike.\n"
    "It does not define the final production DB engine, ORM, migration, "
    "cascade, or deletion policy."
)


def create_memory_connection() -> sqlite3.Connection:
    """Create an isolated SQLite in-memory connection with FK checks enabled."""

    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Initialize the test-local schema.

    This is a test-local SQLite stdlib persistence contract spike.
    It does not define the final production DB engine, ORM, migration,
    cascade, or deletion policy.
    """

    connection.executescript(
        """
        CREATE TABLE canonical_puzzles (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        );

        CREATE TABLE review_queue_items (
            id TEXT PRIMARY KEY,
            canonical_puzzle_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (canonical_puzzle_id)
                REFERENCES canonical_puzzles(id)
                ON DELETE RESTRICT
        );
        """
    )


def _validated_uuid4(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("canonical_puzzle_id must be a UUID v4 string")

    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("canonical_puzzle_id must be a UUID v4 string") from exc

    if parsed.version != 4:
        raise ValueError("canonical_puzzle_id must be a UUID v4 string")

    return str(parsed)


def _created_at() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def insert_canonical_puzzle(
    connection: sqlite3.Connection,
    canonical_puzzle_id: str,
) -> None:
    """Validate and insert one canonical puzzle."""

    validated_id = _validated_uuid4(canonical_puzzle_id)
    connection.execute(
        "INSERT INTO canonical_puzzles (id, created_at) VALUES (?, ?)",
        (validated_id, _created_at()),
    )


def insert_review_queue_item(
    connection: sqlite3.Connection,
    item_id: str,
    canonical_puzzle_id: str,
    status: str,
) -> None:
    """Validate canonical identity and insert one related review queue item."""

    validated_id = _validated_uuid4(canonical_puzzle_id)
    connection.execute(
        """
        INSERT INTO review_queue_items (
            id,
            canonical_puzzle_id,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (item_id, validated_id, status, _created_at()),
    )


def fetch_review_items_for_puzzle(
    connection: sqlite3.Connection,
    canonical_puzzle_id: str,
) -> list[sqlite3.Row]:
    """Fetch review items belonging to a validated canonical identity."""

    validated_id = _validated_uuid4(canonical_puzzle_id)
    previous_row_factory = connection.row_factory
    try:
        connection.row_factory = sqlite3.Row
        return list(
            connection.execute(
                """
                SELECT id, canonical_puzzle_id, status, created_at
                FROM review_queue_items
                WHERE canonical_puzzle_id = ?
                ORDER BY id
                """,
                (validated_id,),
            )
        )
    finally:
        connection.row_factory = previous_row_factory
