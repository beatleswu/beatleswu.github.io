"""Cross-system P1: live Flask routes + isolated native PostgreSQL 17.

The actual XP writer commits in the same DB read by Player Presentation,
XP HUD and Adventure bootstrap.  This is NOT a boss-completion E2E or
a production Test02 login. No mocks of those three HTTP read routes.
"""
from __future__ import annotations

import json
import subprocess
import shutil
from pathlib import Path

import pytest

# Reuse the independently disposable/native PG fixture; it creates a new
# loopback-only test cluster with fresh canonical application schema.
from test_20261019_monthly_postgres import (  # noqa: F401
    local_postgres,
    runtime as native_runtime,
)


@pytest.fixture
def growth_journey(native_runtime):
    app = native_runtime
    uid = 370119
    with app.get_db() as conn:
        conn.execute(
            """INSERT INTO users
               (id,username,nickname,password_hash,is_admin,plan,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (uid, "p1-hero-xp-test02-fixture", "P1 Hero", "synthetic-unused",
             0, "free", "2026-10-19T00:00:00"),
        )
        conn.execute(
            "INSERT INTO user_stats(user_id, coins, xp, rank_level, rank_xp) "
            "VALUES(?,0,119,'LV1',119)",
            (uid,),
        )
        conn.execute(
            "INSERT INTO player_appearance(user_id, character_key) "
            "VALUES(?,'apprentice')",
            (uid,),
        )
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = uid
        session["username"] = "p1-hero-xp-test02-fixture"
    return app, client, uid


def _get(client, route):
    response = client.get(route)
    assert response.status_code == 200, (route, response.status_code,
                                        response.get_data(as_text=True)[:400])
    return response.get_json()


def _check_live_hero_renderer(presentation, profile):
    node = shutil.which('node')
    assert node, 'Node required to run the actual shipped hero.html JavaScript'
    script = (Path(__file__).resolve().parent / 'e9_node_tests'
              / 'run_20261019_hero_real_api_projection.js')
    result = subprocess.run(
        [node, str(script)],
        input=json.dumps({'presentation': presentation, 'profile': profile}),
        encoding='utf-8', text=True, capture_output=True, timeout=20,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0, result.stderr + result.stdout
    output = json.loads(result.stdout)
    assert output['verdict'] == 'REAL_NATIVE_PG_API_TO_SHIPPED_HERO_VIEW_PASS'
    assert output['production_session'] is False
    return output


def test_hero_xp_level_crosses_120_in_real_db_and_all_three_read_routes_agree(growth_journey):
    app, client, uid = growth_journey
    before_hero = _get(client, "/api/player/presentation")
    before_xp = _get(client, "/api/xp/status")
    before_profile = _get(client, "/api/skills/profile")
    assert before_profile["total_xp"] == before_hero["progression"]["xp"]
    assert before_profile["lv_xp"] == before_hero["progression"]["rank_xp"]
    before_render = _check_live_hero_renderer(before_hero, before_profile)
    assert before_render['xp_bar_percent'] == 99
    before_world = _get(client, "/api/adventure/bootstrap")
    assert before_hero["projection_status"] == "OK"
    assert before_hero["progression"]["xp"] == 119
    assert before_hero["progression"]["level"] == 1
    assert before_hero["progression"]["rank_xp"] == 119
    assert before_xp["rank_level"] == "LV1"
    assert before_xp["rank_xp"] == 119
    assert before_xp["rank_xp_needed"] == 120
    assert "zones" in before_world and isinstance(before_world["zones"], list)
    assert before_world["zones"], 'a vacuous empty map cannot prove progression preservation'

    # Exercise the REAL XP settlement helper used by Quest/Daily rewards:
    # writer owns rank cache in the same transaction, no test-side recompute.
    with app.get_db() as conn:
        awarded = app._grant_quest_xp(conn, uid, 1, "p1-native-pg-growth")
    assert awarded >= 1
    after_hero = _get(client, "/api/player/presentation")
    after_xp = _get(client, "/api/xp/status")
    after_profile = _get(client, "/api/skills/profile")
    assert after_profile["total_xp"] == after_hero["progression"]["xp"]
    assert after_profile["xp"] == after_hero["progression"]["rank_xp"]
    assert after_profile["level"] == after_hero["progression"]["level"]
    assert after_profile["xp_next"] == after_xp["rank_xp_needed"]
    after_render = _check_live_hero_renderer(after_hero, after_profile)
    assert after_render['xp_bar_percent'] == 0
    assert before_render['level'] + 1 == after_render['level']
    after_world = _get(client, "/api/adventure/bootstrap")
    expected = app.lv_progress(119 + awarded)
    assert after_hero["progression"]["xp"] == after_xp["xp"] == 119 + awarded
    assert after_hero["progression"]["level"] == after_xp["lv"] == expected[0]
    assert after_hero["progression"]["rank_xp"] == after_xp["rank_xp"] == expected[1]
    assert after_xp["rank_xp_needed"] == expected[2]
    assert after_hero["progression"]["rank_level"] == after_xp["rank_level"]
    # Only XP changed; Adventure unlocks and clear history are independent
    # of the player display level. Never grant a map clear from XP alone.
    assert [(z["key"], z.get("cleared"), z.get("unlocked"))
            for z in after_world["zones"]] == [
                (z["key"], z.get("cleared"), z.get("unlocked"))
                for z in before_world["zones"]]
    with app.get_db() as conn:
        stats = conn.execute(
            "SELECT xp, rank_level,rank_xp FROM user_stats WHERE user_id=?",
            (uid,),
        ).fetchone()
    assert int(stats["xp"]) == 119 + awarded
    assert stats["rank_level"] == after_xp["rank_level"]
    assert int(stats["rank_xp"]) == after_xp["rank_xp"]


def test_same_authority_after_new_login_session_and_no_spurious_world_clear(growth_journey):
    app, old_client, uid = growth_journey
    with app.get_db() as conn:
        app._grant_quest_xp(conn, uid, 162, "p1-native-pg-growth-session")
    old_hero = _get(old_client, "/api/player/presentation")
    world = _get(old_client, "/api/adventure/bootstrap")
    # Re-login equivalent: new, independently constructed Flask session for
    # exactly the same account. Not a real OAuth/account authentication event.
    fresh_client = app.app.test_client()
    with fresh_client.session_transaction() as session:
        session["user_id"] = uid
        session["username"] = "p1-hero-xp-test02-fixture"
    new_hero = _get(fresh_client, "/api/player/presentation")
    new_xp = _get(fresh_client, "/api/xp/status")
    new_world = _get(fresh_client, "/api/adventure/bootstrap")
    new_profile = _get(fresh_client, "/api/skills/profile")
    _check_live_hero_renderer(new_hero, new_profile)
    assert new_hero["progression"] == old_hero["progression"]
    assert new_xp["xp"] == new_hero["progression"]["xp"]
    assert new_xp["rank_xp"] == new_hero["progression"]["rank_xp"]
    # The map can include session-specific "effective selected zone" hints.
    # Assert the durable zone authority rather than equating ephemeral UI state.
    durable = lambda items: [
        (z["key"], z.get("cleared"), z.get("unlocked"),
         z.get("attempts"), z.get("best_score"), z.get("stars"))
        for z in items
    ]
    assert new_world["zones"], 'fresh-session map must not be empty'
    assert durable(new_world["zones"]) == durable(world["zones"])
    assert all(not z.get("cleared") for z in new_world["zones"])
