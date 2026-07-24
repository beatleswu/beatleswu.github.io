"""Regression tests for ECON-RS-1: POST /api/rewards/sync atomicity and
idempotency.

Confirmed defect (pre-fix, app.py ~10537-10546): the handler ran
`INSERT OR IGNORE INTO reward_claimed(...)` for each newly-completed stage
key without checking whether that insert actually won its PRIMARY KEY
(user_id, stage_key) -- the cursor's rowcount was discarded. Coins/XP for
every key in the originally-computed `new_keys` list were then added to the
totals unconditionally, and quest_accepted rows for every one of those keys
were deleted unconditionally too -- regardless of whether this specific
request's own insert actually claimed the row. A retry, a double-submit, or
two genuinely concurrent requests for the same (user_id, stage_key) each
independently compute the same `new_keys`; only one of their inserts can
ever land (the table's own composite PRIMARY KEY guarantees that), but
every one of them granted coins/XP as if it had won.

Fix: capture the INSERT's cursor and check `cursor.rowcount == 1`. Only a
key this transaction's own insert actually won is added to
`tot_c`/`tot_x`/`granted`, and only that key's quest_accepted row is
cleared. A key that loses the race (rowcount == 0 -- the identical primary
key already exists, whether from an earlier request or a concurrent one)
grants nothing and leaves its quest_accepted row untouched. Claim
insertion, the coins/XP mutation, and quest-state clearing all still run
inside the one transaction the request already used (`with get_db() as
conn: ... conn.commit()`), so a failure anywhere rolls back everything.
"""
import contextlib
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import types
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


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
        module.grimoire_bp = Blueprint('grimoire_stub_rewards_sync', __name__)
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


@pytest.fixture()
def client(app_module):
    app_module.app.config['TESTING'] = True
    return app_module.app.test_client()


# Two synthetic guild-quest segments, standing in for real question-bank
# data -- _quest_segments is monkeypatched to return exactly these, so
# tests never depend on the real /questions.json content.
FIXED_SEGMENTS = {
    'demo::LV1::1-2': {
        'quest_key': 'demo::LV1::1-2',
        'legacy_key': 'demo::LV1',
        'discipline': 'demo',
        'stage': 'LV1',
        'segment_index': 1,
        'range_start': 1,
        'range_end': 2,
        'total': 2,
        'question_ids': [90001, 90002],
        'coins': 50,
        'xp': 20,
    },
    'demo::LV2::1-2': {
        'quest_key': 'demo::LV2::1-2',
        'legacy_key': 'demo::LV2',
        'discipline': 'demo',
        'stage': 'LV2',
        'segment_index': 1,
        'range_start': 1,
        'range_end': 2,
        'total': 2,
        'question_ids': [90003, 90004],
        'coins': 30,
        'xp': 10,
    },
}


