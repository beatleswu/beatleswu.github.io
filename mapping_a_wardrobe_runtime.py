"""F027-R1 Mapping A wardrobe/runtime consumption boundary.

Mapping A is a locked, presentation-only subset of the existing appearance
catalog.  This module consumes the already-authoritative B028 cosmetics
projection; it never grants ownership, equips an item, compensates a replay,
or commits a transaction.  Invalid catalog or projection facts fail closed so
the caller cannot turn a malformed cosmetic record into a renderable item.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final


READY: Final[str] = "READY"
INVALID_STORED_STATE: Final[str] = "INVALID_STORED_STATE"
AUTHORITY_UNAVAILABLE: Final[str] = "AUTHORITY_UNAVAILABLE"
WARDROBE_AUTHORITY: Final[str] = "player_wardrobe_and_player_appearance"
MAPPING_A_COMBAT_POWER: Final[int] = 0
MAPPING_A_VERSION: Final[str] = "F027_R1_MAPPING_A_V1"

APPEARANCE_SLOTS: Final[tuple[str, ...]] = (
    "outfit",
    "hat",
    "back",
    "title",
    "accessory",
    "pet",
    "aura",
)


@dataclass(frozen=True, slots=True)
class MappingAEntry:
    """One locked Mapping A identity and its canonical appearance slot."""

    zone: str
    item_id: str
    slot: str


MAPPING_A_CATALOG: Final[tuple[MappingAEntry, ...]] = (
    MappingAEntry("Z1", "back_pack", "back"),
    MappingAEntry("Z2", "hat_cloth", "hat"),
    MappingAEntry("Z3", "hat_bamboo", "hat"),
    MappingAEntry("Z4", "robe_crane", "outfit"),
    MappingAEntry("Z5", "hat_onihorns", "hat"),
    MappingAEntry("Z6", "robe_dragon", "outfit"),
    MappingAEntry("Z7", "acc_dragon_pendant", "accessory"),
    MappingAEntry("Z8", "back_cloak", "back"),
    MappingAEntry("Z9", "hat_dragon_horn", "hat"),
    MappingAEntry("Z10", "hat_celestial_crown", "hat"),
)
MAPPING_A_ID_COUNT: Final[int] = len(MAPPING_A_CATALOG)
MAPPING_A_IDS: Final[tuple[str, ...]] = tuple(
    entry.item_id for entry in MAPPING_A_CATALOG
)
MAPPING_A_BY_ID: Final[Mapping[str, MappingAEntry]] = MappingProxyType(
    {entry.item_id: entry for entry in MAPPING_A_CATALOG}
)


class MappingAWardrobeRuntimeError(ValueError):
    """Stable fail-closed error for an invalid Mapping A authority shape."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class MappingAWardrobeProjection:
    """Detached, render-ready Mapping A records derived from server facts."""

    status: str
    items: tuple[Mapping[str, Any], ...] = ()
    owned_ids: tuple[str, ...] = ()
    selected_ids: tuple[str, ...] = ()
    invalid_item_ids: tuple[str, ...] = ()
    invalid_selected_ids: tuple[str, ...] = ()
    duplicate_item_ids: tuple[str, ...] = ()
    reason_code: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.status == READY

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": MAPPING_A_VERSION,
            "status": self.status,
            "items": [dict(item) for item in self.items],
            "owned_ids": list(self.owned_ids),
            "selected_ids": list(self.selected_ids),
            "invalid_item_ids": list(self.invalid_item_ids),
            "invalid_selected_ids": list(self.invalid_selected_ids),
            "duplicate_item_ids": list(self.duplicate_item_ids),
            "reason_code": self.reason_code,
            "wardrobe_authority": WARDROBE_AUTHORITY,
            "auto_equip": False,
            "combat_power": MAPPING_A_COMBAT_POWER,
        }


def _catalog_values(
    appearance_definitions: (
        Iterable[Mapping[str, Any]]
        | Mapping[str, Mapping[str, Any]]
        | None
    ),
) -> Iterable[Mapping[str, Any]]:
    if appearance_definitions is not None:
        return (
            appearance_definitions.values()
            if isinstance(appearance_definitions, Mapping)
            else appearance_definitions
        )
    try:
        # Lazy import preserves the route-independent boundary and avoids an
        # app import cycle for callers that inject a canonical snapshot.
        from app import APPEARANCE_DEFS
    except Exception as exc:  # pragma: no cover - deployment import failure
        raise MappingAWardrobeRuntimeError(
            "CANONICAL_CATALOG_UNAVAILABLE",
            "canonical appearance catalog is unavailable",
        ) from exc
    return APPEARANCE_DEFS


