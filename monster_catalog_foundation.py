"""Candidate-only canonical Monster catalog foundation for E045.

This module gives future consumers one explicit identity/catalog shape without
activating a new gameplay path.  The current 20-entry Battlefield registry is
the only authoritative catalog data available here; it is referenced through
the existing F003/F004 modules rather than copied into a second live source.

Adventure Normal and Lord entries deliberately have no profile reference yet.
That absence is a contract result, not permission to inherit Battlefield stats
or fabricate Lord numbers.  ``app.py`` does not import this module in E045.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from monster_identity import (
    ENCOUNTER_CLASS_BATTLEFIELD_BOSS,
    ENCOUNTER_CLASS_NORMAL,
)
from monster_profiles import (
    CANONICAL_MONSTER_PROFILE_REGISTRY,
    MonsterProfileRegistry,
    get_stat_profile,
)


CATALOG_VERSION = "e045.catalog.v1"
PROFILE_REGISTRY_VERSION = "e045.profile.v1"
FOUNDATION_STATUS = "CANDIDATE_NOT_LIVE"
NEW_FOUNDATION_RUNTIME_ACTIVE = False
MONSTER_ID_IS_EXPLICIT = True
CONTEXT_PROFILE_REFERENCE_EXPLICIT = True
PROFILE_REFERENCE_VERSIONED = True
MISSING_PROFILE_FAIL_CLOSED = True
UNKNOWN_MONSTER_FAIL_CLOSED = True
UNKNOWN_PROFILE_FAIL_CLOSED = True
ENCOUNTER_CLASS_EXPLICIT = True
NORMAL_BOSS_LORD_COLLAPSED = False
FABRICATED_LORD_NUMERIC_PROFILE = False
ADVENTURE_PROFILE_AUTO_INHERITS_BATTLEFIELD = False
CURRENT_RUNTIME_AUTHORITY_PRESERVED = True
ZONE_QUESTION_STAGE_MAPPING_CHANGED = False

ADVENTURE_NORMAL = "ADVENTURE_NORMAL"
BATTLEFIELD_NORMAL = "BATTLEFIELD_NORMAL"
BATTLEFIELD_BOSS = "BATTLEFIELD_BOSS"
LORD = "LORD"
SUPPORTED_CONTEXTS = frozenset(
    (ADVENTURE_NORMAL, BATTLEFIELD_NORMAL, BATTLEFIELD_BOSS, LORD)
)

ART002_GAMEPLAY_AUTHORITY = False
ART002_AUTOPROMOTED_COUNT = 0
COMMON_RARE_ELITE_ENABLED = False
COMBAT_CLASS_FREQUENCY_COUPLED = False
ELO_MONSTER_STAT_AUTHORITY = False
ROSTER_COUNT_USED_FOR_HP_ATK = False

# This is an evidence assertion from the E043 audit, not a runtime mapping.
# It is kept here so a future catalog task cannot silently normalize the
# existing books/question-stage relationship while adding Monster data.
ZONE_QUESTION_STAGE_MAPPING_RUNTIME_CONSUMED = False
ZONE_QUESTION_STAGE_EVIDENCE_STATUS = "OBSERVED_NOT_GAMEPLAY_AUTHORITY"
ZONE_QUESTION_STAGE_EVIDENCE = (
    ("k26_30", "LV1", "LV1"),
    ("k21_25", "LV2", "LV1"),
    ("k16_20", "LV3", "LV2"),
    ("k11_15", "LV4", "LV3"),
    ("k6_10", "LV5", "LV4"),
    ("k1_5", "LV6", "LV5"),
    ("d1_2", "LV7", "LV7"),
    ("d3_4", "LV8", "LV8"),
    ("d5_6", "LV9", "LV9"),
    ("d7_plus", "LV10", "LV10"),
)


class MonsterCatalogFoundationError(ValueError):
    """Base error for explicit candidate-catalog resolution failures."""


class UnknownMonsterError(MonsterCatalogFoundationError):
    """Raised when no exact canonical Monster ID exists."""


class UnknownProfileError(MonsterCatalogFoundationError):
    """Raised when no exact profile ID/version exists."""


class UnknownContextError(MonsterCatalogFoundationError):
    """Raised when a caller requests an unsupported encounter context."""


class MissingCombatProfileError(MonsterCatalogFoundationError):
    """Raised when a known Monster has no profile for the requested context."""


@dataclass(frozen=True)
class CombatProfileReference:
    """An explicit, versioned link from a catalog entry to a profile."""

    profile_id: str
    version: str


@dataclass(frozen=True)
class VersionedCombatProfile:
    """Immutable candidate profile values with explicit provenance."""

    profile_id: str
    version: str
    max_hp: int
    attack: int
    source_authority: str
    status: str = FOUNDATION_STATUS
    generated_from_zone: bool = False
    generated_from_elo: bool = False
    generated_from_roster_count: bool = False
    combat_class: str | None = None


@dataclass(frozen=True)
class MonsterCatalogEntry:
    """One stable identity and its context-specific profile references."""

    monster_id: str
    display_name_key: str
    family_id: str
    zone_eligibility: tuple[str, ...]
    encounter_class: str
    context_eligibility: tuple[str, ...]
    context_profile_refs: Mapping[str, CombatProfileReference | None]
    catalog_version: str = CATALOG_VERSION
    status: str = FOUNDATION_STATUS
    combat_class: str | None = None
    encounter_frequency_policy: str | None = None
    gameplay_variant_ref: str | None = None
    art_content_ref: str | None = None


@dataclass(frozen=True)
class MonsterCatalog:
    """Candidate catalog and profile registry exposed through exact reads."""

    entries: tuple[MonsterCatalogEntry, ...]
    by_id: Mapping[str, MonsterCatalogEntry]
    profiles: Mapping[tuple[str, str], VersionedCombatProfile]
    version: str = CATALOG_VERSION
    status: str = FOUNDATION_STATUS


def _frozen_mapping(values: Mapping[Any, Any]) -> Mapping[Any, Any]:
    return MappingProxyType(dict(values))


def _profile_ref(profile_id: str) -> CombatProfileReference:
    return CombatProfileReference(
        profile_id=profile_id,
        version=PROFILE_REGISTRY_VERSION,
    )


def _build_versioned_profiles(
    registry: MonsterProfileRegistry,
) -> Mapping[tuple[str, str], VersionedCombatProfile]:
    profiles: dict[tuple[str, str], VersionedCombatProfile] = {}
    for canonical in registry.profiles:
        stat = get_stat_profile(canonical.stat_profile_id, registry=registry)
        if stat is None:
            raise MissingCombatProfileError(
                f"current profile has no stat source: {canonical.monster_id}"
            )
        profile = VersionedCombatProfile(
            profile_id=canonical.stat_profile_id,
            version=PROFILE_REGISTRY_VERSION,
            max_hp=int(stat.max_hp),
            attack=int(stat.attack),
            source_authority="F004_MONSTER_PROFILE_REGISTRY",
        )
        key = (profile.profile_id, profile.version)
        if key in profiles:
            raise ValueError(f"duplicate versioned profile reference: {key}")
        profiles[key] = profile
    return _frozen_mapping(profiles)


def _build_entries(
    registry: MonsterProfileRegistry,
) -> tuple[MonsterCatalogEntry, ...]:
    entries: list[MonsterCatalogEntry] = []
    for canonical in registry.profiles:
        if canonical.encounter_class == ENCOUNTER_CLASS_NORMAL:
            battlefield_context = BATTLEFIELD_NORMAL
        elif canonical.encounter_class == ENCOUNTER_CLASS_BATTLEFIELD_BOSS:
            battlefield_context = BATTLEFIELD_BOSS
        else:
            raise ValueError(
                f"unsupported current encounter class: {canonical.encounter_class}"
            )

        refs: dict[str, CombatProfileReference | None] = {
            ADVENTURE_NORMAL: None,
            BATTLEFIELD_NORMAL: None,
            BATTLEFIELD_BOSS: None,
            LORD: None,
        }
        refs[battlefield_context] = _profile_ref(canonical.stat_profile_id)
        entries.append(
            MonsterCatalogEntry(
                monster_id=canonical.monster_id,
                display_name_key=canonical.display_key,
                family_id=canonical.taxonomy_family,
                zone_eligibility=(canonical.zone_key,),
                encounter_class=canonical.encounter_class,
                context_eligibility=(battlefield_context,),
                context_profile_refs=_frozen_mapping(refs),
                # ART002 is deliberately not guessed from legacy art or name.
                art_content_ref=None,
            )
        )
    return tuple(entries)


def _build_catalog(
    registry: MonsterProfileRegistry = CANONICAL_MONSTER_PROFILE_REGISTRY,
) -> MonsterCatalog:
    entries = _build_entries(registry)
    by_id = {entry.monster_id: entry for entry in entries}
    if len(by_id) != len(entries):
        raise ValueError("canonical Monster IDs must be unique")
    return MonsterCatalog(
        entries=entries,
        by_id=_frozen_mapping(by_id),
        profiles=_build_versioned_profiles(registry),
    )


CANONICAL_MONSTER_CATALOG = _build_catalog()
CURRENT_BATTLEFIELD_PROFILE_SNAPSHOT = tuple(
    (
        entry.monster_id,
        entry.zone_eligibility[0],
        entry.encounter_class,
        CANONICAL_MONSTER_CATALOG.profiles[
            (
                entry.context_profile_refs[
                    next(iter(entry.context_eligibility))
                ].profile_id,
                PROFILE_REGISTRY_VERSION,
            )
        ].max_hp,
        CANONICAL_MONSTER_CATALOG.profiles[
            (
                entry.context_profile_refs[
                    next(iter(entry.context_eligibility))
                ].profile_id,
                PROFILE_REGISTRY_VERSION,
            )
        ].attack,
    )
    for entry in CANONICAL_MONSTER_CATALOG.entries
)


def _exact_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def get_monster(
    monster_id: Any,
    *,
    catalog: MonsterCatalog = CANONICAL_MONSTER_CATALOG,
) -> MonsterCatalogEntry | None:
    """Return an exact Monster entry, or ``None`` without fuzzy fallback."""

    key = _exact_text(monster_id)
    if key is None:
        return None
    return catalog.by_id.get(key)


def get_profile(
    profile_id: Any,
    version: Any,
    *,
    catalog: MonsterCatalog = CANONICAL_MONSTER_CATALOG,
) -> VersionedCombatProfile | None:
    """Return an exact profile ID/version, or ``None`` without latest fallback."""

    profile_key = _exact_text(profile_id)
    version_key = _exact_text(version)
    if profile_key is None or version_key is None:
        return None
    return catalog.profiles.get((profile_key, version_key))


def resolve_context_profile(
    monster_id: Any,
    context: Any,
    *,
    catalog: MonsterCatalog = CANONICAL_MONSTER_CATALOG,
) -> VersionedCombatProfile:
    """Resolve one explicit context profile and fail closed when unavailable."""

    entry = get_monster(monster_id, catalog=catalog)
    if entry is None:
        raise UnknownMonsterError(f"unknown canonical Monster ID: {monster_id!r}")
    context_key = _exact_text(context)
    if context_key not in SUPPORTED_CONTEXTS:
        raise UnknownContextError(f"unknown Monster context: {context!r}")
    reference = entry.context_profile_refs.get(context_key)
    if reference is None:
        raise MissingCombatProfileError(
            f"no profile for Monster {entry.monster_id} in context {context_key}"
        )
    profile = get_profile(
        reference.profile_id,
        reference.version,
        catalog=catalog,
    )
    if profile is None:
        raise UnknownProfileError(
            f"missing exact profile: {reference.profile_id}@{reference.version}"
        )
    return profile


def list_monsters_for_zone(
    zone: Any,
    context: Any,
    *,
    catalog: MonsterCatalog = CANONICAL_MONSTER_CATALOG,
) -> tuple[MonsterCatalogEntry, ...]:
    """List only exact Zone/context memberships with explicit profiles.

    The current catalog has authoritative membership only for Battlefield
    contexts.  Adventure Normal and Lord therefore return an empty tuple;
    they do not inherit or synthesize a profile.
    """

    zone_key = _exact_text(zone)
    context_key = _exact_text(context)
    if context_key not in SUPPORTED_CONTEXTS:
        raise UnknownContextError(f"unknown Monster context: {context!r}")
    if zone_key is None:
        return ()
    return tuple(
        entry
        for entry in catalog.entries
        if zone_key in entry.zone_eligibility
        and context_key in entry.context_eligibility
        and entry.context_profile_refs.get(context_key) is not None
    )


__all__ = [
    "ADVENTURE_NORMAL",
    "ADVENTURE_PROFILE_AUTO_INHERITS_BATTLEFIELD",
    "ART002_AUTOPROMOTED_COUNT",
    "ART002_GAMEPLAY_AUTHORITY",
    "BATTLEFIELD_BOSS",
    "BATTLEFIELD_NORMAL",
    "CATALOG_VERSION",
    "CANONICAL_MONSTER_CATALOG",
    "COMMON_RARE_ELITE_ENABLED",
    "COMBAT_CLASS_FREQUENCY_COUPLED",
    "CombatProfileReference",
    "CONTEXT_PROFILE_REFERENCE_EXPLICIT",
    "CURRENT_BATTLEFIELD_PROFILE_SNAPSHOT",
    "CURRENT_RUNTIME_AUTHORITY_PRESERVED",
    "ELO_MONSTER_STAT_AUTHORITY",
    "ENCOUNTER_CLASS_EXPLICIT",
    "FABRICATED_LORD_NUMERIC_PROFILE",
    "FOUNDATION_STATUS",
    "LORD",
    "MISSING_PROFILE_FAIL_CLOSED",
    "MONSTER_ID_IS_EXPLICIT",
    "MissingCombatProfileError",
    "MonsterCatalog",
    "MonsterCatalogEntry",
    "MonsterCatalogFoundationError",
    "NORMAL_BOSS_LORD_COLLAPSED",
    "NEW_FOUNDATION_RUNTIME_ACTIVE",
    "PROFILE_REFERENCE_VERSIONED",
    "PROFILE_REGISTRY_VERSION",
    "ROSTER_COUNT_USED_FOR_HP_ATK",
    "SUPPORTED_CONTEXTS",
    "UnknownContextError",
    "UnknownMonsterError",
    "UnknownProfileError",
    "UNKNOWN_MONSTER_FAIL_CLOSED",
    "UNKNOWN_PROFILE_FAIL_CLOSED",
    "VersionedCombatProfile",
    "ZONE_QUESTION_STAGE_EVIDENCE",
    "ZONE_QUESTION_STAGE_EVIDENCE_STATUS",
    "ZONE_QUESTION_STAGE_MAPPING_CHANGED",
    "ZONE_QUESTION_STAGE_MAPPING_RUNTIME_CONSUMED",
    "get_monster",
    "get_profile",
    "list_monsters_for_zone",
    "resolve_context_profile",
]
