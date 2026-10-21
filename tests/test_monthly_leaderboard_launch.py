"""October 2026 monthly leaderboard launch acceptance (no production writes)."""
import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import community_leaderboard_rewards as rewards
import community_leaderboard_rewards_scheduler as scheduler
from tools.community_leaderboard_rewards_real_grant_commit import _grant_title_component

TZ = ZoneInfo("Asia/Taipei")


def test_launch_boundary_and_no_historical_backfill():
    october = scheduler.get_monthly_scheduler_target(
        datetime.datetime(2026, 10, 18, 12, 0, tzinfo=TZ))
    assert october["period_key"] == "2026-09"
    assert october["is_due"] is False
    before = scheduler.get_monthly_scheduler_target(
        datetime.datetime(2026, 11, 1, 0, 9, tzinfo=TZ))
    assert before["is_due"] is False
    opened = scheduler.get_monthly_scheduler_target(
        datetime.datetime(2026, 11, 1, 0, 10, tzinfo=TZ))
    assert opened["is_due"] is True
    assert opened["period_start"] == "2026-10-01"
    assert opened["period_end_exclusive"] == "2026-11-01"
    assert opened["period_key"] == "2026-10"
    january = scheduler.get_monthly_scheduler_target(
        datetime.datetime(2027, 1, 1, 0, 10, tzinfo=TZ))
    assert january["period_start"] == "2026-12-01"
    assert january["period_key"] == "2026-12"


def test_monthly_catalog_reward_bundles_and_qualifiers():
    rules = rewards.get_monthly_leaderboard_reward_rules()
    assert rules["minimum_score"] == 150
    assert rules["delivery"] == "automatic"
    assert [(b["rank_min"], b["rank_max"]) for b in rules["rank_bands"]] == [
        (1, 1), (2, 3), (4, 10), (11, 25), (26, 50)]
    assert not rewards.is_leaderboard_reward_eligible("monthly", 149)
    assert rewards.is_leaderboard_reward_eligible("monthly", 150)
    champion = rewards._process_leaderboard_entry(
        "monthly", dict(user_id=25, display_name="Test02", rank=1, score=150))
    assert champion["eligible"] is True
    assert champion["reward_payload"]["coins"] == 1500
    assert champion["reward_payload"]["titles"] == ["title_monthly_master"]
    assert champion["reward_payload"]["badges"] == ["badge_lb_monthly_1"]
    low_score = rewards._process_leaderboard_entry(
        "monthly", dict(user_id=25, display_name="Test02", rank=1, score=149))
    assert low_score["eligible"] is False
    assert low_score["reward_payload"]["coins"] == 0
    for band in rules["rank_bands"]:
        for component in band["rewards"]:
            if component["type"] == "item":
                assert rewards.is_phase_3b_item_key_allowed(component["key"])
            if component["type"] == "badge":
                assert rewards.is_phase_3b_badge_key_allowed(component["key"])
    assert rules["rank_bands"][0]["rewards"][-1] == {
        "type": "title", "key": "title_monthly_master"}


def test_test_accounts_not_excluded_from_snapshot_policy():
    source = Path("tools/community_leaderboard_rewards_exact_period.py").read_text("utf-8")
    assert '"test_accounts_eligible": True' in source
    assert '"admin_accounts_eligible": True' in source


def test_title_component_is_idempotent_per_claim():
    class FakeConn:
        def __init__(self):
            self.logged = set()
        def execute(self, query, args=None):
            class Cursor:
                def fetchone(self): return None
            if "leaderboard_reward_component_log" in query and "INSERT" in query:
                self.logged.add((args["claim_id"], args["component"], args["reward_key"]))
            return Cursor()
    conn = FakeConn()
    owned = set()
    def has_ownership(uid, key): return (uid, key) in owned
    def grant_title(uid, key): owned.add((uid, key))
    first = _grant_title_component(conn, grant_title, has_ownership,
                                   claim_id=10, user_id=25, title_key="title_monthly_master")
    assert first["result"] == "granted"
    assert owned == {(25, "title_monthly_master")}
    second = _grant_title_component(conn, grant_title, has_ownership,
                                    claim_id=11, user_id=25, title_key="title_monthly_master")
    assert second["result"] == "granted"
    assert owned == {(25, "title_monthly_master")}


def test_monthly_reward_notification_includes_title_without_granting():
    payload = rewards.build_reward_notification_payload({
        "id": 8, "board_type": "monthly", "period_key": "2026-10",
        "rank": 1, "rank_band": "top1",
        "granted_coins": 1500,
        "granted_items_json": '{"rare_appearance_fragment":2}',
        "granted_badges_json": '["badge_lb_monthly_1"]',
        "granted_titles_json": '["title_monthly_master"]',
        "granted_at": "2026-11-01T00:10:00+08:00",
    })
    assert payload["board"] == "monthly"
    assert payload["rewards"] == [
        {"type": "coins", "amount": 1500},
        {"type": "item", "key": "rare_appearance_fragment", "quantity": 2},
        {"type": "badge", "key": "badge_lb_monthly_1"},
        {"type": "title", "key": "title_monthly_master"},
    ]


def test_monthly_not_due_does_not_touch_database(monkeypatch):
    monkeypatch.setattr(scheduler, "_community_rewards_flag_enabled", lambda app: True)
    class FakeApp:
        def get_db(self):
            raise AssertionError("monthly not-due must not open DB")
    result = scheduler.run_community_leaderboard_monthly_cycle(
        FakeApp(), now=datetime.datetime(2026, 10, 18, 12, 0, tzinfo=TZ))
    assert result["result"] == "not_due_noop"
    assert result["board_type"] == "monthly"
