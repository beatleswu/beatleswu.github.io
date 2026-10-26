"""Disposable file-backed SQLite + Flask; no app.py, Oracle or runtime DB."""
import concurrent.futures
import json
from pathlib import Path
import sqlite3
import sys

import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from g076_grimoire_adapter import (
    GrimoireSteps, GrimoireRejected, ISOLATED_SCHEMA, create_blueprint, settle_node_only,
)


@pytest.fixture
def fx(tmp_path):
    path = tmp_path / 'grimoire.sqlite'
    state = {'now': 1792713600, 'deny': False, 'identity': 'synthetic-701', 'fail': None,
             'q': {'id': 701, 'content': '(;SZ[5]PL[B]AB[ee];B[aa];W[bb];B[cc])'}}

    def connect():
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        return conn

    with connect() as conn:
        conn.executescript(ISOLATED_SCHEMA + '''
            CREATE TABLE node_mastery (user_id INTEGER,question_id INTEGER,purity REAL,
                attempt_count INTEGER,last_5_history TEXT,last_correct_at TEXT,
                is_contaminated INTEGER,PRIMARY KEY(user_id,question_id));
            CREATE TABLE daily_training_cache (user_id INTEGER,date TEXT,question_ids TEXT,
                completed_ids TEXT,created_at TEXT);
            CREATE TABLE parent (id INTEGER PRIMARY KEY);
            CREATE TABLE deferred_failure (id INTEGER REFERENCES parent(id)
                DEFERRABLE INITIALLY DEFERRED);
        ''')

    def settle(conn, **kwargs):
        value = settle_node_only(conn, **kwargs)
        if state['fail'] == 'after_mastery':
            raise RuntimeError('synthetic exception AFTER mastery write')
        if state['fail'] == 'unsafe_receipt':
            return {**value, 'solution': state['q']['content']}
        if state['fail'] == 'commit':
            conn.execute('INSERT INTO deferred_failure VALUES (99)')
        return value

    service = GrimoireSteps(connect=connect, load=lambda c, qid: state['q'],
        identity=lambda c, qid: state['identity'], admit=lambda c, uid, q: not state['deny'],
        secret=b'isolated-grimoire-test-key-32-bytes', settle=settle,
        clock=lambda: state['now'], environ={'G076_ANSWER_PRIVACY_ENFORCED': 'on',
                                          'G076_GRIMOIRE_STEPS_ENABLED': 'on'})
    app = Flask(__name__)
    app.secret_key = 'isolated-session-secret'
    app.register_blueprint(create_blueprint(service))
    return service, app, state, connect


def client(fx, uid=101):
    c = fx[1].test_client()
    with c.session_transaction() as session:
        if uid is not None:
            session['user_id'] = uid
    return c


def issue(fx, scope='server-admission-1', uid=101):
    return fx[0].issue(uid, question_id=701, scope=scope)


def send(fx, token, cursor=None, xy=(0, 0), extras=None, uid=101):
    body = {'attempt_token': token}
    if cursor is not None:
        body.update(step_index=cursor['step_index'], step_nonce=cursor.get('step_nonce', ''),
                    move={'x': xy[0], 'y': xy[1]})
    body.update(extras or {})
    return client(fx, uid).post('/api/g076/grimoire/steps', json=body)


def rows(fx, table):
    conn = fx[3]()
    try:
        return [dict(r) for r in conn.execute('SELECT * FROM ' + table)]
    finally:
        conn.close()


def test_play_resume_and_exactly_once_mastery(fx):
    token = issue(fx)
    cursor = send(fx, token).json
    assert cursor['content'] == '(;SZ[5]PL[B]AB[ee])'
    first = send(fx, token, cursor).json
    assert first['status'] == 'CONTINUE' and first['opponent_reply'] == [1, 1]
    assert rows(fx, 'node_mastery') == []
    # Never scan HMAC/nonce hex for arbitrary coordinate substrings: random
    # entropy can legitimately contain 'cc'. Inspect only answer-bearing fields.
    assert not any(k in first for k in ('answer_tree', 'accepted_moves', 'solution', 'next_move'))
    assert ';B[cc]' not in str(first.get('content', ''))
    assert [2, 2] not in first.get('played', [])
    assert send(fx, token).json['step_nonce'] == first['step_nonce']
    final = send(fx, token, first, (2, 2))
    assert final.status_code == 200 and final.json['status'] == 'CORRECT'
    assert final.headers['Cache-Control'] == 'private, no-store'
    assert send(fx, token, first, (2, 2)).json == {**final.json, 'duplicate': True}
    assert issue(fx) == token
    resumed = send(fx, token).json
    assert resumed['status'] == 'CORRECT' and 'step_nonce' not in resumed
    assert len(resumed['previous_steps']) == 2
    mastery = rows(fx, 'node_mastery')[0]
    assert mastery['attempt_count'] == 1 and mastery['purity'] == .3
    assert json.loads(mastery['last_5_history']) == [True]


