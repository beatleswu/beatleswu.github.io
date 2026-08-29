"""Focused D5C proofs for durable item-use identity and scoped lineage.

The Flask tests use disposable SQLite files. PostgreSQL tests are enabled only
with an explicitly marked disposable URL and exercise the database's
concurrency/transaction semantics directly. No repository or Production DB is
used.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import datetime
import os
import sqlite3
import threading
from urllib.parse import urlsplit

import pytest

from event_outbox import append_event
from item_use_operations import (
    ItemUseOperationConflict,
    canonical_item_use_request,
    complete_item_use_operation,
    operation_result,
    reserve_item_use_operation,
)
from migrations.domain_event_outbox_v1 import (
    downgrade_for_isolated_test as downgrade_outbox,
    upgrade as upgrade_outbox,
    validate_schema as validate_outbox_schema,
)
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_purchase_operations
from migrations.item_use_operations_v1 import (
    downgrade_for_isolated_test as downgrade_item_use_schema,
    upgrade as upgrade_item_use_schema,
    validate_schema as validate_item_use_schema,
)


os.environ.setdefault("SECRET_KEY", "d5c-item-use-lineage-test-secret")
import app as app_module  # noqa: E402


POTIONS = {
    "small_xp_potion": (1.25, 20),
    "xp_potion": (1.5, 30),
    "grand_xp_potion": (1.5, 60),
}


class _ShopDbContext:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, timeout=20, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()


def _create_sqlite_runtime(path):
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE users(
                id INTEGER PRIMARY KEY,
                plan TEXT NOT NULL DEFAULT 'free',
                premium_until TEXT
            );
            CREATE TABLE user_stats(
                user_id INTEGER PRIMARY KEY,
                coins INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE currency_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE shop_inventory(
                user_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                qty INTEGER NOT NULL,
                PRIMARY KEY(user_id, item_key)
            );
            CREATE TABLE daily_shop(
                shop_date TEXT PRIMARY KEY,
                slots TEXT NOT NULL
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
            CREATE TABLE player_wardrobe(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                obtained_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'drop',
                UNIQUE(user_id, item_id)
            );
            CREATE TABLE player_appearance(
                user_id INTEGER PRIMARY KEY,
                outfit_id TEXT,
                hat_id TEXT,
                back_id TEXT,
                title_id TEXT,
                accessory_id TEXT,
                pet_id TEXT,
                aura_id TEXT,
                updated_at TEXT
            );
            INSERT INTO users(id, plan) VALUES(1, 'free');
            INSERT INTO user_stats(user_id, coins) VALUES(1, 500);
            """
        )
        upgrade_outbox(conn)
        upgrade_purchase_operations(conn)
        upgrade_item_use_schema(conn)


def _logged_client():
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "d5c-item-use-test"
    return client


@pytest.fixture()
def shop_runtime(tmp_path, monkeypatch):
    path = tmp_path / "d5c-item-use.sqlite"
    _create_sqlite_runtime(path)
    monkeypatch.setattr(app_module, "get_db", lambda: _ShopDbContext(path))
    monkeypatch.setitem(app_module.app.config, "TESTING", False)
    monkeypatch.setitem(app_module.app.config, "PROPAGATE_EXCEPTIONS", False)
    monkeypatch.setitem(app_module.app.config, "SESSION_COOKIE_SECURE", False)
    return path


def _item_request(item_id, *, value=None, minutes=None):
    return canonical_item_use_request(
        item_id=item_id,
        effect_key="xp_potion",
        effect_value=value,
        effect_minutes=minutes,
    )


def test_sqlite_schema_and_outbox_contract():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        upgrade_outbox(conn)
        upgrade_item_use_schema(conn)
        assert validate_outbox_schema(conn)["missing"] == []
        assert validate_item_use_schema(conn)["missing"] == []
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(item_use_operations)")
        }
        assert columns == {
            "operation_id",
            "player_id",
            "operation_family",
            "item_id",
            "request_fingerprint",
            "operation_status",
            "result_payload",
            "created_at",
            "committed_at",
        }
    finally:
        downgrade_item_use_schema(conn)
        downgrade_outbox(conn)
        conn.close()


