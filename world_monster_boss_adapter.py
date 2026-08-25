"""Pure F014 adapter core for the World/Monster Battlefield Boss seam.

This module does not execute F010, settle combat, write an outbox, or apply
World progression.  It only translates an already validated F012 World intent
into an F010-compatible call specification, preserves the eligibility
evidence, and builds an F012 defeated fact from an already committed,
server-bound Monster settlement.

The adapter deliberately requires an immutable operation binding between the
F010 selection and the later settlement.  A missing binding, a mismatched
Zone/Monster/operation, or a pre-commit settlement fails closed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from world_monster_boundary_contract import (
    BATTLEFIELD_BOSS_CLASS,
    BATTLEFIELD_BOSS_DEFEATED_FACT_V1,
    BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1,
    BattlefieldBossDefeatedFact,
    BattlefieldBossEncounterIntent,
    SERVER_MONSTER_SETTLEMENT_AUTHORITY,
    WORLD_PROGRESSION_AUTHORITY,
)


F014_ADAPTER_VERSION: Final[str] = (
    "F014_WORLD_BATTLEFIELD_BOSS_THIN_ADAPTER_CORE_V1"
)
F010_BATTLEFIELD_BOSS_INTENT: Final[str] = "BATTLEFIELD_BOSS"
SERVER_MONSTER_SELECTOR_AUTHORITY: Final[str] = "SERVER_MONSTER_SELECTOR"
MONSTER_DEFEATED_EVENT_TYPE: Final[str] = "MONSTER_DEFEATED"
CLIENT_CAN_AUTHORIZE_BOSS: Final[bool] = False

_MACHINE_KEY_RE: Final[re.Pattern[str]] = re.compile(
    r"^[a-z0-9]+(?:_[a-z0-9]+)*$"
)


class BattlefieldBossAdapterError(ValueError):
    """Base class for deterministic F014 adapter failures."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class BattlefieldBossAdapterValidationError(BattlefieldBossAdapterError):
    """Raised when an adapter input is malformed or not authoritative."""


class BattlefieldBossBindingError(BattlefieldBossAdapterError):
    """Raised when a selection and settlement do not share one operation."""


def _fail(code: str, message: str) -> None:
    raise BattlefieldBossAdapterValidationError(code, message)


def _require_user_id(value: Any, *, field: str = "user_id") -> int:
    if type(value) is not int or value <= 0:
        _fail("invalid_user_id", f"{field} must be a positive integer")
    return value


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail("invalid_text", f"{field} must be a non-empty trimmed string")
    if len(value) > 256:
        _fail("text_too_long", f"{field} exceeds 256 characters")
    return value


def _require_machine_key(value: Any, field: str) -> str:
    text = _require_text(value, field)
    if _MACHINE_KEY_RE.fullmatch(text) is None:
        _fail("invalid_machine_key", f"{field} must be a lowercase ASCII key")
    return text


