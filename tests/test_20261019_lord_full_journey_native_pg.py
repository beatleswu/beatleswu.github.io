"""Real 20-question Lord First Clear on disposable PostgreSQL.

No synthetic grade writes, forged session, production database, SRS stub or
client-asserted score. Each practice + Lord answer enters canonical Flask.
"""
import json
from pathlib import Path

import pytest

from test_20261019_monthly_postgres import local_postgres, runtime as native_runtime

SOURCE = Path(__file__).parent / "fixtures" / "lord_trial_natural" / "questions.json"
CORPUS = json.loads(SOURCE.read_text(encoding="utf-8"))
QUESTION_BY_ID = {q["id"]: q for q in CORPUS}
ZONE = "k26_30"
UID = 716020


@pytest.fixture
def lord_player(native_runtime, monkeypatch, tmp_path):
    app = native_runtime
    # The real /api/explain path uses a relative KataGo cache filename.
    # Redirect it to this disposable pytest directory so E2E never creates
    # or reads an untracked sqlite database inside the product worktree.
    monkeypatch.setattr(app, "CACHE_DB", str(tmp_path / "lord-katago-cache.db"))
    monkeypatch.setattr(app, "_load_questions", lambda: CORPUS)
    with app.get_db() as conn:
        conn.execute(
            "INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (UID, "p1-lord-disposable", "Native PG Lord", "never-used", 0,
             "premium", "2026-10-19T00:00:00"),
        )
        conn.execute("INSERT INTO user_stats(user_id,coins,rank_level,xp) "
                     "VALUES(?,0,'LV1',0)", (UID,))
        conn.execute("INSERT INTO player_appearance(user_id,character_key) "
                     "VALUES(?,'apprentice')", (UID,))
        # Zone-star has an independent release migration, not part of the
        # generic bootstrap. Install explicitly in this disposable PG only.
        from migrations.adventure_zone_star_progression_v1 import upgrade as upgrade_zone_star
        assert upgrade_zone_star(conn)["valid"] is True
    # Fresh native PostgreSQL has not adopted the disposable corpus into
    # PuzzleIdentityStore. Practice v1 deliberately rejects legacy-only
    # locators. Install the established synthetic genesis receipt *only*
    # in this fixture; never mark the canonical production corpus as adopted.
    from puzzle_identity_store import PuzzleIdentityStore
    from migrations.puzzle_identity_registry_v1 import upgrade as upgrade_identity
    with app.get_db() as conn:
        upgrade_identity(conn)
        sha = "ab" * 32
        conn.execute(
            "INSERT INTO puzzle_identity_bootstrap_receipt "
            "(receipt_sha256,bootstrap_singleton,frozen_corpus_sha256,record_count,namespace_uuid,"
            "canonicalisation_rules_version,genesis_key_spec_version,historical_tree_commit,"
            "historical_tree_manifest_sha256,historical_rename_map_sha256,genesis_record_manifest_sha256,"
            "proposed_uuid_list_sha256,status,identities_written,applied_at,applied_by) "
            "VALUES(?,'GENESIS',?,?,'synthetic-lord-fixture','canon-source-v1','genesis-key-v1',"
            "'fixture','fixture','fixture','fixture','fixture','APPLIED',?,?, 'disposable-test-fixture')",
            (sha, "cd" * 32, len(CORPUS), len(CORPUS), "2026-10-19T00:00:00"))
        store = PuzzleIdentityStore(conn)
        for q in CORPUS:
            store.create_native_identity(
                creation_reason="Disposable Lord synthetic identity fixture",
                legacy_question_id=q["id"],
                current_source_path=f"fixture/lord/{q['id']}.sgf")
    client = app.app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = UID
        s["username"] = "p1-lord-disposable"
    return app, client


def checked_json(reply, status=200):
    data = reply.get_json()
    assert reply.status_code == status, (reply.status_code, data)
    assert isinstance(data, dict), data
    return data


