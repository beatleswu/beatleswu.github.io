"""G079 B1: the REAL app.py Mistakes services on a disposable PostgreSQL 16.

Runs only with G079_MISTAKES_PG=1 (otherwise skipped, never a fake PASS). Uses
ONLY the disposable container g076-r5-isolated-pg-20261023 (label
go-odyssey.g076.r5=isolated-disposable), creates a uniquely named database
g079_a_<hex> inside it and drops it at teardown. The DSN is read from the
operator JSON and never printed. Real app import, real init_db, real writers,
real Flask routes; identities come from the supported test-only registry
bootstrap (no Product minting).
"""
from __future__ import annotations

import datetime
import json
import os
import secrets
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = 'g076-r5-isolated-pg-20261023'
LABEL = ('go-odyssey.g076.r5', 'isolated-disposable')
DSN_FILE = Path(r'D:\go-odyssey-g076-b1b2r5-integration-20261023\.g076-r5-disposable-pg.json')
QUESTIONS = ROOT / 'tests' / 'fixtures' / 'g079_mistakes_questions.json'
FLAG = 'G076_MISTAKES_STEPS_ENABLED'
EVIDENCE = Path(os.environ.get('G079_EVIDENCE_DIR', r'D:\g079-artifacts\a'))
TWO_STEP = 7901
WRONG = (1, 3)

pytestmark = pytest.mark.skipif(os.environ.get('G079_MISTAKES_PG') != '1',
                                reason='G079_MISTAKES_PG=1 required (disposable PostgreSQL evidence)')


def _admin_dsn():
    return json.loads(DSN_FILE.read_text(encoding='utf-8-sig'))['dsn']


class PG:
    def __init__(self):
        import psycopg2
        from psycopg2.extensions import make_dsn
        info = subprocess.run(['docker', 'inspect', CONTAINER, '--format',
                               '{{json .Config.Labels}}|{{.State.Status}}'],
                              capture_output=True, text=True, timeout=60)
        assert info.returncode == 0, 'BLOCKED_ENVIRONMENT: disposable container missing'
        labels, status = info.stdout.strip().split('|')
        assert json.loads(labels).get(LABEL[0]) == LABEL[1] and status == 'running'
        self.name = 'g079_a_' + secrets.token_hex(6)
        admin = psycopg2.connect(_admin_dsn())
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute('CREATE DATABASE ' + self.name)
        admin.close()
        self.dsn = make_dsn(_admin_dsn(), dbname=self.name)
        self.users = 9000
        self.receipt = {'database': self.name, 'container': CONTAINER, 'label_verified': True}

    def drop(self):
        import psycopg2
        db = sys.modules.get('db')
        if db is not None and getattr(db, '_pool', None) is not None:
            db._pool.closeall()
            db._pool = None
        admin = psycopg2.connect(_admin_dsn())
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute('DROP DATABASE IF EXISTS ' + self.name + ' WITH (FORCE)')
            cur.execute('SELECT 1 FROM pg_database WHERE datname=%s', (self.name,))
            self.receipt['dropped'] = cur.fetchone() is None
        admin.close()


def _bootstrap_identity(app_module, qids):
    import uuid
    from migrations.puzzle_identity_registry_v1 import upgrade as identity_upgrade
    from puzzle_identity_store import PuzzleIdentityStore
    stamp, receipt = '2026-10-23T00:00:00+00:00', 'cd' * 32
    with app_module.get_db() as conn:
        identity_upgrade(conn)
        conn.execute(
            "INSERT INTO puzzle_identity_bootstrap_receipt "
            "(receipt_sha256,bootstrap_singleton,frozen_corpus_sha256,record_count,"
            " namespace_uuid,canonicalisation_rules_version,genesis_key_spec_version,"
            " historical_tree_commit,historical_tree_manifest_sha256,"
            " historical_rename_map_sha256,genesis_record_manifest_sha256,"
            " proposed_uuid_list_sha256,status,identities_written,applied_at,applied_by) "
            "VALUES (?, 'GENESIS', ?, ?, 'ns','canon-source-v1','genesis-key-v1',"
            "'c','tm','rm','gm','ul','APPLIED',0,?,'g079-a-fixture')",
            (receipt, 'x' * 64, len(qids), stamp))
        store = PuzzleIdentityStore(conn, clock=lambda: stamp)
        for qid in qids:
            store.create_historical_genesis_identity(
                str(uuid.uuid5(uuid.UUID('00000000-0000-4000-8000-000000000079'), f'g079:{qid}')),
                receipt_sha256=receipt, canonical_source=f'g079/{qid}.sgf',
                legacy_question_id=str(qid), creation_reason='genesis')
        conn.commit()


@pytest.fixture(scope='module')
def rt():
    pg = PG()
    saved = {k: os.environ.get(k) for k in ('DATABASE_URL', 'QUESTIONS_JSON_PATH', 'SECRET_KEY')}
    try:
        os.environ.update(DATABASE_URL=pg.dsn, QUESTIONS_JSON_PATH=str(QUESTIONS),
                          SECRET_KEY='g079-a-disposable-fixture-secret')
        import db
        db.DATABASE_URL = pg.dsn
        if getattr(db, '_pool', None) is not None:
            db._pool.closeall()
        db._pool = None
        from migrations.sgf_admin_workbench_v1 import upgrade as workbench_upgrade
        with db.get_db() as conn:
            workbench_upgrade(conn)
            conn.commit()
        import app
        app.app.config.update(TESTING=True)
        app.init_db()
        from migrations.g079_mistakes_steps_v1 import upgrade as mistakes_upgrade
        with db.get_db() as conn:
            mistakes_upgrade(conn, environ={'G079_MISTAKES_STEPS_MIGRATION_APPROVED': '1'})
            conn.commit()
        qids = [q['id'] for q in json.loads(QUESTIONS.read_text(encoding='utf-8'))]
        _bootstrap_identity(app, qids)
        pg.app = app
        yield pg
    finally:
        pg.drop()
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / f'pg_receipt_{pg.name}.json').write_text(
            json.dumps(pg.receipt, indent=1, sort_keys=True), encoding='utf-8')


