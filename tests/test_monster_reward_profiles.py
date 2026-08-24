"""F005 canonical Monster reward registry contracts."""

from pathlib import Path

from monster_profiles import CANONICAL_MONSTER_PROFILE_REGISTRY
from monster_reward_profiles import (
    CANONICAL_MONSTER_REWARD_MATRIX,
    CANONICAL_REWARD_PROFILE_REGISTRY,
    REWARD_PROFILE_REGISTRY_COUNT,
    get_reward_profile,
    get_reward_profile_for_monster,
)


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
REWARD_SOURCE = (ROOT / "monster_reward_profiles.py").read_text(encoding="utf-8")


def test_all_twenty_f004_reward_references_resolve_to_one_explicit_legacy_profile():
    ids = {
        profile.reward_profile_id
        for profile in CANONICAL_MONSTER_PROFILE_REGISTRY.profiles
    }
    assert REWARD_PROFILE_REGISTRY_COUNT == 1
    assert ids == {"reward_battlefield_legacy"}
    assert ids <= set(CANONICAL_REWARD_PROFILE_REGISTRY)
    assert get_reward_profile("unknown-reward-profile") is None


def test_current_coin_item_and_xp_authorities_are_not_falsely_unified():
    profile = CANONICAL_REWARD_PROFILE_REGISTRY["reward_battlefield_legacy"]

    assert profile.coins == 2
    assert profile.coin_daily_cap == 40
    assert profile.xp is None
    assert profile.xp_authority == "review_settlement.calc_xp_gain; not Monster-specific"
    assert profile.item_components == (
        "functional_equipment_drop",
        "cosmetic_appearance_drop",
    )
    assert profile.status == "FRAGMENTED_LEGACY_COMPATIBILITY"
    assert get_reward_profile_for_monster("legacy_bf_10_boss") is profile


def test_reward_matrix_has_no_missing_or_unknown_profiles():
    assert len(CANONICAL_MONSTER_REWARD_MATRIX) == 20
    assert all(row.reward_profile_resolves for row in CANONICAL_MONSTER_REWARD_MATRIX)
    assert all(row.runtime_currently_reachable for row in CANONICAL_MONSTER_REWARD_MATRIX)
    assert all(not row.xp_is_monster_specific for row in CANONICAL_MONSTER_REWARD_MATRIX)
    assert {row.coins_per_kill for row in CANONICAL_MONSTER_REWARD_MATRIX} == {2}


def test_reward_registry_has_no_d5_or_runtime_writer():
    assert "append_spirit_reward_event" not in REWARD_SOURCE
    assert "append_spirit_item_use_event" not in REWARD_SOURCE
    assert "def settle_map_battle_submission" not in REWARD_SOURCE
    assert "def _update_monster_and_quests" not in REWARD_SOURCE
    assert "CREATE TABLE" not in REWARD_SOURCE
    assert "conn.execute" not in REWARD_SOURCE


def test_current_sources_are_present_for_boundary_audit():
    assert "_COIN_PER_MONSTER" in APP_SOURCE
    assert "_COIN_MONSTER_DAILY_CAP" in APP_SOURCE
    assert "_grant_coins" in APP_SOURCE
    assert "player_inventory" in APP_SOURCE
    assert "player_wardrobe" in APP_SOURCE
    assert "calc_xp_gain" in APP_SOURCE
