"""Read-only invariant auditor for the E10 Six-Spirit S1 contract.

The auditor consumes snapshots of Lane B-owned authority/projection rows and
the existing D5A outbox/D5C operation evidence.  It never writes, commits,
repairs, grants, revokes, or publishes anything.  Snapshot keys are logical
interfaces, not a request to create a parallel Spirit database.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Iterable, Mapping

from spirit_lineage import (
    LEGACY_COSMETIC_PET_IDS,
    NON_REWARD_SOURCES,
    validate_evolution_event,
    validate_functional_spirit_id,
    validate_spirit_effect_event,
)


REQUIRED_INVARIANTS = (
    "ONE_SOURCE_OPERATION_ONE_AUTHORITY",
    "DUPLICATE_SPIRIT_REWARD",
    "ORPHAN_SPIRIT_REWARD",
    "REWARD_REQUIRES_OUTBOX_LINEAGE",
    "ORPHAN_OUTBOX",
    "OUTBOX_WITHOUT_AUTHORITY",
    "ITEM_CONSUMED_AT_MOST_ONCE",
    "COMPLETED_ITEM_OPERATION_HAS_CONSUMPTION",
    "SPIRIT_EVENT_VALID",
    "UNLOCK_REQUIRES_OWNERSHIP",
    "OWNERSHIP_CATALOG_VALID",
    "ACTIVE_SPIRIT_OWNED",
    "DUPLICATE_EVOLUTION_EVENT",
    "REPLAY_NO_REWARD",
    "LEGACY_PET_QUARANTINE",
    "EFFECT_NOT_BEFORE_JUDGE",
    "OPERATION_PAYLOAD_STABLE",
)

_TABLE_ALIASES = {
    "reward_authorities": ("reward_authorities", "spirit_reward_authority"),
    "spirit_rewards": ("spirit_rewards", "spirit_reward_lineage"),
    "domain_event_outbox": ("domain_event_outbox", "outbox"),
    "item_operations": ("item_operations", "item_use_operations"),
    "item_consumptions": ("item_consumptions", "spirit_item_consumptions"),
    "catalog": ("catalog", "spirit_catalog"),
    "pet_collection": ("pet_collection", "spirit_ownership"),
    "user_pets": ("user_pets", "active_spirits"),
    "spirit_events": ("spirit_events", "telemetry_events"),
    "evolution_events": ("evolution_events", "spirit_evolution_events"),
    "effect_events": ("effect_events", "spirit_effect_events"),
    "replay_mutations": ("replay_mutations", "replay_reward_mutations"),
}


@dataclass(frozen=True)
class InvariantResult:
    name: str
    status: str
    violations: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "violations": list(self.violations),
        }


@dataclass(frozen=True)
class SpiritAuditReport:
    invariants: tuple[InvariantResult, ...]
    source_of_truth_duplicated: bool = False
    auditor_mutation_capability: str = "NO"

    @property
    def valid(self) -> bool:
        return all(item.passed for item in self.invariants)

    @property
    def failure_count(self) -> int:
        return sum(1 for item in self.invariants if not item.passed)

    @property
    def failures(self) -> dict[str, list[str]]:
        return {
            item.name: list(item.violations)
            for item in self.invariants
            if not item.passed
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "failure_count": self.failure_count,
            "invariants": [item.as_dict() for item in self.invariants],
            "source_of_truth_duplicated": self.source_of_truth_duplicated,
            "auditor_mutation_capability": self.auditor_mutation_capability,
        }


def _rows(snapshot: Mapping[str, Iterable[Mapping[str, Any]]], logical_name: str) -> list[dict[str, Any]]:
    for key in _TABLE_ALIASES.get(logical_name, (logical_name,)):
        value = snapshot.get(key)
        if value is not None:
            return [dict(row) for row in value]
    return []


def _payload(row: Mapping[str, Any]) -> dict[str, Any]:
    value = row.get("payload", row.get("result_payload", {}))
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().upper() in {"1", "TRUE", "YES", "COMMITTED", "SUCCESS", "GRANTED"}
    return bool(value)


def _committed(row: Mapping[str, Any]) -> bool:
    if "committed" in row:
        return _truthy(row.get("committed"))
    status = str(row.get("outcome", row.get("operation_status", row.get("component_status", "")))).upper()
    return status in {"SUCCESS", "COMMITTED", "GRANTED"}


def _key(row: Mapping[str, Any], *names: str) -> tuple[Any, ...]:
    return tuple(row.get(name) for name in names)


def _add_result(results: list[InvariantResult], name: str, violations: list[str]) -> None:
    results.append(
        InvariantResult(name=name, status="FAIL" if violations else "PASS", violations=tuple(violations))
    )


def audit_companion_snapshot(snapshot: Mapping[str, Iterable[Mapping[str, Any]]]) -> SpiritAuditReport:
    """Audit a read-only snapshot using only existing/source-bound evidence.

    The logical ``reward_authorities`` and ``item_consumptions`` collections
    represent rows supplied by the future Lane B authority.  They are not
    created or mutated here.  The D5A ``domain_event_outbox`` and D5C
    ``item_operations`` collections are evidence sources when present.
    """

    authorities = _rows(snapshot, "reward_authorities")
    rewards = _rows(snapshot, "spirit_rewards")
    outbox = _rows(snapshot, "domain_event_outbox")
    item_operations = _rows(snapshot, "item_operations")
    item_consumptions = _rows(snapshot, "item_consumptions")
    catalog = _rows(snapshot, "catalog")
    ownership = _rows(snapshot, "pet_collection")
    active = _rows(snapshot, "user_pets")
    spirit_events = _rows(snapshot, "spirit_events")
    evolution_events = _rows(snapshot, "evolution_events")
    effect_events = _rows(snapshot, "effect_events")
    replay_mutations = _rows(snapshot, "replay_mutations")

    results: list[InvariantResult] = []
    authority_by_id = {row.get("authority_id"): row for row in authorities if row.get("authority_id") is not None}
    reward_by_id = {row.get("reward_id"): row for row in rewards if row.get("reward_id") is not None}
    operation_by_key: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in item_operations:
        operation_by_key.setdefault(
            _key(row, "user_id", "operation_id", "operation_type"), []
        ).append(row)

    violations: list[str] = []
    authority_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in authorities:
        authority_groups.setdefault(_key(row, "user_id", "operation_id"), []).append(row)
    for group_key, rows in authority_groups.items():
        committed_rows = [row for row in rows if _committed(row)]
        if len(committed_rows) > 1:
            violations.append(f"authority operation {group_key!r} has {len(committed_rows)} committed rows")
    _add_result(results, "ONE_SOURCE_OPERATION_ONE_AUTHORITY", violations)

    violations = []
    reward_groups: dict[Any, list[dict[str, Any]]] = {}
    for row in rewards:
        if _committed(row):
            reward_groups.setdefault(row.get("authority_id", row.get("operation_id")), []).append(row)
    for group_key, rows in reward_groups.items():
        if len(rows) > 1:
            violations.append(f"authority {group_key!r} has {len(rows)} committed Spirit rewards")
    _add_result(results, "DUPLICATE_SPIRIT_REWARD", violations)

    violations = []
    for row in rewards:
        if not _committed(row):
            continue
        authority = authority_by_id.get(row.get("authority_id"))
        if authority is None or not _committed(authority):
            violations.append(f"reward {row.get('reward_id')!r} has no committed source authority")
        if row.get("operation_id") and authority and row.get("operation_id") != authority.get("operation_id"):
            violations.append(f"reward {row.get('reward_id')!r} operation does not match source authority")
    _add_result(results, "ORPHAN_SPIRIT_REWARD", violations)

    spirit_outbox = []
    for row in outbox:
        payload = _payload(row)
        if payload.get("lineage_kind") in {"SPIRIT_REWARD", "SPIRIT_ITEM_USE"}:
            spirit_outbox.append((row, payload))

    reward_outbox_ids = {
        payload.get("reward_id")
        for _row, payload in spirit_outbox
        if payload.get("lineage_kind") == "SPIRIT_REWARD"
    }
    violations = []
    for row in rewards:
        if _committed(row) and row.get("reward_id") not in reward_outbox_ids:
            violations.append(f"reward {row.get('reward_id')!r} has no D5A outbox lineage")
    _add_result(results, "REWARD_REQUIRES_OUTBOX_LINEAGE", violations)

    violations = []
    for row, payload in spirit_outbox:
        if payload.get("lineage_kind") == "SPIRIT_REWARD":
            reward = reward_by_id.get(payload.get("reward_id"))
            authority = authority_by_id.get(payload.get("authority_id"))
            if reward is None or not _committed(reward):
                violations.append(f"outbox event {row.get('event_id')!r} has no committed reward")
            if authority is None or not _committed(authority):
                violations.append(f"outbox event {row.get('event_id')!r} has no committed authority")
        else:
            op_key = (
                payload.get("user_id", row.get("player_id")),
                payload.get("operation_id"),
                "ITEM_USE",
            )
            matching = operation_by_key.get(op_key, [])
            if not matching or not any(_committed(item) for item in matching):
                violations.append(f"outbox event {row.get('event_id')!r} has no committed item operation")
    _add_result(results, "ORPHAN_OUTBOX", violations)

    violations = []
    for row, payload in spirit_outbox:
        if payload.get("lineage_kind") == "SPIRIT_REWARD" and not authority_by_id.get(payload.get("authority_id")):
            violations.append(f"reward outbox {row.get('event_id')!r} references no authority")
        if payload.get("lineage_kind") == "SPIRIT_ITEM_USE":
            op_key = (payload.get("user_id", row.get("player_id")), payload.get("operation_id"), "ITEM_USE")
            if not operation_by_key.get(op_key):
                violations.append(f"item outbox {row.get('event_id')!r} references no authority")
    _add_result(results, "OUTBOX_WITHOUT_AUTHORITY", violations)

    violations = []
    consumption_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in item_consumptions:
        if _committed(row):
            consumption_groups.setdefault(_key(row, "user_id", "operation_id"), []).append(row)
    for group_key, rows in consumption_groups.items():
        if len(rows) > 1:
            violations.append(f"item operation {group_key!r} consumed {len(rows)} times")
    _add_result(results, "ITEM_CONSUMED_AT_MOST_ONCE", violations)

    violations = []
    for group_key, rows in operation_by_key.items():
        for row in rows:
            if str(row.get("operation_type", "")).upper() == "ITEM_USE" and str(row.get("operation_status", "")).upper() in {"SUCCESS", "COMMITTED"}:
                if not any(
                    _key(item, "user_id", "operation_id") == group_key[:2]
                    for item in item_consumptions
                    if _committed(item)
                ):
                    violations.append(f"completed item operation {group_key!r} has no consumption")
    _add_result(results, "COMPLETED_ITEM_OPERATION_HAS_CONSUMPTION", violations)

    violations = []
    catalog_ids = {
        row.get("spirit_id")
        for row in catalog
        if _truthy(row.get("functional"), default=True)
    }
    ownership_keys = {_key(row, "user_id", "pet_key", "spirit_id") for row in ownership}
    for row in spirit_events:
        event_type = str(row.get("event_type", "")).upper()
        if event_type not in {"SPIRIT_XP_GAINED", "SPIRIT_LEVEL_UP", "SPIRIT_EVOLVED", "SPIRIT_EFFECT_TRIGGERED", "SPIRIT_ITEM_USED", "SPIRIT_REWARD_GRANTED", "SPIRIT_UNLOCKED"}:
            continue
        spirit_id = row.get("spirit_id")
        if spirit_id not in catalog_ids or spirit_id in LEGACY_COSMETIC_PET_IDS:
            violations.append(f"event {row.get('event_id')!r} references an invalid Spirit")
        if event_type == "SPIRIT_UNLOCKED" and not any(
            owner.get("user_id") == row.get("user_id")
            and owner.get("pet_key", owner.get("spirit_id")) == spirit_id
            for owner in ownership
        ):
            violations.append(f"unlock event {row.get('event_id')!r} has no ownership")
    _add_result(results, "SPIRIT_EVENT_VALID", violations)

    violations = []
    for row in spirit_events:
        if str(row.get("event_type", "")).upper() == "SPIRIT_UNLOCKED":
            if not any(
                owner.get("user_id") == row.get("user_id")
                and owner.get("pet_key", owner.get("spirit_id")) == row.get("spirit_id")
                for owner in ownership
            ):
                violations.append(f"unlock event {row.get('event_id')!r} has no ownership")
    _add_result(results, "UNLOCK_REQUIRES_OWNERSHIP", violations)

    violations = []
    for row in ownership:
        spirit_id = row.get("pet_key", row.get("spirit_id"))
        if spirit_id not in catalog_ids or spirit_id in LEGACY_COSMETIC_PET_IDS:
            violations.append(f"ownership row {row.get('id')!r} references invalid Spirit {spirit_id!r}")
    _add_result(results, "OWNERSHIP_CATALOG_VALID", violations)

    violations = []
    for row in active:
        spirit_id = row.get("pet_key", row.get("spirit_id"))
        if not any(
            owner.get("user_id") == row.get("user_id")
            and owner.get("pet_key", owner.get("spirit_id")) == spirit_id
            for owner in ownership
        ):
            violations.append(f"active Spirit {spirit_id!r} for user {row.get('user_id')!r} is not owned")
    _add_result(results, "ACTIVE_SPIRIT_OWNED", violations)

    violations = []
    evolution_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in evolution_events:
        evolution_groups.setdefault(
            _key(row, "user_id", "spirit_id", "from_stage", "to_stage"), []
        ).append(row)
        try:
            if not validate_evolution_event(row):
                violations.append(f"evolution event {row.get('event_id')!r} is not server-derived")
        except (TypeError, ValueError):
            violations.append(f"evolution event {row.get('event_id')!r} has invalid levels")
    for group_key, rows in evolution_groups.items():
        if len(rows) > 1:
            violations.append(f"evolution transition {group_key!r} has {len(rows)} events")
    _add_result(results, "DUPLICATE_EVOLUTION_EVENT", violations)

    violations = []
    for row in rewards + authorities:
        source_type = str(row.get("source_type", "")).upper()
        if source_type in NON_REWARD_SOURCES or _truthy(row.get("replay_source")):
            violations.append(f"replay/cinematic row {row.get('reward_id', row.get('authority_id'))!r} creates functional state")
    for row in replay_mutations:
        if any(_truthy(row.get(field)) or (isinstance(row.get(field), (int, float)) and row.get(field) > 0) for field in ("spirit_xp", "spirit_items", "unlock_progress", "evolution_reward")):
            violations.append(f"replay mutation {row.get('event_id')!r} has functional reward")
    _add_result(results, "REPLAY_NO_REWARD", violations)

    violations = []
    functional_values = set(catalog_ids)
    for collection in (rewards, item_consumptions, ownership, spirit_events, evolution_events, effect_events):
        for row in collection:
            spirit_id = row.get("spirit_id", row.get("pet_key"))
            if spirit_id in LEGACY_COSMETIC_PET_IDS:
                violations.append(f"legacy cosmetic Pet {spirit_id!r} used as functional Spirit")
            if collection is rewards and spirit_id is not None and spirit_id not in functional_values:
                violations.append(f"reward {row.get('reward_id')!r} uses unknown Spirit")
    _add_result(results, "LEGACY_PET_QUARANTINE", violations)

    violations = []
    for row in effect_events:
        try:
            if not validate_spirit_effect_event(row):
                violations.append(f"effect event {row.get('event_id')!r} claims pre-judge or incomplete authority")
        except (TypeError, ValueError):
            violations.append(f"effect event {row.get('event_id')!r} is malformed")
    _add_result(results, "EFFECT_NOT_BEFORE_JUDGE", violations)

    violations = []
    for key, rows in operation_by_key.items():
        fingerprints = {row.get("request_fingerprint") for row in rows}
        if len(fingerprints) > 1:
            violations.append(f"operation {key!r} has conflicting request fingerprints")
    _add_result(results, "OPERATION_PAYLOAD_STABLE", violations)

    return SpiritAuditReport(tuple(results))


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def read_snapshot_tables(conn: Any, table_map: Mapping[str, str]) -> dict[str, list[dict[str, Any]]]:
    """Read configured tables with SELECT only; never commits or mutates.

    ``table_map`` is an operator-supplied mapping of logical snapshot names
    to already-existing source tables.  Identifiers are validated before SQL
    interpolation.  This helper intentionally does not create missing tables.
    """

    snapshot: dict[str, list[dict[str, Any]]] = {}
    for logical_name, table_name in table_map.items():
        if not _IDENTIFIER_RE.fullmatch(table_name):
            raise ValueError(f"unsafe table identifier: {table_name!r}")
        cursor = conn.cursor()
        try:
            cursor.execute(f"SELECT * FROM {table_name}")
            description = cursor.description or ()
            rows = cursor.fetchall()
            snapshot[logical_name] = [
                {str(column[0]): row[index] for index, column in enumerate(description)}
                for row in rows
            ]
        finally:
            cursor.close()
    return snapshot


__all__ = [
    "InvariantResult",
    "REQUIRED_INVARIANTS",
    "SpiritAuditReport",
    "audit_companion_snapshot",
    "read_snapshot_tables",
]