@pytest.fixture
def on(monkeypatch):
    for key in ('G076_ANSWER_PRIVACY_ENFORCED', 'QUEST_V2_RUNTIME_ENABLED'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(FLAG, 'on')


# ─────────────────────────────── helpers ───────────────────────────────

def user(rt, *, plan='free', mistakes=(TWO_STEP,), stats=None):
    rt.users += 1
    uid = rt.users
    with rt.app.get_db() as conn:
        conn.execute('INSERT INTO users(id,username,password_hash,plan,created_at) VALUES(?,?,?,?,?)',
                     (uid, f'g079-{uid}', 'synthetic-not-login-capable', plan,
                      datetime.datetime.now().isoformat()))
        conn.execute('INSERT INTO user_stats(user_id) VALUES(?)', (uid,))
        if stats:
            conn.execute('UPDATE user_stats SET ' + ','.join(k + '=?' for k in stats) + ' WHERE user_id=?',
                         (*stats.values(), uid))
        for qid in mistakes:
            conn.execute('INSERT INTO mistake_log(user_id,question_id,wrong_count,correct_after,'
                         'first_wrong_at,last_wrong_at) VALUES(?,?,1,0,?,?)',
                         (uid, qid, '2026-10-01T00:00:00', '2026-10-01T00:00:00'))
        conn.commit()
    return uid


def client(rt, uid):
    c = rt.app.app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, username=f'g079-{uid}', plan='free', is_admin=False)
    return c


def post(c, route, body):
    return c.post('/api/g076/mistakes' + route, json=body)


def open_attempt(c, qid=TWO_STEP):
    issued = post(c, '/attempt', {'question_id': qid})
    assert issued.status_code == 200, issued.get_json()
    token = issued.get_json()['attempt_token']
    start = post(c, '/steps/start', {'flow': 'mistakes', 'attempt_token': token})
    assert start.status_code == 200, start.get_json()
    return token, start.get_json()


def step_body(token, cursor, move):
    return {'flow': 'mistakes', 'attempt_token': token, 'step_index': cursor['step_index'],
            'step_nonce': cursor['step_nonce'], 'move': {'x': move[0], 'y': move[1]}}


def play(c, qid, moves):
    token, cursor = open_attempt(c, qid)
    out = None
    for move in moves:
        out = c.post('/api/g076/mistakes/steps', json=step_body(token, cursor, move))
        assert out.status_code == 200, out.get_json()
        cursor = out.get_json()
    return token, cursor


def snapshot(rt, uid):
    result = {}
    with rt.app.get_db() as conn:
        tables = conn.execute("SELECT DISTINCT table_name FROM information_schema.columns "
                              "WHERE table_schema='public' AND column_name='user_id'").fetchall()
        for row in tables:
            name = row['table_name']
            rows = conn.execute(f'SELECT * FROM "{name}" WHERE CAST(user_id AS TEXT)=?', (str(uid),)).fetchall()
            result[name] = sorted((json.dumps(dict(r), sort_keys=True, default=str) for r in rows))
        events = conn.execute('SELECT e.* FROM g076_nonmap_events e JOIN g076_nonmap_sessions s '
                              'ON s.id=e.session_id WHERE s.user_id=?', (uid,)).fetchall()
        result['g076_nonmap_events'] = sorted(json.dumps(dict(r), sort_keys=True) for r in events)
    return result


def one(rt, sql, *params):
    with rt.app.get_db() as conn:
        row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def rows(rt, sql, *params):
    with rt.app.get_db() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def seed_quest(rt, uid, key, progress, completed=0):
    today = datetime.date.today().isoformat()
    target = next(q['target'] for q in rt.app.DAILY_QUEST_DEFS if q['key'] == key)
    with rt.app.get_db() as conn:
        conn.execute('INSERT INTO daily_quests(user_id,quest_key,target,progress,completed,xp_awarded,quest_date)'
                     ' VALUES(?,?,?,?,?,0,?)', (uid, key, target, progress, completed, today))
        conn.commit()


def seed_coins_earned(rt, uid, amount):
    with rt.app.get_db() as conn:
        conn.execute('UPDATE user_stats SET coins=? WHERE user_id=?', (amount, uid))
        conn.execute('INSERT INTO currency_log(user_id,delta,balance_after,reason,created_at) VALUES(?,?,?,?,?)',
                     (uid, amount, amount, 'g079-fixture-earned', datetime.datetime.now().isoformat()))
        conn.commit()


def earned_today(rt, uid):
    return one(rt, 'SELECT COALESCE(SUM(delta),0) AS s FROM currency_log WHERE user_id=? AND delta>0 '
                   'AND created_at>=?', uid, datetime.date.today().isoformat())['s']


# ─────────────────────────────── tests ───────────────────────────────

