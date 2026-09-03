"""INCIDENT_018: Lord attempt scope is settled before quota and before the judge.

Reproduction carried forward from
INCIDENT_018_CLAUDE_DIRECT_ROOT_CAUSE_HUNT_001, plus the contracts the fix
must hold.

The proven defect
-----------------
A Lord Trial is BOSS_EXAM_SIZE (20) questions and every Lord answer writes a
``review_log`` row that ``get_today_free_count`` counts, so a free player's
trial consumes their whole FREE_DAILY_LIMIT (20) allowance.  While the attempt
is in scope the answer is exempt from that cap.  Once the attempt left scope,
the answer fell through to the generic ``daily_limit`` rejection, which the
client rendered as 「答題記錄寫入失敗，這題尚未儲存。」 -- a quota refusal
reported as a database write failure, after the judge had already run and its
result had been discarded.

The contract asserted here
--------------------------
``BOSS_ATTEMPT_MAX_MINUTES`` is an evidence/replay window (see its declaring
comment: "Boss attempt evidence window ... Bounds 'stale answer' replay"), not
a quota and not a hard entitlement clock that may be silently renewed.  So:

  * in scope  -> never rejected by the ordinary daily cap (A/B/C)
  * expired   -> reported as ``boss_attempt_expired``, never ``daily_limit``
                 and never a bare write-failure string (D/E)
  * ordinary free practice at the cap is untouched (F), premium untouched (G)
  * invalid question/context still fails closed (H)
  * idempotency and judge semantics unchanged (I/J)
"""
import datetime
import re
import sqlite3
import sys
import types
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
        module.grimoire_bp = Blueprint('grimoire_stub_incident018_scope', __name__)
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
ATTEMPT_ID = 'incident018scope01'
EXAM_QIDS = list(range(1001, 1021))          # BOSS_EXAM_SIZE == 20
OUTSIDE_QID = 5555                           # a real question, not in the exam


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
    # An answer that is *allowed* through the cap keeps going into the real
    # persistence path, so the tables that path reads have to exist for the
    # "not rejected" assertions to be about the gate rather than about a
    # missing fixture table.
    conn.execute('''CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        elo_rating INTEGER NOT NULL DEFAULT 1200,
        plan TEXT NOT NULL DEFAULT 'free',
        premium_until TEXT
    )''')
    conn.execute('''CREATE TABLE user_stats (
        user_id INTEGER PRIMARY KEY,
        coins INTEGER NOT NULL DEFAULT 0
    )''')
    conn.execute('INSERT INTO users(id) VALUES (?)', (UID,))
    conn.execute('INSERT INTO user_stats(user_id) VALUES (?)', (UID,))
    conn.commit()
    return conn


def _seed_today(conn, *, lord_rows, practice_rows, started_at):
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
def judge_calls():
    return []


@pytest.fixture()
def patched(app_module, sqlite_conn, monkeypatch, judge_calls):
    monkeypatch.setattr(app_module, 'get_db', lambda: _FakeDbConnCtx(sqlite_conn))
    monkeypatch.setattr(app_module, 'is_premium', lambda *a, **k: False)
    monkeypatch.setattr(
        app_module, '_load_questions',
        lambda: [{'id': q, 'enabled': True, 'is_free': True}
                 for q in EXAM_QIDS + [OUTSIDE_QID]],
    )
    monkeypatch.setattr(app_module, 'question_is_free', lambda q: True)

    # The judge is upstream of the gate under test and is not what changed.
    # Recording each call lets test J assert it is never run for an answer
    # that cannot be admitted.
    def _fake_judge(boss_answer, *, question, exam):
        judge_calls.append(question.get('id') if isinstance(question, dict) else None)
        judged = types.SimpleNamespace(
            result='AUTHORITATIVE_PASS',
            verdict='AUTHORITATIVE_PASS',
            authoritative_grade=5,
            reason_code='incident018_scope',
            judge_version='lord-trial-map-battle-judge-v1',
        )
        return types.SimpleNamespace(payload={'moves': ['dd']}), judged

    def _fake_verdict(*, attempt_id, question_id, judge):
        return {
            'schema': 'lord_trial_verdict_v1',
            'attempt_id': attempt_id,
            'question_id': int(question_id),
            'verdict': 'AUTHORITATIVE_PASS',
            'authoritative_grade': 5,
            'judge_version': 'lord-trial-map-battle-judge-v1',
            'reason_code': 'incident018_scope',
        }

    monkeypatch.setattr(app_module, 'judge_lord_trial_answer', _fake_judge)
    monkeypatch.setattr(app_module, 'build_lord_trial_verdict', _fake_verdict)
    return sqlite_conn


def _submit(client, conn, *, qid, age_minutes, lord_rows, practice_rows,
            source_context=None, boss_answer=('moves', ['dd'])):
    started_at = datetime.datetime.now() - datetime.timedelta(minutes=age_minutes)
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
    body = {
        'question_id': qid,
        'grade': 5,
        'source_context': (source_context if source_context is not None
                           else f'boss_trial:{ATTEMPT_ID}'),
        'response_ms': 1000,
    }
    if boss_answer is not None:
        body['boss_answer'] = {boss_answer[0]: boss_answer[1]}
    return client.post('/api/srs/review', json=body)


