"""Regression coverage for the 2026-07-14 `/api/community/leaderboard`
HTTP 500 incident.

Root cause: PR #102 (commit 8d9f0f82d) changed the INTEGER-compatible

    COALESCE(u.is_admin,0) AS is_admin

into the PostgreSQL-illegal

    CASE WHEN COALESCE(u.is_admin,FALSE) THEN 1 ELSE 0 END AS is_admin

Production's `users.is_admin` column is `INTEGER`, not `BOOLEAN`; Postgres
refuses to COALESCE an integer column with a boolean literal
(`psycopg2.errors.DatatypeMismatch: COALESCE types integer and boolean
cannot be matched`). The existing SQLite-backed reward test suite did not
catch this because SQLite is dynamically typed, and the one existing
disposable-Postgres test fixture (`_create_pg_schema` in
test_community_leaderboard_weekly_scheduler.py) itself creates `is_admin
BOOLEAN`, which does not match production's actual `INTEGER` column.

This file adds:
  1. A static query-contract test (no DB required) pinning the
     integer-safe expression and forbidding the old boolean-incompatible
     one from ever reappearing.
  2. A dynamic test against a disposable, non-production PostgreSQL
     container -- with the CORRECT `is_admin INTEGER` schema matching
     production -- exercising fetch_leaderboard_participant_rows()
     directly (the exact function/line that raised in production) across
     NULL / 0 / 1 / other-nonzero-integer values.

No production secret, credential, or connection is used anywhere in this
file. No new DB migration is introduced.
"""
import contextlib
import re
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import community_leaderboard_rewards as lbr

COMMUNITY_LEADERBOARD_REWARDS_FILE = REPO_ROOT / "community_leaderboard_rewards.py"


# ---------------------------------------------------------------------------
# 1. Static query-contract test (no DB required).
# ---------------------------------------------------------------------------

def test_fetch_leaderboard_participant_rows_sql_is_integer_safe():
    source = COMMUNITY_LEADERBOARD_REWARDS_FILE.read_text(encoding="utf-8")
    assert "COALESCE(u.is_admin,FALSE)" not in source, (
        "must never reintroduce the PostgreSQL-illegal boolean COALESCE "
        "against the integer users.is_admin column -- this is exactly "
        "what caused the 2026-07-14 /api/community/leaderboard 500"
    )
    assert re.search(r"COALESCE\(u\.is_admin,\s*0\)\s*<>\s*0", source), (
        "expected the integer-safe "
        "`COALESCE(u.is_admin, 0) <> 0` expression"
    )


# ---------------------------------------------------------------------------
# 2. Dynamic test against a disposable, non-production PostgreSQL container
#    with the schema production actually has (is_admin INTEGER).
# ---------------------------------------------------------------------------

def _docker_available():
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _wait_for_port(host, port, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f"timed out waiting for {host}:{port}")


def _wait_for_postgres(database_url, timeout=30.0):
    import psycopg2

    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            conn = psycopg2.connect(database_url)
            conn.close()
            return
        except Exception as exc:  # noqa: BLE001 - retry loop, re-raised below
            last_error = exc
            time.sleep(0.5)
    raise last_error


