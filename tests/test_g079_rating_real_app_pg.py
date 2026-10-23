"""G079 C: REAL app.py + real Flask routes + disposable PostgreSQL (opt-in).

Runs only when PG_DSN names a g079_c_* database on the isolated container
(tests/g079_rating_real_app_boot.verify_isolated). Without it the module SKIPS,
and a skip is NOT evidence. Run it in its own process: it imports app.py with
DATABASE_URL bound to that disposable database.

The Rating flag is read live from os.environ by the installed guard/blueprint,
so each test sets the flags it needs.
"""
import json
import os
import re
from pathlib import Path
import tempfile
import time

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get('PG_DSN'),
                                reason='PG_DSN missing: real-app PG suite NOT_EXECUTED (not PASS)')

ROOT = Path(__file__).resolve().parents[1]
RATING, PRIVACY = 'G076_RATING_STEPS_ENABLED', 'G076_ANSWER_PRIVACY_ENFORCED'
HOLD = 'rating_steps_required'


@pytest.fixture(scope='module')
def real():
    import g079_rating_real_app_boot as boot
    corpus = Path(tempfile.mkdtemp(prefix='g079-c-corpus-')) / 'questions.json'
    app = boot.boot(corpus)
    users = {name: boot.seed_user(app, name) for name in ('g079alice', 'g079bob', 'g079carol', 'g079dave')}
    saved = {k: os.environ.get(k) for k in (RATING, PRIVACY)}
    yield app, boot, users
    for k, v in saved.items():
        os.environ[k] = v if v is not None else ''


@pytest.fixture
def flags():
    def set_flags(rating, privacy='off'):
        os.environ[RATING], os.environ[PRIVACY] = rating, privacy
    yield set_flags
    set_flags('off', 'off')


def login(app, users, name):
    client = app.app.test_client()
    uid, password = users[name]
    r = client.post('/api/auth/login', json={'username': name, 'password': password})
    assert r.status_code == 200 and r.json['ok'], r.get_data(as_text=True)
    return client, uid


def assert_board_only(question):
    assert question['board_only'] is True
    assert not re.search(r';\s*[BW]\[', question['content']), question['content']
    assert not {'token', 'accepted_moves', 'katago_best_move', 'solution', 'answer_tree'} & set(question)


def solution_moves(app, q):
    """Correct line in the DISPLAYED orientation (what a player would click)."""
    from sgf_point_transform import transform_sgf
    pool_q = next(p for p in app._RT_POOL if p['id'] == q['id'])
    sgf = transform_sgf(pool_q['content'], q['transform_index'])
    return [dict(x=ord(x) - 97, y=ord(y) - 97) for x, y in re.findall(r';B\[([a-z])([a-z])\]', sgf)]


def step(client, opened, action, move=None):
    s = opened['question']['step']
    body = dict(session_id=opened['session_id'], attempt_id=s['attempt_id'], nonce=s['nonce'], action=action)
    if move:
        body['move'] = move
    return body, client.post('/api/g076/rating/step', json=body)


def expire_deadline(app, attempt_id):
    """Simulate the clock passing the SERVER deadline (pytest only; the Chrome
    run waits real time). Only the stored deadline moves; nothing else."""
    with app.get_db() as conn:
        state = json.loads(conn.execute('SELECT state_json FROM g076_rating_attempts WHERE id=?',
                                        (attempt_id,)).fetchone()[0])
        state['deadline'] = time.time() - 1
        conn.execute('UPDATE g076_rating_attempts SET state_json=? WHERE id=?',
                     (json.dumps(state, sort_keys=True, separators=(',', ':')), attempt_id))
        conn.commit()


def counts(app):
    with app.get_db() as conn:
        return {t: conn.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0]
                for t in ('rating_test_sessions', 'rating_test_responses', 'g076_rating_events',
                          'g076_rating_attempts', 'mistake_log', 'adventure_zone_unlocks')}


