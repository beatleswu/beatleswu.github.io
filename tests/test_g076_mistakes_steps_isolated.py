"""B1 isolated Mistakes real canonical SGF, SQLite SRS and exactly-once proof.
This deliberately does NOT claim Product ReviewService is wired to this adapter.
"""
from contextlib import contextmanager
import datetime
import sqlite3
import json
from pathlib import Path
import concurrent.futures

import pytest
from flask import Flask,session

from g076_mistakes_product import MistakesServices,create_blueprint,mode
from map_battle_runtime import question_revision_for
from srs_scheduling_core import apply_srs_scheduling,ProgressCreditPolicy

ROOT=Path(__file__).resolve().parents[1]
SECRET='G076-MISTAKES-ISOLATED-ONLY-SECRET-20261023'
TODAY=datetime.date.today().isoformat()

@pytest.fixture
def fx(tmp_path):
    path=tmp_path/'mistakes.sqlite'
    q={'id':701,'content':'(;GM[1]SZ[5]PL[B]AB[ee];B[aa];W[bb];B[cc])'}
    flags={'G076_MISTAKES_STEPS_ENABLED':'on'}
    state={'q':q,'deny':False,'fail':False}
    def connect():
        c=sqlite3.connect(path,timeout=10)
        c.row_factory=sqlite3.Row
        c.create_function('GREATEST',2,max)
        return c
    with connect() as c:
        c.executescript((ROOT/'migrations/g076_nonmap_steps_PROPOSED.sql').read_text().replace("flow IN ('practice','daily')","flow IN ('practice','daily','mistakes')"))
        c.executescript((ROOT/'migrations/g076_mistakes_steps_PROPOSED.sql').read_text())
        c.executescript('''
        CREATE TABLE mistake_log (user_id INTEGER,question_id INTEGER,correct_after INTEGER DEFAULT 0,
          wrong_count INTEGER DEFAULT 1,PRIMARY KEY(user_id,question_id));
        CREATE TABLE receipts (id TEXT PRIMARY KEY,user_id INTEGER,correct INTEGER);
        CREATE TABLE srs_cards (user_id INTEGER,question_id INTEGER,ease_factor REAL,
          interval INTEGER,repetitions INTEGER,due_date TEXT,last_grade INTEGER,
          updated_at TEXT,progress_credited INTEGER,PRIMARY KEY(user_id,question_id));
        INSERT INTO mistake_log(user_id,question_id) VALUES(101,701),(202,701);
        ''')
    @contextmanager
    def transaction():
        c=connect()
        try:
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:c.close()
    def admit(conn,uid,question):
        if state['deny']:return ''
        return 'fixture-rights-'+str(uid)
    def settle(conn,ctx,canonical,outcome,event_id):
        correct=int(outcome.result=='CORRECT')
        conn.execute('INSERT INTO receipts VALUES(?,?,?)',(event_id,ctx.uid,correct))
        if correct:
            conn.execute('UPDATE mistake_log SET correct_after=correct_after+1 WHERE user_id=? AND question_id=?',
                         (ctx.uid,ctx.question['id']))
        srs=apply_srs_scheduling(conn,user_id=ctx.uid,question_id=ctx.question['id'],
            grade=outcome.authoritative_grade,now=TODAY,progress_credit_policy=ProgressCreditPolicy.NEVER)
        if state['fail']:raise RuntimeError('rollback after srs and corrected')
        return {'submission_id':event_id,'srs':{name:getattr(srs,name) for name in ('ease_factor','interval','repetitions','due_date')},'xp_awarded':0}
    services=MistakesServices(
        transaction=transaction,question=lambda c,qid:q if qid==701 else None,
        identity=lambda c,qid:'fixture-uuid-701',
        context=lambda question:{'board_size':5,'player_color':'B',
            'transform_id':'identity','transform_version':'fixture-v1',
            'question_revision':question_revision_for(question)},
        admit=admit,settle=settle)
    app=Flask('g076_mistakes_disposable');app.secret_key=SECRET;app.testing=True
    app.register_blueprint(create_blueprint(secret=SECRET,environ=flags,services=services))
    def client(uid):
        c=app.test_client()
        with c.session_transaction() as s:s['user_id']=uid
        return c
    def rows(table):
        with connect() as c:
            return [dict(r) for r in c.execute('SELECT * FROM '+table)]
    yield client,rows,flags,state,connect

