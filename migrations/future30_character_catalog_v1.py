"""Additive schema for the canonical Future30 catalog and ownership ledger.

This migration stores catalog identity/mapping separately from player
entitlement and applied appearance.  It does not assign the still-unresolved
STARTER/STAGE/PREMIUM/SHOP groups or perform any acquisition.  The caller owns
the transaction and commit boundary.
"""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "future30_character_catalog_v1"
CATALOG_TABLE = "future30_character_catalog"
VISUAL_TABLE = "future30_character_visual_models"
ENTITLEMENT_TABLE = "player_character_entitlements"
ACQUISITION_SOURCES = ("STARTER", "STAGE", "PREMIUM", "SHOP", "ACCEPTANCE_TEST")
ADVISORY_LOCK_KEY = 773310041
INDEX_SPECS = (
    (f"idx_{ENTITLEMENT_TABLE}_character", ENTITLEMENT_TABLE, ("character_key",)),
    (f"idx_{VISUAL_TABLE}_character", VISUAL_TABLE, ("character_key",)),
)


class MigrationError(RuntimeError):
    """Base class for Future30 schema errors."""


class SchemaMismatch(MigrationError):
    """An existing Future30 table does not match this migration contract."""


def _raw(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw(conn).__class__.__module__.lower().startswith("sqlite3")


def _value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _prefix(conn: Any) -> str:
    return "" if _is_sqlite(conn) else "public."


def _table_exists(conn: Any, table: str) -> bool:
    if _is_sqlite(conn):
        return bool(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone())
    return bool(conn.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=?", (table,)
    ).fetchone())


def _column_rows(conn: Any, table: str) -> list[Any]:
    if _is_sqlite(conn):
        return list(conn.execute(f"PRAGMA table_info({table})").fetchall())
    return list(conn.execute(
        "SELECT column_name, data_type, is_nullable, ordinal_position "
        "FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=? ORDER BY ordinal_position",
        (table,),
    ).fetchall())


def _primary_columns(conn: Any, table: str, rows: list[Any]) -> set[str]:
    if _is_sqlite(conn):
        return {
            str(_value(row, 1, "name"))
            for row in rows
            if int(_value(row, 5, "pk") or 0) > 0
        }
    rows = conn.execute(
        """SELECT a.attname
             FROM pg_index i
             JOIN pg_class t ON t.oid=i.indrelid
             JOIN pg_namespace n ON n.oid=t.relnamespace
             JOIN unnest(i.indkey) WITH ORDINALITY k(attnum, ord) ON TRUE
             JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=k.attnum
            WHERE n.nspname='public' AND t.relname=? AND i.indisprimary
            ORDER BY k.ord""",
        (table,),
    ).fetchall()
    return {str(_value(row, 0, "attname")) for row in rows}


def _table_constraints_text(conn: Any, table: str) -> str:
    if _is_sqlite(conn):
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        return str(_value(row, 0, "sql") or "") if row else ""
    rows = conn.execute(
        """SELECT pg_get_constraintdef(c.oid)
             FROM pg_constraint c
             JOIN pg_class t ON t.oid=c.conrelid
             JOIN pg_namespace n ON n.oid=t.relnamespace
            WHERE n.nspname='public' AND t.relname=?""",
        (table,),
    ).fetchall()
    return " ".join(str(_value(row, 0, "pg_get_constraintdef")) for row in rows)


def _index_columns(conn: Any, table: str, index_name: str) -> tuple[str, ...] | None:
    if _is_sqlite(conn):
        names = {
            str(_value(row, 1, "name"))
            for row in conn.execute(f"PRAGMA index_list({table})").fetchall()
        }
        if index_name not in names:
            return None
        rows = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
        return tuple(str(_value(row, 2, "name")) for row in rows)
    row = conn.execute(
        """SELECT indexdef FROM pg_indexes
            WHERE schemaname='public' AND tablename=? AND indexname=?""",
        (table, index_name),
    ).fetchone()
    if not row:
        return None
    import re

    match = re.search(r"\(([^)]*)\)", str(_value(row, 0, "indexdef")))
    return tuple(part.strip().strip('"') for part in match.group(1).split(",")) if match else None


