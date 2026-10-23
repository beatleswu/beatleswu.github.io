"""Disposable SQLite + actual Flask routes and extracted dc_submit providers.
AST loading avoids importing app (and its startup, secrets, databases/threads).
No mocks substitute the D5B/XP/badge/appearance business effects.
"""
import ast
import bisect
from contextlib import contextmanager
import datetime
from pathlib import Path
import sqlite3
import re
from types import SimpleNamespace
from g076_question_privacy import board_only_sgf
from flask import Flask, jsonify, request, session, send_from_directory
import daily_challenge_authority as authority
import daily_challenge_d5b as d5b
from g076_daily_step_integration import DailyServices, create_daily_blueprint, select_daily_question
from g076_nonmap_steps import NonMapRejected
from map_battle_runtime import question_revision_for, MapBattleRuntimeError
from migrations.review_log_submission_idempotency_v1 import upgrade as upgrade_review_schema
from question_idempotency import IdempotencyIdentityError

ROOT = Path(__file__).resolve().parents[1]
SECRET = 'g076-daily-disposable-fixture-not-a-secret'

def load_functions(path, names, namespace):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            node.decorator_list = []
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets):
            nodes.append(node)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)

def make_daily_fixture(path):
    state = {'day': datetime.date.today().isoformat(), 'denied': False,
        'fail_effect': False, 'fail_commit': False,
        'question': {'id': 301, 'content': '(;GM[1]SZ[5]PL[B]AB[ee];B[aa];W[bb];B[cc])'},
        'environ': {'G076_NONMAP_STEPS_ENABLED': 'true',
            'G076_ANSWER_PRIVACY_ENFORCED': 'true', 'G076_DAILY_STEPS_ENABLED': 'true'}}
    ns = {'sqlite3': sqlite3, 'upgrade_review_schema': upgrade_review_schema}
    load_functions(ROOT/'tests/test_daily_challenge_b020_d5b_replay.py', {'_daily_db'}, ns)
    source = ns['_daily_db']()
    dest = sqlite3.connect(path)
    source.backup(dest)
    source.close()
    dest.executescript((ROOT/'migrations/g076_nonmap_steps_PROPOSED.sql').read_text())
    dest.execute('CREATE TABLE users(id INTEGER PRIMARY KEY)')
    dest.execute('CREATE TABLE daily_challenge(challenge_date TEXT PRIMARY KEY, question_id INTEGER NOT NULL, set_by TEXT, note TEXT)')
    dest.executemany('INSERT INTO users VALUES (?)', [(7,), (8,), (9,), (10,)])
    dest.commit(); dest.close()

    def connect():
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def transaction():
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

    def question_context(q):
        preview=board_only_sgf(q['content'])
        return {'board_size': int(re.search(r'SZ\[(\d+)\]',preview)[1]),
                'player_color': re.search(r'PL\[([BW])\]',preview)[1],
                'question_revision': question_revision_for(q)}

    app = Flask('g076_daily_disposable', static_folder=None)
    app.secret_key = SECRET
    app.config['TESTING'] = True
    ns = {'datetime': datetime, 'bisect': bisect, 'session': session,
        'os': SimpleNamespace(environ=state['environ']),
        'request': request, 'jsonify': jsonify, 'app': app, 'get_db': transaction,
        'MapBattleRuntimeError': MapBattleRuntimeError,
        'IdempotencyIdentityError': IdempotencyIdentityError,
        '_map_battle_question_context': lambda q: {**question_context(q),
            'initial_position_identity': authority.question_content_sha256(q)},
        '_load_questions': lambda: [state['question']],
        'get_or_create_daily_challenge': lambda today: {'question_id': 301, 'note': None},
        '_question_content_sha256': authority.question_content_sha256,
        'issue_daily_attempt': authority.issue_daily_attempt,
        '_g076_exposure_content': board_only_sgf,
        '_english_only': lambda text: text, '_i18n_topic_en': lambda text: text,
        '_i18n_level_en': lambda text: text, 'is_premium': lambda uid: True,
        '_observe_xp_shadow': lambda **kwargs: None,
        '_i18n_badge_en': lambda bid: None, '_APPEAR_MAP': {},
        'BADGE_DEFS': [{'id': bid, 'name': bid} for bid in ('daily_first', 'daily_ace', 'daily_7')]}
    ns.update({name: getattr(authority, name) for name in ('verify_daily_attempt',
        'canonicalize_daily_answer', 'judge_daily_answer', 'DailyAttemptError')})
    ns.update({name: getattr(d5b, name) for name in d5b.__all__})
    load_functions(ROOT/'app.py', {'dc_submit', 'dc_today', 'dc_history', 'dc_history_detail', 'xp_to_lv', 'lv_progress',
        'LV_THRESHOLDS', 'MAX_LV', 'DAILY_CHALLENGE_XP_REWARD',
        'check_and_award_daily', 'get_daily_submit_streak', 'give_daily_appearance'}, ns)
    original_badges = ns['check_and_award_daily']
    def badges(*args):
        result = original_badges(*args)
        if state['fail_effect']:
            raise RuntimeError('fixture failure after actual badge write')
        return result
    services = DailyServices(**{key: ns[key] for key in DailyServices.__dataclass_fields__})
    # Fail injection preserves the real writes before triggering rollback.
    from dataclasses import replace
    services = replace(services, check_and_award_daily=badges)
    def admit(uid, q):
        if state['denied']:
            raise NonMapRejected('daily_rights_revoked', 403)
    app.register_blueprint(create_daily_blueprint(transaction=transaction,
        today_question=lambda conn, day: select_daily_question(conn, day, load_questions=lambda: [state['question']]), admit=admit,
        services=services, secret=SECRET, environ=state['environ'],
        today=lambda: state['day'], question_context=question_context))
    from g076_daily_capability import create_capability_blueprint
    app.register_blueprint(create_capability_blueprint(state['environ']))

    @app.before_request
    def fixture_auth():
        if request.path.startswith('/api/daily-challenge/') and not session.get('user_id'):
            return {'error': 'authentication_required'}, 401

    app.add_url_rule('/api/daily-challenge/submit', 'legacy_submit', ns['dc_submit'], methods=['POST'])
    app.add_url_rule('/api/daily-challenge/today', 'legacy_today', ns['dc_today'])
    app.add_url_rule('/api/daily-challenge/history', 'legacy_history', ns['dc_history'])
    app.add_url_rule('/api/daily-challenge/history/<date_str>', 'legacy_history_detail', ns['dc_history_detail'])
    @app.post('/fixture/login')
    def login():
        session['user_id'] = request.get_json()['uid']
        return {'ok': True}
    @app.get('/api/auth/me')
    def me():
        return {'logged_in': bool(session.get('user_id')), 'user_id': session.get('user_id'), 'username': 'Disposable', 'is_premium': True}
    @app.get('/api/player/appearance')
    def appearance():
        return {'equipped': {}, 'wardrobe': []}
    @app.get('/fixture/counts')
    def counts():
        with connect() as conn:
            return {t: conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]
                for t in ('daily_challenge_log', 'review_log', 'badges_earned')}
    @app.get('/')
    def page():
        return send_from_directory(ROOT, 'daily_challenge.html')
    @app.get('/<path:path>')
    def assets(path):
        if path in ('daily_challenge.html', 'daily_challenge_legacy.html'):
            if not session.get('user_id'):
                return '', 401
            return send_from_directory(ROOT, path)
        if path.startswith(('js/', 'wgo/', 'css/', 'fonts/', 'assets/')) or path in (
                'i18n.js', 'sound.js', 'mobile-nav.js', 'site-nav.js', 'pwa.js', 'sgf_report_widget.js'):
            return send_from_directory(ROOT, path)
        return '', 404
    return app, state, connect, transaction, services
