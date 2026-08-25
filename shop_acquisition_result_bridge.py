"""Read-only Shop acquisition ownership-reference bridge.

This module consumes an already committed C019/C023-compatible purchase
fact and produces the accepted D020 CanonicalAcquisitionResult envelope.
It does not perform a purchase, retry an operation, mutate an ownership
authority, append lineage, or use D5C item-use semantics.

The two supported ownership authorities deliberately use aggregate/set
identities that C023 can prove after commit:

* shop_inventory:{user_id}:{item_key}
* player_wardrobe:{user_id}:{item_id}

player_inventory is intentionally rejected because the current Commerce
result does not persist the exact inserted inventory row id.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from canonical_acquisition_result import (
    CONTRACT_VERSION,
    CanonicalAcquisitionResult,
)


SHOP_INVENTORY = "shop_inventory"
PLAYER_WARDROBE = "player_wardrobe"
PLAYER_INVENTORY = "player_inventory"

SUPPORTED_DESTINATIONS = (SHOP_INVENTORY, PLAYER_WARDROBE)
UNSUPPORTED_DESTINATIONS = (
    PLAYER_INVENTORY,
    "pet_inventory",
    "capacity",
    "credit",
    "entitlement",
)

SHOP_INVENTORY_REFERENCE_TEMPLATE = "shop_inventory:{user_id}:{item_key}"
PLAYER_WARDROBE_REFERENCE_TEMPLATE = "player_wardrobe:{user_id}:{item_id}"

PLAYER_INVENTORY_FAILURE_CODE = "OWNERSHIP_REFERENCE_UNAVAILABLE"
DATABASE_WRITES = 0
MUTATION_CAPABILITY = "NO"
READ_ONLY = True

_MISSING = object()
_COMMITTED_STATUSES = frozenset({"COMMITTED", "SETTLED"})
_VALID_RESULT_STATUSES = frozenset({"SUCCESS", "COMMITTED", "SETTLED"})
_REJECTED_STATUSES = frozenset({"FAILED", "PENDING", "PREVIEW", "UNCOMMITTED", "UNSETTLED"})
_COMMIT_MARKERS = (
    "committed",
    "purchase_committed",
    "settlement_committed",
)
_STATUS_FIELDS = (
    "operation_status",
    "purchase_status",
    "transaction_status",
    "settlement_status",
    "status",
)


class ShopAcquisitionBridgeError(ValueError):
    """Stable fail-closed error for the route-independent bridge."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> None:
    raise ShopAcquisitionBridgeError(code, message)


