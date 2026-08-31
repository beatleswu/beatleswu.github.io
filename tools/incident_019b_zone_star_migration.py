"""Owner-gated executor for the Incident019B Zone-star schema.

This tool is deliberately separate from application startup and from the
historical compatibility-baseline runner.  Inspection is the default mode.
Execution requires an explicit database target, the exact migration id, the
exact canonical source SHA, ``--execute``, and the exact Production migration
owner gate.

The Zone-star migration itself is schema-only.  This tool owns the separate,
non-gameplay receipt table and the transaction that surrounds both DDL and the
receipt write.  It never performs a historical compatibility capture or a
gameplay data backfill.
"""

from __future__ import annotations

import argparse
from contextlib import suppress
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from migrations.adventure_zone_star_progression_v1 import (  # noqa: E402
    EARNINGS_TABLE_NAME,
    INDEX_SPECS,
    PROGRESS_TABLE_NAME,
    SCHEMA_VERSION,
    SchemaMismatch,
    upgrade,
    validate_schema,
)


MIGRATION_ID = "incident019b_adventure_zone_star_progression_v1"
OWNER_GATE = "GO_PRODUCTION_DB_MIGRATION"
EXPECTED_MIGRATION_SHA256 = (
    "1f8e0fc2f36f449db0b890f13d80a1530316f641378b20a5c3010f0563e2cfc4"
)
RECEIPT_TABLE_NAME = "incident019b_zone_star_migration_receipt"
RECEIPT_STATUSES = ("STARTED", "APPLIED", "FAILED")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)

_BOSS_COLUMNS = (
    "user_id",
    "zone_key",
    "cleared",
    "stars",
    "attempts",
    "best_score",
    "cooldown_until_seen",
    "last_attempt_at",
    "cleared_at",
    "updated_at",
)
_HISTORICAL_COLUMNS = (
    "user_id",
    "question_id",
    "baseline_version",
    "source_mask",
    "entitlement_source",
    "captured_at",
    "cutoff_literal",
)
_HISTORICAL_BASELINE_COLUMNS = (
    "baseline_version",
    "cutoff_literal",
    "captured_at",
    "frozen_at",
    "status",
    "membership_count",
)
_ZONE_COLUMNS = ("user_id", "zone_key", "earned_stars", "updated_at")
_EARNING_COLUMNS = (
    "user_id",
    "zone_key",
    "event_id",
    "star_number",
    "source",
    "earned_at",
)

_RECEIPT_COLUMNS = {
    "migration_id": ("text", False),
    "migration_version": ("text", False),
    "migration_sha256": ("text", False),
    "canonical_source_sha": ("text", False),
    "applied_at": ("text", False),
    "execution_status": ("text", False),
    "schema_fingerprint": ("text", False),
    "pre_state_fingerprint": ("text", False),
    "post_state_fingerprint": ("text", False),
}


class RunnerError(RuntimeError):
    """Base class for fail-closed runner errors."""


class ReceiptConflict(RunnerError):
    """A receipt is incomplete, duplicated, or identifies another artifact."""


class DataMutationDetected(RunnerError):
    """The schema-only operation changed application data."""


class RunnerUsageError(RunnerError):
    """The operator did not provide an exact execution contract."""


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _table_ref(conn: Any, table_name: str) -> str:
    return table_name if _is_sqlite(conn) else f"public.{table_name}"


