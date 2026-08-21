"""Canonical, read-only World NPC presentation registry.

The JSON identity registry is the sole identity source.  This module only
loads and validates its ``world_npcs`` presentation records for runtime
surfaces; it does not own player selection, inventory, equipment, combat,
shop, or database state.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path


WORLD_NPC_IDENTITY_REGISTRY_PATH = (
    Path(__file__).resolve().parent
    / "docs"
    / "planning"
    / "rpg_wave2_lane_a_character_identity_registry_v1.json"
)
WORLD_NPC_REGISTRY_VERSION = "go-odyssey.world-npc-presentation.v1"
CANONICAL_WORLD_NPC_IDS = (
    "world.village_elder",
    "world.messenger",
    "world.smith_elder",
    "world.archmage",
    "world.serel",
    "world.herder",
    "world.eastern_guardian",
)


def _load_identity_registry() -> dict:
    try:
        with WORLD_NPC_IDENTITY_REGISTRY_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("world_npc_identity_registry_unavailable") from exc


def _validated_records() -> tuple[dict, dict]:
    registry = _load_identity_registry()
    presentation = registry.get("world_npc_presentation_registry")
    records = registry.get("world_npcs")
    if not isinstance(presentation, dict) or not isinstance(records, list):
        raise RuntimeError("world_npc_registry_shape_invalid")
    if presentation.get("registry_version") != WORLD_NPC_REGISTRY_VERSION:
        raise RuntimeError("world_npc_registry_version_invalid")
    if tuple(presentation.get("canonical_ids") or ()) != CANONICAL_WORLD_NPC_IDS:
        raise RuntimeError("world_npc_registry_ids_invalid")
    if len(records) != len(CANONICAL_WORLD_NPC_IDS):
        raise RuntimeError("world_npc_registry_count_invalid")

    record_ids = tuple(record.get("canonical_id") for record in records)
    if record_ids != CANONICAL_WORLD_NPC_IDS or len(set(record_ids)) != len(record_ids):
        raise RuntimeError("world_npc_registry_record_ids_invalid")

    required = (
        "display_name",
        "zone_id",
        "zone",
        "role",
        "asset_key",
        "art_master",
        "runtime_asset",
        "mobile_asset",
        "story_references",
        "player_selectable",
        "combat_authority",
        "equipment_authority",
    )
    for record in records:
        if any(field not in record for field in required):
            raise RuntimeError("world_npc_registry_record_fields_invalid")
        if record["player_selectable"] is not False:
            raise RuntimeError("world_npc_player_selectable_forbidden")
        if record["combat_authority"] != "none":
            raise RuntimeError("world_npc_combat_authority_forbidden")
        if record["equipment_authority"] != "none":
            raise RuntimeError("world_npc_equipment_authority_forbidden")
        if not isinstance(record["story_references"], list) or not record["story_references"]:
            raise RuntimeError("world_npc_story_references_missing")

    return presentation, records


def world_npc_registry_payload() -> dict:
    """Return the immutable presentation projection used by read-only APIs."""

    presentation, records = _validated_records()
    return {
        "version": WORLD_NPC_REGISTRY_VERSION,
        "canonical_count": presentation["canonical_count"],
        "canonical_ids": list(presentation["canonical_ids"]),
        "world_npcs": deepcopy(records),
        "runtime_surfaces": deepcopy(presentation.get("runtime_surfaces", [])),
        "zone_mapping_discrepancies": deepcopy(
            presentation.get("zone_mapping_discrepancies", [])
        ),
        "authority": deepcopy(presentation["authority"]),
        "mutation_boundary": {
            "ownership_mutation": 0,
            "player_inventory_mutation": 0,
            "combat_mutation": 0,
            "database_mutation": 0,
        },
    }


__all__ = [
    "CANONICAL_WORLD_NPC_IDS",
    "WORLD_NPC_IDENTITY_REGISTRY_PATH",
    "WORLD_NPC_REGISTRY_VERSION",
    "world_npc_registry_payload",
]
