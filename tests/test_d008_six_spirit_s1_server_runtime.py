"""Focused D008 server-catalog and projection contracts."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from spirit_lineage import LEGACY_COSMETIC_PET_IDS, validate_functional_spirit_id
from spirit_runtime import (
    CANONICAL_SPIRIT_CATALOG,
    CANONICAL_SPIRIT_IDS,
    SPIRIT_STAGE_VALUES,
    SPIRIT_UNLOCK_LEVELS,
    build_b022_active_spirit_projection,
    build_spirit_projection,
    stage_for_level,
    validate_server_spirit_id,
)


def _state_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE pet_collection(
            user_id INTEGER NOT NULL,
            pet_key TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 1,
            xp INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, pet_key)
        );
        CREATE TABLE user_pets(
            user_id INTEGER PRIMARY KEY,
            pet_key TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 1,
            xp INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    return conn


def test_catalog_is_one_data_driven_six_spirit_authority():
    assert CANONICAL_SPIRIT_IDS == (
        "ink_drop_kelpie",
        "whispering_void_kit",
        "star_shell_hatchling",
        "starpath_antlerling",
        "fatty",
        "obsidian_bastion",
    )
    assert tuple(CANONICAL_SPIRIT_CATALOG) == CANONICAL_SPIRIT_IDS
    assert len(CANONICAL_SPIRIT_CATALOG) == 6
    assert tuple(item["slot"] for item in CANONICAL_SPIRIT_CATALOG.values()) == (
        1, 2, 3, 4, 5, 6
    )
    assert all(item["stage_values"] == SPIRIT_STAGE_VALUES for item in CANONICAL_SPIRIT_CATALOG.values())
    assert SPIRIT_UNLOCK_LEVELS[:3] == (1, 11, 16)
    assert SPIRIT_UNLOCK_LEVELS[3:] == (None, None, None)
    assert all(item["presentation_manifest_is_ownership_authority"] is False
               for item in CANONICAL_SPIRIT_CATALOG.values())


@pytest.mark.parametrize("level,expected", [(1, "STAGE_I"), (9, "STAGE_I"),
                                             (10, "STAGE_II"), (24, "STAGE_II"),
                                             (25, "STAGE_III")])
def test_stage_is_server_derived(level, expected):
    assert stage_for_level(level) == expected


def test_projection_uses_pet_collection_and_rehydrates_one_active_spirit():
    conn = _state_db()
    try:
        conn.execute(
            "INSERT INTO pet_collection(user_id,pet_key,level,xp) VALUES(1,?,?,?)",
            ("ink_drop_kelpie", 10, 7),
        )
        conn.execute(
            "INSERT INTO pet_collection(user_id,pet_key,level,xp) VALUES(1,?,?,?)",
            ("starpath_antlerling", 1, 0),
        )
        conn.execute(
            "INSERT INTO user_pets(user_id,pet_key,level,xp) VALUES(1,?,?,?)",
            ("starpath_antlerling", 1, 0),
        )
        projection = build_spirit_projection(conn, 1)
        assert projection["canonical_spirit_count"] == 6
        assert projection["active_spirit_id"] == "starpath_antlerling"
        assert projection["ownership_validated"] is True
        assert sum(item["active"] for item in projection["spirits"]) == 1
        assert projection["spirits"][3]["owned"] is True
        assert projection["spirits"][3]["evolution_stage"] == "STAGE_I"
        b022 = build_b022_active_spirit_projection(conn, 1)
        assert b022 == {
            "active_spirit_id": "starpath_antlerling",
            "ownership_validated": True,
            "evolution_stage": "STAGE_I",
            "progression_level": 1,
            "effect_profile_id": None,
            "effect_policy_version": None,
            "enabled": True,
            "source": "server_transactional_spirit_projection",
        }
    finally:
        conn.close()


def test_orphan_active_state_fails_closed_for_b022():
    conn = _state_db()
    try:
        conn.execute(
            "INSERT INTO user_pets(user_id,pet_key,level,xp) VALUES(1,?,?,?)",
            ("fatty", 1, 0),
        )
        projection = build_spirit_projection(conn, 1)
        assert projection["active_spirit_id"] is None
        assert projection["ownership_validated"] is False
        assert build_b022_active_spirit_projection(conn, 1)["enabled"] is False
    finally:
        conn.close()


def test_unknown_and_legacy_ids_fail_closed():
    with pytest.raises(ValueError, match="unknown Spirit"):
        validate_server_spirit_id("not-a-spirit")
    with pytest.raises(ValueError, match="unknown functional Spirit"):
        validate_functional_spirit_id("not-a-spirit")
    for legacy_id in LEGACY_COSMETIC_PET_IDS:
        with pytest.raises(ValueError):
            validate_functional_spirit_id(legacy_id)


def test_runtime_routes_consume_b023_and_do_not_define_combat_effects():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert "execute_companion_operation" in source
    assert "commit_evolution_transition" in source
    assert "build_b022_active_spirit_projection" in source
    assert "SPIRIT_EFFECT_BEFORE_JUDGE" not in source
    assert "SECOND_COMBAT_ENGINE" not in source