def request(c,route,body):
    return c.post('/api/g076/mistakes'+route,json=body)

def admit(c):
    response=request(c,'/attempt',{'question_id':701})
    assert response.status_code==200,response.json
    token=response.json['attempt_token']
    begin=request(c,'/steps/start',{'flow':'mistakes','attempt_token':token})
    assert begin.status_code==200,begin.json
    return token,begin.json

def step(c,token,cursor,xy=(0,0),**overrides):
    return request(c,'/steps',{'flow':'mistakes','attempt_token':token,
        'step_index':cursor['step_index'],'step_nonce':cursor['step_nonce'],
        'move':{'x':xy[0],'y':xy[1]},**overrides})

def test_b1_true_authority_two_step_correct_and_durable_replay(fx):
    client,rows,_,_,_=fx
    c=client(101)
    token,start=admit(c)
    assert start['board_only'] and 'B[aa]' not in start['content']
    first=step(c,token,start).json
    assert first['status']=='CONTINUE' and first['opponent_reply']==[1,1]
    assert rows('receipts')==[]
    last=step(c,token,first,(2,2))
    assert last.status_code==200,last.json
    assert last.json['status']=='CORRECT'
    saved=rows('receipts')
    assert len(saved)==1 and saved[0]['correct']==1
    assert step(c,token,first,(2,2)).json['duplicate']
    assert rows('receipts')==saved
    assert rows('mistake_log')[0]['correct_after']==1
    assert rows('srs_cards')[0]['progress_credited']==0
    assert last.json['settlement']['xp_awarded']==0

def test_b1_wrong_and_client_grade_spoof_refused(fx):
    client,rows,_,_,_=fx
    c=client(101)
    token,cursor=admit(c)
    for field in ('correct','grade','reward','user_id'):
        assert step(c,token,cursor,**{field:True}).status_code==400
    bad=step(c,token,cursor,(3,3))
    assert bad.status_code==200,bad.json
    assert bad.json['status']=='INCORRECT'
    assert len(rows('receipts'))==1
    assert rows('mistake_log')[0]['correct_after']==0
    assert rows('srs_cards')[0]['progress_credited']==0

def test_b1_owner_rights_nonce_and_rollback(fx):
    client,rows,flags,state,_=fx
    c=client(101);other=client(202)
    token,cursor=admit(c)
    assert request(other,'/steps/start',{'flow':'mistakes','attempt_token':token}).status_code>=400
    assert step(c,token,{**cursor,'step_nonce':'0'*64}).status_code>=400
    state['fail']=True
    with pytest.raises(RuntimeError,match='rollback after srs'):
        step(c,token,cursor,(3,3))
    assert rows('receipts')==[] and rows('srs_cards')==[]
    state['fail']=False
    good=step(c,token,cursor,(3,3))
    assert good.status_code==200,good.json

def test_b1_mode_matrix_off_on_hold(fx):
    client,rows,flags,_,_=fx
    c=client(101)
    assert mode({})=='legacy'
    assert c.get('/api/g076/mistakes/capability').json['mode']=='steps'
    for value in ('unknown','bogus','2'):
        flags['G076_MISTAKES_STEPS_ENABLED']=value
        assert c.get('/api/g076/mistakes/capability').status_code==503
        assert request(c,'/attempt',{'question_id':701}).status_code==503
    flags['G076_MISTAKES_STEPS_ENABLED']='off'
    assert c.get('/api/g076/mistakes/capability').json['mode']=='legacy'
    assert request(c,'/attempt',{'question_id':701}).status_code==503
    assert rows('receipts')==[]
