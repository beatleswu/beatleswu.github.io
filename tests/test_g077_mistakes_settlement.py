"""Disposable SQLite behavioral tests; progression is an explicit FIXTURE policy.

These prove the implemented review/SRS/correction/terminal replay subset, not
Product rewards, account/quota policy, PostgreSQL admission or playable GO.
No app import (which would bootstrap a configured database).
"""
import ast
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import datetime
import json
from pathlib import Path
import sqlite3

import pytest

from g076_nonmap_steps import Context, NonMapRejected, open_steps, submit_step
from g077_mistakes_settlement import ReviewFacts, build_settlement
from map_battle_runtime import question_revision_for
from practice_answer_authority import issue_practice_attempt, verify_practice_attempt
from srs_scheduling_core import apply_srs_scheduling, ProgressCreditPolicy, SrsAdvancePolicy

ROOT = Path(__file__).resolve().parents[1]
SECRET = 'g077-disposable-fixture-only'
TABLES = ('review_log', 'srs_cards', 'mistake_log', 'fixture_rewards',
          'g076_nonmap_sessions', 'g076_nonmap_events')


def legacy_source():
    return ast.parse((ROOT / 'app.py').read_text(encoding='utf-8-sig'))


def legacy_xp():
    """Execute the actual existing pure formula, without bootstrapping app.py."""
    names = {'XP_BY_DIFF', 'XP_FIRST_CORRECT', 'XP_MISTAKE_CORRECT', 'COMBO_MULTIPLIERS'}
    nodes = [n for n in legacy_source().body if
             (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names
                                               for t in n.targets)) or
             (isinstance(n, ast.FunctionDef) and n.name == 'calc_xp_gain')]
    env = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'app.py:pure-xp', 'exec'), env)
    return env['calc_xp_gain']


