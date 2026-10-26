"""G114 P0-A real Flask / native disposable PG Map Battle safety regression."""
import pytest
from test_20261019_monthly_postgres import runtime, local_postgres

from map_battle_persistence import create_map_battle
from map_battle_runtime import issue_attempt_with_submission_nonce

BAD = {"id":15483, "content":"(;GM[1]FF[4]SZ[19](;B[aa])(;B[bb]))",
       "rank":"30k", "enabled":True}
GOOD = {"id":301, "content":"(;GM[1]FF[4]SZ[19]PL[B](;B[dd]))",
        "rank":"30k", "enabled":True}
PROTOCOL = {"X-Map-Battle-Client-Protocol":"v1"}


@pytest.fixture
def map_app(runtime,monkeypatch):
    app=runtime
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE","global")
    monkeypatch.setattr(app,"_load_questions",lambda:[BAD,GOOD])
    monkeypatch.setattr(app,"is_premium",lambda uid:True)
    monkeypatch.setitem(app.app.config,"TESTING",True)
    with app.get_db() as conn:
        conn.execute("INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at)"
                     "VALUES(?,?,?,?,?,?,?)",
                     (9114,"g114-map-synthetic","g114-map","not-a-password",0,"premium","2026-10-26"))
        conn.execute("INSERT INTO user_stats(user_id,coins,rank_level,xp,player_hp,player_max_hp)"
                     "VALUES(?,?,?,?,?,?)",(9114,50,"LV1",10,80,100))
    return app


def _client(app):
    client=app.app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"]=9114
        sess["username"]="g114-map-synthetic"
    return client


def _post_attempt(client,qid):
    return client.post("/api/adventure/map-battles/v1/attempts",
                       headers=PROTOCOL,
                       json={"zone_key":"legacy::g114-test","question_id":qid})


def test_p0a_new_bad_attempt_rejected_before_any_state_write(map_app):
    c=_client(map_app)
    bad=_post_attempt(c,15483)
    assert bad.status_code==409,bad.get_json()
    j=bad.get_json()
    assert j["code"]=="map_battle_question_incompatible"
    assert j["reason_code"]=="legacy_unreviewed_sgf_terminal"
    assert j["retryable"] is False
    with map_app.get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM map_battles WHERE user_id=9114").fetchone()[0]==0
        assert conn.execute("SELECT COUNT(*) FROM map_battle_attempts WHERE user_id=9114").fetchone()[0]==0


def test_p0a_legacy_unsafe_issued_attempt_can_skip_without_resetting_hp(map_app):
    # Simulates a pre-G114 server-issued nonce, preserving exact existing
    # battle and attempt rows. Neither recovery nor safe new question rewrites it.
    with map_app.get_db() as conn:
        battle_id=create_map_battle(
            conn,user_id=9114,zone_key="legacy::g114-test",
            player_hp=80,player_hp_max=100,monster_hp=70,monster_hp_max=100,
            migration_source="legacy-adventure-map",
            migration_version="map-battle-v1",
        )
        ctx=map_app._map_battle_question_context(BAD)
        prior=issue_attempt_with_submission_nonce(
            conn,user_id=9114,battle_id=battle_id,question=BAD,
            initial_position_identity=ctx["initial_position_identity"],
            board_size=ctx["board_size"],player_color=ctx["player_color"],
            transform_version=ctx["transform_version"],
            transform_id=ctx["transform_id"],
            mode_environ={"E10_MAP_BATTLE_V1_MODE":"global"},
        )
    c=_client(map_app)
    rejected=c.post(
        f"/api/adventure/map-battles/v1/attempts/{prior['attempt_id']}/resume-validation",
        headers=PROTOCOL,json={"battle_id":battle_id,"zone_key":"legacy::g114-test",
            "question_id":15483,"submission_nonce":prior["submission_nonce"]},
    )
    assert rejected.status_code==409,rejected.get_json()
    assert rejected.get_json()["reason_code"]=="legacy_unreviewed_sgf_terminal"
    safe=_post_attempt(c,301)
    assert safe.status_code==200,safe.get_json()
    assert safe.get_json()["battle_id"]==battle_id
    assert safe.get_json()["question_id"]==301
    with map_app.get_db() as conn:
        row=conn.execute("SELECT * FROM map_battles WHERE id=?",(battle_id,)).fetchone()
        assert row["player_hp"]==80 and row["monster_hp"]==70
        old=conn.execute("SELECT * FROM map_battle_attempts WHERE id=?",
                         (prior["attempt_id"],)).fetchone()
        assert old["state"]=="ISSUED"
        assert conn.execute("SELECT COUNT(*) FROM map_battle_submissions WHERE battle_id=?",
                            (battle_id,)).fetchone()[0]==0
        assert conn.execute("SELECT xp,coins FROM user_stats WHERE user_id=9114").fetchone()[:]==[10,50]


