"""B023 durable Companion operation and route-authority proofs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
import sqlite3
from threading import Barrier
from urllib.parse import urlsplit

import pytest

from companion_operations import (
    CompanionMutationRejected,
    CompanionOperationConflict,
    execute_companion_operation,
    commit_evolution_transition,
)
from event_outbox import append_event
from item_use_operations import operation_result
from migrations.companion_operations_v1 import (
    downgrade_for_isolated_test as downgrade_companion_schema,
    upgrade as upgrade_companion_schema,
    validate_schema as validate_companion_schema,
)
from migrations.domain_event_outbox_v1 import (
    downgrade_for_isolated_test as downgrade_outbox,
    upgrade as upgrade_outbox,
)
from migrations.item_use_operations_v1 import (
    downgrade_for_isolated_test as downgrade_item_use_schema,
    upgrade as upgrade_item_use_schema,
)
from migrations.spirit_evolution_events_v1 import (
    downgrade_for_isolated_test as downgrade_evolution_schema,
    upgrade as upgrade_evolution_schema,
    validate_schema as validate_evolution_schema,
)


os.environ.setdefault("SECRET_KEY", "b023-companion-test-secret")
import app as app_module  # noqa: E402


class _DbContext:
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


def _create_runtime(path, *, with_companion=True):
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE user_pets(
                user_id INTEGER PRIMARY KEY, pet_key TEXT NOT NULL, nickname TEXT,
                level INTEGER NOT NULL DEFAULT 1, xp INTEGER NOT NULL DEFAULT 0,
                fullness INTEGER NOT NULL DEFAULT 60, affection INTEGER NOT NULL DEFAULT 10,
                selected_at TEXT NOT NULL, last_fed_at TEXT, last_interacted_at TEXT,
                updated_at TEXT, last_pet_at TEXT, last_train_at TEXT, daily_key TEXT,
                daily_bond INTEGER NOT NULL DEFAULT 0,
                daily_train_xp INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE pet_inventory(
                user_id INTEGER NOT NULL, item_key TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,item_key)
            );
            CREATE TABLE pet_action_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                action TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE pet_collection(
                user_id INTEGER NOT NULL, pet_key TEXT NOT NULL, nickname TEXT,
                level INTEGER NOT NULL DEFAULT 1, xp INTEGER NOT NULL DEFAULT 0,
                fullness INTEGER NOT NULL DEFAULT 60, affection INTEGER NOT NULL DEFAULT 10,
                selected_at TEXT NOT NULL, last_fed_at TEXT, last_interacted_at TEXT,
                last_pet_at TEXT, last_train_at TEXT, daily_key TEXT,
                daily_bond INTEGER NOT NULL DEFAULT 0,
                daily_train_xp INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id,pet_key)
            );
            """
        )
        upgrade_outbox(conn)
        upgrade_item_use_schema(conn)
        if with_companion:
            upgrade_companion_schema(conn)
            upgrade_evolution_schema(conn)


def _client():
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "b023-test"
    return client


@pytest.fixture()
def companion_runtime(tmp_path, monkeypatch):
    path = tmp_path / "b023-companion.sqlite"
    _create_runtime(path)
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(path))
    monkeypatch.setitem(app_module.app.config, "TESTING", False)
    monkeypatch.setitem(app_module.app.config, "PROPAGATE_EXCEPTIONS", False)
    monkeypatch.setitem(app_module.app.config, "SESSION_COOKIE_SECURE", False)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO user_pets(user_id,pet_key,nickname,selected_at,updated_at) "
            "VALUES(1,'ink_drop_kelpie','墨滴水靈馬','2026-01-01T00:00:00','2026-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO pet_collection(user_id,pet_key,nickname,selected_at) "
            "VALUES(1,'ink_drop_kelpie','墨滴水靈馬','2026-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO pet_collection(user_id,pet_key,nickname,selected_at) "
            "VALUES(1,'whispering_void_kit','低語虛空貓','2026-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO pet_inventory(user_id,item_key,qty) VALUES(1,'go_spirit_candy',3)"
        )
    return path


