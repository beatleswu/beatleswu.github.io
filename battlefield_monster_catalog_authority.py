"""E051 fail-closed Battlefield MonsterCatalog authority.

This is the source-side cutover boundary for Battlefield only.  It consumes
the explicit E045 catalog and its versioned context profile references.  The
legacy Battlefield F003/F004/F008 resolvers are intentionally not imported
here: an unresolved or mismatched catalog binding is an operation failure,
never permission to recover through a legacy result.

The authority resolves monster definition data only.  It does not write
player state, settle rewards, select questions, or advance progression.  The
existing combat mutation and settlement writers remain the callers of this
read-only definition boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from monster_catalog_foundation import (
    BATTLEFIELD_BOSS,
    BATTLEFIELD_NORMAL,
    CANONICAL_MONSTER_CATALOG,
    MonsterCatalog,
    MonsterCatalogEntry,
    MissingCombatProfileError,
    UnknownContextError,
    UnknownMonsterError,
    UnknownProfileError,
    VersionedCombatProfile,
    get_monster,
    resolve_context_profile,
)


CATALOG_BATTLEFIELD_AUTHORITY_VERSION = "e051.battlefield-catalog-authority.v1"
CANDIDATE_MONSTER_CATALOG_ACTIVE_AUTHORITY = True
CANDIDATE_LEGACY_F003_F004_F008_ACTIVE_AUTHORITY = False
MONSTER_CATALOG_ACTIVE_AUTHORITY = True
LEGACY_BATTLEFIELD_AUTHORITY_ACTIVE = False
ACTIVE_SILENT_LEGACY_FALLBACK_COUNT = 0
ACTIVE_F003_F004_F008_BATTLEFIELD_AUTHORITY_CALLERS = 0
UNKNOWN_ACTIVE_CONSUMERS = 0
STATUS_READONLY_CUTOVER = True
NORMAL_CUTOVER = True
BOSS_CUTOVER = True
MUTATION_PATH_CUTOVER = True
SETTLEMENT_PATH_RESOLUTION_CUTOVER = True
NORMAL_AUTHORITY_SOURCE = "MONSTER_CATALOG"
BOSS_AUTHORITY_SOURCE = "MONSTER_CATALOG"
ROLLBACK_TARGET_AUTHORITY = "F003_F004_F008"
ROLLBACK_REQUIRES_SCHEMA_CHANGE = False
ROLLBACK_REQUIRES_DATA_REPAIR = False
MONSTER_CATALOG_DIRECT_PLAYER_STATE_MUTATION = False
MONSTER_CATALOG_DIRECT_REWARD_SETTLEMENT = False
PLAYER_STATE_MUTATION_SEMANTICS_CHANGED = False
REWARD_AUTHORITY_CHANGED = False
ITEM_GRANT_AUTHORITY_CHANGED = False
COIN_AUTHORITY_CHANGED = False
PLAYER_STATE_DUPLICATION_RISK = False
REWARD_DUPLICATION_RISK = False
SETTLEMENT_DUPLICATION_RISK = False
PERMANENT_LEGACY_FALLBACK_ALLOWED = False
TIME_BOXED_COMPATIBILITY_BRIDGE_AUTHORIZED = False
GENERATED_PROFILE_FORMULA_FALLBACK = False
ADVENTURE_INCLUDED = False
ADVENTURE_PROFILE_AUTO_INHERITS_BATTLEFIELD = False
LORD_INCLUDED = False
LORD_NUMERIC_PROFILE_CREATED = False
F009_INCLUDED = False
F009_ENABLED = False
F009_CHANGED = False
COMMON_RARE_ELITE_ENABLED = False
COMBAT_CLASS_FREQUENCY_COUPLED = False
BATTLEFIELD_BOSS_IS_LORD = False
NORMAL_BOSS_LORD_COLLAPSED = False
F035_ZONE_USED_FOR_GAMEPLAY = False
F036_BATCH_PLAN_USED_FOR_RUNTIME = False
ART002_GAMEPLAY_AUTHORITY = False
ART003_GAMEPLAY_AUTHORITY = False
SCHEMA_CHANGED = False
MIGRATION_CHANGED = False
DATA_CHANGED = False
PRODUCTION_BATTLEFIELD_AUTHORITY_CHANGED = False

MATCH = "MATCH"
IDENTITY_DRIFT = "IDENTITY_DRIFT"
CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
PROFILE_REF_DRIFT = "PROFILE_REF_DRIFT"
PROFILE_VERSION_DRIFT = "PROFILE_VERSION_DRIFT"
HP_DRIFT = "HP_DRIFT"
ATK_DRIFT = "ATK_DRIFT"
UNKNOWN_MONSTER = "UNKNOWN_MONSTER"
UNKNOWN_PROFILE = "UNKNOWN_PROFILE"
MISSING_PROFILE = "MISSING_PROFILE"

FAIL_CLOSED_DIAGNOSTIC_TYPES = (
    MATCH,
    IDENTITY_DRIFT,
    CONTEXT_MISMATCH,
    PROFILE_REF_DRIFT,
    PROFILE_VERSION_DRIFT,
    HP_DRIFT,
    ATK_DRIFT,
    UNKNOWN_MONSTER,
    UNKNOWN_PROFILE,
    MISSING_PROFILE,
)
FAIL_CLOSED_DIAGNOSTIC_MATRIX_COMPLETE = True

_BATTLEFIELD_CONTEXTS = frozenset((BATTLEFIELD_NORMAL, BATTLEFIELD_BOSS))
_ENCOUNTER_CLASS_TO_CONTEXT = {
    "NORMAL": BATTLEFIELD_NORMAL,
    "BATTLEFIELD_BOSS": BATTLEFIELD_BOSS,
}
_ENCOUNTER_ALIASES = {
    "normal": "NORMAL",
    "NORMAL": "NORMAL",
    "boss": "BATTLEFIELD_BOSS",
    "BOSS": "BATTLEFIELD_BOSS",
    "battlefield_boss": "BATTLEFIELD_BOSS",
    "BATTLEFIELD_BOSS": "BATTLEFIELD_BOSS",
}


class BattlefieldCatalogAuthorityError(ValueError):
    """A deterministic fail-closed Battlefield definition-resolution error."""

    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


class BattlefieldCatalogIdentityDrift(BattlefieldCatalogAuthorityError):
    def __init__(self, message: str):
        super().__init__(message, code=IDENTITY_DRIFT)


class BattlefieldCatalogContextMismatch(BattlefieldCatalogAuthorityError):
    def __init__(self, message: str):
        super().__init__(message, code=CONTEXT_MISMATCH)


class BattlefieldCatalogProfileReferenceDrift(BattlefieldCatalogAuthorityError):
    def __init__(self, message: str):
        super().__init__(message, code=PROFILE_REF_DRIFT)


class BattlefieldCatalogProfileVersionDrift(BattlefieldCatalogAuthorityError):
    def __init__(self, message: str):
        super().__init__(message, code=PROFILE_VERSION_DRIFT)


class BattlefieldCatalogHpDrift(BattlefieldCatalogAuthorityError):
    def __init__(self, message: str):
        super().__init__(message, code=HP_DRIFT)


class BattlefieldCatalogAtkDrift(BattlefieldCatalogAuthorityError):
    def __init__(self, message: str):
        super().__init__(message, code=ATK_DRIFT)


class BattlefieldCatalogUnknownMonster(BattlefieldCatalogAuthorityError):
    def __init__(self, message: str):
        super().__init__(message, code=UNKNOWN_MONSTER)


class BattlefieldCatalogUnknownProfile(BattlefieldCatalogAuthorityError):
    def __init__(self, message: str):
        super().__init__(message, code=UNKNOWN_PROFILE)


class BattlefieldCatalogMissingProfile(BattlefieldCatalogAuthorityError):
    def __init__(self, message: str):
        super().__init__(message, code=MISSING_PROFILE)


def _present(values: Mapping[str, Any], *keys: str) -> tuple[bool, Any]:
    for key in keys:
        if key in values and values[key] not in (None, ""):
            return True, values[key]
    return False, None


def _parse_positive_int(value: Any, *, drift_type: str, field: str) -> int:
    if isinstance(value, bool):
        raise BattlefieldCatalogAuthorityError(
            f"{field} must be a positive integer", code=drift_type
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise BattlefieldCatalogAuthorityError(
            f"{field} must be a positive integer", code=drift_type
        ) from error
    if parsed <= 0:
        raise BattlefieldCatalogAuthorityError(
            f"{field} must be a positive integer", code=drift_type
        )
    return parsed


def _parse_slot(values: Mapping[str, Any]) -> int | None:
    has_slot, raw_slot = _present(values, "roster_slot")
    has_idx, raw_idx = _present(values, "monster_idx")
    slot = None
    if has_slot:
        slot = _parse_positive_int(
            raw_slot, drift_type=IDENTITY_DRIFT, field="roster_slot"
        )
    if has_idx:
        index = _parse_positive_int(
            int(raw_idx) + 1 if str(raw_idx).lstrip("-").isdigit() else None,
            drift_type=IDENTITY_DRIFT,
            field="monster_idx",
        )
        if slot is not None and slot != index:
            raise BattlefieldCatalogIdentityDrift(
                "monster_idx and roster_slot do not identify the same catalog entry"
            )
        slot = index
    return slot


def _normalise_context(value: Any) -> str:
    if value in (None, ""):
        raise BattlefieldCatalogContextMismatch(
            "Battlefield catalog context is required"
        )
    key = str(value).strip()
    if key not in _BATTLEFIELD_CONTEXTS:
        raise BattlefieldCatalogContextMismatch(
            f"unsupported Battlefield catalog context: {value!r}"
        )
    return key


def _normalise_encounter_class(value: Any) -> str:
    if value in (None, ""):
        raise BattlefieldCatalogContextMismatch(
            "Battlefield encounter class is required when supplied"
        )
    normalized = _ENCOUNTER_ALIASES.get(str(value).strip())
    if normalized is None:
        raise BattlefieldCatalogContextMismatch(
            f"unsupported Battlefield encounter class: {value!r}"
        )
    return normalized


def _normalise_zone(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip().lower().replace("-", "_")
    if text.startswith("lv"):
        text = text[2:]
    if text.startswith("zone_"):
        text = text[5:]
    try:
        number = int(text)
    except (TypeError, ValueError):
        return None
    if not 1 <= number <= 10:
        return None
    return f"zone_{number:02d}"


def _find_entry(
    values: Mapping[str, Any],
    *,
    catalog: MonsterCatalog,
) -> MonsterCatalogEntry:
    explicit_id = values.get("monster_id")
    slot = _parse_slot(values)
    entry = None
    if explicit_id not in (None, ""):
        entry = get_monster(explicit_id, catalog=catalog)
        if entry is None:
            raise BattlefieldCatalogUnknownMonster(
                f"unknown canonical Battlefield Monster ID: {explicit_id!r}"
            )
    elif slot is not None:
        entry = next(
            (candidate for candidate in catalog.entries if candidate.roster_slot == slot),
            None,
        )
        if entry is None:
            raise BattlefieldCatalogUnknownMonster(
                f"unknown canonical Battlefield roster slot: {slot!r}"
            )
    else:
        raise BattlefieldCatalogUnknownMonster(
            "Battlefield catalog resolution requires an explicit monster_id or roster_slot"
        )

    if slot is not None and entry.roster_slot != slot:
        raise BattlefieldCatalogIdentityDrift(
            "explicit Monster ID and roster_slot do not identify the same catalog entry"
        )

    zone_present, raw_zone = _present(values, "zone_id", "zone", "stage")
    if zone_present:
        normalized_zone = _normalise_zone(raw_zone)
        if normalized_zone is None or normalized_zone not in entry.zone_eligibility:
            raise BattlefieldCatalogIdentityDrift(
                "Battlefield source Zone does not match the explicit catalog identity"
            )
    return entry


def _profile_reference_values(values: Mapping[str, Any]) -> tuple[Any, Any]:
    ref = values.get("profile_ref")
    if isinstance(ref, Mapping):
        profile_id = ref.get("profile_id")
        version = ref.get("version", ref.get("profile_version"))
    else:
        profile_id = None
        version = None
    if profile_id in (None, ""):
        _has_id, profile_id = _present(
            values, "catalog_profile_id", "profile_id", "stat_profile_id"
        )
    if version in (None, ""):
        _has_version, version = _present(
            values, "catalog_profile_version", "profile_version", "version"
        )
    return profile_id, version


_MUTABLE_BATTLEFIELD_STATE_KEYS = frozenset(
    {
        # These are persisted battle-state values, not a versioned profile
        # reference.  Existing battles may legitimately retain the max HP
        # with which they were started; the Catalog still owns the identity
        # and the explicit profile used for newly materialized encounters.
        "max_hp",
        "current_hp",
        "hp",
        "monster_hp",
        "monster_hp_max",
        "attack",
        "monster_attack",
        "monster_atk",
    }
)


def battlefield_catalog_binding_source(
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return only non-state fields for an active Battlefield lookup.

    The database row has no persisted profile-id/version columns.  Its
    ``monster_idx``/identity binding is resolved against the explicit Catalog;
    ``max_hp`` and ``current_hp`` are mutable state consumed by the existing
    combat transition.  They must not be mistaken for a profile reference.
    Explicit profile-stat fields (``profile_max_hp``/``profile_attack``) are
    retained so callers that possess a profile tuple still receive strict
    drift detection.
    """

    values = dict(source or {})
    return {
        key: value
        for key, value in values.items()
        if key not in _MUTABLE_BATTLEFIELD_STATE_KEYS
    }


