"""G110: explicit, versioned PostgreSQL16 additive Step Ledger migration.

This module NEVER chooses a database, never runs at startup, never commits
or rolls back and never drops player records. Caller must supply an authorized
transaction/connection and a separate Owner DDL gate for production usage.

Scope: the original G076 map-battle step ledger only; G076 nonmap/mistakes,
other migrations and formal production upgrade are independent gates.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

VERSION = "g110_step_ledger_atomic_v1"
APPROVAL_FLAG = "G110_STEP_LEDGER_MIGRATION_APPROVED"
EXPECTED_SQL_SHA256 = "bb897a7e1275209f2160965bc6dd98b265581ebde00d1e6be4dceaf05c030251"
REGISTRY = "g110_schema_migrations"
STEP_TABLES = ("g076_step_sessions", "g076_step_events")
REQUIRED_CONSTRAINTS = {
    "g076_step_sessions": {
        "g076_step_sessions_pkey",
        "g076_step_sessions_state_ck",
        "g076_step_sessions_index_ck",
        "g076_step_sessions_history_ck",
        "g076_step_sessions_revision_ck",
        "g076_step_sessions_owner_attempt_fk",
    },
    "g076_step_events": {
        "g076_step_events_pk",
        "g076_step_events_step_ck",
        "g076_step_events_hash_ck",
        "g076_step_events_response_ck",
        "g076_step_events_attempt_fk",
    },
}


class G110MigrationRejected(RuntimeError):
    """Fail closed. The caller owns transaction rollback."""


def _fetchone(conn, query, params=()):
    cursor = conn.execute(query, params)
    row = cursor.fetchone()
    return tuple(row) if row is not None else None


def _fetchall(conn, query, params=()):
    return [tuple(r) for r in conn.execute(query, params).fetchall()]


def _exists(conn, name):
    row = _fetchone(conn, "SELECT to_regclass(?)::text", ("public." + name,))
    return row is not None and row[0] is not None


def _check_server(conn):
    row = _fetchone(conn, "SELECT current_setting('server_version_num'), current_schema()")
    if not row or not (160000 <= int(row[0]) < 180000) or row[1] != "public":
        raise G110MigrationRejected("requires PostgreSQL 16/17 in public schema")


def _check_parent(conn):
    if not _exists(conn, "map_battle_attempts"):
        raise G110MigrationRejected("map_battle_attempts missing")
    cols = _fetchall(conn, """
        SELECT column_name, data_type, is_nullable
          FROM information_schema.columns
         WHERE table_schema='public' AND table_name='map_battle_attempts'
           AND column_name IN ('user_id','battle_id','id')
    """)
    expected = {
        ("user_id", "integer", "NO"),
        ("battle_id", "text", "NO"),
        ("id", "text", "NO"),
    }
    if set(cols) != expected:
        raise G110MigrationRejected("parent key type or nullability drift")
    unique = _fetchall(conn, """
        SELECT c.contype, pg_get_constraintdef(c.oid)
          FROM pg_constraint c
          JOIN pg_class r ON c.conrelid=r.oid
          JOIN pg_namespace n ON n.oid=r.relnamespace
         WHERE n.nspname='public' AND r.relname='map_battle_attempts'
           AND c.contype IN ('u','p')
    """)
    if not any(kind in ("u", "p") and definition == "UNIQUE (user_id, battle_id, id)"
               for kind, definition in unique):
        raise G110MigrationRejected("missing composite owner/battle/attempt unique key")


def _source_sql():
    path = Path(__file__).with_name("g110_step_ledger_atomic_v1.sql")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != EXPECTED_SQL_SHA256:
        raise G110MigrationRejected("fixed Step Ledger SQL source hash mismatch")
    text = payload.decode("utf-8")
    # The proposal has no executed transaction statements and cannot truncate rows.
    statements = [
        line.strip().upper() for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("--")
    ]
    if any(x.startswith(("BEGIN;", "COMMIT;", "ROLLBACK;", "DROP ", "TRUNCATE "))
           for x in statements):
        raise G110MigrationRejected("unsafe SQL transaction or destructive DDL")
    return text


def _catalog(conn):
    if not all(_exists(conn, name) for name in STEP_TABLES):
        raise G110MigrationRejected("Step Ledger schema absent")
    rows = []
    for table in STEP_TABLES:
        columns = _fetchall(conn, """
            SELECT column_name, data_type, is_nullable, column_default
              FROM information_schema.columns
             WHERE table_schema='public' AND table_name=?
             ORDER BY ordinal_position
        """, (table,))
        constraints = _fetchall(conn, """
            SELECT c.conname, c.contype, pg_get_constraintdef(c.oid)
              FROM pg_constraint c
              JOIN pg_class r ON r.oid=c.conrelid
              JOIN pg_namespace n ON n.oid=r.relnamespace
             WHERE n.nspname='public' AND r.relname=? ORDER BY c.conname
        """, (table,))
        got = {row[0] for row in constraints}
        if got != REQUIRED_CONSTRAINTS[table]:
            raise G110MigrationRejected("Step Ledger named constraint drift: " + table)
        indexes = _fetchall(conn, """
            SELECT indexname, indexdef
              FROM pg_indexes WHERE schemaname='public'
                AND tablename=? ORDER BY indexname
        """, (table,))
        if table == "g076_step_sessions":
            if "idx_g076_step_sessions_owner_battle" not in {x[0] for x in indexes}:
                raise G110MigrationRejected("Step Ledger owner index missing")
        rows.append([table, columns, constraints, indexes])
    return hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()


def _verify_registry(conn):
    columns = _fetchall(conn, """
        SELECT column_name, data_type, is_nullable
          FROM information_schema.columns
         WHERE table_schema='public' AND table_name=?
         ORDER BY ordinal_position
    """, (REGISTRY,))
    expected = [
        ("version", "text", "NO"),
        ("sql_sha256", "text", "NO"),
        ("schema_sha256", "text", "NO"),
        ("applied_at", "timestamp with time zone", "NO"),
    ]
    if columns != expected:
        raise G110MigrationRejected("migration registry column drift")
    constraints = _fetchall(conn, """
        SELECT c.contype, pg_get_constraintdef(c.oid)
          FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid
          JOIN pg_namespace n ON n.oid=r.relnamespace
         WHERE n.nspname='public' AND r.relname=?
    """, (REGISTRY,))
    if ("p", "PRIMARY KEY (version)") not in constraints:
        raise G110MigrationRejected("migration registry primary key missing")


def upgrade(conn, *, environ):
    """Apply or verify exact migration inside caller's transaction, WITHOUT COMMIT.

    Success requires the caller to commit. On failure caller MUST roll back.
    Feature flags are separate: running a migration never enables player routes.
    """
    if environ.get(APPROVAL_FLAG) != "1":
        raise G110MigrationRejected("explicit owner-authorized migration flag required")
    _check_server(conn)
    source = _source_sql()
    # Transaction-scoped admission lock; caller is responsible for commit/rollback.
    conn.execute("SELECT pg_advisory_xact_lock(110076)")
    _check_parent(conn)

    if _exists(conn, REGISTRY):
        _verify_registry(conn)
        marker = _fetchall(conn, "SELECT version,sql_sha256,schema_sha256 FROM g110_schema_migrations")
        if len(marker) != 1 or marker[0][:2] != (VERSION, EXPECTED_SQL_SHA256):
            raise G110MigrationRejected("migration version or code hash mismatch")
        if marker[0][2] != _catalog(conn):
            raise G110MigrationRejected("deployed Step Ledger catalog drift")
        return {"status": "ALREADY_APPLIED_VERIFIED", "version": VERSION}

    if any(_exists(conn, x) for x in STEP_TABLES):
        raise G110MigrationRejected("untracked Step Ledger schema: manual reconciliation")
    if _exists(conn, "idx_g076_step_sessions_owner_battle"):
        raise G110MigrationRejected("untracked Step Ledger index")

    conn.execute(source)
    signature = _catalog(conn)
    conn.execute("""
        CREATE TABLE g110_schema_migrations (
            version TEXT PRIMARY KEY,
            sql_sha256 TEXT NOT NULL CHECK (length(sql_sha256) = 64),
            schema_sha256 TEXT NOT NULL CHECK (length(schema_sha256) = 64),
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        INSERT INTO g110_schema_migrations (version, sql_sha256, schema_sha256)
        VALUES (?, ?, ?)
    """, (VERSION, EXPECTED_SQL_SHA256, signature))
    return {"status": "APPLIED_PENDING_CALLER_COMMIT", "version": VERSION}


def downgrade(*, environ):
    """Data-preserving old-runtime rollback policy, NOT destructive DDL."""
    if environ.get("G076_STEP_RUNTIME_ENABLED", "").lower() not in ("", "off", "false", "0"):
        raise G110MigrationRejected("disable Step Runtime first")
    return {
        "status": "KEEP_ADDITIVE_SCHEMA_FOR_AUDIT",
        "no_ddl": True,
        "no_player_data_delete": True,
        "version": VERSION,
    }
