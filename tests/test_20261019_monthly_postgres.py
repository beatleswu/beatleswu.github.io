"""Offline rehearsal against a fresh, loopback-only native PostgreSQL cluster.

Run: python -m pytest -q tests/test_20261019_monthly_postgres.py
Requires installed initdb/pg_ctl (PATH or MONTHLY_TEST_PG_BIN), psycopg2 and
the application's dependencies. Never consumes DATABASE_URL or existing data.
No Docker image pulls, production connection, scheduler thread or HTTP server.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
from zoneinfo import ZoneInfo

import pytest

import community_leaderboard_rewards as rewards
import community_leaderboard_rewards_scheduler as scheduler
from tools.community_leaderboard_rewards_exact_period import build_exact_period_snapshot


TZ = ZoneInfo("Asia/Taipei")
DUE = dt.datetime(2026, 11, 1, 0, 10, tzinfo=TZ)


@pytest.fixture(scope="module")
def local_postgres(tmp_path_factory):
    """Own the cluster lifecycle; absence of PostgreSQL is an error, not PASS."""
    bin_dir = os.environ.get("MONTHLY_TEST_PG_BIN")
    initdb = str(Path(bin_dir) / "initdb") if bin_dir else shutil.which("initdb")
    pg_ctl = str(Path(bin_dir) / "pg_ctl") if bin_dir else shutil.which("pg_ctl")
    assert initdb and pg_ctl, "Install native PostgreSQL or set MONTHLY_TEST_PG_BIN"
    root = tmp_path_factory.mktemp("monthly-native-postgres")
    data = root / "data"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    def run(*args):
        # On Windows a postgres child can retain pg_ctl's inherited pipe,
        # leaving subprocess.communicate waiting for EOF after pg_ctl exits.
        log = root / "control.log"
        with log.open("a", encoding="utf-8") as output:
            result = subprocess.run(args, stdin=subprocess.DEVNULL,
                stdout=output, stderr=subprocess.STDOUT, timeout=60)
        assert result.returncode == 0, log.read_text(encoding="utf-8", errors="replace")

    run(initdb, "-D", str(data), "-U", "monthly_test", "-A", "trust", "--no-locale", "-E", "UTF8")
    started = False
    try:
        run(pg_ctl, "-D", str(data), "-l", str(root / "server.log"),
            "-o", f"-h 127.0.0.1 -p {port} -F", "-w", "start")
        started = True
        yield f"postgresql://monthly_test@127.0.0.1:{port}/postgres"
    finally:
        if started:
            run(pg_ctl, "-D", str(data), "-m", "fast", "-w", "stop")


def _open(url):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper
    raw = psycopg2.connect(url, connect_timeout=5, cursor_factory=DictCursor)
    return PostgresConnectionWrapper(raw)


@pytest.fixture
def runtime(local_postgres, monkeypatch):
    # Patch before importing app and before its canonical schema bootstrap.
    monkeypatch.setenv("DATABASE_URL", local_postgres)
    monkeypatch.setenv("PRODUCTION", "false")
    monkeypatch.setenv("COMMUNITY_LEADERBOARD_REWARDS_ENABLED", "true")
    monkeypatch.setenv("SECRET_KEY", "monthly-disposable-test-only")
    import app
    import db
    monkeypatch.setattr(db, "DATABASE_URL", local_postgres)
    monkeypatch.setattr(app, "get_db", lambda: _open(local_postgres))
    monkeypatch.setitem(app.app.config, "TESTING", True)
    with _open(local_postgres) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        from migrations.sgf_admin_workbench_v1 import upgrade
        upgrade(conn)
    app.init_db()
    yield app


def _seed(app, users=52):
    """51 qualified, one below threshold; higher ID wins the first tie."""
    with app.get_db() as conn:
        for uid in range(1, users + 1):
            conn.execute("""INSERT INTO users
                (id, username, nickname, password_hash, is_admin, plan, created_at)
                VALUES(?,?,?,?,?,?,?)""",
                (uid, f"monthly-test-{uid}", f"Test{uid:02}", "synthetic-unused",
                 int(uid == 2), "free", "2026-10-01T00:00:00"))
            conn.execute("INSERT INTO user_stats(user_id, coins, rank_level, xp) VALUES(?,0,'LV1',0)", (uid,))
            conn.execute("INSERT INTO player_appearance(user_id, character_key) VALUES(?,'apprentice')", (uid,))
            count = 149 if uid == 52 else 150
            # uid 2 achieves the tied score before uid 1; later duplicate
            # correct answers must not move the first-achievement timestamp.
            second = 0 if uid == 2 else uid
            stamp = f"2026-10-31T15:00:{second:02}"
            conn.executemany("""INSERT INTO review_log
                (user_id,question_id,grade,reviewed_at,source_context)
                VALUES(?,?,?,?,?)""",
                [(uid, qid, 3, stamp, "practice:v1:monthly-fixture")
                 for qid in range(1, count + 1)])
        conn.executemany("""INSERT INTO review_log
            (user_id,question_id,grade,reviewed_at,source_context) VALUES(?,?,?,?,?)""", [
                (2, 1, 3, "2026-10-31T15:59:59", "practice:v1:monthly-fixture"),
                (52, 1, 3, "2026-10-31T15:59:59", "practice:v1:monthly-fixture"),
                (52, 150, 2, "2026-10-31T15:59:59", "practice:v1:monthly-fixture"),
                (52, 151, 3, "2026-10-31T15:59:59", "untrusted-client"),
                (52, 152, 3, "2026-09-30T15:59:59", "practice:v1:monthly-fixture"),
                (52, 153, 3, "2026-10-31T16:00:00", "practice:v1:monthly-fixture"),
            ])


def _state(app):
    tables = ("user_stats", "shop_inventory", "badges_earned", "player_wardrobe",
              "leaderboard_reward_claims", "leaderboard_reward_component_log",
              "leaderboard_snapshots", "currency_log")
    with app.get_db() as conn:
        return {table: sorted([dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()],
                              key=lambda row: json.dumps(row, sort_keys=True, default=str))
                for table in tables}


def _client(app, uid):
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = uid
    return client


def test_monthly_full_settlement_notifications_fragments_rerun_and_weekly(runtime, tmp_path):
    app = runtime
    _seed(app)
    with app.get_db() as conn:
        snapshot = build_exact_period_snapshot(conn, board_type="monthly", period_key="2026-10",
            period_start="2026-10-01", period_end_exclusive="2026-11-01", limit=100)
    rows = snapshot["top_rows"]
    assert [(row["user_id"], row["rank"], row["score"]) for row in rows[:2]] == [(2, 1, 150), (1, 2, 150)]
    assert rows[-1]["user_id"] == 52 and rows[-1]["score"] == 149
    assert rows[-2]["rank"] == 51 and rows[-2]["score"] == 150

    result = scheduler.run_community_leaderboard_monthly_cycle(app, now=DUE, operations_root=tmp_path / "operations")
    assert result["result"] == "granted", result
    assert result["claim_count"] == 50
    operation = tmp_path / "operations" / "2026-10"
    frozen_snapshot = json.loads((operation / "snapshot.json").read_text("utf-8"))
    assert rewards.sha256_hex_from_value(frozen_snapshot) == result["snapshot_sha256"]
    assert hashlib.sha256((operation / "snapshot.json").read_bytes()).hexdigest() == result["snapshot_sha256"]
    assert json.loads((operation / "grant-result.json").read_text("utf-8"))["result"] == "committed"
    state = _state(app)
    assert len(state["leaderboard_reward_claims"]) == 50
    assert {r["status"] for r in state["leaderboard_reward_claims"]} == {"granted"}
    balances = {r["user_id"]: r["coins"] for r in state["user_stats"]}
    assert balances[2] == 1500 and balances[1] == 1000
    assert balances[4] == 600 and balances[11] == 300 and balances[26] == 150
    assert balances[51] == balances[52] == 0
    assert sum(balances.values()) == 15950
    assert len(state["leaderboard_reward_component_log"]) == 86
    assert any(r["user_id"] == 2 and r["badge_id"] == "badge_lb_monthly_1" for r in state["badges_earned"])
    assert any(r["user_id"] == 2 and r["item_id"] == "title_monthly_master" for r in state["player_wardrobe"])
    champion = _client(app, 2)
    notifications = champion.get("/api/community/leaderboard/reward-notifications").get_json()["notifications"]
    assert len(notifications) == 1
    notification = notifications[0]
    assert notification["board"] == "monthly" and notification["period_key"] == "2026-10"
    assert notification["rewards"] == [
        {"type": "coins", "amount": 1500},
        {"type": "item", "key": "rare_appearance_fragment", "quantity": 2},
        {"type": "badge", "key": "badge_lb_monthly_1"},
        {"type": "title", "key": "title_monthly_master"},
    ]
    assert _state(app) == state  # reading the notification never grants
    rerun = scheduler.run_community_leaderboard_monthly_cycle(app, now=DUE, operations_root=tmp_path / "operations")
    assert rerun["result"] == "already_granted_noop", rerun
    assert _state(app) == state
    claim = next(r for r in state["leaderboard_reward_claims"] if r["user_id"] == 2)
    ack_url = f"/api/community/leaderboard/reward-notifications/{claim['id']}/ack"
    assert _client(app, 1).post(ack_url).status_code == 404
    assert champion.post(ack_url).status_code == 200
    assert champion.post(ack_url).status_code == 200
    assert champion.get("/api/community/leaderboard/reward-notifications").get_json()["notifications"] == []

    # Exercise both granted fragment types through the actual authenticated API.
    for uid, key, qty in [(2, "rare_appearance_fragment", 2), (4, "appearance_fragment", 2)]:
        client = _client(app, uid)
        for remaining in reversed(range(qty)):
            response = client.post("/api/shop/use", json={"item_key": key})
            assert response.status_code == 200, response.get_json()
            payload = response.get_json()
            assert payload["reward"] == "appearance"
            with app.get_db() as conn:
                assert conn.execute("SELECT qty FROM shop_inventory WHERE user_id=? AND item_key=?", (uid, key)).fetchone()[0] == remaining
                assert conn.execute("SELECT source FROM player_wardrobe WHERE user_id=? AND item_id=?", (uid, payload["reward_item"])).fetchone()[0] == "fragment"
        assert client.post("/api/shop/use", json={"item_key": key}).status_code == 400
    consumed_state = _state(app)
    assert scheduler.run_community_leaderboard_monthly_cycle(app, now=DUE, operations_root=tmp_path / "operations")["result"] == "already_granted_noop"
    assert _state(app) == consumed_state

    weekly_now = dt.datetime(2026, 11, 2, 0, 10, tzinfo=TZ)
    weekly = scheduler.run_community_leaderboard_weekly_cycle(app, now=weekly_now, operations_root=tmp_path / "operations")
    assert weekly["result"] == "granted", weekly
    assert weekly["claim_count"] == 50 and weekly["total_coins"] == 6040
    with app.get_db() as conn:
        monthly_claims = [dict(r) for r in conn.execute("SELECT * FROM leaderboard_reward_claims WHERE board_type='monthly'").fetchall()]
        assert sorted(monthly_claims, key=lambda r: r["id"]) == sorted(consumed_state["leaderboard_reward_claims"], key=lambda r: r["id"])
    weekly_state = _state(app)
    assert scheduler.run_community_leaderboard_weekly_cycle(app, now=weekly_now, operations_root=tmp_path / "operations")["result"] == "already_granted_noop"
    assert _state(app) == weekly_state


@pytest.mark.parametrize("now", [dt.datetime(2026, 10, 1, 0, 10, tzinfo=TZ), DUE - dt.timedelta(seconds=1)])
def test_monthly_no_retroactive_or_early_settlement(runtime, tmp_path, now):
    before = _state(runtime)
    result = scheduler.run_community_leaderboard_monthly_cycle(runtime, now=now, operations_root=tmp_path / "operations")
    assert result["result"] == "not_due_noop"
    assert _state(runtime) == before
    assert not (tmp_path / "operations").exists()


def test_monthly_component_failure_rolls_back_entire_period(runtime, tmp_path, monkeypatch):
    _seed(runtime, users=2)
    before = _state(runtime)
    original = runtime.grant_community_reward_title
    def fail_title(*args, **kwargs):
        raise RuntimeError("synthetic title storage failure")
    monkeypatch.setattr(runtime, "grant_community_reward_title", fail_title)
    result = scheduler.run_community_leaderboard_monthly_cycle(runtime, now=DUE, operations_root=tmp_path / "operations")
    assert result["result"] == "failed_closed", result
    assert _state(runtime) == before
    monkeypatch.setattr(runtime, "grant_community_reward_title", original)
    retry = scheduler.run_community_leaderboard_monthly_cycle(runtime, now=DUE, operations_root=tmp_path / "operations")
    assert retry["result"] == "granted", retry
    assert retry["claim_count"] == 2 and retry["total_coins"] == 2500
    settled = _state(runtime)
    assert scheduler.run_community_leaderboard_monthly_cycle(runtime, now=DUE, operations_root=tmp_path / "operations")["result"] == "already_granted_noop"
    assert _state(runtime) == settled


def test_monthly_149_at_reward_rank_is_not_paid_and_taipei_boundary_counts(runtime, tmp_path):
    _seed(runtime, users=2)
    with runtime.get_db() as conn:
        conn.execute("DELETE FROM review_log WHERE user_id=1 AND question_id=150")
        # Start is inclusive in Taipei (UTC September 30 16:00), end exclusive.
        conn.execute("UPDATE review_log SET reviewed_at='2026-09-30T16:00:00' WHERE user_id=2 AND question_id=150")
        conn.executemany("""INSERT INTO review_log
            (user_id,question_id,grade,reviewed_at,source_context) VALUES(?,?,?,?,?)""", [
                (1, 150, 3, "2026-09-30T15:59:59", "practice:v1:monthly-fixture"),
                (1, 151, 3, "2026-10-31T16:00:00", "practice:v1:monthly-fixture"),
            ])
    result = scheduler.run_community_leaderboard_monthly_cycle(runtime, now=DUE, operations_root=tmp_path / "operations")
    assert result["result"] == "granted", result
    assert result["claim_count"] == 1 and result["total_coins"] == 1500
    state = _state(runtime)
    assert [(r["user_id"], r["score"]) for r in state["leaderboard_reward_claims"]] == [(2, 150)]
    assert {r["user_id"]: r["coins"] for r in state["user_stats"]} == {1: 0, 2: 1500}


def test_monthly_reward_survives_new_login_session_without_double_grant(runtime, tmp_path):
    """Isolated PostgreSQL session-rehydration rehearsal, NOT production Test02 E2E.

    The seeded nickname Test02 participates as a normal prize-eligible player.
    New Flask test clients represent independent login sessions, without
    reading or changing any existing credential or live player database.
    """
    app = runtime
    _seed(app)
    first_grant = scheduler.run_community_leaderboard_monthly_cycle(
        app, now=DUE, operations_root=tmp_path / "relogin-monthly")
    assert first_grant["result"] == "granted"
    assert first_grant["claim_count"] == 50

    with app.get_db() as conn:
        player = conn.execute(
            "SELECT username, nickname FROM users WHERE id=?", (2,)).fetchone()
        assert player["nickname"] == "Test02"
        assert player["username"] == "monthly-test-2"

    first_session = _client(app, 2)
    first_response = first_session.get("/api/community/leaderboard/reward-notifications")
    assert first_response.status_code == 200
    first_notifications = first_response.get_json()["notifications"]
    assert len(first_notifications) == 1
    assert first_notifications[0]["board"] == "monthly"
    assert first_notifications[0]["period_key"] == "2026-10"
    assert len(first_notifications[0]["rewards"]) == 4
    before = _state(app)

    # Drop the client entirely: a NEW Flask session must rehydrate the same
    # server-owned prize, without triggering a second grant.
    del first_session
    second_session = _client(app, 2)
    again = second_session.get("/api/community/leaderboard/reward-notifications")
    assert again.status_code == 200
    assert again.get_json()["notifications"] == first_notifications
    assert _state(app) == before

    rerun = scheduler.run_community_leaderboard_monthly_cycle(
        app, now=DUE, operations_root=tmp_path / "relogin-monthly")
    assert rerun["result"] == "already_granted_noop"
    assert _state(app) == before

    claim = next(row for row in before["leaderboard_reward_claims"]
                 if row["user_id"] == 2)
    acknowledgement = second_session.post(
        f"/api/community/leaderboard/reward-notifications/{claim['id']}/ack")
    assert acknowledgement.status_code == 200
    after_ack = _state(app)

    third_session = _client(app, 2)
    assert third_session.get("/api/community/leaderboard/reward-notifications"
                             ).get_json()["notifications"] == []
    assert _state(app) == after_ack
    with app.get_db() as conn:
        coins = conn.execute("SELECT coins FROM user_stats WHERE user_id=?", (2,)).fetchone()
        assert coins["coins"] == 1500
        fragments = conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=? AND item_key=?",
            (2, "rare_appearance_fragment")).fetchone()
        assert fragments is not None and fragments["qty"] == 2
