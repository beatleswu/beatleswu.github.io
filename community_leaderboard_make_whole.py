"""Read-time Community leaderboard projection for the P0 make-whole policy.

This module deliberately does not write any table.  The Adventure recovery
ledger is an eligibility boundary only; the original activity timestamp comes
from the matching ``review_log.reviewed_at`` row.  The policy is kept separate
from normal trusted correctness so the projection cannot be mistaken for
historical server evidence.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import datetime as _datetime
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from migrations.adventure_progress_recovery_v1 import (
    HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT,
    OWNER_POLICY_RECOVERY_REASON,
    TABLE_NAME as RECOVERY_TABLE,
    POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING,
)


MAKE_WHOLE_AUTHORITY = "OWNER_P0_MAKE_WHOLE"
MAKE_WHOLE_POLICY_REASON = "QUALIFIED_BY_P0_MAKE_WHOLE_POLICY"
ORIGINAL_TIME_AUTHORITY = "review_log.reviewed_at"
COMMUNITY_IDENTITY_AUTHORITY = "(user_id, legacy_question_id)"

# This is the exact Production-applied refreshed operation.  Binding the
# projection to this immutable operation prevents a future/partial ledger
# operation from silently broadening Community eligibility.
P0_MAKE_WHOLE_OPERATION_ID = "P0_LANE_C_OWNER_POLICY_2026_09_17_FINAL_001"
INCIDENT_WINDOW_START = "2026-08-03T12:54:13Z"
INCIDENT_WINDOW_END = "2026-09-17T02:53:29.2448507Z"

_UTC = _datetime.timezone.utc
_TAIPEI = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True)
class P0MakeWholePair:
    """One safe read-time make-whole candidate for one leaderboard period."""

    user_id: int
    question_id: int
    canonical_question_id: str
    original_activity_timestamp: str
    authority: str = MAKE_WHOLE_AUTHORITY
    policy_reason: str = MAKE_WHOLE_POLICY_REASON
    historical_correctness_status: str = HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT
    original_time_authority: str = ORIGINAL_TIME_AUTHORITY
    identity_authority: str = COMMUNITY_IDENTITY_AUTHORITY

    @property
    def key(self) -> tuple[int, int]:
        return (self.user_id, self.question_id)


def _row_value(row: Any, name: str, index: int | None = None) -> Any:
    try:
        return row[name]
    except (KeyError, IndexError, TypeError):
        if index is None:
            raise
        return row[index]


def _table_exists(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    module = raw.__class__.__module__
    if module.startswith("sqlite3"):
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (RECOVERY_TABLE,),
        ).fetchone() is not None
    return conn.execute(
        """SELECT 1 FROM information_schema.tables
             WHERE table_schema='public' AND table_name=?""",
        (RECOVERY_TABLE,),
    ).fetchone() is not None


def _parse_utc(value: Any) -> _datetime.datetime:
    if isinstance(value, _datetime.datetime):
        parsed = value
    else:
        text = str(value or "").strip().replace("Z", "+00:00")
        if not text:
            raise ValueError("empty timestamp")
        parsed = _datetime.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_UTC)
    return parsed.astimezone(_UTC)


def _timestamp_sort_key(value: Any) -> tuple[_datetime.datetime, str]:
    parsed = _parse_utc(value)
    return parsed, str(value)


def _period_contains(value: Any, period_start_iso: str, period_end_iso: str | None) -> bool:
    timestamp = _parse_utc(value)
    start = _parse_utc(period_start_iso)
    if timestamp < start:
        return False
    return period_end_iso is None or timestamp < _parse_utc(period_end_iso)


def _incident_contains(value: Any) -> bool:
    return _period_contains(value, INCIDENT_WINDOW_START, INCIDENT_WINDOW_END)


def _valid_row(row: Any) -> bool:
    try:
        return (
            int(_row_value(row, "apply_eligible")) == 1
            and int(_row_value(row, "proposed_recovery_credit")) == 1
            and int(_row_value(row, "credit_delta")) == 1
            and str(_row_value(row, "recovery_reason")) == OWNER_POLICY_RECOVERY_REASON
            and str(_row_value(row, "evidence_class")) == "UNRESOLVED_EVIDENCE_GAP"
            and str(_row_value(row, "gap_reason")) == "CORRECTNESS_AUTHORITY_MISSING"
            and str(_row_value(row, "policy_classification"))
            == POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING
            and str(_row_value(row, "historical_correctness_status"))
            == HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def _fetch_applied_rows(conn: Any) -> list[Any]:
    if not _table_exists(conn):
        return []
    return conn.execute(
        f"""SELECT operation_id, user_id, canonical_question_id,
                       legacy_question_id, recovery_reason, evidence_class,
                       gap_reason, apply_eligible, proposed_recovery_credit,
                       policy_classification, credit_delta,
                       historical_correctness_status
                  FROM {RECOVERY_TABLE}
                 WHERE operation_id=?
                   AND recovery_reason=?
                   AND evidence_class=?
                   AND gap_reason=?
                   AND apply_eligible=1
                   AND proposed_recovery_credit=1
                   AND policy_classification=?
                   AND credit_delta=1
                   AND historical_correctness_status=?
              ORDER BY user_id, legacy_question_id, canonical_question_id""",
        (
            P0_MAKE_WHOLE_OPERATION_ID,
            OWNER_POLICY_RECOVERY_REASON,
            "UNRESOLVED_EVIDENCE_GAP",
            "CORRECTNESS_AUTHORITY_MISSING",
            POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING,
            HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT,
        ),
    ).fetchall()


def _fetch_review_timestamps(conn: Any, recovery_rows: Iterable[Any]) -> dict[tuple[int, int], list[Any]]:
    rows = list(recovery_rows)
    if not rows:
        return {}
    values: list[tuple[int, int]] = []
    for row in rows:
        try:
            user_id = int(_row_value(row, "user_id"))
            question_id = int(_row_value(row, "legacy_question_id"))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if user_id > 0 and question_id > 0:
            values.append((user_id, question_id))
    values = sorted(set(values))
    if not values:
        return {}

    # The current Community authority uses the legacy question_id as its
    # compatibility identity.  Filter the bounded incident timestamp range
    # in SQL and perform the package membership check in Python.  A giant OR
    # predicate is not portable and exceeds SQLite's expression-depth limit
    # for the 2716-row package.
    allowed = set(values)
    result = defaultdict(list)
    for row in conn.execute(
        """SELECT user_id, question_id, reviewed_at
                  FROM review_log
                 WHERE reviewed_at >= ?
                   AND reviewed_at < ?
              ORDER BY user_id, question_id, reviewed_at""",
        (INCIDENT_WINDOW_START, INCIDENT_WINDOW_END),
    ).fetchall():
        try:
            key = (int(_row_value(row, "user_id")), int(_row_value(row, "question_id")))
            reviewed_at = _row_value(row, "reviewed_at")
            _parse_utc(reviewed_at)
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if key not in allowed:
            continue
        result[key].append(reviewed_at)
    return dict(result)


def _canonical_identity_groups(recovery_rows: Iterable[Any]) -> tuple[dict[tuple[int, int], Any], set[tuple[int, int]]]:
    """Return safe rows and malformed/ambiguous keys that fail closed."""
    grouped: dict[tuple[int, int], set[str]] = defaultdict(set)
    first_row: dict[tuple[int, int], Any] = {}
    failed: set[tuple[int, int]] = set()
    for row in recovery_rows:
        try:
            user_id = int(_row_value(row, "user_id"))
            question_id = int(_row_value(row, "legacy_question_id"))
            canonical = str(_row_value(row, "canonical_question_id") or "").strip()
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if user_id <= 0 or question_id <= 0 or not canonical:
            failed.add((user_id, question_id))
            continue
        key = (user_id, question_id)
        grouped[key].add(canonical)
        first_row.setdefault(key, row)
    for key, canonical_ids in grouped.items():
        if len(canonical_ids) != 1:
            failed.add(key)
    return {
        key: row for key, row in first_row.items() if key not in failed
    }, failed


def fetch_p0_make_whole_period_rows(
    conn: Any,
    period_start_iso: str,
    period_end_iso: str | None = None,
    *,
    normal_identity_keys: Iterable[tuple[int, int]] = (),
) -> dict[str, Any]:
    """Return the safe P0 candidates for one Community period.

    ``normal_identity_keys`` must come from the existing trusted Community
    identity query for the same period.  The union is distinct by the current
    compatibility identity, so a trusted record before or after this
    projection cannot create a second score unit.
    """
    applied_rows = [row for row in _fetch_applied_rows(conn) if _valid_row(row)]
    safe_rows, failed_identity_keys = _canonical_identity_groups(applied_rows)
    timestamps = _fetch_review_timestamps(conn, safe_rows.values())
    normal_keys = {(int(user_id), int(question_id)) for user_id, question_id in normal_identity_keys}
    candidates: list[P0MakeWholePair] = []
    trusted_overlap: list[tuple[int, int]] = []
    missing_time: set[tuple[int, int]] = set()
    unresolved_time: set[tuple[int, int]] = set()
    for key, row in safe_rows.items():
        matching = [
            value for value in timestamps.get(key, [])
            if _period_contains(value, period_start_iso, period_end_iso)
        ]
        if not matching:
            # A recovery row without a trusted original timestamp cannot be
            # assigned to a period and therefore fails closed.
            if timestamps.get(key):
                missing_time.add(key)
            else:
                unresolved_time.add(key)
            continue
        if key in normal_keys:
            trusted_overlap.append(key)
            continue
        original_timestamp = min(matching, key=_timestamp_sort_key)
        candidates.append(P0MakeWholePair(
            user_id=key[0],
            question_id=key[1],
            canonical_question_id=str(_row_value(row, "canonical_question_id")),
            original_activity_timestamp=str(original_timestamp),
        ))
    candidates.sort(key=lambda item: (item.user_id, item.question_id))
    return {
        "authority": MAKE_WHOLE_AUTHORITY,
        "policy_reason": MAKE_WHOLE_POLICY_REASON,
        "original_time_authority": ORIGINAL_TIME_AUTHORITY,
        "identity_authority": COMMUNITY_IDENTITY_AUTHORITY,
        "candidate_rows": candidates,
        "candidate_keys": {row.key for row in candidates},
        "trusted_overlap_keys": set(trusted_overlap),
        "failed_identity_keys": failed_identity_keys,
        "missing_time_keys": missing_time,
        "unresolved_time_keys": unresolved_time,
        "applied_package_rows": len(applied_rows),
    }


def fetch_p0_make_whole_period_summary(
    conn: Any,
    period_start_iso: str,
    period_end_iso: str | None = None,
    *,
    normal_identity_keys: Iterable[tuple[int, int]] = (),
) -> dict[str, Any]:
    projection = fetch_p0_make_whole_period_rows(
        conn,
        period_start_iso,
        period_end_iso,
        normal_identity_keys=normal_identity_keys,
    )
    by_user: dict[int, int] = defaultdict(int)
    for row in projection["candidate_rows"]:
        by_user[row.user_id] += 1
    return {
        "period_start": period_start_iso,
        "period_end": period_end_iso,
        "candidate_pairs": len(projection["candidate_rows"]),
        "candidate_users": len(by_user),
        "by_user": dict(sorted(by_user.items())),
        "trusted_overlap_pairs": len(projection["trusted_overlap_keys"]),
        "failed_identity_pairs": len(projection["failed_identity_keys"]),
        "missing_original_timestamp_pairs": len(projection["missing_time_keys"]),
        "unresolved_original_timestamp_pairs": len(projection["unresolved_time_keys"]),
        "applied_package_rows": projection["applied_package_rows"],
    }


def classify_original_periods(
    conn: Any,
    *,
    week_start_iso: str,
    week_end_iso: str,
    month_start_iso: str,
    month_end_iso: str,
) -> dict[str, Any]:
    """Classify the applied package without using recovery insertion time."""
    applied_rows = [row for row in _fetch_applied_rows(conn) if _valid_row(row)]
    safe_rows, failed = _canonical_identity_groups(applied_rows)
    timestamps = _fetch_review_timestamps(conn, safe_rows.values())
    current_week: set[tuple[int, int]] = set()
    current_month: set[tuple[int, int]] = set()
    older: set[tuple[int, int]] = set()
    unresolved: set[tuple[int, int]] = set(failed)
    historical_weekly_periods: dict[str, set[tuple[int, int]]] = defaultdict(set)
    historical_monthly_periods: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for key in safe_rows:
        values = timestamps.get(key, [])
        if not values:
            unresolved.add(key)
            continue
        week_values = [v for v in values if _period_contains(v, week_start_iso, week_end_iso)]
        month_values = [v for v in values if _period_contains(v, month_start_iso, month_end_iso)]
        if week_values:
            current_week.add(key)
        if month_values:
            current_month.add(key)
        if not week_values and not month_values:
            older.add(key)
        for value in values:
            local = _parse_utc(value).astimezone(_TAIPEI)
            iso_year, iso_week, _ = local.date().isocalendar()
            historical_weekly_periods[f"{iso_year}-W{iso_week:02d}"].add(key)
            historical_monthly_periods[f"{local.year:04d}-{local.month:02d}"].add(key)
    return {
        "applied_package_pairs": len(applied_rows),
        "current_week_pairs": current_week,
        "current_month_pairs": current_month,
        "older_pairs": older,
        "unresolved_pairs": unresolved,
        "historical_weekly_period_pairs": {
            key: set(value) for key, value in sorted(historical_weekly_periods.items())
        },
        "historical_monthly_period_pairs": {
            key: set(value) for key, value in sorted(historical_monthly_periods.items())
        },
    }


__all__ = [
    "COMMUNITY_IDENTITY_AUTHORITY",
    "INCIDENT_WINDOW_END",
    "INCIDENT_WINDOW_START",
    "MAKE_WHOLE_AUTHORITY",
    "MAKE_WHOLE_POLICY_REASON",
    "ORIGINAL_TIME_AUTHORITY",
    "P0_MAKE_WHOLE_OPERATION_ID",
    "P0MakeWholePair",
    "classify_original_periods",
    "fetch_p0_make_whole_period_rows",
    "fetch_p0_make_whole_period_summary",
]
