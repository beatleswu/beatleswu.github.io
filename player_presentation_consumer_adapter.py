"""Pure consumer adapter for ``PLAYER_PRESENTATION_API_V1``.

This module is deliberately downstream of A025.  It turns an already
validated Player Presentation transport snapshot into a small immutable view
model for future Hero, Adventure, Backpack, and related presentation
surfaces.  It does not call a route, open a database connection, issue API
requests, mutate storage, or calculate gameplay values.

The adapter narrows the transport again at the consumer boundary:

    PLAYER_PRESENTATION_API_V1 -> PLAYER_PRESENTATION_VIEW_MODEL_V1

The result contains only presentation-safe identity, progression, persistent
HP, equipment display state, one active Spirit presentation, and pure
cosmetic display state.  Learning/SRS facts, World, Quest, commerce,
encounter state, and combat/effect fields fail closed or are omitted from the
view model.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from player_presentation_api_contract import (
    PLAYER_PRESENTATION_API_V1,
    PlayerPresentationApiV1,
)


PLAYER_PRESENTATION_VIEW_MODEL_V1 = "PLAYER_PRESENTATION_VIEW_MODEL_V1"

_PROJECTION_STATUSES = frozenset({"OK", "PARTIAL", "INVALID_STATE", "UNAVAILABLE"})
_INPUT_KEYS = frozenset(
    {
        "contract_version",
        "player_id",
        "projection_status",
        "display_identity",
        "hero",
        "progression",
        "persistent_hp",
        "equipment",
        "spirit",
        "cosmetics",
        "provenance",
    }
)
_PROGRESSION_KEYS = frozenset(
    {
        "projection_status",
        "authority",
        "source_version",
        "xp",
        "rank_level",
        "level",
        "rank_xp",
        "go_rank",
        "invalid_fields",
        "reason",
    }
)
_PROGRESSION_FORBIDDEN_KEYS = frozenset(
    {
        "total_correct",
        "current_streak",
        "max_streak",
        "learning_stats",
        "engagement_streak",
        "correct_count",
    }
)
_HERO_KEYS = frozenset(
    {
        "hero_id",
        "identity_status",
        "authority",
        "authority_scope",
        "presentation_fallback_id",
        "invalid_stored_value",
    }
)
_DISPLAY_KEYS = frozenset(
    {"item_id", "name", "slot", "rarity", "icon", "definition_ref", "presentation_only"}
)
_EQUIPMENT_KEYS = frozenset(
    {
        "projection_status",
        "authority",
        "source_version",
        "slots",
        "owned_items",
        "invalid_item_ids",
        "equipped_slot_conflicts",
        "invalid_rows",
        "combat_stats_projected",
    }
)
_EQUIPMENT_ENTRY_KEYS = frozenset(
    {"slot", "item_id", "owned", "equipped", "quantity", "functional_status", "display"}
)
_EQUIPMENT_ITEM_KEYS = frozenset(
    _EQUIPMENT_ENTRY_KEYS | {"combat_power_projected"}
)
_EQUIPMENT_SLOTS = frozenset({"weapon", "armor", "accessory"})
_SPIRIT_KEYS = frozenset(
    {
        "projection_status",
        "authority",
        "source_version",
        "active",
        "single_active_spirit",
        "combat_effects_projected",
    }
)
_SPIRIT_ACTIVE_KEYS = frozenset(
    {"spirit_id", "enabled", "ownership_validated", "evolution_stage", "progression_level", "authority"}
)
_COSMETIC_KEYS = frozenset(
    {
        "projection_status",
        "authority",
        "source_version",
        "selected",
        "owned_items",
        "invalid_item_ids",
        "invalid_selected_ids",
        "gameplay_effects_projected",
    }
)
_APPEARANCE_SLOTS = frozenset({"outfit", "hat", "back", "title", "accessory", "pet", "aura"})
_SELECTED_COSMETIC_KEYS = frozenset(
    {"item_id", "owned", "equipped", "display", "presentation_only", "combat_power_projected"}
)
_OWNED_COSMETIC_KEYS = frozenset(
    {"item_id", "slot", "display", "obtained_at", "source", "presentation_only", "combat_power_projected"}
)
_PROVENANCE_KEYS = frozenset(
    {"read_model", "read_model_version", "projection_status", "groups", "excluded_authorities"}
)


class PlayerPresentationConsumerAdapterError(ValueError):
    """Raised when a transport snapshot cannot be safely consumed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def _fail(code: str, message: str) -> None:
    raise PlayerPresentationConsumerAdapterError(code, message)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INVALID_SHAPE", f"{path} must be an object")
    return value


