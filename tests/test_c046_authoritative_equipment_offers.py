"""C046 authoritative Equipment offer source and C019 compatibility tests."""

from __future__ import annotations

from datetime import datetime, timezone
import ast
import sqlite3
from pathlib import Path

import pytest

from coin_purchase_authority import AcquisitionFailed, InsufficientCoins
import equipment_commerce_service as c043_commerce
from equipment_shop_offer_authority import (
    ALL_OFFER_PRICES_AUTHORITATIVE,
    AUTO_EQUIP_AFTER_PURCHASE,
    EQUIPMENT_OFFERS_SOURCE_IMPLEMENTED,
    FRONTEND_OFFER_DUPLICATION,
    LOADOUT_ENABLED,
    OWNER_APPROVED_STARTER_PRICE_REFERENCES,
    OWNER_APPROVED_STARTER_PRICES,
    PRICE_AUTHORITY_SOURCE,
    SHOP_ENABLED,
    build_authoritative_equipment_offer_facts,
    build_authoritative_equipment_offers,
)
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_purchase_operations
from migrations.domain_event_outbox_v1 import upgrade as upgrade_event_outbox
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033


ROOT = Path(__file__).resolve().parents[1]
FIXED_NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
SLOT_SOURCE = {
    "wooden_sword": "weapon",
    "cloth_robe": "armor",
    "lucky_stone": "accessory",
}
SLOT_DEFS = tuple(
    {"id": item_id, "slot": slot} for item_id, slot in SLOT_SOURCE.items()
)


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


def _connection(*, coins: int = 1000) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE user_stats (user_id INTEGER PRIMARY KEY, coins INTEGER NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE currency_log ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
        "delta INTEGER NOT NULL, balance_after INTEGER NOT NULL, reason TEXT NOT NULL, "
        "created_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE player_inventory ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
        "equip_id TEXT NOT NULL, equipped INTEGER NOT NULL DEFAULT 0, "
        "obtained_at TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'drop')"
    )
    upgrade_b033(conn, equipment_defs=SLOT_DEFS)
    conn.execute(
        "CREATE TABLE shop_inventory ("
        "user_id INTEGER NOT NULL, item_key TEXT NOT NULL, qty INTEGER NOT NULL DEFAULT 0, "
        "PRIMARY KEY (user_id, item_key))"
    )
    conn.execute(
        "CREATE TABLE player_wardrobe ("
        "user_id INTEGER NOT NULL, item_id TEXT NOT NULL, obtained_at TEXT NOT NULL, "
        "source TEXT NOT NULL, PRIMARY KEY (user_id, item_id))"
    )
    upgrade_purchase_operations(conn)
    upgrade_event_outbox(conn)
    conn.execute("INSERT INTO user_stats(user_id, coins) VALUES(1, ?)", (coins,))
    conn.commit()
    return conn


def _purchase(
    conn: sqlite3.Connection,
    operation_id: str,
    offer_id: str,
    *,
    catalog_authority=None,
):
    authority = catalog_authority or c043_commerce.ServerFactEquipmentOfferAuthority(
        build_authoritative_equipment_offer_facts(_equipment_defs())
    )
    equipment_id = offer_id.removeprefix("shop.static.")
    return c043_commerce.purchase_equipment_with_coins(
        conn,
        1,
        operation_id,
        equipment_id,
        catalog_authority=authority,
        equipment_defs=_equipment_defs(),
        now=FIXED_NOW,
    )


def test_authoritative_catalog_has_exact_three_ids_and_owner_prices() -> None:
    facts = build_authoritative_equipment_offer_facts(_equipment_defs())
    assert len(facts) == 3
    assert [fact.item_id for fact in facts] == [
        "wooden_sword",
        "cloth_robe",
        "lucky_stone",
    ]
    assert [fact.server_price for fact in facts] == [300, 300, 400]
    assert all(fact.currency == "COINS" for fact in facts)
    assert all(fact.destination == "player_inventory" for fact in facts)
    assert all(fact.duplicate_policy == "REJECT_IF_OWNED" for fact in facts)
    assert all(
        fact.price_reference == OWNER_APPROVED_STARTER_PRICE_REFERENCES[fact.item_id]
        for fact in facts
    )


