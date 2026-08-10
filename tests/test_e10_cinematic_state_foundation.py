"""Server-authoritative E10 cinematic state contract tests.

The tests use a disposable SQLite connection behind the real Flask routes.
The application import receives only a synthetic test configuration; no
repository secret or production database is read.
"""

import os
import sqlite3
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


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
        module.grimoire_bp = Blueprint('grimoire_stub_e10_cinematics', __name__)
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
    os.environ.setdefault('SECRET_KEY', 'synthetic-e10-cinematic-test-key')
    _install_app_import_stubs()
    import app as app_module
    return app_module


class _DbContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()


@pytest.fixture()
def sqlite_conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE account_cinematic_state (
        user_id INTEGER NOT NULL,
        cinematic_key TEXT NOT NULL,
        seen_at TEXT NOT NULL,
        PRIMARY KEY (user_id, cinematic_key)
    )''')
    conn.execute('''CREATE TABLE adventure_boss_progress (
        user_id INTEGER NOT NULL,
        zone_key TEXT NOT NULL,
        stars INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, zone_key)
    )''')
    return conn


@pytest.fixture()
def client(app_module, sqlite_conn, monkeypatch):
    monkeypatch.setattr(app_module, 'get_db', lambda: _DbContext(sqlite_conn))
    app_module.app.config['TESTING'] = True
    return app_module.app.test_client()


def _login(client, uid):
    with client.session_transaction() as session:
        session['user_id'] = uid


def test_registry_defines_exactly_the_zone_one_to_ten_intro_namespace(app_module):
    expected = tuple(f'e10_zone{number}_intro_v1' for number in range(1, 11))
    assert tuple(app_module.E10_CINEMATIC_KEYS) == expected
    assert tuple(app_module.E10_CINEMATIC_KEY_REGISTRY) == expected


def test_persistence_schema_is_one_generic_account_cinematic_relation():
    app_source = (ROOT / 'app.py').read_text(encoding='utf-8')
    schema_start = app_source.index('CREATE TABLE IF NOT EXISTS account_cinematic_state')
    schema = app_source[schema_start:app_source.index("CREATE INDEX IF NOT EXISTS idx_account_cinematic_state_user", schema_start)]
    assert 'user_id' in schema
    assert 'cinematic_key' in schema
    assert 'seen_at' in schema
    assert 'PRIMARY KEY (user_id, cinematic_key)' in schema
    assert 'zone1_intro_seen' not in schema
    assert 'zone10_intro_seen' not in schema


def test_no_record_returns_unseen_for_every_registered_key(app_module, sqlite_conn, monkeypatch):
    monkeypatch.setattr(app_module, 'get_db', lambda: _DbContext(sqlite_conn))
    state = app_module._e10_cinematic_state(991245)
    assert set(state) == set(app_module.E10_CINEMATIC_KEYS)
    assert all(entry == {'seen': False, 'seen_at': None} for entry in state.values())


def test_unauthenticated_mark_is_rejected(client):
    response = client.post('/api/adventure/cinematics/seen', json={
        'cinematic_key': 'e10_zone1_intro_v1',
    })
    assert response.status_code == 401


def test_unknown_key_is_rejected_without_creating_state(client, sqlite_conn):
    _login(client, 991245)
    response = client.post('/api/adventure/cinematics/seen', json={
        'cinematic_key': 'e10_zone99_intro_v1',
    })
    assert response.status_code == 400
    assert response.get_json()['error'] == 'unsupported_cinematic_key'
    assert sqlite_conn.execute('SELECT COUNT(*) FROM account_cinematic_state').fetchone()[0] == 0


def test_current_user_can_mark_own_state_and_repeated_mark_is_idempotent(client, sqlite_conn):
    _login(client, 991245)
    first = client.post('/api/adventure/cinematics/seen', json={
        'cinematic_key': 'e10_zone1_intro_v1',
    })
    assert first.status_code == 200
    first_body = first.get_json()
    assert first_body['state']['seen'] is True
    assert first_body['cinematics']['e10_zone1_intro_v1']['seen'] is True
    first_seen_at = first_body['state']['seen_at']

    second = client.post('/api/adventure/cinematics/seen', json={
        'cinematic_key': 'e10_zone1_intro_v1',
    })
    assert second.status_code == 200
    assert second.get_json()['state']['seen_at'] == first_seen_at
    assert sqlite_conn.execute(
        'SELECT COUNT(*) FROM account_cinematic_state WHERE user_id=? AND cinematic_key=?',
        (991245, 'e10_zone1_intro_v1'),
    ).fetchone()[0] == 1


def test_client_user_id_cannot_redirect_the_authenticated_write(client, sqlite_conn):
    _login(client, 991245)
    response = client.post('/api/adventure/cinematics/seen', json={
        'cinematic_key': 'e10_zone1_intro_v1',
        'user_id': 7,
    })
    assert response.status_code == 200
    assert sqlite_conn.execute(
        'SELECT COUNT(*) FROM account_cinematic_state WHERE user_id=?', (991245,)
    ).fetchone()[0] == 1
    assert sqlite_conn.execute(
        'SELECT COUNT(*) FROM account_cinematic_state WHERE user_id=?', (7,)
    ).fetchone()[0] == 0


def test_same_account_reads_seen_state_across_independent_clients(client, sqlite_conn, app_module):
    _login(client, 991245)
    client.post('/api/adventure/cinematics/seen', json={
        'cinematic_key': 'e10_zone1_intro_v1',
    })
    with app_module.app.test_client() as second_browser:
        _login(second_browser, 991245)
        state = app_module._e10_cinematic_state(991245)
        assert state['e10_zone1_intro_v1']['seen'] is True


def test_different_accounts_on_same_browser_do_not_share_seen_state(client, sqlite_conn, app_module):
    _login(client, 991245)
    client.post('/api/adventure/cinematics/seen', json={
        'cinematic_key': 'e10_zone1_intro_v1',
    })
    with client.session_transaction() as session:
        session['user_id'] = 991246
    state = app_module._e10_cinematic_state(991246)
    assert state['e10_zone1_intro_v1']['seen'] is False
    assert sqlite_conn.execute(
        'SELECT COUNT(*) FROM account_cinematic_state WHERE user_id=?', (991246,)
    ).fetchone()[0] == 0


def test_clearing_browser_storage_cannot_reset_server_seen_state(client, app_module):
    _login(client, 991245)
    client.post('/api/adventure/cinematics/seen', json={
        'cinematic_key': 'e10_zone1_intro_v1',
    })
    index = (ROOT / 'index.html').read_text(encoding='utf-8')
    start = index.index('function adventureCinematicKey(zone)')
    end = index.index("// Account scope for Zone 1's POST_CLEAR state", start)
    assert 'localStorage' not in index[start:end]
    assert app_module._e10_cinematic_state(991245)['e10_zone1_intro_v1']['seen'] is True


def test_mark_seen_route_does_not_touch_gameplay_progression(client, sqlite_conn):
    _login(client, 991245)
    client.post('/api/adventure/cinematics/seen', json={
        'cinematic_key': 'e10_zone1_intro_v1',
    })
    assert sqlite_conn.execute(
        'SELECT COUNT(*) FROM adventure_boss_progress WHERE user_id=?', (991245,)
    ).fetchone()[0] == 0


def test_bootstrap_exposes_account_state_without_a_second_client_authority(
    client, sqlite_conn, app_module, monkeypatch
):
    _login(client, 991245)
    monkeypatch.setattr(app_module, '_adventure_state', lambda uid: [])
    monkeypatch.setattr(app_module, '_set_adventure_state_cache', lambda uid, zones: None)
    monkeypatch.setattr(
        app_module,
        '_adventure_map_state_from_zones',
        lambda zones, selected_stage_key=None: {'zones': []},
    )
    before = client.get('/api/adventure/bootstrap')
    assert before.status_code == 200
    assert before.get_json()['cinematics']['e10_zone1_intro_v1']['seen'] is False

    client.post('/api/adventure/cinematics/seen', json={
        'cinematic_key': 'e10_zone1_intro_v1',
    })
    after = client.get('/api/adventure/bootstrap')
    assert after.get_json()['cinematics']['e10_zone1_intro_v1']['seen'] is True


def test_frontend_has_no_legacy_intro_localstorage_authority():
    index = (ROOT / 'index.html').read_text(encoding='utf-8')
    assert 'adventure_intro_seen_v1' not in index
    assert 'adventure_intro_seen_v2' not in index
    assert "localStorage.getItem('adventure_intro" not in index
    assert '/api/adventure/cinematics/seen' in index


def test_schema_and_route_keep_first_entry_completion_distinct_from_replay():
    index = (ROOT / 'index.html').read_text(encoding='utf-8')
    finish_start = index.index('async function finishIntroFilm(zone) {')
    finish = index[finish_start:index.index('\nfunction skipIntroFilm()', finish_start)]
    assert "if (mode === 'first_entry')" in finish
    assert "await markAdventureIntroSeen(zone);" in finish
    assert "else if (mode === 'legacy')" in finish
    assert "void markAdventureIntroSeen(zone);" in finish
    assert "mode === 'manual_replay'" in finish
    assert 'if (mode !== \'manual_replay\')' not in finish

    show_start = index.index('async function showStageIntroCinematic(zone, options = {})')
    show = index[show_start:index.index('\n\n window.startAdventureStage', show_start)]
    assert 'markAdventureIntroSeen' not in show
