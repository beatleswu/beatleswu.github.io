"""Additive PostgreSQL schema for the F010 Monster selector authority.

The migration is a candidate only.  It never commits and it is intentionally
not called from request-time application startup.  A governed release step or
an isolated test owns when ``upgrade`` is executed.

Two records are kept together by the caller's transaction:

* ``monster_encounter_selector_state`` is the per-user/per-zone cycle cursor.
* ``monster_encounter_selection_operation`` is the immutable replay binding
  for one server-owned encounter operation.

The before/after selector state is retained on the operation row so support
and tests can reconstruct exactly what was committed without treating logs as
the authority.
"""

from __future__ import annotations

from typing import Any, Iterable


SCHEMA_VERSION = "monster_encounter_selector_state_v1"
STATE_TABLE_NAME = "monster_encounter_selector_state"
OPERATION_TABLE_NAME = "monster_encounter_selection_operation"
ADVISORY_LOCK_KEY = 773310030

STATE_COLUMNS = {
    "user_id": ("INTEGER", False),
    "zone_key": ("TEXT", False),
    "cycle_generation": ("INTEGER", False),
    "seen_monster_ids": ("TEXT", False),
    "last_monster_id": ("TEXT", True),
    "last_family_id": ("TEXT", True),
    "policy_version": ("TEXT", False),
    "updated_at": ("TEXT", False),
}

OPERATION_COLUMNS = {
    "user_id": ("INTEGER", False),
    "zone_key": ("TEXT", False),
    "encounter_operation_id": ("TEXT", False),
    "selected_monster_id": ("TEXT", False),
    "encounter_intent": ("TEXT", False),
    "selector_policy_version": ("TEXT", False),
    "cycle_generation_before": ("INTEGER", False),
    "cycle_generation_after": ("INTEGER", False),
    "seen_monster_ids_before": ("TEXT", False),
    "seen_monster_ids_after": ("TEXT", False),
    "last_monster_id_before": ("TEXT", True),
    "last_monster_id_after": ("TEXT", True),
    "last_family_id_before": ("TEXT", True),
    "last_family_id_after": ("TEXT", True),
    "created_at": ("TEXT", False),
    "committed_at": ("TEXT", False),
}

STATE_PRIMARY_KEY = ("user_id", "zone_key")
OPERATION_PRIMARY_KEY = ("user_id", "zone_key", "encounter_operation_id")

INDEX_SPECS = (
    ("idx_monster_selector_state_updated", STATE_TABLE_NAME, ("updated_at",)),
    ("idx_monster_selector_operation_created", OPERATION_TABLE_NAME, ("created_at",)),
    (
        "idx_monster_selector_operation_selected",
        OPERATION_TABLE_NAME,
        ("selected_monster_id",),
    ),
)


class MigrationError(RuntimeError):
    """Base class for explicit migration/schema failures."""


class SchemaMismatch(MigrationError):
    """An existing F010 table does not match the additive contract."""


