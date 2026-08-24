"""F010 durable runtime adapter for the F009 Monster selector.

This module owns only durable selection state and replay binding.  It does
not choose a Zone, resolve combat stats, settle a battle, grant rewards, or
write Quest progression.  The caller owns the surrounding database
transaction; a successful call never commits by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import re
import uuid
from typing import Any, Iterable, Mapping

from migrations import monster_encounter_selector_state_v1 as selector_schema
from monster_encounter_selector import (
    DEFAULT_SELECTOR_POLICY,
    MonsterEncounterCandidate,
    MonsterEncounterSelection,
    MonsterSelectorPolicy,
    select_monster_encounter,
    validate_monster_encounter_catalog,
)


MONSTER_SELECTOR_V1_ENABLED_ENV = "MONSTER_ENCOUNTER_SELECTOR_V1_ENABLED"
MONSTER_SELECTOR_DEFAULT_ENABLED = False
SELECTOR_STATE_SCHEMA_VERSION = selector_schema.SCHEMA_VERSION
SELECTOR_OPERATION_KIND = "MONSTER_ENCOUNTER_SELECTION"
SERVER_OPERATION_PREFIX = "monster-encounter"
_MACHINE_KEY_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_LOGGER = logging.getLogger(__name__)

# F003/F009 use stable Monster-zone keys while the existing Adventure/Map
# Battle surface still exposes its historical rank-band keys.  This is a
# vocabulary adapter only: it does not decide unlocks, current progression,
# or which Zone the player may enter.
MAP_BATTLE_ZONE_KEY_ALIASES = {
    "k26_30": "zone_01",
    "k21_25": "zone_02",
    "k16_20": "zone_03",
    "k11_15": "zone_04",
    "k6_10": "zone_05",
    "k1_5": "zone_06",
    "d1_2": "zone_07",
    "d3_4": "zone_08",
    "d5_6": "zone_09",
    "d7_plus": "zone_10",
}


class MonsterSelectorRuntimeError(RuntimeError):
    """Base class for fail-closed durable selector failures."""


class SelectorStateSchemaUnavailable(MonsterSelectorRuntimeError):
    """The additive candidate schema has not been applied to this database."""


class SelectorStateCorrupt(MonsterSelectorRuntimeError):
    """Persisted selector state cannot be trusted or reconciled."""


class SelectorOperationConflict(MonsterSelectorRuntimeError):
    """An operation replay key was reused with conflicting authority inputs."""


@dataclass(frozen=True)
class DurableSelectorState:
    user_id: int
    zone_key: str
    cycle_generation: int
    seen_monster_ids: tuple[str, ...]
    last_monster_id: str | None
    last_family_id: str | None
    policy_version: str
    updated_at: Any


@dataclass(frozen=True)
class DurableSelectionOperation:
    user_id: int
    zone_key: str
    encounter_operation_id: str
    selected_monster_id: str
    encounter_intent: str
    selector_policy_version: str
    cycle_generation_before: int
    cycle_generation_after: int
    seen_monster_ids_before: tuple[str, ...]
    seen_monster_ids_after: tuple[str, ...]
    last_monster_id_before: str | None
    last_monster_id_after: str | None
    last_family_id_before: str | None
    last_family_id_after: str | None
    created_at: Any
    committed_at: Any

    def reconstruction(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "zone_key": self.zone_key,
            "encounter_operation_id": self.encounter_operation_id,
            "selected_monster_id": self.selected_monster_id,
            "encounter_intent": self.encounter_intent,
            "selector_policy_version": self.selector_policy_version,
            "cycle_generation_before": self.cycle_generation_before,
            "cycle_generation_after": self.cycle_generation_after,
            "seen_monster_ids_before": list(self.seen_monster_ids_before),
            "seen_monster_ids_after": list(self.seen_monster_ids_after),
            "last_monster_id_before": self.last_monster_id_before,
            "last_monster_id_after": self.last_monster_id_after,
            "last_family_id_before": self.last_family_id_before,
            "last_family_id_after": self.last_family_id_after,
            "created_at": self.created_at,
            "committed_at": self.committed_at,
        }


@dataclass(frozen=True)
class DurableSelectionResult:
    selection: MonsterEncounterSelection
    operation: DurableSelectionOperation
    replayed: bool

    @property
    def monster_id(self) -> str:
        return self.selection.monster_id


def monster_selector_v1_enabled(environ: Mapping[str, Any] | None = None) -> bool:
    """Read a dedicated fail-closed flag; the default is always off."""

    values = os.environ if environ is None else environ
    raw = str(values.get(MONSTER_SELECTOR_V1_ENABLED_ENV, "")).strip().lower()
    return raw in {"1", "true", "yes", "on", "enabled"}


def new_server_encounter_operation_id(
    user_id: Any,
    zone_key: Any,
    *,
    prefix: str = SERVER_OPERATION_PREFIX,
) -> str:
    """Create an operation identity in server code, never from request data."""

    user = str(user_id or "").strip()
    zone = str(zone_key or "").strip()
    if not user or not zone:
        raise ValueError("server user and zone are required for an operation identity")
    return f"{prefix}:{uuid.uuid4().hex}"


def canonical_selector_zone_key(zone_key: Any) -> str:
    """Normalize a server-validated legacy Map Battle Zone vocabulary."""

    value = str(zone_key or "").strip()
    if value in MAP_BATTLE_ZONE_KEY_ALIASES:
        return MAP_BATTLE_ZONE_KEY_ALIASES[value]
    if _MACHINE_KEY_RE.fullmatch(value) and value.startswith("zone_"):
        return value
    raise MonsterSelectorRuntimeError(
        f"unsupported legacy Map Battle zone key: {zone_key!r}"
    )


def _raw_connection(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw_connection(conn).__class__.__module__.startswith("sqlite3")


def _placeholder(conn: Any) -> str:
    return "?" if _is_sqlite(conn) else "%s"


def _execute(conn: Any, statement: str, params: Iterable[Any] | None = None) -> Any:
    values = tuple(params) if params is not None else None
    if hasattr(conn, "execute"):
        return conn.execute(statement) if values is None else conn.execute(statement, values)
    cursor = conn.cursor()
    if values is None:
        cursor.execute(statement)
    else:
        cursor.execute(statement, values)
    return cursor


def _fetchone(conn: Any, statement: str, params: Iterable[Any] = ()) -> Any:
    cursor = _execute(conn, statement, params)
    return cursor.fetchone()


def _row_value(row: Any, name: str, index: int) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _timestamp(value: Any = None) -> Any:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        return value
    return str(value)


def _json_ids(value: Any, *, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError) as error:
            raise SelectorStateCorrupt(f"{field_name} is not valid JSON") from error
    else:
        parsed = value
    if not isinstance(parsed, list):
        raise SelectorStateCorrupt(f"{field_name} must be a JSON array")
    result: list[str] = []
    for raw in parsed:
        if not isinstance(raw, str) or not _MACHINE_KEY_RE.fullmatch(raw):
            raise SelectorStateCorrupt(f"{field_name} contains an invalid Monster ID")
        if raw not in result:
            result.append(raw)
    return tuple(result)


def _json_dump_ids(ids: Iterable[str]) -> str:
    return json.dumps(list(dict.fromkeys(ids)), ensure_ascii=True, separators=(",", ":"))


def _log_operation_id(operation_id: str) -> str:
    """Keep opaque operation values out of logs while retaining correlation."""

    return hashlib.sha256(operation_id.encode("utf-8")).hexdigest()[:16]


def _schema_or_raise(conn: Any) -> None:
    try:
        result = selector_schema.validate_schema(conn)
    except Exception as error:
        if isinstance(error, selector_schema.SchemaMismatch):
            raise SelectorStateSchemaUnavailable(str(error)) from error
        raise
    if result.get("missing") or not result.get("present"):
        raise SelectorStateSchemaUnavailable(
            "F010 selector schema is not applied: " + repr(result.get("missing"))
        )


def _state_from_row(row: Any) -> DurableSelectorState:
    user_id = int(_row_value(row, "user_id", 0))
    cycle = int(_row_value(row, "cycle_generation", 2))
    if cycle < 0:
        raise SelectorStateCorrupt("cycle_generation cannot be negative")
    return DurableSelectorState(
        user_id=user_id,
        zone_key=str(_row_value(row, "zone_key", 1)),
        cycle_generation=cycle,
        seen_monster_ids=_json_ids(
            _row_value(row, "seen_monster_ids", 3),
            field_name="seen_monster_ids",
        ),
        last_monster_id=(
            str(_row_value(row, "last_monster_id", 4))
            if _row_value(row, "last_monster_id", 4) not in (None, "")
            else None
        ),
        last_family_id=(
            str(_row_value(row, "last_family_id", 5))
            if _row_value(row, "last_family_id", 5) not in (None, "")
            else None
        ),
        policy_version=str(_row_value(row, "policy_version", 6)),
        updated_at=_row_value(row, "updated_at", 7),
    )


def _operation_from_row(row: Any) -> DurableSelectionOperation:
    return DurableSelectionOperation(
        user_id=int(_row_value(row, "user_id", 0)),
        zone_key=str(_row_value(row, "zone_key", 1)),
        encounter_operation_id=str(_row_value(row, "encounter_operation_id", 2)),
        selected_monster_id=str(_row_value(row, "selected_monster_id", 3)),
        encounter_intent=str(_row_value(row, "encounter_intent", 4)),
        selector_policy_version=str(_row_value(row, "selector_policy_version", 5)),
        cycle_generation_before=int(_row_value(row, "cycle_generation_before", 6)),
        cycle_generation_after=int(_row_value(row, "cycle_generation_after", 7)),
        seen_monster_ids_before=_json_ids(
            _row_value(row, "seen_monster_ids_before", 8),
            field_name="seen_monster_ids_before",
        ),
        seen_monster_ids_after=_json_ids(
            _row_value(row, "seen_monster_ids_after", 9),
            field_name="seen_monster_ids_after",
        ),
        last_monster_id_before=(
            str(_row_value(row, "last_monster_id_before", 10))
            if _row_value(row, "last_monster_id_before", 10) not in (None, "")
            else None
        ),
        last_monster_id_after=(
            str(_row_value(row, "last_monster_id_after", 11))
            if _row_value(row, "last_monster_id_after", 11) not in (None, "")
            else None
        ),
        last_family_id_before=(
            str(_row_value(row, "last_family_id_before", 12))
            if _row_value(row, "last_family_id_before", 12) not in (None, "")
            else None
        ),
        last_family_id_after=(
            str(_row_value(row, "last_family_id_after", 13))
            if _row_value(row, "last_family_id_after", 13) not in (None, "")
            else None
        ),
        created_at=_row_value(row, "created_at", 14),
        committed_at=_row_value(row, "committed_at", 15),
    )


def _state_insert_if_missing(conn: Any, *, user_id: int, zone_key: str, now: Any) -> None:
    marker = _placeholder(conn)
    _execute(
        conn,
        f"""INSERT INTO {selector_schema.STATE_TABLE_NAME} (
                user_id, zone_key, cycle_generation, seen_monster_ids,
                last_monster_id, last_family_id, policy_version, updated_at
            ) VALUES ({marker}, {marker}, 0, {marker}, NULL, NULL, {marker}, {marker})
            ON CONFLICT (user_id, zone_key) DO NOTHING""",
        (user_id, zone_key, "[]", DEFAULT_SELECTOR_POLICY.version, now),
    )


def load_selector_state(
    conn: Any,
    *,
    user_id: int,
    zone_key: str,
    for_update: bool = False,
) -> DurableSelectorState | None:
    """Read the state cursor; ``for_update`` is only for a caller transaction."""

    _schema_or_raise(conn)
    marker = _placeholder(conn)
    statement = (
        f"SELECT user_id, zone_key, cycle_generation, seen_monster_ids, "
        f"last_monster_id, last_family_id, policy_version, updated_at "
        f"FROM {selector_schema.STATE_TABLE_NAME} "
        f"WHERE user_id={marker} AND zone_key={marker}"
    )
    if for_update and not _is_sqlite(conn):
        statement += " FOR UPDATE"
    row = _fetchone(conn, statement, (int(user_id), str(zone_key)))
    return _state_from_row(row) if row is not None else None


def get_selection_operation(
    conn: Any,
    *,
    user_id: int,
    zone_key: str,
    encounter_operation_id: str,
) -> DurableSelectionOperation | None:
    """Return the immutable replay binding for support/reconstruction."""

    _schema_or_raise(conn)
    marker = _placeholder(conn)
    row = _fetchone(
        conn,
        f"SELECT * FROM {selector_schema.OPERATION_TABLE_NAME} "
        f"WHERE user_id={marker} AND zone_key={marker} "
        f"AND encounter_operation_id={marker}",
        (int(user_id), str(zone_key), str(encounter_operation_id)),
    )
    return _operation_from_row(row) if row is not None else None


def reconstruct_selection_operation(
    conn: Any,
    *,
    user_id: int,
    zone_key: str,
    encounter_operation_id: str,
) -> dict[str, Any] | None:
    operation = get_selection_operation(
        conn,
        user_id=user_id,
        zone_key=zone_key,
        encounter_operation_id=encounter_operation_id,
    )
    if operation is None:
        return None
    state = load_selector_state(conn, user_id=user_id, zone_key=zone_key)
    result = operation.reconstruction()
    result["current_state"] = (
        {
            "cycle_generation": state.cycle_generation,
            "seen_monster_ids": list(state.seen_monster_ids),
            "last_monster_id": state.last_monster_id,
            "last_family_id": state.last_family_id,
            "policy_version": state.policy_version,
            "updated_at": state.updated_at,
        }
        if state is not None
        else None
    )
    return result


def _validate_state_against_catalog(
    state: DurableSelectorState,
    *,
    candidates: tuple[MonsterEncounterCandidate, ...],
    zone_key: str,
) -> None:
    zone_regular_ids = {
        candidate.monster_id
        for candidate in candidates
        if candidate.zone_key == zone_key and candidate.encounter_class != "BATTLEFIELD_BOSS"
    }
    if any(monster_id not in zone_regular_ids for monster_id in state.seen_monster_ids):
        raise SelectorStateCorrupt(
            "selector state contains an unknown or non-regular Monster identity"
        )
    if state.last_monster_id is not None:
        known = {candidate.monster_id for candidate in candidates if candidate.zone_key == zone_key}
        if state.last_monster_id not in known:
            raise SelectorStateCorrupt("selector state last_monster_id is outside the zone catalog")


def _selection_after_state(
    state: DurableSelectorState,
    selection: MonsterEncounterSelection,
) -> tuple[int, tuple[str, ...], str | None, str | None]:
    # Battlefield Boss state is intentionally not part of the regular unseen
    # cycle.  F010 exposes the pure service boundary for future callers but no
    # runtime path authorizes this intent.
    if selection.encounter_class == "BATTLEFIELD_BOSS":
        return (
            state.cycle_generation,
            state.seen_monster_ids,
            state.last_monster_id,
            state.last_family_id,
        )
    if selection.cycle_reset:
        generation = state.cycle_generation + 1
        seen = (selection.monster_id,)
    else:
        generation = state.cycle_generation
        seen = tuple(dict.fromkeys((*state.seen_monster_ids, selection.monster_id)))
    return generation, seen, selection.monster_id, selection.family_id


def select_durable_monster_encounter(
    conn: Any,
    *,
    user_id: int,
    zone_key: str,
    encounter_operation_id: str,
    candidates: Iterable[Any],
    encounter_intent: str = "REGULAR",
    policy: MonsterSelectorPolicy = DEFAULT_SELECTOR_POLICY,
    now: Any = None,
    battlefield_boss_authorized: bool = False,
) -> DurableSelectionResult:
    """Atomically bind one server operation to one F009 selection.

    The caller must run this inside its transaction.  PostgreSQL row locking
    serializes different new operations for one user/zone and the operation
    primary key makes same-operation retries replay the immutable result.
    """

    if isinstance(user_id, bool) or int(user_id) <= 0:
        raise ValueError("user_id must be a positive server identity")
    zone_key = str(zone_key or "").strip()
    if not _MACHINE_KEY_RE.fullmatch(zone_key):
        raise ValueError("zone_key must be a lowercase ASCII machine key")
    operation_id = str(encounter_operation_id or "").strip()
    if not operation_id or len(operation_id) > 255:
        raise ValueError("server encounter_operation_id is required")
    if not isinstance(policy, MonsterSelectorPolicy):
        raise ValueError("policy must be the F009 MonsterSelectorPolicy")

    _schema_or_raise(conn)
    try:
        catalog = validate_monster_encounter_catalog(candidates)
    except Exception:
        _LOGGER.warning(
            "selector_invalid_pool",
            extra={"zone_key": zone_key, "user_id": int(user_id)},
        )
        raise
    valid_ids = {candidate.monster_id for candidate in catalog}
    now_value = _timestamp(now)

    # Insertion is safe under concurrent creation: PostgreSQL's unique key
    # waits for the competing insert before ON CONFLICT evaluates.
    _state_insert_if_missing(
        conn,
        user_id=int(user_id),
        zone_key=zone_key,
        now=now_value,
    )
    state = load_selector_state(
        conn,
        user_id=int(user_id),
        zone_key=zone_key,
        for_update=True,
    )
    if state is None:
        raise SelectorStateCorrupt("selector state row could not be locked")
    _validate_state_against_catalog(state, candidates=catalog, zone_key=zone_key)

    marker = _placeholder(conn)
    replay_row = _fetchone(
        conn,
        f"SELECT * FROM {selector_schema.OPERATION_TABLE_NAME} "
        f"WHERE user_id={marker} AND zone_key={marker} "
        f"AND encounter_operation_id={marker}",
        (int(user_id), zone_key, operation_id),
    )
    if replay_row is not None:
        operation = _operation_from_row(replay_row)
        if operation.encounter_intent != str(encounter_intent or "").strip().upper():
            raise SelectorOperationConflict("operation replay intent does not match")
        if operation.zone_key != zone_key or operation.user_id != int(user_id):
            raise SelectorOperationConflict("operation replay scope does not match")
        selected = next(
            (candidate for candidate in catalog if candidate.monster_id == operation.selected_monster_id),
            None,
        )
        if selected is None:
            raise SelectorStateCorrupt("replayed Monster identity is absent from catalog")
        _LOGGER.info(
            "selector_operation_replayed",
            extra={
                "user_id": int(user_id),
                "zone_key": zone_key,
                "operation_digest": _log_operation_id(operation_id),
                "selected_monster_id": operation.selected_monster_id,
            },
        )
        selection = MonsterEncounterSelection(
            monster_id=operation.selected_monster_id,
            zone_key=operation.zone_key,
            encounter_class=selected.encounter_class,
            family_id=selected.family_id,
            rarity=selected.rarity,
            operation_id=operation.encounter_operation_id,
            selector_version=operation.selector_policy_version,
            seen_state_scope="USER_AND_ZONE",
            candidate_count=(
                sum(1 for candidate in catalog if candidate.zone_key == zone_key)
                if operation.encounter_intent == "BATTLEFIELD_BOSS"
                else sum(
                    1
                    for candidate in catalog
                    if candidate.zone_key == zone_key
                    and candidate.encounter_class != "BATTLEFIELD_BOSS"
                )
            ),
            cycle_reset=(
                operation.cycle_generation_after != operation.cycle_generation_before
            ),
            deterministic_seed_digest="replayed:" + operation.selected_monster_id,
        )
        return DurableSelectionResult(selection=selection, operation=operation, replayed=True)

    selection = select_monster_encounter(
        catalog,
        user_id=int(user_id),
        zone_key=zone_key,
        encounter_intent=encounter_intent,
        seen_monster_ids=state.seen_monster_ids,
        last_monster_id=state.last_monster_id,
        last_family_id=state.last_family_id,
        operation_id=operation_id,
        policy=policy,
        battlefield_boss_authorized=battlefield_boss_authorized,
    )
    generation_after, seen_after, last_after, family_after = _selection_after_state(
        state, selection
    )
    if any(monster_id not in valid_ids for monster_id in seen_after):
        raise SelectorStateCorrupt("selector produced an identity outside the catalog")
    intent = str(encounter_intent or "").strip().upper()
    values = (
        int(user_id),
        zone_key,
        operation_id,
        selection.monster_id,
        intent,
        policy.version,
        state.cycle_generation,
        generation_after,
        _json_dump_ids(state.seen_monster_ids),
        _json_dump_ids(seen_after),
        state.last_monster_id,
        last_after,
        state.last_family_id,
        family_after,
        now_value,
        now_value,
    )
    try:
        _execute(
            conn,
            f"""INSERT INTO {selector_schema.OPERATION_TABLE_NAME} (
                user_id, zone_key, encounter_operation_id, selected_monster_id,
                encounter_intent, selector_policy_version,
                cycle_generation_before, cycle_generation_after,
                seen_monster_ids_before, seen_monster_ids_after,
                last_monster_id_before, last_monster_id_after,
                last_family_id_before, last_family_id_after,
                created_at, committed_at
            ) VALUES ({', '.join([marker] * len(values))})""",
            values,
        )
        update_cursor = _execute(
            conn,
            f"""UPDATE {selector_schema.STATE_TABLE_NAME}
                   SET cycle_generation={marker}, seen_monster_ids={marker},
                       last_monster_id={marker}, last_family_id={marker},
                       policy_version={marker}, updated_at={marker}
                 WHERE user_id={marker} AND zone_key={marker}""",
            (
                generation_after,
                _json_dump_ids(seen_after),
                last_after,
                family_after,
                policy.version,
                now_value,
                int(user_id),
                zone_key,
            ),
        )
    except Exception:
        _LOGGER.warning(
            "selector_state_rollback",
            extra={
                "user_id": int(user_id),
                "zone_key": zone_key,
                "operation_digest": _log_operation_id(operation_id),
            },
        )
        raise
    if getattr(update_cursor, "rowcount", 1) != 1:
        _LOGGER.error(
            "selector_state_conflict",
            extra={"user_id": int(user_id), "zone_key": zone_key},
        )
        raise SelectorStateCorrupt("selector state update did not affect one row")

    if selection.cycle_reset:
        _LOGGER.info(
            "selector_cycle_reset",
            extra={
                "user_id": int(user_id),
                "zone_key": zone_key,
                "cycle_generation": generation_after,
            },
        )
    _LOGGER.info(
        "selector_operation_committed",
        extra={
            "user_id": int(user_id),
            "zone_key": zone_key,
            "operation_digest": _log_operation_id(operation_id),
            "selected_monster_id": selection.monster_id,
            "selector_policy_version": policy.version,
        },
    )

    operation = DurableSelectionOperation(
        user_id=int(user_id),
        zone_key=zone_key,
        encounter_operation_id=operation_id,
        selected_monster_id=selection.monster_id,
        encounter_intent=intent,
        selector_policy_version=policy.version,
        cycle_generation_before=state.cycle_generation,
        cycle_generation_after=generation_after,
        seen_monster_ids_before=state.seen_monster_ids,
        seen_monster_ids_after=seen_after,
        last_monster_id_before=state.last_monster_id,
        last_monster_id_after=last_after,
        last_family_id_before=state.last_family_id,
        last_family_id_after=family_after,
        created_at=now_value,
        committed_at=now_value,
    )
    return DurableSelectionResult(selection=selection, operation=operation, replayed=False)


__all__ = [
    "DurableSelectionOperation",
    "DurableSelectionResult",
    "DurableSelectorState",
    "MONSTER_SELECTOR_DEFAULT_ENABLED",
    "MONSTER_SELECTOR_V1_ENABLED_ENV",
    "MAP_BATTLE_ZONE_KEY_ALIASES",
    "MonsterSelectorRuntimeError",
    "SelectorOperationConflict",
    "SelectorStateCorrupt",
    "SelectorStateSchemaUnavailable",
    "get_selection_operation",
    "canonical_selector_zone_key",
    "load_selector_state",
    "monster_selector_v1_enabled",
    "new_server_encounter_operation_id",
    "reconstruct_selection_operation",
    "select_durable_monster_encounter",
]
