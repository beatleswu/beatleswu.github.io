"""G076 board projection: exact app body exercised under isolated Flask HTTP."""
import ast
import os
import sys
import json
from pathlib import Path
import pytest
from flask import Flask, jsonify, request, session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from g076_question_privacy import board_only_sgf, privacy_enforced

EXAMPLE = ("(;SZ[19]PL[B]AB[dr][br]AW[fj]LB[dr:1][fj:N][bj:Y]"
           "C[SECRET_ANSWER_IS_FJ]GN[No solution](;B[fj]C[SECRET_BRANCH])"
           "(;B[bj];W[dd]))")

@pytest.mark.parametrize("setting,expected", [
    ({}, False), ({"G076_ANSWER_PRIVACY_ENFORCED":"false"},False),
    ({"G076_ANSWER_PRIVACY_ENFORCED":"true"},True),
    ({"G076_ANSWER_PRIVACY_ENFORCED":"ON"},True),
    ({"G076_ANSWER_PRIVACY_ENFORCED":"1"},True),
    ({"G076_ANSWER_PRIVACY_ENFORCED":"unknown"},False),
])
def test_enforcement_gate(setting,expected):
    assert privacy_enforced(setting) is expected

def test_preview_strips_all_solution_branches():
    board=board_only_sgf(EXAMPLE)
    assert board=="(;SZ[19]PL[B]AB[dr]AB[br]AW[fj]LB[dr:1]LB[fj:N]LB[bj:Y])"
    assert not any(secret in board for secret in ("SECRET_ANSWER","SECRET_BRANCH",";B[fj]","GN["))

@pytest.mark.parametrize("source", [
    "", "(;SZ[19]LB[zz:X]", "(;SZ[19]LB[aa:A](;B[bb])",
    "(;B[aa];W[bb])", "(;SZ[9]B[bc];W[cd])", "(;SZ[9]W[bc])",
    "(;SZ[26]AB[aa])", "(;SZ[19]SZ[9]AB[aa])",
    "(;SZ[19]PL[X]AB[aa])", "(;SZ[9])(;SZ[9])",
])
def test_invalid_ambiguous_or_multi_game_sgf_rejected(source):
    with pytest.raises(ValueError):
        board_only_sgf(source)

def test_escaped_semicolon_in_comment_cannot_escape_sanitizer():
    source=r"(;SZ[9]PL[W]AB[aa]C[answer \;B\[zz\] \] and ;W\[yy\]]LB[bc:Y](;W[bb]C[SUPER_SECRET]))"
    preview=board_only_sgf(source)
    assert preview=="(;SZ[9]PL[W]AB[aa]LB[bc:Y])"

def app_handler():
    parsed=ast.parse((ROOT/"app.py").read_text(encoding="utf-8"))
    node=next(n for n in parsed.body if isinstance(n,ast.FunctionDef) and n.name=="get_question")
    assert [ast.unparse(d) for d in node.decorator_list]==[
        "app.route('/api/question/<int:qid>')","login_required"]
    node.decorator_list=[]
    question={
        "id":69853,"content":EXAMPLE,"comment":"ANSWER: fj",
        "katago_best_move":"fj","score_gap":999,"enabled":True}
    funcs={
        "jsonify":jsonify,"request":request,"os":os,
        "_load_questions":lambda:[question],
        "is_premium":lambda:True,
        "question_is_free":lambda q:False,
        "_question_accepted_moves":lambda q:[{"x":5,"y":9}],
        "_question_display_name":lambda q:"display",
        "_question_content_sha256":lambda q:"fake-content-hash",
        "_question_monster_avatar":lambda q:"",
        "_client_question_revision":lambda q:"revision",
        "_session_question_fingerprint":lambda q:"fingerprint"}
    exec(compile(ast.Module(body=[node],type_ignores=[]),"g076-actual-route","exec"),funcs)
    return funcs["get_question"],funcs

