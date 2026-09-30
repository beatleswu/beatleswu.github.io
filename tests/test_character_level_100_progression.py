"""Owner-approved main-player progression extension from Lv50 to Lv100."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "character-level-100-progression-test-secret")
import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
BASELINE_XP = [
    0, 120, 280, 480, 720, 1000, 1320, 1680, 2080, 2520,
    3100, 3800, 4600, 5500, 6500, 7600, 8800, 10100, 11500, 13000,
    14600, 16300, 18100, 20000, 22000, 24100, 26300, 28600, 31000, 33500,
    36500, 40000, 44000, 48500, 53500, 59000, 65000, 71500, 78500, 86000,
    94000, 102500, 111500, 121000, 131000, 141500, 152500, 164000, 176000,
    188500,
]
BASELINE_HP = [
    60, 66, 72, 78, 84, 90, 96, 103, 110, 118,
    126, 135, 144, 154, 164, 175, 186, 198, 210, 224,
    238, 253, 268, 284, 300, 317, 335, 354, 374, 395,
    418, 443, 470, 499, 530, 563, 598, 635, 674, 715,
    758, 803, 850, 900, 952, 1006, 1062, 1120, 1180, 1242,
]


def test_lv1_to_50_authority_is_unchanged_and_new_curve_is_exact():
    thresholds = app_module.LV_THRESHOLDS
    costs = [thresholds[index] - thresholds[index - 1] for index in range(50, 100)]

    assert thresholds[:50] == BASELINE_XP
    assert app_module.MAX_LV == 100
    assert len(thresholds) == 100
    assert thresholds[49] == 188_500
    assert thresholds[99] == 500_000
    assert len(costs) == 50
    assert all(isinstance(cost, int) and cost > 0 for cost in costs)
    assert costs == sorted(costs)
    assert costs[0] == 4_515
    assert costs[-1] == 7_945
    assert sum(costs) == 311_500
    assert app_module.RANK_XP_THRESHOLDS["LV50"] == 4_515
    assert app_module.RANK_XP_THRESHOLDS["LV99"] == 7_945
    assert app_module.RANK_XP_THRESHOLDS["LV100"] == 0


@pytest.mark.parametrize(
    ("total_xp", "expected"),
    [
        (-10, (1, 0, 120)),
        (0, (1, 0, 120)),
        (120, (2, 0, 160)),
        (188_499, (49, 12_499, 12_500)),
        (188_500, (50, 0, 4_515)),
        (193_014, (50, 4_514, 4_515)),
        (193_015, (51, 0, 4_585)),
        (492_055, (99, 0, 7_945)),
        (499_999, (99, 7_944, 7_945)),
        (500_000, (100, 0, 0)),
        (500_123, (100, 123, 0)),
    ],
)
def test_xp_level_and_progress_boundaries(total_xp, expected):
    assert app_module.xp_to_lv(total_xp) == expected[0]
    assert app_module.lv_progress(total_xp) == expected


def test_hp_preserves_lv1_to_50_and_is_monotonic_through_100():
    assert app_module.LV_HP[:50] == BASELINE_HP
    assert len(app_module.LV_HP) == 100
    new_hp = app_module.LV_HP[50:]
    increments = [right - left for left, right in zip(app_module.LV_HP[49:], app_module.LV_HP[50:])]

    assert app_module._lv_max_hp(50) == 1_242
    assert app_module._lv_max_hp(51) == 1_252
    assert app_module._lv_max_hp(100) == 1_750
    assert all(value > 0 for value in new_hp)
    assert all(increment in (10, 11) for increment in increments)
    assert all(right >= left for left, right in zip(app_module.LV_HP, app_module.LV_HP[1:]))
    assert max(increments) == 11
    assert app_module._lv_max_hp(-1) == 60
    assert app_module._lv_max_hp(101) == 1_750
    assert app_module._lv_max_hp("invalid") == 60


def test_canonical_helpers_and_reward_gates_do_not_create_lv51_rewards():
    assert app_module.xp_to_lv(1_000_000) == 100
    assert app_module.lv_progress(1_000_000) == (100, 500_000, 0)
    assert app_module._rank_to_lv("LV100") == 100
    assert app_module._lane_b_level_skill_unlocks(50, 100) == []
    assert all(level <= 50 for level in app_module._LV_APPEARANCE_TRIGGER)


def test_quest_xp_writer_persists_canonical_rank_cache(tmp_path, monkeypatch):
    database = tmp_path / "quest-xp-rank-cache.sqlite"
    with sqlite3.connect(database) as conn:
        conn.execute(
            "CREATE TABLE user_stats (user_id INTEGER PRIMARY KEY, xp INTEGER, "
            "rank_level TEXT, rank_xp INTEGER)"
        )
        conn.execute(
            "INSERT INTO user_stats(user_id,xp,rank_level,rank_xp) "
            "VALUES(7,188500,'LV50',0)"
        )

    monkeypatch.setattr(
        app_module, "_safe_active_equipment_effect", lambda *args, **kwargs: 0
    )
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        granted = app_module._grant_quest_xp(conn, 7, 4_515, "test-level-boundary")
        conn.commit()

    assert granted == 4_515
    with sqlite3.connect(database) as conn:
        assert conn.execute(
            "SELECT xp,rank_level,rank_xp FROM user_stats WHERE user_id=7"
        ).fetchone() == (193_015, "LV51", 0)


def test_xp_status_serializes_lv100_without_next_level_or_division_by_zero(
    tmp_path, monkeypatch
):
    database = tmp_path / "xp-status-lv100.sqlite"
    with sqlite3.connect(database) as conn:
        conn.execute(
            "CREATE TABLE user_stats (user_id INTEGER PRIMARY KEY, xp INTEGER, "
            "rank_level TEXT DEFAULT 'LV1', rank_xp INTEGER DEFAULT 0, "
            "combo_streak INTEGER DEFAULT 0, max_combo INTEGER DEFAULT 0)"
        )
        conn.execute(
            "INSERT INTO user_stats(user_id,xp,rank_level,rank_xp) "
            "VALUES(7,500123,'LV99',7945)"
        )

    class _DbContext:
        def __enter__(self):
            self.conn = sqlite3.connect(database)
            self.conn.row_factory = sqlite3.Row
            return self.conn

        def __exit__(self, exc_type, exc, tb):
            if exc_type:
                self.conn.rollback()
            else:
                self.conn.commit()
            self.conn.close()

    monkeypatch.setattr(app_module, "get_db", _DbContext)
    app_module.app.config["TESTING"] = True
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
        session["username"] = "level100-test"

    response = client.get("/api/xp/status")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["rank_level"] == "LV100"
    assert payload["lv"] == 100
    assert payload["rank_xp"] == 123
    assert payload["rank_xp_needed"] == 0
    assert payload["rank_xp_remaining"] == 0
    assert payload["rank_pct"] == 100
    assert payload["next_level"] is None


def test_rewards_sync_recomputes_rank_cache_after_authoritative_xp_write():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("@app.route('/api/rewards/sync'")
    end = source.index("\n@app.route('/api/map-progress'", start)
    route = source[start:end]

    xp_write = route.index("UPDATE user_stats SET xp=COALESCE(xp,0)+?")
    cache_sync = route.index("_refresh_player_rank_cache(conn, uid)")
    assert xp_write < cache_sync


def test_hero_level_progress_has_capped_nonzero_max_state_copy():
    hero = (ROOT / "hero.html").read_text(encoding="utf-8")

    assert "Math.max(0, Math.min(100, Math.round(xp / xpNext * 100)))" in hero
    assert "      : 100;" in hero
    assert "Max level reached" in hero
    assert "已達目前最高等級" in hero
