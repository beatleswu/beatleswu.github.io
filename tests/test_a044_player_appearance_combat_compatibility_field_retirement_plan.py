"""Static completeness checks for the A044 compatibility-field decision packet."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
HERO = (ROOT / "hero.html").read_text(encoding="utf-8")
COMMUNITY = (ROOT / "community.html").read_text(encoding="utf-8")
MESSAGES = (ROOT / "messages.html").read_text(encoding="utf-8")
BOT = (ROOT / "bot.html").read_text(encoding="utf-8")
MIGRATION = (ROOT / "migrations" / "equipment_canonical_slot_v1.py").read_text(
    encoding="utf-8"
)

FIELDS = (
    "combat_armor",
    "combat_weapon",
    "combat_cape",
    "combat_offhand",
    "combat_hat",
    "combat_pet",
    "combat_aura",
    "combat_acc",
)
SOCIAL_LOADOUT_FIELDS = set(FIELDS) - {"combat_acc"}


def _function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"missing function: {name}")


def test_field_reader_inventory_is_complete_and_classified():
    assert len(FIELDS) == 8
    assert len(set(FIELDS)) == 8

    appearance_effects = _function_source(APP, "_get_appearance_effects")
    appearance_api = _function_source(APP, "get_appearance")
    social_projection = _function_source(APP, "_row_loadout")
    for field in FIELDS:
        assert field in APP
        assert field in appearance_effects
    for field in {"combat_armor", "combat_weapon", "combat_cape", "combat_offhand"}:
        assert field in appearance_api
    for field in SOCIAL_LOADOUT_FIELDS:
        assert field in social_projection
    assert "combat_acc" not in social_projection


def test_field_writer_inventory_is_complete_and_classified():
    server_writer = _function_source(APP, "skills_character")
    for field in FIELDS:
        assert field in server_writer

    # The only browser-side batch writer is retained as a disabled legacy
    # compatibility branch; A044 must not turn it into a new authority.
    assert "HERO_LEGACY_LOADOUT_EFFECTIVE = false" in HERO
    hero_writer = HERO[HERO.index("function saveLoadoutToServer()"):]
    for field in FIELDS:
        assert field in hero_writer


def test_authority_boundary_and_canonical_replacement_are_explicit():
    combat_authority = _function_source(APP, "_get_authoritative_combat_stats")
    appearance_effects = _function_source(APP, "_get_appearance_effects")
    review = _function_source(APP, "_srs_review_operation")

    assert "player_inventory" in combat_authority
    assert "EQUIPMENT_DEFS" in combat_authority
    assert not any(field in combat_authority for field in FIELDS)
    assert "Legacy combat-field values remain visible" in appearance_effects
    assert "_get_appearance_effects" not in review
    assert "_safe_active_equipment_effect" in review

    assert "CANONICAL_SLOTS = (\"weapon\", \"armor\", \"accessory\")" in MIGRATION
    assert "canonical_slot" in MIGRATION
    assert "UNIQUE_INDEX_NAME" in MIGRATION
    assert "VALIDITY_CONSTRAINT_NAME" in MIGRATION


def test_client_and_compatibility_surface_inventory_has_no_unknown_reader():
    # Bot, Community, and Messages consume server-serialized compatibility
    # avatar data only. They do not read localStorage or calculate combat.
    assert "appear.combat_armor" in BOT
    assert "appear.combat_weapon" in BOT
    for field in SOCIAL_LOADOUT_FIELDS:
        assert field in COMMUNITY
        assert field in MESSAGES
    for source in (BOT, COMMUNITY, MESSAGES):
        assert "localStorage.getItem('hero_combat_gear_v1'" not in source
        assert "player_inventory" not in source
        assert "dmg_bonus" not in source