def test_p0a_existing_unsafe_answer_no_settlement_or_hp_mutation(map_app):
    with map_app.get_db() as conn:
        battle_id=create_map_battle(
            conn,user_id=9114,zone_key="legacy::g114-test",
            player_hp=85,player_hp_max=100,monster_hp=75,monster_hp_max=100,
            migration_source="legacy-adventure-map",migration_version="map-battle-v1",
        )
        ctx=map_app._map_battle_question_context(BAD)
        old=issue_attempt_with_submission_nonce(
            conn,user_id=9114,battle_id=battle_id,question=BAD,
            initial_position_identity=ctx["initial_position_identity"],
            board_size=19,player_color="B",transform_version=ctx["transform_version"],
            transform_id=ctx["transform_id"],mode_environ={"E10_MAP_BATTLE_V1_MODE":"global"},
        )
    c=_client(map_app)
    payload={
        "battle_id":battle_id,"attempt_id":old["attempt_id"],
        "submission_nonce":old["submission_nonce"],"battle_revision":0,
        "question_revision":ctx["question_revision"],"player_color":"B",
        "transform_id":"identity","transform_version":ctx["transform_version"],
        "moves":[{"x":0,"y":0,"action":"play"}],
    }
    response=c.post("/api/adventure/map-battles/v1/answers",
                    headers=PROTOCOL,json=payload)
    assert response.status_code==409,response.get_json()
    assert response.get_json()["reason_code"]=="legacy_unreviewed_sgf_terminal"
    with map_app.get_db() as conn:
        b=conn.execute("SELECT player_hp,monster_hp,battle_revision FROM map_battles WHERE id=?",(battle_id,)).fetchone()
        assert tuple(b)==(85,75,0)
        assert conn.execute("SELECT COUNT(*) FROM map_battle_submissions WHERE battle_id=?",(battle_id,)).fetchone()[0]==0
        assert conn.execute("SELECT xp,coins FROM user_stats WHERE user_id=9114").fetchone()[:]==[10,50]


def _answer_from_prepared(data, move, *, nonce=None):
    return {
        "battle_id":data["battle_id"],
        "attempt_id":data["attempt_id"],
        "submission_nonce":nonce or data["submission_nonce"],
        "battle_revision":data["battle"]["battle_revision"],
        "question_revision":data["question_revision"],
        "player_color":data["player_color"],
        "transform_id":data["transform_id"],
        "transform_version":data["transform_version"],
        "moves":[{"action":"play","x":move[0],"y":move[1]}],
    }


@pytest.mark.parametrize("move,expected",[((3,3),"CORRECT"),((4,4),"INCORRECT")])
def test_p0a_safe_question_http_real_pg_settlement_and_exact_replay(map_app,move,expected):
    c=_client(map_app)
    prepared=_post_attempt(c,301)
    assert prepared.status_code==200, prepared.get_json()
    payload=_answer_from_prepared(prepared.get_json(),move)
    first=c.post("/api/adventure/map-battles/v1/answers",
                 headers=PROTOCOL,json=payload)
    assert first.status_code in (200,503),first.get_json()
    original=first.get_json()
    assert original["result"]==expected,original
    duplicate=c.post("/api/adventure/map-battles/v1/answers",
                     headers=PROTOCOL,json=payload)
    assert duplicate.get_json()["duplicate"] is True,duplicate.get_json()
    assert duplicate.get_json()["result"]==expected
    with map_app.get_db() as conn:
        rows=conn.execute("SELECT * FROM map_battle_submissions WHERE attempt_id=?",
                          (payload["attempt_id"],)).fetchall()
        assert len(rows)==1
        assert rows[0]["settlement_state"]=="SETTLED"
        assert rows[0]["judge_result"]==expected
        assert conn.execute("SELECT coins FROM user_stats WHERE user_id=9114").fetchone()[0]==50
