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

from lord_trial_answer_service import encode_lord_trial_verdict
from migrations.companion_operations_v1 import upgrade as upgrade_companion_schema
from migrations.domain_event_outbox_v1 import upgrade as upgrade_domain_event_outbox

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
        reviewed_at TEXT NOT NULL,
        source_context TEXT NOT NULL DEFAULT 'practice'
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
    # Needed by the live F028 Mapping A reward service: a genuine first-clear
    # writes the existing wardrobe ownership authority in this same fixture.
    conn.execute('''CREATE TABLE player_wardrobe (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item_id TEXT NOT NULL,
        obtained_at TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'drop',
        UNIQUE(user_id, item_id)
    )''')
    conn.execute('''CREATE TABLE user_stats (
        user_id INTEGER PRIMARY KEY,
        coins INTEGER NOT NULL DEFAULT 0
    )''')
    conn.execute('''CREATE TABLE currency_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        delta INTEGER NOT NULL,
        balance_after INTEGER NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL
    )''')
    conn.execute('''CREATE TABLE user_pets (
        user_id INTEGER PRIMARY KEY,
        pet_key TEXT NOT NULL,
        nickname TEXT,
        level INTEGER NOT NULL DEFAULT 1,
        xp INTEGER NOT NULL DEFAULT 0,
        fullness INTEGER NOT NULL DEFAULT 60,
        affection INTEGER NOT NULL DEFAULT 10,
        selected_at TEXT NOT NULL,
        last_fed_at TEXT,
        last_interacted_at TEXT,
        updated_at TEXT
    )''')
    conn.execute('''CREATE TABLE pet_inventory (
        user_id INTEGER NOT NULL,
        item_key TEXT NOT NULL,
        qty INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, item_key)
    )''')
    conn.execute('''CREATE TABLE pet_action_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        detail TEXT,
        created_at TEXT NOT NULL
    )''')
    conn.execute('''CREATE TABLE pet_collection (
        user_id INTEGER NOT NULL,
        pet_key TEXT NOT NULL,
        nickname TEXT,
        level INTEGER NOT NULL DEFAULT 1,
        xp INTEGER NOT NULL DEFAULT 0,
        fullness INTEGER NOT NULL DEFAULT 60,
        affection INTEGER NOT NULL DEFAULT 10,
        selected_at TEXT NOT NULL,
        last_fed_at TEXT,
        last_interacted_at TEXT,
        last_pet_at TEXT,
        last_train_at TEXT,
        daily_key TEXT,
        daily_bond INTEGER NOT NULL DEFAULT 0,
        daily_train_xp INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, pet_key)
    )''')
    upgrade_companion_schema(conn)
    upgrade_domain_event_outbox(conn)
    conn.commit()
    yield conn
    conn.close()


TEST_BOSS_ATTEMPT_ID = 'unit-attempt'
TEST_BOSS_SOURCE_CONTEXT = f'boss_trial:{TEST_BOSS_ATTEMPT_ID}'


