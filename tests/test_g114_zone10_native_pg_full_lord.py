"""G114 Zone10 full 20-question Lord on disposable native PostgreSQL.

Fixture simulates a *copied* already-unlocked 7d user's prior nine
server-sourced practice receipts; fresh Boss answers use actual Flask HTTP,
unchanged G065/Lord judgement, server persistence and final reward.
"""
import json
from pathlib import Path
import pytest
from test_20261019_monthly_postgres import local_postgres,runtime as native_runtime
from test_g114_zone10_real_judge import Q as VERIFIED_Q,solution_moves
from test_g114_zone10_source_authority import ORIGINAL

UID=716114
CORPUS=list(VERIFIED_Q)+list(ORIGINAL)
BY_ID={q["id"]:q for q in CORPUS}
ZONE="d7_plus"


@pytest.fixture
def zone10_player(native_runtime,monkeypatch,tmp_path):
    app=native_runtime
    monkeypatch.setattr(app,"CACHE_DB",str(tmp_path/"g114-zone10-cache.db"))
    monkeypatch.setattr(app,"_load_questions",lambda:CORPUS)
    with app.get_db() as conn:
        conn.execute(
            "INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at) VALUES(?,?,?,?,?,?,?)",
            (UID,"g114-z10-disposable","Z10 Clone","never-used",0,"premium","2026-10-26T00:00:00"))
        conn.execute("INSERT INTO user_stats(user_id,coins,rank_level,xp) VALUES(?,0,'LV10',0)",(UID,))
        conn.execute("INSERT INTO player_appearance(user_id,character_key) VALUES(?,'apprentice')",(UID,))
        from migrations.adventure_zone_star_progression_v1 import upgrade as up_star
        assert up_star(conn)["valid"]
        from migrations.puzzle_identity_registry_v1 import upgrade as up_identity
        up_identity(conn)
        from puzzle_identity_store import PuzzleIdentityStore
        sha="bc"*32
        conn.execute(
            "INSERT INTO puzzle_identity_bootstrap_receipt "
            "(receipt_sha256,bootstrap_singleton,frozen_corpus_sha256,record_count,namespace_uuid,"
            "canonicalisation_rules_version,genesis_key_spec_version,historical_tree_commit,"
            "historical_tree_manifest_sha256,historical_rename_map_sha256,genesis_record_manifest_sha256,"
            "proposed_uuid_list_sha256,status,identities_written,applied_at,applied_by) "
            "VALUES(?,'GENESIS',?,?,'g114-z10-disposable','canon-source-v1','genesis-key-v1',"
            "'fixture','fixture','fixture','fixture','fixture','APPLIED',?,?, 'disposable-test-fixture')",
            (sha,"ab"*32,len(CORPUS),len(CORPUS),"2026-10-26T00:00:00"))
        store=PuzzleIdentityStore(conn)
        for q in CORPUS:
            store.create_native_identity(creation_reason="G114 Zone10 disposable copied-player",
                legacy_question_id=q["id"],current_source_path=f"fixture/z10/{q['id']}.sgf")
        # Historical unlocked state, not artificially given by client.
        conn.execute(
            "INSERT INTO adventure_zone_unlocks"
            "(user_id,zone_key,source,start_zone_key,unlocked_at) VALUES(?,?,?,?,?)",
            (UID,ZONE,"placement",ZONE,"2026-10-25T00:00:00"))
        # Restore prior trustworthy practice receipts in disposable *copy*.
        # Future XP/rewards are never fabricated by this fixture.
        for q in VERIFIED_Q[:9]:
            conn.execute(
                "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context)"
                " VALUES(?,?,?,?,?)",
                (UID,q["id"],5,"2026-10-25T00:00:00",
                 f"practice:v1:copied-receipt:{q['id']}"))
    c=app.app.test_client()
    with c.session_transaction() as session:
        session["user_id"]=UID
        session["username"]="g114-z10-disposable"
    return app,c


def check(reply,status=200):
    assert reply.status_code==status,(reply.status_code,reply.get_json())
    return reply.get_json()


def test_zone10_twenty_real_questions_finish_and_durable_relogin(zone10_player):
    app,c=zone10_player
    before=check(c.get("/api/adventure/bootstrap"))
    zone=next(z for z in before["zones"] if z["key"]==ZONE)
    assert zone["unlocked"] and zone["boss_ready"],zone
    assert zone["total"]==30 and zone["g114_qualified_correct"]==9
    start=check(c.post("/api/adventure/boss/start",json={"zone_key":ZONE}))
    assert start["total"]==20 and len(set(start["question_ids"]))==20
    attempt=start["attempt_id"]
    for qid in start["question_ids"]:
        q=BY_ID[qid]
        assert qid in {a["id"] for a in VERIFIED_Q}
        answer=check(c.post("/api/srs/review",json={
            "question_id":qid,"grade":5,
            "source_context":f"boss_trial:{attempt}",
            "response_ms":1200,
            "boss_answer":{"moves":solution_moves(q)}
        }))
        assert answer["ok"],(qid,answer)
    resume=check(c.post("/api/adventure/boss/start",json={"zone_key":ZONE}))
    assert resume["answered_count"]==20
    assert resume["correct"]==20
    result=check(c.post("/api/adventure/boss/finish",json={"correct":0,"total":0}))
    assert result["passed"] and result["correct"]==20
    assert result["first_clear_projection"]["status"]=="COMPLETED"
    relogin=app.app.test_client()
    with relogin.session_transaction() as session:
        session["user_id"]=UID
        session["username"]="g114-z10-disposable"
    saved=check(relogin.get("/api/adventure/bootstrap"))
    state=next(z for z in saved["zones"] if z["key"]==ZONE)
    assert state["cleared"] and state["stars"]>=1 and state["unlocked"]
    with app.get_db() as conn:
        rows=conn.execute("SELECT question_id,source_context FROM review_log WHERE user_id=? AND source_context LIKE ?",
            (UID,"lord_trial:v1:%")).fetchall()
        assert len(rows)==20
        stats=conn.execute("SELECT xp,coins FROM user_stats WHERE user_id=?",(UID,)).fetchone()
        assert stats["xp"]>=0 and stats["coins"]>=0