@pytest.fixture
def fx(tmp_path):
    path = tmp_path / 'fixture.sqlite'
    q = {'id': 701, 'difficulty': '10k', 'content': '(;GM[1]SZ[5]PL[B]AB[ee];B[aa])'}
    state = {'fail': None, 'policy': True, 'deny': False, 'invalid_xp': False}
    xp_formula = legacy_xp()

    def connect():
        # sqlite's context manager commits/rolls back but does not close.
        # Close explicitly on exit so Windows can remove disposable DB files.
        class ClosingConnection(sqlite3.Connection):
            # The existing adapter identifies SQLite by the driver's module.
            __module__ = 'sqlite3'

            def __exit__(self, *args):
                try:
                    return super().__exit__(*args)
                finally:
                    self.close()
        c = sqlite3.connect(path, timeout=15, factory=ClosingConnection)
        c.row_factory = sqlite3.Row
        c.create_function('GREATEST', 2, max)
        c.execute('PRAGMA foreign_keys=ON')
        return c

    with connect() as c:
        c.executescript((ROOT / 'migrations/g076_nonmap_steps_PROPOSED.sql').read_text().replace(
            "flow IN ('practice','daily')", "flow IN ('practice','daily','mistakes')"))
        c.executescript((ROOT / 'migrations/g076_mistakes_steps_PROPOSED.sql').read_text())
        c.executescript('''
        CREATE TABLE mistake_log(user_id INTEGER,question_id INTEGER,wrong_count INTEGER,
          correct_after INTEGER,first_wrong_at TEXT,last_wrong_at TEXT,last_correct_at TEXT,
          PRIMARY KEY(user_id,question_id));
        INSERT INTO mistake_log VALUES(101,701,1,0,'old','old',NULL);
        CREATE TABLE srs_cards(user_id INTEGER,question_id INTEGER,ease_factor REAL,
          interval INTEGER,repetitions INTEGER,due_date TEXT,last_grade INTEGER,
          updated_at TEXT,progress_credited INTEGER,PRIMARY KEY(user_id,question_id));
        CREATE TABLE review_log(id INTEGER PRIMARY KEY,user_id INTEGER,question_id INTEGER,
          grade INTEGER,topic TEXT,level TEXT,difficulty TEXT,reviewed_at TEXT,response_ms INTEGER,
          discipline TEXT,player_rating_snapshot REAL,question_rating_snapshot REAL,
          item_rating_version TEXT,question_version TEXT,source_context TEXT,is_scaffolding INTEGER,
          training_set_id INTEGER,submission_id TEXT,submission_payload_hash TEXT,
          UNIQUE(user_id,submission_id));
        CREATE TABLE fixture_rewards(user_id INTEGER PRIMARY KEY,xp INTEGER,credits INTEGER);
        INSERT INTO fixture_rewards VALUES(101,100,0);
        ''')

    @contextmanager
    def transaction():
        c = connect()
        try:
            c.execute('BEGIN IMMEDIATE')
            yield c
            if state['fail'] == 'commit':
                raise RuntimeError('fixture precommit failure')
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def admit(c, uid, question):
        if state['deny']:
            raise NonMapRejected('fixture_rights_revoked', 403)
        return ReviewFacts(1400, 1400, 'fixture-rating-v1', 'fixture-question-v1')

    def progression(c, ctx, verdict, event_id, srs, prior, now):
        # Explicit narrow fixture contract: no quest/pet/coin/equipment systems.
        # The Product implementation of those systems is still REQUIRED/HOLD.
        gain = xp_formula(q['difficulty'], 1, not srs.existed,
                          prior['wrong_count'] > 0)[0] if srs.progress_credit_granted else 0
        c.execute('UPDATE fixture_rewards SET xp=xp+?,credits=credits+? WHERE user_id=?',
                  (gain, int(srs.progress_credit_granted), ctx.uid))
        if state['invalid_xp']:
            return None
        return gain

    def settlement():
        return build_settlement(secret=SECRET, admit=admit,
                                progression=progression if state['policy'] else None,
                                advance_policy=SrsAdvancePolicy.ALWAYS)

    def context(scope='2026-10-23:701'):
        token = issue_practice_attempt(SECRET, user_id=101, question=q,
            source_record_uuid='fixture-uuid-701', question_context={
                'board_size': 5, 'player_color': 'B', 'transform_id': 'identity',
                'transform_version': 'fixture-v1', 'question_revision': question_revision_for(q)})
        return Context('mistakes', 101, scope, q, verify_practice_attempt(SECRET, token, user_id=101))

    def start(ctx):
        with transaction() as c:
            return open_steps(c, ctx, secret=SECRET, settle=settlement())

    def finish(ctx, cursor, move=(0, 0)):
        with transaction() as c:
            # The real HTTP adapter resolves rights before every replay too.
            admit(c, ctx.uid, ctx.question)
            return submit_step(c, ctx, {'step_index': cursor['step_index'],
                'step_nonce': cursor['step_nonce'], 'move': dict(zip(('x', 'y'), move))},
                secret=SECRET, settle=settlement())

    def snapshot():
        with connect() as c:
            return {t: [dict(r) for r in c.execute('SELECT * FROM ' + t + ' ORDER BY 1')]
                    for t in TABLES}

    return locals()


def test_first_correct_durable_replay_and_conflict(fx):
    ctx = fx['context']()
    cursor = fx['start'](ctx)
    result = fx['finish'](ctx, cursor)
    assert result['status'] == 'CORRECT'
    assert result['settlement']['xp_awarded'] == legacy_xp()('10k', 1, True, True)[0] == 37
    before = fx['snapshot']()
    assert before['srs_cards'][0]['progress_credited'] == 1
    assert before['mistake_log'][0]['correct_after'] == 1
    assert before['fixture_rewards'][0] == {'user_id': 101, 'xp': 137, 'credits': 1}
    replay = fx['finish'](ctx, cursor)
    assert replay == {**result, 'duplicate': True}
    assert fx['snapshot']() == before
    with pytest.raises(NonMapRejected, match='different_move'):
        fx['finish'](ctx, cursor, (3, 3))
    assert fx['snapshot']() == before


