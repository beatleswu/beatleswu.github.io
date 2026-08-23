"""Canonical references for existing Monster reward behavior.

The current battlefield reward path is intentionally represented as one
fragmented legacy profile.  F005 records its exact values and authorities but
does not move settlement, XP, Coins, inventory, Quest, or D5 writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from monster_profiles import (
    CANONICAL_MONSTER_PROFILE_REGISTRY,
    MonsterProfileRegistry,
    get_monster_profile,
)


@dataclass(frozen=True)
class MonsterRewardProfile:
    reward_profile_id: str
    enabled: bool
    xp: int | None
    coins: int | None
    coin_daily_cap: int | None
    item_components: tuple[str, ...]
    source_authority: tuple[str, ...]
    legacy_aliases: tuple[str, ...]
    status: str
    xp_authority: str


@dataclass(frozen=True)
class MonsterRewardMatrixRow:
    monster_id: str
    reward_profile_id: str
    reward_profile_resolves: bool
    runtime_currently_reachable: bool
    xp_is_monster_specific: bool
    coins_per_kill: int | None
    item_components: tuple[str, ...]


_LEGACY_REWARD_PROFILE = MonsterRewardProfile(
    reward_profile_id="reward_battlefield_legacy",
    enabled=True,
    # Current review XP is calculated by calc_xp_gain and is not a Monster
    # reward component.  None is explicit, not an invented zero reward.
    xp=None,
    coins=2,
    coin_daily_cap=40,
    item_components=("functional_equipment_drop", "cosmetic_appearance_drop"),
    source_authority=(
        "app._update_monster_and_quests",
        "app._grant_coins(monster_kill)",
        "app._roll_loot",
        "app._roll_appearance_loot",
    ),
    legacy_aliases=("monster_kill", "battlefield_reward"),
    status="FRAGMENTED_LEGACY_COMPATIBILITY",
    xp_authority="review_settlement.calc_xp_gain; not Monster-specific",
)


def build_canonical_reward_profile_registry(
    monster_registry: MonsterProfileRegistry = CANONICAL_MONSTER_PROFILE_REGISTRY,
) -> dict[str, MonsterRewardProfile]:
    profiles = {_LEGACY_REWARD_PROFILE.reward_profile_id: _LEGACY_REWARD_PROFILE}
    for monster_profile in monster_registry.profiles:
        if monster_profile.reward_profile_id not in profiles:
            raise ValueError(
                f"missing canonical reward profile for {monster_profile.monster_id}"
            )
    return profiles


CANONICAL_REWARD_PROFILE_REGISTRY = build_canonical_reward_profile_registry()
REWARD_PROFILE_REGISTRY_COUNT = len(CANONICAL_REWARD_PROFILE_REGISTRY)


def get_reward_profile(
    reward_profile_id: Any,
    *,
    registry: Mapping[str, MonsterRewardProfile] = CANONICAL_REWARD_PROFILE_REGISTRY,
) -> MonsterRewardProfile | None:
    """Return an exact reward profile; unknown IDs fail closed."""

    if reward_profile_id in (None, ""):
        return None
    return registry.get(str(reward_profile_id))


def get_reward_profile_for_monster(
    monster_id: Any,
    *,
    monster_registry: MonsterProfileRegistry = CANONICAL_MONSTER_PROFILE_REGISTRY,
    reward_registry: Mapping[str, MonsterRewardProfile] = CANONICAL_REWARD_PROFILE_REGISTRY,
) -> MonsterRewardProfile | None:
    profile = get_monster_profile(monster_id, registry=monster_registry)
    if profile is None:
        return None
    return get_reward_profile(profile.reward_profile_id, registry=reward_registry)


def build_monster_reward_matrix(
    monster_registry: MonsterProfileRegistry = CANONICAL_MONSTER_PROFILE_REGISTRY,
    reward_registry: Mapping[str, MonsterRewardProfile] = CANONICAL_REWARD_PROFILE_REGISTRY,
) -> tuple[MonsterRewardMatrixRow, ...]:
    rows: list[MonsterRewardMatrixRow] = []
    for monster_profile in monster_registry.profiles:
        reward_profile = get_reward_profile(
            monster_profile.reward_profile_id,
            registry=reward_registry,
        )
        rows.append(
            MonsterRewardMatrixRow(
                monster_id=monster_profile.monster_id,
                reward_profile_id=monster_profile.reward_profile_id,
                reward_profile_resolves=reward_profile is not None,
                runtime_currently_reachable=bool(reward_profile and reward_profile.enabled),
                xp_is_monster_specific=bool(reward_profile and reward_profile.xp is not None),
                coins_per_kill=reward_profile.coins if reward_profile else None,
                item_components=(
                    reward_profile.item_components if reward_profile else ()
                ),
            )
        )
    return tuple(rows)


CANONICAL_MONSTER_REWARD_MATRIX = build_monster_reward_matrix()


__all__ = [
    "CANONICAL_MONSTER_REWARD_MATRIX",
    "CANONICAL_REWARD_PROFILE_REGISTRY",
    "REWARD_PROFILE_REGISTRY_COUNT",
    "MonsterRewardMatrixRow",
    "MonsterRewardProfile",
    "build_canonical_reward_profile_registry",
    "build_monster_reward_matrix",
    "get_reward_profile",
    "get_reward_profile_for_monster",
]
