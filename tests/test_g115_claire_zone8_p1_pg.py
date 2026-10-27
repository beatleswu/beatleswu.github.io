"""G115 P1 real Flask + disposable PG16 Zone8 regression (no production student writes)."""
import pytest
from test_20261019_monthly_postgres import runtime, local_postgres

UID = 95115
ZONE = "d3_4"
BAD = {"id": 9511501, "content": "(;GM[1]FF[4]SZ[19]PL[B](;B[aa])(;B[bb]))", "rank": "3d", "enabled": True}
GOOD = {"id": 9511502, "content": "(;GM[1]FF[4]SZ[19]PL[B](;B[dd]))", "rank": "3d", "enabled": True}

@pytest.fixture
def player(runtime, monkeypatch):
    app = runtime
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "global")
    topic = next(z for z in app.ADVENTURE_ZONES if z["key"] == ZONE)["books"][0]
    monkeypatch.setattr(app, "_load_questions", lambda: [{**BAD, "topic": topic}, {**GOOD, "topic": topic}])
    app.app.config["TESTING"] = True
    with app.get_db() as c:
        c.execute("INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,premium_until,elo_rating,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                  (UID, "g115-synthetic", "synthetic", "unusable", 0, "premium", None, 1757.79, "2026-10-27"))
        c.execute("INSERT INTO user_stats(user_id,go_rank,xp,coins,player_hp,player_max_hp) VALUES(?,?,?,?,?,?)",
                  (UID, "1d", 2345, 643, 78, 100))
        c.execute("INSERT INTO adventure_boss_progress(user_id,zone_key,cleared,stars,attempts,best_score,cleared_at) VALUES(?,?,1,1,1,16,'2026-07-08T16:04:19')",
                  (UID, "d1_2"))
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = UID
        session["username"] = "g115-synthetic"
    return app, client

def attempt(client, qid):
    return client.post("/api/adventure/map-battles/v1/attempts",
                       headers={"X-Map-Battle-Client-Protocol": "v1"},
                       json={"zone_key": ZONE, "question_id": qid})

def snapshot(app):
    with app.get_db() as c:
        stats = tuple(c.execute("SELECT xp,coins,player_hp,player_max_hp FROM user_stats WHERE user_id=?", (UID,)).fetchone())
        battles = [tuple(r) for r in c.execute("SELECT zone_key,state FROM map_battles WHERE user_id=?", (UID,)).fetchall()]
        attempts = [tuple(r) for r in c.execute("SELECT question_id,state FROM map_battle_attempts WHERE user_id=?", (UID,)).fetchall()]
        unlocks = c.execute("SELECT count(*) FROM adventure_zone_unlocks WHERE user_id=? AND zone_key=?", (UID, ZONE)).fetchone()[0]
    return stats, battles, attempts, unlocks

def test_preprojection_first_star_409_then_safe_zone8_attempt_without_reward_change(player):
    app, client = player
    assert app._premium_live_from_fields("premium", None)
    with app.get_db() as c:
        assert app._map_battle_zone_unlocked(c, UID, ZONE) is True
    before = snapshot(app)
    assert before == ((2345,643,78,100),[],[],0)
    bad = attempt(client, BAD["id"])
    assert bad.status_code == 409, bad.get_json()
    assert bad.get_json()["code"] == "map_battle_question_incompatible"
    assert snapshot(app) == before
    good = attempt(client, GOOD["id"])
    assert good.status_code == 200, good.get_json()
    assert good.get_json()["question_id"] == GOOD["id"]
    after = snapshot(app)
    assert after[0] == before[0] and after[3] == 0
    assert len(after[1]) == 1 and after[1][0][0] == ZONE
    assert after[2] == [(GOOD["id"], "ISSUED")]
    with app.get_db() as c:
        assert tuple(c.execute("SELECT cleared,stars,best_score FROM adventure_boss_progress WHERE user_id=? AND zone_key='d1_2'", (UID,)).fetchone()) == (1,1,16)

def test_no_previous_clear_is_rejected_without_player_write(player):
    app, client = player
    with app.get_db() as c:
        c.execute("UPDATE adventure_boss_progress SET cleared=0,stars=0 WHERE user_id=?", (UID,))
        assert app._map_battle_zone_unlocked(c,UID,ZONE) is False
    rejected = attempt(client,GOOD["id"])
    assert rejected.status_code == 403, rejected.get_json()
    assert rejected.get_json()["code"] == "map_battle_zone_not_unlocked"
    assert snapshot(app) == ((2345,643,78,100),[],[],0)

def test_premium_alone_never_grants_boss_unlock(player):
    app, _ = player
    with app.get_db() as c:
        c.execute("DELETE FROM adventure_boss_progress WHERE user_id=?", (UID,))
        assert app._premium_live_from_fields("premium", None) is True
        assert app._map_battle_zone_unlocked(c,UID,ZONE) is False
