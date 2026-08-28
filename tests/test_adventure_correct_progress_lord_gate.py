"""Focused coverage for the shared E10 correct-progress Lord gate.

The gate is derived from the existing server grading record, not browser
state: a distinct question contributes once after a passing grade (3 or 5),
remains credited if a later review is wrong, and never contributes merely
because an SRS card was displayed or attempted.
"""

import sqlite3
import sys
import types

import pytest

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
        module.grimoire_bp = Blueprint('grimoire_stub_correct_progress', __name__)
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


class _DbContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()


@pytest.fixture()
def sqlite_conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE srs_cards (
        user_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        last_grade INTEGER,
        progress_credited INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, question_id)
    )''')
    conn.execute('''CREATE TABLE review_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        grade INTEGER NOT NULL,
        source_context TEXT NOT NULL DEFAULT 'practice'
    )''')
    conn.execute('''CREATE TABLE adventure_boss_progress (
        user_id INTEGER NOT NULL,
        zone_key TEXT NOT NULL,
        cleared INTEGER NOT NULL DEFAULT 0,
        stars INTEGER NOT NULL DEFAULT 0,
        attempts INTEGER NOT NULL DEFAULT 0,
        best_score INTEGER NOT NULL DEFAULT 0,
        cooldown_until_seen INTEGER NOT NULL DEFAULT 0,
        last_attempt_at TEXT,
        cleared_at TEXT,
        updated_at TEXT,
        PRIMARY KEY (user_id, zone_key)
    )''')
    conn.execute('''CREATE TABLE adventure_zone_unlocks (
        user_id INTEGER NOT NULL,
        zone_key TEXT NOT NULL,
        start_zone_key TEXT,
        source TEXT,
        PRIMARY KEY (user_id, zone_key)
    )''')
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture()
def adventure_state_harness(app_module, sqlite_conn, monkeypatch):
    questions = [
        {
            'id': qid,
            'enabled': True,
            'topic': '1圍棋新手村',
        }
        for qid in range(1, 11)
    ]
    monkeypatch.setattr(app_module, 'get_db', lambda: _DbContext(sqlite_conn))
    monkeypatch.setattr(app_module, '_load_questions', lambda: questions)
    monkeypatch.setattr(app_module, 'is_premium', lambda uid=None: True)
    monkeypatch.setattr(
        app_module,
        '_resolve_adventure_effective_start_zone',
        lambda conn, uid, unlock_rows=None: 'k26_30',
    )
    return app_module, sqlite_conn


def _card(conn, qid, last_grade=0, progress_credited=0, uid=7):
    conn.execute(
        'INSERT INTO srs_cards(user_id,question_id,last_grade,progress_credited) '
        'VALUES (?,?,?,?)',
        (uid, qid, last_grade, progress_credited),
    )


def _review(conn, qid, grade, uid=7):
    conn.execute(
        'INSERT INTO review_log(user_id,question_id,grade,source_context) VALUES (?,?,?,?)',
        (uid, qid, grade, 'mbv1:test'),
    )


def _zone1(app_module, uid=7):
    zones = app_module._adventure_state(uid)
    return next(zone for zone in zones if zone['key'] == 'k26_30')


def test_wrong_or_seen_only_question_does_not_advance_lord_progress(adventure_state_harness):
    app_module, conn = adventure_state_harness
    _card(conn, 1, last_grade=0)
    _card(conn, 2, last_grade=0)
    _review(conn, 1, grade=0)
    conn.commit()

    zone = _zone1(app_module)

    assert zone['attempted'] == 2
    assert zone['correct_count'] == 0
    assert zone['seen'] == 0
    assert zone['pct'] == 0
    assert zone['boss_ready'] is False


def test_passing_grade_advances_once_and_later_wrong_keeps_historical_credit(adventure_state_harness):
    app_module, conn = adventure_state_harness
    # q1 passed, then later failed; q2 has duplicate passing reviews; q3 only
    # has the old sticky bit and therefore cannot supply correctness authority
    # without a trusted server-owned review row.
    _card(conn, 1, last_grade=0, progress_credited=0)
    _card(conn, 2, last_grade=5, progress_credited=1)
    _card(conn, 3, last_grade=0, progress_credited=1)
    _review(conn, 1, grade=3)
    _review(conn, 1, grade=0)
    _review(conn, 2, grade=5)
    _review(conn, 2, grade=5)
    conn.commit()

    zone = _zone1(app_module)

    assert zone['correct_count'] == 2
    assert zone['seen'] == 2
    assert zone['pct'] == 20
    assert zone['boss_ready'] is False


def test_threshold_is_locked_below_thirty_and_ready_at_thirty(adventure_state_harness):
    app_module, conn = adventure_state_harness
    _card(conn, 1, last_grade=3, progress_credited=1)
    _card(conn, 2, last_grade=3, progress_credited=1)
    _review(conn, 1, grade=3)
    _review(conn, 2, grade=3)
    conn.commit()

    below = _zone1(app_module)
    assert below['correct_count'] == 2
    assert below['pct'] == 20
    assert below['boss_ready'] is False

    _card(conn, 3, last_grade=3, progress_credited=1)
    _review(conn, 3, grade=3)
    conn.commit()

    ready = _zone1(app_module)
    assert ready['correct_count'] == 3
    assert ready['pct'] == 30
    assert ready['boss_ready'] is True


def test_rounded_twenty_nine_percent_equivalent_stays_locked(adventure_state_harness, monkeypatch):
    app_module, conn = adventure_state_harness
    monkeypatch.setattr(
        app_module,
        '_load_questions',
        lambda: [
            {'id': qid, 'enabled': True, 'topic': '1圍棋新手村'}
            for qid in range(1, 8)
        ],
    )
    for qid in (1, 2):
        _card(conn, qid, last_grade=3, progress_credited=1)
        _review(conn, qid, grade=3)
    conn.commit()

    zone = _zone1(app_module)

    assert zone['pct'] == 29  # round(2 / 7 * 100)
    assert zone['boss_ready'] is False  # ceil(7 * 0.30) == 3


def test_boss_readiness_is_state_only_and_does_not_settle_or_start_trial(adventure_state_harness):
    app_module, conn = adventure_state_harness
    for qid in (1, 2, 3):
        _card(conn, qid, last_grade=3, progress_credited=1)
        _review(conn, qid, grade=3)
    conn.commit()

    zone = _zone1(app_module)

    assert zone['boss_ready'] is True
    assert conn.execute(
        'SELECT COUNT(*) FROM adventure_boss_progress WHERE user_id=?', (7,)
    ).fetchone()[0] == 0


def test_correct_predicate_rejects_wrong_grade_and_deduplicates_question_ids(app_module, sqlite_conn):
    _review(sqlite_conn, 10, grade=0)
    _review(sqlite_conn, 11, grade=3)
    _review(sqlite_conn, 11, grade=5)
    cards = [
        {'question_id': 12, 'last_grade': 3, 'progress_credited': 1},
        {'question_id': 13, 'last_grade': 0, 'progress_credited': 0},
    ]

    assert app_module._adventure_correct_question_ids(sqlite_conn, 7, cards) == {11}
