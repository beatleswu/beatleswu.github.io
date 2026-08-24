"""D014 durable Quest V2 progress and exactly-once event application.

The service consumes D013's immutable authoritative event and deterministic
delta contracts.  It resolves each delta to an Asia/Taipei period, then
applies the complete event fan-out in one caller-owned transaction.  It never
commits, rolls back the caller's transaction, claims, or grants rewards.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable
import uuid

from migrations.quest_progress_v2 import (
    APPLICATION_TABLE_NAME,
    PROGRESS_TABLE_NAME,
)
from quest_catalog import QuestCatalog, QuestDefinition, CANONICAL_QUEST_CATALOG
from quest_period_authority import (
    QuestPeriodResolver,
    QUEST_PERIOD_RESOLVER,
)
from quest_progress_evaluator import (
    AuthoritativeEvent,
    ProgressDelta,
    evaluate_event,
)


class QuestProgressApplicationError(RuntimeError):
    """Base class for fail-closed durable progress errors."""


class UnknownQuestProgress(QuestProgressApplicationError):
    """A delta did not resolve to a canonical catalog definition."""


class ProgressApplicationConflict(QuestProgressApplicationError):
    """An existing application row disagrees with a replayed delta."""


class EventOrderingConflict(QuestProgressApplicationError):
    """A streak event arrived older than an already-applied event."""


@dataclass(frozen=True)
class QuestProgressApplication:
    user_id: int | str
    quest_id: str
    period_key: str
    source_event_id: str
    operation: str
    amount: int
    resulting_progress: int
    completed: bool
    definition_version: int
    duplicate: bool


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


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _user_key(user_id: Any) -> str:
    if isinstance(user_id, bool) or user_id is None:
        raise QuestProgressApplicationError("user_id_invalid")
    value = str(user_id).strip()
    if not value:
        raise QuestProgressApplicationError("user_id_required")
    return value


def _db_bool(conn: Any, value: bool) -> Any:
    return bool(value) if not _is_sqlite(conn) else int(bool(value))


def _canonical_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical_payload(value[key]) for key in sorted(value)}
    if hasattr(value, "items"):
        return {str(key): _canonical_payload(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_canonical_payload(item) for item in value]
    return value


def _event_payload_hash(event: AuthoritativeEvent) -> str:
    encoded = json.dumps(
        _canonical_payload(event.payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _row_value(row: Any, name: str, index: int) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _application_from_row(row: Any, *, user_id: int | str, duplicate: bool) -> QuestProgressApplication:
    return QuestProgressApplication(
        user_id=user_id,
        quest_id=str(_row_value(row, "quest_id", 2)),
        period_key=str(_row_value(row, "period_key", 3)),
        source_event_id=str(_row_value(row, "source_event_id", 1)),
        operation=str(_row_value(row, "operation", 7)),
        amount=int(_row_value(row, "amount", 8)),
        resulting_progress=int(_row_value(row, "resulting_progress", 9)),
        completed=bool(_row_value(row, "completed", 10)),
        definition_version=int(_row_value(row, "definition_version", 11)),
        duplicate=duplicate,
    )


def _select_application(
    conn: Any,
    *,
    user_key: str,
    event_id: str,
    quest_id: str,
) -> Any:
    return _fetchone(
        conn,
        f"""SELECT user_id, source_event_id, quest_id, period_key,
                          source_event_type, source_authority, source_operation_id, operation,
                          amount, resulting_progress, completed,
                          definition_version, target_snapshot, source_payload_hash,
                          source_occurred_at, applied_at
                     FROM {APPLICATION_TABLE_NAME}
                    WHERE user_id=? AND source_event_id=?
                      AND quest_id=?""",
        (user_key, event_id, quest_id),
    )


def _ensure_progress_row(conn: Any, *, user_key: str, definition: QuestDefinition, period_key: str, now: str) -> None:
    _execute(
        conn,
        f"""INSERT INTO {PROGRESS_TABLE_NAME} (
                    user_id, quest_id, period_key, progress, completed,
                    definition_version, target_snapshot, created_at, updated_at
                ) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id, quest_id, period_key) DO NOTHING""",
        (
            user_key,
            definition.quest_id,
            period_key,
            _db_bool(conn, False),
            definition.version,
            definition.target,
            now,
            now,
        ),
    )


def _select_progress_for_update(conn: Any, *, user_key: str, quest_id: str, period_key: str) -> Any:
    suffix = "" if _is_sqlite(conn) else " FOR UPDATE"
    return _fetchone(
        conn,
        f"""SELECT user_id, quest_id, period_key, progress, completed,
                          definition_version, target_snapshot, created_at, updated_at
                     FROM {PROGRESS_TABLE_NAME}
                    WHERE user_id=? AND quest_id=? AND period_key=?{suffix}""",
        (user_key, quest_id, period_key),
    )


def _select_latest_streak_application(conn: Any, *, user_key: str, quest_id: str, period_key: str) -> Any:
    return _fetchone(
        conn,
        f"""SELECT source_event_id, source_operation_id, source_occurred_at
                     FROM {APPLICATION_TABLE_NAME}
                    WHERE user_id=? AND quest_id=? AND period_key=?
                 ORDER BY source_occurred_at DESC,
                          source_operation_id DESC,
                          source_event_id DESC
                    LIMIT 1""",
        (user_key, quest_id, period_key),
    )


def _ordering_key(*, occurred_at_utc: datetime, source_operation_id: str, event_id: str) -> tuple[str, str, str]:
    stamp = occurred_at_utc.astimezone(timezone.utc).isoformat(timespec="microseconds")
    return stamp, source_operation_id, event_id


def _stored_ordering_key(row: Any) -> tuple[str, str, str]:
    occurred_at = str(_row_value(row, "source_occurred_at", 2))
    if occurred_at.endswith("Z"):
        occurred_at = occurred_at[:-1] + "+00:00"
    parsed = datetime.fromisoformat(occurred_at).astimezone(timezone.utc)
    return (
        parsed.isoformat(timespec="microseconds"),
        str(_row_value(row, "source_operation_id", 1)),
        str(_row_value(row, "source_event_id", 0)),
    )


def _stored_occurred_at(row: Any) -> datetime:
    occurred_at = str(_row_value(row, "source_occurred_at", 14))
    if occurred_at.endswith("Z"):
        occurred_at = occurred_at[:-1] + "+00:00"
    return datetime.fromisoformat(occurred_at).astimezone(timezone.utc)


def _is_streak_definition(definition: QuestDefinition) -> bool:
    return definition.filters.get("streak_scope") == "daily_consecutive"


def _catalog_status_allows_application(definition: QuestDefinition) -> bool:
    return definition.availability.get("catalog_status") not in {"disabled", "retired"}


def _validate_delta(
    *,
    event: AuthoritativeEvent,
    delta: ProgressDelta,
    definition: QuestDefinition,
) -> None:
    if delta.source_event_id != event.event_id:
        raise ProgressApplicationConflict("delta_source_event_mismatch")
    if delta.quest_id != definition.quest_id:
        raise UnknownQuestProgress("delta_quest_not_canonical")
    if delta.period != definition.period:
        raise ProgressApplicationConflict("delta_period_mismatch")


def _apply_delta(
    conn: Any,
    *,
    event: AuthoritativeEvent,
    delta: ProgressDelta,
    definition: QuestDefinition,
    period_key: str,
    occurred_at_utc: datetime,
) -> QuestProgressApplication:
    user_key = _user_key(event.user_id)
    target = definition.target
    if not isinstance(target, int) or isinstance(target, bool) or target <= 0:
        raise QuestProgressApplicationError("catalog_target_invalid")
    now = _now_text()
    _ensure_progress_row(
        conn,
        user_key=user_key,
        definition=definition,
        period_key=period_key,
        now=now,
    )
    progress_row = _select_progress_for_update(
        conn,
        user_key=user_key,
        quest_id=definition.quest_id,
        period_key=period_key,
    )
    if progress_row is None:
        raise QuestProgressApplicationError("progress_row_not_created")

    existing_application = _select_application(
        conn,
        user_key=user_key,
        event_id=event.event_id,
        quest_id=definition.quest_id,
    )
    if existing_application is not None:
        if (
            str(_row_value(existing_application, "operation", 7)) != delta.operation
            or int(_row_value(existing_application, "amount", 8)) != delta.amount
            or str(_row_value(existing_application, "period_key", 3)) != period_key
            or str(_row_value(existing_application, "source_event_type", 4)) != event.event_type
            or str(_row_value(existing_application, "source_authority", 5)) != event.source_authority
            or str(_row_value(existing_application, "source_operation_id", 6)) != event.source_operation_id
            or str(_row_value(existing_application, "source_payload_hash", 13)) != _event_payload_hash(event)
            or _stored_occurred_at(existing_application) != occurred_at_utc.astimezone(timezone.utc)
        ):
            raise ProgressApplicationConflict("replayed_delta_disagrees_with_application")
        return _application_from_row(existing_application, user_id=event.user_id, duplicate=True)

    if _is_streak_definition(definition):
        latest = _select_latest_streak_application(
            conn,
            user_key=user_key,
            quest_id=definition.quest_id,
            period_key=period_key,
        )
        if latest is not None:
            incoming_order = _ordering_key(
                occurred_at_utc=occurred_at_utc,
                source_operation_id=event.source_operation_id,
                event_id=event.event_id,
            )
            latest_order = _stored_ordering_key(latest)
            # D013 exposes an occurrence timestamp but no authoritative
            # sequence number.  Never invent chronology from a random
            # operation UUID or arrival order: older and same-timestamp
            # distinct streak events fail closed.  Ordinary cumulative
            # quests remain order-independent.
            if incoming_order[0] <= latest_order[0]:
                raise EventOrderingConflict("streak_event_arrived_out_of_order")

    current_progress = int(_row_value(progress_row, "progress", 3))
    current_completed = bool(_row_value(progress_row, "completed", 4))
    stored_version = int(_row_value(progress_row, "definition_version", 5))
    stored_target = int(_row_value(progress_row, "target_snapshot", 6))
    if stored_version != definition.version or stored_target != definition.target:
        raise ProgressApplicationConflict("quest_definition_lineage_changed")
    if delta.operation == "RESET":
        # The legacy daily streak is terminal after completion.  A later
        # incorrect answer is recorded as applied but does not reopen it.
        next_progress = current_progress if current_completed else 0
        next_completed = current_completed
    elif delta.operation == "INCREMENT":
        next_progress = min(target, max(0, current_progress) + delta.amount)
        next_completed = current_completed or next_progress >= target
    else:
        raise ProgressApplicationConflict("unsupported_delta_operation")

    updated_at = _now_text()
    _execute(
        conn,
        f"""UPDATE {PROGRESS_TABLE_NAME}
                  SET progress=?, completed=?, updated_at=?
                WHERE user_id=? AND quest_id=? AND period_key=?""",
        (
            next_progress,
            _db_bool(conn, next_completed),
            updated_at,
            user_key,
            definition.quest_id,
            period_key,
        ),
    )
    source_occurred_at = occurred_at_utc.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    _execute(
        conn,
                f"""INSERT INTO {APPLICATION_TABLE_NAME} (
                    user_id, source_event_id, quest_id, period_key,
                    source_event_type, source_authority, source_operation_id, operation,
                    amount, resulting_progress, completed, definition_version,
                    target_snapshot,
                    source_payload_hash,
                    source_occurred_at, applied_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_key,
            event.event_id,
            definition.quest_id,
            period_key,
            event.event_type,
            event.source_authority,
            event.source_operation_id,
            delta.operation,
            delta.amount,
            next_progress,
            _db_bool(conn, next_completed),
            definition.version,
            definition.target,
            _event_payload_hash(event),
            source_occurred_at,
            updated_at,
        ),
    )
    return QuestProgressApplication(
        user_id=event.user_id,
        quest_id=definition.quest_id,
        period_key=period_key,
        source_event_id=event.event_id,
        operation=delta.operation,
        amount=delta.amount,
        resulting_progress=next_progress,
        completed=next_completed,
        definition_version=definition.version,
        duplicate=False,
    )


