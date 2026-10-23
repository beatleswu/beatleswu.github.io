"""Exercise actual dormant G076 Flask route functions through real test_client.

Tests are bound to SQLite Map Battle canonical settlement, with an isolated
authorization session and no live player access.
"""
import ast
import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from flask import Flask, jsonify, request, session

from map_battle_runtime import MapBattleRuntimeError
from test_g076_step_ledger_sqlite import live_fixture, Q, SECRET

ROOT=Path(__file__).resolve().parents[1]
AST=ast.parse((ROOT/"app.py").read_text(encoding="utf-8"))


def app_body(name, namespace):
    node=next(n for n in AST.body if isinstance(n,ast.FunctionDef)
              and n.name==name)
    node.decorator_list=[]
    exec(compile(ast.Module(body=[node],type_ignores=[]),
                 "G076-real-app-source","exec"),namespace)
    return namespace[name]


@pytest.fixture
def api(live_fixture, monkeypatch):
    conn,nonce=live_fixture
    monkeypatch.delenv("G076_STEP_RUNTIME_ENABLED",raising=False)
    monkeypatch.delenv("G076_ANSWER_PRIVACY_ENFORCED",raising=False)
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE","global")
    app=Flask("g076_real_api_fixture")
    app.secret_key=SECRET

    @contextmanager
    def tx():
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    counts={"progress":0,"commit":0}
    def progression(uid,settled):
        counts["progress"]+=1
        assert uid==101
        assert settled["accepted"]
        return {"status":"applied"},200

    names={
        "app":app, "os":os, "request":request, "session":session,
        "jsonify":jsonify,
        "_activation_transaction":tx,
        "_map_battle_require_enabled":lambda uid,db:{},
        "_map_battle_question_by_id":lambda qid:Q if qid==7001 else None,
        "_admit_map_battle_answer_entitlement":lambda db,uid,q:None,
        "_get_authoritative_combat_stats":None,
        "_map_battle_monster_profile_resolver":None,
        "MAP_BATTLE_RUNTIME_PROVIDER_REGISTRY":None,
        "build_b022_active_spirit_projection":None,
        "_run_map_battle_progression":progression,
        "_map_battle_error_response":lambda e:(jsonify({"error":e.code}),e.status),
        "MapBattleRuntimeError":MapBattleRuntimeError,
    }
    gate=app_body("_g076_step_enabled",names)
    names["_g076_step_enabled"]=gate
    start=app_body("g076_map_battle_step_start",names)
    submit=app_body("g076_map_battle_step_submit",names)
    app.add_url_rule("/api/adventure/map-battles/v2/steps/start","start",start,methods=["POST"])
    app.add_url_rule("/api/adventure/map-battles/v2/steps","answer",submit,methods=["POST"])

    @app.before_request
    def isolated_session():
        if "user_id" not in session:
            return jsonify({"error":"authentication_required"}),401

    client=app.test_client()
    with client.session_transaction() as s:
        s["user_id"]=101
    return client,nonce,conn,counts,monkeypatch


def enable(api):
    api[4].setenv("G076_STEP_RUNTIME_ENABLED","true")
    api[4].setenv("G076_ANSWER_PRIVACY_ENFORCED","true")


def start(api):
    client,nonce,*_=api
    return client.post("/api/adventure/map-battles/v2/steps/start",
                       json={"attempt_id":"a1","submission_nonce":nonce})


def answer(api,index,step_nonce,coords,extras=None):
    client,nonce,*_=api
    body={"attempt_id":"a1","submission_nonce":nonce,
          "step_index":index,"step_nonce":step_nonce,
          "move":{"x":coords[0],"y":coords[1]}}
    body.update(extras or {})
    return client.post("/api/adventure/map-battles/v2/steps",json=body)


def test_both_flags_required_and_zero_database_writes(api):
    client,nonce,conn,*_=api
    assert start(api).status_code==503
    api[4].setenv("G076_STEP_RUNTIME_ENABLED","true")
    assert start(api).status_code==503
    api[4].setenv("G076_ANSWER_PRIVACY_ENFORCED","true")
    assert start(api).status_code==200
    assert conn.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0]==0


def test_full_authenticated_http_two_step_game_and_replay(api):
    enable(api)
    client,nonce,conn,counts,*_=api
    r=start(api)
    assert r.status_code==200
    first=answer(api,0,r.get_json()["step_nonce"],(0,0))
    assert first.status_code==200
    assert first.get_json()["status"]=="CONTINUE"
    assert first.get_json()["opponent_reply"]==[1,1]
    assert counts["progress"]==0
    second=answer(api,1,first.get_json()["next_step_nonce"],(2,2))
    assert second.status_code==200
    assert second.get_json()["status"]=="CORRECT"
    assert second.get_json()["battle_settlement"]["accepted"] is True
    assert counts["progress"]==1
    hp=conn.execute("SELECT monster_hp FROM map_battles WHERE id='b1'").fetchone()[0]
    dup=answer(api,1,first.get_json()["next_step_nonce"],(2,2))
    assert dup.status_code==200 and dup.get_json()["duplicate"] is True
    assert conn.execute("SELECT monster_hp FROM map_battles WHERE id='b1'").fetchone()[0]==hp
    assert conn.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0]==1


def test_wrong_single_step_authoritative_settlement_http(api):
    enable(api)
    started=start(api).get_json()
    wrong=answer(api,0,started["step_nonce"],(7,7))
    assert wrong.status_code==200
    assert wrong.get_json()["status"]=="INCORRECT"
    assert wrong.get_json()["battle_settlement"]["result"]=="INCORRECT"


def test_forbidden_fields_and_wrong_nonce_denied_before_db_write(api):
    enable(api)
    client,nonce,conn,*_=api
    token=start(api).get_json()["step_nonce"]
    forbidden=answer(api,0,token,(0,0),{"grade":5})
    assert forbidden.status_code==400
    denied=answer(api,0,"forged",(0,0))
    assert denied.status_code==403
    assert conn.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0]==0
    assert conn.execute("SELECT COUNT(*) FROM g076_step_events").fetchone()[0]==0


def test_logged_out_user_blocked_before_gate_or_db(api):
    client,nonce,conn,*_=api
    with client.session_transaction() as s:
        s.pop("user_id",None)
    assert start(api).status_code==401
    assert conn.execute("SELECT COUNT(*) FROM g076_step_sessions").fetchone()[0]==0


def test_no_runtime_schema_migration_or_prod_write_in_route():
    app_src=(ROOT/"app.py").read_text(encoding="utf-8")
    snippet=app_src.split("def _g076_step_enabled():")[1].split("_MAP_BATTLE_PROGRESS_MARKER_PREFIX")[0]
    assert "CREATE TABLE" not in snippet
    assert "ensure_isolated_step_schema" not in snippet
    assert "G076_ANSWER_PRIVACY_ENFORCED" not in snippet
    assert "_activation_transaction()" in snippet
    assert "entitlement_admitter=_admit_map_battle_answer_entitlement" in snippet
