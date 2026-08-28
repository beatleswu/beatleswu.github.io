"""D037 proof for server-owned active Spirit selection and rehydration."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

import test_d030_r2_spirit_adventure_milestone_wiring as d030


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
SPIRIT_RUNTIME = ROOT / "spirit_runtime.py"
HERO = ROOT / "hero.html"
INDEX = ROOT / "index.html"


class _DbContext:
    """Match the production database context methods used by B023 routes."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        return self._conn.execute(sql, params or ())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        return False


@pytest.fixture(scope="module")
def app_module():
    d030._install_app_import_stubs()
    import app as module

    return module


@pytest.fixture()
def runtime(app_module, monkeypatch):
    conn = d030._new_db()
    for column in (
        "last_pet_at",
        "last_train_at",
        "daily_key",
        "daily_bond",
        "daily_train_xp",
    ):
        definition = "TEXT" if column in {"last_pet_at", "last_train_at", "daily_key"} else "INTEGER NOT NULL DEFAULT 0"
        conn.execute(f"ALTER TABLE user_pets ADD COLUMN {column} {definition}")
    conn.commit()

    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(conn))
    monkeypatch.setattr(
        app_module,
        "_adventure_state",
        lambda _uid: [{
            "key": "k11_15",
            "seen": 50,
            "unlocked": True,
            "cleared": False,
        }],
    )
    monkeypatch.setattr(app_module, "_adventure_map_state", lambda *args, **kwargs: {})
    app_module.app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


def _login(client, user_id=37001):
    with client.session_transaction() as session:
        session["user_id"] = user_id


def _seed_spirits(conn, user_id=37001, *, active="ink_drop_kelpie", owned=None):
    owned = tuple(owned or ("ink_drop_kelpie", "starpath_antlerling"))
    for index, pet_key in enumerate(owned):
        conn.execute(
            "INSERT INTO pet_collection(user_id,pet_key,nickname,selected_at,level) "
            "VALUES(?,?,?,?,?)",
            (user_id, pet_key, pet_key, f"2026-08-28T00:00:0{index}", 1),
        )
    if active is not None:
        conn.execute(
            "INSERT INTO user_pets(user_id,pet_key,nickname,selected_at,updated_at) "
            "VALUES(?,?,?,?,?)",
            (user_id, active, active, "2026-08-28T00:00:00", "2026-08-28T00:00:00"),
        )
    conn.commit()


