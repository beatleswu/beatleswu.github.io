"""P0-2: pre-E055 Adventure Zone 3 Map Battle state must not strand a player.

The Production failure this covers: "Map Battle is temporarily unavailable; no
battle fallback was used", backed by HTTP 503
``map_battle_judge_unavailable: Adventure Zone 3 Monster binding is
unavailable``.

The stranded state is an OPEN ``map_battles`` row for zone ``k16_20`` written
before E055, carrying the generic legacy provenance ``legacy-adventure-map`` /
``map-battle-v1``.  ``/api/map-battle/start`` looks up the player's OPEN battle
for the zone before creating a new one, so that single row makes *every*
subsequent Zone 3 request fail closed -- the player can never reach a battle
that would be bound correctly.

These tests use the real ``map_battles`` schema and the real E055 decoder, so
the reproduction is the actual row shape rather than a stand-in.
"""

from __future__ import annotations

import sqlite3

import pytest

from adventure_zone3_legacy_compatibility import (
    LEGACY_MAP_BATTLE_MIGRATION_SOURCE,
    LEGACY_MAP_BATTLE_MIGRATION_VERSION,
    is_legacy_zone3_battle,
    legacy_zone3_battle_is_retirable,
    retire_legacy_zone3_battle,
)
from adventure_zone3_monster_authority import (
    ZONE3_KEY,
    Zone3MonsterAuthorityError,
    decode_zone3_binding,
    encode_zone3_binding,
    select_zone3_binding,
)
from map_battle_persistence import create_map_battle, ensure_map_battle_tables

USER_ID = 4242


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO users(id) VALUES (?)", (USER_ID,))
    ensure_map_battle_tables(conn)
    return conn


def _legacy_zone3_battle(conn, *, state: str = "OPEN") -> dict:
    """Create the exact pre-E055 Zone 3 row shape seen in Production."""
    battle_id = create_map_battle(
        conn,
        user_id=USER_ID,
        zone_key=ZONE3_KEY,
        player_hp=80,
        player_hp_max=100,
        monster_hp=60,
        monster_hp_max=100,
        migration_source=LEGACY_MAP_BATTLE_MIGRATION_SOURCE,
        migration_version=LEGACY_MAP_BATTLE_MIGRATION_VERSION,
    )
    if state != "OPEN":
        conn.execute(
            "UPDATE map_battles SET state=?, completed_at=? WHERE id=?",
            (state, "2026-08-30T10:00:00" if state == "COMPLETED" else None, battle_id),
        )
    return _load(conn, battle_id)


def _e055_zone3_battle(conn, *, question_id: int = 55001) -> dict:
    binding = select_zone3_binding(question_id)
    battle_id = create_map_battle(
        conn,
        user_id=USER_ID,
        zone_key=ZONE3_KEY,
        player_hp=100,
        player_hp_max=100,
        monster_hp=100,
        monster_hp_max=100,
        migration_source="adventure-zone3-monster-catalog",
        migration_version=encode_zone3_binding(binding),
    )
    return _load(conn, battle_id)


def _load(conn, battle_id: str) -> dict:
    return dict(
        conn.execute("SELECT * FROM map_battles WHERE id=?", (battle_id,)).fetchone()
    )


def _open_for_zone(conn, zone_key: str):
    row = conn.execute(
        "SELECT * FROM map_battles WHERE user_id=? AND zone_key=? AND state='OPEN'"
        " ORDER BY updated_at DESC LIMIT 1",
        (USER_ID, zone_key),
    ).fetchone()
    return dict(row) if row else None


# --------------------------------------------------------------------------
# Reproduce the exact Production failure
# --------------------------------------------------------------------------


def test_legacy_zone3_state_reproduces_the_production_503():
    conn = _db()
    battle = _legacy_zone3_battle(conn)
    with pytest.raises(Zone3MonsterAuthorityError) as excinfo:
        decode_zone3_binding(battle)
    assert "binding source is missing" in str(excinfo.value)


def test_legacy_zone3_battle_is_recognised_exactly():
    conn = _db()
    assert is_legacy_zone3_battle(_legacy_zone3_battle(conn)) is True
    assert is_legacy_zone3_battle(_e055_zone3_battle(conn)) is False
    assert is_legacy_zone3_battle(None) is False
    assert is_legacy_zone3_battle({}) is False


# --------------------------------------------------------------------------
# Recovery
# --------------------------------------------------------------------------


