"""INCIDENT_018 root-cause reproduction.

Reproduces the user-visible Lord Challenge failure

    答題記錄寫入失敗，這題尚未儲存。請稍後重試或重新整理頁面。
    (i18n key ``index.srs.save_fail``)

as a *deterministic* server outcome, using fixtures that match the two
reported field candidates:

    Candidate A -- 4 persisted / 4 correct, failure on the next answer
    Candidate B -- 11 persisted / 9 correct, failure on the next answer

Mechanism under test
--------------------
A Lord Trial is BOSS_EXAM_SIZE (20) questions.  Every Lord review writes a
``review_log`` row, and ``get_today_free_count`` counts Lord rows (it only
excludes the D5B daily-challenge prefix).  So a free player's Lord Trial
consumes their entire FREE_DAILY_LIMIT (20) allowance.  The only thing that
keeps the trial submittable past the wall is the boss exemption in
``/api/srs/review``::

    active_boss_question = (not internal and _adventure_boss_question_is_active(qid))
    if today_count >= _eff_limit and not active_boss_question:
        return jsonify({'error': 'daily_limit', ...}), 429

``_adventure_boss_question_is_active`` returns False once
``now > started_at + BOSS_ATTEMPT_MAX_MINUTES`` (60 min).  ``started_at`` is
set once at ``/api/adventure/boss/start`` and is deliberately *not* refreshed
when the trial is resumed, so a long or resumed trial silently loses its
exemption mid-run.  From that moment every remaining answer is rejected 429
``daily_limit`` -- which the client renders as the bare ``save_fail`` string.

These tests assert BOTH directions, so the expiry is isolated as the single
deciding variable:

  * healthy attempt (within the window)  -> NOT rejected with daily_limit
  * expired attempt (past the window)    -> 429 daily_limit  (the incident)
"""
import datetime
import sqlite3
import sys
import types

import pytest


# ---------------------------------------------------------------------------
# App import stubs (same set as tests/test_adventure_boss_finish_server_authoritative.py)
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
        module.grimoire_bp = Blueprint('grimoire_stub_incident018', __name__)
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


UID = 4242
ATTEMPT_ID = 'incident018repro01'
EXAM_QIDS = list(range(1001, 1021))          # BOSS_EXAM_SIZE == 20


