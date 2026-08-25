from __future__ import annotations

import sqlite3

import pytest

from coin_purchase_authority import (
    AcquisitionFailed,
    OwnershipAuthorityUnavailable,
    PurchaseOperationConflict,
    SqlAcquisitionAuthority,
    purchase_with_coins,
)
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_purchase_schema
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox_schema
from migrations.equipment_canonical_slot_v1 import (
    upgrade as upgrade_equipment_slot_schema,
    validate_schema as validate_equipment_slot_schema,
)
from shop_offer_authority import StaticShopOfferAuthority


# This is a disposable projection fixture.  The future application boundary
# will build the same shape from the server-owned app.EQUIPMENT_DEFS registry.
SERVER_SLOT_PROJECTION = {
    "wooden_sword": "weapon",
    "cloth_robe": "armor",
    "lucky_stone": "accessory",
}


def _create_runtime(*, with_canonical_slot: bool) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE user_stats ("
        "user_id INTEGER PRIMARY KEY, coins INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE currency_log ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
        "delta INTEGER NOT NULL, balance_after INTEGER NOT NULL, "
        "reason TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE shop_inventory ("
        "user_id INTEGER NOT NULL, item_key TEXT NOT NULL, "
        "qty INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,item_key))"
    )
    conn.execute(
        "CREATE TABLE player_inventory ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
        "equip_id TEXT NOT NULL, equipped INTEGER NOT NULL DEFAULT 0, "
        "obtained_at TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'drop')"
    )
    conn.execute(
        "CREATE TABLE player_wardrobe ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
        "item_id TEXT NOT NULL, obtained_at TEXT NOT NULL, "
        "source TEXT NOT NULL DEFAULT 'drop', UNIQUE(user_id,item_id))"
    )
    upgrade_outbox_schema(conn)
    upgrade_purchase_schema(conn)
    if with_canonical_slot:
        upgrade_equipment_slot_schema(
            conn,
            equipment_defs=(
                {"id": "wooden_sword", "slot": "weapon"},
                {"id": "cloth_robe", "slot": "armor"},
                {"id": "lucky_stone", "slot": "accessory"},
            ),
        )
    conn.commit()
    return conn


def _offer(
    item_id: str,
    acquisition_class: str,
    *,
    offer_id: str | None = None,
    price: int = 10,
    duplicate_policy: str = "ALLOW_DUPLICATE",
    extra: dict | None = None,
) -> StaticShopOfferAuthority:
    mapping = {
        "offer_id": offer_id or f"shop.{item_id}.c023.v1",
        "item_id": item_id,
        "quantity": 1,
        "currency": "COINS",
        "price": price,
        "destination": "player_inventory",
        "acquisition_class": acquisition_class,
        "offer_version": "v1",
        "duplicate_policy": duplicate_policy,
    }
    mapping.update(extra or {})
    return StaticShopOfferAuthority.from_mappings([mapping])


def _seed_user(conn: sqlite3.Connection, *, coins: int = 100) -> None:
    conn.execute("INSERT INTO user_stats(user_id,coins) VALUES(?,?)", (1, coins))
    conn.commit()


def _purchase(
    conn: sqlite3.Connection,
    offers: StaticShopOfferAuthority,
    *,
    operation_id: str,
    offer_id: str,
    source=SERVER_SLOT_PROJECTION,
):
    try:
        result = purchase_with_coins(
            conn,
            1,
            operation_id,
            offer_id,
            offer_authority=offers,
            acquisition_authority=SqlAcquisitionAuthority(
                equipment_slot_source=source,
            ),
        )
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


@pytest.mark.parametrize(
    ("item_id", "acquisition_class", "expected_slot"),
    (
        ("wooden_sword", "WEAPON", "weapon"),
        ("cloth_robe", "ARMOR", "armor"),
        ("lucky_stone", "ACCESSORY", "accessory"),
    ),
)
def test_functional_equipment_writes_server_canonical_slot(
    item_id: str,
    acquisition_class: str,
    expected_slot: str,
):
    conn = _create_runtime(with_canonical_slot=True)
    try:
        _seed_user(conn)
        offer_id = f"shop.{item_id}.slot.v1"
        result = _purchase(
            conn,
            _offer(item_id, acquisition_class, offer_id=offer_id),
            operation_id=f"c023-slot-{item_id}",
            offer_id=offer_id,
        )
        row = conn.execute(
            "SELECT equipped,canonical_slot FROM player_inventory "
            "WHERE user_id=1 AND equip_id=?",
            (item_id,),
        ).fetchone()
        assert result.can_equip is True
        assert row["equipped"] == 0
        assert row["canonical_slot"] == expected_slot
    finally:
        conn.close()


def test_pre_b033_schema_keeps_legacy_insert_shape_without_projection_column():
    conn = _create_runtime(with_canonical_slot=False)
    try:
        _seed_user(conn)
        offer_id = "shop.wooden-sword.pre-b033.v1"
        _purchase(
            conn,
            _offer("wooden_sword", "WEAPON", offer_id=offer_id),
            operation_id="c023-pre-b033",
            offer_id=offer_id,
        )
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(player_inventory)")
        }
        assert "canonical_slot" not in columns
        row = conn.execute(
            "SELECT equipped,source FROM player_inventory WHERE user_id=1"
        ).fetchone()
        assert tuple(row) == (0, "coin_shop")
    finally:
        conn.close()


def test_post_b033_schema_is_valid_and_writer_populates_projection():
    conn = _create_runtime(with_canonical_slot=True)
    try:
        assert validate_equipment_slot_schema(conn)["valid"] is True
        _seed_user(conn)
        offer_id = "shop.cloth-robe.post-b033.v1"
        _purchase(
            conn,
            _offer("cloth_robe", "ARMOR", offer_id=offer_id),
            operation_id="c023-post-b033",
            offer_id=offer_id,
        )
        assert conn.execute(
            "SELECT canonical_slot FROM player_inventory WHERE user_id=1"
        ).fetchone()[0] == "armor"
    finally:
        conn.close()