# ---------------------------------------------------------------------------
# The 60-minute value is a replay window, and it has exactly one definition
# ---------------------------------------------------------------------------

def test_attempt_window_has_a_single_shared_definition(app_module):
    source = (REPO_ROOT / 'app.py').read_text(encoding='utf-8')
    # The window arithmetic appears in the shared helper and in the
    # boss/finish evidence query -- nowhere else -- so the review scope check
    # and the evidence query can never drift apart.
    assert source.count(
        'datetime.timedelta(minutes=BOSS_ATTEMPT_MAX_MINUTES)') == 2
    assert 'def _adventure_boss_attempt_within_window' in source


@pytest.mark.parametrize('age_minutes,expected', [
    (5, True), (59, True), (61, False), (240, False),
])
def test_window_predicate(app_module, age_minutes, expected):
    started_at = datetime.datetime.now() - datetime.timedelta(minutes=age_minutes)
    exam = {
        'question_ids': list(EXAM_QIDS),
        'started_at': started_at.isoformat(timespec='seconds'),
        'attempt_id': ATTEMPT_ID,
    }
    assert app_module._adventure_boss_attempt_within_window(exam) is expected
    with app_module.app.test_request_context('/'):
        from flask import session
        session['adventure_boss_exam'] = exam
        assert app_module._adventure_boss_question_is_active(
            EXAM_QIDS[0]) is expected


# ---------------------------------------------------------------------------
# A / B / C -- an in-scope Lord answer at the cap is never a quota failure
# ---------------------------------------------------------------------------

class _PastTheCap(Exception):
    """Raised at the first statement after the daily-cap gate.

    Reaching it means the gate let the answer through.  Asserting here keeps
    these tests about the gate decision instead of requiring the entire
    downstream review-persistence schema.
    """


@pytest.fixture()
def cap_boundary(app_module, monkeypatch):
    def _boom():
        raise _PastTheCap()
    # First call after the premium/daily-limit block in _srs_review_operation.
    monkeypatch.setattr(
        app_module, '_load_premium_weekly_rating_helpers', _boom)


@pytest.mark.parametrize('label,lord_rows,practice_rows', [
    ('A-at-cap', 0, 20),      # today_count == 20 before the answer
    ('B-candidate-A', 4, 16),  # 4 answered / 4 correct
    ('C-candidate-B', 11, 9),  # 11 answered / 9 correct
])
def test_in_scope_lord_answer_is_not_rejected_by_daily_limit(
        client, patched, cap_boundary, sqlite_conn, app_module,
        label, lord_rows, practice_rows):
    with pytest.raises(_PastTheCap):
        _submit(client, sqlite_conn, qid=EXAM_QIDS[lord_rows],
                age_minutes=5, lord_rows=lord_rows,
                practice_rows=practice_rows)
    # ...and the player really was at the cap when that happened.
    assert app_module.get_today_free_count(UID) >= app_module.FREE_DAILY_LIMIT


# ---------------------------------------------------------------------------
# D / E -- an expired attempt reports itself, not quota, not a write failure
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('label,lord_rows,practice_rows', [
    ('candidate-A', 4, 16),
    ('candidate-B', 11, 9),
])
def test_expired_attempt_is_not_reported_as_daily_limit(
        client, patched, sqlite_conn, label, lord_rows, practice_rows):
    response = _submit(client, sqlite_conn, qid=EXAM_QIDS[lord_rows],
                       age_minutes=61, lord_rows=lord_rows,
                       practice_rows=practice_rows)
    payload = response.get_json() or {}
    assert payload.get('error') == 'boss_attempt_expired', (label, payload)
    assert payload.get('error') != 'daily_limit'
    assert response.status_code == 409, (label, payload)


def test_expired_attempt_is_not_rendered_as_a_write_failure():
    """The client must name the state, not report a failed write."""
    transport = (REPO_ROOT / 'js/game/review_transport.js').read_text(encoding='utf-8')
    # Handed back as a payload, so submitSRS's data-driven branch sees it
    # instead of the generic catch that prints the save-failure string.
    # The allowlist was widened from three inline `error.code ===` comparisons
    # to a named SERVER_OWNED_REJECTIONS set when the Guild codes were mapped;
    # assert the membership invariant rather than the old literal shape.
    rejections = re.search(
        r'const SERVER_OWNED_REJECTIONS = new Set\(\[(.*?)\]\);', transport, re.S
    )
    assert rejections, 'the transport must declare an explicit rejection set'
    assert "'boss_attempt_expired'" in rejections.group(1)

    index = (REPO_ROOT / 'index.html').read_text(encoding='utf-8')
    start = index.index("function submitSRS")
    submit = index[start:index.index("function loadQuestion", start)]
    branch_at = submit.index("data.error==='boss_attempt_expired'")
    branch = submit[branch_at:submit.index("}else if(data.error==='daily_limit')", branch_at)]
    assert "index.srs.boss_attempt_expired" in branch
    assert "index.srs.save_fail" not in branch

    i18n = (REPO_ROOT / 'i18n.js').read_text(encoding='utf-8')
    assert "'index.srs.boss_attempt_expired'" in i18n
    assert '領主試煉已逾時' in i18n


