from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_scheduler_script_starts_premium_and_community_threads():
    text = (REPO_ROOT / "scheduler.py").read_text(encoding="utf-8")
    assert "_start_premium_weekly_scheduler" in text
    assert "_start_community_leaderboard_weekly_scheduler" in text
    assert "COMMUNITY_LEADERBOARD_WEEKLY_ENABLED" not in text