def test_on_two_step_correct_settles_every_writer_once(rt, on):
    uid = user(rt)
    c = client(rt, uid)
    assert c.get('/api/g076/mistakes/capability').get_json()['mode'] == 'steps'
    token, start = open_attempt(c)
    assert start['board_only'] and 'B[aa]' not in start['content']
    mid = c.post('/api/g076/mistakes/steps', json=step_body(token, start, (0, 0))).get_json()
    assert mid['status'] == 'CONTINUE' and mid['opponent_reply'] == [1, 1]
    assert rows(rt, 'SELECT * FROM review_log WHERE user_id=?', uid) == []
    final = c.post('/api/g076/mistakes/steps', json=step_body(token, mid, (2, 2)))
    assert final.status_code == 200, final.get_json()
    body = final.get_json()
    expected = rt.app.calc_xp_gain('10k', 1, True, True)[0]
    assert body['status'] == 'CORRECT' and body['settlement']['xp_awarded'] == expected == 37
    stats = one(rt, 'SELECT * FROM user_stats WHERE user_id=?', uid)
    assert (stats['xp'], stats['total_correct'], stats['mistake_corrected'],
            stats['current_streak'], stats['combo_streak']) == (37, 1, 1, 1, 1)
    assert stats['rank_level'] == 'LV%d' % rt.app.xp_to_lv(37)
    assert stats['player_max_hp'] >= rt.app._lv_max_hp(rt.app.xp_to_lv(37))
    review = rows(rt, 'SELECT * FROM review_log WHERE user_id=?', uid)
    assert len(review) == 1 and review[0]['source_context'] == 'mistakes' and review[0]['grade'] == 5
    card = one(rt, 'SELECT * FROM srs_cards WHERE user_id=?', uid)
    assert card['progress_credited'] == 1 and card['repetitions'] == 1
    mlog = one(rt, 'SELECT * FROM mistake_log WHERE user_id=?', uid)
    assert (mlog['wrong_count'], mlog['correct_after']) == (1, 1)
    quest = one(rt, "SELECT * FROM daily_quests WHERE user_id=? AND quest_key='streak_correct'", uid)
    assert quest['progress'] == 1 and not quest['completed']
    badges = {r['badge_id'] for r in rows(rt, 'SELECT badge_id FROM badges_earned WHERE user_id=?', uid)}
    assert badges  # the real badge writer ran (first-correct thresholds)
    before = snapshot(rt, uid)
    replay = c.post('/api/g076/mistakes/steps', json=step_body(token, mid, (2, 2))).get_json()
    assert replay == {**body, 'duplicate': True}
    reopen = post(c, '/steps/start', {'flow': 'mistakes', 'attempt_token': token}).get_json()
    assert reopen['status'] == 'CORRECT' and reopen['duplicate'] is True
    assert snapshot(rt, uid) == before
    rt.receipt['two_step_correct'] = {'xp': 37, 'badges': sorted(badges)}


def test_on_wrong_path_resets_streak_and_grants_nothing(rt, on):
    uid = user(rt, stats={'combo_streak': 4, 'current_streak': 4})
    c = client(rt, uid)
    token, cursor = play(c, TWO_STEP, [WRONG])
    assert cursor['status'] == 'INCORRECT' and cursor['settlement']['xp_awarded'] == 0
    stats = one(rt, 'SELECT * FROM user_stats WHERE user_id=?', uid)
    assert (stats['xp'], stats['current_streak'], stats['combo_streak'], stats['coins'] or 0) == (0, 0, 0, 0)
    assert one(rt, 'SELECT wrong_count FROM mistake_log WHERE user_id=?', uid)['wrong_count'] == 2
    assert one(rt, 'SELECT progress_credited FROM srs_cards WHERE user_id=?', uid)['progress_credited'] == 0
    assert rows(rt, 'SELECT * FROM currency_log WHERE user_id=?', uid) == []
    # Same day, same question: the server cursor is settled; no new attempt.
    issued = post(c, '/attempt', {'question_id': TWO_STEP}).get_json()
    assert issued['attempt_token'] == token
    again = post(c, '/steps/start', {'flow': 'mistakes', 'attempt_token': token}).get_json()
    assert again['status'] == 'INCORRECT' and again['duplicate']


def test_quest_completion_quest_xp_food_and_capped_coins(rt, on):
    uid = user(rt, mistakes=(7902,))
    seed_quest(rt, uid, 'streak_correct', 2)
    seed_coins_earned(rt, uid, 490)
    c = client(rt, uid)
    _, cursor = play(c, 7902, [(0, 0)])
    core = rt.app.calc_xp_gain('10k', 1, True, True)[0]
    quest_xp = 20  # DAILY_QUEST_DEFS streak_correct through the real _grant_quest_xp
    assert cursor['settlement']['xp_awarded'] == core + quest_xp
    assert one(rt, 'SELECT xp FROM user_stats WHERE user_id=?', uid)['xp'] == core + quest_xp
    quest = one(rt, "SELECT * FROM daily_quests WHERE user_id=? AND quest_key='streak_correct'", uid)
    assert quest['completed'] == 1 and quest['xp_awarded'] == quest_xp
    ledger = rows(rt, "SELECT * FROM currency_log WHERE user_id=? AND reason LIKE ?", uid, 'daily_quest:%')
    assert [(r['delta'], r['reason']) for r in ledger] == [(10, 'daily_quest:streak_correct')]
    assert one(rt, 'SELECT coins FROM user_stats WHERE user_id=?', uid)['coins'] == 500
    assert earned_today(rt, uid) == 500
    food = one(rt, "SELECT qty FROM pet_inventory WHERE user_id=? AND item_key='go_spirit_candy'", uid)
    assert food and food['qty'] == 1


def test_all_complete_bonus_cap_holds_at_500(rt, on):
    uid = user(rt, mistakes=(7903,))
    seed_quest(rt, uid, 'kill_monsters', 5, 1)
    seed_quest(rt, uid, 'challenge_dragon', 1, 1)
    seed_quest(rt, uid, 'streak_correct', 2)
    seed_coins_earned(rt, uid, 480)
    c = client(rt, uid)
    _, cursor = play(c, 7903, [(0, 0)])
    core = rt.app.calc_xp_gain('10k', 1, True, True)[0]
    assert cursor['settlement']['xp_awarded'] == core + 20 + 100
    assert earned_today(rt, uid) == 500
    reasons = [(r['delta'], r['reason']) for r in rows(
        rt, "SELECT * FROM currency_log WHERE user_id=? AND reason LIKE ? ORDER BY id", uid, 'daily_quest:%')]
    assert reasons == [(15, 'daily_quest:streak_correct'), (5, 'daily_quest:all_complete')]


