"""E030 current-master Shop and Equipment seam integration tests.

These tests exercise the Flask route orchestration around the accepted B034,
B040, C025/C029, C026, and D024 authorities.  They use only disposable
SQLite databases and keep both new runtime gates disabled unless a test
explicitly opts in.
"""

from __future__ import annotations

import json
import datetime
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

import app as app_module
import coin_purchase_authority
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_purchase_operations
from migrations.domain_event_outbox_v1 import upgrade as upgrade_event_outbox
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033
from shop_offer_identity_projection import ServerShopOfferFacts


class _DbContext:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()


def _create_db(
    path: Path,
    *,
    post_b033: bool = False,
    purchase_schema: bool = False,
    include_wardrobe: bool = True,
    include_appearance: bool = False,
    include_shop_inventory: bool = True,
    coins: int = 1000,
) -> None:
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE user_stats ("
            "user_id INTEGER PRIMARY KEY, coins INTEGER NOT NULL, "
            "xp INTEGER NOT NULL DEFAULT 0, rank_level INTEGER NOT NULL DEFAULT 1)"
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
            "obtained_at TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'test')"
        )
        if post_b033:
            upgrade_b033(conn, equipment_defs=app_module.EQUIPMENT_DEFS)
        if include_shop_inventory:
            conn.execute(
                "CREATE TABLE shop_inventory ("
                "user_id INTEGER NOT NULL, item_key TEXT NOT NULL, "
                "qty INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,item_key))"
            )
        if include_wardrobe:
            conn.execute(
                "CREATE TABLE player_wardrobe ("
                "user_id INTEGER NOT NULL, item_id TEXT NOT NULL, "
                "obtained_at TEXT NOT NULL, source TEXT NOT NULL, "
                "PRIMARY KEY(user_id,item_id))"
            )
        if include_appearance:
            conn.execute(
                "CREATE TABLE player_appearance ("
                "user_id INTEGER PRIMARY KEY, outfit_id TEXT, "
                "updated_at TEXT)"
            )
        conn.execute(
            "CREATE TABLE daily_shop ("
            "shop_date TEXT PRIMARY KEY, slots TEXT NOT NULL)"
        )
        if purchase_schema:
            upgrade_purchase_operations(conn)
            upgrade_event_outbox(conn)
        conn.execute("INSERT INTO user_stats(user_id,coins) VALUES(1,?)", (coins,))


def _seed_daily_slots(path: Path, slots: list[dict]) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO daily_shop(shop_date,slots) VALUES(?,?)",
            (datetime.date.today().isoformat(), json.dumps(slots)),
        )


def _client(path: Path, monkeypatch, *, admin: bool = False):
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(path))
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "e030-test"
        if admin:
            session["is_admin"] = True
    return client


def _inventory(path: Path):
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT id,user_id,equip_id,equipped,source "
            "FROM player_inventory ORDER BY id"
        ).fetchall()


def _coins(path: Path) -> int:
    with sqlite3.connect(path) as conn:
        return int(conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0])


def _synthetic_fact(
    item_id: str,
    acquisition_class: str,
    *,
    duplicate_policy: str = "ALLOW_DUPLICATE",
    price: int = 100,
) -> ServerShopOfferFacts:
    return ServerShopOfferFacts(
        offer_family="STATIC_SHOP_ITEM",
        item_key=item_id,
        item_id=item_id,
        server_price=price,
        quantity=1,
        destination="player_inventory",
        acquisition_class=acquisition_class,
        duplicate_policy=duplicate_policy,
        eligibility_reference="e030-test-server-facts",
        price_reference="e030-test-price",
        catalog_reference="e030-test-catalog",
    )


