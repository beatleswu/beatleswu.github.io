"""D025 detached Monster Equipment acquisition result bridge.

This module consumes two already-authoritative facts:

* a committed Monster settlement/drop decision; and
* the exact row result returned by the B040 ``player_inventory`` writer.

It returns the existing D020 :class:`CanonicalAcquisitionResult` envelope.
It never decides drop eligibility, writes ownership, opens or closes a
transaction, appends D5A lineage, or reads ``player_inventory`` to discover
an identity.  The exact B040 row identity is the only ownership identity
accepted for functional Monster Equipment.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
import re
from typing import Any

from canonical_acquisition_result import (
    CONTRACT_VERSION,
    CanonicalAcquisitionResult,
)


D025_CONTRACT_VERSION = "D025_MONSTER_EQUIPMENT_ACQUISITION_RESULT_V1"
MONSTER_DROP = "MONSTER_DROP"
PLAYER_INVENTORY = "PLAYER_INVENTORY"
PLAYER_INVENTORY_AUTHORITY = "player_inventory"
DATABASE_WRITES = 0
MUTATION_CAPABILITY = "NO"
READ_ONLY = True

READY = "READY"
SOURCE_DROP = "drop"
GO_STONE_BLACK = "go_stone_black"
XP_AMULET = "xp_amulet"
GO_STONE_BLACK_STATUS = "TROPHY_INVENTORY_ONLY_NO_COMBAT_POWER"
XP_AMULET_STATUS = "HOLD_FOR_AUTHORITY"

_MISSING = object()
_ROW_REFERENCE = re.compile(r"^player_inventory:(0|[1-9][0-9]*)$")
_COMMIT_MARKERS = (
    "committed",
    "settlement_committed",
    "ownership_committed",
    "commit_completed",
)
_COMMIT_STATUS_FIELDS = (
    "settlement_status",
    "ownership_status",
    "transaction_status",
    "status",
    "outcome",
)
_COMMITTED_STATUSES = frozenset({"COMMITTED", "SETTLED"})
_TERMINAL_STATUSES = frozenset({"SUCCESS", "COMMITTED", "SETTLED"})
_REJECTED_STATUSES = frozenset(
    {"FAILED", "PENDING", "IN_PROGRESS", "PREVIEW", "UNCOMMITTED", "UNSETTLED"}
)


class MonsterEquipmentAcquisitionError(ValueError):
    """Stable fail-closed error for the D025 result boundary."""

    def __init__(self, code: str, message: str, **details: Any):
        self.code = code
        self.details = details
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str, **details: Any) -> None:
    raise MonsterEquipmentAcquisitionError(code, message, **details)


def _as_mapping(value: Any, field: str) -> Mapping[str, Any]:
    """Read mappings and the exact B040/dataclass result without mutation."""

    if isinstance(value, Mapping):
        return value
    for method_name in ("as_dict", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            converted = method()
            if isinstance(converted, Mapping):
                return converted
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: getattr(value, item.name) for item in fields(value)}
    keys = getattr(value, "keys", None)
    if callable(keys):
        try:
            return {name: value[name] for name in keys()}
        except (KeyError, TypeError, IndexError) as exc:
            raise MonsterEquipmentAcquisitionError(
                "INVALID_TRUSTED_FACT", f"{field} cannot be read as a mapping"
            ) from exc
    _fail("INVALID_TRUSTED_FACT", f"{field} must be a mapping or result object")


def _nested_mappings(mapping: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Return only explicitly nested producer facts; never query or infer."""

    candidates: list[Mapping[str, Any]] = [mapping]
    for key in (
        "ownership_result",
        "payload",
        "functional_payload",
        "event_record",
        "acquisition",
    ):
        nested = mapping.get(key, _MISSING)
        if nested is _MISSING or nested is None:
            continue
        try:
            nested_mapping = _as_mapping(nested, key)
        except MonsterEquipmentAcquisitionError:
            continue
        candidates.append(nested_mapping)
        for child_key in ("payload", "event_record"):
            child = nested_mapping.get(child_key, _MISSING)
            if child is _MISSING or child is None:
                continue
            try:
                candidates.append(_as_mapping(child, f"{key}.{child_key}"))
            except MonsterEquipmentAcquisitionError:
                continue
    return tuple(candidates)


