"""Thin server adapter for the locked Six-Spirit Combat V1 policy.

This module is deliberately narrower than a combat engine.  It obtains the
transaction-local B022/D008 active-Spirit projection, combines it with facts
already calculated by the canonical combat caller, and invokes the one pure
policy evaluator.  It never judges a Go answer, derives equipment or armor
stats, mutates HP, or writes rewards.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from spirit_combat_policy import evaluate_spirit_combat_effect
from spirit_runtime import build_b022_active_spirit_projection


ACTIVE_SPIRIT_SOURCE = "SERVER_B022_D008_PROJECTION"


def _unavailable_projection() -> dict[str, Any]:
    """Return a fail-closed projection when the optional Spirit read is absent."""

    return {
        "active_spirit_id": None,
        "ownership_validated": False,
        "evolution_stage": None,
        "progression_level": None,
        "effect_profile_id": None,
        "effect_policy_version": None,
        "enabled": False,
        "single_active_spirit": True,
        "source": ACTIVE_SPIRIT_SOURCE,
    }


def _server_projection(
    conn: Any,
    user_id: int,
    resolver: Callable[[Any, int], Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Read only the server-owned active projection and fail closed on absence."""

    savepoint = "b027_spirit_projection_read"
    savepoint_open = False
    try:
        # A projection read can encounter an additive-schema rollout where
        # the Spirit tables do not exist yet.  PostgreSQL marks the whole
        # transaction failed after that error; isolate the read so the
        # caller's Map Battle reservation/settlement transaction remains
        # usable and the effect simply becomes no-op.
        conn.execute(f"SAVEPOINT {savepoint}")
        savepoint_open = True
    except Exception:
        savepoint_open = False

    try:
        projection = (
            resolver(conn, int(user_id))
            if resolver is not None
            else build_b022_active_spirit_projection(conn, int(user_id))
        )
    except Exception:
        if savepoint_open:
            try:
                conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            except Exception:
                pass
        # A missing/temporarily unavailable Spirit projection must not block or
        # alter the canonical combat settlement.  It simply means no Spirit
        # effect is eligible for this settlement.
        return _unavailable_projection()
    else:
        if savepoint_open:
            try:
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            except Exception:
                return _unavailable_projection()
    if not isinstance(projection, Mapping):
        return _unavailable_projection()
    result = dict(projection)
    # B022 guarantees one active projection.  Supplying the invariant to the
    # pure evaluator keeps direct adapters fail-closed if a future projection
    # implementation omits the explicit marker.
    result.setdefault("single_active_spirit", True)
    result.setdefault("source", ACTIVE_SPIRIT_SOURCE)
    return result


def apply_spirit_combat_effect(
    conn: Any,
    user_id: int,
    *,
    answer_correct: bool | None,
    encounter_class: str | None,
    monster_hp_before: int | None,
    monster_max_hp: int | None,
    incoming_damage_after_armor: int | None,
    outgoing_damage_after_equipment: int | None,
    player_hp_before: int | None,
    player_max_hp: int | None,
    projection_resolver: Callable[[Any, int], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate one Spirit against one server-owned combat transition.

    ``answer_correct`` is intentionally nullable for legacy review callers
    that have no server answer evidence.  The policy then refuses correctness
    dependent effects; the Support/Bastion trigger remains independent of
    answer correctness and still uses only canonical incoming/HP facts.
    """

    projection = _server_projection(conn, user_id, projection_resolver)
    facts = {
        **projection,
        "answer_correct": answer_correct,
        "encounter_class": encounter_class,
        "monster_hp_before": monster_hp_before,
        "monster_max_hp": monster_max_hp,
        "incoming_damage_after_armor": incoming_damage_after_armor,
        "outgoing_damage_after_equipment": outgoing_damage_after_equipment,
        "player_hp_before": player_hp_before,
        "player_max_hp": player_max_hp,
    }
    return evaluate_spirit_combat_effect(facts)


__all__ = [
    "ACTIVE_SPIRIT_SOURCE",
    "apply_spirit_combat_effect",
]