@pytest.mark.parametrize("post_b033", [False, True])
def test_monster_functional_grant_uses_b040_and_preserves_one_row_per_quantity(
    tmp_path, monkeypatch, post_b033
):
    path = tmp_path / ("monster-post.sqlite" if post_b033 else "monster-legacy.sqlite")
    _create_db(path, post_b033=post_b033, include_shop_inventory=False, include_wardrobe=False)
    raw = sqlite3.connect(path)
    raw.row_factory = sqlite3.Row

    identity = SimpleNamespace(
        monster_id="zone_01_monster_01",
        zone_id="zone_01",
        roster_slot=1,
        encounter_class="MONSTER",
        family_id="family_01",
    )
    monkeypatch.setattr(app_module, "canonical_battlefield_identity", lambda *args: identity)
    monkeypatch.setattr(app_module, "build_monster_defeated_event", lambda **kwargs: kwargs)

    def fake_settlement(conn, event, **kwargs):
        return kwargs["grant_functional_item"]("iron_sword", 2, "drop")

    monkeypatch.setattr(app_module, "settle_monster_defeat", fake_settlement)
    result = app_module._settle_monster_defeat_in_tx(
        raw,
        1,
        battlefield={"monster_idx": 1},
        settlement_id="e030-monster-grant",
        hp_before=10,
        hp_after=0,
    )
    raw.commit()
    rows = raw.execute(
        "SELECT id,equip_id,equipped,source "
        "FROM player_inventory ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    assert [(row[1], row[2], row[3]) for row in rows] == [
        ("iron_sword", 0, "drop"),
        ("iron_sword", 0, "drop"),
    ]
    assert result["grant_id"] == f"player_inventory:{rows[-1][0]}"
    if post_b033:
        assert raw.execute(
            "SELECT canonical_slot FROM player_inventory WHERE id=?", (rows[-1][0],)
        ).fetchone()[0] == "weapon"
    raw.close()


@pytest.mark.parametrize("post_b033", [False, True])
def test_admin_equipment_grant_uses_b040_and_preserves_admin_source(
    tmp_path, monkeypatch, post_b033
):
    path = tmp_path / ("admin-post.sqlite" if post_b033 else "admin-legacy.sqlite")
    _create_db(path, post_b033=post_b033, include_shop_inventory=False, include_wardrobe=False)
    client = _client(path, monkeypatch, admin=True)
    response = client.post(
        "/api/admin/users/1/assets/equipment",
        json={"action": "grant", "equip_id": "iron_sword", "canonical_slot": "armor"},
    )
    assert response.status_code == 200
    rows = _inventory(path)
    assert len(rows) == 1
    assert rows[0][2:] == ("iron_sword", 0, "admin")
    if post_b033:
        with sqlite3.connect(path) as conn:
            assert conn.execute(
                "SELECT canonical_slot FROM player_inventory WHERE id=1"
            ).fetchone()[0] == "weapon"


def test_canonical_loadout_route_uses_b034_after_explicit_opt_in(tmp_path, monkeypatch):
    path = tmp_path / "loadout-on.sqlite"
    _create_db(path, post_b033=True, include_shop_inventory=False, include_wardrobe=False)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO player_inventory(user_id,equip_id,equipped,canonical_slot,obtained_at,source) "
            "VALUES(1,'iron_sword',0,NULL,'2026-08-26','test')"
        )
    monkeypatch.setenv(app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG, "1")
    client = _client(path, monkeypatch)
    response = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 1, "action": "equip", "slot": "armor", "equip_id": "xp_amulet"},
    )
    assert response.status_code == 200
    assert response.get_json()["canonical_slot"] == "weapon"
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT equip_id,equipped,canonical_slot FROM player_inventory WHERE id=1"
        ).fetchone()
    assert tuple(row) == ("iron_sword", 1, "weapon")

    response = client.post(
        "/api/player/inventory/equip", json={"inv_id": 1, "action": "unequip"}
    )
    assert response.status_code == 200
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT equipped FROM player_inventory WHERE id=1"
        ).fetchone()[0] == 0


def test_canonical_loadout_gate_on_fails_closed_without_b033_schema(tmp_path, monkeypatch):
    path = tmp_path / "loadout-schema-missing.sqlite"
    _create_db(path, post_b033=False, include_shop_inventory=False, include_wardrobe=False)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO player_inventory(user_id,equip_id,equipped,obtained_at,source) "
            "VALUES(1,'iron_sword',0,'2026-08-26','test')"
        )
    monkeypatch.setenv(app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG, "true")
    client = _client(path, monkeypatch)
    response = client.post(
        "/api/player/inventory/equip", json={"inv_id": 1, "action": "equip"}
    )
    assert response.status_code == 503
    assert response.get_json() == {"error": "SCHEMA_INVARIANT_UNAVAILABLE"}
    assert _inventory(path)[0][3] == 0


