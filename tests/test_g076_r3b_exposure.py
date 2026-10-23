"""Actual app route bodies, local Flask HTTP and in-memory SQLite only.

No app startup, credentials, network, production DB, or player state. External
providers are injected; these tests do not qualify deployment or migrated play.
"""
import ast
import copy
import datetime
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

import pytest
from flask import Flask, jsonify, request, session

from g076_question_privacy import board_only_sgf
from sgf_point_transform import transform_sgf

ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
GRIMOIRE_TREE = ast.parse((ROOT / 'grimoire_api.py').read_text(encoding='utf-8'))
SGF = ('(;SZ[9]AB[aa]AW[bc]LB[aa:1]C[SECRET_COMMENT]'
       '(;W[dd]C[SECRET_CORRECT];B[ee])(;W[ff]C[SECRET_WRONG]))')
BAD = ['(;SZ[9]C[SECRET]', '(;SZ[9]W[dd])',
       '(;SZ[9])(;SZ[9])', None, '(;SZ[99];B[aa])']


def body(name, ns, tree=TREE):
    node = copy.deepcopy(next(n for n in tree.body
                             if isinstance(n, ast.FunctionDef) and n.name == name))
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]),
                 str(ROOT / 'app.py'), 'exec'), ns)
    return ns[name]


@pytest.fixture
def api(monkeypatch):
    monkeypatch.delenv('G076_ANSWER_PRIVACY_ENFORCED', raising=False)
    app = Flask('g076_r3b_isolated')
    app.secret_key = 'synthetic-isolated-test-only'
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE mistake_log (user_id, question_id, wrong_count,
                                  last_wrong_at, correct_after);
        INSERT INTO mistake_log VALUES (47, 701, 2, '2026-01-01', 1);
        INSERT INTO mistake_log VALUES (99, 702, 2, '2026-01-01', 0);
        CREATE TABLE daily_challenge (challenge_date, question_id, note);
        INSERT INTO daily_challenge VALUES ('2000-01-01', 701, 'SECRET_NOTE');
        CREATE TABLE daily_challenge_log (user_id, challenge_date, correct);
        CREATE TABLE daily_training_cache (user_id, date, question_ids, completed_ids);
        CREATE TABLE node_mastery (user_id, question_id, purity, attempt_count,
                                  last_correct_at, is_contaminated);
        INSERT INTO node_mastery VALUES (47, 701, 0.1, 3, NULL, 1);
    ''')
    conn.execute('INSERT INTO daily_training_cache VALUES (?, ?, ?, ?)',
                 (47, datetime.date.today().isoformat(), '[701]', '[]'))
    q = {'id': 701, 'content': SGF, 'accepted_moves': [{'x': 3, 'y': 3}],
         'katago_best_move': 'D6', 'katago_answer': 'SECRET_KATAGO',
         'comment': 'SECRET_COMMENT', 'rating': 1500,
         'difficulty': '10k', 'discipline': 'life_death', 'enabled': True}
    original = copy.deepcopy(q)
    calls = []
    sql = []
    conn.set_trace_callback(sql.append)

    @contextmanager
    def db():
        yield conn

    def issue(*args, **kwargs):
        # Projection must not replace the server's authoritative SGF.
        assert kwargs['question'] == q
        assert kwargs['question']['content'] == SGF
        calls.append(kwargs)
        return 'synthetic-attempt'

    ns = dict(app=app, jsonify=jsonify, request=request, session=session,
              os=os, datetime=datetime, json=json, _re_mod=re, wraps=wraps,
              get_db=db, get_sdb=db, load_questions=lambda: [q],
              ensure_node_mastery_table=lambda db: None,
              is_premium=lambda *args: True,
              question_is_free=lambda record: False, _load_questions=lambda: [q],
              _question_content_sha256=lambda record: 'synthetic-full-content-hash',
              _question_display_name=lambda record: 'question',
              _question_display_name_en=lambda record: 'question',
              _english_only=lambda value: value, _i18n_topic_en=lambda value: '',
              _i18n_level_en=lambda value: '', _question_accepted_moves=lambda record: record['accepted_moves'],
              get_or_create_daily_challenge=lambda date: {'question_id': 701, 'note': 'SECRET_NOTE'},
              _map_battle_question_context=lambda record: {'synthetic': True},
              issue_daily_attempt=issue, DAILY_CHALLENGE_XP_REWARD=10,
              DailyAttemptError=ValueError, MapBattleRuntimeError=ValueError,
              _rt_transform_idx=lambda sid, qid: 0, _ensure_rt_pool=lambda: None,
              _RT_POOL=[q], _RT_MAX_ROUNDS=20, _RT_MIN_ROUNDS=10,
              _rating_to_rank=lambda rating: '10k', _rt_converged=lambda *args: False)
    for name in ('login_required', '_g076_exposure_content', '_transform_sgf',
                 '_transform_point', '_strip_question', '_g076_grimoire_exposure'):
        body(name, ns)
    app.after_request(ns['_g076_grimoire_exposure'])
    for path, name in [('/api/mistakes', 'get_mistakes'),
                       ('/api/daily-challenge/today', 'dc_today'),
                       ('/api/daily-challenge/history', 'dc_history'),
                       ('/api/daily-challenge/history/<date_str>', 'dc_history_detail')]:
        node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert ast.unparse(node.decorator_list[-1]) == 'login_required'
        app.add_url_rule(path, name, ns['login_required'](body(name, ns)))
    app.add_url_rule('/api/rating_test/resume/<sid>', 'rt_resume', body('rt_resume', ns))
    # Exercise the shared serializer used by start/answer/resume, with all 8
    # transforms; no test grading/session writer is added to the application.
    app.add_url_rule('/serialize-trial', 'trial', lambda: jsonify(ns['_strip_question'](q, 'sid', 'token')))
    body('login_required_bp', ns, GRIMOIRE_TREE)
    for path, name in [('/api/grimoire/training/daily', 'api_training_daily'),
                       ('/api/training/contaminated', 'api_training_contaminated')]:
        app.add_url_rule(path, name, ns['login_required_bp'](body(name, ns, GRIMOIRE_TREE)))
    client = app.test_client()
    with client.session_transaction() as s:
        s['user_id'] = 47
    yield app, client, ns, q, conn, calls, sql
    assert q == original or q.get('_test_modified') is True
    conn.close()


PATHS = ['/api/mistakes', '/api/daily-challenge/today',
         '/api/daily-challenge/history/2000-01-01', '/serialize-trial',
         '/api/grimoire/training/daily', '/api/training/contaminated']


def question_data(response):
    data = response.get_json()
    if isinstance(data, list):
        return data[0]
    for field in ('questions', 'contaminated', 'question'):
        if field in data:
            return data[field][0] if isinstance(data[field], list) else data[field]
    return data


@pytest.mark.parametrize('path', PATHS)
@pytest.mark.parametrize('flag', [None, '0', 'false', 'unknown'])
def test_off_preserves_legacy_content_and_shape(api, monkeypatch, path, flag):
    _, client, _, _, _, _, _ = api
    if flag is not None:
        monkeypatch.setenv('G076_ANSWER_PRIVACY_ENFORCED', flag)
    response = client.get(path)
    if path == '/api/daily-challenge/today' and flag == 'unknown':
        # Unknown Daily config must not silently expose raw SGF; other
        # legacy modes still obey their established global OFF behavior.
        assert response.status_code == 409
        assert response.get_json()['error'] == 'daily_configuration_hold'
        return
    assert response.status_code == 200
    data = question_data(response)
    assert data['content'] == SGF
    assert 'board_only' not in data
    if path == '/serialize-trial':
        assert data['accepted_moves'] == [{'x': 3, 'y': 3}]
    if '/daily-challenge/' in path:
        assert data['note'] == 'SECRET_NOTE'


@pytest.mark.parametrize('path', PATHS)
def test_gate_projects_board_without_answers_or_writes(api, monkeypatch, path):
    _, client, _, _, _, calls, sql = api
    monkeypatch.setenv('G076_ANSWER_PRIVACY_ENFORCED', 'true')
    response = client.get(path + '?view=full&include_answers=1')
    assert response.status_code == 200
    data = question_data(response)
    assert data['content'] == board_only_sgf(SGF)
    assert data['board_only'] is True
    assert not data.get('accepted_moves')
    assert 'SECRET' not in response.get_data(as_text=True)
    assert ';W[' not in data['content'] and ';B[' not in data['content']
    assert 'katago_answer' not in data and 'comment' not in data
    assert response.headers['Cache-Control'] == 'no-store'
    assert all(s.lstrip().upper().startswith('SELECT') for s in sql)
    if path == '/api/daily-challenge/today':
        assert len(calls) == 1
        assert data['attempt_token'] == 'synthetic-attempt'


@pytest.mark.parametrize('path', PATHS)
@pytest.mark.parametrize('source', BAD)
def test_gate_unparseable_fails_closed(api, monkeypatch, path, source):
    _, client, _, q, _, calls, _ = api
    q.update(content=source, _test_modified=True)
    monkeypatch.setenv('G076_ANSWER_PRIVACY_ENFORCED', 'on')
    response = client.get(path)
    assert response.status_code == 422
    assert response.get_json() == {'error': 'question_preview_unavailable',
                                   'code': 'question_preview_unavailable'}
    assert response.headers['Cache-Control'] == 'no-store'
    assert not calls


@pytest.mark.parametrize('path', [p for p in PATHS if p != '/serialize-trial'])
def test_login_still_required(api, monkeypatch, path):
    app, _, _, _, _, _, _ = api
    monkeypatch.setenv('G076_ANSWER_PRIVACY_ENFORCED', '1')
    assert app.test_client().get(path).status_code == 401


def test_mistakes_locked_unparseable_record_does_not_leak(api, monkeypatch):
    _, client, ns, q, _, _, _ = api
    ns['is_premium'] = lambda *args: False
    q.update(content='SECRET_MALFORMED', _test_modified=True)
    monkeypatch.setenv('G076_ANSWER_PRIVACY_ENFORCED', '1')
    response = client.get('/api/mistakes')
    assert response.status_code == 200
    assert len(response.get_json()) == 1  # user 99's row remains inaccessible
    assert question_data(response)['content'] == ''


@pytest.mark.parametrize('path', ['/api/daily-challenge/history',
                                 '/api/daily-challenge/history/2000-01-01'])
def test_history_premium_check_preserved(api, monkeypatch, path):
    _, client, ns, _, _, _, _ = api
    ns['is_premium'] = lambda *args: False
    monkeypatch.setenv('G076_ANSWER_PRIVACY_ENFORCED', '1')
    assert client.get(path).status_code == 403


def test_history_current_date_blocked_and_notes_private(api, monkeypatch):
    _, client, _, _, _, _, _ = api
    monkeypatch.setenv('G076_ANSWER_PRIVACY_ENFORCED', '1')
    assert client.get('/api/daily-challenge/history/' + datetime.date.today().isoformat()).status_code == 403
    assert 'SECRET' not in client.get('/api/daily-challenge/history').get_data(as_text=True)


def test_submitted_today_is_still_private_for_reused_question(api, monkeypatch):
    _, client, _, _, conn, calls, _ = api
    conn.execute('INSERT INTO daily_challenge_log VALUES (?, ?, ?)',
                 (47, datetime.date.today().isoformat(), 0))
    monkeypatch.setenv('G076_ANSWER_PRIVACY_ENFORCED', '1')
    response = client.get('/api/daily-challenge/today')
    data = response.get_json()
    assert data['user_submitted'] is True and data['user_correct'] is False
    assert data['content'] == board_only_sgf(SGF)
    assert data['attempt_token'] is None and not calls


@pytest.mark.parametrize('transform', range(8))
@pytest.mark.parametrize('enforced', [False, True])
def test_trial_transforms_preserve_authority_and_token(api, monkeypatch, transform, enforced):
    _, client, ns, _, _, _, _ = api
    ns['_rt_transform_idx'] = lambda sid, qid: transform
    if enforced:
        monkeypatch.setenv('G076_ANSWER_PRIVACY_ENFORCED', '1')
    data = client.get('/serialize-trial').get_json()
    expected_source = board_only_sgf(SGF) if enforced else SGF
    assert data['content'] == transform_sgf(expected_source, transform)
    assert data['token'] == 'token'
    assert data['transform_index'] == transform
    if not enforced:
        x, y = ns['_transform_point'](3, 3, 9, transform)
        assert data['accepted_moves'] == [{'x': x, 'y': y}]


def test_trial_transform_error_is_safe_422(api, monkeypatch):
    _, client, ns, _, _, _, _ = api
    monkeypatch.setenv('G076_ANSWER_PRIVACY_ENFORCED', '1')
    def broken(*args):
        raise ValueError('SECRET_ERROR_DETAIL')
    ns['_transform_sgf'] = broken
    response = client.get('/serialize-trial')
    assert response.status_code == 422
    assert 'SECRET' not in response.get_data(as_text=True)


def test_trial_resume_ownership_before_projection(api, monkeypatch):
    _, client, ns, _, conn, _, _ = api
    conn.executescript('''
        CREATE TABLE rating_test_sessions (id, user_id, answers, trigger,
          status, round, cur_rating, rating_se, prior_sd, init_rating,
          current_question_id, current_question_token);
        INSERT INTO rating_test_sessions VALUES
          ('sid', 99, '[]', 'normal', 'in_progress', 1, 1500, 300, 300,
           1500, 701, 'token');
    ''')
    monkeypatch.setenv('G076_ANSWER_PRIVACY_ENFORCED', '1')
    response = client.get('/api/rating_test/resume/sid')
    assert response.status_code == 403
    conn.execute("UPDATE rating_test_sessions SET user_id=47")
    response = client.get('/api/rating_test/resume/sid')
    assert response.status_code == 200
    assert question_data(response)['content'] == board_only_sgf(SGF)
    conn.execute("UPDATE rating_test_sessions SET status='completed'")
    assert 'question' not in client.get('/api/rating_test/resume/sid').get_json()


def test_all_trial_question_envelopes_use_shared_serializer():
    for name in ('rt_start', 'rt_resume', 'rt_answer'):
        node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == '_strip_question' for n in ast.walk(node))


def test_blueprint_projection_inventory_matches_actual_envelopes():
    tree = ast.parse((ROOT / 'grimoire_api.py').read_text(encoding='utf-8'))
    for name in ('api_training_daily', 'api_training_contaminated'):
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert ast.unparse(node.decorator_list[-1]) == 'login_required_bp'
        # No hidden full-question passthrough: actual source uses an explicit
        # allowlist with content as its sole solution-bearing response field.
        dictionaries = [n for n in ast.walk(node) if isinstance(n, ast.Dict)
                        and any(isinstance(k, ast.Constant) and k.value == 'content' for k in n.keys)]
        assert len(dictionaries) == 1
        assert all(isinstance(k, ast.Constant) for k in dictionaries[0].keys)
        assert not {'comment', 'accepted_moves', 'katago_answer', 'katago_best_move'} & {
            k.value for k in dictionaries[0].keys}


@pytest.mark.parametrize('payload', [None, {}, {'questions': None},
                                    {'questions': [None]},
                                    {'questions': [{'content': SGF}, {'content': 'SECRET_BAD'}]}])
def test_blueprint_bad_envelope_never_returns_partial_answers(api, monkeypatch, payload):
    app, client, _, _, _, _, _ = api
    monkeypatch.setenv('G076_ANSWER_PRIVACY_ENFORCED', '1')
    app.view_functions['api_training_daily'] = lambda: jsonify(payload)
    response = client.get('/api/grimoire/training/daily')
    assert response.status_code == 422
    assert 'SECRET' not in response.get_data(as_text=True)
    assert 'questions' not in response.get_json()


@pytest.mark.parametrize('status', [401, 403, 404, 409, 503])
def test_blueprint_existing_errors_preserved(api, monkeypatch, status):
    app, client, _, _, _, _, _ = api
    monkeypatch.setenv('G076_ANSWER_PRIVACY_ENFORCED', '1')
    app.view_functions['api_training_daily'] = lambda: (jsonify({'error': 'existing_error'}), status)
    response = client.get('/api/grimoire/training/daily')
    assert response.status_code == status
    assert response.get_json() == {'error': 'existing_error'}


def test_daily_attempt_failure_does_not_fallback_to_raw_solution(api, monkeypatch):
    _, client, ns, _, _, _, _ = api
    monkeypatch.setenv('G076_ANSWER_PRIVACY_ENFORCED', '1')
    def unavailable(*args, **kwargs):
        raise ValueError('SECRET_AUTHORITY_FAILURE')
    ns['issue_daily_attempt'] = unavailable
    response = client.get('/api/daily-challenge/today')
    assert response.status_code == 503
    assert response.get_json() == {'error': 'daily_challenge_unverifiable'}
