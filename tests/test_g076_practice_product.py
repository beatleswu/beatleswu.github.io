"""Actual app.py routes and original Practice writer; disposable DB only."""
import copy
import sqlite3
import os
import uuid
from pathlib import Path

import pytest

from migrations.g076_practice_steps_v1 import upgrade
from migrations.puzzle_identity_registry_v1 import upgrade as identity_schema
from puzzle_identity_store import PuzzleIdentityStore

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ('G076_ANSWER_PRIVACY_ENFORCED', 'G076_NONMAP_STEPS_ENABLED', 'G076_PRACTICE_STEPS_ENABLED')
Q = {'id': 701, 'content': '(;SZ[5]PL[B]AB[ee];B[aa];W[bb];B[cc])',
     'discipline': 'life_death', 'stage': 'LV2', 'enabled': True}


def seed(conn):
    upgrade(conn, environ={'G076_PRACTICE_STEPS_MIGRATION_APPROVED': '1'})
    statements = '''
    CREATE TABLE users(id INTEGER PRIMARY KEY, elo_rating REAL, xp INTEGER,plan TEXT,premium_until TEXT);
    INSERT INTO users VALUES(101,1400,37,'premium',NULL);
    INSERT INTO users VALUES(102,1400,37,'premium',NULL);
    CREATE TABLE srs_cards(user_id INTEGER,question_id INTEGER,ease_factor REAL,
        interval INTEGER,repetitions INTEGER,due_date TEXT,last_grade INTEGER,
        updated_at TEXT,progress_credited INTEGER,PRIMARY KEY(user_id,question_id));
    CREATE TABLE review_log(user_id INTEGER, question_id INTEGER,grade INTEGER,
        topic TEXT,level TEXT,difficulty TEXT,reviewed_at TEXT,response_ms INTEGER,
        discipline TEXT,player_rating_snapshot REAL,question_rating_snapshot REAL,
        item_rating_version TEXT,question_version TEXT,source_context TEXT,is_scaffolding INTEGER,
        training_set_id INTEGER,submission_id TEXT,submission_payload_hash TEXT,
        UNIQUE(user_id,submission_id));
    '''
    for statement in statements.split(';'):
        if statement.strip(): conn.execute(statement)
    identity_schema(conn)
    conn.execute('''INSERT INTO puzzle_identity_bootstrap_receipt
        (receipt_sha256,frozen_corpus_sha256,record_count,namespace_uuid,
         canonicalisation_rules_version,genesis_key_spec_version,historical_tree_commit,
         historical_tree_manifest_sha256,historical_rename_map_sha256,
         genesis_record_manifest_sha256,proposed_uuid_list_sha256,status,applied_at,applied_by)
        VALUES ('test','test',1,'test','test','test','test','test','test','test','test',
                'APPLIED','2026-10-23T00:00:00+00:00','isolated fixture')''')
    PuzzleIdentityStore(conn).create_native_identity(
        creation_reason='isolated Practice product test', legacy_question_id=701)
    conn.commit()


@pytest.fixture(params=['sqlite', 'postgres'])
def product(tmp_path, monkeypatch, request):
    import app as runtime
    path = tmp_path/'product.sqlite'
    admin = None
    if request.param == 'postgres':
        if os.environ.get('G076_LOCAL_PG_TEST') != '1':
            pytest.skip('explicit disposable localhost PG fixture not selected')
        import psycopg2
        from psycopg2.extras import DictCursor
        from db import PostgresConnectionWrapper
        # Deliberately ignores DATABASE_URL and any product credentials.
        params = dict(host='127.0.0.1', port=55493, user='g076',
                      password='g076-local-fixture', connect_timeout=5)
        admin = psycopg2.connect(dbname='g076_practice_fixture', **params)
        admin.autocommit = True
        database = 'g076_practice_test_' + uuid.uuid4().hex
        admin.cursor().execute('CREATE DATABASE '+database)
        def connect():
            return PostgresConnectionWrapper(psycopg2.connect(dbname=database,
                cursor_factory=DictCursor, **params), pooled=False)
    else:
        def connect():
            conn = sqlite3.connect(path, timeout=15)
            conn.row_factory = sqlite3.Row
            conn.create_function('GREATEST', 2, max)
            return conn
    with connect() as conn: seed(conn)
    state = {'question': copy.deepcopy(Q), 'premium': True, 'free': True, 'quota': None}
    monkeypatch.setattr(runtime, 'get_db', connect)
    # Real token, identity resolver, question context, judge, review writer,
    # SRS core, curriculum aggregation and route registration are retained.
    monkeypatch.setattr(runtime, '_load_questions', lambda: [state['question']])
    monkeypatch.setattr(runtime, 'is_premium', lambda *a: state['premium'])
    monkeypatch.setattr(runtime, 'question_is_free', lambda q: state['free'])
    monkeypatch.setattr(runtime, '_lock_user_for_daily_quota', lambda c,u: None)
    monkeypatch.setattr(runtime, '_daily_quota_snapshot_in_transaction', lambda c,u: {})
    monkeypatch.setattr(runtime, '_daily_quota_rejection', lambda s: state['quota'])
    for flag in FLAGS: monkeypatch.setenv(flag, 'true')
    runtime.app.config['TESTING'] = True
    client = runtime.app.test_client()
    with client.session_transaction() as session: session['user_id'] = 101
    yield runtime, client, connect, state
    if admin:
        admin.cursor().execute('DROP DATABASE '+database+' WITH (FORCE)')
        admin.close()


