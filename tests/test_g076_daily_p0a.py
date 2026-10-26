"""Disposable SQLite + actual extracted app route bodies. Never import app."""
import datetime
import itertools
import pytest
from g076_daily_capability import DAILY_FLAGS, daily_mode
from g076_daily_fixture import make_daily_fixture


@pytest.fixture
def fx(tmp_path):
    result = make_daily_fixture(tmp_path/'p0a.sqlite')
    result[1]['environ'].clear()
    return result


def login(fx, uid=7):
    client = fx[0].test_client()
    client.post('/fixture/login', json={'uid': uid})
    return client


def counts(fx):
    with fx[2]() as conn:
        return {table: conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                for table in ('review_log', 'daily_challenge_log', 'badges_earned', 'user_stats')}


@pytest.mark.parametrize('bits', list(itertools.product((False, True), repeat=3)))
def test_all_gate_combinations_and_direct_legacy_admission(fx, bits):
    fx[1]['environ'].update(dict(zip(DAILY_FLAGS, ('on' if b else 'off' for b in bits))))
    c = login(fx)
    mode = 'steps' if all(bits) else 'legacy' if not any(bits) else 'hold'
    r = c.get('/api/g076/daily/capability?mode=legacy&enabled=false')
    assert r.status_code == (409 if mode == 'hold' else 200)
    assert r.json['mode'] == mode
    assert 'no-store' in r.headers['Cache-Control']
    assert r.headers['Vary'] == 'Cookie'
    # Direct legacy URL/POST cannot use a browser-supplied enable override.
    assert c.get('/daily_challenge_legacy.html').status_code == 200
    if mode != 'legacy':
        r = c.post('/api/daily-challenge/submit', json={
            'submission_id':'p0a-unauthorized-new', 'correct':True,
            'mode':'legacy', 'moves':[{'x':0,'y':0},{'x':2,'y':2}]})
        assert r.status_code == 409
        assert counts(fx) == dict.fromkeys(counts(fx), 0)
    if bits[0]:
        d = c.get('/api/daily-challenge/today').json
        assert d['board_only'] and 'B[aa]' not in d['content'] and 'B[cc]' not in d['content']


@pytest.mark.parametrize('value', ['typo', 'enabled', 'yes', '2', 'none'])
def test_unrecognized_flag_is_hold(value):
    for key in DAILY_FLAGS:
        assert daily_mode({key:value}) == 'hold'


def test_capability_requires_real_session_and_never_sets_flags(fx):
    c = fx[0].test_client()
    r = c.get('/api/g076/daily/capability?user_id=7&mode=legacy')
    assert r.status_code == 401 and 'no-store' in r.headers['Cache-Control']
    assert fx[1]['environ'] == {}
    for uid in (True, '7', 0, -1):
        with c.session_transaction() as s:
            s['user_id'] = uid
        assert c.get('/api/g076/daily/capability').status_code == 401


