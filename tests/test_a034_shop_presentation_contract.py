"""A034 Shop presentation-only contracts.

These tests protect the narrow frontend adapter and the authority boundary.
They do not exercise or replace Shop/Commerce mutation authorities.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHOP = (ROOT / "shop.html").read_text(encoding="utf-8")
ADAPTER = (ROOT / "js" / "game" / "shop_presentation_v1.js").read_text(
    encoding="utf-8",
)
STYLES = (ROOT / "css" / "e10" / "shop_presentation_v1.css").read_text(
    encoding="utf-8",
)


def test_a034_mount_is_narrow_and_uses_expected_files_only():
    assert 'class="a034-shop"' in SHOP
    assert '/css/e10/shop_presentation_v1.css?v=a034-v1' in SHOP
    assert '/js/game/shop_presentation_v1.js?v=a034-v1' in SHOP
    assert "app.py" not in ADAPTER
    assert "fetch(" not in ADAPTER
    assert "localStorage" not in ADAPTER
    assert "sessionStorage" not in ADAPTER


def test_a034_adapter_is_presentation_only_and_does_not_create_commerce_truth():
    for marker in (
        "normalizeItem",
        "normalizeCatalog",
        "server_price",
        "owned_quantity",
        "legal_action",
        "MutationObserver",
    ):
        assert marker in ADAPTER
    for forbidden in (
        "purchase_operation_id",
        "coin_balance =",
        "stock =",
        "discount =",
        "rarity =",
        "fetch(",
        "localStorage",
        "sessionStorage",
    ):
        assert forbidden not in ADAPTER


def test_a034_shop_preserves_existing_authority_routes_and_gate():
    for marker in (
        '/api/shop/catalog',
        '/api/shop/buy',
        '/api/shop/buy_appearance',
        '/api/cosmetic-commerce/catalog',
        '/api/cosmetic-commerce/preview/',
        '/api/cosmetic-commerce/purchase',
        '/api/cosmetic-commerce/equip',
        '/api/premium/v1/offer',
        "requestShopPurchase",
    ):
        assert marker in SHOP
    # The gate remains owned by the server/runtime; this presentation layer
    # must not duplicate or reinterpret it.
    assert "CANONICAL_COIN_SHOP_PURCHASE_ENABLED" not in ADAPTER


def test_a034_visual_contract_is_object_first_and_responsive():
    for marker in (
        "a034-legacy-gacha",
        "a034-cosmetic-card",
        "min-height: 44px",
        "item-art",
        "cosmetic-art",
        "prefers-reduced-motion",
        "grid-template-columns: 1fr",
        "grid-template-columns: repeat(2, minmax(0, 1fr))",
        "overflow-x: hidden",
    ):
        assert marker in STYLES
    assert "a034-item-card" in ADAPTER
    assert "emoji" not in STYLES.lower()


def test_a034_does_not_touch_index_or_add_fake_commerce_markers():
    assert "index.html" not in SHOP
    for forbidden in (
        "featured sale",
        "limited flash sale",
        "bundle savings",
        "fake stock",
        "loot box",
        "randomizer",
    ):
        assert forbidden not in ADAPTER.lower()


def test_a034_adapter_source_has_no_transport_or_storage_side_effect_contract():
    assert "JSON.parse" not in ADAPTER
    assert "XMLHttpRequest" not in ADAPTER
    assert "document.cookie" not in ADAPTER
    assert json.loads(json.dumps({"contract": "A034_SHOP_PRESENTATION_V1"}))