def _row_value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _table_exists(conn: Any, table_name: str) -> bool:
    if _is_sqlite(conn):
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name=?""",
            (table_name,),
        ).fetchone()
    return row is not None


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def migration_sha256() -> str:
    path = REPOSITORY_ROOT / "migrations" / "adventure_zone_star_progression_v1.py"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_sha(value: str, *, source: bool = False) -> str:
    normalized = str(value or "").strip().lower()
    pattern = _SOURCE_SHA_RE if source else _SHA256_RE
    if not pattern.fullmatch(normalized):
        kind = "canonical source SHA" if source else "SHA-256"
        raise RunnerUsageError(f"invalid {kind}")
    return normalized


def _receipt_create_sql(conn: Any) -> str:
    prefix = "" if _is_sqlite(conn) else "public."
    return f"""CREATE TABLE IF NOT EXISTS {prefix}{RECEIPT_TABLE_NAME} (
        migration_id TEXT PRIMARY KEY NOT NULL,
        migration_version TEXT NOT NULL,
        migration_sha256 TEXT NOT NULL,
        canonical_source_sha TEXT NOT NULL,
        applied_at TEXT NOT NULL,
        execution_status TEXT NOT NULL CHECK (execution_status IN
            ('STARTED','APPLIED','FAILED')),
        schema_fingerprint TEXT NOT NULL,
        pre_state_fingerprint TEXT NOT NULL,
        post_state_fingerprint TEXT NOT NULL
    )"""


def _columns(conn: Any, table_name: str) -> dict[str, tuple[str, bool]]:
    if _is_sqlite(conn):
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {
            str(_row_value(row, 1, "name")): (
                " ".join(str(_row_value(row, 2, "type") or "").lower().split()),
                not bool(_row_value(row, 3, "notnull")),
            )
            for row in rows
        }
    rows = conn.execute(
        """SELECT column_name, data_type, is_nullable
             FROM information_schema.columns
            WHERE table_schema='public' AND table_name=?
            ORDER BY ordinal_position""",
        (table_name,),
    ).fetchall()
    return {
        str(_row_value(row, 0, "column_name")): (
            " ".join(str(_row_value(row, 1, "data_type") or "").lower().split()),
            str(_row_value(row, 2, "is_nullable")).upper() == "YES",
        )
        for row in rows
    }


def _primary_columns(conn: Any, table_name: str) -> tuple[str, ...]:
    if _is_sqlite(conn):
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return tuple(
            str(_row_value(row, 1, "name"))
            for row in sorted(rows, key=lambda item: int(_row_value(item, 5, "pk") or 0))
            if int(_row_value(row, 5, "pk") or 0) > 0
        )
    rows = conn.execute(
        """SELECT a.attname
             FROM pg_constraint c
             JOIN pg_class t ON t.oid=c.conrelid
             JOIN pg_namespace n ON n.oid=t.relnamespace
             JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
             JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=k.attnum
            WHERE n.nspname='public' AND t.relname=? AND c.contype='p'
            ORDER BY k.ord""",
        (table_name,),
    ).fetchall()
    return tuple(str(_row_value(row, 0, "attname")) for row in rows)


def _unique_columns(conn: Any, table_name: str) -> list[tuple[str, ...]]:
    if _is_sqlite(conn):
        rows = conn.execute(f"PRAGMA index_list({table_name})").fetchall()
        result = []
        for row in rows:
            if not bool(_row_value(row, 2, "unique")):
                continue
            name = str(_row_value(row, 1, "name"))
            columns = conn.execute(f"PRAGMA index_info({name})").fetchall()
            result.append(
                tuple(str(_row_value(item, 2, "name")) for item in columns)
            )
        return result
    rows = conn.execute(
        """SELECT array_agg(a.attname ORDER BY k.ord)
             FROM pg_constraint c
             JOIN pg_class t ON t.oid=c.conrelid
             JOIN pg_namespace n ON n.oid=t.relnamespace
             JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
             JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=k.attnum
            WHERE n.nspname='public' AND t.relname=? AND c.contype='u'
            GROUP BY c.oid""",
        (table_name,),
    ).fetchall()
    result = []
    for row in rows:
        value = _row_value(row, 0, "array_agg")
        result.append(tuple(str(item) for item in (value or [])))
    return result


def _constraint_definitions(conn: Any, table_name: str) -> list[str]:
    if _is_sqlite(conn):
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return [str(_row_value(row, 0, "sql"))] if row else []
    rows = conn.execute(
        """SELECT pg_get_constraintdef(c.oid)
             FROM pg_constraint c
             JOIN pg_class t ON t.oid=c.conrelid
             JOIN pg_namespace n ON n.oid=t.relnamespace
            WHERE n.nspname='public' AND t.relname=?""",
        (table_name,),
    ).fetchall()
    return [str(_row_value(row, 0, "pg_get_constraintdef")) for row in rows]


def _normalized_definitions(definitions: Iterable[str]) -> str:
    return " ".join(
        " ".join(re.sub(r"\s+", " ", str(value).lower().replace('"', "")).split())
        for value in definitions
    )


def _require_definition(text: str, *fragments: str) -> None:
    if not all(fragment.lower() in text for fragment in fragments):
        raise SchemaMismatch(f"expected constraint definition missing: {fragments}")


def _verify_constraints(conn: Any) -> dict[str, Any]:
    progress_pk = _primary_columns(conn, PROGRESS_TABLE_NAME)
    earnings_pk = _primary_columns(conn, EARNINGS_TABLE_NAME)
    if progress_pk != ("user_id", "zone_key"):
        raise SchemaMismatch(f"{PROGRESS_TABLE_NAME}: primary key differs")
    if earnings_pk != ("user_id", "event_id"):
        raise SchemaMismatch(f"{EARNINGS_TABLE_NAME}: primary key differs")

    if ("user_id", "zone_key", "star_number") not in _unique_columns(
        conn, EARNINGS_TABLE_NAME
    ):
        raise SchemaMismatch(f"{EARNINGS_TABLE_NAME}: earning uniqueness differs")

    progress_defs = _normalized_definitions(
        _constraint_definitions(conn, PROGRESS_TABLE_NAME)
    )
    earnings_defs = _normalized_definitions(
        _constraint_definitions(conn, EARNINGS_TABLE_NAME)
    )
    if "earned_stars" not in progress_defs or not (
        ("between 0 and 3" in progress_defs)
        or ("earned_stars >= 0" in progress_defs and "earned_stars <= 3" in progress_defs)
    ):
        raise SchemaMismatch(f"{PROGRESS_TABLE_NAME}: star range check missing")
    if "star_number" not in earnings_defs or not (
        ("between 1 and 3" in earnings_defs)
        or ("star_number >= 1" in earnings_defs and "star_number <= 3" in earnings_defs)
    ):
        raise SchemaMismatch(f"{EARNINGS_TABLE_NAME}: earning range check missing")
    _require_definition(
        earnings_defs,
        "authoritative_adventure_answer",
        "authoritative_boss_clear",
    )
    return {
        "progress_primary_key": list(progress_pk),
        "earnings_primary_key": list(earnings_pk),
        "earnings_unique": ["user_id", "zone_key", "star_number"],
        "checks": ["earned_stars 0..3", "star_number 1..3", "source allowlist"],
    }


def verify_expected_schema(conn: Any) -> dict[str, Any]:
    """Verify the migration module's exact tables plus PK/UNIQUE/CHECK rules."""

    result = validate_schema(conn)
    if not result.get("valid"):
        raise SchemaMismatch(f"Zone-star schema incomplete: {result}")
    constraints = _verify_constraints(conn)
    return {
        "schema_version": SCHEMA_VERSION,
        "tables": [PROGRESS_TABLE_NAME, EARNINGS_TABLE_NAME],
        "indexes": sorted(name for name, _table, _columns in INDEX_SPECS),
        "constraints": constraints,
    }