def _seed_review(conn, uid, question_id, grade, reviewed_at,
                 source_context=TEST_BOSS_SOURCE_CONTEXT,
                 server_verdict=None):
    if source_context.startswith('boss_trial:'):
        attempt_id = source_context[len('boss_trial:'):]
        server_verdict = server_verdict or (
            'AUTHORITATIVE_PASS' if grade >= 3 else 'AUTHORITATIVE_FAIL'
        )
        source_context = encode_lord_trial_verdict({
            'schema': 'lord_trial_verdict_v1',
            'attempt_id': attempt_id,
            'question_id': int(question_id),
            'verdict': server_verdict,
            'authoritative_grade': 5 if server_verdict == 'AUTHORITATIVE_PASS' else 0,
            'judge_version': 'lord-trial-map-battle-judge-v1',
            'reason_code': 'test_fixture',
        })
    conn.execute(
        'INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) VALUES (?,?,?,?,?)',
        (uid, question_id, grade, reviewed_at, source_context),
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


def _exam(question_ids, started_at=STARTED_AT, zone_key=ZONE_KEY,
          attempt_id=TEST_BOSS_ATTEMPT_ID):
    return {
        'zone_key': zone_key,
        'question_ids': question_ids,
        'started_at': started_at,
        'attempt_id': attempt_id,
    }


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
        # legacy retry fixture) must resolve deterministically regardless of
        # scheduling-grade order: one identical server verdict counts once.
        _seed_review(
            sqlite_conn, uid=1, question_id=601, grade=first_grade,
            reviewed_at=within_window(10), server_verdict='AUTHORITATIVE_PASS',
        )
        _seed_review(
            sqlite_conn, uid=1, question_id=601, grade=second_grade,
            reviewed_at=within_window(20), server_verdict='AUTHORITATIVE_PASS',
        )
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


class TestLordFixedSizeAndThreshold:
    """The Owner-locked contract: exactly 20 questions, PASS at >= 16 correct.

    The pass threshold is a constant, never scaled to the attempt's length,
    and an attempt that is not exactly 20 questions is not a Lord Challenge
    at all -- it is refused rather than settled against a lowered bar.
    """

    def _finish(self, client, patched_get_db, uid, *, total, correct):
        qids = list(range(7000 + uid * 100, 7000 + uid * 100 + total))
        for index, qid in enumerate(qids):
            _seed_review(
                patched_get_db, uid=uid, question_id=qid,
                grade=5 if index < correct else 0,
                reviewed_at=within_window(index + 1),
            )
        _login(client, uid)
        _set_exam(client, _exam(qids))
        return client.post('/api/adventure/boss/finish', json={})

    def test_fifteen_of_twenty_fails(
        self, client, app_module, patched_get_db, stub_adventure_state
    ):
        resp = self._finish(client, patched_get_db, 61, total=20, correct=15)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['correct'] == 15
        assert body['total'] == 20
        assert body['passed'] is False

    def test_sixteen_of_twenty_passes(
        self, client, app_module, patched_get_db, stub_adventure_state
    ):
        resp = self._finish(client, patched_get_db, 62, total=20, correct=16)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['correct'] == 16
        assert body['total'] == 20
        assert body['passed'] is True

    def test_zero_of_twenty_fails(
        self, client, app_module, patched_get_db, stub_adventure_state
    ):
        resp = self._finish(client, patched_get_db, 63, total=20, correct=0)
        assert resp.get_json()['passed'] is False

    def test_twenty_of_twenty_passes(
        self, client, app_module, patched_get_db, stub_adventure_state
    ):
        resp = self._finish(client, patched_get_db, 64, total=20, correct=20)
        assert resp.get_json()['passed'] is True

    @pytest.mark.parametrize(
        "total,correct", [(3, 3), (12, 12), (19, 15), (19, 19), (1, 1)]
    )
    def test_short_attempt_can_never_settle_as_pass(
        self, client, app_module, patched_get_db, stub_adventure_state,
        total, correct,
    ):
        """A full-marks short attempt is refused, not scaled down to clear.

        Before the fixed-size contract the threshold was
        ``min(BOSS_PASS_SCORE, total)``, so 3/3 cleared a Zone.
        """
        uid = 70 + total
        resp = self._finish(client, patched_get_db, uid, total=total, correct=correct)
        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'invalid_attempt_size'

        # Nothing was minted, and the invalid attempt is not left in session.
        row = patched_get_db.execute(
            'SELECT * FROM adventure_boss_progress WHERE user_id=? AND zone_key=?',
            (uid, ZONE_KEY),
        ).fetchone()
        assert row is None or (not row['cleared'] and row['stars'] == 0)
        with client.session_transaction() as sess:
            assert 'adventure_boss_exam' not in sess

    def test_short_attempt_is_abandoned_at_start_not_resumed(
        self, client, app_module, monkeypatch, stub_boss_start_state
    ):
        """A pre-existing short signed exam is never resumed toward a clear."""
        _login(client, 79)
        _set_exam(client, _exam(list(range(8001, 8004))))  # legacy 3-question exam
        response = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert response.status_code == 200
        body = response.get_json()
        assert body['resumed'] is False
        assert len(body['question_ids']) == 20
        assert body['total'] == 20
        assert body['pass_score'] == 16

    def test_start_reports_the_fixed_threshold(
        self, client, app_module, stub_boss_start_state
    ):
        _login(client, 80)
        body = client.post(
            '/api/adventure/boss/start', json={'zone_key': 'k26_30'}
        ).get_json()
        assert len(body['question_ids']) == 20
        assert body['total'] == 20
        assert body['pass_score'] == 16


class TestLordRetryRequiresThirtyMapQuestions:
    """Owner-locked: after a Lord FAIL the player must answer 30 more Map
    questions before retrying.  ``cooldown_left`` is derived server-side as
    ``cooldown_until_seen - seen``; the client never supplies it.
    """

    def _stub_state(self, app_module, monkeypatch, *, answered_since_fail):
        remaining = max(0, app_module.BOSS_FAIL_COOLDOWN - answered_since_fail)
        state = {
            'key': 'k26_30', 'seen': 50, 'total': 50, 'pct': 100,
            'unlocked': True, 'cleared': False,
            'cooldown_left': remaining,
        }
        monkeypatch.setattr(app_module, '_adventure_state', lambda uid: [dict(state)])
        monkeypatch.setattr(
            app_module, '_load_questions',
            lambda: [
                {
                    'id': 950000 + i, 'enabled': True,
                    'content': _JUDGEABLE_SGF,
                }
                for i in range(40)
            ],
        )
        monkeypatch.setattr(
            app_module, '_questions_for_adventure_zone',
            lambda qs, zone, premium: list(qs),
        )
        monkeypatch.setattr(app_module, 'is_premium', lambda *a, **k: True)
        return remaining

    @pytest.mark.parametrize("answered_since_fail", [0, 1, 29])
    def test_retry_before_thirty_map_questions_is_blocked(
        self, client, app_module, monkeypatch, answered_since_fail
    ):
        remaining = self._stub_state(
            app_module, monkeypatch, answered_since_fail=answered_since_fail
        )
        _login(client, 8100 + answered_since_fail)
        resp = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body['error'] == 'cooldown'
        assert body['cooldown_left'] == remaining
        with client.session_transaction() as sess:
            assert 'adventure_boss_exam' not in sess

    def test_retry_at_thirty_map_questions_is_allowed(
        self, client, app_module, monkeypatch
    ):
        self._stub_state(app_module, monkeypatch, answered_since_fail=30)
        _login(client, 8130)
        resp = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body['question_ids']) == 20
        assert body['pass_score'] == 16

    def test_client_cannot_forge_past_the_retry_gate(
        self, client, app_module, monkeypatch
    ):
        """Request-body cooldown/replay claims are never consulted."""
        self._stub_state(app_module, monkeypatch, answered_since_fail=0)
        _login(client, 8140)
        for forged in (
            {'zone_key': 'k26_30', 'cooldown_left': 0},
            {'zone_key': 'k26_30', 'replay': True},
            {'zone_key': 'k26_30', 'cooldown_left': 0, 'replay': True,
             'cleared': True},
        ):
            resp = client.post('/api/adventure/boss/start', json=forged)
            assert resp.status_code == 400
            assert resp.get_json()['error'] == 'cooldown'

    def test_invalid_short_attempt_does_not_charge_a_retry_cooldown(
        self, client, app_module, patched_get_db, stub_adventure_state
    ):
        """An attempt that was never a valid Lord Challenge is not punished."""
        uid = 8150
        qids = list(range(8600, 8603))
        for index, qid in enumerate(qids):
            _seed_review(
                patched_get_db, uid=uid, question_id=qid, grade=5,
                reviewed_at=within_window(index + 1),
            )
        _login(client, uid)
        _set_exam(client, _exam(qids))
        resp = client.post('/api/adventure/boss/finish', json={})
        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'invalid_attempt_size'

        row = patched_get_db.execute(
            'SELECT * FROM adventure_boss_progress WHERE user_id=? AND zone_key=?',
            (uid, ZONE_KEY),
        ).fetchone()
        # No attempt recorded, so no cooldown was charged and nothing cleared.
        assert row is None


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
    # F030 replaces the legacy coin-only first-clear reward with the
    # server-authored Mapping A wardrobe result. Currency must remain absent.
    def test_spend_coins_never_invoked_on_a_passing_finish(self, client, app_module, patched_get_db, stub_adventure_state, monkeypatch):
        calls = []
        if hasattr(app_module, '_spend_coins'):
            monkeypatch.setattr(app_module, '_spend_coins', lambda *a, **k: calls.append('_spend_coins'))

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

    def test_legacy_coin_grant_is_not_called_on_a_passing_finish(self, client, app_module, patched_get_db, stub_adventure_state, monkeypatch):
        calls = []
        monkeypatch.setattr(app_module, '_grant_coins', lambda *args, **kwargs: calls.append(args))

        uid = 12
        qids = list(range(5101, 5121))
        for qid in qids:
            _seed_review(patched_get_db, uid=uid, question_id=qid, grade=5, reviewed_at=within_window())
        _login(client, uid)
        _set_exam(client, _exam(qids))

        resp = client.post('/api/adventure/boss/finish', json={})
        assert resp.status_code == 200
        assert calls == []
        assert resp.get_json()['reward']['coins'] == 0

    def test_source_contains_no_direct_currency_writes_bypassing_grant_coins(self):
        # boss/finish may call the reused, audited _grant_coins() helper,
        # but must never write currency_log/_coin_balance/spend directly --
        # that would be a second, ungoverned reward path.
        app_py = _read(REPO_ROOT / 'app.py')
        start = app_py.index("class _AdventureBossAttemptError")
        end = app_py.index("@app.route('/api/adventure/boss/finish'")
        finish_start = app_py.index("def adventure_boss_finish()")
        finish_end = app_py.index("\n@app.route(", finish_start + 1)
        section = app_py[start:end] + app_py[finish_start:finish_end]
        for forbidden in ('_spend_coins', '_coin_balance', '_grant_coins(', 'INSERT INTO currency_log', 'UPDATE user_stats'):
            assert forbidden not in section, f"{forbidden} must not appear directly in boss/finish scoring logic"
        assert app_py.count('def _grant_coins(') == 1, "must reuse the single existing _grant_coins(), not fork it"


