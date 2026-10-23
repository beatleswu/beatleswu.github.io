"""G079 C: unit + isolated-Flask checks for the B2 Rating product wiring.

No database, no app.py import. Real g078 install() guard on a Flask app whose
legacy rating endpoints are stand-ins that only record that they were reached.
"""
from itertools import product

import pytest
from flask import Flask, jsonify

from g076_mode_gate import FLAGS, select_mode
from g076_rating_steps import mode
from g078_rating_integration import RatingAppServices, install, step_ineligible_ids

RATING, PRIVACY = FLAGS['rating'], 'G076_ANSWER_PRIVACY_ENFORCED'
VALUES = ('', 'off', 'on', '0', '1', 'true', 'false', 'typo')


@pytest.mark.parametrize('rating,privacy', tuple(product(VALUES, repeat=2)))
def test_rating_mode_is_the_shared_gate(rating, privacy):
    env = {RATING: rating, PRIVACY: privacy}
    assert mode(env) == select_mode(env, 'rating', adapter_ready=True).selected
    # Without a verified adapter the shared gate never reports steps.
    assert select_mode(env, 'rating').selected != 'steps'


def test_step_ineligible_ids_flags_only_unservable_questions():
    ok = dict(id=1, rating=1500, content='(;SZ[5]PL[B]AB[ee];B[aa];W[bb];B[cc])')
    dup = dict(id=2, rating=1500, content='(;SZ[5]PL[B]AB[ee](;B[aa];W[bb];B[cc])(;B[aa];W[cc];B[bb]))')
    alt = dict(ok, id=3, content='(;SZ[5]PL[B]AB[ed];B[aa];W[bb];B[cc])', accepted_moves=[{'x': 4, 'y': 4}])
    broken = dict(id=4, rating=1500, content='(;SZ[5]')
    assert step_ineligible_ids([ok, dup, alt, broken]) == {2, 3, 4}


def test_ineligible_cache_follows_pool_rebuild():
    ok = dict(id=1, rating=1500, content='(;SZ[5]PL[B]AB[ee];B[aa];W[bb];B[cc])')
    dup = dict(id=2, rating=1500, content='(;SZ[5]PL[B]AB[ee](;B[aa];W[bb];B[cc])(;B[aa];W[cc];B[bb]))')
    runtime = {'_RT_POOL': [ok], '_RT_POOL_BUILT_AT': 1.0}
    services = RatingAppServices(runtime)
    assert services.ineligible_ids() == frozenset()
    runtime.update(_RT_POOL=[ok, dup], _RT_POOL_BUILT_AT=2.0)
    assert services.ineligible_ids() == {2}


LEGACY = (('POST', '/api/rating_test/start', 'rt_start'), ('POST', '/api/rating_test/answer', 'rt_answer'),
          ('GET', '/api/rating_test/resume/s1', 'rt_resume'),
          ('POST', '/api/rating_test/placement_finish', 'rt_placement_finish'),
          ('GET', '/api/rating_test/result/s1', 'rt_result'), ('GET', '/api/rating_test/pool_info', 'rt_pool_info'),
          ('POST', '/api/rating_test/claim_anon', 'rt_claim_anon'), ('POST', '/api/rating_test/claim_sp', 'rt_claim_sp'),
          ('GET', '/api/mistakes', 'get_mistakes'), ('POST', '/api/srs/review', 'srs_review'))
ALLOWED_UNDER_STEPS = {'rt_result', 'rt_pool_info', 'rt_claim_anon', 'rt_claim_sp'}


@pytest.fixture
def guarded():
    env = {}
    app = Flask(__name__)
    app.secret_key = 'g079-unit-only'
    for method, path, endpoint in LEGACY:
        rule = path.replace('/s1', '/<sid>')
        app.add_url_rule(rule, endpoint, (lambda e: lambda **kw: jsonify(reached=e))(endpoint), methods=[method])
    install(app, {}, env)  # empty runtime: adapter can never become ready
    return app, env


@pytest.mark.parametrize('rating,privacy', (('off', 'off'), ('on', 'off'), ('on', 'on'), ('off', 'on'), ('typo', 'off')))
def test_install_guard_matrix(guarded, rating, privacy):
    app, env = guarded
    env.update({RATING: rating, PRIVACY: privacy})
    selected = mode(env)
    client = app.test_client()
    for method, path, endpoint in LEGACY:
        r = client.open(path, method=method, json={})
        rating_route = path.startswith('/api/rating_test/')
        if not rating_route or selected == 'legacy' or (selected == 'steps' and endpoint in ALLOWED_UNDER_STEPS):
            assert (r.status_code, r.json) == (200, {'reached': endpoint}), (rating, privacy, path)
        else:
            assert (r.status_code, r.json['error']) == (503, 'rating_steps_required'), (rating, privacy, path)
        if rating_route and selected != 'legacy':
            assert 'no-store' in r.headers['Cache-Control']
    cap = client.get('/api/g076/rating/capability')
    # Flag ON with an unready adapter (no ledger/runtime) is HOLD, never steps.
    assert (cap.status_code, cap.json['mode']) == ((200, 'legacy') if selected == 'legacy' else (503, 'hold'))
    for path in ('/api/g076/rating/start', '/api/g076/rating/step'):
        r = client.post(path, json={})
        assert (r.status_code, r.json['error']) == (503, 'rating_steps_hold')
