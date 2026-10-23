import concurrent.futures
import json

import pytest

from g076_nonmap_fixture import make_fixture, SECRET
from g076_nonmap_steps import NonMapRejected, open_steps


@pytest.fixture
def fixture(tmp_path):
    return make_fixture(tmp_path/'isolated.sqlite')


def client(fixture, uid=101):
    result = fixture[0].test_client()
    result.post('/fixture/login', json={'uid': uid})
    return result


def start(fixture, flow='practice', token=None, who=None):
    return (who or client(fixture)).post('/api/g076/nonmap/steps/start', json={
        'flow': flow, 'attempt_token': token or fixture[2](flow)})


def play(fixture, cursor, xy=(0, 0), flow='practice', token=None, who=None, extras=None):
    return (who or client(fixture)).post('/api/g076/nonmap/steps', json={
        'flow': flow, 'attempt_token': token or fixture[2](flow),
        'step_index': cursor['step_index'], 'step_nonce': cursor['step_nonce'],
        'move': {'x': xy[0], 'y': xy[1]}, **(extras or {})})


def rows(fixture, table):
    with fixture[3]() as conn:
        return [dict(row) for row in conn.execute('SELECT * FROM ' + table)]


@pytest.mark.parametrize('flow', ['practice', 'daily'])
def test_play_resume_terminal_and_exact_retry(fixture, flow):
    token = fixture[2](flow)
    opened = start(fixture, flow, token)
    assert opened.status_code == 200
    assert opened.headers['Cache-Control'] == 'private, no-store'
    value = opened.get_json()
    assert value['content'] == '(;SZ[5]PL[B]AB[ee])'
    assert 'B[aa]' not in value['content'] and 'B[cc]' not in value['content']
    first = play(fixture, value, flow=flow, token=token).get_json()
    assert first['status'] == 'CONTINUE' and first['opponent_reply'] == [1, 1]
    assert set(first) == {'status', 'step_index', 'opponent_reply', 'step_nonce', 'duplicate'}
    assert rows(fixture, 'fixture_receipts') == []
    resumed = start(fixture, flow, token).get_json()
    assert resumed['step_index'] == 1
    assert resumed['previous_steps'] == [{'player_move': [0, 0], 'opponent_reply': [1, 1]}]
    assert play(fixture, value, flow=flow, token=token).get_json()['duplicate']
    final = play(fixture, first, (2, 2), flow, token)
    assert final.status_code == 200, final.get_json()
    final = final.get_json()
    assert final['status'] == 'CORRECT' and not final['duplicate']
    assert 'step_nonce' not in final
    retry = play(fixture, first, (2, 2), flow, token).get_json()
    assert retry == {**final, 'duplicate': True}
    assert start(fixture, flow, token).get_json() == retry
    assert len(rows(fixture, 'fixture_receipts')) == 1
    if flow == 'practice':
        assert final['settlement']['submission_id'].startswith('practice-v1:')
        assert final['settlement']['srs']['repetitions'] == 1
        assert rows(fixture, 'srs_cards')[0]['progress_credited'] == 0
        assert rows(fixture, 'fixture_daily') == []
    else:
        assert final['settlement']['xp_awarded'] == 75
        assert rows(fixture, 'fixture_daily')[0]['xp'] == 75
    persisted = json.dumps(rows(fixture, 'g076_nonmap_events'))
    assert value['step_nonce'] not in persisted and first['step_nonce'] not in persisted
    assert token not in persisted


@pytest.mark.parametrize('flow', ['practice', 'daily'])
def test_wrong_move_is_terminal_and_cannot_be_corrected(fixture, flow):
    token = fixture[2](flow)
    cursor = start(fixture, flow, token).get_json()
    wrong = play(fixture, cursor, (4, 0), flow, token).get_json()
    assert wrong['status'] == 'INCORRECT'
    assert play(fixture, cursor, (0, 0), flow, token).status_code == 409
    assert len(rows(fixture, 'fixture_receipts')) == 1
    if flow == 'daily':
        assert wrong['settlement']['xp_awarded'] == 0
        new_token = fixture[2](flow)
        assert new_token != token
        assert start(fixture, flow, new_token).get_json()['status'] == 'INCORRECT'
        assert play(fixture, cursor, flow=flow, token=new_token).status_code == 409