def schema_fingerprint(conn: Any) -> str:
    return _sha256_json(verify_expected_schema(conn))


def _table_rows(
    conn: Any,
    table_name: str,
    columns: tuple[str, ...],
) -> dict[str, Any]:
    present = _table_exists(conn, table_name)
    if not present:
        rows: list[list[Any]] = []
    else:
        ref = _table_ref(conn, table_name)
        selected = ", ".join(columns)
        rows = [
            [_row_value(row, index, column) for index, column in enumerate(columns)]
            for row in conn.execute(f"SELECT {selected} FROM {ref}").fetchall()
        ]
    canonical = sorted(
        rows,
        key=lambda row: json.dumps(row, sort_keys=True, default=str, separators=(",", ":")),
    )
    return {
        "present": present,
        "row_count": len(canonical),
        "row_sha256": _sha256_json(canonical),
    }


def _count_table(conn: Any, table_name: str) -> int:
    if not _table_exists(conn, table_name):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM {_table_ref(conn, table_name)}").fetchone()[0])


def _boss_visible_distribution(conn: Any) -> dict[str, int]:
    if not _table_exists(conn, "adventure_boss_progress"):
        return {}
    rows = conn.execute(
        """SELECT CASE
                 WHEN stars < 0 THEN '0'
                 WHEN stars > 3 THEN '3'
                 ELSE CAST(stars AS TEXT)
               END AS visible_stars, COUNT(*)
          FROM adventure_boss_progress
         GROUP BY 1
         ORDER BY 1"""
    ).fetchall()
    return {str(_row_value(row, 0, "visible_stars")): int(_row_value(row, 1, "count")) for row in rows}


