"""Canonical, read-only Player/Hero state projection.

This module deliberately does not own any player state.  It reads the
existing authorities and returns one deterministic projection for a later
API or UI consumer:

* ``user_stats`` remains the XP, level representation, and legacy/global HP
  authority.
* ``player_inventory`` remains equipment ownership/equipped-state authority.
* ``pet_collection`` plus the ``user_pets`` active projection remains Spirit
  authority (via :mod:`spirit_runtime`).
* ``player_wardrobe`` and ``player_appearance`` remain presentation ownership
  and selection authorities.

The default catalog/projection adapters import the existing runtime modules
only when the public builder is called.  That keeps this module import-safe
and avoids a second catalog or combat implementation.  Callers may inject
the adapters in isolated tests, but production callers should use the
defaults so the existing authorities stay the source of truth.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from mapping_a_wardrobe_runtime import (
    MAPPING_A_IDS,
    consume_mapping_a_cosmetics,
)


READ_MODEL_NAME = "player_hero_state"
READ_MODEL_VERSION = "player_hero_state_v1"
EQUIPMENT_SLOTS = ("weapon", "armor", "accessory")
APPEARANCE_SLOTS = ("outfit", "hat", "back", "title", "accessory", "pet", "aura")
PRESENTATION_DEFAULT_HERO_ID = "apprentice"
XP_AMULET_ID = "xp_amulet"
INVENTORY_ONLY_TROPHY_IDS = frozenset({"go_stone_black"})


class PlayerStateReadModelError(RuntimeError):
    """Structured failure for the read-model boundary."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _row_keys(row: Any) -> set[str]:
    if row is None:
        return set()
    try:
        return {str(key) for key in row.keys()}
    except AttributeError:
        return set()


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    keys = _row_keys(row)
    if keys and key not in keys:
        return default
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _missing_sqlite_relation(exc: Exception) -> bool:
    """Recognise only SQLite's optional-fixture missing-table error.

    A missing PostgreSQL relation aborts the caller's transaction and must
    remain an authority-availability failure.  We therefore only downgrade
    the intentionally sparse SQLite fixtures used by read-model tests.
    """

    return isinstance(exc, sqlite3.OperationalError) and "no such table" in str(exc).lower()


def _query_optional(conn: Any, sql: str, params: tuple[Any, ...]) -> tuple[Any, str]:
    try:
        return conn.execute(sql, params), "OK"
    except Exception as exc:  # pragma: no cover - the branch is DB-driver specific
        if _missing_sqlite_relation(exc):
            return None, "OPTIONAL_PROJECTION_UNAVAILABLE"
        raise PlayerStateReadModelError(
            "AUTHORITY_UNAVAILABLE",
            "canonical player-state authority could not be read",
        ) from exc


def _query_required(conn: Any, sql: str, params: tuple[Any, ...]) -> Any:
    try:
        return conn.execute(sql, params)
    except Exception as exc:  # pragma: no cover - the branch is DB-driver specific
        raise PlayerStateReadModelError(
            "AUTHORITY_UNAVAILABLE",
            "required player-state authority could not be read",
        ) from exc


def _as_nonnegative_int(value: Any, field: str) -> tuple[int | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, f"{field} is boolean, not an integer"
    try:
        converted = int(value)
    except (TypeError, ValueError):
        return None, f"{field} is not an integer"
    if converted < 0:
        return None, f"{field} is negative"
    return converted, None


def _as_text(value: Any, field: str) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, str) or not value.strip():
        return None, f"{field} is not a non-empty string"
    return value.strip(), None


def _default_level_resolver(rank_level: Any) -> Any:
    """Use the existing XP/level normalizer rather than copying its rules."""

    try:
        from app import _rank_to_lv  # imported lazily to avoid an import cycle
    except Exception as exc:  # pragma: no cover - depends on deployment imports
        raise PlayerStateReadModelError(
            "AUTHORITY_UNAVAILABLE",
            "existing XP/level authority is unavailable",
        ) from exc
    return _rank_to_lv(rank_level)


