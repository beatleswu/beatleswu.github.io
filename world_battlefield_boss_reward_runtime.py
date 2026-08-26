"""F023 runtime adapter for the Battlefield Boss first-clear reward.

The authoritative Monster/World handoff is already represented by the
validated F012 ``BattlefieldBossDefeatedFact``.  This module composes that
fact with the F022 per-user/per-Zone entitlement and the existing
``player_wardrobe`` ownership writer supplied by the caller.

It deliberately does not import ``app.py`` or write wardrobe SQL itself.
The caller passes the authenticated user's existing wardrobe grant operation
(``grant_wardrobe_item(item_id, source)``).  The caller also owns the
transaction: entitlement, wardrobe ownership, and the existing D5A outbox
lineage either commit together or roll back together.

This is a route-independent adapter.  It does not decide World progression,
Lord state, Quest state, combat, or generic Monster rewards.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from event_outbox import append_event
from world_battlefield_boss_first_clear_entitlement import (
    ALREADY_CLAIMED,
    CONFLICT as ENTITLEMENT_CONFLICT,
    POLICY_VERSION,
    RECORDED,
    REPLAYED,
    BattlefieldBossFirstClearEntitlementResult,
    claim_battlefield_boss_first_clear_entitlement,
    reward_item_for_zone,
)
from world_monster_boundary_contract import BattlefieldBossDefeatedFact


F023_REWARD_RESULT_CONTRACT_VERSION: Final[str] = (
    "F023_BATTLEFIELD_BOSS_FIRST_CLEAR_REWARD_RUNTIME_V1"
)
FIRST_CLEAR_NEW_COSMETIC: Final[str] = "FIRST_CLEAR_NEW_COSMETIC"
FIRST_CLEAR_ALREADY_OWNED_NO_OP: Final[str] = (
    "FIRST_CLEAR_ALREADY_OWNED_NO_OP"
)
NOT_FIRST_CLEAR: Final[str] = "NOT_FIRST_CLEAR"
CONFLICT: Final[str] = "CONFLICT"
COSMETIC_OWNERSHIP_AUTHORITY: Final[str] = "player_wardrobe"
COSMETIC_GRANT_SOURCE: Final[str] = "battlefield_boss_first_clear"
_STATUSES: Final[frozenset[str]] = frozenset(
    {
        FIRST_CLEAR_NEW_COSMETIC,
        FIRST_CLEAR_ALREADY_OWNED_NO_OP,
        NOT_FIRST_CLEAR,
        CONFLICT,
    }
)


class BattlefieldBossRewardRuntimeError(RuntimeError):
    """Base class for F023 runtime-adapter failures."""


class BattlefieldBossRewardValidationError(
    ValueError,
    BattlefieldBossRewardRuntimeError,
):
    """A trusted fact or canonical ownership result failed validation."""


CosmeticGrantWriter = Callable[[str, str], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class BattlefieldBossFirstClearRewardResult:
    """Detached server-authored F023 result.

    ``NOT_FIRST_CLEAR`` covers both a later settlement and a replay of a
    previously committed first clear.  In either case this invocation made
    no new entitlement or ownership mutation.
    """

    contract_version: str
    status: str
    entitlement_status: str
    user_id: int
    zone_key: str
    requested_settlement_id: str
    entitlement_settlement_id: str
    encounter_operation_id: str
    reward_policy_version: str
    mapped_cosmetic_id: str
    first_clear_entitlement_consumed: bool
    entitlement_replayed: bool
    cosmetic_newly_owned: bool
    already_owned_no_op: bool
    acquisition_lineage_id: str | None

    def __post_init__(self) -> None:
        if self.contract_version != F023_REWARD_RESULT_CONTRACT_VERSION:
            raise ValueError("unsupported F023 reward result contract")
        if self.status not in _STATUSES:
            raise ValueError(f"unsupported F023 reward status: {self.status}")
        if type(self.first_clear_entitlement_consumed) is not bool:
            raise ValueError("first_clear_entitlement_consumed must be boolean")
        if type(self.entitlement_replayed) is not bool:
            raise ValueError("entitlement_replayed must be boolean")
        if type(self.cosmetic_newly_owned) is not bool:
            raise ValueError("cosmetic_newly_owned must be boolean")
        if type(self.already_owned_no_op) is not bool:
            raise ValueError("already_owned_no_op must be boolean")
        if self.status == FIRST_CLEAR_NEW_COSMETIC:
            if not self.first_clear_entitlement_consumed:
                raise ValueError("new cosmetic requires consumed entitlement")
            if not self.cosmetic_newly_owned or self.already_owned_no_op:
                raise ValueError("new cosmetic result flags are inconsistent")
            if not self.acquisition_lineage_id:
                raise ValueError("new cosmetic requires acquisition lineage")
        elif self.status == FIRST_CLEAR_ALREADY_OWNED_NO_OP:
            if not self.first_clear_entitlement_consumed:
                raise ValueError("owned no-op requires consumed entitlement")
            if self.cosmetic_newly_owned or not self.already_owned_no_op:
                raise ValueError("owned no-op result flags are inconsistent")
            if self.acquisition_lineage_id is not None:
                raise ValueError("owned no-op cannot have acquisition lineage")
        else:
            if self.first_clear_entitlement_consumed:
                raise ValueError("non-first-clear result cannot consume entitlement")
            if self.cosmetic_newly_owned or self.already_owned_no_op:
                raise ValueError("non-first-clear result cannot mutate ownership")
            if self.acquisition_lineage_id is not None:
                raise ValueError("non-first-clear cannot have acquisition lineage")

    def to_dict(self) -> dict[str, Any]:
        """Return only server-authored reward facts, never World decisions."""

        return {
            "contract_version": self.contract_version,
            "status": self.status,
            "entitlement_status": self.entitlement_status,
            "user_id": self.user_id,
            "zone_key": self.zone_key,
            "requested_settlement_id": self.requested_settlement_id,
            "entitlement_settlement_id": self.entitlement_settlement_id,
            "encounter_operation_id": self.encounter_operation_id,
            "reward_policy_version": self.reward_policy_version,
            "mapped_cosmetic_id": self.mapped_cosmetic_id,
            "first_clear_entitlement_consumed": self.first_clear_entitlement_consumed,
            "entitlement_replayed": self.entitlement_replayed,
            "cosmetic_newly_owned": self.cosmetic_newly_owned,
            "already_owned_no_op": self.already_owned_no_op,
            "acquisition_lineage_id": self.acquisition_lineage_id,
        }


def _validation(code: str, message: str) -> None:
    raise BattlefieldBossRewardValidationError(f"{code}: {message}")


def _require_grant_result(
    value: Any,
    *,
    expected_item_id: str,
) -> tuple[bool, str | None]:
    """Validate the narrow return contract of the existing wardrobe writer.

    The existing app writer returns ``new``, ``grant_id`` and ``payload``.
    F023 only consumes the new/no-op decision and the exact persisted wardrobe
    row reference.  A new grant must use the existing wardrobe-row identity;
    F023 never manufactures an ownership ID.
    """

    if not isinstance(value, Mapping):
        _validation("invalid_wardrobe_result", "wardrobe writer must return a mapping")
    newly_owned = value.get("new")
    if type(newly_owned) is not bool:
        _validation("invalid_wardrobe_result", "wardrobe result new must be boolean")
    if newly_owned:
        grant_id = value.get("grant_id")
        if not isinstance(grant_id, str) or not grant_id.strip():
            _validation(
                "wardrobe_grant_identity_missing",
                "new wardrobe ownership requires its persisted row reference",
            )
        grant_id = grant_id.strip()
        if not grant_id.startswith(f"{COSMETIC_OWNERSHIP_AUTHORITY}:"):
            _validation(
                "wardrobe_authority_mismatch",
                "new cosmetic grant must reference player_wardrobe",
            )
        payload = value.get("payload")
        if payload is not None and not isinstance(payload, Mapping):
            _validation("invalid_wardrobe_result", "wardrobe payload must be a mapping")
        return True, grant_id

    # An already-owned item is a truthful no-op.  A supplied grant ID in this
    # branch is ambiguous and could make a no-op look like a new lineage.
    if value.get("grant_id") not in (None, ""):
        _validation(
            "invalid_wardrobe_result",
            "already-owned wardrobe result cannot contain a grant identity",
        )
    if value.get("item_id") not in (None, expected_item_id):
        _validation("wardrobe_item_mismatch", "wardrobe result item differs from Mapping A")
    return False, None


def _append_cosmetic_acquisition_lineage(
    conn: Any,
    *,
    fact: BattlefieldBossDefeatedFact,
    user_id: int,
    zone_key: str,
    reward_item_id: str,
    grant_id: str,
) -> str:
    """Reuse the existing D5A outbox writer for one new wardrobe row."""

    event = append_event(
        conn,
        event_type="ITEM_ACQUISITION",
        player_id=str(user_id),
        lineage_id=grant_id,
        source_event_id=fact.settlement_id,
        idempotency_key=f"item-acquisition:{grant_id}",
        outcome="SUCCESS",
        payload={
            "operation": "GRANT",
            "grant_id": grant_id,
            "item_id": reward_item_id,
            "quantity": 1,
            "acquisition_source": "BATTLEFIELD_BOSS_FIRST_CLEAR",
            "source_reference": fact.settlement_id,
            "zone_key": zone_key,
            "reward_policy_version": POLICY_VERSION,
            "ownership_authority": COSMETIC_OWNERSHIP_AUTHORITY,
            "ownership_committed": True,
        },
        occurred_at=fact.occurred_at,
    )
    if event.get("duplicate"):
        _validation(
            "unexpected_duplicate_lineage",
            "a new entitlement encountered an existing acquisition lineage",
        )
    event_id = str(event.get("event_id") or "").strip()
    if not event_id:
        _validation("lineage_identity_missing", "D5A acquisition event ID is required")
    return event_id


def _result_from_entitlement(
    entitlement: BattlefieldBossFirstClearEntitlementResult,
    *,
    requested_settlement_id: str,
    status: str,
    consumed: bool,
    entitlement_replayed: bool,
    cosmetic_newly_owned: bool = False,
    already_owned_no_op: bool = False,
    acquisition_lineage_id: str | None = None,
) -> BattlefieldBossFirstClearRewardResult:
    return BattlefieldBossFirstClearRewardResult(
        contract_version=F023_REWARD_RESULT_CONTRACT_VERSION,
        status=status,
        entitlement_status=entitlement.status,
        user_id=entitlement.user_id,
        zone_key=entitlement.zone_key,
        requested_settlement_id=requested_settlement_id,
        entitlement_settlement_id=entitlement.entitlement_settlement_id,
        encounter_operation_id=entitlement.entitlement_encounter_operation_id,
        reward_policy_version=entitlement.reward_policy_version,
        mapped_cosmetic_id=entitlement.reward_item_id,
        first_clear_entitlement_consumed=consumed,
        entitlement_replayed=entitlement_replayed,
        cosmetic_newly_owned=cosmetic_newly_owned,
        already_owned_no_op=already_owned_no_op,
        acquisition_lineage_id=acquisition_lineage_id,
    )


def settle_battlefield_boss_first_clear_reward(
    conn: Any,
    *,
    fact: BattlefieldBossDefeatedFact,
    user_id: int,
    zone_key: str,
    grant_wardrobe_item: CosmeticGrantWriter,
    claimed_at: Any = None,
) -> BattlefieldBossFirstClearRewardResult:
    """Consume F022 and, only for its first claim, grant Mapping A.

    ``fact`` must already be the committed F012/F014 server handoff.  The
    supplied writer must be the authenticated user's existing
    ``player_wardrobe`` operation.  This adapter performs no transaction
    control: if the entitlement insert, wardrobe writer, or D5A lineage
    writer fails, the caller must roll back its transaction.
    """

    if type(fact) is not BattlefieldBossDefeatedFact:
        _validation("fact_type_required", "a validated F012 defeated fact is required")
    if not callable(grant_wardrobe_item):
        _validation("wardrobe_writer_required", "the existing wardrobe writer is required")

    mapped_cosmetic_id = reward_item_for_zone(zone_key)
    entitlement = claim_battlefield_boss_first_clear_entitlement(
        conn,
        fact=fact,
        user_id=user_id,
        zone_key=zone_key,
        source_settlement_id=fact.settlement_id,
        reward_item_id=mapped_cosmetic_id,
        reward_policy_version=POLICY_VERSION,
        claimed_at=claimed_at,
    )

    if entitlement.status == ENTITLEMENT_CONFLICT:
        return _result_from_entitlement(
            entitlement,
            requested_settlement_id=fact.settlement_id,
            status=CONFLICT,
            consumed=False,
            entitlement_replayed=False,
        )
    if entitlement.status == REPLAYED:
        return _result_from_entitlement(
            entitlement,
            requested_settlement_id=fact.settlement_id,
            status=NOT_FIRST_CLEAR,
            consumed=False,
            entitlement_replayed=True,
        )
    if entitlement.status == ALREADY_CLAIMED:
        return _result_from_entitlement(
            entitlement,
            requested_settlement_id=fact.settlement_id,
            status=NOT_FIRST_CLEAR,
            consumed=False,
            entitlement_replayed=False,
        )
    if entitlement.status != RECORDED:
        raise BattlefieldBossRewardRuntimeError(
            f"unexpected F022 entitlement status: {entitlement.status}"
        )

    # F022 has now reserved the one lifetime entitlement inside the caller's
    # transaction.  Any writer/lineage failure propagates so the caller can
    # roll back both the reservation and any partial ownership mutation.
    grant = grant_wardrobe_item(
        entitlement.reward_item_id,
        COSMETIC_GRANT_SOURCE,
    )
    newly_owned, grant_id = _require_grant_result(
        grant,
        expected_item_id=entitlement.reward_item_id,
    )
    if not newly_owned:
        return _result_from_entitlement(
            entitlement,
            requested_settlement_id=fact.settlement_id,
            status=FIRST_CLEAR_ALREADY_OWNED_NO_OP,
            consumed=True,
            entitlement_replayed=False,
            already_owned_no_op=True,
        )

    lineage_event_id = _append_cosmetic_acquisition_lineage(
        conn,
        fact=fact,
        user_id=entitlement.user_id,
        zone_key=entitlement.zone_key,
        reward_item_id=entitlement.reward_item_id,
        grant_id=grant_id or "",
    )
    return _result_from_entitlement(
        entitlement,
        requested_settlement_id=fact.settlement_id,
        status=FIRST_CLEAR_NEW_COSMETIC,
        consumed=True,
        entitlement_replayed=False,
        cosmetic_newly_owned=True,
        acquisition_lineage_id=lineage_event_id,
    )


__all__ = [
    "CONFLICT",
    "COSMETIC_GRANT_SOURCE",
    "COSMETIC_OWNERSHIP_AUTHORITY",
    "FIRST_CLEAR_ALREADY_OWNED_NO_OP",
    "FIRST_CLEAR_NEW_COSMETIC",
    "F023_REWARD_RESULT_CONTRACT_VERSION",
    "NOT_FIRST_CLEAR",
    "BattlefieldBossFirstClearRewardResult",
    "BattlefieldBossRewardRuntimeError",
    "BattlefieldBossRewardValidationError",
    "settle_battlefield_boss_first_clear_reward",
]
