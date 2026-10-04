"""Fresh E HTTP contracts using disposable SQLite and synthetic sessions only."""

import contextlib
import os
import sqlite3

import pytest

os.environ.setdefault("SECRET_KEY", "g008-fresh-e-isolated-test-secret")
import app as application
from future30_character_service import grant_future30_character, initialize_future30_catalog


LEGACY_KEYS = (
    "apprentice", "apprentice_girl", "swordsman", "rogue", "ranger",
    "berserker", "guardian", "paladin", "mage", "sage", "hero_male",
    "woman", "boy_child", "girl_child", "elder_master", "elder_woman",
)


@pytest.fixture
def authority_env(tmp_path, monkeypatch):
    path = tmp_path / "g008-fresh-e.sqlite"

    @contextlib.contextmanager
    def database():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    with database() as conn:
        conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, plan TEXT DEFAULT 'free', "
                     "premium_until TEXT, is_admin INTEGER DEFAULT 0)")
        conn.executemany("INSERT INTO users(id) VALUES(?)", [(1,), (2,)])
        slots = ", ".join(name + " TEXT" for name in application.APPEARANCE_EQUIP_COLUMNS)
        conn.execute("CREATE TABLE player_appearance(user_id INTEGER PRIMARY KEY, "
                     "character_key TEXT, updated_at TEXT, combat_weapon TEXT, " + slots + ")")
        conn.execute("CREATE TABLE player_wardrobe(user_id INTEGER, item_id TEXT, "
                     "obtained_at TEXT, source TEXT)")
        conn.execute("INSERT INTO player_appearance(user_id,character_key,updated_at,combat_weapon) "
                     "VALUES(1,'apprentice','before','preserved-legacy-value')")
        initialize_future30_catalog(conn)
    monkeypatch.setattr(application, "get_db", database)
    monkeypatch.setattr(application, "_compute_title_metrics", lambda *args: {})
    monkeypatch.setitem(application.app.config, "TESTING", True)
    monkeypatch.setitem(application.app.config, "APP_ENV", "test")
    monkeypatch.setitem(application.app.config, "FUTURE30_ACCEPTANCE_ENTITLEMENTS_ENABLED", True)

    def client_for(uid=1):
        client = application.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = uid
        return client

    return database, client_for


@pytest.mark.parametrize("key", LEGACY_KEYS)
def test_all_legacy_keys_bootstrap_to_a1_without_identity_guess(authority_env, key):
    database, client_for = authority_env
    with database() as conn:
        conn.execute("UPDATE player_appearance SET character_key=? WHERE user_id=1", (key,))
    client = client_for()
    response = client.get("/api/player/appearance")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["character_key"] == "A1"
    assert payload["character_key_authority"] == "player_appearance.character_key"
    assert payload["character_runtime"]["character_key"] == "A1"
    with database() as conn:
        assert tuple(conn.execute("SELECT character_key,updated_at FROM player_appearance "
                                  "WHERE user_id=1").fetchone())[0] == "A1"
        assert conn.execute("SELECT COUNT(*) FROM player_character_entitlements").fetchone()[0] == 5
    # Presentation/bootstrap and legacy selection are distinct contracts.
    with database() as conn:
        before = tuple(conn.execute("SELECT * FROM player_appearance WHERE user_id=1").fetchone())
        entitlements_before = conn.execute("SELECT COUNT(*) FROM player_character_entitlements").fetchone()[0]
    result = client.post("/api/skills/character", json={"character_key": key})
    assert result.status_code == 400
    assert result.get_json() == {"error": "invalid character_key"}
    with database() as conn:
        assert tuple(conn.execute("SELECT * FROM player_appearance WHERE user_id=1").fetchone()) == before
        assert conn.execute("SELECT COUNT(*) FROM player_character_entitlements").fetchone()[0] == entitlements_before