def _ddl(conn: Any) -> tuple[str, str, str]:
    prefix = _prefix(conn)
    users = f"{prefix}users"
    catalog = f"{prefix}{CATALOG_TABLE}"
    visuals = f"{prefix}{VISUAL_TABLE}"
    entitlements = f"{prefix}{ENTITLEMENT_TABLE}"
    sources = ", ".join(f"'{value}'" for value in ACQUISITION_SOURCES)
    return (
        f"""CREATE TABLE IF NOT EXISTS {catalog} (
            character_key TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            default_variant TEXT NOT NULL CHECK (default_variant IN ('RED')),
            visual_model_id TEXT NOT NULL UNIQUE,
            character_asset_id TEXT NOT NULL UNIQUE,
            runtime_glb TEXT NOT NULL,
            runtime_sha256 TEXT NOT NULL,
            admission_state TEXT NOT NULL CHECK (admission_state IN ('ENABLED')),
            license_status TEXT NOT NULL,
            provenance_status TEXT NOT NULL,
            authority_ref TEXT NOT NULL,
            product_manifest_sha256 TEXT NOT NULL,
            c005_manifest_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS {visuals} (
            visual_model_id TEXT PRIMARY KEY,
            character_key TEXT NOT NULL REFERENCES {catalog}(character_key) ON DELETE RESTRICT,
            variant TEXT NOT NULL CHECK (variant IN ('RED', 'BLUE')),
            character_asset_id TEXT NOT NULL UNIQUE,
            runtime_glb TEXT NOT NULL,
            runtime_sha256 TEXT NOT NULL,
            mapping_status TEXT NOT NULL CHECK (mapping_status IN ('CONFIRMED')),
            c005_manifest_sha256 TEXT NOT NULL,
            UNIQUE (character_key, variant)
        )""",
        f"""CREATE TABLE IF NOT EXISTS {entitlements} (
            user_id INTEGER NOT NULL REFERENCES {users}(id) ON DELETE CASCADE,
            character_key TEXT NOT NULL REFERENCES {catalog}(character_key) ON DELETE RESTRICT,
            acquisition_source TEXT NOT NULL CHECK (acquisition_source IN ({sources})),
            source_reference TEXT,
            acquired_at TEXT NOT NULL,
            PRIMARY KEY (user_id, character_key)
        )""",
    )


EXPECTED_COLUMNS = {
    CATALOG_TABLE: {
        "character_key", "display_name", "default_variant", "visual_model_id",
        "character_asset_id", "runtime_glb", "runtime_sha256", "admission_state",
        "license_status", "provenance_status", "authority_ref",
        "product_manifest_sha256", "c005_manifest_sha256", "created_at", "updated_at",
    },
    ENTITLEMENT_TABLE: {
        "user_id", "character_key", "acquisition_source", "source_reference", "acquired_at",
    },
    VISUAL_TABLE: {
        "visual_model_id", "character_key", "variant", "character_asset_id",
        "runtime_glb", "runtime_sha256", "mapping_status", "c005_manifest_sha256",
    },
}
EXPECTED_PRIMARY_KEYS = {
    CATALOG_TABLE: {"character_key"},
    ENTITLEMENT_TABLE: {"user_id", "character_key"},
    VISUAL_TABLE: {"visual_model_id"},
}