# ===========================================================================
# Tier 3 -- server-authoritative Lord replay mode
# ===========================================================================

@pytest.fixture()
def stub_cleared_adventure_state(app_module, monkeypatch):
    state = {'seen': 50}

    def fake_adventure_state(uid):
        return [{'key': 'k26_30', 'seen': state['seen'], 'unlocked': True, 'cleared': True}]

    def fake_map_state(uid, selected_stage_key=None, use_cache=False):
        return {}

    monkeypatch.setattr(app_module, '_adventure_state', fake_adventure_state)
    monkeypatch.setattr(app_module, '_adventure_map_state', fake_map_state)
    return state


@pytest.fixture()
def stub_boss_start_state(app_module, monkeypatch):
    state = {
        'key': 'k26_30',
        'seen': 50,
        # Lord eligibility is ceil(total * 0.30) over distinct correct answers,
        # so the stub carries the `total` the real state always emits: 50 of
        # 50 correct is the full coverage the `pct` below already claims.
        'total': 50,
        'pct': 100,
        'unlocked': True,
        'cleared': True,
        'cooldown_left': 0,
    }
    monkeypatch.setattr(app_module, '_adventure_state', lambda uid: [dict(state)])
    # These stubs exercise attempt identity, scope and resume, not judging.
    # They still carry judgeable SGF content because a Lord attempt may only
    # be created from questions the canonical judge can settle; a contentless
    # stub is exactly the unjudgeable shape that stranded Production attempts.
    monkeypatch.setattr(
        app_module,
        '_load_questions',
        lambda: [
            {
                'id': i,
                'enabled': True,
                'content': '(;GM[1]FF[4]CA[UTF-8]SZ[19]PL[B]AB[dp]AW[pd](;B[dd]C[stub]))',
            }
            for i in range(1, 21)
        ],
    )
    monkeypatch.setattr(app_module, '_questions_for_adventure_zone', lambda qs, zone, premium: list(qs))
    monkeypatch.setattr(app_module, 'is_premium', lambda *args, **kwargs: True)
    return state