def test_off_legacy_trial_unchanged(real, flags):
    app, boot, users = real
    flags('off')
    client, uid = login(app, users, 'g079alice')
    cap = client.get('/api/g076/rating/capability')
    assert (cap.status_code, cap.json['mode']) == (200, 'legacy')
    before = counts(app)
    r = client.post('/api/rating_test/start', json={'trigger': 'manual'})
    assert r.status_code == 200, r.get_data(as_text=True)
    q = r.json['question']
    assert 'board_only' not in q and ';B[' in q['content']  # legacy payload unchanged
    moves = solution_moves(app, q)
    a = client.post('/api/rating_test/answer', json=dict(session_id=r.json['session_id'], question_id=q['id'],
                    question_token=q['token'], correct=False, moves=moves, response_ms=3000))
    assert a.status_code == 200 and a.json['correct'] is True  # server judge overrides client flag
    after = counts(app)
    assert after['rating_test_responses'] == before['rating_test_responses'] + 1
    assert after['g076_rating_events'] == before['g076_rating_events']


def test_on_legacy_routes_fail_closed_without_writes(real, flags):
    app, boot, users = real
    flags('off')
    client, uid = login(app, users, 'g079bob')
    legacy = client.post('/api/rating_test/start', json={'trigger': 'placement'}).json
    flags('on')
    before = counts(app)
    q = legacy['question']
    forged = dict(session_id=legacy['session_id'], question_id=q['id'], question_token=q['token'],
                  correct=True, moves=solution_moves(app, q), response_ms=3000)
    attempts = [client.post('/api/rating_test/start', json={'trigger': 'manual', 'init_elo': 2600}),
                client.post('/api/rating_test/answer', json=forged),
                client.post('/api/rating_test/answer', data=''),
                client.get('/api/rating_test/resume/' + legacy['session_id']),
                client.post('/api/rating_test/placement_finish', json={'session_id': legacy['session_id']})]
    for r in attempts:
        assert (r.status_code, r.json['error']) == (503, HOLD), r.get_data(as_text=True)
        assert 'no-store' in r.headers['Cache-Control']
        assert ';B[' not in r.get_data(as_text=True)
    assert counts(app) == before
    assert client.get('/api/rating_test/pool_info').status_code == 200


def test_on_steps_payload_judging_resume_and_retry(real, flags):
    app, boot, users = real
    flags('on', 'off')
    client, uid = login(app, users, 'g079carol')
    assert client.get('/api/g076/rating/capability').json['mode'] == 'steps'
    r = client.post('/api/g076/rating/start', json={'trigger': 'manual', 'init_elo': 2600})
    assert (r.status_code, r.json['error']) == (400, 'rating_untrusted_start_fields')
    opened = client.post('/api/g076/rating/start', json={'trigger': 'manual'}).json
    assert opened['cur_rating'] == 1500.0  # no browser Elo authority
    assert_board_only(opened['question'])
    moves = solution_moves(app, opened['question'])
    before = counts(app)
    _, r = step(client, opened, 'move', moves[0])
    assert r.json['status'] == 'CONTINUE' and len(r.json['played']) == 2
    assert counts(app)['rating_test_responses'] == before['rating_test_responses']
    resumed = client.get('/api/g076/rating/resume/' + opened['session_id']).json
    assert resumed['question']['step']['nonce'] == r.json['nonce']  # refresh keeps the live nonce
    assert_board_only(resumed['question'])
    body, final = step(client, resumed, 'move', moves[1])
    assert final.json['status'] == 'CORRECT' and final.json['result']['correct'] is True
    assert_board_only(final.json['result']['question'])
    snap = counts(app)
    retry = client.post('/api/g076/rating/step', json=body)  # network retry, same nonce/body
    assert retry.json == final.json and counts(app) == snap
    conflict = client.post('/api/g076/rating/step', json=dict(body, action='give_up', move=None))
    assert conflict.status_code in (400, 409) and counts(app) == snap
    assert snap['rating_test_responses'] == before['rating_test_responses'] + 1