@pytest.mark.parametrize("item_id", tuple(POTIONS))
def test_each_xp_potion_uses_server_definition_and_writes_lineage(shop_runtime, item_id):
    with sqlite3.connect(shop_runtime) as conn:
        conn.execute(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(1,?,1)",
            (item_id,),
        )

    response = _logged_client().post(
        "/api/shop/use",
        json={"item_key": item_id, "operation_id": f"{item_id}-op"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["effect"] == "xp_potion"
    assert body["value"] == POTIONS[item_id][0]
    assert body["remaining"] == 0
    assert body["operation_status"] == "SUCCESS"
    assert body["consume_event_id"]

    with sqlite3.connect(shop_runtime) as conn:
        conn.row_factory = sqlite3.Row
        effect = conn.execute(
            "SELECT * FROM active_effects WHERE user_id=1 AND effect_key='xp_potion'"
        ).fetchone()
        operation = conn.execute(
            "SELECT * FROM item_use_operations WHERE player_id=1 AND operation_id=?",
            (f"{item_id}-op",),
        ).fetchone()
        event = conn.execute(
            "SELECT * FROM domain_event_outbox WHERE player_id='1' "
            "AND event_type='ITEM_CONSUME_EFFECT'",
        ).fetchone()
    assert effect is not None
    assert operation["operation_status"] == "SUCCESS"
    assert operation["item_id"] == item_id
    assert event is not None
    assert event["published_at"] is None


def test_same_operation_retry_replays_without_second_mutation_or_event(shop_runtime):
    item_id = "xp_potion"
    with sqlite3.connect(shop_runtime) as conn:
        conn.execute(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(1,?,2)",
            (item_id,),
        )

    client = _logged_client()
    first = client.post(
        "/api/shop/use", json={"item_key": item_id, "operation_id": "retry-op"}
    )
    retry = client.post(
        "/api/shop/use", json={"item_key": item_id, "operation_id": "retry-op"}
    )
    assert first.status_code == retry.status_code == 200
    first_body = first.get_json()
    retry_body = retry.get_json()
    assert retry_body["operation_duplicate"] is True
    assert retry_body["effect_id"] == first_body["effect_id"]
    assert retry_body["consume_event_id"] == first_body["consume_event_id"]
    assert retry_body["remaining"] == 1

    with sqlite3.connect(shop_runtime) as conn:
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key=?",
            (item_id,),
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM active_effects WHERE user_id=1"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM item_use_operations WHERE player_id=1"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='ITEM_CONSUME_EFFECT'"
        ).fetchone()[0] == 1


def test_same_operation_different_item_is_conflict_and_other_player_isolated(shop_runtime):
    with sqlite3.connect(shop_runtime) as conn:
        conn.executemany(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(1,?,1)",
            [("xp_potion",), ("small_xp_potion",)],
        )
    client = _logged_client()
    assert client.post(
        "/api/shop/use", json={"item_key": "xp_potion", "operation_id": "shared-op"}
    ).status_code == 200
    conflict = client.post(
        "/api/shop/use",
        json={"item_key": "small_xp_potion", "operation_id": "shared-op"},
    )
    assert conflict.status_code == 409
    assert conflict.get_json()["error"] == "idempotency_conflict"

    # The DB identity includes player_id; this direct reservation proof does
    # not alias a second authenticated player to player 1's result.
    with sqlite3.connect(shop_runtime) as conn:
        conn.row_factory = sqlite3.Row
        payload = _item_request("xp_potion", value=1.5, minutes=30)
        with pytest.raises(ItemUseOperationConflict):
            reserve_item_use_operation(
                conn,
                player_id=1,
                operation_id="shared-op",
                item_id="xp_potion",
                request_payload=_item_request("xp_potion", value=1.25, minutes=20),
            )
        other = reserve_item_use_operation(
            conn,
            player_id=2,
            operation_id="shared-op",
            item_id="xp_potion",
            request_payload=payload,
        )
        assert other["inserted"] is True
        conn.rollback()


def test_new_operation_while_active_is_committed_rejection_and_retry_is_stable(shop_runtime):
    with sqlite3.connect(shop_runtime) as conn:
        conn.executemany(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(1,?,1)",
            [("xp_potion",), ("small_xp_potion",)],
        )
    client = _logged_client()
    assert client.post(
        "/api/shop/use", json={"item_key": "xp_potion", "operation_id": "active-op"}
    ).status_code == 200
    rejected = client.post(
        "/api/shop/use",
        json={"item_key": "small_xp_potion", "operation_id": "new-op"},
    )
    replay = client.post(
        "/api/shop/use",
        json={"item_key": "small_xp_potion", "operation_id": "new-op"},
    )
    assert rejected.status_code == replay.status_code == 400
    assert rejected.get_json()["error"] == "effect_active"
    assert replay.get_json()["operation_duplicate"] is True
    with sqlite3.connect(shop_runtime) as conn:
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='small_xp_potion'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT operation_status FROM item_use_operations "
            "WHERE player_id=1 AND operation_id='new-op'"
        ).fetchone()[0] == "REJECTED"
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='ITEM_CONSUME_EFFECT'"
        ).fetchone()[0] == 1