# P0-1: the Lord start route itself refuses to sign an attempt it cannot judge.
_JUDGEABLE_SGF = '(;GM[1]FF[4]CA[UTF-8]SZ[19]PL[B]AB[dp]AW[pd](;B[dd]C[stub]))'
# The real 31194 defect shape: canonical MultiGo content with no PL[B/W] root
# property, so the server-only Lord judge cannot establish whose move it is.
_MISSING_PL_SGF = (
    '(;CA[gb2312]AB[eb][cf][dg][eg][ff][fe][ed]AW[de][ee][ef][df][fd][gd][fg][gg]'
    'LB[dd:A][ce:B]AP[MultiGo:4.3.0]SZ[8]AB[fc]MULTIGOGM[1];B[dd];W[ce];B[be])'
)


class TestLordQueueAdmission:
    """A created attempt must contain only questions the Lord judge can settle."""

    def _stub_pool(self, app_module, monkeypatch, questions):
        state = {
            'key': 'k26_30', 'seen': 50, 'total': 50, 'pct': 100,
            'unlocked': True, 'cleared': True, 'cooldown_left': 0,
        }
        monkeypatch.setattr(app_module, '_adventure_state', lambda uid: [dict(state)])
        monkeypatch.setattr(app_module, '_load_questions', lambda: questions)
        monkeypatch.setattr(
            app_module, '_questions_for_adventure_zone',
            lambda qs, zone, premium: list(qs),
        )
        monkeypatch.setattr(app_module, 'is_premium', lambda *a, **k: True)

    def test_unjudgeable_questions_are_never_signed_into_an_attempt(
        self, client, app_module, monkeypatch
    ):
        # 20 judgeable questions alongside 40 of the real 31194 defect shape.
        pool = [
            {'id': 31194 + i, 'enabled': True, 'content': _MISSING_PL_SGF}
            for i in range(40)
        ] + [
            {'id': 900000 + i, 'enabled': True, 'content': _JUDGEABLE_SGF}
            for i in range(20)
        ]
        self._stub_pool(app_module, monkeypatch, pool)
        _login(client, 4101)

        response = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert response.status_code == 200
        body = response.get_json()
        assert len(body['question_ids']) == 20
        # None of the 503-producing questions reached the signed queue, so the
        # attempt cannot strand the way the Production one did at 4/20.
        assert all(qid >= 900000 for qid in body['question_ids'])

    def test_pool_without_enough_judgeable_questions_fails_closed_at_start(
        self, client, app_module, monkeypatch
    ):
        # The real d7_plus shape: a large eligible pool that is almost entirely
        # unjudgeable.  Silently building a 1-question Lord Trial there would
        # hand out a Zone clear, so the attempt is refused instead.
        pool = [
            {'id': 31194 + i, 'enabled': True, 'content': _MISSING_PL_SGF}
            for i in range(60)
        ] + [{'id': 900001, 'enabled': True, 'content': _JUDGEABLE_SGF}]
        self._stub_pool(app_module, monkeypatch, pool)
        _login(client, 4102)

        response = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert response.status_code == 503
        assert response.get_json()['error'] == 'insufficient_judgeable_questions'

        with client.session_transaction() as sess:
            assert 'adventure_boss_exam' not in sess