def read_battlefield_state_max_hp(source: Mapping[str, Any]) -> int:
    """Read an existing battle's max HP without profile or legacy fallback."""

    has_max_hp, raw_max_hp = _present(source, "max_hp")
    if not has_max_hp:
        raise BattlefieldCatalogHpDrift(
            "Battlefield state has no persisted max_hp"
        )
    return _parse_positive_int(
        raw_max_hp,
        drift_type=HP_DRIFT,
        field="battlefield state max_hp",
    )


@dataclass(frozen=True)
class BattlefieldCatalogAuthorityProfile:
    """Immutable active Battlefield definition resolved from E045."""

    entry: MonsterCatalogEntry
    profile: VersionedCombatProfile
    context: str

    @property
    def canonical_monster_id(self) -> str:
        return self.entry.monster_id

    @property
    def monster_id(self) -> str:
        return self.entry.monster_id

    @property
    def zone_key(self) -> str:
        return self.entry.zone_eligibility[0]

    @property
    def roster_slot(self) -> int:
        return int(self.entry.roster_slot)

    @property
    def encounter_class(self) -> str:
        return self.entry.encounter_class

    @property
    def max_hp(self) -> int:
        return int(self.profile.max_hp)

    @property
    def attack(self) -> int:
        return int(self.profile.attack)

    @property
    def profile_id(self) -> str:
        return self.profile.profile_id

    @property
    def profile_version(self) -> str:
        return self.profile.version

    @property
    def stat_source(self) -> str:
        return "MONSTER_CATALOG_E045_VERSIONED_PROFILE"

    @property
    def legacy_encounter_kind(self) -> str:
        return "boss" if self.encounter_class == "BATTLEFIELD_BOSS" else "normal"

    @property
    def spirit_encounter_class(self) -> str:
        """Adapt the canonical class to the existing Spirit policy vocabulary.

        The Catalog keeps the explicit ``NORMAL`` versus
        ``BATTLEFIELD_BOSS`` authority boundary.  The pre-existing Spirit
        Combat V1 evaluator calls ordinary encounters ``COMMON``; this is a
        consumer vocabulary adapter only and does not grant, select, or
        otherwise authorise a Spirit effect.
        """

        return "COMMON" if self.encounter_class == "NORMAL" else self.encounter_class

    @property
    def stage(self) -> int:
        return (self.roster_slot - 1) // 2 + 1

    def runtime_fields(self) -> dict[str, Any]:
        return {
            "canonical_monster_id": self.canonical_monster_id,
            "monster_id": self.monster_id,
            "zone_key": self.zone_key,
            "roster_slot": self.roster_slot,
            "encounter_class": self.encounter_class,
            "max_hp": self.max_hp,
            "attack": self.attack,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "stat_source": self.stat_source,
            "context": self.context,
            "spirit_encounter_class": self.spirit_encounter_class,
        }

    def __getitem__(self, key: str) -> Any:
        aliases = {
            "attack": self.attack,
            "max_hp": self.max_hp,
            "encounter_kind": self.legacy_encounter_kind,
            "stage": self.stage,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
        }
        if key in aliases:
            return aliases[key]
        return self.runtime_fields()[key]