def _zone_visible_distribution(conn: Any) -> dict[str, int]:
    if not _table_exists(conn, PROGRESS_TABLE_NAME):
        return {}
    rows = conn.execute(
        f"""SELECT CAST(earned_stars AS TEXT) AS visible_stars, COUNT(*)
              FROM {_table_ref(conn, PROGRESS_TABLE_NAME)}
             GROUP BY 1
             ORDER BY 1"""
    ).fetchall()
    return {
        str(_row_value(row, 0, "visible_stars")): int(_row_value(row, 1, "count"))
        for row in rows
    }


def snapshot_state(conn: Any) -> dict[str, Any]:
    """Capture aggregate/hash state without exposing account identifiers."""

    data = {
        "users_rows": _count_table(conn, "users"),
        "review_log_rows": _count_table(conn, "review_log"),
        "srs_cards_rows": _count_table(conn, "srs_cards"),
        "boss_progress": _table_rows(conn, "adventure_boss_progress", _BOSS_COLUMNS),
        "boss_visible_distribution": _boss_visible_distribution(conn),
        "zone_visible_distribution": _zone_visible_distribution(conn),
        "historical_mastery": _table_rows(
            conn, "adventure_historical_mastery", _HISTORICAL_COLUMNS
        ),
        "historical_baseline": _table_rows(
            conn,
            "adventure_historical_mastery_baseline",
            _HISTORICAL_BASELINE_COLUMNS,
        ),
        "historical_compatibility_rows": {
            "mastery": _count_table(conn, "adventure_historical_mastery"),
            "baseline": _count_table(conn, "adventure_historical_mastery_baseline"),
        },
        "zone_progress": _table_rows(conn, PROGRESS_TABLE_NAME, _ZONE_COLUMNS),
        "zone_earnings": _table_rows(conn, EARNINGS_TABLE_NAME, _EARNING_COLUMNS),
    }
    fingerprint_data = json.loads(json.dumps(data, default=str))
    for value in fingerprint_data.values():
        if isinstance(value, dict):
            value.pop("present", None)
    return {"fingerprint": _sha256_json(fingerprint_data), "data": data}


def _receipt_columns_valid(conn: Any) -> None:
    found = _columns(conn, RECEIPT_TABLE_NAME)
    if found != _RECEIPT_COLUMNS:
        raise ReceiptConflict("receipt schema columns differ")
    if _primary_columns(conn, RECEIPT_TABLE_NAME) != ("migration_id",):
        raise ReceiptConflict("receipt primary key differs")
    definitions = _normalized_definitions(
        _constraint_definitions(conn, RECEIPT_TABLE_NAME)
    )
    if not all(status.lower() in definitions for status in RECEIPT_STATUSES):
        raise ReceiptConflict("receipt status constraint differs")


def _ensure_receipt_schema(conn: Any) -> None:
    if not _table_exists(conn, RECEIPT_TABLE_NAME):
        conn.execute(_receipt_create_sql(conn))
    _receipt_columns_valid(conn)


def _validate_existing_zone_state(conn: Any) -> None:
    """Reject a partial/conflicting pre-existing Zone-star schema."""

    present = [
        _table_exists(conn, PROGRESS_TABLE_NAME),
        _table_exists(conn, EARNINGS_TABLE_NAME),
    ]
    if any(present) and not all(present):
        raise SchemaMismatch("Zone-star schema is partially present")
    if all(present):
        verify_expected_schema(conn)


def _receipt_row(conn: Any) -> Any:
    return conn.execute(
        f"SELECT migration_id, migration_version, migration_sha256, canonical_source_sha, "
        f"applied_at, execution_status, schema_fingerprint, pre_state_fingerprint, "
        f"post_state_fingerprint FROM {_table_ref(conn, RECEIPT_TABLE_NAME)} "
        "WHERE migration_id=?",
        (MIGRATION_ID,),
    ).fetchone()


def _all_receipt_ids(conn: Any) -> list[str]:
    rows = conn.execute(
        f"SELECT migration_id FROM {_table_ref(conn, RECEIPT_TABLE_NAME)}"
    ).fetchall()
    return [str(_row_value(row, 0, "migration_id")) for row in rows]


