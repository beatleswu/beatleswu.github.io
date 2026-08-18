"""Governed additive migration for the V2-A human review locator.

This table is intentionally separate from Workbench lifecycle statuses.  It
records human observations against a version-scoped record locator and never
becomes canonical question identity or content authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SCHEMA_VERSION = "sgf_human_review_v2a"
TABLE_NAME = "sgf_human_review_state"
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


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _run(conn: Any, statement: str, params: tuple[Any, ...] = ()) -> list[Any]:
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


def validate_schema(conn) -> dict[str, Any]:
    if _is_sqlite(conn):
        rows = conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
        names = {str(row[1] if not hasattr(row, "keys") else row["name"]) for row in rows}
        missing = [spec.name for spec in COLUMNS if spec.name not in names]
        extra = sorted(names - {spec.name for spec in COLUMNS})
        if extra:
            raise SchemaMismatch(f"{TABLE_NAME}: unexpected columns {extra}")
        if rows and not any((row[5] if not hasattr(row, "keys") else row["pk"]) for row in rows if (row[1] if not hasattr(row, "keys") else row["name"]) == "id"):
            raise SchemaMismatch(f"{TABLE_NAME}: id primary key is missing")
        unique_sets = set()
        for index in conn.execute(f"PRAGMA index_list({TABLE_NAME})").fetchall():
            unique_flag = index[2] if not hasattr(index, "keys") else index["unique"]
            if unique_flag:
                index_name = index[1] if not hasattr(index, "keys") else index["name"]
                cols = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
                unique_sets.add(tuple(col[2] if not hasattr(col, "keys") else col["name"] for col in cols))
        if rows and ("reviewer_id", "record_index", "legacy_question_id", "reviewed_record_sha256") not in unique_sets:
            raise SchemaMismatch(f"{TABLE_NAME}: locator uniqueness is missing")
        return {"table": TABLE_NAME, "missing": [TABLE_NAME] if not rows else missing,
                "columns": sorted(names), "schema_version": SCHEMA_VERSION}
    rows = _run(
        conn,
        """SELECT column_name, data_type, is_nullable
           FROM information_schema.columns
          WHERE table_schema=current_schema() AND table_name=%s""",
        (TABLE_NAME,),
    )
    found = {str(_row_value(row, 0, "column_name")): row for row in rows}
    missing = [spec.name for spec in COLUMNS if spec.name not in found]
    extra = sorted(set(found) - {spec.name for spec in COLUMNS})
    if extra:
        raise SchemaMismatch(f"{TABLE_NAME}: unexpected columns {extra}")
    for spec in COLUMNS:
        row = found.get(spec.name)
        if row and ((str(_row_value(row, 1, "data_type")).lower() != spec.data_type) or
                    (str(_row_value(row, 2, "is_nullable")).upper() != ("YES" if spec.nullable else "NO"))):
            raise SchemaMismatch(f"unexpected {TABLE_NAME}.{spec.name} shape")
    constraints = _run(
        conn,
        """SELECT contype, pg_get_constraintdef(oid)
             FROM pg_constraint
            WHERE conrelid = %s::regclass
            ORDER BY contype, oid""",
        (TABLE_NAME,),
    )
    primary = set()
    unique = set()
    for row in constraints:
        kind = str(_row_value(row, 0, "contype"))
        definition = str(_row_value(row, 1, "pg_get_constraintdef"))
        match = __import__("re").search(r"\(([^)]*)\)", definition)
        columns = tuple(part.strip().strip('"') for part in match.group(1).split(",")) if match else ()
        if kind == "p":
            primary.update(columns)
        elif kind == "u":
            unique.add(columns)
        elif kind in {"f", "x"}:
            raise SchemaMismatch(f"{TABLE_NAME}: unexpected destructive constraint {definition}")
    if primary != {"id"} or unique != {("reviewer_id", "record_index", "legacy_question_id", "reviewed_record_sha256")}:
        raise SchemaMismatch(f"{TABLE_NAME}: primary/unique contract differs")
    indexes = _run(
        conn,
        """SELECT indexname, indexdef FROM pg_indexes
            WHERE schemaname=current_schema() AND tablename=%s""",
        (TABLE_NAME,),
    )
    if not any("idx_sgfh_current_locator" == str(_row_value(row, 0, "indexname")) for row in indexes):
        raise SchemaMismatch(f"{TABLE_NAME}: missing idx_sgfh_current_locator")
    return {"table": TABLE_NAME, "missing": [TABLE_NAME] if not rows else missing,
            "columns": sorted(found), "schema_version": SCHEMA_VERSION}


def upgrade(conn) -> dict[str, Any]:
    """Create and validate the additive table; caller owns transaction commit."""
    if _is_sqlite(conn):
        conn.execute(
            """CREATE TABLE IF NOT EXISTS sgf_human_review_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reviewer_id BIGINT NOT NULL,
                record_index BIGINT NOT NULL,
                legacy_question_id TEXT NOT NULL,
                reviewed_record_sha256 TEXT NOT NULL,
                classification TEXT NOT NULL CHECK (classification IN
                    ('CORRECT','WRONG_ROOT','MISSING_ANSWER','MISSING_VARIATION','SPECIAL','UNSURE')),
                reviewed_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(reviewer_id, record_index, legacy_question_id, reviewed_record_sha256)
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sgfh_current_locator "
            "ON sgf_human_review_state(reviewer_id, record_index, legacy_question_id, updated_at DESC)"
        )
    else:
        conn.execute("SELECT pg_advisory_xact_lock(773310021)")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS sgf_human_review_state (
                id BIGSERIAL PRIMARY KEY,
                reviewer_id BIGINT NOT NULL,
                record_index BIGINT NOT NULL,
                legacy_question_id TEXT NOT NULL,
                reviewed_record_sha256 TEXT NOT NULL,
                classification TEXT NOT NULL CHECK (classification IN
                    ('CORRECT','WRONG_ROOT','MISSING_ANSWER','MISSING_VARIATION','SPECIAL','UNSURE')),
                reviewed_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CONSTRAINT uq_sgfh_locator UNIQUE
                    (reviewer_id, record_index, legacy_question_id, reviewed_record_sha256)
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sgfh_current_locator "
            "ON sgf_human_review_state(reviewer_id, record_index, legacy_question_id, updated_at DESC)"
        )
    status = validate_schema(conn)
    if status.get("missing"):
        raise SchemaMismatch("human review schema missing: " + ",".join(status["missing"]))
    return status


def downgrade_for_isolated_test(conn) -> None:
    """Only for disposable fixtures; Production rollback is not automated."""
    conn.execute("DROP TABLE IF EXISTS sgf_human_review_state")