def test_item_use_and_event_roll_back_together_on_infrastructure_failure(shop_runtime, monkeypatch):
    with sqlite3.connect(shop_runtime) as conn:
        conn.execute(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(1,'xp_potion',1)"
        )

    def fail_event(*args, **kwargs):
        raise RuntimeError("forced D5C event failure")

    monkeypatch.setattr(app_module, "append_event", fail_event)
    response = _logged_client().post(
        "/api/shop/use", json={"item_key": "xp_potion", "operation_id": "rollback-op"}
    )
    assert response.status_code == 500
    with sqlite3.connect(shop_runtime) as conn:
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='xp_potion'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM active_effects WHERE user_id=1"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM item_use_operations WHERE player_id=1"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox"
        ).fetchone()[0] == 0


def test_new_operation_after_effect_expiry_is_a_new_committed_use(shop_runtime):
    with sqlite3.connect(shop_runtime) as conn:
        conn.executemany(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(1,?,1)",
            [("xp_potion",), ("small_xp_potion",)],
        )
    client = _logged_client()
    first = client.post(
        "/api/shop/use", json={"item_key": "xp_potion", "operation_id": "expired-first"}
    )
    assert first.status_code == 200
    with sqlite3.connect(shop_runtime) as conn:
        conn.execute(
            "UPDATE active_effects SET expires_at='2000-01-01T00:00:00' "
            "WHERE user_id=1 AND effect_key='xp_potion'"
        )
    second = client.post(
        "/api/shop/use",
        json={"item_key": "small_xp_potion", "operation_id": "expired-second"},
    )
    assert second.status_code == 200
    with sqlite3.connect(shop_runtime) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM item_use_operations WHERE player_id=1"
        ).fetchone()[0] == 2
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='ITEM_CONSUME_EFFECT'"
        ).fetchone()[0] == 2


def test_cosmetic_purchase_emits_scoped_acquisition_evidence_without_owning_from_event(shop_runtime):
    client = _logged_client()
    first = client.post(
        "/api/cosmetic-commerce/purchase",
        json={
            "product_id": "cosmetic.outfit.robe_plain",
            "purchase_operation_id": "d5c-cosmetic-first",
        },
    )
    assert first.status_code == 200
    second = client.post(
        "/api/cosmetic-commerce/purchase",
        json={
            "product_id": "cosmetic.outfit.robe_plain",
            "purchase_operation_id": "d5c-cosmetic-second",
        },
    )
    assert second.status_code == 200
    assert second.get_json()["status"] == "already_owned"
    with sqlite3.connect(shop_runtime) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute(
            "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1 AND item_id='robe_plain'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=1"
        ).fetchone()[0] == 300
        event = conn.execute(
            "SELECT event_type, outcome, payload FROM domain_event_outbox "
            "WHERE event_type='ITEM_ACQUISITION'"
        ).fetchone()
    assert event is not None
    assert event["outcome"] == "SUCCESS"
    assert "player_wardrobe" in event["payload"]


