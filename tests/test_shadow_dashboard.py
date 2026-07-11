import json
import re
import sys
import types
from pathlib import Path

import pytest

import shadow_dashboard


def _install_app_import_stubs():
    if 'katago_explain' not in sys.modules:
        module = types.ModuleType('katago_explain')
        module.KataGoExplainer = type('KataGoExplainer', (), {})
        sys.modules['katago_explain'] = module
    if 'explain_overrides' not in sys.modules:
        module = types.ModuleType('explain_overrides')
        module.get_override = lambda *args, **kwargs: None
        sys.modules['explain_overrides'] = module
    if 'grimoire_api' not in sys.modules:
        from flask import Blueprint
        module = types.ModuleType('grimoire_api')
        module.grimoire_bp = Blueprint('grimoire_stub', __name__)
        sys.modules['grimoire_api'] = module
    if 'question_taxonomy' not in sys.modules:
        module = types.ModuleType('question_taxonomy')
        module.get_taxonomy = lambda *args, **kwargs: {}
        sys.modules['question_taxonomy'] = module
    if 'monster_taxonomy' not in sys.modules:
        module = types.ModuleType('monster_taxonomy')
        module.get_monster_taxonomy = lambda *args, **kwargs: {}
        module.mark_encounters = lambda *args, **kwargs: None
        sys.modules['monster_taxonomy'] = module
    if 'chapter_i18n' not in sys.modules:
        module = types.ModuleType('chapter_i18n')
        module.localize_topic = lambda *args, **kwargs: ''
        module.localize_level = lambda *args, **kwargs: ''
        sys.modules['chapter_i18n'] = module
    if 'backend_i18n' not in sys.modules:
        module = types.ModuleType('backend_i18n')
        module.badge_en = lambda *args, **kwargs: ''
        module.skill_node_en = lambda *args, **kwargs: ''
        module.title_en = lambda *args, **kwargs: ''
        sys.modules['backend_i18n'] = module
    if 'sgf_engine' not in sys.modules:
        sys.modules['sgf_engine'] = types.ModuleType('sgf_engine')
    if 'sgf_engine.parser' not in sys.modules:
        sys.modules['sgf_engine.parser'] = types.ModuleType('sgf_engine.parser')
    if 'sgf_engine.parser.sgf_parser' not in sys.modules:
        module = types.ModuleType('sgf_engine.parser.sgf_parser')
        module.parse_sgf = lambda *args, **kwargs: None
        sys.modules['sgf_engine.parser.sgf_parser'] = module


def _write_jsonl(path: Path, rows):
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')


def _read_static_html():
    return Path('shadow_dashboard.html').read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def app_module():
    _install_app_import_stubs()
    import app as app_module
    return app_module


def test_recent_shadow_dashboard_data_missing_file(tmp_path):
    path = tmp_path / 'missing-shadow.jsonl'
    payload = shadow_dashboard.recent_shadow_dashboard_data(path=str(path), limit=25)

    assert payload['summary']['total_events'] == 0
    assert payload['returned_events'] == 0
    assert payload['recent_events'] == []
    assert payload['parser_failures'] == []
    assert set(payload['routes']) >= set(shadow_dashboard.EXPECTED_ROUTES)


def test_recent_shadow_dashboard_data_empty_file(tmp_path):
    path = tmp_path / 'shadow_events.jsonl'
    path.write_text('', encoding='utf-8')

    payload = shadow_dashboard.recent_shadow_dashboard_data(path=str(path), limit=25)

    assert payload['summary']['total_events'] == 0
    assert payload['summary']['success'] == 0
    assert payload['summary']['parser_failed'] == 0
    assert payload['summary']['exception'] == 0
    assert payload['recent_events'] == []


