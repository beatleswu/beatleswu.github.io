"""E049 request-local Battlefield MonsterCatalog shadow integration.

This module is a bounded observation boundary for the live Battlefield
callers.  It invokes the E047 diagnostic caller beside an already-resolved
F008 profile, stores only deterministic records in a caller-provided
request-local sink, and never writes persistence, emits telemetry, or returns
catalog values to gameplay.  The legacy F003/F004/F008 result remains the only
active result throughout E049.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, MutableSequence

from battlefield_monster_catalog_shadow_caller import (
    BATTLEFIELD_BOSS,
    BATTLEFIELD_NORMAL,
    MATCH,
    SHADOW_CALLER_CONSUMER,
    SHADOW_RUN_ID,
    observe_battlefield_encounter,
)


SHADOW_RUNTIME_VERSION = "e049.battlefield-shadow-runtime.v1"
SHADOW_RUNTIME_CONSUMER = "e049.battlefield.shadow_runtime"

PHASE_STATUS_READ_ONLY_PROJECTION = "STATUS_READ_ONLY_PROJECTION"
PHASE_NORMAL_BATTLEFIELD_CONSUMERS = "NORMAL_BATTLEFIELD_CONSUMERS"
PHASE_BOSS_BATTLEFIELD_CONSUMERS = "BOSS_BATTLEFIELD_CONSUMERS"
PHASE_MUTATION_AND_SETTLEMENT = (
    "MUTATION_AND_SETTLEMENT_PATH_SHADOW_COMPARISON"
)
SHADOW_PHASES = (
    PHASE_STATUS_READ_ONLY_PROJECTION,
    PHASE_NORMAL_BATTLEFIELD_CONSUMERS,
    PHASE_BOSS_BATTLEFIELD_CONSUMERS,
    PHASE_MUTATION_AND_SETTLEMENT,
)

PATH_ROLE_NONE = "NONE"
PATH_ROLE_MUTATION = "MUTATION"
PATH_ROLE_SETTLEMENT = "SETTLEMENT"
SHADOW_PATH_ROLES = (
    PATH_ROLE_NONE,
    PATH_ROLE_MUTATION,
    PATH_ROLE_SETTLEMENT,
)

SHADOW_OBSERVATION_ERROR = "SHADOW_OBSERVATION_ERROR"
SHADOW_DIAGNOSTIC_DRIFT_TYPES = (
    MATCH,
    "IDENTITY_DRIFT",
    "CONTEXT_MISMATCH",
    "PROFILE_REF_DRIFT",
    "PROFILE_VERSION_DRIFT",
    "HP_DRIFT",
    "ATK_DRIFT",
    "UNKNOWN_MONSTER",
    "UNKNOWN_PROFILE",
    "MISSING_PROFILE",
)
SHADOW_DIAGNOSTIC_MATRIX_COMPLETE = True

CATALOG_CAN_MUTATE_PLAYER_STATE = False
CATALOG_CAN_SETTLE_REWARD = False
CATALOG_CAN_CHANGE_COMBAT_RESULT = False
CATALOG_MUTATION_EXECUTED = False
CATALOG_SETTLEMENT_EXECUTED = False
PERMANENT_LEGACY_FALLBACK_PATH = False
TIME_BOXED_COMPATIBILITY_BRIDGE = False
PLAYER_PII_LOGGED = False
PRODUCTION_TELEMETRY_ADDED = False
SHADOW_RECORDS_DETERMINISTIC = True


def _explicit_runtime_id(current_runtime: Mapping[str, Any] | None) -> str | None:
    values = dict(current_runtime or {})
    value = values.get("monster_id")
    if value not in (None, ""):
        return str(value)
    return None


def _safe_error_record(
    *,
    phase: str,
    path_role: str,
    context: Any,
    current_runtime: Mapping[str, Any] | None,
    drift_type: str = SHADOW_OBSERVATION_ERROR,
) -> dict[str, Any]:
    """Return deterministic, non-PII failure evidence for the shadow only."""

    context_key = str(context).strip() if context not in (None, "") else None
    return {
        "timestamp_or_run_id": SHADOW_RUN_ID,
        "runtime_artifact_version": SHADOW_RUNTIME_VERSION,
        "consumer": SHADOW_RUNTIME_CONSUMER,
        "source_consumer": SHADOW_CALLER_CONSUMER,
        "phase": phase,
        "path_role": path_role,
        "zone": None,
        "encounter_class": None,
        "current_monster_id": _explicit_runtime_id(current_runtime),
        "shadow_monster_id": None,
        "current_profile": None,
        "shadow_profile": None,
        "current_hp": None,
        "shadow_hp": None,
        "current_atk": None,
        "shadow_atk": None,
        "current_context": context_key,
        "shadow_context": None,
        "status": "FAIL",
        "drift_type": drift_type,
        "error": "shadow_observation_error",
        "active_result_unchanged": True,
        "player_visible": False,
        "mutation_capable": False,
    }


def observe_battlefield_shadow_phase(
    current_runtime: Mapping[str, Any] | None,
    *,
    context: str,
    phase: str,
    path_role: str = PATH_ROLE_NONE,
    zone: str | None = None,
    current_profile: Any | None = None,
) -> dict[str, Any]:
    """Observe one caller phase without changing the active runtime result.

    The input is an already server-resolved identity/profile tuple.  The
    function returns one structured record and performs no persistence or
    logging.  Invalid phase/role and observer failures become deterministic
    shadow-only records rather than exceptions that could affect gameplay.
    """

    if phase not in SHADOW_PHASES or path_role not in SHADOW_PATH_ROLES:
        return _safe_error_record(
            phase=phase,
            path_role=path_role,
            context=context,
            current_runtime=current_runtime,
        )
    try:
        diagnostic = observe_battlefield_encounter(
            current_runtime,
            context=context,
            zone=zone,
            current_profile=current_profile,
        ).as_dict()
    except Exception:
        # The shadow must never make the active F008 path fail.  Do not copy
        # exception text into a record: it can contain unbounded input data.
        return _safe_error_record(
            phase=phase,
            path_role=path_role,
            context=context,
            current_runtime=current_runtime,
        )

    diagnostic.update(
        {
            "runtime_artifact_version": SHADOW_RUNTIME_VERSION,
            "consumer": SHADOW_RUNTIME_CONSUMER,
            "source_consumer": SHADOW_CALLER_CONSUMER,
            "phase": phase,
            "path_role": path_role,
            "active_result_unchanged": True,
            "player_visible": False,
            "mutation_capable": False,
        }
    )
    return diagnostic


def append_battlefield_shadow_observation(
    sink: MutableSequence[Mapping[str, Any]] | None,
    current_runtime: Mapping[str, Any] | None,
    *,
    context: str,
    phase: str,
    path_role: str = PATH_ROLE_NONE,
    zone: str | None = None,
    current_profile: Any | None = None,
) -> dict[str, Any] | None:
    """Append one bounded observation to a caller-owned request-local sink."""

    if sink is None:
        return None
    record = observe_battlefield_shadow_phase(
        current_runtime,
        context=context,
        phase=phase,
        path_role=path_role,
        zone=zone,
        current_profile=current_profile,
    )
    sink.append(record)
    return record


class BattlefieldShadowCollector:
    """Small in-memory collector for tests or one request lifecycle only."""

    def __init__(self) -> None:
        self._records: list[Mapping[str, Any]] = []

    @property
    def records(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self._records)

    def observe(
        self,
        current_runtime: Mapping[str, Any] | None,
        *,
        context: str,
        phase: str,
        path_role: str = PATH_ROLE_NONE,
        zone: str | None = None,
        current_profile: Any | None = None,
    ) -> Mapping[str, Any]:
        record = append_battlefield_shadow_observation(
            self._records,
            current_runtime,
            context=context,
            phase=phase,
            path_role=path_role,
            zone=zone,
            current_profile=current_profile,
        )
        assert record is not None
        return record

    def artifact(self) -> dict[str, Any]:
        records = [dict(record) for record in self._records]
        drift_count = sum(record.get("drift_type") != MATCH for record in records)
        return {
            "artifact_version": SHADOW_RUNTIME_VERSION,
            "timestamp_or_run_id": SHADOW_RUN_ID,
            "consumer": SHADOW_RUNTIME_CONSUMER,
            "status": "PASS" if drift_count == 0 else "FAIL",
            "drift_count": drift_count,
            "records": records,
        }

    def render_json(self) -> str:
        return json.dumps(
            self.artifact(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )


def build_shadow_runtime_artifact(
    records: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build deterministic output from a bounded caller-owned record list."""

    collector = BattlefieldShadowCollector()
    collector._records.extend(dict(record) for record in records)
    return collector.artifact()