def validate_mapping_a_catalog(
    appearance_definitions: (
        Iterable[Mapping[str, Any]]
        | Mapping[str, Mapping[str, Any]]
        | None
    ) = None,
) -> Mapping[str, Mapping[str, Any]]:
    """Validate Mapping A against the existing canonical appearance catalog."""

    by_id: dict[str, Mapping[str, Any]] = {}
    for definition in _catalog_values(appearance_definitions):
        if not isinstance(definition, Mapping):
            raise MappingAWardrobeRuntimeError(
                "CANONICAL_CATALOG_INVALID",
                "appearance definitions must be mappings",
            )
        item_id = definition.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise MappingAWardrobeRuntimeError(
                "CANONICAL_CATALOG_INVALID",
                "appearance definitions require a non-empty id",
            )
        item_id = item_id.strip()
        if item_id in by_id:
            raise MappingAWardrobeRuntimeError(
                "CANONICAL_CATALOG_INVALID",
                f"duplicate appearance id: {item_id}",
            )
        by_id[item_id] = definition

    for entry in MAPPING_A_CATALOG:
        definition = by_id.get(entry.item_id)
        if definition is None:
            raise MappingAWardrobeRuntimeError(
                "MAPPING_A_CATALOG_MISSING",
                f"Mapping A item is missing from APPEARANCE_DEFS: {entry.item_id}",
            )
        if definition.get("slot") != entry.slot:
            raise MappingAWardrobeRuntimeError(
                "MAPPING_A_SLOT_MISMATCH",
                f"Mapping A slot mismatch for {entry.item_id}",
            )
    return MappingProxyType(by_id)


def _invalid(
    status: str,
    reason_code: str,
    *,
    invalid_item_ids: Iterable[str] = (),
    invalid_selected_ids: Iterable[str] = (),
    duplicate_item_ids: Iterable[str] = (),
) -> MappingAWardrobeProjection:
    return MappingAWardrobeProjection(
        status=status,
        invalid_item_ids=tuple(sorted(set(invalid_item_ids))),
        invalid_selected_ids=tuple(sorted(set(invalid_selected_ids))),
        duplicate_item_ids=tuple(sorted(set(duplicate_item_ids))),
        reason_code=reason_code,
    )


def _valid_display(
    raw: Mapping[str, Any],
    *,
    item_id: str,
    slot: str,
) -> bool:
    display = raw.get("display")
    return (
        isinstance(display, Mapping)
        and display.get("item_id") == item_id
        and display.get("slot") == slot
        and display.get("presentation_only") is True
    )


