"""HTTP admission checks without importing Product or opening any database.

These prove HOLD, not playable settlement, XP equivalence, or browser acceptance.
"""
from itertools import product
from types import SimpleNamespace

import pytest
from flask import Flask

from g076_mistakes_product import create_blueprint


PORTS = ('transaction', 'question', 'identity', 'context', 'admit', 'settle')
MODES = ('MISTAKES', 'RATING', 'GRIMOIRE', 'FRIEND', 'LORD', 'GUILD')


def client(flags, services=None):
    app = Flask(__name__)
    app.secret_key = 'disposable-readiness-only'
    app.testing = True
    app.register_blueprint(create_blueprint(
        secret=app.secret_key, environ=flags, services=services))
    result = app.test_client()
    with result.session_transaction() as session:
        session['user_id'] = 101
    return result


def forbidden(*args, **kwargs):
    raise AssertionError('HOLD must not enter any provider or transaction')


@pytest.mark.parametrize('missing', PORTS)
@pytest.mark.parametrize('kind', ('absent', 'noncallable'))
def test_incomplete_provider_capability_and_writes_hold(missing, kind):
    ports = dict.fromkeys(PORTS, forbidden)
    if kind == 'absent':
        del ports[missing]
    else:
        ports[missing] = None
    c = client({'G076_MISTAKES_STEPS_ENABLED': 'on'}, SimpleNamespace(**ports))
    response = c.get('/api/g076/mistakes/capability')
    assert response.status_code == 503
    assert response.json == {'mode': 'hold', 'error': 'mistakes_review_transaction_hold'}
    for route in ('attempt', 'steps/start', 'steps', 'answer'):
        response = c.post('/api/g076/mistakes/' + route, json={})
        assert response.status_code == 503
        assert response.json['error'] == 'mistakes_review_transaction_hold'


@pytest.mark.parametrize('bits', list(product(('off', 'on'), repeat=6)))
@pytest.mark.parametrize('global_flag', ('off', 'on'))
def test_missing_product_provider_never_advertises_steps(bits, global_flag):
    flags = {'G076_' + name + '_STEPS_ENABLED': bit for name, bit in zip(MODES, bits)}
    flags['G076_ANSWER_PRIVACY_ENFORCED'] = global_flag
    c = client(flags)
    response = c.get('/api/g076/mistakes/capability')
    legacy = global_flag == 'off' and flags['G076_MISTAKES_STEPS_ENABLED'] == 'off'
    assert response.status_code == (200 if legacy else 503)
    assert response.json['mode'] == ('legacy' if legacy else 'hold')
    assert c.post('/api/g076/mistakes/attempt', json={'question_id': 701}).status_code == 503


def test_off_does_not_require_or_invoke_provider():
    c = client({}, SimpleNamespace())
    assert c.get('/api/g076/mistakes/capability').json['mode'] == 'legacy'
    assert c.post('/api/g076/mistakes/attempt', json={}).status_code == 503