def test_additive_migrations_are_idempotent_and_exact(tmp_path):
    path = tmp_path / "schema.sqlite"
    conn = sqlite3.connect(path)
    try:
        first = upgrade_companion_schema(conn)
        second = upgrade_companion_schema(conn)
        evo_first = upgrade_evolution_schema(conn)
        evo_second = upgrade_evolution_schema(conn)
        conn.commit()
        assert first["missing"] == []
        assert second["missing"] == []
        assert evo_first["missing"] == []
        assert evo_second["missing"] == []
        assert validate_companion_schema(conn)["missing"] == []
        assert validate_evolution_schema(conn)["missing"] == []
    finally:
        downgrade_evolution_schema(conn)
        downgrade_companion_schema(conn)
        conn.close()


def test_choose_same_operation_replays_original_result_and_lineage(companion_runtime):
    with sqlite3.connect(companion_runtime) as conn:
        conn.execute("DELETE FROM user_pets")
        conn.execute("DELETE FROM pet_collection")
        conn.execute("DELETE FROM pet_inventory")
    client = _client()
    payload = {"pet_key": "ink_drop_kelpie", "operation_id": "choose-b023-1"}
    first = client.post("/api/pet/choose", json=payload)
    replay = client.post("/api/pet/choose", json=payload)
    assert first.status_code == replay.status_code == 200
    assert first.get_json() == replay.get_json()
    with sqlite3.connect(companion_runtime) as conn:
        assert conn.execute("SELECT COUNT(*) FROM user_pets").fetchone()[0] == 1
        assert conn.execute("SELECT qty FROM pet_inventory WHERE item_key='go_spirit_candy'").fetchone()[0] == 6
        assert conn.execute(
            "SELECT COUNT(*) FROM companion_operations WHERE operation_id='choose-b023-1'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox WHERE idempotency_key LIKE 'spirit-reward:choose-b023-1:%'"
        ).fetchone()[0] == 2


def test_feed_uses_d5c_and_replays_without_second_consume(companion_runtime):
    client = _client()
    payload = {
        "item_key": "go_spirit_candy",
        "spirit_id": "ink_drop_kelpie",
        "operation_id": "feed-b023-1",
    }
    first = client.post("/api/pet/feed", json=payload)
    replay = client.post("/api/pet/feed", json=payload)
    assert first.status_code == replay.status_code == 200
    assert first.get_json() == replay.get_json()
    with sqlite3.connect(companion_runtime) as conn:
        assert conn.execute(
            "SELECT qty FROM pet_inventory WHERE item_key='go_spirit_candy'"
        ).fetchone()[0] == 2
        assert conn.execute(
            "SELECT COUNT(*) FROM item_use_operations WHERE operation_id='feed-b023-1'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM pet_action_log WHERE action='feed'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='ITEM_CONSUME_EFFECT'"
        ).fetchone()[0] == 1

    changed = client.post(
        "/api/pet/feed",
        json={**payload, "item_key": "starfruit"},
    )
    assert changed.status_code == 409


def test_train_and_switch_have_durable_replay(companion_runtime):
    client = _client()
    train_payload = {
        "mode": "train", "hours": 4,
        "spirit_id": "ink_drop_kelpie", "operation_id": "train-b023-1",
    }
    first = client.post("/api/pet/interact", json=train_payload)
    replay = client.post("/api/pet/interact", json=train_payload)
    assert first.status_code == replay.status_code == 200
    assert first.get_json() == replay.get_json()
    with sqlite3.connect(companion_runtime) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM pet_action_log WHERE action='train'"
        ).fetchone()[0] == 1

    switch_payload = {
        "pet_key": "whispering_void_kit", "operation_id": "switch-b023-1",
    }
    switched = client.post("/api/pet/switch", json=switch_payload)
    switched_replay = client.post("/api/pet/switch", json=switch_payload)
    assert switched.status_code == switched_replay.status_code == 200
    assert switched.get_json() == switched_replay.get_json()
    with sqlite3.connect(companion_runtime) as conn:
        assert conn.execute("SELECT pet_key FROM user_pets WHERE user_id=1").fetchone()[0] == "whispering_void_kit"
        assert conn.execute(
            "SELECT COUNT(*) FROM pet_action_log WHERE action='switch'"
        ).fetchone()[0] == 1


