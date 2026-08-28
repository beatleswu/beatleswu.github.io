"""Focused F028 Battlefield Boss Mapping A acquisition contracts.

These tests exercise the route-independent service on disposable SQLite.  The
production route is intentionally not imported or modified here: its current
``app.py`` writer is separately owned by B050.  The tests therefore prove the
service contract and the exact patch boundary without pretending that the
route is already wired.
"""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from battlefield_boss_reward_service import (
    ALREADY_OWNED,
    BATTLEFIELD_BOSS_MAPPING_A_ITEM_BY_ZONE,
    BATTLEFIELD_BOSS_MAPPING_A_ZONE_BY_ZONE,
    BATTLEFIELD_BOSS_ZONE_KEYS,
    BattlefieldBossFirstClearSettlement,
    BattlefieldBossRewardError,
    GRANTED,
    NO_REWARD,
    grant_battlefield_boss_first_clear_reward,
    resolve_battlefield_boss_mapping_a_reward,
)
from mapping_a_wardrobe_runtime import (
    MAPPING_A_CATALOG,
    MAPPING_A_COMBAT_POWER,
    MAPPING_A_ID_COUNT,
    MAPPING_A_IDS,
    READY,
    consume_mapping_a_cosmetics,
)


CANONICAL_MAPPING_A_DEFINITIONS = [
    {"id": "back_pack", "name": "Pack", "slot": "back", "rarity": "common", "emoji": "🎒"},
    {"id": "hat_cloth", "name": "Cloth Hat", "slot": "hat", "rarity": "common", "emoji": "🧢"},
    {"id": "hat_bamboo", "name": "Bamboo Hat", "slot": "hat", "rarity": "common", "emoji": "🎋"},
    {"id": "robe_crane", "name": "Crane Robe", "slot": "outfit", "rarity": "uncommon", "emoji": "🪽"},
    {"id": "hat_onihorns", "name": "Oni Horns", "slot": "hat", "rarity": "rare", "emoji": "👹"},
    {"id": "robe_dragon", "name": "Dragon Robe", "slot": "outfit", "rarity": "epic", "emoji": "🐉"},
    {"id": "acc_dragon_pendant", "name": "Dragon Pendant", "slot": "accessory", "rarity": "epic", "emoji": "🔱"},
    {"id": "back_cloak", "name": "Star Cloak", "slot": "back", "rarity": "epic", "emoji": "🧥"},
    {"id": "hat_dragon_horn", "name": "Dragon Horn", "slot": "hat", "rarity": "epic", "emoji": "🐲"},
    {"id": "hat_celestial_crown", "name": "Celestial Crown", "slot": "hat", "rarity": "legendary", "emoji": "👑"},
]
PRESENTATION_REGISTRY = {
    item["id"]: {
        "asset": f"/assets/hero/items/{item['id']}.svg",
        "asset_id": item["id"],
        "pure_presentation": True,
        "functional_effect_count": 0,
        "combat_authority": "NO",
    }
    for item in CANONICAL_MAPPING_A_DEFINITIONS
}
APPEARANCE_EFFECTS = {}