def issue(client):
    response = client.post('/api/srs/practice/attempt', json={'question_id':701})
    assert response.status_code == 200, response.json
    return response.json['attempt_token']


def start(client, token):
    return client.post('/api/g076/nonmap/steps/start', json={'flow':'practice','attempt_token':token})


def play(client, token, cursor, move):
    return client.post('/api/g076/nonmap/steps', json={
        'flow':'practice','attempt_token':token, 'step_index':cursor['step_index'],
        'step_nonce':cursor['step_nonce'], 'move':{'x':move[0],'y':move[1]}})


@pytest.mark.parametrize('correct', [True,False])
def test_product_route_review_srs_curriculum_once(product, correct):
    runtime, client, connect, state = product
    token = issue(client)
    assert issue(client) == token
    initial = start(client, token).json
    assert initial['content'] == '(;SZ[5]PL[B]AB[ee])'
    first = play(client, token, initial, (0,0)).json
    assert first['status']=='CONTINUE' and first['opponent_reply']==[1,1]
    assert start(client, token).json['previous_steps']==[{'player_move':[0,0],'opponent_reply':[1,1]}]
    with connect() as conn: assert conn.execute('SELECT COUNT(*) FROM review_log').fetchone()[0]==0
    last = (2,2) if correct else (3,0)
    terminal = play(client, token, first, last)
    assert terminal.status_code==200, terminal.json
    assert terminal.json['status']==('CORRECT' if correct else 'INCORRECT')
    assert terminal.json['settlement']['xp_awarded']==0
    assert play(client, token, first, last).json['duplicate'] is True
    assert play(client, token, first, (3,1)).status_code==409
    recovered = start(client, issue(client)).json
    assert recovered['status']==terminal.json['status'] and len(recovered['previous_steps'])==2
    assert client.post('/api/srs/practice/answer',json={'attempt_token':token,'moves':[]}).status_code==409
    with connect() as conn:
        reviews = conn.execute('SELECT * FROM review_log').fetchall()
        card = conn.execute('SELECT * FROM srs_cards').fetchone()
        assert len(reviews)==1 and reviews[0]['grade']==(5 if correct else 0)
        assert reviews[0]['source_context'].startswith('practice:v1:')
        assert reviews[0]['submission_payload_hash']
        assert card['repetitions']==int(correct) and card['progress_credited']==0
        assert conn.execute('SELECT xp FROM users WHERE id=101').fetchone()[0]==37
    summary=client.get('/api/curriculum/summary')
    assert summary.status_code==200, summary.json
    assert summary.json['cardsCount']==1 and summary.json['units'][0]['practiced']==1
    assert summary.json['units'][0]['chapterBossDefeated']==0


@pytest.mark.parametrize('flag', FLAGS)
def test_each_activation_gate_fails_closed(product, monkeypatch, flag):
    _,client,_,_=product
    token=issue(client)
    monkeypatch.delenv(flag)
    assert client.get('/api/g076/practice/steps/capability').json['enabled'] is False
    assert start(client,token).status_code==503


