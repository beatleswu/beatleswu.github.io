"""Pure server-side normalization from catalog facts to C019 Coin offers.

This module deliberately does not import ``app.py`` and does not contain a
copy of ``SHOP_ITEMS`` or any other product catalog.  A caller supplies facts
already resolved from an existing server catalog; this module validates their
shape, derives a stable offer identity, and returns a C019-compatible offer
mapping.

The adapter owns no balances, transactions, inventory, wardrobe state,
eligibility evaluation, or acquisition.  In particular, it never debits
Coins, writes D5A, or creates a purchase-operation identity.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
import json
import re
from typing import Any


COINS = "COINS"
ACTIVE = "ACTIVE"

READY = "READY"
NEEDS_DESTINATION_ADAPTER = "NEEDS_DESTINATION_ADAPTER"
NEEDS_MULTI_GRANT_PROFILE = "NEEDS_MULTI_GRANT_PROFILE"

OFFER_KIND_FIXED_ITEM = "FIXED_ITEM"
OFFER_KIND_DAILY_ITEM = "DAILY_ITEM"
OFFER_KIND_WARDROBE = "WARDROBE"
OFFER_KIND_DAILY_WARDROBE = "DAILY_WARDROBE"
OFFER_KIND_FREE = "FREE_OFFER"

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
SUPPORTED_DESTINATIONS = frozenset({"shop_inventory", "player_wardrobe"})
ADAPTER_DESTINATIONS = frozenset({"pet_inventory"})
DUPLICATE_POLICIES = frozenset(
    {"STACK", "REJECT_IF_OWNED", "ALLOW_DUPLICATE"}
)

_OFFER_KIND_ALIASES = {
    "FIXED": OFFER_KIND_FIXED_ITEM,
    "FIXED_ITEM": OFFER_KIND_FIXED_ITEM,
    "ITEM": OFFER_KIND_FIXED_ITEM,
    "COIN_ITEM_PURCHASE": OFFER_KIND_FIXED_ITEM,
    "DAILY": OFFER_KIND_DAILY_ITEM,
    "DAILY_ITEM": OFFER_KIND_DAILY_ITEM,
    "WARDROBE": OFFER_KIND_WARDROBE,
    "COSMETIC": OFFER_KIND_WARDROBE,
    "COIN_COSMETIC": OFFER_KIND_WARDROBE,
    "DAILY_WARDROBE": OFFER_KIND_DAILY_WARDROBE,
    "DAILY_APPEARANCE": OFFER_KIND_DAILY_WARDROBE,
    "FREE_OFFER": OFFER_KIND_FREE,
    "PREMIUM_CASH": "PREMIUM_CASH_SUBSCRIPTION",
    "PREMIUM_CASH_SUBSCRIPTION": "PREMIUM_CASH_SUBSCRIPTION",
    "PREMIUM": "PREMIUM_ENTITLEMENT",
    "PREMIUM_ENTITLEMENT": "PREMIUM_ENTITLEMENT",
    "ENTITLEMENT": "PREMIUM_ENTITLEMENT",
    "GACHA": "GACHA",
    "LOOT_BOX": "GACHA",
    "LEGACY_EFFECT_COSMETIC": "LEGACY_EFFECT_COSMETIC",
    "LEGACY_EFFECT_APPEARANCE": "LEGACY_EFFECT_COSMETIC",
    "MULTI_GRANT": "MULTI_GRANT",
}

_VERSION_RE = re.compile(r"^v[0-9]+$")
_IDENTITY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

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
    }
)


class ShopOfferAdapterError(ValueError):
    """Base class for fail-closed normalization errors."""

    code = "SHOP_OFFER_ADAPTER_ERROR"

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.details = dict(details or {})
        super().__init__(message)


class ClientAuthoredInput(ShopOfferAdapterError):
    code = "CLIENT_AUTHORED_INPUT"


class InvalidOfferFacts(ShopOfferAdapterError):
    code = "INVALID_OFFER_FACTS"


class UnsupportedCoinOffer(ShopOfferAdapterError):
    code = "UNSUPPORTED_COIN_OFFER"


class UnknownDestination(ShopOfferAdapterError):
    code = "UNKNOWN_DESTINATION"


class UnsupportedDuplicatePolicy(ShopOfferAdapterError):
    code = "UNKNOWN_DUPLICATE_POLICY"


class OfferNotReady(ShopOfferAdapterError):
    """A known offer shape needs a later adapter before C019 wiring."""

    def __init__(self, status: str, reason: str, *, details: Mapping[str, Any] | None = None):
        self.status = status
        super().__init__(reason, details={"status": status, **dict(details or {})})


@dataclass(frozen=True)
class ServerCatalogFacts:
    """Trusted server-side facts for one existing catalog product.

    This is an input boundary, not a catalog.  The caller is responsible for
    resolving these values from the current server catalog and date/eligibility
    context.  There is intentionally no ``offer_id`` field: C021 derives it.
    """

    product_id: str
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
    offer_kind: str = OFFER_KIND_FIXED_ITEM
    offer_version: str = "v1"
    business_date: str | None = None
    grants: tuple[Mapping[str, Any], ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    legacy_effect: bool = False
    random_reward: bool = False


@dataclass(frozen=True)
class NormalizedCoinShopOffer:
    """C021 output and C019-compatible server offer input."""

    offer_id: str
    offer_version: str
    product_id: str
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
        """Return the explicit C021 normalized contract."""

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
        """Return fields accepted by the C019 ``CoinShopOffer`` contract.

        The import remains deliberately indirect because C019 is a separately
        integrated transaction authority.  A future wiring layer can call
        ``CoinShopOffer.from_mapping(offer.as_c019_mapping())`` without this
        adapter owning C019 runtime behavior.
        """

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
            # These aliases make the server-resolved provenance visible to a
            # future integration layer without changing C019's authority.
            "product_id": self.product_id,
            "server_price": self.server_price,
            "price_reference": self.price_reference,
            "catalog_reference": self.catalog_reference,
        }


@dataclass(frozen=True)
class ShopOfferAdaptation:
    """Classification result for one server catalog fact set."""

    status: str
    offer: NormalizedCoinShopOffer | None = None
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
        raise InvalidOfferFacts(f"{field_name} must be non-empty text")
    return value.strip()


def _identity(value: Any, field_name: str) -> str:
    value = _text(value, field_name)
    if not _IDENTITY_RE.fullmatch(value):
        raise InvalidOfferFacts(
            f"{field_name} contains unsupported machine-identity characters",
            details={field_name: value},
        )
    return value


def _positive_int(value: Any, field_name: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidOfferFacts(f"{field_name} must be an integer")
    if value < 0 or (value == 0 and not allow_zero):
        comparison = "non-negative" if allow_zero else "positive"
        raise InvalidOfferFacts(f"{field_name} must be {comparison}")
    return value


def _canonical_kind(value: Any, *, destination: Any = "") -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        destination_text = str(destination or "").strip().lower()
        return (
            OFFER_KIND_WARDROBE
            if destination_text == "player_wardrobe"
            else OFFER_KIND_FIXED_ITEM
        )
    kind = _text(value, "offer_kind").upper().replace("-", "_").replace(" ", "_")
    return _OFFER_KIND_ALIASES.get(kind, kind)


def _metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise InvalidOfferFacts("metadata must be a mapping")
    result = dict(value)
    forbidden_nested = _CLIENT_AUTHORED_KEYS.intersection(result)
    if forbidden_nested:
        raise ClientAuthoredInput(
            "metadata contains client-authoritative purchase fields",
            details={"fields": sorted(forbidden_nested)},
        )
    try:
        json.dumps(result, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise InvalidOfferFacts("metadata must be JSON serializable") from exc
    return result


def _grants(value: Any) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        # Accept the existing catalog's {item_id: quantity} grant shape, but
        # do not flatten it into a single item when it contains >1 component.
        return tuple(
            {"item_id": item_id, "quantity": quantity}
            for item_id, quantity in value.items()
        )
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidOfferFacts("grants must be a sequence or item->quantity mapping")
    result: list[Mapping[str, Any]] = []
    for index, grant in enumerate(value):
        if not isinstance(grant, Mapping):
            raise InvalidOfferFacts(f"grants[{index}] must be a mapping")
        item_id = _identity(grant.get("item_id"), f"grants[{index}].item_id")
        quantity = _positive_int(grant.get("quantity"), f"grants[{index}].quantity")
        result.append({**dict(grant), "item_id": item_id, "quantity": quantity})
    return tuple(result)


def _facts_from_mapping(raw: Mapping[str, Any]) -> ServerCatalogFacts:
    if not isinstance(raw, Mapping):
        raise InvalidOfferFacts("catalog facts must be a mapping")
    forbidden = _CLIENT_AUTHORED_KEYS.intersection(raw)
    if forbidden:
        raise ClientAuthoredInput(
            "client-authored offer identity/price/quantity is not accepted",
            details={"fields": sorted(forbidden)},
        )

    grants_value = raw.get("grants")
    if grants_value is None:
        component_grants: list[Mapping[str, Any]] = []
        for field_name in ("grants_items", "grants_food"):
            value = raw.get(field_name) or {}
            if not isinstance(value, Mapping):
                raise InvalidOfferFacts(f"{field_name} must be a mapping")
            component_grants.extend(
                {"item_id": item_id, "quantity": quantity}
                for item_id, quantity in value.items()
            )
        grants_value = component_grants

    metadata = _metadata(raw.get("metadata"))
    raw_kind = raw.get("offer_kind", raw.get("kind"))
    destination = raw.get("destination", "")
    if raw_kind is None and raw.get("gacha") is True:
        raw_kind = "GACHA"
    if raw_kind is None and raw.get("daily") is True:
        raw_kind = (
            OFFER_KIND_DAILY_WARDROBE
            if str(destination).strip() == "player_wardrobe"
            else OFFER_KIND_DAILY_ITEM
        )

    return ServerCatalogFacts(
        product_id=raw.get("product_id", raw.get("key", "")),
        item_id=raw.get("item_id", raw.get("reward_id", "")),
        quantity=raw.get("quantity", raw.get("server_quantity", 1)),
        currency=raw.get("currency", ""),
        server_price=raw.get("server_price"),
        destination=destination,
        acquisition_class=raw.get("acquisition_class", raw.get("class", "")),
        duplicate_policy=raw.get("duplicate_policy", ""),
        eligibility_reference=raw.get("eligibility_reference", ""),
        price_reference=raw.get("price_reference", ""),
        catalog_reference=raw.get("catalog_reference", ""),
        offer_kind=raw_kind or OFFER_KIND_FIXED_ITEM,
        offer_version=raw.get("offer_version", "v1"),
        business_date=raw.get("business_date", raw.get("offer_date", raw.get("date"))),
        grants=_grants(grants_value),
        metadata=metadata,
        legacy_effect=bool(
            raw.get("legacy_effect")
            or raw.get("is_legacy_effect")
            or metadata.get("legacy_effect")
        ),
        random_reward=bool(
            raw.get("random_reward")
            or raw.get("is_random")
            or raw.get("gacha")
            or metadata.get("random_reward")
        ),
    )


def _coerce_facts(value: ServerCatalogFacts | Mapping[str, Any]) -> ServerCatalogFacts:
    if isinstance(value, ServerCatalogFacts):
        return value
    return _facts_from_mapping(value)


def _is_special_item(item_id: str, suffix: str) -> bool:
    return item_id == suffix or item_id.endswith(f".{suffix}")


def _reject_policy_facts(facts: ServerCatalogFacts, *, kind: str, currency: str) -> None:
    product_id = str(facts.product_id or "").strip()
    item_id = str(facts.item_id or "").strip()

    if kind == OFFER_KIND_FREE:
        raise UnsupportedCoinOffer(
            "FREE_OFFER requires a separate free-grant authority and cannot enter C019",
            details={"status": "NEEDS_FREE_GRANT_AUTHORITY"},
        )
    if kind in {"PREMIUM_CASH_SUBSCRIPTION", "PREMIUM_ENTITLEMENT"}:
        raise UnsupportedCoinOffer(
            "Premium cash or entitlement offers are outside C019 Coin commerce",
            details={"offer_kind": kind},
        )
    if currency != COINS:
        raise UnsupportedCoinOffer(
            "C019 only accepts COINS offers",
            details={"currency": currency},
        )
    if kind == "GACHA" or facts.random_reward:
        raise UnsupportedCoinOffer(
            "random/gacha rewards are outside deterministic C019 Coin offers",
            details={"offer_kind": kind},
        )
    if kind in {"LEGACY_EFFECT_COSMETIC", "LEGACY_EFFECT_APPEARANCE"} or facts.legacy_effect:
        raise UnsupportedCoinOffer(
            "legacy effect-bearing appearances are not pure cosmetic C019 offers",
            details={"product_id": product_id, "item_id": item_id},
        )
    if _is_special_item(product_id, "robe_premium") or _is_special_item(item_id, "robe_premium"):
        raise UnsupportedCoinOffer(
            "robe_premium is a Premium entitlement path, not a Coin offer",
            details={"product_id": product_id, "item_id": item_id},
        )
    if _is_special_item(product_id, "xp_amulet") or _is_special_item(item_id, "xp_amulet"):
        raise UnsupportedCoinOffer(
            "xp_amulet remains HOLD_FOR_AUTHORITY",
            details={"product_id": product_id, "item_id": item_id},
        )
    if _is_special_item(product_id, "go_stone_black") or _is_special_item(item_id, "go_stone_black"):
        raise UnsupportedCoinOffer(
            "go_stone_black remains TROPHY / INVENTORY_ONLY / NO_COMBAT_POWER",
            details={"product_id": product_id, "item_id": item_id},
        )


def _daily_date(value: Any) -> str:
    value = _text(value, "business_date")
    if not _DATE_RE.fullmatch(value):
        raise InvalidOfferFacts("business_date must use YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise InvalidOfferFacts("business_date is not a real calendar date") from exc
    return value


def _version(value: Any) -> str:
    value = _text(value, "offer_version")
    if not _VERSION_RE.fullmatch(value):
        raise InvalidOfferFacts("offer_version must be a stable token such as v1")
    return value


def _offer_id(kind: str, product_id: str, version: str) -> str:
    prefixes = {
        OFFER_KIND_FIXED_ITEM: "shop.item",
        OFFER_KIND_DAILY_ITEM: "shop.daily.item",
        OFFER_KIND_WARDROBE: "shop.cosmetic",
        OFFER_KIND_DAILY_WARDROBE: "shop.daily.appearance",
    }
    try:
        prefix = prefixes[kind]
    except KeyError as exc:
        raise InvalidOfferFacts(f"unsupported Coin offer kind: {kind!r}") from exc
    return f"{prefix}.{product_id}.{version}"


def adapt_shop_offer(
    facts: ServerCatalogFacts | Mapping[str, Any],
) -> ShopOfferAdaptation:
    """Classify and, when safe, normalize one server catalog fact set.

    ``NEEDS_DESTINATION_ADAPTER`` and ``NEEDS_MULTI_GRANT_PROFILE`` are
    explicit non-ready classifications.  Invalid or policy-forbidden facts
    raise a typed error instead of producing an unsafe partial offer.
    """

    facts = _coerce_facts(facts)
    kind = _canonical_kind(facts.offer_kind, destination=facts.destination)
    currency = str(facts.currency or "").strip().upper()
    _reject_policy_facts(facts, kind=kind, currency=currency)

    product_id = _identity(facts.product_id, "product_id")
    destination = _text(facts.destination, "destination")
    if destination not in SUPPORTED_DESTINATIONS and destination not in ADAPTER_DESTINATIONS:
        raise UnknownDestination(
            f"destination is not a recognized C021 shape: {destination!r}",
            details={"destination": destination},
        )

    acquisition_class = _text(facts.acquisition_class, "acquisition_class").upper()
    if acquisition_class not in CANONICAL_ITEM_CLASSES:
        raise InvalidOfferFacts(
            f"unsupported acquisition_class: {acquisition_class!r}",
            details={"allowed": sorted(CANONICAL_ITEM_CLASSES)},
        )
    if destination == "player_wardrobe":
        if acquisition_class != "COSMETIC":
            raise InvalidOfferFacts("player_wardrobe offers must be COSMETIC")
        if facts.metadata.get("gameplay_effect") is True:
            raise UnsupportedCoinOffer(
                "a cosmetic with gameplay power cannot enter the pure Coin cosmetic path",
                details={"product_id": product_id},
            )

    duplicate_policy = _text(facts.duplicate_policy, "duplicate_policy").upper()
    if duplicate_policy not in DUPLICATE_POLICIES:
        raise UnsupportedDuplicatePolicy(
            f"duplicate policy is not a supported V1 value: {duplicate_policy!r}",
            details={"allowed": sorted(DUPLICATE_POLICIES)},
        )

    if currency != COINS:
        # Kept after the policy gate for an explicit, stable error even when
        # the destination is absent on a cash-plan fact.
        raise UnsupportedCoinOffer("C019 only accepts COINS offers")
    if (
        isinstance(facts.server_price, bool)
        or not isinstance(facts.server_price, int)
        or facts.server_price <= 0
    ):
        raise InvalidOfferFacts(
            "server_price must be a positive integer for every READY C019 Coin offer"
        )

    quantity = _positive_int(facts.quantity, "quantity")
    eligibility_reference = _text(
        facts.eligibility_reference, "eligibility_reference"
    )
    price_reference = _text(facts.price_reference, "price_reference")
    catalog_reference = _text(facts.catalog_reference, "catalog_reference")
    version_base = _version(facts.offer_version)
    metadata = _metadata(facts.metadata)
    grants = _grants(facts.grants)

    if len(grants) > 1:
        multi_blocker = NEEDS_MULTI_GRANT_PROFILE
    else:
        multi_blocker = None

    if destination in ADAPTER_DESTINATIONS:
        blockers = [NEEDS_DESTINATION_ADAPTER]
        if multi_blocker:
            blockers.append(multi_blocker)
        return ShopOfferAdaptation(
            status=NEEDS_DESTINATION_ADAPTER,
            reason="pet_inventory requires a later Spirit destination adapter",
            blockers=tuple(blockers),
        )
    if multi_blocker:
        return ShopOfferAdaptation(
            status=NEEDS_MULTI_GRANT_PROFILE,
            reason="multiple grants cannot be flattened into one C019 item result",
            blockers=(multi_blocker,),
        )

    item_id = _identity(facts.item_id, "item_id")
    if grants:
        grant = grants[0]
        grant_item_id = _identity(grant.get("item_id"), "grants[0].item_id")
        grant_quantity = _positive_int(grant.get("quantity"), "grants[0].quantity")
        if item_id != grant_item_id or quantity != grant_quantity:
            raise InvalidOfferFacts(
                "single-grant facts must agree with item_id and quantity",
                details={
                    "item_id": item_id,
                    "grant_item_id": grant_item_id,
                    "quantity": quantity,
                    "grant_quantity": grant_quantity,
                },
            )

    if kind in {OFFER_KIND_DAILY_ITEM, OFFER_KIND_DAILY_WARDROBE}:
        business_date = _daily_date(facts.business_date)
        offer_version = f"{version_base}@{business_date}"
        # The business identity remains date-independent; the date is bound
        # into both the C019 version and eligibility reference.
        eligibility_reference = f"daily_shop:{business_date}:{product_id}"
    else:
        if facts.business_date is not None:
            raise InvalidOfferFacts(
                "business_date is only valid for daily offer kinds"
            )
        business_date = None
        offer_version = version_base

    offer = NormalizedCoinShopOffer(
        offer_id=_offer_id(kind, product_id, version_base),
        offer_version=offer_version,
        product_id=product_id,
        item_id=item_id,
        quantity=quantity,
        currency=COINS,
        server_price=facts.server_price,
        destination=destination,
        acquisition_class=acquisition_class,
        duplicate_policy=duplicate_policy,
        eligibility_reference=eligibility_reference,
        price_reference=price_reference,
        catalog_reference=catalog_reference,
        offer_kind=kind,
        metadata={
            **metadata,
            **({"business_date": business_date} if business_date else {}),
        },
    )
    return ShopOfferAdaptation(status=READY, offer=offer, reason="normalized")


def normalize_shop_offer(
    facts: ServerCatalogFacts | Mapping[str, Any],
) -> NormalizedCoinShopOffer:
    """Return a ready offer or fail closed for a non-ready classification."""

    decision = adapt_shop_offer(facts)
    if decision.status != READY or decision.offer is None:
        raise OfferNotReady(
            decision.status,
            decision.reason,
            details={"blockers": list(decision.blockers)},
        )
    return decision.offer


def normalize_shop_offers(
    facts_iterable: Iterable[ServerCatalogFacts | Mapping[str, Any]],
) -> tuple[NormalizedCoinShopOffer, ...]:
    """Normalize a caller-owned batch and reject derived-ID collisions."""

    normalized: list[NormalizedCoinShopOffer] = []
    seen_ids: set[str] = set()
    for facts in facts_iterable:
        offer = normalize_shop_offer(facts)
        if offer.offer_id in seen_ids:
            raise InvalidOfferFacts(
                f"derived offer_id is duplicated: {offer.offer_id!r}",
                details={"offer_id": offer.offer_id},
            )
        seen_ids.add(offer.offer_id)
        normalized.append(offer)
    return tuple(normalized)


__all__ = [
    "ACTIVE",
    "ADAPTER_DESTINATIONS",
    "CANONICAL_ITEM_CLASSES",
    "COINS",
    "DUPLICATE_POLICIES",
    "InvalidOfferFacts",
    "ClientAuthoredInput",
    "NEEDS_DESTINATION_ADAPTER",
    "NEEDS_MULTI_GRANT_PROFILE",
    "NormalizedCoinShopOffer",
    "OFFER_KIND_DAILY_ITEM",
    "OFFER_KIND_DAILY_WARDROBE",
    "OFFER_KIND_FIXED_ITEM",
    "OFFER_KIND_FREE",
    "OFFER_KIND_WARDROBE",
    "OfferNotReady",
    "READY",
    "ServerCatalogFacts",
    "ShopOfferAdaptation",
    "ShopOfferAdapterError",
    "UnsupportedCoinOffer",
    "UnsupportedDuplicatePolicy",
    "UnknownDestination",
    "adapt_shop_offer",
    "normalize_shop_offer",
    "normalize_shop_offers",
]
