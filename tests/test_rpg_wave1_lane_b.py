"""Focused Lane B contracts for level value and monster progression."""

import ast
from pathlib import Path

import pytest

from rpg_wave1_lane_b import battlefield_profile, build_level_up_rewards


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")

ROSTER = [
    ("slime", "LV1 Slime", 80, 2, "normal"),
    ("slime", "LV1 Guard", 100, 2, "boss"),
    ("wyvern", "LV6 Wyvern", 520, 12, "normal"),
    ("dragon", "LV6 Calculator", 700, 14, "boss"),
]


@pytest.mark.parametrize(
    ("index", "stage", "attack", "kind"),
    [(0, 1, 2, "normal"), (1, 1, 2, "boss"), (2, 2, 12, "normal"), (3, 2, 14, "boss")],
)
def test_early_stronger_and_boss_profiles_are_server_defined(index, stage, attack, kind):
    profile = battlefield_profile(ROSTER, index)
    assert profile["stage"] == stage
    assert profile["attack"] == attack
    assert profile["encounter_kind"] == kind


def test_level_up_summary_exposes_hp_and_skill_value_without_attribute_points():
    summary = build_level_up_rewards(
        16,
        17,
        140,
        150,
        skill_unlocks=[{"id": "focus", "name": "專注", "name_en": "Focus"}],
    )
    assert summary["from_level"] == 16
    assert summary["to_level"] == 17
    assert summary["max_hp_gain"] == 10
    assert summary["max_hp_after"] == 150
    assert summary["skill_unlocks"][0]["id"] == "focus"
    assert summary["attribute_points"] == 0
    assert {reward["kind"] for reward in summary["rewards"]} == {"hp", "skill_eligibility"}


def test_level_hp_definition_progresses_through_wave_one_levels():
    tree = ast.parse(APP_SOURCE)
    hp_assignment = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "LV_HP" for target in node.targets)
    )
    hp_values = ast.literal_eval(hp_assignment.value)
    assert len(hp_values) == 50
    assert hp_values[0] > 0
    assert all(current < following for current, following in zip(hp_values, hp_values[1:]))


def test_level_hp_sync_is_post_commit_presentation_only_and_attribute_writer_is_not_called():
    assert "_srs_review_operation_legacy" in APP_SOURCE
    assert "player_max_hp=GREATEST(COALESCE(player_max_hp,0),?)" in APP_SOURCE
    tree = ast.parse(APP_SOURCE)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "grant_level_up_pts"
    ]
    assert calls == []


def test_retaliation_uses_authoritative_roster_and_ignores_claimed_attack():
    assert "server_q_info['monster_atk'] = profile['attack']" in APP_SOURCE
    assert "monster_atk = q_info.get('monster_atk', 8)" in APP_SOURCE
    assert APP_SOURCE.index("server_q_info['monster_atk'] = profile['attack']") > APP_SOURCE.index(
        "monster_atk = q_info.get('monster_atk', 8)"
    )
    assert "'retaliation':" in APP_SOURCE
    assert "'encounter_kind': bf_profile['encounter_kind']" in APP_SOURCE


def test_monster_hp_progression_and_reward_drop_paths_remain_server_side():
    assert "_calc_damage(grade, max_hp)" in APP_SOURCE
    assert "UPDATE battlefield_monster SET current_hp=?" in APP_SOURCE
    assert "_roll_loot(monster_type, loot_bonus)" in APP_SOURCE
    assert "INSERT INTO player_inventory(user_id,equip_id,equipped,obtained_at,source)" in APP_SOURCE
    assert "INSERT INTO monster_kill_history" in APP_SOURCE
    assert "UPDATE user_stats SET xp=xp+?, rank_xp=rank_xp+?" in APP_SOURCE


def test_boss_and_reward_regressions_are_bounded_by_existing_daily_cap():
    assert APP_SOURCE.count("'encounter_kind':") >= 2
    assert "_COIN_MONSTER_DAILY_CAP  = 40" in APP_SOURCE
    assert "_coins_earned_today(conn, uid, 'monster_kill') < _COIN_MONSTER_DAILY_CAP" in APP_SOURCE
    assert "_grant_coins(conn, _COIN_PER_MONSTER, 'monster_kill')" not in APP_SOURCE
    assert "_grant_coins(conn, uid, _COIN_PER_MONSTER, 'monster_kill')" in APP_SOURCE


def test_xp_authority_boundary_stays_off_and_no_new_writer_fragmentation():
    import xp_settlement

    assert xp_settlement.xp_ledger_schema_enabled() is False
    assert xp_settlement.xp_settlement_enabled() is False
    assert xp_settlement.xp_shadow_enabled() is False
    assert APP_SOURCE.count("grant_level_up_pts(") == 1
    assert "XP_AUTHORITY_CUTOVER" not in APP_SOURCE
    assert "LV{new_lv}" in APP_SOURCE