def test_existing_three_spirits_keep_unlock_feed_train_switch_contracts(companion_runtime):
    with sqlite3.connect(companion_runtime) as conn:
        conn.execute("UPDATE user_pets SET level=16 WHERE user_id=1")
        conn.execute(
            "UPDATE pet_collection SET level=16 WHERE user_id=1 AND pet_key='ink_drop_kelpie'"
        )
        conn.execute("DELETE FROM pet_collection WHERE pet_key='star_shell_hatchling'")
        conn.execute("UPDATE pet_inventory SET qty=12 WHERE item_key='go_spirit_candy'")
    client = _client()
    unlocked = client.post(
        "/api/pet/unlock",
        json={"pet_key": "star_shell_hatchling", "operation_id": "three-unlock-b023"},
    )
    assert unlocked.status_code == 200

    for index, spirit_id in enumerate((
        "ink_drop_kelpie", "whispering_void_kit", "star_shell_hatchling"
    )):
        switched = client.post(
            "/api/pet/switch",
            json={"pet_key": spirit_id, "operation_id": f"three-switch-{index}"},
        )
        assert switched.status_code == 200
        fed = client.post(
            "/api/pet/feed",
            json={"item_key": "go_spirit_candy", "spirit_id": spirit_id,
                  "operation_id": f"three-feed-{index}"},
        )
        assert fed.status_code == 200
        trained = client.post(
            "/api/pet/interact",
            json={"mode": "train", "hours": 4, "spirit_id": spirit_id,
                  "operation_id": f"three-train-{index}"},
        )
        assert trained.status_code == 200

    with sqlite3.connect(companion_runtime) as conn:
        assert conn.execute("SELECT COUNT(*) FROM pet_collection").fetchone()[0] == 3
        assert conn.execute(
            "SELECT COUNT(*) FROM pet_action_log WHERE action='feed'"
        ).fetchone()[0] == 3
        assert conn.execute(
            "SELECT COUNT(*) FROM pet_action_log WHERE action='train'"
        ).fetchone()[0] == 3
        assert conn.execute(
            "SELECT COUNT(*) FROM pet_action_log WHERE action='switch'"
        ).fetchone()[0] == 2


def test_cross_user_identity_is_not_an_alias_and_evolution_is_durable(companion_runtime):
    def mutation(conn, operation_id):
        conn.execute("INSERT INTO pet_action_log(user_id,action,detail,created_at) VALUES(?,?,?,?)",
                     (1, "probe", operation_id, "2026-01-01T00:00:00"))
        return {"ok": True, "operation_id": operation_id}, 200

    with sqlite3.connect(companion_runtime) as conn:
        request = {
            "user_id": 1, "operation_type": "SPIRIT_SWITCH",
            "operation_id": "cross-user-b023", "spirit_id": "ink_drop_kelpie",
            "payload": {"target_spirit_id": "ink_drop_kelpie"},
        }
        execute_companion_operation(conn, **request, mutation=mutation)
        conn.commit()
        other = {
            **request, "user_id": 2,
        }
        result = execute_companion_operation(conn, **other, mutation=mutation)
        conn.commit()
        assert result.body["operation_id"] == "cross-user-b023"
        assert conn.execute(
            "SELECT COUNT(*) FROM companion_operations WHERE operation_id='cross-user-b023'"
        ).fetchone()[0] == 2

    with sqlite3.connect(companion_runtime) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE user_pets SET level=9 WHERE user_id=1")
        conn.execute("UPDATE pet_collection SET level=9 WHERE user_id=1 AND pet_key='ink_drop_kelpie'")
        result = commit_evolution_transition(
            conn, user_id=1, operation_id="evolve-b023-1",
            spirit_id="ink_drop_kelpie", from_level=9, to_level=10,
            source="server_level_settlement",
        )
        replay = commit_evolution_transition(
            conn, user_id=1, operation_id="evolve-b023-1",
            spirit_id="ink_drop_kelpie", from_level=9, to_level=10,
            source="server_level_settlement",
        )
        conn.commit()
        assert result.body == replay.body
        assert conn.execute("SELECT COUNT(*) FROM spirit_evolution_events").fetchone()[0] == 1


def test_missing_schema_fails_closed_without_mutation(companion_runtime):
    with sqlite3.connect(companion_runtime) as conn:
        conn.execute("DROP TABLE companion_operations")
    response = _client().post(
        "/api/pet/feed",
        json={"item_key": "go_spirit_candy", "operation_id": "old-schema-b023"},
    )
    assert response.status_code == 503
    with sqlite3.connect(companion_runtime) as conn:
        assert conn.execute(
            "SELECT qty FROM pet_inventory WHERE item_key='go_spirit_candy'"
        ).fetchone()[0] == 3


