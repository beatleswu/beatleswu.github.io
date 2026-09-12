"""C045-authorized Shop admission for the six EQ-F Equipment products.

This module consumes the exact accepted C045 artifact and projects its six
server-owned prices into the existing ``ServerShopOfferFacts`` contract.  It
does not spend Coins, own player state, or contain HTTP behavior.  The caller
still owns the existing C019 transaction and the C043 ownership adapter.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Any, Final

from equipment_portfolio_registry import EQ_F_SHOP_EQUIPMENT_IDS
from shop_offer_identity_projection import OFFER_FAMILY_STATIC_ITEM, ServerShopOfferFacts


C045_AUTHORITY_COMMIT: Final[str] = (
    "a6d413e83c88bc2495eeaf06d339cfa77abd128a"
)
C045_AUTHORITY_TREE: Final[str] = (
    "65e20152a2d56e668494aa4ed34901f14d834f32"
)
C045_AUTHORITY_DOCUMENT: Final[str] = (
    "docs/planning/c045_new_shop_equipment_final_coin_price_authority_001.md"
)
C045_AUTHORITY_CONTRACT_ID: Final[str] = (
    "GO_ODYSSEY_C045_NEW_SHOP_EQUIPMENT_FINAL_COIN_PRICE_AUTHORITY_001"
)
C045_PRICE_AUTHORITY_SOURCE: Final[str] = C045_AUTHORITY_CONTRACT_ID

C045_FINAL_COIN_PRICES: Final[Mapping[str, int]] = MappingProxyType(
    {
        "emberline_cutlass": 700,
        "starglass_needle": 1000,
        "weaveguard_vest": 650,
        "mirrorfall_mantle": 950,
        "copper_jade_talisman": 600,
        "prism_focus_charm": 900,
    }
)
C045_PRICE_REFERENCES: Final[Mapping[str, str]] = MappingProxyType(
    {
        item_id: f"{C045_PRICE_AUTHORITY_SOURCE}:{item_id}"
        for item_id in EQ_F_SHOP_EQUIPMENT_IDS
    }
)

EQ_F_SHOP_PRICE_AUTHORITY: Final[str] = "LOCKED_C045"
EQ_F_SHOP_CATALOG_REFERENCE: Final[str] = "EQ_F_SHOP_C045_V1"
EQ_F_SHOP_ELIGIBILITY_REFERENCE: Final[str] = (
    "C045:FINAL_COIN_PRICE_AUTHORITY_LOCKED"
)


class EqFShopPriceAuthorityPending(ValueError):
    """Compatibility error for callers that still require unresolved pricing."""

    code = "C045_PRICE_AUTHORITY_PENDING"


def admission_status() -> dict[str, Any]:
    """Return the non-mutating current admission fact for the six candidates."""

    return {
        "price_authority": EQ_F_SHOP_PRICE_AUTHORITY,
        "authority_commit": C045_AUTHORITY_COMMIT,
        "authority_tree": C045_AUTHORITY_TREE,
        "authority_document": C045_AUTHORITY_DOCUMENT,
        "active": True,
        "offer_count": len(EQ_F_SHOP_EQUIPMENT_IDS),
        "item_ids": list(EQ_F_SHOP_EQUIPMENT_IDS),
        "prices": dict(C045_FINAL_COIN_PRICES),
    }


def _locked_c045_mappings(
    accepted_prices: Mapping[str, Any] | None,
    price_references: Mapping[str, Any] | None,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Require any explicit inputs to be byte-for-byte equivalent authority."""

    prices = C045_FINAL_COIN_PRICES if accepted_prices is None else accepted_prices
    references = C045_PRICE_REFERENCES if price_references is None else price_references
    if dict(prices) != dict(C045_FINAL_COIN_PRICES):
        raise ValueError("C045 prices do not match the accepted authority")
    if dict(references) != dict(C045_PRICE_REFERENCES):
        raise ValueError("C045 price references do not match the accepted authority")
    return prices, references


def build_price_authorized_offer_facts(
    equipment_defs: Iterable[Mapping[str, Any]],
    *,
    accepted_prices: Mapping[str, Any] | None = None,
    price_references: Mapping[str, Any] | None = None,
) -> tuple[ServerShopOfferFacts, ...]:
    """Project the exact accepted C045 values into server Shop facts."""

    accepted_prices, price_references = _locked_c045_mappings(
        accepted_prices,
        price_references,
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


def build_authoritative_eq_f_shop_offer_facts(
    equipment_defs: Iterable[Mapping[str, Any]],
) -> tuple[ServerShopOfferFacts, ...]:
    """Return the active six-offer C045 projection for the Shop resolver."""

    return build_price_authorized_offer_facts(equipment_defs)


__all__ = [
    "C045_AUTHORITY_COMMIT",
    "C045_AUTHORITY_CONTRACT_ID",
    "C045_AUTHORITY_DOCUMENT",
    "C045_AUTHORITY_TREE",
    "C045_FINAL_COIN_PRICES",
    "C045_PRICE_AUTHORITY_SOURCE",
    "C045_PRICE_REFERENCES",
    "EQ_F_SHOP_CATALOG_REFERENCE",
    "EQ_F_SHOP_CANDIDATE_IDS",
    "EQ_F_SHOP_ELIGIBILITY_REFERENCE",
    "EQ_F_SHOP_PRICE_AUTHORITY",
    "EqFShopPriceAuthorityPending",
    "admission_status",
    "build_authoritative_eq_f_shop_offer_facts",
    "build_price_authorized_offer_facts",
]


# Public alias keeps the candidate list self-describing for release checks.
EQ_F_SHOP_CANDIDATE_IDS = EQ_F_SHOP_EQUIPMENT_IDS
