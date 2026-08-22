"""Optional D008 acceptance against an explicitly disposable PostgreSQL."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from urllib.parse import urlsplit

import pytest

from companion_operations import commit_evolution_transition
from migrations.companion_operations_v1 import upgrade as upgrade_companion_schema
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from migrations.item_use_operations_v1 import upgrade as upgrade_item_use_schema
from migrations.spirit_evolution_events_v1 import upgrade as upgrade_evolution_schema
from spirit_runtime import build_b022_active_spirit_projection


def _postgres_url():
    url = os.environ.get("D008_SPIRIT_POSTGRES_URL")
    if not url or os.environ.get("D008_SPIRIT_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if not any(token in database for token in ("test", "d008", "d5g")):
        pytest.skip("refusing PostgreSQL URL without an explicitly disposable database name")
    return url


def _connect(url):
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
        self.conn = _connect(self.url)
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()


def _create_schema(url):
    conn = _connect(url)
    try:
        for table in (
            "spirit_evolution_events", "companion_operations", "domain_event_outbox",
            "item_use_operations", "pet_action_log", "pet_inventory",
            "pet_collection", "user_pets",
        ):
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
                 user_id INTEGER NOT NULL, item_key TEXT NOT NULL,
                 qty INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,item_key))"""
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
                 user_id,pet_key,nickname,level,xp,fullness,affection,selected_at,updated_at)
               VALUES(1,'starpath_antlerling','Starpath Antlerling',9,0,60,10,
                      '2026-01-01T00:00:00','2026-01-01T00:00:00')"""
        )
        for spirit_id, level in (
            ("ink_drop_kelpie", 16),
            ("whispering_void_kit", 1),
            ("star_shell_hatchling", 1),
            ("starpath_antlerling", 9),
        ):
            conn.execute(
                """INSERT INTO pet_collection(
                     user_id,pet_key,nickname,level,xp,fullness,affection,selected_at)
                   VALUES(%s,%s,%s,%s,0,60,10,'2026-01-01T00:00:00')""",
                (1, spirit_id, spirit_id, level),
            )
        conn.execute(
            "INSERT INTO pet_inventory(user_id,item_key,qty) VALUES(1,'go_spirit_candy',2)"
        )
        conn.commit()
    finally:
        conn.close()


def test_postgres_six_spirit_projection_is_transactional_and_rehydratable():
    url = _postgres_url()
    _create_schema(url)
    conn = _connect(url)
    try:
        projection = build_b022_active_spirit_projection(conn, 1)
        assert projection["active_spirit_id"] == "starpath_antlerling"
        assert projection["ownership_validated"] is True
        conn.commit()
    finally:
        conn.close()
    fresh = _connect(url)
    try:
        assert build_b022_active_spirit_projection(fresh, 1)["active_spirit_id"] == (
            "starpath_antlerling"
        )
    finally:
        fresh.close()


def test_postgres_evolution_transition_is_one_operation_and_one_event():
    url = _postgres_url()
    _create_schema(url)
    conn = _connect(url)
    try:
        first = commit_evolution_transition(
            conn, user_id=1, operation_id="d008-evolution-1",
            spirit_id="starpath_antlerling", from_level=9, to_level=10,
            source="D008_TEST",
        )
        replay = commit_evolution_transition(
            conn, user_id=1, operation_id="d008-evolution-1",
            spirit_id="starpath_antlerling", from_level=9, to_level=10,
            source="D008_TEST",
        )
        conn.commit()
        assert first.body == replay.body
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM spirit_evolution_events"
        ).fetchone()["n"] == 1
    finally:
        conn.close()


def test_postgres_new_spirit_feed_replays_without_second_item_consume(monkeypatch):
    url = _postgres_url()
    _create_schema(url)
    import app as app_module

    original_get_db = app_module.get_db
    app_module.get_db = lambda: _PgDbContext(url)
    try:
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "d008-pg"
        payload = {
            "item_key": "go_spirit_candy",
            "spirit_id": "starpath_antlerling",
            "operation_id": "d008-feed-starpath-1",
        }
        first = client.post("/api/pet/feed", json=payload)
        replay = client.post("/api/pet/feed", json=payload)
        assert first.status_code == replay.status_code == 200
        assert first.get_json() == replay.get_json()
        conn = _connect(url)
        try:
            assert conn.execute(
                "SELECT qty FROM pet_inventory WHERE user_id=1 AND item_key='go_spirit_candy'"
            ).fetchone()["qty"] == 1
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM item_use_operations "
                "WHERE player_id=1 AND operation_id='d008-feed-starpath-1'"
            ).fetchone()["n"] == 1
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM domain_event_outbox "
                "WHERE event_type='ITEM_CONSUME_EFFECT' AND player_id='1'"
            ).fetchone()["n"] == 1
        finally:
            conn.close()
    finally:
        app_module.get_db = original_get_db


def test_postgres_concurrent_new_spirit_feed_consumes_once(monkeypatch):
    url = _postgres_url()
    _create_schema(url)
    import app as app_module

    original_get_db = app_module.get_db
    app_module.get_db = lambda: _PgDbContext(url)

    def submit():
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "d008-pg-concurrent"
        return client.post(
            "/api/pet/feed",
            json={
                "item_key": "go_spirit_candy",
                "spirit_id": "starpath_antlerling",
                "operation_id": "d008-feed-starpath-concurrent",
            },
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: submit(), range(2)))
        assert [response.status_code for response in responses] == [200, 200]
        assert responses[0].get_json() == responses[1].get_json()
        conn = _connect(url)
        try:
            assert conn.execute(
                "SELECT qty FROM pet_inventory WHERE user_id=1 AND item_key='go_spirit_candy'"
            ).fetchone()["qty"] == 1
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM item_use_operations "
                "WHERE player_id=1 AND operation_id='d008-feed-starpath-concurrent'"
            ).fetchone()["n"] == 1
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM pet_action_log "
                "WHERE user_id=1 AND action='feed'"
            ).fetchone()["n"] == 1
        finally:
            conn.close()
    finally:
        app_module.get_db = original_get_db


def test_postgres_unapproved_new_spirit_unlock_fails_closed():
    url = _postgres_url()
    _create_schema(url)
    import app as app_module

    original_get_db = app_module.get_db
    app_module.get_db = lambda: _PgDbContext(url)
    try:
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "d008-pg"
        response = client.post(
            "/api/pet/unlock",
            json={"pet_key": "fatty", "operation_id": "d008-unlock-source-gap"},
        )
        assert response.status_code == 403
        assert response.get_json()["unlock_source"] == "FUTURE_AUTHENTICATED_SETTLEMENT"
    finally:
        app_module.get_db = original_get_db
