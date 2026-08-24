"""Server-authoritative Coin Shop offer contract for C019.

The existing Shop catalog contains legacy bundles, daily rotation discounts,
Pet-specific grants, and non-Coin products.  C019 therefore consumes an
explicit normalized offer authority instead of importing ``app.py`` or
silently inferring a purchase contract from presentation data.

This module owns no user state, balance, inventory, or HTTP behavior.  It is
safe to construct from a future server-side catalog adapter or from disposable
test fixtures.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import json
from typing import Any, Protocol


CANONICAL_ITEM_CLASSES = frozenset(
    {
        "WEAPON",
        "ARMOR",
        "ACCESSORY",
        "CONSUMABLE",
        "SPIRIT_CONSUMABLE",
        "XP_CONSUMABLE",
        "MATERIAL",
        "COSMETIC",
        "TROPHY",
    }
)
CANONICAL_DESTINATIONS = frozenset(
    {
        "player_inventory",
        "shop_inventory",
        "player_wardrobe",
        "entitlement",
        "capacity",
        "credit",
    }
)
OFFER_STATUSES = frozenset({"ACTIVE", "DISABLED", "HIDDEN"})
DUPLICATE_POLICIES = frozenset(
    {"STACK", "REJECT_IF_OWNED", "ALLOW_DUPLICATE", "UNSPECIFIED"}
)


class ShopOfferError(ValueError):
    """Base class for fail-closed offer contract errors."""


class ShopOfferNotFound(ShopOfferError):
    """The server has no active offer for the requested identifier."""


class ShopOfferNotEligible(ShopOfferError):
    """The resolved offer is not available to the current player."""


class ShopOfferContractError(ShopOfferError):
    """An offer violates the C019 server-side contract."""


@dataclass(frozen=True)
class CoinShopOffer:
    """One normalized, server-owned Coin acquisition opportunity."""

    offer_id: str
    item_id: str
    quantity: int
    currency_type: str
    price: int
    destination: str
    acquisition_class: str
    offer_type: str = "ITEM"
    offer_version: str = "v1"
    status: str = "ACTIVE"
    duplicate_policy: str = "UNSPECIFIED"
    eligibility_metadata: Mapping[str, Any] = field(default_factory=dict)
    presentation_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        text_fields = {
            "offer_id": self.offer_id,
            "item_id": self.item_id,
            "currency_type": self.currency_type,
            "destination": self.destination,
            "acquisition_class": self.acquisition_class,
            "offer_type": self.offer_type,
            "offer_version": self.offer_version,
            "status": self.status,
            "duplicate_policy": self.duplicate_policy,
        }
        for field_name, value in text_fields.items():
            if not isinstance(value, str) or not value.strip():
                raise ShopOfferContractError(f"{field_name} must be non-empty text")

        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int) or self.quantity <= 0:
            raise ShopOfferContractError("quantity must be a positive integer")
        if isinstance(self.price, bool) or not isinstance(self.price, int) or self.price <= 0:
            raise ShopOfferContractError("price must be a positive integer")

        normalized_currency = self.currency_type.strip().upper()
        if normalized_currency != "COINS":
            raise ShopOfferContractError("C019 only supports COINS offers")
        if self.acquisition_class.strip().upper() not in CANONICAL_ITEM_CLASSES:
            raise ShopOfferContractError(
                f"unsupported acquisition class: {self.acquisition_class!r}"
            )
        if self.destination.strip() not in CANONICAL_DESTINATIONS:
            raise ShopOfferContractError(
                f"unsupported acquisition destination: {self.destination!r}"
            )
        if self.status.strip().upper() not in OFFER_STATUSES:
            raise ShopOfferContractError(f"unsupported offer status: {self.status!r}")
        if self.duplicate_policy.strip().upper() not in DUPLICATE_POLICIES:
            raise ShopOfferContractError(
                f"unsupported duplicate policy: {self.duplicate_policy!r}"
            )
        if not isinstance(self.eligibility_metadata, Mapping):
            raise ShopOfferContractError("eligibility_metadata must be a mapping")
        if not isinstance(self.presentation_metadata, Mapping):
            raise ShopOfferContractError("presentation_metadata must be a mapping")
        try:
            json.dumps(
                {
                    "eligibility": dict(self.eligibility_metadata),
                    "presentation": dict(self.presentation_metadata),
                },
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ShopOfferContractError("offer metadata must be JSON serializable") from exc

        object.__setattr__(self, "offer_id", self.offer_id.strip())
        object.__setattr__(self, "item_id", self.item_id.strip())
        object.__setattr__(self, "currency_type", normalized_currency)
        object.__setattr__(self, "destination", self.destination.strip())
        object.__setattr__(self, "acquisition_class", self.acquisition_class.strip().upper())
        object.__setattr__(self, "offer_type", self.offer_type.strip().upper())
        object.__setattr__(self, "offer_version", self.offer_version.strip())
        object.__setattr__(self, "status", self.status.strip().upper())
        object.__setattr__(self, "duplicate_policy", self.duplicate_policy.strip().upper())
        object.__setattr__(self, "eligibility_metadata", dict(self.eligibility_metadata))
        object.__setattr__(self, "presentation_metadata", dict(self.presentation_metadata))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CoinShopOffer":
        """Normalize one already server-owned mapping without client input."""

        if not isinstance(value, Mapping):
            raise ShopOfferContractError("offer must be a mapping")
        item_id = value.get("item_id", value.get("reward_id"))
        currency = value.get("currency_type", value.get("currency", "COINS"))
        eligibility = value.get("eligibility_metadata", value.get("eligibility", {}))
        presentation = value.get("presentation_metadata", value.get("presentation", {}))
        return cls(
            offer_id=value.get("offer_id"),
            item_id=item_id,
            quantity=value.get("quantity", 1),
            currency_type=currency,
            price=value.get("price"),
            destination=value.get("destination"),
            acquisition_class=value.get("acquisition_class", value.get("class")),
            offer_type=value.get("offer_type", "ITEM"),
            offer_version=value.get("offer_version", value.get("version", "v1")),
            status=value.get("status", "ACTIVE"),
            duplicate_policy=value.get("duplicate_policy", "UNSPECIFIED"),
            eligibility_metadata=eligibility or {},
            presentation_metadata=presentation or {},
        )

    def canonical_identity(self) -> dict[str, Any]:
        """Return only mutation-relevant server-resolved offer semantics."""

        return {
            "offer_id": self.offer_id,
            "item_id": self.item_id,
            "quantity": self.quantity,
            "currency_type": self.currency_type,
            "price": self.price,
            "destination": self.destination,
            "acquisition_class": self.acquisition_class,
            "offer_type": self.offer_type,
            "offer_version": self.offer_version,
            "duplicate_policy": self.duplicate_policy,
            "eligibility_metadata": dict(self.eligibility_metadata),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.canonical_identity(),
            "status": self.status,
            "presentation_metadata": dict(self.presentation_metadata),
        }


class ShopOfferAuthority(Protocol):
    """Minimal server-side offer resolver consumed by C019."""

    def resolve(self, offer_id: str) -> CoinShopOffer:
        ...

    def check_eligibility(
        self,
        conn: Any,
        *,
        user_id: int,
        offer: CoinShopOffer,
    ) -> None:
        ...


EligibilityChecker = Callable[[Any, int, CoinShopOffer], bool | None]


class StaticShopOfferAuthority:
    """Small explicit server catalog adapter for C019 and isolated tests."""

    def __init__(
        self,
        offers: Mapping[str, CoinShopOffer | Mapping[str, Any]] | list[CoinShopOffer | Mapping[str, Any]],
        *,
        eligibility_checker: EligibilityChecker | None = None,
    ) -> None:
        if isinstance(offers, Mapping):
            values = offers.values()
        else:
            values = offers
        normalized: dict[str, CoinShopOffer] = {}
        for raw_offer in values:
            offer = raw_offer if isinstance(raw_offer, CoinShopOffer) else CoinShopOffer.from_mapping(raw_offer)
            if offer.offer_id in normalized:
                raise ShopOfferContractError(f"duplicate offer_id: {offer.offer_id!r}")
            normalized[offer.offer_id] = offer
        self._offers = normalized
        self._eligibility_checker = eligibility_checker

    @classmethod
    def from_mappings(
        cls,
        offers: list[Mapping[str, Any]],
        *,
        eligibility_checker: EligibilityChecker | None = None,
    ) -> "StaticShopOfferAuthority":
        return cls(offers, eligibility_checker=eligibility_checker)

    def resolve(self, offer_id: str) -> CoinShopOffer:
        if not isinstance(offer_id, str) or not offer_id.strip():
            raise ShopOfferNotFound("offer_id is required")
        offer = self._offers.get(offer_id.strip())
        if offer is None or offer.status != "ACTIVE":
            raise ShopOfferNotFound(f"active offer not found: {offer_id!r}")
        return offer

    def check_eligibility(
        self,
        conn: Any,
        *,
        user_id: int,
        offer: CoinShopOffer,
    ) -> None:
        metadata = offer.eligibility_metadata
        if metadata.get("eligible") is False or metadata.get("enabled") is False:
            raise ShopOfferNotEligible(f"offer is not eligible: {offer.offer_id!r}")
        if self._eligibility_checker is not None:
            allowed = self._eligibility_checker(conn, user_id, offer)
            if allowed is False:
                raise ShopOfferNotEligible(f"offer is not eligible: {offer.offer_id!r}")

    def get(self, offer_id: str) -> CoinShopOffer | None:
        return self._offers.get(offer_id)

    def all_offers(self) -> tuple[CoinShopOffer, ...]:
        return tuple(self._offers.values())


__all__ = [
    "CANONICAL_DESTINATIONS",
    "CANONICAL_ITEM_CLASSES",
    "CoinShopOffer",
    "DUPLICATE_POLICIES",
    "EligibilityChecker",
    "OFFER_STATUSES",
    "ShopOfferAuthority",
    "ShopOfferContractError",
    "ShopOfferError",
    "ShopOfferNotEligible",
    "ShopOfferNotFound",
    "StaticShopOfferAuthority",
]
