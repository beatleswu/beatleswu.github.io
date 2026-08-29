"""A046 retirement contracts for legacy player appearance combat fields."""

from __future__ import annotations

import ast
import os
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "a046-legacy-authority-retirement-test-secret")
import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
INVENTORY = (ROOT / "inventory.html").read_text(encoding="utf-8")

LEGACY_FIELDS = (
    "combat_armor",
    "combat_weapon",
    "combat_cape",
    "combat_offhand",
    "combat_hat",
    "combat_pet",
    "combat_aura",
    "combat_acc",
)
SOCIAL_FIELDS = LEGACY_FIELDS[:-1]


def _function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"missing function: {name}")


class _DbContext:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()


def _create_appearance_db(path: Path, *, existing: bool) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE player_appearance(
                user_id INTEGER PRIMARY KEY,
                character_key TEXT,
                updated_at TEXT,
                outfit_id TEXT,
                hat_id TEXT,
                back_id TEXT,
                title_id TEXT,
                accessory_id TEXT,
                pet_id TEXT,
                aura_id TEXT,
                combat_armor TEXT,
                combat_weapon TEXT,
                combat_cape TEXT,
                combat_offhand TEXT,
                combat_hat TEXT,
                combat_pet TEXT,
                combat_aura TEXT,
                combat_acc TEXT
            )
            """
        )
        if existing:
            conn.execute(
                """
                INSERT INTO player_appearance(
                    user_id, character_key, updated_at,
                    combat_armor, combat_weapon, combat_cape, combat_offhand,
                    combat_hat, combat_pet, combat_aura, combat_acc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    1,
                    "apprentice",
                    "before",
                    "armor_t5",
                    "weapon_t5",
                    "cape_t4",
                    "offhand_t3",
                    "hat_t2",
                    "pet_t1",
                    "aura_t4",
                    "acc_t3",
                ),
            )


def _client_for(path: Path, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(path))
    monkeypatch.setattr(app_module, "is_premium", lambda _uid: False)
    monkeypatch.setattr(
        app_module,
        "_compute_title_metrics",
        lambda *_args, **_kwargs: {
            "go_rank": "30k",
            "total_correct": 0,
            "units_done": 0,
            "max_streak": 0,
            "challenge_wins": 0,
            "mistake_corrected": 0,
            "total_answered": 0,
            "precision": 0,
            "dragon_kills": 0,
            "strength": 0,
        },
    )
    monkeypatch.setattr(
        app_module,
        "_cosmetic_unlocked",
        lambda *_args, **_kwargs: True,
    )
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "a046-test"
    return client


def _appearance_values(path: Path):
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT character_key, updated_at, "
            + ", ".join(LEGACY_FIELDS)
            + " FROM player_appearance WHERE user_id=1"
        ).fetchone()


def test_legacy_modifier_reader_no_longer_consumes_any_combat_field():
    effects = _function_source(APP, "_get_appearance_effects")

    assert "APPEARANCE_EFFECTS" in effects
    assert "FROM player_inventory" not in effects
    assert all(field not in effects for field in LEGACY_FIELDS)
    assert "_rank_to_tier" not in effects
    assert "_gear_unlocked" not in effects


