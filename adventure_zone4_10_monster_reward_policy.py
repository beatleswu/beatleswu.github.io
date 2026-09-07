"""Owner-approved Monster economy policy for Adventure Zones 4-10.

This module is an L4 policy authority only.  It deliberately consumes the
canonical Zone 4-10 identity authority instead of copying its 79 records, and
it does not perform runtime admission, settlement, persistence, Quest writes,
drop selection, or Shop wiring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from adventure_zone4_10_monster_identity_authority import (
    ZONE4_10_MONSTER_IDENTITIES,
    get_zone4_10_monster_identity,
)


# These are policy facts consumed by a future, separately authorized runtime
# binding.  The existing app.py Coin writer and cap/logging authority remain
# unchanged; this module does not write Coin or create a second writer.
NORMAL_MONSTER_COIN_REWARD: Final = 2
MONSTER_COIN_DAILY_CAP: Final = 40
GLOBAL_COIN_DAILY_CAP: Final = 500
COIN_AUTHORITY_SOURCES: Final = (
    "app._COIN_PER_MONSTER",
    "app._COIN_MONSTER_DAILY_CAP",
    "app._COIN_DAILY_CAP",
)

# ``None`` is intentional.  Review/question XP is not Monster-specific and
# must not be copied into this policy registry.
MONSTER_SPECIFIC_XP: Final = None

ZONE4_10_DROP_ELIGIBILITY: Final = False
ZONE4_10_DROP_TABLES: Final = None
ZONE4_10_DROP_PROFILE: Final = None

NORMAL_FIRST_DEFEAT_REWARD_POLICY: Final = "SAME_AS_NORMAL_REPEAT_DEFEAT"
QUEST_MID_BINDING: Final = None
ADDITIONAL_FIRST_CLEAR_REWARD_BEYOND_F028: Final = None

SHOP_EXPANSION: Final = "NONE"
PAYMENT_ENABLEMENT: Final = False
PREMIUM_ENABLEMENT: Final = False
GACHA_ENABLEMENT: Final = False


@dataclass(frozen=True)
class Zone4_10MonsterRewardPolicy:
    """Deterministic policy facts for one canonical Zone 4-10 M-ID."""

    monster_id: str
    zone_key: str
    coin_reward: int
    monster_specific_xp: int | None
    drop_eligible: bool
    drop_profile: str | None
    additional_first_defeat_reward: str | None
    quest_binding: str | None
    additional_first_clear_reward: str | None
    first_defeat_reward_policy: str


def _policy_for_identity(monster_id: str, zone_key: str) -> Zone4_10MonsterRewardPolicy:
    return Zone4_10MonsterRewardPolicy(
        monster_id=monster_id,
        zone_key=zone_key,
        coin_reward=NORMAL_MONSTER_COIN_REWARD,
        monster_specific_xp=MONSTER_SPECIFIC_XP,
        drop_eligible=ZONE4_10_DROP_ELIGIBILITY,
        drop_profile=ZONE4_10_DROP_PROFILE,
        additional_first_defeat_reward=None,
        quest_binding=QUEST_MID_BINDING,
        additional_first_clear_reward=ADDITIONAL_FIRST_CLEAR_REWARD_BEYOND_F028,
        first_defeat_reward_policy=NORMAL_FIRST_DEFEAT_REWARD_POLICY,
    )


def get_zone4_10_monster_reward_policy(
    monster_id: object,
    *,
    claimed_zone_key: object | None = None,
) -> Zone4_10MonsterRewardPolicy | None:
    """Return policy for a canonical M-ID, or fail closed.

    ``claimed_zone_key`` is an optional boundary check only.  It can never
    override the canonical identity's zone.  A wrong-zone claim is rejected
    rather than being normalized into a different policy record.
    """

    identity = get_zone4_10_monster_identity(str(monster_id).strip())
    if identity is None:
        return None
    if claimed_zone_key is not None and str(claimed_zone_key).strip() != identity.zone_key:
        return None
    return _policy_for_identity(identity.monster_id, identity.zone_key)


def iter_zone4_10_monster_reward_policies() -> tuple[Zone4_10MonsterRewardPolicy, ...]:
    """Materialize policy rows from the identity authority for audit/tests."""

    return tuple(
        _policy_for_identity(identity.monster_id, identity.zone_key)
        for identity in ZONE4_10_MONSTER_IDENTITIES
    )


__all__ = [
    "ADDITIONAL_FIRST_CLEAR_REWARD_BEYOND_F028",
    "COIN_AUTHORITY_SOURCES",
    "GACHA_ENABLEMENT",
    "GLOBAL_COIN_DAILY_CAP",
    "MONSTER_COIN_DAILY_CAP",
    "MONSTER_SPECIFIC_XP",
    "NORMAL_FIRST_DEFEAT_REWARD_POLICY",
    "NORMAL_MONSTER_COIN_REWARD",
    "PAYMENT_ENABLEMENT",
    "PREMIUM_ENABLEMENT",
    "QUEST_MID_BINDING",
    "SHOP_EXPANSION",
    "ZONE4_10_DROP_ELIGIBILITY",
    "ZONE4_10_DROP_PROFILE",
    "ZONE4_10_DROP_TABLES",
    "Zone4_10MonsterRewardPolicy",
    "get_zone4_10_monster_reward_policy",
    "iter_zone4_10_monster_reward_policies",
]