def render_shadow_runtime_json(
    records: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
) -> str:
    collector = BattlefieldShadowCollector()
    collector._records.extend(dict(record) for record in records)
    return collector.render_json()


__all__ = [
    "BATTLEFIELD_BOSS",
    "BATTLEFIELD_NORMAL",
    "CATALOG_CAN_CHANGE_COMBAT_RESULT",
    "CATALOG_CAN_MUTATE_PLAYER_STATE",
    "CATALOG_CAN_SETTLE_REWARD",
    "CATALOG_MUTATION_EXECUTED",
    "CATALOG_SETTLEMENT_EXECUTED",
    "BattlefieldShadowCollector",
    "PATH_ROLE_MUTATION",
    "PATH_ROLE_NONE",
    "PATH_ROLE_SETTLEMENT",
    "PERMANENT_LEGACY_FALLBACK_PATH",
    "PHASE_BOSS_BATTLEFIELD_CONSUMERS",
    "PHASE_MUTATION_AND_SETTLEMENT",
    "PHASE_NORMAL_BATTLEFIELD_CONSUMERS",
    "PHASE_STATUS_READ_ONLY_PROJECTION",
    "PLAYER_PII_LOGGED",
    "PRODUCTION_TELEMETRY_ADDED",
    "SHADOW_DIAGNOSTIC_DRIFT_TYPES",
    "SHADOW_DIAGNOSTIC_MATRIX_COMPLETE",
    "SHADOW_OBSERVATION_ERROR",
    "SHADOW_PATH_ROLES",
    "SHADOW_PHASES",
    "SHADOW_RECORDS_DETERMINISTIC",
    "SHADOW_RUNTIME_CONSUMER",
    "SHADOW_RUNTIME_VERSION",
    "TIME_BOXED_COMPATIBILITY_BRIDGE",
    "append_battlefield_shadow_observation",
    "build_shadow_runtime_artifact",
    "observe_battlefield_shadow_phase",
    "render_shadow_runtime_json",
]