def seed_lord_eligibility(client):
    """Ten real native practice answers, each validated by the judge."""
    for q in CORPUS[:10]:
        issued = checked_json(client.post("/api/srs/practice/attempt",
                                          json={"question_id": q["id"]}))
        credited = checked_json(client.post(
            "/api/srs/practice/answer",
            json={"attempt_token": issued["attempt_token"],
                  "moves": [{"action": "play", **q["accepted_moves"][0]}]}))
        assert credited["authoritative_grade"] == 5, (q["id"], credited)


def test_authoritative_twenty_question_first_clear_reward_unlock_and_new_login(lord_player):
    app, client = lord_player

    initial = checked_json(client.get("/api/adventure/bootstrap"))
    zones = {z["key"]: z for z in initial["zones"]}
    assert zones[ZONE]["unlocked"] is True
    assert zones[ZONE]["boss_ready"] is False
    assert zones["k21_25"]["unlocked"] is False

    refused = client.post("/api/adventure/boss/start", json={"zone_key": ZONE})
    assert refused.status_code == 400, refused.get_json()
    assert refused.get_json()["error"] == "progress_not_enough"

    # Real server-judged practice grants eligibility, no direct DB reviews.
    seed_lord_eligibility(client)
    preboss = checked_json(client.get("/api/adventure/bootstrap"))
    start_zone = next(z for z in preboss["zones"] if z["key"] == ZONE)
    assert start_zone["boss_ready"] is True, start_zone
    started = checked_json(client.post(
        "/api/adventure/boss/start", json={"zone_key": ZONE}))
    assert started["ok"] and not started["resumed"]
    assert started["total"] == 20 and started["pass_score"] == 16
    assert len(set(started["question_ids"])) == 20

    fake_finish = client.post(
        "/api/adventure/boss/finish", json={"correct": 20, "total": 20})
    assert fake_finish.status_code == 400, fake_finish.get_json()
    assert fake_finish.get_json()["error"] == "incomplete_attempt"

    for idx, qid in enumerate(started["question_ids"]):
        q = QUESTION_BY_ID[qid]
        response = checked_json(client.post(
            "/api/srs/review", json={
                "question_id": qid,
                "grade": 5,
                "source_context": f'boss_trial:{started["attempt_id"]}',
                "response_ms": 1234 + idx,
                "boss_answer": {"moves": [dict(q["accepted_moves"][0])]},
            }))
        assert response["ok"] is True, (idx, response)

    resumed = checked_json(client.post(
        "/api/adventure/boss/start", json={"zone_key": ZONE}))
    assert resumed["resumed"] and resumed["ready_to_finish"]
    assert resumed["answered_count"] == 20
    assert resumed["correct"] == 20
    assert resumed["attempt_id"] == started["attempt_id"]

    finish = checked_json(client.post(
        "/api/adventure/boss/finish", json={"correct": 0, "total": 0}))
    assert finish["ok"] and finish["passed"]
    assert finish["correct"] == 20 and finish["total"] == 20
    assert finish["pass_score"] == 16
    assert finish["first_clear_projection"]["status"] == "COMPLETED", finish
    assert finish["first_clear_projection"]["converged"] is True

    persisted = checked_json(client.get("/api/adventure/bootstrap"))
    state = {z["key"]: z for z in persisted["zones"]}
    assert state[ZONE]["cleared"] is True, state[ZONE]
    assert state["k21_25"]["unlocked"] is True, state["k21_25"]

    # New Flask session cookie, same user. Verify server-owned state is
    # durable and reward was issued once, not just UI/session display.
    new_client = app.app.test_client()
    with new_client.session_transaction() as s:
        s["user_id"] = UID
        s["username"] = "p1-lord-disposable"
    relogin = checked_json(new_client.get("/api/adventure/bootstrap"))
    relogin_zones = {z["key"]: z for z in relogin["zones"]}
    assert relogin_zones[ZONE]["cleared"]
    assert relogin_zones["k21_25"]["unlocked"]

    with app.get_db() as conn:
        boss = conn.execute(
            "SELECT cleared,attempts,best_score,stars FROM adventure_boss_progress "
            "WHERE user_id=? AND zone_key=?", (UID, ZONE)).fetchone()
        assert boss["cleared"] == 1 and boss["attempts"] == 1
        assert boss["best_score"] == 20
        rows = conn.execute(
            "SELECT question_id,source_context FROM review_log WHERE user_id=? "
            "AND source_context LIKE ?", (UID, "lord_trial:v1:%")).fetchall()
        assert len(rows) == 20
        wardrobe_before = conn.execute(
            "SELECT id,item_id,source FROM player_wardrobe "
            "WHERE user_id=? AND item_id='back_pack'",
            (UID,)).fetchall()
        assert len(wardrobe_before) == 1
        stars_before = conn.execute(
            "SELECT star_number FROM adventure_zone_star_earnings "
            "WHERE user_id=? AND zone_key=?", (UID,ZONE)).fetchall()
        assert len(stars_before) == 1
        unlock_before = conn.execute(
            "SELECT zone_key,source FROM adventure_zone_unlocks "
            "WHERE user_id=? AND zone_key='k21_25'",(UID,)).fetchall()
        assert len(unlock_before) == 1

    # A second complete 20-question replay on a fresh signed session must
    # never reissue a first-clear wardrobe reward nor a second Zone star.
    replay = checked_json(new_client.post(
        "/api/adventure/boss/start",json={"zone_key":ZONE}))
    assert replay["attempt_mode"] == "replay" and replay["replay"] is True
    assert replay["total"] == 20 and not replay["resumed"]
    for qid in replay["question_ids"]:
        q=QUESTION_BY_ID[qid]
        answer=checked_json(new_client.post(
            "/api/srs/review",json={
                "question_id":qid,"grade":5,
                "source_context":f'boss_trial:{replay["attempt_id"]}',
                "response_ms":1400,
                "boss_answer":{"moves":[dict(q["accepted_moves"][0])]},
            }))
        assert answer["ok"] is True
    replay_end=checked_json(new_client.post(
        "/api/adventure/boss/finish",json={"correct":0,"total":0}))
    assert replay_end["passed"] is True
    assert replay_end["correct"] == 20
    assert replay_end["attempt_mode"] == "replay"
    assert replay_end["reward"]["first_clear"] is False
    assert replay_end["reward"]["replay"] is True
    assert replay_end["reward"]["entitlement_consumed"] is False
    with app.get_db() as conn:
        wardrobe_after = conn.execute(
            "SELECT id,item_id,source FROM player_wardrobe "
            "WHERE user_id=? AND item_id='back_pack'",(UID,)).fetchall()
        stars_after=conn.execute(
            "SELECT star_number FROM adventure_zone_star_earnings "
            "WHERE user_id=? AND zone_key=?",(UID,ZONE)).fetchall()
        unlock_after=conn.execute(
            "SELECT zone_key,source FROM adventure_zone_unlocks "
            "WHERE user_id=? AND zone_key='k21_25'",(UID,)).fetchall()
        boss_after=conn.execute(
            "SELECT cleared,attempts,best_score FROM adventure_boss_progress "
            "WHERE user_id=? AND zone_key=?",(UID,ZONE)).fetchone()
    assert [tuple(x) for x in wardrobe_after]==[tuple(x) for x in wardrobe_before]
    assert [tuple(x) for x in stars_after]==[tuple(x) for x in stars_before]
    assert [tuple(x) for x in unlock_after]==[tuple(x) for x in unlock_before]
    assert boss_after["cleared"] == 1 and boss_after["attempts"] == 2
    final_client=app.app.test_client()
    with final_client.session_transaction() as s:
        s["user_id"]=UID
        s["username"]="p1-lord-disposable"
    after_relogin=checked_json(final_client.get("/api/adventure/bootstrap"))
    final_zones={z["key"]:z for z in after_relogin["zones"]}
    assert final_zones[ZONE]["cleared"] and final_zones["k21_25"]["unlocked"]
    print("LORD_20_FIRST_CLEAR_NATIVE_PG", json.dumps({
        "verdict": "LORD_FIRST_CLEAR_PASS",
        "practice_questions": 10,
        "server_boss_questions": 20,
        "server_score": finish["correct"],
        "reward": finish.get("reward"),
        "first_clear_projection": finish.get("first_clear_projection"),
        "zone1_cleared": state[ZONE]["cleared"],
        "zone2_unlocked": state["k21_25"]["unlocked"],
        "new_session_state_persisted": True,
        "production": False,
    }, default=str, ensure_ascii=True))

