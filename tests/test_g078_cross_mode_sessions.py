"""Synthetic SQLite Rating + original AST seam; NOT official app integration.

The reused fixture removes conn.commit in extracted original Rating functions
and replaces PostgreSQL FOR UPDATE with SQLite BEGIN IMMEDIATE. Those existing
fixture transformations are material limitations, never production evidence.
"""
import pytest

from g076_rating_fixture import make_rating_fixture
from test_g076_rating_steps import body
from test_g078_cross_mode_matrix import FLAGS, PRIVACY, assert_private, pinned_head


@pytest.fixture
def rating(tmp_path, monkeypatch):
    monkeypatch.setenv('SHADOW_JUDGING_ENABLED', '0')
    return make_rating_fixture(tmp_path / 'g078-rating.sqlite')


def client(fx, uid):
    c = fx[0].test_client()
    c.post('/fixture/login', json={'uid': uid})
    return c


def snapshot(fx):
    with fx[2]() as conn:
        return {t: [tuple(row) for row in conn.execute('SELECT * FROM ' + t)] for t in
                ('rating_test_responses', 'g076_rating_events', 'mistake_log', 'users')}


@pytest.mark.parametrize('privacy', ('off', 'on'))
@pytest.mark.parametrize('uid', (None, 7))
def test_rating_single_flag_preserves_authoritative_round(rating, privacy, uid):
    fx = rating
    fx[1]['environ'].update(dict.fromkeys(FLAGS.values(), 'off'))
    fx[1]['environ'].update({FLAGS['rating']: 'on', PRIVACY: privacy})
    c = client(fx, uid)
    r = c.post('/api/g076/rating/start', json={'trigger': 'manual'})
    assert r.status_code == 200
    assert_private(r)
    d = r.json
    assert c.post('/api/g076/rating/step', json=body(d)).json['status'] == 'CONTINUE'
    resumed = c.get('/api/g076/rating/resume/' + d['session_id'])
    assert resumed.status_code == 200
    assert_private(resumed)
    terminal_body = body(resumed.json, (2, 2))
    r = c.post('/api/g076/rating/step', json=terminal_body)
    assert r.status_code == 200 and r.json['status'] == 'CORRECT'
    assert_private(r)
    before = snapshot(fx)
    assert len(before['rating_test_responses']) == 1
    assert c.post('/api/g076/rating/step', json=terminal_body).json == r.json
    assert snapshot(fx) == before


@pytest.mark.parametrize('negative', ('account_switch', 'resume_other_owner',
                                      'replay_conflict', 'revoked_cached_replay'))
def test_four_account_resume_replay_negative_paths(rating, negative):
    fx = rating
    c = client(fx, 7)
    d = c.post('/api/g076/rating/start', json={}).json
    b = body(d)
    if negative in ('replay_conflict', 'revoked_cached_replay'):
        assert c.post('/api/g076/rating/step', json=b).status_code == 200
    before = snapshot(fx)
    if negative == 'account_switch':
        c.post('/fixture/login', json={'uid': 8})
        r = c.post('/api/g076/rating/step', json=b)
        expected = 403
    elif negative == 'resume_other_owner':
        r = client(fx, 8).get('/api/g076/rating/resume/' + d['session_id'])
        expected = 403
    elif negative == 'replay_conflict':
        # The original valid answer has a transform-dependent position.
        # A hardcoded (4,4) can equal that position after rotation, making
        # this a legitimate idempotent 200 rather than a conflicting replay.
        # Change a guaranteed-valid coordinate of the actual submitted move.
        conflict = {'x': (b['move']['x'] + 1) % 5, 'y': b['move']['y']}
        r = c.post('/api/g076/rating/step', json={**b, 'move': conflict})
        expected = 409
    else:
        fx[1]['deny'] = True
        r = c.post('/api/g076/rating/step', json=b)
        expected = 403
    assert r.status_code == expected
    assert_private(r)
    assert snapshot(fx) == before


@pytest.mark.parametrize('flag', (FLAGS['rating'], PRIVACY))
@pytest.mark.parametrize('value', ('typo', '2', '[]'))
def test_rating_unknown_config_holds_before_effects(rating, flag, value):
    fx = rating
    fx[1]['environ'][flag] = value
    c = client(fx, 7)
    before = snapshot(fx)
    assert c.get('/api/g076/rating/capability').status_code == 503
    assert c.post('/api/g076/rating/start', json={}).status_code == 503
    assert snapshot(fx) == before
