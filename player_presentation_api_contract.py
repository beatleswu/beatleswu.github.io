"""Pure transport contract for the authenticated Player Presentation API V1.

This module deliberately sits *after* the B030 read service.  It validates
and narrows a detached B030/B028-safe projection into an immutable transport
envelope.  It does not open a database connection, issue SQL, authenticate a
caller, calculate gameplay values, or own any Player/Hero state.

Topology::

    B028 canonical read model
        -> B030 read service
        -> future authenticated route
        -> this transport contract
        -> per-surface presentation adapters

The contract removes the B028 ``world`` payload from the transport body and
keeps only explicit exclusion metadata in ``provenance``.  Encounter HP,
combat/effect values, quests, commerce, Premium, badges, analytics, and
public-profile policy are not transport fields.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


PLAYER_PRESENTATION_API_V1 = "PLAYER_PRESENTATION_API_V1"
B030_READ_SERVICE_CONTRACT = "PLAYER_PRESENTATION_READ_CONTRACT_V1"

_B030_SERVICE_KEYS = frozenset(
    {
        "contract_version",
        "status",
        "player_state",
        "warnings",
        "read_only",
        "mutates",
        "display_identity",
    }
)
_B028_STATE_KEYS = frozenset(
    {
        "read_model",
        "read_model_version",
        "projection_status",
        "read_only",
        "mutates",
        "player_id",
        "hero",
        "progression",
        "hp",
        "equipment",
        "spirit",
        "cosmetics",
        "world",
        "provenance",
    }
)
_B028_PROJECTION_STATUSES = frozenset(
    {
        "OK",
        "PARTIAL",
        "OPTIONAL_PROJECTION_UNAVAILABLE",
        "INVALID_STORED_STATE",
        "AUTHORITY_AMBIGUOUS",
        "AUTHORITY_UNAVAILABLE",
    }
)
_SERVICE_STATUSES = frozenset({"OK", "PARTIAL", "INVALID_STATE", "UNAVAILABLE"})
_STATUS_FROM_B028 = {
    "OK": "OK",
    "PARTIAL": "PARTIAL",
    "OPTIONAL_PROJECTION_UNAVAILABLE": "PARTIAL",
    "INVALID_STORED_STATE": "INVALID_STATE",
    "AUTHORITY_AMBIGUOUS": "INVALID_STATE",
    "AUTHORITY_UNAVAILABLE": "UNAVAILABLE",
}

_APPEARANCE_SLOTS = ("outfit", "hat", "back", "title", "accessory", "pet", "aura")
_EQUIPMENT_SLOTS = ("weapon", "armor", "accessory")

_EXCLUDED_AUTHORITIES = {
    "world": {
        "projected": False,
        "authority": "world_progression_system",
    },
    "encounter": {
        "projected": False,
        "authority": "encounter_local_battle_state",
    },
    "quest": {
        "projected": False,
        "authority": "quest_and_reward_settlement_system",
    },
    "shop": {
        "projected": False,
        "authority": "shop_commerce_system",
    },
    "premium": {
        "projected": False,
        "authority": "premium_entitlement_and_payment_system",
    },
    "badges": {
        "projected": False,
        "authority": "achievement_and_badge_system",
    },
    "analytics": {
        "projected": False,
        "authority": "stats_analytics_system",
    },
    "public_profile": {
        "projected": False,
        "authority": "owner_decision_required_public_projection",
    },
}


class PlayerPresentationApiContractError(ValueError):
    """Stable contract-validation failure safe for a future route adapter."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code}


def _fail(code: str, message: str) -> None:
    raise PlayerPresentationApiContractError(code, message)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INVALID_SHAPE", f"{path} must be an object")
    return value


def _reject_unknown(value: Mapping[str, Any], allowed: set[str] | frozenset[str], path: str) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        _fail("UNKNOWN_FIELD", f"{path} contains unsupported field(s): {', '.join(unknown)}")


