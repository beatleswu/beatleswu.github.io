"""G009 EQ-F P0: server effects of the 16 EQ-F items must be OFF with the Loadout flag.

An EQ-F row that is still ``equipped=1`` while ``EQUIPMENT_CANONICAL_LOADOUT_ENABLED``
is OFF (earlier ON period, admin grant, rollback) used to keep granting damage,
retaliation reduction, XP, quest XP, loot and SP-cap effects.  Legacy items are
unchanged.  Real Flask route + isolated SQLite/PostgreSQL, no client trust.
"""

from __future__ import annotations

import math
import os
import sqlite3

import pytest

os.environ.setdefault("SECRET_KEY", "g009-eqf-flag-off-test-secret")

import app as app_module  # noqa: E402
from db import PostgresConnectionWrapper  # noqa: E402
from postgres_test_harness import disposable_postgres  # noqa: E402
from test_rpg_b021_equipment_combat_loop import (  # noqa: E402
    _inventory_conn,
    _legacy_battle,
)

FLAG = app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG
EQ_F_DEFS = tuple(app_module.EQ_F_NEW_EQUIPMENT_DEFS)
LEGACY_DEFS = tuple(app_module.EQUIPMENT_DEFS)


def _flag(monkeypatch, on):
    if on:
        monkeypatch.setenv(FLAG, "1")
    else:
        monkeypatch.delenv(FLAG, raising=False)


def test_sixteen_eq_f_items_are_the_scope():
    assert len(EQ_F_DEFS) == 16
    assert app_module._EQ_F_EQUIPMENT_IDS == {d["id"] for d in EQ_F_DEFS}
    assert not app_module._EQ_F_EQUIPMENT_IDS & {d["id"] for d in LEGACY_DEFS}


@pytest.mark.parametrize("definition", EQ_F_DEFS, ids=lambda d: d["id"])
def test_every_eq_f_effect_is_zero_when_flag_off_and_exact_when_on(definition, monkeypatch):
    conn = _inventory_conn(definition["id"])
    try:
        assert definition["effects"], definition["id"]
        for key, value in definition["effects"].items():
            _flag(monkeypatch, False)
            assert app_module._get_active_equip_effect(conn, 1, key) == 0, (definition["id"], key)
            assert app_module._get_equip_effect(conn, 1, key) == 0, (definition["id"], key)
            assert app_module._safe_active_equipment_effect(conn, 1, key) == 0
            _flag(monkeypatch, True)
            assert app_module._get_active_equip_effect(conn, 1, key) == pytest.approx(value)
            assert app_module._get_equip_effect(conn, 1, key) == pytest.approx(value)
    finally:
        conn.close()


@pytest.mark.parametrize("definition", LEGACY_DEFS, ids=lambda d: d["id"])
def test_legacy_items_are_identical_with_flag_off_and_on(definition, monkeypatch):
    conn = _inventory_conn(definition["id"])
    try:
        active = app_module._FUNCTIONAL_EFFECT_ACTIVE_KEYS.get(definition["id"], set())
        for key, value in (definition.get("effects") or {}).items():
            if isinstance(value, bool):
                continue
            expected_active = value if key in active else 0
            for on in (False, True):
                _flag(monkeypatch, on)
                assert app_module._get_active_equip_effect(conn, 1, key) == pytest.approx(expected_active)
                assert app_module._get_equip_effect(conn, 1, key) == pytest.approx(value)
    finally:
        conn.close()


def test_mixed_legacy_and_eq_f_only_legacy_counts_when_off(monkeypatch):
    conn = _inventory_conn("iron_sword", "bamboo_shadow_blade")
    try:
        _flag(monkeypatch, False)
        assert app_module._get_active_equip_effect(conn, 1, "dmg_bonus") == pytest.approx(0.12)
        stats = app_module._get_authoritative_combat_stats(conn, 1)
        assert stats["attack_bonus"] == pytest.approx(0.12)
        _flag(monkeypatch, True)
        assert app_module._get_active_equip_effect(conn, 1, "dmg_bonus") == pytest.approx(0.18)
    finally:
        conn.close()


