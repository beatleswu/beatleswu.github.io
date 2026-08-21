"""Canonical, read-only World NPC presentation registry.

The existing shared JSON identity registry is the sole identity source. Its
historical Lane A filename is preserved deliberately; this module only loads
and validates its ``world_npcs`` presentation records for runtime surfaces.
It does not own player selection, inventory, equipment, combat, shop, or
database state.
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
WORLD_NPC_IDENTITY_REGISTRY_RELATIVE_PATH = (
    "docs/planning/rpg_wave2_lane_a_character_identity_registry_v1.json"
)
WORLD_NPC_REGISTRY_VERSION = "go-odyssey.world-npc-presentation.v1"
CANONICAL_WORLD_NPC_REGISTRY_COUNT = 1
CANONICAL_WORLD_NPC_IDS = (
    "world.village_elder",
    "world.messenger",
    "world.smith_elder",
    "world.archmage",
    "world.serel",
    "world.herder",
    "world.eastern_guardian",
)
_ALLOWED_SURFACE_STATUSES = {
    "INTEGRATED",
    "MISSING_REQUIRED",
    "LEGACY_NONBLOCKING",
    "NOT_REQUIRED",
    "DEFERRED",
}


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
    if presentation.get("canonical_count") != len(CANONICAL_WORLD_NPC_IDS):
        raise RuntimeError("world_npc_registry_count_invalid")
    if tuple(presentation.get("canonical_ids") or ()) != CANONICAL_WORLD_NPC_IDS:
        raise RuntimeError("world_npc_registry_ids_invalid")
    if len(records) != len(CANONICAL_WORLD_NPC_IDS):
        raise RuntimeError("world_npc_registry_count_invalid")

    authority_model = presentation.get("authority_model")
    if not isinstance(authority_model, dict):
        raise RuntimeError("world_npc_registry_authority_model_missing")
    if authority_model.get("canonical_registry_file") != WORLD_NPC_IDENTITY_REGISTRY_RELATIVE_PATH:
        raise RuntimeError("world_npc_registry_authority_file_invalid")
    if authority_model.get("canonical_registry_count") != CANONICAL_WORLD_NPC_REGISTRY_COUNT:
        raise RuntimeError("world_npc_registry_authority_count_invalid")
    if authority_model.get("is_existing_shared_registry") is not True:
        raise RuntimeError("world_npc_registry_shared_authority_invalid")
    if authority_model.get("is_world_npc_canonical_authority") is not True:
        raise RuntimeError("world_npc_registry_canonical_authority_invalid")
    if authority_model.get("competing_npc_registries") != []:
        raise RuntimeError("world_npc_registry_competing_authority")
    if authority_model.get("projection_loaders_are_not_registries") is not True:
        raise RuntimeError("world_npc_registry_projection_authority_invalid")

    surfaces = presentation.get("runtime_surfaces")
    if not isinstance(surfaces, list) or len(surfaces) != 8:
        raise RuntimeError("world_npc_runtime_surface_table_invalid")
    required_surface_fields = {
        "surface_id",
        "user_visible_or_internal",
        "current_consumer",
        "current_npc_source",
        "status",
        "wave2_required",
        "evidence",
        "responsive_validation",
    }
    surface_ids = []
    for surface in surfaces:
        if not isinstance(surface, dict) or not required_surface_fields <= set(surface):
            raise RuntimeError("world_npc_runtime_surface_fields_invalid")
        if surface["status"] not in _ALLOWED_SURFACE_STATUSES:
            raise RuntimeError("world_npc_runtime_surface_status_invalid")
        if surface["status"] == "MISSING_REQUIRED" and surface["wave2_required"] is not True:
            raise RuntimeError("world_npc_missing_surface_contract_invalid")
        if surface["status"] != "MISSING_REQUIRED" and surface["wave2_required"] is not False and surface["status"] != "INTEGRATED":
            raise RuntimeError("world_npc_surface_requirement_invalid")
        surface_ids.append(surface["surface_id"])
    if len(set(surface_ids)) != len(surface_ids):
        raise RuntimeError("world_npc_runtime_surface_ids_invalid")

    legacy_references = presentation.get("legacy_references")
    if not isinstance(legacy_references, list) or len(legacy_references) != 2:
        raise RuntimeError("world_npc_legacy_reference_table_invalid")
    required_legacy_fields = {
        "reference_id",
        "file",
        "reference",
        "current_behavior",
        "live_or_dead",
        "safe_to_remove",
        "classification",
        "resolution",
    }
    for legacy in legacy_references:
        if not isinstance(legacy, dict) or not required_legacy_fields <= set(legacy):
            raise RuntimeError("world_npc_legacy_reference_fields_invalid")
        if legacy["classification"] != "LEGACY_NONBLOCKING":
            raise RuntimeError("world_npc_legacy_reference_unexplained")

    packaging = presentation.get("packaging")
    if not isinstance(packaging, dict):
        raise RuntimeError("world_npc_packaging_contract_missing")
    if packaging.get("source_master_count") != len(CANONICAL_WORLD_NPC_IDS):
        raise RuntimeError("world_npc_packaging_master_count_invalid")
    if packaging.get("release_runtime_count") != len(CANONICAL_WORLD_NPC_IDS):
        raise RuntimeError("world_npc_packaging_runtime_count_invalid")
    if packaging.get("mobile_projection_count") != len(CANONICAL_WORLD_NPC_IDS):
        raise RuntimeError("world_npc_packaging_mobile_count_invalid")
    if packaging.get("mobile_assets_are_runtime_aliases") is not True:
        raise RuntimeError("world_npc_packaging_mobile_policy_invalid")
    if packaging.get("superseded_eastern_guardian_shield_asset_canonical") is not False:
        raise RuntimeError("world_npc_superseded_shield_asset_invalid")

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
        "surface_table": deepcopy(presentation.get("runtime_surfaces", [])),
        "legacy_references": deepcopy(presentation.get("legacy_references", [])),
        "registry_authority": deepcopy(presentation["authority_model"]),
        "packaging": deepcopy(presentation["packaging"]),
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
    "CANONICAL_WORLD_NPC_REGISTRY_COUNT",
    "WORLD_NPC_IDENTITY_REGISTRY_PATH",
    "WORLD_NPC_IDENTITY_REGISTRY_RELATIVE_PATH",
    "WORLD_NPC_REGISTRY_VERSION",
    "world_npc_registry_payload",
]