def _pg_url():
    url = os.environ.get("D5C_ITEM_LINEAGE_POSTGRES_URL")
    if not url or os.environ.get("D5C_ITEM_LINEAGE_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "test" not in database and "d5c" not in database:
        pytest.skip("refusing PostgreSQL URL without a test/d5c database name")
    return url


def _pg_connection(url):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def _create_pg_schema(conn):
    conn.execute("DROP TABLE IF EXISTS domain_event_outbox CASCADE")
    conn.execute("DROP TABLE IF EXISTS item_use_operations CASCADE")
    conn.execute("DROP TABLE IF EXISTS active_effects CASCADE")
    conn.execute("DROP TABLE IF EXISTS shop_inventory CASCADE")
    conn.execute(
        """CREATE TABLE shop_inventory(
               user_id INTEGER NOT NULL, item_key TEXT NOT NULL,
               qty INTEGER NOT NULL, PRIMARY KEY(user_id,item_key))"""
    )
    conn.execute(
        """CREATE TABLE active_effects(
               id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL,
               effect_key TEXT NOT NULL, value REAL NOT NULL DEFAULT 1,
               expires_at TEXT, effect_date TEXT, created_at TEXT NOT NULL)"""
    )
    upgrade_outbox(conn)
    upgrade_item_use_schema(conn)
    conn.commit()


def _pg_item_use_transaction(conn, player_id, operation_id, item_id):
    request_payload = _item_request(item_id, value=1.5, minutes=30)
    reservation = reserve_item_use_operation(
        conn,
        player_id=player_id,
        operation_id=operation_id,
        item_id=item_id,
        request_payload=request_payload,
    )
    if reservation["duplicate"]:
        conn.commit()
        result = operation_result(reservation["operation"])
        result["operation_duplicate"] = True
        return result

    updated = conn.execute(
        "UPDATE shop_inventory SET qty=qty-1 "
        "WHERE user_id=? AND item_key=? AND qty>0",
        (player_id, item_id),
    )
    if updated.rowcount != 1:
        result = {
            "ok": False,
            "error": "not_owned",
            "operation_id": operation_id,
            "operation_status": "REJECTED",
        }
        complete_item_use_operation(
            conn,
            player_id=player_id,
            operation_id=operation_id,
            operation_status="REJECTED",
            result_payload=result,
        )
        conn.commit()
        return result
    effect = conn.execute(
        "INSERT INTO active_effects(user_id,effect_key,value,expires_at,created_at) "
        "VALUES(?,?,?,?,?) RETURNING id",
        (player_id, "xp_potion", 1.5, "2030-01-01T00:30:00", "2030-01-01T00:00:00"),
    ).fetchone()
    remaining = conn.execute(
        "SELECT qty FROM shop_inventory WHERE user_id=? AND item_key=?",
        (player_id, item_id),
    ).fetchone()["qty"]
    event = append_event(
        conn,
        event_type="ITEM_CONSUME_EFFECT",
        player_id=str(player_id),
        lineage_id=operation_id,
        source_event_id=f"item_use_operations:{player_id}:{operation_id}",
        idempotency_key=f"item-consume-effect:{operation_id}",
        outcome="SUCCESS",
        payload={
            "operation": "CONSUME_EFFECT",
            "operation_id": operation_id,
            "item_id": item_id,
            "quantity_delta": -1,
            "resulting_quantity": remaining,
            "effect_id": effect["id"],
            "effect_type": "xp_potion",
        },
    )
    result = {
        "ok": True,
        "operation_id": operation_id,
        "operation_status": "SUCCESS",
        "effect_id": effect["id"],
        "consume_event_id": event["event_id"],
        "remaining": remaining,
    }
    complete_item_use_operation(
        conn,
        player_id=player_id,
        operation_id=operation_id,
        operation_status="SUCCESS",
        result_payload=result,
    )
    conn.commit()
    return result


def test_postgres_concurrent_same_operation_has_one_mutation_and_one_event():
    url = _pg_url()
    setup = _pg_connection(url)
    try:
        _create_pg_schema(setup)
        setup.execute(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(1,'xp_potion',1)"
        )
        setup.commit()
    finally:
        setup.close()

    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        conn = _pg_connection(url)
        try:
            barrier.wait(timeout=15)
            results.append(_pg_item_use_transaction(conn, 1, "pg-same-op", "xp_potion"))
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(worker) for _ in range(2)]
        for future in futures:
            future.result(timeout=30)
    assert not errors
    assert len(results) == 2
    assert sorted(bool(result.get("operation_duplicate")) for result in results) == [False, True]

    verify = _pg_connection(url)
    try:
        assert verify.execute(
            "SELECT COUNT(*) AS n FROM item_use_operations "
            "WHERE player_id=1 AND operation_id='pg-same-op'"
        ).fetchone()["n"] == 1
        assert verify.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='xp_potion'"
        ).fetchone()["qty"] == 0
        assert verify.execute(
            "SELECT COUNT(*) AS n FROM active_effects WHERE user_id=1"
        ).fetchone()["n"] == 1
        assert verify.execute(
            "SELECT COUNT(*) AS n FROM domain_event_outbox "
            "WHERE player_id='1' AND event_type='ITEM_CONSUME_EFFECT'"
        ).fetchone()["n"] == 1
    finally:
        verify.execute("DROP TABLE IF EXISTS domain_event_outbox CASCADE")
        verify.execute("DROP TABLE IF EXISTS item_use_operations CASCADE")
        verify.execute("DROP TABLE IF EXISTS active_effects CASCADE")
        verify.execute("DROP TABLE IF EXISTS shop_inventory CASCADE")
        verify.commit()
        verify.close()


