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


def _function_source(name):
    tree = ast.parse(APP_SOURCE)
    node = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )
    lines = APP_SOURCE.splitlines()
    return "\n".join(lines[node.lineno - 1 : node.end_lineno])


def test_level_hp_sync_is_atomic_and_attribute_writer_is_not_called():
    assert "_srs_review_operation_legacy" in APP_SOURCE
    assert "player_max_hp=GREATEST(COALESCE(player_max_hp,0),?)" in APP_SOURCE
    assert "existing_player_max_hp = int(s['player_max_hp'] or 0)" in APP_SOURCE
    assert "'player_max_hp': max(existing_player_max_hp, _lv_max_hp(new_lv))" in APP_SOURCE
    tree = ast.parse(APP_SOURCE)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "grant_level_up_pts"
    ]
    assert calls == []


def test_level_hp_writer_precedes_core_commit_and_optional_monster_work():
    update_at = APP_SOURCE.index("'''UPDATE user_stats SET")
    hp_at = APP_SOURCE.index(
        "player_max_hp=GREATEST(COALESCE(player_max_hp,0),?)", update_at
    )
    commit_at = APP_SOURCE.index("        conn.commit()", hp_at)
    optional_at = APP_SOURCE.index(
        "monster_data = _update_monster_and_quests", commit_at
    )
    assert update_at < hp_at < commit_at < optional_at
    assert "player_max_hp=GREATEST" not in _function_source(
        "_lane_b_review_with_level_value"
    )


def test_level_wrapper_is_read_only_and_uses_committed_response_state():
    wrapper = _function_source("_lane_b_review_with_level_value")
    assert "_lane_b_level_snapshot(uid)" in wrapper
    assert "stats.get('player_max_hp')" in wrapper
    assert "actual_max_hp = int(persisted_max_hp or 0)" in wrapper
    assert "build_level_up_rewards(" in wrapper
    assert "UPDATE user_stats" not in wrapper
    assert "level_conn.execute" not in wrapper
    assert "level_conn.commit" not in wrapper


def test_duplicate_reviews_and_skill_unlocks_stay_non_mutating_at_lane_boundary():
    wrapper = _function_source("_lane_b_review_with_level_value")
    skill_reader = _function_source("_lane_b_level_skill_unlocks")
    assert "not payload.get('ranked_up')" in wrapper
    assert "should_grant_review_progress" in APP_SOURCE
    assert "progress_credited" in APP_SOURCE
    assert "conn.execute" not in skill_reader
    assert "conn.commit" not in skill_reader
    assert "grant_level_up_pts" not in skill_reader


def test_appearance_milestone_remains_in_canonical_review_flow():
    review = _function_source("_srs_review_operation")
    assert "if ranked_up:" in review
    assert "give_rank_appearance(conn, uid, new_rank_level)" in review
    assert "new_appearance_items" in review


def test_retaliation_uses_authoritative_roster_and_ignores_claimed_attack():
    assert "server_q_info['monster_atk'] = profile['attack']" in APP_SOURCE
    assert "monster_atk = q_info.get('monster_atk', 8)" in APP_SOURCE
    assert APP_SOURCE.index("server_q_info['monster_atk'] = profile['attack']") > APP_SOURCE.index(
        "monster_atk = q_info.get('monster_atk', 8)"
    )
    assert "'retaliation':" in APP_SOURCE
    assert "'encounter_kind': bf_profile['encounter_kind']" in APP_SOURCE


def test_monster_hp_progression_and_reward_drop_paths_remain_server_side():
    assert "dmg_dealt = _calc_damage(grade, max_hp" in APP_SOURCE
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
