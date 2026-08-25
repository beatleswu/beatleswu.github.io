from __future__ import annotations

import pytest

from shop_offer_adapter import (
    NEEDS_DESTINATION_ADAPTER,
    NEEDS_MULTI_GRANT_PROFILE,
    READY,
    ClientAuthoredInput,
    InvalidOfferFacts,
    OfferNotReady,
    UnsupportedCoinOffer,
    UnsupportedDuplicatePolicy,
    UnknownDestination,
    adapt_shop_offer,
    normalize_shop_offer,
    normalize_shop_offers,
)


def _facts(**overrides):
    facts = {
        "product_id": "hint_ticket",
        "item_id": "hint_ticket",
        "quantity": 1,
        "currency": "COINS",
        "server_price": 30,
        "destination": "shop_inventory",
        "acquisition_class": "CONSUMABLE",
        "duplicate_policy": "STACK",
        "eligibility_reference": "SHOP_ITEMS:hint_ticket:active",
        "price_reference": "app.py:SHOP_ITEMS.hint_ticket.price",
        "catalog_reference": "app.py:SHOP_ITEMS",
        "offer_kind": "FIXED_ITEM",
        "offer_version": "v1",
        "metadata": {"presentation_key": "hint_ticket"},
    }
    facts.update(overrides)
    return facts


def test_fixed_coin_offer_normalizes_to_c019_compatible_shape():
    offer = normalize_shop_offer(_facts())

    assert offer.offer_id == "shop.item.hint_ticket.v1"
    assert offer.offer_version == "v1"
    assert offer.product_id == "hint_ticket"
    assert offer.item_id == "hint_ticket"
    assert offer.quantity == 1
    assert offer.currency == "COINS"
    assert offer.server_price == 30
    assert offer.destination == "shop_inventory"
    assert offer.acquisition_class == "CONSUMABLE"
    assert offer.duplicate_policy == "STACK"
    assert offer.as_c019_mapping() == {
        "offer_id": "shop.item.hint_ticket.v1",
        "item_id": "hint_ticket",
        "quantity": 1,
        "currency_type": "COINS",
        "price": 30,
        "destination": "shop_inventory",
        "acquisition_class": "CONSUMABLE",
        "offer_type": "FIXED_ITEM",
        "offer_version": "v1",
        "status": "ACTIVE",
        "duplicate_policy": "STACK",
        "eligibility_metadata": {
            "reference": "SHOP_ITEMS:hint_ticket:active",
            "catalog_reference": "app.py:SHOP_ITEMS",
        },
        "presentation_metadata": {
            "presentation_key": "hint_ticket",
            "product_id": "hint_ticket",
            "price_reference": "app.py:SHOP_ITEMS.hint_ticket.price",
            "catalog_reference": "app.py:SHOP_ITEMS",
        },
        "product_id": "hint_ticket",
        "server_price": 30,
        "price_reference": "app.py:SHOP_ITEMS.hint_ticket.price",
        "catalog_reference": "app.py:SHOP_ITEMS",
    }


def test_daily_discount_uses_server_price_and_date_bound_version():
    offer = normalize_shop_offer(
        _facts(
            product_id="extra_questions",
            item_id="extra_questions",
            server_price=80,
            offer_kind="DAILY_ITEM",
            business_date="2026-08-25",
            eligibility_reference="client-cannot-override-this",
            price_reference="app.py:_daily_shop_slots:extra_questions:2026-08-25",
        )
    )

    assert offer.offer_id == "shop.daily.item.extra_questions.v1"
    assert offer.offer_version == "v1@2026-08-25"
    assert offer.eligibility_reference == "daily_shop:2026-08-25:extra_questions"
    assert offer.server_price == 80
    assert offer.metadata["business_date"] == "2026-08-25"

    next_day = normalize_shop_offer(
        _facts(
            product_id="extra_questions",
            item_id="extra_questions",
            server_price=90,
            offer_kind="DAILY_ITEM",
            business_date="2026-08-26",
            price_reference="app.py:_daily_shop_slots:extra_questions:2026-08-26",
        )
    )
    assert next_day.offer_id == offer.offer_id
    assert next_day.offer_version == "v1@2026-08-26"
    assert next_day.offer_version != offer.offer_version


