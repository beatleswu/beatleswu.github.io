import datetime as dt
import json
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
    path.write_text(
        ''.join(json.dumps(row) + '\n' for row in rows),
        encoding='utf-8',
    )


def test_aggregate_shadow_events_empty_file(tmp_path):
    path = tmp_path / 'shadow_events.jsonl'
    path.write_text('', encoding='utf-8')

    result = shadow_dashboard.aggregate_shadow_events(
        path=str(path),
        now=dt.datetime(2026, 7, 11, 12, 0, tzinfo=dt.timezone.utc),
    )

    assert result['summary']['total_events'] == 0
    assert result['summary']['invalid_lines'] == 0
    assert result['latency']['count'] == 0
    assert result['parser']['failures'] == 0
    assert result['exceptions']['total'] == 0
    assert set(result['routes']) >= set(shadow_dashboard.EXPECTED_ROUTES)


def test_aggregate_shadow_events_one_event(tmp_path):
    path = tmp_path / 'shadow_events.jsonl'
    _write_jsonl(path, [{
        'schema_version': 'shadow-v3',
        'timestamp': '2026-07-11T09:00:00Z',
        'route': '/api/rating_test/answer',
        'question_id': 101,
        'match': True,
        'latency_ms': 12.5,
        'parser_status': 'ok',
        'parser_failure_reason': '',
        'exception_class': '',
    }])

    result = shadow_dashboard.aggregate_shadow_events(
        path=str(path),
        now=dt.datetime(2026, 7, 11, 12, 0, tzinfo=dt.timezone.utc),
    )

    assert result['summary']['total_events'] == 1
    assert result['summary']['today_events'] == 1
    assert result['routes']['/api/rating_test/answer']['total'] == 1
    assert result['routes']['/api/rating_test/answer']['matches'] == 1
    assert result['latency']['average_ms'] == 12.5
    assert result['latency']['p50_ms'] == 12.5
    assert result['schema_versions'] == [{'schema_version': 'shadow-v3', 'count': 1}]


def test_aggregate_shadow_events_multiple_routes_and_groups(tmp_path):
    path = tmp_path / 'shadow_events.jsonl'
    _write_jsonl(path, [
        {
            'schema_version': 'shadow-v3',
            'timestamp': '2026-07-11T02:00:00Z',
            'route': '/api/rating_test/answer',
            'question_id': 1,
            'match': True,
            'latency_ms': 5,
            'parser_status': 'ok',
        },
        {
            'schema_version': 'shadow-v3',
            'timestamp': '2026-07-10T02:00:00Z',
            'route': '/api/daily-challenge/submit',
            'question_id': 2,
            'match': False,
            'latency_ms': 15,
            'parser_status': 'failed',
            'parser_failure_reason': 'route unsupported: daily_challenge',
        },
        {
            'schema_version': 'shadow-v3',
            'timestamp': '2026-07-05T02:00:00Z',
            'route': '/api/challenges/friend/9/answer',
            'question_id': 2,
            'match': False,
            'latency_ms': 30,
            'parser_status': 'failed',
            'parser_failure_reason': 'route unsupported: friend_challenge',
            'exception_class': 'ValueError',
        },
    ])

    result = shadow_dashboard.aggregate_shadow_events(
        path=str(path),
        now=dt.datetime(2026, 7, 11, 12, 0, tzinfo=dt.timezone.utc),
    )

    assert result['summary']['total_events'] == 3
    assert result['summary']['today_events'] == 1
    assert result['summary']['last_7_days'] == 3
    assert result['summary']['last_30_days'] == 3
    assert result['routes']['/api/rating_test/answer']['matches'] == 1
    assert result['routes']['/api/daily-challenge/submit']['mismatches'] == 1
    assert result['routes']['/api/daily-challenge/submit']['parser_failures'] == 1
    assert result['routes']['/api/challenges/friend/<int:cid>/answer']['mismatches'] == 1
    assert result['routes']['/api/challenges/friend/<int:cid>/answer']['exceptions'] == 1
    assert result['parser']['failures'] == 2
    assert result['exceptions']['total'] == 1
    assert result['top_mismatches'][0]['puzzle_id'] == '2'
    assert result['top_mismatches'][0]['count'] == 2
    assert result['top_parser_failures'][0]['puzzle_id'] == '2'
    assert result['top_parser_failures'][0]['count'] == 2


