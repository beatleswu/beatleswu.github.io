"""Canonical Acquisition Result V1 cross-producer result contract.

This module defines an immutable result envelope only.  It does not own
inventory, wardrobe, currency, capacity, entitlement, purchase, or item-use
state and deliberately does not import :mod:`app`.

The envelope lets an upstream, already-authoritative producer describe one
committed acquisition in a common shape while preserving the producer's
domain-specific ownership authority.  D5A lineage is evidence for the
acquisition; D5C item-use lineage remains a separate concern.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
import json
from types import MappingProxyType
from typing import Any


CONTRACT_VERSION = "CANONICAL_ACQUISITION_RESULT_V1"

SOURCE_TYPES = (
    "MONSTER_DROP",
    "QUEST_REWARD",
    "PREMIUM_REWARD",
    "SHOP_COIN_PURCHASE",
    "STARTER_GRANT",
    "ADMIN_GRANT",
    "LEGACY_GRANT",
    "EVENT_REWARD",
)

DESTINATIONS = (
    "PLAYER_INVENTORY",
    "PLAYER_WARDROBE",
    "STACK_INVENTORY",
    "ENTITLEMENT",
    "QUESTION_CAPACITY",
    "CREDIT",
    "TROPHY_OWNERSHIP",
    "OTHER_EXISTING_AUTHORITY",
)

ITEM_CLASSES = (
    "WEAPON",
    "ARMOR",
    "ACCESSORY",
    "CONSUMABLE",
    "SPIRIT_CONSUMABLE",
    "XP_CONSUMABLE",
    "MATERIAL",
    "COSMETIC",
    "TROPHY",
)

GO_STONE_BLACK = "go_stone_black"
XP_AMULET = "xp_amulet"
GO_STONE_BLACK_STATUS = "TROPHY_INVENTORY_ONLY_NO_COMBAT_POWER"
XP_AMULET_STATUS = "HOLD_FOR_AUTHORITY"

MAX_ID_LENGTH = 255
MAX_REFERENCE_LENGTH = 512
MAX_METADATA_KEYS = 32
MAX_METADATA_DEPTH = 4
MAX_METADATA_LIST_LENGTH = 32
MAX_METADATA_STRING_LENGTH = 512
MAX_METADATA_JSON_LENGTH = 8192


class AcquisitionResultError(ValueError):
    """Base class for fail-closed acquisition result errors."""


class AcquisitionResultValidationError(AcquisitionResultError):
    """A result envelope violates the V1 contract.

    ``code`` is stable for callers and tests; the human message is diagnostic
    only and must not be used as an authority signal.
    """

    def __init__(self, code: str, message: str, *, field: str | None = None):
        self.code = code
        self.field = field
        super().__init__(f"{code}: {message}")


def _error(code: str, message: str, *, field: str | None = None) -> None:
    raise AcquisitionResultValidationError(code, message, field=field)


def _text(value: Any, field: str, *, limit: int = MAX_REFERENCE_LENGTH) -> str:
    if not isinstance(value, str):
        _error("INVALID_TEXT", f"{field} must be a string", field=field)
    normalized = value.strip()
    if not normalized:
        _error("MISSING_REQUIRED_FIELD", f"{field} must not be empty", field=field)
    if len(normalized) > limit:
        _error("TEXT_TOO_LONG", f"{field} exceeds {limit} characters", field=field)
    return normalized


def _enum(value: Any, field: str, allowed: tuple[str, ...]) -> str:
    normalized = _text(value, field, limit=MAX_ID_LENGTH).upper()
    if normalized not in allowed:
        _error("UNKNOWN_ENUM_VALUE", f"unsupported {field}: {normalized!r}", field=field)
    return normalized


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _error("INVALID_INTEGER", f"{field} must be an integer", field=field)
    if value <= 0:
        _error("NON_POSITIVE_QUANTITY", f"{field} must be greater than zero", field=field)
    return value


def _optional_nonnegative_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        _error("INVALID_INTEGER", f"{field} must be an integer or null", field=field)
    if value < 0:
        _error("NEGATIVE_RESULTING_QUANTITY", f"{field} must not be negative", field=field)
    return value


def _optional_bool(value: Any, field: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        _error("INVALID_BOOLEAN", f"{field} must be boolean or null", field=field)
    return value


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        _error("INVALID_BOOLEAN", f"{field} must be boolean", field=field)
    return value


def _freeze_metadata(value: Any, *, depth: int = 0, path: str = "metadata") -> Any:
    """Validate and recursively freeze bounded JSON-compatible metadata."""

    if depth > MAX_METADATA_DEPTH:
        _error("METADATA_TOO_DEEP", f"{path} exceeds metadata nesting limit")
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and len(value) > MAX_METADATA_STRING_LENGTH:
            _error("METADATA_VALUE_TOO_LONG", f"{path} contains an oversized string")
        return value
    if isinstance(value, float):
        if not isfinite(value):
            _error("METADATA_NOT_JSON_SAFE", f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        if len(value) > MAX_METADATA_KEYS:
            _error("METADATA_TOO_LARGE", f"{path} has too many keys")
        frozen: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str) or not key.strip():
                _error("METADATA_KEY_INVALID", f"{path} keys must be non-empty strings")
            normalized_key = key.strip()
            if len(normalized_key) > MAX_METADATA_STRING_LENGTH:
                _error("METADATA_KEY_TOO_LONG", f"{path} contains an oversized key")
            frozen[normalized_key] = _freeze_metadata(
                child, depth=depth + 1, path=f"{path}.{normalized_key}"
            )
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_METADATA_LIST_LENGTH:
            _error("METADATA_LIST_TOO_LARGE", f"{path} has too many entries")
        return tuple(
            _freeze_metadata(child, depth=depth + 1, path=f"{path}[{index}]")
            for index, child in enumerate(value)
        )
    _error("METADATA_NOT_JSON_SAFE", f"{path} contains an unsupported value")


def _thaw_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_metadata(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw_metadata(child) for child in value]
    return value


def _validate_capabilities(
    *,
    item_id: str,
    item_class: str,
    destination: str,
    can_equip: bool,
    can_use: bool,
    can_wear: bool,
    metadata: Mapping[str, Any],
) -> None:
    capabilities = (can_equip, can_use, can_wear)

    if item_id == GO_STONE_BLACK:
        if item_class != "TROPHY" or destination != "PLAYER_INVENTORY" or any(capabilities):
            _error(
                "GO_STONE_BLACK_LOCK",
                "go_stone_black is inventory-only trophy data with no gameplay capability",
            )
        if metadata.get("special_status") not in (None, GO_STONE_BLACK_STATUS):
            _error("GO_STONE_BLACK_LOCK", "go_stone_black has an unsupported special status")

    if item_class == "TROPHY" and any(capabilities):
        _error("TROPHY_GAMEPLAY_CAPABILITY", "a trophy cannot be equipped, used, or worn")
    if item_class == "MATERIAL" and any(capabilities):
        _error("MATERIAL_GAMEPLAY_CAPABILITY", "a material has no direct use/equip/wear capability")
    if item_class == "COSMETIC":
        if not can_wear or can_use:
            _error("COSMETIC_CAPABILITY_CONTRADICTION", "a pure cosmetic must be wearable and not usable")
        if can_equip and metadata.get("capability_basis") != "EXISTING_EQUIP_SEMANTICS":
            _error(
                "COSMETIC_COMBAT_CAPABILITY",
                "cosmetic equip terminology requires explicit existing semantics evidence",
            )
        if destination != "PLAYER_WARDROBE":
            _error("COSMETIC_DESTINATION_MISMATCH", "pure cosmetics must land in player_wardrobe")
    if item_class in {"CONSUMABLE", "SPIRIT_CONSUMABLE", "XP_CONSUMABLE"} and not can_use:
        if item_id != XP_AMULET:
            _error("CONSUMABLE_CAPABILITY_MISSING", "a consumable must declare can_use=true")

    if item_id == XP_AMULET:
        if any(capabilities):
            _error("XP_AMULET_HOLD", "xp_amulet capabilities remain on hold for authority review")
        if metadata.get("special_status") != XP_AMULET_STATUS:
            _error("XP_AMULET_HOLD", "xp_amulet must explicitly preserve HOLD_FOR_AUTHORITY")


def _validate_replay_semantics(
    *, is_new: bool | None, replayed: bool, metadata: Mapping[str, Any]
) -> None:
    if not replayed or is_new is not True:
        return
    evidence = metadata.get("ownership_evidence")
    if not isinstance(evidence, Mapping):
        _error(
            "REPLAY_NEW_OWNERSHIP_UNVERIFIED",
            "replayed is_new=true requires verified ownership evidence",
        )
    if evidence.get("verified") is not True or evidence.get("pre_grant_owned") is not False:
        _error(
            "REPLAY_NEW_OWNERSHIP_UNVERIFIED",
            "replay ownership evidence must prove the identity was absent before grant",
        )
    _text(evidence.get("authority"), "metadata.ownership_evidence.authority")


@dataclass(frozen=True, slots=True)
class CanonicalAcquisitionResult:
    """One immutable, validated result from an authoritative acquisition."""

    contract_version: str
    item_id: str
    quantity: int
    source_type: str
    source_operation_id: str
    source_reference: str
    destination: str
    ownership_authority: str
    ownership_reference: str
    resulting_quantity: int | None
    is_new: bool | None
    can_equip: bool
    can_use: bool
    can_wear: bool
    replayed: bool
    lineage_event_id: str
    item_class: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.contract_version != CONTRACT_VERSION:
            _error("UNSUPPORTED_CONTRACT_VERSION", "contract_version is not the V1 contract")
        object.__setattr__(self, "contract_version", CONTRACT_VERSION)
        object.__setattr__(self, "item_id", _text(self.item_id, "item_id", limit=MAX_ID_LENGTH))
        object.__setattr__(self, "quantity", _positive_int(self.quantity, "quantity"))
        object.__setattr__(self, "source_type", _enum(self.source_type, "source_type", SOURCE_TYPES))
        object.__setattr__(self, "source_operation_id", _text(self.source_operation_id, "source_operation_id"))
        object.__setattr__(self, "source_reference", _text(self.source_reference, "source_reference"))
        object.__setattr__(self, "destination", _enum(self.destination, "destination", DESTINATIONS))
        object.__setattr__(self, "ownership_authority", _text(self.ownership_authority, "ownership_authority"))
        object.__setattr__(self, "ownership_reference", _text(self.ownership_reference, "ownership_reference"))
        object.__setattr__(
            self,
            "resulting_quantity",
            _optional_nonnegative_int(self.resulting_quantity, "resulting_quantity"),
        )
        object.__setattr__(self, "is_new", _optional_bool(self.is_new, "is_new"))
        object.__setattr__(self, "can_equip", _bool(self.can_equip, "can_equip"))
        object.__setattr__(self, "can_use", _bool(self.can_use, "can_use"))
        object.__setattr__(self, "can_wear", _bool(self.can_wear, "can_wear"))
        object.__setattr__(self, "replayed", _bool(self.replayed, "replayed"))
        object.__setattr__(self, "lineage_event_id", _text(self.lineage_event_id, "lineage_event_id"))
        object.__setattr__(self, "item_class", _enum(self.item_class, "item_class", ITEM_CLASSES))
        metadata = _freeze_metadata(self.metadata)
        if not isinstance(metadata, Mapping):
            _error("METADATA_NOT_OBJECT", "metadata must be a JSON object")
        encoded = json.dumps(_thaw_metadata(metadata), ensure_ascii=False, allow_nan=False, sort_keys=True)
        if len(encoded) > MAX_METADATA_JSON_LENGTH:
            _error("METADATA_TOO_LARGE", "metadata exceeds the serialized size limit")
        object.__setattr__(self, "metadata", metadata)
        _validate_capabilities(
            item_id=self.item_id,
            item_class=self.item_class,
            destination=self.destination,
            can_equip=self.can_equip,
            can_use=self.can_use,
            can_wear=self.can_wear,
            metadata=metadata,
        )
        _validate_replay_semantics(is_new=self.is_new, replayed=self.replayed, metadata=metadata)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible defensive copy of the envelope."""

        return {
            "contract_version": self.contract_version,
            "item_id": self.item_id,
            "quantity": self.quantity,
            "source_type": self.source_type,
            "source_operation_id": self.source_operation_id,
            "source_reference": self.source_reference,
            "destination": self.destination,
            "ownership_authority": self.ownership_authority,
            "ownership_reference": self.ownership_reference,
            "resulting_quantity": self.resulting_quantity,
            "is_new": self.is_new,
            "can_equip": self.can_equip,
            "can_use": self.can_use,
            "can_wear": self.can_wear,
            "replayed": self.replayed,
            "lineage_event_id": self.lineage_event_id,
            "item_class": self.item_class,
            "metadata": _thaw_metadata(self.metadata),
        }

    as_dict = to_dict

    def to_json(self) -> str:
        """Serialize deterministically for transport or committed replay."""

        return json.dumps(
            self.to_dict(), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CanonicalAcquisitionResult":
        """Validate a producer payload without silently dropping fields."""

        if not isinstance(payload, Mapping):
            _error("INVALID_ENVELOPE", "acquisition result must be a mapping")
        required = {
            "contract_version",
            "item_id",
            "quantity",
            "source_type",
            "source_operation_id",
            "source_reference",
            "destination",
            "ownership_authority",
            "ownership_reference",
            "resulting_quantity",
            "is_new",
            "can_equip",
            "can_use",
            "can_wear",
            "replayed",
            "lineage_event_id",
            "item_class",
        }
        missing = sorted(required.difference(payload.keys()))
        if missing:
            _error("MISSING_REQUIRED_FIELD", f"missing fields: {', '.join(missing)}")
        unknown = sorted(set(payload.keys()).difference(required | {"metadata"}))
        if unknown:
            _error("UNKNOWN_FIELD", f"unsupported envelope fields: {', '.join(map(str, unknown))}")
        return cls(
            contract_version=payload["contract_version"],
            item_id=payload["item_id"],
            quantity=payload["quantity"],
            source_type=payload["source_type"],
            source_operation_id=payload["source_operation_id"],
            source_reference=payload["source_reference"],
            destination=payload["destination"],
            ownership_authority=payload["ownership_authority"],
            ownership_reference=payload["ownership_reference"],
            resulting_quantity=payload["resulting_quantity"],
            is_new=payload["is_new"],
            can_equip=payload["can_equip"],
            can_use=payload["can_use"],
            can_wear=payload["can_wear"],
            replayed=payload["replayed"],
            lineage_event_id=payload["lineage_event_id"],
            item_class=payload["item_class"],
            metadata=payload.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, payload: str) -> "CanonicalAcquisitionResult":
        if not isinstance(payload, str):
            _error("INVALID_JSON", "serialized acquisition result must be a string")
        try:
            decoded = json.loads(payload)
        except (TypeError, ValueError) as exc:
            raise AcquisitionResultValidationError("INVALID_JSON", "serialized acquisition result is invalid JSON") from exc
        return cls.from_mapping(decoded)


__all__ = [
    "ACQUISITION_RESULT_CONTRACT_VERSION",
    "CONTRACT_VERSION",
    "DESTINATIONS",
    "GO_STONE_BLACK",
    "GO_STONE_BLACK_STATUS",
    "ITEM_CLASSES",
    "CanonicalAcquisitionResult",
    "AcquisitionResultError",
    "AcquisitionResultValidationError",
    "SOURCE_TYPES",
    "XP_AMULET",
    "XP_AMULET_STATUS",
]


ACQUISITION_RESULT_CONTRACT_VERSION = CONTRACT_VERSION