def _settlement(
    zone_key: str,
    *,
    passed: bool = True,
    first_clear: bool = True,
    replay: bool = False,
) -> BattlefieldBossFirstClearSettlement:
    return BattlefieldBossFirstClearSettlement.from_authoritative_attempt(
        user_id=1,
        zone_key=zone_key,
        passed=passed,
        attempt_result={
            "operation_id": f"adventure:first_clear:1:{zone_key}",
            "is_first_clear": first_clear,
            "is_replay": replay,
        },
    )


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE player_wardrobe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'drop',
            UNIQUE(user_id, item_id)
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
            updated_at TEXT
        );
        CREATE TABLE adventure_boss_progress (
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            cleared INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, zone_key)
        );
        INSERT INTO player_appearance(user_id) VALUES (1);
        """
    )
    connection.commit()


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    _create_schema(connection)
    try:
        yield connection
    finally:
        connection.close()


def _grant_kwargs():
    return {
        "appearance_definitions": CANONICAL_MAPPING_A_DEFINITIONS,
        "presentation_registry": PRESENTATION_REGISTRY,
        "appearance_effects": APPEARANCE_EFFECTS,
        "obtained_at": "2026-08-28T00:00:00+00:00",
    }


def _projection_for_owned(item_id: str):
    definition = next(item for item in CANONICAL_MAPPING_A_DEFINITIONS if item["id"] == item_id)
    display = {
        "item_id": item_id,
        "slot": definition["slot"],
        "presentation_only": True,
    }
    return consume_mapping_a_cosmetics(
        {
            "projection_status": "OK",
            "authority": "player_wardrobe_and_player_appearance",
            "selected": {
                "outfit": None,
                "hat": None,
                "back": None,
                "title": None,
                "accessory": None,
                "pet": None,
                "aura": None,
            },
            "owned_items": [
                {
                    "item_id": item_id,
                    "slot": definition["slot"],
                    "display": display,
                    "presentation_only": True,
                    "combat_power_projected": False,
                }
            ],
            "invalid_item_ids": [],
            "invalid_selected_ids": [],
            "gameplay_effects_projected": False,
        },
        appearance_definitions=CANONICAL_MAPPING_A_DEFINITIONS,
    )


def test_f027_dependency_and_locked_zone_topology_are_exact():
    assert MAPPING_A_ID_COUNT == 10
    assert len(BATTLEFIELD_BOSS_ZONE_KEYS) == 10
    assert tuple(BATTLEFIELD_BOSS_MAPPING_A_ZONE_BY_ZONE.values()) == tuple(
        entry.zone for entry in MAPPING_A_CATALOG
    )
    assert tuple(BATTLEFIELD_BOSS_MAPPING_A_ITEM_BY_ZONE.values()) == MAPPING_A_IDS
    assert all(
        resolve_battlefield_boss_mapping_a_reward(
            zone,
            appearance_definitions=CANONICAL_MAPPING_A_DEFINITIONS,
            presentation_registry=PRESENTATION_REGISTRY,
            appearance_effects=APPEARANCE_EFFECTS,
        ).item_id
        == BATTLEFIELD_BOSS_MAPPING_A_ITEM_BY_ZONE[zone]
        for zone in BATTLEFIELD_BOSS_ZONE_KEYS
    )


@pytest.mark.parametrize("zone_key", BATTLEFIELD_BOSS_ZONE_KEYS)
def test_all_ten_first_clear_rewards_persist_without_equip_or_combat_power(conn, zone_key):
    result = grant_battlefield_boss_first_clear_reward(
        conn,
        _settlement(zone_key),
        **_grant_kwargs(),
    )

    expected_item_id = BATTLEFIELD_BOSS_MAPPING_A_ITEM_BY_ZONE[zone_key]
    assert result.status == GRANTED
    assert result.first_clear is True
    assert result.replay is False
    assert result.entitlement_consumed is True
    assert result.item_id == expected_item_id
    assert result.ownership_row_id > 0
    assert result.as_response()["auto_equip"] is False
    assert result.as_response()["compensation"] is False
    assert result.as_response()["replacement_reward"] is False
    assert result.as_response()["combat_power"] == MAPPING_A_COMBAT_POWER == 0
    assert result.as_response()["reward_item"]["equipped"] is False
    assert result.as_response()["reward_item"]["auto_equipped"] is False
    assert conn.execute(
        "SELECT item_id, source FROM player_wardrobe WHERE user_id=1"
    ).fetchone()["item_id"] == expected_item_id
    appearance = conn.execute(
        "SELECT outfit_id, hat_id, back_id, accessory_id FROM player_appearance WHERE user_id=1"
    ).fetchone()
    assert all(value is None for value in appearance)


@pytest.mark.parametrize(
    ("zone_key", "expected_item_id"),
    tuple(BATTLEFIELD_BOSS_MAPPING_A_ITEM_BY_ZONE.items()),
)
def test_integration_matrix_identity_and_f027_consumption(zone_key, expected_item_id, conn):
    result = grant_battlefield_boss_first_clear_reward(
        conn,
        _settlement(zone_key),
        **_grant_kwargs(),
    )
    assert result.item_id == expected_item_id
    projection = _projection_for_owned(expected_item_id)
    assert projection.status == READY
    assert projection.owned_ids == (expected_item_id,)
    assert projection.selected_ids == ()


def test_same_settlement_retry_is_idempotent_and_does_not_create_compensation(conn):
    settlement = _settlement("k1_5")
    first = grant_battlefield_boss_first_clear_reward(conn, settlement, **_grant_kwargs())
    changes_after_first = conn.total_changes
    retry = grant_battlefield_boss_first_clear_reward(conn, settlement, **_grant_kwargs())

    assert first.status == GRANTED
    assert retry.status == ALREADY_OWNED
    assert retry.entitlement_consumed is True
    assert retry.item_id == first.item_id
    assert retry.ownership_row_id == first.ownership_row_id
    assert conn.total_changes == changes_after_first
    assert conn.execute(
        "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1 AND item_id=?",
        (BATTLEFIELD_BOSS_MAPPING_A_ITEM_BY_ZONE["k1_5"],),
    ).fetchone()[0] == 1
    payload = retry.as_response()
    assert payload["compensation"] is False
    assert payload["replacement_reward"] is False
    assert "coins" not in payload


def test_already_owned_consumes_first_clear_entitlement_as_wardrobe_no_op(conn):
    item_id = BATTLEFIELD_BOSS_MAPPING_A_ITEM_BY_ZONE["d7_plus"]
    conn.execute(
        "INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) VALUES(?,?,?,?)",
        (1, item_id, "before-first-clear", "existing_authoritative_ownership"),
    )
    conn.commit()
    before = conn.total_changes

    result = grant_battlefield_boss_first_clear_reward(
        conn,
        _settlement("d7_plus"),
        **_grant_kwargs(),
    )

    assert result.status == ALREADY_OWNED
    assert result.entitlement_consumed is True
    assert result.item_id == item_id
    assert conn.total_changes == before
    assert conn.execute(
        "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1 AND item_id=?",
        (item_id,),
    ).fetchone()[0] == 1
    assert result.as_response()["compensation"] is False
    assert result.as_response()["replacement_reward"] is False


def test_replay_and_failed_boss_have_no_reward_or_ownership_mutation(conn):
    replay = grant_battlefield_boss_first_clear_reward(
        conn,
        _settlement("k26_30", first_clear=False, replay=True),
        **_grant_kwargs(),
    )
    failed = grant_battlefield_boss_first_clear_reward(
        conn,
        _settlement("k21_25", passed=False, first_clear=False),
        **_grant_kwargs(),
    )

    assert replay.status == NO_REWARD
    assert replay.reason_code == "REPLAY_ALREADY_CLEARED"
    assert replay.entitlement_consumed is False
    assert failed.status == NO_REWARD
    assert failed.reason_code == "BOSS_NOT_FIRST_CLEAR"
    assert conn.execute("SELECT COUNT(*) FROM player_wardrobe").fetchone()[0] == 0


def test_service_is_caller_transactional_and_rollback_removes_clear_and_reward(conn):
    conn.execute(
        "INSERT INTO adventure_boss_progress(user_id,zone_key,cleared,attempts) VALUES(?,?,?,?)",
        (1, "k26_30", 1, 1),
    )
    result = grant_battlefield_boss_first_clear_reward(
        conn,
        _settlement("k26_30"),
        **_grant_kwargs(),
    )
    assert result.status == GRANTED
    conn.rollback()

    assert conn.execute("SELECT COUNT(*) FROM adventure_boss_progress").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM player_wardrobe").fetchone()[0] == 0


def test_reload_keeps_authoritative_ownership_and_f027_consumes_it(tmp_path):
    database_path = tmp_path / "f028-reload.sqlite"
    first_connection = sqlite3.connect(database_path)
    first_connection.row_factory = sqlite3.Row
    _create_schema(first_connection)
    for zone_key in BATTLEFIELD_BOSS_ZONE_KEYS:
        grant_battlefield_boss_first_clear_reward(
            first_connection,
            _settlement(zone_key),
            **_grant_kwargs(),
        )
    first_connection.commit()
    first_connection.close()

    reloaded = sqlite3.connect(database_path)
    reloaded.row_factory = sqlite3.Row
    rows = reloaded.execute(
        "SELECT item_id FROM player_wardrobe WHERE user_id=1 ORDER BY id"
    ).fetchall()
    assert tuple(row["item_id"] for row in rows) == MAPPING_A_IDS
    for row in rows:
        projection = _projection_for_owned(row["item_id"])
        assert projection.status == READY
        assert projection.owned_ids == (row["item_id"],)
        assert projection.selected_ids == ()
    reloaded.close()


def test_unknown_zone_fails_closed_before_any_ownership_write(conn):
    with pytest.raises(BattlefieldBossRewardError) as error:
        grant_battlefield_boss_first_clear_reward(
            conn,
            _settlement("unknown-zone", first_clear=False, replay=True),
            **_grant_kwargs(),
        )
    assert error.value.code == "UNKNOWN_ZONE"
    assert conn.execute("SELECT COUNT(*) FROM player_wardrobe").fetchone()[0] == 0


def test_missing_mapping_and_non_cosmetic_metadata_fail_closed(conn):
    with pytest.raises(BattlefieldBossRewardError) as missing:
        grant_battlefield_boss_first_clear_reward(
            conn,
            _settlement("k26_30"),
            **{
                **_grant_kwargs(),
                "appearance_definitions": CANONICAL_MAPPING_A_DEFINITIONS[:-1],
            },
        )
    assert missing.value.code == "MAPPING_A_CATALOG_MISSING"

    bad_presentation = dict(PRESENTATION_REGISTRY)
    bad_presentation["back_pack"] = {
        **bad_presentation["back_pack"],
        "combat_authority": "EQUIPMENT",
    }
    with pytest.raises(BattlefieldBossRewardError) as non_cosmetic:
        grant_battlefield_boss_first_clear_reward(
            conn,
            _settlement("k26_30"),
            **{**_grant_kwargs(), "presentation_registry": bad_presentation},
        )
    assert non_cosmetic.value.code == "MAPPING_A_PRESENTATION_NOT_COSMETIC"
    assert conn.execute("SELECT COUNT(*) FROM player_wardrobe").fetchone()[0] == 0


def test_malformed_item_id_cannot_cross_typed_authority_boundary():
    with pytest.raises(BattlefieldBossRewardError) as error:
        BattlefieldBossFirstClearSettlement.from_authoritative_attempt(
            user_id=1,
            zone_key="k26_30",
            passed=True,
            attempt_result={
                "operation_id": "adventure:first_clear:1:k26_30",
                "is_first_clear": True,
                "is_replay": False,
                "reward_id": "unrelated-item",
            },
        )
    assert error.value.code == "SETTLEMENT_SHAPE_INVALID"


def test_malformed_user_and_operation_fail_closed_without_client_authority():
    with pytest.raises(BattlefieldBossRewardError) as bad_user:
        BattlefieldBossFirstClearSettlement.from_authoritative_attempt(
            user_id=0,
            zone_key="k26_30",
            passed=True,
            attempt_result={
                "operation_id": "adventure:first_clear:0:k26_30",
                "is_first_clear": True,
                "is_replay": False,
            },
        )
    assert bad_user.value.code == "INVALID_AUTHENTICATED_USER"

    with pytest.raises(BattlefieldBossRewardError) as bad_operation:
        BattlefieldBossFirstClearSettlement(
            user_id=1,
            zone_key="k26_30",
            operation_id="client-chosen-operation",
            passed=True,
            is_first_clear=True,
            is_replay=False,
        )
    assert bad_operation.value.code == "OPERATION_ID_MISMATCH"


def test_ownership_write_failure_does_not_return_fake_success(conn):
    class FailingConnection:
        def __init__(self, inner):
            self.inner = inner

        def execute(self, statement, parameters=()):
            if statement.startswith("INSERT OR IGNORE"):
                raise sqlite3.OperationalError("simulated ownership write failure")
            return self.inner.execute(statement, parameters)

    with pytest.raises(sqlite3.OperationalError, match="ownership write failure"):
        grant_battlefield_boss_first_clear_reward(
            FailingConnection(conn),
            _settlement("d1_2"),
            **_grant_kwargs(),
        )
    assert conn.execute("SELECT COUNT(*) FROM player_wardrobe").fetchone()[0] == 0


def test_world_progression_is_not_mutated_by_reward_service(conn):
    conn.execute(
        "INSERT INTO adventure_boss_progress(user_id,zone_key,cleared,attempts) VALUES(?,?,?,?)",
        (1, "k1_5", 0, 3),
    )
    conn.commit()
    before = tuple(conn.execute("SELECT * FROM adventure_boss_progress").fetchone())
    grant_battlefield_boss_first_clear_reward(
        conn,
        _settlement("k1_5"),
        **_grant_kwargs(),
    )
    after = tuple(conn.execute("SELECT * FROM adventure_boss_progress").fetchone())
    assert after == before


def test_service_has_no_route_import_or_transaction_or_world_authority():
    source_path = Path(__file__).resolve().parents[1] / "battlefield_boss_reward_service.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "app" not in imported_modules
    assert "app" not in imported_names
    assert ".commit(" not in source
    assert ".rollback(" not in source
    assert "CREATE TABLE" not in source
    assert "player_appearance" not in source
    assert "adventure_boss_progress" not in source
