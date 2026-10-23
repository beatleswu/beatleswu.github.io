"""Loopback-only P0-A runner, disposable SQLite; no app startup/Oracle."""
import datetime
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from flask import redirect, session, request
from g076_daily_fixture import make_daily_fixture
from g076_daily_capability import DAILY_FLAGS

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='g076-p0a-') as directory:
        app, state, connect, transaction, _ = make_daily_fixture(Path(directory)/'daily.sqlite')
        state['environ'].clear()
        day = (datetime.date.today()-datetime.timedelta(days=1)).isoformat()
        with transaction() as conn:
            conn.execute('INSERT INTO daily_challenge(challenge_date,question_id,set_by,note) VALUES(?,?,?,?)',
                         (day,301,'fixture','fixture historical row'))

        @app.get('/fixture/entry/<int:uid>')
        def entry(uid):
            session['user_id'] = uid
            state['environ'].clear()
            return redirect('/')

        @app.post('/fixture/mode/<bits>')
        def mode(bits):
            if len(bits) != 3 or set(bits)-set('01'):
                return '', 400
            state['environ'].update(dict(zip(DAILY_FLAGS, ('on' if b=='1' else 'off' for b in bits))))
            return {'ok':True}

        @app.get('/fixture/effects')
        def effects():
            with connect() as conn:
                return {table:[dict(r) for r in conn.execute('SELECT * FROM '+table)]
                        for table in ('user_stats','daily_challenge_log','badges_earned','review_log')}

        app.run(host='127.0.0.1', port=5081, threaded=True, use_reloader=False)
