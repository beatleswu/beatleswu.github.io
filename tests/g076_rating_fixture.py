"""Disposable SQLite + AST-extracted original Rating route/math/judge bodies.

The two explicit AST edits demonstrate the REQUIRED integration seam: remove
internal commit and reuse caller connection. This is NOT exact app registration,
Postgres, real selection corpus, or real placement/claim integration evidence.
"""
import ast
from contextlib import contextmanager
import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import sqlite3
from types import SimpleNamespace
import uuid

from g076_rating_steps import RatingContext, RatingRejected, SCHEMA, create_rating_blueprint
from g076_question_privacy import board_only_sgf
from sgf_engine.parser.sgf_parser import parse_sgf
from sgf_point_transform import transform_sgf

ROOT = Path(__file__).resolve().parents[1]


class SharedConnection:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, args=()):
        # SQLite fixture serializes entire writes with BEGIN IMMEDIATE.
        return self.conn.execute(sql.replace(' FOR UPDATE', ''), args)

    def commit(self):
        raise AssertionError('settlement MUST NOT commit independently')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class RemoveCommit(ast.NodeTransformer):
    def visit_Expr(self, node):
        if (isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                and isinstance(node.value.func.value, ast.Name)
                and node.value.func.value.id == 'conn' and node.value.func.attr == 'commit'):
            return ast.copy_location(ast.Pass(), node)
        return self.generic_visit(node)


def original_functions():
    tree = ast.parse((ROOT/'app.py').read_text(encoding='utf-8-sig'))
    names = {'rt_start', 'rt_resume', 'rt_answer', '_rt_server_verify', '_rt_transform_idx',
             '_rt_probability', '_rt_estimate', '_rt_converged', '_compute_streak', '_placement_rounds',
             '_rt_write_step_result', '_rt_step_placement_unlock', '_rt_forfeit_on_connection',
             '_finalize_placement'}
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            node.decorator_list = []
            nodes.append(RemoveCommit().visit(node))
    assert len(nodes) == len(names)
    return compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), 'app.py:rating-seam-fixture', 'exec')


