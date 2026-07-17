"""Additive migration for the canonical puzzle identity alias table.

This module is deliberately not registered with application startup. Importing
it performs no database access. ``upgrade`` must be invoked by an explicitly
authorized migration/backfill operation. ``downgrade`` is destructive and
refuses to run unless its caller passes the exact boolean ``True``.

The statements use the small SQL subset shared by SQLite (for disposable test
databases) and PostgreSQL through this repository's DB-API wrapper.
"""

from __future__ import annotations


TABLE_NAME = "puzzle_identity_alias"
LEGACY_INDEX_NAME = "idx_puzzle_identity_alias_legacy_question_id"


class DestructiveMigrationRefused(RuntimeError):
    """Raised when a caller attempts the destructive down migration by default."""


def _uuid_hex_remainder_sql(column_name: str) -> str:
    """Return portable SQL that removes every valid UUID character.

    Combined with the length, hyphen-position, version, and variant checks in
    ``CREATE_TABLE_SQL``, an empty remainder proves the other characters are
    hexadecimal. ``LOWER``, ``REPLACE``, ``LENGTH``, and ``SUBSTR`` have the
    same forms in SQLite and PostgreSQL.
    """

    expression = f"LOWER({column_name})"
    for character in "0123456789abcdef-":
        expression = f"REPLACE({expression}, '{character}', '')"
    return expression


_UUID_REMAINDER_SQL = _uuid_hex_remainder_sql("canonical_puzzle_id")

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    record_index INTEGER NOT NULL
        CHECK (record_index >= 0),
    legacy_question_id INTEGER NOT NULL,
    canonical_puzzle_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_puzzle_identity_alias
        PRIMARY KEY (record_index, legacy_question_id),
    CONSTRAINT uq_puzzle_identity_alias_canonical
        UNIQUE (canonical_puzzle_id),
    CONSTRAINT ck_puzzle_identity_alias_uuid_v4
        CHECK (
            canonical_puzzle_id = LOWER(canonical_puzzle_id)
            AND LENGTH(canonical_puzzle_id) = 36
            AND SUBSTR(canonical_puzzle_id, 9, 1) = '-'
            AND SUBSTR(canonical_puzzle_id, 14, 1) = '-'
            AND SUBSTR(canonical_puzzle_id, 19, 1) = '-'
            AND SUBSTR(canonical_puzzle_id, 24, 1) = '-'
            AND SUBSTR(canonical_puzzle_id, 15, 1) = '4'
            AND SUBSTR(canonical_puzzle_id, 20, 1) IN ('8', '9', 'a', 'b')
            AND LENGTH(canonical_puzzle_id)
                - LENGTH(REPLACE(canonical_puzzle_id, '-', '')) = 4
            AND LENGTH({_UUID_REMAINDER_SQL}) = 0
        )
)
""".strip()

CREATE_LEGACY_INDEX_SQL = f"""
CREATE INDEX IF NOT EXISTS {LEGACY_INDEX_NAME}
ON {TABLE_NAME} (legacy_question_id)
""".strip()

DROP_LEGACY_INDEX_SQL = f"DROP INDEX IF EXISTS {LEGACY_INDEX_NAME}"
DROP_TABLE_SQL = f"DROP TABLE IF EXISTS {TABLE_NAME}"


def _rollback_quietly(conn) -> None:
    try:
        conn.rollback()
    except Exception:
        # Preserve the original migration exception. A broken connection may
        # also reject rollback, but that secondary failure is not actionable.
        pass


def upgrade(conn) -> None:
    """Create the additive alias table and non-unique diagnostic index.

    The caller supplies an isolated DB-API-compatible connection. Existing
    rows are never read, updated, or deleted by this migration.
    """

    try:
        conn.execute(CREATE_TABLE_SQL)
        conn.execute(CREATE_LEGACY_INDEX_SQL)
        conn.commit()
    except Exception:
        _rollback_quietly(conn)
        raise


def downgrade(conn, *, allow_destructive: bool = False) -> None:
    """Drop the alias table only after an explicit destructive opt-in.

    This function is not a normal application rollback mechanism. The strict
    identity check intentionally rejects truthy non-booleans such as ``1``.
    """

    if allow_destructive is not True:
        raise DestructiveMigrationRefused(
            "puzzle_identity_alias downgrade is destructive; "
            "normal application rollback must preserve canonical mappings"
        )

    try:
        conn.execute(DROP_LEGACY_INDEX_SQL)
        conn.execute(DROP_TABLE_SQL)
        conn.commit()
    except Exception:
        _rollback_quietly(conn)
        raise