def test_on_timeout_forfeit_and_late_move_settle_once(real, flags):
    app, boot, users = real
    flags('on', 'off')
    client, uid = login(app, users, 'g079dave')
    opened = client.post('/api/g076/rating/start', json={'trigger': 'manual'}).json
    # early timeout is refused
    before = counts(app)
    _, r = step(client, opened, 'timeout')
    assert (r.status_code, r.json['error']) == (409, 'rating_timeout_not_due') and counts(app) == before
    # give_up forfeit
    _, r = step(client, opened, 'give_up')
    assert r.json['status'] == 'INCORRECT' and r.json['result']['correct'] is False
    assert counts(app)['rating_test_responses'] == before['rating_test_responses'] + 1
    current = r.json['result']
    # deadline timeout after one committed move
    moves = solution_moves(app, current['question'])
    _, r = step(client, current, 'move', moves[0])
    assert r.json['status'] == 'CONTINUE'
    current = client.get('/api/g076/rating/resume/' + current['session_id']).json
    expire_deadline(app, current['question']['step']['attempt_id'])
    _, r = step(client, current, 'timeout')
    assert r.json['status'] == 'INCORRECT' and len(r.json['played']) == 2
    current = r.json['result']
    # late (correct!) move after the deadline is a timeout, never judged
    moves = solution_moves(app, current['question'])
    expire_deadline(app, current['question']['step']['attempt_id'])
    body, r = step(client, current, 'move', moves[0])
    assert r.json['status'] == 'INCORRECT' and r.json['played'] == []
    snap = counts(app)
    assert client.post('/api/g076/rating/step', json=body).json == r.json and counts(app) == snap
    rows = boot.effects(app, current['session_id'])['responses']
    assert [x['correct'] for x in rows] == [0, 0, 0]
    assert all(x['ability_after'] < x['ability_before'] for x in rows)


def run_trial(app, client, trigger):
    opened = client.post('/api/g076/rating/start', json={'trigger': trigger}).json
    current, rounds = opened, 0
    while not current.get('finished'):
        moves = solution_moves(app, current['question'])
        assert current['question']['id'] not in (929001, 929002)
        if rounds % 2 == 0:
            _, r = step(client, current, 'move', moves[0])
            current = client.get('/api/g076/rating/resume/' + current['session_id']).json
            body, r = step(client, current, 'move', moves[1])
        else:
            body, r = step(client, current, 'give_up')
        assert r.status_code == 200, r.get_data(as_text=True)
        current, rounds = r.json['result'], rounds + 1
    return opened['session_id'], current, body, r.json, rounds


def test_full_manual_and_placement_trials_settle_elo_once(real, flags):
    app, boot, users = real
    flags('on', 'off')
    for name, trigger in (('g079alice', 'manual'), ('g079bob', 'placement')):
        client, uid = login(app, users, name)
        sid, final, body, receipt, rounds = run_trial(app, client, trigger)
        fx = boot.effects(app, sid)
        assert len(fx['responses']) == rounds == final['rounds_used']
        assert rounds == (7 if trigger == 'placement' else final['rounds_used'])
        user = next(u for u in fx['users'] if u['id'] == uid)
        assert user['elo_rating'] == final['cur_rating']
        snap = counts(app)
        assert client.post('/api/g076/rating/step', json=body).json == receipt  # final retry
        assert counts(app) == snap
        assert boot.effects(app)['users'] == fx['users']
        if trigger == 'placement':
            assert user['elo_provisional'] == 1
            assert {u['source'] for u in fx['unlocks'] if u['user_id'] == uid} == {'placement_test'}
        result = client.get('/api/rating_test/result/' + sid)
        assert result.status_code == 200 and result.json['final_rating'] == final['cur_rating']
        assert ';B[' not in result.get_data(as_text=True)


def test_step_ineligible_questions_never_selected(real, flags):
    app, boot, users = real
    flags('on', 'off')
    services = app._g078_rating_services
    assert services.ineligible_ids() == boot.INELIGIBLE_IDS
    seen = set()
    for _ in range(40):
        r = app.app.test_client().post('/api/g076/rating/start', json={'trigger': 'manual'})
        assert r.status_code == 200, r.get_data(as_text=True)
        seen.add(r.json['question']['id'])
    assert not seen & boot.INELIGIBLE_IDS
    fx = boot.effects(app)
    assert not {s['current_question_id'] for s in fx['sessions']} & boot.INELIGIBLE_IDS - {None}


