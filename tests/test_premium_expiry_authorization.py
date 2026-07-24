"""Regression coverage for DB-first Premium authorization."""
import importlib
import os
import sqlite3
import sys

import pytest


TEST_SECRET = 'test-only-premium-authorization-secret'


def _app_module():
    os.environ.setdefault('SECRET_KEY', TEST_SECRET)
    sys.modules.pop('app', None)
    return importlib.import_module('app')


class _DbContext:
    def __init__(self, path, factory):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.factory = factory

    def execute(self, sql, params=()):
        self.factory.queries += 1
        return self.conn.execute(sql, params)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.conn.close()


class _DbFactory:
    def __init__(self, path):
        self.path = path
        self.queries = 0

    def __call__(self):
        return _DbContext(self.path, self)


@pytest.fixture()
def app_with_db(tmp_path, monkeypatch):
    path = tmp_path / 'premium-auth.sqlite'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, plan TEXT, premium_until TEXT)')
    app = _app_module()
    factory = _DbFactory(path)
    monkeypatch.setattr(app, 'get_db', factory)
    app.app.config.update(TESTING=True)
    return app, factory, path


def _set_user(path, plan, until):
    with sqlite3.connect(path) as conn:
        conn.execute('INSERT INTO users(id,plan,premium_until) VALUES(1,?,?)', (plan, until))


@pytest.mark.parametrize('db_plan,until,expected', [
    ('premium', '2030-01-01T00:00:00', True),
    ('premium', None, True),
    ('premium', '2000-01-01T00:00:00', False),
    ('free', None, False),
])
def test_db_authority_overrides_session_and_synchronizes_cache(app_with_db, db_plan, until, expected):
    app, _, path = app_with_db
    _set_user(path, db_plan, until)
    with app.app.test_request_context('/'):
        from flask import session
        session.update(user_id=1, plan='premium')
        assert app.is_premium() is expected
        assert session['plan'] == ('premium' if expected else 'free')


def test_free_session_recovers_valid_durable_entitlement(app_with_db):
    app, _, path = app_with_db
    _set_user(path, 'premium', '2030-01-01T00:00:00')
    with app.app.test_request_context('/'):
        from flask import session
        session.update(user_id=1, plan='free')
        assert app.is_premium() is True
        assert session['plan'] == 'premium'


def test_request_cache_is_per_uid_and_does_not_reuse_stale_session(app_with_db):
    app, factory, path = app_with_db
    _set_user(path, 'premium', '2030-01-01T00:00:00')
    with app.app.test_request_context('/'):
        from flask import session
        session.update(user_id=1, plan='premium')
        assert app.is_premium() is True
        assert app.is_premium() is True
        assert factory.queries == 1


def test_db_failure_with_stale_premium_session_never_fails_open(app_with_db, monkeypatch):
    app, _, _ = app_with_db
    monkeypatch.setattr(app, 'get_db', lambda: (_ for _ in ()).throw(sqlite3.OperationalError('offline')))
    with app.app.test_request_context('/'):
        from flask import session
        session.update(user_id=1, plan='premium')
        with pytest.raises(sqlite3.OperationalError, match='offline'):
            app.is_premium()


def test_admin_override_remains_authorized_without_entitlement_query(app_with_db):
    app, factory, _ = app_with_db
    with app.app.test_request_context('/'):
        from flask import session
        session.update(user_id=1, plan='free', is_admin=True)
        assert app.is_premium() is True
        assert factory.queries == 0


def test_two_stale_sessions_are_denied_after_durable_revocation(app_with_db):
    app, _, path = app_with_db
    _set_user(path, 'free', None)
    for _ in range(2):
        with app.app.test_request_context('/'):
            from flask import session
            session.update(user_id=1, plan='premium')
            assert app.is_premium() is False
            assert session['plan'] == 'free'


def test_protected_daily_history_route_denies_stale_premium_session(app_with_db):
    app, _, path = app_with_db
    _set_user(path, 'premium', '2000-01-01T00:00:00')
    client = app.app.test_client()
    with client.session_transaction() as sess:
        sess.update(user_id=1, plan='premium', is_admin=False)
    response = client.get('/api/daily-challenge/history')
    assert response.status_code == 403
    with client.session_transaction() as sess:
        assert sess['plan'] == 'free'


def test_evaluator_is_pure_and_malformed_expiry_fails_closed(app_with_db):
    app, _, _ = app_with_db
    assert app._evaluate_premium_entitlement('premium', None) is True
    assert app._evaluate_premium_entitlement('premium', 'not-a-date') is False
    assert app._evaluate_premium_entitlement('free', None) is False