def test_owned_apply_refresh_and_fresh_synthetic_session_use_persistent_authority(authority_env):
    database, client_for = authority_env
    with database() as conn:
        grant_future30_character(conn, 1, "A1", "ACCEPTANCE_TEST", environment="test",
                                 allow_acceptance_test=True, source_reference="fresh-e-test")
    client = client_for()
    response = client.post("/api/skills/character", json={"character_key": "A1",
                           "combat_weapon": "forged", "active_character": "A3"})
    assert response.status_code == 200
    assert "combat_weapon" in response.get_json()["rejected"]
    for reader in (client, client_for()):
        response = reader.get("/api/player/appearance")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["character_key"] == "A1"
        assert payload["character_key_source"] == "player_appearance.character_key"
        assert payload["character_entitled"] is True
        assert payload["combat_weapon"] == "preserved-legacy-value"
        catalog = reader.get("/api/player/character-catalog").get_json()
        assert catalog["applied_character_key"] == "A1"
        assert sum(entry["owned"] for entry in catalog["entries"]) == 5
        assert sum(entry["is_applied"] for entry in catalog["entries"]) == 1
    # Another synthetic user cannot borrow ownership through request fields.
    rejected = client_for(2).post("/api/skills/character", json={"character_key": "A1",
                                 "user_id": 1, "owned": True, "entitled": True})
    assert rejected.status_code == 403
    with database() as conn:
        assert conn.execute("SELECT COUNT(*) FROM player_appearance WHERE user_id=2").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM player_character_entitlements").fetchone()[0] == 5


@pytest.mark.parametrize("key,status", [("A3", 403), ("A31", 400), ("AR1_BLUE", 400),
                                       ("FUTURE30_MODEL_AR1_BLUE", 400)])
def test_client_ownership_and_visual_identity_claims_cannot_apply(authority_env, key, status):
    database, client_for = authority_env
    result = client_for().post("/api/skills/character", json={"character_key": key,
                              "owned": True, "is_applied": True, "acquisition_source": "STARTER"})
    assert result.status_code == status
    with database() as conn:
        assert tuple(conn.execute("SELECT character_key,updated_at FROM player_appearance "
                                  "WHERE user_id=1").fetchone()) == ("apprentice", "before")
        assert conn.execute("SELECT COUNT(*) FROM player_character_entitlements").fetchone()[0] == 0


def test_unentitled_persisted_selection_projects_closed_without_rewriting(authority_env):
    database, client_for = authority_env
    with database() as conn:
        conn.execute("UPDATE player_appearance SET character_key='A3' WHERE user_id=1")
    result = client_for().get("/api/player/appearance")
    assert result.status_code == 200
    assert result.get_json()["character_key"] == "A1"
    assert result.get_json()["character_entitled"] is True
    assert result.get_json()["character_runtime"]["character_key"] == "A1"
    with database() as conn:
        assert tuple(conn.execute("SELECT character_key,updated_at FROM player_appearance "
                                  "WHERE user_id=1").fetchone())[0] == "A1"


def test_disposable_postgres_catalog_entitlement_and_persistence():
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper
    from postgres_test_harness import disposable_postgres
    from future30_character_service import (
        Future30CharacterNotEntitled, apply_future30_character, ensure_future30_catalog,
    )
    from migrations.future30_character_catalog_v1 import upgrade, validate_schema

    with disposable_postgres(name_prefix="g009-e-g008-catalog-test") as runtime:
        def connect():
            raw = psycopg2.connect(runtime["database_url"], connect_timeout=10)
            raw.cursor_factory = DictCursor
            return PostgresConnectionWrapper(raw)

        conn = connect()
        try:
            conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO users(id) VALUES(7)")
            conn.execute("CREATE TABLE player_appearance(user_id INTEGER PRIMARY KEY, "
                         "character_key TEXT, updated_at TEXT)")
            assert len(upgrade(conn)["created"]) == 3
            assert upgrade(conn)["created"] == []
            assert validate_schema(conn)["valid"] is True
            initialize_future30_catalog(conn)
            assert ensure_future30_catalog(conn)["visual_count"] == 33
            grant = grant_future30_character(conn, 7, "A1", "ACCEPTANCE_TEST", environment="test",
                                             allow_acceptance_test=True, source_reference="pg-test")
            assert grant["created"] is True
            apply_future30_character(conn, 7, "A1", allow_acceptance_test=True)
            conn.commit()
        finally:
            conn.close()
        conn = connect()
        try:
            repeated = grant_future30_character(conn, 7, "A1", "ACCEPTANCE_TEST", environment="test",
                                                allow_acceptance_test=True, source_reference="retry")
            assert repeated["created"] is False
            assert repeated["source_reference"] == "pg-test"
            with pytest.raises(Future30CharacterNotEntitled):
                apply_future30_character(conn, 7, "A3", allow_acceptance_test=True)
            assert conn.execute("SELECT character_key FROM player_appearance WHERE user_id=7").fetchone()[0] == "A1"
            assert conn.execute("SELECT COUNT(*) FROM player_character_entitlements").fetchone()[0] == 1
            assert ensure_future30_catalog(conn)["logical_count"] == 30
            conn.rollback()
        finally:
            conn.close()
