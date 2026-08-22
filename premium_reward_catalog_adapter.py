"""Server-owned boundary for a future Premium reward catalog.

No production reward rows are defined here.  The default resolver fails
closed; isolated tests may inject a deterministic resolver without changing
the commercial catalog or enabling a route.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol


CATALOG_INTERFACE_VERSION = "premium_reward_catalog_resolver_v1"


class PremiumRewardCatalogResolver(Protocol):
    def resolve_period_reward(
        self,
        *,
        period_key: str,
        reward_catalog_key: str,
        requested_reward_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        """Return one server-approved reward or ``None``."""


class UnconfiguredPremiumRewardCatalog:
    """Fail-closed until an Owner-approved catalog is wired in."""

    def resolve_period_reward(
        self,
        *,
        period_key: str,
        reward_catalog_key: str,
        requested_reward_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        del period_key, reward_catalog_key, requested_reward_id
        return None


__all__ = [
    "CATALOG_INTERFACE_VERSION",
    "PremiumRewardCatalogResolver",
    "UnconfiguredPremiumRewardCatalog",
]