def test_auth_rights_identity_revision_and_foreign_flow(product):
    runtime,client,connect,state=product
    token=issue(client)
    assert runtime.app.test_client().post('/api/g076/nonmap/steps/start',json={'flow':'practice','attempt_token':token}).status_code==401
    other=runtime.app.test_client()
    with other.session_transaction() as session: session['user_id']=102
    assert start(other,token).status_code==409
    state.update(premium=False,free=False)
    with connect() as conn: conn.execute("UPDATE users SET plan='free' WHERE id=101")
    assert start(client,token).status_code==403
    state.update(premium=True,free=True)
    with connect() as conn: conn.execute("UPDATE users SET plan='premium' WHERE id=101")
    assert client.post('/api/g076/nonmap/steps/start',json={'flow':'daily','attempt_token':token}).status_code==503
    state['question']['content']+=' '
    assert start(client,token).status_code==409
    assert client.post('/api/srs/practice/attempt',json={'question_id':701}).status_code==409
    state['question']=copy.deepcopy(Q)
    with connect() as conn:
        conn.execute("UPDATE puzzle_identity_registry SET identity_status='RETIRED', retired_at='2026-10-23'")
    assert start(client,token).status_code==503


def test_rollback_after_real_writer_and_safe_retry(product, monkeypatch):
    runtime,client,connect,state=product
    token=issue(client); ready=start(client,token).json
    original=runtime.apply_srs_scheduling
    def broken(*a,**kw):
        original(*a,**kw)
        raise RuntimeError('failure after schedule write')
    monkeypatch.setattr(runtime,'apply_srs_scheduling',broken)
    assert play(client,token,ready,(3,0)).status_code==503
    with connect() as conn:
        for table in ('review_log','srs_cards','g076_nonmap_events'):
            assert conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
    monkeypatch.setattr(runtime,'apply_srs_scheduling',original)
    assert play(client,token,ready,(3,0)).json['status']=='INCORRECT'


def test_quota_unsupported_csrf_and_schema_hold(product, monkeypatch):
    _,client,connect,state=product
    token=issue(client); ready=start(client,token).json
    state.update(premium=False,quota={'error':'daily_limit'})
    with connect() as conn: conn.execute("UPDATE users SET plan='free' WHERE id=101")
    assert play(client,token,ready,(3,0)).status_code==429
    assert start(client,token).json['step_index']==0
    state.update(premium=True,quota=None)
    with connect() as conn: conn.execute("UPDATE users SET plan='premium' WHERE id=101")
    assert client.post('/api/srs/practice/attempt',json={'question_id':701},headers={'Origin':'https://evil.invalid'}).status_code==403
    state['question']['accepted_moves']=[{'x':0,'y':0}]
    assert start(client,token).status_code==422
    state['question'].pop('accepted_moves')
    with connect() as conn: conn.execute('DROP TABLE g076_nonmap_events')
    assert play(client,token,ready,(3,0)).status_code==503


def test_migration_requires_separate_explicit_gate():
    conn=sqlite3.connect(':memory:')
    with pytest.raises(RuntimeError,match='explicit Practice migration approval'):
        upgrade(conn,environ={})
    assert not conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()


@pytest.mark.parametrize('same_move',[True,False])
def test_product_concurrent_terminal_requests(product, same_move):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    runtime,client,connect,state=product
    token=issue(client); ready=start(client,token).json
    first=play(client,token,ready,(0,0)).json
    barrier=threading.Barrier(2)
    def submit(move):
        local=runtime.app.test_client()
        with local.session_transaction() as session: session['user_id']=101
        barrier.wait(timeout=10)
        response=play(local,token,first,move)
        return response.status_code,response.json
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(submit,[(2,2),(2,2) if same_move else (3,0)]))
    assert sorted(code for code,_ in results)==([200,200] if same_move else [200,409])
    if same_move: assert sorted(value['duplicate'] for _,value in results)==[False,True]
    with connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM review_log').fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM srs_cards').fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM g076_nonmap_events').fetchone()[0]==2


def test_expired_and_old_signed_attempts_cannot_create_parallel_probe(product):
    from practice_answer_authority import issue_practice_attempt
    runtime,client,connect,state=product
    token=issue(client)
    with connect() as conn:
        identity=runtime._practice_identity_for_write(conn,701)
    def independent(now=None):
        return issue_practice_attempt(runtime.app.secret_key,user_id=101,question=state['question'],
            source_record_uuid=identity,question_context=runtime._map_battle_question_context(state['question']),now=now)
    assert start(client,independent()).status_code==409
    assert start(client,independent(1)).status_code==409
    with connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM g076_nonmap_sessions').fetchone()[0]==0


def test_next_server_day_allows_bounded_new_practice_and_rejects_stale_cursor(product, monkeypatch):
    import g076_practice_product
    _,client,connect,state=product
    first_token=issue(client); initial=start(client,first_token).json
    assert play(client,first_token,initial,(3,0)).json['status']=='INCORRECT'
    assert issue(client)==first_token
    monkeypatch.setattr(g076_practice_product,'_slot_day',lambda:'2099-01-01')
    second_token=issue(client)
    assert second_token!=first_token
    assert start(client,first_token).status_code==409
    assert start(client,second_token).json['step_index']==0