def _check_receipt_identity(
    row: Any,
    current_migration_sha: str,
    canonical_source_sha: str,
) -> None:
    migration_id = str(_row_value(row, 0, "migration_id"))
    if migration_id != MIGRATION_ID:
        raise ReceiptConflict("receipt migration id differs")
    if str(_row_value(row, 1, "migration_version")) != SCHEMA_VERSION:
        raise ReceiptConflict("receipt migration version differs")
    if str(_row_value(row, 2, "migration_sha256")).lower() != current_migration_sha:
        raise ReceiptConflict("receipt migration SHA differs")
    if str(_row_value(row, 3, "canonical_source_sha")).lower() != canonical_source_sha:
        raise ReceiptConflict("receipt canonical source SHA differs")
    if str(_row_value(row, 5, "execution_status")) != "APPLIED":
        raise ReceiptConflict("receipt is incomplete or failed")


def inspect_state(conn: Any) -> dict[str, Any]:
    """Read-only inspection; this function never creates a receipt table."""

    state = snapshot_state(conn)
    receipt = {
        "present": _table_exists(conn, RECEIPT_TABLE_NAME),
        "rows": 0,
        "migration_id": None,
        "execution_status": None,
    }
    schema: dict[str, Any]
    if receipt["present"]:
        _receipt_columns_valid(conn)
        ids = _all_receipt_ids(conn)
        receipt["rows"] = len(ids)
        row = _receipt_row(conn)
        if row:
            receipt["migration_id"] = str(_row_value(row, 0, "migration_id"))
            receipt["execution_status"] = str(_row_value(row, 5, "execution_status"))
        if ids != [MIGRATION_ID] and ids:
            raise ReceiptConflict("receipt contains an unexpected migration id")
    try:
        schema = {"valid": True, "fingerprint": schema_fingerprint(conn)}
    except SchemaMismatch as exc:
        schema = {"valid": False, "error": str(exc)}
    return {
        "mode": "inspect",
        "migration_id": MIGRATION_ID,
        "migration_version": SCHEMA_VERSION,
        "migration_sha256": migration_sha256(),
        "receipt": receipt,
        "schema": schema,
        "state": state,
    }


