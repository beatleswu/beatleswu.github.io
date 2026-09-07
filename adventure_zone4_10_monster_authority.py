"""Adventure identity consumption for the canonical Zone 4-10 Monster set.

This module is deliberately an adapter, not a second Monster authority.  It
returns the immutable identity objects from
``adventure_zone4_10_monster_identity_authority`` and derives only lookup
indexes from that canonical tuple.

No Adventure roster, question binding, combat profile, reward, drop,
Boss/Lord, or persistence authority is admitted here.
"""

from __future__ import annotations

from collections import Counter
from types import MappingProxyType
from typing import Final, Iterable, Mapping

from adventure_zone4_10_monster_identity_authority import (
    AdventureZoneMonsterIdentity,
    IDENTITY_AUTHORITY_VERSION,
    IDENTITY_PROVENANCE,
    RUNTIME_ADMISSION_PERFORMED as _CANONICAL_RUNTIME_ADMISSION_PERFORMED,
    ZONE4_10_MONSTER_IDENTITIES as _CANONICAL_IDENTITIES,
)


ADVENTURE_IDENTITY_AUTHORITY_VERSION: Final = IDENTITY_AUTHORITY_VERSION
ADVENTURE_IDENTITY_PROVENANCE: Final = IDENTITY_PROVENANCE

# C2A is an identity-consumption layer only.  These flags make the boundary
# explicit without creating a runtime roster or any gameplay profile fields.
ADVENTURE_RUNTIME_ADMISSION_PERFORMED: Final = False
RUNTIME_READY_COUNT: Final = 0
QUESTION_BINDING_CREATED: Final = False
PROFILE_BINDING_CREATED: Final = False
COMBAT_BINDING_CREATED: Final = False
REWARD_BINDING_CREATED: Final = False
DROP_BINDING_CREATED: Final = False
PERSISTED_ENCOUNTER_BINDING_CREATED: Final = False
BOSS_LORD_IDENTITY_CREATED: Final = False
ELITE_IDENTITY_CREATED: Final = False

ADVENTURE_ZONE_KEYS: tuple[str, ...] = (
    "Z4",
    "Z5",
    "Z6",
    "Z7",
    "Z8",
    "Z9",
    "Z10",
)
EXPECTED_ZONE_COUNTS: Mapping[str, int] = MappingProxyType(
    {
        "Z4": 12,
        "Z5": 12,
        "Z6": 12,
        "Z7": 12,
        "Z8": 11,
        "Z9": 10,
        "Z10": 10,
    }
)

# This is a fence, not an alias table.  The historical Battlefield anchors
# remain identity records but receive zero automatic Battlefield aliases.
LEGACY_BATTLEFIELD_AUTO_ALIAS_COUNT: Final = 0


class AdventureMonsterIdentityAuthorityError(ValueError):
    """The canonical identity input is malformed or outside the C2A contract."""


class AdventureMonsterIdentityLookupError(AdventureMonsterIdentityAuthorityError):
    """An exact identity or zone lookup cannot be satisfied safely."""


def _validate_consumed_identity_authority(
    identities: Iterable[AdventureZoneMonsterIdentity],
) -> tuple[AdventureZoneMonsterIdentity, ...]:
    """Validate the imported B7 source before deriving any indexes.

    The adapter intentionally does not repeat the 79 names or assignments.
    This validator protects against a malformed imported authority and checks
    the small C2A boundary contract around it.
    """

    records = tuple(identities)
    if len(records) != 79:
        raise AdventureMonsterIdentityAuthorityError(
            "canonical Zone 4-10 identity authority must contain 79 records"
        )
    if not ADVENTURE_IDENTITY_AUTHORITY_VERSION.strip():
        raise AdventureMonsterIdentityAuthorityError(
            "canonical identity authority version is required"
        )
    if not ADVENTURE_IDENTITY_PROVENANCE.strip():
        raise AdventureMonsterIdentityAuthorityError(
            "canonical identity provenance is required"
        )
    if _CANONICAL_RUNTIME_ADMISSION_PERFORMED:
        raise AdventureMonsterIdentityAuthorityError(
            "canonical identity source unexpectedly admits runtime behavior"
        )

    seen_ids: set[str] = set()
    for identity in records:
        if not isinstance(identity, AdventureZoneMonsterIdentity):
            raise AdventureMonsterIdentityAuthorityError(
                "canonical identity record has an unexpected type"
            )
        if set(identity.as_record()) != {
            "M_ID",
            "canonical_name_zh",
            "canonical_name_en",
            "zone_key",
        }:
            raise AdventureMonsterIdentityAuthorityError(
                "canonical identity record contains gameplay fields"
            )
        monster_id = str(identity.monster_id).strip()
        if not monster_id or monster_id in seen_ids:
            raise AdventureMonsterIdentityAuthorityError(
                "canonical Zone 4-10 M-IDs must be non-empty and unique"
            )
        seen_ids.add(monster_id)
        if identity.zone_key not in ADVENTURE_ZONE_KEYS:
            raise AdventureMonsterIdentityAuthorityError(
                f"unsupported Zone 4-10 identity zone: {identity.zone_key!r}"
            )
        if monster_id.startswith("legacy_bf_"):
            raise AdventureMonsterIdentityAuthorityError(
                "legacy Battlefield identities cannot enter the Adventure set"
            )

    observed_counts = Counter(identity.zone_key for identity in records)
    if dict(observed_counts) != dict(EXPECTED_ZONE_COUNTS):
        raise AdventureMonsterIdentityAuthorityError(
            "canonical Zone 4-10 identity zone counts differ from the contract"
        )

    m073 = next((identity for identity in records if identity.monster_id == "M073"), None)
    if m073 is None or (
        m073.canonical_name_zh,
        m073.canonical_name_en,
        m073.zone_key,
    ) != ("黃銅魔像", "Brass Golem", "Z10"):
        raise AdventureMonsterIdentityAuthorityError(
            "M073 must remain 黃銅魔像 / Brass Golem / Z10"
        )
    return records


