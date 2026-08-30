"""Inventory gate for the explicitly reused legacy Lord contracts.

Lane B does not repair these behaviors.  This test prevents the architecture
contract commit from silently dropping the existing test ownership while Lane
A changes the Lord review path.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


LEGACY_CONTRACTS = {
    "signed_attempt_identity": (
        "tests/test_e10_lord_autonext_harness_foundation.py",
        ("BOSS_ATTEMPT_SIGNED", "BOSS_ATTEMPT_CONTEXT_ENFORCED", "forged_boss_context_error"),
    ),
    "same_session_progression": (
        "tests/e2e/run_e10_lord_trial_owner_acceptance_regression.mjs",
        ("afterCorrect", "answered_count", "real correct board answer"),
    ),
    "exactly_one_finish": (
        "tests/e2e/run_e10_lord_trial_owner_acceptance_regression.mjs",
        ("finishCalls", "exactly", "finish"),
    ),
    "replay_zero_rewards": (
        "tests/test_adventure_first_clear_reward.py",
        (
            "class TestReplayGrantsNothing",
            "body['reward']['coins'] == 0",
            "coins, log = _coins_and_log",
            "assert log == []",
        ),
    ),
    "daily_limit_exemption": (
        "tests/test_e10_lord_trial_daily_limit_autonext.py",
        ("daily", "limit", "boss"),
    ),
    "visible_board_recovery": (
        "tests/e2e/run_e10_lord_trial_visible_board_recovery_contract.mjs",
        ("visible", "recovery", "RETURN_MAP_VISIBLE"),
    ),
    "zone_audio": (
        "tests/test_e10_zone1_lord_trial_art_integration.py",
        ("audio", "Zone 1", "lord"),
    ),
}


def test_legacy_lord_contract_owners_remain_present():
    for name, (relative, needles) in LEGACY_CONTRACTS.items():
        path = REPO_ROOT / relative
        assert path.is_file(), f"legacy contract owner missing for {name}: {relative}"
        text = path.read_text(encoding="utf-8").lower()
        missing = [needle for needle in needles if needle.lower() not in text]
        assert not missing, f"{name} lost contract markers: {missing}"