@pytest.mark.parametrize('field,value', [('grade', 5), ('correct', True), ('history', []),
    ('moves', []), ('opponent_reply', [1, 1]), ('question_id', 701), ('user_id', 999)])
def test_forbidden_authority_fields(fixture, field, value):
    token = fixture[2]('practice')
    cursor = start(fixture, token=token).get_json()
    assert play(fixture, cursor, token=token, extras={field: value}).status_code == 400
    assert rows(fixture, 'fixture_receipts') == []
    assert rows(fixture, 'g076_nonmap_events') == []


@pytest.mark.parametrize('uid', [None, '101', True, 0, -1])
def test_authentication_required(fixture, uid):
    who = fixture[0].test_client()
    if uid is not None:
        with who.session_transaction() as s:
            s['user_id'] = uid
    assert start(fixture, who=who).status_code == 401


@pytest.mark.parametrize('flow', ['practice', 'daily'])
def test_owner_flow_expiry_rights_revision_and_nonce(fixture, flow):
    token = fixture[2](flow)
    cursor = start(fixture, flow, token).get_json()
    assert start(fixture, flow, token, client(fixture, 202)).status_code == 409
    other = 'daily' if flow == 'practice' else 'practice'
    assert start(fixture, other, token).status_code == 409
    forged = {**cursor, 'step_nonce': 'forged'}
    assert play(fixture, forged, flow=flow, token=token).status_code == 403
    fixture[1]['denied'] = True
    assert play(fixture, cursor, flow=flow, token=token).status_code == 403
    fixture[1]['denied'] = False
    fixture[1]['now'] = 1000000
    assert play(fixture, cursor, flow=flow, token=token).status_code == 409
    fixture[1]['now'] = 101
    fixture[1]['question']['content'] += ' '
    assert play(fixture, cursor, flow=flow, token=token).status_code == 409
    assert rows(fixture, 'g076_nonmap_events') == []


def test_daily_reissued_revision_cannot_reset_cursor(fixture):
    token = fixture[2]('daily')
    start(fixture, 'daily', token)
    fixture[1]['question']['content'] += ' '
    assert start(fixture, 'daily').get_json()['error'] == 'step_session_revision_changed'


def test_practice_identity_change_rejected(fixture):
    token = fixture[2]('practice')
    fixture[1]['identity'] = 'replacement'
    assert start(fixture, token=token).status_code == 409


@pytest.mark.parametrize('key', ['G076_NONMAP_STEPS_ENABLED', 'G076_ANSWER_PRIVACY_ENFORCED'])
@pytest.mark.parametrize('value', [None, 'false', '0', 'yes', 'unknown'])
def test_both_explicit_flags_required(fixture, key, value):
    fixture[1]['environ'].pop(key)
    if value is not None:
        fixture[1]['environ'][key] = value
    assert start(fixture).status_code == 503
    assert rows(fixture, 'g076_nonmap_sessions') == []


@pytest.mark.parametrize('flow', ['lord', 'boss', 'guild', 'rating', 'map', 'Practice'])
def test_unsupported_modes_fail_closed(fixture, flow):
    assert start(fixture, flow, fixture[2]('practice')).status_code == 400


@pytest.mark.parametrize('key', ['accepted_moves', 'accepted_answers', 'katago_best_move'])
def test_unsupported_answer_alternatives_hold(fixture, key):
    fixture[1]['question'][key] = [{'x': 3, 'y': 3}]
    assert start(fixture).status_code == 422
    assert rows(fixture, 'g076_nonmap_sessions') == []