class TestLordReplayMode:
    def test_new_attempts_receive_distinct_server_generated_ids(
        self, client, app_module, stub_boss_start_state, monkeypatch
    ):
        _login(client, 19)
        first = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert first.status_code == 200
        first_id = first.get_json()['attempt_id']
        assert app_module._adventure_boss_attempt_id_is_valid(first_id)

        # A mode transition abandons the old signed exam and creates a fresh
        # server-owned attempt, rather than reusing its identity.
        stub_boss_start_state.update({'cleared': False, 'pct': 100})
        second = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert second.status_code == 200
        second_id = second.get_json()['attempt_id']
        assert app_module._adventure_boss_attempt_id_is_valid(second_id)
        assert first_id != second_id

    def test_legacy_same_zone_exam_without_attempt_id_is_not_resumed(
        self, client, app_module, patched_get_db, stub_boss_start_state
    ):
        _login(client, 18)
        with client.session_transaction() as sess:
            sess['adventure_boss_exam'] = {
                'zone_key': 'k26_30',
                'question_ids': [1, 2],
                'started_at': STARTED_AT,
                'attempt_mode': 'replay',
            }
        response = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert response.status_code == 200
        body = response.get_json()
        assert body['resumed'] is False
        assert _session_exam(client)['attempt_id'] == body['attempt_id']

    def test_start_derives_replay_from_authoritative_clear_ignoring_client_flag(
        self, client, app_module, stub_boss_start_state
    ):
        _login(client, 20)
        response = client.post('/api/adventure/boss/start', json={
            'zone_key': 'k26_30',
            'replay': False,
        })
        assert response.status_code == 200
        body = response.get_json()
        assert body['replay'] is True
        assert body['attempt_mode'] == 'replay'
        with client.session_transaction() as sess:
            assert sess['adventure_boss_exam']['attempt_mode'] == 'replay'

    def test_uncleared_start_ignores_forged_replay_flag(self, client, app_module, stub_boss_start_state):
        stub_boss_start_state.update({'cleared': False, 'pct': 30})
        _login(client, 21)
        response = client.post('/api/adventure/boss/start', json={
            'zone_key': 'k26_30',
            'replay': True,
        })
        assert response.status_code == 200
        body = response.get_json()
        assert body['replay'] is False
        assert body['attempt_mode'] == 'first_clear'

    def test_explicit_replay_attempt_for_uncleared_zone_fails_closed(
        self, client, app_module, patched_get_db, stub_adventure_state
    ):
        uid = 22
        qids = list(range(6101, 6121))
        for qid in qids:
            _seed_review(patched_get_db, uid, qid, 5, within_window())
        _login(client, uid)
        _set_exam(client, {**_exam(qids, zone_key='k26_30'), 'attempt_mode': 'replay'})
        response = client.post('/api/adventure/boss/finish', json={})
        assert response.status_code == 400
        assert response.get_json()['error'] == 'invalid_replay_attempt'

    def _seed_cleared_row(self, conn, uid, zone_key='k26_30'):
        conn.execute('''
            INSERT INTO adventure_boss_progress
                (user_id, zone_key, cleared, stars, attempts, best_score,
                 cooldown_until_seen, last_attempt_at, cleared_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        ''', (uid, zone_key, 1, 2, 3, 18, 0,
              '2026-08-14T10:00:00', '2026-08-14T09:00:00', '2026-08-14T10:00:00'))
        conn.commit()

    def test_replay_pass_preserves_clear_and_has_zero_rewards(
        self, client, app_module, patched_get_db, stub_cleared_adventure_state, monkeypatch
    ):
        uid = 23
        self._seed_cleared_row(patched_get_db, uid)
        qids = list(range(6201, 6221))
        for qid in qids:
            _seed_review(patched_get_db, uid, qid, 5, within_window())
        grants = []
        monkeypatch.setattr(app_module, '_grant_coins', lambda *args, **kwargs: grants.append(args) or 999)
        _login(client, uid)
        _set_exam(client, {**_exam(qids, zone_key='k26_30'), 'attempt_mode': 'replay'})

        response = client.post('/api/adventure/boss/finish', json={'correct': 0, 'total': 0})
        assert response.status_code == 200
        body = response.get_json()
        assert body['passed'] is True
        assert body['replay'] is True
        assert body['attempt_mode'] == 'replay'
        assert body['reward']['coins'] == 0
        assert body['reward']['first_clear'] is False
        assert body['reward']['status'] == 'NO_REWARD'
        assert body['cooldown_left'] == 0
        assert grants == []
        row = patched_get_db.execute(
            'SELECT * FROM adventure_boss_progress WHERE user_id=? AND zone_key=?', (uid, 'k26_30')
        ).fetchone()
        assert row['cleared'] == 1
        assert row['stars'] == 2
        assert row['best_score'] == 18
        assert row['cleared_at'] == '2026-08-14T09:00:00'
        assert row['attempts'] == 4


# ===========================================================================
# Tier 4 -- signed-session Boss resume authority
# ===========================================================================

def _exam_review_time(exam, offset_seconds=5):
    started_at = _dt.datetime.fromisoformat(exam['started_at'])
    return (started_at + _dt.timedelta(seconds=offset_seconds)).isoformat()