def _reject_unknown(value: Mapping[str, Any], allowed: frozenset[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        _fail("FORBIDDEN_FIELD", f"{path} contains unsupported fields: {', '.join(unknown)}")


def _copy_json(value: Any, path: str) -> Any:
    """Copy JSON-compatible data without retaining references to input."""

    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("INVALID_SHAPE", f"{path} object keys must be strings")
            result[key] = _copy_json(item, f"{path}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [_copy_json(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("NON_JSON_VALUE", f"{path} contains a non-finite number")
        return value
    _fail("NON_JSON_VALUE", f"{path} contains an unsupported value")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail("INVALID_VALUE", f"{path} must be a positive integer")
    return value


def _nonnegative_int(value: Any, path: str, *, nullable: bool = False) -> int | None:
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("INVALID_VALUE", f"{path} must be a non-negative integer")
    return value


def _text(value: Any, path: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str):
        _fail("INVALID_VALUE", f"{path} must be text")
    return value


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail("INVALID_VALUE", f"{path} must be boolean")
    return value


def _optional_boolean(value: Any, path: str) -> bool | None:
    if value is None:
        return None
    return _boolean(value, path)


def _adapt_display(value: Any, path: str) -> dict[str, Any] | None:
    if value is None:
        return None
    data = _mapping(value, path)
    _reject_unknown(data, _DISPLAY_KEYS, path)
    return _copy_json(data, path)


def _adapt_identity(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    data = _mapping(value, "snapshot.display_identity")
    _reject_unknown(data, frozenset({"display_name", "username"}), "snapshot.display_identity")
    return _copy_json(data, "snapshot.display_identity")


def _adapt_hero(value: Any) -> dict[str, Any]:
    data = _mapping(value, "snapshot.hero")
    _reject_unknown(data, _HERO_KEYS, "snapshot.hero")
    if data.get("authority") != "player_appearance.character_key":
        _fail("AUTHORITY_BOUNDARY", "Hero authority must be player_appearance.character_key")
    if data.get("authority_scope") != "presentation_only":
        _fail("AUTHORITY_BOUNDARY", "Hero authority_scope must be presentation_only")
    result: dict[str, Any] = {}
    for key in ("hero_id", "identity_status", "presentation_fallback_id", "invalid_stored_value"):
        if key in data:
            result[key] = _copy_json(data[key], f"snapshot.hero.{key}")
    return result


def _adapt_progression(value: Any) -> dict[str, Any]:
    data = _mapping(value, "snapshot.progression")
    _reject_unknown(data, _PROGRESSION_KEYS, "snapshot.progression")
    if _PROGRESSION_FORBIDDEN_KEYS & set(data):
        _fail("FORBIDDEN_FIELD", "Learning/SRS and streak state are not presentation fields")
    if data.get("authority") != "user_stats":
        _fail("AUTHORITY_BOUNDARY", "Progression authority must be user_stats")
    result: dict[str, Any] = {}
    for key in ("projection_status", "invalid_fields", "reason"):
        if key in data:
            result[key] = _copy_json(data[key], f"snapshot.progression.{key}")
    for key in ("xp", "level", "rank_xp"):
        if key in data:
            result[key] = _nonnegative_int(data[key], f"snapshot.progression.{key}")
    for key in ("rank_level", "go_rank"):
        if key in data:
            result[key] = _text(data[key], f"snapshot.progression.{key}", nullable=True)
    return result


def _adapt_persistent_hp(value: Any) -> dict[str, Any]:
    data = _mapping(value, "snapshot.persistent_hp")
    allowed = frozenset({"persistent_player_hp", "persistent_player_max_hp", "authority", "scope"})
    _reject_unknown(data, allowed, "snapshot.persistent_hp")
    if data.get("authority") != "user_stats":
        _fail("AUTHORITY_BOUNDARY", "persistent HP authority must be user_stats")
    result: dict[str, Any] = {}
    for key in ("persistent_player_hp", "persistent_player_max_hp"):
        if key in data:
            result[key] = _nonnegative_int(data[key], f"snapshot.persistent_hp.{key}", nullable=True)
    if data.get("scope") != "persistent_player_state":
        _fail("AUTHORITY_BOUNDARY", "persistent HP scope is invalid")
    result["scope"] = "persistent_player_state"
    return result


def _adapt_equipment_entry(value: Any, path: str) -> dict[str, Any]:
    data = _mapping(value, path)
    _reject_unknown(data, _EQUIPMENT_ENTRY_KEYS, path)
    if data.get("equipped") is True and data.get("owned") is not True:
        _fail("INVALID_STATE", f"{path} cannot be equipped without ownership")
    result: dict[str, Any] = {}
    for key in ("slot", "item_id", "functional_status"):
        if key in data:
            result[key] = _copy_json(data[key], f"{path}.{key}")
    for key in ("owned", "equipped"):
        if key in data:
            result[key] = _boolean(data[key], f"{path}.{key}")
    if "quantity" in data:
        result["quantity"] = _nonnegative_int(data["quantity"], f"{path}.quantity")
    if "display" in data:
        result["display"] = _adapt_display(data["display"], f"{path}.display")
    return result


def _adapt_equipment_item(value: Any, path: str) -> dict[str, Any]:
    data = _mapping(value, path)
    _reject_unknown(data, _EQUIPMENT_ITEM_KEYS, path)
    if data.get("combat_power_projected") not in (None, False):
        _fail("FORBIDDEN_FIELD", "equipment combat power is not presentation state")
    return _adapt_equipment_entry(
        {key: item for key, item in data.items() if key != "combat_power_projected"},
        path,
    )


def _adapt_equipment(value: Any) -> dict[str, Any]:
    data = _mapping(value, "snapshot.equipment")
    _reject_unknown(data, _EQUIPMENT_KEYS, "snapshot.equipment")
    if data.get("authority") != "player_inventory":
        _fail("AUTHORITY_BOUNDARY", "equipment authority must be player_inventory")
    if data.get("combat_stats_projected") not in (None, False):
        _fail("FORBIDDEN_FIELD", "equipment combat stats are not presentation state")
    result: dict[str, Any] = {}
    if "projection_status" in data:
        result["projection_status"] = _copy_json(data["projection_status"], "snapshot.equipment.projection_status")
    if "slots" in data:
        slots = _mapping(data["slots"], "snapshot.equipment.slots")
        _reject_unknown(slots, _EQUIPMENT_SLOTS, "snapshot.equipment.slots")
        result["slots"] = {
            slot: _adapt_equipment_entry(raw, f"snapshot.equipment.slots.{slot}")
            for slot, raw in slots.items()
        }
    if "owned_items" in data:
        items = data["owned_items"]
        if not isinstance(items, (list, tuple)):
            _fail("INVALID_SHAPE", "snapshot.equipment.owned_items must be an array")
        result["owned_items"] = [
            _adapt_equipment_item(raw, f"snapshot.equipment.owned_items[{index}]")
            for index, raw in enumerate(items)
        ]
    for key in ("invalid_item_ids", "equipped_slot_conflicts", "invalid_rows"):
        if key in data:
            result[key] = _copy_json(data[key], f"snapshot.equipment.{key}")
    return result


def _adapt_spirit_active(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    data = _mapping(value, "snapshot.spirit.active")
    _reject_unknown(data, _SPIRIT_ACTIVE_KEYS, "snapshot.spirit.active")
    result: dict[str, Any] = {}
    for key in ("spirit_id", "evolution_stage"):
        if key in data:
            result[key] = _text(data[key], f"snapshot.spirit.active.{key}")
    for key in ("enabled", "ownership_validated"):
        if key in data:
            result[key] = _boolean(data[key], f"snapshot.spirit.active.{key}")
    if "progression_level" in data:
        result["progression_level"] = _nonnegative_int(data["progression_level"], "snapshot.spirit.active.progression_level")
    return result


def _adapt_spirit(value: Any) -> dict[str, Any]:
    data = _mapping(value, "snapshot.spirit")
    _reject_unknown(data, _SPIRIT_KEYS, "snapshot.spirit")
    if data.get("authority") != "pet_collection_and_user_pets":
        _fail("AUTHORITY_BOUNDARY", "Spirit authority is invalid")
    if data.get("combat_effects_projected") not in (None, False):
        _fail("FORBIDDEN_FIELD", "Spirit combat effects are not presentation state")
    if data.get("single_active_spirit") is not True:
        _fail("AUTHORITY_BOUNDARY", "Spirit view requires one active Spirit projection")
    result: dict[str, Any] = {"single_active_spirit": True}
    if "projection_status" in data:
        result["projection_status"] = _copy_json(data["projection_status"], "snapshot.spirit.projection_status")
    if "active" in data:
        result["active"] = _adapt_spirit_active(data["active"])
    return result


def _adapt_selected_cosmetic(value: Any, path: str) -> dict[str, Any]:
    data = _mapping(value, path)
    _reject_unknown(data, _SELECTED_COSMETIC_KEYS, path)
    if data.get("presentation_only") is not True or data.get("combat_power_projected") not in (None, False):
        _fail("FORBIDDEN_FIELD", "selected cosmetic is not pure presentation state")
    result: dict[str, Any] = {}
    for key in ("item_id", "display"):
        if key in data:
            result[key] = _adapt_display(data[key], f"{path}.{key}") if key == "display" else _copy_json(data[key], f"{path}.{key}")
    for key in ("owned", "equipped", "presentation_only"):
        if key in data:
            result[key] = _boolean(data[key], f"{path}.{key}")
    return result


def _adapt_owned_cosmetic(value: Any, path: str) -> dict[str, Any]:
    data = _mapping(value, path)
    _reject_unknown(data, _OWNED_COSMETIC_KEYS, path)
    if data.get("presentation_only") is not True or data.get("combat_power_projected") not in (None, False):
        _fail("FORBIDDEN_FIELD", "owned cosmetic is not pure presentation state")
    result: dict[str, Any] = {}
    for key in ("item_id", "slot", "obtained_at", "source"):
        if key in data:
            result[key] = _copy_json(data[key], f"{path}.{key}")
    if "display" in data:
        result["display"] = _adapt_display(data["display"], f"{path}.display")
    result["presentation_only"] = True
    return result


def _adapt_cosmetics(value: Any) -> dict[str, Any]:
    data = _mapping(value, "snapshot.cosmetics")
    _reject_unknown(data, _COSMETIC_KEYS, "snapshot.cosmetics")
    if data.get("authority") != "player_wardrobe_and_player_appearance":
        _fail("AUTHORITY_BOUNDARY", "cosmetic authority is invalid")
    if data.get("gameplay_effects_projected") not in (None, False):
        _fail("FORBIDDEN_FIELD", "cosmetic gameplay effects are not presentation state")
    result: dict[str, Any] = {}
    if "projection_status" in data:
        result["projection_status"] = _copy_json(data["projection_status"], "snapshot.cosmetics.projection_status")
    if "selected" in data:
        selected = _mapping(data["selected"], "snapshot.cosmetics.selected")
        _reject_unknown(selected, _APPEARANCE_SLOTS, "snapshot.cosmetics.selected")
        result["selected"] = {
            slot: None if raw is None else _adapt_selected_cosmetic(raw, f"snapshot.cosmetics.selected.{slot}")
            for slot, raw in selected.items()
        }
    if "owned_items" in data:
        items = data["owned_items"]
        if not isinstance(items, (list, tuple)):
            _fail("INVALID_SHAPE", "snapshot.cosmetics.owned_items must be an array")
        result["owned_items"] = [
            _adapt_owned_cosmetic(raw, f"snapshot.cosmetics.owned_items[{index}]")
            for index, raw in enumerate(items)
        ]
    for key in ("invalid_item_ids", "invalid_selected_ids"):
        if key in data:
            result[key] = _copy_json(data[key], f"snapshot.cosmetics.{key}")
    return result


def _validate_provenance(value: Any) -> None:
    data = _mapping(value, "snapshot.provenance")
    _reject_unknown(data, _PROVENANCE_KEYS, "snapshot.provenance")


@dataclass(frozen=True, slots=True)
class PlayerPresentationViewModelV1:
    """Immutable presentation-only consumer view model."""

    view_model_version: str
    contract_version: str
    projection_status: str
    player_id: int
    hero: Mapping[str, Any]
    progression: Mapping[str, Any]
    persistent_hp: Mapping[str, Any]
    equipment: Mapping[str, Any]
    spirit: Mapping[str, Any]
    cosmetics: Mapping[str, Any]
    display_identity: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "view_model_version": self.view_model_version,
            "contract_version": self.contract_version,
            "projection_status": self.projection_status,
            "player_id": self.player_id,
            "hero": _thaw(self.hero),
            "progression": _thaw(self.progression),
            "persistent_hp": _thaw(self.persistent_hp),
            "equipment": _thaw(self.equipment),
            "spirit": _thaw(self.spirit),
            "cosmetics": _thaw(self.cosmetics),
        }
        if self.display_identity is not None:
            result["display_identity"] = _thaw(self.display_identity)
        return result


def build_player_presentation_view_model(
    snapshot: PlayerPresentationApiV1 | Mapping[str, Any],
) -> PlayerPresentationViewModelV1:
    """Build a deterministic presentation-only view model from A025 output."""

    if isinstance(snapshot, PlayerPresentationApiV1):
        data = snapshot.to_dict()
    else:
        raw = _mapping(snapshot, "snapshot")
        data = _copy_json(raw, "snapshot")
    _reject_unknown(data, _INPUT_KEYS, "snapshot")
    if data.get("contract_version") != PLAYER_PRESENTATION_API_V1:
        _fail("INVALID_CONTRACT", "input must be PLAYER_PRESENTATION_API_V1")
    if data.get("projection_status") not in _PROJECTION_STATUSES:
        _fail("INVALID_VALUE", "unsupported Player Presentation projection status")
    player_id = _positive_int(data.get("player_id"), "snapshot.player_id")
    _validate_provenance(data.get("provenance"))

    view_model = {
        "view_model_version": PLAYER_PRESENTATION_VIEW_MODEL_V1,
        "contract_version": PLAYER_PRESENTATION_API_V1,
        "projection_status": data["projection_status"],
        "player_id": player_id,
        "hero": _adapt_hero(data.get("hero")),
        "progression": _adapt_progression(data.get("progression")),
        "persistent_hp": _adapt_persistent_hp(data.get("persistent_hp")),
        "equipment": _adapt_equipment(data.get("equipment")),
        "spirit": _adapt_spirit(data.get("spirit")),
        "cosmetics": _adapt_cosmetics(data.get("cosmetics")),
    }
    display_identity = _adapt_identity(data.get("display_identity"))
    if display_identity is not None:
        view_model["display_identity"] = display_identity
    return PlayerPresentationViewModelV1(
        view_model_version=PLAYER_PRESENTATION_VIEW_MODEL_V1,
        contract_version=PLAYER_PRESENTATION_API_V1,
        projection_status=data["projection_status"],
        player_id=player_id,
        hero=_freeze(view_model["hero"]),
        progression=_freeze(view_model["progression"]),
        persistent_hp=_freeze(view_model["persistent_hp"]),
        equipment=_freeze(view_model["equipment"]),
        spirit=_freeze(view_model["spirit"]),
        cosmetics=_freeze(view_model["cosmetics"]),
        display_identity=_freeze(display_identity) if display_identity is not None else None,
    )


def serialize_player_presentation_view_model(view_model: PlayerPresentationViewModelV1) -> str:
    """Serialize the view model deterministically without side effects."""

    if not isinstance(view_model, PlayerPresentationViewModelV1):
        _fail("INVALID_SHAPE", "serialize expects PlayerPresentationViewModelV1")
    try:
        return json.dumps(
            view_model.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise PlayerPresentationConsumerAdapterError(
            "NON_JSON_VALUE", "Player Presentation view model is not JSON serializable"
        ) from exc


__all__ = [
    "PLAYER_PRESENTATION_API_V1",
    "PLAYER_PRESENTATION_VIEW_MODEL_V1",
    "PlayerPresentationConsumerAdapterError",
    "PlayerPresentationViewModelV1",
    "build_player_presentation_view_model",
    "serialize_player_presentation_view_model",
]
