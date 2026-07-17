from __future__ import annotations

from contextlib import nullcontext
import json
import sqlite3
import uuid

import pytest

from migrations.puzzle_identity_alias_v1 import (
    DestructiveMigrationRefused,
    downgrade,
    upgrade,
)
from puzzle_identity import resolve_puzzle_identity
from tools.puzzle_identity_backfill import (
    backfill_missing_aliases,
    build_parser,
    deterministic_snapshot_bytes,
    run,
)


UUID_A = "00000000-0000-4000-8000-000000000001"
UUID_B = "00000000-0000-4000-9000-000000000002"
UUID_C = "00000000-0000-4000-a000-000000000003"


@pytest.fixture()
def connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    upgrade(conn)
    try:
        yield conn
    finally:
        conn.close()


def _insert_alias(conn, record_index, legacy_question_id, canonical_puzzle_id):
    conn.execute(
        """
        INSERT INTO puzzle_identity_alias
            (record_index, legacy_question_id, canonical_puzzle_id)
        VALUES (?, ?, ?)
        """,
        (record_index, legacy_question_id, canonical_puzzle_id),
    )
    conn.commit()


def _factory(conn):
    return lambda: nullcontext(conn)


def test_a_composite_alias_key_is_unique(connection):
    _insert_alias(connection, 17, 70450, UUID_A)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO puzzle_identity_alias
                (record_index, legacy_question_id, canonical_puzzle_id)
            VALUES (?, ?, ?)
            """,
            (17, 70450, UUID_B),
        )


def test_b_canonical_uuid_is_unique(connection):
    _insert_alias(connection, 17, 70450, UUID_A)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO puzzle_identity_alias
                (record_index, legacy_question_id, canonical_puzzle_id)
            VALUES (?, ?, ?)
            """,
            (18, 63382, UUID_A),
        )


def test_c_duplicate_legacy_ids_get_distinct_uuid4_values(connection):
    generated = iter(
        [
            uuid.UUID(UUID_A),
            uuid.UUID(UUID_B),
        ]
    )
    result = backfill_missing_aliases(
        connection,
        [(17, 70450), (91, 70450)],
        uuid_factory=lambda: next(generated),
    )
    connection.commit()

    rows = connection.execute(
        """
        SELECT record_index, canonical_puzzle_id
          FROM puzzle_identity_alias
         WHERE legacy_question_id=?
         ORDER BY record_index
        """,
        (70450,),
    ).fetchall()
    assert result == {"source_records": 2, "inserted": 2, "preserved": 0}
    assert [(row[0], row[1]) for row in rows] == [(17, UUID_A), (91, UUID_B)]


def test_d_exact_composite_resolver_returns_only_the_matching_uuid(connection):
    _insert_alias(connection, 17, 70450, UUID_A)
    _insert_alias(connection, 91, 70450, UUID_B)

    resolution = resolve_puzzle_identity(
        _factory(connection),
        record_index=91,
        legacy_question_id=70450,
    )

    assert resolution.canonical_puzzle_id == UUID_B
    assert resolution.invalid_identity is False


def test_e_unique_legacy_id_fallback_resolves(connection):
    _insert_alias(connection, 22, 63382, UUID_A)

    resolution = resolve_puzzle_identity(
        _factory(connection),
        legacy_question_id=63382,
    )

    assert resolution.canonical_puzzle_id == UUID_A
    assert resolution.invalid_identity is False


def test_f_ambiguous_legacy_id_fallback_fails_closed(connection):
    _insert_alias(connection, 17, 71240, UUID_A)
    _insert_alias(connection, 91, 71240, UUID_B)

    resolution = resolve_puzzle_identity(
        _factory(connection),
        legacy_question_id=71240,
    )

    assert resolution.canonical_puzzle_id is None
    assert resolution.invalid_identity is True


def test_g_missing_alias_fails_closed(connection):
    resolution = resolve_puzzle_identity(
        _factory(connection),
        record_index=404,
        legacy_question_id=62011,
    )

    assert resolution.canonical_puzzle_id is None
    assert resolution.invalid_identity is True


def test_h_unknown_request_lookup_performs_no_writes(connection):
    statements = []
    connection.set_trace_callback(statements.append)
    try:
        resolution = resolve_puzzle_identity(
            _factory(connection),
            record_index=404,
            legacy_question_id=71238,
        )
    finally:
        connection.set_trace_callback(None)

    normalized = [statement.lstrip().upper() for statement in statements]
    assert resolution.canonical_puzzle_id is None
    assert resolution.invalid_identity is True
    assert any(statement.startswith("SELECT") for statement in normalized)
    assert not any(
        statement.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))
        for statement in normalized
    )
    assert connection.execute(
        "SELECT COUNT(*) FROM puzzle_identity_alias"
    ).fetchone()[0] == 0


