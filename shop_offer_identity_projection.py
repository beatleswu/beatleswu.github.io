"""Pure projection of trusted Shop facts into stable C021 offer identity.

This module deliberately does not import ``app.py`` and does not contain a
copy of any Shop, appearance, pet, Premium, or gacha catalog.  A caller must
resolve the current server facts first.  C025 only validates those facts,
derives a stable business identity, and derives a deterministic semantic
version suitable for a later C019 wiring layer.

There are no database, balance, inventory, wardrobe, lineage, transaction,
or purchase-operation APIs here.  A ready result is a projection only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
import hashlib
import json
import re
from typing import Any


COINS = "COINS"
ACTIVE = "ACTIVE"

READY = "READY"
NEEDS_DESTINATION_ADAPTER = "NEEDS_DESTINATION_ADAPTER"
NEEDS_MULTI_GRANT_PROFILE = "NEEDS_MULTI_GRANT_PROFILE"
NEEDS_CATALOG_NORMALIZATION = "NEEDS_CATALOG_NORMALIZATION"
LEGACY_EFFECT_EXCLUDED = "LEGACY_EFFECT_EXCLUDED"
NEEDS_FREE_GRANT_AUTHORITY = "NEEDS_FREE_GRANT_AUTHORITY"
PREMIUM_CASH_SEPARATE = "PREMIUM_CASH_SEPARATE"
PREMIUM_ENTITLEMENT_SEPARATE = "PREMIUM_ENTITLEMENT_SEPARATE"
GACHA_EXCLUDED = "GACHA_EXCLUDED"

OFFER_FAMILY_STATIC_ITEM = "STATIC_SHOP_ITEM"
OFFER_FAMILY_EXPLICIT_COSMETIC = "EXPLICIT_COIN_COSMETIC"
OFFER_FAMILY_DAILY_ITEM = "DAILY_SHOP_ITEM"
OFFER_FAMILY_DAILY_COSMETIC = "DAILY_MAPPED_COSMETIC"

OFFER_KIND_FIXED_ITEM = "FIXED_ITEM"
OFFER_KIND_WARDROBE = "WARDROBE"
OFFER_KIND_DAILY_ITEM = "DAILY_ITEM"
OFFER_KIND_DAILY_WARDROBE = "DAILY_WARDROBE"

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
READY_DESTINATIONS = frozenset({"shop_inventory", "player_wardrobe"})
PLAYER_INVENTORY_EQUIPMENT_CLASSES = frozenset(
    {"WEAPON", "ARMOR", "ACCESSORY"}
)
PLAYER_INVENTORY_EQUIPMENT_DUPLICATE_POLICIES = frozenset(
    {"REJECT_IF_OWNED", "ALLOW_DUPLICATE"}
)
ADAPTER_DESTINATIONS = frozenset({"pet_inventory"})
KNOWN_NON_C025_DESTINATIONS = frozenset(
    {"entitlement", "capacity", "credit"}
)
DUPLICATE_POLICIES = frozenset(
    {"STACK", "REJECT_IF_OWNED", "ALLOW_DUPLICATE"}
)

_IDENTITY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_VERSION_ALGORITHM = "sha256-canonical-server-facts-v1"

_CLIENT_AUTHORED_KEYS = frozenset(
    {
        "offer_id",
        "client_offer_id",
        "price",
        "client_price",
        "display_price",
        "price_override",
        "client_quantity",
        "requested_quantity",
        "qty_requested",
        "purchase_operation_id",
        "canonical_slot",
    }
)

_FAMILY_ALIASES = {
    "STATIC": OFFER_FAMILY_STATIC_ITEM,
    "STATIC_ITEM": OFFER_FAMILY_STATIC_ITEM,
    "FIXED": OFFER_FAMILY_STATIC_ITEM,
    "FIXED_ITEM": OFFER_FAMILY_STATIC_ITEM,
    "ITEM": OFFER_FAMILY_STATIC_ITEM,
    "COIN_ITEM_PURCHASE": OFFER_FAMILY_STATIC_ITEM,
    "EXPLICIT_COSMETIC": OFFER_FAMILY_EXPLICIT_COSMETIC,
    "COIN_COSMETIC": OFFER_FAMILY_EXPLICIT_COSMETIC,
    "WARDROBE": OFFER_FAMILY_EXPLICIT_COSMETIC,
    "COSMETIC": OFFER_FAMILY_EXPLICIT_COSMETIC,
    "DAILY": OFFER_FAMILY_DAILY_ITEM,
    "DAILY_ITEM": OFFER_FAMILY_DAILY_ITEM,
    "DAILY_SHOP_ITEM": OFFER_FAMILY_DAILY_ITEM,
    "DAILY_APPEARANCE": OFFER_FAMILY_DAILY_COSMETIC,
    "DAILY_WARDROBE": OFFER_FAMILY_DAILY_COSMETIC,
    "DAILY_MAPPED_COSMETIC": OFFER_FAMILY_DAILY_COSMETIC,
    "FREE_OFFER": "FREE_OFFER",
    "PREMIUM_CASH": "PREMIUM_CASH",
    "PREMIUM_CASH_SUBSCRIPTION": "PREMIUM_CASH",
    "PREMIUM_ENTITLEMENT": "PREMIUM_ENTITLEMENT",
    "PREMIUM": "PREMIUM_ENTITLEMENT",
    "GACHA": "GACHA",
    "LOOT_BOX": "GACHA",
}


class ShopOfferIdentityError(ValueError):
    """Base class for fail-closed server-fact projection errors."""

    code = "SHOP_OFFER_IDENTITY_ERROR"

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.details = dict(details or {})
        super().__init__(message)


class ClientAuthoredInput(ShopOfferIdentityError):
    code = "CLIENT_AUTHORED_INPUT"


class InvalidServerFacts(ShopOfferIdentityError):
    code = "INVALID_SERVER_FACTS"


class UnsupportedServerOffer(ShopOfferIdentityError):
    code = "UNSUPPORTED_SERVER_OFFER"


class UnknownDestination(ShopOfferIdentityError):
    code = "UNKNOWN_DESTINATION"


class UnsupportedDuplicatePolicy(ShopOfferIdentityError):
    code = "UNKNOWN_DUPLICATE_POLICY"


class OfferNotReady(ShopOfferIdentityError):
    """A known source fact shape is not ready for C019 normalization."""

    def __init__(
        self,
        status: str,
        reason: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.status = status
        super().__init__(reason, details={"status": status, **dict(details or {})})


@dataclass(frozen=True)
class GrantFact:
    """One server-resolved grant component; it is not an ownership row."""

    item_id: str
    quantity: int
    destination: str | None = None

    def canonical(self, default_destination: str) -> dict[str, Any]:
        destination = self.destination or default_destination
        return {
            "item_id": _identity(self.item_id, "grant_profile.item_id"),
            "quantity": _positive_int(self.quantity, "grant_profile.quantity"),
            "destination": _text(destination, "grant_profile.destination"),
        }


@dataclass(frozen=True)
class ServerShopOfferFacts:
    """Caller-supplied server facts for one existing Shop product.

    This dataclass intentionally has no offer ID or purchase-operation ID.
    ``server_price`` is the only accepted price field; request/display price
    aliases are rejected by ``from_mapping``.
    """

    offer_family: str
    item_key: str | None
    item_id: str | None
    server_price: Any
    quantity: Any
    destination: str
    acquisition_class: str
    duplicate_policy: str
    eligibility_reference: str
    price_reference: str
    catalog_reference: str
    product_id: str | None = None
    currency: str = COINS
    daily: bool = False
    shop_date: str | None = None
    legacy_effect: bool = False
    premium_cash: bool = False
    premium_entitlement: bool = False
    gacha: bool = False
    free: bool = False
    grant_profile: tuple[GrantFact, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ServerShopOfferFacts":
        if not isinstance(raw, Mapping):
            raise InvalidServerFacts("server offer facts must be a mapping")
        forbidden = _CLIENT_AUTHORED_KEYS.intersection(raw)
        if forbidden:
            raise ClientAuthoredInput(
                "client-authored offer or price fields are not accepted",
                details={"fields": sorted(forbidden)},
            )

        grant_value = raw.get("grant_profile", raw.get("grants", ()))
        grants = _grant_profile(grant_value)
        metadata = _metadata(raw.get("metadata"))
        return cls(
            offer_family=raw.get("offer_family", raw.get("offer_kind", "")),
            item_key=raw.get("item_key", raw.get("key")),
            item_id=raw.get("item_id", raw.get("reward_id")),
            server_price=raw.get("server_price"),
            quantity=raw.get("quantity", raw.get("server_quantity", 1)),
            destination=raw.get("destination", ""),
            acquisition_class=raw.get("acquisition_class", raw.get("class", "")),
            duplicate_policy=raw.get("duplicate_policy", ""),
            eligibility_reference=raw.get("eligibility_reference", ""),
            price_reference=raw.get("price_reference", ""),
            catalog_reference=raw.get("catalog_reference", ""),
            product_id=raw.get("product_id"),
            currency=raw.get("currency", COINS),
            daily=raw.get("daily", False),
            shop_date=raw.get("shop_date", raw.get("business_date")),
            legacy_effect=raw.get("legacy_effect", False),
            premium_cash=raw.get("premium_cash", False),
            premium_entitlement=raw.get("premium_entitlement", False),
            gacha=raw.get("gacha", raw.get("random_reward", False)),
            free=raw.get("free", False),
            grant_profile=grants,
            metadata=metadata,
        )


@dataclass(frozen=True)
class NormalizedShopOffer:
    """A ready C021-compatible projection with no mutation authority."""

    offer_id: str
    offer_version: str
    product_id: str | None
    item_id: str
    quantity: int
    currency: str
    server_price: int
    destination: str
    acquisition_class: str
    duplicate_policy: str
    eligibility_reference: str
    price_reference: str
    catalog_reference: str
    offer_kind: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "offer_id": self.offer_id,
            "offer_version": self.offer_version,
            "product_id": self.product_id,
            "item_id": self.item_id,
            "quantity": self.quantity,
            "currency": self.currency,
            "server_price": self.server_price,
            "destination": self.destination,
            "acquisition_class": self.acquisition_class,
            "duplicate_policy": self.duplicate_policy,
            "eligibility_reference": self.eligibility_reference,
            "price_reference": self.price_reference,
            "catalog_reference": self.catalog_reference,
            "offer_kind": self.offer_kind,
            "metadata": dict(self.metadata),
        }

    def as_c019_mapping(self) -> dict[str, Any]:
        """Return the accepted C019 ``CoinShopOffer.from_mapping`` shape."""

        eligibility = {
            "reference": self.eligibility_reference,
            "catalog_reference": self.catalog_reference,
        }
        presentation = {
            **dict(self.metadata),
            "product_id": self.product_id,
            "price_reference": self.price_reference,
            "catalog_reference": self.catalog_reference,
        }
        return {
            "offer_id": self.offer_id,
            "item_id": self.item_id,
            "quantity": self.quantity,
            "currency_type": self.currency,
            "price": self.server_price,
            "destination": self.destination,
            "acquisition_class": self.acquisition_class,
            "offer_type": self.offer_kind,
            "offer_version": self.offer_version,
            "status": ACTIVE,
            "duplicate_policy": self.duplicate_policy,
            "eligibility_metadata": eligibility,
            "presentation_metadata": presentation,
            "product_id": self.product_id,
            "server_price": self.server_price,
            "price_reference": self.price_reference,
            "catalog_reference": self.catalog_reference,
        }


@dataclass(frozen=True)
class ShopOfferProjection:
    """Ready or explicitly blocked projection result."""

    status: str
    offer: NormalizedShopOffer | None = None
    reason: str = ""
    blockers: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "offer": self.offer.as_dict() if self.offer else None,
            "reason": self.reason,
            "blockers": list(self.blockers),
        }


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidServerFacts(f"{field_name} must be non-empty text")
    return value.strip()


def _identity(value: Any, field_name: str) -> str:
    value = _text(value, field_name)
    if not _IDENTITY_RE.fullmatch(value):
        raise InvalidServerFacts(
            f"{field_name} contains unsupported machine-identity characters",
            details={field_name: value},
        )
    return value


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidServerFacts(f"{field_name} must be a positive integer")
    return value


def _bool_flag(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise InvalidServerFacts(f"{field_name} must be boolean")
    return value


def _metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise InvalidServerFacts("metadata must be a mapping")
    forbidden = _CLIENT_AUTHORED_KEYS.intersection(value)
    if forbidden:
        raise ClientAuthoredInput(
            "metadata contains client-authoritative purchase fields",
            details={"fields": sorted(forbidden)},
        )
    result = dict(value)
    try:
        json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise InvalidServerFacts("metadata must be JSON serializable") from exc
    return result


def _grant_profile(value: Any) -> tuple[GrantFact, ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        value = tuple(
            {"item_id": item_id, "quantity": quantity}
            for item_id, quantity in value.items()
        )
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidServerFacts("grant_profile must be a sequence or mapping")
    grants: list[GrantFact] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise InvalidServerFacts(f"grant_profile[{index}] must be a mapping")
        grants.append(
            GrantFact(
                item_id=_identity(raw.get("item_id"), f"grant_profile[{index}].item_id"),
                quantity=_positive_int(
                    raw.get("quantity"), f"grant_profile[{index}].quantity"
                ),
                destination=raw.get("destination"),
            )
        )
    return tuple(grants)


def _canonical_family(value: Any) -> tuple[str, bool]:
    raw = _text(value, "offer_family").upper().replace("-", "_").replace(" ", "_")
    family = _FAMILY_ALIASES.get(raw, raw)
    if family in {"FREE_OFFER", "PREMIUM_CASH", "PREMIUM_ENTITLEMENT", "GACHA"}:
        return family, False
    if family not in {
        OFFER_FAMILY_STATIC_ITEM,
        OFFER_FAMILY_EXPLICIT_COSMETIC,
        OFFER_FAMILY_DAILY_ITEM,
        OFFER_FAMILY_DAILY_COSMETIC,
    }:
        raise UnsupportedServerOffer(
            f"unsupported offer_family: {value!r}",
            details={"offer_family": value},
        )
    daily = family in {OFFER_FAMILY_DAILY_ITEM, OFFER_FAMILY_DAILY_COSMETIC}
    base = (
        OFFER_FAMILY_EXPLICIT_COSMETIC
        if family in {OFFER_FAMILY_EXPLICIT_COSMETIC, OFFER_FAMILY_DAILY_COSMETIC}
        else OFFER_FAMILY_STATIC_ITEM
    )
    return base, daily


def _date(value: Any) -> str:
    value = _text(value, "shop_date")
    if not _DATE_RE.fullmatch(value):
        raise InvalidServerFacts("shop_date must use YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise InvalidServerFacts("shop_date is not a real calendar date") from exc
    return value


def _identity_suffix(value: str | None, suffix: str) -> bool:
    return bool(value) and (value == suffix or value.endswith(f".{suffix}"))


def _blocked(
    status: str,
    reason: str,
    *,
    blockers: tuple[str, ...] = (),
) -> ShopOfferProjection:
    return ShopOfferProjection(status=status, reason=reason, blockers=blockers)


def _version(
    *,
    offer_id: str,
    family: str,
    daily: bool,
    shop_date: str | None,
    product_id: str | None,
    item_key: str | None,
    item_id: str,
    server_price: int,
    quantity: int,
    destination: str,
    acquisition_class: str,
    duplicate_policy: str,
    grants: list[dict[str, Any]],
) -> str:
    payload = {
        "algorithm": _VERSION_ALGORITHM,
        "offer_id": offer_id,
        "family": family,
        "daily": daily,
        "shop_date": shop_date if daily else None,
        "product_id": product_id,
        "item_key": item_key,
        "item_id": item_id,
        "currency": COINS,
        "server_price": server_price,
        "quantity": quantity,
        "destination": destination,
        "acquisition_class": acquisition_class,
        "duplicate_policy": duplicate_policy,
        "grant_profile": grants,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:20]
    return f"v1-{shop_date + '-' if daily else ''}{digest}"


def _offer_kind(*, family: str, daily: bool) -> str:
    if family == OFFER_FAMILY_EXPLICIT_COSMETIC:
        return OFFER_KIND_DAILY_WARDROBE if daily else OFFER_KIND_WARDROBE
    return OFFER_KIND_DAILY_ITEM if daily else OFFER_KIND_FIXED_ITEM


def project_shop_offer(
    facts: ServerShopOfferFacts | Mapping[str, Any],
) -> ShopOfferProjection:
    """Project trusted facts, or return an explicit non-ready status.

    This function has no side effects.  It never creates a purchase identity,
    because ``offer_id`` and ``offer_version`` are not purchase operations.
    """

    if not isinstance(facts, ServerShopOfferFacts):
        facts = ServerShopOfferFacts.from_mapping(facts)

    family, family_daily = _canonical_family(facts.offer_family)
    daily = family_daily or _bool_flag(facts.daily, "daily")
    legacy_effect = _bool_flag(facts.legacy_effect, "legacy_effect")
    premium_cash = _bool_flag(facts.premium_cash, "premium_cash")
    premium_entitlement = _bool_flag(
        facts.premium_entitlement, "premium_entitlement"
    )
    gacha = _bool_flag(facts.gacha, "gacha")
    free = _bool_flag(facts.free, "free")
    currency = _text(facts.currency, "currency").upper()
    item_id = _identity(facts.item_id, "item_id") if facts.item_id else None
    product_id = _identity(facts.product_id, "product_id") if facts.product_id else None
    item_key = _identity(facts.item_key, "item_key") if facts.item_key else None

    if premium_cash or family == "PREMIUM_CASH" or currency != COINS:
        return _blocked(
            PREMIUM_CASH_SEPARATE,
            "Premium cash and non-Coin products are outside C019 Coin offers",
        )
    if premium_entitlement or family == "PREMIUM_ENTITLEMENT":
        return _blocked(
            PREMIUM_ENTITLEMENT_SEPARATE,
            "Premium entitlement products are outside the C019 Coin path",
        )
    if gacha or family == "GACHA":
        return _blocked(
            GACHA_EXCLUDED,
            "random/gacha rewards cannot become deterministic C019 offers",
        )
    if free or family == "FREE_OFFER":
        return _blocked(
            NEEDS_FREE_GRANT_AUTHORITY,
            "free grants require a separate approved grant authority",
        )
    if _identity_suffix(product_id, "robe_premium") or _identity_suffix(
        item_id, "robe_premium"
    ):
        return _blocked(
            PREMIUM_ENTITLEMENT_SEPARATE,
            "robe_premium is a Premium entitlement, not a Coin offer",
        )
    if _identity_suffix(product_id, "xp_amulet") or _identity_suffix(
        item_id, "xp_amulet"
    ):
        return _blocked(
            "AUTHORITY_HOLD",
            "xp_amulet remains HOLD_FOR_AUTHORITY",
        )
    if _identity_suffix(product_id, "go_stone_black") or _identity_suffix(
        item_id, "go_stone_black"
    ):
        return _blocked(
            "TROPHY_INVENTORY_ONLY",
            "go_stone_black has no functional Coin sale authority",
        )
    if legacy_effect:
        return _blocked(
            LEGACY_EFFECT_EXCLUDED,
            "effect-bearing appearance is not a pure Coin cosmetic",
        )
    if item_id is None:
        raise InvalidServerFacts(
            "item_id is required for a Coin item or cosmetic offer"
        )

    if isinstance(facts.server_price, bool) or not isinstance(facts.server_price, int):
        raise InvalidServerFacts("server_price must be an integer")
    if facts.server_price == 0:
        return _blocked(
            NEEDS_FREE_GRANT_AUTHORITY,
            "zero-price offers cannot enter the C019 Coin debit path",
        )
    if facts.server_price < 0:
        raise InvalidServerFacts("server_price must not be negative")
    server_price = facts.server_price
    quantity = _positive_int(facts.quantity, "quantity")
    destination = _text(facts.destination, "destination").lower()
    if destination in ADAPTER_DESTINATIONS:
        destination_blocker = NEEDS_DESTINATION_ADAPTER
    elif destination == "multi_grant_profile":
        return _blocked(
            NEEDS_MULTI_GRANT_PROFILE,
            "multi-grant destinations require an explicit grant profile",
            blockers=(NEEDS_MULTI_GRANT_PROFILE,),
        )
    elif destination == "player_inventory":
        # C029 extends C025 only for the explicitly validated functional
        # Equipment matrix below.  This is deliberately not a generic
        # player_inventory readiness flag.
        destination_blocker = None
    elif destination in READY_DESTINATIONS:
        destination_blocker = None
    elif destination in KNOWN_NON_C025_DESTINATIONS:
        raise UnknownDestination(
            f"destination is outside the C025 first slice: {destination!r}",
            details={"destination": destination},
        )
    else:
        raise UnknownDestination(
            f"destination is not a recognized server destination: {destination!r}",
            details={"destination": destination},
        )

    acquisition_class = _text(
        facts.acquisition_class, "acquisition_class"
    ).upper()
    duplicate_policy = _text(
        facts.duplicate_policy, "duplicate_policy"
    ).upper()

    multi_grant_hint = (
        len(facts.grant_profile) > 1
        or acquisition_class == "TREASURE_BUNDLE"
        or duplicate_policy == "NEEDS_PROFILE"
    )

    if destination_blocker:
        blockers = [destination_blocker]
        if multi_grant_hint:
            blockers.append(NEEDS_MULTI_GRANT_PROFILE)
        return _blocked(
            destination_blocker,
            "pet_inventory requires a later destination adapter",
            blockers=tuple(blockers),
        )
    if multi_grant_hint:
        return _blocked(
            NEEDS_MULTI_GRANT_PROFILE,
            "bundle or multiple grants require an explicit C019 grant profile",
            blockers=(NEEDS_MULTI_GRANT_PROFILE,),
        )

    if acquisition_class not in CANONICAL_ITEM_CLASSES:
        raise InvalidServerFacts(
            f"unsupported acquisition_class: {acquisition_class!r}"
        )

    if daily:
        shop_date = _date(facts.shop_date)
    else:
        if facts.shop_date is not None:
            raise InvalidServerFacts(
                "shop_date is only valid for daily offer facts"
            )
        shop_date = None

    if family == OFFER_FAMILY_EXPLICIT_COSMETIC and product_id is None:
        return _blocked(
            NEEDS_CATALOG_NORMALIZATION,
            "daily/fallback cosmetics require a server-owned product_id",
        )

    if duplicate_policy not in DUPLICATE_POLICIES:
        raise UnsupportedDuplicatePolicy(
            f"duplicate policy is not supported: {duplicate_policy!r}",
            details={"allowed": sorted(DUPLICATE_POLICIES)},
        )

    eligibility_reference = _text(
        facts.eligibility_reference, "eligibility_reference"
    )
    price_reference = _text(facts.price_reference, "price_reference")
    catalog_reference = _text(facts.catalog_reference, "catalog_reference")
    metadata = _metadata(facts.metadata)

    grants = [grant.canonical(destination) for grant in facts.grant_profile]
    grants.sort(
        key=lambda grant: (
            grant["item_id"],
            grant["destination"],
            grant["quantity"],
        )
    )
    if not grants:
        grants = [
            {
                "item_id": item_id,
                "quantity": quantity,
                "destination": destination,
            }
        ]

    if len(grants) > 1:
        multi_blocker = NEEDS_MULTI_GRANT_PROFILE
    else:
        multi_blocker = None
    if multi_blocker:
        return _blocked(
            multi_blocker,
            "multiple grants require an explicit C019 multi-grant profile",
            blockers=(multi_blocker,),
        )

    grant = grants[0]
    if grant["item_id"] != item_id or grant["quantity"] != quantity:
        raise InvalidServerFacts(
            "single grant must agree with item_id and quantity",
            details={"item_id": item_id, "grant": grant},
        )

    if family == OFFER_FAMILY_STATIC_ITEM:
        if item_key is None:
            return _blocked(
                NEEDS_CATALOG_NORMALIZATION,
                "static item facts require an authoritative item_key",
            )
        if destination == "player_inventory":
            if daily:
                raise UnsupportedServerOffer(
                    "daily functional Equipment is outside the C029 projection"
                )
            if acquisition_class not in PLAYER_INVENTORY_EQUIPMENT_CLASSES:
                raise UnsupportedServerOffer(
                    "player_inventory readiness is limited to functional Equipment"
                )
            if quantity != 1:
                raise UnsupportedServerOffer(
                    "player_inventory functional Equipment requires quantity=1"
                )
            if duplicate_policy not in PLAYER_INVENTORY_EQUIPMENT_DUPLICATE_POLICIES:
                raise UnsupportedServerOffer(
                    "player_inventory functional Equipment requires an explicit "
                    "REJECT_IF_OWNED or ALLOW_DUPLICATE policy"
                )
            if grant["destination"] != destination:
                raise UnsupportedServerOffer(
                    "player_inventory Equipment grant destination must match "
                    "the acquisition destination"
                )
        else:
            if destination != "shop_inventory" or acquisition_class == "COSMETIC":
                raise UnsupportedServerOffer(
                    "C025 first slice only projects direct stackable Shop items"
                )
            if duplicate_policy != "STACK":
                raise UnsupportedServerOffer(
                    "C025 first slice requires STACK for direct Shop items"
                )
        offer_id = f"shop.static.{item_key}"
    else:
        if destination != "player_wardrobe" or acquisition_class != "COSMETIC":
            raise InvalidServerFacts(
                "explicit Coin cosmetics must target player_wardrobe as COSMETIC"
            )
        if product_id is None:
            return _blocked(
                NEEDS_CATALOG_NORMALIZATION,
                "daily/fallback cosmetics require a server-owned product_id",
            )
        if duplicate_policy != "REJECT_IF_OWNED" or quantity != 1:
            raise UnsupportedServerOffer(
                "explicit Coin cosmetics require one REJECT_IF_OWNED grant"
            )
        offer_id = f"shop.cosmetic.{product_id}"

    offer_version = _version(
        offer_id=offer_id,
        family=family,
        daily=daily,
        shop_date=shop_date,
        product_id=product_id,
        item_key=item_key,
        item_id=item_id,
        server_price=server_price,
        quantity=quantity,
        destination=destination,
        acquisition_class=acquisition_class,
        duplicate_policy=duplicate_policy,
        grants=grants,
    )
    kind = _offer_kind(family=family, daily=daily)
    output_metadata = {
        **metadata,
        "business_identity": offer_id,
        "version_algorithm": _VERSION_ALGORITHM,
        "daily": daily,
        **({"shop_date": shop_date} if shop_date else {}),
    }
    offer = NormalizedShopOffer(
        offer_id=offer_id,
        offer_version=offer_version,
        product_id=product_id,
        item_id=item_id,
        quantity=quantity,
        currency=COINS,
        server_price=server_price,
        destination=destination,
        acquisition_class=acquisition_class,
        duplicate_policy=duplicate_policy,
        eligibility_reference=eligibility_reference,
        price_reference=price_reference,
        catalog_reference=catalog_reference,
        offer_kind=kind,
        metadata=output_metadata,
    )
    return ShopOfferProjection(status=READY, offer=offer, reason="normalized")


def normalize_shop_offer(
    facts: ServerShopOfferFacts | Mapping[str, Any],
) -> NormalizedShopOffer:
    """Return a ready offer or raise ``OfferNotReady`` fail-closed."""

    result = project_shop_offer(facts)
    if result.status != READY or result.offer is None:
        raise OfferNotReady(
            result.status,
            result.reason,
            details={"blockers": list(result.blockers)},
        )
    return result.offer


def normalize_shop_offers(
    facts_iterable: Sequence[ServerShopOfferFacts | Mapping[str, Any]],
) -> tuple[NormalizedShopOffer, ...]:
    """Normalize a caller-owned batch and reject business-ID collisions."""

    normalized: list[NormalizedShopOffer] = []
    seen_ids: set[str] = set()
    for facts in facts_iterable:
        offer = normalize_shop_offer(facts)
        if offer.offer_id in seen_ids:
            raise InvalidServerFacts(
                f"derived offer_id is duplicated: {offer.offer_id!r}",
                details={"offer_id": offer.offer_id},
            )
        seen_ids.add(offer.offer_id)
        normalized.append(offer)
    return tuple(normalized)


__all__ = [
    "ACTIVE",
    "CANONICAL_ITEM_CLASSES",
    "COINS",
    "DUPLICATE_POLICIES",
    "PLAYER_INVENTORY_EQUIPMENT_CLASSES",
    "PLAYER_INVENTORY_EQUIPMENT_DUPLICATE_POLICIES",
    "ClientAuthoredInput",
    "GrantFact",
    "GACHA_EXCLUDED",
    "InvalidServerFacts",
    "LEGACY_EFFECT_EXCLUDED",
    "NEEDS_CATALOG_NORMALIZATION",
    "NEEDS_DESTINATION_ADAPTER",
    "NEEDS_FREE_GRANT_AUTHORITY",
    "NEEDS_MULTI_GRANT_PROFILE",
    "NormalizedShopOffer",
    "OfferNotReady",
    "PREMIUM_CASH_SEPARATE",
    "PREMIUM_ENTITLEMENT_SEPARATE",
    "READY",
    "ServerShopOfferFacts",
    "ShopOfferIdentityError",
    "ShopOfferProjection",
    "UnknownDestination",
    "UnsupportedDuplicatePolicy",
    "UnsupportedServerOffer",
    "normalize_shop_offer",
    "normalize_shop_offers",
    "project_shop_offer",
]