@pytest.mark.parametrize('content', ['(;SZ[5]B[aa])', '(;SZ[5];B[aa]', '(;SZ[5])(;SZ[5])'])
def test_malformed_preview_fails_without_full_source(fixture, content):
    fixture[1]['question']['content'] = content
    response = start(fixture)
    assert response.status_code == 422
    assert content not in response.get_data(as_text=True)


@pytest.mark.parametrize('flag', ['fail_settle', 'unsafe_settle', 'fail_commit'])
@pytest.mark.parametrize('flow', ['practice', 'daily'])
def test_settlement_failure_rolls_back_and_same_request_recovers(fixture, flag, flow):
    token = fixture[2](flow)
    cursor = start(fixture, flow, token).get_json()
    first = play(fixture, cursor, flow=flow, token=token).get_json()
    fixture[1][flag] = True
    failed = play(fixture, first, (2, 2), flow, token)
    assert failed.status_code == 503
    assert 'B[aa]' not in failed.get_data(as_text=True)
    assert rows(fixture, 'fixture_receipts') == []
    assert rows(fixture, 'srs_cards') == []
    assert rows(fixture, 'fixture_daily') == []
    assert rows(fixture, 'g076_nonmap_sessions')[0]['step_index'] == 1
    fixture[1][flag] = False
    assert play(fixture, first, (2, 2), flow, token).get_json()['status'] == 'CORRECT'
    assert len(rows(fixture, 'fixture_receipts')) == 1


def test_missing_adapter_holds_before_any_write(fixture):
    with pytest.raises(NonMapRejected, match='mode_settlement_unavailable'):
        with fixture[4]() as conn:
            ctx = fixture[5](conn, 101, 'practice', fixture[2]('practice'))
            open_steps(conn, ctx, secret=SECRET, settle=None)
    assert rows(fixture, 'g076_nonmap_sessions') == []


@pytest.mark.parametrize('flow', ['practice', 'daily'])
def test_concurrent_terminal_retries_settle_once(fixture, flow):
    token = fixture[2](flow)
    cursor = start(fixture, flow, token).get_json()
    first = play(fixture, cursor, flow=flow, token=token).get_json()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: play(fixture, first, (2, 2), flow, token), range(4)))
    assert all(r.status_code == 200 for r in responses)
    assert sum(not r.get_json()['duplicate'] for r in responses) == 1
    assert len(rows(fixture, 'fixture_receipts')) == 1


def test_ambiguous_tree_and_explicit_failure_policy(fixture):
    fixture[1]['question']['content'] = '(;SZ[5]PL[B](;B[aa])(;B[cc]))'
    token = fixture[2]('practice')
    cursor = start(fixture, token=token).get_json()
    assert play(fixture, cursor, token=token).status_code == 422
    assert rows(fixture, 'fixture_receipts') == []
    fixture[1]['question'].update(answer_policy='g065-explicit-v1',
        content='(;SZ[5]PL[B](;B[aa]C[G065:INCORRECT])(;B[cc]C[G065:CORRECT]))')
    token = fixture[2]('practice')
    cursor = start(fixture, token=token).get_json()
    assert play(fixture, cursor, token=token).get_json()['status'] == 'INCORRECT'


def test_practice_opaque_revision_is_not_content_identity(fixture):
    fixture[1]['question']['question_revision'] = 'editorial-r1'
    assert start(fixture).get_json()['error'] == 'practice_content_revision_binding_unavailable'
    assert rows(fixture, 'g076_nonmap_sessions') == []


def test_rights_checked_even_for_committed_replay(fixture):
    token = fixture[2]('practice')
    cursor = start(fixture, token=token).get_json()
    assert play(fixture, cursor, (3, 3), token=token).status_code == 200
    fixture[1]['denied'] = True
    assert play(fixture, cursor, (3, 3), token=token).status_code == 403
    assert start(fixture, token=token).status_code == 403


