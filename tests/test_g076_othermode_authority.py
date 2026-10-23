"""Isolated HTTP containment proofs; no app import or persistent database.

Execute exact legacy function ASTs rather than importing app.py (which has
runtime bootstrap side effects). These are bounded tests, not live deployment
or PostgreSQL qualification. The OFF Grimoire proof intentionally preserves
the historical vulnerability so the guard cannot masquerade as a judge fix.
"""
import ast
from contextlib import contextmanager
import datetime
import json
from pathlib import Path
import sqlite3

from flask import Flask, jsonify, request, session
import pytest

from g076_othermode_authority import install_othermode_guard
from guild_quest_answer_service import (
    GuildQuestAnswerError, GuildQuestVerdictPersistenceError,
    build_guild_quest_verdict, judge_guild_quest_answer,
)
from lord_trial_answer_service import LordTrialAnswerError, judge_lord_trial_answer
from srs_review_authority import resolve_public_srs_review_authority


ROOT = Path(__file__).resolve().parents[1]
FLAG = 'G076_ANSWER_PRIVACY_ENFORCED'
QUESTION = {'id': 7, 'answer_policy': 'g065-explicit-v1',
            'content': '(;SZ[9]PL[B];B[dd]C[G065:CORRECT])'}


def legacy_function(filename, name, dependencies):
    tree = ast.parse((ROOT / filename).read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    namespace = dict(dependencies)
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, 'exec'), namespace)
    return namespace[name]


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE node_mastery (
            user_id INTEGER, question_id INTEGER, purity REAL, attempt_count INTEGER,
            last_5_history TEXT, last_correct_at TEXT, is_contaminated INTEGER,
            UNIQUE(user_id, question_id));
        CREATE TABLE daily_training_cache (
            user_id INTEGER, date TEXT, question_ids TEXT, completed_ids TEXT);
    ''')
    calls = []

    @contextmanager
    def db():
        calls.append('db')
        yield conn

    def no_read():
        calls.append('questions')
        raise AssertionError('guard must stop legacy question loading')

    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='isolated-othermode-test-key')
    install_othermode_guard(app)
    dependencies = dict(json=json, datetime=datetime, request=request, session=session,
                        jsonify=jsonify, get_sdb=db, get_db=db,
                        ensure_node_mastery_table=lambda c: None,
                        calc_node_purity=lambda history: sum(history) / len(history),
                        load_questions=lambda: [dict(QUESTION)])
    training = legacy_function('grimoire_api.py', 'api_training_answer', dependencies)
    app.add_url_rule('/api/training/answer', 'grimoire.api_training_answer', training,
                     methods=['POST'])
    # Endpoint alias plus renamed endpoint on canonical rule are both guarded.
    app.add_url_rule('/alias/answer', 'grimoire.api_training_answer', training, methods=['POST'])
    for path, name in [('/api/grimoire/training/daily', 'api_training_daily'),
                       ('/api/training/contaminated', 'api_training_contaminated')]:
        view = legacy_function('grimoire_api.py', name,
                               dict(dependencies, load_questions=no_read))
        app.add_url_rule(path, 'grimoire.' + name, view)
    friend = legacy_function('app.py', 'friend_challenge_answer', dependencies)
    app.add_url_rule('/api/challenges/friend/<int:cid>/answer', 'renamed_friend', friend,
                     methods=['POST'])

    @app.get('/unrelated')
    def unrelated():
        return jsonify(ok=True)

    # These stubs assert only guard scope, not the other workers' integration.
    for i, path in enumerate(('/api/srs/practice/answer', '/api/daily-challenge/submit',
                              '/api/srs/review', '/api/rating_test/answer',
                              '/api/adventure/boss/finish')):
        app.add_url_rule(path, 'unaffected_' + str(i), unrelated, methods=['POST'])
    client = app.test_client()
    with client.session_transaction() as signed:
        signed['user_id'] = 11
    yield app, client, conn, calls
    conn.close()


def test_off_actual_grimoire_accepts_forged_correct_and_replay(harness):
    """Evidence of the existing bug, NOT a new-mode success claim."""
    _, client, conn, _ = harness
    for _ in range(2):
        result = client.post('/api/training/answer', json={
            'questionId': 7, 'correct': True, 'moves': [], 'grade': 5})
        assert result.status_code == 200
    row = conn.execute('SELECT * FROM node_mastery').fetchone()
    assert row['attempt_count'] == 2
    assert json.loads(row['last_5_history']) == [True, True]


@pytest.mark.parametrize('payload', [
    {'questionId': 7, 'correct': True, 'grade': 5},
    {'questionId': 7, 'correct': 'false', 'authoritative_grade': 5},
    {'questionId': 7, 'moves': [], 'nonce': 'forged', 'source_context': 'practice'},
    {'questionId': 7, 'correct': True, 'original_question_id': 999, 'reward': 100},
    [], None,
])
def test_enforced_forgery_and_replay_never_reach_writer(harness, monkeypatch, payload):
    _, client, conn, calls = harness
    monkeypatch.setenv(FLAG, 'on')
    for _ in range(3):
        result = client.post('/api/training/answer?mode=practice&privacy=off',
                             json=payload, headers={'Idempotency-Key': 'new-every-time'})
        assert result.status_code == 409
        assert result.json == dict(ok=False, error='othermode_authority_unavailable',
                                   code='othermode_authority_unavailable',
                                   mode='grimoire', retryable=False)
        assert result.headers['Cache-Control'] == 'no-store'
    assert not calls
    assert conn.execute('SELECT COUNT(*) FROM node_mastery').fetchone()[0] == 0


@pytest.mark.parametrize('uid,premium', [(None, False), (11, False), (22, True)])
def test_no_entitlement_or_owner_claim_can_bypass_guard(harness, monkeypatch, uid, premium):
    _, client, _, calls = harness
    monkeypatch.setenv(FLAG, 'true')
    with client.session_transaction() as signed:
        signed.clear()
        if uid:
            signed.update(user_id=uid, is_premium=premium, is_admin=True)
    for path in ('/api/grimoire/training/daily', '/api/training/contaminated'):
        result = client.get(path + '?reveal=1&submitted=true&view=full')
        assert result.status_code == 409
        assert 'content' not in result.json
        assert result.headers['Cache-Control'] == 'no-store'
    assert not calls


@pytest.mark.parametrize('path,method', [
    ('/alias/answer', 'POST'),
    ('/api/training/answer', 'OPTIONS'),
    ('/api/grimoire/training/daily', 'HEAD'),
    ('/api/challenges/friend/99/answer', 'POST'),
    ('/api/challenges/friend/99/answer', 'OPTIONS'),
])
def test_matched_rules_aliases_and_http_methods_are_contained(harness, monkeypatch, path, method):
    _, client, _, calls = harness
    monkeypatch.setenv(FLAG, '1')
    assert client.open(path, method=method, json={'correct': True}).status_code == 409
    assert not calls


def test_guard_scope_and_unmatched_routes(harness, monkeypatch):
    _, client, _, _ = harness
    monkeypatch.setenv(FLAG, 'true')
    for path in ('/api/srs/practice/answer', '/api/daily-challenge/submit', '/api/srs/review',
                 '/api/rating_test/answer', '/api/adventure/boss/finish'):
        assert client.post(path).status_code == 200
    assert client.get('/unrelated').status_code == 200
    assert client.get('/api/training/answer').status_code == 405
    assert client.post('/api/challenges/friend/not-an-int/answer').status_code == 404


def test_install_is_idempotent_and_late_hook_order_is_rejected():
    app = Flask('idempotent')
    install_othermode_guard(app)
    install_othermode_guard(app)
    assert len(app.before_request_funcs[None]) == 1
    app2 = Flask('late')
    app2.before_request(lambda: None)
    with pytest.raises(RuntimeError, match='must_be_installed_first'):
        install_othermode_guard(app2)


@pytest.mark.parametrize('field', ['grade', 'correct', 'authoritative_grade', 'question_id'])
def test_existing_lord_and_guild_judges_reject_forged_answer_fields(field):
    answer = {'moves': [{'action': 'play', 'x': 3, 'y': 3}], field: 5}
    with pytest.raises(GuildQuestAnswerError, match='forbidden_answer_field'):
        judge_guild_quest_answer(answer, question=QUESTION, quest_key='life_death::LV3')
    with pytest.raises(LordTrialAnswerError, match='forbidden_answer_field'):
        judge_lord_trial_answer(answer, question=QUESTION,
                                exam={'attempt_id': 'server-attempt', 'zone_key': 'zone1'})


def test_existing_guild_verdict_needs_entitlement_and_wrong_move_fails():
    _, outcome = judge_guild_quest_answer(
        {'moves': [{'action': 'play', 'x': 2, 'y': 2}]},
        question=QUESTION, quest_key='life_death::LV3')
    assert outcome.result == 'INCORRECT'
    assert outcome.authoritative_grade == 0
    with pytest.raises(GuildQuestVerdictPersistenceError):
        build_guild_quest_verdict(quest_key='life_death::LV3', question_id=7,
                                  judge=outcome, guild_eligible=False)


def test_legacy_srs_grade_is_scheduling_only():
    decision = resolve_public_srs_review_authority(5)
    assert decision.scheduling_grade == 5
    assert decision.authoritative_answer_correct is None
    assert decision.progress_eligible is False


def test_actual_guild_eligibility_requires_accepted_owner_and_catalog_membership():
    conn = sqlite3.connect(':memory:')
    try:
        conn.execute('CREATE TABLE quest_accepted (user_id INTEGER, quest_key TEXT)')
        conn.execute('INSERT INTO quest_accepted VALUES (11, ?)', ('life_death::LV3',))
        eligible = legacy_function('app.py', '_guild_quest_answer_eligibility', {
            'is_premium': lambda uid: False,
            '_quest_segment_for_key': lambda key, premium: (
                {'question_ids': [7]} if key == 'life_death::LV3' else None),
        })
        assert eligible(conn, 11, 'life_death::LV3', 7)
        assert not eligible(conn, 22, 'life_death::LV3', 7)
        assert not eligible(conn, 11, 'life_death::LV3', 8)
        assert not eligible(conn, 11, 'invented::LV3', 7)
    finally:
        conn.close()


def test_actual_rating_judge_does_not_need_client_grade():
    from sgf_engine.parser.sgf_parser import parse_sgf
    verify = legacy_function('app.py', '_rt_server_verify', {
        'parse_sgf': parse_sgf, '_rt_transform_idx': lambda sid, qid: 0,
    })
    assert verify(QUESTION, 'owned-session', [{'x': 3, 'y': 3}]) is True
    assert verify(QUESTION, 'owned-session', [{'x': 2, 'y': 2}]) is False
    # Historical C[correct] annotations are not an approved authority policy.
    assert verify({'id': 7, 'content': '(;SZ[9]PL[B];B[dd]C[correct])'},
                  'owned-session', [{'x': 3, 'y': 3}]) is None


@pytest.mark.parametrize('setting', ['', 'off', 'false', 'unknown'])
def test_non_enforced_values_preserve_legacy_behavior(harness, monkeypatch, setting):
    _, client, conn, _ = harness
    monkeypatch.setenv(FLAG, setting)
    assert client.post('/api/training/answer', json={
        'questionId': 7, 'correct': True}).status_code == 200
    assert conn.execute('SELECT attempt_count FROM node_mastery').fetchone()[0] == 1
