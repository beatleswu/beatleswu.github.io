"""G078 D/E: real Flask requests, isolated SQLite, CURRENT app source bodies.

This is explicitly NOT an import/boot of official app.py. No production config,
DB, corpus, secret, scheduler or network is loaded. Guards/blueprints are real;
legacy view bodies retain source bytes and have synthetic dependency ports.
"""
import ast
import copy
from contextlib import contextmanager
import datetime
from functools import wraps
import hashlib
from itertools import product
import json
import os
from pathlib import Path
import sqlite3
import subprocess

import pytest
from flask import Flask, jsonify, request, session

from g076_grimoire_product import install_product_grimoire
from g076_mistakes_product import create_blueprint
from g076_mode_gate import FLAGS
from g076_othermode_authority import install_othermode_guard
from review_contracts import ReviewCommand, EXTERNAL_AUTHORITATIVE_MAP_BATTLE
from review_service import ReviewService
from srs_review_authority import (is_authoritative_review_source_context,
    resolve_public_srs_review_authority, PublicSrsReviewAuthorityError)
from lord_trial_answer_service import LORD_TRIAL_RESULT_SOURCE_PREFIX
from guild_quest_answer_service import GUILD_QUEST_RESULT_SOURCE_PREFIX, GUILD_QUEST_SOURCE_CONTEXT

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'app.py').read_text(encoding='utf-8-sig')
TREE = ast.parse(SOURCE)
PRIVACY = 'G076_ANSWER_PRIVACY_ENFORCED'
SGF = '(;SZ[5]PL[B]AB[ee];B[aa]C[G078_SECRET];W[bb];B[cc])'
Q = {'id': 701, 'content': SGF, 'enabled': True, 'grimoire_id': 5}


@pytest.fixture(scope='session', autouse=True)
def pinned_head():
    assert Path.cwd().resolve() == ROOT.resolve(), 'Run only from the authorized worktree'
    # G079: the matrix must run on a committed descendant of the G078 audited
    # baseline (fe696e87). An exact-SHA pin made every later commit, including
    # the one that added this suite, error before any request was issued.
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert subprocess.call(['git', 'merge-base', '--is-ancestor',
                            'fe696e87806a177d74e3ebfd4e3bd37cd2571a64', head],
                           cwd=ROOT) == 0, head
    tracked = subprocess.check_output(['git', 'diff', 'HEAD', '--name-only'], cwd=ROOT, text=True)
    assert not tracked.strip(), 'Tracked baseline changed: ' + tracked


def function(name, namespace):
    node = copy.deepcopy(next(n for n in TREE.body
                             if isinstance(n, ast.FunctionDef) and n.name == name))
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]),
                 str(ROOT / 'app.py') + ':G078-isolated-body', 'exec'), namespace)
    return namespace[name]


def assert_private(response):
    raw = response.get_data(as_text=True)
    for secret in ('G078_SECRET', ';B[', ';W['):
        assert secret not in raw, (response.status_code, raw)
    def walk(value):
        if isinstance(value, dict):
            assert not set(value) & {'solution', 'answer_tree', 'accepted_moves', 'katago_answer'}
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(response.get_json(silent=True))


