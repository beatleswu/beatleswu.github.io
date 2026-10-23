"""Synthetic local integration providers, NOT production settlement adapters."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3

from flask import Flask, request, session, send_file
from g076_nonmap_steps import create_blueprint, resolve_daily, resolve_practice, NonMapRejected
from map_battle_runtime import question_revision_for
from practice_answer_authority import issue_practice_attempt
from daily_challenge_authority import issue_daily_attempt
from srs_scheduling_core import apply_srs_scheduling, ProgressCreditPolicy

ROOT = Path(__file__).resolve().parents[1]
SECRET = 'synthetic-local-only-g076-nonmap-fixture-key'
DATE = '2026-10-23'


def make_fixture(path):
    state = {'question': {'id': 701, 'content': '(;GM[1]SZ[5]PL[B]AB[ee];B[aa];W[bb];B[cc])'},
             'identity': 'fixture-uuid-701', 'denied': False, 'fail_settle': False,
             'unsafe_settle': False, 'fail_commit': False, 'now': 101,
             'environ': {'G076_NONMAP_STEPS_ENABLED': 'true', 'G076_ANSWER_PRIVACY_ENFORCED': 'true'}}

    def connect():
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.create_function('GREATEST', 2, max)
        conn.execute('PRAGMA foreign_keys=ON')
        return conn

    with connect() as conn:
        conn.executescript((ROOT/'migrations/g076_nonmap_steps_PROPOSED.sql').read_text())
        conn.executescript('''
            CREATE TABLE fixture_receipts (id TEXT PRIMARY KEY,user_id INTEGER,flow TEXT,grade INTEGER);
            CREATE TABLE fixture_daily (user_id INTEGER,date TEXT,correct INTEGER,xp INTEGER,
                UNIQUE(user_id,date));
            CREATE TABLE srs_cards (user_id INTEGER,question_id INTEGER,ease_factor REAL,
                interval INTEGER,repetitions INTEGER,due_date TEXT,last_grade INTEGER,
                updated_at TEXT,progress_credited INTEGER,PRIMARY KEY(user_id,question_id));
        ''')

    @contextmanager
    def transaction():
        conn = connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            if state['fail_commit']:
                raise RuntimeError('synthetic failure before commit')
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def context():
        return {'board_size': 5, 'player_color': 'B', 'transform_id': 'identity',
                'transform_version': 'fixture-v1',
                'question_revision': question_revision_for(state['question'])}

    def token(flow, uid=101):
        if flow == 'practice':
            return issue_practice_attempt(SECRET, user_id=uid, question=state['question'],
                source_record_uuid=state['identity'], question_context=context(), now=100)
        return issue_daily_attempt(SECRET, user_id=uid, challenge_date=DATE,
                question=state['question'], question_context=context(), now=100)

    def admit(uid, question):
        if state['denied']:
            raise NonMapRejected('fixture_rights_revoked', 403)

    def resolve(conn, uid, flow, attempt_token):
        if flow == 'practice':
            return resolve_practice(SECRET, attempt_token, uid=uid,
                question_loader=lambda qid: state['question'] if qid == 701 else None,
                identity=lambda qid: state['identity'], admit=admit, now=state['now'])
        return resolve_daily(SECRET, attempt_token, uid=uid, today=DATE,
            question=state['question'], admit=admit, now=state['now'])

    def settle(conn, ctx, canonical, outcome, event_id):
        # Local test writer, using the real canonical SRS writer for Practice.
        # Daily XP below is deliberately a synthetic ledger, not dc_submit.
        conn.execute('INSERT INTO fixture_receipts VALUES (?,?,?,?)',
                     (event_id, ctx.uid, ctx.flow, outcome.authoritative_grade))
        response = {'submission_id': event_id}
        if ctx.flow == 'practice':
            srs = apply_srs_scheduling(conn, user_id=ctx.uid, question_id=ctx.question['id'],
                grade=outcome.authoritative_grade, now=DATE,
                progress_credit_policy=ProgressCreditPolicy.NEVER)
            response['srs'] = {key: getattr(srs, key) for key in
                               ('ease_factor', 'interval', 'repetitions', 'due_date')}
        else:
            xp = 75 if outcome.result == 'CORRECT' else 0
            conn.execute('INSERT INTO fixture_daily VALUES (?,?,?,?)',
                         (ctx.uid, DATE, int(outcome.result == 'CORRECT'), xp))
            response['xp_awarded'] = xp
        if state['fail_settle']:
            raise RuntimeError('synthetic failure AFTER write')
        if state['unsafe_settle']:
            response['content'] = ctx.question['content']
        return response

    app = Flask('g076_nonmap_isolated')
    app.secret_key = SECRET
    # Test-only session issuance, NEVER imported or registered by app.py.
    @app.post('/fixture/login')
    def login():
        session['user_id'] = request.get_json()['uid']
        return {'ok': True}

    @app.get('/fixture/token/<flow>')
    def get_token(flow):
        return {'attempt_token': token(flow, session['user_id'])}

    @app.get('/client.js')
    def client_script():
        return send_file(ROOT/'js/game/g076_nonmap_step_client.js')

    @app.get('/')
    def browser_page():
        return send_file(ROOT/'tests/e2e/g076_nonmap_browser.html')

    app.register_blueprint(create_blueprint(transaction=transaction, resolve=resolve,
        settle=settle, secret=SECRET, environ=state['environ']))
    return app, state, token, connect, transaction, resolve, settle