def test_copied_player_progress_entitlements_never_diluted_or_early(zone10_player):
    app,_client=zone10_player
    cases=[
        # fresh but never unlocked, partial legacy, unlocked pending,
        # completed with existing stars, just under new threshold, exact threshold
        ("not_started",716124,0,0,False,False,0,False),
        ("partial_original",716125,2,0,True,False,0,True),
        ("unlocked_no_progress",716126,0,0,True,False,0,False),
        ("already_cleared_stars",716127,3,0,True,True,2,False),
        ("new_progress_below_gate",716128,0,8,True,False,0,False),
        ("new_progress_at_gate",716129,0,9,True,False,0,True)
    ]
    with app.get_db() as conn:
        for name,uid,legacy,qualified,unlocked,cleared,stars,_ready in cases:
            conn.execute(
                "INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (uid,"g114-copy-"+name,name,"unused",0,"premium","2026-10-26T00:00:00"))
            conn.execute("INSERT INTO user_stats(user_id,coins,rank_level,xp) VALUES(?,0,'LV10',0)",(uid,))
            conn.execute("INSERT INTO player_appearance(user_id,character_key) VALUES(?,'apprentice')",(uid,))
            if unlocked:
                conn.execute("INSERT INTO adventure_zone_unlocks(user_id,zone_key,source,start_zone_key,unlocked_at) "
                             "VALUES(?,?,?,?,?)",
                             (uid,ZONE,"placement",ZONE,"2026-10-01T00:00:00"))
            if cleared:
                conn.execute("INSERT INTO adventure_boss_progress "
                             "(user_id,zone_key,cleared,stars,attempts,best_score) VALUES(?,?,1,?,1,18)",
                             (uid,ZONE,stars))
            for q in ORIGINAL[:legacy]+VERIFIED_Q[:qualified]:
                conn.execute("INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context)"
                             " VALUES(?,?,?,?,?)",
                             (uid,q["id"],5,"2026-10-01T00:00:00",f"practice:v1:copied:{q['id']}"))
    for name,uid,old_count,new_count,unlocked,cleared,stars,expected_ready in cases:
        c=app.app.test_client()
        with c.session_transaction() as session:
            session["user_id"]=uid
        body=check(c.get("/api/adventure/bootstrap"))
        state=next(z for z in body["zones"] if z["key"]==ZONE)
        assert state["total"]==30
        assert state["unlocked"]==unlocked,(name,state)
        assert state["cleared"]==cleared,(name,state)
        assert state["stars"]>=stars,(name,state)
        assert state["g114_qualified_correct"]==new_count,(name,state)
        assert state["g114_historical_correct"]==old_count,(name,state)
        old_pct=round(old_count/5*100)
        new_pct=round(new_count/30*100)
        assert state["pct"]==max(old_pct,new_pct),(name,state)
        assert 0<=state["pct"]<=100
        assert state["boss_ready"]==expected_ready,(name,state)



def test_zone10_actual_map_battle_http_correct_and_idempotent(zone10_player,monkeypatch):
    app,c=zone10_player
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE","global")
    q=VERIFIED_Q[0]
    protocol={"X-Map-Battle-Client-Protocol":"v1"}
    started=c.post("/api/adventure/map-battles/v1/attempts",
                   headers=protocol,json={"zone_key":ZONE,"question_id":q["id"]})
    assert started.status_code==200,(started.status_code,started.get_json())
    data=started.get_json()
    payload={
       "battle_id":data["battle_id"],"attempt_id":data["attempt_id"],
       "submission_nonce":data["submission_nonce"],
       "battle_revision":data["battle"]["battle_revision"],
       "question_revision":data["question_revision"],
       "player_color":data["player_color"],
       "transform_id":data["transform_id"],
       "transform_version":data["transform_version"],
       "moves":solution_moves(q)
    }
    first=c.post("/api/adventure/map-battles/v1/answers",headers=protocol,json=payload)
    assert first.status_code==200,(first.status_code,first.get_json())
    assert first.get_json()["result"]=="CORRECT",first.get_json()
    replay=c.post("/api/adventure/map-battles/v1/answers",headers=protocol,json=payload)
    assert replay.status_code==200,(replay.status_code,replay.get_json())
    assert replay.get_json()["duplicate"] is True
    with app.get_db() as conn:
        rows=conn.execute("SELECT * FROM map_battle_submissions WHERE attempt_id=?",
                          (payload["attempt_id"],)).fetchall()
        assert len(rows)==1
        assert rows[0]["settlement_state"]=="SETTLED"