def test_disabled_legacy_route_uses_same_writer_without_new_policy(product, monkeypatch):
    runtime,client,connect,state=product
    monkeypatch.delenv('G076_PRACTICE_STEPS_ENABLED')
    token=issue(client)
    moves=[{'x':0,'y':0},{'x':2,'y':2}]
    response=client.post('/api/srs/practice/answer',json={'attempt_token':token,'moves':moves})
    assert response.status_code==200, response.json
    assert response.json['result']=='CORRECT'
    assert client.post('/api/srs/practice/answer',json={'attempt_token':token,'moves':moves}).json['duplicate']
    with connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM review_log').fetchone()[0]==1
        assert conn.execute('SELECT repetitions FROM srs_cards').fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM g076_nonmap_events').fetchone()[0]==0


def test_actual_index_chrome_clicks_marks_xp_and_reload(product, tmp_path):
    import subprocess
    import threading
    from werkzeug.serving import make_server
    runtime,client,connect,state=product
    probe=connect()
    is_sqlite=isinstance(probe,sqlite3.Connection)
    probe.close()
    if not is_sqlite:
        pytest.skip('UI acceptance runs once on SQLite; PG actual routes tested separately')
    server=make_server('127.0.0.1',0,runtime.app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    serializer=runtime.app.session_interface.get_signing_serializer(runtime.app)
    env={**os.environ,'G076_SECOND_COOKIE':serializer.dumps({'user_id':102})}
    try:
        run=subprocess.run(['node',str(ROOT/'tests/e2e/g076_practice_real_index.mjs'),
            'http://127.0.0.1:'+str(server.server_port),serializer.dumps({'user_id':101}),str(tmp_path)],
            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=75,env=env)
        (tmp_path/'browser-stdout.txt').write_text(run.stdout,encoding='utf-8')
        (tmp_path/'browser-stderr.txt').write_text(run.stderr,encoding='utf-8')
        assert run.returncode==0,run.stdout+'\n'+run.stderr
        with connect() as conn:
            assert conn.execute('SELECT COUNT(*) FROM review_log').fetchone()[0]==2
            assert conn.execute('SELECT SUM(repetitions) FROM srs_cards').fetchone()[0]==1
            assert conn.execute('SELECT SUM(xp) FROM users').fetchone()[0]==74
    finally:
        server.shutdown();thread.join(timeout=5);server.server_close()


def test_deleted_account_session_is_not_step_authority(product):
    _,client,connect,state=product
    token=issue(client)
    with connect() as conn: conn.execute('DELETE FROM users WHERE id=101')
    assert start(client,token).status_code==401
    assert client.post('/api/srs/practice/attempt',json={'question_id':701}).status_code==401


def test_settlement_borrows_only_one_connection_and_rechecks_real_entitlement(product, monkeypatch):
    runtime,client,connect,state=product
    token=issue(client); cursor=start(client,token).json
    calls=[]
    def counted():
        calls.append(True)
        return connect()
    monkeypatch.setattr(runtime,'get_db',counted)
    monkeypatch.setattr(runtime,'is_premium',lambda *a: (_ for _ in ()).throw(AssertionError('outside transaction entitlement read')))
    assert play(client,token,cursor,(3,0)).status_code==200
    assert len(calls)==1
    with connect() as conn:
        conn.execute("UPDATE users SET plan='premium',premium_until='2000-01-01' WHERE id=101")
    state['free']=False
    assert start(client,token).status_code==403


def test_prior_legacy_settlement_cannot_schedule_again(product, monkeypatch):
    _,client,connect,state=product
    token=issue(client)
    monkeypatch.delenv('G076_PRACTICE_STEPS_ENABLED')
    saved=client.post('/api/srs/practice/answer',json={
        'attempt_token':token,'moves':[{'x':0,'y':0},{'x':2,'y':2}]})
    assert saved.status_code==200
    monkeypatch.setenv('G076_PRACTICE_STEPS_ENABLED','true')
    cursor=start(client,token).json
    first=play(client,token,cursor,(0,0)).json
    terminal=play(client,token,first,(2,2))
    assert terminal.status_code==503
    assert terminal.json['error']=='practice_prior_settlement_requires_reconciliation'
    with connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM review_log').fetchone()[0]==1
        assert conn.execute('SELECT repetitions FROM srs_cards').fetchone()[0]==1