def _first(mapping: Mapping[str, Any], *names: str) -> Any:
    for candidate in _nested_mappings(mapping):
        for name in names:
            if name in candidate:
                return candidate[name]
    return _MISSING


def _required(mapping: Mapping[str, Any], field: str, *names: str) -> Any:
    value = _first(mapping, *names)
    if value is _MISSING or value is None:
        _fail("REQUIRED_TRUSTED_FACT_MISSING", f"{field} is required", field=field)
    return value


def _identity(value: Any, field: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        _fail("INVALID_TRUSTED_FACT", f"{field} must be a non-empty identity", field=field)
    normalized = str(value).strip()
    if not normalized:
        _fail("REQUIRED_TRUSTED_FACT_MISSING", f"{field} must not be empty", field=field)
    return normalized


def _same_identity(left: Any, right: Any, field: str) -> bool:
    return _identity(left, field) == _identity(right, field)


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail("INVALID_TRUSTED_FACT", f"{field} must be a positive integer", field=field)
    return value


def _optional_bool(value: Any, field: str) -> bool | None:
    if value is _MISSING or value is None:
        return None
    if not isinstance(value, bool):
        _fail("INVALID_TRUSTED_FACT", f"{field} must be boolean or null", field=field)
    return value


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        _fail("INVALID_TRUSTED_FACT", f"{field} must be boolean", field=field)
    return value


def _status_evidence(
    mappings: tuple[Mapping[str, Any], ...],
    *,
    marker_names: tuple[str, ...],
    status_names: tuple[str, ...],
    label: str,
) -> None:
    """Require explicit persistence evidence; SUCCESS remains non-committing."""

    explicit_commit = False
    status_seen = False
    for mapping in mappings:
        for name in marker_names:
            value = mapping.get(name, _MISSING)
            if value is _MISSING:
                continue
            if not isinstance(value, bool):
                _fail("INVALID_COMMIT_EVIDENCE", f"{label}.{name} must be boolean")
            explicit_commit = explicit_commit or value
        for name in status_names:
            value = mapping.get(name, _MISSING)
            if value is _MISSING or value is None:
                continue
            status_seen = True
            if not isinstance(value, str):
                _fail("INVALID_COMMIT_EVIDENCE", f"{label}.{name} must be a status string")
            normalized = value.strip().upper()
            if normalized in _REJECTED_STATUSES or normalized not in _TERMINAL_STATUSES:
                _fail("COMMITTED_RESULT_EVIDENCE_REQUIRED", f"{label}.{name} is not terminal")
            if normalized in _COMMITTED_STATUSES:
                explicit_commit = True
    if not explicit_commit:
        reason = "has no explicit committed/settled evidence" if status_seen else "has no explicit commit evidence"
        _fail("COMMITTED_RESULT_EVIDENCE_REQUIRED", f"{label} {reason}")


def _row_reference(value: Any) -> str:
    if not isinstance(value, str) or _ROW_REFERENCE.fullmatch(value) is None:
        _fail(
            "MALFORMED_OWNERSHIP_REFERENCE",
            "B040 ownership_reference must be player_inventory:<positive row id>",
        )
    row_id = int(value.rsplit(":", 1)[1])
    if row_id <= 0:
        _fail("MALFORMED_OWNERSHIP_REFERENCE", "B040 ownership row id must be positive")
    return value


def _ownership_reference(ownership: Mapping[str, Any]) -> tuple[str, int]:
    explicit: list[str] = []
    row_ids: list[int] = []
    for mapping in _nested_mappings(ownership):
        for name in ("ownership_reference", "grant_id"):
            value = mapping.get(name, _MISSING)
            if value is not _MISSING and value is not None:
                explicit.append(_row_reference(value))
        if "row_id" in mapping:
            row_ids.append(_positive_int(mapping["row_id"], "ownership_result.row_id"))
        for name in ("inventory_id", "inv_id"):
            if name in mapping:
                row_ids.append(_positive_int(mapping[name], f"ownership_result.{name}"))

    references = set(explicit)
    if len(references) > 1:
        _fail("OWNERSHIP_REFERENCE_MISMATCH", "B040 ownership references disagree")
    if row_ids and len(set(row_ids)) > 1:
        _fail("OWNERSHIP_REFERENCE_MISMATCH", "B040 row identities disagree")
    row_reference = f"player_inventory:{row_ids[0]}" if row_ids else None
    if references and row_reference is not None and next(iter(references)) != row_reference:
        _fail("OWNERSHIP_REFERENCE_MISMATCH", "B040 row id and ownership reference disagree")
    if not references and row_reference is None:
        _fail("OWNERSHIP_REFERENCE_UNAVAILABLE", "exact B040 ownership row identity is required")
    reference = next(iter(references)) if references else row_reference
    assert reference is not None
    return reference, int(reference.rsplit(":", 1)[1])


def _settlement_id(settlement: Mapping[str, Any]) -> str:
    value = _required(settlement, "settlement_id", "settlement_id", "source_reference")
    return _identity(value, "settlement_id")


def _settlement_user(settlement: Mapping[str, Any]) -> str:
    value = _required(settlement, "user_id", "user_id", "player_id", "owner_user_id")
    return _identity(value, "settlement.user_id")


def _settlement_item(settlement: Mapping[str, Any]) -> str:
    value = _required(
        settlement,
        "functional_drop_id",
        "functional_drop_id",
        "item_id",
        "drop_item_id",
    )
    return _identity(value, "settlement.functional_drop_id")


def _settlement_monster(settlement: Mapping[str, Any]) -> str:
    value = _required(settlement, "monster_id", "monster_id", "monster_type")
    return _identity(value, "settlement.monster_id")


def _settlement_source(settlement: Mapping[str, Any], ownership: Mapping[str, Any]) -> str:
    value = _first(settlement, "source", "acquisition_source")
    if value is _MISSING:
        value = _first(ownership, "source", "acquisition_source")
    if not isinstance(value, str) or value.strip().lower() != SOURCE_DROP:
        _fail("INVALID_MONSTER_ACQUISITION_SOURCE", "Monster Equipment source must be drop")
    return SOURCE_DROP


def _source_operation_id(settlement: Mapping[str, Any], extra: Mapping[str, Any], settlement_id: str) -> str:
    value = _first(
        extra,
        "source_operation_id",
        "operation_id",
        "settlement_operation_id",
    )
    if value is _MISSING:
        value = _first(settlement, "source_operation_id", "operation_id", "settlement_operation_id")
    # A settlement_id is a server-owned immutable operation identity when a
    # producer has not exposed a separate operation id. It is never used as
    # the ownership identity.
    return _identity(settlement_id if value is _MISSING else value, "source_operation_id")


def _lineage_event_id(settlement: Mapping[str, Any], ownership: Mapping[str, Any], extra: Mapping[str, Any]) -> str:
    value = _first(
        extra,
        "lineage_event_id",
        "item_acquisition_event_id",
        "acquisition_event_id",
    )
    if value is _MISSING:
        value = _first(
            ownership,
            "lineage_event_id",
            "item_acquisition_event_id",
            "acquisition_event_id",
        )
    if value is _MISSING:
        value = _first(settlement, "lineage_event_id", "item_acquisition_event_id", "acquisition_event_id")
    if value is _MISSING:
        event_record = settlement.get("event_record", _MISSING)
        if event_record is not _MISSING:
            event_mapping = _as_mapping(event_record, "settlement.event_record")
            value = event_mapping.get("event_id", _MISSING)
    if value is _MISSING:
        _fail("LINEAGE_EVENT_ID_REQUIRED", "committed Monster acquisition lineage identity is required")
    return _identity(value, "lineage_event_id")


def _quantity(settlement: Mapping[str, Any], ownership: Mapping[str, Any], extra: Mapping[str, Any]) -> int:
    value = _first(extra, "quantity", "functional_drop_quantity")
    if value is _MISSING:
        value = _first(ownership, "quantity", "grant_quantity")
    if value is _MISSING:
        value = _first(settlement, "functional_drop_quantity", "quantity")
    if value is _MISSING:
        # One exact B040 row represents one functional Equipment acquisition.
        value = 1
    quantity = _positive_int(value, "quantity")
    if quantity != 1:
        _fail(
            "EXACT_ROW_QUANTITY_UNSUPPORTED",
            "one D025 result must correspond to exactly one B040 ownership row",
        )
    return quantity


def _item_class_and_capabilities(
    item_id: str,
    ownership: Mapping[str, Any],
    extra: Mapping[str, Any],
) -> tuple[str, bool, bool, bool, dict[str, Any]]:
    item_class_value = _first(extra, "item_class", "acquisition_class")
    if item_class_value is _MISSING:
        item_class_value = _first(ownership, "item_class", "acquisition_class", "reward_class")

    slot = _first(extra, "canonical_slot", "slot")
    if slot is _MISSING:
        slot = _first(ownership, "canonical_slot", "slot")
    normalized_slot = str(slot).strip().lower() if isinstance(slot, str) and slot.strip() else None

    if item_id == GO_STONE_BLACK:
        derived_class = "TROPHY"
        derived_capabilities = (False, False, False)
        special_status = GO_STONE_BLACK_STATUS
    elif item_id == XP_AMULET:
        derived_class = "ACCESSORY"
        derived_capabilities = (False, False, False)
        special_status = XP_AMULET_STATUS
    else:
        class_by_slot = {"weapon": "WEAPON", "armor": "ARMOR", "accessory": "ACCESSORY"}
        derived_class = class_by_slot.get(normalized_slot or "")
        if derived_class is None and item_class_value is _MISSING:
            _fail("ITEM_CLASS_UNAVAILABLE", "B040/server item class evidence is required")
        if derived_class is None:
            derived_class = str(item_class_value).strip().upper()
        derived_capabilities = (
            derived_class in {"WEAPON", "ARMOR", "ACCESSORY"},
            False,
            False,
        )
        special_status = None

    if item_class_value is not _MISSING and str(item_class_value).strip().upper() != derived_class:
        _fail("ITEM_CLASS_MISMATCH", "server item class disagrees with the exact Equipment identity")

    capability_values: list[Any] = []
    for name in ("can_equip", "can_use", "can_wear"):
        value = _first(extra, name)
        if value is _MISSING:
            value = _first(ownership, name)
        capability_values.append(value)
    if any(value is not _MISSING for value in capability_values):
        if any(value is _MISSING for value in capability_values):
            _fail("CAPABILITIES_INCOMPLETE", "all capability flags are required when supplied")
        capabilities = tuple(_bool(value, f"{name}") for name, value in zip(("can_equip", "can_use", "can_wear"), capability_values))
    else:
        capabilities = derived_capabilities

    if item_id in {GO_STONE_BLACK, XP_AMULET} and capabilities != (False, False, False):
        _fail("SPECIAL_ITEM_CAPABILITY_LOCK", f"{item_id} cannot gain gameplay capabilities")
    if normalized_slot and item_id not in {GO_STONE_BLACK, XP_AMULET} and derived_class in {"WEAPON", "ARMOR", "ACCESSORY"} and normalized_slot != derived_class.lower():
        _fail("CANONICAL_SLOT_MISMATCH", "B040 canonical slot does not match item class")

    metadata: dict[str, Any] = {
        "adapter_version": D025_CONTRACT_VERSION,
        "source_authority": "MONSTER_SETTLEMENT",
        "ownership_reference_kind": "ROW_PRIMARY_KEY",
    }
    if normalized_slot is not None:
        metadata["canonical_slot"] = normalized_slot
    if special_status is not None:
        metadata["special_status"] = special_status
    return derived_class, capabilities[0], capabilities[1], capabilities[2], metadata


def _is_new(ownership: Mapping[str, Any], settlement: Mapping[str, Any], extra: Mapping[str, Any]) -> bool | None:
    value = _first(extra, "is_new", "new")
    if value is _MISSING:
        value = _first(ownership, "is_new", "new")
    if value is _MISSING:
        value = _first(settlement, "is_new", "new")
    return _optional_bool(value, "is_new")


def _replayed(settlement: Mapping[str, Any], ownership: Mapping[str, Any], extra: Mapping[str, Any]) -> bool:
    value = _first(extra, "replayed", "is_replay")
    if value is _MISSING:
        value = _first(ownership, "replayed", "is_replay")
    if value is _MISSING:
        value = _first(settlement, "replayed", "is_replay", "duplicate")
    return False if value is _MISSING else _bool(value, "replayed")


def _resulting_quantity(ownership: Mapping[str, Any], settlement: Mapping[str, Any], extra: Mapping[str, Any]) -> int | None:
    value = _first(extra, "resulting_quantity", "new_quantity", "owned_quantity")
    if value is _MISSING:
        value = _first(ownership, "resulting_quantity", "new_quantity", "owned_quantity")
    if value is _MISSING:
        value = _first(settlement, "resulting_quantity", "new_quantity", "owned_quantity")
    if value is _MISSING or value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("INVALID_RESULTING_QUANTITY", "resulting_quantity must be a non-negative integer or null")
    return value


def _ownership_user(ownership: Mapping[str, Any]) -> str:
    values: list[str] = []
    for mapping in _nested_mappings(ownership):
        for name in ("user_id", "player_id", "owner_user_id"):
            if name in mapping:
                values.append(_identity(mapping[name], f"ownership.{name}"))
    if not values:
        _fail("REQUIRED_TRUSTED_FACT_MISSING", "ownership.user_id is required")
    if len(set(values)) != 1:
        _fail("OWNERSHIP_USER_BINDING_MISMATCH", "nested B040 ownership users differ")
    return values[0]


def _ownership_item(ownership: Mapping[str, Any]) -> str:
    values: list[str] = []
    for mapping in _nested_mappings(ownership):
        for name in ("equip_id", "item_id"):
            if name in mapping:
                values.append(_identity(mapping[name], f"ownership.{name}"))
    if not values:
        _fail("REQUIRED_TRUSTED_FACT_MISSING", "ownership.equip_id is required")
    if len(set(values)) != 1:
        _fail("OWNERSHIP_ITEM_MISMATCH", "nested B040 ownership items differ")
    return values[0]


def build_monster_equipment_acquisition_result(
    settlement: Any,
    ownership_result: Any,
    *,
    committed_facts: Any | None = None,
) -> CanonicalAcquisitionResult:
    """Build one detached D020 result from committed Monster/B040 facts.

    ``committed_facts`` is an optional server-only envelope for facts that are
    not part of the narrow B040 result object (for example commit markers,
    capabilities, lineage, or item class).  It is never treated as client
    authority.  Both the settlement and ownership boundaries require explicit
    committed evidence; ``SUCCESS`` alone is intentionally insufficient.
    """

    settlement_mapping = _as_mapping(settlement, "settlement")
    ownership_mapping = _as_mapping(ownership_result, "ownership_result")
    extra = {} if committed_facts is None else dict(_as_mapping(committed_facts, "committed_facts"))

    _status_evidence(
        _nested_mappings(settlement_mapping) + (extra,),
        marker_names=("committed", "settlement_committed", "commit_completed"),
        status_names=("settlement_status", "transaction_status", "status", "outcome"),
        label="settlement",
    )
    _status_evidence(
        _nested_mappings(ownership_mapping) + (extra,),
        marker_names=("ownership_committed", "committed", "commit_completed"),
        status_names=("ownership_status", "transaction_status", "status", "outcome"),
        label="ownership",
    )

    settlement_id = _settlement_id(settlement_mapping)
    settlement_user = _settlement_user(settlement_mapping)
    ownership_user = _ownership_user(ownership_mapping)
    if settlement_user != ownership_user:
        _fail("OWNERSHIP_USER_BINDING_MISMATCH", "settlement and B040 ownership users differ")

    settlement_item = _settlement_item(settlement_mapping)
    ownership_item = _ownership_item(ownership_mapping)
    if settlement_item != ownership_item:
        _fail("OWNERSHIP_ITEM_MISMATCH", "settlement drop and B040 ownership item differ")

    source = _settlement_source(settlement_mapping, ownership_mapping)
    ownership_reference, row_id = _ownership_reference(ownership_mapping)
    quantity = _quantity(settlement_mapping, ownership_mapping, extra)
    item_class, can_equip, can_use, can_wear, metadata = _item_class_and_capabilities(
        settlement_item, ownership_mapping, extra
    )
    replayed = _replayed(settlement_mapping, ownership_mapping, extra)
    is_new = _is_new(ownership_mapping, settlement_mapping, extra)
    if replayed and is_new is True:
        evidence = _first(extra, "ownership_evidence")
        if evidence is _MISSING:
            evidence = _first(ownership_mapping, "ownership_evidence")
        if not isinstance(evidence, Mapping):
            _fail("REPLAY_NEW_OWNERSHIP_UNVERIFIED", "replayed new state needs verified ownership evidence")
        metadata["ownership_evidence"] = dict(evidence)

    source_operation_id = _source_operation_id(settlement_mapping, extra, settlement_id)
    lineage_event_id = _lineage_event_id(settlement_mapping, ownership_mapping, extra)
    monster_id = _settlement_monster(settlement_mapping)
    encounter_class = _first(settlement_mapping, "encounter_class", "encounter_kind")
    if encounter_class is not _MISSING:
        normalized_encounter = _identity(encounter_class, "settlement.encounter_class").upper()
        if normalized_encounter in {"LORD", "LORD_TRIAL", "LORD_CLEAR"}:
            _fail("LORD_AUTHORITY_BOUNDARY", "Battlefield Boss and Lord authority are distinct")
        metadata["encounter_class"] = normalized_encounter

    metadata.update(
        {
            "settlement_id": settlement_id,
            "monster_id": monster_id,
            "ownership_row_id": row_id,
            "source": source,
            "settlement_authority": "MONSTER_SETTLEMENT",
        }
    )

    return CanonicalAcquisitionResult(
        contract_version=CONTRACT_VERSION,
        item_id=settlement_item,
        quantity=quantity,
        source_type=MONSTER_DROP,
        source_operation_id=source_operation_id,
        source_reference=settlement_id,
        destination=PLAYER_INVENTORY,
        ownership_authority=PLAYER_INVENTORY_AUTHORITY,
        ownership_reference=ownership_reference,
        resulting_quantity=_resulting_quantity(ownership_mapping, settlement_mapping, extra),
        is_new=is_new,
        can_equip=can_equip,
        can_use=can_use,
        can_wear=can_wear,
        replayed=replayed,
        lineage_event_id=lineage_event_id,
        item_class=item_class,
        metadata=metadata,
    )


adapt_committed_monster_equipment = build_monster_equipment_acquisition_result
adapt_monster_equipment_acquisition = build_monster_equipment_acquisition_result


__all__ = [
    "DATABASE_WRITES",
    "D025_CONTRACT_VERSION",
    "MONSTER_DROP",
    "MUTATION_CAPABILITY",
    "MonsterEquipmentAcquisitionError",
    "PLAYER_INVENTORY",
    "PLAYER_INVENTORY_AUTHORITY",
    "READ_ONLY",
    "READY",
    "adapt_committed_monster_equipment",
    "adapt_monster_equipment_acquisition",
    "build_monster_equipment_acquisition_result",
]
