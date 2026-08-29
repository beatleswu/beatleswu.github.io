"""Controlled, exact-ledger importer for historical leaderboard evidence.

This module intentionally has no Flask route and no client-facing entrypoint.
The caller must explicitly choose dry-run or execute mode, and the execute
path accepts only the reviewed B070 ledger identity.  It writes only the
dedicated historical evidence table; it never rewrites ``review_log`` or any
player progression/economy table.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from migrations.historical_leaderboard_evidence_v1 import (
    SCHEMA_VERSION,
    SOURCE_PREFIX,
    TABLE_NAME,
    validate_schema,
)


EXPECTED_LEDGER_SHA256 = (
    "03B0001C5D41CB4CDBD49B6C4B7C506D0F8716F6D17D114B8B09EDDFEA5264E5"
)
EXPECTED_SCORE_UNIT_COUNT = 7596
EXPECTED_RAW_EVENT_COUNT = 8803
EXPECTED_RESTORED_ROW_COUNT = 7436
EXPECTED_RESTORED_SCORE_TOTAL = 7436
EXPECTED_RESTORED_USER_COUNT = 27
EXPECTED_EXCLUDED_SCORE_TOTAL = 160
EXPECTED_PERIOD_KEY = "2026-W35"
EXPECTED_POLICY = "POLICY_3_PLAYER_PRESERVATION"
EXPECTED_EVENT_TYPE = "LEADERBOARD_HISTORICAL_EVIDENCE"
EXPECTED_KEY_RE = re.compile(
    r"^b069:weekly:2026-W35:user:(?P<user>[0-9]+):question:(?P<question>[0-9]+)$"
)


class RestorationError(RuntimeError):
    """Raised when an exact restoration precondition is not met."""


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _row_value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _row_dict(row: Any, description: Any = None) -> dict[str, Any]:
    if hasattr(row, "keys"):
        return {str(key): row[key] for key in row.keys()}
    if description:
        return {
            str(column[0]): row[index]
            for index, column in enumerate(description)
        }
    return dict(row)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _json_parameter(conn: Any, value: Mapping[str, Any]) -> Any:
    encoded = _canonical_json(value)
    if _is_sqlite(conn):
        return encoded
    from psycopg2.extras import Json

    return Json(dict(value))


def _table_exists(conn: Any) -> bool:
    if _is_sqlite(conn):
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE_NAME,),
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name=?""",
            (TABLE_NAME,),
        ).fetchone()
    return row is not None


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RestorationError(f"{field} must be non-empty text")
    return value.strip()


