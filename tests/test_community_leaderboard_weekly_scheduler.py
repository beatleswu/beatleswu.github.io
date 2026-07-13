import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import community_leaderboard_rewards as lbr
import community_leaderboard_rewards_scheduler as scheduler


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message, payload):
        self.messages.append((message, payload))


class FakeConn:
    def __init__(self):
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def close(self):
        self.close_calls += 1


class FakeAppModule:
    def __init__(self, enabled, conn):
        self._enabled = enabled
        self._conn = conn
        self.app = SimpleNamespace(logger=FakeLogger())

    def _env_flag_enabled(self, name):
        assert name == scheduler.COMMUNITY_LEADERBOARD_WEEKLY_ENABLED
        return self._enabled

    def get_db(self):
        return self._conn


def _make_snapshot(period_key="2026-W28"):
    snapshot = {
        "board_type": "weekly",
        "period_key": period_key,
        "timezone": "Asia/Taipei",
        "period_start": "2026-07-06",
        "period_end_exclusive": "2026-07-13",
        "entries": [
            {
                "user_id": 101,
                "display_name": "Alice",
                "avatar": "sage",
                "rank": 1,
                "rank_band": "top1",
                "score": 300,
                "eligible": True,
                "reward_bundle_key": "weekly_top1",
                "reward_payload": {
                    "coins": 500,
                    "items": {"xp_potion": 2},
                    "badges": ["badge_lb_weekly_1"],
                    "titles": [],
                },
                "ineligible_reason": None,
            }
        ],
        "participant_counts": {
            "original_participant_count": 1,
            "ranked_participant_count": 1,
            "top_ranked_row_count": 1,
            "reward_eligible_count": 1,
        },
        "excluded_accounts": [],
    }
    preview = {
        "board_type": snapshot["board_type"],
        "period_key": snapshot["period_key"],
        "period_start": snapshot["period_start"],
        "period_end_exclusive": snapshot["period_end_exclusive"],
        "timezone": snapshot["timezone"],
        "participant_counts": snapshot["participant_counts"],
        "excluded_accounts": [],
        "preview": snapshot["entries"],
        "summary": {
            "claims_count": 1,
            "snapshot_row_count": 1,
            "eligible_claim_count": 1,
            "non_rewarded_row_count": 0,
            "component_count": 3,
            "total_coins": 500,
            "total_items": {"xp_potion": 2},
            "total_badges": {"badge_lb_weekly_1": 1},
            "total_titles": {},
        },
    }
    preview["snapshot_sha256"] = lbr.sha256_hex_from_value(snapshot)
    preview["preview_sha256"] = lbr.sha256_hex_from_value(preview)
    return snapshot, preview


def test_weekly_scheduler_target_respects_taipei_monday_boundary():
    before_due = datetime.datetime(2026, 7, 12, 16, 9, tzinfo=datetime.timezone.utc)
    target = scheduler.get_weekly_scheduler_target(now=before_due)
    assert target["period_key"] == "2026-W28"
    assert target["period_start"] == "2026-07-06"
    assert target["period_end_exclusive"] == "2026-07-13"
    assert target["is_due"] is False

    at_due = datetime.datetime(2026, 7, 12, 16, 10, tzinfo=datetime.timezone.utc)
    due_target = scheduler.get_weekly_scheduler_target(now=at_due)
    assert due_target["period_key"] == "2026-W28"
    assert due_target["is_due"] is True


