"""Local-only fixture entrypoint; never imported by app.py."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from flask import session, redirect
from g076_daily_fixture import make_daily_fixture

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='g076-daily-fixture-') as directory:
        app, state, *_ = make_daily_fixture(Path(directory)/'daily.sqlite')
        @app.get('/fixture/entry/<int:uid>')
        def entry(uid):
            session['user_id'] = uid
            return redirect('/')
        @app.get('/fixture/white-entry')
        def white_entry():
            session['user_id'] = 9
            state['question']['content'] = '(;SZ[5]PL[W]AW[ee];W[aa];B[bb];W[cc])'
            return redirect('/')
        @app.get('/fixture/disabled-entry')
        def disabled_entry():
            session['user_id'] = 10
            state['environ'].clear()
            return redirect('/')
        app.run(host='0.0.0.0',port=5079,threaded=True,use_reloader=False)
