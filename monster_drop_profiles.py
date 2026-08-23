"""Canonical references for the existing Monster item-drop behavior.

F005 records the current functional-equipment drop channel without changing
the legacy execution path.  The runtime still owns the behavior through
``_roll_loot``, ``BASE_LOOT_CHANCE``, and ``EQUIPMENT_DEFS.drop_from``.  Empty
profiles are intentional: they represent active battlefield types for which
the current equipment pool is defined but unreachable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from monster_profiles import (
    CANONICAL_MONSTER_PROFILE_REGISTRY,
    MonsterProfileRegistry,
    get_monster_profile,
)


DROP_STATUS_REACHABLE = "REACHABLE"
DROP_STATUS_DEFINED_BUT_UNREACHABLE = "DEFINED_BUT_UNREACHABLE"
DROP_STATUS_LEGACY_ONLY = "LEGACY_ONLY"


@dataclass(frozen=True)
class DropEntry:
    """One existing functional item entry from EQUIPMENT_DEFS.drop_from."""

    item_id: str
    relative_weight: int
    quantity: int = 1
    gate_condition: str = "monster_defeated"
    item_kind: str = "FUNCTIONAL_EQUIPMENT"


@dataclass(frozen=True)
class MonsterDropProfile:
    drop_profile_id: str
    enabled: bool
    entries: tuple[DropEntry, ...]
    source_authority: tuple[str, ...]
    legacy_aliases: tuple[str, ...]
    legacy_monster_type: str
    gate_chance: float
    status: str


@dataclass(frozen=True)
class MonsterDropMatrixRow:
    monster_id: str
    legacy_monster_type: str
    drop_profile_id: str
    drop_profile_resolves: bool
    runtime_currently_reachable: bool
    status: str
    entry_count: int


_SOURCE_AUTHORITY = (
    "app._roll_loot",
    "app.BASE_LOOT_CHANCE",
    "app.EQUIPMENT_DEFS.drop_from",
)

# Exact current BASE_LOOT_CHANCE values.  Types absent from the current map
# use the existing _roll_loot fallback of 0.20; that fallback is recorded, not
# changed or normalized.
_LEGACY_GATE_CHANCE: dict[str, float] = {
    "caterpillar": 0.08,
    "bee": 0.10,
    "turtle": 0.12,
    "rabbit": 0.14,
    "raccoon": 0.16,
    "goblin": 0.20,
    "fox": 0.30,
    "dragon": 0.45,
    "wolf": 0.20,
    "golem": 0.20,
}

# Exact current EQUIPMENT_DEFS.drop_from / drop_weight entries.  This is a
# registry snapshot, not a second execution path.  The test matrix compares
# it to app.py so values cannot silently drift at the F005 boundary.
_LEGACY_EQUIPMENT_ENTRIES: dict[str, tuple[DropEntry, ...]] = {
    "goblin": (
        DropEntry("wooden_sword", 30),
        DropEntry("iron_sword", 20),
        DropEntry("cloth_robe", 25),
        DropEntry("leather_armor", 18),
        DropEntry("lucky_stone", 20),
        DropEntry("xp_amulet", 12),
    ),
    "fox": (
        DropEntry("iron_sword", 20),
        DropEntry("fox_fang", 15),
        DropEntry("leather_armor", 18),
        DropEntry("fox_pelt", 12),
        DropEntry("xp_amulet", 12),
        DropEntry("fox_mask", 10),
    ),
    "dragon": (
        DropEntry("dragon_claw", 10),
        DropEntry("celestial_blade", 3),
        DropEntry("dragon_scale", 8),
        DropEntry("void_mantle", 2),
        DropEntry("dragon_eye", 6),
        DropEntry("go_stone_black", 1),
    ),
}


def _profile_id(legacy_monster_type: str) -> str:
    return f"drop_legacy_{legacy_monster_type}"


def _build_drop_profile(
    legacy_monster_type: str,
    *,
    status: str,
) -> MonsterDropProfile:
    return MonsterDropProfile(
        drop_profile_id=_profile_id(legacy_monster_type),
        enabled=True,
        entries=_LEGACY_EQUIPMENT_ENTRIES.get(legacy_monster_type, ()),
        source_authority=_SOURCE_AUTHORITY,
        legacy_aliases=(legacy_monster_type,),
        legacy_monster_type=legacy_monster_type,
        gate_chance=_LEGACY_GATE_CHANCE[legacy_monster_type],
        status=status,
    )


def build_canonical_drop_profile_registry(
    monster_registry: MonsterProfileRegistry = CANONICAL_MONSTER_PROFILE_REGISTRY,
) -> dict[str, MonsterDropProfile]:
    """Build F005 profiles for all F004 references plus legacy-only goblin."""

    legacy_types = {
        profile.drop_profile_id.removeprefix("drop_legacy_")
        for profile in monster_registry.profiles
    }
    profiles: dict[str, MonsterDropProfile] = {}
    for legacy_type in sorted(legacy_types | {"goblin"}):
        entries = _LEGACY_EQUIPMENT_ENTRIES.get(legacy_type, ())
        status = (
            DROP_STATUS_REACHABLE
            if entries
            else DROP_STATUS_DEFINED_BUT_UNREACHABLE
        )
        if legacy_type == "goblin":
            status = DROP_STATUS_LEGACY_ONLY
        profiles[_profile_id(legacy_type)] = _build_drop_profile(
            legacy_type,
            status=status,
        )
    for monster_profile in monster_registry.profiles:
        if monster_profile.drop_profile_id not in profiles:
            raise ValueError(
                f"missing canonical drop profile for {monster_profile.monster_id}"
            )
    return profiles


CANONICAL_DROP_PROFILE_REGISTRY = build_canonical_drop_profile_registry()
DROP_PROFILE_REGISTRY_COUNT = len(CANONICAL_DROP_PROFILE_REGISTRY)


def get_drop_profile(
    drop_profile_id: Any,
    *,
    registry: Mapping[str, MonsterDropProfile] = CANONICAL_DROP_PROFILE_REGISTRY,
) -> MonsterDropProfile | None:
    """Return an exact profile; unknown IDs never inherit another profile."""

    if drop_profile_id in (None, ""):
        return None
    return registry.get(str(drop_profile_id))


def get_drop_profile_for_monster(
    monster_id: Any,
    *,
    monster_registry: MonsterProfileRegistry = CANONICAL_MONSTER_PROFILE_REGISTRY,
    drop_registry: Mapping[str, MonsterDropProfile] = CANONICAL_DROP_PROFILE_REGISTRY,
) -> MonsterDropProfile | None:
    profile = get_monster_profile(monster_id, registry=monster_registry)
    if profile is None:
        return None
    return get_drop_profile(profile.drop_profile_id, registry=drop_registry)


def build_monster_drop_matrix(
    monster_registry: MonsterProfileRegistry = CANONICAL_MONSTER_PROFILE_REGISTRY,
    drop_registry: Mapping[str, MonsterDropProfile] = CANONICAL_DROP_PROFILE_REGISTRY,
) -> tuple[MonsterDropMatrixRow, ...]:
    rows: list[MonsterDropMatrixRow] = []
    for monster_profile in monster_registry.profiles:
        drop_profile = get_drop_profile(
            monster_profile.drop_profile_id,
            registry=drop_registry,
        )
        rows.append(
            MonsterDropMatrixRow(
                monster_id=monster_profile.monster_id,
                legacy_monster_type=(
                    drop_profile.legacy_monster_type if drop_profile else ""
                ),
                drop_profile_id=monster_profile.drop_profile_id,
                drop_profile_resolves=drop_profile is not None,
                runtime_currently_reachable=bool(
                    drop_profile and drop_profile.entries
                ),
                status=(
                    drop_profile.status
                    if drop_profile
                    else "UNKNOWN"
                ),
                entry_count=len(drop_profile.entries) if drop_profile else 0,
            )
        )
    return tuple(rows)


CANONICAL_MONSTER_DROP_MATRIX = build_monster_drop_matrix()


__all__ = [
    "CANONICAL_DROP_PROFILE_REGISTRY",
    "CANONICAL_MONSTER_DROP_MATRIX",
    "DROP_PROFILE_REGISTRY_COUNT",
    "DROP_STATUS_DEFINED_BUT_UNREACHABLE",
    "DROP_STATUS_LEGACY_ONLY",
    "DROP_STATUS_REACHABLE",
    "DropEntry",
    "MonsterDropMatrixRow",
    "MonsterDropProfile",
    "build_canonical_drop_profile_registry",
    "build_monster_drop_matrix",
    "get_drop_profile",
    "get_drop_profile_for_monster",
]