def test_i_repeated_backfill_preserves_mapping_bytes(connection):
    records = [(0, 70450), (1, 63382), (2, 70450)]
    generated = iter(
        [
            uuid.UUID(UUID_A),
            uuid.UUID(UUID_B),
            uuid.UUID(UUID_C),
        ]
    )

    first_result = backfill_missing_aliases(
        connection,
        records,
        uuid_factory=lambda: next(generated),
    )
    connection.commit()
    first_snapshot = deterministic_snapshot_bytes(connection)

    second_result = backfill_missing_aliases(
        connection,
        records,
        uuid_factory=lambda: pytest.fail("existing mappings must not regenerate UUIDs"),
    )
    connection.commit()
    second_snapshot = deterministic_snapshot_bytes(connection)

    assert first_result == {"source_records": 3, "inserted": 3, "preserved": 0}
    assert second_result == {"source_records": 3, "inserted": 0, "preserved": 3}
    assert second_snapshot == first_snapshot


def test_local_test_command_is_idempotent_with_synthetic_input(tmp_path):
    input_path = tmp_path / "synthetic_questions.json"
    database_path = tmp_path / "identity.sqlite3"
    snapshot_path = tmp_path / "identity.snapshot.json"
    input_path.write_text(
        json.dumps([{"id": 70450}, {"id": 63382}, {"id": 70450}]),
        encoding="utf-8",
    )
    parser = build_parser()
    args = parser.parse_args(
        [
            "--scope",
            "local-test",
            "--ephemeral-root",
            str(tmp_path),
            "--input",
            input_path.name,
            "--database",
            database_path.name,
            "--snapshot-output",
            snapshot_path.name,
        ]
    )

    first = run(args)
    first_bytes = snapshot_path.read_bytes()
    second = run(args)

    assert first["source_records"] == 3
    assert first["inserted"] == 3
    assert first["preserved"] == 0
    assert second["source_records"] == 3
    assert second["inserted"] == 0
    assert second["preserved"] == 3
    assert second["snapshot_sha256"] == first["snapshot_sha256"]
    assert snapshot_path.read_bytes() == first_bytes


def test_backfill_command_rejects_non_local_scope_and_paths_outside_root(tmp_path):
    ephemeral_root = tmp_path / "ephemeral"
    ephemeral_root.mkdir()
    outside_input = tmp_path / "outside.json"
    outside_input.write_text("[]", encoding="utf-8")
    parser = build_parser()

    wrong_scope = parser.parse_args(
        [
            "--scope",
            "production",
            "--ephemeral-root",
            str(ephemeral_root),
            "--input",
            str(outside_input),
            "--database",
            "identity.sqlite3",
        ]
    )
    with pytest.raises(ValueError, match="local-test"):
        run(wrong_scope)

    outside_path = parser.parse_args(
        [
            "--scope",
            "local-test",
            "--ephemeral-root",
            str(ephemeral_root),
            "--input",
            str(outside_input),
            "--database",
            "identity.sqlite3",
        ]
    )
    with pytest.raises(ValueError, match="remain under"):
        run(outside_path)


def test_j_normal_rollback_preserves_alias_table_and_mapping(tmp_path):
    database_path = tmp_path / "identity.sqlite3"
    connection = sqlite3.connect(database_path)
    upgrade(connection)
    _insert_alias(connection, 17, 70450, UUID_A)

    connection.execute("BEGIN")
    connection.execute(
        """
        INSERT INTO puzzle_identity_alias
            (record_index, legacy_question_id, canonical_puzzle_id)
        VALUES (?, ?, ?)
        """,
        (18, 63382, UUID_B),
    )
    connection.rollback()

    with pytest.raises(DestructiveMigrationRefused):
        downgrade(connection)
    connection.close()

    reopened = sqlite3.connect(database_path)
    try:
        rows = reopened.execute(
            """
            SELECT record_index, legacy_question_id, canonical_puzzle_id
              FROM puzzle_identity_alias
            """
        ).fetchall()
    finally:
        reopened.close()

    assert rows == [(17, 70450, UUID_A)]


def test_uuid_constraint_accepts_only_lowercase_rfc4122_uuid4(connection):
    invalid_values = [
        "00000000-0000-3000-8000-000000000001",
        "00000000-0000-4000-7000-000000000001",
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa".upper(),
        "00000000-0000-4000-8000-00000000-001",
        "not-a-uuid",
    ]

    for record_index, value in enumerate(invalid_values):
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO puzzle_identity_alias
                    (record_index, legacy_question_id, canonical_puzzle_id)
                VALUES (?, ?, ?)
                """,
                (record_index, 1000 + record_index, value),
            )


def test_destructive_down_requires_exact_boolean_true(connection):
    with pytest.raises(DestructiveMigrationRefused):
        downgrade(connection, allow_destructive=1)

    downgrade(connection, allow_destructive=True)
    table = connection.execute(
        """
        SELECT name FROM sqlite_master
         WHERE type='table' AND name='puzzle_identity_alias'
        """
    ).fetchone()
    assert table is None
