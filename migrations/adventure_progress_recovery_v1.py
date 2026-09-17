"""Additive, owner-gated ledger for incident Adventure make-whole credit.

This migration is deliberately separate from ``review_log``, ``srs_cards``,
Map Battle tables, and the Adventure reward/clear tables.  It records an
explicit recovery fact; it never rewrites historical answer provenance and it
never grants a reward or a Lord victory.

The migration does not commit.  The caller owns the transaction so a future
apply can snapshot, insert, verify, or roll back one operation atomically.
"""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "p0_lane_c_adventure_progress_recovery_v2"
TABLE_NAME = "adventure_progress_recovery_ledger"
ADVISORY_LOCK_KEY = 773310041

POLICY_CLASSIFICATION_SERVER_CORRECT = "SERVER_CORRECT"
POLICY_CLASSIFICATION_ALREADY_CREDITED = "ALREADY_CREDITED"
POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING = "CORRECTNESS_AUTHORITY_MISSING"
POLICY_CLASSIFICATION_CANONICAL_IDENTITY_UNRESOLVED = "CANONICAL_IDENTITY_UNRESOLVED"
HISTORICAL_CORRECTNESS_SERVER_CORRECT = "SERVER_CORRECT"
HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT = "UNRESOLVED_DUE_TO_INCIDENT"
OWNER_POLICY_RECOVERY_REASON = "INCIDENT_MAKE_WHOLE_OWNER_POLICY"

EXPECTED_COLUMNS = {
    "id",
    "operation_id",
    "user_id",
    "canonical_question_id",
    "legacy_question_id",
    "zone_key",
    "recovery_reason",
    "provenance",
    "evidence_class",
    "gap_reason",
    "apply_eligible",
    "existing_credit",
    "proposed_recovery_credit",
    "policy_classification",
    "credit_delta",
    "historical_correctness_status",
    "created_at",
}


class MigrationError(RuntimeError):
    """Raised when the additive recovery schema cannot be validated."""


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _columns(conn: Any) -> set[str]:
    if _is_sqlite(conn):
        rows = conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
        return {str(_value(row, 1, "name")) for row in rows}
    rows = conn.execute(
        """SELECT column_name
             FROM information_schema.columns
            WHERE table_schema='public' AND table_name=?""",
        (TABLE_NAME,),
    ).fetchall()
    return {str(_value(row, 0, "column_name")) for row in rows}


def _indexes(conn: Any) -> set[str]:
    if _is_sqlite(conn):
        rows = conn.execute(f"PRAGMA index_list({TABLE_NAME})").fetchall()
        return {str(_value(row, 1, "name")) for row in rows}
    rows = conn.execute(
        """SELECT indexname
             FROM pg_indexes
            WHERE schemaname='public' AND tablename=?""",
        (TABLE_NAME,),
    ).fetchall()
    return {str(_value(row, 0, "indexname")) for row in rows}