def _damage(tmp_path, monkeypatch, name, equipment, **kw):
    return _legacy_battle(tmp_path / f"{name}.sqlite", monkeypatch, equipment=equipment, **kw)


def test_real_battle_damage_ignores_eq_f_weapon_when_off(tmp_path, monkeypatch):
    base = _damage(tmp_path, monkeypatch, "base", ())["monster"]["dmg"]
    assert base == 80
    _flag(monkeypatch, False)
    off = _damage(tmp_path, monkeypatch, "off", ((1, "bamboo_shadow_blade", 1),))
    assert off["monster"]["dmg"] == base
    assert off["combat_stats"]["attack_bonus"] == pytest.approx(0.0)
    _flag(monkeypatch, True)
    on = _damage(tmp_path, monkeypatch, "on", ((1, "bamboo_shadow_blade", 1),))
    assert on["monster"]["dmg"] == math.ceil(80 * 1.06) == 85
    _flag(monkeypatch, False)
    off_again = _damage(tmp_path, monkeypatch, "off2", ((1, "bamboo_shadow_blade", 1),))
    assert off_again["monster"]["dmg"] == base
    unequipped = _damage(tmp_path, monkeypatch, "un", ((1, "bamboo_shadow_blade", 0),))
    assert unequipped["monster"]["dmg"] == base


def test_real_battle_retaliation_ignores_eq_f_armor_when_off(tmp_path, monkeypatch):
    kw = dict(grade=0, monster_idx=11, monster_type="dragon")
    base = _damage(tmp_path, monkeypatch, "base", (), **kw)["monster"]["player_dmg"]
    assert base == 14
    _flag(monkeypatch, False)
    off = _damage(tmp_path, monkeypatch, "off", ((1, "bamboo_scale_vest", 1),), **kw)
    assert off["monster"]["player_dmg"] == base
    _flag(monkeypatch, True)
    on = _damage(tmp_path, monkeypatch, "on", ((1, "bamboo_scale_vest", 1),), **kw)
    assert on["monster"]["player_dmg"] < base


@pytest.mark.parametrize(
    "equipment,off_damage,on_damage",
    [
        ("bamboo_shadow_blade", 80, 85),   # EQ-F: gated by the flag
        ("iron_sword", 90, 90),            # legacy: not gated
    ],
)
def test_map_battle_settlement_gates_eq_f_by_flag(
    tmp_path, monkeypatch, equipment, off_damage, on_damage
):
    from test_rpg_b021_equipment_combat_loop import _map_battle_settlement

    _flag(monkeypatch, False)
    assert _map_battle_settlement(tmp_path, equipment=equipment)["damage_to_monster"] == off_damage
    _flag(monkeypatch, True)
    assert _map_battle_settlement(tmp_path, equipment=equipment)["damage_to_monster"] == on_damage


def test_legacy_weapon_unchanged_with_flag_off(tmp_path, monkeypatch):
    _flag(monkeypatch, False)
    result = _damage(tmp_path, monkeypatch, "iron", ((1, "iron_sword", 1),))
    assert result["monster"]["dmg"] == 90


def test_loot_bonus_input_ignores_eq_f_when_off(tmp_path, monkeypatch):
    import monster_settlement as ms

    seen = []
    monkeypatch.setattr(
        ms, "roll_functional_drop",
        lambda profile, loot_bonus=0.0, random_source=None: seen.append(loot_bonus) or (None, 0),
    )
    _flag(monkeypatch, False)
    _legacy_battle(tmp_path / "off.sqlite", monkeypatch, equipment=((1, "jade_river_bead", 1),), current_hp=80)
    _flag(monkeypatch, True)
    _legacy_battle(tmp_path / "on.sqlite", monkeypatch, equipment=((1, "jade_river_bead", 1),), current_hp=80)
    assert seen == [pytest.approx(0.0), pytest.approx(0.05)]