def test_wardrobe_offer_uses_player_wardrobe_and_rejects_gameplay_power():
    offer = normalize_shop_offer(
        _facts(
            product_id="cosmetic.outfit.robe_plain",
            item_id="robe_plain",
            server_price=200,
            destination="player_wardrobe",
            acquisition_class="COSMETIC",
            duplicate_policy="REJECT_IF_OWNED",
            offer_kind="WARDROBE",
            eligibility_reference="COSMETIC_COMMERCE_PRODUCTS:robe_plain",
            price_reference="app.py:COSMETIC_COMMERCE_PRODUCTS.robe_plain.price",
        )
    )

    assert offer.offer_id == "shop.cosmetic.cosmetic.outfit.robe_plain.v1"
    assert offer.destination == "player_wardrobe"
    assert offer.acquisition_class == "COSMETIC"
    assert offer.duplicate_policy == "REJECT_IF_OWNED"

    with pytest.raises(UnsupportedCoinOffer):
        normalize_shop_offer(
            _facts(
                product_id="cosmetic.outfit.powerful",
                item_id="powerful",
                destination="player_wardrobe",
                acquisition_class="COSMETIC",
                offer_kind="WARDROBE",
                metadata={"gameplay_effect": True},
            )
        )


def test_same_server_facts_produce_same_normalized_output():
    facts = _facts()
    assert normalize_shop_offer(facts) == normalize_shop_offer(dict(facts))
    assert normalize_shop_offer(facts).as_dict() == normalize_shop_offer(facts).as_dict()


def test_client_price_and_offer_id_are_rejected():
    with pytest.raises(ClientAuthoredInput) as price_error:
        normalize_shop_offer(_facts(price=1))
    assert price_error.value.code == "CLIENT_AUTHORED_INPUT"

    with pytest.raises(ClientAuthoredInput) as offer_id_error:
        normalize_shop_offer(_facts(offer_id="shop.item.forged.v1"))
    assert offer_id_error.value.code == "CLIENT_AUTHORED_INPUT"


def test_premium_cash_is_not_a_c019_coin_offer():
    with pytest.raises(UnsupportedCoinOffer) as exc_info:
        normalize_shop_offer(
            _facts(
                product_id="premium.monthly",
                item_id="premium",
                currency="USD",
                server_price=9,
                destination="entitlement",
                acquisition_class="COSMETIC",
                offer_kind="PREMIUM_CASH_SUBSCRIPTION",
            )
        )
    assert "outside C019" in str(exc_info.value)


def test_robe_premium_is_rejected_from_coin_path():
    with pytest.raises(UnsupportedCoinOffer) as exc_info:
        normalize_shop_offer(
            _facts(
                product_id="cosmetic.outfit.robe_premium",
                item_id="robe_premium",
                destination="player_wardrobe",
                acquisition_class="COSMETIC",
                duplicate_policy="REJECT_IF_OWNED",
                offer_kind="WARDROBE",
            )
        )
    assert "Premium entitlement" in str(exc_info.value)


def test_gacha_is_rejected_even_when_coin_priced():
    with pytest.raises(UnsupportedCoinOffer) as exc_info:
        normalize_shop_offer(
            _facts(
                product_id="gacha.draw",
                item_id="random_reward",
                server_price=150,
                offer_kind="GACHA",
                random_reward=True,
            )
        )
    assert "random/gacha" in str(exc_info.value)


def test_legacy_effect_cosmetic_is_rejected_from_pure_coin_path():
    with pytest.raises(UnsupportedCoinOffer) as exc_info:
        normalize_shop_offer(
            _facts(
                product_id="daily.aura_green",
                item_id="aura_green",
                destination="player_wardrobe",
                acquisition_class="COSMETIC",
                duplicate_policy="REJECT_IF_OWNED",
                offer_kind="DAILY_WARDROBE",
                business_date="2026-08-25",
                legacy_effect=True,
            )
        )
    assert "legacy effect-bearing" in str(exc_info.value)


def test_pet_inventory_is_classified_as_destination_adapter_needed():
    decision = adapt_shop_offer(
        _facts(
            product_id="pet_snack",
            item_id="go_spirit_candy",
            quantity=3,
            destination="pet_inventory",
            acquisition_class="SPIRIT_CONSUMABLE",
            price_reference="app.py:SHOP_ITEMS.pet_snack.price",
        )
    )

    assert decision.status == NEEDS_DESTINATION_ADAPTER
    assert decision.offer is None
    assert decision.blockers == (NEEDS_DESTINATION_ADAPTER,)
    with pytest.raises(OfferNotReady):
        normalize_shop_offer(
            _facts(
                product_id="pet_snack",
                item_id="go_spirit_candy",
                quantity=3,
                destination="pet_inventory",
                acquisition_class="SPIRIT_CONSUMABLE",
            )
        )


