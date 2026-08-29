"""Additive persistent storage for the Immutable Puzzle Identity foundation.

LC011 ratified the architecture; LC012 / LC012-R1 / LC012-R2 closed the
historical genesis provenance and issued the immutable P2 genesis receipt.
This migration candidate is the **empty** storage layer that must exist
*before* any owner-gated genesis bootstrap:

  * ``puzzle_identity_registry``          — one durable row per Puzzle identity
  * ``puzzle_identity_alias``             — legacy id / source path / resolver aliases
  * ``puzzle_identity_lineage``           — append-only LC011 lineage events
  * ``puzzle_identity_bootstrap_receipt`` — once-only genesis bootstrap guard

It is a migration candidate only: it never commits, never runs at request
time, and the caller owns the surrounding transaction.  It does **not** create,
mutate, or reference any of the 42,804 frozen genesis identities.

``source_record_uuid`` is the permanent identity.  A live/current source path is
never the identity primary key.  Immutability of the UUID (and of the other
creation-time facts) and append-only lineage are enforced in the database with
triggers on both SQLite (test) and PostgreSQL (production target).
"""
from __future__ import annotations

from typing import Any, Callable


SCHEMA_VERSION = "puzzle_identity_registry_v1"
IDENTITY_SCHEMA_VERSION = "puzzle-identity-schema-v1"
ADVISORY_LOCK_KEY = 773310131

TABLE_NAMES = (
    "puzzle_identity_registry",
    "puzzle_identity_alias",
    "puzzle_identity_lineage",
    "puzzle_identity_bootstrap_receipt",
)

IDENTITY_KINDS = ("HISTORICAL_GENESIS", "NATIVE_UUIDV4")
ORIGIN_CLASSES = ("GENESIS", "NATIVE")
IDENTITY_STATUSES = ("ACTIVE", "RETIRED")

ALIAS_KINDS = (
    "LEGACY_QUESTION_ID",
    "HISTORICAL_SOURCE_PATH",
    "CURRENT_SOURCE_PATH",
    "CANONICAL_SOURCE_KEY",
    "RESOLVER_ALIAS",
)
ALIAS_CONFIDENCE = ("EXACT", "HIGH_CONFIDENCE", "RECORDED")

# The 13 LC011-approved lineage mutation events plus the two creation anchors
# (GENESIS / NATIVE_CREATE).  Anything outside this set fails closed via CHECK.
LINEAGE_MUTATION_EVENTS = (
    "RENAME",
    "MOVE",
    "COLLECTION_CHANGE",
    "CASE_CORRECTION",
    "CANONICALIZATION_CORRECTION",
    "CONTENT_CORRECTION",
    "METADATA_CORRECTION",
    "DELETE",
    "RESTORE",
    "SPLIT",
    "MERGE",
    "REPLACED",
    "MANUAL",
)
LINEAGE_CREATION_EVENTS = ("GENESIS", "NATIVE_CREATE")
LINEAGE_EVENT_TYPES = LINEAGE_CREATION_EVENTS + LINEAGE_MUTATION_EVENTS

LINEAGE_RELATIONSHIP_ROLES = (
    "PARENT",
    "CHILD",
    "SURVIVOR",
    "NON_SURVIVOR",
    "SUPERSEDES",
    "SUPERSEDED_BY",
)

BOOTSTRAP_STATUSES = ("APPLIED", "ABORTED")
BOOTSTRAP_SINGLETON_VALUE = "GENESIS"

_UUID_SHAPE_CHECK = (
    "length({col}) = 36 "
    "AND substr({col}, 9, 1) = '-' AND substr({col}, 14, 1) = '-' "
    "AND substr({col}, 19, 1) = '-' AND substr({col}, 24, 1) = '-'"
)