# ── real Flask route: /api/player/sp reads the SP-cap effect ───────────────


class _DbContext:
    def __init__(self, path):
        self.path = path
        self.conn = None

    def __enter__(self):
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        (self.conn.rollback if exc_type else self.conn.commit)()
        self.conn.close()


def _sqlite_sp_db(path, rows, *, today_row):
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE player_inventory(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,"
            "equip_id TEXT NOT NULL,equipped INTEGER NOT NULL DEFAULT 0,obtained_at TEXT,source TEXT)"
        )
        conn.execute(
            "CREATE TABLE player_sp(user_id INTEGER PRIMARY KEY,current_sp INTEGER,sp_date TEXT,daily_used TEXT)"
        )
        for i, (equip_id, equipped) in enumerate(rows, 1):
            conn.execute(
                "INSERT INTO player_inventory(id,user_id,equip_id,equipped,obtained_at,source) VALUES(?,?,?,?,?,?)",
                (i, 1, equip_id, equipped, "2026-10-12", "test"),
            )
        if today_row:
            import datetime

            conn.execute(
                "INSERT INTO player_sp VALUES(1,5,?,?)", (datetime.date.today().isoformat(), "{}")
            )


def _client(monkeypatch, ctx_factory, user_id=1):
    monkeypatch.setattr(app_module, "get_db", ctx_factory)
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    if user_id is not None:
        with client.session_transaction() as session:
            session["user_id"] = user_id
            session["username"] = "g009-eqf-test"
    return client


SP = app_module.SP_MAX_DAILY


@pytest.mark.parametrize("today_row", [False, True])
@pytest.mark.parametrize(
    "equip_id,off_bonus,on_bonus",
    [
        ("riverguard_coat", 0, 8),
        ("dragon_scale", 30, 30),  # legacy: unchanged by the flag
        ("jade_river_bead", 0, 0),
    ],
)
def test_real_sp_route_cap_follows_flag_for_eq_f_only(
    tmp_path, monkeypatch, equip_id, off_bonus, on_bonus, today_row
):
    path = tmp_path / "sp.sqlite"
    _sqlite_sp_db(path, [(equip_id, 1)], today_row=today_row)
    client = _client(monkeypatch, lambda: _DbContext(path))
    _flag(monkeypatch, False)
    assert client.get("/api/player/sp").get_json()["max_sp"] == SP + off_bonus
    _flag(monkeypatch, True)
    assert client.get("/api/player/sp").get_json()["max_sp"] == SP + on_bonus
    _flag(monkeypatch, False)
    assert client.get("/api/player/sp").get_json()["max_sp"] == SP + off_bonus


def test_real_sp_route_unequipped_eq_f_never_counts(tmp_path, monkeypatch):
    path = tmp_path / "sp-unequipped.sqlite"
    _sqlite_sp_db(path, [("riverguard_coat", 0)], today_row=True)
    client = _client(monkeypatch, lambda: _DbContext(path))
    for on in (False, True):
        _flag(monkeypatch, on)
        assert client.get("/api/player/sp").get_json()["max_sp"] == SP


def test_sp_route_requires_a_player_session(tmp_path, monkeypatch):
    path = tmp_path / "sp-anon.sqlite"
    _sqlite_sp_db(path, [("riverguard_coat", 1)], today_row=True)
    client = _client(monkeypatch, lambda: _DbContext(path), user_id=None)
    _flag(monkeypatch, True)
    assert client.get("/api/player/sp").status_code != 200


def test_gain_sp_cap_uses_flag_gated_effect(tmp_path, monkeypatch):
    path = tmp_path / "gain.sqlite"
    _sqlite_sp_db(path, [("riverguard_coat", 1)], today_row=True)
    for on, cap in ((False, SP), (True, SP + 8)):
        _flag(monkeypatch, on)
        with _DbContext(path) as conn:
            conn.execute("UPDATE player_sp SET current_sp=?", (SP,))
            assert app_module._gain_sp(conn, 1, 10_000) == cap


