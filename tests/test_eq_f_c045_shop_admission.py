"""EQ-F/SHOP-F proof for the locked C045 six-item Equipment admission."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess
import sqlite3

import pytest

os.environ.setdefault("SECRET_KEY", "eq-f-c045-disposable-test-secret")

import app as app_module  # noqa: E402
import equipment_commerce_service  # noqa: E402
from equipment_shop_eq_f_admission import (  # noqa: E402
    C045_AUTHORITY_COMMIT,
    C045_AUTHORITY_DOCUMENT,
    C045_AUTHORITY_TREE,
    C045_FINAL_COIN_PRICES,
    C045_PRICE_REFERENCES,
    admission_status,
)
from test_c047_equipment_commerce_live_route import (  # noqa: E402
    _coins,
    _inventory,
    _route_fixture,
)


ROOT = Path(__file__).resolve().parents[1]
SHOP_IDS = tuple(C045_FINAL_COIN_PRICES)


def test_c045_artifact_is_exactly_preserved_from_accepted_commit() -> None:
    artifact = ROOT / C045_AUTHORITY_DOCUMENT
    accepted = subprocess.check_output(
        ["git", "show", f"{C045_AUTHORITY_COMMIT}:{C045_AUTHORITY_DOCUMENT}"],
        cwd=ROOT,
    )
    assert artifact.read_bytes() == accepted
    assert C045_AUTHORITY_TREE == "65e20152a2d56e668494aa4ed34901f14d834f32"


def test_c045_admission_is_active_and_exactly_six_server_facts(
    tmp_path, monkeypatch
) -> None:
    path, client = _route_fixture(tmp_path, monkeypatch, coins=5000)
    catalog = client.get("/api/shop/catalog")

    assert catalog.status_code == 200
    offers = catalog.get_json()["equipment_offers"]
    c045 = [offer for offer in offers if offer["item_id"] in SHOP_IDS]
    assert [offer["item_id"] for offer in c045] == list(SHOP_IDS)
    assert [offer["price"] for offer in c045] == [
        C045_FINAL_COIN_PRICES[item_id] for item_id in SHOP_IDS
    ]
    assert all(offer["currency_type"] == "COINS" for offer in c045)
    assert all(offer["destination"] == "player_inventory" for offer in c045)
    assert all(offer["duplicate_policy"] == "REJECT_IF_OWNED" for offer in c045)
    assert admission_status() == {
        "price_authority": "LOCKED_C045",
        "authority_commit": C045_AUTHORITY_COMMIT,
        "authority_tree": C045_AUTHORITY_TREE,
        "authority_document": C045_AUTHORITY_DOCUMENT,
        "active": True,
        "offer_count": 6,
        "item_ids": list(SHOP_IDS),
        "prices": dict(C045_FINAL_COIN_PRICES),
    }
    assert set(C045_PRICE_REFERENCES) == set(SHOP_IDS)


@pytest.mark.parametrize("item_id", SHOP_IDS)
def test_each_c045_sku_uses_server_price_and_permanent_unequipped_ownership(
    tmp_path, monkeypatch, item_id
) -> None:
    price = C045_FINAL_COIN_PRICES[item_id]
    path, client = _route_fixture(tmp_path, monkeypatch, coins=2500)
    response = client.post(
        "/api/shop/buy",
        json={
            "item_id": item_id,
            "purchase_operation_id": f"c045-success-{item_id}",
            "price": 1,
            "coin_cost": 999999,
            "expected_price": 0,
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["coins_spent"] == price
    assert body["coins_after"] == 2500 - price
    assert body["item_id"] == item_id
    assert body["canonical_acquisition_result"]["destination"] == "PLAYER_INVENTORY"
    rows = _inventory(path)
    assert len(rows) == 1
    assert rows[0][2:] == (item_id, 0, "coin_shop")


def test_c045_idempotency_conflict_and_already_owned_are_fail_closed(
    tmp_path, monkeypatch
) -> None:
    path, client = _route_fixture(tmp_path, monkeypatch, coins=2500)
    first = client.post(
        "/api/shop/buy",
        json={
            "item_id": "starglass_needle",
            "purchase_operation_id": "c045-replay",
            "price": 1,
        },
    )
    replay = client.post(
        "/api/shop/buy",
        json={
            "item_id": "starglass_needle",
            "purchase_operation_id": "c045-replay",
            "price": 999999,
        },
    )
    conflict = client.post(
        "/api/shop/buy",
        json={
            "item_id": "mirrorfall_mantle",
            "purchase_operation_id": "c045-replay",
        },
    )
    already_owned = client.post(
        "/api/shop/buy",
        json={
            "item_id": "starglass_needle",
            "purchase_operation_id": "c045-owned-again",
        },
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.get_json()["replayed"] is True
    assert replay.get_json()["coins_spent"] == 1000
    assert conflict.status_code == 409
    assert conflict.get_json()["code"] == "PURCHASE_OPERATION_CONFLICT"
    assert already_owned.status_code == 409
    assert already_owned.get_json()["code"] == "EQUIPMENT_ALREADY_OWNED"
    assert _coins(path) == 1500
    assert len(_inventory(path)) == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM currency_log WHERE delta < 0"
        ).fetchone()[0] == 1


def test_c045_insufficient_coins_and_forced_failure_roll_back(
    tmp_path, monkeypatch
) -> None:
    poor_path, poor_client = _route_fixture(tmp_path, monkeypatch, coins=599)
    poor = poor_client.post(
        "/api/shop/buy",
        json={
            "item_id": "copper_jade_talisman",
            "purchase_operation_id": "c045-poor",
            "price": 1,
        },
    )
    assert poor.status_code == 400
    assert poor.get_json()["code"] == "INSUFFICIENT_COINS"
    assert _coins(poor_path) == 599
    assert _inventory(poor_path) == []

    rollback_root = tmp_path / "rollback"
    rollback_root.mkdir()
    rollback_path, rollback_client = _route_fixture(
        rollback_root, monkeypatch, coins=2500
    )

    def fail_acquisition(*args, **kwargs):
        raise equipment_commerce_service.EquipmentOwnershipError(
            "forced C045 acquisition failure"
        )

    monkeypatch.setattr(
        equipment_commerce_service,
        "grant_equipment_ownership",
        fail_acquisition,
    )
    failed = rollback_client.post(
        "/api/shop/buy",
        json={
            "item_id": "prism_focus_charm",
            "purchase_operation_id": "c045-rollback",
            "price": 1,
        },
    )
    assert failed.status_code == 422
    assert failed.get_json()["code"] == "ACQUISITION_FAILED"
    assert _coins(rollback_path) == 2500
    assert _inventory(rollback_path) == []
    with sqlite3.connect(rollback_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM coin_purchase_operations"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM currency_log WHERE delta < 0"
        ).fetchone()[0] == 0


def test_c045_does_not_change_the_existing_sixteen_sku_shop_surface(
    tmp_path, monkeypatch
) -> None:
    path, client = _route_fixture(tmp_path, monkeypatch, coins=2500)
    body = client.get("/api/shop/catalog").get_json()
    assert {item["key"] for item in body["items"]} == set(app_module.SHOP_ITEMS)
    assert len(body["equipment_offers"]) == 9
    assert {
        offer["item_id"] for offer in body["equipment_offers"]
    } == {
        "wooden_sword",
        "cloth_robe",
        "lucky_stone",
        *SHOP_IDS,
    }
    assert _coins(path) == 2500


def test_c045_price_and_shop_business_logic_is_not_duplicated_in_app() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "C045_FINAL_COIN_PRICES" not in source
    assert "C045_AUTHORITY_COMMIT" not in source


@pytest.fixture(scope="module")
def c045_postgres_database():
    """Opt-in disposable PostgreSQL database for the real Shop transaction."""

    if os.environ.get("EQ_F_C045_RUN_POSTGRES", "") != "1":
        pytest.skip(
            "C045 PostgreSQL proof is explicit; set EQ_F_C045_RUN_POSTGRES=1"
        )
    from postgres_test_harness import disposable_postgres

    with disposable_postgres(name_prefix="eq-f-c045-shop") as record:
        yield record["database_url"]


def _prepare_c045_postgres(database_url: str) -> None:
    from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033
    from test_shop_e_16_sku_end_to_end_acceptance import (
        _connect,
        _reset_disposable_schema,
    )

    _reset_disposable_schema(database_url)
    conn = _connect(database_url)
    try:
        conn.execute(
            """CREATE TABLE public.player_inventory (
                id BIGSERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                equip_id TEXT NOT NULL,
                equipped INTEGER NOT NULL DEFAULT 0,
                obtained_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'test'
            )"""
        )
        app = importlib.import_module("app")
        upgrade_b033(conn, equipment_defs=app.CANONICAL_EQUIPMENT_DEFS)
        conn.commit()
    finally:
        conn.close()


def _c045_postgres_client(database_url: str, monkeypatch):
    from test_shop_e_16_sku_end_to_end_acceptance import _PostgresDbContext

    app = importlib.import_module("app")
    monkeypatch.setenv(app.CANONICAL_COIN_SHOP_PURCHASE_FLAG, "1")
    monkeypatch.setattr(
        app,
        "get_db",
        lambda: _PostgresDbContext(database_url),
    )
    app.app.config.update(TESTING=True)
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "eq-f-c045-postgres"
    return client


def test_c045_postgres_purchase_replay_and_rollback(
    c045_postgres_database, monkeypatch
) -> None:
    from test_shop_e_16_sku_end_to_end_acceptance import _connect

    database_url = c045_postgres_database
    _prepare_c045_postgres(database_url)
    client = _c045_postgres_client(database_url, monkeypatch)

    first = client.post(
        "/api/shop/buy",
        json={
            "item_id": "starglass_needle",
            "purchase_operation_id": "c045-pg-replay",
            "price": 1,
        },
    )
    replay = client.post(
        "/api/shop/buy",
        json={
            "item_id": "starglass_needle",
            "purchase_operation_id": "c045-pg-replay",
            "price": 999999,
        },
    )
    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.get_json()["replayed"] is True
    assert replay.get_json()["coins_spent"] == 1000

    verify = _connect(database_url)
    try:
        assert verify.execute(
            "SELECT coins FROM public.user_stats WHERE user_id=1"
        ).fetchone()[0] == 999000
        assert verify.execute(
            "SELECT COUNT(*) FROM public.player_inventory WHERE user_id=1"
        ).fetchone()[0] == 1
        assert verify.execute(
            "SELECT equipped FROM public.player_inventory WHERE user_id=1"
        ).fetchone()[0] == 0
        assert verify.execute(
            "SELECT COUNT(*) FROM public.coin_purchase_operations "
            "WHERE purchase_operation_id='c045-pg-replay'"
        ).fetchone()[0] == 1
    finally:
        verify.rollback()
        verify.close()

    def fail_acquisition(*args, **kwargs):
        raise equipment_commerce_service.EquipmentOwnershipError(
            "forced C045 PostgreSQL acquisition failure"
        )

    monkeypatch.setattr(
        equipment_commerce_service,
        "grant_equipment_ownership",
        fail_acquisition,
    )
    failed = client.post(
        "/api/shop/buy",
        json={
            "item_id": "emberline_cutlass",
            "purchase_operation_id": "c045-pg-rollback",
            "price": 1,
        },
    )
    assert failed.status_code == 422

    verify = _connect(database_url)
    try:
        assert verify.execute(
            "SELECT coins FROM public.user_stats WHERE user_id=1"
        ).fetchone()[0] == 999000
        assert verify.execute(
            "SELECT COUNT(*) FROM public.player_inventory WHERE user_id=1"
        ).fetchone()[0] == 1
        assert verify.execute(
            "SELECT COUNT(*) FROM public.coin_purchase_operations "
            "WHERE purchase_operation_id='c045-pg-rollback'"
        ).fetchone()[0] == 0
    finally:
        verify.rollback()
        verify.close()
