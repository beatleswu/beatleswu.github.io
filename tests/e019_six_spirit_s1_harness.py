"""Pure test-only fixtures and projections for E019 Six-Spirit S1.

This module deliberately does not import or modify app.py.  It models the
accepted boundary between authoritative Spirit state and future presentation
surfaces so S1 tests can run before the six-Spirit runtime exists.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping


CONTRACT_PATH = Path(__file__).resolve().parent / "fixtures" / "e019_six_spirit_s1_contract.json"


def load_contract() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def stage_for_level(level: int) -> str:
    level = max(1, int(level))
    if level >= 25:
        return "III"
    if level >= 10:
        return "II"
    return "I"


def validate_server_state(state: Mapping[str, Any]) -> None:
    owned = set(state.get("owned", ()))
    active = state.get("active")
    if active not in owned:
        raise ValueError("active Spirit must be present in functional ownership")


def roster_projection(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project one authoritative state into six logical presentation slots."""

    contract = load_contract()
    validate_server_state(state)
    owned = set(state.get("owned", ()))
    levels = state.get("levels", {})
    active = state["active"]
    projection: list[dict[str, Any]] = []
    for slot in contract["six_slots"]:
        spirit_id = slot["spirit_id"]
        if spirit_id is None:
            projection.append({
                "slot": slot["slot"],
                "spirit_id": None,
                "role": slot["role"],
                "state": "future_catalog_slot",
                "level": None,
                "stage": None,
            })
            continue
        level = max(1, int(levels.get(spirit_id, 1)))
        projection.append({
            "slot": slot["slot"],
            "spirit_id": spirit_id,
            "role": slot["role"],
            "state": "active" if spirit_id == active else ("owned" if spirit_id in owned else "locked"),
            "level": level if spirit_id in owned else None,
            "stage": stage_for_level(level) if spirit_id in owned else None,
        })
    return projection


def future_slot_projection(role: str, state: str) -> dict[str, Any]:
    """Represent a future catalog slot without inventing an ID or name."""

    allowed_roles = {slot["role"] for slot in load_contract()["six_slots"][3:]}
    if role not in allowed_roles:
        raise ValueError(f"unknown future slot role: {role}")
    if state not in {"LOCKED", "AVAILABLE", "OWNED"}:
        raise ValueError(f"unknown generic unlock state: {state}")
    return {
        "role": role,
        "spirit_id": None,
        "canonical_name": None,
        "unlock_state": state,
    }


def presentation_adapter(state: Mapping[str, Any], *, presentation_state: str = "following") -> dict[str, Any]:
    """Create a presentation-only follower payload from server state."""

    validate_server_state(state)
    active = state["active"]
    level = max(1, int(state.get("levels", {}).get(active, 1)))
    return {
        "spirit_id": active,
        "evolution_stage": stage_for_level(level),
        "art_manifest": f"catalog:{active}",
        "animation_manifest": f"animation:{active}:stage-{stage_for_level(level)}",
        "presentation_state": presentation_state,
    }


def apply_scene_override(state: Mapping[str, Any], scene_spirit_id: str) -> dict[str, Any]:
    """Add a scene-only visual override without changing authoritative state."""

    contract = load_contract()
    if scene_spirit_id not in contract["canonical_existing_spirit_ids"]:
        raise ValueError("scene override must reference a catalog Spirit")
    result = copy.deepcopy(dict(state))
    result["scene_override"] = scene_spirit_id
    return result


def replay_settlement_delta() -> dict[str, int]:
    return {
        "spirit_xp": 0,
        "spirit_items": 0,
        "spirit_unlock_progress": 0,
        "evolution_reward": 0,
    }


def asset_failure_fallback(state: Mapping[str, Any], failure: str) -> dict[str, Any]:
    """Return a safe presentation fallback while preserving authority."""

    allowed = set(load_contract()["asset_failure_contract"]["failure_inputs"])
    if failure not in allowed:
        raise ValueError(f"unknown asset failure: {failure}")
    result = copy.deepcopy(dict(state))
    result["presentation_fallback"] = "safe_placeholder"
    return result


def authority_boundary() -> dict[str, bool]:
    return {
        "spirit_effect_before_judge": False,
        "second_combat_engine": False,
        "client_spirit_damage_authority": False,
        "follower_can_change_active_spirit": False,
        "follower_can_unlock_spirit": False,
        "follower_can_grant_reward": False,
        "follower_can_change_zone_progress": False,
        "multiple_client_active_authorities": False,
        "client_can_select_evolution_stage": False,
    }