def _raw_connection(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw_connection(conn).__class__.__module__.startswith("sqlite3")


def _placeholder(conn: Any) -> str:
    return "?" if _is_sqlite(conn) else "%s"


def _row_value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _normalize_type(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _execute(conn: Any, sql: str, params: Iterable[Any] | None = None) -> Any:
    if not hasattr(conn, "execute"):
        cursor = conn.cursor()
        if params is None:
            cursor.execute(sql)
        else:
            cursor.execute(sql, tuple(params))
        return cursor
    if params is None:
        return conn.execute(sql)
    return conn.execute(sql, tuple(params))


def _sqlite_index_columns(conn: Any, index_name: str) -> tuple[str, ...]:
    rows = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
    return tuple(str(_row_value(row, 2, "name")) for row in rows)


def _postgres_table_columns(conn: Any, table_name: str) -> list[Any]:
    marker = _placeholder(conn)
    return _execute(
        conn,
        """SELECT column_name, data_type, is_nullable
             FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position""".replace("%s", marker),
        (table_name,),
    ).fetchall()


def _postgres_primary_key(conn: Any, table_name: str) -> tuple[str, ...]:
    marker = _placeholder(conn)
    rows = _execute(
        conn,
        """SELECT a.attname
             FROM pg_index i
             JOIN pg_class t ON t.oid = i.indrelid
             JOIN pg_namespace n ON n.oid = t.relnamespace
             JOIN pg_attribute a ON a.attrelid = t.oid
                               AND a.attnum = ANY(i.indkey)
            WHERE n.nspname = 'public' AND t.relname = %s AND i.indisprimary
            ORDER BY array_position(i.indkey, a.attnum)""".replace("%s", marker),
        (table_name,),
    ).fetchall()
    return tuple(str(_row_value(row, 0, "attname")) for row in rows)


def _validate_table_sqlite(
    conn: Any,
    table_name: str,
    expected_columns: dict[str, tuple[str, bool]],
    primary_key: tuple[str, ...],
) -> dict[str, Any]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    if not rows:
        return {"table": table_name, "present": False, "missing": [table_name]}
    actual_names = {str(_row_value(row, 1, "name")) for row in rows}
    if actual_names != set(expected_columns):
        raise SchemaMismatch(
            f"{table_name}: columns differ; unexpected="
            f"{sorted(actual_names - set(expected_columns))}, "
            f"missing={sorted(set(expected_columns) - actual_names)}"
        )
    for row in rows:
        name = str(_row_value(row, 1, "name"))
        observed_type = _normalize_type(_row_value(row, 2, "type"))
        observed_nullable = not bool(_row_value(row, 3, "notnull"))
        expected_type, expected_nullable = expected_columns[name]
        if (
            observed_type != _normalize_type(expected_type)
            or observed_nullable != expected_nullable
        ):
            raise SchemaMismatch(
                f"{table_name}.{name}: expected type={expected_type} "
                f"nullable={expected_nullable}; observed type={observed_type} "
                f"nullable={observed_nullable}"
            )
    actual_primary = tuple(
        str(_row_value(row, 1, "name"))
        for row in sorted(rows, key=lambda item: int(_row_value(item, 5, "pk")))
        if bool(_row_value(row, 5, "pk"))
    )
    if actual_primary != primary_key:
        raise SchemaMismatch(
            f"{table_name}: primary key differs: {actual_primary!r}"
        )
    return {
        "table": table_name,
        "present": True,
        "missing": [],
        "columns": sorted(actual_names),
    }


def _validate_table_postgres(
    conn: Any,
    table_name: str,
    expected_columns: dict[str, tuple[str, bool]],
    primary_key: tuple[str, ...],
) -> dict[str, Any]:
    rows = _postgres_table_columns(conn, table_name)
    if not rows:
        return {"table": table_name, "present": False, "missing": [table_name]}
    expected_types = {
        name: ("integer" if type_name == "INTEGER" else "text", nullable)
        for name, (type_name, nullable) in expected_columns.items()
    }
    # Timestamp and JSON fields use their PostgreSQL-native types in the
    # operation/state tables.  Their exact expected types are supplied below.
    if table_name == STATE_TABLE_NAME:
        expected_types["seen_monster_ids"] = ("jsonb", False)
        expected_types["updated_at"] = ("timestamp with time zone", False)
    else:
        for name in ("seen_monster_ids_before", "seen_monster_ids_after"):
            expected_types[name] = ("jsonb", False)
        for name in ("created_at", "committed_at"):
            expected_types[name] = ("timestamp with time zone", False)
    found = {str(_row_value(row, 0, "column_name")): row for row in rows}
    if set(found) != set(expected_types):
        raise SchemaMismatch(
            f"{table_name}: columns differ; unexpected="
            f"{sorted(set(found) - set(expected_types))}, "
            f"missing={sorted(set(expected_types) - set(found))}"
        )
    for name, (expected_type, expected_nullable) in expected_types.items():
        row = found[name]
        observed_type = _normalize_type(_row_value(row, 1, "data_type"))
        observed_nullable = str(_row_value(row, 2, "is_nullable")).upper() == "YES"
        if (
            observed_type != _normalize_type(expected_type)
            or observed_nullable != expected_nullable
        ):
            raise SchemaMismatch(
                f"{table_name}.{name}: expected type={expected_type} "
                f"nullable={expected_nullable}; observed type={observed_type} "
                f"nullable={observed_nullable}"
            )
    actual_primary = _postgres_primary_key(conn, table_name)
    if actual_primary != primary_key:
        raise SchemaMismatch(
            f"{table_name}: primary key differs: {actual_primary!r}"
        )
    return {
        "table": table_name,
        "present": True,
        "missing": [],
        "columns": sorted(found),
    }


def validate_schema(conn: Any) -> dict[str, Any]:
    validator = _validate_table_sqlite if _is_sqlite(conn) else _validate_table_postgres
    state = validator(conn, STATE_TABLE_NAME, STATE_COLUMNS, STATE_PRIMARY_KEY)
    operation = validator(
        conn,
        OPERATION_TABLE_NAME,
        OPERATION_COLUMNS,
        OPERATION_PRIMARY_KEY,
    )
    missing = list(state.get("missing", [])) + list(operation.get("missing", []))
    return {
        "schema_version": SCHEMA_VERSION,
        "present": not missing,
        "missing": missing,
        "tables": {STATE_TABLE_NAME: state, OPERATION_TABLE_NAME: operation},
    }


def _create_sqlite_sql() -> tuple[str, str]:
    return (
        f"""CREATE TABLE IF NOT EXISTS {STATE_TABLE_NAME} (
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            cycle_generation INTEGER NOT NULL DEFAULT 0 CHECK (cycle_generation >= 0),
            seen_monster_ids TEXT NOT NULL DEFAULT '[]',
            last_monster_id TEXT,
            last_family_id TEXT,
            policy_version TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, zone_key)
        )""",
        f"""CREATE TABLE IF NOT EXISTS {OPERATION_TABLE_NAME} (
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            encounter_operation_id TEXT NOT NULL,
            selected_monster_id TEXT NOT NULL,
            encounter_intent TEXT NOT NULL CHECK (
                encounter_intent IN ('REGULAR', 'BATTLEFIELD_BOSS')
            ),
            selector_policy_version TEXT NOT NULL,
            cycle_generation_before INTEGER NOT NULL CHECK (cycle_generation_before >= 0),
            cycle_generation_after INTEGER NOT NULL CHECK (cycle_generation_after >= 0),
            seen_monster_ids_before TEXT NOT NULL,
            seen_monster_ids_after TEXT NOT NULL,
            last_monster_id_before TEXT,
            last_monster_id_after TEXT,
            last_family_id_before TEXT,
            last_family_id_after TEXT,
            created_at TEXT NOT NULL,
            committed_at TEXT NOT NULL,
            PRIMARY KEY (user_id, zone_key, encounter_operation_id)
        )""",
    )


def _create_postgres_sql() -> tuple[str, str]:
    return (
        f"""CREATE TABLE IF NOT EXISTS public.{STATE_TABLE_NAME} (
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            cycle_generation INTEGER NOT NULL DEFAULT 0 CHECK (cycle_generation >= 0),
            seen_monster_ids JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
                jsonb_typeof(seen_monster_ids) = 'array'
            ),
            last_monster_id TEXT,
            last_family_id TEXT,
            policy_version TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (user_id, zone_key)
        )""",
        f"""CREATE TABLE IF NOT EXISTS public.{OPERATION_TABLE_NAME} (
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            encounter_operation_id TEXT NOT NULL,
            selected_monster_id TEXT NOT NULL,
            encounter_intent TEXT NOT NULL CHECK (
                encounter_intent IN ('REGULAR', 'BATTLEFIELD_BOSS')
            ),
            selector_policy_version TEXT NOT NULL,
            cycle_generation_before INTEGER NOT NULL CHECK (cycle_generation_before >= 0),
            cycle_generation_after INTEGER NOT NULL CHECK (cycle_generation_after >= 0),
            seen_monster_ids_before JSONB NOT NULL CHECK (
                jsonb_typeof(seen_monster_ids_before) = 'array'
            ),
            seen_monster_ids_after JSONB NOT NULL CHECK (
                jsonb_typeof(seen_monster_ids_after) = 'array'
            ),
            last_monster_id_before TEXT,
            last_monster_id_after TEXT,
            last_family_id_before TEXT,
            last_family_id_after TEXT,
            created_at TIMESTAMPTZ NOT NULL,
            committed_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (user_id, zone_key, encounter_operation_id)
        )""",
    )


def _create_index_sql(name: str, table: str, columns: tuple[str, ...], *, sqlite: bool) -> str:
    qualified_table = table if sqlite else f"public.{table}"
    return f"CREATE INDEX IF NOT EXISTS {name} ON {qualified_table} ({', '.join(columns)})"


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Create and validate the additive F010 schema; caller owns commit."""

    sqlite = _is_sqlite(conn)
    if not sqlite:
        marker = _placeholder(conn)
        _execute(
            conn,
            f"SELECT pg_advisory_xact_lock({marker})",
            (ADVISORY_LOCK_KEY,),
        )
    before = validate_schema(conn)
    if dry_run:
        return {**before, "created": [], "planned_create": before["missing"], "dry_run": True}
    create_sql = _create_sqlite_sql() if sqlite else _create_postgres_sql()
    if not before["tables"][STATE_TABLE_NAME]["present"]:
        _execute(conn, create_sql[0])
    if not before["tables"][OPERATION_TABLE_NAME]["present"]:
        _execute(conn, create_sql[1])
    for index_name, table_name, columns in INDEX_SPECS:
        _execute(
            conn,
            _create_index_sql(index_name, table_name, columns, sqlite=sqlite),
        )
    after = validate_schema(conn)
    if after["missing"]:
        raise SchemaMismatch(f"F010 selector schema missing: {after['missing']}")
    return {
        **after,
        "created": before["missing"],
        "planned_create": [],
        "dry_run": False,
    }


def downgrade_for_isolated_test(conn: Any) -> None:
    """Drop only F010 tables from a disposable test database."""

    prefix = "" if _is_sqlite(conn) else "public."
    _execute(conn, f"DROP TABLE IF EXISTS {prefix}{OPERATION_TABLE_NAME}")
    _execute(conn, f"DROP TABLE IF EXISTS {prefix}{STATE_TABLE_NAME}")


__all__ = [
    "ADVISORY_LOCK_KEY",
    "SCHEMA_VERSION",
    "OPERATION_COLUMNS",
    "OPERATION_PRIMARY_KEY",
    "OPERATION_TABLE_NAME",
    "STATE_COLUMNS",
    "STATE_PRIMARY_KEY",
    "STATE_TABLE_NAME",
    "SchemaMismatch",
    "MigrationError",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
