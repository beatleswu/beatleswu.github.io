"""Loopback-only Flask/SQLite fixture for the candidate Rating seam.
Never imports app or connects to production. Synthetic accounts/questions only.
"""
import os
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ['SHADOW_JUDGING_ENABLED']='0'
from flask import request
from g076_rating_fixture import make_rating_fixture

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='g076-rating-') as directory:
        app,state,connect,services=make_rating_fixture(Path(directory)/'rating.sqlite')

        @app.post('/fixture/clock')
        def clock():
            state['now']+=float(request.json['seconds'])
            return {'now':state['now']}

        @app.post('/fixture/gate/<value>')
        def gate(value):
            if value=='hold':
                state['environ']['G076_RATING_STEPS_ENABLED']='unknown'
            elif value=='on':
                state['environ']['G076_RATING_STEPS_ENABLED']='on'
            else:
                return {},400
            return {'ok':True}

        @app.get('/fixture/effects')
        def effects():
            with connect() as conn:
                return {'responses':[dict(r) for r in conn.execute('SELECT * FROM rating_test_responses')]}

        app.run(host='127.0.0.1',port=15083,threaded=True,use_reloader=False)