def apply_migration(
    conn: Any,
    *,
    canonical_source_sha: str,
    migration_id: str | None = None,
    owner_gate: str | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    """Apply the additive schema and receipt atomically under explicit control."""

    if not execute or owner_gate != OWNER_GATE or migration_id != MIGRATION_ID:
        raise RunnerUsageError(
            "migration execution requires --execute, the exact migration id, "
            f"and --owner-gate {OWNER_GATE}"
        )
    source_sha = _validate_sha(canonical_source_sha, source=True)
    current_migration_sha = migration_sha256()
    if current_migration_sha != EXPECTED_MIGRATION_SHA256:
        raise RunnerError("migration source SHA differs from the reviewed artifact")

    began = False
    try:
        conn.execute("BEGIN")
        began = True
        _ensure_receipt_schema(conn)
        ids = _all_receipt_ids(conn)
        if ids and ids != [MIGRATION_ID]:
            raise ReceiptConflict("receipt contains an unexpected migration id")
        existing = _receipt_row(conn)
        if existing:
            _check_receipt_identity(existing, current_migration_sha, source_sha)
            observed_schema = schema_fingerprint(conn)
            if str(_row_value(existing, 6, "schema_fingerprint")) != observed_schema:
                raise ReceiptConflict("receipt schema fingerprint differs")
            conn.rollback()
            return {
                "status": "ALREADY_APPLIED",
                "migration_id": MIGRATION_ID,
                "migration_version": SCHEMA_VERSION,
                "migration_sha256": current_migration_sha,
                "receipt_applied_at": str(_row_value(existing, 4, "applied_at")),
                "schema_fingerprint": observed_schema,
            }

        _validate_existing_zone_state(conn)
        before = snapshot_state(conn)
        if before["data"]["zone_progress"]["row_count"] or before["data"]["zone_earnings"]["row_count"]:
            raise ReceiptConflict("Zone-star data exists without a receipt")

        upgrade(conn)
        schema = verify_expected_schema(conn)
        after = snapshot_state(conn)
        if before["fingerprint"] != after["fingerprint"]:
            raise DataMutationDetected("schema migration changed application data")

        applied_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute(
            f"INSERT INTO {_table_ref(conn, RECEIPT_TABLE_NAME)} "
            "(migration_id, migration_version, migration_sha256, canonical_source_sha, "
            "applied_at, execution_status, schema_fingerprint, pre_state_fingerprint, "
            "post_state_fingerprint) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                MIGRATION_ID,
                SCHEMA_VERSION,
                current_migration_sha,
                source_sha,
                applied_at,
                "APPLIED",
                _sha256_json(schema),
                before["fingerprint"],
                after["fingerprint"],
            ),
        )
        conn.commit()
        began = False
        return {
            "status": "APPLIED",
            "migration_id": MIGRATION_ID,
            "migration_version": SCHEMA_VERSION,
            "migration_sha256": current_migration_sha,
            "canonical_source_sha": source_sha,
            "applied_at": applied_at,
            "schema_fingerprint": _sha256_json(schema),
            "pre_state_fingerprint": before["fingerprint"],
            "post_state_fingerprint": after["fingerprint"],
        }
    except Exception:
        if began:
            with suppress(Exception):
                conn.rollback()
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Owner-gated Incident019B Zone-star schema migration"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--inspect", action="store_true", help="read-only inspection (default)")
    mode.add_argument("--dry-run", action="store_true", help="read-only inspection alias")
    parser.add_argument("--execute", action="store_true", help="enable the gated migration")
    parser.add_argument("--owner-gate", default=None)
    parser.add_argument("--migration-id", default=None)
    parser.add_argument("--canonical-source-sha", default=None)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--database-url", default=None, help="PostgreSQL URL; never printed")
    target.add_argument("--sqlite-path", default=None, help="disposable/local SQLite path")
    return parser


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.execute:
        if args.owner_gate != OWNER_GATE:
            parser.error(f"--execute requires --owner-gate {OWNER_GATE}")
        if args.migration_id != MIGRATION_ID:
            parser.error(f"--execute requires --migration-id {MIGRATION_ID}")
        if not args.canonical_source_sha:
            parser.error("--execute requires --canonical-source-sha")
        _validate_sha(args.canonical_source_sha, source=True)
        if args.inspect or args.dry_run:
            parser.error("--execute cannot be combined with inspect/dry-run")
    else:
        if args.owner_gate is not None:
            parser.error("--owner-gate is valid only with --execute")
        if args.migration_id not in (None, MIGRATION_ID):
            parser.error(f"unsupported --migration-id; expected {MIGRATION_ID}")
        if args.canonical_source_sha is not None:
            _validate_sha(args.canonical_source_sha, source=True)


def _connect(args: argparse.Namespace) -> Any:
    if args.sqlite_path is not None:
        if args.execute:
            conn = sqlite3.connect(args.sqlite_path)
        else:
            path = Path(args.sqlite_path).resolve()
            if not path.is_file():
                raise RunnerUsageError("inspect target must already exist")
            conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(args.database_url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw, pooled=False)


def _close(conn: Any) -> None:
    with suppress(Exception):
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    _validate_args(parser, args)
    conn: Any | None = None
    try:
        conn = _connect(args)
        if args.execute:
            result = apply_migration(
                conn,
                canonical_source_sha=args.canonical_source_sha,
                migration_id=args.migration_id,
                owner_gate=args.owner_gate,
                execute=True,
            )
        else:
            conn.execute("BEGIN")
            try:
                result = inspect_state(conn)
            finally:
                conn.rollback()
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        return 0
    except Exception as exc:
        if conn is not None:
            with suppress(Exception):
                conn.rollback()
        print(
            json.dumps(
                {"status": "FAIL_CLOSED", "error_type": type(exc).__name__},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    finally:
        if conn is not None:
            _close(conn)


if __name__ == "__main__":  # pragma: no cover - exercised by the operator
    raise SystemExit(main())


__all__ = [
    "EXPECTED_MIGRATION_SHA256",
    "MIGRATION_ID",
    "OWNER_GATE",
    "RECEIPT_TABLE_NAME",
    "RunnerError",
    "apply_migration",
    "inspect_state",
    "main",
    "migration_sha256",
    "schema_fingerprint",
    "snapshot_state",
    "verify_expected_schema",
]
