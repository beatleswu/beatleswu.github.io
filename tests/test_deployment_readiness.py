import json
import hashlib
import sys
import types
from pathlib import Path

import pytest


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


@pytest.fixture(scope='module')
def app_module():
    _install_app_import_stubs()
    import app as app_module
    return app_module


class _FakeResult:
    def fetchone(self):
        return (1,)


class _FakeConn:
    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return _FakeResult()


class _FakeConnCtx:
    def __enter__(self):
        return _FakeConn()

    def __exit__(self, exc_type, exc, tb):
        return False


def _make_questions_file(path: Path, rows):
    path.write_text(json.dumps(rows), encoding='utf-8')


def _set_readiness_env(monkeypatch, app_module, questions_path: Path, static_root: Path, shadow_path: Path):
    monkeypatch.setattr(app_module, 'DATA_FILE', str(questions_path))
    monkeypatch.setenv('QUESTIONS_JSON_PATH', str(questions_path))
    monkeypatch.setenv('GO_ODYSSEY_LIVE_STATIC_ROOT', str(static_root))
    monkeypatch.setenv('SHADOW_EVENTS_PATH', str(shadow_path))
    monkeypatch.setenv('APP_GIT_SHA', '0123456789abcdef0123456789abcdef01234567')
    monkeypatch.setenv('APP_BUILD_DATE', '2026-07-11T00:00:00Z')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://go:secret@postgres:5432/go_odyssey')
    monkeypatch.setattr(app_module, 'get_db', lambda: _FakeConnCtx())


def test_describe_database_url_is_secret_safe():
    import db

    summary = db.describe_database_url('postgresql://go:topsecret@postgres:5432/go_odyssey')
    assert summary['configured'] is True
    assert summary['host'] == 'postgres'
    assert summary['port'] == 5432
    assert summary['database'] == 'go_odyssey'
    assert summary['user'] == 'go'
    assert summary['password_present'] is True


def test_readiness_blocks_missing_questions_file(tmp_path, monkeypatch, app_module):
    static_root = tmp_path / 'static'
    static_root.mkdir()
    shadow_path = tmp_path / 'shadow_events.jsonl'
    shadow_path.write_text('', encoding='utf-8')
    _set_readiness_env(monkeypatch, app_module, tmp_path / 'questions.json', static_root, shadow_path)

    report = app_module._read_runtime_deployment_readiness()

    assert report['ok'] is False
    assert any('missing' in failure for failure in report['questions']['failures'])


def test_readiness_blocks_zero_record_dataset(tmp_path, monkeypatch, app_module):
    questions_path = tmp_path / 'questions.json'
    questions_path.write_text('[]', encoding='utf-8')
    static_root = tmp_path / 'static'
    static_root.mkdir()
    shadow_path = tmp_path / 'shadow_events.jsonl'
    shadow_path.write_text('', encoding='utf-8')
    _set_readiness_env(monkeypatch, app_module, questions_path, static_root, shadow_path)

    report = app_module._read_runtime_deployment_readiness()

    assert report['ok'] is False
    assert report['questions']['record_count'] == 0
    assert any('no records' in failure for failure in report['questions']['failures'])


def test_readiness_passes_for_valid_dataset_and_does_not_expose_secret(tmp_path, monkeypatch, app_module):
    questions_path = tmp_path / 'questions.json'
    _make_questions_file(questions_path, [{'id': 1, 'source': 'q1.sgf', 'content': '(;SZ[19])'}])
    static_root = tmp_path / 'static'
    static_root.mkdir()
    shadow_path = tmp_path / 'shadow_events.jsonl'
    shadow_path.write_text('', encoding='utf-8')
    _set_readiness_env(monkeypatch, app_module, questions_path, static_root, shadow_path)

    report = app_module._read_runtime_deployment_readiness()

    serialized = json.dumps(report, ensure_ascii=False)
    assert report['ok'] is True
    assert report['questions']['record_count'] == 1
    assert report['questions']['structural_record_check'] is True
    assert 'topsecret' not in serialized
    assert 'DATABASE_URL' not in serialized


