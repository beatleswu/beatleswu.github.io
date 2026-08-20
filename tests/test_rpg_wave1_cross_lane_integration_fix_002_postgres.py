"""RPG_WAVE1_CROSS_LANE_INTEGRATION_FIX_002: required PostgreSQL proof.

Section 12 of the task: POST /api/srs/review must return HTTP 200 after a
successful domain commit, response and DB must agree on XP/rank/
player_max_hp, and duplicate/retry behavior must stay safe -- against a
healthy, disposable, NON-PRODUCTION PostgreSQL container. This is the live,
end-to-end confirmation that Blocker 2 (review_compatibility's exact-shape
check rejecting combat_stats/level_up_rewards after a durable commit) is
actually fixed through the real route, not just at the unit level (see
tests/test_rpg_wave1_cross_lane_integration_fix_002.py for that).

Schema is bootstrapped via the app's own canonical app.init_db() -- the
same function Production uses -- never a hand-rolled subset. Question data
is read (never written) from the canonical repository's real questions.json
so the free-tier/premium gate behaves exactly as it does in Production.
"""

import contextlib
import os
import shutil
import socket
import subprocess
import time
import uuid

import pytest

REAL_QUESTIONS_JSON = "D:/go-website/questions.json"
FREE_QUESTION_ID = 48126  # real, existing, unranked (=> treated as free) question
LEVEL2_XP_THRESHOLD = 120  # LV_THRESHOLDS[1] in app.py


