import json
import os
import types
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

import community_leaderboard_rewards as lbr
import community_leaderboard_rewards_exact_period as exact_period
import community_leaderboard_rewards_scheduler as scheduler_mod
import tools.community_leaderboard_rewards_manual as manual


class DummyConn:
    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _snapshot_fixture():
    return {
        "board_type": "weekly",
        "period_key": "2026-W28",
        "timezone": "Asia/Taipei",
        "period_start": "2026-07-06",
        "period_end_exclusive": "2026-07-13",
        "entries": [
            {"user_id": 1, "display_name": "A", "avatar": None, "rank": 1, "score": 99},
            {"user_id": 2, "display_name": "B", "avatar": None, "rank": 2, "score": 25},
        ],
        "participant_counts": {
            "original_participant_count": 2,
            "ranked_participant_count": 2,
            "top_ranked_row_count": 2,
            "reward_eligible_count": 1,
        },
        "excluded_accounts": [],
    }


def _preview_fixture(snapshot):
    preview_entries = lbr.finalize_leaderboard_reward_period(
        None,
        snapshot["board_type"],
        snapshot["period_key"],
        snapshot["period_start"],
        "2026-07-12",
        snapshot["entries"],
        dry_run=True,
    )["preview"]
    summary = lbr.summarize_preview_rewards(preview_entries)
    return {
        "board_type": snapshot["board_type"],
        "period_key": snapshot["period_key"],
        "period_start": snapshot["period_start"],
        "period_end_exclusive": snapshot["period_end_exclusive"],
        "timezone": snapshot["timezone"],
        "participant_counts": snapshot["participant_counts"],
        "excluded_accounts": [],
        "preview": preview_entries,
        "summary": summary,
        "snapshot_sha256": lbr.sha256_hex_from_value(snapshot),
        "preview_sha256": lbr.sha256_hex_from_value({
            "board_type": snapshot["board_type"],
            "period_key": snapshot["period_key"],
            "period_start": snapshot["period_start"],
            "period_end_exclusive": snapshot["period_end_exclusive"],
            "timezone": snapshot["timezone"],
            "participant_counts": snapshot["participant_counts"],
            "excluded_accounts": [],
            "preview": preview_entries,
            "summary": summary,
            "snapshot_sha256": lbr.sha256_hex_from_value(snapshot),
        }),
    }


def test_operation_dir_rejects_git_worktree(monkeypatch, tmp_path):
    monkeypatch.setattr(manual, "DEFAULT_OPERATIONS_ROOT", tmp_path.resolve())
    with pytest.raises(ValueError, match="Git working tree"):
        manual._validate_operation_dir(str((manual.REPO_ROOT / "docs" / "testing").resolve()))


def test_operation_dir_must_stay_under_configured_root(monkeypatch, tmp_path):
    monkeypatch.setattr(manual, "DEFAULT_OPERATIONS_ROOT", tmp_path.resolve())
    outside = tmp_path.parent / "elsewhere" / "2026-W28"
    with pytest.raises(ValueError, match="must stay under"):
        manual._validate_operation_dir(str(outside.resolve()))


def test_snapshot_command_writes_snapshot_and_preview_to_operation_dir(monkeypatch, tmp_path):
    root = tmp_path / "reward-operations"
    monkeypatch.setattr(manual, "DEFAULT_OPERATIONS_ROOT", root.resolve())
    monkeypatch.setattr(manual, "_connect", lambda _url: DummyConn())
    snapshot = _snapshot_fixture()
    preview = _preview_fixture(snapshot)
    monkeypatch.setattr(exact_period, "build_exact_period_snapshot", lambda *a, **k: snapshot)
    monkeypatch.setattr(exact_period, "build_exact_period_preview", lambda *a, **k: preview)

    op_dir = root / "2026-W28"
    args = types.SimpleNamespace(
        board="weekly",
        period_key="2026-W28",
        period_start="2026-07-06",
        period_end="2026-07-13",
        timezone="Asia/Taipei",
        limit=50,
        database_url="postgresql://go:go@db:5432/go_odyssey",
        operation_dir=str(op_dir),
    )
    assert manual.cmd_snapshot_exact_period(args) == 0
    assert (op_dir / manual.SNAPSHOT_FILENAME).is_file()
    assert (op_dir / manual.PREVIEW_FILENAME).is_file()
    written_snapshot = json.loads((op_dir / manual.SNAPSHOT_FILENAME).read_text(encoding="utf-8"))
    written_preview = json.loads((op_dir / manual.PREVIEW_FILENAME).read_text(encoding="utf-8"))
    assert written_snapshot["period_key"] == "2026-W28"
    assert written_preview["snapshot_sha256"] == lbr.sha256_hex_from_value(snapshot)