def _load_exact_ledger(path: str | Path) -> tuple[dict[str, Any], str]:
    ledger_path = Path(path)
    raw = ledger_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest().upper()
    if digest != EXPECTED_LEDGER_SHA256:
        raise RestorationError(
            f"ledger hash mismatch: expected {EXPECTED_LEDGER_SHA256}, got {digest}"
        )
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RestorationError("ledger is not valid UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise RestorationError("ledger root must be an object")
    return data, digest


def _validate_exact_ledger(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    canonical = data.get("canonical_restoration_event")
    if not isinstance(canonical, Mapping):
        raise RestorationError("canonical_restoration_event is missing")
    if canonical.get("source_prefix") != SOURCE_PREFIX:
        raise RestorationError("unexpected canonical source prefix")
    if canonical.get("event_schema") != SCHEMA_VERSION:
        raise RestorationError("unexpected canonical event schema")
    if canonical.get("event_type") != EXPECTED_EVENT_TYPE:
        raise RestorationError("unexpected canonical event type")
    if canonical.get("native_trusted_source_masquerade") is not False:
        raise RestorationError("native trusted source masquerade must remain false")

    policy = data.get("policy3_contract")
    if not isinstance(policy, Mapping) or policy.get("policy") != EXPECTED_POLICY:
        raise RestorationError("unexpected restoration policy")
    authority = data.get("source_authority")
    if not isinstance(authority, Mapping):
        raise RestorationError("source_authority is missing")
    if authority.get("server_timezone") != "Asia/Taipei":
        raise RestorationError("unexpected server timezone")
    if authority.get("database_timezone") != "UTC":
        raise RestorationError("unexpected database timezone")
    if authority.get("window_start_sql_utc") != "2026-08-23 16:00:00":
        raise RestorationError("unexpected restoration window start")
    if authority.get("window_end_exclusive_sql_utc") != "2026-08-30 16:00:00":
        raise RestorationError("unexpected restoration window end")

    score_units = data.get("score_units")
    raw_events = data.get("raw_event_inventory")
    if not isinstance(score_units, list) or len(score_units) != EXPECTED_SCORE_UNIT_COUNT:
        raise RestorationError("unexpected score unit count")
    if not isinstance(raw_events, list) or len(raw_events) != EXPECTED_RAW_EVENT_COUNT:
        raise RestorationError("unexpected raw event count")

    restored = [row for row in score_units if isinstance(row, Mapping) and row.get("restore") is True]
    excluded = [row for row in score_units if isinstance(row, Mapping) and row.get("restore") is False]
    if len(restored) != EXPECTED_RESTORED_ROW_COUNT:
        raise RestorationError("unexpected restored row count")
    if len(excluded) != EXPECTED_SCORE_UNIT_COUNT - EXPECTED_RESTORED_ROW_COUNT:
        raise RestorationError("unexpected excluded score-unit count")
    if sum(int(row.get("original_score", -1)) for row in restored) != EXPECTED_RESTORED_SCORE_TOTAL:
        raise RestorationError("unexpected restored score total")
    if sum(int(row.get("original_score", -1)) for row in excluded) != EXPECTED_EXCLUDED_SCORE_TOTAL:
        raise RestorationError("unexpected excluded score total")
    if len({int(row["user_id"]) for row in restored}) != EXPECTED_RESTORED_USER_COUNT:
        raise RestorationError("unexpected restored user count")

    keys: set[str] = set()
    for row in score_units:
        if not isinstance(row, Mapping):
            raise RestorationError("score unit must be an object")
        key = _require_text(row.get("canonical_idempotency_key"), "canonical_idempotency_key")
        if key in keys:
            raise RestorationError(f"duplicate score-unit key: {key}")
        keys.add(key)
        match = EXPECTED_KEY_RE.fullmatch(key)
        if not match:
            raise RestorationError(f"unexpected canonical key: {key}")
        if int(row.get("user_id", -1)) != int(match.group("user")):
            raise RestorationError(f"canonical key user mismatch: {key}")
        if int(row.get("question_id", -1)) != int(match.group("question")):
            raise RestorationError(f"canonical key question mismatch: {key}")
        if row.get("canonical_migration_source") != SOURCE_PREFIX:
            raise RestorationError(f"unexpected migration source: {key}")
        if int(row.get("original_score", -1)) != 1:
            raise RestorationError(f"score unit is not one point: {key}")
        if int(row.get("original_grade", -1)) < 3:
            raise RestorationError(f"score unit grade is not qualifying: {key}")
        _require_text(row.get("legacy_event_id_or_stable_identity"), "legacy_event_id_or_stable_identity")
        _require_text(row.get("legacy_source"), "legacy_source")
        _require_text(row.get("original_timestamp"), "original_timestamp")
        if row.get("reconciliation_class") not in {
            "C_LEGACY_ONLY_BUT_PLAUSIBLE",
            "D_DUPLICATE_OR_CONFLICTED",
        }:
            raise RestorationError(f"unexpected reconciliation class: {key}")
        if row.get("restore") is True and row.get("reconciliation_class") != "C_LEGACY_ONLY_BUT_PLAUSIBLE":
            raise RestorationError(f"non-clean row marked restore: {key}")

    counts = data.get("counts")
    if not isinstance(counts, Mapping):
        raise RestorationError("ledger counts are missing")
    if int(counts.get("policy3_restored_event_count", -1)) != EXPECTED_RESTORED_ROW_COUNT:
        raise RestorationError("ledger policy3 row count disagrees")
    if int(counts.get("policy3_restored_score_total", -1)) != EXPECTED_RESTORED_SCORE_TOTAL:
        raise RestorationError("ledger policy3 score disagrees")
    if int(counts.get("duplicate_excluded_score_total", -1)) != EXPECTED_EXCLUDED_SCORE_TOTAL:
        raise RestorationError("ledger duplicate exclusion disagrees")
    if int(counts.get("unattributed_historical_rows_restored", -1)) != 0:
        raise RestorationError("unattributed historical rows must not be restored")
    if int(counts.get("premium_weekly_restored_score", -1)) != 0:
        raise RestorationError("premium_weekly must not be restored")

    return [dict(row) for row in restored]


def _trusted_keys(conn: Any, authority: Mapping[str, Any]) -> set[tuple[int, int]]:
    # reviewed_at is a legacy TEXT column. Current server writers use ISO
    # ``T`` separators, while the B070 packet records SQL timestamps with
    # spaces. Normalize only the comparison boundary; retain each source
    # event timestamp unchanged in the canonical evidence row.
    window_start = str(authority["window_start_sql_utc"]).replace(" ", "T", 1)
    window_end = str(authority["window_end_exclusive_sql_utc"]).replace(" ", "T", 1)
    rows = conn.execute(
        """SELECT DISTINCT user_id, question_id
             FROM review_log
            WHERE reviewed_at >= ? AND reviewed_at < ?
              AND grade >= 3
              AND (source_context LIKE ? OR source_context LIKE ? OR source LIKE ?)""",
        (
            window_start,
            window_end,
            "mbv1:%",
            "daily_d5b:v1:%",
            "rt:%",
        ),
    ).fetchall()
    return {
        (int(_row_value(row, 0, "user_id")), int(_row_value(row, 1, "question_id")))
        for row in rows
    }


def _expected_row(
    row: Mapping[str, Any],
    *,
    authority: Mapping[str, Any],
    policy_version: str,
) -> dict[str, Any]:
    key = str(row["canonical_idempotency_key"])
    return {
        "canonical_idempotency_key": key,
        "user_id": int(row["user_id"]),
        "question_id": int(row["question_id"]),
        "source_prefix": SOURCE_PREFIX,
        "canonical_source": SOURCE_PREFIX + key,
        "legacy_event_id": str(row["legacy_event_id_or_stable_identity"]),
        "legacy_source": str(row["legacy_source"]),
        "event_timestamp": str(row["original_timestamp"]),
        "score": 1,
        "period_key": EXPECTED_PERIOD_KEY,
        "period_start_at": str(authority["window_start_local"]),
        "period_end_at": str(authority["window_end_exclusive_local"]),
        "policy_version": policy_version,
        "reconciliation_class": str(row["reconciliation_class"]),
        "evidence_json": _canonical_json(dict(row)),
    }


def _existing_rows(conn: Any, authority: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""SELECT canonical_idempotency_key, user_id, question_id,
                       source_prefix, canonical_source, legacy_event_id,
                       legacy_source, event_timestamp, score, period_key,
                       period_start_at, period_end_at, policy_version,
                       reconciliation_class, evidence_json
                  FROM {TABLE_NAME}
                 WHERE period_key=? AND source_prefix=?""",
        (EXPECTED_PERIOD_KEY, SOURCE_PREFIX),
    ).fetchall()
    return [_row_dict(row) for row in rows]


_COMPARE_FIELDS = (
    "canonical_idempotency_key",
    "user_id",
    "question_id",
    "source_prefix",
    "canonical_source",
    "legacy_event_id",
    "legacy_source",
    "event_timestamp",
    "score",
    "period_key",
    "period_start_at",
    "period_end_at",
    "policy_version",
    "reconciliation_class",
)


def _normalize_existing(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["user_id"] = int(result["user_id"])
    result["question_id"] = int(result["question_id"])
    result["score"] = int(result["score"])
    evidence = result.get("evidence_json")
    if isinstance(evidence, str):
        try:
            result["evidence_json"] = _canonical_json(json.loads(evidence))
        except json.JSONDecodeError as exc:
            raise RestorationError("existing evidence_json is not valid JSON") from exc
    else:
        result["evidence_json"] = _canonical_json(evidence)
    return result


def restore_ledger(
    conn: Any,
    ledger_path: str | Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Validate and optionally insert the exact reviewed B070 score units.

    The function owns commit/rollback for the operation.  It requires the
    schema to have been installed separately; it never runs DDL.
    """

    data, digest = _load_exact_ledger(ledger_path)
    restored = _validate_exact_ledger(data)
    if not _table_exists(conn):
        raise RestorationError(
            f"{TABLE_NAME} is not installed; run the repository migration first"
        )
    schema = validate_schema(conn)
    if schema.get("missing"):
        raise RestorationError(f"{TABLE_NAME} schema is incomplete")

    authority = data["source_authority"]
    policy_version = str(data["policy3_contract"]["policy"])
    expected = {
        str(row["canonical_idempotency_key"]): _expected_row(
            row, authority=authority, policy_version=policy_version
        )
        for row in restored
    }
    if len(expected) != EXPECTED_RESTORED_ROW_COUNT:
        raise RestorationError("restored canonical key set is not unique")

    missing_users = conn.execute(
        """SELECT id FROM users
            WHERE id IN ({})""".format(
                ",".join("?" for _ in sorted({row["user_id"] for row in expected.values()}))
            ),
        tuple(sorted({row["user_id"] for row in expected.values()})),
    ).fetchall()
    present_users = {
        int(_row_value(row, 0, "id"))
        for row in missing_users
    }
    expected_users = {row["user_id"] for row in expected.values()}
    if present_users != expected_users:
        raise RestorationError(
            f"ledger references missing users: {sorted(expected_users - present_users)}"
        )

    overlap = _trusted_keys(conn, authority) & {
        (row["user_id"], row["question_id"])
        for row in expected.values()
    }
    if overlap:
        raise RestorationError(
            f"restoration overlaps trusted review evidence: {sorted(overlap)[:5]}"
        )

    existing = {
        str(row["canonical_idempotency_key"]): _normalize_existing(row)
        for row in _existing_rows(conn, authority)
    }
    unexpected_existing = set(existing) - set(expected)
    if unexpected_existing:
        raise RestorationError(
            f"existing rows are outside the exact ledger: {sorted(unexpected_existing)[:5]}"
        )
    for key, row in existing.items():
        wanted = expected[key]
        normalized_wanted = {**wanted, "evidence_json": wanted["evidence_json"]}
        if any(row.get(field) != normalized_wanted.get(field) for field in _COMPARE_FIELDS):
            raise RestorationError(f"existing canonical row conflicts with ledger: {key}")
        if row.get("evidence_json") != wanted["evidence_json"]:
            raise RestorationError(f"existing evidence payload conflicts with ledger: {key}")

    insertable = [expected[key] for key in expected if key not in existing]
    result = {
        "ledger_sha256": digest,
        "ledger_restore_row_count": EXPECTED_RESTORED_ROW_COUNT,
        "ledger_restore_score_total": EXPECTED_RESTORED_SCORE_TOTAL,
        "ledger_restored_user_count": EXPECTED_RESTORED_USER_COUNT,
        "existing_rows": len(existing),
        "insertable_rows": len(insertable),
        "insertable_score_total": sum(int(row["score"]) for row in insertable),
        "dry_run": dry_run,
    }
    if dry_run:
        return result

    now = datetime.now(timezone.utc).isoformat()
    try:
        for row in insertable:
            conn.execute(
                f"""INSERT INTO {TABLE_NAME} (
                    canonical_idempotency_key, user_id, question_id,
                    source_prefix, canonical_source, legacy_event_id,
                    legacy_source, event_timestamp, score, period_key,
                    period_start_at, period_end_at, policy_version,
                    reconciliation_class, evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (canonical_idempotency_key) DO NOTHING""",
                (
                    row["canonical_idempotency_key"],
                    row["user_id"],
                    row["question_id"],
                    row["source_prefix"],
                    row["canonical_source"],
                    row["legacy_event_id"],
                    row["legacy_source"],
                    row["event_timestamp"],
                    row["score"],
                    row["period_key"],
                    row["period_start_at"],
                    row["period_end_at"],
                    row["policy_version"],
                    row["reconciliation_class"],
                    _json_parameter(conn, json.loads(row["evidence_json"])),
                    now,
                ),
            )
        # Verify the complete key/payload set before commit so every failure
        # rolls back the whole batch rather than leaving a partial install.
        after = _existing_rows(conn, authority)
        after_by_key = {str(row["canonical_idempotency_key"]): _normalize_existing(row) for row in after}
        if set(after_by_key) != set(expected):
            raise RestorationError("pre-commit canonical key set does not match ledger")
        for key, row in expected.items():
            current = after_by_key[key]
            if any(current.get(field) != row.get(field) for field in _COMPARE_FIELDS):
                raise RestorationError(f"pre-commit canonical row mismatch: {key}")
            if current.get("evidence_json") != row.get("evidence_json"):
                raise RestorationError(f"pre-commit evidence mismatch: {key}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    result.update(
        {
            "inserted_rows": len(insertable),
            "inserted_score_total": sum(int(row["score"]) for row in insertable),
            "final_rows": len(after_by_key),
            "final_score_total": sum(int(row["score"]) for row in after_by_key.values()),
            "final_user_count": len({int(row["user_id"]) for row in after_by_key.values()}),
        }
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, help="exact reviewed B070 ledger JSON")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    from db import get_db

    with get_db() as conn:
        result = restore_ledger(conn, args.ledger, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EXPECTED_LEDGER_SHA256",
    "RestorationError",
    "restore_ledger",
]