def test_recent_shadow_dashboard_data_valid_shadow_v3_and_e24a_error(tmp_path):
    path = tmp_path / 'shadow_events.jsonl'
    _write_jsonl(path, [{
        'schema_version': 'shadow-v3',
        'timestamp': '2026-07-11T02:00:00Z',
        'route': '/api/daily-challenge/submit',
        'request_id': 'req-e24a',
        'parser_status': 'failed',
        'shadow_judgement': 'error',
        'reason': 'sgf_engine unavailable or failed: RuntimeError',
        'latency': 18.5,
        'entry_point': 'daily_challenge',
        'exception_class': 'RuntimeError',
        'exception_message': 'boom',
    }])

    payload = shadow_dashboard.recent_shadow_dashboard_data(path=str(path), limit=25)

    event = payload['recent_events'][0]
    assert payload['summary']['total_events'] == 1
    assert payload['summary']['parser_failed'] == 1
    assert payload['summary']['judgement_error'] == 1
    assert event['schema_version'] == 'shadow-v3'
    assert event['shadow_judgement'] == 'error'
    assert event['parser_status'] == 'failed'
    assert event['reason'] == 'sgf_engine unavailable or failed: RuntimeError'
    assert event['latency_ms'] == 18.5
    assert event['details']['schema_version'] == 'shadow-v3'
    assert event['details']['entry_point'] == 'daily_challenge'


def test_recent_shadow_dashboard_data_skips_malformed_and_old_schema(tmp_path):
    path = tmp_path / 'shadow_events.jsonl'
    path.write_text(
        '\n'.join([
            '{"schema_version":"shadow-v2","timestamp":"2026-07-11T00:00:00Z","route":"/api/rating_test/answer","request_id":"old-1","parser_status":"ok","latency_ms":11}',
            'not-json',
            '{"timestamp":"2026-07-11T00:01:00Z","route":"/api/rating_test/answer","request_id":"old-2","match":false,"parser_status":"ok","latency_ms":12}',
        ]) + '\n',
        encoding='utf-8',
    )

    payload = shadow_dashboard.recent_shadow_dashboard_data(path=str(path), limit=25)

    assert payload['invalid_lines'] == 1
    assert payload['summary']['total_events'] == 2
    assert [event['request_id'] for event in payload['recent_events']] == ['old-2', 'old-1']
    assert payload['recent_events'][0]['shadow_judgement'] == 'mismatch'


def test_recent_shadow_dashboard_data_is_bounded_and_newest_first(tmp_path):
    path = tmp_path / 'shadow_events.jsonl'
    rows = []
    for idx in range(6):
        rows.append({
            'schema_version': 'shadow-v3',
            'timestamp': f'2026-07-11T0{idx}:00:00Z',
            'route': '/api/rating_test/answer',
            'request_id': f'req-{idx}',
            'parser_status': 'ok',
            'shadow_judgement': 'match',
            'latency_ms': idx + 1,
        })
    _write_jsonl(path, rows)

    payload = shadow_dashboard.recent_shadow_dashboard_data(path=str(path), limit=3)

    assert payload['returned_events'] == 3
    assert [event['request_id'] for event in payload['recent_events']] == ['req-5', 'req-4', 'req-3']


def test_recent_shadow_dashboard_data_filters(tmp_path):
    path = tmp_path / 'shadow_events.jsonl'
    _write_jsonl(path, [
        {
            'schema_version': 'shadow-v3',
            'timestamp': '2026-07-11T00:00:00Z',
            'route': '/api/rating_test/answer',
            'request_id': 'abc-111',
            'parser_status': 'ok',
            'shadow_judgement': 'match',
            'latency_ms': 11,
        },
        {
            'schema_version': 'shadow-v3',
            'timestamp': '2026-07-11T01:00:00Z',
            'route': '/api/daily-challenge/submit',
            'request_id': 'xyz-222',
            'parser_status': 'failed',
            'shadow_judgement': 'error',
            'reason': 'sgf_engine unavailable or failed: ValueError',
            'latency_ms': 22,
        },
    ])

    filtered = shadow_dashboard.recent_shadow_dashboard_data(
        path=str(path),
        limit=25,
        route='/api/daily-challenge/submit',
        parser_status='failed',
        shadow_judgement='error',
        request_id='xyz',
    )

    assert filtered['returned_events'] == 1
    assert filtered['recent_events'][0]['request_id'] == 'xyz-222'