# ---------------------------------------------------------------------------
# F / G -- ordinary practice and premium semantics are untouched
# ---------------------------------------------------------------------------

def test_ordinary_free_practice_at_cap_is_still_rejected_by_daily_limit(
        client, patched, sqlite_conn):
    response = _submit(client, sqlite_conn, qid=OUTSIDE_QID, age_minutes=5,
                       lord_rows=0, practice_rows=20,
                       source_context='practice', boss_answer=None)
    payload = response.get_json() or {}
    assert response.status_code == 429, payload
    assert payload['error'] == 'daily_limit'
    assert payload['limit'] == 20


def test_premium_player_is_never_capped(client, patched, cap_boundary,
                                        sqlite_conn, app_module, monkeypatch):
    monkeypatch.setattr(app_module, 'is_premium', lambda *a, **k: True)
    with pytest.raises(_PastTheCap):
        _submit(client, sqlite_conn, qid=OUTSIDE_QID, age_minutes=5,
                lord_rows=0, practice_rows=40,
                source_context='practice', boss_answer=None)


# ---------------------------------------------------------------------------
# H -- invalid question / context still fails closed
# ---------------------------------------------------------------------------

def test_question_outside_the_exam_fails_closed(client, patched, sqlite_conn):
    response = _submit(client, sqlite_conn, qid=OUTSIDE_QID, age_minutes=5,
                       lord_rows=4, practice_rows=16)
    payload = response.get_json() or {}
    assert response.status_code == 400, payload
    assert payload['error'] == 'invalid_boss_attempt_question'


def test_attempt_id_mismatch_fails_closed(client, patched, sqlite_conn):
    response = _submit(client, sqlite_conn, qid=EXAM_QIDS[0], age_minutes=5,
                       lord_rows=0, practice_rows=0,
                       source_context='boss_trial:someotherattempt01')
    payload = response.get_json() or {}
    assert response.status_code == 400, payload
    assert payload['error'] == 'invalid_boss_attempt_context'


def test_boss_answer_still_required_for_an_in_scope_attempt(
        client, patched, sqlite_conn):
    response = _submit(client, sqlite_conn, qid=EXAM_QIDS[0], age_minutes=5,
                       lord_rows=0, practice_rows=0, boss_answer=None)
    payload = response.get_json() or {}
    assert response.status_code == 400, payload
    assert payload['error'] == 'boss_answer_required'


# ---------------------------------------------------------------------------
# I / J -- identity and judge semantics unchanged
# ---------------------------------------------------------------------------

def test_submission_identity_is_still_server_owned_per_attempt_question(
        app_module):
    from lord_trial_answer_service import lord_trial_submission_id
    first = lord_trial_submission_id(ATTEMPT_ID, EXAM_QIDS[0])
    again = lord_trial_submission_id(ATTEMPT_ID, EXAM_QIDS[0])
    other = lord_trial_submission_id(ATTEMPT_ID, EXAM_QIDS[1])
    assert first == again          # retries of one answer share one identity
    assert first != other          # a different question never collides


def test_judge_never_runs_for_an_answer_that_cannot_be_admitted(
        client, patched, sqlite_conn, judge_calls):
    """No discarded judge work: scope is settled before the judge."""
    expired = _submit(client, sqlite_conn, qid=EXAM_QIDS[4], age_minutes=61,
                      lord_rows=4, practice_rows=16)
    assert expired.get_json()['error'] == 'boss_attempt_expired'
    assert judge_calls == []

    outside = _submit(client, sqlite_conn, qid=OUTSIDE_QID, age_minutes=5,
                      lord_rows=4, practice_rows=16)
    assert outside.get_json()['error'] == 'invalid_boss_attempt_question'
    assert judge_calls == []

    # ...but a properly scoped answer still reaches the judge unchanged.
    _submit(client, sqlite_conn, qid=EXAM_QIDS[4], age_minutes=5,
            lord_rows=4, practice_rows=16)
    assert judge_calls == [EXAM_QIDS[4]]


# ---------------------------------------------------------------------------
# Incident 018 observability must not regress
# ---------------------------------------------------------------------------

def test_incident_018_observability_is_preserved():
    source = (REPO_ROOT / 'app.py').read_text(encoding='utf-8')
    for marker in (
        'incident018_begin_request', 'incident018_end_request',
        'incident018_log_stage', 'incident018_log_exception',
        'incident018_update_current', 'incident018_observe_lord_endpoint',
        'diagnostic_ref',
    ):
        assert marker in source, marker
    # the new refusal is observable through the same channel
    assert "'BOSS_ATTEMPT_SCOPE'" in source
