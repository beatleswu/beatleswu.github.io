"""Pure World <-> Monster Battlefield Boss boundary contracts.

This module deliberately has no application, database, Quest, Shop, or
Flask dependency.  It transports a World eligibility intent to the Monster
boundary and a committed Monster defeat fact back to a future World consumer.
Neither contract contains World policy or combat/stat authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, TypeAlias


BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1: Final[str] = (
    "BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1"
)
BATTLEFIELD_BOSS_DEFEATED_FACT_V1: Final[str] = (
    "BATTLEFIELD_BOSS_DEFEATED_FACT_V1"
)
BATTLEFIELD_BOSS_CLASS: Final[str] = "BATTLEFIELD_BOSS"
WORLD_PROGRESSION_AUTHORITY: Final[str] = "WORLD_PROGRESSION"
SERVER_MONSTER_SETTLEMENT_AUTHORITY: Final[str] = "SERVER_MONSTER_SETTLEMENT"

_MAX_TEXT_LENGTH: Final[int] = 256
_MAX_METADATA_DEPTH: Final[int] = 4
_MAX_METADATA_ENTRIES: Final[int] = 32
_MAX_METADATA_ITEMS_PER_LIST: Final[int] = 32
_MAX_METADATA_JSON_BYTES: Final[int] = 4096

_INTENT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "contract_version",
        "user_id",
        "zone_key",
        "intent_operation_id",
        "encounter_class",
        "eligibility_authority",
        "eligibility_reference",
        "requested_at",
        "replayed",
        "metadata",
    }
)
_FACT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "contract_version",
        "user_id",
        "zone_key",
        "monster_id",
        "encounter_class",
        "encounter_operation_id",
        "settlement_id",
        "defeated",
        "source_authority",
        "occurred_at",
        "replayed",
        "metadata",
    }
)

# These fields are not transport authority for either boundary.  They are
# rejected even inside metadata so callers cannot smuggle a second authority
# through an otherwise opaque object.
_FORBIDDEN_WORLD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "boss_ready",
        "lord_ready",
        "lord_unlocked",
        "zone_clear",
        "zone_cleared",
        "star_granted",
        "stars",
        "next_zone",
        "next_zone_unlock",
        "next_zone_unlocked",
        "world_progressed",
        "quest_completed",
        "correct_answer",
        "mastery_pct",
    }
)
_FORBIDDEN_MONSTER_KEYS: Final[frozenset[str]] = frozenset(
    {
        "attack",
        "drop",
        "drop_profile_id",
        "max_hp",
        "monster_atk",
        "monster_attack",
        "monster_def",
        "monster_hp",
        "monster_hp_max",
        "profile_id",
        "rarity",
        "reward",
        "reward_profile_id",
        "sprite_path",
        "stats",
    }
)
_FORBIDDEN_METADATA_KEYS: Final[frozenset[str]] = (
    _FORBIDDEN_WORLD_KEYS | _FORBIDDEN_MONSTER_KEYS
)

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class BoundaryContractError(ValueError):
    """Base class for deterministic boundary validation failures."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class BoundaryContractValidationError(BoundaryContractError):
    """Raised when a contract payload is malformed or out of scope."""


class BoundaryReplayMismatchError(BoundaryContractError):
    """Raised when a replay identity is reused with changed payload data."""


def _fail(code: str, message: str) -> None:
    raise BoundaryContractValidationError(code, message)


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or not value.strip():
        _fail("invalid_text", f"{field} must be a non-empty string")
    if value != value.strip():
        _fail("invalid_text", f"{field} must not have surrounding whitespace")
    if len(value) > _MAX_TEXT_LENGTH:
        _fail("text_too_long", f"{field} exceeds {_MAX_TEXT_LENGTH} characters")
    return value


def _require_user_id(value: Any) -> int:
    if type(value) is not int or value <= 0:
        _fail("invalid_user_id", "user_id must be a positive integer")
    return value


def _require_bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        _fail("invalid_boolean", f"{field} must be a boolean")
    return value


def _metadata_key_is_forbidden(key: str) -> bool:
    return key.lower() in _FORBIDDEN_METADATA_KEYS


