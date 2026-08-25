"""D017's single server event-to-Quest runtime boundary.

This module composes, but does not replace, D012 catalog/identity, D013
evaluation, D014 period/progress, and D016/D015 authorities.  Callers own the
open transaction.  In particular, this module never settles a reward and
never commits or rolls back the caller's connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from migrations.quest_progress_v2 import APPLICATION_TABLE_NAME, PROGRESS_TABLE_NAME
from quest_catalog import (
    CANONICAL_QUEST_CATALOG,
    CURRENT_DAILY_PRIMARY_KEYS,
    QuestCatalog,
)
from quest_period_authority import QuestPeriodResolver, QUEST_PERIOD_RESOLVER
from quest_progress_authority import (
    QuestProgressApplication,
    apply_authoritative_event,
)
from quest_progress_evaluator import AuthoritativeEvent
from question_idempotency import IdempotencyIdentityError, normalize_identity


class QuestRuntimeError(RuntimeError):
    """Base class for fail-closed runtime integration failures."""


class QuestRuntimeEventIdentityError(ValueError, QuestRuntimeError):
    """A source event identity was not server-bound and valid."""


@dataclass(frozen=True)
class QuestRuntimeApplication:
    """Committed-in-caller-transaction result for one source event."""

    event_id: str
    applications: tuple[QuestProgressApplication, ...]
    derived_applications: tuple[QuestProgressApplication, ...]

    @property
    def all_applications(self) -> tuple[QuestProgressApplication, ...]:
        return self.applications + self.derived_applications


def _raw(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw(conn).__class__.__module__.lower().startswith("sqlite3")


def _execute(conn: Any, sql: str, params: Iterable[Any] = ()) -> Any:
    params = tuple(params)
    if hasattr(conn, "execute"):
        return conn.execute(sql, params)
    cursor = conn.cursor()
    cursor.execute(sql.replace("?", "%s"), params)
    return cursor


def _fetchone(conn: Any, sql: str, params: Iterable[Any] = ()) -> Any:
    cursor = _execute(conn, sql, params)
    try:
        return cursor.fetchone()
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _row_value(row: Any, key: str, index: int) -> Any:
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _user_key(user_id: Any) -> str:
    if isinstance(user_id, bool) or user_id is None:
        raise QuestRuntimeError("user_id_invalid")
    value = str(user_id).strip()
    if not value:
        raise QuestRuntimeError("user_id_required")
    return value


def _server_now(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise QuestRuntimeError("server_now_must_be_timezone_aware")
    return value.astimezone(timezone.utc)


def _bound_source_identity(value: Any, *, field: str) -> str:
    try:
        identity, generated = normalize_identity(
            value,
            field=field,
            generate_if_missing=False,
        )
    except IdempotencyIdentityError as exc:
        raise QuestRuntimeEventIdentityError(str(exc)) from exc
    if generated:
        raise QuestRuntimeEventIdentityError(f"{field}_must_be_server_bound")
    return identity


def build_review_settlement_event(
    *,
    user_id: int | str,
    submission_id: Any,
    occurred_at: str,
    correct: bool,
    monster_family: str | None = None,
    source_scope: str = "daily_battlefield",
) -> AuthoritativeEvent:
    """Build a Quest event from a committed D5B review identity.

    ``submission_id`` is accepted only after the review authority has bound
    it to the authenticated user and authoritative grade.  The client never
    supplies the resulting Quest event ID or correctness payload.
    """

    submission = _bound_source_identity(submission_id, field="submission_id")
    payload: dict[str, Any] = {
        "correct": bool(correct),
        "source_scope": source_scope,
        # This is the server-owned compatibility vocabulary for the current
        # D012 streak quest; it is never copied from the request payload.
        "streak_scope": "daily_consecutive",
    }
    if monster_family:
        payload["monster_family"] = str(monster_family)
    return AuthoritativeEvent.from_server(
        event_id=f"quest:review:{submission}:answer",
        event_type="QUESTION_CORRECT",
        user_id=user_id,
        source_authority="review_settlement",
        source_operation_id=f"review:{submission}",
        occurred_at=occurred_at,
        payload=payload,
    )


def build_monster_defeat_event(
    *,
    user_id: int | str,
    submission_id: Any,
    occurred_at: str,
    monster_family: str,
    monster_id: str | None = None,
    encounter_class: str | None = None,
    source_scope: str = "daily_battlefield",
) -> AuthoritativeEvent:
    """Build a Quest event from a server-computed Monster defeat result."""

    submission = _bound_source_identity(submission_id, field="submission_id")
    payload: dict[str, Any] = {
        "source_scope": source_scope,
        "monster_family": str(monster_family),
    }
    if monster_id:
        payload["monster_id"] = str(monster_id)
    if encounter_class:
        payload["encounter_class"] = str(encounter_class)
    return AuthoritativeEvent.from_server(
        event_id=f"quest:review:{submission}:monster-defeat",
        event_type="MONSTER_DEFEATED",
        user_id=user_id,
        source_authority="monster_settlement",
        source_operation_id=f"review:{submission}:monster-defeat",
        occurred_at=occurred_at,
        payload=payload,
    )


def build_server_quest_event(
    *,
    event_id: Any,
    event_type: str,
    user_id: int | str,
    source_authority: str,
    source_operation_id: Any,
    occurred_at: str,
    payload: Mapping[str, Any],
) -> AuthoritativeEvent:
    """Common adapter for future authoritative Adventure/Spirit/Lord sources."""

    return AuthoritativeEvent.from_server(
        event_id=_bound_source_identity(event_id, field="event_id"),
        event_type=event_type,
        user_id=user_id,
        source_authority=source_authority,
        source_operation_id=_bound_source_identity(source_operation_id, field="source_operation_id"),
        occurred_at=occurred_at,
        payload=payload,
    )


def _daily_primary_period(
    resolver: QuestPeriodResolver,
    catalog: QuestCatalog,
    occurred_at: str,
    *,
    server_now: datetime,
) -> tuple[str, str] | None:
    definition = catalog.canonical_map.get("daily:kill_monsters")
    if definition is None:
        return None
    resolved = resolver.resolve_definition(definition, occurred_at, server_now=server_now)
    if resolved is None:
        return None
    return resolved.period_key, resolved.occurred_at_utc.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _completed_primary_ids(
    conn: Any,
    *,
    user_key: str,
    period_key: str,
    catalog: QuestCatalog,
) -> tuple[str, ...]:
    ids = tuple(f"daily:{key}" for key in CURRENT_DAILY_PRIMARY_KEYS)
    placeholders = ",".join("?" for _ in ids)
    suffix = "" if _is_sqlite(conn) else " FOR UPDATE"
    rows = _execute(
        conn,
        f"""SELECT quest_id, progress, completed, definition_version, target_snapshot
                  FROM {PROGRESS_TABLE_NAME}
                 WHERE user_id=? AND period_key=? AND quest_id IN ({placeholders})
                 ORDER BY quest_id{suffix}""",
        (user_key, period_key, *ids),
    ).fetchall()
    completed: list[str] = []
    for row in rows:
        quest_id = str(_row_value(row, "quest_id", 0))
        definition = catalog.canonical_map.get(quest_id)
        if definition is None:
            continue
        if (
            int(_row_value(row, "progress", 1) or 0) >= int(definition.target or 0)
            and bool(_row_value(row, "completed", 2))
            and int(_row_value(row, "definition_version", 3) or 0) == int(definition.version)
            and int(_row_value(row, "target_snapshot", 4) or 0) == int(definition.target or 0)
        ):
            completed.append(quest_id)
    return tuple(sorted(completed))


def _derive_daily_completion(
    conn: Any,
    *,
    source_event: AuthoritativeEvent,
    catalog: QuestCatalog,
    period_resolver: QuestPeriodResolver,
    server_now: datetime,
) -> tuple[QuestProgressApplication, ...]:
    """Derive all_complete from locked durable primary progress only once."""

    bonus = catalog.canonical_map.get("daily:all_complete")
    if bonus is None or not bonus.enabled:
        return ()
    resolved = period_resolver.resolve_definition(
        bonus,
        source_event.occurred_at,
        server_now=server_now,
    )
    if resolved is None:
        return ()
    user_key = _user_key(source_event.user_id)
    completed_ids = _completed_primary_ids(
        conn,
        user_key=user_key,
        period_key=resolved.period_key,
        catalog=catalog,
    )
    expected_ids = tuple(sorted(f"daily:{key}" for key in CURRENT_DAILY_PRIMARY_KEYS))
    if completed_ids != expected_ids:
        return ()

    derived_event_id = f"quest:set-completion:{user_key}:{resolved.period_key}:daily_primary"
    existing = _fetchone(
        conn,
        f"""SELECT source_event_id FROM {APPLICATION_TABLE_NAME}
                   WHERE user_id=? AND source_event_id=? AND quest_id=?""",
        (user_key, derived_event_id, bonus.quest_id),
    )
    if existing is not None:
        return ()

    derived_event = AuthoritativeEvent.from_server(
        event_id=derived_event_id,
        event_type="QUEST_SET_COMPLETED",
        user_id=source_event.user_id,
        source_authority="quest_evaluator:derived",
        source_operation_id=derived_event_id,
        occurred_at=source_event.occurred_at,
        payload={
            "quest_group": "daily_primary",
            "completed_quest_ids": expected_ids,
        },
    )
    return apply_authoritative_event(
        conn,
        event=derived_event,
        catalog=catalog,
        period_resolver=period_resolver,
        server_now=server_now,
    )


def apply_quest_runtime_event(
    conn: Any,
    *,
    event: AuthoritativeEvent,
    catalog: QuestCatalog | None = None,
    period_resolver: QuestPeriodResolver = QUEST_PERIOD_RESOLVER,
    server_now: datetime | None = None,
) -> QuestRuntimeApplication:
    """Evaluate and persist one authoritative event through D013/D014."""

    if not isinstance(event, AuthoritativeEvent):
        raise QuestRuntimeError("authoritative_event_instance_required")
    active_catalog = catalog or CANONICAL_QUEST_CATALOG
    now = _server_now(server_now)
    applications = apply_authoritative_event(
        conn,
        event=event,
        catalog=active_catalog,
        period_resolver=period_resolver,
        server_now=now,
    )
    derived = ()
    if event.event_type != "QUEST_SET_COMPLETED":
        derived = _derive_daily_completion(
            conn,
            source_event=event,
            catalog=active_catalog,
            period_resolver=period_resolver,
            server_now=now,
        )
    return QuestRuntimeApplication(
        event_id=event.event_id,
        applications=tuple(applications),
        derived_applications=tuple(derived),
    )


__all__ = [
    "QuestRuntimeApplication",
    "QuestRuntimeError",
    "QuestRuntimeEventIdentityError",
    "apply_quest_runtime_event",
    "build_monster_defeat_event",
    "build_review_settlement_event",
    "build_server_quest_event",
]
