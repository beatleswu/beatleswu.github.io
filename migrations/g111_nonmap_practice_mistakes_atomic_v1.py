"""G111 scoped Nonmap/Practice/Mistakes PostgreSQL 16/17 migration candidate.

Explicit operator-only entry point, never called from product startup.
All DDL is strictly additive and owned by the caller's non-autocommit transaction.
Not authorized for Oracle, real players, or source-policy adoption.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

VERSION = "g111_nonmap_practice_mistakes_atomic_v1"
FLAG = "G111_NONMAP_MIGRATION_APPROVED"
REGISTRY = "g111_nonmap_schema_versions"
SQL_SHA256 = "284bd5b4e38c197009740978070443d96e59030139bbcc8bbf71f7942daece84"
TABLES = (
    "g076_nonmap_sessions",
    "g076_nonmap_events",
    "g076_practice_attempts",
    "g076_mistakes_attempts",
)
EXPECTED_CHECKS = {
    "g076_nonmap_sessions": {
        "g076_nonmap_sessions_pkey",
        "g076_nonmap_sessions_flow_check",
        "g076_nonmap_sessions_state_check",
    },
    "g076_nonmap_events": {
        "g076_nonmap_events_pkey",
        "g076_nonmap_events_session_id_fkey",
    },
    "g076_practice_attempts": {"g076_practice_attempts_pkey"},
    "g076_mistakes_attempts": {"g076_mistakes_attempts_pkey"},
}
# Historical migrations are mutually exclusive with a fresh bundle install.
# Pin their exact old contents to detect unreviewed schema prerequisite drift.
HISTORICAL_SHA256 = {
    "g076_nonmap_steps_PROPOSED.sql": "9ec041413fbfca17eeb709e3861ea7bbfebaf32320f8cfc2ed93b4deb349c702",
    "g076_mistakes_steps_PROPOSED.sql": "397fde858e113caac66772e9f2067203021431a3bab840fbc03b9f17b1d0e997",
    "g077_mistakes_flow_PROPOSED.sql": "b688acc5f53e6b4275d8ca705e5b1dd3fb690356361d6bb2e61d7b499bc5f828",
    "g076_practice_steps_v1.py": "44bc30e8f98e659b7edd045b6ba8a5148aa6c5b7af1b19d2e2630b14e57595b1",
    "g079_mistakes_steps_v1.py": "cdb1e2452d023fb20fb8a87061abe933b58df6d6a63445ef3b1e73af12aba715",
}


class G111MigrationRejected(RuntimeError):
    """Strict staging refusal; caller MUST rollback the transaction on failure."""


def _read(conn, query, values=()):
    cur = conn.execute(query, values)
    if cur.description:
        return [tuple(row) for row in cur.fetchall()]
    return []


def _present(conn, table):
    return _read(conn, "SELECT to_regclass(?)::text", ("public." + table,))[0][0] is not None


def _preflight(conn):
    raw = getattr(conn, "_conn", conn)
    if getattr(raw, "autocommit", None) is not False:
        raise G111MigrationRejected("requires managed non-autocommit PostgreSQL transaction")
    row = _read(conn, "SELECT current_setting('server_version_num'), current_schema()")
    if not row or not (160000 <= int(row[0][0]) < 180000) or row[0][1] != "public":
        raise G111MigrationRejected("requires PostgreSQL16/17 and public schema")
    folder = Path(__file__).parent
    for filename, expected in HISTORICAL_SHA256.items():
        if hashlib.sha256((folder / filename).read_bytes()).hexdigest() != expected:
            raise G111MigrationRejected("historical source drift: " + filename)


def _sql():
    raw = Path(__file__).with_name("g111_nonmap_practice_mistakes_atomic_v1.sql").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SQL_SHA256:
        raise G111MigrationRejected("G111 migration source hash mismatch")
    source = raw.decode("utf-8")
    lines = [line.strip().upper() for line in source.splitlines()
             if line.strip() and not line.lstrip().startswith("--")]
    if any(line.startswith(("BEGIN;", "COMMIT;", "ROLLBACK;", "DROP ", "TRUNCATE ",
                            "DELETE ", "ALTER TABLE", "CREATE TABLE IF NOT EXISTS"))
           for line in lines):
        raise G111MigrationRejected("unsafe migration DDL or implicit transaction")
    return source


def _catalog_signature(conn):
    schema = []
    for table in TABLES:
        if not _present(conn, table):
            raise G111MigrationRejected("missing G111 table: " + table)
        columns = _read(conn, """
          SELECT column_name,data_type,is_nullable,column_default
            FROM information_schema.columns
           WHERE table_schema='public' AND table_name=?
           ORDER BY ordinal_position
        """, (table,))
        constraints = _read(conn, """
          SELECT c.conname,c.contype,pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_class t ON t.oid=c.conrelid
            JOIN pg_namespace n ON n.oid=t.relnamespace
           WHERE n.nspname='public' AND t.relname=?
           ORDER BY c.conname
        """, (table,))
        names = {x[0] for x in constraints}
        if names != EXPECTED_CHECKS[table]:
            raise G111MigrationRejected("G111 table constraints drift: " + table)
        indexes = _read(conn, """
          SELECT indexname,indexdef FROM pg_indexes
           WHERE schemaname='public' AND tablename=?
           ORDER BY indexname
        """, (table,))
        schema.append([table,columns,constraints,indexes])
    return hashlib.sha256(repr(schema).encode("utf-8")).hexdigest()


def _verify_registry(conn):
    # Exact live registry contract. A valid row alone is NOT proof that future
    # source/schema hashes remain protected against newly inserted bad values.
    cols = _read(conn, """
      SELECT column_name,data_type,is_nullable,column_default
        FROM information_schema.columns
       WHERE table_schema='public' AND table_name=?
       ORDER BY ordinal_position
    """, (REGISTRY,))
    expected = [
        ("version","text","NO",None),
        ("source_sha256","text","NO",None),
        ("schema_sha256","text","NO",None),
        ("installed_at","timestamp with time zone","NO","CURRENT_TIMESTAMP"),
    ]
    if cols != expected:
        raise G111MigrationRejected("G111 migration registry columns/default drift")
    constraints = _read(conn, """
      SELECT c.conname,c.contype,pg_get_constraintdef(c.oid)
        FROM pg_constraint c
        JOIN pg_class r ON r.oid=c.conrelid
        JOIN pg_namespace n ON n.oid=r.relnamespace
       WHERE n.nspname='public' AND r.relname=?
       ORDER BY c.conname
    """, (REGISTRY,))
    expected_constraints = {
        "g111_nonmap_schema_versions_pkey":
            ("p", "PRIMARY KEY (version)"),
        "g111_nonmap_schema_versions_source_sha256_check":
            ("c", "CHECK ((length(source_sha256) = 64))"),
        "g111_nonmap_schema_versions_schema_sha256_check":
            ("c", "CHECK ((length(schema_sha256) = 64))"),
    }
    observed = {name:(kind,definition) for name,kind,definition in constraints}
    if observed != expected_constraints or len(constraints) != len(expected_constraints):
        raise G111MigrationRejected("G111 migration registry constraint drift")


def upgrade(conn, *, environ):
    """Controlled single-transaction additive upgrade; no connection creation.

    Return on success does NOT commit. Caller must own a fresh valid PG tx,
    hold a separately granted Owner DDL permission and commit/rollback.
    """
    if environ.get(FLAG) != "1":
        raise G111MigrationRejected("G111 explicit operator approval required")
    _preflight(conn)
    source = _sql()
    conn.execute("SELECT pg_advisory_xact_lock(111076)")
    if _present(conn, REGISTRY):
        _verify_registry(conn)
        rows = _read(conn, "SELECT version,source_sha256,schema_sha256 FROM g111_nonmap_schema_versions")
        if len(rows) != 1 or rows[0][:2] != (VERSION,SQL_SHA256):
            raise G111MigrationRejected("G111 unknown migration version/source hash")
        if rows[0][2] != _catalog_signature(conn):
            raise G111MigrationRejected("G111 deployed schema drift")
        return {"status":"ALREADY_APPLIED_VERIFIED","version":VERSION}

    if any(_present(conn, table) for table in TABLES):
        raise G111MigrationRejected("G111 unversioned or partial legacy migration, reconcile manually")

    conn.execute(source)
    signature = _catalog_signature(conn)
    conn.execute("""
      CREATE TABLE g111_nonmap_schema_versions (
        version TEXT PRIMARY KEY,
        source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
        schema_sha256 TEXT NOT NULL CHECK(length(schema_sha256)=64),
        installed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
      )
    """)
    conn.execute("""
      INSERT INTO g111_nonmap_schema_versions
      (version,source_sha256,schema_sha256) VALUES (?,?,?)
    """, (VERSION, SQL_SHA256, signature))
    return {"status":"APPLIED_PENDING_CALLER_COMMIT","version":VERSION}


def downgrade(*, environ):
    """Old-app feature rollback: disable flags and preserve ALL history."""
    flags = ("G076_NONMAP_STEPS_ENABLED","G076_PRACTICE_STEPS_ENABLED",
             "G076_DAILY_STEPS_ENABLED","G076_MISTAKES_STEPS_ENABLED")
    for name in flags:
        if str(environ.get(name,"")).strip().lower() not in ("","0","off","false"):
            raise G111MigrationRejected("disable step feature before rollback: " + name)
    return {"status":"PRESERVE_ADDITIVE_HISTORY","no_ddl":True,
            "no_player_records_deleted":True,"version":VERSION}