@pytest.mark.parametrize("input_mode", ["desktop_mouse", "chrome_tablet_touch"])
def test_shipped_index_wgo_clicks_complete_full_twenty_lord_questions(lord_player, input_mode):
    """Player-visible 20 consecutive WGo inputs, real SRS and Boss finish."""
    import os
    import subprocess
    import threading
    from werkzeug.serving import make_server

    app, client = lord_player
    # The initial Spirit is a governed mutation. Provision additive schema
    # only inside this disposable PG, as in the separate Companion proof.
    from migrations.companion_operations_v1 import upgrade as upgrade_companion
    from migrations.spirit_evolution_events_v1 import upgrade as upgrade_evolution
    with app.get_db() as conn:
        assert upgrade_companion(conn)["missing"] == []
        assert upgrade_evolution(conn)["missing"] == []

    seed_lord_eligibility(client)
    pre = checked_json(client.get("/api/adventure/bootstrap"))
    assert next(z for z in pre["zones"] if z["key"] == ZONE)["boss_ready"]
    cookie = client.get_cookie("session")
    assert cookie and cookie.value
    server = make_server("127.0.0.1", 0, app.app.wsgi_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        runner = Path(__file__).parent / "e2e" / "run_20261019_real_lord_20_wgo_browser.mjs"
        proc = subprocess.run(
            ["node", str(runner)],
            input=json.dumps({"origin": f"http://127.0.0.1:{server.server_port}",
                              "sessionCookie": cookie.value}),
            capture_output=True, text=True, encoding="utf-8", timeout=180,
            cwd=Path(__file__).resolve().parent.parent,
            env={**os.environ, "GO_P1_LORD_TOUCH":
                 "1" if input_mode == "chrome_tablet_touch" else "0"},
        )
        assert proc.returncode == 0, proc.stderr[-2800:] + proc.stdout[-1300:]
        report = json.loads(proc.stdout)
        assert report["verdict"] == "REAL_INDEX_LORD_20_WGO_FIRST_CLEAR_PASS"
        assert report["answered"] == 20
        assert report["actualIndex"] is True and report["actualWGoClicks"] is True
        assert report["usedMockRoutes"] is False
        assert report["fresh"][ZONE]["cleared"] is True
        assert report["fresh"]["k21_25"]["unlocked"] is True
        assert report["realIpad"] is False
        with app.get_db() as conn:
            rows=conn.execute(
                "SELECT COUNT(*) AS n FROM review_log WHERE user_id=? "
                "AND source_context LIKE ?",
                (UID, "lord_trial:v1:%"),
            ).fetchone()["n"]
            rewards=conn.execute(
                "SELECT COUNT(*) AS n FROM player_wardrobe "
                "WHERE user_id=? AND item_id='back_pack'", (UID,),
            ).fetchone()["n"]
        assert rows == 20 and rewards == 1
        print("P1_LORD_PLAYER_VISIBLE_WGO_20",json.dumps({
            "input":input_mode,"answered":20,
            "reward_once":rewards,"canonical_verdict":report["verdict"],
            "zone2_unlocked":True,"actual_iPad":False},ensure_ascii=True))
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()