def validate_schema(conn: Any) -> dict[str, Any]:
    columns = _columns(conn)
    missing = sorted(EXPECTED_COLUMNS - columns)
    indexes = _indexes(conn) if not missing else set()
    required_indexes = {
        "uq_adventure_recovery_credit",
        "uq_adventure_recovery_operation_record",
    }
    missing_indexes = sorted(required_indexes - indexes) if not missing else []
    if missing or missing_indexes:
        raise MigrationError(
            f"{TABLE_NAME} schema incomplete: columns={missing}, indexes={missing_indexes}"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "table": TABLE_NAME,
        "columns": sorted(columns),
        "indexes": sorted(indexes),
        "missing": [],
    }


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Create/validate the additive ledger without committing the transaction."""

    if _is_sqlite(conn):
        if not dry_run:
            conn.execute(
                f"""CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    canonical_question_id TEXT NOT NULL,
                    legacy_question_id INTEGER NOT NULL,
                    zone_key TEXT NOT NULL,
                    recovery_reason TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    evidence_class TEXT NOT NULL CHECK (evidence_class IN
                        ('PROVEN_RECOVERABLE','ALREADY_CREDITED','UNRESOLVED_EVIDENCE_GAP')),
                    gap_reason TEXT NOT NULL DEFAULT '' CHECK (gap_reason IN
                        ('','ALREADY_CREDITED','CORRECTNESS_AUTHORITY_MISSING',
                         'CANONICAL_IDENTITY_UNRESOLVED')),
                    apply_eligible INTEGER NOT NULL DEFAULT 0
                        CHECK (apply_eligible IN (0,1)),
                    existing_credit INTEGER NOT NULL DEFAULT 0
                        CHECK (existing_credit IN (0,1)),
                    proposed_recovery_credit INTEGER NOT NULL DEFAULT 0
                        CHECK (proposed_recovery_credit IN (0,1)),
                    policy_classification TEXT NOT NULL DEFAULT 'SERVER_CORRECT'
                        CHECK (policy_classification IN
                            ('SERVER_CORRECT','ALREADY_CREDITED',
                             'CORRECTNESS_AUTHORITY_MISSING',
                             'CANONICAL_IDENTITY_UNRESOLVED')),
                    credit_delta INTEGER NOT NULL DEFAULT 0
                        CHECK (credit_delta IN (0,1)),
                    historical_correctness_status TEXT NOT NULL DEFAULT 'SERVER_CORRECT'
                        CHECK (historical_correctness_status IN
                            ('SERVER_CORRECT','ALREADY_CREDITED',
                             'UNRESOLVED_DUE_TO_INCIDENT')),
                    created_at TEXT NOT NULL,
                    CHECK (
                        (evidence_class='PROVEN_RECOVERABLE' AND gap_reason=''
                         AND apply_eligible=1
                         AND existing_credit=0 AND proposed_recovery_credit=1
                         AND policy_classification='SERVER_CORRECT'
                         AND credit_delta=1
                         AND historical_correctness_status='SERVER_CORRECT')
                        OR (evidence_class='ALREADY_CREDITED' AND apply_eligible=0
                            AND gap_reason='ALREADY_CREDITED'
                            AND existing_credit=1 AND proposed_recovery_credit=0
                            AND policy_classification='ALREADY_CREDITED'
                            AND credit_delta=0
                            AND historical_correctness_status='ALREADY_CREDITED')
                        OR (evidence_class='UNRESOLVED_EVIDENCE_GAP' AND apply_eligible=0
                            AND gap_reason='CORRECTNESS_AUTHORITY_MISSING'
                            AND existing_credit=0 AND proposed_recovery_credit=0
                            AND policy_classification='CORRECTNESS_AUTHORITY_MISSING'
                            AND credit_delta=0
                            AND historical_correctness_status='UNRESOLVED_DUE_TO_INCIDENT')
                        OR (evidence_class='UNRESOLVED_EVIDENCE_GAP'
                            AND gap_reason='CORRECTNESS_AUTHORITY_MISSING'
                            AND apply_eligible=1 AND existing_credit=0
                            AND proposed_recovery_credit=1
                            AND policy_classification='CORRECTNESS_AUTHORITY_MISSING'
                            AND credit_delta=1
                            AND historical_correctness_status='UNRESOLVED_DUE_TO_INCIDENT')
                        OR (evidence_class='UNRESOLVED_EVIDENCE_GAP' AND apply_eligible=0
                            AND gap_reason='CANONICAL_IDENTITY_UNRESOLVED'
                            AND existing_credit=0 AND proposed_recovery_credit=0
                            AND policy_classification='CANONICAL_IDENTITY_UNRESOLVED'
                            AND credit_delta=0
                            AND historical_correctness_status='UNRESOLVED_DUE_TO_INCIDENT')
                    )
                )"""
            )
            conn.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS uq_adventure_recovery_credit
                   ON adventure_progress_recovery_ledger(
                       user_id, canonical_question_id, zone_key, recovery_reason
                   )"""
            )
            conn.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS uq_adventure_recovery_operation_record
                   ON adventure_progress_recovery_ledger(
                       operation_id, user_id, canonical_question_id, zone_key
                   )"""
            )
    else:
        conn.execute("SELECT pg_advisory_xact_lock(?)", (ADVISORY_LOCK_KEY,))
        if not dry_run:
            conn.execute(
                f"""CREATE TABLE IF NOT EXISTS public.{TABLE_NAME} (
                    id BIGSERIAL PRIMARY KEY,
                    operation_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    canonical_question_id TEXT NOT NULL,
                    legacy_question_id INTEGER NOT NULL,
                    zone_key TEXT NOT NULL,
                    recovery_reason TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    evidence_class TEXT NOT NULL CHECK (evidence_class IN
                        ('PROVEN_RECOVERABLE','ALREADY_CREDITED','UNRESOLVED_EVIDENCE_GAP')),
                    gap_reason TEXT NOT NULL DEFAULT '' CHECK (gap_reason IN
                        ('','ALREADY_CREDITED','CORRECTNESS_AUTHORITY_MISSING',
                         'CANONICAL_IDENTITY_UNRESOLVED')),
                    apply_eligible INTEGER NOT NULL DEFAULT 0
                        CHECK (apply_eligible IN (0,1)),
                    existing_credit INTEGER NOT NULL DEFAULT 0
                        CHECK (existing_credit IN (0,1)),
                    proposed_recovery_credit INTEGER NOT NULL DEFAULT 0
                        CHECK (proposed_recovery_credit IN (0,1)),
                    policy_classification TEXT NOT NULL DEFAULT 'SERVER_CORRECT'
                        CHECK (policy_classification IN
                            ('SERVER_CORRECT','ALREADY_CREDITED',
                             'CORRECTNESS_AUTHORITY_MISSING',
                             'CANONICAL_IDENTITY_UNRESOLVED')),
                    credit_delta INTEGER NOT NULL DEFAULT 0
                        CHECK (credit_delta IN (0,1)),
                    historical_correctness_status TEXT NOT NULL DEFAULT 'SERVER_CORRECT'
                        CHECK (historical_correctness_status IN
                            ('SERVER_CORRECT','ALREADY_CREDITED',
                             'UNRESOLVED_DUE_TO_INCIDENT')),
                    created_at TEXT NOT NULL,
                    CHECK (
                        (evidence_class='PROVEN_RECOVERABLE' AND gap_reason=''
                         AND apply_eligible=1
                         AND existing_credit=0 AND proposed_recovery_credit=1
                         AND policy_classification='SERVER_CORRECT'
                         AND credit_delta=1
                         AND historical_correctness_status='SERVER_CORRECT')
                        OR (evidence_class='ALREADY_CREDITED' AND apply_eligible=0
                            AND gap_reason='ALREADY_CREDITED'
                            AND existing_credit=1 AND proposed_recovery_credit=0
                            AND policy_classification='ALREADY_CREDITED'
                            AND credit_delta=0
                            AND historical_correctness_status='ALREADY_CREDITED')
                        OR (evidence_class='UNRESOLVED_EVIDENCE_GAP' AND apply_eligible=0
                            AND gap_reason='CORRECTNESS_AUTHORITY_MISSING'
                            AND existing_credit=0 AND proposed_recovery_credit=0
                            AND policy_classification='CORRECTNESS_AUTHORITY_MISSING'
                            AND credit_delta=0
                            AND historical_correctness_status='UNRESOLVED_DUE_TO_INCIDENT')
                        OR (evidence_class='UNRESOLVED_EVIDENCE_GAP'
                            AND gap_reason='CORRECTNESS_AUTHORITY_MISSING'
                            AND apply_eligible=1 AND existing_credit=0
                            AND proposed_recovery_credit=1
                            AND policy_classification='CORRECTNESS_AUTHORITY_MISSING'
                            AND credit_delta=1
                            AND historical_correctness_status='UNRESOLVED_DUE_TO_INCIDENT')
                        OR (evidence_class='UNRESOLVED_EVIDENCE_GAP' AND apply_eligible=0
                            AND gap_reason='CANONICAL_IDENTITY_UNRESOLVED'
                            AND existing_credit=0 AND proposed_recovery_credit=0
                            AND policy_classification='CANONICAL_IDENTITY_UNRESOLVED'
                            AND credit_delta=0
                            AND historical_correctness_status='UNRESOLVED_DUE_TO_INCIDENT')
                    )
                )"""
            )
            conn.execute(
                f"""CREATE UNIQUE INDEX IF NOT EXISTS uq_adventure_recovery_credit
                   ON public.{TABLE_NAME}(
                       user_id, canonical_question_id, zone_key, recovery_reason
                   )"""
            )
            conn.execute(
                f"""CREATE UNIQUE INDEX IF NOT EXISTS uq_adventure_recovery_operation_record
                   ON public.{TABLE_NAME}(
                       operation_id, user_id, canonical_question_id, zone_key
                   )"""
            )
    if dry_run:
        # A dry-run against an absent table is useful to report as absent; it
        # must not create a schema as a side effect.
        return {
            "schema_version": SCHEMA_VERSION,
            "table": TABLE_NAME,
            "dry_run": True,
            "present": bool(_columns(conn)),
        }
    return {**validate_schema(conn), "dry_run": False}


__all__ = [
    "ADVISORY_LOCK_KEY",
    "EXPECTED_COLUMNS",
    "HISTORICAL_CORRECTNESS_SERVER_CORRECT",
    "HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT",
    "MigrationError",
    "OWNER_POLICY_RECOVERY_REASON",
    "POLICY_CLASSIFICATION_ALREADY_CREDITED",
    "POLICY_CLASSIFICATION_CANONICAL_IDENTITY_UNRESOLVED",
    "POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING",
    "POLICY_CLASSIFICATION_SERVER_CORRECT",
    "SCHEMA_VERSION",
    "TABLE_NAME",
    "upgrade",
    "validate_schema",
]