def _freeze_json(
    value: Any,
    *,
    path: str,
    depth: int,
    entry_count: list[int],
) -> Any:
    if depth > _MAX_METADATA_DEPTH:
        _fail("metadata_too_deep", f"{path} exceeds metadata nesting limit")

    if value is None or type(value) is bool or type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            _fail("metadata_not_json_safe", f"{path} contains a non-finite number")
        return value
    if isinstance(value, str):
        if len(value) > _MAX_TEXT_LENGTH:
            _fail("metadata_value_too_long", f"{path} exceeds text limit")
        return value

    if isinstance(value, Mapping):
        if len(value) > _MAX_METADATA_ENTRIES:
            _fail("metadata_too_large", f"{path} has too many keys")
        frozen: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str) or not key or key != key.strip():
                _fail("metadata_invalid_key", f"{path} has an invalid key")
            if _metadata_key_is_forbidden(key):
                _fail("forbidden_authority_field", f"{path}.{key} is not transport metadata")
            entry_count[0] += 1
            if entry_count[0] > _MAX_METADATA_ENTRIES:
                _fail("metadata_too_large", "metadata has too many nested entries")
            frozen[key] = _freeze_json(
                child,
                path=f"{path}.{key}",
                depth=depth + 1,
                entry_count=entry_count,
            )
        return MappingProxyType(frozen)

    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_METADATA_ITEMS_PER_LIST:
            _fail("metadata_too_large", f"{path} has too many list items")
        return tuple(
            _freeze_json(
                child,
                path=f"{path}[{index}]",
                depth=depth + 1,
                entry_count=entry_count,
            )
            for index, child in enumerate(value)
        )

    _fail("metadata_not_json_safe", f"{path} contains an unsupported value")


