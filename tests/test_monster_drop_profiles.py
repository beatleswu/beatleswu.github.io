"""F005 canonical Monster drop registry contracts."""

import ast
from pathlib import Path

from monster_drop_profiles import (
    CANONICAL_DROP_PROFILE_REGISTRY,
    CANONICAL_MONSTER_DROP_MATRIX,
    DROP_PROFILE_REGISTRY_COUNT,
    DROP_STATUS_DEFINED_BUT_UNREACHABLE,
    DROP_STATUS_LEGACY_ONLY,
    DROP_STATUS_REACHABLE,
    get_drop_profile,
    get_drop_profile_for_monster,
)
from monster_profiles import CANONICAL_MONSTER_PROFILE_REGISTRY


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
DROP_SOURCE = (ROOT / "monster_drop_profiles.py").read_text(encoding="utf-8")


def _assignment(name):
    tree = ast.parse(APP_SOURCE)
    node = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    )
    return ast.literal_eval(node.value)


BASE_LOOT_CHANCE = _assignment("BASE_LOOT_CHANCE")
EQUIPMENT_DEFS = _assignment("EQUIPMENT_DEFS")


def test_all_f004_drop_references_resolve_and_registry_has_legacy_only_goblin():
    f004_ids = {
        profile.drop_profile_id
        for profile in CANONICAL_MONSTER_PROFILE_REGISTRY.profiles
    }
    assert DROP_PROFILE_REGISTRY_COUNT == 10
    assert f004_ids <= set(CANONICAL_DROP_PROFILE_REGISTRY)
    assert get_drop_profile("unknown-drop-profile") is None
    assert CANONICAL_DROP_PROFILE_REGISTRY["drop_legacy_goblin"].status == DROP_STATUS_LEGACY_ONLY


def test_drop_entries_preserve_exact_current_equipment_source_values():
    expected = {}
    for equipment in EQUIPMENT_DEFS:
        for legacy_type in equipment.get("drop_from", ()):
            expected.setdefault(legacy_type, []).append(
                (equipment["id"], equipment["drop_weight"])
            )

    for profile in CANONICAL_DROP_PROFILE_REGISTRY.values():
        actual = [(entry.item_id, entry.relative_weight) for entry in profile.entries]
        assert actual == expected.get(profile.legacy_monster_type, [])
        assert profile.gate_chance == BASE_LOOT_CHANCE.get(profile.legacy_monster_type, 0.20)
        assert all(entry.quantity == 1 for entry in profile.entries)
        assert all(entry.gate_condition == "monster_defeated" for entry in profile.entries)


def test_twenty_monster_drop_matrix_is_explicit_about_reachability():
    assert len(CANONICAL_MONSTER_DROP_MATRIX) == 20
    assert all(row.drop_profile_resolves for row in CANONICAL_MONSTER_DROP_MATRIX)
    assert sum(row.runtime_currently_reachable for row in CANONICAL_MONSTER_DROP_MATRIX) == 7
    assert sum(
        row.status == DROP_STATUS_DEFINED_BUT_UNREACHABLE
        for row in CANONICAL_MONSTER_DROP_MATRIX
    ) == 13
    assert sum(row.status == DROP_STATUS_REACHABLE for row in CANONICAL_MONSTER_DROP_MATRIX) == 7

    assert get_drop_profile_for_monster("legacy_bf_01_normal").entries == ()
    assert get_drop_profile_for_monster("legacy_bf_06_boss").entries
    assert get_drop_profile_for_monster("not-a-monster") is None


def test_drop_registry_has_no_settlement_or_schema_writer():
    assert "def settle_map_battle_submission" not in DROP_SOURCE
    assert "def _update_monster_and_quests" not in DROP_SOURCE
    assert "CREATE TABLE" not in DROP_SOURCE
    assert "conn.execute" not in DROP_SOURCE
    assert "DROP_RATE_CHANGED" not in DROP_SOURCE