def test_concurrent_duplicate_submit_is_one_settlement(rt, on):
    uid = user(rt, mistakes=(7904,))
    c1, c2 = client(rt, uid), client(rt, uid)
    token, cursor = open_attempt(c1, 7904)
    body = step_body(token, cursor, (0, 0))
    barrier = threading.Barrier(4)

    def go(c):
        barrier.wait()
        r = c.post('/api/g076/mistakes/steps', json=body)
        return r.status_code, r.get_json()
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(go, (c1, c2, c1, c2)))
    assert all(s == 200 for s, _ in results), results
    assert sorted(b['duplicate'] for _, b in results) == [False, True, True, True]
    assert len({b['settlement']['submission_id'] for _, b in results}) == 1
    assert len(rows(rt, 'SELECT * FROM review_log WHERE user_id=?', uid)) == 1
    assert one(rt, 'SELECT xp FROM user_stats WHERE user_id=?', uid)['xp'] == 37
    assert len(rows(rt, 'SELECT e.* FROM g076_nonmap_events e JOIN g076_nonmap_sessions s '
                        'ON s.id=e.session_id WHERE s.user_id=?', uid)) == 1


def test_concurrent_distinct_mistakes_keep_daily_coin_cap(rt, on, monkeypatch):
    qids = (7905, 7906, 7907, 7908, 7909, 7910)
    if os.environ.get('G079_NEGATIVE_CONTROL_NO_USER_LOCK') == '1':
        # Manual negative control only: proves the users-row lock is load-bearing.
        monkeypatch.setattr(rt.app, '_lock_user_for_daily_quota', lambda conn, uid: None)
    uid = user(rt, plan='premium', mistakes=qids)
    with rt.app.get_db() as conn:
        conn.execute("UPDATE users SET premium_until=? WHERE id=?",
                     ((datetime.date.today() + datetime.timedelta(days=30)).isoformat(), uid))
        conn.commit()
    seed_quest(rt, uid, 'kill_monsters', 5, 1)
    seed_quest(rt, uid, 'challenge_dragon', 1, 1)
    seed_quest(rt, uid, 'streak_correct', 2)
    seed_coins_earned(rt, uid, 490)
    prepared = []
    for qid in qids:
        c = client(rt, uid)
        prepared.append((c,) + open_attempt(c, qid))
    barrier = threading.Barrier(len(prepared))

    def go(item):
        c, token, cursor = item
        barrier.wait()
        r = c.post('/api/g076/mistakes/steps', json=step_body(token, cursor, (0, 0)))
        return r.status_code, r.get_json()
    with ThreadPoolExecutor(len(prepared)) as pool:
        results = list(pool.map(go, prepared))
    assert all(s == 200 and b['status'] == 'CORRECT' for s, b in results), results
    assert earned_today(rt, uid) == 500
    completions = rows(rt, "SELECT reason FROM currency_log WHERE user_id=? AND reason LIKE ?", uid, 'daily_quest:%')
    assert sorted(r['reason'] for r in completions) == ['daily_quest:streak_correct']  # bonus capped to 0
    assert len(rows(rt, 'SELECT * FROM review_log WHERE user_id=?', uid)) == len(qids)
    total_xp = sum(b['settlement']['xp_awarded'] for _, b in results)
    assert one(rt, 'SELECT xp FROM user_stats WHERE user_id=?', uid)['xp'] == total_xp
    rt.receipt['concurrent_cap'] = {'requests': len(qids), 'earned_today': 500, 'xp': total_xp}


WRITERS = [
    ('app', '_review_learning_in_transaction'), ('app', 'check_and_award'),
    ('app', '_update_daily_quests'), ('app', '_grant_quest_xp'), ('app', '_grant_coins'),
    ('app', '_grant_pet_food'), ('app', '_add_pet_xp_with_evolution'),
    ('g077', 'apply_srs_scheduling'), ('g077', 'insert_review_log_with_identity'),
    ('trigger', 'g076_nonmap_events'), ('trigger', 'g076_nonmap_sessions'),
]


