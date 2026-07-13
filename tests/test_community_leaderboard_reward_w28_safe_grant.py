import datetime
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

import community_leaderboard_rewards as lbr
import community_leaderboard_rewards_manual as manual
from community_leaderboard_rewards_exact_period import (
    build_exact_period_preview,
    build_exact_period_snapshot,
    commit_exact_period,
    detect_existing_operation_state,
)


class SqliteConnWrapper:
    _named_re = re.compile(r"%\(([^)]+)\)s")

    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row

    def execute(self, sql, parameters=None):
        if "pg_advisory_xact_lock" in sql:
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


def make_conn():
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
    conn.execute(
        "CREATE TABLE user_stats (user_id INTEGER PRIMARY KEY, rank_level TEXT, xp INTEGER DEFAULT 0)"
    )
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
    return conn


def add_user(conn, user_id, username, nickname, *, is_admin=0, plan="free"):
    conn.execute(
        "INSERT INTO users(id, username, nickname, is_admin, plan) VALUES(?,?,?,?,?)",
        (user_id, username, nickname, is_admin, plan),
    )
    conn.execute(
        "INSERT INTO user_stats(user_id, rank_level, xp) VALUES(?,?,?)",
        (user_id, "LV10", 100),
    )
    conn.execute(
        """
        INSERT INTO player_appearance(
            user_id, character_key, combat_armor, combat_weapon, combat_cape,
            combat_offhand, combat_hat, combat_pet, combat_aura
        ) VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (user_id, "apprentice", "", "", "", "", "", "", ""),
    )


def add_review(conn, user_id, question_id, reviewed_at, grade=3):
    conn.execute(
        "INSERT INTO review_log(user_id, question_id, grade, reviewed_at) VALUES(?,?,?,?)",
        (user_id, question_id, grade, reviewed_at),
    )


def seed_ranking_fixture(conn):
    add_user(conn, 10, "admin1", "Admin", is_admin=1)
    add_user(conn, 20, "qa-smoke", "QA User")
    add_user(conn, 30, "player-a", "test01")
    add_user(conn, 40, "player-b", "..................?")
    add_user(conn, 65, "player-c", "Tie Low")
    add_user(conn, 70, "player-d", "Tie High")

    for qid in (1, 2, 3):
        add_review(conn, 10, qid, f"2026-07-06T0{qid}:00:00")
        add_review(conn, 20, qid, f"2026-07-06T1{qid}:00:00")
    add_review(conn, 30, 1, "2026-07-06T01:00:00")
    add_review(conn, 30, 2, "2026-07-06T03:00:00")
    add_review(conn, 40, 1, "2026-07-06T00:30:00")
    add_review(conn, 40, 2, "2026-07-06T02:00:00")
    add_review(conn, 40, 2, "2026-07-10T09:00:00")  # repeated solve must not move tie-break
    add_review(conn, 40, 99, "2026-07-13T00:00:00")  # must be excluded by exact end bound
    add_review(conn, 65, 1, "2026-07-06T05:00:00")
    add_review(conn, 70, 1, "2026-07-06T05:00:00")
    conn.commit()


def seed_commit_fixture(conn):
    add_user(conn, 101, "normal-top1", "Winner One")
    add_user(conn, 102, "normal-top3", "Winner Two")
    add_user(conn, 103, "admin-top", "Admin Winner", is_admin=1)
    add_user(conn, 104, "normal-test-name", "test01")
    add_user(conn, 105, "registry-only", "Fixture Bot")

    for qid in range(1, 41):
        add_review(conn, 103, qid, f"2026-07-{6 + ((qid - 1) % 6):02d}T01:00:00")
    for qid in range(1, 36):
        add_review(conn, 101, qid, f"2026-07-{6 + ((qid - 1) % 6):02d}T02:00:00")
    for qid in range(1, 35):
        add_review(conn, 105, qid, f"2026-07-{6 + ((qid - 1) % 6):02d}T02:30:00")
    for qid in range(1, 34):
        add_review(conn, 102, qid, f"2026-07-{6 + ((qid - 1) % 6):02d}T03:00:00")
    for qid in range(1, 32):
        add_review(conn, 104, qid, f"2026-07-{6 + ((qid - 1) % 6):02d}T04:00:00")
    conn.commit()


class FakeAppModule:
    SHOP_ITEMS = {
        "xp_potion": {"key": "xp_potion"},
        "small_xp_potion": {"key": "small_xp_potion"},
    }

    @staticmethod
    def _grant_coins(conn, user_id, amount, reason, bypass_daily_cap=False):
        conn.execute("UPDATE users SET coin_balance = coin_balance + ? WHERE id = ?", (amount, user_id))
        return amount

    @staticmethod
    def _grant_shop_purchase(conn, user_id, item, quantity):
        conn.execute(
            """
            INSERT INTO shop_inventory(user_id, item_key, qty) VALUES(?,?,?)
            ON CONFLICT(user_id, item_key) DO UPDATE SET qty = shop_inventory.qty + excluded.qty
            """,
            (user_id, item["key"], quantity),
        )

    @staticmethod
    def grant_community_reward_badge(conn, *, user_id, badge_key, claim_id=None, context=None):
        conn.execute(
            "INSERT OR IGNORE INTO badges_earned(user_id, badge_id, earned_at, seen) VALUES(?,?,?,0)",
            (user_id, badge_key, "2026-07-13T00:00:00"),
        )

    @staticmethod
    def is_community_reward_badge_owned(conn, *, user_id, badge_key):
        return conn.execute(
            "SELECT 1 FROM badges_earned WHERE user_id = ? AND badge_id = ?",
            (user_id, badge_key),
        ).fetchone() is not None


def build_commit_snapshot(conn, monkeypatch):
    monkeypatch.setattr(
        lbr,
        "CANONICAL_TEST_ACCOUNT_REGISTRY",
        ({
            "user_id": 105,
            "evidence_class": lbr.TEST_ACCOUNT_EVIDENCE_FIXTURE,
            "note": "reward safety fixture account",
        },),
    )
    snapshot = build_exact_period_snapshot(
        conn,
        board_type="weekly",
        period_key="2026-W28",
        period_start="2026-07-06",
        period_end_exclusive="2026-07-13",
    )
    preview = build_exact_period_preview(snapshot)
    return snapshot, preview


def test_admin_and_registry_exclusions_apply_before_ranking_and_names_are_not_heuristics(monkeypatch):
    conn = make_conn()
    seed_ranking_fixture(conn)
    monkeypatch.setattr(
        lbr,
        "CANONICAL_TEST_ACCOUNT_REGISTRY",
        ({
            "user_id": 20,
            "evidence_class": lbr.TEST_ACCOUNT_EVIDENCE_FIXTURE,
            "note": "fixture user",
        },),
    )
    snapshot = build_exact_period_snapshot(
        conn,
        board_type="weekly",
        period_key="2026-W28",
        period_start="2026-07-06",
        period_end_exclusive="2026-07-13",
    )
    excluded_ids = {row["user_id"] for row in snapshot["excluded_accounts"]}
    assert excluded_ids == {10, 20}
    assert snapshot["participant_counts"]["excluded_admin_count"] == 1
    assert snapshot["participant_counts"]["excluded_canonical_test_account_count"] == 1
    assert snapshot["top_rows"][0]["user_id"] == 40
    assert snapshot["top_rows"][1]["user_id"] == 30
    assert 30 not in excluded_ids
    assert snapshot["top_rows"][1]["display_name"] == "test01"
    conn.close()


def test_tiebreak_uses_final_counted_timestamp_then_user_id_and_repeated_solves_do_not_inflate(monkeypatch):
    conn = make_conn()
    seed_ranking_fixture(conn)
    monkeypatch.setattr(lbr, "CANONICAL_TEST_ACCOUNT_REGISTRY", ())
    snapshot = build_exact_period_snapshot(
        conn,
        board_type="weekly",
        period_key="2026-W28",
        period_start="2026-07-06",
        period_end_exclusive="2026-07-13",
    )
    top = {row["user_id"]: row for row in snapshot["top_rows"]}
    assert top[40]["rank"] < top[30]["rank"]
    assert top[65]["rank"] < top[70]["rank"]
    assert top[40]["score"] == 2
    assert top[40]["final_counted_at"] == "2026-07-06T02:00:00"
    assert snapshot["participant_counts"]["original_participant_count"] == 6
    conn.close()


def test_exact_period_preview_is_deterministic_and_monday_activity_is_excluded(monkeypatch):
    conn = make_conn()
    seed_ranking_fixture(conn)
    monkeypatch.setattr(lbr, "CANONICAL_TEST_ACCOUNT_REGISTRY", ())
    snapshot1 = build_exact_period_snapshot(
        conn,
        board_type="weekly",
        period_key="2026-W28",
        period_start="2026-07-06",
        period_end_exclusive="2026-07-13",
    )
    snapshot2 = build_exact_period_snapshot(
        conn,
        board_type="weekly",
        period_key="2026-W28",
        period_start="2026-07-06",
        period_end_exclusive="2026-07-13",
    )
    preview1 = build_exact_period_preview(snapshot1)
    preview2 = build_exact_period_preview(snapshot2)
    assert lbr.sha256_hex_from_value(snapshot1) == lbr.sha256_hex_from_value(snapshot2)
    assert preview1["preview_sha256"] == preview2["preview_sha256"]
    # user_id 40 would have score 3 if 2026-07-13 activity were counted
    assert next(row for row in snapshot1["top_rows"] if row["user_id"] == 40)["score"] == 2
    conn.close()


def test_commit_rejects_preview_hash_snapshot_hash_open_period_and_changed_snapshot(monkeypatch):
    conn = make_conn()
    seed_commit_fixture(conn)
    snapshot, preview = build_commit_snapshot(conn, monkeypatch)
    with pytest.raises(ValueError, match="snapshot SHA-256 mismatch"):
        commit_exact_period(
            conn,
            snapshot=snapshot,
            expected_snapshot_sha256="deadbeef",
            expected_preview_sha256=preview["preview_sha256"],
            expected_claim_count=preview["summary"]["claims_count"],
            expected_component_count=preview["summary"]["component_count"],
            expected_total_coins=preview["summary"]["total_coins"],
            expected_total_items=preview["summary"]["total_items"],
            expected_total_badges=preview["summary"]["total_badges"],
            owner_gate=lbr.EXACT_PERIOD_OWNER_GATE,
        )
    with pytest.raises(ValueError, match="preview SHA-256 mismatch"):
        commit_exact_period(
            conn,
            snapshot=snapshot,
            expected_snapshot_sha256=lbr.sha256_hex_from_value(snapshot),
            expected_preview_sha256="deadbeef",
            expected_claim_count=preview["summary"]["claims_count"],
            expected_component_count=preview["summary"]["component_count"],
            expected_total_coins=preview["summary"]["total_coins"],
            expected_total_items=preview["summary"]["total_items"],
            expected_total_badges=preview["summary"]["total_badges"],
            owner_gate=lbr.EXACT_PERIOD_OWNER_GATE,
        )
    with pytest.raises(ValueError, match="open leaderboard period"):
        commit_exact_period(
            conn,
            snapshot=snapshot,
            expected_snapshot_sha256=lbr.sha256_hex_from_value(snapshot),
            expected_preview_sha256=preview["preview_sha256"],
            expected_claim_count=preview["summary"]["claims_count"],
            expected_component_count=preview["summary"]["component_count"],
            expected_total_coins=preview["summary"]["total_coins"],
            expected_total_items=preview["summary"]["total_items"],
            expected_total_badges=preview["summary"]["total_badges"],
            owner_gate=lbr.EXACT_PERIOD_OWNER_GATE,
            now=datetime.datetime(2026, 7, 12, 12, 0, tzinfo=datetime.timezone.utc),
        )
    add_review(conn, 102, 999, "2026-07-12T15:00:00")
    conn.commit()
    with pytest.raises(ValueError, match="eligible ranking changed since preview"):
        commit_exact_period(
            conn,
            snapshot=snapshot,
            expected_snapshot_sha256=lbr.sha256_hex_from_value(snapshot),
            expected_preview_sha256=preview["preview_sha256"],
            expected_claim_count=preview["summary"]["claims_count"],
            expected_component_count=preview["summary"]["component_count"],
            expected_total_coins=preview["summary"]["total_coins"],
            expected_total_items=preview["summary"]["total_items"],
            expected_total_badges=preview["summary"]["total_badges"],
            owner_gate=lbr.EXACT_PERIOD_OWNER_GATE,
        )
    conn.close()


def test_commit_rejects_total_mismatch_and_partial_existing_claims(monkeypatch):
    conn = make_conn()
    seed_commit_fixture(conn)
    snapshot, preview = build_commit_snapshot(conn, monkeypatch)
    with pytest.raises(ValueError, match="expected reward totals mismatch"):
        commit_exact_period(
            conn,
            snapshot=snapshot,
            expected_snapshot_sha256=lbr.sha256_hex_from_value(snapshot),
            expected_preview_sha256=preview["preview_sha256"],
            expected_claim_count=preview["summary"]["claims_count"],
            expected_component_count=preview["summary"]["component_count"],
            expected_total_coins=preview["summary"]["total_coins"] + 1,
            expected_total_items=preview["summary"]["total_items"],
            expected_total_badges=preview["summary"]["total_badges"],
            owner_gate=lbr.EXACT_PERIOD_OWNER_GATE,
        )
    lbr.finalize_leaderboard_reward_period(
        conn,
        snapshot["board_type"],
        snapshot["period_key"],
        snapshot["period_start"],
        (datetime.date.fromisoformat(snapshot["period_end_exclusive"]) - datetime.timedelta(days=1)).isoformat(),
        snapshot["entries"],
        dry_run=False,
    )
    conn.commit()
    state = detect_existing_operation_state(conn, snapshot, preview)
    assert state["state"] == "conflict"
    with pytest.raises(ValueError, match="existing claim status is not fully settled"):
        commit_exact_period(
            conn,
            snapshot=snapshot,
            expected_snapshot_sha256=lbr.sha256_hex_from_value(snapshot),
            expected_preview_sha256=preview["preview_sha256"],
            expected_claim_count=preview["summary"]["claims_count"],
            expected_component_count=preview["summary"]["component_count"],
            expected_total_coins=preview["summary"]["total_coins"],
            expected_total_items=preview["summary"]["total_items"],
            expected_total_badges=preview["summary"]["total_badges"],
            owner_gate=lbr.EXACT_PERIOD_OWNER_GATE,
        )
    conn.close()


def test_commit_succeeds_once_then_returns_controlled_noop_without_duplicate_rewards(monkeypatch):
    conn = make_conn()
    seed_commit_fixture(conn)
    snapshot, preview = build_commit_snapshot(conn, monkeypatch)
    import community_leaderboard_rewards_real_grant_preview as real_preview

    monkeypatch.setattr(real_preview, "load_app_module", lambda: FakeAppModule)
    monkeypatch.setattr(real_preview, "verify_real_grant_targets_for_claims", lambda app_module, conn, claims: [])

    result = commit_exact_period(
        conn,
        snapshot=snapshot,
        expected_snapshot_sha256=lbr.sha256_hex_from_value(snapshot),
        expected_preview_sha256=preview["preview_sha256"],
        expected_claim_count=preview["summary"]["claims_count"],
        expected_component_count=preview["summary"]["component_count"],
        expected_total_coins=preview["summary"]["total_coins"],
        expected_total_items=preview["summary"]["total_items"],
        expected_total_badges=preview["summary"]["total_badges"],
        owner_gate=lbr.EXACT_PERIOD_OWNER_GATE,
    )
    conn.commit()
    assert result["result"] == "committed"
    claims = conn.execute(
        "SELECT status FROM leaderboard_reward_claims WHERE board_type=? AND period_key=? ORDER BY rank",
        ("weekly", "2026-W28"),
    ).fetchall()
    assert [row[0] for row in claims] == ["granted", "granted", "granted"]
    notifications = lbr.fetch_unacknowledged_granted_reward_claims(conn, 101)
    assert len(notifications) == 1
    coins_after_first = conn.execute(
        "SELECT coin_balance FROM users WHERE id = ?", (101,)
    ).fetchone()[0]
    noop = commit_exact_period(
        conn,
        snapshot=snapshot,
        expected_snapshot_sha256=lbr.sha256_hex_from_value(snapshot),
        expected_preview_sha256=preview["preview_sha256"],
        expected_claim_count=preview["summary"]["claims_count"],
        expected_component_count=preview["summary"]["component_count"],
        expected_total_coins=preview["summary"]["total_coins"],
        expected_total_items=preview["summary"]["total_items"],
        expected_total_badges=preview["summary"]["total_badges"],
        owner_gate=lbr.EXACT_PERIOD_OWNER_GATE,
    )
    assert noop["result"] == "already_granted_noop"
    assert conn.execute("SELECT coin_balance FROM users WHERE id = ?", (101,)).fetchone()[0] == coins_after_first
    assert len(lbr.fetch_unacknowledged_granted_reward_claims(conn, 101)) == 1
    conn.close()


def test_transaction_failure_rolls_back_partial_writes(monkeypatch):
    conn = make_conn()
    seed_commit_fixture(conn)
    snapshot, preview = build_commit_snapshot(conn, monkeypatch)
    import community_leaderboard_rewards_real_grant_preview as real_preview
    import community_leaderboard_rewards_real_grant_commit as real_commit

    monkeypatch.setattr(real_preview, "load_app_module", lambda: FakeAppModule)
    monkeypatch.setattr(real_preview, "verify_real_grant_targets_for_claims", lambda app_module, conn, claims: [])

    def broken_execute(conn_, app_module, claims, *, board_type, period_key):
        first = claims[0]
        conn_.execute("UPDATE users SET coin_balance = coin_balance + 999 WHERE id = ?", (first["user_id"],))
        raise RuntimeError("boom")

    monkeypatch.setattr(real_commit, "execute_exact_period_grant_commit", broken_execute)

    with pytest.raises(RuntimeError, match="boom"):
        commit_exact_period(
            conn,
            snapshot=snapshot,
            expected_snapshot_sha256=lbr.sha256_hex_from_value(snapshot),
            expected_preview_sha256=preview["preview_sha256"],
            expected_claim_count=preview["summary"]["claims_count"],
            expected_component_count=preview["summary"]["component_count"],
            expected_total_coins=preview["summary"]["total_coins"],
            expected_total_items=preview["summary"]["total_items"],
            expected_total_badges=preview["summary"]["total_badges"],
            owner_gate=lbr.EXACT_PERIOD_OWNER_GATE,
        )
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM leaderboard_reward_claims").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM leaderboard_snapshots").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM leaderboard_reward_component_log").fetchone()[0] == 0
    assert conn.execute("SELECT coin_balance FROM users WHERE id = 101").fetchone()[0] == 0
    conn.close()


def test_manual_grant_commit_remains_disabled():
    result = manual.main([
        "grant-commit",
        "--board", "weekly",
        "--period-key", "2026-W28",
        "--confirm-grant",
    ])
    assert result == 3