def test_stranded_legacy_battle_is_retired_and_zone_becomes_usable_again():
    conn = _db()
    battle = _legacy_zone3_battle(conn)
    assert _open_for_zone(conn, ZONE3_KEY) is not None

    assert legacy_zone3_battle_is_retirable(battle) is True
    assert retire_legacy_zone3_battle(conn, user_id=USER_ID, battle=battle) is True

    # The zone is free, so the next request creates a properly bound battle.
    assert _open_for_zone(conn, ZONE3_KEY) is None
    replacement = _e055_zone3_battle(conn)
    assert decode_zone3_binding(replacement).zone_key == ZONE3_KEY


def test_retirement_settles_nothing():
    """DUPLICATE_REWARD_RISK / DUPLICATE_PROGRESS_RISK must both stay NO."""
    conn = _db()
    battle = _legacy_zone3_battle(conn)
    retire_legacy_zone3_battle(conn, user_id=USER_ID, battle=battle)

    retired = _load(conn, battle["id"])
    assert retired["state"] == "EXPIRED"
    # Never COMPLETED and never stamped: it cannot be read as a clear, and no
    # settlement, drop, coin, star or Boss clear can be replayed from it.
    assert retired["completed_at"] is None
    assert retired["monster_hp"] == battle["monster_hp"]
    assert retired["player_hp"] == battle["player_hp"]


# --------------------------------------------------------------------------
# Server authority is preserved
# --------------------------------------------------------------------------


def test_completed_legacy_battle_is_never_touched():
    conn = _db()
    battle = _legacy_zone3_battle(conn, state="COMPLETED")
    assert legacy_zone3_battle_is_retirable(battle) is False
    assert retire_legacy_zone3_battle(conn, user_id=USER_ID, battle=battle) is False
    assert _load(conn, battle["id"])["state"] == "COMPLETED"


def test_concurrent_settlement_wins_over_retirement():
    """A battle completed between the read and the write is not overwritten."""
    conn = _db()
    battle = _legacy_zone3_battle(conn)
    conn.execute(
        "UPDATE map_battles SET state='COMPLETED', completed_at=? WHERE id=?",
        ("2026-08-31T09:00:00", battle["id"]),
    )
    # `battle` is the pre-settlement snapshot, exactly as a racing request holds.
    assert retire_legacy_zone3_battle(conn, user_id=USER_ID, battle=battle) is False
    assert _load(conn, battle["id"])["state"] == "COMPLETED"


def test_e055_bound_battle_is_never_retired():
    conn = _db()
    battle = _e055_zone3_battle(conn)
    assert legacy_zone3_battle_is_retirable(battle) is False
    assert retire_legacy_zone3_battle(conn, user_id=USER_ID, battle=battle) is False


def test_corrupt_e055_binding_still_fails_closed():
    """Corruption or tampering is not legacy state and must not be recovered."""
    conn = _db()
    battle = _e055_zone3_battle(conn)
    battle["migration_version"] = "e055.zone3.binding.v1:M999:bogus:bogus"
    assert legacy_zone3_battle_is_retirable(battle) is False
    with pytest.raises(Zone3MonsterAuthorityError):
        decode_zone3_binding(battle)


def test_other_zones_are_untouched():
    conn = _db()
    battle_id = create_map_battle(
        conn,
        user_id=USER_ID,
        zone_key="k21_25",
        player_hp=100,
        player_hp_max=100,
        monster_hp=100,
        monster_hp_max=100,
        migration_source=LEGACY_MAP_BATTLE_MIGRATION_SOURCE,
        migration_version=LEGACY_MAP_BATTLE_MIGRATION_VERSION,
    )
    battle = _load(conn, battle_id)
    assert legacy_zone3_battle_is_retirable(battle) is False
    assert retire_legacy_zone3_battle(conn, user_id=USER_ID, battle=battle) is False
    assert _load(conn, battle_id)["state"] == "OPEN"


def test_another_owner_cannot_retire_someone_elses_battle():
    conn = _db()
    battle = _legacy_zone3_battle(conn)
    assert retire_legacy_zone3_battle(conn, user_id=USER_ID + 1, battle=battle) is False
    assert _load(conn, battle["id"])["state"] == "OPEN"


def test_no_monster_identity_is_ever_invented_for_legacy_state():
    """The legacy row records no Monster, and none is synthesized for it."""
    import inspect

    import adventure_zone3_legacy_compatibility as module

    source = inspect.getsource(module)
    assert "select_zone3_binding" not in source
    assert "encode_zone3_binding" not in source
