"""Grandfathered legacy continuity baseline runner, census and comparison.

This tool builds and reports ``GRANDFATHERED_LEGACY_PROGRESS`` (Tier 1): the
reconstruction of the complete pre-change player-facing display predicate at
``4f2547a6defd60a228f77a4457b96f24b916e22c``.  Tier 1 is continuity
entitlement.  It is never trusted correctness, never server-judged evidence,
and never an input to Guild, leaderboard or reward settlement.

Every membership is reported under its reconstruction class -- exact versus
conservative -- so the two can never be conflated in an evidence claim.

Default mode is read-only preview.  ``--capture-baseline`` is intentionally
explicit and requires the exact version confirmation, ``--execute``, and the
exact ``GO_PRODUCTION_DB_MIGRATION`` owner gate.

``--compare-account --username <name>`` is a generic read-only comparison for
any single account.  No account is hard-coded.

The output contains only aggregate counts and short deterministic player
pseudonyms.  It never prints connection details or account identifiers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

# Allow the runner to be invoked directly as ``python tools/<runner>.py`` from
# the repository root, as well as imported by a test or another tool.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from adventure_progress_compatibility import (
    BASELINE_VERSION,
    CUTOFF_LITERAL,
    PRECHANGE_PREDICATE_REFERENCE_SHA,
    RECONSTRUCTION_CLASS_CONSERVATIVE,
    RECONSTRUCTION_CLASS_EXACT,
    TRUSTED_REVIEW_SOURCE_PREFIXES,
    build_progression_milestone_dry_run,
    build_compatibility_census,
    last_grade_fallback_memberships,
    post_cutoff_review_memberships,
    pre_cutoff_review_memberships,
    prechange_display_reconstruction,
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


class CensusScanPlan:
    """Bounded scan plan for a later Production integrity preflight.

    A question-id-only predicate spans every account in one statement, so a
    single chunk can return an unbounded number of rows on a real database.
    Batching by an indexed ``user_id`` range keeps each statement bounded, lets
    the run pause between batches to protect a live server, and makes the work
    resumable from a checkpoint after an interruption.
    """

    def __init__(
        self,
        *,
        batch_size: int = 2000,
        inter_batch_pause: float = 0.0,
        checkpoint_file: str | None = None,
    ):
        self.batch_size = max(1, int(batch_size))
        self.inter_batch_pause = max(0.0, float(inter_batch_pause))
        self.checkpoint_file = checkpoint_file
        self.batches_run = 0

    def resume_from(self) -> int:
        if not self.checkpoint_file:
            return 0
        path = Path(self.checkpoint_file)
        if not path.is_file():
            return 0
        try:
            return int(json.loads(path.read_text(encoding="utf-8"))["last_user_id"])
        except Exception:
            return 0

    def record(self, last_user_id: int) -> None:
        if not self.checkpoint_file:
            return
        Path(self.checkpoint_file).write_text(
            json.dumps({"last_user_id": int(last_user_id)}), encoding="utf-8"
        )

    def user_ranges(self, conn: Any) -> list[tuple[int, int]]:
        row = conn.execute(
            "SELECT MIN(user_id), MAX(user_id) FROM srs_cards"
        ).fetchone()
        if not row or row[0] is None:
            return []
        low = max(int(row[0]), self.resume_from())
        high = int(row[1])
        return [
            (start, min(start + self.batch_size - 1, high))
            for start in range(low, high + 1, self.batch_size)
        ]

    def pause(self) -> None:
        self.batches_run += 1
        if self.inter_batch_pause:
            time.sleep(self.inter_batch_pause)


def _raw_progress_rows(
    conn: Any, question_ids: set[int], plan: CensusScanPlan | None = None
) -> int:
    if not question_ids:
        return 0
    plan = plan or CensusScanPlan()
    total = 0
    ordered_ids = sorted(question_ids)
    for low, high in plan.user_ranges(conn) or [(None, None)]:
        for start in range(0, len(ordered_ids), _QUERY_CHUNK_SIZE):
            batch = ordered_ids[start : start + _QUERY_CHUNK_SIZE]
            placeholders = ",".join("?" for _ in batch)
            user_clause = "" if low is None else " AND user_id BETWEEN ? AND ?"
            params = tuple(batch) if low is None else (*batch, low, high)
            sql = (
                "SELECT COUNT(*) FROM srs_cards "
                f"WHERE progress_credited <> 0 AND question_id IN ({placeholders})"
                f"{user_clause}"
            )
            total += int(conn.execute(sql, params).fetchone()[0])
        if low is not None:
            plan.record(high)
            plan.pause()
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
    scan_plan: "CensusScanPlan | None" = None,
) -> dict[str, Any]:
    """Build the global, trust-filtered baseline and milestone dry-run.

    This function is read-only and receives a connection already configured by
    :func:`_configure_read_only_transaction`.  It intentionally reports only
    aggregate values and a single optional Owner projection; raw account IDs
    are never serialized.
    """

    scan_plan = scan_plan or CensusScanPlan()
    all_question_ids = set().union(*zone_question_ids.values()) if zone_question_ids else set()
    # Tier 1 is the full pre-change display predicate, not one column.
    reconstruction = prechange_display_reconstruction(
        conn, question_ids=all_question_ids, cutoff_literal=cutoff_literal
    )
    baseline = reconstruction["memberships"]
    current = trusted_current_memberships(conn, question_ids=all_question_ids)
    assert isinstance(baseline, dict)
    assert isinstance(current, dict)
    raw_progress_rows = _raw_progress_rows(conn, all_question_ids, scan_plan)
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
            "reconstruct_prechange_display_predicate",
            "classify_exact_and_conservative_memberships",
            "verify_count_and_fingerprint",
            "BASELINE_READY",
        ],
        "predicate_reference_sha": PRECHANGE_PREDICATE_REFERENCE_SHA,
        "exact_reconstructable_memberships": reconstruction["exact_count"],
        "conservative_grandfathered_memberships": reconstruction["conservative_count"],
        "post_cutoff_only_excluded": reconstruction["post_cutoff_only_count"],
        "review_grade_branch_memberships": sum(
            1 for mask in reconstruction["masks"].values() if mask & 1
        ),
        "progress_credited_branch_memberships": sum(
            1 for mask in reconstruction["masks"].values() if mask & 2
        ),
        "last_grade_branch_memberships": sum(
            1 for mask in reconstruction["masks"].values() if mask & 4
        ),
        "multi_source_memberships": sum(
            1
            for mask in reconstruction["masks"].values()
            if bin(mask).count("1") > 1
        ),
        "failure_recovery": "rollback_or_leave_non_ready_then_rerun_same_version",
        "users_with_grandfathered_candidates": len(baseline),
        "grandfathered_memberships_total": baseline_total,
        "duplicates_eliminated": max(0, raw_progress_rows - baseline_total),
        "unverifiable_memberships_excluded": len(
            (last_grade_only | non_client_unverifiable_pairs) - baseline_pairs - client_pairs
        ),
        "client_originated_memberships_excluded": len(client_pairs - baseline_pairs),
        "owner_grandfathered_distinct": len(owner_baseline),
        "owner_current_mbv1_distinct": len(owner_current),
        "owner_baseline_mbv1_overlap": len(owner_overlap),
        "owner_effective_union_distinct": len(owner_baseline | owner_current),
        "owner_effective_zone_projection": owner_projection,
        "progression_blast_radius": progression_report,
        "raw_progress_rows_observed": raw_progress_rows,
        "historical_source_rule": (
            "prechange display predicate: review_log.grade>=3 "
            "| srs_cards.progress_credited | srs_cards.last_grade>=3"
        ),
        "historical_tier": "GRANDFATHERED_LEGACY_PROGRESS",
        "historical_is_trusted_correctness": False,
        "client_grade_source_used_as_correctness_authority": False,
        "cutoff_literal": cutoff_literal,
        "census_batch_key": "srs_cards.user_id range",
        "census_batch_size": scan_plan.batch_size,
        "census_batches_run": scan_plan.batches_run,
        "census_inter_batch_pause_seconds": scan_plan.inter_batch_pause,
        "census_resumable_checkpoint": bool(scan_plan.checkpoint_file),
        "census_parallel_batches": 0,
        "census_max_connections": 1,
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


def resolve_user_id_by_username(conn: Any, username: str) -> int | None:
    """Resolve one account id from a username, without printing either.

    Deliberately generic: the tool must be able to compare any account, so no
    Owner account name is compiled into the migration logic.
    """

    name = str(username or "").strip()
    if not name:
        return None
    row = conn.execute(
        "SELECT id FROM users WHERE username=?", (name,)
    ).fetchone()
    if row is None:
        return None
    try:
        return int(row["id"])
    except (KeyError, IndexError, TypeError):
        return int(row[0])


def build_account_comparison(
    conn: Any,
    zone_question_ids: dict[str, set[int]],
    *,
    user_id: int,
    cutoff_literal: str = CUTOFF_LITERAL,
) -> dict[str, Any]:
    """Read-only per-account comparison of the old and new continuity models.

    Answers the question this whole repair turns on: does reconstructing the
    complete pre-change predicate differ materially from the earlier
    ``progress_credited``-only estimate, and how much of the raw legacy set is
    still renderable against the *current* canonical catalog?

    Emits counts only.  The account identifier is never echoed.
    """

    all_ids: set[int] = set()
    for ids in zone_question_ids.values():
        all_ids |= set(ids)

    reconstruction = prechange_display_reconstruction(
        conn, question_ids=all_ids, cutoff_literal=cutoff_literal
    )
    classes = reconstruction["classes"]
    masks = reconstruction["masks"]
    mine = {
        question_id
        for (owner, question_id) in classes
        if owner == int(user_id)
    }
    exact = {
        question_id
        for (owner, question_id), value in classes.items()
        if owner == int(user_id) and value == RECONSTRUCTION_CLASS_EXACT
    }
    conservative = {
        question_id
        for (owner, question_id), value in classes.items()
        if owner == int(user_id) and value == RECONSTRUCTION_CLASS_CONSERVATIVE
    }
    post_cutoff_only = {
        question_id
        for (owner, question_id) in reconstruction["post_cutoff_only"]
        if owner == int(user_id)
    }
    credited_only = set(
        qualifying_card_memberships(conn, question_ids=all_ids, user_id=int(user_id))
    )
    trusted_now = set(
        trusted_current_memberships(
            conn,
            source_prefixes=TRUSTED_REVIEW_SOURCE_PREFIXES,
            question_ids=all_ids,
            user_id=int(user_id),
        )
    )

    per_zone = {}
    for zone_key, ids in sorted(zone_question_ids.items()):
        zone_ids = set(ids)
        per_zone[zone_key] = {
            "canonical_denominator": len(zone_ids),
            "grandfathered_raw": len(mine & zone_ids),
            "exact": len(exact & zone_ids),
            "conservative": len(conservative & zone_ids),
            "currently_renderable": len((mine | trusted_now) & zone_ids),
            "progress_credited_only_model": len(credited_only & zone_ids),
        }

    return {
        "predicate_reference_sha": PRECHANGE_PREDICATE_REFERENCE_SHA,
        "cutoff_literal": cutoff_literal,
        "old_predicate_raw_set_count": len(mine),
        "exact_reconstructable_count": len(exact),
        "conservative_grandfathered_count": len(conservative),
        "post_cutoff_only_count": len(post_cutoff_only),
        "progress_credited_only_count": len(credited_only),
        "old_predicate_minus_progress_credited_model": len(mine - credited_only),
        "progress_credited_model_minus_old_predicate": len(credited_only - mine),
        "trusted_current_count": len(trusted_now),
        "currently_renderable_count": len(mine | trusted_now),
        "multi_source_memberships": sum(
            1
            for (owner, _q), mask in masks.items()
            if owner == int(user_id) and bin(mask).count("1") > 1
        ),
        "per_zone": per_zone,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Grandfathered legacy continuity (Tier 1) baseline runner, census "
            "and generic per-account comparison. Tier 1 is continuity "
            "entitlement, never trusted correctness."
        )
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
        help="optional already-resolved account id for one redacted projection; never printed",
    )
    mode.add_argument(
        "--compare-account",
        action="store_true",
        help="read-only single-account comparison of old predicate vs current model",
    )
    parser.add_argument(
        "--username",
        default=None,
        help="account to compare with --compare-account; no account is hard-coded",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=2000,
        help="user-range batch size for bounded census scans",
    )
    parser.add_argument(
        "--inter-batch-pause",
        type=float,
        default=0.0,
        help="seconds to sleep between census batches to protect a live database",
    )
    parser.add_argument(
        "--checkpoint-file",
        default=None,
        help="resumable checkpoint path; a rerun continues after the last batch",
    )
    return parser


def _validate_execution_gate(args: argparse.Namespace) -> None:
    """Keep baseline mutation separate from ordinary deployment execution."""

    if getattr(args, "compare_account", False):
        if not str(getattr(args, "username", "") or "").strip():
            raise SystemExit("--compare-account requires --username")
        if args.execute or args.owner_gate:
            raise SystemExit("--compare-account is read-only and takes no gate")
        return
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
    if args.compare_account:
        with app_module.get_db() as conn:
            _configure_read_only_transaction(conn)
            resolved = resolve_user_id_by_username(conn, args.username)
            if resolved is None:
                raise SystemExit("account not found")
            result = {
                "mode": "compare_account",
                "account_resolved": True,
                "comparison": build_account_comparison(
                    conn, zone_question_ids, user_id=resolved
                ),
            }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
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
                scan_plan=CensusScanPlan(
                    batch_size=args.batch_size,
                    inter_batch_pause=args.inter_batch_pause,
                    checkpoint_file=args.checkpoint_file,
                ),
            )
            result["compatibility_census"] = build_compatibility_census(
                conn, zone_question_ids, historical_mode=args.historical_mode
            )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