def test_wrong_move_is_terminal_no_reset_or_solution(fx):
    token = issue(fx)
    cursor = send(fx, token).json
    wrong = send(fx, token, cursor, (3, 3)).json
    assert wrong['status'] == 'INCORRECT' and wrong['opponent_reply'] is None
    assert send(fx, token, cursor).status_code == 409
    assert issue(fx) == token
    assert send(fx, token).json['status'] == 'INCORRECT'
    row = rows(fx, 'node_mastery')[0]
    assert row['purity'] == 0 and row['is_contaminated'] == 1


@pytest.mark.parametrize('field', ['correct', 'grade', 'history', 'solution', 'moves',
    'question_id', 'user_id', 'source_record_uuid', 'opponent_reply', 'reward'])
def test_client_authority_fields_rejected(fx, field):
    token = issue(fx)
    cursor = send(fx, token).json
    assert send(fx, token, cursor, extras={field: True}).status_code == 400
    assert send(fx, token, extras={field: True}).status_code == 400
    assert not rows(fx, 'g076_grimoire_events')


@pytest.mark.parametrize('uid', [None, True, '101', 0, -1, 202])
def test_authentication_and_owner(fx, uid):
    token = issue(fx)
    assert send(fx, token, uid=uid).status_code == (409 if uid == 202 else 401)


@pytest.mark.parametrize('change', ['rights', 'identity', 'revision', 'content', 'expiry', 'disabled'])
def test_authority_revalidated_on_replay_and_resume(fx, change):
    token = issue(fx)
    cursor = send(fx, token).json
    assert send(fx, token, cursor, (3, 3)).status_code == 200
    if change == 'rights':
        fx[2]['deny'] = True
    elif change == 'identity':
        fx[2]['identity'] = 'replacement'
    elif change == 'revision':
        fx[2]['q']['question_revision'] = 'changed'
    elif change == 'content':
        fx[2]['q']['content'] += ' '
    elif change == 'expiry':
        fx[2]['now'] += 3600
    else:
        fx[2]['q']['enabled'] = False
    assert send(fx, token).status_code >= 400
    assert send(fx, token, cursor, (3, 3)).status_code >= 400
    assert rows(fx, 'node_mastery')[0]['attempt_count'] == 1


@pytest.mark.parametrize('flag', ['G076_ANSWER_PRIVACY_ENFORCED', 'G076_GRIMOIRE_STEPS_ENABLED'])
@pytest.mark.parametrize('value', [None, '', 'false', 'unknown'])
def test_default_off_no_connection_or_write(fx, flag, value):
    fx[0].environ.pop(flag)
    if value is not None:
        fx[0].environ[flag] = value
    fx[0].connect = lambda: pytest.fail('disabled service opened DB')
    with pytest.raises(GrimoireRejected, match='disabled'):
        issue(fx)


@pytest.mark.parametrize('failure', ['after_mastery', 'unsafe_receipt', 'commit', 'event_insert'])
def test_transaction_failure_does_not_publish_terminal_or_mastery(fx, failure):
    token = issue(fx)
    first = send(fx, token, send(fx, token).json).json
    if failure == 'event_insert':
        with fx[3]() as conn:
            conn.execute("CREATE TRIGGER reject_event BEFORE INSERT ON g076_grimoire_events BEGIN SELECT RAISE(ABORT,'synthetic'); END")
    else:
        fx[2]['fail'] = failure
    response = send(fx, token, first, (2, 2))
    assert response.status_code == 503
    assert response.json == {'error': 'unsafe_settlement_receipt' if failure == 'unsafe_receipt'
                            else 'grimoire_backend_unavailable'}
    assert not rows(fx, 'node_mastery') and not rows(fx, 'deferred_failure')
    assert rows(fx, 'g076_grimoire_attempts')[0]['step_index'] == 1
    assert len(rows(fx, 'g076_grimoire_events')) == 1
    fx[2]['fail'] = None
    if failure == 'event_insert':
        with fx[3]() as conn:
            conn.execute('DROP TRIGGER reject_event')
    assert send(fx, token, first, (2, 2)).json['status'] == 'CORRECT'
    assert rows(fx, 'node_mastery')[0]['attempt_count'] == 1


def test_concurrent_terminal_retries_and_conflicting_answer(fx):
    token = issue(fx)
    first = send(fx, token, send(fx, token).json).json
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: send(fx, token, first, (2, 2)), range(4)))
    assert all(r.status_code == 200 for r in results)
    assert sum(not r.json['duplicate'] for r in results) == 1
    assert rows(fx, 'node_mastery')[0]['attempt_count'] == 1
    assert send(fx, token, first, (3, 3)).status_code == 409


def test_concurrent_distinct_answers_serialize(fx):
    token = issue(fx)
    cursor = send(fx, token).json
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda xy: send(fx, token, cursor, xy), [(0, 0), (3, 3)]))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert len(rows(fx, 'g076_grimoire_events')) == 1