@pytest.mark.parametrize(
    ("equip_id", "error"),
    [
        ("xp_amulet", "XP_AMULET_HOLD_FOR_AUTHORITY"),
        ("go_stone_black", "GO_STONE_BLACK_NOT_EQUIPPABLE"),
    ],
)
def test_canonical_loadout_preserves_locked_item_rejections(tmp_path, monkeypatch, equip_id, error):
    path = tmp_path / f"locked-{equip_id}.sqlite"
    _create_db(path, post_b033=True, include_shop_inventory=False, include_wardrobe=False)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO player_inventory(user_id,equip_id,equipped,canonical_slot,obtained_at,source) "
            "VALUES(1,?,0,NULL,'2026-08-26','test')",
            (equip_id,),
        )
    monkeypatch.setenv(app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG, "on")
    client = _client(path, monkeypatch)
    response = client.post(
        "/api/player/inventory/equip", json={"inv_id": 1, "action": "equip"}
    )
    assert response.status_code == 400
    assert response.get_json() == {"error": error}


def test_shop_default_purchase_requires_canonical_operation_authority(tmp_path, monkeypatch):
    path = tmp_path / "shop-off.sqlite"
    _create_db(path, include_wardrobe=False, purchase_schema=False, coins=500)
    monkeypatch.delenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, raising=False)
    client = _client(path, monkeypatch)
    response = client.post(
        "/api/shop/buy",
        json={"item_key": "hint_ticket", "qty": 2, "purchase_operation_id": "c048-no-schema"},
    )
    assert response.status_code == 503
    assert response.get_json() == {
        "error": "schema_unavailable",
        "code": "SCHEMA_UNAVAILABLE",
    }
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='hint_ticket'"
        ).fetchone() is None
        assert not conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='coin_purchase_operations'"
        ).fetchone()


def test_canonical_shop_stackable_purchase_uses_server_facts_and_replays_once(tmp_path, monkeypatch):
    path = tmp_path / "shop-stackable.sqlite"
    _create_db(path, purchase_schema=True, include_wardrobe=False, coins=500)
    _seed_daily_slots(path, [{"type": "item", "item_key": "hint_ticket", "price": 24}])
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    client = _client(path, monkeypatch)
    first = client.post(
        "/api/shop/buy",
        json={
            "item_key": "hint_ticket",
            "purchase_operation_id": "e030-stack-1",
            "qty": 99,
            "price": 1,
            "canonical_slot": "armor",
        },
    )
    assert first.status_code == 200
    first_body = first.get_json()
    assert first_body["coins_spent"] == 24
    assert first_body["quantity"] == 1
    assert first_body["canonical_acquisition_result"]["destination"] == "STACK_INVENTORY"

    second = client.post(
        "/api/shop/buy",
        json={"item_key": "hint_ticket", "purchase_operation_id": "e030-stack-1", "price": 9999},
    )
    assert second.status_code == 200
    assert second.get_json()["replayed"] is True
    assert _coins(path) == 476
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='hint_ticket'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM currency_log WHERE user_id=1 AND delta<0"
        ).fetchone()[0] == 1


