"""A031-R2 visual contract for the E10 Backpack category plaques.

The category data, counts and filter behavior remain owned by inventory.html.
This test only protects the presentation replacement for the rejected dark
navigation-label artwork, including the narrow mobile layout.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = (ROOT / "inventory.html").read_text(encoding="utf-8")
CSS = (ROOT / "css/e10/backpack.css").read_text(encoding="utf-8")


def test_backpack_filter_uses_light_plaque_treatment_not_dark_label_art():
    filter_block = CSS[CSS.index('html[data-e10-backpack-shell="true"] .backpack-filter {') :]
    filter_block = filter_block[: filter_block.index('html[data-e10-backpack-shell="true"] .backpack-filter::before {')]

    assert "background: var(--e10-art-label-plaque)" not in filter_block
    assert "linear-gradient(180deg, #fff9e9, #f1dfb7)" in filter_block
    assert "border-radius: 14px 10px 14px 10px" in filter_block
    assert "box-shadow:" in filter_block


def test_backpack_filter_selected_state_is_teal_and_distinct():
    selected = CSS[CSS.index('html[data-e10-backpack-shell="true"] .backpack-filter[aria-selected="true"] {') :]
    selected = selected[: selected.index('html[data-e10-backpack-shell="true"] .backpack-filter[aria-selected="true"]::before {')]

    assert "linear-gradient(180deg, #48cbb8, #118887)" in selected
    assert "#e4b85b" in selected
    assert "aria-selected" in INVENTORY


def test_mobile_filter_plaques_keep_two_columns_and_fit_narrow_viewports():
    assert "@media (max-width: 767px)" in CSS
    mobile = CSS[CSS.index("@media (max-width: 767px)") :]
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in mobile
    assert "white-space: normal;" in mobile
    assert "@media (max-width: 380px)" in mobile
    assert "font-size: 11px;" in mobile


def test_filter_logic_and_category_identity_are_unchanged():
    for category in (
        "all",
        "consumable",
        "training",
        "growth",
        "guard",
        "collection",
        "quest",
        "material",
        "chest",
        "exchange",
        "other",
    ):
        assert f"key:'{category}'" in INVENTORY
    for token in (
        "button.dataset.category = category.key;",
        "button.setAttribute('aria-selected', String(activeBackpackCategory === category.key));",
        "renderBackpackFilters();",
        "renderBackpackGrid();",
    ):
        assert token in INVENTORY