def test_multi_grant_is_not_flattened_into_a_fake_item():
    decision = adapt_shop_offer(
        _facts(
            product_id="collector_archive_crate",
            item_id="",
            quantity=1,
            server_price=3200,
            acquisition_class="MATERIAL",
            grants={
                "rare_appearance_fragment": 4,
                "ai_explain_ticket": 8,
            },
        )
    )

    assert decision.status == NEEDS_MULTI_GRANT_PROFILE
    assert decision.offer is None
    assert decision.blockers == (NEEDS_MULTI_GRANT_PROFILE,)
    with pytest.raises(OfferNotReady):
        normalize_shop_offer(
            _facts(
                product_id="collector_archive_crate",
                item_id="",
                quantity=1,
                server_price=3200,
                acquisition_class="MATERIAL",
                grants={
                    "rare_appearance_fragment": 4,
                    "ai_explain_ticket": 8,
                },
            )
        )


def test_pet_multi_grant_reports_both_unresolved_blockers():
    decision = adapt_shop_offer(
        _facts(
            product_id="pet_feast_box",
            item_id="",
            quantity=1,
            server_price=230,
            destination="pet_inventory",
            acquisition_class="SPIRIT_CONSUMABLE",
            grants={"go_spirit_candy": 3, "starfruit": 2, "moon_drop": 1},
        )
    )
    assert decision.status == NEEDS_DESTINATION_ADAPTER
    assert decision.blockers == (
        NEEDS_DESTINATION_ADAPTER,
        NEEDS_MULTI_GRANT_PROFILE,
    )


def test_unknown_destination_fails_closed():
    with pytest.raises(UnknownDestination) as exc_info:
        normalize_shop_offer(_facts(destination="mystery_store"))
    assert exc_info.value.code == "UNKNOWN_DESTINATION"


def test_unknown_duplicate_policy_fails_closed():
    with pytest.raises(UnsupportedDuplicatePolicy) as exc_info:
        normalize_shop_offer(_facts(duplicate_policy="CONVERT_TO_COINS"))
    assert exc_info.value.code == "UNKNOWN_DUPLICATE_POLICY"


@pytest.mark.parametrize(
    ("server_price", "expected_type"),
    [
        (-1, InvalidOfferFacts),
        (1.5, InvalidOfferFacts),
        (True, InvalidOfferFacts),
        (None, InvalidOfferFacts),
        (0, InvalidOfferFacts),
    ],
)
def test_invalid_server_price_fails_closed(server_price, expected_type):
    with pytest.raises(expected_type):
        normalize_shop_offer(_facts(server_price=server_price))


def test_zero_price_free_offer_is_rejected_from_c019():
    with pytest.raises(UnsupportedCoinOffer) as exc_info:
        normalize_shop_offer(
            _facts(
                product_id="free.training_pass",
                item_id="training_pass",
                server_price=0,
                offer_kind="FREE_OFFER",
                metadata={"free_offer_approved": True},
            )
        )
    assert "separate free-grant authority" in str(exc_info.value)
    assert exc_info.value.details["status"] == "NEEDS_FREE_GRANT_AUTHORITY"


def test_ready_offer_mapping_keeps_c019_positive_price_contract():
    ready_offers = [
        normalize_shop_offer(_facts()),
        normalize_shop_offer(
            _facts(
                product_id="extra_questions",
                item_id="extra_questions",
                server_price=80,
                offer_kind="DAILY_ITEM",
                business_date="2026-08-25",
            )
        ),
        normalize_shop_offer(
            _facts(
                product_id="cosmetic.outfit.robe_plain",
                item_id="robe_plain",
                server_price=200,
                destination="player_wardrobe",
                acquisition_class="COSMETIC",
                duplicate_policy="REJECT_IF_OWNED",
                offer_kind="WARDROBE",
            )
        ),
    ]
    for offer in ready_offers:
        c019 = offer.as_c019_mapping()
        assert c019["currency_type"] == "COINS"
        assert isinstance(c019["price"], int)
        assert not isinstance(c019["price"], bool)
        assert c019["price"] > 0


def test_single_grant_must_match_normalized_item_and_quantity():
    offer = normalize_shop_offer(
        _facts(
            product_id="ai_analysis_pack",
            item_id="ai_explain_ticket",
            quantity=5,
            server_price=860,
            grants=[{"item_id": "ai_explain_ticket", "quantity": 5}],
        )
    )
    assert offer.item_id == "ai_explain_ticket"
    assert offer.quantity == 5

    with pytest.raises(InvalidOfferFacts):
        normalize_shop_offer(
            _facts(
                product_id="ai_analysis_pack",
                item_id="ai_explain_ticket",
                quantity=1,
                server_price=860,
                grants=[{"item_id": "ai_explain_ticket", "quantity": 5}],
            )
        )


def test_batch_normalization_rejects_derived_id_collision():
    with pytest.raises(InvalidOfferFacts) as exc_info:
        normalize_shop_offers([_facts(), _facts()])
    assert "derived offer_id is duplicated" in str(exc_info.value)
