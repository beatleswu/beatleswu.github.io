import contextlib
import datetime
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

import community_leaderboard_rewards as lbr
import community_leaderboard_rewards_scheduler as scheduler
from community_leaderboard_rewards_exact_period import create_scheduler_commit_authorization


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

    def _env_flag_exact_true(self, name):
        assert name == scheduler.COMMUNITY_LEADERBOARD_REWARDS_ENABLED
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


def _result_payload(logger):
    assert logger.messages
    message, payload = logger.messages[-1]
    assert message == "[community_leaderboard_weekly] %s"
    return json.loads(payload)


def test_weekly_scheduler_target_monday_boundary_and_catchup_contract():
    before_due = datetime.datetime(2026, 7, 13, 0, 9, 59, tzinfo=ZoneInfo("Asia/Taipei"))
    target = scheduler.get_weekly_scheduler_target(now=before_due)
    assert target["period_key"] == "2026-W28"
    assert target["period_start"] == "2026-07-06"
    assert target["period_end_exclusive"] == "2026-07-13"
    assert target["is_due"] is False

    at_due = datetime.datetime(2026, 7, 13, 0, 10, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    due_target = scheduler.get_weekly_scheduler_target(now=at_due)
    assert due_target["period_key"] == "2026-W28"
    assert due_target["is_due"] is True

    later_monday = datetime.datetime(2026, 7, 13, 9, 0, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    assert scheduler.get_weekly_scheduler_target(now=later_monday)["period_key"] == "2026-W28"

    thursday = datetime.datetime(2026, 7, 16, 10, 0, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    thursday_target = scheduler.get_weekly_scheduler_target(now=thursday)
    assert thursday_target["period_key"] == "2026-W28"
    assert thursday_target["is_due"] is True

    later_week = datetime.datetime(2026, 7, 20, 0, 10, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    assert scheduler.get_weekly_scheduler_target(now=later_week)["period_key"] == "2026-W29"


def test_next_scheduler_check_at_uses_bounded_sixty_second_wakeups():
    before_due = datetime.datetime(2026, 7, 13, 0, 9, 20, tzinfo=ZoneInfo("Asia/Taipei"))
    assert scheduler.next_scheduler_check_at(now=before_due) == datetime.datetime(
        2026, 7, 13, 0, 10, 0, tzinfo=ZoneInfo("Asia/Taipei")
    )

    after_due = datetime.datetime(2026, 7, 13, 0, 10, 5, tzinfo=ZoneInfo("Asia/Taipei"))
    assert scheduler.next_scheduler_check_at(now=after_due) == datetime.datetime(
        2026, 7, 13, 0, 11, 5, tzinfo=ZoneInfo("Asia/Taipei")
    )


def test_disabled_env_noops_without_db_lock_or_files(tmp_path):
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
    payload = _result_payload(app_module.app.logger)
    assert payload["result"] == "disabled_noop"


def test_not_due_noop_returns_before_db_connection_or_files(tmp_path):
    conn = FakeConn()
    app_module = FakeAppModule(enabled=True, conn=conn)

    result = scheduler.run_community_leaderboard_weekly_cycle(
        app_module,
        now=datetime.datetime(2026, 7, 13, 0, 9, 59, tzinfo=ZoneInfo("Asia/Taipei")),
        operations_root=tmp_path,
    )

    assert result["result"] == "not_due_noop"
    assert conn.commit_calls == 0
    assert conn.rollback_calls == 0
    assert conn.close_calls == 0
    assert list(tmp_path.iterdir()) == []


def test_lock_busy_noop_does_not_create_operation_dir(monkeypatch, tmp_path):
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
    payload = _result_payload(app_module.app.logger)
    assert payload["result"] == "lock_busy_noop"


def test_success_flow_writes_operation_files_uses_scheduler_auth_and_commits(monkeypatch, tmp_path):
    conn = FakeConn()
    app_module = FakeAppModule(enabled=True, conn=conn)
    snapshot, preview = _make_snapshot()
    release_calls = []
    commit_kwargs = {}

    monkeypatch.setattr(scheduler, "try_acquire_period_lock", lambda conn, board_type, period_key: True)
    monkeypatch.setattr(
        scheduler,
        "release_period_lock",
        lambda conn, board_type, period_key: release_calls.append((board_type, period_key)),
    )
    monkeypatch.setattr(scheduler, "build_exact_period_snapshot", lambda *args, **kwargs: snapshot)
    monkeypatch.setattr(scheduler, "build_exact_period_preview", lambda payload: preview)

    def fake_commit(*args, **kwargs):
        commit_kwargs.update(kwargs)
        return {
            "result": "committed",
            "snapshot_sha256": preview["snapshot_sha256"],
            "preview_sha256": preview["preview_sha256"],
            "summary": preview["summary"],
        }

    monkeypatch.setattr(scheduler, "commit_exact_period", fake_commit)
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
    monkeypatch.setenv("DATABASE_URL", "postgresql://go:secret@postgres:5432/go_odyssey")
    monkeypatch.setenv("PRODUCTION", "1")
    monkeypatch.setenv("COMMUNITY_LEADERBOARD_REWARDS_ENABLED", "true")

    result = scheduler.run_community_leaderboard_weekly_cycle(
        app_module,
        now=datetime.datetime(2026, 7, 13, 0, 10, tzinfo=ZoneInfo("Asia/Taipei")),
        operations_root=tmp_path,
    )

    op_dir = tmp_path / "2026-W28"
    preview_identity = json.loads((op_dir / "preview.json").read_text(encoding="utf-8"))
    assert result["result"] == "granted"
    assert conn.commit_calls == 1
    assert conn.rollback_calls == 0
    assert conn.close_calls == 1
    assert release_calls == [("weekly", "2026-W28")]
    assert (op_dir / "snapshot.json").exists()
    assert (op_dir / "preview.json").exists()
    assert (op_dir / "grant-result.json").exists()
    assert preview_identity["snapshot_sha256"] == preview["snapshot_sha256"]
    assert preview_identity["snapshot_file_sha256"] == scheduler._sha256_hex_bytes(
        (op_dir / "snapshot.json").read_bytes()
    )
    auth = commit_kwargs["scheduler_authorization"]
    assert getattr(auth, "board_type") == "weekly"
    assert getattr(auth, "period_key") == "2026-W28"
    assert getattr(auth, "flag_name") == "COMMUNITY_LEADERBOARD_REWARDS_ENABLED"
    assert getattr(auth, "flag_enabled") is True
    assert "owner_gate" not in commit_kwargs or commit_kwargs["owner_gate"] is None


def test_existing_claim_path_returns_controlled_noop(monkeypatch, tmp_path):
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
    monkeypatch.setenv("COMMUNITY_LEADERBOARD_REWARDS_ENABLED", "true")

    result = scheduler.run_community_leaderboard_weekly_cycle(
        app_module,
        now=datetime.datetime(2026, 7, 15, 10, 0, tzinfo=ZoneInfo("Asia/Taipei")),
        operations_root=tmp_path,
    )

    assert result["result"] == "already_granted_noop"
    assert conn.commit_calls == 1


def test_failed_closed_logs_and_rolls_back(monkeypatch, tmp_path):
    conn = FakeConn()
    app_module = FakeAppModule(enabled=True, conn=conn)

    monkeypatch.setattr(scheduler, "try_acquire_period_lock", lambda conn, board_type, period_key: True)
    monkeypatch.setattr(scheduler, "release_period_lock", lambda conn, board_type, period_key: None)
    monkeypatch.setattr(
        scheduler,
        "build_exact_period_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = scheduler.run_community_leaderboard_weekly_cycle(
        app_module,
        now=datetime.datetime(2026, 7, 13, 0, 10, tzinfo=ZoneInfo("Asia/Taipei")),
        operations_root=tmp_path,
    )

    assert result["result"] == "failed_closed"
    assert conn.rollback_calls == 1
    assert conn.commit_calls == 0
    assert conn.close_calls == 1
    payload = _result_payload(app_module.app.logger)
    assert payload["result"] == "failed_closed"
    assert payload["snapshot_sha_prefix"] == ""
    assert payload["preview_sha_prefix"] == ""


def test_preview_identity_rejects_changed_snapshot_bytes_database_and_environment(monkeypatch, tmp_path):
    snapshot, preview = _make_snapshot()
    monkeypatch.setenv("DATABASE_URL", "postgresql://go:secret@postgres:5432/go_odyssey")
    monkeypatch.setenv("PRODUCTION", "1")
    snapshot_file = scheduler._write_exact_json(tmp_path / "snapshot.json", snapshot)
    preview_identity = scheduler.build_preview_identity_record(
        snapshot,
        preview,
        database_url=os.environ["DATABASE_URL"],
        snapshot_file=snapshot_file,
    )

    scheduler.validate_preview_identity(
        dict(preview_identity),
        snapshot=snapshot,
        snapshot_file=snapshot_file,
        database_url=os.environ["DATABASE_URL"],
    )

    snapshot_file.write_bytes(snapshot_file.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="exact snapshot file bytes"):
        scheduler.validate_preview_identity(
            dict(preview_identity),
            snapshot=snapshot,
            snapshot_file=snapshot_file,
            database_url=os.environ["DATABASE_URL"],
        )

    snapshot_file = scheduler._write_exact_json(tmp_path / "snapshot-reset.json", snapshot)
    preview_identity = scheduler.build_preview_identity_record(
        snapshot,
        preview,
        database_url=os.environ["DATABASE_URL"],
        snapshot_file=snapshot_file,
    )
    with pytest.raises(ValueError, match="database mismatch"):
        scheduler.validate_preview_identity(
            dict(preview_identity),
            snapshot=snapshot,
            snapshot_file=snapshot_file,
            database_url="postgresql://go:secret@other:5432/go_odyssey",
        )
    monkeypatch.setenv("PRODUCTION", "0")
    with pytest.raises(ValueError, match="environment mismatch"):
        scheduler.validate_preview_identity(
            dict(preview_identity),
            snapshot=snapshot,
            snapshot_file=snapshot_file,
            database_url=os.environ["DATABASE_URL"],
        )


def test_operation_dir_rejects_relative_git_worktree_symlink_and_world_writable_paths(tmp_path):
    with pytest.raises(ValueError, match="absolute path"):
        scheduler._validate_operation_dir(Path("relative"), "2026-W28")

    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    (fake_repo / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
    with pytest.raises(ValueError, match="git working-tree"):
        scheduler._validate_operation_dir(fake_repo / "ops", "2026-W28")

    root = tmp_path / "ops"
    root.mkdir()
    if os.name != "nt":
        os.chmod(root, 0o777)
        with pytest.raises(ValueError, match="world-writable directory"):
            scheduler._validate_operation_dir(root, "2026-W28")


@pytest.mark.parametrize("result_name", [
    "disabled_noop",
    "not_due_noop",
    "lock_busy_noop",
    "already_granted_noop",
    "granted",
    "failed_closed",
])
def test_structured_logs_exclude_sensitive_fields(result_name):
    logger = FakeLogger()
    scheduler.log_scheduler_result(
        logger,
        {
            "result": result_name,
            "board_type": "weekly",
            "period_key": "2026-W28",
            "claim_count": 30,
            "component_count": 56,
            "total_coins": 4840,
            "total_items": {"xp_potion": 4},
            "total_badges": {"badge_lb_weekly_1": 1},
            "snapshot_sha256": "a" * 64,
            "preview_sha256": "b" * 64,
            "duration_seconds": 1.23,
            "database_url": "postgresql://secret",
            "email": "secret@example.com",
            "raw_snapshot_data": {"user": "hidden"},
        },
    )
    payload = _result_payload(logger)
    encoded = json.dumps(payload, ensure_ascii=False)
    assert "DATABASE_URL" not in encoded
    assert "password" not in encoded.lower()
    assert "secret@example.com" not in encoded
    assert "raw_snapshot_data" not in encoded
    assert payload["result"] == result_name


class SqliteConnWrapper:
    _named_re = re.compile(r"%\(([^)]+)\)s")

    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row

    def execute(self, sql, parameters=None):
        if (
            "pg_try_advisory_lock" in sql
            or "pg_advisory_unlock" in sql
            or "pg_advisory_xact_lock" in sql
            or "FROM pg_locks" in sql
        ):
            return self._conn.execute("SELECT 1")
        if "ADD COLUMN IF NOT EXISTS notification_acknowledged_at" in sql:
            cols = [row[1] for row in self._conn.execute("PRAGMA table_info(leaderboard_reward_claims)").fetchall()]
            if "notification_acknowledged_at" in cols:
                return self._conn.execute("SELECT 1")
            sql = sql.replace(" IF NOT EXISTS", "")
        sql = sql.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        ordered = parameters
        if isinstance(parameters, dict):
            names = []

            def repl(match):
                names.append(match.group(1))
                return "?"

            sql = self._named_re.sub(repl, sql)
            ordered = tuple(parameters[name] for name in names)
        elif parameters is None:
            ordered = ()
        else:
            sql = sql.replace("%s", "?")
        return self._conn.execute(sql, ordered)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def _add_user(conn, user_id, username, nickname, *, is_admin=0, plan="free"):
    conn.execute(
        "INSERT INTO users(id, username, nickname, is_admin, plan) VALUES(?,?,?,?,?)",
        (user_id, username, nickname, int(bool(is_admin)), plan),
    )
    conn.execute("INSERT INTO user_stats(user_id, rank_level, xp) VALUES(?,?,?)", (user_id, "LV10", 100))
    conn.execute(
        """
        INSERT INTO player_appearance(
            user_id, character_key, combat_armor, combat_weapon, combat_cape,
            combat_offhand, combat_hat, combat_pet, combat_aura
        ) VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (user_id, "apprentice", "", "", "", "", "", "", ""),
    )


def _add_review(conn, user_id, question_id, reviewed_at, grade=3):
    conn.execute(
        "INSERT INTO review_log(user_id, question_id, grade, reviewed_at) VALUES(?,?,?,?)",
        (user_id, question_id, grade, reviewed_at),
    )


def _seed_commit_fixture(conn):
    _add_user(conn, 101, "normal-top1", "Winner One")
    _add_user(conn, 102, "normal-top3", "Winner Two")
    _add_user(conn, 103, "admin-top", "Admin Winner", is_admin=1)
    _add_user(conn, 104, "normal-test-name", "test01")
    _add_user(conn, 105, "registry-only", "Fixture Bot")
    for qid in range(1, 41):
        _add_review(conn, 103, qid, f"2026-07-{6 + ((qid - 1) % 6):02d}T01:00:00")
    for qid in range(1, 36):
        _add_review(conn, 101, qid, f"2026-07-{6 + ((qid - 1) % 6):02d}T02:00:00")
    for qid in range(1, 35):
        _add_review(conn, 105, qid, f"2026-07-{6 + ((qid - 1) % 6):02d}T02:30:00")
    for qid in range(1, 34):
        _add_review(conn, 102, qid, f"2026-07-{6 + ((qid - 1) % 6):02d}T03:00:00")
    for qid in range(1, 32):
        _add_review(conn, 104, qid, f"2026-07-{6 + ((qid - 1) % 6):02d}T04:00:00")
    conn.commit()


def _make_sqlite_reward_conn():
    conn = SqliteConnWrapper()
    conn.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            nickname TEXT,
            is_admin INTEGER NOT NULL DEFAULT 0,
            plan TEXT NOT NULL DEFAULT 'free',
            coin_balance INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE review_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            grade INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE TABLE user_stats (user_id INTEGER PRIMARY KEY, rank_level TEXT, xp INTEGER DEFAULT 0)")
    conn.execute(
        """
        CREATE TABLE player_appearance (
            user_id INTEGER PRIMARY KEY,
            character_key TEXT,
            combat_armor TEXT,
            combat_weapon TEXT,
            combat_cape TEXT,
            combat_offhand TEXT,
            combat_hat TEXT,
            combat_pet TEXT,
            combat_aura TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE shop_inventory (
            user_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            qty INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, item_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE badges_earned (
            user_id INTEGER NOT NULL,
            badge_id TEXT NOT NULL,
            earned_at TEXT NOT NULL,
            seen INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, badge_id)
        )
        """
    )
    lbr.ensure_leaderboard_reward_tables(conn)
    _seed_commit_fixture(conn)
    return conn


def test_scheduler_commit_authorization_requires_flag_and_lock(monkeypatch):
    from community_leaderboard_rewards_exact_period import commit_exact_period
    conn = _make_sqlite_reward_conn()
    snapshot = scheduler.build_exact_period_snapshot(
        conn,
        board_type="weekly",
        period_key="2026-W28",
        period_start="2026-07-06",
        period_end_exclusive="2026-07-13",
        timezone="Asia/Taipei",
        limit=50,
    )
    preview = scheduler.build_exact_period_preview(snapshot)
    auth = create_scheduler_commit_authorization(
        board_type="weekly",
        period_key="2026-W28",
        flag_enabled=True,
    )
    monkeypatch.setenv("COMMUNITY_LEADERBOARD_REWARDS_ENABLED", "false")
    with pytest.raises(ValueError, match="COMMUNITY_LEADERBOARD_REWARDS_ENABLED=true"):
        commit_exact_period(
            conn,
            snapshot=snapshot,
            expected_snapshot_sha256=preview["snapshot_sha256"],
            expected_preview_sha256=preview["preview_sha256"],
            expected_claim_count=preview["summary"]["claims_count"],
            expected_component_count=preview["summary"]["component_count"],
            expected_total_coins=preview["summary"]["total_coins"],
            expected_total_items=preview["summary"]["total_items"],
            expected_total_badges=preview["summary"]["total_badges"],
            scheduler_authorization=auth,
        )

    monkeypatch.setenv("COMMUNITY_LEADERBOARD_REWARDS_ENABLED", "true")
    monkeypatch.setattr(
        "community_leaderboard_rewards_exact_period.scheduler_period_lock_is_held",
        lambda conn, board_type, period_key: False,
    )
    with pytest.raises(ValueError, match="held advisory lock"):
        commit_exact_period(
            conn,
            snapshot=snapshot,
            expected_snapshot_sha256=preview["snapshot_sha256"],
            expected_preview_sha256=preview["preview_sha256"],
            expected_claim_count=preview["summary"]["claims_count"],
            expected_component_count=preview["summary"]["component_count"],
            expected_total_coins=preview["summary"]["total_coins"],
            expected_total_items=preview["summary"]["total_items"],
            expected_total_badges=preview["summary"]["total_badges"],
            scheduler_authorization=auth,
        )
    conn.close()


def _docker_available():
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], capture_output=True, text=True)
    return result.returncode == 0 and bool(result.stdout.strip())


def _wait_for_port(host, port, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f"timed out waiting for {host}:{port}")


def _wait_for_postgres(database_url, timeout=30.0):
    import psycopg2

    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            conn = psycopg2.connect(database_url)
            conn.close()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    raise last_error


@contextlib.contextmanager
def _postgres_container():
    if not _docker_available():
        pytest.skip("docker server unavailable for disposable PostgreSQL scheduler test")
    container_name = f"go-odyssey-reward-test-{uuid.uuid4().hex[:10]}"
    run = subprocess.run(
        [
            "docker", "run", "--rm", "-d",
            "--name", container_name,
            "-e", "POSTGRES_PASSWORD=go",
            "-e", "POSTGRES_USER=go",
            "-e", "POSTGRES_DB=go_odyssey",
            "-p", "127.0.0.1::5432",
            "postgres:16-alpine",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    container_id = run.stdout.strip()
    try:
        port_result = subprocess.run(
            ["docker", "port", container_id, "5432/tcp"],
            capture_output=True,
            text=True,
            check=True,
        )
        host, port_text = port_result.stdout.strip().rsplit(":", 1)
        port = int(port_text)
        _wait_for_port(host, port)
        _wait_for_postgres(f"postgresql://go:go@{host}:{port}/go_odyssey")
        yield {
            "container_id": container_id,
            "host": host,
            "port": port,
            "database_url": f"postgresql://go:go@{host}:{port}/go_odyssey",
        }
    finally:
        subprocess.run(["docker", "rm", "-f", container_id], capture_output=True, text=True)


def _pg_connect(database_url):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    conn.cursor_factory = DictCursor
    return PostgresConnectionWrapper(conn, pooled=False)


def _create_pg_schema(conn):
    conn.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            nickname TEXT,
            is_admin INTEGER NOT NULL DEFAULT 0,
            plan TEXT NOT NULL DEFAULT 'free',
            coin_balance INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE review_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            grade INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE TABLE user_stats (user_id INTEGER PRIMARY KEY, rank_level TEXT, xp INTEGER DEFAULT 0)")
    conn.execute(
        """
        CREATE TABLE player_appearance (
            user_id INTEGER PRIMARY KEY,
            character_key TEXT,
            combat_armor TEXT,
            combat_weapon TEXT,
            combat_cape TEXT,
            combat_offhand TEXT,
            combat_hat TEXT,
            combat_pet TEXT,
            combat_aura TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE shop_inventory (
            user_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            qty INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, item_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE badges_earned (
            user_id INTEGER NOT NULL,
            badge_id TEXT NOT NULL,
            earned_at TEXT NOT NULL,
            seen INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, badge_id)
        )
        """
    )
    lbr.ensure_leaderboard_reward_tables(conn)
    _seed_commit_fixture(conn)
    conn.commit()


class _PgFakeRewardApp:
    SHOP_ITEMS = {
        "xp_potion": {"key": "xp_potion"},
        "small_xp_potion": {"key": "small_xp_potion"},
    }

    @staticmethod
    def _grant_coins(conn, user_id, amount, reason, bypass_daily_cap=False):
        conn.execute("UPDATE users SET coin_balance = coin_balance + %s WHERE id = %s", (amount, user_id))
        return amount

    @staticmethod
    def _grant_shop_purchase(conn, user_id, item, quantity):
        conn.execute(
            """
            INSERT INTO shop_inventory(user_id, item_key, qty) VALUES(%s,%s,%s)
            ON CONFLICT(user_id, item_key) DO UPDATE SET qty = shop_inventory.qty + excluded.qty
            """,
            (user_id, item["key"], quantity),
        )

    @staticmethod
    def grant_community_reward_badge(conn, *, user_id, badge_key, claim_id=None, context=None):
        conn.execute(
            """
            INSERT INTO badges_earned(user_id, badge_id, earned_at, seen)
            VALUES(%s,%s,%s,0)
            ON CONFLICT(user_id, badge_id) DO NOTHING
            """,
            (user_id, badge_key, "2026-07-13T00:00:00"),
        )

    @staticmethod
    def is_community_reward_badge_owned(conn, *, user_id, badge_key):
        return conn.execute(
            "SELECT 1 FROM badges_earned WHERE user_id = %s AND badge_id = %s",
            (user_id, badge_key),
        ).fetchone() is not None


class _PgAppModule:
    def __init__(self, database_url):
        self.database_url = database_url
        self.app = SimpleNamespace(logger=FakeLogger())

    def _env_flag_exact_true(self, name):
        assert name == scheduler.COMMUNITY_LEADERBOARD_REWARDS_ENABLED
        return True

    def get_db(self):
        return _pg_connect(self.database_url)


def test_disposable_postgres_concurrency_lock_and_cleanup(monkeypatch, tmp_path):
    with _postgres_container() as pg:
        admin_conn = _pg_connect(pg["database_url"])
        try:
            _create_pg_schema(admin_conn)
        finally:
            admin_conn.close()

        monkeypatch.setenv("DATABASE_URL", pg["database_url"])
        monkeypatch.setenv("PRODUCTION", "1")
        monkeypatch.setenv("COMMUNITY_LEADERBOARD_REWARDS_ENABLED", "true")
        import community_leaderboard_rewards_real_grant_preview as real_preview

        monkeypatch.setattr(real_preview, "load_app_module", lambda: _PgFakeRewardApp)
        monkeypatch.setattr(real_preview, "verify_real_grant_targets_for_claims", lambda app_module, conn, claims: [])

        real_commit = scheduler.commit_exact_period
        delay_once = {"done": False}
        delay_lock = threading.Lock()

        def delayed_commit(*args, **kwargs):
            with delay_lock:
                if not delay_once["done"]:
                    delay_once["done"] = True
                    time.sleep(0.75)
            return real_commit(*args, **kwargs)

        monkeypatch.setattr(scheduler, "commit_exact_period", delayed_commit)

        app_module = _PgAppModule(pg["database_url"])
        results = []
        threads = []

        def run_cycle():
            results.append(
                scheduler.run_community_leaderboard_weekly_cycle(
                    app_module,
                    now=datetime.datetime(2026, 7, 13, 0, 10, tzinfo=ZoneInfo("Asia/Taipei")),
                    operations_root=tmp_path,
                )
            )

        for _ in range(2):
            thread = threading.Thread(target=run_cycle)
            thread.start()
            threads.append(thread)
        for thread in threads:
            thread.join(timeout=30)
            assert not thread.is_alive()

        result_names = sorted(result["result"] for result in results)
        assert result_names == ["granted", "lock_busy_noop"]

        verify_conn = _pg_connect(pg["database_url"])
        try:
            claims = verify_conn.execute(
                "SELECT COUNT(*) FROM leaderboard_reward_claims WHERE board_type = %s AND period_key = %s",
                ("weekly", "2026-W28"),
            ).fetchone()[0]
            snapshots = verify_conn.execute(
                "SELECT COUNT(*) FROM leaderboard_snapshots WHERE board_type = %s AND period_key = %s",
                ("weekly", "2026-W28"),
            ).fetchone()[0]
            components = verify_conn.execute(
                """
                SELECT COUNT(*) FROM leaderboard_reward_component_log cl
                JOIN leaderboard_reward_claims c ON c.id = cl.claim_id
                WHERE c.board_type = %s AND c.period_key = %s
                """,
                ("weekly", "2026-W28"),
            ).fetchone()[0]
            notifications = verify_conn.execute(
                """
                SELECT COUNT(*) FROM leaderboard_reward_claims
                WHERE board_type = %s AND period_key = %s AND notification_acknowledged_at IS NULL
                """,
                ("weekly", "2026-W28"),
            ).fetchone()[0]
            assert claims > 0
            assert snapshots == 5
            assert components > 0
            assert notifications == claims
            assert scheduler.try_acquire_period_lock(verify_conn, "weekly", "2026-W28") is True
            scheduler.release_period_lock(verify_conn, "weekly", "2026-W28")
        finally:
            verify_conn.close()

        cleanup_conn = _pg_connect(pg["database_url"])
        assert scheduler.try_acquire_period_lock(cleanup_conn, "weekly", "2026-W28") is True
        cleanup_conn.close()

        reacquire_conn = _pg_connect(pg["database_url"])
        try:
            assert scheduler.try_acquire_period_lock(reacquire_conn, "weekly", "2026-W28") is True
            scheduler.release_period_lock(reacquire_conn, "weekly", "2026-W28")
        finally:
            reacquire_conn.close()


def test_disposable_postgres_failed_transaction_releases_lock_and_keeps_zero_writes(monkeypatch, tmp_path):
    with _postgres_container() as pg:
        admin_conn = _pg_connect(pg["database_url"])
        try:
            _create_pg_schema(admin_conn)
        finally:
            admin_conn.close()

        monkeypatch.setenv("DATABASE_URL", pg["database_url"])
        monkeypatch.setenv("COMMUNITY_LEADERBOARD_REWARDS_ENABLED", "true")
        monkeypatch.setattr(
            scheduler,
            "build_exact_period_snapshot",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("planned scheduler failure")),
        )
        app_module = _PgAppModule(pg["database_url"])
        result = scheduler.run_community_leaderboard_weekly_cycle(
            app_module,
            now=datetime.datetime(2026, 7, 13, 0, 10, tzinfo=ZoneInfo("Asia/Taipei")),
            operations_root=tmp_path / "ops-fail",
        )
        assert result["result"] == "failed_closed"

        verify_conn = _pg_connect(pg["database_url"])
        try:
            assert verify_conn.execute("SELECT COUNT(*) FROM leaderboard_snapshots").fetchone()[0] == 0
            assert verify_conn.execute("SELECT COUNT(*) FROM leaderboard_reward_claims").fetchone()[0] == 0
            assert verify_conn.execute("SELECT COUNT(*) FROM leaderboard_reward_component_log").fetchone()[0] == 0
            assert scheduler.try_acquire_period_lock(verify_conn, "weekly", "2026-W28") is True
            scheduler.release_period_lock(verify_conn, "weekly", "2026-W28")
        finally:
            verify_conn.close()
