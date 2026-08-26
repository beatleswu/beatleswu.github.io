"""A034 Shop presentation-only contracts.

These tests protect the narrow frontend adapter and the authority boundary.
They do not exercise or replace Shop/Commerce mutation authorities.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHOP = (ROOT / "shop.html").read_text(encoding="utf-8")
ADAPTER = (ROOT / "js" / "game" / "shop_presentation_v1.js").read_text(
    encoding="utf-8",
)
STYLES = (ROOT / "css" / "e10" / "shop_presentation_v1.css").read_text(
    encoding="utf-8",
)
MERCHANT_COPY = SHOP.split("const MERCHANT_LINES = {", 1)[1].split(
    "const ZH_ITEM =", 1
)[0]
INITIAL_MERCHANT_COPY = re.search(
    r'id="merchant-line">([^<]*)</span>', SHOP
).group(1)
A034_VISIBLE_COPY = SHOP.split("const A034_VISIBLE_COPY = Object.freeze({", 1)[1].split(
    "function visibleShopCopy", 1
)[0]
VISIBLE_COPY_MARKUP = "\n".join(
    re.findall(r'data-a034-copy="[^"]+"[^>]*>(.*?)</(?:p|div)>', SHOP, re.DOTALL)
)
DAILY_RENDER_COPY = SHOP.split("function renderDaily(res) {", 1)[1].split(
    "function renderItems", 1
)[0]
MERCHANT_VISIBLE_COPY = "\n".join(
    (MERCHANT_COPY, INITIAL_MERCHANT_COPY, A034_VISIBLE_COPY, VISIBLE_COPY_MARKUP, DAILY_RENDER_COPY)
)


# These are semantic groups rather than a single list of exact phrases.  The
# scan is limited to the rendered merchant/hero/daily-rotation presentation
# surface so legacy gacha mechanics and truthful product descriptions remain
# governed by their existing owners.
MERCHANT_FORBIDDEN_SEMANTICS = {
    "discount_or_sale": re.compile(
        r"discount|sale|deal|best value|special price|折扣|特賣|特價|優惠|促銷|原價|划算|性價比|不虧|超值",
        re.IGNORECASE,
    ),
    "stock_or_scarcity": re.compile(
        r"stock|scarcity|out of stock|runs out|moves fast|fresh batch|庫存|售罄|賣得很快|剛進|新進|僅剩|剩餘數量|庫存不足",
        re.IGNORECASE,
    ),
    "pity_or_guarantee": re.compile(
        r"pity|guarantee|guaranteed|odds|pull|chest|保底|保證|機率|開箱|抽",
        re.IGNORECASE,
    ),
    "countdown_or_expiry": re.compile(
        r"until midnight|won't last|today|tomorrow|expires?|expiry|countdown|"
        r"今天|今日|明天|午夜|到期|倒數|限時|輪替不等人",
        re.IGNORECASE,
    ),
    "unsupported_power_recommendation": re.compile(
        r"recommend|right pick|current (?:level|progress|stage)|skill level|"
        r"best effect|twice as strong|pair .* shield|quality|value|"
        r"推薦|段位|等級|適合|效果|搭配|組合|品質|用得上|最有效率|絕對",
        re.IGNORECASE,
    ),
    "refund_or_exchange_promise": re.compile(
        r"refund|exchange|wrong one|wrong item|換貨|退款|退費|退貨|交換|買錯",
        re.IGNORECASE,
    ),
}


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


def test_a034_final_merchant_copy_has_no_unsupported_commerce_semantics():
    violations = {
        name: sorted(
            set(match.group(0) for match in pattern.finditer(MERCHANT_VISIBLE_COPY))
        )
        for name, pattern in MERCHANT_FORBIDDEN_SEMANTICS.items()
    }
    violations = {name: hits for name, hits in violations.items() if hits}
    assert violations == {}


def test_a034_rendered_shop_copy_is_not_overwritten_by_legacy_i18n_keys():
    assert 'data-a034-copy="hero-lead"' in SHOP
    assert 'data-a034-copy="daily-sub"' in SHOP
    assert 'data-i18n="shop.lead"' not in SHOP
    assert 'data-i18n="shop.daily.sub"' not in SHOP
    assert "Premium members still enjoy daily rotation discounts" not in SHOP
    assert "Premium 會員仍享每日輪替折扣" not in SHOP


def test_a034_daily_rotation_copy_has_no_sale_price_or_urgency_render_path():
    assert 'visibleShopCopy("dailyItemDescription")' in DAILY_RENDER_COPY
    assert 'visibleShopCopy("dailyRotationBadge")' in DAILY_RENDER_COPY
    assert "sale: true" not in DAILY_RENDER_COPY
    assert "Daily Deal" not in SHOP
    assert "每日特價" not in SHOP
    assert "orig_price" not in SHOP


def test_a034_visible_copy_guard_reports_required_semantic_counts_as_zero():
    expected_zero_groups = {
        "discount_or_sale",
        "stock_or_scarcity",
        "countdown_or_expiry",
        "pity_or_guarantee",
        "refund_or_exchange_promise",
        "unsupported_power_recommendation",
    }
    for name in expected_zero_groups:
        assert not MERCHANT_FORBIDDEN_SEMANTICS[name].search(MERCHANT_VISIBLE_COPY), name
    assert not re.search(
        r"Premium.{0,80}(?:discount|sale|deal|折扣|特價|優惠)",
        MERCHANT_VISIBLE_COPY,
        re.IGNORECASE,
    )


def test_a034_merchant_semantic_guard_covers_required_fixture_groups():
    fixtures = {
        "discount_or_sale": "Today's discount is the best deal.",
        "stock_or_scarcity": "Grab it before stock runs out.",
        "pity_or_guarantee": "The next pull is guaranteed by pity.",
        "countdown_or_expiry": "Today's rotation expires at midnight.",
        "unsupported_power_recommendation": "At your current level, I recommend this effect.",
        "refund_or_exchange_promise": "If you pick the wrong item, I can refund or exchange it.",
    }
    for name, fixture in fixtures.items():
        assert MERCHANT_FORBIDDEN_SEMANTICS[name].search(fixture), name