# The adapter consumes the canonical tuple by identity; it does not recreate
# the 79-entry truth set.  All maps below are mechanically derived indexes.
ADVENTURE_ZONE4_10_MONSTER_IDENTITIES: tuple[AdventureZoneMonsterIdentity, ...] = (
    _validate_consumed_identity_authority(_CANONICAL_IDENTITIES)
)
ADVENTURE_ZONE4_10_MONSTER_IDENTITY_BY_ID: Mapping[
    str, AdventureZoneMonsterIdentity
] = MappingProxyType(
    {
        identity.monster_id: identity
        for identity in ADVENTURE_ZONE4_10_MONSTER_IDENTITIES
    }
)
ADVENTURE_ZONE4_10_MONSTER_IDENTITIES_BY_ZONE: Mapping[
    str, tuple[AdventureZoneMonsterIdentity, ...]
] = MappingProxyType(
    {
        zone_key: tuple(
            identity
            for identity in ADVENTURE_ZONE4_10_MONSTER_IDENTITIES
            if identity.zone_key == zone_key
        )
        for zone_key in ADVENTURE_ZONE_KEYS
    }
)


def _normalize_monster_id(monster_id: object) -> str | None:
    if monster_id is None:
        return None
    normalized = str(monster_id).strip()
    return normalized or None


def _require_zone_key(zone_key: object) -> str:
    if zone_key is None:
        raise AdventureMonsterIdentityLookupError("zone_key is required")
    normalized = str(zone_key).strip()
    if normalized not in ADVENTURE_ZONE_KEYS:
        raise AdventureMonsterIdentityLookupError(
            f"unknown Zone 4-10 Adventure zone: {zone_key!r}"
        )
    return normalized


def all_adventure_monster_identities() -> tuple[AdventureZoneMonsterIdentity, ...]:
    """Return all canonical Zone 4-10 identity objects without copying them."""

    return ADVENTURE_ZONE4_10_MONSTER_IDENTITIES


def adventure_monster_identities_for_zone(
    zone_key: object,
) -> tuple[AdventureZoneMonsterIdentity, ...]:
    """Return the exact canonical identity set for one authoritative zone."""

    return ADVENTURE_ZONE4_10_MONSTER_IDENTITIES_BY_ZONE[_require_zone_key(zone_key)]


def get_adventure_monster_identity(
    monster_id: object,
    *,
    zone_key: object | None = None,
) -> AdventureZoneMonsterIdentity | None:
    """Return an exact identity, or ``None`` for unknown/wrong-zone input."""

    normalized_id = _normalize_monster_id(monster_id)
    if normalized_id is None:
        return None
    identity = ADVENTURE_ZONE4_10_MONSTER_IDENTITY_BY_ID.get(normalized_id)
    if identity is None:
        return None
    if zone_key is not None and identity.zone_key != str(zone_key).strip():
        return None
    return identity


def require_adventure_monster_identity(
    monster_id: object,
    *,
    zone_key: object | None = None,
) -> AdventureZoneMonsterIdentity:
    """Require an exact identity and fail closed for unknown/wrong-zone input."""

    identity = get_adventure_monster_identity(monster_id, zone_key=zone_key)
    if identity is None:
        raise AdventureMonsterIdentityLookupError(
            f"unknown or wrong-zone Adventure Monster identity: "
            f"monster_id={monster_id!r}, zone_key={zone_key!r}"
        )
    return identity


def is_adventure_monster_identity(monster_id: object) -> bool:
    """Return whether an exact M-ID belongs to the canonical Adventure set."""

    return get_adventure_monster_identity(monster_id) is not None


__all__ = [
    "ADVENTURE_IDENTITY_AUTHORITY_VERSION",
    "ADVENTURE_IDENTITY_PROVENANCE",
    "ADVENTURE_RUNTIME_ADMISSION_PERFORMED",
    "ADVENTURE_ZONE4_10_MONSTER_IDENTITIES",
    "ADVENTURE_ZONE4_10_MONSTER_IDENTITIES_BY_ZONE",
    "ADVENTURE_ZONE4_10_MONSTER_IDENTITY_BY_ID",
    "ADVENTURE_ZONE_KEYS",
    "AdventureMonsterIdentityAuthorityError",
    "AdventureMonsterIdentityLookupError",
    "AdventureZoneMonsterIdentity",
    "COMBAT_BINDING_CREATED",
    "DROP_BINDING_CREATED",
    "ELITE_IDENTITY_CREATED",
    "EXPECTED_ZONE_COUNTS",
    "LEGACY_BATTLEFIELD_AUTO_ALIAS_COUNT",
    "PERSISTED_ENCOUNTER_BINDING_CREATED",
    "PROFILE_BINDING_CREATED",
    "QUESTION_BINDING_CREATED",
    "REWARD_BINDING_CREATED",
    "RUNTIME_READY_COUNT",
    "all_adventure_monster_identities",
    "adventure_monster_identities_for_zone",
    "get_adventure_monster_identity",
    "is_adventure_monster_identity",
    "require_adventure_monster_identity",
]