@pytest.mark.parametrize('kind,name', WRITERS, ids=[w[1] for w in WRITERS])
def test_injected_writer_failure_rolls_back_everything(rt, on, monkeypatch, kind, name):
    import g077_mistakes_settlement as g077
    uid = user(rt, mistakes=(7911,))
    seed_quest(rt, uid, 'streak_correct', 2)   # make quest/coin/food writers reachable
    with rt.app.get_db() as conn:              # make the pet writer reachable
        conn.execute("INSERT INTO user_pets(user_id,pet_key,fullness,selected_at,last_fed_at) "
                     "VALUES(?,?,80,?,?)", (uid, 'star_shell_hatchling', datetime.datetime.now().isoformat(),
                                            datetime.datetime.now().isoformat()))
        conn.commit()
    c = client(rt, uid)
    token, cursor = open_attempt(c, 7911)
    calls = []
    if kind in ('app', 'g077'):
        target = rt.app if kind == 'app' else g077
        real = getattr(target, name)

        def broken(*args, **kwargs):
            calls.append(name)
            real(*args, **kwargs)          # the real write happens first ...
            raise RuntimeError('g079 injected failure after ' + name)  # ... then fails
        monkeypatch.setattr(target, name, broken)
    else:
        with rt.app.get_db() as conn:
            conn.execute(f"CREATE OR REPLACE FUNCTION g079_fail() RETURNS trigger AS $$ BEGIN "
                         f"RAISE EXCEPTION 'g079 injected'; END $$ LANGUAGE plpgsql")
            conn.execute(f'CREATE TRIGGER g079_fail BEFORE INSERT OR UPDATE ON {name} '
                         'FOR EACH ROW EXECUTE FUNCTION g079_fail()')
            conn.commit()
    before = snapshot(rt, uid)
    rt.app.app.config['TESTING'] = False
    try:
        response = c.post('/api/g076/mistakes/steps', json=step_body(token, cursor, (0, 0)))
    finally:
        rt.app.app.config['TESTING'] = True
        if kind == 'trigger':
            with rt.app.get_db() as conn:
                conn.execute(f'DROP TRIGGER g079_fail ON {name}')
                conn.commit()
    assert response.status_code == 503 and response.get_json() == {'error': 'mistakes_backend_hold'}
    assert kind == 'trigger' or calls, 'writer was not reached'
    assert snapshot(rt, uid) == before
    monkeypatch.undo()
    monkeypatch.setenv(FLAG, 'on')
    retry = c.post('/api/g076/mistakes/steps', json=step_body(token, cursor, (0, 0)))
    assert retry.status_code == 200, retry.get_json()
    assert retry.get_json()['settlement']['xp_awarded'] > 0
    assert len(rows(rt, 'SELECT * FROM review_log WHERE user_id=?', uid)) == 1
    assert one(rt, "SELECT completed FROM daily_quests WHERE user_id=? AND quest_key='streak_correct'",
               uid)['completed'] == 1
    pet = one(rt, 'SELECT xp FROM user_pets WHERE user_id=?', uid)
    assert pet['xp'] == 1


def test_rejections_write_nothing(rt, on, monkeypatch):
    uid = user(rt, mistakes=(TWO_STEP, 7950))
    other = user(rt, mistakes=(TWO_STEP,))
    c, o = client(rt, uid), client(rt, other)
    token, cursor = open_attempt(c)
    body = step_body(token, cursor, (0, 0))
    before, before_other = snapshot(rt, uid), snapshot(rt, other)
    outcomes = {
        'other_account_step': o.post('/api/g076/mistakes/steps', json=body),
        'other_account_start': post(o, '/steps/start', {'flow': 'mistakes', 'attempt_token': token}),
        'forged_nonce': c.post('/api/g076/mistakes/steps', json={**body, 'step_nonce': '0' * 64}),
        'client_grade': c.post('/api/g076/mistakes/steps', json={**body, 'grade': 5}),
        'client_correct': c.post('/api/g076/mistakes/steps', json={**body, 'correct': True}),
        'client_reward': c.post('/api/g076/mistakes/steps', json={**body, 'xp_awarded': 999}),
        'forged_token': c.post('/api/g076/mistakes/steps', json={**body, 'attempt_token': token[:-4] + 'AAAA'}),
        'not_owned': post(c, '/attempt', {'question_id': 7902}),
        'premium_only': post(c, '/attempt', {'question_id': 7950}),
        'anonymous': rt.app.app.test_client().post('/api/g076/mistakes/steps', json=body),
        'cross_site': c.post('/api/g076/mistakes/steps', json=body, headers={'Sec-Fetch-Site': 'cross-site'}),
    }
    questions = rt.app._load_questions()
    changed = [dict(q, content=q['content'].replace('B[cc]', 'B[dd]')) if q['id'] == TWO_STEP else q
               for q in questions]
    monkeypatch.setattr(rt.app, '_load_questions', lambda: changed)
    outcomes['revision_changed'] = c.post('/api/g076/mistakes/steps', json=body)
    monkeypatch.setattr(rt.app, '_load_questions', lambda: questions)
    statuses = {k: (r.status_code, (r.get_json(silent=True) or {}).get('error')) for k, r in outcomes.items()}
    assert all(code >= 400 for code, _ in statuses.values()), statuses
    assert statuses['premium_only'] == (403, 'premium_required')
    assert statuses['not_owned'] == (403, 'mistake_not_owned')
    assert statuses['client_grade'][0] == 400 and statuses['client_correct'][0] == 400
    assert snapshot(rt, uid) == before and snapshot(rt, other) == before_other
    good = c.post('/api/g076/mistakes/steps', json=body)
    assert good.status_code == 200 and good.get_json()['status'] == 'CONTINUE'
    rt.receipt['rejections'] = statuses


def test_expired_token_rejected_without_writes(rt, on, monkeypatch):
    import practice_answer_authority
    uid = user(rt, mistakes=(7902,))
    c = client(rt, uid)
    token, cursor = open_attempt(c, 7902)
    before = snapshot(rt, uid)
    real = practice_answer_authority.verify_practice_attempt
    later = practice_answer_authority.PRACTICE_ATTEMPT_TTL_SECONDS + 3600

    def expired(*args, **kwargs):
        import time
        kwargs['now'] = int(time.time()) + later
        return real(*args, **kwargs)
    import g076_nonmap_steps
    monkeypatch.setattr(g076_nonmap_steps, 'verify_practice_attempt', expired)
    r = c.post('/api/g076/mistakes/steps', json=step_body(token, cursor, (0, 0)))
    assert r.status_code >= 400, r.get_json()
    assert snapshot(rt, uid) == before
    rt.receipt['expired'] = [r.status_code, r.get_json()]


