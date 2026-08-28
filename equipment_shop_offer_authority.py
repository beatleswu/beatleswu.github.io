"""C046 server-owned Coins offers for the approved Equipment starter set.

The canonical Equipment definitions remain the caller-supplied server
registry.  This module owns only the Owner-approved Shop offer projection:
three static Coins offers, their stable price references, and the existing
C025/C029 -> C019 compatibility adapter.  It does not import ``app.py``,
write player state, spend Coins, or enable either player-facing feature.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Any

from equipment_shop_starter_catalog import (
    RECOMMENDED_STARTER_ASSORTMENT_IDS,
    StarterCatalogContractError,
    build_authoritative_starter_offer_facts,
    build_equipment_acquisition_audit,
)
from shop_offer_authority import CoinShopOffer, StaticShopOfferAuthority
from shop_offer_identity_projection import (
    ServerShopOfferFacts,
    normalize_shop_offer,
)


PRICE_AUTHORITY_SOURCE = "OWNER_EQUIPMENT_SHOP_PRICING_DECISION_001"

OWNER_APPROVED_STARTER_PRICES: Mapping[str, int] = MappingProxyType(
    {
        "wooden_sword": 300,
        "cloth_robe": 300,
        "lucky_stone": 400,
    }
)
OWNER_APPROVED_STARTER_PRICE_REFERENCES: Mapping[str, str] = MappingProxyType(
    {
        item_id: f"{PRICE_AUTHORITY_SOURCE}:{item_id}"
        for item_id in RECOMMENDED_STARTER_ASSORTMENT_IDS
    }
)

EQUIPMENT_OFFERS_SOURCE_IMPLEMENTED = True
ALL_OFFER_PRICES_AUTHORITATIVE = True
FRONTEND_OFFER_DUPLICATION = False
AUTO_EQUIP_AFTER_PURCHASE = False
SHOP_ENABLED = False
LOADOUT_ENABLED = False

_EXPECTED_SLOTS = {
    "wooden_sword": "weapon",
    "cloth_robe": "armor",
    "lucky_stone": "accessory",
}


class EquipmentOfferContractError(ValueError):
    """The canonical Equipment source cannot support the offer projection."""


def _validated_definitions(
    equipment_defs: Iterable[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    try:
        definitions = tuple(equipment_defs)
    except TypeError as exc:
        raise EquipmentOfferContractError(
            "canonical Equipment definitions are required"
        ) from exc

    try:
        build_equipment_acquisition_audit(definitions)
    except StarterCatalogContractError as exc:
        raise EquipmentOfferContractError(
            "canonical Equipment definitions are invalid"
        ) from exc

    by_id = {str(definition.get("id")): definition for definition in definitions}
    for item_id, expected_slot in _EXPECTED_SLOTS.items():
        definition = by_id.get(item_id)
        if definition is None or definition.get("slot") != expected_slot:
            raise EquipmentOfferContractError(
                f"{item_id} does not have its canonical {expected_slot} slot"
            )
    return definitions


def build_authoritative_equipment_offer_facts(
    equipment_defs: Iterable[Mapping[str, Any]],
) -> tuple[ServerShopOfferFacts, ...]:
    """Return exactly the three Owner-approved server offer facts."""

    definitions = _validated_definitions(equipment_defs)
    facts = build_authoritative_starter_offer_facts(
        definitions,
        accepted_prices=OWNER_APPROVED_STARTER_PRICES,
        price_references=OWNER_APPROVED_STARTER_PRICE_REFERENCES,
    )
    expected_ids = tuple(RECOMMENDED_STARTER_ASSORTMENT_IDS)
    if tuple(fact.item_id for fact in facts) != expected_ids:
        raise EquipmentOfferContractError(
            "authoritative Equipment offer ids do not match the approved set"
        )
    if tuple(fact.server_price for fact in facts) != tuple(
        OWNER_APPROVED_STARTER_PRICES[item_id] for item_id in expected_ids
    ):
        raise EquipmentOfferContractError(
            "authoritative Equipment offer prices do not match Owner authority"
        )
    return facts


def build_authoritative_equipment_offers(
    equipment_defs: Iterable[Mapping[str, Any]],
) -> tuple[CoinShopOffer, ...]:
    """Normalize the facts into the existing C019 purchase contract."""

    offers: list[CoinShopOffer] = []
    for facts in build_authoritative_equipment_offer_facts(equipment_defs):
        normalized = normalize_shop_offer(facts)
        offers.append(CoinShopOffer.from_mapping(normalized.as_c019_mapping()))
    return tuple(offers)


def build_authoritative_equipment_offer_authority(
    equipment_defs: Iterable[Mapping[str, Any]],
) -> StaticShopOfferAuthority:
    """Return the C019 resolver backed by the canonical three-offer catalog."""

    return StaticShopOfferAuthority(build_authoritative_equipment_offers(equipment_defs))


__all__ = [
    "ALL_OFFER_PRICES_AUTHORITATIVE",
    "AUTO_EQUIP_AFTER_PURCHASE",
    "EQUIPMENT_OFFERS_SOURCE_IMPLEMENTED",
    "EquipmentOfferContractError",
    "FRONTEND_OFFER_DUPLICATION",
    "LOADOUT_ENABLED",
    "OWNER_APPROVED_STARTER_PRICE_REFERENCES",
    "OWNER_APPROVED_STARTER_PRICES",
    "PRICE_AUTHORITY_SOURCE",
    "SHOP_ENABLED",
    "build_authoritative_equipment_offer_authority",
    "build_authoritative_equipment_offer_facts",
    "build_authoritative_equipment_offers",
]
