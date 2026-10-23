"""R5 real PG16 local disposable validation, NEVER against an existing database.

Requires .g076-r5-disposable-pg.json created by G MASTER with explicit isolated
Docker target, then connects only to that localhost port and exact db name.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import uuid

import psycopg2
import pytest
from flask import Flask

from g076_grimoire_pg_service import PgGrimoireSteps
from g076_grimoire_adapter import GrimoireRejected, create_blueprint

CONFIG=Path(__file__).resolve().parents[1]/'.g076-r5-disposable-pg.json'

@pytest.fixture
def case():
    data=json.loads(CONFIG.read_text(encoding='utf-8-sig'))
    assert data['container']=='g076-r5-isolated-pg-20261023'
    assert data['port']==55476
    assert data['database']=='go_odyssey_g076_r5_disposable'
    dsn=data['dsn']
    def connect():
        c=psycopg2.connect(dsn)
        with c.cursor() as x:
            x.execute('SELECT current_database(),inet_server_port()')
            assert x.fetchone()==(data['database'],5432)
        c.rollback()
        return c
    schema='g076_test_'+uuid.uuid4().hex[:16]
    c=connect()
    try:
        c.autocommit=True
        with c.cursor() as x:
            x.execute('CREATE SCHEMA '+schema)
            x.execute('''
                CREATE TABLE '''+schema+'''.grimoires(id BIGINT PRIMARY KEY,node_count INTEGER NOT NULL);
                CREATE TABLE '''+schema+'''.g076_grimoire_catalog_members(
                    question_id BIGINT PRIMARY KEY,grimoire_id BIGINT NOT NULL);
                CREATE TABLE '''+schema+'''.g076_grimoire_settlement_owners(user_id BIGINT PRIMARY KEY);
                CREATE TABLE '''+schema+'''.g076_grimoire_attempts(
                    token TEXT PRIMARY KEY,user_id BIGINT NOT NULL,scope TEXT NOT NULL,
                    question_id BIGINT NOT NULL,binding TEXT NOT NULL,expires BIGINT NOT NULL,
                    step_index INTEGER NOT NULL DEFAULT 0,history TEXT NOT NULL DEFAULT '[]',
                    state TEXT NOT NULL DEFAULT 'OPEN',UNIQUE(user_id,scope));
                CREATE TABLE '''+schema+'''.g076_grimoire_events(
                    token TEXT NOT NULL,step_index INTEGER NOT NULL,
                    request_hash TEXT NOT NULL,response TEXT NOT NULL,
                    PRIMARY KEY(token,step_index));
                CREATE TABLE '''+schema+'''.node_mastery(
                    user_id BIGINT,question_id BIGINT,purity DOUBLE PRECISION,
                    attempt_count INTEGER,last_5_history TEXT,last_correct_at TEXT,
                    is_contaminated INTEGER,PRIMARY KEY(user_id,question_id));
                CREATE TABLE '''+schema+'''.player_grimoire_progress(
                    user_id BIGINT,grimoire_id BIGINT,rank INTEGER,purity DOUBLE PRECISION,
                    total_attempts INTEGER,correct_count INTEGER,last_studied_at TEXT,
                    PRIMARY KEY(user_id,grimoire_id));
                CREATE TABLE '''+schema+'''.daily_training_cache(
                    user_id BIGINT,date TEXT,question_ids TEXT,completed_ids TEXT,
                    created_at TEXT,PRIMARY KEY(user_id,date));
            ''')
            x.execute('INSERT INTO '+schema+'.grimoires VALUES(5,1)')
            x.execute('INSERT INTO '+schema+'.g076_grimoire_catalog_members VALUES(701,5)')
            x.execute('INSERT INTO '+schema+'''.daily_training_cache VALUES
                (101,'2026-10-23','[701]','[]','fixture'),
                (202,'2026-10-23','[701]','[]','fixture')''')
    finally:
        c.close()
    state={'q':{'id':701,'grimoire_id':5,'content':'(;SZ[5]PL[B]AB[ee];B[aa])'},
           'now':1792713600,'deny':False}
    service=PgGrimoireSteps(connect=connect,schema=schema,
        load=lambda c,qid:state['q'],identity=lambda c,qid:'fixture-uuid-701',
        admit=lambda c,uid,q:not state['deny'],
        secret=b'isolated-pg-grimoire-secret-more-than-32-bytes',clock=lambda:state['now'],
        environ={'G076_ANSWER_PRIVACY_ENFORCED':'on','G076_GRIMOIRE_STEPS_ENABLED':'on'})
    with service._transaction(101) as c:
        state['q']['g076_catalog_revision']=service.catalog_revision(c)
    app=Flask(__name__);app.secret_key='isolated-test-session'
    app.register_blueprint(create_blueprint(service))
    def client(uid):
        cl=app.test_client()
        with cl.session_transaction() as s:s['user_id']=uid
        return cl
    def tables():
        with connect() as c:
            with c.cursor() as x:
                result={}
                for t in ['node_mastery','player_grimoire_progress',
                          'daily_training_cache','g076_grimoire_events']:
                    x.execute('SELECT * FROM '+schema+'.'+t+' ORDER BY 1,2')
                    result[t]=x.fetchall()
                return result
    try:
        yield service,client,tables,state,connect,schema
    finally:
        c=connect()
        try:
            c.autocommit=True
            with c.cursor() as x:x.execute('DROP SCHEMA '+schema+' CASCADE')
        finally:c.close()

def send(client,token,cursor=None,move=(0,0),extras=None):
    d={'attempt_token':token}
    if cursor is not None:
        d.update(step_index=cursor['step_index'],step_nonce=cursor['step_nonce'],
                 move={'x':move[0],'y':move[1]})
    d.update(extras or {})
    return client.post('/api/g076/grimoire/steps',json=d)

def test_pg_16_real_terminal_and_replay(case):
    service,make,tables,_,_,_=case
    token=service.issue(101,question_id=701,scope='daily-slot-1')
    client=make(101)
    start=send(client,token)
    assert start.status_code==200,start.json
    assert start.json['content']=='(;SZ[5]PL[B]AB[ee])'
    assert 'B[aa]' not in start.json['content']
    terminal=send(client,token,start.json,move=(0,0))
    assert terminal.status_code==200,terminal.json
    assert terminal.json['status']=='CORRECT'
    before=tables()
    for _ in range(3):
        response=send(client,token,start.json,move=(0,0))
        assert response.status_code==200,response.json
        assert response.json['duplicate'] is True
        assert tables()==before
    assert len(before['g076_grimoire_events'])==1
    assert before['node_mastery'][0][3]==1
    assert before['player_grimoire_progress'][0][4]==1
    assert json.loads(before['daily_training_cache'][0][3])==[701]
    assert send(make(202),token).status_code==409
    assert send(client,token,start.json,move=(1,1)).status_code==409

def test_pg_16_real_two_accounts_and_duplicate_concurrency(case):
    service,make,tables,_,_,_=case
    a=service.issue(101,question_id=701,scope='slot-A')
    b=service.issue(202,question_id=701,scope='slot-B')
    cur_a=send(make(101),a).json
    cur_b=send(make(202),b).json
    def run(i):
        uid,token,cursor=(101,a,cur_a) if i%2==0 else (202,b,cur_b)
        r=send(make(uid),token,cursor,move=(0,0))
        return r.status_code,r.json
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses=list(pool.map(run,range(8)))
    assert all(status==200 for status,_ in responses),responses
    assert sum(not p['duplicate'] for _,p in responses)==2
    allrows=tables()
    assert len(allrows['node_mastery'])==2
    assert len(allrows['g076_grimoire_events'])==2
    assert len(allrows['player_grimoire_progress'])==2
    assert [r[4] for r in allrows['player_grimoire_progress']]==[1,1]

def test_pg_16_real_bad_nonce_and_client_grade(case):
    service,make,tables,_,_,_=case
    token=service.issue(101,question_id=701,scope='slot-sabotage')
    start=send(make(101),token).json
    before=tables()
    for extra in [{'correct':True},{'grade':4},{'reward':1000},{'user_id':202}]:
        r=send(make(101),token,start,move=(0,0),extras=extra)
        assert r.status_code==400,r.json
        assert tables()==before
    forged=dict(start,step_nonce='0'*64)
    assert send(make(101),token,forged).status_code==403
    assert tables()==before

def test_pg_16_real_rollback_after_settlement_insert(case):
    service,make,tables,_,connect,schema=case
    token=service.issue(101,question_id=701,scope='slot-failing-node')
    cursor=send(make(101),token).json
    with connect() as c:
        with c.cursor() as x:
            x.execute("""CREATE FUNCTION """+schema+""".inject_failure() RETURNS trigger
                 LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'G076_PG_INJECTED'; END $$""")
            x.execute('CREATE TRIGGER fail_after_mastery AFTER INSERT ON '+schema+
                      '.node_mastery FOR EACH ROW EXECUTE FUNCTION '+schema+'.inject_failure()')
    before=tables()
    failed=send(make(101),token,cursor,move=(0,0))
    assert failed.status_code==503,failed.json
    assert tables()==before
    with connect() as c:
        with c.cursor() as x:x.execute('DROP TRIGGER fail_after_mastery ON '+schema+'.node_mastery')
    good=send(make(101),token,cursor,move=(0,0))
    assert good.status_code==200,good.json
    assert good.json['status']=='CORRECT'
    assert len(tables()['g076_grimoire_events'])==1

def test_pg_16_real_rollback_at_deferred_commit(case):
    service,make,tables,_,connect,schema=case
    token=service.issue(101,question_id=701,scope='slot-failing-commit')
    cursor=send(make(101),token).json
    with connect() as c:
        with c.cursor() as x:
            x.execute('CREATE TABLE '+schema+'.failure_parent(id INTEGER PRIMARY KEY)')
            x.execute('CREATE TABLE '+schema+'.failure_child(id INTEGER REFERENCES '+
                      schema+'.failure_parent(id) DEFERRABLE INITIALLY DEFERRED)')
            x.execute('CREATE FUNCTION '+schema+'''.inject_deferred() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN INSERT INTO '''+schema+'''.failure_child VALUES(99);RETURN NEW;END $$''')
            x.execute('CREATE TRIGGER fail_at_commit AFTER UPDATE ON '+schema+
                      '.daily_training_cache FOR EACH ROW EXECUTE FUNCTION '+schema+'.inject_deferred()')
    before=tables()
    failed=send(make(101),token,cursor,move=(0,0))
    assert failed.status_code==503,failed.json
    assert tables()==before
    with connect() as c:
        with c.cursor() as x:x.execute('DROP TRIGGER fail_at_commit ON '+schema+'.daily_training_cache')
    recovered=send(make(101),token,cursor,move=(0,0))
    assert recovered.status_code==200,recovered.json
    assert len(tables()['g076_grimoire_events'])==1

def test_pg_16_real_same_owner_distinct_tokens_serialized(case):
    service,make,tables,_,_,_=case
    tokens=[service.issue(101,question_id=701,scope='same-owner-'+str(i)) for i in range(3)]
    cursors=[send(make(101),token).json for token in tokens]
    def terminal(p):
        token,start=p
        return send(make(101),token,start,move=(0,0))
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses=list(pool.map(terminal,zip(tokens,cursors)))
    assert all(r.status_code==200 for r in responses),[(r.status_code,r.json) for r in responses]
    rows=tables()
    assert len(rows['g076_grimoire_events'])==3
    assert rows['node_mastery'][0][3]==3
    assert rows['player_grimoire_progress'][0][4]==3
    assert json.loads(rows['daily_training_cache'][0][3])==[701]

def test_pg_16_real_revision_and_rights_rechecked(case):
    service,make,tables,state,_,_=case
    token=service.issue(101,question_id=701,scope='owner-check')
    start=send(make(101),token).json
    before=tables()
    state['deny']=True
    bad=send(make(101),token,start,move=(0,0))
    assert bad.status_code>=400 and tables()==before
    state['deny']=False
    state['q']['question_revision']='tampered'
    bad=send(make(101),token,start,move=(0,0))
    assert bad.status_code>=400 and tables()==before
    state['q'].pop('question_revision')
    ok=send(make(101),token,start,move=(0,0))
    assert ok.status_code==200,ok.json