def apply_progress_deltas(
    conn: Any,
    *,
    event: AuthoritativeEvent,
    deltas: Iterable[ProgressDelta],
    catalog: QuestCatalog | None = None,
    period_resolver: QuestPeriodResolver = QUEST_PERIOD_RESOLVER,
    server_now: datetime | None = None,
) -> tuple[QuestProgressApplication, ...]:
    """Apply one event's complete delta fan-out atomically in caller scope."""

    if not isinstance(event, AuthoritativeEvent):
        raise QuestProgressApplicationError("authoritative_event_instance_required")
    active_catalog = catalog or CANONICAL_QUEST_CATALOG
    if not isinstance(active_catalog, QuestCatalog):
        raise QuestProgressApplicationError("quest_catalog_instance_required")
    deltas = tuple(deltas)
    expected_deltas = frozenset(evaluate_event(event, active_catalog))

    # Validate the event timestamp even when it happens to match zero Quests.
    occurred_at_utc = period_resolver.validate_occurrence(
        event.occurred_at,
        server_now=server_now,
    )
    savepoint = f"d014_apply_{uuid.uuid4().hex}"
    _execute(conn, f"SAVEPOINT {savepoint}")
    try:
        results: list[QuestProgressApplication] = []
        for delta in deltas:
            definition = active_catalog.canonical_map.get(delta.quest_id)
            if definition is None or not definition.enabled or not _catalog_status_allows_application(definition):
                raise UnknownQuestProgress("unknown_or_disabled_quest_delta")
            if delta not in expected_deltas:
                raise ProgressApplicationConflict("delta_not_authoritative")
            _validate_delta(event=event, delta=delta, definition=definition)
            resolved = period_resolver.resolve_definition(
                definition,
                event.occurred_at,
                server_now=server_now,
            )
            if resolved is None:
                # An event outside a governed event window is not an applied
                # event and therefore must not create a ledger row.
                continue
            results.append(
                _apply_delta(
                    conn,
                    event=event,
                    delta=delta,
                    definition=definition,
                    period_key=resolved.period_key,
                    occurred_at_utc=resolved.occurred_at_utc,
                )
            )
        _execute(conn, f"RELEASE SAVEPOINT {savepoint}")
        return tuple(results)
    except Exception:
        _execute(conn, f"ROLLBACK TO SAVEPOINT {savepoint}")
        _execute(conn, f"RELEASE SAVEPOINT {savepoint}")
        raise


def apply_authoritative_event(
    conn: Any,
    *,
    event: AuthoritativeEvent,
    catalog: QuestCatalog | None = None,
    period_resolver: QuestPeriodResolver = QUEST_PERIOD_RESOLVER,
    server_now: datetime | None = None,
) -> tuple[QuestProgressApplication, ...]:
    """Evaluate D013 and persist all resulting D014 applications."""

    deltas = evaluate_event(event, catalog or CANONICAL_QUEST_CATALOG)
    return apply_progress_deltas(
        conn,
        event=event,
        deltas=deltas,
        catalog=catalog,
        period_resolver=period_resolver,
        server_now=server_now,
    )


__all__ = [
    "EventOrderingConflict",
    "ProgressApplicationConflict",
    "QuestProgressApplication",
    "QuestProgressApplicationError",
    "UnknownQuestProgress",
    "apply_authoritative_event",
    "apply_progress_deltas",
]