def _load_user(conn: Any, user_id: int) -> None:
    row = _query_required(
        conn,
        "SELECT id FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    if row is None:
        raise PlayerStateReadModelError("PLAYER_NOT_FOUND", "player does not exist")


def _project_progression(
    conn: Any,
    user_id: int,
    *,
    level_resolver: Callable[[Any], Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], Any]:
    cursor, table_status = _query_optional(
        conn,
        "SELECT * FROM user_stats WHERE user_id=?",
        (user_id,),
    )
    if cursor is None:
        return (
            {
                "projection_status": table_status,
                "authority": "user_stats",
                "xp": None,
                "rank_level": None,
                "level": None,
                "rank_xp": None,
                "go_rank": None,
                "total_correct": None,
                "current_streak": None,
                "max_streak": None,
            },
            {
                "projection_status": table_status,
                "authority": "user_stats",
            },
            None,
        )

    row = cursor.fetchone()
    if row is None:
        return (
            {
                "projection_status": "OPTIONAL_PROJECTION_UNAVAILABLE",
                "authority": "user_stats",
                "reason": "user_stats row is absent; no synthetic defaults created",
                "xp": None,
                "rank_level": None,
                "level": None,
                "rank_xp": None,
                "go_rank": None,
                "total_correct": None,
                "current_streak": None,
                "max_streak": None,
            },
            {
                "projection_status": "OPTIONAL_PROJECTION_UNAVAILABLE",
                "authority": "user_stats",
            },
            None,
        )

    invalid: list[str] = []
    numbers: dict[str, int | None] = {}
    for field in (
        "xp",
        "rank_xp",
        "total_correct",
        "current_streak",
        "max_streak",
    ):
        value, error = _as_nonnegative_int(_row_value(row, field), field)
        numbers[field] = value
        if error:
            invalid.append(error)

    rank_level, rank_error = _as_text(_row_value(row, "rank_level"), "rank_level")
    if rank_error:
        invalid.append(rank_error)

    level = None
    if rank_level is not None:
        resolver = level_resolver or _default_level_resolver
        try:
            level = resolver(rank_level)
            if isinstance(level, bool) or not isinstance(level, int) or level < 1:
                invalid.append("resolved level is invalid")
                level = None
        except PlayerStateReadModelError:
            raise
        except Exception as exc:
            raise PlayerStateReadModelError(
                "AUTHORITY_UNAVAILABLE",
                "existing XP/level authority could not normalize rank_level",
            ) from exc

    go_rank, go_rank_error = _as_text(_row_value(row, "go_rank"), "go_rank")
    if go_rank_error:
        invalid.append(go_rank_error)

    status = "INVALID_STORED_STATE" if invalid else "OK"
    projection = {
        "projection_status": status,
        "authority": "user_stats",
        "xp": numbers["xp"],
        "rank_level": rank_level,
        "level": level,
        "rank_xp": numbers["rank_xp"],
        "go_rank": go_rank,
        "total_correct": numbers["total_correct"],
        "current_streak": numbers["current_streak"],
        "max_streak": numbers["max_streak"],
    }
    if invalid:
        projection["invalid_fields"] = tuple(invalid)
    return projection, {
        "projection_status": status,
        "authority": "user_stats",
        "source_version": "existing_user_stats_xp_rank_projection",
    }, row


def _canonical_equipment_catalog(
    equipment_definitions: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] | None,
) -> tuple[dict[str, Mapping[str, Any]], frozenset[str], dict[str, set[str]]]:
    if equipment_definitions is None:
        try:
            from app import EQUIPMENT_DEFS, INVENTORY_ONLY_EQUIPMENT_IDS, _FUNCTIONAL_EFFECT_ACTIVE_KEYS
        except Exception as exc:  # pragma: no cover - depends on deployment imports
            raise PlayerStateReadModelError(
                "AUTHORITY_UNAVAILABLE",
                "canonical equipment catalog is unavailable",
            ) from exc
        definitions = EQUIPMENT_DEFS
        inventory_only = frozenset(INVENTORY_ONLY_EQUIPMENT_IDS)
        active_keys = {
            str(item_id): set(effect_keys)
            for item_id, effect_keys in _FUNCTIONAL_EFFECT_ACTIVE_KEYS.items()
        }
    elif isinstance(equipment_definitions, Mapping):
        definitions = equipment_definitions.values()
        inventory_only = INVENTORY_ONLY_TROPHY_IDS
        active_keys = {}
    else:
        definitions = equipment_definitions
        inventory_only = INVENTORY_ONLY_TROPHY_IDS
        active_keys = {}

    by_id: dict[str, Mapping[str, Any]] = {}
    for definition in definitions:
        item_id = str(definition.get("id") or "").strip()
        slot = str(definition.get("slot") or "").strip()
        if item_id and slot in EQUIPMENT_SLOTS:
            by_id[item_id] = definition
    return by_id, inventory_only, active_keys


