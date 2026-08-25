"""Route-independent F017 orchestration for Battlefield Boss milestones.

This module composes the accepted F012 contract, F014 validation/binding, and
F015 projection service.  It accepts only trusted typed handoffs from the
caller; it does not authenticate requests, select Monsters, settle combat, or
apply any World policy.

The caller owns the surrounding transaction.  This service never commits or
rolls back and never writes SQL directly.  Expected input rejection and an
F015 evidence conflict are represented by a detached result so a future E
route can handle them without reimplementing the F boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from world_battlefield_boss_milestone import (
    MilestoneProjectionConflict,
    MilestoneProjectionValidationError,
    record_battlefield_boss_defeated_fact,
)
from world_monster_boss_adapter import (
    BattlefieldBossAdapterError,
    ServerBattlefieldBossSelection,
    ServerMonsterSettlementEvidence,
    bind_battlefield_boss_selection,
    build_battlefield_boss_defeated_fact,
    build_f010_battlefield_boss_selector_call,
)
from world_monster_boundary_contract import (
    BattlefieldBossEncounterIntent,
)


F017_ORCHESTRATOR_VERSION: Final[str] = (
    "F017_BATTLEFIELD_BOSS_MILESTONE_ORCHESTRATOR_V1"
)
RECORDED: Final[str] = "RECORDED"
REPLAYED: Final[str] = "REPLAYED"
CONFLICT: Final[str] = "CONFLICT"
REJECTED: Final[str] = "REJECTED"
_STATUSES: Final[frozenset[str]] = frozenset(
    {RECORDED, REPLAYED, CONFLICT, REJECTED}
)


class BattlefieldBossOrchestrationError(RuntimeError):
    """Base class for F017 service failures outside expected outcomes."""


class BattlefieldBossOrchestrationValidationError(
    ValueError, BattlefieldBossOrchestrationError
):
    """Retained for callers that prefer an explicit validation exception."""


@dataclass(frozen=True, slots=True)
class BattlefieldBossMilestoneOrchestrationResult:
    """Detached F017 outcome with identifiers only, never policy decisions."""

    status: str
    user_id: int | None
    settlement_id: str | None
    zone_key: str | None
    monster_id: str | None
    encounter_operation_id: str | None
    recorded: bool
    replayed: bool
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.status not in _STATUSES:
            raise ValueError(f"unsupported F017 result status: {self.status}")
        if type(self.recorded) is not bool or type(self.replayed) is not bool:
            raise ValueError("recorded and replayed must be booleans")
        if self.status == RECORDED and not self.recorded:
            raise ValueError("RECORDED requires recorded=True")
        if self.status == REPLAYED and not self.replayed:
            raise ValueError("REPLAYED requires replayed=True")
        if self.status in {CONFLICT, REJECTED} and (self.recorded or self.replayed):
            raise ValueError("rejected outcomes cannot be recorded or replayed")


def _known(obj: Any, field: str) -> Any:
    return getattr(obj, field, None)


def _context(
    authenticated_user_id: Any,
    intent: Any,
    selection: Any,
    settlement: Any,
) -> dict[str, Any]:
    """Collect non-authoritative identifiers for a detached error result."""

    return {
        "user_id": authenticated_user_id
        if type(authenticated_user_id) is int
        else _known(intent, "user_id"),
        "settlement_id": _known(settlement, "settlement_id"),
        "zone_key": _known(intent, "zone_key") or _known(selection, "zone_key"),
        "monster_id": _known(selection, "monster_id")
        or _known(settlement, "monster_id"),
        "encounter_operation_id": _known(intent, "intent_operation_id")
        or _known(selection, "encounter_operation_id")
        or _known(settlement, "encounter_operation_id"),
    }


def _result(
    *,
    status: str,
    context: dict[str, Any],
    recorded: bool,
    replayed: bool,
    error_code: str | None = None,
) -> BattlefieldBossMilestoneOrchestrationResult:
    return BattlefieldBossMilestoneOrchestrationResult(
        status=status,
        user_id=context["user_id"],
        settlement_id=context["settlement_id"],
        zone_key=context["zone_key"],
        monster_id=context["monster_id"],
        encounter_operation_id=context["encounter_operation_id"],
        recorded=recorded,
        replayed=replayed,
        error_code=error_code,
    )


def orchestrate_battlefield_boss_milestone(
    conn: Any,
    *,
    authenticated_user_id: int,
    intent: BattlefieldBossEncounterIntent,
    selection: ServerBattlefieldBossSelection,
    settlement: ServerMonsterSettlementEvidence,
    fact_replayed: bool = False,
    created_at: Any = None,
) -> BattlefieldBossMilestoneOrchestrationResult:
    """Validate, bind, and record one trusted Battlefield Boss milestone.

    ``authenticated_user_id`` is supplied by the caller's authenticated
    server boundary and must agree with every typed F012/F014 handoff.  The
    selection and settlement objects must already be server-bound typed
    evidence; raw network mappings are rejected by F014.

    The function invokes F014 for all identity/operation/commit validation and
    invokes F015 for the only projection mutation.  It intentionally returns
    no progression decision.  A schema or database error is propagated to the
    caller so the caller can choose the transaction outcome.
    """

    context = _context(
        authenticated_user_id,
        intent,
        selection,
        settlement,
    )
    if type(authenticated_user_id) is not int or authenticated_user_id <= 0:
        return _result(
            status=REJECTED,
            context=context,
            recorded=False,
            replayed=False,
            error_code="INVALID_AUTHENTICATED_USER",
        )

    try:
        for trusted in (intent, selection, settlement):
            if _known(trusted, "user_id") != authenticated_user_id:
                return _result(
                    status=REJECTED,
                    context=context,
                    recorded=False,
                    replayed=False,
                    error_code="AUTHENTICATED_USER_MISMATCH",
                )

        selector_call = build_f010_battlefield_boss_selector_call(intent)
        binding = bind_battlefield_boss_selection(selector_call, selection)
        fact = build_battlefield_boss_defeated_fact(
            binding,
            settlement,
            replayed=fact_replayed,
        )
        stored = record_battlefield_boss_defeated_fact(
            conn,
            fact,
            created_at=created_at,
        )
    except MilestoneProjectionConflict:
        return _result(
            status=CONFLICT,
            context=context,
            recorded=False,
            replayed=False,
            error_code="CHANGED_AUTHORITATIVE_PAYLOAD",
        )
    except (BattlefieldBossAdapterError, MilestoneProjectionValidationError) as exc:
        return _result(
            status=REJECTED,
            context=context,
            recorded=False,
            replayed=False,
            error_code=getattr(exc, "code", "VALIDATION_REJECTED"),
        )

    return _result(
        status=RECORDED if stored.recorded else REPLAYED,
        context={
            "user_id": stored.user_id,
            "settlement_id": stored.settlement_id,
            "zone_key": stored.zone_key,
            "monster_id": stored.monster_id,
            "encounter_operation_id": stored.encounter_operation_id,
        },
        recorded=stored.recorded,
        replayed=stored.replayed,
    )


__all__ = [
    "BATTLEFIELD_BOSS_MILESTONE_ORCHESTRATOR_V1",
    "BattlefieldBossMilestoneOrchestrationResult",
    "BattlefieldBossOrchestrationError",
    "BattlefieldBossOrchestrationValidationError",
    "CONFLICT",
    "F017_ORCHESTRATOR_VERSION",
    "RECORDED",
    "REJECTED",
    "REPLAYED",
    "orchestrate_battlefield_boss_milestone",
]


BATTLEFIELD_BOSS_MILESTONE_ORCHESTRATOR_V1: Final[str] = (
    F017_ORCHESTRATOR_VERSION
)