def consume_mapping_a_cosmetics(
    cosmetics: Any,
    *,
    appearance_definitions: (
        Iterable[Mapping[str, Any]]
        | Mapping[str, Mapping[str, Any]]
        | None
    ) = None,
) -> MappingAWardrobeProjection:
    """Consume an authoritative B028 cosmetics projection, read-only.

    Non-Mapping-A canonical cosmetics remain available to their existing
    generic consumer.  Unknown IDs, malformed Mapping A records, duplicate
    Mapping A ownership rows, and invalid selected state are excluded from the
    renderable result and return a non-ready projection.
    """

    try:
        catalog = validate_mapping_a_catalog(appearance_definitions)
    except MappingAWardrobeRuntimeError as exc:
        return _invalid(AUTHORITY_UNAVAILABLE, exc.code)

    if not isinstance(cosmetics, Mapping):
        return _invalid(INVALID_STORED_STATE, "COSMETICS_PAYLOAD_NOT_MAPPING")
    if cosmetics.get("authority") != WARDROBE_AUTHORITY:
        return _invalid(INVALID_STORED_STATE, "WARDROBE_AUTHORITY_INVALID")
    if cosmetics.get("gameplay_effects_projected") is not False:
        return _invalid(INVALID_STORED_STATE, "COSMETIC_EFFECT_PROJECTION_FORBIDDEN")

    owned_items = cosmetics.get("owned_items")
    selected = cosmetics.get("selected")
    if not isinstance(owned_items, (list, tuple)):
        return _invalid(INVALID_STORED_STATE, "OWNED_ITEMS_NOT_ARRAY")
    if not isinstance(selected, Mapping):
        return _invalid(INVALID_STORED_STATE, "SELECTED_PROJECTION_NOT_MAPPING")

    canonical_ids = set(catalog)
    owned_mapping_ids: set[str] = set()
    invalid_item_ids: set[str] = set()
    duplicate_item_ids: set[str] = set()
    malformed = False

    for raw in owned_items:
        if not isinstance(raw, Mapping):
            malformed = True
            continue
        item_id = raw.get("item_id")
        if not isinstance(item_id, str) or not item_id.strip():
            malformed = True
            continue
        item_id = item_id.strip()
        if item_id not in canonical_ids:
            invalid_item_ids.add(item_id)
            continue
        entry = MAPPING_A_BY_ID.get(item_id)
        if entry is None:
            continue
        if item_id in owned_mapping_ids:
            duplicate_item_ids.add(item_id)
            continue
        if (
            raw.get("slot") != entry.slot
            or raw.get("presentation_only") is not True
            or raw.get("combat_power_projected") is not False
            or not _valid_display(raw, item_id=item_id, slot=entry.slot)
        ):
            invalid_item_ids.add(item_id)
            continue
        owned_mapping_ids.add(item_id)

    selected_mapping_ids: set[str] = set()
    invalid_selected_ids: set[str] = set()
    selected_seen: set[str] = set()
    for slot, raw in selected.items():
        if slot not in APPEARANCE_SLOTS:
            malformed = True
            continue
        if raw is None:
            continue
        if not isinstance(raw, Mapping):
            malformed = True
            continue
        item_id = raw.get("item_id")
        if not isinstance(item_id, str) or not item_id.strip():
            malformed = True
            continue
        item_id = item_id.strip()
        if item_id not in canonical_ids:
            invalid_selected_ids.add(item_id)
            continue
        entry = MAPPING_A_BY_ID.get(item_id)
        if entry is None:
            continue
        if (
            entry.slot != slot
            or raw.get("owned") is not True
            or raw.get("equipped") is not True
            or raw.get("presentation_only") is not True
            or raw.get("combat_power_projected") is not False
            or not _valid_display(raw, item_id=item_id, slot=entry.slot)
            or item_id not in owned_mapping_ids
        ):
            invalid_selected_ids.add(item_id)
            continue
        if item_id in selected_seen:
            invalid_selected_ids.add(item_id)
            continue
        selected_seen.add(item_id)
        selected_mapping_ids.add(item_id)

    if malformed or invalid_item_ids or invalid_selected_ids or duplicate_item_ids:
        return _invalid(
            INVALID_STORED_STATE,
            "MAPPING_A_PROJECTION_INVALID",
            invalid_item_ids=invalid_item_ids,
            invalid_selected_ids=invalid_selected_ids,
            duplicate_item_ids=duplicate_item_ids,
        )

    items: list[Mapping[str, Any]] = []
    for entry in MAPPING_A_CATALOG:
        if entry.item_id not in owned_mapping_ids:
            continue
        items.append(
            MappingProxyType(
                {
                    "zone": entry.zone,
                    "item_id": entry.item_id,
                    "slot": entry.slot,
                    "owned": True,
                    "equipped": entry.item_id in selected_mapping_ids,
                    "presentation_only": True,
                    "combat_power_projected": False,
                }
            )
        )

    return MappingAWardrobeProjection(
        status=READY,
        items=tuple(items),
        owned_ids=tuple(entry.item_id for entry in MAPPING_A_CATALOG if entry.item_id in owned_mapping_ids),
        selected_ids=tuple(entry.item_id for entry in MAPPING_A_CATALOG if entry.item_id in selected_mapping_ids),
    )


__all__ = [
    "APPEARANCE_SLOTS",
    "AUTHORITY_UNAVAILABLE",
    "INVALID_STORED_STATE",
    "MAPPING_A_BY_ID",
    "MAPPING_A_CATALOG",
    "MAPPING_A_COMBAT_POWER",
    "MAPPING_A_ID_COUNT",
    "MAPPING_A_IDS",
    "MAPPING_A_VERSION",
    "MappingAEntry",
    "MappingAWardrobeProjection",
    "MappingAWardrobeRuntimeError",
    "READY",
    "WARDROBE_AUTHORITY",
    "consume_mapping_a_cosmetics",
    "validate_mapping_a_catalog",
]
