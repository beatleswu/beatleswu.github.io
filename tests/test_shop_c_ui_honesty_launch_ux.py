"""Focused SHOP-C UI honesty and launch UX contracts."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHOP = (ROOT / "shop.html").read_text(encoding="utf-8")


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


def test_purchase_enabled_is_strict_server_fact_and_missing_fails_closed():
    enabled = _function_body(SHOP, "function shopPurchaseEnabled(")
    state = _function_body(SHOP, "function updateShopPurchaseState(")

    assert "data?.purchase_enabled === true" in enabled
    assert "typeof data?.purchase_enabled === 'boolean'" in state
    assert "state.hidden = enabled" in state
    assert "data-purchase-enabled-source=\"missing\"" in SHOP
    assert 'id="shop-purchase-state"' in SHOP
    assert 'role="status"' in SHOP
    assert 'aria-live="polite"' in SHOP
    assert "You can browse the catalog" in SHOP
    assert "目前可以瀏覽商品" in SHOP


def test_every_purchase_entry_point_and_shared_request_guard_fail_closed():
    request = _function_body(SHOP, "async function requestShopPurchase(")
    assert "shopPurchaseEnabled" in request
    assert request.index("shopPurchaseEnabled") < request.index("beginShopPurchaseIntent")
    assert "return { error: 'SHOP_PURCHASE_DISABLED' }" in request

    for signature in (
        "async function buyItem(",
        "async function buyAppearance(",
        "async function purchaseCosmetic(",
        "async function purchaseEquipment(",
        "async function doGacha(",
    ):
        body = _function_body(SHOP, signature)
        assert "if (!shopPurchaseEnabled())" in body, signature
        assert "showShopPurchaseClosed()" in body, signature

    # The UI never sends a client-provided price or a raw internal error token.
    assert "price:" not in _function_body(SHOP, "async function buyItem(")
    assert "return map[code] || fallback || code" not in SHOP
    assert "return generic;" in _function_body(SHOP, "function errorMessage(")


def test_required_error_codes_have_bilingual_player_copy():
    error = _function_body(SHOP, "function errorMessage(")
    for code in (
        "shop_offer_unavailable",
        "SHOP_PURCHASE_DISABLED",
        "LEGACY_PURCHASE_RETIRED",
        "insufficient_coins",
        "already_owned",
        "purchase_operation_in_progress",
        "purchase_operation_conflict",
        "purchase_conflict",
        "purchase_failed",
        "generic_purchase_failure",
    ):
        # Uppercase server codes are normalized before lookup, so each required
        # contract token is still present in the source or its canonical lower
        # case lookup form.
        assert code in SHOP or code.lower() in error, code
    assert "Purchases are temporarily closed" in error
    assert "購買功能暫時關閉" in error
    assert "This purchase identity is already bound" in error
    assert "這筆購買識別已綁定" in error
    assert "The Shop could not complete this purchase" in error
    assert "商城無法完成這筆購買" in error


def test_catalog_cards_keep_repeatable_consumables_buyable_and_separate_use():
    item_card = _function_body(SHOP, "function itemCard(")
    use_copy = _function_body(SHOP, "function shopItemPurchaseUseCopy(")
    r1_renderer = _function_body(SHOP, "function renderR1Consumables(")

    assert "SHOP_EFFECT_ITEM_KEYS" in SHOP
    assert 'id="shop-r1-consumables-grid"' in SHOP
    assert "Array.isArray(res?.items)" in r1_renderer
    assert "renderR1Consumables(res);" in SHOP
    for key in (
        "small_xp_potion",
        "xp_potion",
        "grand_xp_potion",
        "streak_shield",
        "double_streak_shield",
        "extra_questions_small",
        "extra_questions",
        "grand_training_pass",
    ):
        assert key in SHOP
    assert "Added to Backpack; not activated yet." in use_copy
    assert "Activate it later from Backpack" in use_copy
    assert "加入背包；尚未啟用效果" in use_copy
    assert "之後可在背包主動使用" in use_copy
    # Inventory quantity is display-only for this card; it is not a disabled
    # condition, so a repeatable consumable remains purchasable when owned > 0.
    assert "const owned = Number(catalog?.inventory?.[key] || 0);" in item_card
    assert "owned ?" in item_card
    assert "disabled" in item_card
    assert "data-shop-purchase-use=\"separate\"" in SHOP


def test_permanent_cosmetics_show_owned_state_without_purchase_action():
    renderer = _function_body(SHOP, "function renderCosmeticCommerce(")
    assert "const owned = !!ownership.owned;" in renderer
    assert "shop.cosmetic.state.owned" in renderer
    assert "data-cosmetic-equip" in renderer
    assert "!shopPurchaseEnabled()" in renderer
    assert "data-cosmetic-purchase" in renderer
    action = renderer[renderer.index("const action =") : renderer.index("const artClass")]
    owned_branch = action[action.index(": owned") : action.index(": purchasePending")]
    assert "data-cosmetic-equip" in owned_branch
    assert "data-cosmetic-purchase" not in owned_branch


def test_purchase_success_refreshes_authoritative_views_and_preserves_retry_identity():
    cosmetic = _function_body(SHOP, "async function purchaseCosmetic(")
    item = _function_body(SHOP, "async function buyItem(")
    assert "Promise.all([loadCatalog(), loadCosmeticCommerce()])" in cosmetic
    assert "await loadCatalog();" in item
    assert "purchase_operation_id: intent.operationId" in SHOP
    assert "Retry the same purchase" in SHOP
    assert "重試同一筆購買" in SHOP
    assert "shopPurchaseUiInFlight" in SHOP
    assert "aria-busy=\"true\"" in SHOP


def test_responsive_and_accessible_closed_controls_remain_in_shop_visual_language():
    assert "@media (max-width: 920px)" in SHOP
    assert "@media (max-width: 640px)" in SHOP
    assert ".btn:focus-visible" in SHOP
    assert "button:focus-visible" in SHOP
    assert ".btn:disabled" in SHOP
    assert 'data-shop-purchase-control="true"' in SHOP
    assert 'aria-disabled="true"' in SHOP
    assert 'aria-busy="true"' in SHOP
    assert 'role="alert"' in SHOP
    assert 'role="status"' in SHOP
    assert 'data-shop-r1-surface="consumables"' in SHOP


def test_shop_c_does_not_touch_app_or_add_a_second_purchase_authority():
    assert "/api/shop/catalog" in SHOP
    assert "/api/shop/buy" in SHOP
    assert "fetch('/api/shop/catalog'" not in SHOP
    assert "fetch('/api/shop/buy'" not in SHOP
    assert "GO_ENABLE" not in SHOP
    assert "GO_REVENUE_LIVE" not in SHOP
