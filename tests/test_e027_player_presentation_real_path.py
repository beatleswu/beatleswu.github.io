from __future__ import annotations

import os
import sqlite3

import pytest

# Keep app import isolated from the protected local secret artifact.  The
# route still uses the real Flask application; this only supplies a disposable
# test-session key before importing it.
os.environ.setdefault("SECRET_KEY", "e027-disposable-session-key")

import app as app_module


class _SQLiteRouteContext:
    """Disposable get_db context with production-like exit semantics."""

    def __init__(self, connection: sqlite3.Connection, tracker: dict[str, int]):
        self.connection = connection
        self.tracker = tracker

    def __enter__(self) -> sqlite3.Connection:
        return self.connection

    def __exit__(self, exc_type, _exc_value, _traceback) -> bool:
        if exc_type is None:
            self.connection.commit()
            self.tracker["commit_calls"] += 1
        else:
            self.connection.rollback()
            self.tracker["rollback_calls"] += 1
        return False


def _schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE user_stats (
            user_id INTEGER PRIMARY KEY,
            total_correct INTEGER NOT NULL DEFAULT 0,
            current_streak INTEGER NOT NULL DEFAULT 0,
            max_streak INTEGER NOT NULL DEFAULT 0,
            xp INTEGER NOT NULL DEFAULT 0,
            rank_level TEXT NOT NULL DEFAULT 'LV1',
            rank_xp INTEGER NOT NULL DEFAULT 0,
            go_rank TEXT NOT NULL DEFAULT '30k',
            player_hp INTEGER NOT NULL DEFAULT 100,
            player_max_hp INTEGER NOT NULL DEFAULT 100
        );
        CREATE TABLE player_inventory (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            equip_id TEXT NOT NULL,
            equipped INTEGER NOT NULL DEFAULT 0,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'drop'
        );
        CREATE TABLE pet_collection (
            user_id INTEGER NOT NULL,
            pet_key TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 1,
            xp INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, pet_key)
        );
        CREATE TABLE user_pets (
            user_id INTEGER PRIMARY KEY,
            pet_key TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 1,
            xp INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE player_wardrobe (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'drop'
        );
        CREATE TABLE player_appearance (
            user_id INTEGER PRIMARY KEY,
            outfit_id TEXT,
            hat_id TEXT,
            back_id TEXT,
            title_id TEXT,
            accessory_id TEXT,
            pet_id TEXT,
            aura_id TEXT,
            character_key TEXT,
            updated_at TEXT
        );
        """
    )


def _seed_player(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO users(id, username, password_hash, created_at) VALUES(17, 'p17', 'x', 'now')"
    )
    connection.execute(
        """
        INSERT INTO user_stats(
            user_id, total_correct, current_streak, max_streak, xp, rank_level,
            rank_xp, go_rank, player_hp, player_max_hp
        ) VALUES(17, 12, 4, 8, 321, 'LV12', 40, '18k', 80, 120)
        """
    )
    connection.executemany(
        "INSERT INTO player_inventory(id, user_id, equip_id, equipped, obtained_at, source) "
        "VALUES(?, 17, ?, 1, 'now', 'drop')",
        [(1, "iron_sword"), (2, "leather_armor"), (3, "lucky_stone")],
    )
    connection.execute(
        "INSERT INTO pet_collection(user_id, pet_key, level, xp) VALUES(17, 'ink_drop_kelpie', 12, 7)"
    )
    connection.execute(
        "INSERT INTO user_pets(user_id, pet_key, level, xp) VALUES(17, 'ink_drop_kelpie', 12, 7)"
    )
    connection.execute(
        "INSERT INTO player_wardrobe(id, user_id, item_id, obtained_at, source) "
        "VALUES(1, 17, 'robe_plain', 'now', 'drop')"
    )
    connection.execute(
        "INSERT INTO player_appearance(user_id, outfit_id, character_key) "
        "VALUES(17, 'robe_plain', 'apprentice')"
    )
    connection.commit()


@pytest.fixture()
def real_db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    _schema(connection)
    _seed_player(connection)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture()
def authenticated_route(monkeypatch, real_db):
    tracker = {"commit_calls": 0, "rollback_calls": 0}
    monkeypatch.setattr(
        app_module,
        "get_db",
        lambda: _SQLiteRouteContext(real_db, tracker),
    )
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 17
    return client, real_db, tracker


def _snapshot(connection: sqlite3.Connection) -> dict[str, list[tuple]]:
    tables = (
        "users",
        "user_stats",
        "player_inventory",
        "pet_collection",
        "user_pets",
        "player_wardrobe",
        "player_appearance",
    )
    return {
        table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")]
        for table in tables
    }


def test_real_http_path_uses_session_identity_and_narrows_authoritative_values(
    authenticated_route,
):
    client, connection, tracker = authenticated_route
    before = _snapshot(connection)
    changes_before = connection.total_changes

    response = client.get("/api/player/presentation?user_id=999")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["contract_version"] == "PLAYER_PRESENTATION_API_V1"
    assert payload["player_id"] == 17
    assert payload["hero"]["hero_id"] == "apprentice"
    assert payload["progression"]["xp"] == 321
    assert payload["progression"]["level"] == 12
    assert payload["progression"]["rank_level"] == "LV12"
    assert payload["persistent_hp"] == {
        "persistent_player_hp": 80,
        "persistent_player_max_hp": 120,
        "authority": "user_stats",
        "scope": "persistent_player_state",
    }
    assert payload["equipment"]["slots"]["weapon"]["item_id"] == "iron_sword"
    assert payload["equipment"]["slots"]["armor"]["item_id"] == "leather_armor"
    assert payload["spirit"]["active"]["spirit_id"] == "ink_drop_kelpie"
    assert payload["spirit"]["active"]["ownership_validated"] is True
    assert payload["spirit"]["combat_effects_projected"] is False
    assert payload["cosmetics"]["selected"]["outfit"]["item_id"] == "robe_plain"
    assert payload["cosmetics"]["selected"]["outfit"]["presentation_only"] is True

    assert "total_correct" not in payload["progression"]
    assert "current_streak" not in payload["progression"]
    assert "max_streak" not in payload["progression"]
    assert "world" not in payload
    assert "selectedZone" not in payload
    assert "progressionZone" not in payload
    assert "quest" not in payload
    assert "shop" not in payload
    assert "premium" not in payload
    assert "encounter_hp" not in payload["persistent_hp"]
    assert "combat_stats" not in payload["equipment"]
    assert "damage" not in payload["equipment"]
    assert "effect" not in payload["spirit"]
    assert payload["provenance"]["excluded_authorities"]["world"]["projected"] is False
    assert payload["provenance"]["excluded_authorities"]["quest"]["projected"] is False
    assert payload["provenance"]["excluded_authorities"]["shop"]["projected"] is False
    assert payload["provenance"]["excluded_authorities"]["premium"]["projected"] is False

    after = _snapshot(connection)
    assert after == before
    assert connection.total_changes == changes_before
    # The context's successful commit is driver bookkeeping for a read-only
    # transaction; SQLite reports no business-data change.
    assert tracker == {"commit_calls": 1, "rollback_calls": 0}


def test_unauthenticated_real_route_is_denied_without_db_access(monkeypatch):
    calls = []

    def unexpected_db():
        calls.append(True)
        raise AssertionError("unauthenticated request must stop at login_required")

    monkeypatch.setattr(app_module, "get_db", unexpected_db)

    response = app_module.app.test_client().get("/api/player/presentation")

    assert response.status_code == 401
    assert calls == []


def test_real_malformed_equipment_projection_does_not_choose_a_winner(
    authenticated_route,
):
    client, connection, _tracker = authenticated_route
    connection.execute(
        "INSERT INTO player_inventory(id, user_id, equip_id, equipped, obtained_at, source) "
        "VALUES(4, 17, 'wooden_sword', 1, 'now', 'drop')"
    )
    connection.commit()
    before = _snapshot(connection)
    changes_before = connection.total_changes

    response = client.get("/api/player/presentation")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["projection_status"] == "INVALID_STATE"
    assert payload["equipment"]["projection_status"] == "INVALID_STORED_STATE"
    assert payload["equipment"]["slots"]["weapon"]["item_id"] is None
    assert payload["equipment"]["slots"]["weapon"]["equipped"] is False
    assert payload["equipment"]["equipped_slot_conflicts"] == ["weapon"]
    owned = {item["item_id"]: item for item in payload["equipment"]["owned_items"]}
    assert owned["iron_sword"]["equipped"] is False
    assert owned["wooden_sword"]["equipped"] is False
    assert owned["leather_armor"]["equipped"] is True
    assert owned["lucky_stone"]["equipped"] is True
    assert _snapshot(connection) == before
    assert connection.total_changes == changes_before


def test_real_missing_required_authority_fails_closed_without_fallback(monkeypatch):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    tracker = {"commit_calls": 0, "rollback_calls": 0}
    monkeypatch.setattr(
        app_module,
        "get_db",
        lambda: _SQLiteRouteContext(connection, tracker),
    )
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 17

    response = client.get("/api/player/presentation")

    assert response.status_code == 503
    assert response.get_json() == {
        "error": "PLAYER_STATE_UNAVAILABLE",
        "status": "UNAVAILABLE",
    }
    assert tracker == {"commit_calls": 0, "rollback_calls": 1}
    assert connection.total_changes == 0
    connection.close()