def _session_exam(client):
    with client.session_transaction() as sess:
        return dict(sess['adventure_boss_exam'])


def _seed_exam_review(conn, app_module, uid, exam, question_id, grade, reviewed_at):
    _seed_review(
        conn, uid, question_id, grade, reviewed_at,
        source_context=app_module._adventure_boss_source_context(exam['attempt_id']),
    )


class TestBossResumeAuthority:
    def test_practice_row_inside_attempt_window_is_ignored(
        self, client, app_module, patched_get_db, stub_boss_start_state
    ):
        uid = 40
        _login(client, uid)
        first = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        exam = _session_exam(client)
        _seed_exam_review(
            patched_get_db, app_module, uid, exam, exam['question_ids'][0], 5,
            _exam_review_time(exam),
        )
        _seed_review(
            patched_get_db, uid, exam['question_ids'][1], 5,
            _exam_review_time(exam, 6), source_context='practice',
        )

        resumed = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert resumed.status_code == 200
        body = resumed.get_json()
        assert body['resume_index'] == 1
        assert body['answered_count'] == 1
        assert body['correct'] == 1

    def test_review_from_another_attempt_cannot_contaminate_current_resume(
        self, client, app_module, patched_get_db, stub_boss_start_state
    ):
        uid = 41
        _login(client, uid)
        first = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        exam_a = _session_exam(client)
        exam_b = {**exam_a, 'attempt_id': 'previous-attempt'}
        _seed_exam_review(
            patched_get_db, app_module, uid, exam_a, exam_a['question_ids'][0], 5,
            _exam_review_time(exam_a),
        )
        _set_exam(client, exam_b)

        resumed = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert resumed.status_code == 200
        body = resumed.get_json()
        assert body['resume_index'] == 0
        assert body['correct'] == 0
        assert body['attempt_id'] == 'previous-attempt'

    def test_resumed_response_preserves_exact_attempt_id(
        self, client, app_module, patched_get_db, stub_boss_start_state
    ):
        _login(client, 42)
        first = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        exam = _session_exam(client)
        attempt_id = first.get_json()['attempt_id']
        _seed_exam_review(
            patched_get_db, app_module, 42, exam, exam['question_ids'][0], 5,
            _exam_review_time(exam),
        )
        resumed = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert resumed.status_code == 200
        assert resumed.get_json()['attempt_id'] == attempt_id

    def test_q1_resume_reuses_queue_started_at_and_rejects_client_cursor(
        self, client, app_module, patched_get_db, stub_boss_start_state
    ):
        uid = 30
        _login(client, uid)
        first = client.post('/api/adventure/boss/start', json={
            'zone_key': 'k26_30',
            'resume_index': 19,
            'correct': 20,
            'answered_count': 20,
            'replay': False,
        })
        assert first.status_code == 200
        initial = first.get_json()
        exam_before = _session_exam(client)
        _seed_exam_review(
            patched_get_db, app_module, uid, exam_before,
            exam_before['question_ids'][0], 5, _exam_review_time(exam_before),
        )

        resumed = client.post('/api/adventure/boss/start', json={
            'zone_key': 'k26_30',
            'resume_index': 19,
            'correct': 20,
            'answered_count': 20,
            'replay': False,
        })
        assert resumed.status_code == 200
        body = resumed.get_json()
        exam_after = _session_exam(client)
        assert body['resumed'] is True
        assert body['question_ids'] == initial['question_ids']
        assert body['resume_index'] == 1
        assert body['answered_count'] == 1
        assert body['correct'] == 1
        assert body['attempt_mode'] == 'replay'
        assert body['ready_to_finish'] is False
        assert exam_after['question_ids'] == exam_before['question_ids']
        assert exam_after['started_at'] == exam_before['started_at']

    def test_multi_question_resume_uses_best_grade_prefix(self, client, app_module, patched_get_db, stub_boss_start_state):
        uid = 31
        _login(client, uid)
        first = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert first.status_code == 200
        exam = _session_exam(client)
        grades = [5, 0, 5, 5, 0]
        for qid, grade in zip(exam['question_ids'][:5], grades):
            _seed_exam_review(
                patched_get_db, app_module, uid, exam, qid, grade,
                _exam_review_time(exam, qid % 7 + 5),
            )

        resumed = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert resumed.status_code == 200
        body = resumed.get_json()
        assert body['resumed'] is True
        assert body['answered_count'] == 5
        assert body['resume_index'] == 5
        assert body['correct'] == 3
        assert body['question_ids'] == exam['question_ids']

    def test_duplicate_rows_count_once(self, client, app_module, patched_get_db, stub_boss_start_state):
        uid = 32
        _login(client, uid)
        first = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        exam = _session_exam(client)
        qid = exam['question_ids'][0]
        for offset, grade in ((5, 0), (6, 5), (7, 5)):
            _seed_exam_review(
                patched_get_db, app_module, uid, exam, qid, grade,
                _exam_review_time(exam, offset),
            )
            # The scheduling grade is intentionally varied to model retries;
            # the server-owned verdict is immutable and therefore identical.
            if offset == 5:
                patched_get_db.execute(
                    'UPDATE review_log SET source_context=? WHERE user_id=? AND question_id=? AND reviewed_at=?',
                    (
                        encode_lord_trial_verdict({
                            'schema': 'lord_trial_verdict_v1',
                            'attempt_id': exam['attempt_id'],
                            'question_id': qid,
                            'verdict': 'AUTHORITATIVE_PASS',
                            'authoritative_grade': 5,
                            'judge_version': 'lord-trial-map-battle-judge-v1',
                            'reason_code': 'test_fixture',
                        }),
                        uid, qid, _exam_review_time(exam, offset),
                    ),
                )
                patched_get_db.commit()

        resumed = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert resumed.status_code == 200
        body = resumed.get_json()
        assert body['answered_count'] == 1
        assert body['correct'] == 1

    def test_nonsequential_evidence_fails_closed_and_preserves_exam(
        self, client, app_module, patched_get_db, stub_boss_start_state
    ):
        uid = 33
        _login(client, uid)
        first = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        exam = _session_exam(client)
        _seed_exam_review(
            patched_get_db, app_module, uid, exam, exam['question_ids'][1], 5,
            _exam_review_time(exam),
        )
        response = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert response.status_code == 400
        assert response.get_json()['error'] == 'nonsequential_attempt_evidence'
        assert _session_exam(client) == exam

    @pytest.mark.parametrize('malformed_exam', [
        {'zone_key': 'k26_30', 'question_ids': 'bad', 'started_at': STARTED_AT, 'attempt_mode': 'replay'},
        {'zone_key': 'k26_30', 'question_ids': [1, 2], 'started_at': 'not-a-date', 'attempt_mode': 'replay'},
    ])
    def test_malformed_exam_is_not_resumed_and_fresh_exam_is_created(
        self, client, app_module, patched_get_db, stub_boss_start_state, malformed_exam
    ):
        _login(client, 34)
        with client.session_transaction() as sess:
            sess['adventure_boss_exam'] = malformed_exam
        response = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert response.status_code == 200
        body = response.get_json()
        assert body['resumed'] is False
        assert body['resume_index'] == 0
        assert _session_exam(client)['question_ids'] == body['question_ids']

    def test_expired_exam_is_not_resumed_and_fresh_exam_is_created(
        self, client, app_module, patched_get_db, stub_boss_start_state
    ):
        _login(client, 35)
        old_started_at = (_dt.datetime.now() - _dt.timedelta(minutes=app_module.BOSS_ATTEMPT_MAX_MINUTES + 1)).isoformat()
        with client.session_transaction() as sess:
            sess['adventure_boss_exam'] = {
                'zone_key': 'k26_30', 'question_ids': [999],
                'started_at': old_started_at, 'attempt_mode': 'replay',
            }
        response = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert response.status_code == 200
        body = response.get_json()
        assert body['resumed'] is False
        assert _session_exam(client)['started_at'] != old_started_at

    def test_different_zone_exam_is_abandoned_not_reused(self, client, app_module, stub_boss_start_state, monkeypatch):
        states = [
            {**stub_boss_start_state, 'key': 'k26_30', 'cleared': True},
            {**stub_boss_start_state, 'key': 'k21_25', 'cleared': True},
        ]
        monkeypatch.setattr(app_module, '_adventure_state', lambda _uid: [dict(s) for s in states])
        _login(client, 36)
        first = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert first.status_code == 200
        old_exam = _session_exam(client)
        second = client.post('/api/adventure/boss/start', json={'zone_key': 'k21_25'})
        assert second.status_code == 200
        body = second.get_json()
        new_exam = _session_exam(client)
        assert body['resumed'] is False
        assert new_exam['zone_key'] == 'k21_25'
        assert new_exam['zone_key'] != old_exam['zone_key']

    def test_attempt_mode_cannot_change_across_authoritative_clear_state(
        self, client, app_module, stub_boss_start_state, monkeypatch
    ):
        _login(client, 37)
        first = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert first.status_code == 200
        assert _session_exam(client)['attempt_mode'] == 'replay'

        stub_boss_start_state.update({'cleared': False, 'pct': 100})
        second = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert second.status_code == 200
        body = second.get_json()
        assert body['resumed'] is False
        assert body['attempt_mode'] == 'first_clear'
        assert body['replay'] is False

    def test_first_clear_resume_remains_first_clear(self, client, app_module, patched_get_db, stub_boss_start_state):
        stub_boss_start_state.update({'cleared': False, 'pct': 100})
        _login(client, 38)
        first = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert first.status_code == 200
        exam = _session_exam(client)
        _seed_exam_review(
            patched_get_db, app_module, 38, exam, exam['question_ids'][0], 0,
            _exam_review_time(exam),
        )
        resumed = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30', 'replay': True})
        assert resumed.status_code == 200
        body = resumed.get_json()
        assert body['attempt_mode'] == 'first_clear'
        assert body['replay'] is False
        assert body['resume_index'] == 1
        assert body['correct'] == 0

    def test_lost_finish_response_reuses_complete_exam_and_finish_is_single_use(
        self, client, app_module, patched_get_db, stub_boss_start_state, monkeypatch
    ):
        stub_boss_start_state.update({'cleared': False, 'pct': 100})
        monkeypatch.setattr(app_module, '_grant_coins', lambda *args, **kwargs: 0)
        uid = 39
        _login(client, uid)
        first = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert first.status_code == 200
        exam = _session_exam(client)
        for qid in exam['question_ids']:
            _seed_exam_review(
                patched_get_db, app_module, uid, exam, qid, 5,
                _exam_review_time(exam, qid % 11 + 5),
            )

        resume = client.post('/api/adventure/boss/start', json={'zone_key': 'k26_30'})
        assert resume.status_code == 200
        body = resume.get_json()
        assert body['resumed'] is True
        assert body['ready_to_finish'] is True
        assert body['resume_index'] == len(exam['question_ids'])
        assert body['correct'] == len(exam['question_ids'])
        assert _session_exam(client)['question_ids'] == exam['question_ids']

        finish = client.post('/api/adventure/boss/finish', json={'correct': 0, 'total': 0})
        assert finish.status_code == 200
        assert finish.get_json()['passed'] is True
        second_finish = client.post('/api/adventure/boss/finish', json={})
        assert second_finish.status_code == 400
        assert second_finish.get_json()['error'] == 'no_active_exam'

