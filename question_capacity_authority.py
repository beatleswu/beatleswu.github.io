"""Caller-owned question-capacity mutation authority.

This is the reusable D5B boundary for the three server-defined capacity
benefits.  It deliberately owns the active_effects mutation and its
QUESTION_CAPACITY evidence, but never commits or rolls back the caller's
transaction.  Premium claims may call it with ``consume_inventory=False``
when the benefit is granted directly by an authoritative Premium claim; the
capacity state is still created through this same authority.
"""

from __future__ import annotations

import datetime as _datetime
import uuid
from dataclasses import dataclass
from typing import Any

from event_outbox import DuplicateOutboxEvent, append_event, get_event_by_idempotency_key


FREE_DAILY_LIMIT = 20
CAPACITY_DELTAS = {
    "extra_questions_small": 5,
    "extra_questions": 10,
    "grand_training_pass": 20,
}
EVENT_TYPE = "QUESTION_CAPACITY"


class QuestionCapacityError(RuntimeError):
    """Base class for fail-closed capacity mutation errors."""


class QuestionCapacityConflict(QuestionCapacityError):
    """A durable operation identity is bound to a different use."""


class QuestionCapacityNotOwned(QuestionCapacityError):
    """The caller requested an inventory-backed use without ownership."""


class QuestionCapacityLineageUnavailable(QuestionCapacityError):
    """A committed capacity mutation cannot be reconstructed with evidence."""


@dataclass(frozen=True)
class QuestionCapacityMutation:
    user_id: int
    item_id: str
    operation_id: str
    capacity_delta: int
    business_date: str
    effective_capacity_after: int
    effect_id: int
    event_id: str
    duplicate: bool
    resulting_quantity: int | None

    def as_payload(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "operation_id": self.operation_id,
            "capacity_delta": self.capacity_delta,
            "base_capacity": FREE_DAILY_LIMIT,
            "effective_capacity_after": self.effective_capacity_after,
            "business_date": self.business_date,
            "effect_id": self.effect_id,
            "capacity_event_id": self.event_id,
            "duplicate": self.duplicate,
            "resulting_quantity": self.resulting_quantity,
        }


def _now(value: _datetime.datetime | None) -> _datetime.datetime:
    current = value or _datetime.datetime.now()
    return current.replace(tzinfo=_datetime.timezone.utc) if current.tzinfo is None else current.astimezone()


def _event_key(operation_id: str) -> str:
    return f"question-capacity:{operation_id}"


def _savepoint(conn: Any) -> str:
    name = f"d5b_capacity_{uuid.uuid4().hex}"
    conn.execute(f"SAVEPOINT {name}")
    return name


def _rollback_savepoint(conn: Any, name: str) -> None:
    conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
    conn.execute(f"RELEASE SAVEPOINT {name}")


def _release_savepoint(conn: Any, name: str) -> None:
    conn.execute(f"RELEASE SAVEPOINT {name}")


def _extra_questions_today(conn: Any, user_id: int, business_date: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(value),0) AS total FROM active_effects "
        "WHERE user_id=? AND effect_key='extra_questions' AND effect_date=?",
        (user_id, business_date),
    ).fetchone()
    return int(row["total"] or 0)


def _existing_effect(conn: Any, user_id: int, operation_id: str) -> Any:
    return conn.execute(
        "SELECT * FROM active_effects WHERE user_id=? AND operation_id=?",
        (user_id, operation_id),
    ).fetchone()


def _validate_existing(effect: Any, *, item_id: str, capacity_delta: int, business_date: str) -> None:
    source_item = effect["source_item_key"]
    if (
        source_item != item_id
        or int(effect["value"]) != capacity_delta
        or effect["effect_date"] != business_date
    ):
        raise QuestionCapacityConflict("operation_id is already bound to a different capacity use")


def _recover_duplicate(
    conn: Any,
    *,
    effect: Any,
    user_id: int,
    item_id: str,
    capacity_delta: int,
    business_date: str,
) -> QuestionCapacityMutation:
    _validate_existing(
        effect,
        item_id=item_id,
        capacity_delta=capacity_delta,
        business_date=business_date,
    )
    event = get_event_by_idempotency_key(
        conn,
        player_id=str(user_id),
        event_type=EVENT_TYPE,
        idempotency_key=_event_key(str(effect["operation_id"])),
    )
    if event is None:
        raise QuestionCapacityLineageUnavailable("capacity mutation has no committed QUESTION_CAPACITY event")
    row = conn.execute(
        "SELECT qty FROM shop_inventory WHERE user_id=? AND item_key=?",
        (user_id, item_id),
    ).fetchone()
    return QuestionCapacityMutation(
        user_id=user_id,
        item_id=item_id,
        operation_id=str(effect["operation_id"]),
        capacity_delta=capacity_delta,
        business_date=business_date,
        effective_capacity_after=FREE_DAILY_LIMIT + _extra_questions_today(conn, user_id, business_date),
        effect_id=int(effect["id"]),
        event_id=str(event["event_id"]),
        duplicate=True,
        resulting_quantity=int(row["qty"] or 0) if row else 0,
    )


