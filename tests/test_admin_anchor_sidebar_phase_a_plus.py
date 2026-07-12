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
    if 'sgf_engine' not in sys.modules:
        sys.modules['sgf_engine'] = types.ModuleType('sgf_engine')
    if 'sgf_engine.parser' not in sys.modules:
        sys.modules['sgf_engine.parser'] = types.ModuleType('sgf_engine.parser')
    if 'sgf_engine.parser.sgf_parser' not in sys.modules:
        module = types.ModuleType('sgf_engine.parser.sgf_parser')
        module.parse_sgf = lambda *args, **kwargs: None
        sys.modules['sgf_engine.parser.sgf_parser'] = module


@pytest.fixture(scope='module')
def app_module():
    _install_app_import_stubs()
    import app as app_module
    return app_module


def test_admin_html_exposes_sidebar_sections():
    html = Path('admin.html').read_text(encoding='utf-8')

    for token in (
        'admin-nav-search',
        'admin-sidebar-nav',
        'admin-section-overview',
        'admin-section-user-management',
        'admin-section-analytics',
        'rating-shadow-card',
        'admin-section-adventure',
        'admin-section-growth-billing',
        'admin-section-system-tools',
        'admin-section-review-queue',
        'admin-section-content-moderation',
        'upsell-status-panel',
        '/admin/shadow-dashboard',
        'Shadow Dashboard',
    ):
        assert token in html


def test_admin_page_renders_for_admin(app_module):
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 11
        sess['is_admin'] = True

    response = client.get('/admin')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    for token in (
        'admin-sidebar-nav',
        'review-queue-import-btn',
        'problem-report-list',
        'dm-reports',
        'trial-batch-key',
        'weekly-shadow-toggle',
    ):
        assert token in html


def test_admin_page_redirects_non_admin(app_module):
    client = app_module.app.test_client()
    response = client.get('/admin')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/login')


def test_admin_page_includes_student_note_controls(app_module):
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 11
        sess['is_admin'] = True

    response = client.get('/admin')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    for token in (
        'admin_note',
        'saveUserNote(${u.id}, this.value)',
        '/api/admin/users/${uid}/note',
    ):
        assert token in html


class _FakeNoteResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeNoteConn:
    def __init__(self, row):
        self.row = row
        self.executed = []
        self.committed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return _FakeNoteResult(self.row)

    def commit(self):
        self.committed = True


class _FakeNoteConnCtx:
    def __init__(self, row):
        self.conn = _FakeNoteConn(row)

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_admin_note_endpoint_updates_admin_note(app_module, monkeypatch):
    row = {'id': 7}
    ctx = _FakeNoteConnCtx(row)
    monkeypatch.setattr(app_module, 'get_db', lambda: ctx)

    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 11
        sess['is_admin'] = True

    response = client.post('/api/admin/users/7/note', json={'note': '  keep studying  '})

    assert response.status_code == 200
    assert response.get_json() == {'ok': True}
    assert ctx.conn.committed is True
    assert any(
        sql.strip().startswith('UPDATE users SET admin_note=? WHERE id=?')
        and params == ('keep studying', 7)
        for sql, params in ctx.conn.executed
    )