@contextlib.contextmanager
def _disposable_postgres():
    if not _docker_available():
        pytest.skip("docker unavailable for disposable PostgreSQL regression test")
    container_name = f"go-odyssey-admin-type-test-{uuid.uuid4().hex[:10]}"
    run = subprocess.run(
        [
            "docker", "run", "--rm", "-d",
            "--name", container_name,
            "-e", "POSTGRES_PASSWORD=test",
            "-e", "POSTGRES_USER=test",
            "-e", "POSTGRES_DB=test",
            "-p", "127.0.0.1::5432",
            "postgres:16-alpine",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    container_id = run.stdout.strip()
    try:
        port_result = subprocess.run(
            ["docker", "port", container_id, "5432/tcp"],
            capture_output=True,
            text=True,
            check=True,
        )
        host, port_text = port_result.stdout.strip().rsplit(":", 1)
        port = int(port_text)
        _wait_for_port(host, port)
        database_url = f"postgresql://test:test@{host}:{port}/test"
        _wait_for_postgres(database_url)
        yield database_url
    finally:
        subprocess.run(["docker", "rm", "-f", container_id], capture_output=True, text=True)


def _pg_connect(database_url):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    conn.cursor_factory = DictCursor
    return PostgresConnectionWrapper(conn, pooled=False)


def _create_schema_matching_production(conn):
    # is_admin INTEGER matches production's actual column type (confirmed
    # 2026-07-14 via a read-only `information_schema.columns` query:
    # data_type=integer, is_nullable=NO, column_default=0) -- NOT BOOLEAN,
    # which is what the existing weekly-scheduler test's own
    # disposable-Postgres fixture uses and why it never caught this bug.
    #
    # Production currently enforces NOT NULL DEFAULT 0, so a real NULL
    # can't occur there today -- but is_admin is left nullable here so
    # this test can still exercise the COALESCE(...,0) NULL-defensive
    # branch, matching this repo's convention of defending against NULL
    # even where a constraint currently forbids it.
    conn.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            nickname TEXT,
            is_admin INTEGER,
            plan TEXT NOT NULL DEFAULT 'free'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE review_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            grade INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE TABLE user_stats (user_id INTEGER PRIMARY KEY, rank_level TEXT)")
    conn.execute(
        """
        CREATE TABLE player_appearance (
            user_id INTEGER PRIMARY KEY,
            character_key TEXT,
            combat_armor TEXT,
            combat_weapon TEXT,
            combat_cape TEXT,
            combat_offhand TEXT,
            combat_hat TEXT,
            combat_pet TEXT,
            combat_aura TEXT
        )
        """
    )
    conn.commit()


def _add_user(conn, user_id, username, *, is_admin):
    conn.execute(
        "INSERT INTO users(id, username, is_admin) VALUES(%s,%s,%s)",
        (user_id, username, is_admin),
    )


def _add_solve(conn, user_id, question_id, *, grade=3, reviewed_at="2026-07-01T00:00:00"):
    conn.execute(
        "INSERT INTO review_log(user_id, question_id, grade, reviewed_at) VALUES(%s,%s,%s,%s)",
        (user_id, question_id, grade, reviewed_at),
    )


def test_fetch_leaderboard_participant_rows_against_production_shaped_schema():
    """Direct regression test for the exact function/line that raised in
    production: fetch_leaderboard_participant_rows() must not raise
    against a real PostgreSQL server with an INTEGER is_admin column, and
    must normalize NULL/0/1/other-nonzero-integer to 0/1 output."""
    with _disposable_postgres() as database_url:
        conn = _pg_connect(database_url)
        try:
            _create_schema_matching_production(conn)

            _add_user(conn, 1, "regular_user", is_admin=0)
            _add_user(conn, 2, "admin_user", is_admin=1)
            _add_user(conn, 3, "legacy_admin_flag", is_admin=2)  # other nonzero int
            _add_user(conn, 4, "null_admin_flag", is_admin=None)

            for user_id in (1, 2, 3, 4):
                _add_solve(conn, user_id, question_id=100 + user_id)
            conn.commit()

            # This is the exact call, with the exact SQL, that raised
            # psycopg2.errors.DatatypeMismatch in production.
            rows = lbr.fetch_leaderboard_participant_rows(conn, "2026-06-01T00:00:00")
        finally:
            conn.close()

    by_id = {row["id"]: row for row in rows}
    assert set(by_id) == {1, 2, 3, 4}
    assert by_id[1]["is_admin"] == 0, "is_admin=0 must normalize to 0"
    assert by_id[2]["is_admin"] == 1, "is_admin=1 must normalize to 1"
    assert by_id[3]["is_admin"] == 1, "is_admin=2 (other nonzero) must normalize to 1"
    assert by_id[4]["is_admin"] == 0, "is_admin=NULL must normalize to 0"

    # Every row must be JSON-serializable with plain Python types (0/1
    # ints), for both regular users and admins -- the app.py route
    # serializes this straight into the JSON response.
    import json

    for row in rows:
        json.dumps({"id": row["id"], "is_admin": row["is_admin"], "is_premium": row["is_premium"]})
