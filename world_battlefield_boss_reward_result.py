"""Pure F018 result shell for an accepted Battlefield Boss milestone.

F017 is the authoritative handoff: it has already applied F014 validation
and delegated the durable write to F015.  F018 converts that detached outcome
into the result shape a future route can present or pass to a later, approved
reward layer.

The current source has no dedicated, authoritative Battlefield Boss reward
definition.  Therefore this version deliberately reports reward content as
unavailable and emits no currency, experience, item, or drop values.  It does
not access a database, call a route, or apply World policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from world_battlefield_boss_orchestrator import (
    CONFLICT,
    RECORDED,
    REJECTED,
    REPLAYED,
    BattlefieldBossMilestoneOrchestrationResult,
)


F018_RESULT_CONTRACT_VERSION: Final[str] = (
    "F018_BATTLEFIELD_BOSS_MILESTONE_REWARD_RESULT_V1"
)
F018_REWARD_CONTENT_AUTHORITY_MISSING: Final[bool] = True
REWARD_CONTENT_AUTHORITY_MISSING: Final[bool] = True
REWARD_CONTENT_AUTHORITY_MISSING_STATUS: Final[str] = (
    "REWARD_CONTENT_AUTHORITY_MISSING"
)
_STATUSES: Final[frozenset[str]] = frozenset(
    {RECORDED, REPLAYED, CONFLICT, REJECTED}
)


@dataclass(frozen=True, slots=True)
class BattlefieldBossMilestoneRewardResult:
    """Detached milestone status with an explicit empty reward contract."""

    contract_version: str
    status: str
    milestone_status: str
    reward_status: str
    reward_content_authority_missing: bool
    user_id: int | None
    settlement_id: str | None
    zone_key: str | None
    monster_id: str | None
    encounter_operation_id: str | None
    recorded: bool
    replayed: bool
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.contract_version != F018_RESULT_CONTRACT_VERSION:
            raise ValueError("unsupported F018 result contract")
        if self.status not in _STATUSES:
            raise ValueError(f"unsupported F018 result status: {self.status}")
        if self.milestone_status != self.status:
            raise ValueError("milestone_status must mirror status")
        if self.reward_status != REWARD_CONTENT_AUTHORITY_MISSING_STATUS:
            raise ValueError("F018 has no authorized reward status")
        if self.reward_content_authority_missing is not True:
            raise ValueError("F018 must fail closed without reward authority")
        if type(self.recorded) is not bool or type(self.replayed) is not bool:
            raise ValueError("recorded and replayed must be booleans")
        if self.status == RECORDED and not self.recorded:
            raise ValueError("RECORDED requires recorded=True")
        if self.status == REPLAYED and not self.replayed:
            raise ValueError("REPLAYED requires replayed=True")
        if self.status in {CONFLICT, REJECTED} and (self.recorded or self.replayed):
            raise ValueError("rejected outcomes cannot be recorded or replayed")


def _context(
    milestone: Any,
) -> dict[str, Any]:
    return {
        "user_id": getattr(milestone, "user_id", None),
        "settlement_id": getattr(milestone, "settlement_id", None),
        "zone_key": getattr(milestone, "zone_key", None),
        "monster_id": getattr(milestone, "monster_id", None),
        "encounter_operation_id": getattr(
            milestone,
            "encounter_operation_id",
            None,
        ),
    }


def _rejected(
    milestone: Any,
    error_code: str,
) -> BattlefieldBossMilestoneRewardResult:
    context = _context(milestone)
    return BattlefieldBossMilestoneRewardResult(
        contract_version=F018_RESULT_CONTRACT_VERSION,
        status=REJECTED,
        milestone_status=REJECTED,
        reward_status=REWARD_CONTENT_AUTHORITY_MISSING_STATUS,
        reward_content_authority_missing=REWARD_CONTENT_AUTHORITY_MISSING,
        user_id=context["user_id"],
        settlement_id=context["settlement_id"],
        zone_key=context["zone_key"],
        monster_id=context["monster_id"],
        encounter_operation_id=context["encounter_operation_id"],
        recorded=False,
        replayed=False,
        error_code=error_code,
    )


def build_battlefield_boss_milestone_reward_result(
    milestone: BattlefieldBossMilestoneOrchestrationResult,
) -> BattlefieldBossMilestoneRewardResult:
    """Convert one accepted F017 outcome into the F018 result shell.

    F017's ``RECORDED`` and ``REPLAYED`` outcomes are already backed by the
    F015 projection.  ``CONFLICT`` and ``REJECTED`` are propagated without
    manufacturing any reward result.  Raw mappings or other objects cannot
    cross this boundary.
    """

    if type(milestone) is not BattlefieldBossMilestoneOrchestrationResult:
        return _rejected(milestone, "MILESTONE_RESULT_TYPE_REQUIRED")

    if milestone.status not in _STATUSES:
        return _rejected(milestone, "UNSUPPORTED_MILESTONE_STATUS")

    return BattlefieldBossMilestoneRewardResult(
        contract_version=F018_RESULT_CONTRACT_VERSION,
        status=milestone.status,
        milestone_status=milestone.status,
        reward_status=REWARD_CONTENT_AUTHORITY_MISSING_STATUS,
        reward_content_authority_missing=REWARD_CONTENT_AUTHORITY_MISSING,
        user_id=milestone.user_id,
        settlement_id=milestone.settlement_id,
        zone_key=milestone.zone_key,
        monster_id=milestone.monster_id,
        encounter_operation_id=milestone.encounter_operation_id,
        recorded=milestone.recorded,
        replayed=milestone.replayed,
        error_code=milestone.error_code,
    )


__all__ = [
    "BattlefieldBossMilestoneRewardResult",
    "F018_REWARD_CONTENT_AUTHORITY_MISSING",
    "F018_RESULT_CONTRACT_VERSION",
    "REWARD_CONTENT_AUTHORITY_MISSING",
    "REWARD_CONTENT_AUTHORITY_MISSING_STATUS",
    "build_battlefield_boss_milestone_reward_result",
]