def make_rating_fixture(path, *, core_only=False):
    state = {'now': 1000., 'fail_settle': False, 'fail_commit': False,
             'deny': False, 'environ': {'G076_RATING_STEPS_ENABLED': 'on'}}
    pool = [dict(id=i, rating=1500, difficulty='5k', discipline='life_death',
                 content='(;SZ[5]PL[B]AB[ee];B[aa];W[bb];B[cc])', katago_best_move='') for i in (301,302)]
    state['pool'] = pool
    class ClosingConnection(sqlite3.Connection):
        def __exit__(self, *args):
            try:
                return super().__exit__(*args)
            finally:
                self.close()
    def connect():
        conn = sqlite3.connect(path, timeout=15, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        return conn
    with connect() as conn:
        for sql in SCHEMA:
            conn.execute(sql)
        conn.executescript('''
        CREATE TABLE users(id INTEGER PRIMARY KEY,elo_rating REAL,elo_updated_at TEXT,elo_provisional INTEGER);
        INSERT INTO users(id,elo_rating) VALUES(7,1500),(8,1500);
        CREATE TABLE user_stats(user_id INTEGER PRIMARY KEY,go_rank TEXT,go_rank_initialized INTEGER);
        CREATE TABLE daily_training_queue(user_id INTEGER,date TEXT);
        CREATE TABLE adventure_zone_unlocks(user_id INTEGER,zone_key TEXT,source TEXT,
          start_zone_key TEXT,unlocked_at TEXT,PRIMARY KEY(user_id,zone_key));
        CREATE TABLE rating_test_sessions(id TEXT PRIMARY KEY,user_id INTEGER,status TEXT,
          init_rating REAL,cur_rating REAL,prior_sd REAL,rating_se REAL,round INTEGER,
          current_question_id INTEGER,current_question_token TEXT,current_question_role TEXT,
          bank_version TEXT,algorithm_version TEXT,answers TEXT,trigger TEXT,started_at TEXT,
          last_activity_at TEXT,finished_at TEXT);
        CREATE TABLE rating_test_responses(session_id TEXT,user_id INTEGER,question_id INTEGER,
          round INTEGER,correct INTEGER,response_ms INTEGER,question_rating REAL,
          ability_before REAL,ability_after REAL,question_role TEXT,bank_version TEXT,
          algorithm_version TEXT,created_at TEXT,UNIQUE(session_id,round));
        CREATE TABLE mistake_log(user_id INTEGER,question_id INTEGER,wrong_count INTEGER,
          correct_after INTEGER,first_wrong_at TEXT,last_wrong_at TEXT,last_correct_at TEXT,
          PRIMARY KEY(user_id,question_id));
        ''')
    code = original_functions()
    class Services:
        @contextmanager
        def transaction(self):
            conn = connect()
            try:
                conn.execute('BEGIN IMMEDIATE')
                yield conn
                if state['fail_commit']:
                    raise RuntimeError('fixture commit failure')
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                conn.close()

        def namespace(self, conn, uid, body=None):
            ns = dict(json=json, datetime=datetime, math=math, hashlib=hashlib,
                _re_mod=re, secrets=secrets, uuid=uuid, parse_sgf=parse_sgf,
                session={'user_id':uid}, request=SimpleNamespace(get_json=lambda **kw:body or {}),
                jsonify=lambda value:value, get_db=lambda:SharedConnection(conn),
                _RT_POOL=pool, _RT_ANCHOR_VERSION=None, _RT_MAX_ROUNDS=2,
                _RT_MIN_ROUNDS=2, _RT_TARGET_SE=95., _RT_PLACEMENT_ROUNDS=2,
                _RT_ALGORITHM_VERSION='rt-anchor-mix-v1', _RT_BASE_ALGORITHM_VERSION='rt-p0-v1',
                _ensure_rt_pool=lambda:None, _rt_anchor_available=lambda:False,
                _get_recent_seen_ids=lambda uid:set(), _rt_client_exclude_ids=lambda v:set(),
                _rt_recent_seen_ids=lambda *a,**kw:set(),
                _rt_desired_question_role=lambda *a:'regular',
                _pick_question=lambda rating,round_idx,excluded,**kw:next((q for q in pool if q['id'] not in excluded),None),
                _rating_to_rank=lambda r:'fixture-rank', _strip_question=lambda q,sid,token:q | {'token':token},
                _transform_sgf=transform_sgf, _question_accepted_moves=lambda q:[],
                ADVENTURE_ZONES=[{'key':'z1'},{'key':'z2'}],
                _adventure_start_zone_for_elo=lambda elo:'z1' if elo<1500 else 'z2',
                _adventure_zone_index=lambda key:('z1','z2').index(key),
                app=SimpleNamespace(logger=SimpleNamespace(exception=lambda *a:None)))
            exec(code, ns)
            # Legacy path's after-commit callback is redirected only in this
            # disposable fixture; the candidate uses the original SQL helper.
            ns['_apply_placement_adventure_unlock'] = lambda uid,elo,source: ns['_rt_step_placement_unlock'](SharedConnection(conn),uid,elo)
            return ns

        def resolve(self, conn, sid, uid):
            row = SharedConnection(conn).execute('SELECT * FROM rating_test_sessions WHERE id=? FOR UPDATE', (sid,)).fetchone()
            if row is None:
                raise RatingRejected('not_found',404)
            if state['deny'] or row['user_id'] is not None and row['user_id'] != uid:
                raise RatingRejected('session_owner_mismatch',403)
            ns = self.namespace(conn,uid)
            summary = ns['rt_resume'](sid)
            if isinstance(summary,tuple):
                raise RatingRejected(summary[0]['error'],summary[1])
            q = next((q for q in pool if q['id']==row['current_question_id']),None)
            return RatingContext(sid,row['user_id'],row['current_question_token'],q,
                ns['_rt_transform_idx'](sid,q['id']) if q else 0,summary)

        def start(self, conn, uid, trigger):
            ns = self.namespace(conn,uid,{'trigger':trigger})
            result = ns['rt_start']()
            return self.resolve(conn,result['session_id'],uid)

        def settle(self, conn, ctx, moves, response_ms):
            ns = self.namespace(conn,ctx.user_id,dict(session_id=ctx.session_id,
                question_id=ctx.question['id'],question_token=ctx.question_token,
                moves=moves,response_ms=response_ms))
            result = ns['rt_answer']()
            if isinstance(result,tuple):
                raise RatingRejected(result[0]['error'],result[1])
            if state['fail_settle']:
                raise RuntimeError('fixture after original effects before receipt')
            return result

        def settle_forfeit(self, conn, ctx, moves, response_ms, reason):
            ns = self.namespace(conn,ctx.user_id)
            result = ns['_rt_forfeit_on_connection'](SharedConnection(conn), ctx, moves, response_ms, reason)
            if state['fail_settle']:
                raise RuntimeError('fixture after original forfeit effects before receipt')
            return result
    services = Services()
    if core_only:
        return None,state,connect,services
    from flask import Flask, request, session, send_from_directory
    app = Flask(__name__,static_folder=None)
    app.secret_key = 'g076-rating-disposable-only'
    app.config['TESTING'] = True
    app.register_blueprint(create_rating_blueprint(services,state['environ'],clock=lambda:state['now']))

    @app.post('/fixture/login')
    def login():
        session.clear()
        uid = request.json.get('uid')
        if uid is not None:
            session['user_id'] = uid
        return {'ok':True}

    @app.get('/')
    def page():
        return send_from_directory(ROOT,'rating_test.html')

    @app.get('/<path:name>')
    def assets(name):
        if name.startswith(('wgo/','js/','assets/')) or name in ('i18n.js','site-nav.js','sound.js','sgf_report_widget.js'):
            return send_from_directory(ROOT,name)
        return {},404
    return app,state,connect,services