def test_client_cannot_author_canonical_slot():
    conn = _create_runtime(with_canonical_slot=True)
    try:
        _seed_user(conn)
        offer_id = "shop.wooden-sword.client-slot.v1"
        offers = _offer(
            "wooden_sword",
            "WEAPON",
            offer_id=offer_id,
            extra={
                "presentation_metadata": {"canonical_slot": "armor"},
                "canonical_slot": "armor",
            },
        )
        result = _purchase(
            conn,
            offers,
            operation_id="c023-client-slot",
            offer_id=offer_id,
        )
        assert result.can_equip is True
        assert conn.execute(
            "SELECT canonical_slot FROM player_inventory WHERE user_id=1"
        ).fetchone()[0] == "weapon"
    finally:
        conn.close()


def test_unknown_functional_item_fails_closed_and_rolls_back_everything():
    conn = _create_runtime(with_canonical_slot=True)
    try:
        _seed_user(conn)
        offer_id = "shop.unknown-functional.v1"
        with pytest.raises(AcquisitionFailed):
            _purchase(
                conn,
                _offer("unknown_functional", "WEAPON", offer_id=offer_id),
                operation_id="c023-unknown-functional",
                offer_id=offer_id,
            )
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 100
        assert conn.execute("SELECT COUNT(*) FROM player_inventory").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM currency_log").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM coin_purchase_operations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM domain_event_outbox").fetchone()[0] == 0
    finally:
        conn.close()


@pytest.mark.parametrize("item_id", ("xp_amulet", "go_stone_black"))
def test_locked_equipment_identities_remain_rejected(item_id: str):
    conn = _create_runtime(with_canonical_slot=True)
    try:
        _seed_user(conn)
        offer_id = f"shop.{item_id}.locked.v1"
        with pytest.raises(AcquisitionFailed):
            _purchase(
                conn,
                _offer(
                    item_id,
                    "ACCESSORY" if item_id == "xp_amulet" else "TROPHY",
                    offer_id=offer_id,
                ),
                operation_id=f"c023-locked-{item_id}",
                offer_id=offer_id,
            )
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 100
        assert conn.execute("SELECT COUNT(*) FROM player_inventory").fetchone()[0] == 0
    finally:
        conn.close()


def test_same_operation_replay_and_reject_if_owned_remain_unchanged():
    conn = _create_runtime(with_canonical_slot=True)
    try:
        _seed_user(conn, coins=100)
        replay_offer_id = "shop.wooden-sword.replay.v1"
        offers = _offer(
            "wooden_sword",
            "WEAPON",
            offer_id=replay_offer_id,
            price=25,
        )
        first = _purchase(
            conn,
            offers,
            operation_id="c023-replay",
            offer_id=replay_offer_id,
        )
        replay = _purchase(
            conn,
            offers,
            operation_id="c023-replay",
            offer_id=replay_offer_id,
        )
        assert replay.replayed is True
        assert replay.canonical_payload() == first.canonical_payload()
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 75
        assert conn.execute("SELECT COUNT(*) FROM player_inventory").fetchone()[0] == 1

        reject_offer_id = "shop.cloth-robe.reject.v1"
        reject_offers = _offer(
            "cloth_robe",
            "ARMOR",
            offer_id=reject_offer_id,
            price=10,
            duplicate_policy="REJECT_IF_OWNED",
        )
        _purchase(
            conn,
            reject_offers,
            operation_id="c023-reject-first",
            offer_id=reject_offer_id,
        )
        with pytest.raises(AcquisitionFailed):
            _purchase(
                conn,
                reject_offers,
                operation_id="c023-reject-second",
                offer_id=reject_offer_id,
            )
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 65
        assert conn.execute(
            "SELECT COUNT(*) FROM player_inventory WHERE equip_id='cloth_robe'"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_changed_operation_payload_conflicts_without_mutation():
    conn = _create_runtime(with_canonical_slot=True)
    try:
        _seed_user(conn)
        first_offer_id = "shop.wooden-sword.conflict.v1"
        second_offer_id = "shop.cloth-robe.conflict.v1"
        _purchase(
            conn,
            _offer("wooden_sword", "WEAPON", offer_id=first_offer_id),
            operation_id="c023-conflict",
            offer_id=first_offer_id,
        )
        with pytest.raises(PurchaseOperationConflict):
            _purchase(
                conn,
                _offer("cloth_robe", "ARMOR", offer_id=second_offer_id),
                operation_id="c023-conflict",
                offer_id=second_offer_id,
            )
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 90
        assert conn.execute("SELECT COUNT(*) FROM player_inventory").fetchone()[0] == 1
    finally:
        conn.close()


def test_functional_acquisition_requires_injected_slot_authority():
    conn = _create_runtime(with_canonical_slot=True)
    try:
        _seed_user(conn)
        offer_id = "shop.wooden-sword.no-authority.v1"
        with pytest.raises(OwnershipAuthorityUnavailable):
            try:
                purchase_with_coins(
                    conn,
                    1,
                    "c023-no-slot-authority",
                    offer_id,
                    offer_authority=_offer(
                        "wooden_sword", "WEAPON", offer_id=offer_id
                    ),
                    acquisition_authority=SqlAcquisitionAuthority(),
                )
            finally:
                conn.rollback()
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0] == 100
        assert conn.execute("SELECT COUNT(*) FROM player_inventory").fetchone()[0] == 0
    finally:
        conn.close()
