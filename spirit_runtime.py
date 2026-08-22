"""Server-owned Six-Spirit catalog and read projection.

The catalog in this module is the gameplay identity registry. A021A asset
manifests are presentation inputs only and never create ownership, active
state, progression, or evolution authority.
"""

from __future__ import annotations

from typing import Any

from spirit_lineage import (
    KNOWN_SPIRIT_IDS,
    SPIRIT_UNLOCK_LEVEL_THRESHOLDS,
    evolution_stage_for_level,
)


CANONICAL_SPIRIT_IDS = tuple(KNOWN_SPIRIT_IDS)
# Only the first three unlock gates are currently product-authorized.  The
# final three entries are deliberately source-less until Adventure/Boss/Quest
# supplies an approved authoritative settlement; assets do not unlock a
# Spirit and D008 must not invent level gates for them.
SPIRIT_UNLOCK_LEVELS = tuple(
    1 if index == 0 and level is None else level
    for index, level in enumerate(SPIRIT_UNLOCK_LEVEL_THRESHOLDS)
)
SPIRIT_STAGE_VALUES = ("STAGE_I", "STAGE_II", "STAGE_III")

_ROLES = (
    "TRAINING",
    "REVIEW",
    "CHALLENGE",
    "EXPLORATION",
    "PRECISION",
    "SUPPORT",
)


CANONICAL_SPIRIT_CATALOG: dict[str, dict[str, Any]] = {
    spirit_id: {
        "spirit_id": spirit_id,
        "slot": index + 1,
        "role": _ROLES[index],
        "unlock_level": SPIRIT_UNLOCK_LEVELS[index],
        "unlock_source": (
            "LEVEL_THRESHOLD" if SPIRIT_UNLOCK_LEVELS[index] is not None
            else "FUTURE_AUTHENTICATED_SETTLEMENT"
        ),
        "stage_values": SPIRIT_STAGE_VALUES,
        "effect_profile_id": None,
        "effect_policy_version": None,
        "enabled": True,
        "presentation_manifest_is_ownership_authority": False,
    }
    for index, spirit_id in enumerate(CANONICAL_SPIRIT_IDS)
}


def validate_catalog() -> None:
    """Fail closed if the server registry is internally inconsistent."""

    if len(CANONICAL_SPIRIT_IDS) != 6:
        raise RuntimeError("Six-Spirit catalog must contain exactly six IDs")
    if len(set(CANONICAL_SPIRIT_IDS)) != len(CANONICAL_SPIRIT_IDS):
        raise RuntimeError("Six-Spirit catalog contains duplicate IDs")
    if set(CANONICAL_SPIRIT_CATALOG) != set(CANONICAL_SPIRIT_IDS):
        raise RuntimeError("Six-Spirit catalog metadata is incomplete")
    if tuple(CANONICAL_SPIRIT_CATALOG) != CANONICAL_SPIRIT_IDS:
        raise RuntimeError("Six-Spirit catalog order is not canonical")
    if len(SPIRIT_UNLOCK_LEVELS) != len(CANONICAL_SPIRIT_IDS):
        raise RuntimeError("Six-Spirit unlock metadata is incomplete")
    if any(level is not None and (not isinstance(level, int) or level < 1)
           for level in SPIRIT_UNLOCK_LEVELS):
        raise RuntimeError("Six-Spirit unlock metadata contains an invalid gate")


validate_catalog()


def validate_server_spirit_id(spirit_id: Any) -> str:
    value = str(spirit_id or "").strip()
    if value not in CANONICAL_SPIRIT_CATALOG:
        raise ValueError("unknown Spirit ID")
    return value


def stage_for_level(level: Any) -> str:
    return evolution_stage_for_level(max(1, int(level or 1)))


def build_spirit_projection(conn: Any, user_id: int) -> dict[str, Any]:
    """Build the server-owned projection consumed by presentation/B022.

    ``pet_collection`` remains functional ownership/progression authority;
    ``user_pets`` contributes only the active compatibility projection and
    the freshest active-row snapshot.
    """

    collection_rows = conn.execute(
        "SELECT * FROM pet_collection WHERE user_id=?", (user_id,)
    ).fetchall()
    active_row = conn.execute(
        "SELECT * FROM user_pets WHERE user_id=?", (user_id,)
    ).fetchone()
    collection = {str(row["pet_key"]): row for row in collection_rows}
    stored_active_id = str(active_row["pet_key"]) if active_row else None
    active_owned = stored_active_id in collection if stored_active_id else False
    active_id = stored_active_id if active_owned else None

    spirits: list[dict[str, Any]] = []
    for spirit_id in CANONICAL_SPIRIT_IDS:
        row = active_row if active_id == spirit_id else collection.get(spirit_id)
        owned = spirit_id in collection
        level = max(1, int(row["level"] or 1)) if row and owned else None
        stage = stage_for_level(level) if level is not None else None
        spirits.append(
            {
                "spirit_id": spirit_id,
                "slot": CANONICAL_SPIRIT_CATALOG[spirit_id]["slot"],
                "owned": owned,
                "active": active_id == spirit_id,
                "progression_level": level,
                "progression_value": (
                    max(0, int(row["xp"] or 0)) if row and owned else None
                ),
                "evolution_stage": stage,
                "evolution_eligible": bool(level is not None and level >= 25),
                "effect_profile_id": None,
                "effect_policy_version": None,
                "enabled": True,
                "source_operation_id": None,
            }
        )

    return {
        "canonical_spirit_count": len(CANONICAL_SPIRIT_IDS),
        "active_spirit_id": active_id,
        "ownership_validated": bool(not stored_active_id or active_owned),
        "single_active_spirit": True,
        "spirits": spirits,
        "source": "pet_collection_with_user_pets_active_projection",
        "presentation_manifest_is_ownership_authority": False,
    }


def build_b022_active_spirit_projection(conn: Any, user_id: int) -> dict[str, Any]:
    """Return an authenticated server projection for the post-judge adapter.

    This is an internal read contract, not the client-facing status payload.
    An orphaned active row is returned as invalid and disabled so a future
    B022 caller cannot treat a presentation response as combat authority.
    """

    projection = build_spirit_projection(conn, user_id)
    active_id = projection["active_spirit_id"]
    active = next(
        (spirit for spirit in projection["spirits"] if spirit["spirit_id"] == active_id),
        None,
    )
    valid = bool(
        projection["ownership_validated"]
        and active_id
        and active
        and active["owned"]
        and active["active"]
    )
    if not valid:
        return {
            "active_spirit_id": None,
            "ownership_validated": False,
            "evolution_stage": None,
            "progression_level": None,
            "effect_profile_id": None,
            "effect_policy_version": None,
            "enabled": False,
            "source": "server_transactional_spirit_projection",
        }
    return {
        "active_spirit_id": active["spirit_id"],
        "ownership_validated": True,
        "evolution_stage": active["evolution_stage"],
        "progression_level": active["progression_level"],
        "effect_profile_id": active["effect_profile_id"],
        "effect_policy_version": active["effect_policy_version"],
        "enabled": bool(active["enabled"]),
        "source": "server_transactional_spirit_projection",
    }


__all__ = [
    "CANONICAL_SPIRIT_CATALOG",
    "CANONICAL_SPIRIT_IDS",
    "SPIRIT_STAGE_VALUES",
    "SPIRIT_UNLOCK_LEVELS",
    "build_b022_active_spirit_projection",
    "build_spirit_projection",
    "stage_for_level",
    "validate_catalog",
    "validate_server_spirit_id",
]