def test_wrong_then_first_lifetime_pass_then_repeated_correct(fx):
    ctx = fx['context']()
    wrong = fx['finish'](ctx, fx['start'](ctx), (3, 3))
    assert wrong['status'] == 'INCORRECT' and wrong['settlement']['xp_awarded'] == 0
    assert fx['snapshot']()['mistake_log'][0]['wrong_count'] == 2
    ctx2 = fx['context']('2026-10-24:701')
    correct = fx['finish'](ctx2, fx['start'](ctx2))
    assert correct['settlement']['xp_awarded'] == 32  # existing SRS: no first-answer bonus
    ctx3 = fx['context']('2026-10-25:701')
    repeated = fx['finish'](ctx3, fx['start'](ctx3))
    assert repeated['settlement']['xp_awarded'] == 0
    rows = fx['snapshot']()
    assert rows['mistake_log'][0]['correct_after'] == 2
    assert rows['fixture_rewards'][0]['credits'] == 1
    assert rows['srs_cards'][0]['repetitions'] == 2
    assert rows['srs_cards'][0]['interval'] == 6
    assert len(rows['review_log']) == len(rows['g076_nonmap_events']) == 3


@pytest.mark.parametrize('table,operation', [
    ('review_log', 'INSERT'), ('srs_cards', 'INSERT'), ('mistake_log', 'UPDATE'),
    ('fixture_rewards', 'UPDATE'), ('g076_nonmap_sessions', 'UPDATE'),
    ('g076_nonmap_events', 'INSERT'), (None, 'commit')])
def test_fault_rolls_back_entire_terminal_and_retry(fx, table, operation):
    ctx = fx['context']()
    cursor = fx['start'](ctx)
    before = fx['snapshot']()
    if table:
        with fx['connect']() as c:
            c.execute(f"CREATE TRIGGER fail BEFORE {operation} ON {table} "
                      "BEGIN SELECT RAISE(ABORT,'fixture fault'); END")
    else:
        fx['state']['fail'] = 'commit'
    with pytest.raises((sqlite3.IntegrityError, RuntimeError)):
        fx['finish'](ctx, cursor)
    assert fx['snapshot']() == before
    with fx['connect']() as c:
        c.execute('DROP TRIGGER IF EXISTS fail')
    fx['state']['fail'] = None
    assert fx['finish'](ctx, cursor)['settlement']['xp_awarded'] == 37
    assert len(fx['snapshot']()['review_log']) == 1


def test_concurrent_same_terminal_exactly_one_credit(fx):
    ctx = fx['context']()
    cursor = fx['start'](ctx)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: fx['finish'](ctx, cursor), range(2)))
    assert sorted(r['duplicate'] for r in results) == [False, True]
    rows = fx['snapshot']()
    assert len(rows['review_log']) == len(rows['g076_nonmap_events']) == 1
    assert rows['fixture_rewards'][0]['xp'] == 137


def test_concurrent_distinct_attempts_share_lifetime_credit(fx):
    contexts = [fx['context'](f'fixture-day-{i}:701') for i in range(2)]
    cursors = [fx['start'](ctx) for ctx in contexts]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda i: fx['finish'](contexts[i], cursors[i]), range(2)))
    assert sorted(r['settlement']['xp_awarded'] for r in results) == [0, 37]
    rows = fx['snapshot']()
    assert len(rows['review_log']) == 2 and rows['fixture_rewards'][0]['credits'] == 1
    assert rows['mistake_log'][0]['correct_after'] == 2


