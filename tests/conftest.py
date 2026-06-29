"""Isolated Flask test bootstrap.

The production WSGI entrypoint is deliberately not imported: it monkey-patches
gevent, initializes PostgreSQL, and preloads the production question dataset.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import importlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash


# These values must be set before importing app.py.
os.environ["SECRET_KEY"] = "testing-baseline-secret"
os.environ["SOCKETIO_ASYNC_MODE"] = "threading"
os.environ["PREMIUM_WEEKLY_SCHEDULER_ENABLED"] = "0"
os.environ["SITE_URL"] = "http://localhost"
os.environ["TURNSTILE_SECRET"] = ""
os.environ["RESEND_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["SOCKETIO_MESSAGE_QUEUE"] = ""

# The pytest console entrypoint does not guarantee that the repository root is
# importable. Add it before importing the root-level app.py module.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

_APP_IMPORT_ERROR = None
app_module = None

try:
    app_module = importlib.import_module("app")
except ModuleNotFoundError as exc:
    if exc.name == "app":
        _APP_IMPORT_ERROR = exc
    else:
        raise


def require_backend_app():
    if app_module is None:
        pytest.skip(
            "backend-dependent tests require root-level app.py / app module; "
            "this GitHub clean clone only contains the static site and isolated SGF engine",
            allow_module_level=False,
        )
    return app_module


class SQLiteTestConnection:
    """Keep one in-memory connection alive across route context managers."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def execute(self, sql: str, parameters=None):
        if parameters is None:
            return self.connection.execute(sql)
        return self.connection.execute(sql, parameters)

    def executemany(self, sql: str, parameters):
        return self.connection.executemany(sql, parameters)

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()


def _create_auth_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            plan TEXT NOT NULL DEFAULT 'free',
            created_at TEXT,
            last_login TEXT,
            nickname TEXT,
            email TEXT UNIQUE COLLATE NOCASE,
            email_verified INTEGER NOT NULL DEFAULT 0,
            email_verify_token TEXT,
            email_token_expires TEXT,
            onboarding_required INTEGER NOT NULL DEFAULT 1,
            premium_until TEXT,
            google_sub TEXT,
            elo_rating REAL NOT NULL DEFAULT 1400
        );

        CREATE TABLE user_stats (
            user_id INTEGER PRIMARY KEY
        );
        """
    )


@pytest.fixture
def isolated_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[sqlite3.Connection]:
    backend = require_backend_app()
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    _create_auth_schema(connection)
    wrapper = SQLiteTestConnection(connection)

    monkeypatch.setattr(backend, "get_db", lambda: wrapper)
    monkeypatch.setattr(backend, "_send_email_async", lambda *args, **kwargs: None)
    monkeypatch.setattr(backend, "_notify_admin_new_user", lambda *args, **kwargs: None)
    backend._auth_fail_log.clear()

    yield connection
    connection.close()


@pytest.fixture
def lightweight_questions(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Small in-memory data; _load_questions never opens questions.json."""
    backend = require_backend_app()
    questions = [
        {
            "id": 101,
            "topic": "Test Book",
            "level": "Test Chapter",
            "display_name": "Corner capture",
            "source": "fixtures/corner-capture.sgf",
            "difficulty": "30k",
            "rank": "30k",
            "enabled": True,
            "content": "(;SZ[19]PL[B];B[dd])",
            "accepted_moves": [{"x": 3, "y": 3}],
            "discipline": "capture_escape",
            "stage": "LV1",
            "sort_order": 1,
        }
    ]
    monkeypatch.setattr(backend, "_load_questions", lambda: questions)
    return questions


@pytest.fixture
def app(isolated_db: sqlite3.Connection, lightweight_questions: list[dict]):
    backend = require_backend_app()
    backend.app.config.update(
        TESTING=True,
        SECRET_KEY="testing-baseline-secret",
        SESSION_COOKIE_SECURE=False,
    )
    return backend.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seeded_user(isolated_db: sqlite3.Connection) -> dict:
    password = "correct-horse-123"
    cursor = isolated_db.execute(
        """
        INSERT INTO users (
            username, password_hash, is_admin, plan, created_at,
            nickname, email, email_verified, onboarding_required
        ) VALUES (?, ?, 0, 'free', '2026-06-27T00:00:00', ?, ?, 1, 0)
        """,
        ("alice", generate_password_hash(password), "Alice", "alice@example.test"),
    )
    isolated_db.execute(
        "INSERT INTO user_stats(user_id) VALUES (?)",
        (cursor.lastrowid,),
    )
    isolated_db.commit()
    return {
        "id": cursor.lastrowid,
        "username": "alice",
        "password": password,
        "email": "alice@example.test",
    }


@pytest.fixture
def authenticated_client(client, seeded_user: dict):
    with client.session_transaction() as flask_session:
        flask_session["user_id"] = seeded_user["id"]
        flask_session["username"] = seeded_user["username"]
        flask_session["nickname"] = "Alice"
        flask_session["is_admin"] = False
        flask_session["plan"] = "free"
    return client
