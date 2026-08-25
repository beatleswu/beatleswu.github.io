"""Focused tests for the C025 server-fact offer identity projection."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from shop_offer_identity_projection import (
    ClientAuthoredInput,
    GACHA_EXCLUDED,
    InvalidServerFacts,
    LEGACY_EFFECT_EXCLUDED,
    NEEDS_CATALOG_NORMALIZATION,
    NEEDS_DESTINATION_ADAPTER,
    NEEDS_FREE_GRANT_AUTHORITY,
    NEEDS_MULTI_GRANT_PROFILE,
    OfferNotReady,
    PREMIUM_CASH_SEPARATE,
    PREMIUM_ENTITLEMENT_SEPARATE,
    READY,
    UnknownDestination,
    UnsupportedDuplicatePolicy,
    normalize_shop_offer,
    project_shop_offer,
)


def server_facts(**overrides: object) -> dict[str, object]:
    facts: dict[str, object] = {
        "offer_family": "STATIC_SHOP_ITEM",
        "item_key": "hint_ticket",
        "item_id": "hint_ticket",
        "server_price": 30,
        "quantity": 1,
        "currency": "COINS",
        "destination": "shop_inventory",
        "acquisition_class": "CONSUMABLE",
        "duplicate_policy": "STACK",
        "eligibility_reference": "server:shop_items.hint_ticket",
        "price_reference": "server:shop_items.hint_ticket.price",
        "catalog_reference": "server:shop_items",
        "grant_profile": [
            {
                "item_id": "hint_ticket",
                "quantity": 1,
                "destination": "shop_inventory",
            }
        ],
    }
    facts.update(overrides)
    return facts


def assert_ready(facts: dict[str, object]):
    result = project_shop_offer(facts)
    assert result.status == READY
    assert result.offer is not None
    return result.offer


def test_static_identity_and_version_are_stable_for_same_server_facts() -> None:
    first = assert_ready(server_facts())
    second = assert_ready(server_facts())

    assert first.offer_id == "shop.static.hint_ticket"
    assert first.offer_id == second.offer_id
    assert first.offer_version == second.offer_version
    assert first.offer_version.startswith("v1-")


def test_static_price_change_keeps_identity_but_changes_version() -> None:
    first = assert_ready(server_facts())
    changed = assert_ready(server_facts(server_price=31))

    assert changed.offer_id == first.offer_id
    assert changed.offer_version != first.offer_version


def test_material_grant_semantics_change_version() -> None:
    first = assert_ready(server_facts())
    changed = assert_ready(
        server_facts(
            quantity=2,
            grant_profile=[
                {
                    "item_id": "hint_ticket",
                    "quantity": 2,
                    "destination": "shop_inventory.v2",
                }
            ],
        )
    )

    assert changed.offer_id == first.offer_id
    assert changed.offer_version != first.offer_version


def test_daily_version_contains_date_and_identity_is_business_stable() -> None:
    first = assert_ready(
        server_facts(
            offer_family="DAILY_SHOP_ITEM",
            shop_date="2026-08-25",
        )
    )
    same_day = assert_ready(
        server_facts(
            offer_family="DAILY_SHOP_ITEM",
            shop_date="2026-08-25",
        )
    )
    next_day = assert_ready(
        server_facts(
            offer_family="DAILY_SHOP_ITEM",
            shop_date="2026-08-26",
        )
    )

    assert first.offer_id == "shop.static.hint_ticket"
    assert first.offer_id == next_day.offer_id
    assert first.offer_version == same_day.offer_version
    assert first.offer_version.startswith("v1-2026-08-25-")
    assert next_day.offer_version.startswith("v1-2026-08-26-")
    assert first.offer_version != next_day.offer_version


def test_explicit_coin_cosmetic_uses_product_identity() -> None:
    offer = assert_ready(
        server_facts(
            offer_family="EXPLICIT_COIN_COSMETIC",
            item_key=None,
            item_id="robe_plain",
            product_id="cosmetic.robe_plain",
            server_price=120,
            destination="player_wardrobe",
            acquisition_class="COSMETIC",
            duplicate_policy="REJECT_IF_OWNED",
            grant_profile=[
                {
                    "item_id": "robe_plain",
                    "quantity": 1,
                    "destination": "player_wardrobe",
                }
            ],
        )
    )

    assert offer.offer_id == "shop.cosmetic.cosmetic.robe_plain"
    assert offer.destination == "player_wardrobe"
    assert offer.acquisition_class == "COSMETIC"
    assert offer.duplicate_policy == "REJECT_IF_OWNED"


def test_client_price_and_identity_fields_are_rejected() -> None:
    with pytest.raises(ClientAuthoredInput):
        project_shop_offer({**server_facts(), "price": 1})
    with pytest.raises(ClientAuthoredInput):
        project_shop_offer({**server_facts(), "client_price": 1})
    with pytest.raises(ClientAuthoredInput):
        project_shop_offer({**server_facts(), "offer_id": "client.offer"})
    with pytest.raises(ClientAuthoredInput):
        project_shop_offer({**server_facts(), "purchase_operation_id": "op-1"})


@pytest.mark.parametrize("price", [True, False, 1.5, -1, None])
def test_invalid_server_price_is_rejected(price: object) -> None:
    with pytest.raises(InvalidServerFacts):
        project_shop_offer(server_facts(server_price=price))


def test_zero_price_is_not_a_c019_offer_even_when_free_is_approved() -> None:
    result = project_shop_offer(
        server_facts(
            offer_family="FREE_OFFER",
            server_price=0,
            free=True,
        )
    )

    assert result.status == NEEDS_FREE_GRANT_AUTHORITY
    with pytest.raises(OfferNotReady) as error:
        normalize_shop_offer(
            server_facts(
                offer_family="FREE_OFFER",
                server_price=0,
                free=True,
            )
        )
    assert error.value.status == NEEDS_FREE_GRANT_AUTHORITY


def test_premium_cash_and_entitlement_are_outside_coin_path() -> None:
    cash = project_shop_offer(
        server_facts(
            offer_family="PREMIUM_CASH",
            item_id=None,
            currency="TWD",
            server_price=299,
            premium_cash=True,
        )
    )
    entitlement = project_shop_offer(
        server_facts(
            offer_family="PREMIUM_ENTITLEMENT",
            item_id="robe_premium",
            premium_entitlement=True,
        )
    )

    assert cash.status == PREMIUM_CASH_SEPARATE
    assert entitlement.status == PREMIUM_ENTITLEMENT_SEPARATE


def test_gacha_legacy_effect_and_locked_identities_fail_closed() -> None:
    gacha = project_shop_offer(
        server_facts(
            offer_family="GACHA",
            item_id=None,
            gacha=True,
        )
    )
    legacy = project_shop_offer(
        server_facts(
            offer_family="DAILY_MAPPED_COSMETIC",
            item_id="aura_green",
            product_id="aura_green",
            destination="player_wardrobe",
            acquisition_class="COSMETIC",
            duplicate_policy="REJECT_IF_OWNED",
            legacy_effect=True,
        )
    )
    xp_amulet = project_shop_offer(
        server_facts(item_id="xp_amulet", item_key="xp_amulet")
    )
    go_stone = project_shop_offer(
        server_facts(
            item_id="go_stone_black",
            item_key="go_stone_black",
            acquisition_class="TROPHY",
        )
    )

    assert gacha.status == GACHA_EXCLUDED
    assert legacy.status == LEGACY_EFFECT_EXCLUDED
    assert xp_amulet.status == "AUTHORITY_HOLD"
    assert go_stone.status == "TROPHY_INVENTORY_ONLY"


def test_pet_destination_remains_an_explicit_adapter_blocker() -> None:
    result = project_shop_offer(
        server_facts(
            destination="pet_inventory",
            grant_profile=[
                {
                    "item_id": "go_spirit_candy",
                    "quantity": 1,
                    "destination": "pet_inventory",
                }
            ],
            item_id="go_spirit_candy",
            item_key="go_spirit_candy",
            acquisition_class="SPIRIT_CONSUMABLE",
        )
    )

    assert result.status == NEEDS_DESTINATION_ADAPTER
    assert NEEDS_DESTINATION_ADAPTER in result.blockers


def test_multi_grant_is_not_flattened() -> None:
    result = project_shop_offer(
        server_facts(
            item_id="starter_bundle",
            item_key="starter_bundle",
            grant_profile=[
                {"item_id": "hint_ticket", "quantity": 1},
                {"item_id": "starfruit", "quantity": 1},
            ],
        )
    )

    assert result.status == NEEDS_MULTI_GRANT_PROFILE
    assert result.offer is None


def test_unmapped_daily_cosmetic_requires_catalog_normalization() -> None:
    result = project_shop_offer(
        server_facts(
            offer_family="DAILY_MAPPED_COSMETIC",
            item_id="daily.fallback.robe",
            product_id=None,
            destination="player_wardrobe",
            acquisition_class="COSMETIC",
            duplicate_policy="REJECT_IF_OWNED",
            shop_date="2026-08-25",
            grant_profile=[
                {
                    "item_id": "daily.fallback.robe",
                    "quantity": 1,
                    "destination": "player_wardrobe",
                }
            ],
        )
    )

    assert result.status == NEEDS_CATALOG_NORMALIZATION


def test_unknown_destination_and_duplicate_policy_fail_closed() -> None:
    with pytest.raises(UnknownDestination):
        project_shop_offer(server_facts(destination="mystery_inventory"))
    with pytest.raises(UnsupportedDuplicatePolicy):
        project_shop_offer(server_facts(duplicate_policy="CONVERT_TO_COINS"))


def test_ready_mapping_has_the_accepted_c019_shape_and_no_operation_id() -> None:
    offer = normalize_shop_offer(server_facts())
    mapping = offer.as_c019_mapping()

    assert mapping["offer_id"] == offer.offer_id
    assert mapping["offer_version"] == offer.offer_version
    assert mapping["currency_type"] == "COINS"
    assert mapping["price"] == 30
    assert mapping["server_price"] == 30
    assert mapping["status"] == "ACTIVE"
    assert "purchase_operation_id" not in mapping


def test_current_c024_shape_counts_are_representable_without_a_catalog_copy() -> None:
    results = []
    for index in range(12):
        results.append(
            project_shop_offer(
                server_facts(
                    item_key=f"ready.item.{index}",
                    item_id=f"ready.item.{index}",
                    server_price=10 + index,
                    grant_profile=[
                        {
                            "item_id": f"ready.item.{index}",
                            "quantity": 1,
                            "destination": "shop_inventory",
                        }
                    ],
                )
            )
        )
    for product_id in ("cosmetic.robe_plain", "cosmetic.robe_bamboo"):
        item_id = product_id.removeprefix("cosmetic.")
        results.append(
            project_shop_offer(
                server_facts(
                    offer_family="EXPLICIT_COIN_COSMETIC",
                    item_key=None,
                    item_id=item_id,
                    product_id=product_id,
                    server_price=120,
                    destination="player_wardrobe",
                    acquisition_class="COSMETIC",
                    duplicate_policy="REJECT_IF_OWNED",
                    grant_profile=[
                        {
                            "item_id": item_id,
                            "quantity": 1,
                            "destination": "player_wardrobe",
                        }
                    ],
                )
            )
        )
    for index in range(4):
        results.append(
            project_shop_offer(
                server_facts(
                    item_key=f"pet.item.{index}",
                    item_id=f"pet.item.{index}",
                    destination="pet_inventory",
                    duplicate_policy="NEEDS_PROFILE",
                )
            )
        )
    for index in range(3):
        results.append(
            project_shop_offer(
                server_facts(
                    item_key=f"bundle.{index}",
                    item_id=f"bundle.{index}",
                    acquisition_class="TREASURE_BUNDLE",
                    duplicate_policy="NEEDS_PROFILE",
                    grant_profile=[
                        {"item_id": f"bundle.{index}.a", "quantity": 5},
                    ],
                )
            )
        )
    for index in range(2):
        results.append(
            project_shop_offer(
                server_facts(
                    item_key=f"multi.bundle.{index}",
                    item_id=f"multi.bundle.{index}",
                    destination="MULTI_GRANT_PROFILE",
                    acquisition_class="TREASURE_BUNDLE",
                    duplicate_policy="NEEDS_PROFILE",
                    grant_profile=[
                        {"item_id": f"multi.bundle.{index}.a", "quantity": 4},
                        {"item_id": f"multi.bundle.{index}.b", "quantity": 2},
                    ],
                )
            )
        )
    for index in range(16):
        results.append(
            project_shop_offer(
                server_facts(
                    offer_family="DAILY_MAPPED_COSMETIC",
                    item_key=None,
                    item_id=f"daily.fallback.{index}",
                    product_id=None,
                    destination="player_wardrobe",
                    acquisition_class="COSMETIC",
                    duplicate_policy="UNKNOWN",
                    shop_date="2026-08-25",
                    grant_profile=[
                        {
                            "item_id": f"daily.fallback.{index}",
                            "quantity": 1,
                            "destination": "player_wardrobe",
                        }
                    ],
                )
            )
        )
    for index in range(4):
        results.append(
            project_shop_offer(
                server_facts(
                    offer_family="DAILY_MAPPED_COSMETIC",
                    item_key=None,
                    item_id=f"legacy.effect.{index}",
                    product_id=f"legacy.effect.{index}",
                    destination="player_wardrobe",
                    acquisition_class="COSMETIC",
                    duplicate_policy="REJECT_IF_OWNED",
                    legacy_effect=True,
                    shop_date="2026-08-25",
                )
            )
        )

    statuses = [result.status for result in results]
    assert statuses.count(READY) == 14
    assert statuses.count(NEEDS_DESTINATION_ADAPTER) == 4
    assert statuses.count(NEEDS_MULTI_GRANT_PROFILE) == 5
    assert statuses.count(NEEDS_CATALOG_NORMALIZATION) == 16
    assert statuses.count(LEGACY_EFFECT_EXCLUDED) == 4


def test_module_has_no_copied_catalog_or_mutation_authority() -> None:
    source = Path(__file__).resolve().parents[1] / "shop_offer_identity_projection.py"
    text = source.read_text(encoding="utf-8")
    copied_registry = re.compile(
        r"^\s*(SHOP_ITEMS|APPEARANCE_DEFS|COSMETIC_COMMERCE_PRODUCTS|"
        r"PET_FOOD_CATALOG|PAY_PLANS|GACHA_POOLS)\s*=",
        re.MULTILINE,
    )

    assert copied_registry.search(text) is None
    assert "import app" not in text
    assert "from app" not in text
    assert "purchase_with_coins" not in text
    assert "_spend_coins" not in text
    assert "sqlite3" not in text
    assert ".execute(" not in text


def test_projection_does_not_create_database_or_purchase_side_effects() -> None:
    offer = normalize_shop_offer(server_facts())

    assert offer.offer_id != "purchase_operation_id"
    assert not hasattr(offer, "purchase_operation_id")
    assert not hasattr(offer, "ownership_reference")