@pytest.fixture
def route_fixture(monkeypatch):
    monkeypatch.delenv("G076_ANSWER_PRIVACY_ENFORCED",raising=False)
    func,funcs=app_handler()
    app=Flask("g076_isolated_http")
    app.secret_key="isolated-not-production"
    @app.before_request
    def require_login_in_fixture():
        if "user_id" not in session:
            return jsonify({"error":"authentication_required"}),401
    app.add_url_rule("/api/question/<int:qid>","get_question",func)
    return app,funcs

def login(client):
    with client.session_transaction() as s:
        s["user_id"]=47

def test_isolated_http_auth_without_session(route_fixture):
    app,_=route_fixture
    assert app.test_client().get("/api/question/69853?view=board").status_code==401

def test_http_authorized_preview_is_solution_free(route_fixture):
    app,_=route_fixture
    client=app.test_client()
    login(client)
    response=client.get("/api/question/69853?view=board")
    assert response.status_code==200
    data=response.get_json()
    assert data["board_only"] is True
    assert data["content"]==board_only_sgf(EXAMPLE)
    assert data["comment"]==""
    assert data["accepted_moves"]==[]
    assert data["katago_best_move"]==""
    assert data["score_gap"] is None
    assert response.headers["Cache-Control"]=="no-store"

def test_http_locked_account_sees_no_board(route_fixture):
    app,funcs=route_fixture
    funcs["is_premium"]=lambda:False
    client=app.test_client()
    login(client)
    data=client.get("/api/question/69853?view=board").get_json()
    assert data["locked"] is True
    assert data["content"]==""
    assert data["accepted_moves"]==[]

def test_http_enforcement_flag_cannot_be_bypassed_by_old_url(route_fixture,monkeypatch):
    app,_=route_fixture
    monkeypatch.setenv("G076_ANSWER_PRIVACY_ENFORCED","true")
    client=app.test_client()
    login(client)
    data=client.get("/api/question/69853").get_json()
    assert data["board_only"] is True
    assert data["content"]==board_only_sgf(EXAMPLE)
    assert data["accepted_moves"]==[]

def test_ambiguous_root_http_fails_closed(route_fixture):
    app,funcs=route_fixture
    funcs["_load_questions"]=lambda:[{"id":69853,"content":"(;SZ[9]B[bc];W[dd])"}]
    client=app.test_client()
    login(client)
    resp=client.get("/api/question/69853?view=board")
    assert resp.status_code==422
    assert resp.get_json()["code"]=="question_preview_unavailable"

def test_exact_question_69853_fixture_has_all_marker_labels():
    fixture=json.loads((ROOT/"tests/fixtures/g064_sgf_annotations.json").read_text(encoding="utf-8"))
    q=next(x for x in fixture if x["name"]=="map-battle-69853-root")
    preview=board_only_sgf(q["sgf"])
    for label in ("LB[dr:1]","[fj:N]","[bj:Y]"):
        assert label in preview
    assert ";B[" not in preview and ";W[" not in preview

def test_global_enforcement_must_wait_for_client_migration():
    source=(ROOT/"index.html").read_text(encoding="utf-8")
    assert "currentNode.children.find(c=>c.move" in source
    assert "currentProblem.tree=makeAnswerRoot" in source
    assert privacy_enforced({}) is False


@pytest.mark.parametrize("source,expected", [
    ("(;AB[aa](;W[bb]C[SECRET]))", "(;SZ[19]AB[aa]PL[W])"),
    ("(;SZ[9]AB[aa](;B[bb]C[SECRET]))", "(;SZ[9]AB[aa]PL[B])"),
    ("(;SZ[19]LB[aa:1])", "(;SZ[19]LB[aa:1]PL[B])"),
])
def test_implicit_board_size_and_side_to_move_without_solution_leak(source,expected):
    assert board_only_sgf(source)==expected
    assert "SECRET" not in board_only_sgf(source)


@pytest.mark.parametrize("size", [2, 5, 7, 9, 13, 15, 19, 21, 25])
def test_preview_respects_real_browser_board_size_contract(size):
    source=f"(;SZ[{size}]PL[B]AB[aa];B[bb])"
    assert board_only_sgf(source)==f"(;SZ[{size}]PL[B]AB[aa])"
