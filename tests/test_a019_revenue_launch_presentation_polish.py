"""A019 presentation-only contracts for Revenue V1 launch polish."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "rpg-wave2-lane-a-a019-test-secret")
import app as app_module  # noqa: E402
from premium_v1_revenue import C013_LAUNCH_COSMETIC_IDS, c013_claim_route_enabled  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
SHOP = (ROOT / "shop.html").read_text(encoding="utf-8")
UPGRADE = (ROOT / "upgrade.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")

LOCKED_FIVE = {
    "robe_plain",
    "robe_bamboo",
    "robe_fox",
    "back_pack",
    "acc_dragon_pendant",
}
HIDDEN_IDS = {
    "robe_snow",
    "hat_scholar",
    "back_lantern",
    "back_scroll",
    "acc_goban_seal",
}


def test_a019_preserves_exact_five_and_default_off_revenue_gate():
    assert set(C013_LAUNCH_COSMETIC_IDS) == LOCKED_FIVE
    assert len(C013_LAUNCH_COSMETIC_IDS) == 5
    assert c013_claim_route_enabled({}) is False
    assert c013_claim_route_enabled({"GO_REVENUE_V1_PREMIUM_CLAIM_ENABLED": "0"}) is False


def test_locked_five_remain_canonical_pure_presentation_assets():
    for item_id in LOCKED_FIVE:
        presentation = app_module.PURE_COSMETIC_PRESENTATION_REGISTRY[item_id]
        assert presentation["asset_id"] == item_id
        assert presentation["asset_format"] == "WEBP"
        assert presentation["pure_presentation"] is True
        assert presentation["functional_effect_count"] == 0
        assert presentation["combat_authority"] == "NO"
        assert (ROOT / presentation["asset"].lstrip("/")).is_file()
        assert not app_module.APPEARANCE_EFFECTS.get(item_id, {})


def test_hidden_cosmetics_are_not_added_to_the_locked_pool():
    assert not (LOCKED_FIVE & HIDDEN_IDS)
    assert app_module.HIDDEN_UNRELEASED_APPEARANCE_IDS == frozenset(HIDDEN_IDS)


def test_shop_has_explicit_selection_state_and_accessible_modal_contract():
    for marker in (
        "data-premium-v1-select",
        "premium-v1-claim-selected",
        "aria-pressed=\"${selected ? 'true' : 'false'}\"",
        "data-cosmetic-state=\"${stateClass}\"",
        "closeCosmeticPreview",
        "aria-describedby=\"cosmetic-preview-copy\"",
        "document.addEventListener('keydown'",
        "window.onLangChange",
    ):
        assert marker in SHOP


def test_shop_has_loading_error_empty_and_bilingual_revenue_copy():
    for marker in (
        "renderCosmeticCommerceError",
        "renderShopLoadError",
        "renderPremiumV1Error",
        "shop.state.retry",
        "shop.cosmetic.emptyTitle",
        "shop.premium.copy.active",
        "shop.premium.benefit.questions.copy",
        "shop.premium.benefit.cosmetic.copy",
        "shop.premium.benefit.vesting.copy",
        "shop.premium.grace",
    ):
        assert marker in SHOP
    assert "transform:scale(3); transform-origin:82% 38%;" in SHOP
    assert "assets/hero/items/back_pack.svg" not in SHOP
    assert "assets/hero/items/acc_dragon_pendant.svg" not in SHOP


def test_upgrade_copy_and_controls_are_localized_and_keyboard_visible():
    for marker in (
        'data-i18n="up.hero.eyebrow"',
        'data-i18n="up.tag.choose"',
        'data-i18n="up.tag.unlock"',
        'data-i18n="up.tag.permission"',
        'data-i18n="up.tag.faq"',
        'data-i18n="up.revenue.note.title"',
        'data-i18n="up.revenue.note.copy"',
        'data-i18n-aria-label="up.modal.close"',
        "aria-pressed=\"true\"",
        "setAttribute('aria-pressed'",
    ):
        assert marker in UPGRADE
    for marker in (
        "up.revenue.note.title",
        "up.revenue.note.copy",
        "up.revenue.note.link",
        "up.modal.close",
        "shop.premium.copy.active",
        "shop.premium.selection.selected",
    ):
        assert marker in I18N


def test_a019_does_not_reintroduce_functional_or_commerce_authority():
    assert "No claim or payment action was performed." in SHOP or "未執行領取或付款動作" in SHOP
    assert "C013_LAUNCH_COSMETIC_IDS" not in SHOP
    assert "player_inventory" not in SHOP