def test_practice_nonce_cannot_be_used_by_another_attempt(fixture):
    first, second = fixture[2]('practice'), fixture[2]('practice')
    cursor = start(fixture, token=first).get_json()
    start(fixture, token=second)
    assert play(fixture, cursor, token=second).status_code == 403
    assert rows(fixture, 'fixture_receipts') == []


def test_daily_reissued_token_resumes_same_open_step(fixture):
    first = fixture[2]('daily')
    cursor = start(fixture, 'daily', first).get_json()
    response = play(fixture, cursor, flow='daily', token=first).get_json()
    refreshed = start(fixture, 'daily').get_json()
    assert refreshed['step_nonce'] == response['step_nonce']
    assert refreshed['step_index'] == 1
    assert len(rows(fixture, 'g076_nonmap_sessions')) == 1


@pytest.mark.parametrize('xy', [(True, 0), (-1, 0), (5, 0), (0.1, 0), ('0', 0)])
def test_invalid_coordinates_do_not_consume_step(fixture, xy):
    token = fixture[2]('practice')
    cursor = start(fixture, token=token).get_json()
    assert play(fixture, cursor, xy, token=token).status_code == 400
    assert rows(fixture, 'g076_nonmap_events') == []


def test_nonascii_nonce_and_stale_index(fixture):
    token = fixture[2]('practice')
    cursor = start(fixture, token=token).get_json()
    assert play(fixture, {**cursor, 'step_nonce': '偽造'}, token=token).status_code == 403
    assert play(fixture, {**cursor, 'step_index': 1}, token=token).status_code == 403


def test_server_judge_disagreement_never_settles(fixture, monkeypatch):
    from map_battle_runtime import JudgeOutcome
    monkeypatch.setattr('g076_nonmap_steps.judge_practice_answer',
        lambda *args: JudgeOutcome('CORRECT', 5, 'map-battle-judge-v1', 'synthetic'))
    token = fixture[2]('practice')
    cursor = start(fixture, token=token).get_json()
    response = play(fixture, cursor, (3, 3), token=token)
    assert response.get_json()['error'] == 'step_final_judge_disagreement'
    assert response.status_code == 503
    assert rows(fixture, 'fixture_receipts') == []
    assert rows(fixture, 'g076_nonmap_events') == []


def test_missing_schema_fails_closed(fixture):
    with fixture[3]() as conn:
        conn.execute('DROP TABLE g076_nonmap_events')
        conn.execute('DROP TABLE g076_nonmap_sessions')
    response = start(fixture)
    assert response.status_code == 503
    assert response.get_json() == {'error': 'step_backend_unavailable'}


def test_cross_origin_rejected(fixture):
    response = client(fixture).post('/api/g076/nonmap/steps/start',
        json={'flow': 'practice', 'attempt_token': fixture[2]('practice')},
        headers={'Origin': 'https://unrelated.invalid'})
    assert response.status_code == 403
    assert response.headers['Cache-Control'] == 'private, no-store'
    assert rows(fixture, 'g076_nonmap_sessions') == []


def test_bridge_is_not_registered_in_product():
    from g076_nonmap_fixture import ROOT
    source = (ROOT/'app.py').read_text(encoding='utf-8')
    assert 'g076_nonmap_steps' not in source
    assert 'g076_nonmap_step_client.js' not in (ROOT/'index.html').read_text(encoding='utf-8')


def test_two_different_concurrent_answers_cannot_both_win(fixture):
    token = fixture[2]('daily')
    cursor = start(fixture, 'daily', token).get_json()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda xy: play(fixture, cursor, xy, 'daily', token),
                                  [(0, 0), (3, 3)]))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert len(rows(fixture, 'g076_nonmap_events')) == 1
    assert len(rows(fixture, 'fixture_receipts')) <= 1