def test_postgres_conflict_and_atomic_rollback():
    url = _pg_url()
    conn = _pg_connection(url)
    try:
        _create_pg_schema(conn)
        conn.execute(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(1,'xp_potion',1)"
        )
        conn.commit()
        payload = _item_request("xp_potion", value=1.5, minutes=30)
        first = reserve_item_use_operation(
            conn,
            player_id=1,
            operation_id="pg-conflict",
            item_id="xp_potion",
            request_payload=payload,
        )
        assert first["inserted"] is True
        with pytest.raises(ItemUseOperationConflict):
            reserve_item_use_operation(
                conn,
                player_id=1,
                operation_id="pg-conflict",
                item_id="small_xp_potion",
                request_payload=_item_request("small_xp_potion", value=1.25, minutes=20),
            )
        # The ON CONFLICT reservation path does not abort the outer transaction.
        other = reserve_item_use_operation(
            conn,
            player_id=2,
            operation_id="pg-conflict",
            item_id="xp_potion",
            request_payload=payload,
        )
        assert other["inserted"] is True
        conn.rollback()

        conn.execute(
            "UPDATE shop_inventory SET qty=1 WHERE user_id=1 AND item_key='xp_potion'"
        )
        conn.commit()
        reservation = reserve_item_use_operation(
            conn,
            player_id=1,
            operation_id="pg-rollback",
            item_id="xp_potion",
            request_payload=payload,
        )
        assert reservation["inserted"] is True
        conn.execute(
            "UPDATE shop_inventory SET qty=qty-1 WHERE user_id=1 AND item_key='xp_potion'"
        )
        conn.execute(
            "INSERT INTO active_effects(user_id,effect_key,value,created_at) "
            "VALUES(1,'xp_potion',1.5,'2030-01-01T00:00:00')"
        )
        append_event(
            conn,
            event_type="ITEM_CONSUME_EFFECT",
            player_id="1",
            lineage_id="pg-rollback",
            source_event_id="item_use_operations:1:pg-rollback",
            idempotency_key="item-consume-effect:pg-rollback",
            outcome="SUCCESS",
            payload={"operation_id": "pg-rollback", "item_id": "xp_potion"},
        )
        conn.rollback()
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM item_use_operations WHERE operation_id='pg-rollback'"
        ).fetchone()["n"] == 0
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='xp_potion'"
        ).fetchone()["qty"] == 1
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM domain_event_outbox"
        ).fetchone()["n"] == 0
    finally:
        try:
            conn.rollback()
            downgrade_item_use_schema(conn)
            downgrade_outbox(conn)
            conn.execute("DROP TABLE IF EXISTS active_effects CASCADE")
            conn.execute("DROP TABLE IF EXISTS shop_inventory CASCADE")
            conn.commit()
        finally:
            conn.close()