def test_weekly_scheduler_target_catches_up_later_in_week():
    tuesday = datetime.datetime(2026, 7, 14, 10, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    target = scheduler.get_weekly_scheduler_target(now=tuesday)
    assert target["period_key"] == "2026-W28"
    assert target["is_due"] is True


def test_disabled_env_noops_without_db_or_files(tmp_path):
    conn = FakeConn()
    app_module = FakeAppModule(enabled=False, conn=conn)

    result = scheduler.run_community_leaderboard_weekly_cycle(
        app_module,
        now=datetime.datetime(2026, 7, 13, 0, 10, tzinfo=ZoneInfo("Asia/Taipei")),
        operations_root=tmp_path,
    )

    assert result["result"] == "disabled_noop"
    assert conn.commit_calls == 0
    assert conn.rollback_calls == 0
    assert conn.close_calls == 0
    assert list(tmp_path.iterdir()) == []


def test_lock_busy_noops_without_creating_operation_dir(monkeypatch, tmp_path):
    conn = FakeConn()
    app_module = FakeAppModule(enabled=True, conn=conn)
    monkeypatch.setattr(scheduler, "try_acquire_period_lock", lambda conn, board_type, period_key: False)
    monkeypatch.setattr(scheduler, "release_period_lock", lambda conn, board_type, period_key: None)

    result = scheduler.run_community_leaderboard_weekly_cycle(
        app_module,
        now=datetime.datetime(2026, 7, 13, 0, 10, tzinfo=ZoneInfo("Asia/Taipei")),
        operations_root=tmp_path,
    )

    assert result["result"] == "lock_busy_noop"
    assert conn.rollback_calls == 1
    assert conn.close_calls == 1
    assert list(tmp_path.iterdir()) == []


def test_success_flow_writes_operation_files_and_commits(monkeypatch, tmp_path):
    conn = FakeConn()
    app_module = FakeAppModule(enabled=True, conn=conn)
    snapshot, preview = _make_snapshot()
    release_calls = []

    monkeypatch.setattr(scheduler, "try_acquire_period_lock", lambda conn, board_type, period_key: True)
    monkeypatch.setattr(
        scheduler,
        "release_period_lock",
        lambda conn, board_type, period_key: release_calls.append((board_type, period_key)),
    )
    monkeypatch.setattr(scheduler, "build_exact_period_snapshot", lambda *args, **kwargs: snapshot)
    monkeypatch.setattr(scheduler, "build_exact_period_preview", lambda payload: preview)
    monkeypatch.setattr(
        scheduler,
        "commit_exact_period",
        lambda *args, **kwargs: {
            "result": "committed",
            "snapshot_sha256": preview["snapshot_sha256"],
            "preview_sha256": preview["preview_sha256"],
            "summary": preview["summary"],
        },
    )
    monkeypatch.setattr(
        scheduler,
        "summarize_post_grant_state",
        lambda *args, **kwargs: {
            "claims_count": 1,
            "granted_claim_count": 1,
            "non_granted_claim_count": 0,
            "total_coins": 500,
            "unacknowledged_notification_count": 1,
            "component_count": 3,
            "total_items": {"xp_potion": 2},
            "total_badges": {"badge_lb_weekly_1": 1},
        },
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://go:go@postgres:5432/go_odyssey")
    monkeypatch.setenv("PRODUCTION", "1")

    result = scheduler.run_community_leaderboard_weekly_cycle(
        app_module,
        now=datetime.datetime(2026, 7, 13, 0, 10, tzinfo=ZoneInfo("Asia/Taipei")),
        operations_root=tmp_path,
    )

    op_dir = tmp_path / "2026-W28"
    assert result["result"] == "committed"
    assert result["claim_count"] == 1
    assert conn.commit_calls == 1
    assert conn.rollback_calls == 0
    assert conn.close_calls == 1
    assert release_calls == [("weekly", "2026-W28")]
    assert (op_dir / "snapshot.json").exists()
    assert (op_dir / "preview.json").exists()
    assert (op_dir / "grant-result.json").exists()
    preview_identity = json.loads((op_dir / "preview.json").read_text(encoding="utf-8"))
    assert preview_identity["snapshot_sha256"] == preview["snapshot_sha256"]


def test_existing_claim_path_returns_already_granted_noop(monkeypatch, tmp_path):
    conn = FakeConn()
    app_module = FakeAppModule(enabled=True, conn=conn)
    snapshot, preview = _make_snapshot()

    monkeypatch.setattr(scheduler, "try_acquire_period_lock", lambda conn, board_type, period_key: True)
    monkeypatch.setattr(scheduler, "release_period_lock", lambda conn, board_type, period_key: None)
    monkeypatch.setattr(scheduler, "build_exact_period_snapshot", lambda *args, **kwargs: snapshot)
    monkeypatch.setattr(scheduler, "build_exact_period_preview", lambda payload: preview)
    monkeypatch.setattr(
        scheduler,
        "commit_exact_period",
        lambda *args, **kwargs: {
            "result": "already_granted_noop",
            "snapshot_sha256": preview["snapshot_sha256"],
            "preview_sha256": preview["preview_sha256"],
            "summary": preview["summary"],
        },
    )
    monkeypatch.setattr(
        scheduler,
        "summarize_post_grant_state",
        lambda *args, **kwargs: {
            "claims_count": 1,
            "granted_claim_count": 1,
            "non_granted_claim_count": 0,
            "total_coins": 500,
            "unacknowledged_notification_count": 1,
            "component_count": 3,
            "total_items": {"xp_potion": 2},
            "total_badges": {"badge_lb_weekly_1": 1},
        },
    )

    result = scheduler.run_community_leaderboard_weekly_cycle(
        app_module,
        now=datetime.datetime(2026, 7, 15, 10, 0, tzinfo=ZoneInfo("Asia/Taipei")),
        operations_root=tmp_path,
    )

    assert result["result"] == "already_granted_noop"
    assert conn.commit_calls == 1


def test_failure_rolls_back_and_closes(monkeypatch, tmp_path):
    conn = FakeConn()
    app_module = FakeAppModule(enabled=True, conn=conn)

    monkeypatch.setattr(scheduler, "try_acquire_period_lock", lambda conn, board_type, period_key: True)
    monkeypatch.setattr(scheduler, "release_period_lock", lambda conn, board_type, period_key: None)
    monkeypatch.setattr(
        scheduler,
        "build_exact_period_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        scheduler.run_community_leaderboard_weekly_cycle(
            app_module,
            now=datetime.datetime(2026, 7, 13, 0, 10, tzinfo=ZoneInfo("Asia/Taipei")),
            operations_root=tmp_path,
        )

    assert conn.rollback_calls == 1
    assert conn.commit_calls == 0
    assert conn.close_calls == 1
