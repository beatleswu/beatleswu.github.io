"""Regression tests for the live Battlefield Boss first-clear reward route.

F030 replaces the historical coin-only first-clear projection with the
server-authored F028 Mapping A wardrobe result. The existing finish route,
authoritative score handoff, and caller-owned transaction remain the scope
under test; currency must stay at zero and no legacy coin writer may run.
"""
import sys
import sqlite3
import types
from pathlib import Path

import pytest

from lord_trial_answer_service import encode_lord_trial_verdict
from migrations.companion_operations_v1 import upgrade as upgrade_companion_schema
from migrations.domain_event_outbox_v1 import upgrade as upgrade_domain_event_outbox

REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(path):
    return (REPO_ROOT / path).read_text(encoding="utf-8")


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
        module.grimoire_bp = Blueprint('grimoire_stub_first_clear_reward', __name__)
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
                 source_context=TEST_BOSS_SOURCE_CONTEXT, server_verdict=None):
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
    a persistent shared sqlite3 connection: commits on clean exit, rolls
    back on exception -- this is exactly the atomicity property PR2's
    "same transaction" requirement depends on."""
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
        return False


@pytest.fixture()
def patched_get_db(app_module, sqlite_conn, monkeypatch):
    monkeypatch.setattr(app_module, 'get_db', lambda: _FakeDbConnCtx(sqlite_conn))
    return sqlite_conn


@pytest.fixture()
def stub_adventure_state(app_module, monkeypatch):
    state = {'seen': 50}

    def fake_adventure_state(uid):
        return [{'key': 'k1_5', 'seen': state['seen'], 'unlocked': True, 'cleared': False}]

    def fake_map_state(uid, selected_stage_key=None, use_cache=False):
        return {}

    monkeypatch.setattr(app_module, '_adventure_state', fake_adventure_state)
    monkeypatch.setattr(app_module, '_adventure_map_state', fake_map_state)
    return state


ZONE_KEY = 'k1_5'

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
    return (STARTED_AT_DT + _dt.timedelta(seconds=offset_seconds)).isoformat()


def _login(client, uid):
    with client.session_transaction() as sess:
        sess['user_id'] = uid


def _set_exam(client, exam):
    with client.session_transaction() as sess:
        sess['adventure_boss_exam'] = exam


def _seed_full_pass_evidence(conn, uid, qids):
    for qid in qids:
        _seed_review(conn, uid, qid, 5, within_window())


def _seed_full_fail_evidence(conn, uid, qids, correct_count=0):
    for i, qid in enumerate(qids):
        grade = 5 if i < correct_count else 0
        _seed_review(conn, uid, qid, grade, within_window())


def _coins_and_log(conn, uid):
    row = conn.execute('SELECT coins FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    coins = row['coins'] if row else 0
    log_rows = conn.execute(
        'SELECT delta, reason FROM currency_log WHERE user_id=? ORDER BY id', (uid,)
    ).fetchall()
    return coins, [dict(r) for r in log_rows]


class TestFirstClearGrantsReward:
    def test_first_clear_grants_mapping_a_wardrobe_item_without_coins(self, client, app_module, patched_get_db, stub_adventure_state):
        uid = 101
        qids = list(range(11001, 11021))
        _seed_full_pass_evidence(patched_get_db, uid, qids)
        _login(client, uid)
        _set_exam(client, _exam(qids))

        resp = client.post('/api/adventure/boss/finish', json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['passed'] is True
        assert body['reward']['coins'] == 0
        assert body['reward']['first_clear'] is True
        assert body['reward']['status'] == 'GRANTED'
        assert body['reward']['item_id'] == 'robe_dragon'

        coins, log = _coins_and_log(patched_get_db, uid)
        assert coins == 0
        assert log == []
        assert patched_get_db.execute(
            'SELECT COUNT(*) FROM player_wardrobe WHERE user_id=? AND item_id=?',
            (uid, 'robe_dragon'),
        ).fetchone()[0] == 1

    def test_pass_after_failed_attempt_claims_atomic_first_clear_once(
        self, client, app_module, patched_get_db, stub_adventure_state
    ):
        uid = 109
        patched_get_db.execute(
            '''INSERT INTO adventure_boss_progress
               (user_id, zone_key, cleared, stars, attempts, best_score,
                cooldown_until_seen, last_attempt_at, cleared_at, updated_at)
               VALUES (?, ?, 0, 0, 1, 8, 0, ?, NULL, ?)''',
            (uid, ZONE_KEY, within_window(), within_window()),
        )
        patched_get_db.commit()
        qids = list(range(19001, 19021))
        _seed_full_pass_evidence(patched_get_db, uid, qids)
        _login(client, uid)
        _set_exam(client, _exam(qids))

        response = client.post('/api/adventure/boss/finish', json={})

        assert response.status_code == 200
        assert response.get_json()['reward']['status'] == 'GRANTED'
        row = patched_get_db.execute(
            'SELECT cleared, attempts FROM adventure_boss_progress WHERE user_id=? AND zone_key=?',
            (uid, ZONE_KEY),
        ).fetchone()
        assert row['cleared'] == 1
        assert row['attempts'] == 2
        coins, log = _coins_and_log(patched_get_db, uid)
        assert coins == 0
        assert log == []


class TestAlreadyClearedGrantsNothing:
    def test_already_cleared_zone_grants_no_second_reward(self, client, app_module, patched_get_db, stub_adventure_state):
        uid = 102
        qids_first = list(range(12001, 12021))
        _seed_full_pass_evidence(patched_get_db, uid, qids_first)
        _login(client, uid)
        _set_exam(client, _exam(qids_first))
        first = client.post('/api/adventure/boss/finish', json={})
        assert first.get_json()['reward']['status'] == 'GRANTED'

        # A second, later, independent clear attempt (fresh boss/start ->
        # fresh question set) of the SAME already-cleared zone must not pay out again.
        qids_second = list(range(12101, 12121))
        _seed_full_pass_evidence(patched_get_db, uid, qids_second)
        _set_exam(client, _exam(qids_second))
        second = client.post('/api/adventure/boss/finish', json={})
        assert second.status_code == 200
        body = second.get_json()
        assert body['passed'] is True
        assert body['reward']['coins'] == 0
        assert body['reward']['first_clear'] is False
        assert body['reward']['status'] == 'NO_REWARD'

        coins, log = _coins_and_log(patched_get_db, uid)
        assert coins == 0
        assert log == []


class TestReplayGrantsNothing:
    def test_replay_without_fresh_start_grants_no_reward(self, client, app_module, patched_get_db, stub_adventure_state):
        uid = 103
        qids = list(range(13001, 13021))
        _seed_full_pass_evidence(patched_get_db, uid, qids)
        _login(client, uid)
        _set_exam(client, _exam(qids))

        first = client.post('/api/adventure/boss/finish', json={})
        assert first.get_json()['reward']['status'] == 'GRANTED'

        # Session's exam slot was popped on completion -- an immediate
        # second call (no fresh boss/start) must be rejected outright, not
        # re-evaluated, and must not grant anything.
        second = client.post('/api/adventure/boss/finish', json={})
        assert second.status_code == 400
        assert second.get_json()['error'] == 'no_active_exam'

        coins, log = _coins_and_log(patched_get_db, uid)
        assert coins == 0
        assert log == []


class TestForgedScoreGrantsNothing:
    def test_forged_perfect_score_with_failing_evidence_grants_no_reward(self, client, app_module, patched_get_db, stub_adventure_state):
        uid = 104
        qids = list(range(14001, 14021))
        _seed_full_fail_evidence(patched_get_db, uid, qids, correct_count=0)
        _login(client, uid)
        _set_exam(client, _exam(qids))

        # Client claims a perfect score; server derives 0/20 from evidence.
        resp = client.post('/api/adventure/boss/finish', json={'correct': 20, 'total': 20})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['passed'] is False
        assert body['correct'] == 0
        assert body['reward']['coins'] == 0
        assert body['reward']['first_clear'] is False
        assert body['reward']['status'] == 'NO_REWARD'

        coins, log = _coins_and_log(patched_get_db, uid)
        assert coins == 0
        assert log == []


class TestDailyCapDoesNotBlockFirstClear:
    def test_daily_coin_cap_is_irrelevant_to_mapping_a_first_clear(self, client, app_module, patched_get_db, stub_adventure_state):
        uid = 105
        # Simulate the user already having earned the full daily cap today
        # via ordinary (non-adventure) income.
        patched_get_db.execute(
            'INSERT INTO currency_log(user_id,delta,balance_after,reason,created_at) VALUES (?,?,?,?,?)',
            (uid, app_module._COIN_DAILY_CAP, app_module._COIN_DAILY_CAP, 'monster_kill',
             __import__('datetime').date.today().isoformat() + 'T00:00:00'),
        )
        patched_get_db.execute(
            'INSERT INTO user_stats(user_id, coins) VALUES (?, ?)',
            (uid, app_module._COIN_DAILY_CAP),
        )
        patched_get_db.commit()
        assert app_module._coins_earned_today(patched_get_db, uid) >= app_module._COIN_DAILY_CAP

        qids = list(range(15001, 15021))
        _seed_full_pass_evidence(patched_get_db, uid, qids)
        _login(client, uid)
        _set_exam(client, _exam(qids))

        resp = client.post('/api/adventure/boss/finish', json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['reward']['coins'] == 0
        assert body['reward']['first_clear'] is True
        assert body['reward']['status'] == 'GRANTED'

        coins, _ = _coins_and_log(patched_get_db, uid)
        assert coins == app_module._COIN_DAILY_CAP


class TestCurrencyLogRecordsReward:
    def test_mapping_a_reward_does_not_write_currency_log(self, client, app_module, patched_get_db, stub_adventure_state):
        uid = 106
        qids = list(range(16001, 16021))
        _seed_full_pass_evidence(patched_get_db, uid, qids)
        _login(client, uid)
        _set_exam(client, _exam(qids))

        client.post('/api/adventure/boss/finish', json={})
        assert patched_get_db.execute(
            'SELECT COUNT(*) FROM currency_log WHERE user_id=?', (uid,)
        ).fetchone()[0] == 0


class TestRewardAndClearAreSameTransaction:
    def test_reward_grant_failure_rolls_back_the_clear_transition_too(self, client, app_module, patched_get_db, stub_adventure_state, monkeypatch):
        uid = 107
        qids = list(range(17001, 17021))
        _seed_full_pass_evidence(patched_get_db, uid, qids)
        _login(client, uid)
        _set_exam(client, _exam(qids))

        def boom(*args, **kwargs):
            raise RuntimeError("simulated wardrobe-grant failure")

        monkeypatch.setattr(app_module, 'grant_battlefield_boss_first_clear_reward', boom)

        with pytest.raises(RuntimeError):
            client.post('/api/adventure/boss/finish', json={})

        # Nothing must be half-committed: no adventure_boss_progress row,
        # no wardrobe row and no currency_log entry.
        progress_row = patched_get_db.execute(
            'SELECT * FROM adventure_boss_progress WHERE user_id=? AND zone_key=?', (uid, ZONE_KEY)
        ).fetchone()
        assert progress_row is None
        coins, log = _coins_and_log(patched_get_db, uid)
        assert coins == 0
        assert log == []


class TestLegacyFlowUnaffected:
    def test_legacy_and_e9_share_one_finish_contract_still(self):
        for f in (REPO_ROOT / 'js' / 'e9').rglob('*.js'):
            text = _read(f)
            assert 'boss/finish' not in text and 'boss/start' not in text, f

    def test_legacy_failing_flow_unaffected_by_reward_change(self, client, app_module, patched_get_db, stub_adventure_state):
        uid = 108
        qids = list(range(18001, 18021))
        _seed_full_fail_evidence(patched_get_db, uid, qids, correct_count=10)
        _login(client, uid)
        _set_exam(client, _exam(qids))

        resp = client.post('/api/adventure/boss/finish', json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['passed'] is False
        assert body['correct'] == 10
        assert body['cooldown_left'] == app_module.BOSS_FAIL_COOLDOWN
        assert body['reward']['coins'] == 0
        assert body['reward']['first_clear'] is False
        assert body['reward']['status'] == 'NO_REWARD'


class TestNoSecondRewardSystemIntroduced:
    def test_no_new_reward_route_and_no_second_grant_helper(self):
        app_py = _read(REPO_ROOT / 'app.py')
        for forbidden_route in ("'/api/adventure/reward'", "'/reward'", "'/grant'"):
            assert forbidden_route not in app_py
        # Exactly one legacy currency helper remains; F030 must not call or
        # fork it for the Mapping A reward.
        assert app_py.count('def _grant_coins(') == 1