@pytest.fixture()
def sqlite_conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE srs_cards (
        user_id     INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        PRIMARY KEY (user_id, question_id)
    )''')
    conn.execute('''CREATE TABLE user_stats (
        user_id    INTEGER PRIMARY KEY,
        coins      INTEGER NOT NULL DEFAULT 0,
        xp         INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT
    )''')
    conn.execute('''CREATE TABLE reward_claimed (
        user_id    INTEGER NOT NULL,
        stage_key  TEXT    NOT NULL,
        coins      INTEGER NOT NULL DEFAULT 0,
        xp         INTEGER NOT NULL DEFAULT 0,
        claimed_at TEXT,
        PRIMARY KEY (user_id, stage_key)
    )''')
    conn.execute('''CREATE TABLE quest_accepted (
        user_id     INTEGER NOT NULL,
        quest_key   TEXT    NOT NULL,
        accepted_at TEXT    NOT NULL,
        PRIMARY KEY (user_id, quest_key)
    )''')
    conn.commit()
    yield conn
    conn.close()


class _FakeDbConnCtx:
    """Mimics db.PostgresConnectionWrapper's context-manager protocol
    around a persistent shared sqlite3 connection: commits on clean exit,
    rolls back on exception -- exactly the atomicity property the real
    `with get_db() as conn: ...` block in rewards_sync() depends on."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        return self._conn.execute(sql, params or ())

    def commit(self):
        self._conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        return False


@pytest.fixture()
def patched_get_db(app_module, sqlite_conn, monkeypatch):
    monkeypatch.setattr(app_module, 'get_db', lambda: _FakeDbConnCtx(sqlite_conn))
    return sqlite_conn


@pytest.fixture()
def stub_quest_state(app_module, monkeypatch):
    monkeypatch.setattr(app_module, '_quest_segments', lambda premium: dict(FIXED_SEGMENTS))
    monkeypatch.setattr(app_module, 'is_premium', lambda uid=None: False)


def _login(client, uid):
    with client.session_transaction() as sess:
        sess['user_id'] = uid


def _mark_practiced(conn, uid, question_ids):
    for qid in question_ids:
        conn.execute('INSERT INTO srs_cards(user_id, question_id) VALUES (?, ?)', (uid, qid))
    conn.commit()


def _accept_quest(conn, uid, quest_key):
    conn.execute(
        'INSERT INTO quest_accepted(user_id, quest_key, accepted_at) VALUES (?, ?, ?)',
        (uid, quest_key, 'accepted-at-test'),
    )
    conn.commit()


def _user_stats(conn, uid):
    row = conn.execute('SELECT coins, xp FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    return (row['coins'], row['xp']) if row else (0, 0)


def _claimed_keys(conn, uid):
    rows = conn.execute('SELECT stage_key FROM reward_claimed WHERE user_id=?', (uid,)).fetchall()
    return {r['stage_key'] for r in rows}


def _accepted_keys(conn, uid):
    rows = conn.execute('SELECT quest_key FROM quest_accepted WHERE user_id=?', (uid,)).fetchall()
    return {r['quest_key'] for r in rows}


class TestFirstSuccessfulSync:
    def test_first_sync_grants_reward_once(self, client, app_module, patched_get_db, stub_quest_state):
        uid = 301
        _mark_practiced(patched_get_db, uid, [90001, 90002])
        _accept_quest(patched_get_db, uid, 'demo::LV1::1-2')
        _login(client, uid)

        resp = client.post('/api/rewards/sync', json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['gained_coins'] == 50
        assert body['gained_xp'] == 20
        assert body['coins'] == 50
        assert body['xp'] == 20
        assert [g['quest_key'] for g in body['granted']] == ['demo::LV1::1-2']

        assert _claimed_keys(patched_get_db, uid) == {'demo::LV1::1-2'}
        assert _user_stats(patched_get_db, uid) == (50, 20)
        assert _accepted_keys(patched_get_db, uid) == set()  # cleared for the winning key


class TestIdenticalRetryIsNoop:
    def test_retry_grants_nothing_and_does_not_duplicate_claim(self, client, app_module, patched_get_db, stub_quest_state):
        uid = 302
        _mark_practiced(patched_get_db, uid, [90001, 90002])
        _login(client, uid)

        first = client.post('/api/rewards/sync', json={})
        assert first.get_json()['gained_coins'] == 50

        second = client.post('/api/rewards/sync', json={})
        body = second.get_json()
        assert body['granted'] == []
        assert body['gained_coins'] == 0
        assert body['gained_xp'] == 0
        assert body['coins'] == 50  # unchanged from the first call
        assert body['xp'] == 20

        row = patched_get_db.execute(
            'SELECT COUNT(*) AS n FROM reward_claimed WHERE user_id=? AND stage_key=?',
            (uid, 'demo::LV1::1-2'),
        ).fetchone()
        assert row['n'] == 1  # not duplicated


class TestManyRetriesGrantExactlyOnce:
    def test_repeated_retries_never_exceed_one_grant(self, client, app_module, patched_get_db, stub_quest_state):
        uid = 303
        _mark_practiced(patched_get_db, uid, [90001, 90002])
        _login(client, uid)

        for _ in range(10):
            resp = client.post('/api/rewards/sync', json={})
            assert resp.status_code == 200

        assert _user_stats(patched_get_db, uid) == (50, 20)
        assert len(_claimed_keys(patched_get_db, uid)) == 1


class TestMixedBatchAlreadyClaimedAndNewlyClaimed:
    def test_mixed_batch_only_grants_the_newly_claimed_key(self, client, app_module, patched_get_db, stub_quest_state):
        uid = 304
        _mark_practiced(patched_get_db, uid, [90001, 90002, 90003, 90004])
        # demo::LV1::1-2 was already claimed and granted by an earlier request.
        patched_get_db.execute(
            'INSERT INTO reward_claimed(user_id,stage_key,coins,xp,claimed_at) VALUES (?,?,?,?,?)',
            (uid, 'demo::LV1::1-2', 50, 20, 'earlier'),
        )
        patched_get_db.execute(
            'INSERT INTO user_stats(user_id,coins,xp,updated_at) VALUES (?,?,?,?)',
            (uid, 50, 20, 'earlier'),
        )
        patched_get_db.commit()
        _login(client, uid)

        resp = client.post('/api/rewards/sync', json={})
        body = resp.get_json()
        assert [g['quest_key'] for g in body['granted']] == ['demo::LV2::1-2']
        assert body['gained_coins'] == 30
        assert body['gained_xp'] == 10
        assert body['coins'] == 80  # 50 (earlier) + 30 (this request)
        assert body['xp'] == 30
        assert _claimed_keys(patched_get_db, uid) == {'demo::LV1::1-2', 'demo::LV2::1-2'}


class TestLosingTheClaimRaceGrantsNothing:
    def test_key_that_loses_the_insert_race_grants_nothing_and_keeps_quest_accepted(
        self, client, app_module, sqlite_conn, monkeypatch, stub_quest_state,
    ):
        """Simulates a real concurrent-request race without needing real
        threads: right as this request's own INSERT OR IGNORE for
        demo::LV1::1-2 is about to run, a "concurrent" transaction sneaks
        in and claims the exact same (user_id, stage_key) a moment
        earlier, so this request's own insert legitimately loses the
        PRIMARY KEY race (rowcount == 0). The real cross-thread version of
        this same guarantee is verified against real PostgreSQL below."""
        uid = 305
        _mark_practiced(sqlite_conn, uid, [90001, 90002, 90003, 90004])
        _accept_quest(sqlite_conn, uid, 'demo::LV1::1-2')
        _accept_quest(sqlite_conn, uid, 'demo::LV2::1-2')

        class _RaceSimulatingConnCtx(_FakeDbConnCtx):
            def __init__(self, conn):
                super().__init__(conn)
                self._sneaked = False

            def execute(self, sql, params=None):
                if (not self._sneaked and 'INTO reward_claimed' in sql
                        and params and params[1] == 'demo::LV1::1-2'):
                    self._sneaked = True
                    self._conn.execute(
                        'INSERT INTO reward_claimed(user_id,stage_key,coins,xp,claimed_at) '
                        'VALUES (?,?,?,?,?)',
                        (uid, 'demo::LV1::1-2', 999999, 999999, 'concurrent-winner'),
                    )
                return self._conn.execute(sql, params or ())

        monkeypatch.setattr(app_module, 'get_db', lambda: _RaceSimulatingConnCtx(sqlite_conn))
        _login(client, uid)

        resp = client.post('/api/rewards/sync', json={})
        body = resp.get_json()

        # Only the key that actually won its own insert is granted.
        assert [g['quest_key'] for g in body['granted']] == ['demo::LV2::1-2']
        assert body['gained_coins'] == 30
        assert body['gained_xp'] == 10

        # The "concurrent winner"'s claim row is untouched by this losing
        # request -- not overwritten, not duplicated.
        row = sqlite_conn.execute(
            'SELECT coins, xp FROM reward_claimed WHERE user_id=? AND stage_key=?',
            (uid, 'demo::LV1::1-2'),
        ).fetchone()
        assert (row['coins'], row['xp']) == (999999, 999999)

        # Quest state is cleared only for the winning key -- the losing
        # key's quest_accepted row must survive untouched.
        assert _accepted_keys(sqlite_conn, uid) == {'demo::LV1::1-2'}


class TestRollbackLeavesNoClaimAndNoReward:
    def test_failure_after_claim_insertion_rolls_back_the_claim_too(
        self, client, app_module, sqlite_conn, monkeypatch, stub_quest_state,
    ):
        uid = 306
        _mark_practiced(sqlite_conn, uid, [90001, 90002])
        _accept_quest(sqlite_conn, uid, 'demo::LV1::1-2')

        class _BoomOnQuestClearConnCtx(_FakeDbConnCtx):
            def execute(self, sql, params=None):
                if 'DELETE FROM quest_accepted' in sql:
                    raise RuntimeError('simulated failure after claim insertion')
                return self._conn.execute(sql, params or ())

        monkeypatch.setattr(app_module, 'get_db', lambda: _BoomOnQuestClearConnCtx(sqlite_conn))
        _login(client, uid)

        with pytest.raises(RuntimeError):
            client.post('/api/rewards/sync', json={})

        # Nothing half-committed: no claim row, no coins/xp, quest_accepted untouched.
        assert _claimed_keys(sqlite_conn, uid) == set()
        assert _user_stats(sqlite_conn, uid) == (0, 0)
        assert _accepted_keys(sqlite_conn, uid) == {'demo::LV1::1-2'}

    def test_reward_grant_failure_rolls_back_the_claim_insertion_too(
        self, client, app_module, sqlite_conn, monkeypatch, stub_quest_state,
    ):
        uid = 307
        _mark_practiced(sqlite_conn, uid, [90001, 90002])

        class _BoomOnRewardGrantConnCtx(_FakeDbConnCtx):
            def execute(self, sql, params=None):
                if 'INSERT INTO user_stats' in sql:
                    raise RuntimeError('simulated reward-grant failure')
                return self._conn.execute(sql, params or ())

        monkeypatch.setattr(app_module, 'get_db', lambda: _BoomOnRewardGrantConnCtx(sqlite_conn))
        _login(client, uid)

        with pytest.raises(RuntimeError):
            client.post('/api/rewards/sync', json={})

        assert _claimed_keys(sqlite_conn, uid) == set()
        assert _user_stats(sqlite_conn, uid) == (0, 0)


# ── Real-PostgreSQL concurrency: two genuinely concurrent threads, two
# independent Flask test-client sessions for the SAME user, racing the
# SAME stage key against a real disposable Postgres container -- proves
# the fix under real transaction isolation, not just single-threaded
# sqlite3 simulation. ──────────────────────────────────────────────────

def _docker_available():
    if shutil.which('docker') is None:
        return False
    result = subprocess.run(['docker', 'version', '--format', '{{.Server.Version}}'], capture_output=True, text=True)
    return result.returncode == 0 and bool(result.stdout.strip())


def _wait_for_port(host, port, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f'timed out waiting for {host}:{port}')


def _wait_for_postgres(database_url, timeout=30.0):
    import psycopg2
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            conn = psycopg2.connect(database_url)
            conn.close()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    raise last_error


@contextlib.contextmanager
def _postgres_container():
    if not _docker_available():
        pytest.skip('docker server unavailable for disposable PostgreSQL reward-sync test')
    container_name = f'go-odyssey-reward-sync-test-{uuid.uuid4().hex[:10]}'
    run = subprocess.run(
        ['docker', 'run', '--rm', '-d', '--name', container_name,
         '-e', 'POSTGRES_PASSWORD=go', '-e', 'POSTGRES_USER=go', '-e', 'POSTGRES_DB=go_odyssey',
         '-p', '127.0.0.1::5432', 'postgres:16-alpine'],
        capture_output=True, text=True, check=True,
    )
    container_id = run.stdout.strip()
    try:
        port_result = subprocess.run(['docker', 'port', container_id, '5432/tcp'], capture_output=True, text=True, check=True)
        host, port_text = port_result.stdout.strip().rsplit(':', 1)
        port = int(port_text)
        _wait_for_port(host, port)
        database_url = f'postgresql://go:go@{host}:{port}/go_odyssey'
        _wait_for_postgres(database_url)
        yield {'container_id': container_id, 'database_url': database_url}
    finally:
        subprocess.run(['docker', 'rm', '-f', container_id], capture_output=True, text=True)


def _create_pg_reward_schema(database_url):
    import psycopg2
    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute('''CREATE TABLE srs_cards (
        user_id     INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        PRIMARY KEY (user_id, question_id)
    )''')
    cur.execute('''CREATE TABLE user_stats (
        user_id    INTEGER PRIMARY KEY,
        coins      INTEGER NOT NULL DEFAULT 0,
        xp         INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT
    )''')
    cur.execute('''CREATE TABLE reward_claimed (
        user_id    INTEGER NOT NULL,
        stage_key  TEXT    NOT NULL,
        coins      INTEGER NOT NULL DEFAULT 0,
        xp         INTEGER NOT NULL DEFAULT 0,
        claimed_at TEXT,
        PRIMARY KEY (user_id, stage_key)
    )''')
    cur.execute('''CREATE TABLE quest_accepted (
        user_id     INTEGER NOT NULL,
        quest_key   TEXT    NOT NULL,
        accepted_at TEXT    NOT NULL,
        PRIMARY KEY (user_id, quest_key)
    )''')
    cur.close()
    conn.close()


class TestConcurrentSyncHasExactlyOneWinner:
    def test_disposable_postgres_two_concurrent_sessions_same_user_stage(
        self, app_module, monkeypatch, stub_quest_state,
    ):
        import psycopg2
        import db as db_module

        with _postgres_container() as pg:
            _create_pg_reward_schema(pg['database_url'])
            # db.py's connection pool is a module-level singleton created
            # lazily on first use and bound to whatever DATABASE_URL was
            # set at that moment -- force a fresh pool bound to this
            # disposable container instead of whatever (if anything) an
            # earlier test in this session already created.
            monkeypatch.setattr(db_module, 'DATABASE_URL', pg['database_url'])
            monkeypatch.setattr(db_module, '_pool', None)

            uid = 401
            seed_conn = psycopg2.connect(pg['database_url'])
            seed_cur = seed_conn.cursor()
            for qid in (90001, 90002):
                seed_cur.execute('INSERT INTO srs_cards(user_id, question_id) VALUES (%s, %s)', (uid, qid))
            seed_conn.commit()
            seed_cur.close()
            seed_conn.close()

            app_module.app.config['TESTING'] = True
            client_a = app_module.app.test_client()
            client_b = app_module.app.test_client()
            with client_a.session_transaction() as sess:
                sess['user_id'] = uid
            with client_b.session_transaction() as sess:
                sess['user_id'] = uid

            responses = {}

            def fire(name, client):
                responses[name] = client.post('/api/rewards/sync', json={})

            threads = [
                threading.Thread(target=fire, args=('a', client_a)),
                threading.Thread(target=fire, args=('b', client_b)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
                assert not thread.is_alive()

            assert set(responses) == {'a', 'b'}
            for resp in responses.values():
                assert resp.status_code == 200
            gained = {name: resp.get_json()['gained_coins'] for name, resp in responses.items()}
            winners = [name for name, coins in gained.items() if coins > 0]
            losers = [name for name, coins in gained.items() if coins == 0]
            # Exactly one of the two genuinely concurrent requests wins the
            # claim for demo::LV1::1-2; the other grants zero -- never both.
            assert len(winners) == 1, gained
            assert len(losers) == 1, gained
            assert gained[winners[0]] == 50

            verify_conn = psycopg2.connect(pg['database_url'])
            verify_cur = verify_conn.cursor()
            verify_cur.execute(
                'SELECT COUNT(*) FROM reward_claimed WHERE user_id=%s AND stage_key=%s',
                (uid, 'demo::LV1::1-2'),
            )
            assert verify_cur.fetchone()[0] == 1
            verify_cur.execute('SELECT coins, xp FROM user_stats WHERE user_id=%s', (uid,))
            coins, xp = verify_cur.fetchone()
            # Granted exactly once, from whichever side won -- never doubled.
            assert coins == 50
            assert xp == 20
            verify_cur.close()
            verify_conn.close()