def _equipment_display(definition: Mapping[str, Any], item_id: str) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "name": definition.get("name"),
        "slot": definition.get("slot"),
        "rarity": definition.get("rarity"),
        "icon": definition.get("icon"),
        "definition_ref": f"EQUIPMENT_DEFS:{item_id}",
    }


def _equipment_status(
    item_id: str,
    *,
    inventory_only: frozenset[str],
    active_keys: Mapping[str, set[str]],
) -> str:
    if item_id in inventory_only:
        return "INVENTORY_ONLY_TROPHY"
    if item_id == XP_AMULET_ID:
        return "HOLD_FOR_AUTHORITY"
    if active_keys.get(item_id):
        return "SERVER_EFFECTIVE"
    return "DEFINED_ONLY"


def _project_equipment(
    conn: Any,
    user_id: int,
    *,
    equipment_definitions: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    catalog, inventory_only, active_keys = _canonical_equipment_catalog(equipment_definitions)
    cursor, table_status = _query_optional(
        conn,
        "SELECT * FROM player_inventory WHERE user_id=? ORDER BY id",
        (user_id,),
    )
    empty_slots = {
        slot: {
            "slot": slot,
            "item_id": None,
            "owned": False,
            "equipped": False,
            "quantity": 0,
            "functional_status": "NONE",
            "display": None,
        }
        for slot in EQUIPMENT_SLOTS
    }
    if cursor is None:
        return (
            {
                "projection_status": table_status,
                "authority": "player_inventory",
                "slots": empty_slots,
                "owned_items": [],
                "invalid_item_ids": [],
                "equipped_slot_conflicts": [],
                "combat_stats_projected": False,
            },
            {
                "projection_status": table_status,
                "authority": "player_inventory",
            },
        )

    rows = cursor.fetchall()
    invalid_item_ids: set[str] = set()
    invalid_rows: list[str] = []
    owned_counts: dict[str, int] = {}
    equipped_by_slot: dict[str, list[str]] = {slot: [] for slot in EQUIPMENT_SLOTS}

    for row in rows:
        item_id = str(_row_value(row, "equip_id") or "").strip()
        definition = catalog.get(item_id)
        if definition is None:
            if item_id:
                invalid_item_ids.add(item_id)
            continue
        owned_counts[item_id] = owned_counts.get(item_id, 0) + 1
        equipped_value = _row_value(row, "equipped", 0)
        if equipped_value not in (0, 1, False, True):
            invalid_rows.append(f"{item_id}:equipped")
            continue
        if bool(equipped_value):
            slot = str(definition.get("slot") or "")
            if item_id in inventory_only:
                invalid_rows.append(f"{item_id}:inventory_only_equipped")
            elif slot in equipped_by_slot:
                equipped_by_slot[slot].append(item_id)

    conflicts = [
        slot
        for slot, item_ids in equipped_by_slot.items()
        if len(item_ids) > 1
    ]
    if invalid_item_ids:
        invalid_rows.extend(f"{item_id}:unknown" for item_id in sorted(invalid_item_ids))
    invalid = bool(invalid_rows or conflicts)

    slots = {slot: dict(value) for slot, value in empty_slots.items()}
    for slot in EQUIPMENT_SLOTS:
        item_ids = equipped_by_slot[slot]
        if len(item_ids) != 1:
            continue
        item_id = item_ids[0]
        definition = catalog[item_id]
        slots[slot] = {
            "slot": slot,
            "item_id": item_id,
            "owned": True,
            "equipped": True,
            "quantity": owned_counts[item_id],
            "functional_status": _equipment_status(
                item_id,
                inventory_only=inventory_only,
                active_keys=active_keys,
            ),
            "display": _equipment_display(definition, item_id),
        }

    # Only a slot with exactly one valid candidate has an effective equipped
    # item.  A conflicted slot is intentionally unresolved; choosing its
    # first/last/highest-rarity row would turn malformed stored state into
    # gameplay authority.
    resolved_equipped_item_ids = {
        item_ids[0]
        for item_ids in equipped_by_slot.values()
        if len(item_ids) == 1
    }

    owned_items = []
    for item_id in sorted(owned_counts):
        definition = catalog[item_id]
        owned_items.append(
            {
                "item_id": item_id,
                "slot": definition.get("slot"),
                "quantity": owned_counts[item_id],
                "equipped": item_id in resolved_equipped_item_ids,
                "functional_status": _equipment_status(
                    item_id,
                    inventory_only=inventory_only,
                    active_keys=active_keys,
                ),
                "display": _equipment_display(definition, item_id),
                "combat_power_projected": False,
            }
        )

    status = "INVALID_STORED_STATE" if invalid else "OK"
    projection = {
        "projection_status": status,
        "authority": "player_inventory",
        "slots": slots,
        "owned_items": owned_items,
        "invalid_item_ids": sorted(invalid_item_ids),
        "equipped_slot_conflicts": sorted(conflicts),
        "combat_stats_projected": False,
    }
    if invalid_rows:
        projection["invalid_rows"] = tuple(sorted(invalid_rows))
    return projection, {
        "projection_status": status,
        "authority": "player_inventory",
        "source_version": "existing_equipment_defs_and_player_inventory",
    }


def _canonical_appearance_catalog(
    appearance_definitions: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] | None,
    active_character_keys: Iterable[str] | None = None,
) -> tuple[dict[str, Mapping[str, Any]], frozenset[str]]:
    if appearance_definitions is None:
        try:
            from app import APPEARANCE_DEFS, ACTIVE_CHARACTER_KEYS
        except Exception as exc:  # pragma: no cover - depends on deployment imports
            raise PlayerStateReadModelError(
                "AUTHORITY_UNAVAILABLE",
                "canonical appearance catalog is unavailable",
            ) from exc
        definitions = APPEARANCE_DEFS
        active_characters = frozenset(ACTIVE_CHARACTER_KEYS)
    elif isinstance(appearance_definitions, Mapping):
        definitions = appearance_definitions.values()
        active_characters = frozenset()
    else:
        definitions = appearance_definitions
        active_characters = frozenset()
    by_id = {
        str(definition.get("id")): definition
        for definition in definitions
        if str(definition.get("id") or "").strip()
    }
    if active_character_keys is not None:
        active_characters = frozenset(str(value) for value in active_character_keys)
    return by_id, active_characters


