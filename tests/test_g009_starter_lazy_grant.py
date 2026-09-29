"""G009 owner-finalized STARTER lazy bootstrap coverage."""

import contextlib
import concurrent.futures
import sqlite3

import pytest

from future30_character_service import (
    STARTER_CHARACTER_KEYS,
    apply_future30_character,
    ensure_future30_starter_bootstrap,
    grant_future30_character,
    initialize_future30_catalog,
)


def _create_state_database(path=":memory:"):
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE)")
    connection.execute(
        """CREATE TABLE player_appearance(
            user_id INTEGER PRIMARY KEY, character_key TEXT, updated_at TEXT,
            outfit_id TEXT, hat_id TEXT, back_id TEXT, title_id TEXT,
            accessory_id TEXT, pet_id TEXT, aura_id TEXT,
            combat_armor TEXT, combat_cape TEXT, combat_weapon TEXT,
            combat_offhand TEXT, stone_skin TEXT, board_skin TEXT
        )"""
    )
    connection.execute(
        "CREATE TABLE player_wardrobe(user_id INTEGER, item_id TEXT, obtained_at TEXT, source TEXT)"
    )
    initialize_future30_catalog(connection)
    connection.commit()
    return connection


@pytest.fixture
def isolated_state():
    connection = _create_state_database()
    for user_id in range(1, 8):
        connection.execute("INSERT INTO users(id, username) VALUES(?, ?)", (user_id, f"starter-{user_id}"))
    connection.commit()
    try:
        yield connection
    finally:
        connection.close()


def _entitled_keys(connection, user_id):
    return [row[0] for row in connection.execute(
        "SELECT character_key FROM player_character_entitlements WHERE user_id=? ORDER BY character_key",
        (user_id,),
    ).fetchall()]


def test_new_missing_and_repeat_are_all_five_idempotent(isolated_state):
    first = ensure_future30_starter_bootstrap(isolated_state, 1)
    assert first["created"] == list(STARTER_CHARACTER_KEYS)
    assert first["active_character_key"] == "A1"
    assert _entitled_keys(isolated_state, 1) == sorted(STARTER_CHARACTER_KEYS)
    assert isolated_state.execute(
        "SELECT character_key FROM player_appearance WHERE user_id=1"
    ).fetchone()[0] == "A1"

    repeated = ensure_future30_starter_bootstrap(isolated_state, 1)
    assert repeated["created"] == []
    assert _entitled_keys(isolated_state, 1) == sorted(STARTER_CHARACTER_KEYS)


def test_partial_backfill_only_adds_missing_starters_and_legacy_defaults_a1(isolated_state):
    isolated_state.execute(
        "INSERT INTO player_appearance(user_id, character_key) VALUES(2, 'apprentice')"
    )
    for key in ("A1", "R1"):
        grant_future30_character(isolated_state, 2, key, "STARTER", source_reference="preexisting")

    result = ensure_future30_starter_bootstrap(isolated_state, 2)
    assert result["created"] == ["R2", "R3", "S2"]
    assert result["active_character_key"] == "A1"
    assert _entitled_keys(isolated_state, 2) == sorted(STARTER_CHARACTER_KEYS)


def test_existing_valid_future30_selection_is_preserved(isolated_state):
    grant_future30_character(isolated_state, 3, "A3", "STAGE", source_reference="accepted-stage")
    apply_future30_character(isolated_state, 3, "A3")
    result = ensure_future30_starter_bootstrap(isolated_state, 3)
    assert result["created"] == ["A1", "R1", "R2", "R3", "S2"]
    assert result["active_character_key"] == "A3"
    assert isolated_state.execute(
        "SELECT character_key FROM player_appearance WHERE user_id=3"
    ).fetchone()[0] == "A3"


def test_missing_appearance_creates_a1_without_mapping_legacy_key(isolated_state):
    assert isolated_state.execute(
        "SELECT 1 FROM player_appearance WHERE user_id=4"
    ).fetchone() is None
    result = ensure_future30_starter_bootstrap(isolated_state, 4)
    assert result["active_character_key"] == "A1"
    assert isolated_state.execute(
        "SELECT character_key FROM player_appearance WHERE user_id=4"
    ).fetchone()[0] == "A1"


def test_authenticated_appearance_boundary_grants_and_projects_real_player_state(isolated_state, monkeypatch):
    import app as application

    @contextlib.contextmanager
    def database():
        yield isolated_state

    monkeypatch.setattr(application, "get_db", database)
    monkeypatch.setattr(application, "ensure_premium_rewards", lambda *args, **kwargs: None)
    monkeypatch.setitem(application.app.config, "TESTING", True)
    client = application.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 5
        session["username"] = "starter-5"

    appearance = client.get("/api/player/appearance")
    assert appearance.status_code == 200
    payload = appearance.get_json()
    assert payload["character_key"] == "A1"
    assert payload["character_key_source"] == "player_appearance.character_key"
    assert payload["character_entitled"] is True
    assert payload["character_runtime"]["character_key"] == "A1"
    assert _entitled_keys(isolated_state, 5) == sorted(STARTER_CHARACTER_KEYS)

    catalog = client.get("/api/player/character-catalog")
    assert catalog.status_code == 200
    owned = [entry["character_key"] for entry in catalog.get_json()["entries"] if entry["owned"]]
    assert owned == sorted(STARTER_CHARACTER_KEYS)


def test_normal_authenticated_switch_persists_across_fresh_session(isolated_state, monkeypatch):
    import app as application

    @contextlib.contextmanager
    def database():
        yield isolated_state

    monkeypatch.setattr(application, "get_db", database)
    monkeypatch.setattr(application, "ensure_premium_rewards", lambda *args, **kwargs: None)
    monkeypatch.setitem(application.app.config, "APP_ENV", "production")
    monkeypatch.setitem(application.app.config, "FUTURE30_ACCEPTANCE_ENTITLEMENTS_ENABLED", False)
    client = application.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 5
        session["username"] = "starter-5"

    assert client.get("/api/player/appearance").get_json()["character_key"] == "A1"
    switched = client.post("/api/skills/character", json={"character_key": "R2"})
    assert switched.status_code == 200
    assert client.get("/api/player/appearance").get_json()["character_key"] == "R2"
    catalog = client.get("/api/player/character-catalog").get_json()
    assert catalog["applied_character_key"] == "R2"
    assert sum(entry["owned"] for entry in catalog["entries"]) == 5

    fresh = application.app.test_client()
    with fresh.session_transaction() as session:
        session["user_id"] = 5
        session["username"] = "starter-5"
    assert fresh.get("/api/player/appearance").get_json()["character_key"] == "R2"


def test_two_concurrent_bootstrap_requests_converge_without_duplicates(tmp_path):
    db_path = str(tmp_path / "starter-concurrency.sqlite")
    setup = _create_state_database(db_path)
    setup.execute("INSERT INTO users(id, username) VALUES(6, 'starter-concurrency')")
    setup.commit()
    setup.close()

    def run_once():
        connection = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            with connection:
                return ensure_future30_starter_bootstrap(connection, 6)
        finally:
            connection.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run_once(), range(2)))

    check = sqlite3.connect(db_path)
    assert check.execute(
        "SELECT COUNT(*) FROM player_character_entitlements WHERE user_id=6"
    ).fetchone()[0] == 5
    assert check.execute(
        "SELECT character_key FROM player_appearance WHERE user_id=6"
    ).fetchone()[0] == "A1"
    assert sorted(result["active_character_key"] for result in results) == ["A1", "A1"]
    check.close()
