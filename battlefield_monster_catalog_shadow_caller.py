"""E047 bounded Battlefield-only shadow caller.

The caller evaluates the existing F003/F008 Battlefield authority beside the
candidate E045/E046 catalog.  It is a pure diagnostic helper: no application
module imports it, it does not choose an encounter, and it cannot write
combat, reward, progression, telemetry, or persistence state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from monster_catalog_foundation import (
    BATTLEFIELD_BOSS,
    BATTLEFIELD_NORMAL,
    CANONICAL_MONSTER_CATALOG,
    MonsterCatalog,
    UnknownContextError,
    UnknownMonsterError,
    UnknownProfileError,
    MissingCombatProfileError,
    get_monster,
)
from monster_catalog_shadow_adapter import (
    ShadowIdentityInputError,
    compare_runtime_encounter,
)
from monster_combat_profiles import (
    MonsterCombatProfileError,
    resolve_monster_combat_profile,
)
from monster_identity import CANONICAL_MONSTER_IDENTITY_REGISTRY


SHADOW_CALLER_VERSION = "e047.battlefield-shadow.v1"
SHADOW_CALLER_CONSUMER = "e047.battlefield.shadow_caller"
SHADOW_RUN_ID = SHADOW_CALLER_VERSION

SHADOW_RESULT_CAN_MUTATE_GAMEPLAY = False
SHADOW_RESULT_CAN_SELECT_MONSTER = False
SHADOW_RESULT_CAN_SET_HP_ATK = False
SHADOW_FAILURE_CHANGES_ACTIVE_RESULT = False
SHADOW_CALLER_ACTIVE_GAMEPLAY_AUTHORITY = False
SHADOW_CALLER_PLAYER_VISIBLE = False
SHADOW_CALLER_MUTATION_CAPABLE = False
SHADOW_CALLER_SIDE_EFFECTS = "NONE"
PRODUCTION_TELEMETRY_ADDED = False
SHADOW_DIAGNOSTIC_ARTIFACT_CREATED = True
SHADOW_DIAGNOSTIC_DETERMINISTIC = True
F009_ACTIVE_CALLER_INTEGRATED = False
F009_ENABLED = False
ADVENTURE_ACTIVE_CALLER_INTEGRATED = False
LORD_ACTIVE_CALLER_INTEGRATED = False
WORLD_ACTIVE_CALLER_INTEGRATED = False
F009_SELECTION_AUTHORITY_CHANGED = False
ADVENTURE_PROFILE_AUTO_INHERITS_BATTLEFIELD = False
LORD_NUMERIC_PROFILE_CREATED = False
COMMON_RARE_ELITE_ENABLED = False
COMBAT_CLASS_FREQUENCY_COUPLED = False
ART002_GAMEPLAY_AUTHORITY = False
F034_PLANNING_ZONE_USED_FOR_GAMEPLAY = False
UNKNOWN_MONSTER_FAIL_CLOSED = True
UNKNOWN_PROFILE_FAIL_CLOSED = True
MISSING_PROFILE_FAIL_CLOSED = True

MATCH = "MATCH"
IDENTITY_DRIFT = "IDENTITY_DRIFT"
PROFILE_REF_DRIFT = "PROFILE_REF_DRIFT"
HP_DRIFT = "HP_DRIFT"
ATK_DRIFT = "ATK_DRIFT"
MISSING_PROFILE = "MISSING_PROFILE"
UNKNOWN_MONSTER = "UNKNOWN_MONSTER"
UNKNOWN_PROFILE = "UNKNOWN_PROFILE"
CONTEXT_MISMATCH = "CONTEXT_MISMATCH"

SHADOW_DRIFT_TYPES = (
    MATCH,
    IDENTITY_DRIFT,
    PROFILE_REF_DRIFT,
    HP_DRIFT,
    ATK_DRIFT,
    MISSING_PROFILE,
    UNKNOWN_MONSTER,
    UNKNOWN_PROFILE,
    CONTEXT_MISMATCH,
)
SHADOW_DRIFT_TYPES_EXPLICIT = True
_BATTLEFIELD_CONTEXTS = frozenset((BATTLEFIELD_NORMAL, BATTLEFIELD_BOSS))


@dataclass(frozen=True)
class BattlefieldShadowDiagnostic:
    """One JSON-compatible observation with no mutation capability."""

    timestamp_or_run_id: str
    consumer: str
    zone: str | None
    encounter_class: str | None
    current_monster_id: str | None
    shadow_monster_id: str | None
    current_profile: Mapping[str, Any] | None
    shadow_profile: Mapping[str, Any] | None
    current_hp: int | None
    shadow_hp: int | None
    current_atk: int | None
    shadow_atk: int | None
    status: str
    drift_type: str
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the stable machine-readable diagnostic record."""

        return {
            "timestamp_or_run_id": self.timestamp_or_run_id,
            "consumer": self.consumer,
            "zone": self.zone,
            "encounter_class": self.encounter_class,
            "current_monster_id": self.current_monster_id,
            "shadow_monster_id": self.shadow_monster_id,
            "current_profile": (
                dict(self.current_profile) if self.current_profile is not None else None
            ),
            "shadow_profile": (
                dict(self.shadow_profile) if self.shadow_profile is not None else None
            ),
            "current_hp": self.current_hp,
            "shadow_hp": self.shadow_hp,
            "current_atk": self.current_atk,
            "shadow_atk": self.shadow_atk,
            "status": self.status,
            "drift_type": self.drift_type,
            "error": self.error,
        }