class _FakeDbConnCtx:
    def __init__(self, conn):
        self._conn = conn

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
def sqlite_conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE review_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        grade INTEGER NOT NULL,
        reviewed_at TEXT NOT NULL,
        source_context TEXT NOT NULL DEFAULT 'practice',
        submission_id TEXT,
        submission_payload_hash TEXT
    )''')
    conn.execute('''CREATE TABLE active_effects (
        user_id INTEGER NOT NULL,
        effect_key TEXT NOT NULL,
        effect_date TEXT NOT NULL,
        value INTEGER NOT NULL DEFAULT 0
    )''')
    conn.commit()
    return conn


def _seed_today(conn, *, lord_rows, practice_rows, started_at):
    """Seed the day's review_log exactly like a real mid-trial state."""
    for i in range(practice_rows):
        conn.execute(
            'INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) '
            'VALUES (?,?,?,?,?)',
            (UID, 900000 + i, 4,
             (started_at - datetime.timedelta(minutes=5)).isoformat(), 'practice'),
        )
    for i in range(lord_rows):
        conn.execute(
            'INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) '
            'VALUES (?,?,?,?,?)',
            (UID, EXAM_QIDS[i], 5,
             (started_at + datetime.timedelta(minutes=i)).isoformat(),
             f'boss_trial:{ATTEMPT_ID}'),
        )
    conn.commit()


@pytest.fixture()
def patched(app_module, sqlite_conn, monkeypatch):
    """Patch only the subsystems this reproduction does not exercise."""
    monkeypatch.setattr(app_module, 'get_db', lambda: _FakeDbConnCtx(sqlite_conn))
    # Free (non-premium) player -- the daily wall only exists for free users.
    monkeypatch.setattr(app_module, 'is_premium', lambda *a, **k: False)
    # Every exam question is a free question, so the premium_required branch
    # above the daily-limit branch can never fire and mask the result.
    monkeypatch.setattr(
        app_module, '_load_questions',
        lambda: [{'id': q, 'enabled': True, 'is_free': True} for q in EXAM_QIDS],
    )
    monkeypatch.setattr(app_module, 'question_is_free', lambda q: True)

    # The Lord judge runs BEFORE the daily-limit gate (app.py:14853 vs 14979)
    # and is upstream of what is under test here.  Stub it to a deterministic
    # success so the reproduction isolates the gate: this is precisely the
    # "judge succeeds but persistence is skipped" shape.
    def _fake_judge(boss_answer, *, question, exam):
        judged = types.SimpleNamespace(
            result='AUTHORITATIVE_PASS',
            verdict='AUTHORITATIVE_PASS',
            authoritative_grade=5,
            reason_code='incident018_repro',
            judge_version='lord-trial-map-battle-judge-v1',
        )
        canonical = types.SimpleNamespace(payload={'moves': ['dd']})
        return canonical, judged

    def _fake_verdict(*, attempt_id, question_id, judge):
        return {
            'schema': 'lord_trial_verdict_v1',
            'attempt_id': attempt_id,
            'question_id': int(question_id),
            'verdict': 'AUTHORITATIVE_PASS',
            'authoritative_grade': 5,
            'judge_version': 'lord-trial-map-battle-judge-v1',
            'reason_code': 'incident018_repro',
        }

    monkeypatch.setattr(app_module, 'judge_lord_trial_answer', _fake_judge)
    monkeypatch.setattr(app_module, 'build_lord_trial_verdict', _fake_verdict)
    return sqlite_conn


def _post_review(client, qid, *, started_at_offset_minutes, lord_rows,
                 practice_rows, conn):
    """Submit the next Lord answer with an exam that started N minutes ago."""
    started_at = (datetime.datetime.now()
                  - datetime.timedelta(minutes=started_at_offset_minutes))
    _seed_today(conn, lord_rows=lord_rows, practice_rows=practice_rows,
                started_at=started_at)
    with client.session_transaction() as sess:
        sess['user_id'] = UID
        sess['adventure_boss_exam'] = {
            'zone_key': 'k26_30',
            'question_ids': list(EXAM_QIDS),
            'started_at': started_at.isoformat(timespec='seconds'),
            'attempt_id': ATTEMPT_ID,
            'attempt_mode': 'first_clear',
        }
    return client.post('/api/srs/review', json={
        'question_id': qid,
        'grade': 5,
        'source_context': f'boss_trial:{ATTEMPT_ID}',
        'response_ms': 1000,
        'boss_answer': {'moves': ['dd']},
    })


# ---------------------------------------------------------------------------
# Tier 1 -- the exemption predicate itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('offset_minutes,expected_active', [
    (5, True),      # healthy, well inside the 60-minute window
    (59, True),     # last minute inside the window
    (61, False),    # one minute past -- exemption silently lost
    (240, False),   # a resumed trial hours after its original start
])
def test_boss_exemption_expires_on_original_started_at(
        app_module, offset_minutes, expected_active):
    started_at = (datetime.datetime.now()
                  - datetime.timedelta(minutes=offset_minutes))
    with app_module.app.test_request_context('/'):
        from flask import session
        session['adventure_boss_exam'] = {
            'zone_key': 'k26_30',
            'question_ids': list(EXAM_QIDS),
            'started_at': started_at.isoformat(timespec='seconds'),
            'attempt_id': ATTEMPT_ID,
            'attempt_mode': 'first_clear',
        }
        assert app_module._adventure_boss_question_is_active(
            EXAM_QIDS[0]) is expected_active


def test_lord_reviews_are_counted_against_the_free_daily_limit(
        app_module, patched, sqlite_conn):
    """A Lord Trial burns the player's whole free allowance."""
    started_at = datetime.datetime.now() - datetime.timedelta(minutes=10)
    _seed_today(sqlite_conn, lord_rows=11, practice_rows=9, started_at=started_at)
    assert app_module.get_today_free_count(UID) == 20
    assert app_module.FREE_DAILY_LIMIT == 20
    assert app_module.BOSS_EXAM_SIZE == 20


# ---------------------------------------------------------------------------
# Tier 2 -- the exact incident, end to end through the real route
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('candidate,lord_rows,practice_rows', [
    ('A', 4, 16),    # 4 persisted / 4 correct  -> next answer is #5
    ('B', 11, 9),    # 11 persisted / 9 correct -> next answer is #12
])
def test_expired_attempt_reproduces_daily_limit_rejection(
        client, patched, sqlite_conn, candidate, lord_rows, practice_rows):
    """THE INCIDENT: past the 60-minute window the answer is refused 429."""
    response = _post_review(
        client, EXAM_QIDS[lord_rows],
        started_at_offset_minutes=61,
        lord_rows=lord_rows, practice_rows=practice_rows, conn=sqlite_conn,
    )
    payload = response.get_json()
    assert response.status_code == 429, (candidate, payload)
    assert payload['error'] == 'daily_limit', (candidate, payload)
    assert payload['today_count'] == 20
    assert payload['limit'] == 20
    # The client turns exactly this payload into the bare save_fail string:
    #   review_transport.legacyReview() returns (does not throw) for
    #   error === 'daily_limit'; submitSRS() then takes the _bossMode branch
    #   and calls setMsg(I18n.t('index.srs.save_fail')).
    assert payload.get('ok') is not True


@pytest.mark.parametrize('candidate,lord_rows,practice_rows', [
    ('A', 4, 16),
    ('B', 11, 9),
])
def test_healthy_attempt_is_not_rejected_with_daily_limit(
        client, patched, sqlite_conn, candidate, lord_rows, practice_rows):
    """Control: identical state, only the attempt age differs."""
    response = _post_review(
        client, EXAM_QIDS[lord_rows],
        started_at_offset_minutes=5,
        lord_rows=lord_rows, practice_rows=practice_rows, conn=sqlite_conn,
    )
    payload = response.get_json() or {}
    assert not (
        response.status_code == 429 and payload.get('error') == 'daily_limit'
    ), (candidate, response.status_code, payload)