def test_anonymous_trial_claim_under_on(real, flags):
    app, boot, users = real
    flags('on', 'off')
    anon = app.app.test_client()
    sid, final, *_ = run_trial(app, anon, 'placement')
    uid, password = boot.seed_user(app, 'g079erin')
    client = app.app.test_client()  # signs up/logs in after the anonymous trial
    assert client.post('/api/auth/login', json={'username': 'g079erin', 'password': password}).json['ok']
    r = client.post('/api/rating_test/claim_anon', json={'session_id': sid})
    assert r.status_code == 200 and r.json['cur_rating'] == final['cur_rating'], r.get_data(as_text=True)
    assert client.post('/api/rating_test/claim_anon', json={'session_id': sid}).status_code == 409
    user = next(u for u in boot.effects(app)['users'] if u['id'] == uid)
    assert user['elo_rating'] == final['cur_rating']


OTHER_MODE_PROBES = (
    ('GET', '/api/mistakes', None), ('GET', '/api/mistakes/stats', None),
    ('GET', '/api/srs/due', None), ('GET', '/api/srs/stats', None),
    ('GET', '/api/training/daily', None), ('GET', '/api/daily-challenge/today', None),
    ('GET', '/api/adventure/map-state', None), ('GET', '/api/adventure/progress', None),
    ('GET', '/api/adventure/map-battles/v2/steps/capability', None),
    ('GET', '/api/grimoire/training/daily', None), ('GET', '/api/grimoire/flux/today', None),
    ('GET', '/api/g076/mistakes/capability', None), ('GET', '/api/g076/daily/capability', None),
    ('GET', '/api/challenges/friend/list', None), ('GET', '/api/quest-board', None),
    ('POST', '/api/srs/review', {}), ('POST', '/api/training/answer', {}),
    ('POST', '/api/challenges/friend/1/answer', {}), ('POST', '/api/adventure/boss/finish', {}),
)


def test_rating_on_alone_does_not_change_other_modes(real, flags):
    app, boot, users = real
    client, uid = login(app, users, 'g079carol')
    observed = {}
    for rating in ('off', 'on', 'off'):
        flags(rating, 'off')
        for method, path, body in OTHER_MODE_PROBES:
            r = client.open(path, method=method, json=body)
            observed.setdefault((method, path), []).append(r.status_code)
            assert HOLD not in r.get_data(as_text=True), (rating, path)
    out = os.environ.get('G079_EVIDENCE_DIR')
    if out:
        Path(out, 'other_modes_status.json').write_text(json.dumps(
            {' '.join(k): v for k, v in observed.items()}, indent=1), encoding='utf-8')
    changed = {k: v for k, v in observed.items() if len(set(v)) != 1}
    assert not changed, changed
    assert all(v[0] < 500 for v in observed.values()), observed


def test_step_ineligible_exclusion_is_load_bearing(real, flags, monkeypatch):
    """Deterministic: a pool where ineligible questions are the closest match.

    Negative control first: with the exclusion disabled the step path hands
    out an ineligible question and the trial HOLDs (the pre-G079 defect).
    """
    app, boot, users = real
    flags('on', 'off')
    services = app._g078_rating_services
    app._ensure_rt_pool()  # build once so the patched pool is not rebuilt
    full = app._RT_POOL
    small = [dict(q) for q in full if q['id'] in boot.INELIGIBLE_IDS]
    small += [dict(q) for q in full if q['id'] not in boot.INELIGIBLE_IDS][:1]
    for q in small:
        q['rating'] = 1500.0
    monkeypatch.setattr(app, '_RT_POOL', small)
    client = app.app.test_client()
    monkeypatch.setattr(services, 'ineligible_ids', lambda: frozenset())
    outcomes = {client.post('/api/g076/rating/start', json={'trigger': 'manual'}).status_code for _ in range(30)}
    assert 422 in outcomes  # defect reproduced without the exclusion
    monkeypatch.undo()
    monkeypatch.setattr(app, '_RT_POOL', small)
    flags('on', 'off')
    assert services.ineligible_ids() == boot.INELIGIBLE_IDS
    for _ in range(30):
        r = client.post('/api/g076/rating/start', json={'trigger': 'manual'})
        assert r.status_code == 200 and r.json['question']['id'] not in boot.INELIGIBLE_IDS
    # Writer side: answering the only eligible question must not hand out an
    # ineligible next question; the session finishes instead of HOLDing.
    _, r = step(client, r.json, 'give_up')
    assert r.status_code == 200 and r.json['result']['finished'] is True
