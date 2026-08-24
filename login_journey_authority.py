"""Server-owned Login Journey, attendance, and login-streak authority.

This module is a service-level foundation for D016.  It deliberately does
not wire an authentication route, mutate ``app.py``, settle rewards, create
Quest rows, or claim anything.  A caller supplies an already-authenticated
server login occurrence and owns the surrounding transaction.

The durable attendance ledger is the source of truth.  Streak and Journey
rows are deterministic projections recomputed from the committed ledger
while a per-user PostgreSQL row lock serializes competing mutations.  This
means a delayed event is assigned to its original Asia/Taipei date and cannot
become an arrival-order streak corruption.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import uuid
from typing import Any, Mapping

from migrations.login_journey_v1 import (
    JOURNEY_ID,
    JOURNEY_LENGTH,
    JOURNEY_TABLE_NAME,
    JOURNEY_VERSION,
    LOGIN_DAYS_TABLE_NAME,
    STREAK_TABLE_NAME,
)
from quest_period_authority import PERIOD_TIMEZONE, PeriodResolutionError, QuestPeriodResolver


LOGIN_EVENT_TYPE = "AUTHENTICATED_LOGIN"
LOGIN_DAY_TIMEZONE = "Asia/Taipei"
MAX_USER_ID = 2**63 - 1


class LoginAuthorityError(RuntimeError):
    """Base class for fail-closed Login V1 errors."""


class LoginEventValidationError(ValueError, LoginAuthorityError):
    """The server-side login event is malformed or unsafe."""


class LoginEventIdentityConflict(LoginAuthorityError):
    """One source event identity was reused for a different login date."""

    def __init__(self, *, user_id: int, source_event_id: str, existing_date: str, proposed_date: str):
        self.user_id = user_id
        self.source_event_id = source_event_id
        self.existing_date = existing_date
        self.proposed_date = proposed_date
        super().__init__(
            "source event identity is already bound to another local login date: "
            f"user_id={user_id!r}, source_event_id={source_event_id!r}, "
            f"existing_date={existing_date!r}, proposed_date={proposed_date!r}"
        )


class LoginSchemaUnavailable(LoginAuthorityError):
    """The additive D016 schema has not been installed."""


@dataclass(frozen=True)
class LoginStateResult:
    """Authoritative result returned after one caller-owned transaction step."""

    user_id: int
    local_login_date: str
    source_event_id: str
    outcome: str
    is_new_login_day: bool
    source_event_replayed: bool
    current_streak_days: int
    best_streak_days: int
    total_login_days: int
    last_login_date: str | None
    journey_id: str
    journey_version: int
    journey_day_completed: int
    journey_completed: bool
    journey_advanced: bool

    @property
    def duplicate(self) -> bool:
        return not self.is_new_login_day


@dataclass(frozen=True)
class LoginStateSnapshot:
    """Server-owned read projection suitable for a future authenticated API."""

    user_id: int
    current_streak_days: int
    best_streak_days: int
    total_login_days: int
    last_login_date: str | None
    journey_id: str
    journey_version: int
    journey_day_completed: int
    journey_completed: bool
    first_login_date: str | None
    last_progress_date: str | None


def _raw(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw(conn).__class__.__module__.lower().startswith("sqlite3")


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if hasattr(row, "keys"):
        return {str(key): row[key] for key in row.keys()}
    return dict(row)


def _normalize_user_id(value: Any) -> int:
    if isinstance(value, bool):
        raise LoginEventValidationError("user_id_invalid")
    try:
        user_id = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise LoginEventValidationError("user_id_invalid") from exc
    if user_id <= 0 or user_id > MAX_USER_ID:
        raise LoginEventValidationError("user_id_invalid")
    return user_id


def _normalize_text(value: Any, *, field: str, required: bool = True, max_length: int = 200) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise LoginEventValidationError(f"{field}_invalid")
    normalized = value.strip()
    if required and not normalized:
        raise LoginEventValidationError(f"{field}_required")
    if len(normalized) > max_length or any(ord(char) < 32 for char in normalized):
        raise LoginEventValidationError(f"{field}_invalid")
    return normalized


def _server_now(value: Any = None) -> datetime:
    """Normalize server time; callers never supply this from the browser."""

    value = value or datetime.now(timezone.utc)
    # QuestPeriodResolver deliberately requires an aware timestamp.  Passing
    # the same value as both occurrence and server_now gives us its one
    # canonical parser without creating a second timestamp implementation.
    try:
        return QuestPeriodResolver().validate_occurrence(value, server_now=value)
    except PeriodResolutionError as exc:
        raise LoginEventValidationError(str(exc)) from exc


def _resolve_login_date(occurred_at: Any, *, server_now: datetime) -> tuple[datetime, str]:
    resolver = QuestPeriodResolver()
    try:
        occurred_at_utc = resolver.validate_occurrence(occurred_at, server_now=server_now)
    except PeriodResolutionError as exc:
        raise LoginEventValidationError(str(exc)) from exc
    local_date = occurred_at_utc.astimezone(PERIOD_TIMEZONE).date().isoformat()
    return occurred_at_utc, local_date


def _db_timestamp(conn: Any, value: datetime) -> Any:
    return value.isoformat() if _is_sqlite(conn) else value


def _db_date(conn: Any, value: str | date | None) -> Any:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        parsed = value
    else:
        parsed = date.fromisoformat(str(value))
    return parsed.isoformat() if _is_sqlite(conn) else parsed


def _timestamp_identity(value: Any) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise LoginEventValidationError("stored_occurred_at_missing_timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value)).isoformat()


def _ensure_schema(conn: Any) -> None:
    try:
        conn.execute(f"SELECT 1 FROM {LOGIN_DAYS_TABLE_NAME} LIMIT 1").fetchone()
        conn.execute(f"SELECT 1 FROM {STREAK_TABLE_NAME} LIMIT 1").fetchone()
        conn.execute(f"SELECT 1 FROM {JOURNEY_TABLE_NAME} LIMIT 1").fetchone()
    except Exception as exc:
        text = str(exc).lower()
        if "no such table" in text or "does not exist" in text or "undefinedtable" in exc.__class__.__name__.lower():
            raise LoginSchemaUnavailable("D016 login schema is not installed") from exc
        raise


def _insert_ignore(conn: Any, table: str, columns: tuple[str, ...], values: tuple[Any, ...]) -> Any:
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    sql = f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
    return conn.execute(sql, values)


def _lock_user_state(conn: Any, *, user_id: int, updated_at: Any) -> dict[str, Any]:
    _insert_ignore(
        conn,
        STREAK_TABLE_NAME,
        ("user_id", "current_streak_days", "best_streak_days", "total_login_days", "last_login_date", "updated_at"),
        (user_id, 0, 0, 0, None, updated_at),
    )
    if _is_sqlite(conn):
        row = conn.execute(
            f"SELECT * FROM {STREAK_TABLE_NAME} WHERE user_id=?", (user_id,)
        ).fetchone()
    else:
        row = conn.execute(
            f"SELECT * FROM {STREAK_TABLE_NAME} WHERE user_id=? FOR UPDATE", (user_id,)
        ).fetchone()
    result = _row_to_dict(row)
    if result is None:
        raise LoginAuthorityError("login_streak_state_missing_after_lock")
    return result


def _read_login_dates(conn: Any, *, user_id: int) -> list[date]:
    rows = conn.execute(
        f"SELECT local_login_date FROM {LOGIN_DAYS_TABLE_NAME} "
        "WHERE user_id=? ORDER BY local_login_date ASC", (user_id,)
    ).fetchall()
    return [date.fromisoformat(_date_text(row["local_login_date"] if hasattr(row, "keys") else row[0])) for row in rows]


def _calculate_streaks(login_dates: list[date]) -> tuple[int, int, int, date | None]:
    if not login_dates:
        return 0, 0, 0, None
    unique_dates = sorted(set(login_dates))
    best = 0
    run = 0
    previous: date | None = None
    for current in unique_dates:
        if previous is not None and current == previous + timedelta(days=1):
            run += 1
        else:
            run = 1
        best = max(best, run)
        previous = current
    current = run if unique_dates[-1] == previous else 0
    return current, best, len(unique_dates), unique_dates[-1]


def _journey_projection(login_dates: list[date]) -> tuple[int, date | None, date | None, bool]:
    unique_dates = sorted(set(login_dates))
    completed_day_count = min(len(unique_dates), JOURNEY_LENGTH)
    if not unique_dates:
        return 0, None, None, False
    first = unique_dates[0]
    last_progress = unique_dates[completed_day_count - 1]
    return completed_day_count, first, last_progress, completed_day_count >= JOURNEY_LENGTH


def _existing_source_event(conn: Any, *, user_id: int, source_event_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        f"SELECT * FROM {LOGIN_DAYS_TABLE_NAME} WHERE user_id=? AND source_event_id=?",
        (user_id, source_event_id),
    ).fetchone()
    return _row_to_dict(row)


def _existing_journey(conn: Any, *, user_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        f"SELECT * FROM {JOURNEY_TABLE_NAME} WHERE user_id=?", (user_id,)
    ).fetchone()
    return _row_to_dict(row)


def record_authenticated_login(
    conn: Any,
    *,
    user_id: Any,
    occurred_at: Any,
    source_authority: Any = "auth:server",
    source_event_id: Any = None,
    source_operation_id: Any = None,
    server_now: Any = None,
) -> LoginStateResult:
    """Record one successful authenticated login in the caller transaction.

    ``occurred_at`` and ``server_now`` must be timezone-aware.  The service
    derives the Taiwan local date itself.  It never commits or rolls back;
    callers must roll back the whole transaction if a later mutation fails.
    """

    _ensure_schema(conn)
    normalized_user_id = _normalize_user_id(user_id)
    authority = _normalize_text(source_authority, field="source_authority")
    operation_id = _normalize_text(source_operation_id, field="source_operation_id", required=False)
    now_utc = _server_now(server_now)
    occurred_at_utc, local_login_date = _resolve_login_date(occurred_at, server_now=now_utc)
    event_id = _normalize_text(source_event_id, field="source_event_id", required=False)
    if event_id is None:
        event_id = f"server-login-{uuid.uuid4().hex}"

    prior_source = _existing_source_event(conn, user_id=normalized_user_id, source_event_id=event_id)
    if prior_source is not None:
        existing_date = _date_text(prior_source["local_login_date"])
        if existing_date != local_login_date:
            raise LoginEventIdentityConflict(
                user_id=normalized_user_id,
                source_event_id=event_id,
                existing_date=existing_date,
                proposed_date=local_login_date,
            )
        prior_authority = str(prior_source.get("source_authority") or "")
        prior_operation = prior_source.get("source_operation_id")
        if (
            prior_authority != authority
            or prior_operation != operation_id
            or _timestamp_identity(prior_source["occurred_at"]) != _timestamp_identity(occurred_at_utc)
        ):
            raise LoginEventValidationError("source_event_payload_conflict")

    recorded_at = _db_timestamp(conn, now_utc)
    # All durable per-user state is serialized by this row lock.  The ledger
    # insert follows it so adjacent-date races cannot calculate projections
    # from an arrival-order snapshot.
    _lock_user_state(conn, user_id=normalized_user_id, updated_at=recorded_at)
    insert_cursor = _insert_ignore(
        conn,
        LOGIN_DAYS_TABLE_NAME,
        (
            "user_id",
            "local_login_date",
            "source_event_id",
            "source_operation_id",
            "source_authority",
            "occurred_at",
            "recorded_at",
        ),
        (
            normalized_user_id,
            _db_date(conn, local_login_date),
            event_id,
            operation_id,
            authority,
            _db_timestamp(conn, occurred_at_utc),
            recorded_at,
        ),
    )
    is_new_login_day = int(getattr(insert_cursor, "rowcount", 0)) == 1
    if not is_new_login_day and prior_source is None:
        # A concurrent request may have won the source-event unique key after
        # the initial read.  Re-read the winner so a cross-day identity race
        # is reported as a deterministic conflict rather than being silently
        # mistaken for an ordinary same-day duplicate.
        prior_source = _existing_source_event(
            conn,
            user_id=normalized_user_id,
            source_event_id=event_id,
        )
        if prior_source is not None:
            existing_date = _date_text(prior_source["local_login_date"])
            if existing_date != local_login_date:
                raise LoginEventIdentityConflict(
                    user_id=normalized_user_id,
                    source_event_id=event_id,
                    existing_date=existing_date,
                    proposed_date=local_login_date,
                )
            prior_authority = str(prior_source.get("source_authority") or "")
            prior_operation = prior_source.get("source_operation_id")
            if (
                prior_authority != authority
                or prior_operation != operation_id
                or _timestamp_identity(prior_source["occurred_at"]) != _timestamp_identity(occurred_at_utc)
            ):
                raise LoginEventValidationError("source_event_payload_conflict")

    # One row lock serializes all projections for this user in PostgreSQL.
    # The ledger is then re-read and projected, so late events are handled by
    # event-date truth rather than by request arrival order.
    journey_before = _existing_journey(conn, user_id=normalized_user_id)
    login_dates = _read_login_dates(conn, user_id=normalized_user_id)
    current_streak, best_streak, total_days, last_login = _calculate_streaks(login_dates)
    journey_count, first_login, last_progress, journey_completed = _journey_projection(login_dates)
    old_journey_count = int(journey_before.get("completed_day_count", 0)) if journey_before else 0
    old_completed_at = journey_before.get("completed_at") if journey_before else None
    completed_at = old_completed_at or (recorded_at if journey_completed else None)

    conn.execute(
        f"UPDATE {STREAK_TABLE_NAME} SET current_streak_days=?, best_streak_days=?, "
        "total_login_days=?, last_login_date=?, updated_at=? WHERE user_id=?",
        (
            current_streak,
            best_streak,
            total_days,
            _db_date(conn, last_login),
            recorded_at,
            normalized_user_id,
        ),
    )
    _insert_ignore(
        conn,
        JOURNEY_TABLE_NAME,
        (
            "user_id",
            "journey_id",
            "journey_version",
            "completed_day_count",
            "first_login_date",
            "last_progress_date",
            "completed_at",
            "status",
            "updated_at",
        ),
        (
            normalized_user_id,
            JOURNEY_ID,
            JOURNEY_VERSION,
            journey_count,
            _db_date(conn, first_login),
            _db_date(conn, last_progress),
            completed_at,
            "COMPLETED" if journey_completed else "ACTIVE",
            recorded_at,
        ),
    )
    conn.execute(
        f"UPDATE {JOURNEY_TABLE_NAME} SET journey_id=?, journey_version=?, completed_day_count=?, "
        "first_login_date=?, last_progress_date=?, completed_at=?, status=?, updated_at=? WHERE user_id=?",
        (
            JOURNEY_ID,
            JOURNEY_VERSION,
            journey_count,
            _db_date(conn, first_login),
            _db_date(conn, last_progress),
            completed_at,
            "COMPLETED" if journey_completed else "ACTIVE",
            recorded_at,
            normalized_user_id,
        ),
    )

    return LoginStateResult(
        user_id=normalized_user_id,
        local_login_date=local_login_date,
        source_event_id=event_id,
        outcome="RECORDED" if is_new_login_day else "DUPLICATE",
        is_new_login_day=is_new_login_day,
        source_event_replayed=prior_source is not None,
        current_streak_days=current_streak,
        best_streak_days=best_streak,
        total_login_days=total_days,
        last_login_date=last_login.isoformat() if last_login else None,
        journey_id=JOURNEY_ID,
        journey_version=JOURNEY_VERSION,
        journey_day_completed=journey_count,
        journey_completed=journey_completed,
        journey_advanced=journey_count > old_journey_count,
    )


def get_login_state(conn: Any, *, user_id: Any) -> LoginStateSnapshot:
    """Read the server-owned projection without creating a state row."""

    _ensure_schema(conn)
    normalized_user_id = _normalize_user_id(user_id)
    streak = _row_to_dict(
        conn.execute(
            f"SELECT * FROM {STREAK_TABLE_NAME} WHERE user_id=?", (normalized_user_id,)
        ).fetchone()
    ) or {}
    journey = _row_to_dict(
        conn.execute(
            f"SELECT * FROM {JOURNEY_TABLE_NAME} WHERE user_id=?", (normalized_user_id,)
        ).fetchone()
    ) or {}
    return LoginStateSnapshot(
        user_id=normalized_user_id,
        current_streak_days=int(streak.get("current_streak_days", 0) or 0),
        best_streak_days=int(streak.get("best_streak_days", 0) or 0),
        total_login_days=int(streak.get("total_login_days", 0) or 0),
        last_login_date=_date_text(streak["last_login_date"]) if streak.get("last_login_date") else None,
        journey_id=str(journey.get("journey_id") or JOURNEY_ID),
        journey_version=int(journey.get("journey_version", JOURNEY_VERSION) or JOURNEY_VERSION),
        journey_day_completed=int(journey.get("completed_day_count", 0) or 0),
        journey_completed=str(journey.get("status") or "ACTIVE") == "COMPLETED",
        first_login_date=_date_text(journey["first_login_date"]) if journey.get("first_login_date") else None,
        last_progress_date=_date_text(journey["last_progress_date"]) if journey.get("last_progress_date") else None,
    )


__all__ = [
    "LOGIN_DAY_TIMEZONE",
    "LOGIN_EVENT_TYPE",
    "LoginAuthorityError",
    "LoginEventIdentityConflict",
    "LoginEventValidationError",
    "LoginSchemaUnavailable",
    "LoginStateResult",
    "LoginStateSnapshot",
    "get_login_state",
    "record_authenticated_login",
]