class TestLordReplayModeContinuation:
    @staticmethod
    def _seed_cleared_row(conn, uid, zone_key='k26_30'):
        conn.execute('''
            INSERT INTO adventure_boss_progress
                (user_id, zone_key, cleared, stars, attempts, best_score,
                 cooldown_until_seen, last_attempt_at, cleared_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        ''', (uid, zone_key, 1, 2, 3, 18, 0,
              '2026-08-14T10:00:00', '2026-08-14T09:00:00', '2026-08-14T10:00:00'))
        conn.commit()

    def test_replay_fail_preserves_clear_and_does_not_create_cooldown(
        self, client, app_module, patched_get_db, stub_cleared_adventure_state
    ):
        uid = 24
        self._seed_cleared_row(patched_get_db, uid)
        qids = list(range(6301, 6321))
        for qid in qids:
            _seed_review(patched_get_db, uid, qid, 0, within_window())
        _login(client, uid)
        _set_exam(client, {**_exam(qids, zone_key='k26_30'), 'attempt_mode': 'replay'})

        response = client.post('/api/adventure/boss/finish', json={})
        assert response.status_code == 200
        body = response.get_json()
        assert body['passed'] is False
        assert body['replay'] is True
        assert body['reward']['coins'] == 0
        assert body['reward']['first_clear'] is False
        assert body['reward']['status'] == 'NO_REWARD'
        assert body['cooldown_left'] == 0
        row = patched_get_db.execute(
            'SELECT * FROM adventure_boss_progress WHERE user_id=? AND zone_key=?', (uid, 'k26_30')
        ).fetchone()
        assert row['cleared'] == 1
        assert row['stars'] == 2
        assert row['best_score'] == 18
        assert row['cooldown_until_seen'] == 0
        assert row['attempts'] == 4

    def test_zone2_replay_pass_uses_same_authoritative_zero_reward_contract(
        self, client, app_module, patched_get_db, stub_cleared_adventure_state, monkeypatch
    ):
        uid = 25
        monkeypatch.setattr(app_module, '_adventure_state', lambda _uid: [{
            'key': 'k21_25', 'seen': 50, 'unlocked': True, 'cleared': True,
        }])
        self._seed_cleared_row(patched_get_db, uid, zone_key='k21_25')
        qids = list(range(6401, 6421))
        for qid in qids:
            _seed_review(patched_get_db, uid, qid, 5, within_window())
        grants = []
        monkeypatch.setattr(app_module, '_grant_coins', lambda *args, **kwargs: grants.append(args) or 999)
        _login(client, uid)
        _set_exam(client, {**_exam(qids, zone_key='k21_25'), 'attempt_mode': 'replay'})

        response = client.post('/api/adventure/boss/finish', json={})
        assert response.status_code == 200
        body = response.get_json()
        assert body['passed'] is True
        assert body['replay'] is True
        assert body['attempt_mode'] == 'replay'
        assert body['reward']['coins'] == 0
        assert body['reward']['first_clear'] is False
        assert body['reward']['status'] == 'NO_REWARD'
        assert grants == []
        row = patched_get_db.execute(
            'SELECT * FROM adventure_boss_progress WHERE user_id=? AND zone_key=?', (uid, 'k21_25')
        ).fetchone()
        assert row['cleared'] == 1
        assert row['stars'] == 2
        assert row['best_score'] == 18
