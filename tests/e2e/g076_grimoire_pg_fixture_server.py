"""Loopback-only Grimoire prototype: real PG16, Flask auth sessions and WGo.
The HTTP fixture is disposable and MUST NOT be used as an official app route.
"""
from pathlib import Path
import sys
import socket
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
from flask import Flask, jsonify, send_file, session, redirect
from test_g076_grimoire_pg_live import case
from g076_grimoire_adapter import create_blueprint

CASE=case.__wrapped__()
SVC,CLIENT,TABLES,STATE,CONNECT,SCHEMA=next(CASE)
app=Flask('g076_grimoire_pg_disposable',root_path=str(ROOT))
app.secret_key='disposable-browser-pg-sandbox-only-not-production'
app.register_blueprint(create_blueprint(SVC))

@app.get('/fixture/entry/<int:user>')
def entry(user):
    if user not in (101,202):return 'unknown user',403
    session['user_id']=user
    return redirect('/fixture/player')

@app.get('/fixture/player')
def player():
    if session.get('user_id') not in (101,202):return 'login first',401
    return send_file(ROOT/'tests/e2e/g076_grimoire_pg_player.html')

@app.get('/wgo/wgo.min.js')
def wgo():
    return send_file(ROOT/'wgo/wgo.min.js',mimetype='application/javascript')

@app.get('/fixture/token')
def token():
    uid=session.get('user_id')
    if uid not in (101,202):return jsonify(error='auth_required'),401
    try: return jsonify(attempt_token=SVC.issue(uid,question_id=701,scope='browser-pg-'+str(uid)))
    except Exception: return jsonify(error='issue_failed'),503

@app.get('/fixture/effects')
def effects():
    if session.get('user_id') not in (101,202):return jsonify(error='auth_required'),401
    tables=TABLES()
    return jsonify({name:len(rows) for name,rows in tables.items()})

if __name__=='__main__':
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',5083))==0:
            raise RuntimeError('port5083_occupied')
    try:
        app.run(host='127.0.0.1',port=5083,threaded=True,use_reloader=False)
    finally:
        try:next(CASE)
        except StopIteration:pass