def test_aggregate_shadow_events_skips_malformed_and_unknown_schema(tmp_path):
    path = tmp_path / 'shadow_events.jsonl'
    path.write_text(
        '\n'.join([
            '{"schema_version":"shadow-v999","route":"/api/rating_test/answer","timestamp":"2026-07-11T00:00:00Z"}',
            'not-json',
            '{"route":"","timestamp":"2026-07-11T00:00:00Z"}',
        ]) + '\n',
        encoding='utf-8',
    )

    result = shadow_dashboard.aggregate_shadow_events(
        path=str(path),
        now=dt.datetime(2026, 7, 11, 12, 0, tzinfo=dt.timezone.utc),
    )

    assert result['summary']['total_events'] == 2
    assert result['summary']['invalid_lines'] == 1
    assert result['summary']['partial_events'] == 1
    assert result['summary']['unknown_schema_versions'] == 1


def test_aggregate_shadow_events_latency_percentiles(tmp_path):
    path = tmp_path / 'shadow_events.jsonl'
    rows = []
    for idx, latency in enumerate([10, 20, 30, 40, 50], start=1):
        rows.append({
            'schema_version': 'shadow-v3',
            'timestamp': '2026-07-11T01:00:00Z',
            'route': '/api/rating_test/answer',
            'question_id': idx,
            'latency_ms': latency,
        })
    _write_jsonl(path, rows)

    result = shadow_dashboard.aggregate_shadow_events(
        path=str(path),
        now=dt.datetime(2026, 7, 11, 12, 0, tzinfo=dt.timezone.utc),
    )

    assert result['latency']['count'] == 5
    assert result['latency']['minimum_ms'] == 10.0
    assert result['latency']['maximum_ms'] == 50.0
    assert result['latency']['average_ms'] == 30.0
    assert result['latency']['p50_ms'] == 30.0
    assert result['latency']['p95_ms'] == 50.0


@pytest.fixture(scope='module')
def app_module():
    _install_app_import_stubs()
    import app as app_module
    return app_module


def test_dashboard_api_requires_admin(app_module):
    client = app_module.app.test_client()

    response = client.get('/api/admin/shadow/dashboard')

    assert response.status_code == 401


def test_dashboard_api_returns_empty_dataset_for_admin(tmp_path, monkeypatch, app_module):
    path = tmp_path / 'shadow_events.jsonl'
    path.write_text('', encoding='utf-8')
    monkeypatch.setattr(shadow_dashboard, 'DEFAULT_SHADOW_EVENTS_PATH', str(path))

    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 7
        sess['is_admin'] = True

    response = client.get('/api/admin/shadow/dashboard')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['summary']['total_events'] == 0
    assert set(payload['routes']) >= set(shadow_dashboard.EXPECTED_ROUTES)


def test_dashboard_api_returns_populated_dataset(tmp_path, monkeypatch, app_module):
    path = tmp_path / 'shadow_events.jsonl'
    _write_jsonl(path, [{
        'schema_version': 'shadow-v3',
        'timestamp': '2026-07-11T00:00:00Z',
        'route': '/api/challenges/friend/88/answer',
        'question_id': 88,
        'match': False,
        'latency_ms': 22,
        'parser_status': 'failed',
        'parser_failure_reason': 'route unsupported: friend_challenge',
        'exception_class': 'RuntimeError',
    }])
    monkeypatch.setattr(shadow_dashboard, 'DEFAULT_SHADOW_EVENTS_PATH', str(path))

    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 9
        sess['is_admin'] = True

    response = client.get('/api/admin/shadow/dashboard')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['summary']['total_events'] == 1
    assert payload['routes']['/api/challenges/friend/<int:cid>/answer']['total'] == 1
    assert payload['parser']['failures'] == 1
    assert payload['exceptions']['total'] == 1
    assert payload['latency']['average_ms'] == 22.0


def test_shadow_dashboard_doc_contract():
    doc = Path('docs/planning/shadow_dashboard_backend_e23.md').read_text(encoding='utf-8').lower()

    assert 'aggregation architecture' in doc
    assert 'dashboard api' in doc
    assert 'supported metrics' in doc
    assert 'known limitations' in doc
    assert '/api/admin/shadow/dashboard' in doc