def _reported_monster_id(current_runtime: Mapping[str, Any]) -> str | None:
    """Read an explicit ID or F003 slot for diagnostics, without guessing."""

    explicit_id = current_runtime.get("monster_id")
    if explicit_id not in (None, ""):
        return str(explicit_id)
    slot = current_runtime.get("roster_slot")
    if slot in (None, ""):
        return None
    try:
        identity = CANONICAL_MONSTER_IDENTITY_REGISTRY.by_roster_slot.get(int(slot))
    except (TypeError, ValueError):
        return None
    return identity.monster_id if identity is not None else None


def _profile_view(profile: Any) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "version": profile.profile_version,
        "source": profile.stat_source,
    }


def _shadow_profile_view(comparison: Any) -> dict[str, Any] | None:
    if comparison.foundation_profile_id is None:
        return None
    return {
        "profile_id": comparison.foundation_profile_id,
        "version": comparison.foundation_profile_version,
    }


def _failure(
    *,
    context: str | None,
    zone: str | None,
    encounter_class: str | None,
    current_monster_id: str | None,
    drift_type: str,
    error: str,
    current_profile: Mapping[str, Any] | None = None,
    current_hp: int | None = None,
    current_atk: int | None = None,
) -> BattlefieldShadowDiagnostic:
    return BattlefieldShadowDiagnostic(
        timestamp_or_run_id=SHADOW_RUN_ID,
        consumer=SHADOW_CALLER_CONSUMER,
        zone=zone,
        encounter_class=encounter_class,
        current_monster_id=current_monster_id,
        shadow_monster_id=None,
        current_profile=current_profile,
        shadow_profile=None,
        current_hp=current_hp,
        shadow_hp=None,
        current_atk=current_atk,
        shadow_atk=None,
        status="FAIL",
        drift_type=drift_type,
        error=error,
    )


def classify_shadow_drift(
    *,
    current_monster_id: str | None,
    shadow_monster_id: str | None,
    current_context: str | None,
    shadow_context: str | None,
    current_profile_id: str | None,
    shadow_profile_id: str | None,
    current_hp: int | None,
    shadow_hp: int | None,
    current_atk: int | None,
    shadow_atk: int | None,
) -> str:
    """Classify the first explicit difference; never fall back silently."""

    if current_monster_id != shadow_monster_id:
        return IDENTITY_DRIFT
    if current_context != shadow_context:
        return CONTEXT_MISMATCH
    if shadow_profile_id is None:
        return MISSING_PROFILE
    if current_profile_id != shadow_profile_id:
        return PROFILE_REF_DRIFT
    if current_hp != shadow_hp:
        return HP_DRIFT
    if current_atk != shadow_atk:
        return ATK_DRIFT
    return MATCH


