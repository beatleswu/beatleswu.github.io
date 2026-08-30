"""C053 Option B Shop-surface containment contracts.

These checks keep the public Shop projection narrow while preserving the
existing server authorities and compatibility source for later use.  The
Shop remains default-off; the client may only reveal the admitted surfaces
after the server catalog proves the canonical equipment list is available.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHOP = (ROOT / "shop.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")
OFFERS = (ROOT / "equipment_shop_offer_authority.py").read_text(encoding="utf-8")
STARTER = (ROOT / "equipment_shop_starter_catalog.py").read_text(encoding="utf-8")


def _function_body(source: str, signature: str) -> str:
    start = source.find(signature)
    assert start >= 0, f"missing {signature}"
    opening = source.find("{", start)
    assert opening >= 0, f"{signature} must have a body"
    depth = 0
    quote = None
    escaped = False
    for index in range(opening, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "'\"`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated {signature}")


def test_option_b_hides_every_non_admitted_public_shop_surface_by_default():
    assert re.search(
        r'<section[^>]+class="[^"]*cosmetic-commerce-panel[^" ]*"'
        r'[^>]+data-c053-option-b-surface="cosmetics"[^>]+hidden',
        SHOP,
    )
    assert re.search(
        r'<section[^>]+id="equipment-commerce-panel"[^>]+data-c044-catalog="equipment-offers"'
        r'[^>]+data-c053-option-b-surface="equipment"[^>]+[^>]*hidden',
        SHOP,
    )
    for retired in ("premium", "daily", "gacha", "weekly", "monthly", "items"):
        assert re.search(
            rf'data-c053-option-b-retired="{retired}"[^>]*hidden', SHOP
        ), f"{retired} Shop surface must be hidden for Option B"
    assert 'data-c053-option-b-retired="gacha-collection"' in SHOP
    assert 'id="legacy-gacha-collection-summary"' in SHOP
    assert "Premium 與付款不在此頁" in SHOP
    assert "功能裝備進入背包" in SHOP
    assert "外觀裝扮進入衣櫃" in SHOP


def test_option_b_reveal_latch_is_server_catalog_driven_and_fail_closed():
    helper = _function_body(SHOP, "function c053SetOptionBVisibility(")
    readiness = _function_body(SHOP, "function c053ServerCatalogEnablesOptionB(")
    load_catalog = _function_body(SHOP, "async function loadCatalog(")

    assert "let c053OptionBVisible = false;" in SHOP
    assert "[data-c053-option-b-surface]" in helper
    assert "surface.hidden = !c053OptionBVisible" in helper
    assert "c043EquipmentOffers(data).length === 3" in readiness
    assert "Number.isInteger(data?.coins)" in readiness
    assert "c053SetOptionBVisibility(c053ServerCatalogEnablesOptionB(res));" in load_catalog
    assert "c053SetOptionBVisibility(false);" in load_catalog
    assert "wooden_sword" not in readiness
    assert "300" not in readiness and "400" not in readiness


def test_cosmetic_projection_admits_only_server_coin_products_and_no_candidates():
    products = _function_body(SHOP, "function c053CoinCosmeticProducts(")
    renderer = _function_body(SHOP, "function renderCosmeticCommerce(")

    assert "product.unlock_type === 'coins'" in products
    assert "product.currency" in products
    assert "Number.isInteger(product.price)" in products
    assert "c053CoinCosmeticProducts(data)" in renderer
    assert "Premium products" in renderer
    assert "const candidateCards = '';" in renderer
    assert "grid.innerHTML = productCards + candidateCards;" in renderer
    assert "visualCandidates.map(renderVisualReviewCandidate)" not in renderer
    assert not re.search(r"^\s*loadPremiumV1Offer\(\);\s*$", SHOP, re.MULTILINE)


def test_authorities_still_own_prices_products_and_destinations():
    cosmetic_products = APP[
        APP.index("COSMETIC_COMMERCE_PRODUCTS =") : APP.index("_COSMETIC_PRODUCT_BY_ID")
    ]
    assert cosmetic_products.count("'unlock_type': 'coins'") == 2
    assert cosmetic_products.count("'unlock_type': 'premium'") == 1
    for item_id, price in (
        ("wooden_sword", 300),
        ("cloth_robe", 300),
        ("lucky_stone", 400),
    ):
        assert item_id in OFFERS
        assert re.search(rf"[\"']{item_id}[\"']:\s*{price}\b", OFFERS)
        assert item_id not in SHOP

    for product_id, price in (
        ("cosmetic.outfit.robe_plain", 200),
        ("cosmetic.outfit.robe_bamboo", 450),
    ):
        assert product_id in APP
        assert re.search(
            rf"['\"]product_id['\"]:\s*['\"]{re.escape(product_id)}['\"][\s\S]{{0,260}}?"
            rf"['\"]unlock_type['\"]:\s*['\"]coins['\"][\s\S]{{0,100}}?['\"]price['\"]:\s*{price}\b",
            APP,
        )
        assert product_id not in SHOP
    assert "cosmetic.outfit.robe_premium" not in SHOP
    assert "'product_id': 'cosmetic.outfit.robe_premium'" in APP
    assert re.search(
        r"'product_id': 'cosmetic\.outfit\.robe_premium'[\s\S]{0,260}?"
        r"'unlock_type': 'premium'",
        APP,
    )
    assert "player_wardrobe.item_id" in APP
    assert "player_inventory" in STARTER


def test_option_b_copy_separates_functional_equipment_and_cosmetics_in_both_locales():
    assert "Coins Shop" in I18N
    assert "功能裝備" in SHOP
    assert "FUNCTIONAL EQUIPMENT" in SHOP
    assert "Coins Cosmetics" in I18N
    assert "COINS ONLY" in I18N
    assert "combat power 0" in I18N
    assert "戰鬥力固定為 0" in SHOP
    assert "purchase != equip" not in SHOP.lower()
    assert "auto-equipped" in SHOP
    assert "自動裝備" in SHOP


def test_legacy_and_payment_paths_remain_compatibility_source_not_public_ui():
    assert "/api/shop/gacha" in SHOP
    assert re.search(r'data-c053-option-b-retired="gacha"[^>]*hidden', SHOP)
    assert "/api/shop/buy_appearance" in SHOP
    assert "/api/cosmetic-commerce/purchase" in SHOP
    assert "/api/cosmetic-commerce/equip" in SHOP
    assert "NewebPay" not in SHOP
    assert "PayPal" not in SHOP
    assert "GO_ENABLE" not in SHOP
    assert "GO_REVENUE_LIVE" not in SHOP