def test_free_daily_quota_admission_at_terminal(rt, on):
    uid = user(rt, mistakes=(7902,))
    c = client(rt, uid)
    token, cursor = open_attempt(c, 7902)
    with rt.app.get_db() as conn:
        for i in range(rt.app.FREE_DAILY_LIMIT):
            conn.execute('INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context,submission_id) '
                         'VALUES(?,?,?,?,?,?)', (uid, 1, 5, datetime.datetime.now().isoformat(), 'practice',
                                                 f'g079-quota-{uid}-{i}'))
        conn.commit()
    before = snapshot(rt, uid)
    r = c.post('/api/g076/mistakes/steps', json=step_body(token, cursor, (0, 0)))
    assert (r.status_code, r.get_json()) == (429, {'error': 'daily_limit'})
    assert snapshot(rt, uid) == before
    with rt.app.get_db() as conn:   # extra capacity through the existing reader
        conn.execute('UPDATE users SET plan=?, premium_until=? WHERE id=?',
                     ('premium', (datetime.date.today() + datetime.timedelta(days=3)).isoformat(), uid))
        conn.commit()
    ok = c.post('/api/g076/mistakes/steps', json=step_body(token, cursor, (0, 0)))
    assert ok.status_code == 200 and ok.get_json()['status'] == 'CORRECT'


def test_quest_v2_mode_records_mistakes_answer_event_atomically(rt, on, monkeypatch):
    from migrations.quest_progress_v2 import upgrade as qp
    from migrations.quest_claim_v1 import upgrade as qc
    with rt.app.get_db() as conn:
        qp(conn)
        qc(conn)
        conn.commit()
    monkeypatch.setenv('QUEST_V2_RUNTIME_ENABLED', '1')
    uid = user(rt, mistakes=(7902,))
    c = client(rt, uid)
    token, cursor = open_attempt(c, 7902)
    before = snapshot(rt, uid)
    real, seen = rt.app.apply_quest_runtime_event, []

    def broken(conn, *, event, server_now):
        seen.append(event.payload.get('source_scope'))
        real(conn, event=event, server_now=server_now)
        raise RuntimeError('g079 injected quest v2 failure')
    monkeypatch.setattr(rt.app, 'apply_quest_runtime_event', broken)
    rt.app.app.config['TESTING'] = False
    try:
        failed = c.post('/api/g076/mistakes/steps', json=step_body(token, cursor, (0, 0)))
    finally:
        rt.app.app.config['TESTING'] = True
    assert failed.status_code == 503 and seen == ['mistakes']
    assert snapshot(rt, uid) == before
    monkeypatch.setattr(rt.app, 'apply_quest_runtime_event', real)
    ok = c.post('/api/g076/mistakes/steps', json=step_body(token, cursor, (0, 0)))
    assert ok.status_code == 200 and ok.get_json()['status'] == 'CORRECT'
    after = snapshot(rt, uid)
    changed = sorted(t for t in set(before) | set(after) if before.get(t) != after.get(t))
    quest_tables = [t for t in changed if t.startswith('quest')]
    assert quest_tables, changed
    assert one(rt, "SELECT COUNT(*) AS n FROM daily_quests WHERE user_id=?", uid)['n'] == 0  # legacy off
    rt.receipt['quest_v2_tables_written'] = quest_tables


