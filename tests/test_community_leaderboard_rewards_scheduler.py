from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_scheduler_does_not_enable_community_leaderboard_rewards():
    text = (REPO_ROOT / "scheduler.py").read_text(encoding="utf-8")
    assert "COMMUNITY_LEADERBOARD_REWARDS_ENABLED" not in text
    assert "community_leaderboard" not in text.lower()
    assert "_start_premium_weekly_scheduler" in text