def test_canonical_shop_wardrobe_purchase_uses_d024_result(tmp_path, monkeypatch):
    path = tmp_path / "shop-wardrobe.sqlite"
    _create_db(
        path,
        purchase_schema=True,
        include_shop_inventory=False,
        include_appearance=True,
        coins=500,
    )
    _seed_daily_slots(
        path,
        [{
            "type": "appearance",
            "item_key": "robe_plain",
            "cosmetic_id": "robe_plain",
            "product_id": "cosmetic.outfit.robe_plain",
            "price": 200,
        }],
    )
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "true")
    client = _client(path, monkeypatch)
    response = client.post(
        "/api/shop/buy_appearance",
        json={"item_id": "robe_plain", "purchase_operation_id": "e030-wardrobe-1"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["destination"] == "player_wardrobe"
    assert body["canonical_acquisition_result"]["destination"] == "PLAYER_WARDROBE"
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1 AND item_id='robe_plain'"
        ).fetchone()[0] == 1


@pytest.mark.parametrize("item_id,acquisition_class", [("iron_sword", "WEAPON"), ("cloth_robe", "ARMOR"), ("lucky_stone", "ACCESSORY")])
def test_synthetic_functional_equipment_purchase_uses_exact_c026_reference(
    tmp_path, monkeypatch, item_id, acquisition_class
):
    path = tmp_path / f"shop-{item_id}.sqlite"
    _create_db(path, post_b033=True, purchase_schema=True, include_wardrobe=False, coins=500)
    fact = _synthetic_fact(item_id, acquisition_class)
    monkeypatch.setattr(
        app_module,
        "_canonical_shop_offer_facts",
        lambda _conn, *, appearance_only=False: [fact],
    )
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    client = _client(path, monkeypatch)
    response = client.post(
        "/api/shop/buy",
        json={
            "item_key": item_id,
            "purchase_operation_id": f"e030-{item_id}-1",
            "price": 1,
            "canonical_slot": "armor",
            "qty": 10,
        },
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["destination"] == "player_inventory"
    assert body["ownership_reference"].startswith("player_inventory:")
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT id,equip_id,equipped,canonical_slot FROM player_inventory"
        ).fetchone()
    assert body["ownership_reference"] == f"player_inventory:{row[0]}"
    assert tuple(row[1:]) == (item_id, 0, {"iron_sword": "weapon", "cloth_robe": "armor", "lucky_stone": "accessory"}[item_id])


def test_synthetic_allow_duplicate_keeps_distinct_refs_and_stable_replay(tmp_path, monkeypatch):
    path = tmp_path / "shop-duplicate.sqlite"
    _create_db(path, post_b033=True, purchase_schema=True, include_wardrobe=False, coins=500)
    fact = _synthetic_fact("iron_sword", "WEAPON")
    monkeypatch.setattr(
        app_module,
        "_canonical_shop_offer_facts",
        lambda _conn, *, appearance_only=False: [fact],
    )
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    client = _client(path, monkeypatch)
    first = client.post(
        "/api/shop/buy", json={"item_key": "iron_sword", "purchase_operation_id": "e030-dup-a"}
    ).get_json()
    second = client.post(
        "/api/shop/buy", json={"item_key": "iron_sword", "purchase_operation_id": "e030-dup-b"}
    ).get_json()
    replay = client.post(
        "/api/shop/buy", json={"item_key": "iron_sword", "purchase_operation_id": "e030-dup-a"}
    ).get_json()
    assert first["ownership_reference"] != second["ownership_reference"]
    assert replay["ownership_reference"] == first["ownership_reference"]
    assert replay["replayed"] is True
    assert _coins(path) == 300
    assert len(_inventory(path)) == 2


@pytest.mark.parametrize(
    "item_id,acquisition_class,expected_code",
    [
        ("xp_amulet", "ACCESSORY", "AUTHORITY_HOLD"),
        ("go_stone_black", "ACCESSORY", "TROPHY_INVENTORY_ONLY"),
    ],
)
def test_shop_locked_equipment_products_fail_closed_without_debit(
    tmp_path, monkeypatch, item_id, acquisition_class, expected_code
):
    path = tmp_path / f"shop-locked-{item_id}.sqlite"
    _create_db(path, post_b033=True, purchase_schema=True, include_wardrobe=False, coins=500)
    fact = _synthetic_fact(item_id, acquisition_class)
    monkeypatch.setattr(
        app_module,
        "_canonical_shop_offer_facts",
        lambda _conn, *, appearance_only=False: [fact],
    )
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    client = _client(path, monkeypatch)
    response = client.post(
        "/api/shop/buy",
        json={"item_key": item_id, "purchase_operation_id": f"e030-lock-{item_id}"},
    )
    assert response.status_code == 409
    assert response.get_json()["code"] == expected_code
    assert _coins(path) == 500
    assert _inventory(path) == []


def test_shop_post_commit_result_failure_replays_without_second_mutation(tmp_path, monkeypatch):
    path = tmp_path / "shop-post-commit-failure.sqlite"
    _create_db(path, purchase_schema=True, include_wardrobe=False, coins=500)
    _seed_daily_slots(path, [{"type": "item", "item_key": "hint_ticket", "price": 30}])
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    client = _client(path, monkeypatch)
    original_adapter = app_module.adapt_committed_shop_purchase

    def fail_after_commit(*args, **kwargs):
        raise RuntimeError("forced D024 presentation failure")

    monkeypatch.setattr(app_module, "adapt_committed_shop_purchase", fail_after_commit)
    failed = client.post(
        "/api/shop/buy", json={"item_key": "hint_ticket", "purchase_operation_id": "e030-post-commit"}
    )
    assert failed.status_code == 503
    assert failed.get_json()["error"] == "canonical_result_unavailable"

    monkeypatch.setattr(app_module, "adapt_committed_shop_purchase", original_adapter)
    recovered = client.post(
        "/api/shop/buy", json={"item_key": "hint_ticket", "purchase_operation_id": "e030-post-commit"}
    )
    assert recovered.status_code == 200
    assert recovered.get_json()["replayed"] is True
    assert _coins(path) == 470
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='hint_ticket'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM currency_log WHERE user_id=1 AND delta<0"
        ).fetchone()[0] == 1