@pytest.mark.parametrize('content,policy', [
    ('(;SZ[5];B[aa]', None), ('(;SZ[5]B[aa])', None),
    ('(;SZ[5](;B[aa])(;B[bb]))', None),
    ('(;SZ[5];B[aa](;W[bb];B[cc])(;W[dd];B[ee]))', None),
    ('(;SZ[5];B[aa])', 'unknown'),
    ('(;SZ[5];B[aa])', 'g065-explicit-v1'),
])
def test_unsupported_questions_never_issue(fx, content, policy):
    fx[2]['q'].update(content=content, answer_policy=policy)
    with pytest.raises(ValueError):
        issue(fx)
    assert not rows(fx, 'g076_grimoire_attempts')


@pytest.mark.parametrize('move,result', [((0, 0), 'INCORRECT'), ((2, 2), 'CORRECT')])
def test_explicit_canonical_verdict_policy(fx, move, result):
    fx[2]['q'].update(answer_policy='g065-explicit-v1',
        content='(;SZ[5]PL[B](;B[aa]C[G065:INCORRECT])(;B[cc]C[G065:CORRECT]))')
    token = issue(fx)
    assert send(fx, token, send(fx, token).json, move).json['status'] == result


@pytest.mark.parametrize('key', ['accepted_moves', 'accepted_answers', 'katago_best_move'])
def test_alternative_answer_policy_holds(fx, key):
    fx[2]['q'][key] = ['aa']
    with pytest.raises(GrimoireRejected, match='answer_policy_hold'):
        issue(fx)


@pytest.mark.parametrize('xy', [(True, 0), (-1, 0), (5, 0), ('0', 0), (0.1, 0)])
def test_invalid_coordinates_do_not_consume(fx, xy):
    token = issue(fx)
    assert send(fx, token, send(fx, token).json, xy).status_code == 400
    assert not rows(fx, 'g076_grimoire_events')


def test_nonce_scope_and_sequence(fx):
    token = issue(fx)
    other = issue(fx, 'second-server-admission')
    cursor = send(fx, token).json
    assert send(fx, other, cursor).status_code == 403
    assert send(fx, token, {**cursor, 'step_nonce': '偽造'}).status_code == 403
    assert send(fx, token, {**cursor, 'step_index': 1}).status_code == 403
    assert not rows(fx, 'g076_grimoire_events')


@pytest.mark.parametrize('hold', ['catalog', 'cache', 'missing_settlement', 'schema'])
def test_precise_settlement_and_schema_holds(fx, hold):
    if hold == 'catalog':
        fx[2]['q']['grimoire_id'] = 5
    token = issue(fx)
    if hold == 'cache':
        from datetime import datetime
        with fx[3]() as conn:
            conn.execute('INSERT INTO daily_training_cache VALUES (?,?,?,?,?)',
                         (101, datetime.fromtimestamp(fx[2]['now']).date().isoformat(), '[701]', '[]', ''))
    if hold == 'missing_settlement':
        fx[0].settle = None
    if hold == 'schema':
        with fx[3]() as conn:
            conn.execute('DROP TABLE g076_grimoire_events')
    response = send(fx, token)
    if hold in ('catalog', 'cache'):
        response = send(fx, token, response.json, (3, 3))
        assert response.json['error'] == ('catalog_grimoire_settlement_hold' if hold == 'catalog' else 'daily_cache_settlement_hold')
    assert response.status_code == 503
    assert not rows(fx, 'node_mastery')


def test_mastery_legacy_history_timestamp_and_contamination(fx):
    with fx[3]() as conn:
        conn.execute('INSERT INTO node_mastery VALUES (101,701,1,9,?,?,0)',
                     (json.dumps([True] * 5), '2026-10-01T00:00:00'))
    token = issue(fx)
    send(fx, token, send(fx, token).json, (3, 3))
    row = rows(fx, 'node_mastery')[0]
    assert row['attempt_count'] == 10 and row['purity'] == pytest.approx(.7)
    assert row['last_correct_at'] == '2026-10-01T00:00:00'
    assert row['is_contaminated'] == 0
    assert json.loads(row['last_5_history']) == [True, True, True, True, False]


def test_final_judge_disagreement_rolls_back(fx, monkeypatch):
    from map_battle_runtime import JudgeOutcome
    monkeypatch.setattr('g076_grimoire_adapter.judge_practice_answer', lambda *a:
        JudgeOutcome('CORRECT', 5, 'synthetic', 'synthetic'))
    token = issue(fx)
    response = send(fx, token, send(fx, token).json, (3, 3))
    assert response.json == {'error': 'final_judge_disagreement'}
    assert not rows(fx, 'node_mastery') and not rows(fx, 'g076_grimoire_events')


def test_cross_origin_and_body_limit(fx):
    token = issue(fx)
    c = client(fx)
    for headers in ({'Origin': 'https://other.invalid'}, {'Sec-Fetch-Site': 'cross-site'}):
        assert c.post('/api/g076/grimoire/steps', json={'attempt_token': token}, headers=headers).status_code == 403
    assert c.post('/api/g076/grimoire/steps', data='x' * 16385, content_type='application/json').status_code == 413
    assert not rows(fx, 'g076_grimoire_events')
