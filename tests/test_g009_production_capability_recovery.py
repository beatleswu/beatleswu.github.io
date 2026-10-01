"""D001/D002 disposable contracts; never Production or corpus acceptance."""
import datetime
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from urllib.parse import urlsplit

import pytest


@pytest.fixture
def application(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'g009-capability-test-only')
    import app
    return app


@pytest.fixture
def content_env(application, monkeypatch):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE users(id INTEGER PRIMARY KEY, plan TEXT, premium_until TEXT);
        INSERT INTO users VALUES(101,'free',NULL);
        CREATE TABLE mistake_log(user_id INTEGER, question_id INTEGER,
                                 wrong_count INTEGER, last_wrong_at TEXT);
        INSERT INTO mistake_log VALUES(101,990001,1,'2026-10-01');
    ''')
    question = dict(id=990001, rank='1d', topic='7迷霧森林',
                    content='(;SZ[19]PL[B];B[dd]TE[1])', comment='private-solution',
                    accepted_moves=[dict(x=3,y=3)], katago_best_move='dd', score_gap=5)
    class Connection:
        def execute(self, sql, args=()): return conn.execute(sql,args)
        def commit(self): conn.commit()
        def rollback(self): conn.rollback()
        def close(self): pass
        def __enter__(self): return conn
        def __exit__(self, kind, value, traceback):
            conn.rollback() if kind else conn.commit()
    conn.commit()
    monkeypatch.setattr(application, 'get_db', Connection)
    monkeypatch.setattr(application, '_load_questions', lambda: [question])
    monkeypatch.setenv('E10_MAP_BATTLE_V1_MODE', 'global')
    client = application.app.test_client()
    with client.session_transaction() as s:
        s['user_id'] = 101
        s['plan'] = 'premium'  # stale client cache must not authorize content
    yield client, conn, question
    conn.close()


@pytest.mark.parametrize('premium', [False, True])
def test_real_question_endpoint_field_policy_and_db_entitlement(content_env, premium):
    client, conn, question = content_env
    if premium:
        conn.execute("UPDATE users SET plan='premium'")
    response = client.get('/api/question/990001')
    assert response.status_code == 200
    body = response.get_json()
    assert body['locked'] is (not premium)
    assert body['content'] == (question['content'] if premium else '')
    assert body['comment'] == (question['comment'] if premium else '')
    assert body['katago_best_move'] == ('dd' if premium else '')
    assert body['score_gap'] == (5 if premium else None)
    assert body['accepted_moves'] == (question['accepted_moves'] if premium else [])


@pytest.mark.parametrize('premium', [False, True])
def test_mistakes_do_not_leak_locked_sgf(content_env, premium):
    client, conn, question = content_env
    if premium:
        conn.execute("UPDATE users SET plan='premium'")
    response = client.get('/api/mistakes')
    assert response.status_code == 200
    assert response.get_json()[0]['content'] == (question['content'] if premium else '')


@pytest.mark.parametrize('path,body,headers', [
    ('/api/srs/practice/attempt', {'question_id':990001}, {}),
    ('/api/adventure/map-battles/v1/attempts',
     {'zone_key':'k11_15','question_id':990001}, {'X-Map-Battle-Client-Protocol':'v1'}),
])
def test_real_attempt_routes_reject_paid_question_before_state_creation(content_env, path, body, headers):
    client, conn, _ = content_env
    before = conn.total_changes
    response = client.post(path, json=body, headers=headers)
    assert response.status_code == 403
    assert response.get_json()['code'] == 'premium_required'
    assert conn.total_changes == before


def test_quota_pending_settlement_counts_once_and_d5b_remains_exempt(application):
    conn = sqlite3.connect(':memory:'); conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE review_log(user_id INTEGER, source_context TEXT, reviewed_at TEXT);
        CREATE TABLE map_battle_submissions(id TEXT, user_id INTEGER, settlement_state TEXT,
                                           settled_at TEXT, received_at TEXT, created_at TEXT);
    ''')
    today = datetime.date.today().isoformat()
    conn.execute('INSERT INTO review_log VALUES(?,?,?)', (101,application.DAILY_D5B_SOURCE_PREFIX+'test',today))
    conn.execute('INSERT INTO map_battle_submissions VALUES(?,?,?,?,?,?)', ('s1',101,'SETTLED',today,today,today))
    conn.execute('INSERT INTO map_battle_submissions VALUES(?,?,?,?,?,?)', ('s2',101,'PENDING',today,today,today))
    assert application._today_free_count_in_transaction(conn,101) == 1
    conn.execute('INSERT INTO review_log VALUES(?,?,?)', (101,'mbv1:s1',today))
    assert application._today_free_count_in_transaction(conn,101) == 1
    conn.close()


