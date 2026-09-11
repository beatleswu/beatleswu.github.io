"""Cross-lane ACT-A integration proof for the accepted D1 seams."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import types

import pytest

from adventure_monster_runtime_contract import AdventureQuestionBinding, persistence_metadata
from migrations import w2_a1_onboarding_v1 as onboarding_migration
from map_battle_persistence import (
    create_map_battle,
    ensure_map_battle_tables,
    load_authoritative_battle_state,
)


def _install_app_import_stubs():
    """Keep this integration test independent of optional local services."""

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
        module.grimoire_bp = Blueprint('grimoire_stub_act_a_cross_lane', __name__)
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
    os.environ.setdefault('SECRET_KEY', 'act-a-r1-cross-lane-test-only')
    _install_app_import_stubs()
    import app as app_module

    return app_module


class _DbContext:
    """App DB wrapper over a test-owned SQLite connection."""

    def __init__(self, connection):
        self._conn = connection
        self.commit_calls = 0
        self.rollback_calls = 0

    def execute(self, statement, parameters=()):
        return self._conn.execute(statement, parameters)

    def commit(self):
        self.commit_calls += 1
        self._conn.commit()

    def rollback(self):
        self.rollback_calls += 1
        self._conn.rollback()

    def close(self):
        # The pytest fixture owns the connection, as the production pool owns
        # the underlying connection after the ACT-A wrapper returns it.
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_app_provider_create_restore_settlement_roundtrip_and_outer_rollback(
    app_module, monkeypatch
):
    question = {
        'id': 8101,
        'content': '(;SZ[19];B[dd];W[ee])',
    }
    revision = hashlib.sha256(question['content'].encode('utf-8')).hexdigest()
    question_binding = AdventureQuestionBinding(question['id'], revision)

    create_provider = app_module._map_battle_provider_for_new(
        question,
        {'question_revision': revision},
        zone_key='k26_30',
        user_id=101,
        eligibility={},
        payload={},
    )
    assert create_provider is not None

    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    connection.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
    connection.execute('INSERT INTO users(id) VALUES (101)')
    ensure_map_battle_tables(connection)

    # A provider-bound creation is part of the caller-owned transaction.  A
    # failure before the coordinator commit must remove the battle row.
    connection.execute('BEGIN')
    rolled_back_battle_id = create_map_battle(
        connection,
        battle_id='act-a-roundtrip-rolled-back',
        user_id=101,
        zone_key='k26_30',
        player_hp=20,
        player_hp_max=20,
        monster_hp=create_provider.max_hp,
        monster_hp_max=create_provider.max_hp,
        **persistence_metadata(create_provider),
    )
    assert rolled_back_battle_id == 'act-a-roundtrip-rolled-back'
    connection.rollback()
    assert load_authoritative_battle_state(
        connection,
        user_id=101,
        battle_id=rolled_back_battle_id,
    ) is None

    battle_id = create_map_battle(
        connection,
        battle_id='act-a-roundtrip-committed',
        user_id=101,
        zone_key='k26_30',
        player_hp=20,
        player_hp_max=20,
        monster_hp=create_provider.max_hp,
        monster_hp_max=create_provider.max_hp,
        **persistence_metadata(create_provider),
    )
    connection.commit()
    persisted_battle = load_authoritative_battle_state(
        connection,
        user_id=101,
        battle_id=battle_id,
    )
    assert persisted_battle is not None

    restored_provider = app_module._map_battle_provider_for_restore(
        persisted_battle,
        question,
        {'question_revision': revision},
        user_id=101,
    )
    assert restored_provider.binding is not None
    assert restored_provider.provider_id == create_provider.provider_id
    assert restored_provider.binding.provider_id == create_provider.provider_id

    captured = {}

    def fake_settle_answer(*args, **kwargs):
        settlement_provider = kwargs['runtime_provider']
        captured['provider'] = settlement_provider
        captured['binding'] = settlement_provider.settlement_binding(
            battle=persisted_battle,
            question_binding=question_binding,
            user_id=101,
        )
        return {'accepted': True, 'submission_id': 'act-a-roundtrip-settlement'}

    monkeypatch.setattr(app_module, 'get_db', lambda: _DbContext(connection))
    monkeypatch.setattr(app_module, '_map_battle_eligibility', lambda conn, user_id: {})
    monkeypatch.setattr(app_module, 'settle_answer', fake_settle_answer)
    monkeypatch.setattr(
        app_module,
        '_run_map_battle_progression',
        lambda user_id, result: ({'status': 'applied'}, 200),
    )
    app_module.app.config['TESTING'] = True
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = 101

    response = client.post(
        '/api/adventure/map-battles/v1/answers',
        json={},
        headers={'X-Map-Battle-Client-Protocol': 'v1'},
    )
    assert response.status_code == 200
    settlement_provider = captured['provider']
    assert settlement_provider is app_module.MAP_BATTLE_RUNTIME_PROVIDER_REGISTRY
    assert captured['binding'].provider_id == create_provider.provider_id

    broken_battle = dict(persisted_battle)
    broken_battle['migration_version'] = 'w2.z1_z2.binding.v1:Z1:MISSING:missing:v1'
    with pytest.raises(app_module.JudgeUnavailable):
        app_module._map_battle_provider_for_restore(
            broken_battle,
            question,
            {'question_revision': revision},
            user_id=101,
        )

    connection.close()


def test_v2_dark_schema_guard_and_transaction_rollback(app_module, monkeypatch):
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    db_context = _DbContext(connection)
    monkeypatch.setattr(app_module, 'get_db', lambda: db_context)
    app_module.app.config['TESTING'] = True
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = 102

    # Dark-by-default is a controlled response and does not write the legacy
    # Newbie Quest tables or any V2 state.
    monkeypatch.delenv('GO_ODYSSEY_ONBOARDING_V2_ENABLED', raising=False)
    dark_response = client.post('/api/onboarding/v2/start', json={})
    assert dark_response.status_code == 503
    assert dark_response.get_json()['code'] == 'onboarding_v2_disabled'
    assert db_context.commit_calls == 0
    assert db_context.rollback_calls == 0

    # Even with the dark gate explicitly requested, absent schema fails closed
    # through the typed unavailable response; no fallback write is attempted.
    monkeypatch.setenv('GO_ODYSSEY_ONBOARDING_V2_ENABLED', '1')
    missing_schema_response = client.post('/api/onboarding/v2/start', json={})
    assert missing_schema_response.status_code == 503
    assert missing_schema_response.get_json()['code'] == 'onboarding_v2_schema_unavailable'
    assert db_context.commit_calls == 0
    assert db_context.rollback_calls == 1

    # The accepted schema fixture is materialized locally only for this test;
    # the app route itself only probes it and never applies the migration.
    onboarding_migration.upgrade(connection)
    connection.commit()
    started = client.post('/api/onboarding/v2/start', json={})
    assert started.status_code == 200
    assert started.get_json()['state']['status'] == 'NOT_STARTED'
    # The accepted authority observes the already-open transaction and leaves
    # commit/rollback to ACT-A; exactly one coordinator commit occurs here.
    assert db_context.commit_calls == 1
    assert db_context.rollback_calls == 1

    real_start = app_module.start_onboarding_v2

    def fail_after_v2_write(conn, user_id, expected_state_version):
        result = real_start(conn, user_id, expected_state_version)
        raise RuntimeError('injected V2 downstream failure')

    monkeypatch.setattr(app_module, 'start_onboarding_v2', fail_after_v2_write)
    with client.session_transaction() as session:
        session['user_id'] = 103
    with pytest.raises(RuntimeError, match='injected V2 downstream failure'):
        client.post('/api/onboarding/v2/start', json={})
    assert db_context.commit_calls == 1
    assert db_context.rollback_calls == 2
    assert connection.execute(
        'SELECT COUNT(*) FROM wave2_onboarding_state_v1 WHERE user_id=103'
    ).fetchone()[0] == 0
    connection.close()
