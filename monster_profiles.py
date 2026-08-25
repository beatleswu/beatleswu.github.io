"""Canonical Monster profile registry for F004.

This module adds a profile/data authority behind the F003 stable identity
adapter.  It is intentionally not wired into application settlement yet:
F004 owns the profile contract and truthful legacy references only.  Combat,
drops, rewards, quests, persistence, and Lord Trial authority remain owned by
their existing runtime paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from monster_identity import (
    CANONICAL_BATTLEFIELD_MONSTER_COUNT,
    CANONICAL_MONSTER_IDENTITY_REGISTRY,
    CanonicalMonsterIdentity,
    MonsterIdentityRegistry,
)


@dataclass(frozen=True)
class MonsterStatProfile:
    """The effective stat fields that currently exist for battlefield monsters."""

    profile_id: str
    max_hp: int
    attack: int


@dataclass(frozen=True)
class MonsterDropProfile:
    """A truthful reference to the existing legacy drop execution path."""

    profile_id: str
    legacy_monster_type: str
    source_ref: str = "app._roll_loot + EQUIPMENT_DEFS.drop_from"
    status: str = "LEGACY_COMPATIBILITY_REFERENCE"


@dataclass(frozen=True)
class MonsterRewardProfile:
    """A truthful reference to current battlefield reward settlement."""

    profile_id: str
    source_ref: str = "app._update_monster_and_quests"
    status: str = "LEGACY_COMPATIBILITY_REFERENCE"


@dataclass(frozen=True)
class MonsterPresentationProfile:
    """Presentation metadata only; it is not gameplay identity authority."""

    profile_id: str
    display_key: str
    source_ref: str = "F003 display_key + existing battlefield avatar mapping"


@dataclass(frozen=True)
class CanonicalMonsterProfile:
    """One canonical profile for one F003 Monster identity."""

    monster_id: str
    roster_slot: int
    zone_key: str
    encounter_class: str
    taxonomy_family: str
    display_key: str
    stat_profile_id: str
    drop_profile_id: str
    reward_profile_id: str
    presentation_profile_id: str
    enabled: bool
    legacy_aliases: tuple[str, ...] = ()
    boss_role: str | None = None


@dataclass(frozen=True)
class MonsterProfileRegistry:
    profiles: tuple[CanonicalMonsterProfile, ...]
    by_id: Mapping[str, CanonicalMonsterProfile]
    by_roster_slot: Mapping[int, CanonicalMonsterProfile]
    stat_profiles: Mapping[str, MonsterStatProfile]
    drop_profiles: Mapping[str, MonsterDropProfile]
    reward_profiles: Mapping[str, MonsterRewardProfile]
    presentation_profiles: Mapping[str, MonsterPresentationProfile]


# These are copied from the current server-owned _BATTLEFIELD_ROSTER at the
# F004 foundation boundary.  The tests compare them to the live roster source
# so a future change cannot silently drift this foundation snapshot.
_CURRENT_BATTLEFIELD_STATS: dict[str, tuple[int, int]] = {
    "legacy_bf_01_normal": (80, 2),
    "legacy_bf_01_boss": (100, 2),
    "legacy_bf_02_normal": (130, 3),
    "legacy_bf_02_boss": (160, 4),
    "legacy_bf_03_normal": (200, 4),
    "legacy_bf_03_boss": (240, 5),
    "legacy_bf_04_normal": (220, 5),
    "legacy_bf_04_boss": (260, 6),
    "legacy_bf_05_normal": (260, 6),
    "legacy_bf_05_boss": (290, 7),
    "legacy_bf_06_normal": (520, 12),
    "legacy_bf_06_boss": (700, 14),
    "legacy_bf_07_normal": (760, 16),
    "legacy_bf_07_boss": (920, 18),
    "legacy_bf_08_normal": (1100, 20),
    "legacy_bf_08_boss": (1350, 22),
    "legacy_bf_09_normal": (1700, 28),
    "legacy_bf_09_boss": (2000, 32),
    "legacy_bf_10_normal": (2400, 36),
    "legacy_bf_10_boss": (2800, 40),
}


def _build_stat_profiles() -> dict[str, MonsterStatProfile]:
    profiles = {
        f"stat_{monster_id}": MonsterStatProfile(
            profile_id=f"stat_{monster_id}",
            max_hp=max_hp,
            attack=attack,
        )
        for monster_id, (max_hp, attack) in _CURRENT_BATTLEFIELD_STATS.items()
    }
    return profiles


def _build_drop_profiles(
    identities: tuple[CanonicalMonsterIdentity, ...],
) -> dict[str, MonsterDropProfile]:
    profiles: dict[str, MonsterDropProfile] = {}
    for identity in identities:
        legacy_type = identity.legacy_type
        if not legacy_type:
            raise ValueError(f"{identity.monster_id} has no legacy drop reference")
        profile_id = f"drop_legacy_{legacy_type}"
        profiles.setdefault(
            profile_id,
            MonsterDropProfile(
                profile_id=profile_id,
                legacy_monster_type=legacy_type,
            ),
        )
    return profiles


def _build_reward_profiles() -> dict[str, MonsterRewardProfile]:
    profile = MonsterRewardProfile(profile_id="reward_battlefield_legacy")
    return {profile.profile_id: profile}


def _build_presentation_profiles(
    identities: tuple[CanonicalMonsterIdentity, ...],
) -> dict[str, MonsterPresentationProfile]:
    profiles: dict[str, MonsterPresentationProfile] = {}
    for identity in identities:
        profile_id = f"presentation_{identity.monster_id}"
        profiles[profile_id] = MonsterPresentationProfile(
            profile_id=profile_id,
            display_key=identity.display_name_key,
        )
    return profiles


def _registry_from_profiles(
    profiles: tuple[CanonicalMonsterProfile, ...],
    *,
    stat_profiles: Mapping[str, MonsterStatProfile],
    drop_profiles: Mapping[str, MonsterDropProfile],
    reward_profiles: Mapping[str, MonsterRewardProfile],
    presentation_profiles: Mapping[str, MonsterPresentationProfile],
) -> MonsterProfileRegistry:
    by_id = {profile.monster_id: profile for profile in profiles}
    by_roster_slot = {profile.roster_slot: profile for profile in profiles}
    if len(by_id) != len(profiles):
        raise ValueError("canonical Monster profile IDs must be unique")
    if len(by_roster_slot) != len(profiles):
        raise ValueError("canonical Monster profile roster slots must be unique")
    for profile in profiles:
        if profile.stat_profile_id not in stat_profiles:
            raise ValueError(f"missing stat profile for {profile.monster_id}")
        if profile.drop_profile_id not in drop_profiles:
            raise ValueError(f"missing drop profile for {profile.monster_id}")
        if profile.reward_profile_id not in reward_profiles:
            raise ValueError(f"missing reward profile for {profile.monster_id}")
        if profile.presentation_profile_id not in presentation_profiles:
            raise ValueError(f"missing presentation profile for {profile.monster_id}")
    return MonsterProfileRegistry(
        profiles=profiles,
        by_id=by_id,
        by_roster_slot=by_roster_slot,
        stat_profiles=stat_profiles,
        drop_profiles=drop_profiles,
        reward_profiles=reward_profiles,
        presentation_profiles=presentation_profiles,
    )


def build_canonical_monster_profile_registry(
    identity_registry: MonsterIdentityRegistry = CANONICAL_MONSTER_IDENTITY_REGISTRY,
) -> MonsterProfileRegistry:
    """Build and validate the F004 profile registry behind F003 identities."""

    identities = tuple(identity_registry.entries)
    if len(identities) != CANONICAL_BATTLEFIELD_MONSTER_COUNT:
        raise ValueError("F004 requires all 20 F003 battlefield identities")
    stat_profiles = _build_stat_profiles()
    if set(stat_profiles) != {f"stat_{identity.monster_id}" for identity in identities}:
        raise ValueError("stat profile coverage does not match F003 identity coverage")
    drop_profiles = _build_drop_profiles(identities)
    reward_profiles = _build_reward_profiles()
    presentation_profiles = _build_presentation_profiles(identities)

    profiles = tuple(
        CanonicalMonsterProfile(
            monster_id=identity.monster_id,
            roster_slot=identity.roster_slot,
            zone_key=identity.zone_id,
            encounter_class=identity.encounter_class,
            taxonomy_family=identity.family_id,
            display_key=identity.display_name_key,
            stat_profile_id=f"stat_{identity.monster_id}",
            drop_profile_id=f"drop_legacy_{identity.legacy_type}",
            reward_profile_id="reward_battlefield_legacy",
            presentation_profile_id=f"presentation_{identity.monster_id}",
            enabled=True,
            legacy_aliases=identity.legacy_aliases,
            boss_role=(
                "BATTLEFIELD_BOSS"
                if identity.encounter_class == "BATTLEFIELD_BOSS"
                else None
            ),
        )
        for identity in identities
    )
    return _registry_from_profiles(
        profiles,
        stat_profiles=stat_profiles,
        drop_profiles=drop_profiles,
        reward_profiles=reward_profiles,
        presentation_profiles=presentation_profiles,
    )


CANONICAL_MONSTER_PROFILE_REGISTRY = build_canonical_monster_profile_registry()
CANONICAL_PROFILE_COUNT = len(CANONICAL_MONSTER_PROFILE_REGISTRY.profiles)


def get_monster_profile(
    monster_id: Any,
    *,
    registry: MonsterProfileRegistry = CANONICAL_MONSTER_PROFILE_REGISTRY,
) -> CanonicalMonsterProfile | None:
    """Return an exact profile or ``None``; never inherit a fallback profile."""

    if monster_id in (None, ""):
        return None
    return registry.by_id.get(str(monster_id))


def get_stat_profile(
    stat_profile_id: Any,
    *,
    registry: MonsterProfileRegistry = CANONICAL_MONSTER_PROFILE_REGISTRY,
) -> MonsterStatProfile | None:
    if stat_profile_id in (None, ""):
        return None
    return registry.stat_profiles.get(str(stat_profile_id))


__all__ = [
    "CANONICAL_MONSTER_PROFILE_REGISTRY",
    "CANONICAL_PROFILE_COUNT",
    "CanonicalMonsterProfile",
    "MonsterDropProfile",
    "MonsterPresentationProfile",
    "MonsterProfileRegistry",
    "MonsterRewardProfile",
    "MonsterStatProfile",
    "build_canonical_monster_profile_registry",
    "get_monster_profile",
    "get_stat_profile",
]