def _require_hp(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        _fail("invalid_hp", f"{field} must be a non-negative integer")
    return value


def _freeze_context(values: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(values, Mapping):
        _fail("invalid_audit_context", "audit context must be a mapping")
    frozen: dict[str, Any] = {}
    for key, value in values.items():
        if not isinstance(key, str) or not key or key != key.strip():
            _fail("invalid_audit_context", "audit context keys must be strings")
        if not isinstance(value, (str, bool)):
            _fail("invalid_audit_context", f"audit context value {key!r} is not scalar")
        frozen[key] = value
    return MappingProxyType(frozen)


@dataclass(frozen=True, slots=True)
class F010BattlefieldBossSelectorCall:
    """Validated arguments for the existing F010 durable selector seam.

    ``battlefield_boss_authorized`` is a derived property, not an input.
    Only an F012 intent whose authority is exactly World progression can
    produce this object.
    """

    user_id: int
    zone_key: str
    encounter_operation_id: str
    encounter_intent: str
    eligibility_authority: str
    eligibility_reference: str
    intent_contract_version: str
    intent_replay_fingerprint: str
    audit_context: Mapping[str, Any]

    def __post_init__(self) -> None:
        _require_user_id(self.user_id)
        _require_machine_key(self.zone_key, "zone_key")
        _require_text(self.encounter_operation_id, "encounter_operation_id")
        _require_text(self.eligibility_reference, "eligibility_reference")
        _require_text(self.intent_contract_version, "intent_contract_version")
        _require_text(self.intent_replay_fingerprint, "intent_replay_fingerprint")
        if self.encounter_intent != F010_BATTLEFIELD_BOSS_INTENT:
            _fail("invalid_selector_intent", "F010 call must request Battlefield Boss")
        if self.eligibility_authority != WORLD_PROGRESSION_AUTHORITY:
            _fail("invalid_eligibility_authority", "F010 call must be World-authorized")
        object.__setattr__(self, "audit_context", _freeze_context(self.audit_context))

    @property
    def battlefield_boss_authorized(self) -> bool:
        """The only authorization marker exposed to the future F010 call."""

        return self.eligibility_authority == WORLD_PROGRESSION_AUTHORITY

    def to_selector_kwargs(self) -> dict[str, Any]:
        """Return only the fields accepted by F010's selector service."""

        return {
            "user_id": self.user_id,
            "zone_key": self.zone_key,
            "encounter_operation_id": self.encounter_operation_id,
            "encounter_intent": self.encounter_intent,
            "battlefield_boss_authorized": self.battlefield_boss_authorized,
        }

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "adapter_version": F014_ADAPTER_VERSION,
            "contract_version": self.intent_contract_version,
            "user_id": self.user_id,
            "zone_key": self.zone_key,
            "encounter_operation_id": self.encounter_operation_id,
            "eligibility_authority": self.eligibility_authority,
            "eligibility_reference": self.eligibility_reference,
            "intent_replay_fingerprint": self.intent_replay_fingerprint,
            "audit_context": dict(self.audit_context),
        }


def build_f010_battlefield_boss_selector_call(
    intent: BattlefieldBossEncounterIntent,
) -> F010BattlefieldBossSelectorCall:
    """Translate one validated F012 World intent into an F010 call spec.

    Raw mappings are deliberately rejected.  Network/client payloads must
    first cross the F012 contract and the authenticated World authority; this
    pure adapter never accepts a caller-supplied authorization boolean.
    """

    if type(intent) is not BattlefieldBossEncounterIntent:
        _fail(
            "intent_type_required",
            "F014 requires a validated BattlefieldBossEncounterIntent object",
        )
    if intent.contract_version != BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1:
        _fail("invalid_intent_contract", "unsupported F012 intent contract")
    if intent.encounter_class != BATTLEFIELD_BOSS_CLASS:
        _fail("invalid_encounter_class", "only Battlefield Boss intent is supported")
    if intent.eligibility_authority != WORLD_PROGRESSION_AUTHORITY:
        _fail("invalid_eligibility_authority", "client or Quest authority is rejected")

    return F010BattlefieldBossSelectorCall(
        user_id=intent.user_id,
        zone_key=intent.zone_key,
        encounter_operation_id=intent.intent_operation_id,
        encounter_intent=F010_BATTLEFIELD_BOSS_INTENT,
        eligibility_authority=intent.eligibility_authority,
        eligibility_reference=intent.eligibility_reference,
        intent_contract_version=intent.contract_version,
        intent_replay_fingerprint=intent.replay_fingerprint(),
        audit_context={
            "requested_at": intent.requested_at,
            "replayed": intent.replayed,
            "eligibility_reference": intent.eligibility_reference,
        },
    )


@dataclass(frozen=True, slots=True)
class ServerBattlefieldBossSelection:
    """The server-bound identity result returned by the F010 selector."""

    user_id: int
    zone_key: str
    encounter_operation_id: str
    monster_id: str
    encounter_class: str
    source_authority: str = SERVER_MONSTER_SELECTOR_AUTHORITY

    def __post_init__(self) -> None:
        _require_user_id(self.user_id)
        _require_machine_key(self.zone_key, "zone_key")
        _require_text(self.encounter_operation_id, "encounter_operation_id")
        _require_machine_key(self.monster_id, "monster_id")
        if self.encounter_class != BATTLEFIELD_BOSS_CLASS:
            _fail("invalid_encounter_class", "selection must be a Battlefield Boss")
        if self.source_authority != SERVER_MONSTER_SELECTOR_AUTHORITY:
            _fail("invalid_selection_authority", "selection must come from F010 server selector")

    @classmethod
    def from_f010_result(
        cls,
        *,
        user_id: int,
        zone_key: str,
        encounter_operation_id: str,
        monster_id: str,
        encounter_class: str,
    ) -> "ServerBattlefieldBossSelection":
        """Normalize the already server-owned F010 selection result."""

        return cls(
            user_id=user_id,
            zone_key=zone_key,
            encounter_operation_id=encounter_operation_id,
            monster_id=monster_id,
            encounter_class=encounter_class,
        )


@dataclass(frozen=True, slots=True)
class BattlefieldBossEncounterBinding:
    """Immutable continuity binding from intent, selection, and operation."""

    user_id: int
    zone_key: str
    encounter_operation_id: str
    monster_id: str
    encounter_class: str
    eligibility_reference: str
    intent_replay_fingerprint: str

    def __post_init__(self) -> None:
        _require_user_id(self.user_id)
        _require_machine_key(self.zone_key, "zone_key")
        _require_text(self.encounter_operation_id, "encounter_operation_id")
        _require_machine_key(self.monster_id, "monster_id")
        _require_text(self.eligibility_reference, "eligibility_reference")
        _require_text(self.intent_replay_fingerprint, "intent_replay_fingerprint")
        if self.encounter_class != BATTLEFIELD_BOSS_CLASS:
            _fail("invalid_encounter_class", "binding must be a Battlefield Boss")


def bind_battlefield_boss_selection(
    call: F010BattlefieldBossSelectorCall,
    selection: ServerBattlefieldBossSelection,
) -> BattlefieldBossEncounterBinding:
    """Bind the F010-selected Monster to the authorized operation."""

    if type(call) is not F010BattlefieldBossSelectorCall:
        _fail("selector_call_type_required", "F014 requires its validated F010 call spec")
    if type(selection) is not ServerBattlefieldBossSelection:
        _fail(
            "selection_type_required",
            "F014 requires a server-bound F010 selection result",
        )
    if selection.user_id != call.user_id:
        raise BattlefieldBossBindingError(
            "user_binding_mismatch",
            "selection user does not match World intent user",
        )
    if selection.zone_key != call.zone_key:
        raise BattlefieldBossBindingError(
            "zone_binding_mismatch",
            "selection Zone does not match World intent Zone",
        )
    if selection.encounter_operation_id != call.encounter_operation_id:
        raise BattlefieldBossBindingError(
            "operation_binding_mismatch",
            "selection operation does not match World intent operation",
        )

    return BattlefieldBossEncounterBinding(
        user_id=call.user_id,
        zone_key=call.zone_key,
        encounter_operation_id=call.encounter_operation_id,
        monster_id=selection.monster_id,
        encounter_class=selection.encounter_class,
        eligibility_reference=call.eligibility_reference,
        intent_replay_fingerprint=call.intent_replay_fingerprint,
    )


@dataclass(frozen=True, slots=True)
class ServerMonsterSettlementEvidence:
    """Server-bound settlement evidence supplied after the caller commits.

    The factory is intentionally explicit about the source authority and
    committed flag.  The adapter does not authenticate a request or perform a
    database lookup; it accepts only this typed server-bound handoff, never a
    client mapping or a client ``monster_defeated`` flag.
    """

    user_id: int
    zone_key: str
    monster_id: str
    encounter_class: str
    encounter_operation_id: str
    settlement_id: str
    hp_before: int
    hp_after: int
    committed: bool
    occurred_at: str
    event_type: str = MONSTER_DEFEATED_EVENT_TYPE
    source_authority: str = SERVER_MONSTER_SETTLEMENT_AUTHORITY

    def __post_init__(self) -> None:
        _require_user_id(self.user_id)
        _require_machine_key(self.zone_key, "zone_key")
        _require_machine_key(self.monster_id, "monster_id")
        _require_text(self.encounter_operation_id, "encounter_operation_id")
        _require_text(self.settlement_id, "settlement_id")
        _require_text(self.occurred_at, "occurred_at")
        _require_hp(self.hp_before, "hp_before")
        _require_hp(self.hp_after, "hp_after")
        if self.encounter_class != BATTLEFIELD_BOSS_CLASS:
            _fail("invalid_encounter_class", "settlement must be a Battlefield Boss")
        if type(self.committed) is not bool:
            _fail("invalid_commit_marker", "committed must be a boolean")
        if self.event_type != MONSTER_DEFEATED_EVENT_TYPE:
            _fail("invalid_event_type", "settlement evidence must be MONSTER_DEFEATED")
        if self.source_authority != SERVER_MONSTER_SETTLEMENT_AUTHORITY:
            _fail(
                "invalid_source_authority",
                "settlement evidence must come from server Monster settlement",
            )

    @classmethod
    def from_server_settlement(
        cls,
        *,
        user_id: int,
        zone_key: str,
        monster_id: str,
        encounter_class: str,
        encounter_operation_id: str,
        settlement_id: str,
        hp_before: int,
        hp_after: int,
        committed: bool,
        occurred_at: str,
    ) -> "ServerMonsterSettlementEvidence":
        """Create the typed handoff from the existing settlement authority."""

        return cls(
            user_id=user_id,
            zone_key=zone_key,
            monster_id=monster_id,
            encounter_class=encounter_class,
            encounter_operation_id=encounter_operation_id,
            settlement_id=settlement_id,
            hp_before=hp_before,
            hp_after=hp_after,
            committed=committed,
            occurred_at=occurred_at,
        )


def build_battlefield_boss_defeated_fact(
    binding: BattlefieldBossEncounterBinding,
    settlement: ServerMonsterSettlementEvidence,
    *,
    replayed: bool = False,
) -> BattlefieldBossDefeatedFact:
    """Build F012's fact only from a committed, bound Monster settlement."""

    if type(binding) is not BattlefieldBossEncounterBinding:
        raise BattlefieldBossBindingError(
            "operation_binding_required",
            "a server-bound Battlefield Boss operation binding is required",
        )
    if type(settlement) is not ServerMonsterSettlementEvidence:
        _fail(
            "settlement_evidence_type_required",
            "a typed server settlement handoff is required",
        )
    if settlement.user_id != binding.user_id:
        raise BattlefieldBossBindingError(
            "user_binding_mismatch",
            "settlement user does not match the encounter binding",
        )
    if settlement.zone_key != binding.zone_key:
        raise BattlefieldBossBindingError(
            "zone_binding_mismatch",
            "settlement Zone does not match the encounter binding",
        )
    if settlement.monster_id != binding.monster_id:
        raise BattlefieldBossBindingError(
            "monster_binding_mismatch",
            "settlement Monster does not match the encounter binding",
        )
    if settlement.encounter_operation_id != binding.encounter_operation_id:
        raise BattlefieldBossBindingError(
            "operation_binding_mismatch",
            "settlement operation does not match the encounter binding",
        )
    if settlement.committed is not True:
        raise BattlefieldBossAdapterValidationError(
            "settlement_not_committed",
            "F012 fact cannot be emitted before Monster settlement commit",
        )
    if settlement.hp_before <= 0 or settlement.hp_after != 0:
        raise BattlefieldBossAdapterValidationError(
            "invalid_defeat_transition",
            "defeat requires hp_before > 0 and hp_after == 0",
        )
    if type(replayed) is not bool:
        _fail("invalid_replay_marker", "replayed must be a boolean")

    return BattlefieldBossDefeatedFact(
        contract_version=BATTLEFIELD_BOSS_DEFEATED_FACT_V1,
        user_id=binding.user_id,
        zone_key=binding.zone_key,
        monster_id=binding.monster_id,
        encounter_class=BATTLEFIELD_BOSS_CLASS,
        encounter_operation_id=binding.encounter_operation_id,
        settlement_id=settlement.settlement_id,
        defeated=True,
        source_authority=SERVER_MONSTER_SETTLEMENT_AUTHORITY,
        occurred_at=settlement.occurred_at,
        replayed=replayed,
        metadata={
            "adapter_version": F014_ADAPTER_VERSION,
            "eligibility_authority": WORLD_PROGRESSION_AUTHORITY,
            "eligibility_reference": binding.eligibility_reference,
            "intent_replay_fingerprint": binding.intent_replay_fingerprint,
            "operation_binding_verified": True,
            "settlement_event_type": settlement.event_type,
        },
    )


__all__ = [
    "BATTLEFIELD_BOSS_CLASS",
    "BattlefieldBossAdapterError",
    "BattlefieldBossAdapterValidationError",
    "BattlefieldBossBindingError",
    "BattlefieldBossEncounterBinding",
    "CLIENT_CAN_AUTHORIZE_BOSS",
    "F010BattlefieldBossSelectorCall",
    "F010_BATTLEFIELD_BOSS_INTENT",
    "F014_ADAPTER_VERSION",
    "MONSTER_DEFEATED_EVENT_TYPE",
    "SERVER_MONSTER_SELECTOR_AUTHORITY",
    "ServerBattlefieldBossSelection",
    "ServerMonsterSettlementEvidence",
    "bind_battlefield_boss_selection",
    "build_battlefield_boss_defeated_fact",
    "build_f010_battlefield_boss_selector_call",
]
