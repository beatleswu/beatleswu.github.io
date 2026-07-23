"""Regression tests for the adventure boss/finish server-authoritative
scoring fix (fix: make adventure boss scoring server-authoritative).

Trust boundary under test: before this fix, `correct`/`total` in
POST /api/adventure/boss/finish were read directly from the client JSON
body. This file proves the replacement design -- score is recomputed from
review_log evidence recorded during the attempt window -- closes that hole
without breaking the single finish contract shared by the legacy Adventure
UI and the E9 Adventure Shell.

Two tiers:
  * Tier 1 (`Test*AuthoritativeResult`): unit tests of the new pure helper
    `_adventure_boss_authoritative_result(conn, uid, exam)` against a
    disposable in-memory SQLite `review_log` table. This is where nearly
    all of the security-relevant assertions live.
  * Tier 2 (`Test*FinishRoute`): Flask test_client() tests of the real
    `/api/adventure/boss/finish` route, with `get_db` monkeypatched to the
    same SQLite backing store and `_adventure_state`/`_adventure_map_state`
    stubbed (unrelated, pre-existing, DB-heavy subsystems this PR does not
    touch) so the route test exercises the real session/evidence/upsert
    path without needing to replicate the whole adventure-progression
    schema.
"""
import re
import sqlite3
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(path):
    return (REPO_ROOT / path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# App import stubs (same set as tests/test_e9_adventure_shell_integration.py)
# ---------------------------------------------------------------------------

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
        module.grimoire_bp = Blueprint('grimoire_stub_boss_finish', __name__)
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


# ---------------------------------------------------------------------------
# SQLite-backed review_log / adventure_boss_progress fake
# ---------------------------------------------------------------------------

@pytest.fixture()
def sqlite_conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.create_function('GREATEST', 2, max)
    conn.execute('''CREATE TABLE review_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        grade INTEGER NOT NULL,
        reviewed_at TEXT NOT NULL
    )''')
    conn.execute('''CREATE TABLE adventure_boss_progress (
        user_id             INTEGER NOT NULL,
        zone_key            TEXT    NOT NULL,
        cleared             INTEGER NOT NULL DEFAULT 0,
        stars               INTEGER NOT NULL DEFAULT 0,
        attempts            INTEGER NOT NULL DEFAULT 0,
        best_score          INTEGER NOT NULL DEFAULT 0,
        cooldown_until_seen INTEGER NOT NULL DEFAULT 0,
        last_attempt_at     TEXT,
        cleared_at          TEXT,
        updated_at          TEXT,
        PRIMARY KEY (user_id, zone_key)
    )''')
    conn.commit()
    yield conn
    conn.close()


def _seed_review(conn, uid, question_id, grade, reviewed_at):
    conn.execute(
        'INSERT INTO review_log(user_id,question_id,grade,reviewed_at) VALUES (?,?,?,?)',
        (uid, question_id, grade, reviewed_at),
    )
    conn.commit()


class _FakeDbConnCtx:
    """Mimics db.PostgresConnectionWrapper's context-manager protocol around
    a persistent shared sqlite3 connection, so the two separate
    `with get_db() as conn:` blocks inside adventure_boss_finish() see the
    same data."""
    def __init__(self, sqlite_conn):
        self._conn = sqlite_conn

    def execute(self, sql, params=None):
        return self._conn.execute(sql, params or ())

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()


@pytest.fixture()
def patched_get_db(app_module, sqlite_conn, monkeypatch):
    monkeypatch.setattr(app_module, 'get_db', lambda: _FakeDbConnCtx(sqlite_conn))
    return sqlite_conn


@pytest.fixture()
def stub_adventure_state(app_module, monkeypatch):
    """_adventure_state/_adventure_map_state are pre-existing, DB-heavy
    (srs_cards/adventure_zone_unlocks/questions.json) subsystems this PR
    does not touch. Stubbing them keeps these route tests scoped to what
    changed: the boss/finish scoring-authority logic."""
    state = {'seen': 50}

    def fake_adventure_state(uid):
        return [{'key': 'k1_5', 'seen': state['seen'], 'unlocked': True, 'cleared': False}]

    def fake_map_state(uid, selected_stage_key=None, use_cache=False):
        return {}

    monkeypatch.setattr(app_module, '_adventure_state', fake_adventure_state)
    monkeypatch.setattr(app_module, '_adventure_map_state', fake_map_state)
    return state


ZONE_KEY = 'k1_5'

# Anchored to real "now" (not a hardcoded date) so this file's pass/fail
# behavior can never depend on what wall-clock time it happens to run at.
# The internal datetime.datetime.now() call inside
# _adventure_boss_authoritative_result runs a moment after _TEST_NOW, always
# comfortably inside [STARTED_AT, STARTED_AT + BOSS_ATTEMPT_MAX_MINUTES].
import datetime as _dt
_TEST_NOW = _dt.datetime.now()
STARTED_AT_DT = _TEST_NOW - _dt.timedelta(minutes=5)
STARTED_AT = STARTED_AT_DT.isoformat()


def _exam(question_ids, started_at=STARTED_AT, zone_key=ZONE_KEY):
    return {'zone_key': zone_key, 'question_ids': question_ids, 'started_at': started_at}


def within_window(offset_seconds=60):
    # STARTED_AT + offset, still comfortably inside BOSS_ATTEMPT_MAX_MINUTES
    # and safely in the past relative to _TEST_NOW.
    return (STARTED_AT_DT + _dt.timedelta(seconds=offset_seconds)).isoformat()


# ===========================================================================
# Tier 1 -- _adventure_boss_authoritative_result unit tests
# ===========================================================================

class TestAuthoritativeResultScenarios:

    def test_forged_perfect_score_with_failing_evidence_is_rejected(self, app_module, sqlite_conn):
        # All three answered, but all wrong -- a client claiming 3/3 must not
        # be honored; the server must independently derive 0/3.
        for qid in (101, 102, 103):
            _seed_review(sqlite_conn, uid=1, question_id=qid, grade=0, reviewed_at=within_window())
        correct, total = app_module._adventure_boss_authoritative_result(
            sqlite_conn, uid=1, exam=_exam([101, 102, 103]))
        assert (correct, total) == (0, 3)

    def test_forged_failing_score_with_passing_evidence_is_honored_server_side(self, app_module, sqlite_conn):
        # A client claiming 0/3 must not suppress a genuinely passing result.
        for qid in (201, 202, 203):
            _seed_review(sqlite_conn, uid=1, question_id=qid, grade=5, reviewed_at=within_window())
        correct, total = app_module._adventure_boss_authoritative_result(
            sqlite_conn, uid=1, exam=_exam([201, 202, 203]))
        assert (correct, total) == (3, 3)

    def test_another_users_correct_answers_are_not_counted(self, app_module, sqlite_conn):
        # qid 302 was answered correctly, but by a DIFFERENT user -- our own
        # user has no evidence for it, so the attempt must be incomplete.
        _seed_review(sqlite_conn, uid=1, question_id=301, grade=5, reviewed_at=within_window())
        _seed_review(sqlite_conn, uid=999, question_id=302, grade=5, reviewed_at=within_window())
        with pytest.raises(app_module._AdventureBossAttemptError) as exc:
            app_module._adventure_boss_authoritative_result(
                sqlite_conn, uid=1, exam=_exam([301, 302]))
        assert exc.value.code == 'incomplete_attempt'

    def test_answers_outside_attempt_window_are_not_counted(self, app_module, sqlite_conn):
        # qid 401 answered correctly, but BEFORE this attempt started
        # (leftover from unrelated free practice) -- must not count as
        # evidence for this boss attempt.
        before_start = (STARTED_AT_DT - _dt.timedelta(hours=1)).isoformat()
        _seed_review(sqlite_conn, uid=1, question_id=401, grade=5, reviewed_at=before_start)
        with pytest.raises(app_module._AdventureBossAttemptError) as exc:
            app_module._adventure_boss_authoritative_result(
                sqlite_conn, uid=1, exam=_exam([401]))
        assert exc.value.code == 'incomplete_attempt'

        # Symmetric case: a fabricated row timestamped after the evidence
        # window closes (started_at + BOSS_ATTEMPT_MAX_MINUTES), while the
        # attempt itself is still within its valid lifetime (now is still
        # well before the deadline) -- must be excluded as evidence, not
        # accepted just because SOME row exists for that question.
        far_after = (STARTED_AT_DT + _dt.timedelta(hours=3)).isoformat()
        _seed_review(sqlite_conn, uid=1, question_id=402, grade=5, reviewed_at=far_after)
        with pytest.raises(app_module._AdventureBossAttemptError) as exc2:
            app_module._adventure_boss_authoritative_result(
                sqlite_conn, uid=1, exam=_exam([402]))
        assert exc2.value.code in ('incomplete_attempt', 'attempt_expired')

    def test_missing_one_expected_question_fails_closed_no_partial_result(self, app_module, sqlite_conn):
        _seed_review(sqlite_conn, uid=1, question_id=501, grade=5, reviewed_at=within_window())
        _seed_review(sqlite_conn, uid=1, question_id=502, grade=5, reviewed_at=within_window())
        # qid 503 was never answered.
        with pytest.raises(app_module._AdventureBossAttemptError) as exc:
            app_module._adventure_boss_authoritative_result(
                sqlite_conn, uid=1, exam=_exam([501, 502, 503]))
        assert exc.value.code == 'incomplete_attempt'

    @pytest.mark.parametrize("first_grade,second_grade", [(0, 5), (5, 0)])
    def test_duplicate_records_are_deterministically_deduplicated(self, app_module, sqlite_conn, first_grade, second_grade):
        # Two review_log rows for the same question inside the window (e.g. a
        # client retry) must resolve deterministically regardless of order:
        # correct if ANY row for that question has grade>=3.
        _seed_review(sqlite_conn, uid=1, question_id=601, grade=first_grade, reviewed_at=within_window(10))
        _seed_review(sqlite_conn, uid=1, question_id=601, grade=second_grade, reviewed_at=within_window(20))
        correct, total = app_module._adventure_boss_authoritative_result(
            sqlite_conn, uid=1, exam=_exam([601]))
        assert (correct, total) == (1, 1)

    def test_unexpected_extra_question_ids_do_not_inflate_score(self, app_module, sqlite_conn):
        for qid in (701, 702, 703):
            _seed_review(sqlite_conn, uid=1, question_id=qid, grade=5, reviewed_at=within_window())
        # qid 999 is real evidence but not part of THIS exam.
        _seed_review(sqlite_conn, uid=1, question_id=999, grade=5, reviewed_at=within_window())
        correct, total = app_module._adventure_boss_authoritative_result(
            sqlite_conn, uid=1, exam=_exam([701, 702, 703]))
        assert (correct, total) == (3, 3)

    @pytest.mark.parametrize("bad_exam", [
        {},
        {'zone_key': 'k1_5'},
        {'zone_key': 'k1_5', 'question_ids': []},
        {'zone_key': 'k1_5', 'question_ids': 'not-a-list'},
        {'zone_key': 'k1_5', 'question_ids': [1, 2], 'started_at': None},
        {'zone_key': 'k1_5', 'question_ids': [1, 2], 'started_at': 'not-a-timestamp'},
        {'zone_key': 'k1_5', 'question_ids': ['abc'], 'started_at': STARTED_AT},
    ])
    def test_malformed_session_shapes_are_rejected(self, app_module, sqlite_conn, bad_exam):
        with pytest.raises(app_module._AdventureBossAttemptError) as exc:
            app_module._adventure_boss_authoritative_result(sqlite_conn, uid=1, exam=bad_exam)
        assert exc.value.code == 'malformed_session'

    def test_attempt_older_than_max_duration_is_rejected_even_with_full_evidence(self, app_module, sqlite_conn):
        old_started_at_dt = _TEST_NOW - _dt.timedelta(days=3)  # far more than 60 minutes ago
        old_started_at = old_started_at_dt.isoformat()
        _seed_review(sqlite_conn, uid=1, question_id=801, grade=5,
                     reviewed_at=(old_started_at_dt + _dt.timedelta(minutes=5)).isoformat())
        with pytest.raises(app_module._AdventureBossAttemptError) as exc:
            app_module._adventure_boss_authoritative_result(
                sqlite_conn, uid=1, exam=_exam([801], started_at=old_started_at))
        assert exc.value.code == 'attempt_expired'


# ===========================================================================
# Tier 2 -- /api/adventure/boss/finish route tests
# ===========================================================================

def _login(client, uid):
    with client.session_transaction() as sess:
        sess['user_id'] = uid


def _set_exam(client, exam):
    with client.session_transaction() as sess:
        sess['adventure_boss_exam'] = exam


class TestFinishRouteNoActiveSession:
    def test_no_active_boss_session_is_rejected(self, client, app_module, patched_get_db, stub_adventure_state):
        _login(client, 1)
        resp = client.post('/api/adventure/boss/finish', json={'correct': 20, 'total': 20})
        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'no_active_exam'


class TestFinishRouteLegitimateFlows:
    def test_legitimate_flow_with_honest_full_evidence_passes(self, client, app_module, patched_get_db, stub_adventure_state):
        uid = 7
        qids = list(range(1001, 1021))  # 20 questions, matching BOSS_EXAM_SIZE
        for qid in qids:
            _seed_review(patched_get_db, uid=uid, question_id=qid, grade=5, reviewed_at=within_window())
        _login(client, uid)
        _set_exam(client, _exam(qids))

        resp = client.post('/api/adventure/boss/finish', json={'correct': 20, 'total': 20})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['ok'] is True
        assert body['correct'] == 20
        assert body['total'] == 20
        assert body['passed'] is True

    def test_legitimate_flow_with_honest_failing_evidence_fails_with_cooldown(self, client, app_module, patched_get_db, stub_adventure_state):
        # This single shared finish contract is also the only one the E9
        # Adventure Shell uses -- grep-verified live here, not just asserted:
        # E9's own JS never calls boss/start or boss/finish directly.
        for f in (REPO_ROOT / 'js' / 'e9').rglob('*.js'):
            assert 'boss/finish' not in _read(f) and 'boss/start' not in _read(f), f

        uid = 8
        qids = list(range(2001, 2021))
        for qid in qids:
            # Only 10 of 20 correct -- below BOSS_PASS_SCORE (16).
            grade = 5 if qid < 2011 else 0
            _seed_review(patched_get_db, uid=uid, question_id=qid, grade=grade, reviewed_at=within_window())
        _login(client, uid)
        _set_exam(client, _exam(qids))

        resp = client.post('/api/adventure/boss/finish', json={'correct': 999, 'total': 999})  # forged, ignored
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['correct'] == 10
        assert body['total'] == 20
        assert body['passed'] is False
        assert body['cooldown_left'] == app_module.BOSS_FAIL_COOLDOWN


class TestFinishRouteReplayAndIdempotency:
    def test_replay_without_fresh_start_is_rejected_no_duplicate_mutation(self, client, app_module, patched_get_db, stub_adventure_state):
        uid = 9
        qids = list(range(3001, 3021))
        for qid in qids:
            _seed_review(patched_get_db, uid=uid, question_id=qid, grade=5, reviewed_at=within_window())
        _login(client, uid)
        _set_exam(client, _exam(qids))

        first = client.post('/api/adventure/boss/finish', json={})
        assert first.status_code == 200
        assert first.get_json()['passed'] is True

        # Session's exam slot is popped on completion -- an immediate second
        # call (simple replay, no fresh boss/start) must be rejected outright.
        second = client.post('/api/adventure/boss/finish', json={})
        assert second.status_code == 400
        assert second.get_json()['error'] == 'no_active_exam'

        row = patched_get_db.execute(
            'SELECT * FROM adventure_boss_progress WHERE user_id=? AND zone_key=?', (uid, ZONE_KEY)
        ).fetchone()
        assert row['attempts'] == 1  # not incremented by the rejected replay

    def test_resent_stale_session_reevaluation_does_not_create_a_new_clear_transition(self, client, app_module, patched_get_db, stub_adventure_state):
        # Simulates an attacker (or a client bug) resending an old, still
        # validly-signed session cookie whose exam slot was never popped
        # from their own copy. Because the idempotent upsert already
        # COALESCEs cleared_at, a second successful evaluation of an
        # already-cleared zone must not create a NEW clear transition.
        uid = 10
        qids = list(range(4001, 4021))
        for qid in qids:
            _seed_review(patched_get_db, uid=uid, question_id=qid, grade=5, reviewed_at=within_window())
        _login(client, uid)
        _set_exam(client, _exam(qids))

        first = client.post('/api/adventure/boss/finish', json={})
        assert first.status_code == 200
        row_after_first = patched_get_db.execute(
            'SELECT * FROM adventure_boss_progress WHERE user_id=? AND zone_key=?', (uid, ZONE_KEY)
        ).fetchone()
        cleared_at_first = row_after_first['cleared_at']
        assert cleared_at_first is not None

        # Manually reinject the same exam (as a resent stale cookie would).
        _set_exam(client, _exam(qids))
        second = client.post('/api/adventure/boss/finish', json={})
        assert second.status_code == 200

        row_after_second = patched_get_db.execute(
            'SELECT * FROM adventure_boss_progress WHERE user_id=? AND zone_key=?', (uid, ZONE_KEY)
        ).fetchone()
        assert row_after_second['cleared_at'] == cleared_at_first  # unchanged, not a new transition
        assert row_after_second['attempts'] == 2  # attempt accounting still advances normally


class TestFinishRouteNoRewardSideEffects:
    def test_no_reward_helper_is_invoked_on_a_passing_finish(self, client, app_module, patched_get_db, stub_adventure_state, monkeypatch):
        calls = []
        for name in ('_grant_coins', '_spend_coins'):
            if hasattr(app_module, name):
                monkeypatch.setattr(app_module, name, lambda *a, name=name, **k: calls.append(name))

        uid = 11
        qids = list(range(5001, 5021))
        for qid in qids:
            _seed_review(patched_get_db, uid=uid, question_id=qid, grade=5, reviewed_at=within_window())
        _login(client, uid)
        _set_exam(client, _exam(qids))

        resp = client.post('/api/adventure/boss/finish', json={})
        assert resp.status_code == 200
        assert resp.get_json()['passed'] is True
        assert calls == []

    def test_source_contains_no_reward_grant_reference(self):
        app_py = _read(REPO_ROOT / 'app.py')
        start = app_py.index("class _AdventureBossAttemptError")
        end = app_py.index("@app.route('/api/adventure/boss/finish'")
        finish_start = app_py.index("def adventure_boss_finish()")
        finish_end = app_py.index("\n@app.route(", finish_start + 1)
        section = app_py[start:end] + app_py[finish_start:finish_end]
        for forbidden in ('_grant_coins', '_spend_coins', 'currency_log', '_coin_balance'):
            assert forbidden not in section, f"{forbidden} must not appear in boss/finish scoring logic"