def _appearance_display(definition: Mapping[str, Any], item_id: str) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "name": definition.get("name"),
        "slot": definition.get("slot"),
        "rarity": definition.get("rarity"),
        "definition_ref": f"APPEARANCE_DEFS:{item_id}",
        "presentation_only": True,
    }


def _project_cosmetics_and_hero(
    conn: Any,
    user_id: int,
    *,
    appearance_definitions: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] | None,
    active_character_keys: Iterable[str] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    catalog, active_characters = _canonical_appearance_catalog(
        appearance_definitions,
        active_character_keys,
    )
    wardrobe_cursor, wardrobe_status = _query_optional(
        conn,
        "SELECT item_id, obtained_at, source FROM player_wardrobe "
        "WHERE user_id=? ORDER BY item_id",
        (user_id,),
    )
    appearance_cursor, appearance_status = _query_optional(
        conn,
        "SELECT * FROM player_appearance WHERE user_id=?",
        (user_id,),
    )
    if wardrobe_cursor is None or appearance_cursor is None:
        status = (
            "OPTIONAL_PROJECTION_UNAVAILABLE"
            if wardrobe_status != "OK" or appearance_status != "OK"
            else "OK"
        )
        hero = {
            "hero_id": None,
            "identity_status": "MISSING_HERO_SELECTION",
            "authority": "player_appearance.character_key",
            "authority_scope": "presentation_only",
            "presentation_fallback_id": PRESENTATION_DEFAULT_HERO_ID,
        }
        cosmetics = {
            "projection_status": status,
            "authority": "player_wardrobe_and_player_appearance",
            "selected": {slot: None for slot in APPEARANCE_SLOTS},
            "owned_items": [],
            "invalid_item_ids": [],
            "invalid_selected_ids": [],
            "gameplay_effects_projected": False,
        }
        return cosmetics, hero, {
            "projection_status": status,
            "authority": "player_wardrobe_and_player_appearance",
        }

    wardrobe_rows = wardrobe_cursor.fetchall()
    appearance_row = appearance_cursor.fetchone()
    owned_ids: set[str] = set()
    invalid_item_ids: set[str] = set()
    owned_items: list[dict[str, Any]] = []
    for row in wardrobe_rows:
        item_id = str(_row_value(row, "item_id") or "").strip()
        definition = catalog.get(item_id)
        if definition is None:
            if item_id:
                invalid_item_ids.add(item_id)
            continue
        owned_ids.add(item_id)
        owned_items.append(
            {
                "item_id": item_id,
                "slot": definition.get("slot"),
                "display": _appearance_display(definition, item_id),
                "obtained_at": _row_value(row, "obtained_at"),
                "source": _row_value(row, "source"),
                "presentation_only": True,
                "combat_power_projected": False,
            }
        )

    invalid_selected_ids: set[str] = set()
    selected: dict[str, Any] = {}
    appearance_keys = _row_keys(appearance_row)
    for slot in APPEARANCE_SLOTS:
        column = f"{slot}_id"
        raw_item_id = _row_value(appearance_row, column) if column in appearance_keys else None
        item_id = str(raw_item_id).strip() if raw_item_id else None
        definition = catalog.get(item_id) if item_id else None
        if item_id and (
            item_id not in owned_ids
            or definition is None
            or definition.get("slot") != slot
        ):
            invalid_selected_ids.add(item_id)
            item_id = None
            definition = None
        selected[slot] = (
            {
                "item_id": item_id,
                "owned": True,
                "equipped": True,
                "display": _appearance_display(definition, item_id),
                "presentation_only": True,
                "combat_power_projected": False,
            }
            if item_id and definition
            else None
        )

    stored_character = _row_value(appearance_row, "character_key") if appearance_row else None
    stored_character = str(stored_character).strip() if stored_character else None
    if stored_character in active_characters:
        hero = {
            "hero_id": stored_character,
            "identity_status": "PRESENTATION_SELECTION",
            "authority": "player_appearance.character_key",
            "authority_scope": "presentation_only",
            "presentation_fallback_id": PRESENTATION_DEFAULT_HERO_ID,
        }
        hero_status = "OK"
    elif stored_character:
        hero = {
            "hero_id": None,
            "identity_status": "INVALID_STORED_STATE",
            "authority": "player_appearance.character_key",
            "authority_scope": "presentation_only",
            "presentation_fallback_id": PRESENTATION_DEFAULT_HERO_ID,
            "invalid_stored_value": stored_character,
        }
        hero_status = "INVALID_STORED_STATE"
    else:
        hero = {
            "hero_id": None,
            "identity_status": "MISSING_HERO_SELECTION",
            "authority": "player_appearance.character_key",
            "authority_scope": "presentation_only",
            "presentation_fallback_id": PRESENTATION_DEFAULT_HERO_ID,
        }
        hero_status = "OPTIONAL_PROJECTION_UNAVAILABLE"

    invalid = bool(invalid_item_ids or invalid_selected_ids)
    status = "INVALID_STORED_STATE" if invalid else "OK"
    if hero_status == "INVALID_STORED_STATE":
        status = hero_status
    cosmetics = {
        "projection_status": status,
        "authority": "player_wardrobe_and_player_appearance",
        "selected": selected,
        "owned_items": sorted(owned_items, key=lambda item: item["item_id"]),
        "invalid_item_ids": sorted(invalid_item_ids),
        "invalid_selected_ids": sorted(invalid_selected_ids),
        "gameplay_effects_projected": False,
    }

    # F027-R1 is an additive validation/consumption gate over the existing
    # B028 projection.  Minimal injected catalogs used by older callers may
    # intentionally omit Mapping A, so only the complete canonical catalog
    # activates this gate; the production catalog contains all ten IDs.
    if set(MAPPING_A_IDS).issubset(catalog):
        mapping_a_projection = consume_mapping_a_cosmetics(
            cosmetics,
            appearance_definitions=catalog,
        )
        if not mapping_a_projection.is_ready:
            invalid_item_ids.update(mapping_a_projection.invalid_item_ids)
            invalid_selected_ids.update(mapping_a_projection.invalid_selected_ids)
            cosmetics["invalid_item_ids"] = sorted(invalid_item_ids)
            cosmetics["invalid_selected_ids"] = sorted(invalid_selected_ids)
            cosmetics["projection_status"] = (
                "AUTHORITY_UNAVAILABLE"
                if mapping_a_projection.status == "AUTHORITY_UNAVAILABLE"
                else "INVALID_STORED_STATE"
            )
    return cosmetics, hero, {
        "projection_status": cosmetics["projection_status"],
        "authority": "player_wardrobe_and_player_appearance",
        "source_version": "existing_appearance_defs_wardrobe_projection",
    }