def test_normalized_offers_are_c019_compatible_and_not_frontend_defined() -> None:
    offers = build_authoritative_equipment_offers(_equipment_defs())
    assert [offer.offer_id for offer in offers] == [
        "shop.static.wooden_sword",
        "shop.static.cloth_robe",
        "shop.static.lucky_stone",
    ]
    assert [offer.item_id for offer in offers] == list(OWNER_APPROVED_STARTER_PRICES)
    assert [offer.price for offer in offers] == [300, 300, 400]
    assert all(offer.currency_type == "COINS" for offer in offers)
    assert all(offer.destination == "player_inventory" for offer in offers)
    assert all(offer.presentation_metadata["starter_assortment"] is True for offer in offers)
    assert FRONTEND_OFFER_DUPLICATION is False
    assert PRICE_AUTHORITY_SOURCE in {
        offer.presentation_metadata["price_reference"].split(":", 1)[0]
        for offer in offers
    }


def test_unauthorized_and_locked_items_are_not_offerable() -> None:
    offers = build_authoritative_equipment_offers(_equipment_defs())
    offered_ids = {offer.item_id for offer in offers}
    assert offered_ids == {"wooden_sword", "cloth_robe", "lucky_stone"}
    assert not offered_ids.intersection(
        {
            "iron_sword",
            "leather_armor",
            "fox_fang",
            "fox_pelt",
            "fox_mask",
            "dragon_claw",
            "dragon_scale",
            "dragon_eye",
            "celestial_blade",
            "void_mantle",
            "xp_amulet",
            "go_stone_black",
        }
    )


def test_c043_purchase_service_acquires_owned_item_without_auto_equip() -> None:
    conn = _connection()
    result = _purchase(conn, "c046-buy-wooden", "shop.static.wooden_sword")
    conn.commit()

    row = conn.execute(
        "SELECT id, equip_id, equipped, canonical_slot, source FROM player_inventory"
    ).fetchone()
    assert row is not None
    assert dict(row) == {
        "id": row["id"],
        "equip_id": "wooden_sword",
        "equipped": 0,
        "canonical_slot": "weapon",
        "source": "coin_shop",
    }
    assert result.item_id == "wooden_sword"
    assert result.coins_after == 700
    assert result.ownership_reference == f"player_inventory:{row['id']}"
    assert AUTO_EQUIP_AFTER_PURCHASE is False


def test_already_owned_rejects_second_operation_without_debit_or_duplicate_row() -> None:
    conn = _connection()
    _purchase(conn, "c046-first", "shop.static.cloth_robe")
    conn.commit()
    before_coins = conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0]

    with pytest.raises(AcquisitionFailed):
        _purchase(conn, "c046-second", "shop.static.cloth_robe")
    conn.rollback()

    assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == before_coins
    assert conn.execute(
        "SELECT COUNT(*) FROM player_inventory WHERE equip_id='cloth_robe'"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM coin_purchase_operations WHERE purchase_operation_id='c046-second'"
    ).fetchone()[0] == 0


def test_insufficient_coins_rolls_back_operation_debit_and_acquisition() -> None:
    conn = _connection(coins=299)
    with pytest.raises(InsufficientCoins):
        _purchase(conn, "c046-insufficient", "shop.static.wooden_sword")
    conn.rollback()

    assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 299
    assert conn.execute("SELECT COUNT(*) FROM player_inventory").fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM coin_purchase_operations WHERE purchase_operation_id='c046-insufficient'"
    ).fetchone()[0] == 0


def test_feature_gates_remain_off_and_source_does_not_wire_app() -> None:
    source = (ROOT / "equipment_shop_offer_authority.py").read_text(encoding="utf-8")
    assert "from app import" not in source
    assert SHOP_ENABLED is False
    assert LOADOUT_ENABLED is False
    assert EQUIPMENT_OFFERS_SOURCE_IMPLEMENTED is True
