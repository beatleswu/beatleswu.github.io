"""C029 extension tests for C025 functional Equipment projections."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

import pytest

import shop_acquisition_result_bridge as bridge
from coin_purchase_authority import (
    AcquisitionFailed,
    SqlAcquisitionAuthority,
    purchase_with_coins,
)
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_purchase_operations
from migrations.domain_event_outbox_v1 import upgrade as upgrade_event_outbox
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033
from shop_offer_authority import CoinShopOffer, StaticShopOfferAuthority
from shop_offer_identity_projection import (
    ClientAuthoredInput,
    InvalidServerFacts,
    OfferNotReady,
    UnsupportedDuplicatePolicy,
    UnsupportedServerOffer,
    normalize_shop_offer,
    project_shop_offer,
)


FIXED_NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
SLOT_DEFS = (
    {"id": "iron_sword", "slot": "weapon"},
    {"id": "cloth_robe", "slot": "armor"},
    {"id": "lucky_stone", "slot": "accessory"},
)
SLOT_SOURCE = {
    "iron_sword": "weapon",
    "cloth_robe": "armor",
    "lucky_stone": "accessory",
}


def equipment_facts(
    *,
    item_id: str = "iron_sword",
    acquisition_class: str = "WEAPON",
    duplicate_policy: str = "ALLOW_DUPLICATE",
    quantity: int = 1,
    destination: str = "player_inventory",
    **overrides: object,
) -> dict[str, object]:
    facts: dict[str, object] = {
        "offer_family": "STATIC_SHOP_ITEM",
        "item_key": item_id,
        "item_id": item_id,
        "server_price": 100,
        "quantity": quantity,
        "currency": "COINS",
        "destination": destination,
        "acquisition_class": acquisition_class,
        "duplicate_policy": duplicate_policy,
        "eligibility_reference": f"server:shop_items.{item_id}",
        "price_reference": f"server:shop_items.{item_id}.price",
        "catalog_reference": "server:shop_items",
        "grant_profile": [
            {
                "item_id": item_id,
                "quantity": quantity,
                "destination": destination,
            }
        ],
    }
    facts.update(overrides)
    return facts


def _connection() -> sqlite3.Connection:
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
    conn.execute("INSERT INTO user_stats(user_id, coins) VALUES(1, 1000)")
    conn.commit()
    return conn


def _purchase_from_facts(
    conn: sqlite3.Connection,
    *,
    operation_id: str,
    facts: dict[str, object],
):
    normalized = normalize_shop_offer(facts)
    offer = CoinShopOffer.from_mapping(normalized.as_c019_mapping())
    authority = StaticShopOfferAuthority({offer.offer_id: offer})
    result = purchase_with_coins(
        conn,
        1,
        operation_id,
        offer.offer_id,
        offer_authority=authority,
        acquisition_authority=SqlAcquisitionAuthority(
            equipment_slot_source=SLOT_SOURCE
        ),
        now=FIXED_NOW,
    )
    return normalized, offer, result


@pytest.mark.parametrize(
    ("item_id", "acquisition_class"),
    [
        ("iron_sword", "WEAPON"),
        ("cloth_robe", "ARMOR"),
        ("lucky_stone", "ACCESSORY"),
    ],
)
@pytest.mark.parametrize("duplicate_policy", ["REJECT_IF_OWNED", "ALLOW_DUPLICATE"])
def test_static_functional_equipment_projection_is_ready(
    item_id: str,
    acquisition_class: str,
    duplicate_policy: str,
) -> None:
    offer = normalize_shop_offer(
        equipment_facts(
            item_id=item_id,
            acquisition_class=acquisition_class,
            duplicate_policy=duplicate_policy,
        )
    )

    assert offer.offer_id == f"shop.static.{item_id}"
    assert offer.destination == "player_inventory"
    assert offer.acquisition_class == acquisition_class
    assert offer.quantity == 1
    assert offer.duplicate_policy == duplicate_policy


@pytest.mark.parametrize(
    ("acquisition_class", "item_id"),
    [
        ("TROPHY", "old_trophy"),
        ("COSMETIC", "robe_plain"),
        ("CONSUMABLE", "hint_ticket"),
        ("SPIRIT_CONSUMABLE", "go_spirit_candy"),
        ("XP_CONSUMABLE", "xp_potion"),
        ("MATERIAL", "iron_ore"),
    ],
)
def test_player_inventory_non_equipment_classes_fail_closed(
    acquisition_class: str, item_id: str
) -> None:
    with pytest.raises(UnsupportedServerOffer):
        normalize_shop_offer(
            equipment_facts(
                item_id=item_id,
                acquisition_class=acquisition_class,
            )
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"quantity": 2},
        {"duplicate_policy": "STACK"},
        {"duplicate_policy": "UNSPECIFIED"},
        {"daily": True, "shop_date": "2026-08-25"},
    ],
)
def test_player_inventory_unsupported_shape_is_not_ready(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(
        (UnsupportedServerOffer, UnsupportedDuplicatePolicy, InvalidServerFacts)
    ):
        normalize_shop_offer(equipment_facts(**overrides))


def test_locked_equipment_identities_remain_outside_coin_projection() -> None:
    xp_amulet = project_shop_offer(
        equipment_facts(item_id="xp_amulet", acquisition_class="ACCESSORY")
    )
    go_stone_black = project_shop_offer(
        equipment_facts(item_id="go_stone_black", acquisition_class="TROPHY")
    )

    assert xp_amulet.status == "AUTHORITY_HOLD"
    assert go_stone_black.status == "TROPHY_INVENTORY_ONLY"
    with pytest.raises(OfferNotReady):
        normalize_shop_offer(
            equipment_facts(item_id="xp_amulet", acquisition_class="ACCESSORY")
        )
    with pytest.raises(OfferNotReady):
        normalize_shop_offer(
            equipment_facts(item_id="go_stone_black", acquisition_class="TROPHY")
        )


def test_client_price_and_canonical_slot_cannot_enter_projection() -> None:
    with pytest.raises(ClientAuthoredInput):
        project_shop_offer({**equipment_facts(), "price": 1})
    with pytest.raises(ClientAuthoredInput):
        project_shop_offer({**equipment_facts(), "canonical_slot": "armor"})
    with pytest.raises(ClientAuthoredInput):
        project_shop_offer(
            {
                **equipment_facts(),
                "metadata": {"canonical_slot": "armor"},
            }
        )


def test_equipment_id_and_semantic_version_are_deterministic() -> None:
    first = normalize_shop_offer(equipment_facts())
    same = normalize_shop_offer(equipment_facts())
    changed_price = normalize_shop_offer(equipment_facts(server_price=101))
    changed_semantics = normalize_shop_offer(
        equipment_facts(
            destination="shop_inventory",
            acquisition_class="CONSUMABLE",
            duplicate_policy="STACK",
            grant_profile=[
                {
                    "item_id": "iron_sword",
                    "quantity": 1,
                    "destination": "shop_inventory",
                }
            ],
        )
    )

    assert first.offer_id == same.offer_id == changed_price.offer_id
    assert first.offer_id == "shop.static.iron_sword"
    assert first.offer_version == same.offer_version
    assert first.offer_version != changed_price.offer_version
    assert first.offer_version != changed_semantics.offer_version
    assert first.offer_version.startswith("v1-")


def test_existing_stackable_and_wardrobe_projection_shapes_remain_unchanged() -> None:
    stackable = normalize_shop_offer(
        {
            "offer_family": "STATIC_SHOP_ITEM",
            "item_key": "hint_ticket",
            "item_id": "hint_ticket",
            "server_price": 30,
            "quantity": 1,
            "currency": "COINS",
            "destination": "shop_inventory",
            "acquisition_class": "CONSUMABLE",
            "duplicate_policy": "STACK",
            "eligibility_reference": "server:shop_items.hint_ticket",
            "price_reference": "server:shop_items.hint_ticket.price",
            "catalog_reference": "server:shop_items",
        }
    )
    wardrobe = normalize_shop_offer(
        {
            "offer_family": "EXPLICIT_COIN_COSMETIC",
            "item_id": "robe_plain",
            "product_id": "cosmetic.outfit.robe_plain",
            "server_price": 120,
            "quantity": 1,
            "currency": "COINS",
            "destination": "player_wardrobe",
            "acquisition_class": "COSMETIC",
            "duplicate_policy": "REJECT_IF_OWNED",
            "eligibility_reference": "server:cosmetic_products.robe_plain",
            "price_reference": "server:cosmetic_products.robe_plain.price",
            "catalog_reference": "server:COSMETIC_COMMERCE_PRODUCTS",
        }
    )

    assert stackable.offer_id == "shop.static.hint_ticket"
    assert stackable.destination == "shop_inventory"
    assert stackable.acquisition_class == "CONSUMABLE"
    assert stackable.duplicate_policy == "STACK"
    assert wardrobe.offer_id == "shop.cosmetic.cosmetic.outfit.robe_plain"
    assert wardrobe.destination == "player_wardrobe"
    assert wardrobe.acquisition_class == "COSMETIC"


@pytest.mark.parametrize(
    ("item_id", "acquisition_class"),
    [
        ("iron_sword", "WEAPON"),
        ("cloth_robe", "ARMOR"),
        ("lucky_stone", "ACCESSORY"),
    ],
)
def test_c019_mapping_and_c026_acquisition_accept_all_equipment_classes(
    item_id: str, acquisition_class: str
) -> None:
    conn = _connection()
    normalized, offer, result = _purchase_from_facts(
        conn,
        operation_id=f"op-{item_id}",
        facts=equipment_facts(
            item_id=item_id,
            acquisition_class=acquisition_class,
            duplicate_policy="ALLOW_DUPLICATE",
        ),
    )

    mapped = CoinShopOffer.from_mapping(normalized.as_c019_mapping())
    row = conn.execute(
        "SELECT id, equip_id, equipped, canonical_slot "
        "FROM player_inventory WHERE user_id=1 AND equip_id=?",
        (item_id,),
    ).fetchone()

    assert mapped.destination == "player_inventory"
    assert mapped.acquisition_class == acquisition_class
    assert row is not None
    assert row["id"] > 0
    assert row["equipped"] == 0
    assert row["canonical_slot"] == SLOT_SOURCE[item_id]
    assert result.ownership_reference == f"player_inventory:{row['id']}"
    conn.rollback()


def test_c026_duplicate_policies_preserve_exact_ownership_references() -> None:
    conn = _connection()
    reject_facts = equipment_facts(
        item_id="iron_sword",
        duplicate_policy="REJECT_IF_OWNED",
    )
    _, _, first = _purchase_from_facts(
        conn, operation_id="op-reject-a", facts=reject_facts
    )
    conn.commit()

    with pytest.raises(AcquisitionFailed):
        _purchase_from_facts(conn, operation_id="op-reject-b", facts=reject_facts)
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM player_inventory").fetchone()[0] == 1

    allow_facts = equipment_facts(
        item_id="cloth_robe",
        acquisition_class="ARMOR",
        duplicate_policy="ALLOW_DUPLICATE",
    )
    _, _, second = _purchase_from_facts(
        conn, operation_id="op-allow-a", facts=allow_facts
    )
    conn.commit()
    _, _, third = _purchase_from_facts(
        conn, operation_id="op-allow-b", facts=allow_facts
    )
    conn.commit()
    _, _, replay = _purchase_from_facts(
        conn, operation_id="op-allow-a", facts=allow_facts
    )

    assert second.ownership_reference != third.ownership_reference
    assert replay.replayed is True
    assert replay.ownership_reference == second.ownership_reference
    assert conn.execute(
        "SELECT COUNT(*) FROM player_inventory WHERE equip_id='cloth_robe'"
    ).fetchone()[0] == 2
    conn.rollback()


class _BridgeReadOnlyConnection:
    def __init__(self, raw: sqlite3.Connection) -> None:
        self.raw = raw
        self.statements: list[str] = []

    def execute(self, sql: str, parameters: Any = ()):
        normalized = sql.strip().upper()
        self.statements.append(sql)
        assert not normalized.startswith(
            ("INSERT", "UPDATE", "DELETE", "REPLACE", "ALTER", "DROP", "CREATE")
        )
        assert "FROM PLAYER_INVENTORY" not in normalized
        assert "MAX(" not in normalized
        assert "ORDER BY" not in normalized
        assert "TIMESTAMP" not in normalized
        return self.raw.execute(sql, parameters)

    def commit(self) -> None:
        raise AssertionError("D024 bridge must not commit")

    def rollback(self) -> None:
        raise AssertionError("D024 bridge must not rollback")


def test_d024_adapts_projected_equipment_result_without_identity_lookup() -> None:
    conn = _connection()
    _, _, result = _purchase_from_facts(
        conn,
        operation_id="op-d024-equipment",
        facts=equipment_facts(),
    )
    conn.commit()
    operation = dict(
        conn.execute(
            "SELECT user_id, purchase_operation_id, offer_id, reward_id, "
            "reward_quantity, destination, acquisition_class, operation_status, "
            "lineage_event_id FROM coin_purchase_operations "
            "WHERE user_id=1 AND purchase_operation_id=?",
            (result.operation_id,),
        ).fetchone()
    )
    lineage = dict(
        conn.execute(
            "SELECT event_id, event_type, player_id, payload "
            "FROM domain_event_outbox WHERE event_id=?",
            (result.lineage_event_id,),
        ).fetchone()
    )

    readonly = _BridgeReadOnlyConnection(conn)
    canonical = bridge.adapt_committed_shop_purchase(
        readonly,
        result,
        operation,
        lineage,
    )

    assert canonical.destination == "PLAYER_INVENTORY"
    assert canonical.ownership_reference == result.ownership_reference
    assert readonly.statements == []


def test_c025_projection_module_has_no_downstream_mutation_authority() -> None:
    source = Path(__file__).resolve().parents[1] / "shop_offer_identity_projection.py"
    text = source.read_text(encoding="utf-8")

    assert "purchase_with_coins" not in text
    assert "_spend_coins" not in text
    assert ".execute(" not in text
    assert "import app" not in text
    assert "from app" not in text
    assert "canonical_slot" in text
    assert "ownership_reference" not in text
    assert "commit(" not in text
    assert "rollback(" not in text


def test_current_shop_static_catalog_has_no_functional_equipment_offer_fact() -> None:
    """The contract is ready even though current SHOP_ITEMS has no Equipment sale."""

    app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text(
        encoding="utf-8"
    )
    shop_start = app_source.index("SHOP_ITEMS = {")
    shop_end = app_source.index("\n}\n\n_COIN_DAILY_CAP", shop_start) + 2
    shop_source = app_source[shop_start:shop_end]

    equipment_ids = (
        "wooden_sword",
        "iron_sword",
        "fox_fang",
        "dragon_claw",
        "celestial_blade",
        "cloth_robe",
        "leather_armor",
        "fox_pelt",
        "dragon_scale",
        "void_mantle",
        "lucky_stone",
        "xp_amulet",
        "fox_mask",
        "dragon_eye",
        "go_stone_black",
    )
    assert all(item_id not in shop_source for item_id in equipment_ids)