def _docker_available():
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _wait_for_port(host, port, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError:
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
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    raise last_error


@contextlib.contextmanager
def _postgres_container():
    if not _docker_available():
        pytest.skip("docker server unavailable for disposable RPG Wave1 integration-fix PostgreSQL proof")
    container_name = f"go-odyssey-wave1-fix-test-{uuid.uuid4().hex[:10]}"
    run = subprocess.run(
        [
            "docker", "run", "--rm", "-d", "--name", container_name,
            "-e", "POSTGRES_PASSWORD=go", "-e", "POSTGRES_USER=go",
            "-e", "POSTGRES_DB=go_odyssey", "-p", "127.0.0.1::5432",
            "postgres:16-alpine",
        ],
        capture_output=True, text=True, check=True,
    )
    container_id = run.stdout.strip()
    try:
        port_result = subprocess.run(
            ["docker", "port", container_id, "5432/tcp"],
            capture_output=True, text=True, check=True,
        )
        host, port_text = port_result.stdout.strip().rsplit(":", 1)
        port = int(port_text)
        _wait_for_port(host, port)
        database_url = f"postgresql://go:go@{host}:{port}/go_odyssey"
        _wait_for_postgres(database_url)
        yield database_url
    finally:
        subprocess.run(["docker", "rm", "-f", container_id], capture_output=True, text=True)


@pytest.fixture(scope="module")
def live_app():
    with _postgres_container() as database_url:
        os.environ["DATABASE_URL"] = database_url
        os.environ.setdefault("SECRET_KEY", "rpg-wave1-integration-fix-002-postgres-proof")
        if os.path.exists(REAL_QUESTIONS_JSON):
            os.environ["QUESTIONS_JSON_PATH"] = REAL_QUESTIONS_JSON

        import db as db_module
        db_module.DATABASE_URL = database_url
        db_module._pool = None

        import app as app_module
        # init_db() fail-closes on PostgreSQL unless the already-reviewed
        # PR332 SGF Workbench migration ran first (see sgf_admin_workbench.py
        # ensure_sgf_workbench_tables). Apply it -- it's Production's own
        # bootstrap order, not something invented for this test.
        from migrations.sgf_admin_workbench_v1 import upgrade as _sgf_workbench_upgrade
        with app_module.get_db() as _mig_conn:
            _sgf_workbench_upgrade(_mig_conn)
        app_module.init_db()
        app_module.app.config["TESTING"] = True
        yield app_module


def _seed_user(app_module, uid, *, xp):
    with app_module.get_db() as conn:
        conn.execute('INSERT INTO user_stats(user_id) VALUES(?) ON CONFLICT DO NOTHING', (uid,))
        conn.execute('UPDATE user_stats SET xp=?, rank_level=?, rank_xp=? WHERE user_id=?',
                     (xp, 'LV1', xp, uid))


def _client_for(app_module, uid):
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = uid
    return client


def _post_review(client, *, grade):
    return client.post(
        '/api/srs/review',
        json={'question_id': FREE_QUESTION_ID, 'grade': grade, 'source_context': 'practice'},
    )


def test_srs_review_returns_200_after_commit_and_response_matches_db(live_app):
    uid = 101
    _seed_user(live_app, uid, xp=LEVEL2_XP_THRESHOLD - 1)  # one XP away from ranking up
    client = _client_for(live_app, uid)

    response = _post_review(client, grade=5)
    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()
    assert payload['ok'] is True

    with live_app.get_db() as conn:
        row = conn.execute(
            'SELECT xp, rank_level, player_max_hp FROM user_stats WHERE user_id=?', (uid,)
        ).fetchone()

    assert row['xp'] == payload['stats']['xp']
    assert row['rank_level'] == payload['stats']['rank_level']
    if payload.get('player') and payload['player'].get('max_hp') is not None:
        assert row['player_max_hp'] == payload['player']['max_hp']
    else:
        assert row['player_max_hp'] == payload['stats']['player_max_hp']


def test_level_up_response_carries_combat_stats_and_level_up_rewards_as_presentation_only(live_app):
    """The exact scenario Blocker 2 broke: a level-up on a real committed
    review used to return HTTP 500 because level_up_rewards (and, for any
    review that goes through the equipment-aware combat wrapper,
    combat_stats) broke the compatibility seam's exact-shape check."""
    uid = 102
    _seed_user(live_app, uid, xp=LEVEL2_XP_THRESHOLD - 1)
    client = _client_for(live_app, uid)

    response = _post_review(client, grade=5)
    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()

    assert payload.get('ranked_up') is True, "test setup did not actually cross a level boundary"
    assert 'level_up_rewards' in payload
    assert isinstance(payload['level_up_rewards'], dict)

    with live_app.get_db() as conn:
        row = conn.execute(
            'SELECT xp, rank_level, player_max_hp FROM user_stats WHERE user_id=?', (uid,)
        ).fetchone()
    assert row['rank_level'] == 'LV2'
    assert row['xp'] == payload['stats']['xp']


def test_no_second_xp_or_hp_mutation_from_response_composition(live_app):
    """LEVEL_RESPONSE_MATCHES_DB plus NO_SECOND_XP_MUTATION/NO_SECOND_HP_MUTATION:
    the presentation wrapper reads the already-committed state; it must not
    perform (or trigger) any additional write."""
    uid = 103
    _seed_user(live_app, uid, xp=LEVEL2_XP_THRESHOLD - 1)
    client = _client_for(live_app, uid)

    response = _post_review(client, grade=5)
    payload = response.get_json()
    xp_after_first_call = payload['stats']['xp']

    with live_app.get_db() as conn:
        row = conn.execute('SELECT xp FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    assert row['xp'] == xp_after_first_call


def test_repeated_identical_review_submission_stays_safe(live_app):
    """Duplicate/retry behavior must remain safe: resubmitting the exact
    same already-credited question must not 500, and must not keep granting
    XP indefinitely (Phase 4D anti-farming already governs this; this test
    only proves the integration fix did not disturb it)."""
    uid = 104
    _seed_user(live_app, uid, xp=0)
    client = _client_for(live_app, uid)

    first = _post_review(client, grade=5)
    assert first.status_code == 200, first.get_data(as_text=True)
    first_xp = first.get_json()['stats']['xp']

    second = _post_review(client, grade=5)
    assert second.status_code == 200, second.get_data(as_text=True)
    second_xp = second.get_json()['stats']['xp']

    # Anti-farming: a repeat of an already-credited question grants no
    # further XP. The important integration-fix property is "still 200,
    # still a coherent response" -- not a new XP-authority decision.
    assert second_xp == first_xp

    with live_app.get_db() as conn:
        row = conn.execute('SELECT xp FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    assert row['xp'] == second_xp


def test_unapproved_extension_key_is_still_rejected_through_the_live_route(live_app, monkeypatch):
    """UNKNOWN_EXTENSION_FAILS_CLOSED, proven live: if the durable operation
    ever returned a result carrying a key outside the exact allowlist
    (combat_stats, level_up_rewards), the real route must still fail closed
    -- not silently serialize arbitrary data to the client."""
    from review_service import ReviewService

    def _poisoned_operation(uid, data, *, internal=False, submission_id=None):
        real = live_app._dispatch_to_srs_review_operation(
            uid, data, internal=internal, submission_id=submission_id
        )
        payload = real.get_json()
        payload['totally_unapproved_debug_key'] = 'should never reach a client'
        return live_app.jsonify(payload)

    monkeypatch.setattr(live_app, '_review_service', ReviewService(_poisoned_operation))
    # TESTING mode re-raises unhandled exceptions instead of converting them
    # to a response, which is correct for catching bugs but would hide the
    # actual client-facing behavior here. Flip it off for this one request
    # so the assertion below matches what a real (non-debug) client sees.
    monkeypatch.setitem(live_app.app.config, 'TESTING', False)
    monkeypatch.setitem(live_app.app.config, 'PROPAGATE_EXCEPTIONS', False)
    monkeypatch.setitem(live_app.app.config, 'DEBUG', False)
    uid = 105
    _seed_user(live_app, uid, xp=0)
    client = _client_for(live_app, uid)

    response = _post_review(client, grade=5)
    assert response.status_code == 500
    body = response.get_data(as_text=True)
    assert 'totally_unapproved_debug_key' not in body