def test_recent_shadow_dashboard_data_sanitizes_reason(tmp_path):
    path = tmp_path / 'shadow_events.jsonl'
    _write_jsonl(path, [{
        'schema_version': 'shadow-v3',
        'timestamp': '2026-07-11T02:00:00Z',
        'route': '/api/daily-challenge/submit',
        'request_id': 'req-safe',
        'parser_status': 'failed',
        'shadow_judgement': 'error',
        'reason': 'line1\nline2\tline3',
        'exception_class': 'ValueError',
    }])

    payload = shadow_dashboard.recent_shadow_dashboard_data(path=str(path), limit=25)

    assert payload['recent_events'][0]['reason'] == 'line1 line2 line3'
    assert '\n' not in payload['recent_events'][0]['reason']


def test_dashboard_page_requires_admin(app_module):
    client = app_module.app.test_client()
    response = client.get('/admin/shadow-dashboard')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/login')


def test_dashboard_api_requires_admin(app_module):
    client = app_module.app.test_client()
    response = client.get('/api/admin/shadow/dashboard/recent')
    assert response.status_code == 401


def test_dashboard_page_renders_for_admin(app_module):
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 11
        sess['is_admin'] = True

    response = client.get('/admin/shadow-dashboard')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Shadow Dashboard' in html
    assert '/api/admin/shadow/dashboard/recent' in html
    assert 'summary-total-events' in html
    assert 'judgement-filter' in html


def test_dashboard_api_returns_bounded_recent_payload_and_ignores_path(tmp_path, monkeypatch, app_module):
    path = tmp_path / 'shadow_events.jsonl'
    _write_jsonl(path, [
        {
            'schema_version': 'shadow-v3',
            'timestamp': '2026-07-11T01:00:00Z',
            'route': '/api/rating_test/answer',
            'request_id': 'req-1',
            'parser_status': 'ok',
            'shadow_judgement': 'match',
            'latency_ms': 14,
        },
        {
            'schema_version': 'shadow-v3',
            'timestamp': '2026-07-11T02:00:00Z',
            'route': '/api/daily-challenge/submit',
            'request_id': 'req-2',
            'parser_status': 'failed',
            'shadow_judgement': 'error',
            'reason': 'sgf_engine unavailable or failed: RuntimeError',
            'latency_ms': 28,
        },
    ])
    monkeypatch.setattr(shadow_dashboard, 'DEFAULT_SHADOW_EVENTS_PATH', str(path))

    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 12
        sess['is_admin'] = True

    response = client.get('/api/admin/shadow/dashboard/recent?limit=1&route=/api/daily-challenge/submit&path=/etc/passwd')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['limit'] == 1
    assert payload['returned_events'] == 1
    assert payload['source_path'] == str(path)
    assert payload['recent_events'][0]['request_id'] == 'req-2'


def test_shadow_dashboard_html_contract():
    html = _read_static_html()
    required_ids = [
        'shadow-dashboard-app',
        'summary-total-events',
        'summary-success',
        'summary-parser-failed',
        'summary-judgement-error',
        'summary-average-latency',
        'route-filter',
        'parser-status-filter',
        'judgement-filter',
        'request-id-search',
        'refresh-button',
        'recent-window-note',
        'recent-events-table',
        'route-stats-table',
        'parser-failures-table',
        'dashboard-error',
        'empty-state',
    ]
    ids = re.findall(r'id="([^"]+)"', html)
    assert len(ids) == len(set(ids)), "duplicate HTML id attributes detected"
    for required_id in required_ids:
        assert required_id in ids, f"{required_id} missing from shadow_dashboard.html"

    for token in (
        '/api/admin/shadow/dashboard/recent',
        'Schema Version',
        'Parser Status',
        'Shadow Judgement',
        'Request ID Search',
        'Parser Failure Reason',
        'Exception Message',
        'empty-state',
        'dashboard-error',
    ):
        assert token in html


def test_shadow_dashboard_html_renders_current_schema_fields():
    html = _read_static_html()
    for token in (
        'schema_version',
        'route',
        'request_id',
        'latency',
        'parser_status',
        'shadow_judgement',
        'reason',
    ):
        assert token in html or token.replace('_', ' ') in html.lower()