def test_canonical_shop_insufficient_coins_rolls_back_operation_and_balance(tmp_path, monkeypatch):
    path = tmp_path / "shop-insufficient.sqlite"
    _create_db(path, purchase_schema=True, include_wardrobe=False, coins=10)
    _seed_daily_slots(path, [{"type": "item", "item_key": "hint_ticket", "price": 30}])
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    client = _client(path, monkeypatch)
    response = client.post(
        "/api/shop/buy", json={"item_key": "hint_ticket", "purchase_operation_id": "e030-poor"}
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "INSUFFICIENT_COINS"
    assert _coins(path) == 10
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM coin_purchase_operations"
        ).fetchone()[0] == 0


def test_canonical_shop_requires_existing_stable_operation_identity(tmp_path, monkeypatch):
    path = tmp_path / "shop-operation-identity.sqlite"
    _create_db(path, purchase_schema=True, include_wardrobe=False, coins=500)
    _seed_daily_slots(path, [{"type": "item", "item_key": "hint_ticket", "price": 30}])
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    client = _client(path, monkeypatch)
    response = client.post("/api/shop/buy", json={"item_key": "hint_ticket"})
    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid_operation_identity"}
    assert _coins(path) == 500


def test_canonical_shop_operation_conflict_never_debits_twice(tmp_path, monkeypatch):
    path = tmp_path / "shop-operation-conflict.sqlite"
    _create_db(path, purchase_schema=True, include_wardrobe=False, coins=500)
    _seed_daily_slots(path, [{"type": "item", "item_key": "hint_ticket", "price": 30}])
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    client = _client(path, monkeypatch)
    first = client.post(
        "/api/shop/buy", json={"item_key": "hint_ticket", "purchase_operation_id": "e030-conflict"}
    )
    assert first.status_code == 200
    second = client.post(
        "/api/shop/buy", json={"item_key": "ai_explain_ticket", "purchase_operation_id": "e030-conflict"}
    )
    assert second.status_code == 409
    assert second.get_json()["code"] == "PURCHASE_OPERATION_CONFLICT"
    assert _coins(path) == 470


def test_canonical_shop_d5a_failure_rolls_back_all_mutation(tmp_path, monkeypatch):
    path = tmp_path / "shop-d5a-failure.sqlite"
    _create_db(path, purchase_schema=True, include_wardrobe=False, coins=500)
    _seed_daily_slots(path, [{"type": "item", "item_key": "hint_ticket", "price": 30}])
    monkeypatch.setenv(app_module.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")

    def fail_lineage(*args, **kwargs):
        raise coin_purchase_authority.AcquisitionFailed("forced D5A failure")

    monkeypatch.setattr(coin_purchase_authority, "append_shop_acquisition_lineage", fail_lineage)
    client = _client(path, monkeypatch)
    response = client.post(
        "/api/shop/buy", json={"item_key": "hint_ticket", "purchase_operation_id": "e030-d5a-failure"}
    )
    assert response.status_code == 422
    assert response.get_json()["code"] == "ACQUISITION_FAILED"
    assert _coins(path) == 500
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM shop_inventory").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM coin_purchase_operations").fetchone()[0] == 0


def test_current_real_shop_has_no_functional_equipment_offers():
    equipment_ids = {str(definition["id"]) for definition in app_module.EQUIPMENT_DEFS}
    assert not equipment_ids.intersection(app_module.SHOP_ITEMS)