def resolve_battlefield_catalog_profile(
    source: Mapping[str, Any] | None = None,
    *,
    monster_id: Any = None,
    context: Any = None,
    catalog: MonsterCatalog = CANONICAL_MONSTER_CATALOG,
) -> BattlefieldCatalogAuthorityProfile:
    """Resolve one explicit Battlefield profile or raise a typed failure.

    ``monster_idx`` is accepted only as the existing server-persisted slot
    binding and is immediately checked against the explicit catalog
    ``roster_slot``.  No presentation field, array fallback, display-name
    lookup, formula, or legacy resolver is consulted.
    """

    values = dict(source or {})
    if monster_id not in (None, ""):
        if values.get("monster_id") not in (None, "") and values["monster_id"] != monster_id:
            raise BattlefieldCatalogIdentityDrift(
                "explicit Monster IDs disagree"
            )
        values["monster_id"] = monster_id

    entry = _find_entry(values, catalog=catalog)
    expected_context = _ENCOUNTER_CLASS_TO_CONTEXT.get(entry.encounter_class)
    if expected_context is None:
        raise BattlefieldCatalogContextMismatch(
            f"catalog entry has unsupported Battlefield class: {entry.encounter_class!r}"
        )

    source_context = values.get("context")
    requested_context = context if context not in (None, "") else source_context
    if requested_context in (None, ""):
        requested_context = expected_context
    requested_context = _normalise_context(requested_context)
    if requested_context != expected_context:
        raise BattlefieldCatalogContextMismatch(
            f"catalog entry {entry.monster_id} is not eligible for {requested_context}"
        )

    has_encounter, raw_encounter = _present(
        values, "encounter_class", "encounter_kind", "encounter_type"
    )
    if has_encounter:
        normalized_encounter = _normalise_encounter_class(raw_encounter)
        if normalized_encounter != entry.encounter_class:
            raise BattlefieldCatalogContextMismatch(
                "Battlefield encounter class does not match catalog context"
            )

    try:
        profile = resolve_context_profile(
            entry.monster_id,
            requested_context,
            catalog=catalog,
        )
    except UnknownMonsterError as error:
        raise BattlefieldCatalogUnknownMonster(str(error)) from error
    except UnknownProfileError as error:
        raise BattlefieldCatalogUnknownProfile(str(error)) from error
    except MissingCombatProfileError as error:
        raise BattlefieldCatalogMissingProfile(str(error)) from error
    except UnknownContextError as error:
        raise BattlefieldCatalogContextMismatch(str(error)) from error

    source_profile_id, source_profile_version = _profile_reference_values(values)
    if source_profile_id not in (None, "") and str(source_profile_id) != profile.profile_id:
        raise BattlefieldCatalogProfileReferenceDrift(
            "Battlefield profile ID does not match the explicit catalog reference"
        )
    if source_profile_version not in (None, "") and str(source_profile_version) != profile.version:
        raise BattlefieldCatalogProfileVersionDrift(
            "Battlefield profile version does not match the explicit catalog reference"
        )

    has_hp, raw_hp = _present(values, "profile_max_hp", "max_hp", "monster_hp_max")
    if has_hp:
        observed_hp = _parse_positive_int(
            raw_hp, drift_type=HP_DRIFT, field="profile_max_hp"
        )
        if observed_hp != int(profile.max_hp):
            raise BattlefieldCatalogHpDrift(
                "Battlefield profile HP does not match the explicit catalog profile"
            )

    has_atk, raw_atk = _present(
        values, "profile_attack", "profile_atk", "attack", "monster_attack"
    )
    if has_atk:
        observed_atk = _parse_positive_int(
            raw_atk, drift_type=ATK_DRIFT, field="profile_attack"
        )
        if observed_atk != int(profile.attack):
            raise BattlefieldCatalogAtkDrift(
                "Battlefield profile ATK does not match the explicit catalog profile"
            )

    return BattlefieldCatalogAuthorityProfile(
        entry=entry,
        profile=profile,
        context=requested_context,
    )


