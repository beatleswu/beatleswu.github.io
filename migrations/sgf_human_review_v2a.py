"""Governed additive migration for V2-A human review state and progress.

Both tables are deliberately separate from the legacy review queue lifecycle
and from canonical question identity/content. Production creation is owned by
this migration; request-time PostgreSQL DDL is never performed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SCHEMA_VERSION = "sgf_human_review_v2a"
TABLE_NAME = "sgf_human_review_state"
PROGRESS_TABLE_NAME = "sgf_human_review_progress"
CLASSIFICATIONS = (
    "CORRECT", "WRONG_ROOT", "MISSING_ANSWER", "MISSING_VARIATION", "SPECIAL", "UNSURE"
)


class MigrationError(RuntimeError):
    pass


class SchemaMismatch(MigrationError):
    pass


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    data_type: str
    nullable: bool


COLUMNS = (
    ColumnSpec("id", "bigint", False),
    ColumnSpec("reviewer_id", "bigint", False),
    ColumnSpec("record_index", "bigint", False),
    ColumnSpec("legacy_question_id", "text", False),
    ColumnSpec("reviewed_record_sha256", "text", False),
    ColumnSpec("classification", "text", False),
    ColumnSpec("reviewed_at", "text", False),
    ColumnSpec("updated_at", "text", False),
)
PROGRESS_COLUMNS = (
    ColumnSpec("id", "bigint", False),
    ColumnSpec("reviewer_id", "bigint", False),
    ColumnSpec("snapshot_sha256", "text", False),
    ColumnSpec("record_index", "bigint", False),
    ColumnSpec("legacy_question_id", "text", False),
    ColumnSpec("record_sha256", "text", False),
    ColumnSpec("revision", "bigint", False),
    ColumnSpec("updated_at", "text", False),
)


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _run(conn, statement: str, params: tuple[Any, ...] = ()) -> list[Any]:
    with conn.cursor() as cursor:
        cursor.execute(statement, params)
        try:
            return cursor.fetchall()
        except Exception:
            return []


def _row_value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _validate_sqlite_table(conn, table: str, columns: tuple[ColumnSpec, ...],
                           unique_contract: tuple[str, ...] | None = None) -> dict[str, Any]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    names = {str(row[1] if not hasattr(row, "keys") else row["name"]) for row in rows}
    expected = {spec.name for spec in columns}
    missing = [spec.name for spec in columns if spec.name not in names]
    extra = sorted(names - expected)
    if extra:
        raise SchemaMismatch(f"{table}: unexpected columns {extra}")
    if rows and not any((row[5] if not hasattr(row, "keys") else row["pk"])
                        for row in rows
                        if (row[1] if not hasattr(row, "keys") else row["name"]) == "id"):
        raise SchemaMismatch(f"{table}: id primary key is missing")
    if rows and unique_contract:
        unique_sets = set()
        for index in conn.execute(f"PRAGMA index_list({table})").fetchall():
            unique_flag = index[2] if not hasattr(index, "keys") else index["unique"]
            if unique_flag:
                index_name = index[1] if not hasattr(index, "keys") else index["name"]
                cols = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
                unique_sets.add(tuple(col[2] if not hasattr(col, "keys") else col["name"] for col in cols))
        if unique_contract not in unique_sets:
            raise SchemaMismatch(f"{table}: required uniqueness is missing")
    return {"table": table, "missing": [table] if not rows else missing,
            "columns": sorted(names)}


def _validate_postgres_table(conn, table: str, columns: tuple[ColumnSpec, ...],
                             unique_contract: tuple[str, ...] | None = None,
                             index_name: str | None = None) -> dict[str, Any]:
    rows = _run(
        conn,
        """SELECT column_name, data_type, is_nullable
             FROM information_schema.columns
            WHERE table_schema=current_schema() AND table_name=%s""",
        (table,),
    )
    found = {str(_row_value(row, 0, "column_name")): row for row in rows}
    expected = {spec.name for spec in columns}
    missing = [spec.name for spec in columns if spec.name not in found]
    extra = sorted(set(found) - expected)
    if extra:
        raise SchemaMismatch(f"{table}: unexpected columns {extra}")
    for spec in columns:
        row = found.get(spec.name)
        if row and ((str(_row_value(row, 1, "data_type")).lower() != spec.data_type) or
                    (str(_row_value(row, 2, "is_nullable")).upper() !=
                     ("YES" if spec.nullable else "NO"))):
            raise SchemaMismatch(f"unexpected {table}.{spec.name} shape")
    if rows and unique_contract:
        constraints = _run(
            conn,
            """SELECT contype, pg_get_constraintdef(oid)
                 FROM pg_constraint
                WHERE conrelid = %s::regclass
                ORDER BY contype, oid""",
            (table,),
        )
        primary, unique = set(), set()
        for row in constraints:
            kind = str(_row_value(row, 0, "contype"))
            definition = str(_row_value(row, 1, "pg_get_constraintdef"))
            match = __import__("re").search(r"\(([^)]*)\)", definition)
            values = tuple(part.strip().strip('"') for part in match.group(1).split(",")) if match else ()
            if kind == "p":
                primary.update(values)
            elif kind == "u":
                unique.add(values)
            elif kind in {"f", "x"}:
                raise SchemaMismatch(f"{table}: unexpected destructive constraint {definition}")
        if primary != {"id"} or unique_contract not in unique:
            raise SchemaMismatch(f"{table}: primary/unique contract differs")
    if rows and index_name:
        indexes = _run(
            conn,
            """SELECT indexname FROM pg_indexes
                WHERE schemaname=current_schema() AND tablename=%s""",
            (table,),
        )
        if not any(index_name == str(_row_value(row, 0, "indexname")) for row in indexes):
            raise SchemaMismatch(f"{table}: missing {index_name}")
    return {"table": table, "missing": [table] if not rows else missing,
            "columns": sorted(found)}


def validate_schema(conn) -> dict[str, Any]:
    state_unique = ("reviewer_id", "record_index", "legacy_question_id", "reviewed_record_sha256")
    progress_unique = ("reviewer_id", "snapshot_sha256")
    if _is_sqlite(conn):
        state = _validate_sqlite_table(conn, TABLE_NAME, COLUMNS, state_unique)
        progress = _validate_sqlite_table(conn, PROGRESS_TABLE_NAME, PROGRESS_COLUMNS, progress_unique)
    else:
        state = _validate_postgres_table(conn, TABLE_NAME, COLUMNS, state_unique, "idx_sgfh_current_locator")
        progress = _validate_postgres_table(conn, PROGRESS_TABLE_NAME, PROGRESS_COLUMNS, progress_unique,
                                            "idx_sgfh_progress_locator")
    return {
        "table": TABLE_NAME,
        "missing": state["missing"] + progress["missing"],
        "columns": state["columns"],
        "progress_columns": progress["columns"],
        "schema_version": SCHEMA_VERSION,
    }


def upgrade(conn) -> dict[str, Any]:
    """Create and validate the two additive V2-A tables; caller owns commit."""
    sqlite = _is_sqlite(conn)
    if not sqlite:
        conn.execute("SELECT pg_advisory_xact_lock(773310021)")
    state_id = "INTEGER PRIMARY KEY AUTOINCREMENT" if sqlite else "BIGSERIAL PRIMARY KEY"
    state_unique = "UNIQUE(reviewer_id, record_index, legacy_question_id, reviewed_record_sha256)" if sqlite else (
        "CONSTRAINT uq_sgfh_locator UNIQUE (reviewer_id, record_index, legacy_question_id, reviewed_record_sha256)"
    )
    conn.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id {state_id}, reviewer_id BIGINT NOT NULL, record_index BIGINT NOT NULL,
        legacy_question_id TEXT NOT NULL, reviewed_record_sha256 TEXT NOT NULL,
        classification TEXT NOT NULL CHECK (classification IN
          ('CORRECT','WRONG_ROOT','MISSING_ANSWER','MISSING_VARIATION','SPECIAL','UNSURE')),
        reviewed_at TEXT NOT NULL, updated_at TEXT NOT NULL, {state_unique}
    )""")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_sgfh_current_locator ON {TABLE_NAME}(reviewer_id, record_index, legacy_question_id, updated_at DESC)")
    progress_id = "INTEGER PRIMARY KEY AUTOINCREMENT" if sqlite else "BIGSERIAL PRIMARY KEY"
    progress_unique = "UNIQUE(reviewer_id, snapshot_sha256)" if sqlite else (
        "CONSTRAINT uq_sgfh_progress UNIQUE (reviewer_id, snapshot_sha256)"
    )
    conn.execute(f"""CREATE TABLE IF NOT EXISTS {PROGRESS_TABLE_NAME} (
        id {progress_id}, reviewer_id BIGINT NOT NULL, snapshot_sha256 TEXT NOT NULL,
        record_index BIGINT NOT NULL, legacy_question_id TEXT NOT NULL,
        record_sha256 TEXT NOT NULL, revision BIGINT NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL, {progress_unique}
    )""")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_sgfh_progress_locator ON {PROGRESS_TABLE_NAME}(reviewer_id, record_index, updated_at DESC)")
    status = validate_schema(conn)
    if status.get("missing"):
        raise SchemaMismatch("human review schema missing: " + ",".join(status["missing"]))
    return status


def downgrade_for_isolated_test(conn) -> None:
    """Only for disposable fixtures; Production rollback is not automated."""
    conn.execute(f"DROP TABLE IF EXISTS {PROGRESS_TABLE_NAME}")
    conn.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
