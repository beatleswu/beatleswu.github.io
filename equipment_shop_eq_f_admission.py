"""Price-gated plumbing for the six EQ-F Shop Equipment candidates.

C045 has not supplied authoritative prices, so this module intentionally
returns no active offers by default.  Once an explicit C045 price/reference
map is provided, it can project the candidates into the existing
``ServerShopOfferFacts`` shape consumed by C019/C043; it never spends Coins,
opens the catalog, or changes the current Shop V2 16-SKU release.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Any, Final

from equipment_portfolio_registry import EQ_F_SHOP_EQUIPMENT_IDS
from shop_offer_identity_projection import OFFER_FAMILY_STATIC_ITEM, ServerShopOfferFacts


EQ_F_SHOP_PRICE_AUTHORITY: Final[str] = "PENDING_C045"
EQ_F_SHOP_CATALOG_REFERENCE: Final[str] = "EQ_F_SHOP_CANDIDATES_V1"
EQ_F_SHOP_ELIGIBILITY_REFERENCE: Final[str] = "EQ_F_SHOP_C045_PENDING"


class EqFShopPriceAuthorityPending(ValueError):
    """The six candidates are known but have no authoritative prices yet."""

    code = "C045_PRICE_AUTHORITY_PENDING"


def admission_status() -> dict[str, Any]:
    """Return the non-mutating current admission fact for the six candidates."""

    return {
        "price_authority": EQ_F_SHOP_PRICE_AUTHORITY,
        "active": False,
        "offer_count": 0,
        "item_ids": list(EQ_F_SHOP_EQUIPMENT_IDS),
    }


def build_price_authorized_offer_facts(
    equipment_defs: Iterable[Mapping[str, Any]],
    *,
    accepted_prices: Mapping[str, Any] | None = None,
    price_references: Mapping[str, Any] | None = None,
) -> tuple[ServerShopOfferFacts, ...]:
    """Project exact C045 values into the existing server-facts contract."""

    if accepted_prices is None or price_references is None:
        raise EqFShopPriceAuthorityPending(
            "C045 final prices and price references are required before admission"
        )
    if set(accepted_prices) != set(EQ_F_SHOP_EQUIPMENT_IDS):
        raise ValueError("C045 must provide exactly the six EQ-F Shop prices")
    if set(price_references) != set(EQ_F_SHOP_EQUIPMENT_IDS):
        raise ValueError("C045 must provide exactly six EQ-F price references")

    definitions = {
        str(item.get("id")): item
        for item in tuple(equipment_defs)
    }
    facts: list[ServerShopOfferFacts] = []
    for item_id in EQ_F_SHOP_EQUIPMENT_IDS:
        definition = definitions.get(item_id)
        if definition is None:
            raise ValueError(f"missing canonical EQ-F Shop definition: {item_id}")
        price = accepted_prices[item_id]
        if isinstance(price, bool) or not isinstance(price, int) or price <= 0:
            raise ValueError(f"C045 price is invalid for {item_id}")
        reference = str(price_references[item_id] or "").strip()
        if not reference:
            raise ValueError(f"C045 price reference is missing for {item_id}")
        facts.append(
            ServerShopOfferFacts(
                offer_family=OFFER_FAMILY_STATIC_ITEM,
                item_key=item_id,
                item_id=item_id,
                server_price=price,
                quantity=1,
                destination="player_inventory",
                acquisition_class=str(definition.get("slot") or "").upper(),
                duplicate_policy="REJECT_IF_OWNED",
                eligibility_reference=EQ_F_SHOP_ELIGIBILITY_REFERENCE,
                price_reference=reference,
                catalog_reference=EQ_F_SHOP_CATALOG_REFERENCE,
                metadata=MappingProxyType(
                    {
                        "source_classification": "SHOP_EXCLUSIVE",
                        "price_authority": EQ_F_SHOP_PRICE_AUTHORITY,
                        "auto_equip": False,
                    }
                ),
            )
        )
    return tuple(facts)


__all__ = [
    "EQ_F_SHOP_CATALOG_REFERENCE",
    "EQ_F_SHOP_CANDIDATE_IDS",
    "EQ_F_SHOP_ELIGIBILITY_REFERENCE",
    "EQ_F_SHOP_PRICE_AUTHORITY",
    "EqFShopPriceAuthorityPending",
    "admission_status",
    "build_price_authorized_offer_facts",
]


# Public alias keeps the candidate list self-describing for release checks.
EQ_F_SHOP_CANDIDATE_IDS = EQ_F_SHOP_EQUIPMENT_IDS