def test_existing_mistakes_services_terminal_integration(fx):
    from flask import Flask
    from g076_mistakes_product import MistakesServices, create_blueprint
    q = fx['q']
    app = Flask('g077-disposable-port-integration')
    app.secret_key = SECRET
    app.testing = True
    services = MistakesServices(
        transaction=fx['transaction'],
        question=lambda c, qid: q if qid == q['id'] else None,
        identity=lambda c, qid: 'fixture-uuid-701',
        context=lambda question: {
            'board_size': 5, 'player_color': 'B', 'transform_id': 'identity',
            'transform_version': 'fixture-v1', 'question_revision': question_revision_for(question)},
        admit=lambda c, uid, question: 'fixture-rights-v1', settle=fx['settlement']())
    app.register_blueprint(create_blueprint(secret=SECRET,
        environ={'G076_MISTAKES_STEPS_ENABLED': 'on'}, services=services))
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = 101
    token = client.post('/api/g076/mistakes/attempt', json={'question_id': 701})
    assert token.status_code == 200, token.json
    body = {'flow': 'mistakes', 'attempt_token': token.json['attempt_token']}
    start = client.post('/api/g076/mistakes/steps/start', json=body)
    assert start.status_code == 200, start.json
    body.update(step_index=start.json['step_index'], step_nonce=start.json['step_nonce'],
                move={'x': 0, 'y': 0})
    result = client.post('/api/g076/mistakes/steps', json=body)
    assert result.status_code == 200, result.json
    assert result.json['settlement']['xp_awarded'] == 37
    replay = client.post('/api/g076/mistakes/steps', json=body)
    assert replay.json == {**result.json, 'duplicate': True}
    assert len(fx['snapshot']()['review_log']) == 1


@pytest.mark.parametrize('setting', ['policy', 'invalid_xp', 'deny'])
def test_unknown_policy_invalid_reward_and_revoked_rights_fail_closed(fx, setting):
    ctx = fx['context']()
    cursor = fx['start'](ctx)
    before = fx['snapshot']()
    fx['state'][setting] = setting != 'policy'
    with pytest.raises(NonMapRejected):
        fx['finish'](ctx, cursor)
    assert fx['snapshot']() == before


@pytest.mark.parametrize('correct', [True, False])
@pytest.mark.parametrize('credited', [0, 1])
def test_correction_and_srs_parity_with_actual_legacy_source(fx, correct, credited):
    """Compare analytics with the exact app.py trusted correction AST block.

    SRS reference invokes the actual shared core on a separate fixture DB.
    This parity claim intentionally excludes unimplemented Product rewards.
    """
    with fx['connect']() as c:
        c.execute('INSERT INTO srs_cards VALUES(101,701,2.5,6,2,?,5,?,?)',
                  ((datetime.date.today() + datetime.timedelta(days=6)).isoformat(), 'old', credited))
    reference = sqlite3.connect(':memory:')
    reference.row_factory = sqlite3.Row
    reference.create_function('GREATEST', 2, max)
    with fx['connect']() as c:
        c.backup(reference)
    ctx = fx['context']()
    fx['finish'](ctx, fx['start'](ctx), (0, 0) if correct else (3, 3))
    rows = fx['snapshot']()
    now = rows['review_log'][0]['reviewed_at']
    grade = 5 if correct else 0
    outcome = apply_srs_scheduling(reference, user_id=101, question_id=701, grade=grade,
        now=now, progress_credit_policy=ProgressCreditPolicy.FIRST_PASS_ONLY,
        advance_policy=SrsAdvancePolicy.ALWAYS)
    operation = next(n for n in legacy_source().body if isinstance(n, ast.FunctionDef)
                     and n.name == '_review_learning_in_transaction')
    block = next(n for n in ast.walk(operation) if isinstance(n, ast.If) and
                 ast.unparse(n.test) == 'update_mistakes and internal and (grade < 3)')
    env = {'conn': reference, 'uid': 101, 'qid': 701, 'now': now, 'grade': grade,
           'internal': True, 'update_mistakes': True, 'mc': 0, 'should_grant_progress': outcome.progress_credit_granted,
           'mrow': reference.execute('SELECT * FROM mistake_log').fetchone()}
    exec(compile(ast.Module(body=[block], type_ignores=[]), 'app.py:correction', 'exec'), env)
    assert rows['mistake_log'] == [dict(r) for r in reference.execute('SELECT * FROM mistake_log')]
    assert rows['srs_cards'] == [dict(r) for r in reference.execute('SELECT * FROM srs_cards')]
    assert outcome.progress_credited == (1 if correct or credited else 0)
    reference.close()