def _as_mapping(value: Any, field: str) -> Mapping[str, Any]:
    """Accept mappings, DB rows, and C023 result objects without guessing."""

    if isinstance(value, Mapping):
        return value

    for method_name in ("as_dict", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            converted = method()
            if isinstance(converted, Mapping):
                return converted

    keys = getattr(value, "keys", None)
    if callable(keys):
        try:
            names = tuple(keys())
            return {name: value[name] for name in names}
        except (KeyError, TypeError, IndexError) as exc:
            raise ShopAcquisitionBridgeError(
                "INVALID_TRUSTED_FACT",
                f"{field} could not be read as a mapping",
            ) from exc

    _fail("INVALID_TRUSTED_FACT", f"{field} must be a mapping or result object")


def _value(mapping: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return _MISSING


def _nested_value(
    outer: Mapping[str, Any],
    nested: Mapping[str, Any],
    *names: str,
) -> Any:
    value = _value(nested, *names)
    if value is not _MISSING:
        return value
    return _value(outer, *names)


def _required(mapping: Mapping[str, Any], field: str, *names: str) -> Any:
    value = _value(mapping, *names)
    if value is _MISSING or value is None:
        _fail("REQUIRED_TRUSTED_FACT_MISSING", f"{field} is required")
    return value


def _text(value: Any, field: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        _fail("INVALID_TRUSTED_FACT", f"{field} must be a non-empty identity value")
    normalized = str(value).strip()
    if not normalized:
        _fail("REQUIRED_TRUSTED_FACT_MISSING", f"{field} must not be empty")
    return normalized


def _same_identity(left: Any, right: Any) -> bool:
    return _text(left, "identity") == _text(right, "identity")


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail("INVALID_TRUSTED_FACT", f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("INVALID_TRUSTED_FACT", f"{field} must be a non-negative integer")
    return value


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        _fail("INVALID_TRUSTED_FACT", f"{field} must be boolean")
    return value


def _optional_bool(value: Any, field: str) -> bool | None:
    if value is _MISSING or value is None:
        return None
    return _bool(value, field)


def _json_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ShopAcquisitionBridgeError(
                "INVALID_TRUSTED_FACT",
                f"{field} is not valid JSON",
            ) from exc
    return _as_mapping(value, field)


def _validate_terminal_statuses(
    mapping: Mapping[str, Any],
    *,
    field_prefix: str,
    require_commit_evidence: bool,
) -> None:
    """Keep terminal vocabulary separate from explicit commit evidence."""

    has_commit_marker = False
    for name in _COMMIT_MARKERS:
        value = mapping.get(name, _MISSING)
        if value is not _MISSING:
            if not isinstance(value, bool):
                _fail("INVALID_COMMIT_EVIDENCE", f"{field_prefix}.{name} must be boolean")
            has_commit_marker = has_commit_marker or value

    status_seen = False
    for name in _STATUS_FIELDS:
        value = mapping.get(name, _MISSING)
        if value is _MISSING or value is None:
            continue
        status_seen = True
        if not isinstance(value, str):
            _fail("INVALID_COMMIT_EVIDENCE", f"{field_prefix}.{name} must be a status string")
        normalized = value.strip().upper()
        if normalized in _REJECTED_STATUSES or normalized not in _VALID_RESULT_STATUSES:
            _fail("COMMITTED_RESULT_EVIDENCE_REQUIRED", f"{field_prefix}.{name} is not committed")
        if normalized in _COMMITTED_STATUSES:
            has_commit_marker = True

    if require_commit_evidence and not has_commit_marker:
        # SUCCESS is a valid producer result vocabulary value, but never a
        # persistence marker by itself.
        if status_seen:
            _fail(
                "COMMITTED_RESULT_EVIDENCE_REQUIRED",
                f"{field_prefix} has no explicit committed/settled evidence",
            )
        _fail(
            "COMMITTED_RESULT_EVIDENCE_REQUIRED",
            f"{field_prefix} has no explicit commit evidence",
        )


def _event_payload(lineage: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = lineage.get("payload", _MISSING)
    if raw is _MISSING:
        return lineage
    return _json_mapping(raw, "lineage_evidence.payload")


def _validate_lineage(
    lineage_input: Any,
    *,
    user_id: str,
    operation_id: str,
    item_id: str,
    quantity: int,
    destination: str,
    lineage_event_id: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    lineage = _as_mapping(lineage_input, "lineage_evidence")
    event_id = _required(lineage, "lineage_event_id", "event_id", "lineage_event_id")
    if not _same_identity(event_id, lineage_event_id):
        _fail("LINEAGE_ID_MISMATCH", "D5A event id does not match the committed result")

    event_type = lineage.get("event_type", _MISSING)
    if event_type is not _MISSING and str(event_type).strip().upper() != "ITEM_ACQUISITION":
        _fail("D5A_EVIDENCE_INVALID", "lineage event is not ITEM_ACQUISITION")

    for name in ("user_id", "player_id", "owner_user_id"):
        value = lineage.get(name, _MISSING)
        if value is not _MISSING and not _same_identity(value, user_id):
            _fail("OWNERSHIP_USER_BINDING_MISMATCH", f"lineage {name} is not operation-owned")

    payload = _event_payload(lineage)
    for name in ("user_id", "player_id", "owner_user_id"):
        value = payload.get(name, _MISSING)
        if value is not _MISSING and not _same_identity(value, user_id):
            _fail("OWNERSHIP_USER_BINDING_MISMATCH", f"lineage payload {name} is not operation-owned")

    checks = (
        (("source_operation_id", "operation_id", "purchase_operation_id"), operation_id, "source operation"),
        (("item_id", "reward_id", "item_key"), item_id, "item"),
        (("quantity", "reward_quantity"), quantity, "quantity"),
        (("destination",), destination, "destination"),
    )
    for names, expected, label in checks:
        value = _value(payload, *names)
        if value is not _MISSING and not _same_identity(value, expected):
            _fail("D5A_EVIDENCE_MISMATCH", f"lineage {label} does not match the purchase result")

    return lineage, payload


def _verify_authority_row(conn: Any, *, destination: str, user_id: str, item_id: str) -> None:
    """Prove membership with a fixed SELECT; never read quantity or latest id."""

    if destination == SHOP_INVENTORY:
        sql = "SELECT 1 FROM shop_inventory WHERE user_id = ? AND item_key = ?"
    elif destination == PLAYER_WARDROBE:
        sql = "SELECT 1 FROM player_wardrobe WHERE user_id = ? AND item_id = ?"
    else:
        _fail("UNSUPPORTED_DESTINATION", f"unsupported Shop destination: {destination}")

    try:
        cursor = conn.execute(sql, (user_id, item_id))
        row = cursor.fetchone()
    except Exception as exc:
        raise ShopAcquisitionBridgeError(
            "OWNERSHIP_AUTHORITY_UNAVAILABLE",
            f"could not read {destination} ownership authority",
        ) from exc
    if row is None:
        _fail(
            "OWNERSHIP_AUTHORITY_ROW_MISSING",
            f"no committed {destination} ownership row for this operation",
        )


def _first_present(
    outer: Mapping[str, Any],
    nested: Mapping[str, Any],
    *names: str,
) -> Any:
    value = _value(nested, *names)
    if value is not _MISSING:
        return value
    return _value(outer, *names)


def adapt_committed_shop_purchase(
    conn: Any,
    purchase_result: Any,
    operation_record: Any,
    lineage_evidence: Any,
) -> CanonicalAcquisitionResult:
    """Build D020 output from a committed C019/C023 result and read proof.

    operation_record is the trusted, user-bound committed operation row.
    lineage_evidence is the committed D5A ITEM_ACQUISITION evidence.  The
    function only performs one fixed membership SELECT against the supported
    destination and never calls commit or rollback.
    """

    result = _as_mapping(purchase_result, "purchase_result")
    operation = _as_mapping(operation_record, "operation_record")

    # A result status may describe SUCCESS/COMMITTED/SETTLED, but the
    # operation record is the separate persistence authority checked below.
    _validate_terminal_statuses(
        result,
        field_prefix="purchase_result",
        require_commit_evidence=False,
    )
    _validate_terminal_statuses(
        operation,
        field_prefix="operation_record",
        require_commit_evidence=True,
    )

    raw_user_id = _required(operation, "user_id", "user_id", "player_id")
    user_id = _text(raw_user_id, "operation_record.user_id")

    operation_id_value = _required(
        operation,
        "purchase_operation_id",
        "purchase_operation_id",
        "operation_id",
        "source_operation_id",
    )
    operation_id = _text(operation_id_value, "operation_record.purchase_operation_id")

    result_operation_id = _required(
        result,
        "purchase result operation_id",
        "operation_id",
        "source_operation_id",
    )
    if not _same_identity(result_operation_id, operation_id):
        _fail("OPERATION_ID_MISMATCH", "purchase result is not the committed operation")

    for name in ("user_id", "player_id"):
        value = result.get(name, _MISSING)
        if value is not _MISSING and not _same_identity(value, user_id):
            _fail("OWNERSHIP_USER_BINDING_MISMATCH", f"purchase result {name} is not operation-owned")

    destination_value = _required(result, "destination", "destination")
    destination = _text(destination_value, "purchase_result.destination")
    if destination not in SUPPORTED_DESTINATIONS:
        if destination == PLAYER_INVENTORY:
            _fail(
                PLAYER_INVENTORY_FAILURE_CODE,
                "current Commerce result does not persist the exact player_inventory row identity",
            )
        _fail("UNSUPPORTED_DESTINATION", f"Shop destination is not supported: {destination}")

    operation_destination = _value(operation, "destination")
    if operation_destination is not _MISSING and not _same_identity(operation_destination, destination):
        _fail("RESULT_IDENTITY_MISMATCH", "operation and result destinations differ")

    item_value = _required(result, "item_id", "item_id", "reward_id", "item_key")
    item_id = _text(item_value, "purchase_result.item_id")
    trusted_item = _value(operation, "item_id", "reward_id", "item_key")
    if trusted_item is not _MISSING and not _same_identity(trusted_item, item_id):
        _fail("RESULT_IDENTITY_MISMATCH", "operation and result items differ")
    trusted_item_id = _text(
        item_id if trusted_item is _MISSING else trusted_item,
        "operation_record.item_id",
    )
    if not _same_identity(trusted_item_id, item_id):
        _fail("RESULT_IDENTITY_MISMATCH", "item identity is not bound to the operation")

    ownership = _json_mapping(
        _required(result, "ownership_result", "ownership_result"),
        "purchase_result.ownership_result",
    )
    for name in ("destination", "item_id", "item_key"):
        value = ownership.get(name, _MISSING)
        if value is not _MISSING:
            expected = destination if name == "destination" else item_id
            if not _same_identity(value, expected):
                _fail("RESULT_IDENTITY_MISMATCH", f"ownership result {name} does not match purchase result")

    quantity_value = _required(result, "quantity", "quantity", "reward_quantity")
    quantity = _positive_int(quantity_value, "purchase_result.quantity")
    for mapping, field_prefix in ((operation, "operation_record"), (ownership, "ownership_result")):
        value = _value(mapping, "quantity", "reward_quantity")
        if value is not _MISSING and _positive_int(value, f"{field_prefix}.quantity") != quantity:
            _fail("RESULT_IDENTITY_MISMATCH", f"{field_prefix}.quantity differs from purchase result")

    lineage_id_value = _required(
        result,
        "lineage_event_id",
        "lineage_event_id",
        "item_acquisition_event_id",
        "acquisition_event_id",
    )
    lineage_event_id = _text(lineage_id_value, "purchase_result.lineage_event_id")
    operation_lineage = _value(operation, "lineage_event_id", "item_acquisition_event_id")
    if operation_lineage is not _MISSING and not _same_identity(operation_lineage, lineage_event_id):
        _fail("LINEAGE_ID_MISMATCH", "operation lineage id differs from purchase result")

    _, lineage_payload = _validate_lineage(
        lineage_evidence,
        user_id=user_id,
        operation_id=operation_id,
        item_id=item_id,
        quantity=quantity,
        destination=destination,
        lineage_event_id=lineage_event_id,
    )

    source_reference_value = _value(operation, "offer_id", "source_reference", "offer_key")
    if source_reference_value is _MISSING:
        source_reference_value = _value(lineage_payload, "offer_id", "source_reference", "offer_key")
    if source_reference_value is _MISSING:
        _fail("REQUIRED_TRUSTED_FACT_MISSING", "committed offer/source reference is required")
    source_reference = _text(source_reference_value, "source_reference")

    item_class_value = _value(operation, "item_class", "acquisition_class", "reward_class")
    if item_class_value is _MISSING:
        item_class_value = _value(lineage_payload, "item_class", "acquisition_class", "reward_class")
    if item_class_value is _MISSING:
        _fail("REQUIRED_TRUSTED_FACT_MISSING", "committed item_class is required")
    item_class = _text(item_class_value, "item_class").upper()

    resulting_quantity_value = _first_present(
        result,
        ownership,
        "new_quantity",
        "resulting_quantity",
    )
    if resulting_quantity_value is _MISSING:
        _fail("REQUIRED_TRUSTED_FACT_MISSING", "ownership_result.new_quantity is required")
    resulting_quantity = (
        None
        if resulting_quantity_value is None
        else _nonnegative_int(resulting_quantity_value, "ownership_result.new_quantity")
    )

    is_new_value = _first_present(result, ownership, "is_new")
    is_new = _optional_bool(is_new_value, "purchase_result.is_new")
    replayed_value = _value(result, "replayed")
    if replayed_value is _MISSING:
        _fail("REQUIRED_TRUSTED_FACT_MISSING", "purchase_result.replayed is required")
    replayed = _bool(replayed_value, "purchase_result.replayed")

    capabilities: dict[str, bool] = {}
    for name in ("can_equip", "can_use", "can_wear"):
        value = _first_present(result, ownership, name)
        if value is _MISSING:
            _fail("REQUIRED_TRUSTED_FACT_MISSING", f"ownership_result.{name} is required")
        capabilities[name] = _bool(value, f"ownership_result.{name}")

    ownership_reference = (
        SHOP_INVENTORY_REFERENCE_TEMPLATE.format(user_id=user_id, item_key=item_id)
        if destination == SHOP_INVENTORY
        else PLAYER_WARDROBE_REFERENCE_TEMPLATE.format(user_id=user_id, item_id=item_id)
    )
    supplied_reference = _first_present(result, ownership, "ownership_reference")
    if supplied_reference is not _MISSING and not _same_identity(supplied_reference, ownership_reference):
        _fail(
            "CLIENT_OWNERSHIP_REFERENCE_REJECTED",
            "ownership_reference must be derived from the authority key",
        )

    _verify_authority_row(
        conn,
        destination=destination,
        user_id=user_id,
        item_id=item_id,
    )

    metadata_value = _value(operation, "metadata", "presentation_metadata")
    metadata: dict[str, Any] = {
        "bridge_version": "D023_SHOP_ACQUISITION_RESULT_BRIDGE_V1",
        "source_destination": destination,
        "ownership_reference_kind": "COMPOSITE_AUTHORITY_KEY",
    }
    if metadata_value is not _MISSING:
        metadata.update(dict(_json_mapping(metadata_value, "operation_record.metadata")))
    special_status = _value(operation, "special_status")
    if special_status is not _MISSING:
        metadata["special_status"] = _text(special_status, "operation_record.special_status")

    # D020 separates replay transport from is_new. A replayed C023 result may
    # truthfully retain is_new=true; the committed result's explicit is_new
    # fact is the evidence for the pre-grant state.
    if replayed and is_new is True:
        metadata["ownership_evidence"] = {
            "verified": True,
            "pre_grant_owned": False,
            "authority": destination,
            "basis": "committed_result_is_new",
        }

    d018_destination = "STACK_INVENTORY" if destination == SHOP_INVENTORY else "PLAYER_WARDROBE"
    return CanonicalAcquisitionResult(
        contract_version=CONTRACT_VERSION,
        item_id=item_id,
        quantity=quantity,
        source_type="SHOP_COIN_PURCHASE",
        source_operation_id=operation_id,
        source_reference=source_reference,
        destination=d018_destination,
        ownership_authority=destination,
        ownership_reference=ownership_reference,
        resulting_quantity=resulting_quantity,
        is_new=is_new,
        can_equip=capabilities["can_equip"],
        can_use=capabilities["can_use"],
        can_wear=capabilities["can_wear"],
        replayed=replayed,
        lineage_event_id=lineage_event_id,
        item_class=item_class,
        metadata=metadata,
    )


adapt_shop_acquisition_result = adapt_committed_shop_purchase
bridge_shop_purchase_result = adapt_committed_shop_purchase


__all__ = [
    "DATABASE_WRITES",
    "MUTATION_CAPABILITY",
    "PLAYER_INVENTORY",
    "PLAYER_INVENTORY_FAILURE_CODE",
    "PLAYER_WARDROBE",
    "PLAYER_WARDROBE_REFERENCE_TEMPLATE",
    "READ_ONLY",
    "SHOP_INVENTORY",
    "SHOP_INVENTORY_REFERENCE_TEMPLATE",
    "SUPPORTED_DESTINATIONS",
    "ShopAcquisitionBridgeError",
    "adapt_committed_shop_purchase",
    "adapt_shop_acquisition_result",
    "bridge_shop_purchase_result",
]