def test_deployment_readiness_endpoint_requires_admin(app_module):
    client = app_module.app.test_client()
    response = client.get('/api/admin/deployment/readiness')
    assert response.status_code == 401


def test_deployment_readiness_endpoint_returns_report_for_admin(monkeypatch, app_module):
    monkeypatch.setattr(app_module, '_read_runtime_deployment_readiness', lambda: {'ok': True, 'failures': []})
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 42
        sess['is_admin'] = True

    response = client.get('/api/admin/deployment/readiness')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['ok'] is True
    assert payload['failures'] == []


def _write_static_release_fixture(root: Path, generation='20260719-191549-9007ded4-v201-e9-quest-board'):
    files = {}
    for name, content in {
        'index.html': b'<html>quest</html>',
        'i18n.js': b'window.I18N = {};',
        'sw.js': b'const VERSION = "v201-e9-quest-board";'
    }.items():
        (root / name).write_bytes(content)
        files[name] = hashlib.sha256(content).hexdigest()
    (root / 'manifest.json').write_text(json.dumps({
        'static_generation_id': generation,
        'release_git_sha': '9007ded4bb1c185995e1a4f570b36dfe47c91cb2',
        'files': [{'path': name, 'sha256': digest} for name, digest in files.items()]
    }), encoding='utf-8')


def test_static_release_healthz_uses_manifest_generation_for_literal_mount(tmp_path, monkeypatch, app_module):
    root = tmp_path / 'current'
    root.mkdir()
    _write_static_release_fixture(root)
    monkeypatch.setenv('GO_ODYSSEY_LIVE_STATIC_ROOT', str(root))

    payload = app_module.app.test_client().get('/healthz/static-release').get_json()

    assert payload['ok'] is True
    assert payload['generation'] == '20260719-191549-9007ded4-v201-e9-quest-board'
    assert payload['generation'] != 'current'
    assert payload['source_sha'] == '9007ded4bb1c185995e1a4f570b36dfe47c91cb2'


def test_static_release_healthz_uses_manifest_generation_for_symlink(tmp_path, monkeypatch, app_module):
    target = tmp_path / 'generation'
    target.mkdir()
    _write_static_release_fixture(target)
    current = tmp_path / 'current'
    try:
        current.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        if getattr(exc, 'winerror', None) == 1314:
            pytest.skip('symlink creation requires SeCreateSymbolicLinkPrivilege on this Windows host')
        raise
    monkeypatch.setenv('GO_ODYSSEY_LIVE_STATIC_ROOT', str(current))

    response = app_module.app.test_client().get('/healthz/static-release')

    assert response.status_code == 200
    assert response.get_json()['generation'].startswith('20260719-191549-9007ded4-')


@pytest.mark.parametrize('mutation', ['missing', 'current', 'malformed', 'bad_hash'])
def test_static_release_healthz_fails_closed_on_invalid_manifest(tmp_path, monkeypatch, app_module, mutation):
    root = tmp_path / 'current'
    root.mkdir()
    _write_static_release_fixture(root)
    manifest_path = root / 'manifest.json'
    if mutation == 'missing':
        manifest_path.unlink()
    elif mutation == 'current':
        data = json.loads(manifest_path.read_text(encoding='utf-8'))
        data['static_generation_id'] = 'current'
        manifest_path.write_text(json.dumps(data), encoding='utf-8')
    elif mutation == 'malformed':
        manifest_path.write_text('{', encoding='utf-8')
    else:
        data = json.loads(manifest_path.read_text(encoding='utf-8'))
        data['files'][0]['sha256'] = '0' * 64
        manifest_path.write_text(json.dumps(data), encoding='utf-8')
    monkeypatch.setenv('GO_ODYSSEY_LIVE_STATIC_ROOT', str(root))

    response = app_module.app.test_client().get('/healthz/static-release')

    assert response.status_code == 503
    assert response.get_json()['ok'] is False