def test_owned_selection_replaces_active_and_read_model_is_single_active(
    app_module, client, runtime
):
    _seed_spirits(runtime)
    _login(client)

    response = client.post(
        "/api/pet/switch",
        json={
            "pet_key": "starpath_antlerling",
            "operation_id": "d037-owned-switch-1",
            "expected_active_spirit_id": "ink_drop_kelpie",
        },
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["pet"]["pet_key"] == "starpath_antlerling"
    assert body["collection"]["collection"]
    assert sum(item["active"] for item in body["collection"]["collection"]) == 1

    status = client.get("/api/pet/status")
    assert status.status_code == 200
    read_model = status.get_json()
    assert read_model["pet"]["pet_key"] == "starpath_antlerling"
    assert read_model["spirit_projection"]["active_spirit_id"] == "starpath_antlerling"
    assert read_model["spirit_projection"]["single_active_spirit"] is True
    assert sum(item["active"] for item in read_model["collection"]["collection"]) == 1
    assert runtime.execute(
        "SELECT COUNT(*) FROM user_pets WHERE user_id=?", (37001,)
    ).fetchone()[0] == 1


def test_operation_replay_and_same_spirit_selection_are_noop_without_duplicate_active_state(
    client, runtime
):
    _seed_spirits(runtime)
    _login(client)
    payload = {
        "pet_key": "starpath_antlerling",
        "operation_id": "d037-replay-switch-1",
        "expected_active_spirit_id": "ink_drop_kelpie",
    }
    first = client.post("/api/pet/switch", json=payload)
    replay = client.post("/api/pet/switch", json=payload)
    assert first.status_code == replay.status_code == 200
    assert replay.get_json()["pet"]["pet_key"] == "starpath_antlerling"
    assert runtime.execute(
        "SELECT COUNT(*) FROM companion_operations WHERE user_id=?", (37001,)
    ).fetchone()[0] == 1

    same = client.post(
        "/api/pet/switch",
        json={
            "pet_key": "starpath_antlerling",
            "operation_id": "d037-same-switch-2",
            "expected_active_spirit_id": "starpath_antlerling",
        },
    )
    assert same.status_code == 200
    assert same.get_json()["pet"]["pet_key"] == "starpath_antlerling"
    assert runtime.execute(
        "SELECT COUNT(*) FROM pet_action_log WHERE user_id=? AND action='switch'",
        (37001,),
    ).fetchone()[0] == 1
    assert runtime.execute(
        "SELECT COUNT(*) FROM user_pets WHERE user_id=?", (37001,)
    ).fetchone()[0] == 1


@pytest.mark.parametrize(
    ("pet_key", "error_code"),
    (
        ("fatty", "SPIRIT_NOT_OWNED"),
        ("seventh_spirit", "UNKNOWN_SPIRIT"),
        ("not a canonical Spirit", "UNKNOWN_SPIRIT"),
        ("", "UNKNOWN_SPIRIT"),
    ),
)
def test_unowned_unknown_and_malformed_spirit_ids_fail_closed(
    client, runtime, pet_key, error_code
):
    _seed_spirits(runtime, owned=("ink_drop_kelpie",))
    _login(client)
    response = client.post(
        "/api/pet/switch",
        json={
            "pet_key": pet_key,
            "operation_id": "d037-reject-1",
            "expected_active_spirit_id": "ink_drop_kelpie",
        },
    )
    assert response.status_code in {400, 403}
    body = response.get_json()
    assert body["ok"] is False
    operation = runtime.execute(
        "SELECT error_code FROM companion_operations WHERE user_id=? AND operation_id=?",
        (37001, "d037-reject-1"),
    ).fetchone()
    if operation is None:
        # Canonical ID validation happens before B023 reserves an operation;
        # the request still fails closed without touching active state.
        assert body.get("code") == "INVALID_COMPANION_OPERATION"
    else:
        assert operation[0] == error_code
    assert runtime.execute(
        "SELECT pet_key FROM user_pets WHERE user_id=?", (37001,)
    ).fetchone()[0] == "ink_drop_kelpie"


def test_stale_expected_active_rejects_without_changing_server_state(client, runtime):
    _seed_spirits(runtime)
    _login(client)
    response = client.post(
        "/api/pet/switch",
        json={
            "pet_key": "starpath_antlerling",
            "operation_id": "d037-stale-switch-1",
            "expected_active_spirit_id": "fatty",
        },
    )
    assert response.status_code == 409
    assert response.get_json()["ok"] is False
    assert runtime.execute(
        "SELECT error_code FROM companion_operations WHERE user_id=? AND operation_id=?",
        (37001, "d037-stale-switch-1"),
    ).fetchone()[0] == "STALE_ACTIVE_SPIRIT"
    assert runtime.execute(
        "SELECT pet_key FROM user_pets WHERE user_id=?", (37001,)
    ).fetchone()[0] == "ink_drop_kelpie"


def test_no_active_state_is_preserved_and_selection_does_not_force_activate(
    client, runtime
):
    _seed_spirits(runtime, active=None)
    _login(client)
    status = client.get("/api/pet/status").get_json()
    assert status["pet"] is None
    assert status["spirit_projection"]["active_spirit_id"] is None
    assert all(item["active"] is False for item in status["collection"]["collection"])

    response = client.post(
        "/api/pet/switch",
        json={
            "pet_key": "starpath_antlerling",
            "operation_id": "d037-no-active-1",
            "expected_active_spirit_id": None,
        },
    )
    assert response.status_code == 400
    assert response.get_json()["ok"] is False
    assert runtime.execute(
        "SELECT error_code FROM companion_operations WHERE user_id=? AND operation_id=?",
        (37001, "d037-no-active-1"),
    ).fetchone()[0] == "NO_ACTIVE_SPIRIT"


def test_reload_login_and_reentry_rehydrate_the_same_active_spirit(client, runtime):
    _seed_spirits(runtime)
    _login(client)
    switched = client.post(
        "/api/pet/switch",
        json={
            "pet_key": "starpath_antlerling",
            "operation_id": "d037-persist-switch-1",
            "expected_active_spirit_id": "ink_drop_kelpie",
        },
    )
    assert switched.status_code == 200
    with client.session_transaction() as session:
        session.clear()
    _login(client)
    for _surface in ("hero", "adventure"):
        status = client.get("/api/pet/status")
        assert status.status_code == 200
        assert status.get_json()["spirit_projection"]["active_spirit_id"] == (
            "starpath_antlerling"
        )


def test_historical_unlock_does_not_replace_existing_active_spirit(app_module, runtime):
    _seed_spirits(runtime, owned=("ink_drop_kelpie",))
    result, status_code = app_module._adventure_spirit_unlock_sink(
        runtime,
        37001,
        "starpath_antlerling",
        "k11_15",
        "d037-historical-unlock-1",
    )
    assert status_code == 200
    assert result["ok"] is True
    assert runtime.execute(
        "SELECT pet_key FROM user_pets WHERE user_id=?", (37001,)
    ).fetchone()[0] == "ink_drop_kelpie"
    assert runtime.execute(
        "SELECT 1 FROM pet_collection WHERE user_id=? AND pet_key=?",
        (37001, "starpath_antlerling"),
    ).fetchone() is not None


def test_d037_frontend_wires_server_selection_refresh_without_app_or_schema_logic():
    hero = HERO.read_text(encoding="utf-8")
    index = INDEX.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    projection = SPIRIT_RUNTIME.read_text(encoding="utf-8")

    for marker in (
        "ACTIVE_SPIRIT_SYNC_EVENT",
        "_petSwitchInFlight",
        "operation_id: operationId",
        "expected_active_spirit_id: expectedActive",
        "A network-level retry deliberately reuses the B023 operation identity",
        "notifyActiveSpiritSelection();",
    ):
        assert marker in hero
    for marker in (
        "function refreshActiveSpiritPresentation()",
        "active-spirit-selection-complete",
        "refreshActiveSpiritPresentation().catch(() => {});",
        "cache:'no-store'",
    ):
        assert marker in index
    for marker in (
        "@app.route('/api/pet/switch', methods=['POST'])",
        "SPIRIT_NOT_OWNED",
        "STALE_ACTIVE_SPIRIT",
        "_run_companion_route(",
    ):
        assert marker in app
    assert "single_active_spirit" in projection
    assert "pet_collection_with_user_pets_active_projection" in projection
