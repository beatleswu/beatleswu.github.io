"""Focused XP-consumable runtime contract proofs for B_011.

These tests use disposable SQLite files only to exercise the real Flask shop
use route and its transaction boundaries.  They never touch a repository DB
or Production.  PostgreSQL-specific concurrency evidence remains a separate
runtime report.
"""

import datetime
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "rpg-wave2-xp-consumable-runtime-test-secret")
import app as app_module  # noqa: E402


POTION_IDS = ("small_xp_potion", "xp_potion", "grand_xp_potion")
EXPECTED = {
    "small_xp_potion": (1.25, 20),
    "xp_potion": (1.5, 30),
    "grand_xp_potion": (1.5, 60),
}


class _ShopDbContext:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, timeout=15)
        self.conn.row_factory = sqlite3.Row

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()


def _create_shop_db(path):
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE users(
                id INTEGER PRIMARY KEY,
                plan TEXT NOT NULL DEFAULT 'free',
                premium_until TEXT
            );
            CREATE TABLE shop_inventory(
                user_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                qty INTEGER NOT NULL,
                UNIQUE(user_id, item_key)
            );
            CREATE TABLE active_effects(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                effect_key TEXT NOT NULL,
                value REAL NOT NULL DEFAULT 1,
                expires_at TEXT,
                effect_date TEXT,
                created_at TEXT NOT NULL
            );
            INSERT INTO users(id, plan) VALUES(1, 'free');
            """
        )


def _logged_client():
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "xp-consumable-test"
    return client


def _inventory_state(path, item_key):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        qty = conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key=?",
            (item_key,),
        ).fetchone()
        effects = conn.execute(
            "SELECT * FROM active_effects WHERE user_id=1 AND effect_key='xp_potion' "
            "ORDER BY id"
        ).fetchall()
    return (qty[0] if qty else 0), effects


@pytest.fixture
def shop_runtime(tmp_path, monkeypatch):
    path = tmp_path / "xp-consumable-runtime.sqlite"
    _create_shop_db(path)
    monkeypatch.setattr(app_module, "get_db", lambda: _ShopDbContext(path))
    app_module.app.config.update(
        TESTING=False,
        PROPAGATE_EXCEPTIONS=False,
        SESSION_COOKIE_SECURE=False,
    )
    return path


def test_server_definitions_lock_the_three_product_contracts():
    for item_id, (multiplier, minutes) in EXPECTED.items():
        item = app_module.SHOP_ITEMS[item_id]
        assert item["usable"] == "activate"
        assert item["effect"] == {
            "key": "xp_potion",
            "value": multiplier,
            "minutes": minutes,
        }


@pytest.mark.parametrize("item_id", POTION_IDS)
def test_consume_creates_server_effect_and_persists_across_reload(shop_runtime, item_id):
    path = shop_runtime
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(1,?,1)",
            (item_id,),
        )

    response = _logged_client().post("/api/shop/use", json={"item_key": item_id})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["effect"] == "xp_potion"
    assert payload["value"] == EXPECTED[item_id][0]
    assert payload["remaining"] == 0

    qty, effects = _inventory_state(path, item_id)
    assert qty == 0
    assert len(effects) == 1
    effect = effects[0]
    assert effect["value"] == EXPECTED[item_id][0]
    created = datetime.datetime.fromisoformat(effect["created_at"])
    expires = datetime.datetime.fromisoformat(effect["expires_at"])
    assert expires - created == datetime.timedelta(minutes=EXPECTED[item_id][1])

    # A new client/session reads the same server-side effect row.
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        persisted = app_module._effect_get(conn, 1, "xp_potion")
    assert persisted is not None
    assert float(persisted["value"]) == EXPECTED[item_id][0]


@pytest.mark.parametrize("first_id", POTION_IDS)
@pytest.mark.parametrize("second_id", POTION_IDS)
def test_same_and_cross_potion_use_is_rejected_while_one_effect_is_active(
    shop_runtime, first_id, second_id
):
    path = shop_runtime
    with sqlite3.connect(path) as conn:
        conn.executemany(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(1,?,1)",
            [(first_id,), (second_id,)] if first_id != second_id else [(first_id,)],
        )

    client = _logged_client()
    first = client.post("/api/shop/use", json={"item_key": first_id})
    assert first.status_code == 200

    second = client.post("/api/shop/use", json={"item_key": second_id})
    assert second.status_code == 400
    assert second.get_json()["error"] == "effect_active"

    first_qty, effects = _inventory_state(path, first_id)
    assert first_qty == 0
    assert len(effects) == 1
    if first_id != second_id:
        second_qty, _ = _inventory_state(path, second_id)
        assert second_qty == 1


def test_expiration_is_server_enforced_before_at_and_after_boundary(shop_runtime, monkeypatch):
    path = shop_runtime
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO active_effects(user_id,effect_key,value,expires_at,created_at) "
            "VALUES(1,'xp_potion',1.5,?,?)",
            ("2030-01-01T00:00:01", "2029-12-31T23:59:00"),
        )

    monkeypatch.setattr(app_module, "_now_iso", lambda: "2030-01-01T00:00:00")
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        assert app_module._effect_get(conn, 1, "xp_potion") is not None

    with sqlite3.connect(path) as conn:
        conn.execute(
            "UPDATE active_effects SET expires_at=? WHERE user_id=1",
            ("2030-01-01T00:00:00",),
        )

    # The strict `expires_at > server_now` predicate makes equality expired.
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        assert app_module._effect_get(conn, 1, "xp_potion") is None

    with sqlite3.connect(path) as conn:
        conn.execute(
            "UPDATE active_effects SET expires_at=? WHERE user_id=1",
            ("2029-12-31T23:59:59",),
        )
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        assert app_module._effect_get(conn, 1, "xp_potion") is None


def test_consume_and_effect_creation_roll_back_together_on_effect_failure(shop_runtime, monkeypatch):
    path = shop_runtime
    item_id = "small_xp_potion"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(1,?,1)",
            (item_id,),
        )

    def fail_effect_timestamp():
        raise RuntimeError("simulated effect creation failure")

    monkeypatch.setattr(app_module, "_now_iso", fail_effect_timestamp)
    response = _logged_client().post("/api/shop/use", json={"item_key": item_id})
    assert response.status_code == 500
    qty, effects = _inventory_state(path, item_id)
    assert qty == 1
    assert effects == []


def test_server_ignores_client_effect_values_and_rejects_invalid_or_unowned(shop_runtime):
    client = _logged_client()
    unknown = client.post("/api/shop/use", json={"item_key": "xp_potion_fake"})
    assert unknown.status_code == 400
    assert unknown.get_json()["error"] == "unknown_item"

    not_owned = client.post(
        "/api/shop/use",
        json={"item_key": "small_xp_potion", "value": 999, "minutes": 999},
    )
    assert not_owned.status_code == 400
    assert not_owned.get_json()["error"] == "not_owned"

    with sqlite3.connect(shop_runtime) as conn:
        conn.execute(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(1,'xp_potion',0)"
        )
    zero_quantity = client.post("/api/shop/use", json={"item_key": "xp_potion"})
    assert zero_quantity.status_code == 400
    assert zero_quantity.get_json()["error"] == "not_owned"

    with sqlite3.connect(shop_runtime) as conn:
        conn.execute(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(1,'small_xp_potion',1)"
        )
    forged = client.post(
        "/api/shop/use",
        json={
            "item_key": "small_xp_potion",
            "effect": {"key": "xp_potion", "value": 99, "minutes": 9999},
        },
    )
    assert forged.status_code == 200
    with sqlite3.connect(shop_runtime) as conn:
        row = conn.execute(
            "SELECT value,expires_at,created_at FROM active_effects WHERE user_id=1"
        ).fetchone()
    assert row[0] == 1.25
    assert (
        datetime.datetime.fromisoformat(row[1])
        - datetime.datetime.fromisoformat(row[2])
    ) == datetime.timedelta(minutes=20)


def _concurrent_use(path, item_id, barrier):
    client = _logged_client()
    barrier.wait()
    response = client.post("/api/shop/use", json={"item_key": item_id})
    return response.status_code, response.get_json()


@pytest.mark.parametrize("same_item", [True, False])
def test_concurrent_potion_consumption_has_one_authoritative_activation(shop_runtime, same_item):
    path = shop_runtime
    first_id = "small_xp_potion"
    second_id = first_id if same_item else "xp_potion"
    with sqlite3.connect(path) as conn:
        conn.executemany(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(1,?,1)",
            [(first_id,)] if same_item else [(first_id,), (second_id,)],
        )

    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_concurrent_use, path, first_id, barrier),
            executor.submit(_concurrent_use, path, second_id, barrier),
        ]
        results = [future.result(timeout=20) for future in futures]

    assert sorted(status for status, _ in results) == [200, 400]
    assert sum(status == 200 for status, _ in results) == 1
    with sqlite3.connect(path) as conn:
        effect_count = conn.execute(
            "SELECT COUNT(*) FROM active_effects WHERE user_id=1 AND effect_key='xp_potion'"
        ).fetchone()[0]
        first_qty = conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key=?",
            (first_id,),
        ).fetchone()[0]
        second_row = conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key=?",
            (second_id,),
        ).fetchone()
    assert effect_count == 1
    if same_item:
        assert first_qty == 0
    else:
        assert sorted((first_qty, second_row[0])) == [0, 1]


def test_xp_potion_is_a_single_server_stage_not_a_client_or_second_authority():
    source = Path(app_module.__file__).read_text(encoding="utf-8")
    review_start = source.index("def _srs_review_operation")
    review_end = source.index("def _dispatch_to_srs_review_operation", review_start)
    review_source = source[review_start:review_end]
    assert review_source.count("_effect_get(conn, uid, 'xp_potion')") == 1
    assert "xp_gain = int(xp_gain * float(_potion_factor))" in review_source
    assert "data.get('effect')" not in review_source
    assert "XPSettlement.settle" not in review_source


def test_existing_premium_appearance_xp_and_drop_effects_remain_server_projected():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE user_stats(
            user_id INTEGER PRIMARY KEY,
            go_rank TEXT NOT NULL DEFAULT '30k',
            total_correct INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE player_appearance(
            user_id INTEGER PRIMARY KEY,
            outfit_id TEXT,
            hat_id TEXT,
            back_id TEXT,
            title_id TEXT,
            accessory_id TEXT,
            pet_id TEXT,
            aura_id TEXT
        );
        INSERT INTO user_stats(user_id) VALUES(1);
        INSERT INTO player_appearance(
            user_id,outfit_id,accessory_id,aura_id,pet_id
        ) VALUES(1,'robe_premium','acc_premium','aura_premium','pet_premium');
        """
    )
    assert app_module._get_appearance_effects(1, conn) == {
        "xp_bonus": pytest.approx(0.33),
        "drop_bonus": pytest.approx(0.25),
    }
    conn.close()