def test_off_keeps_legacy_routes(rt, monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    monkeypatch.delenv('G076_ANSWER_PRIVACY_ENFORCED', raising=False)
    uid = user(rt, mistakes=(TWO_STEP,))
    c = client(rt, uid)
    assert c.get('/api/g076/mistakes/capability').get_json() == {'mode': 'legacy',
                                                                  'protocol': 'g076-mistakes-steps-v1'}
    r = post(c, '/attempt', {'question_id': TWO_STEP})
    assert (r.status_code, r.get_json()) == (503, {'error': 'mistakes_steps_disabled'})
    listing = c.get('/api/mistakes').get_json()
    assert listing[0]['question_id'] == TWO_STEP and 'B[aa]' in listing[0]['content']
    assert 'board_only' not in listing[0]
    review = c.post('/api/srs/review', json={'question_id': TWO_STEP, 'grade': 5})
    assert review.status_code == 200 and review.get_json()['ok'] is True
    assert review.get_json()['xp_gain'] == 0       # public grade remains scheduling-only
    assert rows(rt, 'SELECT * FROM g076_mistakes_attempts WHERE user_id=?', uid) == []


def test_g080_internal_map_progression_waits_for_same_user_reward_lock(rt, on):
    """Real PG: internal Map handoff must serialize with Mistakes' user row.

    A deliberately unknown settlement is sufficient to prove lock ORDER:
    without the early user lock this request returns 409 immediately, while
    a true user lock waits until the conflicting transaction commits.  No
    reward or player data is written by this synthetic rejected request.
    """
    import concurrent.futures
    import time
    import uuid
    uid = user(rt, plan='premium', mistakes=())
    app = rt.app
    with app.get_db() as held:
        held.execute('SELECT id FROM users WHERE id=? FOR UPDATE', (uid,)).fetchone()
        def call_progression():
            with app.app.test_request_context('/api/srs/review'):
                result = app._srs_review_operation_legacy(
                    uid, {'question_id': None}, internal=True,
                    submission_id=str(uuid.uuid4()),
                )
                if isinstance(result, tuple):
                    return result[1]
                return result.status_code
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(call_progression)
            time.sleep(.35)
            assert not future.done(), 'internal Map path bypassed the users row lock'
            held.commit()
            assert future.result(timeout=15) == 409


def _g080_map_settlement(rt, uid, qid=7902):
    """Create a genuine committed Map Battle settlement on disposable PG."""
    from map_battle_persistence import create_map_battle, ensure_map_battle_tables
    from map_battle_runtime import (ensure_submission_lifecycle_schema,
        issue_attempt_for_context, issue_submission_nonce_for_attempt, settle_answer)
    import uuid
    now = datetime.datetime.now(datetime.timezone.utc)
    at = now.isoformat()
    later = (now + datetime.timedelta(hours=1)).isoformat()
    battle_id, attempt_id = 'g080-battle-' + uuid.uuid4().hex, 'g080-attempt-' + uuid.uuid4().hex
    q = next(q for q in json.loads(QUESTIONS.read_text(encoding='utf-8')) if q['id'] == qid)
    with rt.app.get_db() as conn:
        ensure_map_battle_tables(conn)
        ensure_submission_lifecycle_schema(conn)
        create_map_battle(conn, battle_id=battle_id, user_id=uid,
            zone_key='legacy::g080-test', player_hp=100, player_hp_max=100,
            monster_hp=100, monster_hp_max=100, now=at)
        issue_attempt_for_context(conn, user_id=uid, battle_id=battle_id,
            question=q, initial_position_identity='g080-position',
            board_size=5, player_color='B', transform_version='transform-v1',
            transform_id='identity', attempt_id=attempt_id, issued_at=at, expires_at=later)
        issued = issue_submission_nonce_for_attempt(conn,user_id=uid,attempt_id=attempt_id,
            now=at,mode_environ={'E10_MAP_BATTLE_V1_MODE':'global'})
        attempt = conn.execute('SELECT * FROM map_battle_attempts WHERE id=?',(attempt_id,)).fetchone()
        submitted = settle_answer(conn,user_id=uid,payload={
            'battle_id':battle_id,'attempt_id':attempt_id,
            'submission_nonce':issued['submission_nonce'],'battle_revision':0,
            'question_revision':attempt['question_revision'],'player_color':'black',
            'transform_id':'identity','transform_version':'transform-v1',
            'moves':[{'x':0,'y':0}]},
            question_loader=lambda x:q if x==qid else None,
            mode_environ={'E10_MAP_BATTLE_V1_MODE':'global'},now=at)
        conn.commit()
    assert submitted['result']=='CORRECT', submitted
    return submitted

def _g080_apply_map(rt, uid, settlement):
    with rt.app.app.test_request_context('/api/adventure/map-battles/v1/answers',method='POST'):
        from flask import session
        session.update(user_id=uid,plan='premium')
        return rt.app._run_map_battle_progression(uid,settlement)

def test_g080_real_map_reward_solo_postgresql(rt,on):
    uid=user(rt,plan='premium',mistakes=(7903,))
    s=_g080_map_settlement(rt,uid)
    body,status=_g080_apply_map(rt,uid,s)
    assert status==200,(body,status)
    assert body['status']=='applied',body
    again,again_status=_g080_apply_map(rt,uid,s)
    assert again_status==200 and again['status']=='duplicate',(again,again_status)
    logs=rows(rt,'SELECT id FROM review_log WHERE user_id=? AND source_context LIKE ?',uid,'mbv1:%')
    assert len(logs)==1


def _g080_seed_reward_player(rt,uid):
    with rt.app.get_db() as conn:
        conn.execute("INSERT INTO user_pets(user_id,pet_key,selected_at) VALUES(?,?,?)",
                     (uid,'go_spirit','2026-10-24T00:00:00'))
        conn.commit()
    seed_quest(rt,uid,'streak_correct',2)
    seed_coins_earned(rt,uid,490)


def test_g080_map_tail_failure_rolls_back_core_then_retries_once(rt,on,monkeypatch):
    uid=user(rt,plan='premium',mistakes=(7903,))
    _g080_seed_reward_player(rt,uid)
    settlement=_g080_map_settlement(rt,uid)
    before=snapshot(rt,uid)
    original=rt.app._map_battle_noncombat_progression
    def injected(*args,**kw):
        raise RuntimeError('G080_SYNTHETIC_TAIL_DB_FAILURE')
    monkeypatch.setattr(rt.app,'_map_battle_noncombat_progression',injected)
    body,status=_g080_apply_map(rt,uid,settlement)
    assert status==503 and body.get('retryable'),(body,status)
    assert snapshot(rt,uid)==before, 'core or item was committed before failing tail'
    monkeypatch.setattr(rt.app,'_map_battle_noncombat_progression',original)
    done,status=_g080_apply_map(rt,uid,settlement)
    assert status==200 and done['status']=='applied',(done,status)
    saved=snapshot(rt,uid)
    duplicate,code=_g080_apply_map(rt,uid,settlement)
    assert code==200 and duplicate['status']=='duplicate'
    assert snapshot(rt,uid)==saved
    assert len(rows(rt,'SELECT id FROM review_log WHERE user_id=? AND source_context LIKE ?',uid,'mbv1:%'))==1
    assert earned_today(rt,uid)==500
    quest=one(rt,"SELECT completed,xp_awarded FROM daily_quests WHERE user_id=? AND quest_key='streak_correct'",uid)
    assert quest=={'completed':1,'xp_awarded':20},quest
    assert one(rt,"SELECT qty FROM pet_inventory WHERE user_id=? AND item_key='go_spirit_candy'",uid)['qty']==1


@pytest.mark.parametrize('round_index',range(8))
def test_g080_real_pg_b1_vs_map_concurrent_reward_integrity(rt,on,round_index):
    uid=user(rt,plan='premium',mistakes=(7903,))
    _g080_seed_reward_player(rt,uid)
    settlement=_g080_map_settlement(rt,uid)
    c=client(rt,uid)
    token,cursor=open_attempt(c,7903)
    request=step_body(token,cursor,(0,0))
    gate=threading.Barrier(2)
    def run_map():
        gate.wait(timeout=10)
        return _g080_apply_map(rt,uid,settlement)
    def run_mistakes():
        gate.wait(timeout=10)
        c2=client(rt,uid)
        r=c2.post('/api/g076/mistakes/steps',json=request)
        return (r.get_json(),r.status_code)
    with ThreadPoolExecutor(max_workers=2) as pool:
        fa=pool.submit(run_map)
        fb=pool.submit(run_mistakes)
        map_body,map_status=fa.result(timeout=30)
        b1_body,b1_status=fb.result(timeout=30)
    assert map_status==200 and map_body['status']=='applied',(map_status,map_body)
    assert b1_status==200 and b1_body['status']=='CORRECT',(b1_status,b1_body)
    logs=rows(rt,'SELECT source_context FROM review_log WHERE user_id=?',uid)
    assert len(logs)==2 and {v['source_context'].startswith('mbv1:') for v in logs}=={False,True},logs
    stat=one(rt,'SELECT xp,coins,total_correct,combo_streak FROM user_stats WHERE user_id=?',uid)
    map_awarded_quest = any(q.get('key')=='streak_correct' and q.get('pet_reward')
                            for q in map_body.get('quest_updates',[]))
    expected_xp = (int(map_body['xp_gain']) + int(b1_body['settlement']['xp_awarded'])
                   + (20 if map_awarded_quest else 0))
    assert stat['total_correct']==2 and stat['xp']==expected_xp,(stat,expected_xp)
    assert stat['coins']==500,stat
    quest=one(rt,"SELECT completed,xp_awarded FROM daily_quests WHERE user_id=? AND quest_key='streak_correct'",uid)
    assert quest=={'completed':1,'xp_awarded':20},quest
    assert earned_today(rt,uid)==500
    assert len(rows(rt,"SELECT id FROM currency_log WHERE user_id=? AND reason='daily_quest:streak_correct'",uid))==1
    assert one(rt,"SELECT qty FROM pet_inventory WHERE user_id=? AND item_key='go_spirit_candy'",uid)['qty']==1
    assert one(rt,'SELECT xp FROM user_pets WHERE user_id=?',uid)['xp']>=1
    prior=snapshot(rt,uid)
    replay1,replay_status=_g080_apply_map(rt,uid,settlement)
    replay2=c.post('/api/g076/mistakes/steps',json=request)
    assert replay_status==200 and replay1['status']=='duplicate'
    assert replay2.status_code==200 and replay2.get_json()['duplicate'] is True
    assert snapshot(rt,uid)==prior


@pytest.mark.parametrize('failure',['crash','pg-disconnect'])
def test_g080_pg_map_core_tail_process_restart_after_failure(rt,on,failure):
    """Actual external process & PG sockets: crash/terminate backend then fresh app."""
    uid=user(rt,plan='premium',mistakes=(7903,))
    _g080_seed_reward_player(rt,uid)
    settlement=_g080_map_settlement(rt,uid)
    before=snapshot(rt,uid)
    worker=ROOT/'tests'/'e2e'/'g080_map_restart_worker.py'
    def execute(mode):
        env=os.environ.copy()
        env['DATABASE_URL']=rt.dsn
        env['QUESTIONS_JSON_PATH']=str(QUESTIONS)
        env['SECRET_KEY']='g080-pg-disposable-worker'
        env['G076_MISTAKES_STEPS_ENABLED']='on'
        return subprocess.run([sys.executable,'-B',str(worker),str(uid),json.dumps(settlement),mode],
            cwd=str(ROOT),env=env,capture_output=True,text=True,timeout=60)
    killed=execute(failure)
    assert killed.returncode!=0,(killed.stdout,killed.stderr)
    assert snapshot(rt,uid)==before,('partial commit after '+failure,killed.stderr[-800:])
    fresh=execute('normal')
    assert fresh.returncode==0,(fresh.stdout,fresh.stderr[-1200:])
    applied=json.loads(fresh.stdout.splitlines()[-1])
    assert applied['status']==200 and applied['payload']['status']=='applied',applied
    committed=snapshot(rt,uid)
    duplicate=execute('normal')
    assert duplicate.returncode==0,(duplicate.stdout,duplicate.stderr[-800:])
    assert json.loads(duplicate.stdout.splitlines()[-1])['payload']['status']=='duplicate'
    assert snapshot(rt,uid)==committed
    assert len(rows(rt,'SELECT id FROM review_log WHERE user_id=? AND source_context LIKE ?',uid,'mbv1:%'))==1
    assert earned_today(rt,uid)==500


def test_g080_pg_lock_inversion_deadlock_detected_and_recoverable(rt,on):
    """Deliberately invert two users-row locks; show PG abort and recovery.

    This is a DB failure-injection (not a claim that Product locks invert).
    Production Map/Mistakes use the same users-row-first ordering.
    """
    import psycopg2
    a=user(rt,plan='premium',mistakes=())
    b=user(rt,plan='premium',mistakes=())
    gate=threading.Barrier(2)
    def inverted(first,second):
        conn=psycopg2.connect(rt.dsn,connect_timeout=5)
        try:
            with conn.cursor() as cur:
                cur.execute('SET lock_timeout=\'5s\'')
                cur.execute('SELECT id FROM users WHERE id=%s FOR UPDATE',(first,))
                gate.wait(timeout=10)
                try:
                    cur.execute('SELECT id FROM users WHERE id=%s FOR UPDATE',(second,))
                    conn.commit()
                    return 'committed'
                except psycopg2.Error as e:
                    code=e.pgcode
                    conn.rollback()
                    return code
        finally:
            conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        left=pool.submit(inverted,a,b)
        right=pool.submit(inverted,b,a)
        results={left.result(timeout=20),right.result(timeout=20)}
    assert results=={'committed','40P01'},results
    def canonical():
        conn=psycopg2.connect(rt.dsn,connect_timeout=5)
        try:
            with conn.cursor() as cur:
                cur.execute('SET lock_timeout=\'5s\'')
                for uid in sorted([a,b]):
                    cur.execute('SELECT id FROM users WHERE id=%s FOR UPDATE',(uid,))
                conn.commit()
                return 'recovered'
        finally:
            conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        both=list(pool.map(lambda _:canonical(),range(2)))
    assert both==['recovered','recovered']