def test_off_real_judge_badges_xp_replay_after_flags_change_and_other_user(fx):
    c = login(fx)
    d = c.get('/api/daily-challenge/today').json
    assert 'B[aa]' in d['content'] and d['attempt_token']
    body = {'submission_id':'p0a-response-loss', 'attempt_token':d['attempt_token'],
            'moves':[{'x':0,'y':0},{'x':2,'y':2}], 'correct':False}
    r = c.post('/api/daily-challenge/submit', json=body)
    assert r.status_code == 200, r.json
    assert r.json['server_correct'] and r.json['xp_awarded'] == 50
    assert {b['id'] for b in r.json['new_badges']} == {'daily_first','daily_ace'}
    before = counts(fx)
    # Lost response retry remains the same durable receipt through every mode.
    for bits in itertools.product((False, True), repeat=3):
        fx[1]['environ'].update(dict(zip(DAILY_FLAGS, ('on' if b else 'off' for b in bits))))
        assert c.post('/api/daily-challenge/submit', json=body).json == r.json
        # Client correct is diagnostic, not in the authoritative idempotency payload.
        assert c.post('/api/daily-challenge/submit', json={**body,'correct':True}).json == r.json
        # A changed move sequence under the same receipt is a real conflict.
        assert c.post('/api/daily-challenge/submit', json={**body,'moves':[{'x':3,'y':3}]}).status_code == 409
        assert counts(fx) == before
    fx[1]['environ'].clear()
    assert c.get('/api/daily-challenge/today').json['user_submitted']
    assert c.post('/api/daily-challenge/submit', json={**body,'submission_id':'p0a-second-same-day'}).status_code == 409
    other = login(fx,8)
    assert other.post('/api/daily-challenge/submit', json=body).status_code == 409
    other_data = other.get('/api/daily-challenge/today').json
    # Even correct:true cannot award XP for a wrong actual sequence.
    wrong = other.post('/api/daily-challenge/submit', json={**body,
        'attempt_token':other_data['attempt_token'], 'moves':[{'x':3,'y':3}], 'correct':True})
    assert wrong.status_code == 200, wrong.json
    assert not wrong.json['server_correct'] and wrong.json['xp_awarded'] == 0
    with fx[2]() as conn:
        assert conn.execute('SELECT xp FROM user_stats WHERE user_id=7').fetchone()['xp'] == 50
        assert conn.execute('SELECT xp FROM user_stats WHERE user_id=8').fetchone() is None
        assert conn.execute('SELECT COUNT(*) FROM review_log').fetchone()[0] == 2


def test_actual_history_route_and_privacy_projection(fx):
    day = (datetime.date.today()-datetime.timedelta(days=1)).isoformat()
    with fx[3]() as conn:
        conn.execute('INSERT INTO daily_challenge(challenge_date,question_id,set_by,note) VALUES(?,?,?,?)',
                     (day,301,'fixture','private-note'))
        conn.execute('INSERT INTO daily_challenge_log(user_id,challenge_date,question_id,correct,submitted_at) VALUES(7,?,301,1,?)',(day,day))
    c = login(fx)
    assert c.get('/api/daily-challenge/history').json['history'][0]['user_correct']
    assert 'B[aa]' in c.get('/api/daily-challenge/history/'+day).json['content']
    fx[1]['environ']['G076_ANSWER_PRIVACY_ENFORCED'] = 'true'
    d = c.get('/api/daily-challenge/history/'+day).json
    assert d['board_only'] and 'B[aa]' not in d['content'] and d['note'] is None


def test_actual_live_static_and_baked_resolver(tmp_path, monkeypatch):
    import os
    from flask import Flask, send_file, send_from_directory
    from g076_daily_fixture import ROOT, load_functions
    app = Flask('p0a-static', root_path=str(ROOT))
    live = tmp_path/'live'
    live.mkdir()
    name = 'daily_challenge_legacy.html'
    original = (ROOT/name).read_bytes()
    (live/name).write_bytes(original)
    ns = {'os':os, 'app':app, 'send_file':send_file,
          'send_from_directory':send_from_directory,
          'LIVE_STATIC_ROOT_ENV_VAR':'GO_ODYSSEY_LIVE_STATIC_ROOT'}
    load_functions(ROOT/'app.py', {'_LIVE_STATIC_ELIGIBLE_FILES',
        '_get_live_static_root','_resolve_live_static_path','_serve_live_static_or_baked',
        'daily_challenge_legacy_page'}, ns)
    app.add_url_rule('/daily_challenge_legacy.html', view_func=ns['daily_challenge_legacy_page'])
    c = app.test_client()
    monkeypatch.setenv('GO_ODYSSEY_LIVE_STATIC_ROOT', str(live))
    assert ns['_resolve_live_static_path'](name, ns['_LIVE_STATIC_ELIGIBLE_FILES']) == str(live/name)
    assert c.get('/daily_challenge_legacy.html').data == original
    (live/name).unlink()
    assert c.get('/daily_challenge_legacy.html').data == original
    monkeypatch.delenv('GO_ODYSSEY_LIVE_STATIC_ROOT')
    assert c.get('/daily_challenge_legacy.html').data == original
