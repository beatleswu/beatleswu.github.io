"""F024 presentation transport for the authoritative F023 reward result.

F023 owns the first-clear entitlement and the existing wardrobe/D5A
mutation path.  This module only projects the already-validated F023 result
into the small JSON-safe shape that F018/result presentation may transport.
It never resolves Mapping A, writes ownership, grants rewards, or applies
World/Lord/Quest policy.

The raw-mapping decoder is deliberately strict.  It is a transport decoder,
not an authority boundary: callers must only pass a payload received from a
trusted server result.  Runtime reward code should use
``build_battlefield_boss_reward_transport`` with the typed F023 result.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any, Final

from world_battlefield_boss_reward_runtime import (
    CONFLICT,
    FIRST_CLEAR_ALREADY_OWNED_NO_OP,
    FIRST_CLEAR_NEW_COSMETIC,
    NOT_FIRST_CLEAR,
    BattlefieldBossFirstClearRewardResult,
)


F024_RESULT_TRANSPORT_CONTRACT_VERSION: Final[str] = (
    "F024_BATTLEFIELD_BOSS_REWARD_RESULT_TRANSPORT_V1"
)
_STATUSES: Final[frozenset[str]] = frozenset(
    {
        FIRST_CLEAR_NEW_COSMETIC,
        FIRST_CLEAR_ALREADY_OWNED_NO_OP,
        NOT_FIRST_CLEAR,
        CONFLICT,
    }
)
_TRANSPORT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "contract_version",
        "status",
        "zone_key",
        "reward_policy_version",
        "mapped_cosmetic_id",
        "first_clear_entitlement_consumed",
        "cosmetic_newly_owned",
        "already_owned_no_op",
        "entitlement_replayed",
    }
)
_F023_RESULT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "contract_version",
        "status",
        "entitlement_status",
        "user_id",
        "zone_key",
        "requested_settlement_id",
        "entitlement_settlement_id",
        "encounter_operation_id",
        "reward_policy_version",
        "mapped_cosmetic_id",
        "first_clear_entitlement_consumed",
        "entitlement_replayed",
        "cosmetic_newly_owned",
        "already_owned_no_op",
        "acquisition_lineage_id",
    }
)


class BattlefieldBossRewardTransportError(ValueError):
    """A server-authored reward result failed transport validation."""


def _fail(code: str, message: str) -> None:
    raise BattlefieldBossRewardTransportError(f"{code}: {message}")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("invalid_text", f"{field} must be a non-empty string")
    return value.strip()


def _bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        _fail("invalid_boolean", f"{field} must be boolean")
    return value


@dataclass(frozen=True, slots=True)
class BattlefieldBossRewardResultTransport:
    """Minimal server-authored reward facts for presentation transport."""

    contract_version: str
    status: str
    zone_key: str
    reward_policy_version: str
    mapped_cosmetic_id: str
    first_clear_entitlement_consumed: bool
    cosmetic_newly_owned: bool
    already_owned_no_op: bool
    entitlement_replayed: bool

    def __post_init__(self) -> None:
        if self.contract_version != F024_RESULT_TRANSPORT_CONTRACT_VERSION:
            _fail("unsupported_contract", "contract_version is not the F024 V1 contract")
        if not isinstance(self.status, str) or self.status not in _STATUSES:
            _fail("unsupported_status", f"unsupported reward status: {self.status}")
        object.__setattr__(self, "zone_key", _text(self.zone_key, "zone_key"))
        object.__setattr__(
            self,
            "reward_policy_version",
            _text(self.reward_policy_version, "reward_policy_version"),
        )
        object.__setattr__(
            self,
            "mapped_cosmetic_id",
            _text(self.mapped_cosmetic_id, "mapped_cosmetic_id"),
        )
        for field in (
            "first_clear_entitlement_consumed",
            "cosmetic_newly_owned",
            "already_owned_no_op",
            "entitlement_replayed",
        ):
            object.__setattr__(self, field, _bool(getattr(self, field), field))

        if self.status == FIRST_CLEAR_NEW_COSMETIC:
            expected = (True, True, False)
        elif self.status == FIRST_CLEAR_ALREADY_OWNED_NO_OP:
            expected = (True, False, True)
        else:
            expected = (False, False, False)
        actual = (
            self.first_clear_entitlement_consumed,
            self.cosmetic_newly_owned,
            self.already_owned_no_op,
        )
        if actual != expected:
            _fail("status_flags_mismatch", "transport status flags are inconsistent")
        if self.status != NOT_FIRST_CLEAR and self.entitlement_replayed:
            _fail(
                "replay_flag_mismatch",
                "only NOT_FIRST_CLEAR may carry entitlement_replayed=True",
            )

    def to_dict(self) -> dict[str, Any]:
        """Return only the approved presentation fields."""

        return {
            "contract_version": self.contract_version,
            "status": self.status,
            "zone_key": self.zone_key,
            "reward_policy_version": self.reward_policy_version,
            "mapped_cosmetic_id": self.mapped_cosmetic_id,
            "first_clear_entitlement_consumed": self.first_clear_entitlement_consumed,
            "cosmetic_newly_owned": self.cosmetic_newly_owned,
            "already_owned_no_op": self.already_owned_no_op,
            "entitlement_replayed": self.entitlement_replayed,
        }

    def to_json(self) -> str:
        """Serialize deterministically for a presentation response."""

        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> "BattlefieldBossRewardResultTransport":
        """Strictly decode an already server-authored transport payload."""

        if not isinstance(payload, Mapping):
            _fail("invalid_payload", "transport payload must be a mapping")
        unknown = set(payload) - _TRANSPORT_FIELDS
        if unknown:
            _fail("unknown_payload_field", ", ".join(sorted(map(str, unknown))))
        missing = _TRANSPORT_FIELDS - set(payload)
        if missing:
            _fail("missing_payload_field", ", ".join(sorted(missing)))
        return cls(
            contract_version=payload["contract_version"],
            status=payload["status"],
            zone_key=payload["zone_key"],
            reward_policy_version=payload["reward_policy_version"],
            mapped_cosmetic_id=payload["mapped_cosmetic_id"],
            first_clear_entitlement_consumed=payload[
                "first_clear_entitlement_consumed"
            ],
            cosmetic_newly_owned=payload["cosmetic_newly_owned"],
            already_owned_no_op=payload["already_owned_no_op"],
            entitlement_replayed=payload["entitlement_replayed"],
        )

    @classmethod
    def from_json(cls, payload: str) -> "BattlefieldBossRewardResultTransport":
        try:
            decoded = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            _fail("invalid_json", str(exc))
        return cls.from_mapping(decoded)


def build_battlefield_boss_reward_transport(
    result: BattlefieldBossFirstClearRewardResult,
) -> BattlefieldBossRewardResultTransport:
    """Project one typed F023 result without creating reward authority."""

    if type(result) is not BattlefieldBossFirstClearRewardResult:
        _fail("result_type_required", "a typed F023 reward result is required")
    source = result.to_dict()
    if set(source) != _F023_RESULT_FIELDS:
        _fail("f023_payload_shape_changed", "F023 result fields changed unexpectedly")
    return BattlefieldBossRewardResultTransport(
        contract_version=F024_RESULT_TRANSPORT_CONTRACT_VERSION,
        status=source["status"],
        zone_key=source["zone_key"],
        reward_policy_version=source["reward_policy_version"],
        mapped_cosmetic_id=source["mapped_cosmetic_id"],
        first_clear_entitlement_consumed=source[
            "first_clear_entitlement_consumed"
        ],
        cosmetic_newly_owned=source["cosmetic_newly_owned"],
        already_owned_no_op=source["already_owned_no_op"],
        entitlement_replayed=source["entitlement_replayed"],
    )


__all__ = [
    "F024_RESULT_TRANSPORT_CONTRACT_VERSION",
    "BattlefieldBossRewardResultTransport",
    "BattlefieldBossRewardTransportError",
    "build_battlefield_boss_reward_transport",
]
