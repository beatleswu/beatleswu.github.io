"""Canonical adapter boundary for Quest V2 reward settlement.

Quest definitions select a server-owned ``reward_profile_id``.  This module
resolves that profile and delegates each mutation to an already-authoritative
server callback supplied by the future runtime cutover.  It intentionally
does not import or modify ``app.py`` and it never writes a reward itself.

The current Daily profile values are derived from D012's executable
compatibility records, which were reconciled with ``app.py:DAILY_QUEST_DEFS``
and ``_update_daily_quests``.  The callbacks must be bound to those existing
authorities when D017 wires the service: ``_grant_coins`` for Coins, the
existing Quest/Daily XP settlement path for XP, and ``_grant_pet_food`` (or
the canonical inventory adapter) for the current food rewards.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Protocol

from quest_catalog import CURRENT_DAILY_COMPATIBILITY


class QuestRewardSettlementError(RuntimeError):
    """A reward adapter could not prove the requested committed mutation."""


@dataclass(frozen=True)
class RewardItem:
    item_id: str
    quantity: int


@dataclass(frozen=True)
class QuestRewardProfile:
    profile_id: str
    xp: int = 0
    coins: int = 0
    items: tuple[RewardItem, ...] = ()
    cosmetics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise ValueError("reward profile ID is required")
        if isinstance(self.xp, bool) or not isinstance(self.xp, int) or self.xp < 0:
            raise ValueError("reward profile XP must be a non-negative integer")
        if isinstance(self.coins, bool) or not isinstance(self.coins, int) or self.coins < 0:
            raise ValueError("reward profile Coins must be a non-negative integer")
        for item in self.items:
            if not isinstance(item, RewardItem) or not item.item_id or item.quantity <= 0:
                raise ValueError("reward profile item is invalid")
        for cosmetic in self.cosmetics:
            if not isinstance(cosmetic, str) or not cosmetic.strip():
                raise ValueError("reward profile cosmetic ID is invalid")


class QuestRewardCatalog:
    """One immutable reward-profile authority for a claim service."""

    def __init__(self, profiles: Iterable[QuestRewardProfile]):
        values = tuple(profiles)
        profile_map = {profile.profile_id: profile for profile in values}
        if len(profile_map) != len(values):
            raise ValueError("duplicate reward profile ID")
        self._profiles = MappingProxyType(profile_map)

    @property
    def profiles(self) -> Mapping[str, QuestRewardProfile]:
        return self._profiles

    def resolve(self, reward_profile_id: str | None) -> QuestRewardProfile:
        if not isinstance(reward_profile_id, str) or not reward_profile_id.strip():
            raise QuestRewardSettlementError("reward_profile_missing")
        profile = self._profiles.get(reward_profile_id)
        if profile is None:
            raise QuestRewardSettlementError("reward_profile_unknown")
        return profile


def _profile_from_compatibility(record: Mapping[str, Any]) -> QuestRewardProfile:
    profile_id = f"legacy:daily:{record['legacy_machine_key']}"
    reward = record["current_reward_behavior"]
    item_id = reward.get("item_id")
    item_quantity = int(reward.get("item_quantity") or 0)
    items = (RewardItem(str(item_id), item_quantity),) if item_id and item_quantity else ()
    return QuestRewardProfile(
        profile_id=profile_id,
        xp=int(reward.get("xp") or 0),
        coins=int(reward.get("coins") or 0),
        items=items,
    )


CURRENT_DAILY_REWARD_PROFILES = tuple(
    _profile_from_compatibility(record) for record in CURRENT_DAILY_COMPATIBILITY
)
CURRENT_QUEST_REWARD_CATALOG = QuestRewardCatalog(CURRENT_DAILY_REWARD_PROFILES)

# This is an executable adapter contract, not a second mutation authority.
# The values name the existing authorities that D017 must bind at cutover.
CURRENT_REWARD_AUTHORITY_CONTRACT = MappingProxyType(
    {
        "coins": "app.py:_grant_coins",
        "quest_xp": "app.py:_update_daily_quests user_stats XP settlement",
        "items": "app.py:_grant_pet_food / canonical inventory adapter",
        "cosmetics": "app.py:player_wardrobe ownership authority",
        "quest_xp_bonus": "app.py:_safe_active_equipment_effect(..., 'quest_xp_bonus')",
    }
)


class QuestRewardAuthorities(Protocol):
    """Server callbacks for already-authoritative reward mutations."""

    def grant_xp(
        self,
        conn: Any,
        user_id: int | str,
        amount: int,
        reason: str,
        reward_profile_id: str,
    ) -> int:
        ...

    def grant_coins(
        self,
        conn: Any,
        user_id: int | str,
        amount: int,
        reason: str,
        reward_profile_id: str,
    ) -> int:
        ...

    def grant_item(
        self,
        conn: Any,
        user_id: int | str,
        item_id: str,
        quantity: int,
        reason: str,
        reward_profile_id: str,
    ) -> Mapping[str, Any]:
        ...

    def grant_cosmetic(
        self,
        conn: Any,
        user_id: int | str,
        cosmetic_id: str,
        reason: str,
        reward_profile_id: str,
    ) -> Mapping[str, Any]:
        ...


GrantXP = Callable[[Any, int | str, int, str, str], int]
GrantCoins = Callable[[Any, int | str, int, str, str], int]
GrantItem = Callable[[Any, int | str, str, int, str, str], Mapping[str, Any]]
GrantCosmetic = Callable[[Any, int | str, str, str, str], Mapping[str, Any]]


class CallableQuestRewardAuthorities:
    """Bind the claim service to existing server mutation functions.

    The callbacks execute inside the caller-owned transaction.  No callback
    is allowed to commit or rollback that transaction.  Item callbacks must
    return ``ownership_authority`` and ``ownership_reference`` so D5A can
    record truthful acquisition evidence.
    """

    def __init__(
        self,
        *,
        grant_xp: GrantXP,
        grant_coins: GrantCoins,
        grant_item: GrantItem,
        grant_cosmetic: GrantCosmetic | None = None,
    ) -> None:
        self._grant_xp = grant_xp
        self._grant_coins = grant_coins
        self._grant_item = grant_item
        self._grant_cosmetic = grant_cosmetic

    def grant_xp(self, conn: Any, user_id: int | str, amount: int, reason: str, reward_profile_id: str) -> int:
        return self._validated_amount(
            self._grant_xp(conn, user_id, amount, reason, reward_profile_id),
            field="xp",
        )

    def grant_coins(self, conn: Any, user_id: int | str, amount: int, reason: str, reward_profile_id: str) -> int:
        return self._validated_amount(
            self._grant_coins(conn, user_id, amount, reason, reward_profile_id),
            field="coins",
        )

    def grant_item(
        self,
        conn: Any,
        user_id: int | str,
        item_id: str,
        quantity: int,
        reason: str,
        reward_profile_id: str,
    ) -> Mapping[str, Any]:
        result = self._grant_item(conn, user_id, item_id, quantity, reason, reward_profile_id)
        if not isinstance(result, Mapping):
            raise QuestRewardSettlementError("item_adapter_result_missing")
        normalized = dict(result)
        if not normalized.get("ownership_authority") or not normalized.get("ownership_reference"):
            raise QuestRewardSettlementError("item_adapter_ownership_reference_missing")
        granted = normalized.get("granted_quantity", quantity)
        if isinstance(granted, bool) or not isinstance(granted, int) or granted != quantity:
            raise QuestRewardSettlementError("item_adapter_quantity_mismatch")
        return normalized

    def grant_cosmetic(
        self,
        conn: Any,
        user_id: int | str,
        cosmetic_id: str,
        reason: str,
        reward_profile_id: str,
    ) -> Mapping[str, Any]:
        if self._grant_cosmetic is None:
            raise QuestRewardSettlementError("cosmetic_adapter_unavailable")
        result = self._grant_cosmetic(conn, user_id, cosmetic_id, reason, reward_profile_id)
        if not isinstance(result, Mapping):
            raise QuestRewardSettlementError("cosmetic_adapter_result_missing")
        normalized = dict(result)
        if not normalized.get("ownership_authority") or not normalized.get("ownership_reference"):
            raise QuestRewardSettlementError("cosmetic_adapter_ownership_reference_missing")
        return normalized

    @staticmethod
    def _validated_amount(value: Any, *, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise QuestRewardSettlementError(f"{field}_adapter_result_invalid")
        return value


class UnavailableQuestRewardAuthorities:
    """Fail closed until a runtime owner supplies canonical callbacks."""

    def _unavailable(self, *_args: Any, **_kwargs: Any) -> Any:
        raise QuestRewardSettlementError("canonical_reward_authority_not_bound")

    grant_xp = _unavailable
    grant_coins = _unavailable
    grant_item = _unavailable
    grant_cosmetic = _unavailable


DEFAULT_QUEST_REWARD_AUTHORITIES = UnavailableQuestRewardAuthorities()


def current_daily_reward_matrix() -> tuple[Mapping[str, Any], ...]:
    """Return immutable-compatible current Daily reward evidence."""

    return tuple(dict(record) for record in CURRENT_DAILY_COMPATIBILITY)


__all__ = [
    "CURRENT_DAILY_REWARD_PROFILES",
    "CURRENT_QUEST_REWARD_CATALOG",
    "CURRENT_REWARD_AUTHORITY_CONTRACT",
    "CallableQuestRewardAuthorities",
    "DEFAULT_QUEST_REWARD_AUTHORITIES",
    "QuestRewardAuthorities",
    "QuestRewardCatalog",
    "QuestRewardProfile",
    "QuestRewardSettlementError",
    "RewardItem",
    "UnavailableQuestRewardAuthorities",
    "current_daily_reward_matrix",
]
