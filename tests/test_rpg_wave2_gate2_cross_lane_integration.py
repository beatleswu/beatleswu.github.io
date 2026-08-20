"""Wave 2 Gate 2 cross-lane authority and presentation reconciliation."""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
import re
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_BIBLE = ROOT / "docs" / "planning" / "GO_ODYSSEY_RPG_VISUAL_BIBLE.md"


def _app_source() -> str:
    return (ROOT / "app.py").read_text(encoding="utf-8")


def test_one_canonical_visual_bible_preserves_character_and_item_contracts():
    assert CANONICAL_BIBLE.is_file()
    assert not (ROOT / "GO_ODYSSEY_RPG_VISUAL_BIBLE.md").exists()

    bible = CANONICAL_BIBLE.read_text(encoding="utf-8")
    for token in (
        "Character System Section v1",
        "Item / Collection Section — Wave 2 Lane C Gate 2 P1",
        "PLAYER_FRAME_A_STANDARD_CHIBI",
        "WEARABLE_PROTOTYPE_READY=YES",
        "UNIVERSAL_WEARABLE_FIT_PROVEN=NO",
        "Functional Equipment remains Lane B / Backpack",
        "COIN_SPEND_AUTHORITY=existing server-side atomic _spend_coins",
        "BADGE_EARNING_AUTHORITY=existing badge earning authority",
    ):
        assert token in bible


def test_inventory_information_architecture_keeps_authorities_separate():
    inventory = (ROOT / "inventory.html").read_text(encoding="utf-8")

    assert "戰鬥裝備 / Functional Equipment" in inventory
    assert "data-functional-equipment-backpack" in inventory
    assert "fetch('/api/player/inventory'" in inventory
    assert "fetch('/api/player/inventory/equip'" in inventory
    assert 'href="/item-journal"' in inventory
    assert "物品圖鑑 / Item Journal" in inventory
    assert inventory.index("data-functional-equipment-backpack") < inventory.index(
        'href="/item-journal"'
    )
    assert "@media (max-width:700px)" in inventory
    assert ".functional-equipment-layout { grid-template-columns:1fr; }" in inventory
    assert ".backpack-heading { flex-direction:column; }" in inventory
    assert ".backpack-shop-link { width:100%; justify-content:center; }" in inventory


def test_routes_and_domain_writers_remain_single_authorities():
    source = _app_source()
    tree = ast.parse(source)
    functions = Counter()
    routes = Counter()

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        functions[node.name] += 1
        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "route"
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                continue
            routes[decorator.args[0].value] += 1

    for function_name in (
        "_spend_coins",
        "_grant_shop_purchase",
        "_roll_loot",
        "check_and_award",
        "get_inventory",
        "equip_item",
        "item_journal",
    ):
        assert functions[function_name] == 1

    for route in (
        "/api/player/inventory",
        "/api/player/inventory/equip",
        "/api/item-journal",
        "/api/shop/buy",
        "/api/badges/earned",
    ):
        assert routes[route] == 1


def test_item_journal_projection_contains_no_database_mutation():
    source = _app_source()
    start = source.index("@app.route('/api/item-journal')")
    end = source.index("# ── 商城 API", start)
    route = source[start:end]

    assert "SELECT " in route
    assert not re.search(
        r"\b(?:INSERT|UPDATE|DELETE|REPLACE|ALTER|CREATE|DROP)\b", route, re.I
    )
    assert ".commit(" not in route
    assert "'functional_equipment': {'authority': 'player_inventory'" in route


def test_gate2_svg_assets_are_well_formed_and_resolve():
    asset_roots = (
        ROOT / "assets" / "hero" / "equipment" / "functional",
        ROOT / "assets" / "items",
        ROOT / "assets" / "badges" / "prototypes",
    )
    assets = [path for root in asset_roots for path in root.glob("*.svg")]
    assert len(assets) == 33
    for asset in assets:
        ET.parse(asset)