def _text(value: Any, path: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip():
        _fail("INVALID_VALUE", f"{path} must be a non-empty string")
    return value.strip()


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail("INVALID_VALUE", f"{path} must be a positive integer")
    return value


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail("INVALID_VALUE", f"{path} must be boolean")
    return value


def _nonnegative_or_none(value: Any, path: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("INVALID_VALUE", f"{path} must be a non-negative integer or null")
    return value


def _json_detach(value: Any, path: str = "value") -> Any:
    """Copy only JSON-native values so the envelope cannot retain DB objects."""

    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            _fail("NON_JSON_VALUE", f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_detach(item, f"{path}.{key}") for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_detach(item, f"{path}[]") for item in value]
    _fail("NON_JSON_VALUE", f"{path} contains unsupported type {type(value).__name__}")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _validate_display_identity(value: Any) -> dict[str, Any]:
    data = _mapping(value, "display_identity")
    _reject_unknown(data, {"display_name", "username"}, "display_identity")
    return {
        key: _text(data[key], f"display_identity.{key}", nullable=True)
        for key in ("display_name", "username")
        if key in data
    }


def _validate_hero(value: Any) -> dict[str, Any]:
    data = _mapping(value, "player_state.hero")
    allowed = {
        "hero_id",
        "identity_status",
        "authority",
        "authority_scope",
        "presentation_fallback_id",
        "invalid_stored_value",
    }
    _reject_unknown(data, allowed, "player_state.hero")
    if data.get("authority") != "player_appearance.character_key":
        _fail("AUTHORITY_BOUNDARY", "Hero authority must be player_appearance.character_key")
    if data.get("authority_scope") != "presentation_only":
        _fail("AUTHORITY_BOUNDARY", "Hero authority_scope must be presentation_only")
    result = {}
    for key in allowed:
        if key in data:
            result[key] = _json_detach(data[key], f"player_state.hero.{key}")
    return result


def _validate_progression(value: Any) -> dict[str, Any]:
    data = _mapping(value, "player_state.progression")
    allowed = {
        "projection_status",
        "authority",
        "source_version",
        "xp",
        "rank_level",
        "level",
        "rank_xp",
        "go_rank",
        "total_correct",
        "current_streak",
        "max_streak",
        "invalid_fields",
        "reason",
    }
    _reject_unknown(data, allowed, "player_state.progression")
    if data.get("authority") != "user_stats":
        _fail("AUTHORITY_BOUNDARY", "Progression authority must be user_stats")
    result = dict(data)
    for key in ("xp", "rank_xp", "total_correct", "current_streak", "max_streak", "level"):
        if key in result:
            result[key] = _nonnegative_or_none(result[key], f"player_state.progression.{key}")
    for key in ("rank_level", "go_rank"):
        if key in result and result[key] is not None:
            result[key] = _text(result[key], f"player_state.progression.{key}", nullable=True)
    return _json_detach(result, "progression")


def _validate_persistent_hp(value: Any) -> dict[str, Any]:
    data = _mapping(value, "player_state.hp")
    allowed = {
        "projection_status",
        "authority",
        "scope",
        "persistent_player_hp",
        "persistent_player_max_hp",
        "encounter_hp",
        "invalid_fields",
    }
    _reject_unknown(data, allowed, "player_state.hp")
    if data.get("authority") != "user_stats":
        _fail("AUTHORITY_BOUNDARY", "Persistent HP authority must be user_stats")
    if "encounter_hp" in data:
        boundary = _mapping(data["encounter_hp"], "player_state.hp.encounter_hp")
        _reject_unknown(boundary, {"projected", "authority", "reason"}, "player_state.hp.encounter_hp")
        if boundary.get("projected") is not False:
            _fail("FORBIDDEN_FIELD", "active encounter HP cannot enter Player Presentation")
        if boundary.get("authority") != "encounter_local_battle_state":
            _fail("AUTHORITY_BOUNDARY", "encounter HP authority is invalid")
    persistent_hp = {
        key: data.get(key)
        for key in ("persistent_player_hp", "persistent_player_max_hp")
    }
    persistent_hp["authority"] = data.get("authority")
    persistent_hp["scope"] = "persistent_player_state"
    for key in ("persistent_player_hp", "persistent_player_max_hp"):
        persistent_hp[key] = _nonnegative_or_none(persistent_hp[key], f"player_state.hp.{key}")
    return _json_detach(persistent_hp, "persistent_hp")


def _validate_display(value: Any, path: str) -> dict[str, Any] | None:
    if value is None:
        return None
    data = _mapping(value, path)
    allowed = {"item_id", "name", "slot", "rarity", "icon", "definition_ref", "presentation_only"}
    _reject_unknown(data, allowed, path)
    return _json_detach(dict(data), path)


def _validate_equipment(value: Any) -> dict[str, Any]:
    data = _mapping(value, "player_state.equipment")
    allowed = {
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
    _reject_unknown(data, allowed, "player_state.equipment")
    if data.get("authority") != "player_inventory":
        _fail("AUTHORITY_BOUNDARY", "Equipment authority must be player_inventory")
    if data.get("combat_stats_projected") is not False:
        _fail("FORBIDDEN_FIELD", "equipment combat stats are not part of this contract")
    if "slots" in data:
        slots = _mapping(data["slots"], "player_state.equipment.slots")
        _reject_unknown(slots, set(_EQUIPMENT_SLOTS), "player_state.equipment.slots")
        for slot, raw in slots.items():
            entry = _mapping(raw, f"player_state.equipment.slots.{slot}")
            _reject_unknown(
                entry,
                {"slot", "item_id", "owned", "equipped", "quantity", "functional_status", "display"},
                f"player_state.equipment.slots.{slot}",
            )
            if entry.get("equipped") is True and entry.get("owned") is not True:
                _fail("INVALID_STATE", f"equipped equipment is not owned: {slot}")
            _validate_display(entry.get("display"), f"player_state.equipment.slots.{slot}.display")
    if "owned_items" in data:
        items = data["owned_items"]
        if not isinstance(items, (list, tuple)):
            _fail("INVALID_SHAPE", "player_state.equipment.owned_items must be an array")
        for index, raw in enumerate(items):
            item = _mapping(raw, f"player_state.equipment.owned_items[{index}]")
            _reject_unknown(
                item,
                {"item_id", "slot", "quantity", "equipped", "functional_status", "display", "combat_power_projected"},
                f"player_state.equipment.owned_items[{index}]",
            )
            if item.get("combat_power_projected") is not False:
                _fail("FORBIDDEN_FIELD", "equipment combat power is not part of this contract")
            _validate_display(item.get("display"), f"player_state.equipment.owned_items[{index}].display")
    result = _json_detach(dict(data), "equipment")
    result.pop("combat_stats_projected", None)
    result["combat_stats_projected"] = False
    return result


def _validate_spirit(value: Any) -> dict[str, Any]:
    data = _mapping(value, "player_state.spirit")
    allowed = {
        "projection_status",
        "authority",
        "source_version",
        "active",
        "single_active_spirit",
        "combat_effects_projected",
    }
    _reject_unknown(data, allowed, "player_state.spirit")
    if data.get("authority") != "pet_collection_and_user_pets":
        _fail("AUTHORITY_BOUNDARY", "Spirit authority is invalid")
    if data.get("single_active_spirit") is not True:
        _fail("AUTHORITY_BOUNDARY", "Player Presentation requires one active Spirit projection")
    if data.get("combat_effects_projected", False) is not False:
        _fail("FORBIDDEN_FIELD", "Spirit combat effects are not part of this contract")
    if data.get("active") is not None:
        active = _mapping(data["active"], "player_state.spirit.active")
        _reject_unknown(
            active,
            {"spirit_id", "enabled", "ownership_validated", "evolution_stage", "progression_level", "authority"},
            "player_state.spirit.active",
        )
        if active.get("authority") != "server_b022_d008_active_spirit_projection":
            _fail("AUTHORITY_BOUNDARY", "active Spirit authority is invalid")
    result = _json_detach(dict(data), "spirit")
    result.pop("combat_effects_projected", None)
    result["combat_effects_projected"] = False
    return result


def _validate_cosmetics(value: Any) -> dict[str, Any]:
    data = _mapping(value, "player_state.cosmetics")
    allowed = {
        "projection_status",
        "authority",
        "source_version",
        "selected",
        "owned_items",
        "invalid_item_ids",
        "invalid_selected_ids",
        "gameplay_effects_projected",
    }
    _reject_unknown(data, allowed, "player_state.cosmetics")
    if data.get("authority") != "player_wardrobe_and_player_appearance":
        _fail("AUTHORITY_BOUNDARY", "Cosmetic authority is invalid")
    if data.get("gameplay_effects_projected", False) is not False:
        _fail("FORBIDDEN_FIELD", "cosmetic gameplay effects are not part of this contract")
    if "selected" in data:
        selected = _mapping(data["selected"], "player_state.cosmetics.selected")
        _reject_unknown(selected, set(_APPEARANCE_SLOTS), "player_state.cosmetics.selected")
        for slot, raw in selected.items():
            if raw is None:
                continue
            entry = _mapping(raw, f"player_state.cosmetics.selected.{slot}")
            _reject_unknown(
                entry,
                {"item_id", "owned", "equipped", "display", "presentation_only", "combat_power_projected"},
                f"player_state.cosmetics.selected.{slot}",
            )
            if entry.get("presentation_only") is not True or entry.get("combat_power_projected") is not False:
                _fail("FORBIDDEN_FIELD", "selected cosmetic is not presentation-only")
            _validate_display(entry.get("display"), f"player_state.cosmetics.selected.{slot}.display")
    if "owned_items" in data:
        items = data["owned_items"]
        if not isinstance(items, (list, tuple)):
            _fail("INVALID_SHAPE", "player_state.cosmetics.owned_items must be an array")
        for index, raw in enumerate(items):
            item = _mapping(raw, f"player_state.cosmetics.owned_items[{index}]")
            _reject_unknown(
                item,
                {"item_id", "slot", "display", "obtained_at", "source", "presentation_only", "combat_power_projected"},
                f"player_state.cosmetics.owned_items[{index}]",
            )
            if item.get("presentation_only") is not True or item.get("combat_power_projected") is not False:
                _fail("FORBIDDEN_FIELD", "owned cosmetic is not presentation-only")
            _validate_display(item.get("display"), f"player_state.cosmetics.owned_items[{index}].display")
    result = _json_detach(dict(data), "cosmetics")
    result.pop("gameplay_effects_projected", None)
    result["gameplay_effects_projected"] = False
    return result


def _validate_b028_state(value: Any) -> tuple[int, str, dict[str, Any]]:
    state = _mapping(value, "player_state")
    _reject_unknown(state, _B028_STATE_KEYS, "player_state")
    if state.get("read_model") != "player_hero_state":
        _fail("INVALID_CONTRACT", "player_state is not the B028 player_hero_state model")
    if state.get("read_model_version") != "player_hero_state_v1":
        _fail("INVALID_CONTRACT", "unsupported B028 player_hero_state version")
    raw_projection_status = state.get("projection_status")
    if raw_projection_status not in _B028_PROJECTION_STATUSES:
        _fail("INVALID_VALUE", "unsupported B028 projection status")
    if state.get("read_only") is not True or state.get("mutates") is not False:
        _fail("AUTHORITY_BOUNDARY", "B028 player state must be read-only and non-mutating")
    player_id = _positive_int(state.get("player_id"), "player_state.player_id")

    world = _mapping(state.get("world"), "player_state.world")
    _reject_unknown(
        world,
        {"projected", "authority", "selected_zone_is_not_player_progression", "reason"},
        "player_state.world",
    )
    if world.get("projected") is not False or world.get("authority") != "world_progression_system":
        _fail("FORBIDDEN_FIELD", "World progression cannot enter Player Presentation")

    hero = _validate_hero(state.get("hero"))
    progression = _validate_progression(state.get("progression"))
    persistent_hp = _validate_persistent_hp(state.get("hp"))
    equipment = _validate_equipment(state.get("equipment"))
    spirit = _validate_spirit(state.get("spirit"))
    cosmetics = _validate_cosmetics(state.get("cosmetics"))
    provenance = _mapping(state.get("provenance"), "player_state.provenance")

    source_groups = {}
    for group in ("player", "hero", "progression", "hp", "equipment", "spirit", "cosmetics"):
        raw_group = provenance.get(group)
        if isinstance(raw_group, Mapping):
            group_copy = {}
            for key in ("authority", "scope", "source_version", "projection_status"):
                if key in raw_group:
                    group_copy[key] = _json_detach(raw_group[key], f"player_state.provenance.{group}.{key}")
            source_groups[group] = group_copy

    source_projection = {
        "read_model": state["read_model"],
        "read_model_version": state["read_model_version"],
        "projection_status": raw_projection_status,
        "groups": source_groups,
        "excluded_authorities": _EXCLUDED_AUTHORITIES,
    }
    output_state = {
        "hero": hero,
        "progression": progression,
        "persistent_hp": persistent_hp,
        "equipment": equipment,
        "spirit": spirit,
        "cosmetics": cosmetics,
        "provenance": source_projection,
    }
    return player_id, raw_projection_status, _json_detach(output_state, "transport")


@dataclass(frozen=True, slots=True)
class PlayerPresentationApiV1:
    """Immutable, JSON-serializable Player Presentation transport envelope."""

    contract_version: str
    player_id: int
    projection_status: str
    hero: Mapping[str, Any]
    progression: Mapping[str, Any]
    persistent_hp: Mapping[str, Any]
    equipment: Mapping[str, Any]
    spirit: Mapping[str, Any]
    cosmetics: Mapping[str, Any]
    provenance: Mapping[str, Any]
    display_identity: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a detached plain-object copy for a route serializer."""

        result: dict[str, Any] = {
            "contract_version": self.contract_version,
            "player_id": self.player_id,
            "projection_status": self.projection_status,
            "hero": _thaw(self.hero),
            "progression": _thaw(self.progression),
            "persistent_hp": _thaw(self.persistent_hp),
            "equipment": _thaw(self.equipment),
            "spirit": _thaw(self.spirit),
            "cosmetics": _thaw(self.cosmetics),
            "provenance": _thaw(self.provenance),
        }
        if self.display_identity is not None:
            result["display_identity"] = _thaw(self.display_identity)
        return result


def build_player_presentation_api_v1(service_result: Mapping[str, Any]) -> PlayerPresentationApiV1:
    """Validate a B030 result and create the A025 transport envelope.

    The function is intentionally input-only.  It receives a detached B030
    result, invokes no B028/B030 code, performs no database work, and creates
    no ownership or gameplay state.
    """

    service = _mapping(service_result, "service_result")
    _reject_unknown(service, _B030_SERVICE_KEYS, "service_result")
    if service.get("contract_version") != B030_READ_SERVICE_CONTRACT:
        _fail("INVALID_CONTRACT", "input must be the B030 read-service envelope")
    service_status = service.get("status")
    if service_status not in _SERVICE_STATUSES:
        _fail("INVALID_VALUE", "unsupported B030 service status")
    if service.get("read_only") is not True or service.get("mutates") is not False:
        _fail("AUTHORITY_BOUNDARY", "B030 service result must be read-only and non-mutating")
    warnings = service.get("warnings", [])
    if not isinstance(warnings, (list, tuple)):
        _fail("INVALID_SHAPE", "service_result.warnings must be an array")
    player_id, raw_projection_status, output = _validate_b028_state(service.get("player_state"))
    if _STATUS_FROM_B028[raw_projection_status] != service_status:
        _fail("STATUS_MISMATCH", "B030 status does not match B028 projection status")

    display_identity = None
    if service.get("display_identity") is not None:
        display_identity = _validate_display_identity(service["display_identity"])

    return PlayerPresentationApiV1(
        contract_version=PLAYER_PRESENTATION_API_V1,
        player_id=player_id,
        projection_status=service_status,
        hero=_freeze(output["hero"]),
        progression=_freeze(output["progression"]),
        persistent_hp=_freeze(output["persistent_hp"]),
        equipment=_freeze(output["equipment"]),
        spirit=_freeze(output["spirit"]),
        cosmetics=_freeze(output["cosmetics"]),
        provenance=_freeze(output["provenance"]),
        display_identity=_freeze(display_identity) if display_identity is not None else None,
    )


def serialize_player_presentation_api_v1(envelope: PlayerPresentationApiV1) -> str:
    """Serialize an envelope with deterministic key order and JSON syntax."""

    if not isinstance(envelope, PlayerPresentationApiV1):
        _fail("INVALID_SHAPE", "serialize expects PlayerPresentationApiV1")
    try:
        return json.dumps(
            envelope.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise PlayerPresentationApiContractError(
            "NON_JSON_VALUE",
            "Player Presentation envelope is not JSON serializable",
        ) from exc


__all__ = [
    "B030_READ_SERVICE_CONTRACT",
    "PLAYER_PRESENTATION_API_V1",
    "PlayerPresentationApiContractError",
    "PlayerPresentationApiV1",
    "build_player_presentation_api_v1",
    "serialize_player_presentation_api_v1",
]