def test_appearance_effects_keep_compatibility_shape_but_ignore_legacy_modifiers():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE player_appearance(
            user_id INTEGER PRIMARY KEY,
            aura_id TEXT,
            combat_armor TEXT,
            combat_weapon TEXT,
            combat_cape TEXT,
            combat_offhand TEXT,
            combat_hat TEXT,
            combat_pet TEXT,
            combat_aura TEXT,
            combat_acc TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO player_appearance(
            user_id, aura_id, combat_armor, combat_weapon, combat_cape,
            combat_offhand, combat_hat, combat_pet, combat_aura, combat_acc
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (1, "aura_green", "armor_t10", "weapon_t10", "cape_t10",
         "offhand_t10", "hat_t10", "pet_t10", "aura_t10", "acc_t10"),
    )
    try:
        assert app_module._get_appearance_effects(1, conn) == {
            "xp_bonus": 0.05,
            "drop_bonus": 0.0,
        }
    finally:
        conn.close()


def test_skills_character_rejects_new_compatibility_values_and_preserves_existing_data(
    tmp_path: Path, monkeypatch
):
    path = tmp_path / "existing-appearance.sqlite"
    _create_appearance_db(path, existing=True)
    client = _client_for(path, monkeypatch)
    before = _appearance_values(path)

    payload = {"character_key": "swordsman"}
    payload.update({field: f"new_{field}" for field in LEGACY_FIELDS})
    response = client.post("/api/skills/character", json=payload)

    assert response.status_code == 200
    assert set(response.get_json()["rejected"]) == set(LEGACY_FIELDS)
    after = _appearance_values(path)
    assert after[2:] == before[2:]
    assert after[0] == "swordsman"


def test_skills_character_cannot_create_new_compatibility_values(
    tmp_path: Path, monkeypatch
):
    path = tmp_path / "new-appearance.sqlite"
    _create_appearance_db(path, existing=False)
    client = _client_for(path, monkeypatch)
    payload = {"character_key": "apprentice"}
    payload.update({field: f"new_{field}" for field in LEGACY_FIELDS})

    response = client.post("/api/skills/character", json=payload)

    assert response.status_code == 200
    assert set(response.get_json()["rejected"]) == set(LEGACY_FIELDS)
    row = _appearance_values(path)
    assert row[0] == "apprentice"
    assert all(value is None for value in row[2:])


def test_social_avatar_read_window_remains_read_only():
    row = {
        "character_key": "apprentice",
        **{field: f"legacy_{field}" for field in SOCIAL_FIELDS},
        "is_premium": 0,
    }
    payload = app_module._row_loadout(row)

    assert {field: payload[field] for field in SOCIAL_FIELDS} == {
        field: row[field] for field in SOCIAL_FIELDS
    }
    assert "combat_acc" not in payload

    character = _function_source(APP, "skills_character")
    assert all(field not in character for field in LEGACY_FIELDS)
    assert "player_inventory" in character


def test_legacy_compatibility_writer_has_no_ownership_or_grant_path():
    character = _function_source(APP, "skills_character")

    for forbidden in (
        "grant_equipment_ownership(",
        "equip_owned_item(",
        "unequip_owned_item(",
        "INSERT INTO player_inventory",
        "UPDATE player_inventory",
    ):
        assert forbidden not in character


def test_legacy_combat_fields_cannot_change_server_damage():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE player_inventory("
        "id INTEGER PRIMARY KEY, user_id INTEGER, equip_id TEXT, equipped INTEGER)"
    )
    conn.execute(
        "INSERT INTO player_inventory(id,user_id,equip_id,equipped) "
        "VALUES(1,1,'wooden_sword',1)"
    )
    try:
        stats = app_module._get_authoritative_combat_stats(conn, 1)
        assert stats["attack_bonus"] == pytest.approx(0.05)
        assert app_module._calc_damage(5, 1000, attack_bonus=0.0) == 80
        assert app_module._calc_damage(5, 1000, attack_bonus=0.05) == 84
        assert app_module._calc_damage(5, 1000, attack_bonus=0.12) == 90
    finally:
        conn.close()


def test_canonical_equipment_and_product_gates_remain_closed():
    assert len(app_module.EQUIPMENT_DEFS) == 15
    assert app_module.INVENTORY_ONLY_EQUIPMENT_IDS == {"go_stone_black"}
    assert app_module._functional_equipment_payload(
        next(item for item in app_module.EQUIPMENT_DEFS if item["id"] == "xp_amulet")
    )["active_effect_details"] == []
    assert app_module._functional_equipment_payload(
        next(item for item in app_module.EQUIPMENT_DEFS if item["id"] == "go_stone_black")
    )["active_effect_details"] == []
    assert "const FUNCTIONAL_EQUIPMENT_LOADOUT_ENABLED = false;" in INVENTORY
    assert "EQUIPMENT_CANONICAL_LOADOUT_ENABLED" in APP
    assert "CANONICAL_COIN_SHOP_PURCHASE_ENABLED" in APP