def validate_schema(conn: Any) -> dict[str, Any]:
    tables = (CATALOG_TABLE, VISUAL_TABLE, ENTITLEMENT_TABLE)
    missing_tables = [table for table in tables if not _table_exists(conn, table)]
    missing_columns: dict[str, list[str]] = {}
    unexpected_columns: dict[str, list[str]] = {}
    primary_key_mismatches: dict[str, list[str]] = {}
    for table in tables:
        if not _table_exists(conn, table):
            continue
        rows = _column_rows(conn, table)
        actual = {
            str(_value(row, 1 if _is_sqlite(conn) else 0,
                       "name" if _is_sqlite(conn) else "column_name"))
            for row in rows
        }
        missing = sorted(EXPECTED_COLUMNS[table] - actual)
        unexpected = sorted(actual - EXPECTED_COLUMNS[table])
        if missing:
            missing_columns[table] = missing
        if unexpected:
            unexpected_columns[table] = unexpected
        primary = _primary_columns(conn, table, rows)
        if primary != EXPECTED_PRIMARY_KEYS[table]:
            primary_key_mismatches[table] = sorted(primary)

    catalog_checks = _table_constraints_text(conn, CATALOG_TABLE).upper()
    visual_checks = _table_constraints_text(conn, VISUAL_TABLE).upper()
    entitlement_checks = _table_constraints_text(conn, ENTITLEMENT_TABLE).upper()
    checks_valid = all(value in catalog_checks for value in ("RED", "ENABLED")) and all(
        value in entitlement_checks for value in ACQUISITION_SOURCES
    ) and all(value in visual_checks for value in ("RED", "BLUE", "CONFIRMED"))
    indexes_valid = True
    missing_indexes: list[str] = []
    for name, table, columns in INDEX_SPECS:
        if table not in missing_tables:
            if _index_columns(conn, table, name) != columns:
                indexes_valid = False
                missing_indexes.append(name)

    valid = not (
        missing_tables or missing_columns or unexpected_columns
        or primary_key_mismatches or not checks_valid or not indexes_valid
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": valid,
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "unexpected_columns": unexpected_columns,
        "primary_key_mismatches": primary_key_mismatches,
        "checks_valid": checks_valid,
        "missing_indexes": missing_indexes,
        "catalog_table": CATALOG_TABLE,
        "visual_table": VISUAL_TABLE,
        "entitlement_table": ENTITLEMENT_TABLE,
        "logical_character_count": 30,
        "visual_model_count": 33,
        "acquisition_sources": list(ACQUISITION_SOURCES),
    }


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Create and validate the additive schema; the caller owns commit."""

    if not _is_sqlite(conn):
        conn.execute("SELECT pg_advisory_xact_lock(?)", (ADVISORY_LOCK_KEY,))
    before = validate_schema(conn)
    created: list[str] = []
    if dry_run:
        return {
            **before,
            "created": [],
            "planned_create": before["missing_tables"],
            "dry_run": True,
        }

    catalog_sql, visual_sql, entitlement_sql = _ddl(conn)
    if CATALOG_TABLE in before["missing_tables"]:
        conn.execute(catalog_sql)
        created.append(CATALOG_TABLE)
    if VISUAL_TABLE in before["missing_tables"]:
        conn.execute(visual_sql)
        created.append(VISUAL_TABLE)
    if ENTITLEMENT_TABLE in before["missing_tables"]:
        conn.execute(entitlement_sql)
        created.append(ENTITLEMENT_TABLE)
    for index_name, table, columns in INDEX_SPECS:
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS {index_name} ON "
            f"{_prefix(conn)}{table} ({', '.join(columns)})"
        )

    after = validate_schema(conn)
    if not after["valid"]:
        raise SchemaMismatch(f"Future30 character schema mismatch: {after}")
    return {**after, "created": created, "planned_create": [], "dry_run": False}


def downgrade_for_isolated_test(conn: Any) -> None:
    """Drop only this migration's two tables from a disposable test database."""

    prefix = _prefix(conn)
    conn.execute(f"DROP TABLE IF EXISTS {prefix}{ENTITLEMENT_TABLE}")
    conn.execute(f"DROP TABLE IF EXISTS {prefix}{VISUAL_TABLE}")
    conn.execute(f"DROP TABLE IF EXISTS {prefix}{CATALOG_TABLE}")


__all__ = [
    "ACQUISITION_SOURCES", "ADVISORY_LOCK_KEY", "CATALOG_TABLE", "ENTITLEMENT_TABLE", "VISUAL_TABLE",
    "INDEX_SPECS", "MigrationError", "SCHEMA_VERSION", "SchemaMismatch",
    "downgrade_for_isolated_test", "upgrade", "validate_schema",
]