_TRIGGERS_SQLITE = (
    "trg_pir_uuid_immutable",
    "trg_pir_creation_facts_immutable",
    "trg_pia_binding_immutable",
    "trg_pil_no_update",
    "trg_pil_no_delete",
    "trg_pibr_no_update",
    "trg_pibr_no_delete",
)
_TRIGGERS_PG = (
    "trg_pir_uuid_immutable",
    "trg_pir_creation_facts_immutable",
    "trg_pia_binding_immutable",
    "trg_pil_append_only",
    "trg_pibr_append_only",
)
_PG_FUNCTIONS = (
    "puzzle_identity_reject_uuid_change",
    "puzzle_identity_reject_creation_fact_change",
    "puzzle_identity_reject_alias_binding_change",
    "puzzle_identity_reject_write",
)


class PuzzleIdentitySchemaError(RuntimeError):
    """The target does not satisfy the additive puzzle-identity storage contract."""


# --------------------------------------------------------------------------- #
# dialect helpers (repository convention: ? paramstyle, TEXT-first, dual PG/SQLite)
# --------------------------------------------------------------------------- #

def _raw(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw(conn).__class__.__module__.lower().startswith("sqlite3")


def _dialect(conn: Any) -> str:
    return "sqlite" if _is_sqlite(conn) else "postgres"


def _execute(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    # No-param statements (all DDL) are sent without a parameter sequence so the
    # PostgreSQL wrapper does not run %-interpolation over DDL that legitimately
    # contains '%' (e.g. plpgsql RAISE format specifiers, LIKE patterns).
    if hasattr(conn, "execute"):
        return conn.execute(sql, params) if params else conn.execute(sql)
    cursor = conn.cursor()
    if params:
        cursor.execute(sql.replace("?", "%s"), params)
    else:
        cursor.execute(sql)
    return cursor


def _fetchone(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    cur = _execute(conn, sql, params)
    try:
        return cur.fetchone()
    finally:
        if not hasattr(conn, "execute"):
            cur.close()


def _fetchall(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    cur = _execute(conn, sql, params)
    try:
        return list(cur.fetchall())
    finally:
        if not hasattr(conn, "execute"):
            cur.close()


def _table_exists(conn: Any, table: str) -> bool:
    if _is_sqlite(conn):
        return bool(_fetchone(
            conn, "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)))
    return bool(_fetchone(
        conn,
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=?",
        (table,),
    ))


def _columns(conn: Any, table: str) -> set[str]:
    if _is_sqlite(conn):
        return {str(r[1]) for r in _fetchall(conn, f"PRAGMA table_info({table})")}
    rows = _fetchall(
        conn,
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=?",
        (table,),
    )
    return {str(r[0] if not hasattr(r, "keys") else r["column_name"]) for r in rows}


def _sqlite_trigger_names(conn: Any) -> set[str]:
    return {str(r[0]) for r in _fetchall(
        conn, "SELECT name FROM sqlite_master WHERE type='trigger'")}


def _pg_trigger_names(conn: Any) -> set[str]:
    rows = _fetchall(
        conn,
        "SELECT tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
        "WHERE NOT t.tgisinternal AND c.relname IN "
        "('puzzle_identity_registry','puzzle_identity_alias',"
        "'puzzle_identity_lineage','puzzle_identity_bootstrap_receipt')",
    )
    return {str(r[0] if not hasattr(r, "keys") else r["tgname"]) for r in rows}


# --------------------------------------------------------------------------- #
# DDL
# --------------------------------------------------------------------------- #

def _id_type(dialect: str) -> str:
    return "INTEGER PRIMARY KEY AUTOINCREMENT" if dialect == "sqlite" else "BIGSERIAL PRIMARY KEY"


def _stamp(dialect: str) -> str:
    return "TEXT" if dialect == "sqlite" else "TIMESTAMPTZ"


def _bool_type(dialect: str) -> str:
    return "INTEGER" if dialect == "sqlite" else "BOOLEAN"


def _bool_default(dialect: str, value: bool) -> str:
    if dialect == "sqlite":
        return "1" if value else "0"
    return "TRUE" if value else "FALSE"


def _is_true_predicate(dialect: str, col: str = "is_current") -> str:
    """A dialect-correct 'this boolean flag is true' predicate.

    PostgreSQL evaluates the BOOLEAN column directly; SQLite compares the
    INTEGER flag to 1.  Neither relies on an implicit 0/1 -> BOOLEAN cast.
    """
    return col if dialect == "postgres" else f"{col} = 1"


def _in_list(col: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{col} IN ({joined})"


def _table_ddl(dialect: str) -> list[str]:
    """CREATE TABLE statements in FK-dependency order.

    bootstrap_receipt (no deps) -> registry (-> bootstrap_receipt)
    -> alias / lineage (-> registry).  PostgreSQL requires every referenced
    parent to exist first; SQLite tolerates any order but is created the same way.
    """
    ident = _id_type(dialect)
    stamp = _stamp(dialect)
    bool_type = _bool_type(dialect)
    bool_default_true = _bool_default(dialect, True)
    # SQLite keeps an explicit 0/1 domain check; PostgreSQL BOOLEAN needs none.
    is_current_check = (
        "\n                CHECK (is_current IN (0, 1)),"
        if dialect == "sqlite" else ","
    )
    uuid_shape = _UUID_SHAPE_CHECK.format(col="source_record_uuid")
    related_shape = _UUID_SHAPE_CHECK.format(col="related_source_record_uuid")

    return [
        f"""CREATE TABLE IF NOT EXISTS puzzle_identity_bootstrap_receipt (
            receipt_sha256 TEXT PRIMARY KEY NOT NULL,
            bootstrap_singleton TEXT NOT NULL DEFAULT 'GENESIS' UNIQUE
                CHECK (bootstrap_singleton = 'GENESIS'),
            frozen_corpus_sha256 TEXT NOT NULL,
            record_count INTEGER NOT NULL CHECK (record_count > 0),
            namespace_uuid TEXT NOT NULL,
            canonicalisation_rules_version TEXT NOT NULL,
            genesis_key_spec_version TEXT NOT NULL,
            historical_tree_commit TEXT NOT NULL,
            historical_tree_manifest_sha256 TEXT NOT NULL,
            historical_rename_map_sha256 TEXT NOT NULL,
            genesis_record_manifest_sha256 TEXT NOT NULL,
            proposed_uuid_list_sha256 TEXT NOT NULL,
            status TEXT NOT NULL CHECK ({_in_list('status', BOOTSTRAP_STATUSES)}),
            identities_written INTEGER NOT NULL DEFAULT 0 CHECK (identities_written >= 0),
            applied_at {stamp} NOT NULL,
            applied_by TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS puzzle_identity_registry (
            source_record_uuid TEXT PRIMARY KEY NOT NULL
                CHECK ({uuid_shape}),
            identity_kind TEXT NOT NULL CHECK ({_in_list('identity_kind', IDENTITY_KINDS)}),
            identity_version TEXT NOT NULL,
            origin_class TEXT NOT NULL CHECK ({_in_list('origin_class', ORIGIN_CLASSES)}),
            identity_status TEXT NOT NULL DEFAULT 'ACTIVE'
                CHECK ({_in_list('identity_status', IDENTITY_STATUSES)}),
            created_at {stamp} NOT NULL,
            created_by_process TEXT NOT NULL,
            creation_reason TEXT NOT NULL,
            genesis_receipt_ref TEXT
                REFERENCES puzzle_identity_bootstrap_receipt(receipt_sha256),
            retired_at {stamp},
            retire_reason TEXT,
            provenance_note TEXT,
            CHECK (identity_kind <> 'HISTORICAL_GENESIS' OR origin_class = 'GENESIS'),
            CHECK (identity_kind <> 'NATIVE_UUIDV4' OR origin_class = 'NATIVE'),
            CHECK (identity_kind <> 'HISTORICAL_GENESIS' OR genesis_receipt_ref IS NOT NULL),
            CHECK (identity_status <> 'RETIRED' OR retired_at IS NOT NULL)
        )""",
        f"""CREATE TABLE IF NOT EXISTS puzzle_identity_alias (
            id {ident},
            source_record_uuid TEXT NOT NULL
                REFERENCES puzzle_identity_registry(source_record_uuid),
            alias_kind TEXT NOT NULL CHECK ({_in_list('alias_kind', ALIAS_KINDS)}),
            alias_value TEXT NOT NULL,
            alias_context TEXT NOT NULL DEFAULT 'genesis-v1',
            confidence TEXT NOT NULL DEFAULT 'EXACT'
                CHECK ({_in_list('confidence', ALIAS_CONFIDENCE)}),
            is_current {bool_type} NOT NULL DEFAULT {bool_default_true}{is_current_check}
            recorded_at {stamp} NOT NULL,
            recorded_by TEXT NOT NULL,
            UNIQUE (source_record_uuid, alias_kind, alias_value, alias_context)
        )""",
        f"""CREATE TABLE IF NOT EXISTS puzzle_identity_lineage (
            id {ident},
            source_record_uuid TEXT NOT NULL
                REFERENCES puzzle_identity_registry(source_record_uuid),
            seq BIGINT NOT NULL,
            event_type TEXT NOT NULL CHECK ({_in_list('event_type', LINEAGE_EVENT_TYPES)}),
            occurred_at {stamp} NOT NULL,
            actor TEXT NOT NULL,
            from_value TEXT,
            to_value TEXT,
            related_source_record_uuid TEXT
                CHECK (related_source_record_uuid IS NULL OR ({related_shape})),
            relationship_role TEXT
                CHECK (relationship_role IS NULL
                       OR {_in_list('relationship_role', LINEAGE_RELATIONSHIP_ROLES)}),
            reason TEXT NOT NULL,
            evidence_ref TEXT,
            recorded_at {stamp} NOT NULL,
            UNIQUE (source_record_uuid, seq)
        )""",
    ]


INDEX_SPECS: tuple[tuple[str, str, str], ...] = (
    ("idx_pir_status_kind", "puzzle_identity_registry", "identity_status, identity_kind"),
    ("idx_pir_receipt_ref", "puzzle_identity_registry", "genesis_receipt_ref"),
    ("idx_pia_uuid", "puzzle_identity_alias", "source_record_uuid"),
    ("idx_pil_uuid_seq", "puzzle_identity_lineage", "source_record_uuid, seq"),
    ("idx_pil_event_type", "puzzle_identity_lineage", "event_type"),
    ("idx_pil_related_uuid", "puzzle_identity_lineage", "related_source_record_uuid"),
)

# Partial unique indexes.  The predicate is rendered per dialect so PostgreSQL
# evaluates the BOOLEAN column directly and SQLite compares the 0/1 flag.
#   uq_pia_current_alias     -> AMBIGUOUS_ALIAS_FAILS_CLOSED: at most one identity
#                               may *currently* hold a given (kind, value, context)
#   uq_pia_one_current_path  -> at most one *current* CURRENT_SOURCE_PATH per
#                               identity, so rename/move fail-closed on `from_path`
PARTIAL_UNIQUE_SPECS: tuple[tuple[str, str, str, Callable[[str], str]], ...] = (
    (
        "uq_pia_current_alias",
        "puzzle_identity_alias",
        "alias_kind, alias_value, alias_context",
        lambda d: _is_true_predicate(d),
    ),
    (
        "uq_pia_one_current_path",
        "puzzle_identity_alias",
        "source_record_uuid",
        lambda d: f"alias_kind = 'CURRENT_SOURCE_PATH' AND {_is_true_predicate(d)}",
    ),
)


def _sqlite_trigger_ddl() -> list[tuple[str, str]]:
    return [
        (
            "trg_pir_uuid_immutable",
            """CREATE TRIGGER trg_pir_uuid_immutable
               BEFORE UPDATE OF source_record_uuid ON puzzle_identity_registry
               WHEN NEW.source_record_uuid IS NOT OLD.source_record_uuid
               BEGIN SELECT RAISE(ABORT, 'source_record_uuid is immutable'); END""",
        ),
        (
            "trg_pir_creation_facts_immutable",
            """CREATE TRIGGER trg_pir_creation_facts_immutable
               BEFORE UPDATE OF identity_kind, identity_version, origin_class,
                                created_at, created_by_process, creation_reason,
                                genesis_receipt_ref
               ON puzzle_identity_registry
               BEGIN SELECT RAISE(ABORT,
                 'puzzle_identity_registry creation facts are immutable'); END""",
        ),
        (
            "trg_pia_binding_immutable",
            """CREATE TRIGGER trg_pia_binding_immutable
               BEFORE UPDATE OF source_record_uuid, alias_kind, alias_value, alias_context
               ON puzzle_identity_alias
               BEGIN SELECT RAISE(ABORT,
                 'alias identity binding is immutable (supersede instead)'); END""",
        ),
        (
            "trg_pil_no_update",
            """CREATE TRIGGER trg_pil_no_update
               BEFORE UPDATE ON puzzle_identity_lineage
               BEGIN SELECT RAISE(ABORT, 'puzzle_identity_lineage is append-only'); END""",
        ),
        (
            "trg_pil_no_delete",
            """CREATE TRIGGER trg_pil_no_delete
               BEFORE DELETE ON puzzle_identity_lineage
               BEGIN SELECT RAISE(ABORT, 'puzzle_identity_lineage is append-only'); END""",
        ),
        (
            "trg_pibr_no_update",
            """CREATE TRIGGER trg_pibr_no_update
               BEFORE UPDATE ON puzzle_identity_bootstrap_receipt
               BEGIN SELECT RAISE(ABORT,
                 'puzzle_identity_bootstrap_receipt is immutable'); END""",
        ),
        (
            "trg_pibr_no_delete",
            """CREATE TRIGGER trg_pibr_no_delete
               BEFORE DELETE ON puzzle_identity_bootstrap_receipt
               BEGIN SELECT RAISE(ABORT,
                 'puzzle_identity_bootstrap_receipt is immutable'); END""",
        ),
    ]


def _pg_trigger_ddl() -> list[str]:
    return [
        """CREATE OR REPLACE FUNCTION puzzle_identity_reject_uuid_change()
           RETURNS trigger AS $$
           BEGIN
             IF NEW.source_record_uuid IS DISTINCT FROM OLD.source_record_uuid THEN
               RAISE EXCEPTION 'source_record_uuid is immutable';
             END IF;
             RETURN NEW;
           END;
           $$ LANGUAGE plpgsql""",
        """CREATE OR REPLACE FUNCTION puzzle_identity_reject_creation_fact_change()
           RETURNS trigger AS $$
           BEGIN
             IF (NEW.identity_kind, NEW.identity_version, NEW.origin_class,
                 NEW.created_at, NEW.created_by_process, NEW.creation_reason,
                 NEW.genesis_receipt_ref)
                IS DISTINCT FROM
                (OLD.identity_kind, OLD.identity_version, OLD.origin_class,
                 OLD.created_at, OLD.created_by_process, OLD.creation_reason,
                 OLD.genesis_receipt_ref) THEN
               RAISE EXCEPTION 'puzzle_identity_registry creation facts are immutable';
             END IF;
             RETURN NEW;
           END;
           $$ LANGUAGE plpgsql""",
        """CREATE OR REPLACE FUNCTION puzzle_identity_reject_alias_binding_change()
           RETURNS trigger AS $$
           BEGIN
             IF (NEW.source_record_uuid, NEW.alias_kind, NEW.alias_value, NEW.alias_context)
                IS DISTINCT FROM
                (OLD.source_record_uuid, OLD.alias_kind, OLD.alias_value, OLD.alias_context) THEN
               RAISE EXCEPTION 'alias identity binding is immutable (supersede instead)';
             END IF;
             RETURN NEW;
           END;
           $$ LANGUAGE plpgsql""",
        """CREATE OR REPLACE FUNCTION puzzle_identity_reject_write()
           RETURNS trigger AS $$
           BEGIN
             RAISE EXCEPTION 'append-only puzzle_identity table: operation not permitted';
           END;
           $$ LANGUAGE plpgsql""",
        "DROP TRIGGER IF EXISTS trg_pir_uuid_immutable ON puzzle_identity_registry",
        """CREATE TRIGGER trg_pir_uuid_immutable
           BEFORE UPDATE ON puzzle_identity_registry
           FOR EACH ROW EXECUTE FUNCTION puzzle_identity_reject_uuid_change()""",
        "DROP TRIGGER IF EXISTS trg_pir_creation_facts_immutable ON puzzle_identity_registry",
        """CREATE TRIGGER trg_pir_creation_facts_immutable
           BEFORE UPDATE ON puzzle_identity_registry
           FOR EACH ROW EXECUTE FUNCTION puzzle_identity_reject_creation_fact_change()""",
        "DROP TRIGGER IF EXISTS trg_pia_binding_immutable ON puzzle_identity_alias",
        """CREATE TRIGGER trg_pia_binding_immutable
           BEFORE UPDATE ON puzzle_identity_alias
           FOR EACH ROW EXECUTE FUNCTION puzzle_identity_reject_alias_binding_change()""",
        "DROP TRIGGER IF EXISTS trg_pil_append_only ON puzzle_identity_lineage",
        """CREATE TRIGGER trg_pil_append_only
           BEFORE UPDATE OR DELETE ON puzzle_identity_lineage
           FOR EACH ROW EXECUTE FUNCTION puzzle_identity_reject_write()""",
        "DROP TRIGGER IF EXISTS trg_pibr_append_only ON puzzle_identity_bootstrap_receipt",
        """CREATE TRIGGER trg_pibr_append_only
           BEFORE UPDATE OR DELETE ON puzzle_identity_bootstrap_receipt
           FOR EACH ROW EXECUTE FUNCTION puzzle_identity_reject_write()""",
    ]


# --------------------------------------------------------------------------- #
# validate / upgrade / downgrade
# --------------------------------------------------------------------------- #

REQUIRED_COLUMNS = {
    "puzzle_identity_registry": {
        "source_record_uuid", "identity_kind", "identity_version", "origin_class",
        "identity_status", "created_at", "created_by_process", "creation_reason",
        "genesis_receipt_ref", "retired_at", "retire_reason", "provenance_note",
    },
    "puzzle_identity_alias": {
        "id", "source_record_uuid", "alias_kind", "alias_value", "alias_context",
        "confidence", "is_current", "recorded_at", "recorded_by",
    },
    "puzzle_identity_lineage": {
        "id", "source_record_uuid", "seq", "event_type", "occurred_at", "actor",
        "from_value", "to_value", "related_source_record_uuid", "relationship_role",
        "reason", "evidence_ref", "recorded_at",
    },
    "puzzle_identity_bootstrap_receipt": {
        "receipt_sha256", "bootstrap_singleton", "frozen_corpus_sha256",
        "record_count", "namespace_uuid", "canonicalisation_rules_version",
        "genesis_key_spec_version", "historical_tree_commit",
        "historical_tree_manifest_sha256", "historical_rename_map_sha256",
        "genesis_record_manifest_sha256", "proposed_uuid_list_sha256",
        "status", "identities_written", "applied_at", "applied_by",
    },
}


def validate_schema(conn: Any) -> dict[str, Any]:
    missing_tables = [t for t in TABLE_NAMES if not _table_exists(conn, t)]
    missing_columns = {
        t: sorted(REQUIRED_COLUMNS[t] - _columns(conn, t))
        for t in TABLE_NAMES
        if _table_exists(conn, t) and REQUIRED_COLUMNS[t] - _columns(conn, t)
    }
    triggers = _sqlite_trigger_names(conn) if _is_sqlite(conn) else _pg_trigger_names(conn)
    expected_triggers = set(_TRIGGERS_SQLITE if _is_sqlite(conn) else _TRIGGERS_PG)
    missing_triggers = sorted(expected_triggers - triggers) if not missing_tables else []
    return {
        "schema_version": SCHEMA_VERSION,
        "identity_schema_version": IDENTITY_SCHEMA_VERSION,
        "dialect": _dialect(conn),
        "valid": not missing_tables and not missing_columns and not missing_triggers,
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "missing_triggers": missing_triggers,
        "lineage_event_types": list(LINEAGE_EVENT_TYPES),
        "identity_kinds": list(IDENTITY_KINDS),
    }


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Create the additive candidate inside the caller-owned transaction.

    Never commits.  Idempotent (``IF NOT EXISTS`` / ``CREATE OR REPLACE``).
    """
    before = validate_schema(conn)
    if dry_run:
        return {**before, "created": [], "dry_run": True}

    if not _is_sqlite(conn):
        _execute(conn, "SELECT pg_advisory_xact_lock(?)", (ADVISORY_LOCK_KEY,))

    for statement in _table_ddl(before["dialect"]):
        _execute(conn, statement)
    for name, table, cols in INDEX_SPECS:
        _execute(conn, f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})")
    for name, table, cols, predicate_fn in PARTIAL_UNIQUE_SPECS:
        _execute(
            conn,
            f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {table} ({cols}) "
            f"WHERE {predicate_fn(before['dialect'])}",
        )

    if _is_sqlite(conn):
        existing = _sqlite_trigger_names(conn)
        for name, ddl in _sqlite_trigger_ddl():
            if name not in existing:
                _execute(conn, ddl)
    else:
        for statement in _pg_trigger_ddl():
            _execute(conn, statement)

    after = validate_schema(conn)
    if not after["valid"]:
        raise PuzzleIdentitySchemaError(f"puzzle-identity schema incomplete: {after}")
    return {**after, "created": True, "dry_run": False}


def downgrade_for_isolated_test(conn: Any) -> None:
    """Drop only this candidate's objects for a disposable fixture."""
    if _is_sqlite(conn):
        for name in _TRIGGERS_SQLITE:
            _execute(conn, f"DROP TRIGGER IF EXISTS {name}")
    else:
        for name, table in (
            ("trg_pir_uuid_immutable", "puzzle_identity_registry"),
            ("trg_pir_creation_facts_immutable", "puzzle_identity_registry"),
            ("trg_pia_binding_immutable", "puzzle_identity_alias"),
            ("trg_pil_append_only", "puzzle_identity_lineage"),
            ("trg_pibr_append_only", "puzzle_identity_bootstrap_receipt"),
        ):
            _execute(conn, f"DROP TRIGGER IF EXISTS {name} ON {table}")
        for fn in _PG_FUNCTIONS:
            _execute(conn, f"DROP FUNCTION IF EXISTS {fn}()")
    for name, _table, _cols, _pred in PARTIAL_UNIQUE_SPECS:
        _execute(conn, f"DROP INDEX IF EXISTS {name}")
    for name, _table, _cols in reversed(INDEX_SPECS):
        _execute(conn, f"DROP INDEX IF EXISTS {name}")
    # FK-safe order: dependants (alias, lineage, registry) before the
    # bootstrap-receipt parent.
    drop_order = (
        "puzzle_identity_alias",
        "puzzle_identity_lineage",
        "puzzle_identity_registry",
        "puzzle_identity_bootstrap_receipt",
    )
    cascade = "" if _is_sqlite(conn) else " CASCADE"
    for table in drop_order:
        _execute(conn, f"DROP TABLE IF EXISTS {table}{cascade}")


__all__ = [
    "ADVISORY_LOCK_KEY",
    "ALIAS_KINDS",
    "BOOTSTRAP_SINGLETON_VALUE",
    "IDENTITY_KINDS",
    "IDENTITY_SCHEMA_VERSION",
    "IDENTITY_STATUSES",
    "LINEAGE_CREATION_EVENTS",
    "LINEAGE_EVENT_TYPES",
    "LINEAGE_MUTATION_EVENTS",
    "PuzzleIdentitySchemaError",
    "SCHEMA_VERSION",
    "TABLE_NAMES",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
