"""C045 evidence, pricing-boundary, and C044/C043 shape contracts."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from equipment_shop_starter_catalog import (
    C045_FUNCTIONAL_EQUIPMENT_IDS,
    FUNCTIONAL_EQUIPMENT_ID_SET,
    HIGH_VALUE_DEFAULT_EXCLUDED_IDS,
    LOCKED_DEFAULT_EXCLUDED_IDS,
    OFFERS_ACTIVATABLE,
    PRICING_AUTHORITY_READY,
    RECOMMENDED_STARTER_ASSORTMENT_IDS,
    STARTER_SHOP_CANDIDATE_IDS,
    StarterCatalogContractError,
    build_authoritative_starter_offer_facts,
    build_equipment_acquisition_audit,
    build_owner_pricing_decision_matrix,
)
from shop_offer_identity_projection import normalize_shop_offer


ROOT = Path(__file__).resolve().parents[1]


def _literal_assignment(name: str):
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                return ast.literal_eval(node.value)
    raise AssertionError(f"app.py assignment not found: {name}")


def _equipment_defs() -> list[dict[str, object]]:
    return _literal_assignment("EQUIPMENT_DEFS")


def _shop_items() -> dict[str, dict[str, object]]:
    return _literal_assignment("SHOP_ITEMS")


def _economy_context() -> dict[str, int]:
    return {
        "daily_cap": _literal_assignment("_COIN_DAILY_CAP"),
        "monster_each": _literal_assignment("_COIN_PER_MONSTER"),
        "monster_cap": _literal_assignment("_COIN_MONSTER_DAILY_CAP"),
        "daily_quest_each": _literal_assignment("_COIN_PER_DAILY_QUEST"),
        "all_quests_bonus": _literal_assignment("_COIN_ALL_QUESTS_BONUS"),
        "first_clear": _literal_assignment("ADVENTURE_FIRST_CLEAR_REWARD_COINS"),
    }


def test_audit_covers_exact_canonical_15_item_pool_from_app_source() -> None:
    definitions = _equipment_defs()
    audit = build_equipment_acquisition_audit(definitions)

    assert len(definitions) == 15
    assert tuple(row.item_id for row in audit) == C045_FUNCTIONAL_EQUIPMENT_IDS
    assert {row.item_id for row in audit} == FUNCTIONAL_EQUIPMENT_ID_SET

    by_id = {definition["id"]: definition for definition in definitions}
    for row in audit:
        definition = by_id[row.item_id]
        assert row.slot == definition["slot"]
        assert row.rarity == definition["rarity"]
        assert row.monster_drop_sources == tuple(definition["drop_from"])
        assert set(row.current_acquisition_sources) == {
            "MONSTER_DROP",
            "ADMIN/LEGACY",
        }
        assert row.shop_overlap_risk == "MONSTER_DROP_OVERLAP"


def test_current_equipment_pool_has_no_shop_price_or_shop_product_authority() -> None:
    definitions = _equipment_defs()
    shop_items = _shop_items()

    assert all("price" not in definition for definition in definitions)
    assert not FUNCTIONAL_EQUIPMENT_ID_SET.intersection(shop_items)
    assert not any(
        item.get("key") in FUNCTIONAL_EQUIPMENT_ID_SET for item in shop_items.values()
    )


def test_three_item_recommendation_covers_one_item_per_functional_slot() -> None:
    assert set(RECOMMENDED_STARTER_ASSORTMENT_IDS) == {
        "wooden_sword",
        "cloth_robe",
        "lucky_stone",
    }
    assert len(RECOMMENDED_STARTER_ASSORTMENT_IDS) == 3
    assert set(STARTER_SHOP_CANDIDATE_IDS) == {
        "wooden_sword",
        "iron_sword",
        "cloth_robe",
        "leather_armor",
        "lucky_stone",
    }

    audit = build_equipment_acquisition_audit(_equipment_defs())
    by_id = {row.item_id: row for row in audit}
    assert {by_id[item_id].slot for item_id in RECOMMENDED_STARTER_ASSORTMENT_IDS} == {
        "weapon",
        "armor",
        "accessory",
    }
    assert all(
        by_id[item_id].recommended_shop_eligibility
        == "PROPOSED_STARTER_SHOP_CANDIDATE"
        for item_id in RECOMMENDED_STARTER_ASSORTMENT_IDS
    )


def test_high_value_and_locked_items_are_explicitly_excluded() -> None:
    audit = build_equipment_acquisition_audit(_equipment_defs())
    by_id = {row.item_id: row for row in audit}

    assert set(HIGH_VALUE_DEFAULT_EXCLUDED_IDS) == {
        "fox_fang",
        "fox_pelt",
        "fox_mask",
        "dragon_claw",
        "dragon_scale",
        "dragon_eye",
        "celestial_blade",
        "void_mantle",
    }
    assert set(LOCKED_DEFAULT_EXCLUDED_IDS) == {"xp_amulet", "go_stone_black"}
    for item_id in HIGH_VALUE_DEFAULT_EXCLUDED_IDS:
        assert by_id[item_id].recommended_shop_eligibility == "DEFAULT_DO_NOT_LIST"
    assert (
        by_id["xp_amulet"].recommended_shop_eligibility
        == "DEFAULT_DO_NOT_LIST_LOCKED_NEW_EQUIP"
    )
    assert (
        by_id["go_stone_black"].recommended_shop_eligibility
        == "DEFAULT_DO_NOT_LIST_INVENTORY_ONLY"
    )


def test_owner_pricing_matrix_is_complete_and_does_not_promote_comparables() -> None:
    audit = build_equipment_acquisition_audit(_equipment_defs())
    matrix = build_owner_pricing_decision_matrix(
        audit,
        comparable_shop_items=_shop_items(),
        economy_context=_economy_context(),
    )

    assert len(matrix) == 15
    assert {row.item_id for row in matrix} == FUNCTIONAL_EQUIPMENT_ID_SET
    assert all(row.owner_decision_required for row in matrix)
    assert all(row.recommended_price_range is None for row in matrix)
    assert all(row.recommended_default is None for row in matrix)
    assert all(row.confidence == "LOW" for row in matrix)
    assert all("30–6000 Coins (21 valid products)" in row.existing_comparable_price for row in matrix)
    assert all("no equipment comparable" in row.existing_comparable_price for row in matrix)
    assert all("global cap=500" in row.estimated_player_earning_context for row in matrix)


def test_no_owner_price_authority_means_no_activatable_offers() -> None:
    facts = build_authoritative_starter_offer_facts(_equipment_defs())

    assert facts == ()
    assert PRICING_AUTHORITY_READY is False
    assert OFFERS_ACTIVATABLE is False


def test_explicit_owner_prices_produce_c025_c029_compatible_server_facts_only() -> None:
    facts = build_authoritative_starter_offer_facts(
        _equipment_defs(),
        accepted_prices={
            "wooden_sword": 101,
            "cloth_robe": 102,
            "lucky_stone": 103,
        },
        price_references={
            "wooden_sword": "owner:c045:wooden_sword",
            "cloth_robe": "owner:c045:cloth_robe",
            "lucky_stone": "owner:c045:lucky_stone",
        },
    )

    assert [fact.item_id for fact in facts] == list(RECOMMENDED_STARTER_ASSORTMENT_IDS)
    normalized = [normalize_shop_offer(fact) for fact in facts]
    assert [offer.offer_id for offer in normalized] == [
        "shop.static.wooden_sword",
        "shop.static.cloth_robe",
        "shop.static.lucky_stone",
    ]
    assert [offer.server_price for offer in normalized] == [101, 102, 103]
    assert all(offer.destination == "player_inventory" for offer in normalized)
    assert all(offer.duplicate_policy == "REJECT_IF_OWNED" for offer in normalized)
    assert all(offer.quantity == 1 for offer in normalized)


@pytest.mark.parametrize(
    "accepted_prices",
    [
        {"wooden_sword": 0},
        {"wooden_sword": -1},
        {"wooden_sword": True},
        {"dragon_claw": 100},
    ],
)
def test_offer_factory_rejects_invalid_or_non_starter_price_input(accepted_prices) -> None:
    with pytest.raises(StarterCatalogContractError):
        build_authoritative_starter_offer_facts(
            _equipment_defs(),
            accepted_prices=accepted_prices,
            price_references={key: "owner:c045:test" for key in accepted_prices},
        )


def test_module_is_source_catalog_only_and_preserves_runtime_boundaries() -> None:
    source = (ROOT / "equipment_shop_starter_catalog.py").read_text(encoding="utf-8")
    assert "import app" not in source
    assert "equipment_loadout_service" not in source
    assert "UPDATE user_stats" not in source
    assert "INSERT INTO" not in source
    assert "NewebPay" not in source
    assert "PayPal" not in source
    assert "SHOP_ENABLED" not in source
    assert "LOADOUT_ENABLED" not in source


def test_c044_consumes_server_equipment_offers_without_frontend_offer_constants() -> None:
    shop = (ROOT / "shop.html").read_text(encoding="utf-8")
    assert "equipment_offers" in shop
    assert "/api/shop/catalog" in shop
    assert "offer.price" in shop
    for item_id in C045_FUNCTIONAL_EQUIPMENT_IDS:
        assert item_id not in shop