def observe_battlefield_encounter(
    current_runtime: Mapping[str, Any] | None,
    *,
    context: Any,
    zone: str | None = None,
    catalog: MonsterCatalog = CANONICAL_MONSTER_CATALOG,
) -> BattlefieldShadowDiagnostic:
    """Evaluate one current Battlefield result beside the E046 adapter.

    Current HP/ATK come from the active F008 resolver, not from the caller's
    raw fields.  The input is copied and is never modified.  All resolution
    failures become typed diagnostic records, leaving the active result alone.
    """

    values = dict(current_runtime or {})
    context_key = str(context).strip() if context not in (None, "") else None
    reported_id = _reported_monster_id(values)
    if context_key not in _BATTLEFIELD_CONTEXTS:
        return _failure(
            context=context_key,
            zone=zone,
            encounter_class=None,
            current_monster_id=reported_id,
            drift_type=CONTEXT_MISMATCH,
            error=f"unsupported Battlefield shadow context: {context!r}",
        )

    entry = get_monster(reported_id, catalog=catalog) if reported_id else None
    identity = (
        CANONICAL_MONSTER_IDENTITY_REGISTRY.by_id.get(reported_id)
        if reported_id
        else None
    )
    if entry is None or identity is None:
        return _failure(
            context=context_key,
            zone=zone,
            encounter_class=None,
            current_monster_id=reported_id,
            drift_type=UNKNOWN_MONSTER,
            error="current Battlefield identity is not an exact catalog identity",
        )

    if context_key not in entry.context_eligibility:
        return _failure(
            context=context_key,
            zone=zone or entry.zone_eligibility[0],
            encounter_class=identity.encounter_class,
            current_monster_id=reported_id,
            drift_type=CONTEXT_MISMATCH,
            error=(
                f"{reported_id} is not eligible for shadow context {context_key}"
            ),
        )

    try:
        # F008 remains the current runtime stat authority.  This call is read
        # only and uses the explicit canonical ID, never presentation fields.
        current_profile = resolve_monster_combat_profile(
            {"monster_id": reported_id},
            context="LEGACY_BATTLEFIELD",
        )
    except MonsterCombatProfileError as error:
        return _failure(
            context=context_key,
            zone=zone or entry.zone_eligibility[0],
            encounter_class=identity.encounter_class,
            current_monster_id=reported_id,
            drift_type=MISSING_PROFILE,
            error=str(error),
        )

    try:
        comparison = compare_runtime_encounter(
            {
                "monster_id": reported_id,
                "current_hp": current_profile.max_hp,
                "current_atk": current_profile.attack,
            },
            context=context_key,
            catalog=catalog,
        )
    except UnknownMonsterError as error:
        drift_type = UNKNOWN_MONSTER
        message = str(error)
        shadow_profile = None
    except UnknownProfileError as error:
        drift_type = UNKNOWN_PROFILE
        message = str(error)
        shadow_profile = None
    except MissingCombatProfileError as error:
        drift_type = MISSING_PROFILE
        message = str(error)
        shadow_profile = None
    except (ShadowIdentityInputError, UnknownContextError) as error:
        drift_type = CONTEXT_MISMATCH if isinstance(error, UnknownContextError) else UNKNOWN_MONSTER
        message = str(error)
        shadow_profile = None
    else:
        shadow_profile = _shadow_profile_view(comparison)
        drift_type = classify_shadow_drift(
            current_monster_id=current_profile.canonical_monster_id,
            shadow_monster_id=comparison.foundation_monster_id,
            current_context=context_key,
            shadow_context=comparison.foundation_context,
            current_profile_id=current_profile.profile_id,
            shadow_profile_id=comparison.foundation_profile_id,
            current_hp=current_profile.max_hp,
            shadow_hp=comparison.foundation_hp,
            current_atk=current_profile.attack,
            shadow_atk=comparison.foundation_atk,
        )
        message = None

    if message is not None:
        return _failure(
            context=context_key,
            zone=zone or entry.zone_eligibility[0],
            encounter_class=identity.encounter_class,
            current_monster_id=reported_id,
            drift_type=drift_type,
            error=message,
            current_profile=_profile_view(current_profile),
            current_hp=current_profile.max_hp,
            current_atk=current_profile.attack,
        )

    status = "PASS" if drift_type == MATCH else "DRIFT"
    return BattlefieldShadowDiagnostic(
        timestamp_or_run_id=SHADOW_RUN_ID,
        consumer=SHADOW_CALLER_CONSUMER,
        zone=zone or entry.zone_eligibility[0],
        encounter_class=identity.encounter_class,
        current_monster_id=current_profile.canonical_monster_id,
        shadow_monster_id=comparison.foundation_monster_id,
        current_profile=_profile_view(current_profile),
        shadow_profile=shadow_profile,
        current_hp=current_profile.max_hp,
        shadow_hp=comparison.foundation_hp,
        current_atk=current_profile.attack,
        shadow_atk=comparison.foundation_atk,
        status=status,
        drift_type=drift_type,
        error=None,
    )


