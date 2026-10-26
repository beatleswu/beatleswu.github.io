"""GO_ODYSSEY_ZONE4_10_CANONICAL_MAP_BATTLE_PROVIDER_ACTIVATION_001.

Owner-authorized admission of the real Zone4-10 Adventure Monster provider
(previously a `CanonicalAdventureProviderSlot` stub with `enabled = False`,
by design, pending separate authorization -- see
`adventure_zone4_10_monster_identity_authority.py`'s `RUNTIME_ADMISSION_PERFORMED`
and `adventure_zone4_10_monster_reward_policy.py`'s "future, separately
authorized runtime binding").

This file exercises the real HTTP endpoint end-to-end (not just the provider
registry in isolation, which `tests/test_act_b_provider_boundary_d1.py`
already covers) to prove two independent properties hold together:

1. A brand-new Map Battle can now be created in Zone4 (`k11_15`) -- the exact
   failure oberon hit, reproduced here as `test_locked_player_is_denied_a_fresh_zone4_battle`'s
   opposite case.
2. Provider *availability* is never a substitute for the player's own
   *zone-unlock eligibility* (`adventure_zone_unlocks` / the effective
   start-zone rank fallback) -- a locked player must still be denied, and
   denial must be server-authoritative (this endpoint, not a hidden client
   button).

An existing legacy OPEN battle (`migration_source='legacy-adventure-map'`)
is untouched by any of this: it keeps resuming through the pre-existing
`LEGACY_COMPATIBILITY_RESTORE` path, which never consults the unlock gate.
That is Section 8's requirement ("Owner's legacy Zone4 battle must not be
invalidated") and is verified directly against the real
`map_battle_v1_prepare_attempt` code path here.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import types

import pytest

os.environ.setdefault("SECRET_KEY", "zone4-10-activation-test-secret")


def _install_app_import_stubs():
    """Keep this test independent from optional local app modules."""

    if "katago_explain" not in sys.modules:
        module = types.ModuleType("katago_explain")
        module.KataGoExplainer = type("KataGoExplainer", (), {})
        sys.modules["katago_explain"] = module
    if "explain_overrides" not in sys.modules:
        module = types.ModuleType("explain_overrides")
        module.get_override = lambda *args, **kwargs: None
        sys.modules["explain_overrides"] = module
    if "grimoire_api" not in sys.modules:
        from flask import Blueprint

        module = types.ModuleType("grimoire_api")
        module.grimoire_bp = Blueprint("grimoire_stub_zone4_10_activation", __name__)
        module.official_grimoire_lookup = lambda _qid: None
        sys.modules["grimoire_api"] = module
    if "question_taxonomy" not in sys.modules:
        module = types.ModuleType("question_taxonomy")
        module.get_taxonomy = lambda *args, **kwargs: {}
        sys.modules["question_taxonomy"] = module
    if "monster_taxonomy" not in sys.modules:
        module = types.ModuleType("monster_taxonomy")
        module.get_monster_taxonomy = lambda *args, **kwargs: {}
        module.mark_encounters = lambda *args, **kwargs: None
        sys.modules["monster_taxonomy"] = module
    if "chapter_i18n" not in sys.modules:
        module = types.ModuleType("chapter_i18n")
        module.localize_topic = lambda *args, **kwargs: ""
        module.localize_level = lambda *args, **kwargs: ""
        sys.modules["chapter_i18n"] = module
    if "backend_i18n" not in sys.modules:
        module = types.ModuleType("backend_i18n")
        module.badge_en = lambda *args, **kwargs: ""
        module.skill_node_en = lambda *args, **kwargs: ""
        module.title_en = lambda *args, **kwargs: ""
        sys.modules["backend_i18n"] = module


ATTEMPT_ENDPOINT = "/api/adventure/map-battles/v1/attempts"
PROTOCOL = {"X-Map-Battle-Client-Protocol": "v1"}
ZONE4_APP_KEY = "k11_15"
# A real board position, and a real Zone4 topic ("7迷霧森林" is one of
# k11_15's two bound books per app.ADVENTURE_ZONES), so this exercises the
# actual `_map_battle_require_question_in_zone` topic check too, not a
# zone-key that `_zone_by_key` can't resolve.
ZONE4_QUESTION = {
    "id": 900001,
    "topic": "7迷霧森林",
    "content": "(;SZ[19];B[dd];W[ee])",
}

LOCKED_USER_ID = 501
UNLOCKED_USER_ID = 502
LEGACY_CONTINUE_USER_ID = 503


class _DbContext:
    """Mimics the production connection context manager over one shared conn."""

    def __init__(self, conn):
        self.conn = conn
        self._conn = conn

    def execute(self, statement, parameters=()):
        return self.conn.execute(statement, parameters)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        pass

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        return False


@pytest.fixture(scope="module")
def app_module():
    _install_app_import_stubs()
    import app as application

    application.app.config["TESTING"] = True
    return application


@pytest.fixture()
def api_env(app_module, monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """CREATE TABLE users (
             id INTEGER PRIMARY KEY,
             is_admin INTEGER NOT NULL DEFAULT 0,
             plan TEXT NOT NULL DEFAULT 'free',
             premium_until TEXT,
             elo_rating REAL
        )"""
    )
    conn.execute(
        """CREATE TABLE user_stats (
             user_id INTEGER PRIMARY KEY,
             go_rank TEXT,
             player_hp INTEGER NOT NULL DEFAULT 100,
             player_max_hp INTEGER NOT NULL DEFAULT 100
        )"""
    )
    conn.execute(
        """CREATE TABLE rating_test_sessions (
             user_id INTEGER NOT NULL,
             status TEXT NOT NULL,
             cur_rating REAL,
             finished_at TEXT,
             started_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE adventure_zone_unlocks (
             user_id INTEGER NOT NULL,
             zone_key TEXT NOT NULL,
             source TEXT NOT NULL DEFAULT 'placement',
             start_zone_key TEXT,
             unlocked_at TEXT NOT NULL,
             PRIMARY KEY (user_id, zone_key)
        )"""
    )

    from map_battle_persistence import create_map_battle, ensure_map_battle_tables
    from map_battle_runtime import ensure_submission_lifecycle_schema

    ensure_map_battle_tables(conn)
    ensure_submission_lifecycle_schema(conn)

    # LOCKED_USER_ID: no explicit unlock row, and a low placement Elo that
    # only reaches Zone1 (k26_30) -- genuinely locked out of Zone4 (k11_15).
    conn.execute(
        "INSERT INTO users(id, elo_rating) VALUES (?, ?)", (LOCKED_USER_ID, 1000.0)
    )
    conn.execute("INSERT INTO user_stats(user_id) VALUES (?)", (LOCKED_USER_ID,))

    # UNLOCKED_USER_ID: an explicit adventure_zone_unlocks row for k11_15,
    # the canonical real-world shape (placement or a star-earn unlock).
    conn.execute("INSERT INTO users(id, elo_rating) VALUES (?, ?)", (UNLOCKED_USER_ID, 1000.0))
    conn.execute("INSERT INTO user_stats(user_id) VALUES (?)", (UNLOCKED_USER_ID,))
    conn.execute(
        "INSERT INTO adventure_zone_unlocks(user_id, zone_key, source, start_zone_key, unlocked_at)"
        " VALUES (?, 'k11_15', 'placement_self', 'k1_5', '2026-06-07T00:00:00')",
        (UNLOCKED_USER_ID,),
    )

    # LEGACY_CONTINUE_USER_ID: reproduces the owner's real production shape --
    # locked-by-rank (no unlock row, low Elo) but already holding a pre-
    # existing OPEN legacy battle in k11_15 from before this admission.
    conn.execute(
        "INSERT INTO users(id, elo_rating) VALUES (?, ?)", (LEGACY_CONTINUE_USER_ID, 1000.0)
    )
    conn.execute("INSERT INTO user_stats(user_id) VALUES (?)", (LEGACY_CONTINUE_USER_ID,))
    create_map_battle(
        conn,
        user_id=LEGACY_CONTINUE_USER_ID,
        zone_key=ZONE4_APP_KEY,
        player_hp=100,
        player_hp_max=100,
        monster_hp=40,
        monster_hp_max=100,
        migration_source="legacy-adventure-map",
        migration_version="map-battle-v1",
    )

    conn.commit()

    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(conn))
    monkeypatch.setattr(app_module, "_load_questions", lambda: [dict(ZONE4_QUESTION)])
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "global")

    client = app_module.app.test_client()
    try:
        yield client, conn
    finally:
        conn.close()


def _login(client, user_id):
    with client.session_transaction() as session:
        session["user_id"] = user_id


def _prepare(client, zone_key=ZONE4_APP_KEY, question_id=ZONE4_QUESTION["id"]):
    return client.post(
        ATTEMPT_ENDPOINT,
        json={"zone_key": zone_key, "question_id": question_id},
        headers=PROTOCOL,
    )


def test_locked_player_is_denied_a_fresh_zone4_battle(api_env):
    client, conn = api_env
    _login(client, LOCKED_USER_ID)

    response = _prepare(client)

    assert response.status_code == 403, response.get_json()
    payload = response.get_json()
    assert payload["code"] == "map_battle_zone_not_unlocked"
    assert payload["retryable"] is False
    assert "attempt_id" not in payload
    assert "battle_id" not in payload
    # Denial must be server-authoritative: no row was ever written.
    assert conn.execute(
        "SELECT COUNT(*) FROM map_battles WHERE user_id=?", (LOCKED_USER_ID,)
    ).fetchone()[0] == 0


def test_unlocked_player_creates_a_real_zone4_battle_via_the_admitted_provider(api_env):
    client, conn = api_env
    _login(client, UNLOCKED_USER_ID)

    response = _prepare(client)

    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["battle_id"]
    assert payload["attempt_id"]
    assert payload["submission_nonce"]
    # `_map_battle_public_state` only projects `adventure_monster` for Zone 3
    # today (pre-existing, not something this activation changes) -- Zone1/2
    # have the same omission in production. The provider binding itself is
    # verified directly against the persisted row below instead.
    assert "adventure_monster" not in payload or payload["adventure_monster"] is None

    row = dict(
        conn.execute(
            "SELECT * FROM map_battles WHERE id=?", (payload["battle_id"],)
        ).fetchone()
    )
    assert row["zone_key"] == ZONE4_APP_KEY
    assert row["migration_source"] == "C2A_E1A_ADVENTURE_ZONE4_10_PROVIDER"
    assert row["monster_hp_max"] > 0
    assert ":Z4:" in row["migration_version"]


def test_legacy_open_battle_continues_unaffected_by_the_unlock_gate(api_env):
    """Section 8: the owner's real pre-existing legacy Zone4 battle shape.

    This account is locked by rank exactly like ``LOCKED_USER_ID`` -- the
    unlock gate would deny a *fresh* creation for it -- but it already holds
    an OPEN legacy battle, so `_map_battle_open_for_zone` finds it and the
    request never reaches the `battle is None` branch the gate lives in.
    """
    client, conn = api_env
    _login(client, LEGACY_CONTINUE_USER_ID)

    before = dict(
        conn.execute(
            "SELECT * FROM map_battles WHERE user_id=? AND zone_key=?",
            (LEGACY_CONTINUE_USER_ID, ZONE4_APP_KEY),
        ).fetchone()
    )

    response = _prepare(client)

    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    assert payload["battle_id"] == before["id"]
    # Still the same legacy row -- no new battle, no provider re-bind.
    after = dict(
        conn.execute("SELECT * FROM map_battles WHERE id=?", (before["id"],)).fetchone()
    )
    assert after["migration_source"] == "legacy-adventure-map"


def test_zone_unlocked_helper_matches_the_canonical_effective_start_zone_logic(app_module, api_env):
    """Direct unit coverage of `_map_battle_zone_unlocked` itself."""
    _, conn = api_env

    # Explicit row wins regardless of rank.
    assert app_module._map_battle_zone_unlocked(conn, UNLOCKED_USER_ID, "k11_15") is True
    # No row, low rank: Zone4 (index 3) is out of reach, Zone1 (index 0) is not.
    assert app_module._map_battle_zone_unlocked(conn, LOCKED_USER_ID, "k11_15") is False
    assert app_module._map_battle_zone_unlocked(conn, LOCKED_USER_ID, "k26_30") is True
    # A non-canonical zone key carries no zone-progression concept at all --
    # this mirrors `_map_battle_require_question_in_zone`'s exact treatment
    # of the same condition (a no-op passthrough for legacy callers), which
    # is what keeps `tests/test_map_battle_legacy_adapter.py`'s synthetic
    # "legacy::..." zone keys working unmodified by this gate.
    assert app_module._map_battle_zone_unlocked(conn, UNLOCKED_USER_ID, "not-a-real-zone") is True