def _default_spirit_projection(conn: Any, user_id: int) -> dict[str, Any]:
    try:
        from spirit_runtime import build_b022_active_spirit_projection
    except Exception as exc:  # pragma: no cover - depends on deployment imports
        raise PlayerStateReadModelError(
            "AUTHORITY_UNAVAILABLE",
            "canonical Spirit projection is unavailable",
        ) from exc
    return build_b022_active_spirit_projection(conn, user_id)


def _project_spirit(
    conn: Any,
    user_id: int,
    *,
    spirit_projection_builder: Callable[[Any, int], Mapping[str, Any]] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    builder = spirit_projection_builder or _default_spirit_projection
    try:
        projection = builder(conn, user_id)
    except PlayerStateReadModelError:
        raise
    except Exception as exc:
        if isinstance(exc, sqlite3.OperationalError) and "no such table" in str(exc).lower():
            return (
                {
                    "projection_status": "OPTIONAL_PROJECTION_UNAVAILABLE",
                    "authority": "pet_collection_and_user_pets",
                    "active": None,
                    "single_active_spirit": True,
                },
                {
                    "projection_status": "OPTIONAL_PROJECTION_UNAVAILABLE",
                    "authority": "pet_collection_and_user_pets",
                },
            )
        raise PlayerStateReadModelError(
            "AUTHORITY_UNAVAILABLE",
            "canonical Spirit projection could not be read",
        ) from exc

    if not isinstance(projection, Mapping):
        raise PlayerStateReadModelError(
            "AUTHORITY_AMBIGUOUS",
            "Spirit projection is not a structured server projection",
        )
    if projection.get("single_active_spirit") is False:
        return (
            {
                "projection_status": "AUTHORITY_AMBIGUOUS",
                "authority": "pet_collection_and_user_pets",
                "active": None,
                "single_active_spirit": False,
            },
            {
                "projection_status": "AUTHORITY_AMBIGUOUS",
                "authority": "pet_collection_and_user_pets",
            },
        )

    active_id = projection.get("active_spirit_id")
    if active_id is not None:
        active_id = str(active_id).strip()
        try:
            from spirit_runtime import CANONICAL_SPIRIT_IDS
            known_ids = set(CANONICAL_SPIRIT_IDS)
        except Exception as exc:  # pragma: no cover - depends on deployment imports
            raise PlayerStateReadModelError(
                "AUTHORITY_UNAVAILABLE",
                "canonical Spirit identity authority is unavailable",
            ) from exc
        if active_id not in known_ids:
            return (
                {
                    "projection_status": "INVALID_STORED_STATE",
                    "authority": "pet_collection_and_user_pets",
                    "active": None,
                    "single_active_spirit": True,
                    "invalid_active_spirit_id": active_id,
                },
                {
                    "projection_status": "INVALID_STORED_STATE",
                    "authority": "pet_collection_and_user_pets",
                },
            )

    active = None
    if active_id:
        active = {
            "spirit_id": active_id,
            "enabled": bool(projection.get("enabled")),
            "ownership_validated": bool(projection.get("ownership_validated")),
            "evolution_stage": projection.get("evolution_stage"),
            "progression_level": projection.get("progression_level"),
            "authority": "server_b022_d008_active_spirit_projection",
        }
        if not active["ownership_validated"] or not active["enabled"]:
            active = None

    return (
        {
            "projection_status": "OK",
            "authority": "pet_collection_and_user_pets",
            "active": active,
            "single_active_spirit": True,
            "combat_effects_projected": False,
        },
        {
            "projection_status": "OK",
            "authority": "pet_collection_and_user_pets",
            "source_version": "build_b022_active_spirit_projection",
        },
    )


def _project_hp_and_boundary(stats: Mapping[str, Any]) -> dict[str, Any]:
    projection = {
        "projection_status": stats.get("projection_status", "OK"),
        "authority": "user_stats",
        "scope": "persistent_player_state_for_legacy_battlefield",
        "persistent_player_hp": stats.get("persistent_player_hp"),
        "persistent_player_max_hp": stats.get("persistent_player_max_hp"),
        "encounter_hp": {
            "projected": False,
            "authority": "encounter_local_battle_state",
            "reason": "Map Battle and other encounters require battle context",
        },
    }
    if stats.get("invalid_fields"):
        projection["invalid_fields"] = tuple(stats["invalid_fields"])
    return projection


def _project_stats_with_hp(progression: Mapping[str, Any], row: Any) -> dict[str, Any]:
    projection = dict(progression)
    invalid = list(projection.get("invalid_fields", ()))
    hp, hp_error = _as_nonnegative_int(_row_value(row, "player_hp"), "player_hp")
    hp_max, hp_max_error = _as_nonnegative_int(
        _row_value(row, "player_max_hp"), "player_max_hp"
    )
    if hp_error:
        invalid.append(hp_error)
    if hp_max_error:
        invalid.append(hp_max_error)
    if hp_max is not None and hp_max == 0:
        invalid.append("player_max_hp is zero")
    if hp is not None and hp_max is not None and hp > hp_max:
        invalid.append("player_hp exceeds player_max_hp")
    projection["persistent_player_hp"] = hp
    projection["persistent_player_max_hp"] = hp_max
    if invalid:
        projection["projection_status"] = "INVALID_STORED_STATE"
        projection["invalid_fields"] = tuple(invalid)
    return projection


def build_player_state_read_model(
    conn: Any,
    user_id: int,
    *,
    level_resolver: Callable[[Any], Any] | None = None,
    equipment_definitions: Iterable[Mapping[str, Any]]
    | Mapping[str, Mapping[str, Any]]
    | None = None,
    appearance_definitions: Iterable[Mapping[str, Any]]
    | Mapping[str, Mapping[str, Any]]
    | None = None,
    active_character_keys: Iterable[str] | None = None,
    spirit_projection_builder: Callable[[Any, int], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the canonical server-side Player/Hero read model.

    The authenticated caller supplies ``user_id``; this function does not
    accept client-authored state.  It performs only SELECTs and never commits,
    mutates, grants, or recalculates combat/reward state.
    """

    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise PlayerStateReadModelError("INVALID_REQUEST", "user_id must be a positive integer")

    _load_user(conn, user_id)
    progression, progression_provenance, stats_row = _project_progression(
        conn,
        user_id,
        level_resolver=level_resolver,
    )

    if stats_row is None:
        stats_for_hp: Mapping[str, Any] = {
            "projection_status": progression.get(
                "projection_status", "OPTIONAL_PROJECTION_UNAVAILABLE"
            )
        }
    else:
        stats_for_hp = _project_stats_with_hp(progression, stats_row)
    hp = _project_hp_and_boundary(stats_for_hp)

    equipment, equipment_provenance = _project_equipment(
        conn,
        user_id,
        equipment_definitions=equipment_definitions,
    )
    spirit, spirit_provenance = _project_spirit(
        conn,
        user_id,
        spirit_projection_builder=spirit_projection_builder,
    )
    cosmetics, hero, cosmetics_provenance = _project_cosmetics_and_hero(
        conn,
        user_id,
        appearance_definitions=appearance_definitions,
        active_character_keys=active_character_keys,
    )

    statuses = [
        progression.get("projection_status"),
        equipment.get("projection_status"),
        spirit.get("projection_status"),
        cosmetics.get("projection_status"),
        hero.get("identity_status"),
        hp.get("projection_status"),
    ]
    if "AUTHORITY_AMBIGUOUS" in statuses:
        overall_status = "AUTHORITY_AMBIGUOUS"
    elif "INVALID_STORED_STATE" in statuses:
        overall_status = "INVALID_STORED_STATE"
    elif "AUTHORITY_UNAVAILABLE" in statuses:
        overall_status = "AUTHORITY_UNAVAILABLE"
    elif any(status == "OPTIONAL_PROJECTION_UNAVAILABLE" for status in statuses):
        overall_status = "PARTIAL"
    else:
        overall_status = "OK"

    return {
        "read_model": READ_MODEL_NAME,
        "read_model_version": READ_MODEL_VERSION,
        "projection_status": overall_status,
        "read_only": True,
        "mutates": False,
        "player_id": user_id,
        "hero": hero,
        "progression": progression,
        "hp": hp,
        "equipment": equipment,
        "spirit": spirit,
        "cosmetics": cosmetics,
        "world": {
            "projected": False,
            "authority": "world_progression_system",
            "selected_zone_is_not_player_progression": True,
            "reason": "World progression is outside the Player/Hero read model authority",
        },
        "provenance": {
            "player": {
                "authority": "users.id",
                "source_version": "existing_users_identity",
            },
            "hero": {
                "authority": hero.get("authority"),
                "scope": "presentation_only",
            },
            "progression": progression_provenance,
            "hp": {
                "authority": "user_stats.player_hp/player_max_hp",
                "scope": "persistent legacy/global player state",
            },
            "equipment": equipment_provenance,
            "spirit": spirit_provenance,
            "cosmetics": cosmetics_provenance,
            "world": {
                "authority": "world_progression_system",
                "projected": False,
            },
        },
    }


__all__ = [
    "APPEARANCE_SLOTS",
    "EQUIPMENT_SLOTS",
    "PlayerStateReadModelError",
    "READ_MODEL_NAME",
    "READ_MODEL_VERSION",
    "build_player_state_read_model",
]
