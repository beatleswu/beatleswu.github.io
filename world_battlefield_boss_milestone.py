"""Pure F015 storage service for consumed Battlefield Boss facts.

The service accepts only the validated F012 defeated-fact type.  It records a
World milestone evidence projection with the composite key
``(user_id, settlement_id)`` and returns a detached replay-safe result.

It never builds facts, calculates World policy, emits Quest events, or
commits.  The caller owns the transaction and must apply the candidate
migration before calling the service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from migrations.world_battlefield_boss_milestone_v1 import (
    CONTRACT_VERSION,
    SOURCE_AUTHORITY,
    SOURCE_EVENT_TYPE,
    TABLE_NAME,
    validate_schema,
)
from world_monster_boundary_contract import (
    BattlefieldBossDefeatedFact,
)


class MilestoneProjectionError(RuntimeError):
    """Base class for F015 storage failures."""


class MilestoneProjectionSchemaUnavailable(MilestoneProjectionError):
    """The additive candidate schema has not been applied to this connection."""


class MilestoneProjectionValidationError(ValueError, MilestoneProjectionError):
    """The supplied typed fact lacks required F014 provenance evidence."""


class MilestoneProjectionConflict(MilestoneProjectionError):
    """A dedupe key was reused with changed authoritative evidence."""


@dataclass(frozen=True, slots=True)
class BattlefieldBossMilestoneRecordResult:
    """Detached storage result; contains no World progression decision."""

    user_id: int
    settlement_id: str
    zone_key: str
    monster_id: str
    encounter_operation_id: str
    recorded: bool
    replayed: bool
    created_at: str


_SELECT_COLUMNS = (
    "user_id",
    "settlement_id",
    "zone_key",
    "monster_id",
    "encounter_operation_id",
    "created_at",
)
_AUTHORITATIVE_COLUMNS = (
    "user_id",
    "settlement_id",
    "zone_key",
    "monster_id",
    "encounter_operation_id",
    "eligibility_reference",
    "intent_replay_fingerprint",
    "source_authority",
    "source_event_type",
    "contract_version",
)


def _raw(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw(conn).__class__.__module__.lower().startswith("sqlite3")


def _execute(conn: Any, sql: str, params: Iterable[Any] = ()) -> Any:
    values = tuple(params)
    if hasattr(conn, "execute"):
        return conn.execute(sql, values)
    cursor = conn.cursor()
    cursor.execute(sql.replace("?", "%s"), values)
    return cursor


def _fetchone(conn: Any, sql: str, params: Iterable[Any] = ()) -> Any:
    cursor = _execute(conn, sql, params)
    try:
        return cursor.fetchone()
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _row_value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _qualified_table(conn: Any) -> str:
    return TABLE_NAME if _is_sqlite(conn) else f"public.{TABLE_NAME}"


def _timestamp(value: Any) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise MilestoneProjectionValidationError(
                "created_at must be timezone-aware"
            )
        return value.astimezone(timezone.utc).isoformat()
    if not isinstance(value, str) or not value or value != value.strip():
        raise MilestoneProjectionValidationError(
            "created_at must be a non-empty timestamp string"
        )
    return value


def _fact_evidence(fact: BattlefieldBossDefeatedFact) -> dict[str, Any]:
    metadata = fact.metadata
    eligibility_reference = metadata.get("eligibility_reference")
    intent_replay_fingerprint = metadata.get("intent_replay_fingerprint")
    operation_binding_verified = metadata.get("operation_binding_verified")
    source_event_type = metadata.get("settlement_event_type")
    if not isinstance(eligibility_reference, str) or not eligibility_reference.strip():
        raise MilestoneProjectionValidationError(
            "eligibility_reference evidence is required"
        )
    if not isinstance(intent_replay_fingerprint, str) or not intent_replay_fingerprint.strip():
        raise MilestoneProjectionValidationError(
            "intent_replay_fingerprint evidence is required"
        )
    if operation_binding_verified is not True:
        raise MilestoneProjectionValidationError(
            "operation binding evidence is required"
        )
    if source_event_type != SOURCE_EVENT_TYPE:
        raise MilestoneProjectionValidationError(
            "MONSTER_DEFEATED source event evidence is required"
        )
    return {
        "eligibility_reference": eligibility_reference,
        "intent_replay_fingerprint": intent_replay_fingerprint,
        "source_event_type": source_event_type,
    }


def _validated_fact(fact: Any) -> dict[str, Any]:
    if type(fact) is not BattlefieldBossDefeatedFact:
        raise MilestoneProjectionValidationError(
            "storage requires a validated BattlefieldBossDefeatedFact"
        )
    evidence = _fact_evidence(fact)
    return {
        "user_id": fact.user_id,
        "settlement_id": fact.settlement_id,
        "zone_key": fact.zone_key,
        "monster_id": fact.monster_id,
        "encounter_operation_id": fact.encounter_operation_id,
        "eligibility_reference": evidence["eligibility_reference"],
        "intent_replay_fingerprint": evidence["intent_replay_fingerprint"],
        "source_authority": fact.source_authority,
        "source_event_type": evidence["source_event_type"],
        "contract_version": fact.contract_version,
    }


def _existing_row(conn: Any, *, user_id: int, settlement_id: str) -> Any:
    table = _qualified_table(conn)
    columns = ", ".join(_SELECT_COLUMNS + _AUTHORITATIVE_COLUMNS[5:])
    return _fetchone(
        conn,
        f"SELECT {columns} FROM {table} WHERE user_id=? AND settlement_id=?",
        (user_id, settlement_id),
    )


def _row_authority(row: Any) -> dict[str, Any]:
    # The select list is _SELECT_COLUMNS followed by the six persisted
    # authority fields not already present in that prefix.
    names = _SELECT_COLUMNS + (
        "eligibility_reference",
        "intent_replay_fingerprint",
        "source_authority",
        "source_event_type",
        "contract_version",
    )
    return {name: _row_value(row, index, name) for index, name in enumerate(names)}


def _row_result(row: Any, *, recorded: bool, replayed: bool) -> BattlefieldBossMilestoneRecordResult:
    return BattlefieldBossMilestoneRecordResult(
        user_id=int(_row_value(row, 0, "user_id")),
        settlement_id=str(_row_value(row, 1, "settlement_id")),
        zone_key=str(_row_value(row, 2, "zone_key")),
        monster_id=str(_row_value(row, 3, "monster_id")),
        encounter_operation_id=str(_row_value(row, 4, "encounter_operation_id")),
        recorded=recorded,
        replayed=replayed,
        created_at=_render_timestamp(_row_value(row, 5, "created_at")),
    )


def _render_timestamp(value: Any) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def record_battlefield_boss_defeated_fact(
    conn: Any,
    fact: BattlefieldBossDefeatedFact,
    *,
    created_at: Any = None,
) -> BattlefieldBossMilestoneRecordResult:
    """Record one consumed F012 fact without committing the caller's tx.

    ``ON CONFLICT DO NOTHING`` lets concurrent deliveries converge on the
    composite key.  The existing row is then compared against every
    persisted authoritative field; a changed payload raises a conflict
    instead of updating or silently accepting the replay.
    """

    status = validate_schema(conn)
    if not status.get("valid"):
        raise MilestoneProjectionSchemaUnavailable(
            f"{TABLE_NAME} schema is not applied: {status.get('missing')}"
        )
    values = _validated_fact(fact)
    created_value = _timestamp(created_at)
    table = _qualified_table(conn)
    columns = (
        "user_id",
        "settlement_id",
        "zone_key",
        "monster_id",
        "encounter_operation_id",
        "eligibility_reference",
        "intent_replay_fingerprint",
        "source_authority",
        "occurred_at",
        "created_at",
        "source_event_type",
        "contract_version",
    )
    insert_values = (
        values["user_id"],
        values["settlement_id"],
        values["zone_key"],
        values["monster_id"],
        values["encounter_operation_id"],
        values["eligibility_reference"],
        values["intent_replay_fingerprint"],
        values["source_authority"],
        fact.occurred_at,
        created_value,
        values["source_event_type"],
        values["contract_version"],
    )
    marker = ", ".join("?" for _ in columns)
    inserted_cursor = _execute(
        conn,
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({marker}) "
        "ON CONFLICT (user_id, settlement_id) DO NOTHING",
        insert_values,
    )
    inserted = int(getattr(inserted_cursor, "rowcount", 0)) == 1
    row = _existing_row(
        conn,
        user_id=values["user_id"],
        settlement_id=values["settlement_id"],
    )
    if row is None:
        raise MilestoneProjectionError(
            "milestone insert completed without a readable projection row"
        )

    if not inserted:
        actual = _row_authority(row)
        expected = {
            key: values[key]
            for key in _AUTHORITATIVE_COLUMNS
        }
        if any(actual[key] != expected[key] for key in _AUTHORITATIVE_COLUMNS):
            raise MilestoneProjectionConflict(
                "same (user_id, settlement_id) has changed authoritative payload"
            )
    return _row_result(row, recorded=inserted, replayed=not inserted)


__all__ = [
    "BattlefieldBossMilestoneRecordResult",
    "MilestoneProjectionConflict",
    "MilestoneProjectionError",
    "MilestoneProjectionSchemaUnavailable",
    "MilestoneProjectionValidationError",
    "record_battlefield_boss_defeated_fact",
]