def battlefield_catalog_identity_payload(
    authority: BattlefieldCatalogAuthorityProfile,
) -> dict[str, Any]:
    """Project catalog identity fields without adding mutation authority."""

    return {
        "monster_id": authority.monster_id,
        "zone_id": authority.zone_key,
        "roster_slot": authority.roster_slot,
        "encounter_class": authority.encounter_class,
        "family_id": authority.entry.family_id,
        "display_name_key": authority.entry.display_name_key,
        "monster_identity_resolved": True,
    }


__all__ = [
    "ATK_DRIFT",
    "ADVENTURE_INCLUDED",
    "ADVENTURE_PROFILE_AUTO_INHERITS_BATTLEFIELD",
    "ART002_GAMEPLAY_AUTHORITY",
    "ART003_GAMEPLAY_AUTHORITY",
    "ACTIVE_F003_F004_F008_BATTLEFIELD_AUTHORITY_CALLERS",
    "ACTIVE_SILENT_LEGACY_FALLBACK_COUNT",
    "BOSS_AUTHORITY_SOURCE",
    "BATTLEFIELD_BOSS",
    "BATTLEFIELD_BOSS_IS_LORD",
    "BATTLEFIELD_NORMAL",
    "BattlefieldCatalogAuthorityError",
    "BattlefieldCatalogAuthorityProfile",
    "BattlefieldCatalogAtkDrift",
    "BattlefieldCatalogContextMismatch",
    "BattlefieldCatalogHpDrift",
    "BattlefieldCatalogIdentityDrift",
    "BattlefieldCatalogMissingProfile",
    "BattlefieldCatalogProfileReferenceDrift",
    "BattlefieldCatalogProfileVersionDrift",
    "BattlefieldCatalogUnknownMonster",
    "BattlefieldCatalogUnknownProfile",
    "battlefield_catalog_binding_source",
    "CANDIDATE_LEGACY_F003_F004_F008_ACTIVE_AUTHORITY",
    "CANDIDATE_MONSTER_CATALOG_ACTIVE_AUTHORITY",
    "COMMON_RARE_ELITE_ENABLED",
    "COMBAT_CLASS_FREQUENCY_COUPLED",
    "COIN_AUTHORITY_CHANGED",
    "CONTEXT_MISMATCH",
    "DATA_CHANGED",
    "FAIL_CLOSED_DIAGNOSTIC_MATRIX_COMPLETE",
    "FAIL_CLOSED_DIAGNOSTIC_TYPES",
    "F009_CHANGED",
    "F009_ENABLED",
    "F009_INCLUDED",
    "F035_ZONE_USED_FOR_GAMEPLAY",
    "F036_BATCH_PLAN_USED_FOR_RUNTIME",
    "GENERATED_PROFILE_FORMULA_FALLBACK",
    "HP_DRIFT",
    "IDENTITY_DRIFT",
    "ITEM_GRANT_AUTHORITY_CHANGED",
    "LORD_INCLUDED",
    "LORD_NUMERIC_PROFILE_CREATED",
    "LEGACY_BATTLEFIELD_AUTHORITY_ACTIVE",
    "MATCH",
    "MIGRATION_CHANGED",
    "MISSING_PROFILE",
    "MONSTER_CATALOG_DIRECT_PLAYER_STATE_MUTATION",
    "MONSTER_CATALOG_DIRECT_REWARD_SETTLEMENT",
    "MONSTER_CATALOG_ACTIVE_AUTHORITY",
    "MUTATION_PATH_CUTOVER",
    "NORMAL_AUTHORITY_SOURCE",
    "NORMAL_BOSS_LORD_COLLAPSED",
    "NORMAL_CUTOVER",
    "SETTLEMENT_PATH_RESOLUTION_CUTOVER",
    "STATUS_READONLY_CUTOVER",
    "PERMANENT_LEGACY_FALLBACK_ALLOWED",
    "PLAYER_STATE_DUPLICATION_RISK",
    "PLAYER_STATE_MUTATION_SEMANTICS_CHANGED",
    "PROFILE_REF_DRIFT",
    "PROFILE_VERSION_DRIFT",
    "PRODUCTION_BATTLEFIELD_AUTHORITY_CHANGED",
    "read_battlefield_state_max_hp",
    "REWARD_AUTHORITY_CHANGED",
    "REWARD_DUPLICATION_RISK",
    "ROLLBACK_REQUIRES_DATA_REPAIR",
    "ROLLBACK_REQUIRES_SCHEMA_CHANGE",
    "ROLLBACK_TARGET_AUTHORITY",
    "SCHEMA_CHANGED",
    "SETTLEMENT_DUPLICATION_RISK",
    "TIME_BOXED_COMPATIBILITY_BRIDGE_AUTHORIZED",
    "UNKNOWN_ACTIVE_CONSUMERS",
    "UNKNOWN_MONSTER",
    "UNKNOWN_PROFILE",
    "battlefield_catalog_identity_payload",
    "resolve_battlefield_catalog_profile",
]
