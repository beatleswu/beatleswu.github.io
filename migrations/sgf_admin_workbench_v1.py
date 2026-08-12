"""Fail-closed PostgreSQL migration for the SGF Admin Workbench tables.

PR331 currently creates these tables implicitly during application startup with
``CREATE TABLE IF NOT EXISTS``.  That is useful for local compatibility, but it
cannot be the Production migration authority: an existing table with the wrong
shape would be silently accepted.  This module is the narrow, explicit
preflight/migration artifact for the seven additive tables.  It deliberately
does not touch question content, legacy review data, or application flags.

``upgrade`` never commits.  The caller owns the transaction and must commit
only after the returned schema has been validated.  PostgreSQL DDL is
transactional, and the advisory transaction lock prevents two governed runs
from racing each other.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable


SCHEMA_VERSION = "sgf_admin_workbench_v1"
# The review-queue startup schema uses 773310019.  Keep this artifact's lock
# distinct so a migration cannot block or accidentally share that lock.
ADVISORY_LOCK_KEY = 773310020


class MigrationError(RuntimeError):
    """Base class for a migration that must fail closed."""


class SchemaMismatch(MigrationError):
    """An existing table/index/constraint does not match the contract."""


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    data_type: str
    nullable: bool
    default: str | None = None


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[ColumnSpec, ...]
    unique_sets: tuple[tuple[str, ...], ...] = ()


def _c(name: str, data_type: str, nullable: bool = True, default: str | None = None) -> ColumnSpec:
    return ColumnSpec(name, data_type, nullable, default)


# This is intentionally a literal contract derived from PR331's
# sgf_admin_workbench.ensure_sgf_workbench_tables.  Do not add columns or
# foreign keys here without a separate reviewed Workbench schema change.
TABLE_SPECS: "OrderedDict[str, TableSpec]" = OrderedDict(
    (
        (
            "sgf_workbench_reports",
            TableSpec(
                "sgf_workbench_reports",
                (
                    _c("id", "bigint", False, "nextval"),
                    _c("source", "text", False),
                    _c("legacy_report_type", "text"),
                    _c("legacy_report_id", "bigint"),
                    _c("reporter_id", "bigint"),
                    _c("question_id", "bigint", False),
                    _c("record_index", "bigint"),
                    _c("issue_type", "text", False),
                    _c("candidate_move_json", "text"),
                    _c("observed_system_verdict", "text"),
                    _c("gameplay_surface", "text"),
                    _c("sgf_identity", "text"),
                    _c("node_identity", "text"),
                    _c("position_identity", "text", False),
                    _c("board_state_json", "text"),
                    _c("comment", "text", False, ""),
                    _c("question_content_sha256", "text"),
                    _c("source_provenance_json", "text", False, "{}"),
                    _c("external_key", "text", False),
                    _c("created_at", "text", False),
                ),
                (("external_key",),),
            ),
        ),
        (
            "sgf_workbench_review_items",
            TableSpec(
                "sgf_workbench_review_items",
                (
                    _c("id", "bigint", False, "nextval"),
                    _c("group_key", "text", False),
                    _c("question_id", "bigint", False),
                    _c("record_index", "bigint"),
                    _c("issue_type", "text", False),
                    _c("candidate_move_json", "text"),
                    _c("position_identity", "text", False),
                    _c("source_types_json", "text", False),
                    _c("report_count", "bigint", False, "0"),
                    _c("gameplay_surfaces_json", "text", False, "[]"),
                    _c("first_report_at", "text", False),
                    _c("last_report_at", "text", False),
                    _c("authority_json", "text", False, "{}"),
                    _c("provenance_json", "text", False, "{}"),
                    _c("status", "text", False, "OPEN"),
                    _c("stale_reason", "text"),
                    _c("created_at", "text", False),
                    _c("updated_at", "text", False),
                ),
                (("group_key",),),
            ),
        ),
        (
            "sgf_workbench_staged_repairs",
            TableSpec(
                "sgf_workbench_staged_repairs",
                (
                    _c("id", "bigint", False, "nextval"),
                    _c("review_item_id", "bigint", False),
                    _c("reviewer_id", "bigint", False),
                    _c("action", "text", False),
                    _c("reason", "text", False, ""),
                    _c("original_state_json", "text", False),
                    _c("proposed_state_json", "text", False),
                    _c("candidate_move_json", "text"),
                    _c("source_provenance_json", "text", False, "{}"),
                    _c("baseline_sha256", "text"),
                    _c("mutation_key", "text", False),
                    _c("status", "text", False, "STAGED"),
                    _c("created_at", "text", False),
                    _c("updated_at", "text", False),
                ),
                (("mutation_key",),),
            ),
        ),
        (
            "sgf_workbench_batches",
            TableSpec(
                "sgf_workbench_batches",
                (
                    _c("id", "bigint", False, "nextval"),
                    _c("batch_key", "text", False),
                    _c("created_by", "bigint", False),
                    _c("status", "text", False, "STAGED"),
                    _c("manifest_json", "text", False),
                    _c("manifest_sha256", "text", False),
                    _c("staged_count", "bigint", False),
                    _c("created_at", "text", False),
                ),
                (("batch_key",),),
            ),
        ),
        (
            "sgf_workbench_batch_items",
            TableSpec(
                "sgf_workbench_batch_items",
                (
                    _c("id", "bigint", False, "nextval"),
                    _c("batch_id", "bigint", False),
                    _c("staged_repair_id", "bigint", False),
                    _c("order_index", "bigint", False),
                ),
                (("batch_id", "staged_repair_id"),),
            ),
        ),
        (
            "sgf_workbench_audit",
            TableSpec(
                "sgf_workbench_audit",
                (
                    _c("id", "bigint", False, "nextval"),
                    _c("target_type", "text", False),
                    _c("target_id", "bigint"),
                    _c("actor_id", "bigint"),
                    _c("action", "text", False),
                    _c("detail", "text", False, ""),
                    _c("created_at", "text", False),
                ),
            ),
        ),
        (
            "sgf_workbench_direct_versions",
            TableSpec(
                "sgf_workbench_direct_versions",
                (
                    _c("id", "bigint", False, "nextval"),
                    _c("question_id", "bigint", False),
                    _c("record_index", "bigint", False),
                    _c("predecessor_hash", "text", False),
                    _c("new_hash", "text", False),
                    _c("predecessor_version", "text", False),
                    _c("new_version", "text", False),
                    _c("operation_id", "text", False),
                    _c("action_type", "text", False),
                    _c("actor_id", "bigint", False),
                    _c("old_record_json", "text", False),
                    _c("new_record_json", "text", False),
                    _c("validation_result_json", "text", False),
                    _c("rollback_reference", "bigint"),
                    _c("source", "text", False),
                    _c("status", "text", False, "APPLIED"),
                    _c("created_at", "text", False),
                ),
                (("operation_id",),),
            ),
        ),
    )
)


INDEX_SPECS: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    (
        "idx_sgw_reports_group",
        "sgf_workbench_reports",
        ("question_id", "position_identity", "issue_type"),
        "",
    ),
    (
        "idx_sgw_items_status",
        "sgf_workbench_review_items",
        ("status", "updated_at"),
        "DESC",
    ),
    (
        "idx_sgw_items_source",
        "sgf_workbench_review_items",
        ("question_id", "issue_type"),
        "",
    ),
    (
        "idx_sgw_repairs_item",
        "sgf_workbench_staged_repairs",
        ("review_item_id", "status"),
        "",
    ),
    (
        "idx_sgw_audit_target",
        "sgf_workbench_audit",
        ("target_type", "target_id", "created_at"),
        "DESC",
    ),
    (
        "idx_sgw_direct_versions_question",
        "sgf_workbench_direct_versions",
        ("question_id", "record_index", "id"),
        "DESC",
    ),
)


def _run(conn: Any, sql: str, params: Iterable[Any] | None = None) -> list[Any]:
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        if cursor.description is None:
            return []
        return cursor.fetchall()


def _one(conn: Any, sql: str, params: Iterable[Any] | None = None) -> Any:
    rows = _run(conn, sql, params)
    return rows[0][0] if rows else None


def _row_value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _normalize_sql(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower().replace('"', "")).strip()


def _normalize_default(value: str | None) -> str | None:
    if value is None:
        return None
    result = _normalize_sql(value)
    result = re.sub(r"::[a-z0-9_ ]+", "", result)
    return result


def _default_matches(expected: str | None, actual: str | None) -> bool:
    if expected is None:
        return actual is None
    if expected == "nextval":
        return bool(actual and _normalize_sql(actual).startswith("nextval("))
    if expected == "0":
        return _normalize_default(actual) == "0"
    return _normalize_default(actual) == _normalize_default(repr(expected))


def _table_exists(conn: Any, table: str) -> bool:
    return bool(
        _one(
            conn,
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        )
    )


def _column_rows(conn: Any, table: str) -> list[Any]:
    return _run(
        conn,
        "SELECT column_name, data_type, is_nullable, column_default "
        "FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s "
        "ORDER BY ordinal_position",
        (table,),
    )


def _constraint_rows(conn: Any, table: str) -> list[Any]:
    return _run(
        conn,
        "SELECT c.contype, pg_get_constraintdef(c.oid) "
        "FROM pg_constraint c "
        "JOIN pg_class t ON t.oid = c.conrelid "
        "JOIN pg_namespace n ON n.oid = t.relnamespace "
        "WHERE n.nspname = 'public' AND t.relname = %s "
        "ORDER BY c.contype, c.oid",
        (table,),
    )


def _index_rows(conn: Any, table: str) -> list[Any]:
    return _run(
        conn,
        "SELECT idx.relname, i.indisunique, i.indisprimary, "
        "EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.indexrelid), "
        "pg_get_indexdef(i.indexrelid) "
        "FROM pg_class tbl "
        "JOIN pg_namespace n ON n.oid = tbl.relnamespace "
        "JOIN pg_index i ON i.indrelid = tbl.oid "
        "JOIN pg_class idx ON idx.oid = i.indexrelid "
        "WHERE n.nspname = 'public' AND tbl.relname = %s "
        "ORDER BY idx.relname",
        (table,),
    )


def _constraint_sets(conn: Any, table: str) -> tuple[set[str], set[tuple[str, ...]]]:
    primary: set[str] = set()
    unique: set[tuple[str, ...]] = set()
    for row in _constraint_rows(conn, table):
        contype = str(_row_value(row, 0, "contype"))
        definition = _normalize_sql(str(_row_value(row, 1, "pg_get_constraintdef")))
        match = re.search(r"\(([^)]*)\)", definition)
        columns = tuple(part.strip() for part in match.group(1).split(",")) if match else ()
        if contype == "p":
            primary.update(columns)
        elif contype == "u":
            unique.add(columns)
        elif contype in {"f", "c", "x"}:
            raise SchemaMismatch(f"{table}: unexpected constraint {definition}")
    return primary, unique


def _validate_table(conn: Any, spec: TableSpec) -> None:
    if not _table_exists(conn, spec.name):
        return
    actual_rows = _column_rows(conn, spec.name)
    actual = {
        str(_row_value(row, 0, "column_name")): (
            str(_row_value(row, 1, "data_type")),
            str(_row_value(row, 2, "is_nullable")) == "YES",
            _row_value(row, 3, "column_default"),
        )
        for row in actual_rows
    }
    expected = {column.name: (column.data_type, column.nullable, column.default) for column in spec.columns}
    if set(actual) != set(expected):
        raise SchemaMismatch(
            f"{spec.name}: columns differ; unexpected={sorted(set(actual) - set(expected))}, "
            f"missing={sorted(set(expected) - set(actual))}"
        )
    for column in spec.columns:
        data_type, nullable, default = actual[column.name]
        if data_type != column.data_type or nullable != column.nullable or not _default_matches(column.default, default):
            raise SchemaMismatch(
                f"{spec.name}.{column.name}: expected "
                f"type={column.data_type} nullable={column.nullable} default={column.default!r}; "
                f"observed type={data_type} nullable={nullable} default={default!r}"
            )
    primary, unique = _constraint_sets(conn, spec.name)
    if primary != {"id"}:
        raise SchemaMismatch(f"{spec.name}: primary key differs: {sorted(primary)}")
    if unique != set(spec.unique_sets):
        raise SchemaMismatch(f"{spec.name}: unique constraints differ: {sorted(unique)}")

    expected_indexes = {index[0]: index for index in INDEX_SPECS if index[1] == spec.name}
    rows = _index_rows(conn, spec.name)
    by_name = {str(_row_value(row, 0, "relname")): row for row in rows}
    for name, (_, _, columns, direction) in expected_indexes.items():
        row = by_name.get(name)
        if row is None:
            raise SchemaMismatch(f"{spec.name}: missing index {name}")
        definition = _normalize_sql(str(_row_value(row, 4, "pg_get_indexdef")))
        column_text = ", ".join(columns)
        if column_text not in definition or (direction and direction.lower() not in definition):
            raise SchemaMismatch(f"{spec.name}: index {name} has unexpected definition {definition}")
    expected_names = set(expected_indexes)
    for row in rows:
        name = str(_row_value(row, 0, "relname"))
        constraint_backed = bool(_row_value(row, 3, "?column?"))
        if name not in expected_names and not constraint_backed:
            raise SchemaMismatch(f"{spec.name}: unexpected index {name}")


def validate_schema(conn: Any) -> dict[str, Any]:
    """Validate all seven tables without creating anything."""
    for spec in TABLE_SPECS.values():
        _validate_table(conn, spec)
    present = [name for name in TABLE_SPECS if _table_exists(conn, name)]
    missing = [name for name in TABLE_SPECS if name not in present]
    return {"schema_version": SCHEMA_VERSION, "present": present, "missing": missing, "valid": True}


def _create_sql(spec: TableSpec) -> str:
    definitions: list[str] = []
    for column in spec.columns:
        if column.name == "id":
            definitions.append("id BIGSERIAL PRIMARY KEY")
            continue
        sql_type = "BIGINT" if column.data_type == "bigint" else "TEXT"
        definition = f"{column.name} {sql_type}"
        if not column.nullable:
            definition += " NOT NULL"
        if column.default is not None:
            if column.default == "0":
                definition += " DEFAULT 0"
            else:
                escaped = column.default.replace("'", "''")
                definition += " DEFAULT '" + escaped + "'"
        definitions.append(definition)
    for columns in spec.unique_sets:
        definitions.append("UNIQUE (" + ", ".join(columns) + ")")
    return f"CREATE TABLE public.{spec.name} (" + ", ".join(definitions) + ")"


def _create_index_sql(name: str, table: str, columns: tuple[str, ...], direction: str) -> str:
    rendered = ", ".join(columns)
    if direction:
        rendered = ", ".join((*columns[:-1], f"{columns[-1]} {direction}"))
    return f"CREATE INDEX {name} ON public.{table} ({rendered})"


def _index_exists(conn: Any, table: str, name: str) -> bool:
    return bool(
        _one(
            conn,
            "SELECT 1 FROM pg_class idx "
            "JOIN pg_namespace n ON n.oid = idx.relnamespace "
            "JOIN pg_class tbl ON tbl.oid = (SELECT i.indrelid FROM pg_index i WHERE i.indexrelid = idx.oid) "
            "WHERE n.nspname = 'public' AND tbl.relname = %s AND idx.relname = %s",
            (table, name),
        )
    )


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Validate and (unless dry-run) create the seven additive tables.

    The caller must commit the transaction after success.  Any exception must
    be followed by a caller rollback.  No question/corpus path is accepted or
    touched by this API.
    """
    _run(conn, "SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_KEY,))
    before = validate_schema(conn)
    if dry_run:
        return {**before, "created": [], "planned_create": before["missing"], "dry_run": True}
    for spec in TABLE_SPECS.values():
        if spec.name not in before["present"]:
            _run(conn, _create_sql(spec))
    for name, table, columns, direction in INDEX_SPECS:
        if not _index_exists(conn, table, name):
            _run(conn, _create_index_sql(name, table, columns, direction))
    after = validate_schema(conn)
    if after["missing"]:
        raise SchemaMismatch(f"migration incomplete: {after['missing']}")
    return {**after, "created": before["missing"], "planned_create": [], "dry_run": False}


def _connect(database_url: str):
    import psycopg2

    return psycopg2.connect(database_url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--apply", action="store_true", help="commit the additive migration; default is rollback-only dry-run")
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    conn = _connect(args.database_url)
    try:
        result = upgrade(conn, dry_run=not args.apply)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover - exercised by release operator
    raise SystemExit(main())
