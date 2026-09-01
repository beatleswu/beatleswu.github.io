"""Controlled Incident 019B compatibility baseline runner and census.

Default mode is read-only preview.  ``--capture-baseline`` is intentionally
explicit and requires the exact version confirmation, ``--execute``, and the
exact ``GO_PRODUCTION_DB_MIGRATION`` owner gate; it is the future governed
migration/backfill entrypoint and is not run by this task.

The output contains only aggregate counts and short deterministic player
pseudonyms.  It never prints connection details or account identifiers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

# Allow the runner to be invoked directly as ``python tools/<runner>.py`` from
# the repository root, as well as imported by a test or another tool.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from adventure_progress_compatibility import (
    BASELINE_VERSION,
    CUTOFF_LITERAL,
    TRUSTED_REVIEW_SOURCE_PREFIXES,
    build_progression_milestone_dry_run,
    build_compatibility_census,
    qualifying_card_memberships,
    trusted_current_memberships,
    populate_frozen_historical_baseline,
)
from adventure_zone_star_progression import PROGRESS_TABLE_NAME


MIGRATION_OWNER_GATE = "GO_PRODUCTION_DB_MIGRATION"
_QUERY_CHUNK_SIZE = 500


def _table_exists(conn: Any, table_name: str) -> bool:
    raw = getattr(conn, "_conn", conn)
    if raw.__class__.__module__.lower().startswith("sqlite3"):
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone() is not None
    return conn.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=?",
        (table_name,),
    ).fetchone() is not None


def _configure_read_only_transaction(conn: Any) -> None:
    """Apply bounded forensic settings before any census SELECT.

    PostgreSQL receives a read-only transaction and short statement/lock
    limits.  SQLite has no equivalent transaction setting, so the helper is a
    no-op there.  The runner still uses one connection and performs no writes
    in preview mode.
    """

    raw = getattr(conn, "_conn", conn)
    if raw.__class__.__module__.lower().startswith("sqlite3"):
        return
    conn.execute("SET TRANSACTION READ ONLY")
    conn.execute("SET LOCAL statement_timeout = '30s'")
    conn.execute("SET LOCAL lock_timeout = '2s'")


def _raw_progress_rows(conn: Any, question_ids: set[int]) -> int:
    if not question_ids:
        return 0
    total = 0
    ordered_ids = sorted(question_ids)
    for start in range(0, len(ordered_ids), _QUERY_CHUNK_SIZE):
        batch = ordered_ids[start : start + _QUERY_CHUNK_SIZE]
        placeholders = ",".join("?" for _ in batch)
        sql = (
            "SELECT COUNT(*) FROM srs_cards "
            f"WHERE progress_credited <> 0 AND question_id IN ({placeholders})"
        )
        total += int(conn.execute(sql, tuple(batch)).fetchone()[0])
    return total


def _last_grade_only_pairs(conn: Any, question_ids: set[int]) -> set[tuple[int, int]]:
    """Return diagnostic-only card pairs excluded from the trusted baseline."""

    if not question_ids:
        return set()
    result: set[tuple[int, int]] = set()
    ordered_ids = sorted(question_ids)
    for start in range(0, len(ordered_ids), _QUERY_CHUNK_SIZE):
        batch = ordered_ids[start : start + _QUERY_CHUNK_SIZE]
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            "SELECT DISTINCT user_id, question_id FROM srs_cards "
            f"WHERE question_id IN ({placeholders}) "
            "AND last_grade >= 3 AND COALESCE(progress_credited, 0) = 0",
            tuple(batch),
        ).fetchall()
        result.update((int(row[0]), int(row[1])) for row in rows)
    return result


def _bounded_non_authoritative_review_pairs(
    conn: Any,
    question_ids: set[int],
    *,
    cutoff_literal: str,
    trusted_source_prefixes: tuple[str, ...] = TRUSTED_REVIEW_SOURCE_PREFIXES,
) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    """Census client/unverifiable pairs with bounded, explained SELECTs.

    ``review_log`` is only consulted in canonical question-id chunks and below
    the locked historical cutoff.  The EXPLAIN is issued before each SELECT;
    the result is diagnostic only and never enters the baseline authority.
    """

    client_pairs: set[tuple[int, int]] = set()
    unverifiable_pairs: set[tuple[int, int]] = set()
    ordered_ids = sorted(question_ids)
    raw = getattr(conn, "_conn", conn)
    is_sqlite = raw.__class__.__module__.lower().startswith("sqlite3")
    explain_prefix = "EXPLAIN QUERY PLAN " if is_sqlite else "EXPLAIN "
    for start in range(0, len(ordered_ids), _QUERY_CHUNK_SIZE):
        batch = ordered_ids[start : start + _QUERY_CHUNK_SIZE]
        placeholders = ",".join("?" for _ in batch)
        sql = (
            "SELECT DISTINCT user_id, question_id, source_context FROM review_log "
            f"WHERE grade>=3 AND reviewed_at < ? AND question_id IN ({placeholders})"
        )
        params = (cutoff_literal, *batch)
        # EXPLAIN is read-only and does not acquire write locks.  Do not run an
        # EXPLAIN ANALYZE here: the global review table is intentionally never
        # executed as an unbounded forensic aggregation.
        conn.execute(explain_prefix + sql, params).fetchall()
        for row in conn.execute(sql, params).fetchall():
            pair = (int(row[0]), int(row[1]))
            context = None if row[2] is None else str(row[2])
            if context is None or context in {"practice", "guild_quest"}:
                client_pairs.add(pair)
            elif any(context.startswith(prefix) for prefix in trusted_source_prefixes):
                # This is already current trusted Map evidence, not a
                # historical baseline candidate and not an unverified class.
                continue
            else:
                unverifiable_pairs.add(pair)
    return client_pairs, unverifiable_pairs


def _legacy_first_stars(conn: Any) -> dict[tuple[int, str], int]:
    if not _table_exists(conn, "adventure_boss_progress"):
        return {}
    rows = conn.execute(
        "SELECT user_id, zone_key, stars FROM adventure_boss_progress "
        "WHERE stars >= 1"
    ).fetchall()
    return {
        (int(row[0]), str(row[1])): max(0, min(3, int(row[2] or 0)))
        for row in rows
    }


def _current_zone_stars(conn: Any) -> dict[tuple[int, str], int]:
    if not _table_exists(conn, PROGRESS_TABLE_NAME):
        return {}
    rows = conn.execute(
        f"SELECT user_id, zone_key, earned_stars FROM {PROGRESS_TABLE_NAME}"
    ).fetchall()
    return {
        (int(row[0]), str(row[1])): max(0, min(3, int(row[2] or 0)))
        for row in rows
    }


def build_global_dry_run(
    conn: Any,
    zone_question_ids: dict[str, set[int]],
    *,
    owner_user_id: int | None = None,
    cutoff_literal: str = CUTOFF_LITERAL,
) -> dict[str, Any]:
    """Build the global, trust-filtered baseline and milestone dry-run.

    This function is read-only and receives a connection already configured by
    :func:`_configure_read_only_transaction`.  It intentionally reports only
    aggregate values and a single optional Owner projection; raw account IDs
    are never serialized.
    """

    all_question_ids = set().union(*zone_question_ids.values()) if zone_question_ids else set()
    baseline = qualifying_card_memberships(conn, question_ids=all_question_ids)
    current = trusted_current_memberships(conn, question_ids=all_question_ids)
    assert isinstance(baseline, dict)
    assert isinstance(current, dict)
    raw_progress_rows = _raw_progress_rows(conn, all_question_ids)
    baseline_total = sum(len(values) for values in baseline.values())
    last_grade_only = _last_grade_only_pairs(conn, all_question_ids)
    client_pairs, non_client_unverifiable_pairs = _bounded_non_authoritative_review_pairs(
        conn,
        all_question_ids,
        cutoff_literal=cutoff_literal,
        trusted_source_prefixes=TRUSTED_REVIEW_SOURCE_PREFIXES,
    )
    baseline_pairs = {
        (int(user_id), int(question_id))
        for user_id, question_ids_for_user in baseline.items()
        for question_id in question_ids_for_user
    }
    legacy_stars = _legacy_first_stars(conn)
    current_stars = _current_zone_stars(conn)
    progression = build_progression_milestone_dry_run(
        baseline,
        current,
        zone_question_ids,
        legacy_first_stars=legacy_stars,
        current_zone_stars=current_stars,
    )

    owner_rows = [
        row for row in progression["rows"]
        if owner_user_id is not None and row["user_id"] == int(owner_user_id)
    ]
    owner_projection = {
        row["zone"]: {
            "current_correct": row["current_correct"],
            "effective_correct": row["effective_correct"],
            "total": row["total"],
        }
        for row in owner_rows
    }
    owner_baseline = baseline.get(int(owner_user_id), set()) if owner_user_id is not None else set()
    owner_current = current.get(int(owner_user_id), set()) if owner_user_id is not None else set()
    owner_overlap = owner_baseline & owner_current

    # The only historical card predicate admitted by this candidate is the
    # sticky server-owned bit.  Public/client-grade rows are diagnostics and
    # fail closed.  The last-grade-only count is therefore reported as an
    # explicit unverified exclusion, not as baseline authority.
    progression_report = dict(progression)
    # ``rows`` contains internal user ids for the pure helper's calculations.
    # The CLI output is an aggregate forensic report and must never expose
    # those ids, even when an Owner projection was requested.
    progression_report.pop("rows", None)
    progression_report["star_transitions_with_default_hold"] = 0
    progression_report["potential_star_transitions_if_full_policy"] = (
        progression.get("star_transitions_current_runtime_would_commit", 0)
    )
    return {
        "migration_mode": "DRY_RUN_READ_ONLY",
        "migration_owner_gate": MIGRATION_OWNER_GATE,
        "migration_publish_order": [
            "BASELINE_BUILDING",
            "populate_trusted_progress_credited_memberships",
            "verify_count_and_fingerprint",
            "BASELINE_READY",
        ],
        "failure_recovery": "rollback_or_leave_non_ready_then_rerun_same_version",
        "users_with_trusted_baseline_candidates": len(baseline),
        "trusted_baseline_memberships_total": baseline_total,
        "duplicates_eliminated": max(0, raw_progress_rows - baseline_total),
        "unverifiable_memberships_excluded": len(
            (last_grade_only | non_client_unverifiable_pairs) - baseline_pairs - client_pairs
        ),
        "client_originated_memberships_excluded": len(client_pairs - baseline_pairs),
        "owner_trusted_baseline_distinct": len(owner_baseline),
        "owner_current_mbv1_distinct": len(owner_current),
        "owner_baseline_mbv1_overlap": len(owner_overlap),
        "owner_effective_union_distinct": len(owner_baseline | owner_current),
        "owner_effective_zone_projection": owner_projection,
        "progression_blast_radius": progression_report,
        "raw_progress_rows_observed": raw_progress_rows,
        "historical_source_rule": "srs_cards.progress_credited only",
        "client_grade_source_used": False,
        "cutoff_literal": cutoff_literal,
    }


def _zone_question_ids(app_module: Any) -> dict[str, set[int]]:
    questions = app_module._load_questions()
    return {
        zone["key"]: {
            int(question["id"])
            for question in app_module._questions_for_adventure_zone(
                questions, zone, premium=True
            )
        }
        for zone in app_module.ADVENTURE_ZONES
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Incident 019B Adventure mastery compatibility census"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="preview the one-time baseline and print a set-aware census (default)",
    )
    mode.add_argument(
        "--capture-baseline",
        action="store_true",
        help="capture the frozen baseline in the caller-selected database",
    )
    parser.add_argument(
        "--historical-mode",
        choices=("preview", "frozen"),
        default="preview",
        help="use live source preview or the already frozen table for the census",
    )
    parser.add_argument(
        "--confirm-baseline-version",
        default=None,
        help="required with --capture-baseline; must equal the locked version",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="allow the explicitly gated baseline capture to commit",
    )
    parser.add_argument(
        "--owner-gate",
        default=None,
        help=f"required with --execute; must equal {MIGRATION_OWNER_GATE}",
    )
    parser.add_argument(
        "--owner-user-id",
        type=int,
        default=None,
        help="optional already-resolved Owner account id for one redacted projection; never printed",
    )
    return parser


def _validate_execution_gate(args: argparse.Namespace) -> None:
    """Keep baseline mutation separate from ordinary deployment execution."""

    if args.capture_baseline:
        if not args.execute:
            raise SystemExit(
                "--capture-baseline requires --execute; ordinary deployment cannot capture it"
            )
        if args.owner_gate != MIGRATION_OWNER_GATE:
            raise SystemExit(
                "--capture-baseline requires --owner-gate "
                f"{MIGRATION_OWNER_GATE}"
            )
        return
    if args.execute or args.owner_gate:
        raise SystemExit(
            "--execute and --owner-gate are only valid with --capture-baseline"
        )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _validate_execution_gate(args)
    if args.capture_baseline and args.confirm_baseline_version != BASELINE_VERSION:
        raise SystemExit(
            "--capture-baseline requires --confirm-baseline-version "
            f"{BASELINE_VERSION}"
        )

    # Importing app is deliberately deferred so importing this tool remains a
    # pure helper operation and no database connection is opened accidentally.
    import app as app_module

    zone_question_ids = _zone_question_ids(app_module)
    all_question_ids = set().union(*zone_question_ids.values())
    if args.capture_baseline:
        with app_module.get_db() as conn:
            result = populate_frozen_historical_baseline(
                conn,
                question_ids=all_question_ids,
            )
            conn.commit()
            result["census"] = build_compatibility_census(
                conn,
                zone_question_ids,
                historical_mode="frozen",
            )
    else:
        with app_module.get_db() as conn:
            _configure_read_only_transaction(conn)
            result = build_global_dry_run(
                conn,
                zone_question_ids,
                owner_user_id=args.owner_user_id,
            )
            result["compatibility_census"] = build_compatibility_census(
                conn, zone_question_ids, historical_mode=args.historical_mode
            )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