def observe_battlefield_shadow_matrix(
    *,
    catalog: MonsterCatalog = CANONICAL_MONSTER_CATALOG,
) -> tuple[BattlefieldShadowDiagnostic, ...]:
    """Observe the ten normal and ten Boss Battlefield catalog entries."""

    entries = tuple(
        entry
        for entry in catalog.entries
        if entry.context_eligibility
        and entry.context_eligibility[0] in _BATTLEFIELD_CONTEXTS
    )
    entries = tuple(
        sorted(
            entries,
            key=lambda item: (
                item.zone_eligibility[0],
                0 if item.encounter_class == "NORMAL" else 1,
                item.monster_id,
            ),
        )
    )
    return tuple(
        observe_battlefield_encounter(
            {"monster_id": entry.monster_id},
            context=entry.context_eligibility[0],
            zone=entry.zone_eligibility[0],
            catalog=catalog,
        )
        for entry in entries
    )


def build_shadow_diagnostic_artifact(
    *,
    catalog: MonsterCatalog = CANONICAL_MONSTER_CATALOG,
) -> dict[str, Any]:
    """Build deterministic JSON-compatible output without writing it anywhere."""

    records = observe_battlefield_shadow_matrix(catalog=catalog)
    drift_count = sum(record.drift_type != MATCH for record in records)
    return {
        "artifact_version": SHADOW_CALLER_VERSION,
        "timestamp_or_run_id": SHADOW_RUN_ID,
        "consumer": SHADOW_CALLER_CONSUMER,
        "status": "PASS" if drift_count == 0 else "FAIL",
        "drift_count": drift_count,
        "records": [record.as_dict() for record in records],
    }


def render_shadow_diagnostic_json(
    *,
    catalog: MonsterCatalog = CANONICAL_MONSTER_CATALOG,
) -> str:
    """Render the artifact deterministically for developer/test consumers."""

    return json.dumps(
        build_shadow_diagnostic_artifact(catalog=catalog),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = [
    "ADVENTURE_ACTIVE_CALLER_INTEGRATED",
    "ADVENTURE_PROFILE_AUTO_INHERITS_BATTLEFIELD",
    "ART002_GAMEPLAY_AUTHORITY",
    "ATK_DRIFT",
    "BATTLEFIELD_BOSS",
    "BATTLEFIELD_NORMAL",
    "COMMON_RARE_ELITE_ENABLED",
    "COMBAT_CLASS_FREQUENCY_COUPLED",
    "CONTEXT_MISMATCH",
    "F009_ACTIVE_CALLER_INTEGRATED",
    "F009_ENABLED",
    "F009_SELECTION_AUTHORITY_CHANGED",
    "F034_PLANNING_ZONE_USED_FOR_GAMEPLAY",
    "HP_DRIFT",
    "IDENTITY_DRIFT",
    "LORD_ACTIVE_CALLER_INTEGRATED",
    "LORD_NUMERIC_PROFILE_CREATED",
    "MATCH",
    "MISSING_PROFILE",
    "PRODUCTION_TELEMETRY_ADDED",
    "PROFILE_REF_DRIFT",
    "SHADOW_CALLER_ACTIVE_GAMEPLAY_AUTHORITY",
    "SHADOW_CALLER_CONSUMER",
    "SHADOW_CALLER_MUTATION_CAPABLE",
    "SHADOW_CALLER_PLAYER_VISIBLE",
    "SHADOW_CALLER_SIDE_EFFECTS",
    "SHADOW_CALLER_VERSION",
    "SHADOW_DIAGNOSTIC_ARTIFACT_CREATED",
    "SHADOW_DIAGNOSTIC_DETERMINISTIC",
    "SHADOW_DRIFT_TYPES",
    "SHADOW_DRIFT_TYPES_EXPLICIT",
    "SHADOW_RESULT_CAN_MUTATE_GAMEPLAY",
    "SHADOW_RESULT_CAN_SELECT_MONSTER",
    "SHADOW_RESULT_CAN_SET_HP_ATK",
    "SHADOW_FAILURE_CHANGES_ACTIVE_RESULT",
    "UNKNOWN_MONSTER",
    "UNKNOWN_PROFILE",
    "UNKNOWN_MONSTER_FAIL_CLOSED",
    "UNKNOWN_PROFILE_FAIL_CLOSED",
    "MISSING_PROFILE_FAIL_CLOSED",
    "WORLD_ACTIVE_CALLER_INTEGRATED",
    "BattlefieldShadowDiagnostic",
    "build_shadow_diagnostic_artifact",
    "classify_shadow_drift",
    "observe_battlefield_encounter",
    "observe_battlefield_shadow_matrix",
    "render_shadow_diagnostic_json",
]
