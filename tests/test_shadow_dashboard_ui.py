import json
from pathlib import Path

import pytest

import shadow_dashboard


def _write_jsonl(path: Path, rows):
    path.write_text(
        ''.join(json.dumps(row) + '\n' for row in rows),
        encoding='utf-8',
    )


@pytest.fixture(scope='module')
def app_module():
    import app as app_module
    return app_module


def test_recent_shadow_dashboard_data_empty_file(tmp_path):
    path = tmp_path / 'shadow_events.jsonl'
    path.write_text('', encoding='utf-8')

    payload = shadow_dashboard.recent_shadow_dashboard_data(path=str(path), limit=50)

    assert payload['summary']['total_events'] == 0
    assert payload['summary']['success'] == 0
    assert payload['summary']['parser_failed'] == 0
    assert payload['summary']['exception'] == 0
    assert payload['recent_events'] == []
    assert payload['parser_failures'] == []
    assert set(payload['routes']) >= set(shadow_dashboard.EXPECTED_ROUTES)


def test_recent_shadow_dashboard_data_sorts_and_summarizes(tmp_path):
    path = tmp_path / 'shadow_events.jsonl'
    _write_jsonl(path, [
        {
            'schema_version': 'shadow-v3',
            'created_at': '2026-07-11T00:00:00Z',
            'route': '/api/rating_test/answer',
            'request_id': 'req-1',
            'parser_status': 'ok',
            'latency_ms': 10,
            'entry_point': 'rating_test',
        },
        {
            'schema_version': 'shadow-v3',
            'created_at': '2026-07-11T01:00:00Z',
            'route': '/api/daily-challenge/submit',
            'request_id': 'req-2',
            'parser_status': 'failed',
            'parser_failure_reason': 'parse failed: ValueError',
            'latency_ms': 20,
            'entry_point': 'daily_challenge',
        },
        {
            'schema_version': 'shadow-v3',
            'created_at': '2026-07-11T02:00:00Z',
            'route': '/api/challenges/friend/3/answer',
            'request_id': 'req-3',
            'parser_status': 'ok',
            'latency_ms': 30,
            'entry_point': 'friend_challenge',
            'exception_class': 'RuntimeError',
            'exception_message': 'safe failure',
        },
    ])

    payload = shadow_dashboard.recent_shadow_dashboard_data(path=str(path), limit=50)

    assert payload['summary']['total_events'] == 3
    assert payload['summary']['success'] == 1
    assert payload['summary']['parser_failed'] == 1
    assert payload['summary']['exception'] == 1
    assert payload['summary']['average_latency_ms'] == 20.0
    assert [event['request_id'] for event in payload['recent_events']] == ['req-3', 'req-2', 'req-1']
    assert payload['routes']['/api/rating_test/answer']['event_count'] == 1
    assert payload['routes']['/api/daily-challenge/submit']['parser_failed'] == 1
    assert payload['routes']['/api/challenges/friend/<int:cid>/answer']['average_latency_ms'] == 30.0
    assert payload['parser_failures'][0]['request_id'] == 'req-2'
    assert payload['parser_failures'][0]['details']['parser_failure_reason'] == 'parse failed: ValueError'


def test_recent_shadow_dashboard_data_is_bounded_to_limit(tmp_path):
    path = tmp_path / 'shadow_events.jsonl'
    rows = []
    for idx in range(6):
        rows.append({
            'schema_version': 'shadow-v3',
            'created_at': f'2026-07-11T0{idx}:00:00Z',
            'route': '/api/rating_test/answer',
            'request_id': f'req-{idx}',
            'parser_status': 'ok',
        })
    _write_jsonl(path, rows)

    payload = shadow_dashboard.recent_shadow_dashboard_data(path=str(path), limit=3)

    assert payload['returned_events'] == 3
    assert [event['request_id'] for event in payload['recent_events']] == ['req-5', 'req-4', 'req-3']


def test_recent_dashboard_api_requires_admin(app_module):
    client = app_module.app.test_client()

    response = client.get('/api/admin/shadow/dashboard/recent')

    assert response.status_code == 401


def test_recent_dashboard_api_returns_recent_payload(tmp_path, monkeypatch, app_module):
    path = tmp_path / 'shadow_events.jsonl'
    _write_jsonl(path, [{
        'schema_version': 'shadow-v3',
        'created_at': '2026-07-11T02:00:00Z',
        'route': '/api/daily-challenge/submit',
        'request_id': 'req-daily',
        'parser_status': 'failed',
        'parser_failure_reason': 'parse failed: ValueError',
        'latency_ms': 17,
        'entry_point': 'daily_challenge',
    }])
    monkeypatch.setattr(shadow_dashboard, 'DEFAULT_SHADOW_EVENTS_PATH', str(path))

    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 11
        sess['is_admin'] = True

    response = client.get('/api/admin/shadow/dashboard/recent?limit=25')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['limit'] == 25
    assert payload['summary']['total_events'] == 1
    assert payload['summary']['parser_failed'] == 1
    assert payload['routes']['/api/daily-challenge/submit']['event_count'] == 1
    assert payload['recent_events'][0]['request_id'] == 'req-daily'


def test_shadow_dashboard_page_requires_admin(app_module):
    client = app_module.app.test_client()

    response = client.get('/admin/shadow-dashboard')

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/login')


def test_shadow_dashboard_page_contains_read_only_ui(app_module):
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 15
        sess['is_admin'] = True

    response = client.get('/admin/shadow-dashboard')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Shadow Dashboard' in html
    assert 'Recent Events' in html
    assert 'Route Statistics' in html
    assert 'Parser Failure Table' in html
    assert 'request-id-search' in html
    assert '/api/admin/shadow/dashboard/recent?limit=200' in html


def test_shadow_dashboard_ui_doc_contract():
    doc = Path('docs/planning/shadow_dashboard_ui_e25.md').read_text(encoding='utf-8').lower()

    assert 'read-only admin ui' in doc
    assert 'recent events' in doc
    assert 'summary cards' in doc
    assert 'route statistics' in doc
    assert 'parser failure table' in doc
    assert '/api/admin/shadow/dashboard/recent' in doc
    assert '/admin/shadow-dashboard' in doc