def apply_question_capacity_in_transaction(
    conn: Any,
    *,
    user_id: int,
    item_id: str,
    operation_id: str,
    source: str,
    source_reference: str | None = None,
    lineage_id: str | None = None,
    source_event_id: str | None = None,
    consume_inventory: bool,
    now: _datetime.datetime | None = None,
    event_writer: Any = None,
) -> QuestionCapacityMutation:
    """Apply one capacity benefit inside the caller's open transaction.

    The operation identity is the active-effect mutation identity.  The
    outbox row is appended after the effect row exists and is never used to
    decide whether the mutation is allowed.  A local savepoint makes a
    duplicate/rejection recoverable without aborting the caller transaction.
    """

    user_id = int(user_id)
    item_id = str(item_id or "").strip()
    operation_id = str(operation_id or "").strip()
    if item_id not in CAPACITY_DELTAS:
        raise QuestionCapacityError("unsupported question capacity item")
    if not operation_id:
        raise QuestionCapacityError("operation_id is required")
    capacity_delta = CAPACITY_DELTAS[item_id]
    business_date = _now(now).date().isoformat()

    existing = _existing_effect(conn, user_id, operation_id)
    if existing is not None:
        return _recover_duplicate(
            conn,
            effect=existing,
            user_id=user_id,
            item_id=item_id,
            capacity_delta=capacity_delta,
            business_date=business_date,
        )

    savepoint = _savepoint(conn)
    try:
        resulting_quantity: int | None = None
        if consume_inventory:
            updated = conn.execute(
                "UPDATE shop_inventory SET qty=qty-1 "
                "WHERE user_id=? AND item_key=? AND qty>=1",
                (user_id, item_id),
            )
            if int(getattr(updated, "rowcount", 0) or 0) != 1:
                raise QuestionCapacityNotOwned("capacity item is not owned")
            inventory_row = conn.execute(
                "SELECT qty FROM shop_inventory WHERE user_id=? AND item_key=?",
                (user_id, item_id),
            ).fetchone()
            resulting_quantity = int(inventory_row["qty"] or 0) if inventory_row else 0

        inserted = conn.execute(
            "INSERT INTO active_effects("
            "user_id,effect_key,value,effect_date,created_at,operation_id,source_item_key) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            (
                user_id,
                "extra_questions",
                capacity_delta,
                business_date,
                _now(now).isoformat(timespec="seconds"),
                operation_id,
                item_id,
            ),
        )
        if int(getattr(inserted, "rowcount", 0) or 0) != 1:
            _rollback_savepoint(conn, savepoint)
            effect = _existing_effect(conn, user_id, operation_id)
            if effect is None:
                raise QuestionCapacityLineageUnavailable("capacity duplicate effect is not recoverable")
            return _recover_duplicate(
                conn,
                effect=effect,
                user_id=user_id,
                item_id=item_id,
                capacity_delta=capacity_delta,
                business_date=business_date,
            )

        effect = _existing_effect(conn, user_id, operation_id)
        if effect is None:
            raise QuestionCapacityLineageUnavailable("capacity effect insert is not recoverable")
        effective_capacity_after = FREE_DAILY_LIMIT + _extra_questions_today(conn, user_id, business_date)
        write_event = event_writer or append_event
        event = write_event(
            conn,
            event_type=EVENT_TYPE,
            player_id=str(user_id),
            lineage_id=str(lineage_id or operation_id),
            source_event_id=str(source_event_id or f"active_effects:{effect['id']}"),
            idempotency_key=_event_key(operation_id),
            outcome="SUCCESS",
            payload={
                "operation": "CONSUME",
                "operation_id": operation_id,
                "item_id": item_id,
                "capacity_delta": capacity_delta,
                "base_capacity": FREE_DAILY_LIMIT,
                "effective_capacity_after": effective_capacity_after,
                "business_date": business_date,
                "effect_id": int(effect["id"]),
                "source": source,
                "source_reference": source_reference,
                "inventory_consumed": bool(consume_inventory),
            },
            occurred_at=_now(now),
        )
        _release_savepoint(conn, savepoint)
        return QuestionCapacityMutation(
            user_id=user_id,
            item_id=item_id,
            operation_id=operation_id,
            capacity_delta=capacity_delta,
            business_date=business_date,
            effective_capacity_after=effective_capacity_after,
            effect_id=int(effect["id"]),
            event_id=str(event["event_id"]),
            duplicate=False,
            resulting_quantity=resulting_quantity,
        )
    except DuplicateOutboxEvent as duplicate:
        _rollback_savepoint(conn, savepoint)
        effect = _existing_effect(conn, user_id, operation_id)
        if effect is None:
            raise QuestionCapacityLineageUnavailable("duplicate capacity event has no effect row") from duplicate
        return _recover_duplicate(
            conn,
            effect=effect,
            user_id=user_id,
            item_id=item_id,
            capacity_delta=capacity_delta,
            business_date=business_date,
        )
    except Exception:
        try:
            _rollback_savepoint(conn, savepoint)
        except Exception:
            pass
        raise


__all__ = [
    "CAPACITY_DELTAS",
    "FREE_DAILY_LIMIT",
    "QuestionCapacityConflict",
    "QuestionCapacityError",
    "QuestionCapacityLineageUnavailable",
    "QuestionCapacityMutation",
    "QuestionCapacityNotOwned",
    "apply_question_capacity_in_transaction",
]