def test_equip_route_still_blocked_with_flag_off_and_row_unchanged(tmp_path, monkeypatch):
    path = tmp_path / "equip.sqlite"
    _sqlite_sp_db(path, [("bamboo_shadow_blade", 1), ("iron_sword", 0)], today_row=False)
    client = _client(monkeypatch, lambda: _DbContext(path))
    _flag(monkeypatch, False)
    for inv_id, action in ((2, "equip"), (1, "unequip")):
        response = client.post("/api/player/inventory/equip", json={"inv_id": inv_id, "action": action})
        assert response.status_code == 409
        assert response.get_json() == {"error": "LOADOUT_DISABLED"}
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT id,equipped FROM player_inventory ORDER BY id").fetchall() == [(1, 1), (2, 0)]


# ── PostgreSQL parity (disposable container) ───────────────────────────────


def _pg_connect(url):
    import psycopg2
    from psycopg2.extras import DictCursor

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


class _PgContext:
    def __init__(self, url):
        self.url = url
        self.conn = None

    def __enter__(self):
        self.conn = _pg_connect(self.url)
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        (self.conn.rollback if exc_type else self.conn.commit)()
        self.conn.close()


@pytest.fixture()
def eqf_pg_url():
    with disposable_postgres(name_prefix="g009-eqf") as record:
        url = str(record["database_url"])
        conn = _pg_connect(url)
        try:
            conn.execute(
                "CREATE TABLE player_inventory(id SERIAL PRIMARY KEY,user_id INTEGER NOT NULL,"
                "equip_id TEXT NOT NULL,equipped INTEGER NOT NULL DEFAULT 0,obtained_at TEXT,source TEXT)"
            )
            conn.execute(
                "CREATE TABLE player_sp(user_id INTEGER PRIMARY KEY,current_sp INTEGER,sp_date TEXT,daily_used TEXT)"
            )
            conn.execute(
                "CREATE TABLE player_skills(user_id INTEGER NOT NULL,skill_id TEXT NOT NULL,"
                "equipped INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(user_id,skill_id))"
            )
            conn.commit()
        finally:
            conn.close()
        yield url


def test_postgres_flag_off_eq_f_effects_are_zero_and_legacy_unchanged(eqf_pg_url, monkeypatch):
    conn = _pg_connect(eqf_pg_url)
    try:
        for equip_id in ("riverguard_coat", "bamboo_shadow_blade", "dragon_scale", "iron_sword"):
            conn.execute(
                "INSERT INTO player_inventory(user_id,equip_id,equipped,obtained_at,source) VALUES(?,?,?,?,?)",
                (7, equip_id, 1, "2026-10-12", "eqf-test"),
            )
        conn.commit()
    finally:
        conn.close()
    client = _client(monkeypatch, lambda: _PgContext(eqf_pg_url), user_id=7)

    _flag(monkeypatch, False)
    conn = _pg_connect(eqf_pg_url)
    try:
        stats = app_module._get_authoritative_combat_stats(conn, 7, "dragon")
    finally:
        conn.close()
    assert stats["attack_bonus"] == pytest.approx(0.12)  # iron_sword only; no bamboo_shadow_blade
    assert client.get("/api/player/sp").get_json()["max_sp"] == SP + 30  # dragon_scale only

    _flag(monkeypatch, True)
    conn = _pg_connect(eqf_pg_url)
    try:
        stats = app_module._get_authoritative_combat_stats(conn, 7, "dragon")
    finally:
        conn.close()
    assert stats["attack_bonus"] == pytest.approx(0.18)
    assert client.get("/api/player/sp").get_json()["max_sp"] == SP + 30 + 8