def test_public_community_projection_zero_write_and_default_rewards_view_excluded(application):
    from tests.test_p0_community_leaderboard_make_whole import _db, _add_user, _add_review, _add_recovery, WEEK_START, WEEK_END
    import community_leaderboard_rewards as leaderboard
    conn = _db(); _add_user(conn,1)
    _add_review(conn,user_id=1,question_id=101,reviewed_at='2026-09-14T01:00:00')
    _add_recovery(conn,user_id=1,question_id=101,canonical_question_id='uuid-101');conn.commit()
    before=conn.total_changes
    normal=leaderboard.fetch_leaderboard_participant_rows(conn,WEEK_START,WEEK_END)
    first=application._fetch_community_leaderboard_score_rows(conn,WEEK_START,WEEK_END)
    second=application._fetch_community_leaderboard_score_rows(conn,WEEK_START,WEEK_END)
    assert normal == []
    assert len(first) == 1 and first[0]['score'] == 1
    assert first == second
    assert conn.total_changes == before
    conn.close()


def test_postgres_concurrent_quota_20th_only_and_rollback(application, monkeypatch):
    """Real two-session PostgreSQL test of the exact runtime admission callback."""
    dsn=os.environ.get('G009_DISPOSABLE_QUOTA_TEST_DSN')
    if not dsn:
        pytest.skip('explicit disposable PostgreSQL DSN required')
    parsed=urlsplit(dsn)
    assert parsed.hostname == '127.0.0.1' and parsed.port == 55439
    assert parsed.path == '/postgres' and parsed.username == 'g009test'
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper
    schema='g009_quota_'+uuid.uuid4().hex
    def connect():
        raw=psycopg2.connect(dsn,cursor_factory=DictCursor)
        c=PostgresConnectionWrapper(raw)
        c.execute('SET search_path TO '+schema)
        c.execute("SET lock_timeout='5s'")
        return c
    setup=connect();setup.execute('CREATE SCHEMA '+schema)
    setup.execute('CREATE TABLE users(id INTEGER PRIMARY KEY)')
    setup.execute('INSERT INTO users VALUES(101)')
    setup.execute('CREATE TABLE review_log(user_id INTEGER,source_context TEXT,reviewed_at TEXT)')
    setup.execute('CREATE TABLE map_battle_submissions(id TEXT,user_id INTEGER,settlement_state TEXT,settled_at TEXT,received_at TEXT,created_at TEXT)')
    setup.execute('CREATE TABLE active_effects(user_id INTEGER,effect_key TEXT,effect_date TEXT,value INTEGER)')
    today=datetime.date.today().isoformat()
    for i in range(19):
        setup.execute('INSERT INTO review_log VALUES(?,?,?)',(101,'practice',today))
    setup.commit()
    # Entitlement authorization is independently DB-tested above. This test
    # isolates row-lock/quota admission, not account/browser acceptance.
    monkeypatch.setattr(application,'is_premium',lambda uid:False)
    held=threading.Event();waiting=threading.Event();release=threading.Event();done=threading.Event()
    results=[];errors=[]
    def first():
        c=connect()
        try:
            application._admit_map_battle_answer_entitlement(c,101,{'rank':'30k'})
            held.set(); assert release.wait(5)
            c.execute('INSERT INTO review_log VALUES(?,?,?)',(101,'practice',today));c.commit()
            results.append('accepted')
        except Exception as e: errors.append(e);c.rollback()
        finally:c.close()
    def second():
        c=connect()
        try:
            assert held.wait(5);waiting.set()
            application._admit_map_battle_answer_entitlement(c,101,{'rank':'30k'})
            results.append('incorrectly-accepted')
        except application.MapBattleEntitlementRejected as e:
            assert e.code == 'daily_limit' and e.details['today_count'] == 20
            c.rollback();results.append('rejected')
        except Exception as e: errors.append(e);c.rollback()
        finally:c.close();done.set()
    t1=threading.Thread(target=first);t2=threading.Thread(target=second)
    try:
        t1.start(); assert held.wait(5);t2.start();assert waiting.wait(5)
        assert not done.wait(.2), 'second session must block while first holds users lock'
        release.set();t1.join(8);t2.join(8)
        assert not t1.is_alive() and not t2.is_alive()
        assert not errors
        assert sorted(results)==['accepted','rejected']
        assert setup.execute('SELECT COUNT(*) AS cnt FROM review_log').fetchone()['cnt']==20
        # Rejected admissions cannot append another row; missing user fail closed.
        with pytest.raises(LookupError): application._lock_user_for_daily_quota(setup,999)
        setup.rollback()
    finally:
        release.set();t1.join(8)
        if t2.ident:t2.join(8)
        setup.close()
        cleanup=psycopg2.connect(dsn);cleanup.autocommit=True
        with cleanup.cursor() as cursor:cursor.execute('DROP SCHEMA '+schema+' CASCADE')
        cleanup.close()
