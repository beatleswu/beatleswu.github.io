"""G076 G MASTER localhost-only Flask/SQLite real HTTP browser fixture.

Never use any production Oracle credentials, data, cookies or public network.
The fixture alone enables the G076 gates for its own process, on 127.0.0.1.
"""
import ast
import hashlib
import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from flask import Flask, jsonify, request, session, send_file

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from map_battle_persistence import ensure_map_battle_tables, create_map_battle
from map_battle_runtime import (
    MapBattleRuntimeError, ensure_submission_lifecycle_schema,
    issue_attempt_for_context, issue_submission_nonce_for_attempt
)
from g076_step_ledger import ensure_isolated_step_schema
from g076_question_privacy import board_only_sgf

PORT=5067
DB_PATH=Path(r"D:\g075-artifacts\g076-r2-browser-isolated.sqlite")
if DB_PATH.exists():
    DB_PATH.unlink()
os.environ["G076_STEP_RUNTIME_ENABLED"]="true"
os.environ["G076_ANSWER_PRIVACY_ENFORCED"]="true"
os.environ["E10_MAP_BATTLE_V1_MODE"]="global"
SECRET="g076-browser-fixture-only-not-prod"
NOW="2026-10-23T10:00:00+00:00"
Q={"id":7001, "source":"g076/localhost-only.sgf",
   "content":"(;SZ[9]PL[B]AB[fh]LB[hh:1];B[aa];W[bb];B[cc])",
   "monster_atk":6}
revision=hashlib.sha256(Q["content"].encode("utf-8")).hexdigest()
CORPUS=Path(r"D:\g075-artifacts\questions.production-readonly.b7b4eedf.json")
assert hashlib.sha256(CORPUS.read_bytes()).hexdigest()==(
    "b7b4eedf72a87ab8fbc82ff51b658cd4dc0f08cb33426aee013e97814edae232"
)
import json
REAL_Q=next(q for q in json.loads(CORPUS.read_text(encoding="utf-8"))
            if q.get("id")==69853)
QUESTION_BY_ID={7001:Q,69853:REAL_Q}


def connect():
    conn=sqlite3.connect(str(DB_PATH),timeout=8)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

with connect() as conn:
    conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO users(id) VALUES(101)")
    ensure_map_battle_tables(conn)
    ensure_submission_lifecycle_schema(conn)
    ensure_isolated_step_schema(conn)
    ISSUED_NONCES={}
    for q,board,side,aid,bid in (
        (Q,9,"B","a1","b1"),
        (REAL_Q,19,"B","a69853good","b69853good"),
        (REAL_Q,19,"B","a69853bad","b69853bad"),
    ):
        create_map_battle(
            conn,battle_id=bid,user_id=101,zone_key="legacy::local",
            player_hp=20,player_hp_max=20,monster_hp=30,
            monster_hp_max=30,now=NOW)
        issue_attempt_for_context(
            conn,user_id=101,battle_id=bid,question=q,
            initial_position_identity=hashlib.sha256(
                q["content"].encode("utf-8")).hexdigest(),
            board_size=board,player_color=side,
            transform_version="map-battle-v1",transform_id="identity",
            attempt_id=aid,issued_at=NOW,
            expires_at="2026-10-24T10:00:00+00:00")
        issued=issue_submission_nonce_for_attempt(
            conn,user_id=101,attempt_id=aid,now=NOW,
            mode_environ={"E10_MAP_BATTLE_V1_MODE":"global"})
        ISSUED_NONCES[aid]=issued["submission_nonce"]

app=Flask(__name__)
app.secret_key=SECRET

@contextmanager
def tx():
    conn=connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

parser=ast.parse((ROOT/"app.py").read_text(encoding="utf-8"))
ns={
    "app":app, "os":os, "request":request, "session":session,"jsonify":jsonify,
    "_activation_transaction":tx,
    "_map_battle_require_enabled":lambda uid,db:{},
    "_map_battle_question_by_id":lambda qid:QUESTION_BY_ID.get(qid),
    "_admit_map_battle_answer_entitlement":lambda db,uid,q:None,
    "_get_authoritative_combat_stats":None,
    "_map_battle_monster_profile_resolver":None,
    "MAP_BATTLE_RUNTIME_PROVIDER_REGISTRY":None,
    "build_b022_active_spirit_projection":None,
    "_run_map_battle_progression":lambda uid,r:({"status":"applied"},200),
    "_map_battle_error_response":lambda err:(jsonify({"error":err.code}),err.status),
    "MapBattleRuntimeError":MapBattleRuntimeError,
}
def original(name):
    node=next(x for x in parser.body if isinstance(x,ast.FunctionDef) and x.name==name)
    node.decorator_list=[]
    exec(compile(ast.Module(body=[node],type_ignores=[]),"g076-real-app-route","exec"),ns)
    return ns[name]
original("_g076_step_enabled")
app.add_url_rule("/api/adventure/map-battles/v2/steps/start","start",
                 original("g076_map_battle_step_start"),methods=["POST"])
app.add_url_rule("/api/adventure/map-battles/v2/steps","step",
                 original("g076_map_battle_step_submit"),methods=["POST"])

@app.route("/")
def page():
    session["user_id"]=101
    return send_file(ROOT/"tests/e2e/g076_live_browser.html")

@app.route("/test/boot")
def boot():
    if session.get("user_id")!=101:return jsonify(error="unauthorized"),401
    return jsonify(attempt_id="a1",submission_nonce=ISSUED_NONCES["a1"],
                   real_good={"attempt_id":"a69853good",
                              "submission_nonce":ISSUED_NONCES["a69853good"]},
                   real_bad={"attempt_id":"a69853bad",
                             "submission_nonce":ISSUED_NONCES["a69853bad"]})

@app.route("/api/question/<int:qid>")
def question(qid):
    if session.get("user_id")!=101:return jsonify(error="unauthorized"),401
    question=QUESTION_BY_ID.get(qid)
    if question is None:return jsonify(error="not_found"),404
    return jsonify(content=board_only_sgf(question["content"]),
                   accepted_moves=[],katago_best_move="",board_only=True,
                   id=qid)

@app.route("/test/hp")
def hp():
    if session.get("user_id")!=101:return jsonify(error="unauthorized"),401
    battle=request.args.get("battle") or "b1"
    if battle not in ("b1","b69853good","b69853bad"):
        return jsonify(error="invalid_battle"),400
    with connect() as conn:
        row=conn.execute("SELECT player_hp,monster_hp FROM map_battles WHERE id=?",
                         (battle,)).fetchone()
    return jsonify(player_hp=row[0],monster_hp=row[1])

@app.route("/js/game/g076_authoritative_step_client.js")
def js():
    return send_file(ROOT/"js/game/g076_authoritative_step_client.js",
                     mimetype="text/javascript")

@app.route("/js/game/board_renderer.js")
def renderer():
    return send_file(ROOT/"js/game/board_renderer.js",mimetype="text/javascript")

@app.route("/wgo/wgo.min.js")
def wgo():
    return send_file(ROOT/"wgo/wgo.min.js",mimetype="text/javascript")

@app.route("/healthz")
def health():
    return jsonify(ok=True,sandbox="g076-r2",local_only=True)

if __name__=="__main__":
    print("G076_LOCAL_HTTP_READY",PORT,flush=True)
    app.run(host="127.0.0.1",port=PORT,debug=False,use_reloader=False,threaded=True)