def test_grant_exact_period_commit_requires_matching_preview_identity(monkeypatch, tmp_path):
    root = tmp_path / "reward-operations"
    monkeypatch.setattr(manual, "DEFAULT_OPERATIONS_ROOT", root.resolve())
    monkeypatch.setattr(manual, "_connect", lambda _url: DummyConn())
    snapshot = _snapshot_fixture()
    preview = _preview_fixture(snapshot)
    op_dir = manual._validate_operation_dir(str((root / "2026-W28").resolve()))
    snapshot_path, _ = manual._write_operation_json(op_dir / manual.SNAPSHOT_FILENAME, snapshot)
    preview_identity = manual._build_preview_identity_record(
        snapshot,
        preview,
        database_url="postgresql://go:go@db:5432/go_odyssey",
        snapshot_file=snapshot_path,
    )
    preview_path, _ = manual._write_operation_json(op_dir / manual.PREVIEW_FILENAME, preview_identity)

    monkeypatch.setattr(
        exact_period,
        "commit_exact_period",
        lambda *a, **k: {
            "result": "committed",
            "snapshot_sha256": preview["snapshot_sha256"],
            "preview_sha256": preview["preview_sha256"],
            "summary": preview["summary"],
        },
    )
    # cmd_grant_exact_period_commit acquires/releases the reward-sync
    # advisory lock around the (here mocked) commit_exact_period call --
    # DummyConn has no real execute(), so stub the lock functions too.
    monkeypatch.setattr(scheduler_mod, "try_acquire_period_lock", lambda conn, board_type, period_key: True)
    monkeypatch.setattr(scheduler_mod, "release_period_lock", lambda conn, board_type, period_key: None)
    args = types.SimpleNamespace(
        snapshot_file=str(snapshot_path),
        preview_file=str(preview_path),
        expected_snapshot_sha256=preview["snapshot_sha256"],
        expected_preview_sha256=preview["preview_sha256"],
        expected_claim_count=preview["summary"]["claims_count"],
        expected_component_count=preview["summary"]["component_count"],
        expected_total_coins=preview["summary"]["total_coins"],
        expected_total_items_json=json.dumps(preview["summary"]["total_items"]),
        expected_total_badges_json=json.dumps(preview["summary"]["total_badges"]),
        owner_gate=lbr.EXACT_PERIOD_OWNER_GATE,
        database_url="postgresql://go:go@db:5432/go_odyssey",
    )
    assert manual.cmd_grant_exact_period_commit(args) == 0
    assert (op_dir / manual.GRANT_RESULT_FILENAME).is_file()

    bad_preview = dict(preview_identity)
    bad_preview["snapshot_file_sha256"] = "deadbeef"
    bad_preview_path = op_dir / "bad-preview-test.json"
    bad_preview_path.write_text(json.dumps(bad_preview), encoding="utf-8")
    with pytest.raises(ValueError, match="exact snapshot file bytes"):
        manual._load_and_validate_preview_identity(
            bad_preview_path,
            snapshot=snapshot,
            snapshot_file=snapshot_path,
            database_url="postgresql://go:go@db:5432/go_odyssey",
        )

    stale_env_preview = dict(preview_identity)
    stale_env_preview["environment_identity"] = dict(stale_env_preview["environment_identity"])
    stale_env_preview["environment_identity"]["hostname"] = "stale-container-id-from-before-deploy"
    stale_env_path = op_dir / "stale-env-preview-test.json"
    stale_env_path.write_text(json.dumps(stale_env_preview), encoding="utf-8")
    manual._load_and_validate_preview_identity(
        stale_env_path,
        snapshot=snapshot,
        snapshot_file=snapshot_path,
        database_url="postgresql://go:go@db:5432/go_odyssey",
    )

    bad_flag_preview = dict(preview_identity)
    bad_flag_preview["environment_identity"] = dict(bad_flag_preview["environment_identity"])
    bad_flag_preview["environment_identity"]["production_flag"] = "not-the-real-flag"
    bad_flag_path = op_dir / "bad-flag-preview-test.json"
    bad_flag_path.write_text(json.dumps(bad_flag_preview), encoding="utf-8")
    with pytest.raises(ValueError, match="environment mismatch"):
        manual._load_and_validate_preview_identity(
            bad_flag_path,
            snapshot=snapshot,
            snapshot_file=snapshot_path,
            database_url="postgresql://go:go@db:5432/go_odyssey",
        )