@pytest.fixture
def isolated(monkeypatch):
    for flag in (*FLAGS.values(), PRIVACY, 'G076_STEP_RUNTIME_ENABLED',
                 'G076_NONMAP_STEPS_ENABLED', 'G076_DAILY_STEPS_ENABLED'):
        monkeypatch.delenv(flag, raising=False)
    app = Flask('G078_NOT_OFFICIAL_APP', static_folder=None)
    app.secret_key = 'G078-synthetic-session-only'
    app.testing = True
    # Identical ordering to app.py, without reading official lookup/config.
    install_othermode_guard(app)
    def lookup(qid):
        from g076_grimoire_adapter import GrimoireRejected
        if qid not in (701, 702):
            raise GrimoireRejected('question_unavailable', 503)
        return Q if qid == 701 else {'id': 702, 'grimoire_id': None}
    install_product_grimoire(app, environ=os.environ, lookup=lookup)
    app.register_blueprint(create_blueprint(secret=app.secret_key, environ=os.environ))
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE mistake_log(user_id, question_id, wrong_count, last_wrong_at, correct_after);
        INSERT INTO mistake_log VALUES(101,701,2,'2026-10-23',0);
        CREATE TABLE friend_challenges(id,from_user,to_user,status,question_ids);
    ''')
    @contextmanager
    def db():
        yield conn
    ns = dict(app=app, os=os, jsonify=jsonify, request=request, session=session,
              wraps=wraps, datetime=datetime, json=json, get_db=db,
              is_premium=lambda uid: True, question_is_free=lambda q: True,
              _load_questions=lambda: [Q], _ensure_rt_pool=lambda: None, _RT_POOL=[],
              _question_content_sha256=lambda q: hashlib.sha256(q['content'].encode()).hexdigest(),
              _question_display_name=lambda q: 'synthetic',
              _question_display_name_en=lambda q: 'synthetic',
              _english_only=lambda s: s, _i18n_topic_en=lambda s: '', _i18n_level_en=lambda s: '',
              incident018_update_current=lambda **kw: None)
    ns.update(ReviewCommand=ReviewCommand,
              EXTERNAL_AUTHORITATIVE_MAP_BATTLE=EXTERNAL_AUTHORITATIVE_MAP_BATTLE,
              is_authoritative_review_source_context=is_authoritative_review_source_context,
              resolve_public_srs_review_authority=resolve_public_srs_review_authority,
              PublicSrsReviewAuthorityError=PublicSrsReviewAuthorityError,
              LORD_TRIAL_RESULT_SOURCE_PREFIX=LORD_TRIAL_RESULT_SOURCE_PREFIX,
              GUILD_QUEST_RESULT_SOURCE_PREFIX=GUILD_QUEST_RESULT_SOURCE_PREFIX,
              GUILD_QUEST_SOURCE_CONTEXT=GUILD_QUEST_SOURCE_CONTEXT,
              BOSS_REVIEW_SOURCE_CONTEXT_PREFIX='boss_trial:', BOSS_REVIEW_SOURCE_CONTEXT_MAX_LENGTH=40,
              INCIDENT_018_LORD_REVIEW_ENDPOINT='/api/srs/review',
              incident018_begin_request=lambda *a, **kw: (None, None),
              incident018_current_observation=lambda: None,
              incident018_log_stage=lambda *a, **kw: None,
              incident018_log_exception=lambda *a, **kw: None,
              incident018_end_request=lambda token: None)
    for name in ('login_required', '_g076_exposure_content'):
        function(name, ns)
    # Real route -> real ReviewService -> current unedited operation body.
    # Scope is EARLY authority rejection, not positive full reward settlement.
    ns['_review_service'] = ReviewService(function('_srs_review_operation', ns))
    # Current official functions; no fake success view or blanket auth hook.
    routes = [('/api/mistakes', 'get_mistakes', 'GET', True),
              ('/api/challenges/friend/<int:cid>/answer', 'friend_challenge_answer', 'POST', True),
              ('/api/adventure/boss/finish', 'adventure_boss_finish', 'POST', True),
              ('/api/srs/review', 'srs_review', 'POST', True),
              ('/api/rating_test/answer', 'rt_answer', 'POST', False)]
    for rule, name, method, auth in routes:
        view = function(name, ns)
        app.add_url_rule(rule, name, ns['login_required'](view) if auth else view, methods=[method])
    # Training body is from its official blueprint module. Empty body returns
    # before any mastery writer. Global/per-Grimoire containment runs first.
    training_tree = ast.parse((ROOT / 'grimoire_api.py').read_text(encoding='utf-8-sig'))
    node = copy.deepcopy(next(n for n in training_tree.body
                             if isinstance(n, ast.FunctionDef) and n.name == 'api_training_answer'))
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'grimoire_api.py:G078', 'exec'), ns)
    app.add_url_rule('/api/training/answer', 'grimoire.api_training_answer',
                     ns['login_required'](ns['api_training_answer']), methods=['POST'])
    try:
        yield app, conn, monkeypatch
    finally:
        conn.close()


@pytest.mark.parametrize('bits', list(product(('off', 'on'), repeat=6)),
                         ids=lambda b: ''.join('1' if x == 'on' else '0' for x in b))
@pytest.mark.parametrize('privacy', ('off', 'on'))
def test_128_scenarios_real_flask_routes(isolated, bits, privacy):
    app, conn, patch = isolated
    for flag, value in zip(FLAGS.values(), bits):
        patch.setenv(flag, value)
    patch.setenv(PRIVACY, privacy)
    enabled = dict(zip(FLAGS, bits))
    grimoire = enabled['grimoire'] == 'on'
    for uid in (None, 101):
        client = app.test_client()
        if uid:
            with client.session_transaction() as s:
                s['user_id'] = uid
        baseline = conn.total_changes
        # Product Mistakes has no official transaction provider: HOLD is honest.
        cap = client.get('/api/g076/mistakes/capability')
        legacy = privacy == 'off' and enabled['mistakes'] == 'off'
        assert cap.status_code == ((200 if legacy else 503) if uid else 401)
        if uid:
            assert cap.json['mode'] == ('legacy' if legacy else 'hold')
        assert_private(cap)
        for suffix in ('attempt', 'steps/start', 'steps', 'answer'):
            r = client.post('/api/g076/mistakes/' + suffix, json={'grade': 5, 'correct': True})
            assert r.status_code == (503 if uid else 401)
            assert_private(r)
        r = client.get('/api/mistakes?include_answers=1&view=full')
        assert r.status_code == (409 if grimoire else 200 if uid else 401)
        if grimoire or not uid or privacy == 'on' or enabled['mistakes'] == 'on':
            assert_private(r)
        else:
            assert r.json[0]['content'] == SGF  # explicit legacy OFF compatibility
        for path, endpoint in (('/api/training/answer', 'training'),
                               ('/api/challenges/friend/1/answer', 'friend')):
            r = client.post(path, json={})
            blocked = privacy == 'on' or grimoire
            assert r.status_code == (409 if blocked else 400 if uid else 401)
            assert_private(r)
        r = client.post('/api/adventure/boss/finish', json={'correct': 20, 'total': 20, 'grade': 5})
        assert r.status_code == (400 if uid else 401)
        assert_private(r)
        r = client.post('/api/rating_test/answer', json={'grade': 5, 'correct': True})
        assert r.status_code == (409 if grimoire else 400)
        assert_private(r)
        for envelope in ({'source_context': 'mbv1:spoof'},
                         {'source_context': 'practice', 'guild_answer': {'correct': True}},
                         {'source_context': 'practice', 'boss_answer': {'correct': True}}):
            r = client.post('/api/srs/review', json={'question_id': 701, 'grade': 5, **envelope})
            assert r.status_code == (409 if grimoire else 400 if uid else 401)
            assert_private(r)
        # Installed Grimoire Product is explicit HOLD without providers.
        headers = {'X-Grimoire-Request': '1'}
        r = client.post('/api/g076/grimoire/product/admission', json={}, headers=headers)
        assert r.status_code == (503 if not grimoire or uid else 401)
        assert_private(r)
        assert conn.total_changes == baseline


@pytest.mark.parametrize('flag', (*FLAGS.values(), PRIVACY))
@pytest.mark.parametrize('value', ('typo', '2', '[]'))
def test_unknown_flags_real_mistakes_request(isolated, flag, value):
    app, _, patch = isolated
    patch.setenv(flag, value)
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_id'] = 101
    r = c.get('/api/g076/mistakes/capability')
    relevant = flag in (FLAGS['mistakes'], PRIVACY)
    assert r.status_code == (503 if relevant else 200)
    assert r.json['mode'] == ('hold' if relevant else 'legacy')
    assert_private(r)


def test_default_off_and_unknown_routes(isolated):
    app, _, _ = isolated
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_id'] = 101
    assert c.get('/api/g076/mistakes/capability').json['mode'] == 'legacy'
    assert c.get('/api/g076/unknown/capability').status_code == 404
    assert c.get('/api/g076/mistakes/attempt').status_code == 405
    # Rating module exists but CURRENT app.py does not install it.
    assert 'create_rating_blueprint' not in SOURCE


def test_current_official_installation_source_receipt():
    """Static installation evidence, never represented as official app boot."""
    guard = SOURCE.index('install_othermode_guard(app)')
    product_install = SOURCE.index('install_product_grimoire(app,')
    assert guard < product_install < SOURCE.index('CORS(app,')
    assert 'app.register_blueprint(_g076_mistakes_blueprint(secret=app.secret_key, environ=os.environ))' in SOURCE
    assert 'from grimoire_api import official_grimoire_lookup' in SOURCE
    assert 'create_rating_blueprint' not in SOURCE
    assert "if __name__ == '__main__':\n    init_db()" in SOURCE


@pytest.mark.parametrize('bad_sgf', (None, '(;SZ[5]', '(;SZ[99];B[aa])', '(;SZ[5]B[aa])'))
def test_malformed_question_fails_closed_in_current_route(isolated, bad_sgf):
    app, conn, patch = isolated
    patch.setenv(FLAGS['mistakes'], 'on')
    patch.setitem(Q, 'content', bad_sgf)
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_id'] = 101
    before = conn.total_changes
    r = c.get('/api/mistakes?view=full')
    assert r.status_code == 422
    assert_private(r)
    assert conn.total_changes == before


def test_malformed_grimoire_flag_must_hold_legacy_transport(isolated):
    app, _, patch = isolated
    patch.setenv(FLAGS['grimoire'], 'typo')
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_id'] = 101
    assert c.post('/api/training/answer', json={}).status_code in (409, 503)


def test_single_grimoire_on_other_normal_mode_serviceability(isolated):
    app, _, patch = isolated
    patch.setenv(FLAGS['grimoire'], 'on')
    c = app.test_client()
    with c.session_transaction() as s:
        s['user_id'] = 101
    assert c.get('/api/mistakes').status_code == 200