def _freeze_metadata(metadata: Any) -> Mapping[str, Any]:
    if not isinstance(metadata, Mapping):
        _fail("invalid_metadata", "metadata must be a JSON object")
    frozen = _freeze_json(
        metadata,
        path="metadata",
        depth=0,
        entry_count=[0],
    )
    encoded = json.dumps(
        _thaw_json(frozen),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > _MAX_METADATA_JSON_BYTES:
        _fail("metadata_too_large", "metadata exceeds serialized size limit")
    return frozen


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(child) for child in value]
    return value


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        _thaw_json(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _payload_fingerprint(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _strict_mapping(data: Any, fields: frozenset[str], kind: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        _fail("invalid_payload", f"{kind} payload must be a mapping")
    unknown = sorted(set(data) - fields)
    missing = sorted(fields - set(data))
    if unknown:
        _fail("unknown_top_level_field", f"{kind} payload contains {unknown}")
    if missing:
        _fail("missing_required_field", f"{kind} payload misses {missing}")
    return data


@dataclass(frozen=True, slots=True)
class BattlefieldBossEncounterIntent:
    """World authorization to create one Battlefield Boss encounter."""

    contract_version: str
    user_id: int
    zone_key: str
    intent_operation_id: str
    encounter_class: str
    eligibility_authority: str
    eligibility_reference: str
    requested_at: str
    replayed: bool
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.contract_version != BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1:
            _fail("invalid_contract_version", "unsupported encounter intent version")
        _require_user_id(self.user_id)
        for field in (
            "zone_key",
            "intent_operation_id",
            "eligibility_reference",
            "requested_at",
        ):
            _require_text(getattr(self, field), field)
        if self.encounter_class != BATTLEFIELD_BOSS_CLASS:
            _fail("invalid_encounter_class", "intent must be BATTLEFIELD_BOSS")
        if self.eligibility_authority != WORLD_PROGRESSION_AUTHORITY:
            _fail("invalid_eligibility_authority", "intent must be World-authorized")
        _require_bool(self.replayed, "replayed")
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "user_id": self.user_id,
            "zone_key": self.zone_key,
            "intent_operation_id": self.intent_operation_id,
            "encounter_class": self.encounter_class,
            "eligibility_authority": self.eligibility_authority,
            "eligibility_reference": self.eligibility_reference,
            "requested_at": self.requested_at,
            "replayed": self.replayed,
            "metadata": _thaw_json(self.metadata),
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BattlefieldBossEncounterIntent":
        payload = _strict_mapping(data, _INTENT_FIELDS, "encounter intent")
        return cls(**dict(payload))

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())

    def fingerprint(self) -> str:
        return _payload_fingerprint(self.to_dict())

    def replay_fingerprint(self) -> str:
        payload = self.to_dict()
        payload.pop("requested_at")
        payload.pop("replayed")
        return _payload_fingerprint(payload)


@dataclass(frozen=True, slots=True)
class BattlefieldBossDefeatedFact:
    """Committed server fact that a Battlefield Boss encounter was defeated."""

    contract_version: str
    user_id: int
    zone_key: str
    monster_id: str
    encounter_class: str
    encounter_operation_id: str
    settlement_id: str
    defeated: bool
    source_authority: str
    occurred_at: str
    replayed: bool
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.contract_version != BATTLEFIELD_BOSS_DEFEATED_FACT_V1:
            _fail("invalid_contract_version", "unsupported defeated fact version")
        _require_user_id(self.user_id)
        for field in (
            "zone_key",
            "monster_id",
            "encounter_operation_id",
            "settlement_id",
            "occurred_at",
        ):
            _require_text(getattr(self, field), field)
        if self.encounter_class != BATTLEFIELD_BOSS_CLASS:
            _fail("invalid_encounter_class", "defeated fact must be BATTLEFIELD_BOSS")
        if self.defeated is not True:
            _fail("invalid_defeat_state", "defeated fact must contain defeated=true")
        if self.source_authority != SERVER_MONSTER_SETTLEMENT_AUTHORITY:
            _fail("invalid_source_authority", "fact must come from server Monster settlement")
        _require_bool(self.replayed, "replayed")
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "user_id": self.user_id,
            "zone_key": self.zone_key,
            "monster_id": self.monster_id,
            "encounter_class": self.encounter_class,
            "encounter_operation_id": self.encounter_operation_id,
            "settlement_id": self.settlement_id,
            "defeated": self.defeated,
            "source_authority": self.source_authority,
            "occurred_at": self.occurred_at,
            "replayed": self.replayed,
            "metadata": _thaw_json(self.metadata),
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BattlefieldBossDefeatedFact":
        payload = _strict_mapping(data, _FACT_FIELDS, "defeated fact")
        return cls(**dict(payload))

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())

    def fingerprint(self) -> str:
        return _payload_fingerprint(self.to_dict())

    def replay_fingerprint(self) -> str:
        payload = self.to_dict()
        payload.pop("occurred_at")
        payload.pop("replayed")
        return _payload_fingerprint(payload)


def intent_operation_key(intent: BattlefieldBossEncounterIntent) -> tuple[int, str]:
    """Return the server-side logical key for an intent operation."""

    return intent.user_id, intent.intent_operation_id


def defeated_fact_dedupe_key(
    fact: BattlefieldBossDefeatedFact,
) -> tuple[int, str]:
    """Return the canonical future consumer dedupe key.

    F012 does not persist it.  Global uniqueness of ``settlement_id`` is not
    proven, so V1 scopes the stable settlement identity to its user.
    """

    return fact.user_id, fact.settlement_id


def assert_intent_replay_compatible(
    original: BattlefieldBossEncounterIntent,
    replay: BattlefieldBossEncounterIntent,
) -> None:
    """Fail closed if one intent operation is reused with changed meaning.

    ``requested_at`` and ``replayed`` are delivery metadata and may change on
    a retry.  All eligibility and identity-bearing fields remain part of the
    replay fingerprint.
    """

    if not isinstance(original, BattlefieldBossEncounterIntent):
        _fail("invalid_original_intent", "original must be a Battlefield Boss intent")
    if not isinstance(replay, BattlefieldBossEncounterIntent):
        _fail("invalid_replay_intent", "replay must be a Battlefield Boss intent")
    if intent_operation_key(original) != intent_operation_key(replay):
        raise BoundaryReplayMismatchError(
            "intent_operation_mismatch",
            "same-operation replay requires the same user and operation ID",
        )
    if original.replay_fingerprint() != replay.replay_fingerprint():
        raise BoundaryReplayMismatchError(
            "intent_payload_mismatch",
            "same intent operation was delivered with changed authoritative payload",
        )


def assert_defeated_fact_replay_compatible(
    original: BattlefieldBossDefeatedFact,
    replay: BattlefieldBossDefeatedFact,
) -> None:
    """Fail closed if one settlement is replayed with changed defeat facts."""

    if not isinstance(original, BattlefieldBossDefeatedFact):
        _fail("invalid_original_fact", "original must be a Battlefield Boss fact")
    if not isinstance(replay, BattlefieldBossDefeatedFact):
        _fail("invalid_replay_fact", "replay must be a Battlefield Boss fact")
    if defeated_fact_dedupe_key(original) != defeated_fact_dedupe_key(replay):
        raise BoundaryReplayMismatchError(
            "settlement_id_mismatch",
            "defeat fact replay requires the same settlement ID",
        )
    if original.replay_fingerprint() != replay.replay_fingerprint():
        raise BoundaryReplayMismatchError(
            "fact_payload_mismatch",
            "same settlement was delivered with changed authoritative payload",
        )


__all__ = [
    "BATTLEFIELD_BOSS_CLASS",
    "BATTLEFIELD_BOSS_DEFEATED_FACT_V1",
    "BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1",
    "BoundaryContractError",
    "BoundaryContractValidationError",
    "BoundaryReplayMismatchError",
    "BattlefieldBossDefeatedFact",
    "BattlefieldBossEncounterIntent",
    "SERVER_MONSTER_SETTLEMENT_AUTHORITY",
    "WORLD_PROGRESSION_AUTHORITY",
    "assert_defeated_fact_replay_compatible",
    "assert_intent_replay_compatible",
    "defeated_fact_dedupe_key",
    "intent_operation_key",
]