def _pg_url():
    url = os.environ.get("B023_COMPANION_POSTGRES_URL")
    if not url or os.environ.get("B023_COMPANION_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "test" not in database and "b023" not in database and "d5g" not in database:
        pytest.skip("refusing PostgreSQL URL without an explicitly disposable database name")
    return url


def _pg_connection(url):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


class _PgDbContext:
    def __init__(self, url):
        self.url = url
        self.conn = None

    def __enter__(self):
        self.conn = _pg_connection(self.url)
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()


def _create_pg_pet_schema(conn):
    for table in ("spirit_evolution_events", "companion_operations", "domain_event_outbox",
                  "item_use_operations", "pet_action_log", "pet_inventory",
                  "pet_collection", "user_pets"):
        conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    conn.execute(
        """CREATE TABLE user_pets(
             user_id INTEGER PRIMARY KEY, pet_key TEXT NOT NULL, nickname TEXT,
             level INTEGER NOT NULL DEFAULT 1, xp INTEGER NOT NULL DEFAULT 0,
             fullness INTEGER NOT NULL DEFAULT 60, affection INTEGER NOT NULL DEFAULT 10,
             selected_at TEXT NOT NULL, last_fed_at TEXT, last_interacted_at TEXT,
             updated_at TEXT, last_pet_at TEXT, last_train_at TEXT, daily_key TEXT,
             daily_bond INTEGER NOT NULL DEFAULT 0, daily_train_xp INTEGER NOT NULL DEFAULT 0)"""
    )
    conn.execute(
        """CREATE TABLE pet_inventory(
             user_id INTEGER NOT NULL, item_key TEXT NOT NULL, qty INTEGER NOT NULL DEFAULT 0,
             PRIMARY KEY(user_id,item_key))"""
    )
    conn.execute(
        """CREATE TABLE pet_action_log(
             id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL, action TEXT NOT NULL,
             detail TEXT, created_at TEXT NOT NULL)"""
    )
    conn.execute(
        """CREATE TABLE pet_collection(
             user_id INTEGER NOT NULL, pet_key TEXT NOT NULL, nickname TEXT,
             level INTEGER NOT NULL DEFAULT 1, xp INTEGER NOT NULL DEFAULT 0,
             fullness INTEGER NOT NULL DEFAULT 60, affection INTEGER NOT NULL DEFAULT 10,
             selected_at TEXT NOT NULL, last_fed_at TEXT, last_interacted_at TEXT,
             last_pet_at TEXT, last_train_at TEXT, daily_key TEXT,
             daily_bond INTEGER NOT NULL DEFAULT 0, daily_train_xp INTEGER NOT NULL DEFAULT 0,
             PRIMARY KEY(user_id,pet_key))"""
    )
    upgrade_outbox(conn)
    upgrade_item_use_schema(conn)
    upgrade_companion_schema(conn)
    upgrade_evolution_schema(conn)
    conn.execute(
        """INSERT INTO user_pets(
             user_id,pet_key,nickname,level,fullness,affection,selected_at,updated_at)
           VALUES(1,'ink_drop_kelpie','墨滴水靈馬',16,60,10,
                  '2026-01-01T00:00:00','2026-01-01T00:00:00')"""
    )
    for pet_key, level in (("ink_drop_kelpie", 16), ("whispering_void_kit", 1)):
        conn.execute(
            """INSERT INTO pet_collection(
                 user_id,pet_key,nickname,level,selected_at)
               VALUES(?,?,?,?,?)""",
            (1, pet_key, pet_key, level, "2026-01-01T00:00:00"),
        )
    conn.execute(
        "INSERT INTO pet_inventory(user_id,item_key,qty) VALUES(1,'go_spirit_candy',3)"
    )
    conn.commit()


def test_postgres_pet_routes_replay_and_d5_boundaries(monkeypatch):
    url = _pg_url()
    setup = _pg_connection(url)
    try:
        _create_pg_pet_schema(setup)
    finally:
        setup.close()

    monkeypatch.setattr(app_module, "get_db", lambda: _PgDbContext(url))
    monkeypatch.setitem(app_module.app.config, "TESTING", False)
    monkeypatch.setitem(app_module.app.config, "PROPAGATE_EXCEPTIONS", False)
    monkeypatch.setitem(app_module.app.config, "SESSION_COOKIE_SECURE", False)
    client = _client()
    try:
        feed_payload = {
            "item_key": "go_spirit_candy", "spirit_id": "ink_drop_kelpie",
            "operation_id": "pg-feed-b023",
        }
        feed = client.post("/api/pet/feed", json=feed_payload)
        assert feed.status_code == 200
        assert client.post("/api/pet/feed", json=feed_payload).get_json() == feed.get_json()

        train_payload = {
            "mode": "train", "hours": 4, "spirit_id": "ink_drop_kelpie",
            "operation_id": "pg-train-b023",
        }
        train = client.post("/api/pet/interact", json=train_payload)
        assert train.status_code == 200
        assert client.post("/api/pet/interact", json=train_payload).get_json() == train.get_json()

        switch_payload = {"pet_key": "whispering_void_kit", "operation_id": "pg-switch-b023"}
        switched = client.post("/api/pet/switch", json=switch_payload)
        assert switched.status_code == 200
        assert client.post("/api/pet/switch", json=switch_payload).get_json() == switched.get_json()

        unlock_payload = {"pet_key": "star_shell_hatchling", "operation_id": "pg-unlock-b023"}
        unlocked = client.post("/api/pet/unlock", json=unlock_payload)
        assert unlocked.status_code == 200
        assert client.post("/api/pet/unlock", json=unlock_payload).get_json() == unlocked.get_json()
    finally:
        cleanup = _pg_connection(url)
        try:
            for table in ("spirit_evolution_events", "companion_operations", "domain_event_outbox",
                          "item_use_operations", "pet_action_log", "pet_inventory",
                          "pet_collection", "user_pets"):
                cleanup.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            cleanup.commit()
        finally:
            cleanup.close()


def test_postgres_companion_reservation_concurrency_and_rollback():
    url = _pg_url()
    setup = _pg_connection(url)
    try:
        for table in ("spirit_evolution_events", "companion_operations", "domain_event_outbox", "item_use_operations", "b023_probe"):
            setup.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        setup.execute("CREATE TABLE b023_probe(id SERIAL PRIMARY KEY, operation_id TEXT NOT NULL)")
        upgrade_outbox(setup)
        upgrade_item_use_schema(setup)
        upgrade_companion_schema(setup)
        upgrade_evolution_schema(setup)
        assert upgrade_companion_schema(setup)["missing"] == []
        assert upgrade_evolution_schema(setup)["missing"] == []
        setup.commit()
    finally:
        setup.close()

    barrier = Barrier(2)

    def reserve_once():
        conn = _pg_connection(url)
        try:
            barrier.wait(timeout=10)

            def mutation(inner, operation_id):
                inner.execute("INSERT INTO b023_probe(operation_id) VALUES(?)", (operation_id,))
                return {"ok": True, "operation_id": operation_id}, 200

            result = execute_companion_operation(
                conn, user_id=1, operation_type="SPIRIT_TRAIN",
                operation_id="same-pg-operation", spirit_id="ink_drop_kelpie",
                payload={"mode": "train", "hours": 4}, mutation=mutation)
            conn.commit()
            return result
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _unused: reserve_once(), range(2)))
    assert sorted(result.replayed for result in results) == [False, True]

    verify = _pg_connection(url)
    try:
        assert verify.execute(
            "SELECT COUNT(*) FROM companion_operations WHERE user_id=1 AND operation_id='same-pg-operation'"
        ).fetchone()[0] == 1
        assert verify.execute("SELECT COUNT(*) FROM b023_probe").fetchone()[0] == 1
        conflict = None
        try:
            execute_companion_operation(
                verify, user_id=1, operation_type="SPIRIT_TRAIN",
                operation_id="same-pg-operation", spirit_id="ink_drop_kelpie",
                payload={"mode": "train", "hours": 8},
                mutation=lambda _conn, _op: ({"ok": True}, 200),
            )
        except CompanionOperationConflict:
            conflict = True
            verify.rollback()
        assert conflict is True
        try:
            execute_companion_operation(
                verify, user_id=1, operation_type="SPIRIT_TRAIN",
                operation_id="rollback-pg-operation", spirit_id="ink_drop_kelpie",
                payload={"mode": "train", "hours": 4},
                mutation=lambda inner, operation_id: (
                    inner.execute("INSERT INTO b023_probe(operation_id) VALUES(?)", (operation_id,)),
                    (_ for _ in ()).throw(RuntimeError("forced rollback")),
                )[1],
            )
        except RuntimeError:
            verify.rollback()
        assert verify.execute("SELECT COUNT(*) FROM b023_probe").fetchone()[0] == 1
        assert verify.execute(
            "SELECT COUNT(*) FROM companion_operations WHERE operation_id='rollback-pg-operation'"
        ).fetchone()[0] == 0
    finally:
        verify.close()
