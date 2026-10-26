"""G079 C: loopback server = REAL app.py + disposable PostgreSQL, then Chrome.

Usage (from the worktree root, with PG_DSN for a g079_c_* database exported by
the caller):  python -B tests/e2e/g079_rating_real_app_server.py <node script>

The official app module is imported unchanged. A few /fixture/* routes are
added to the in-memory app object by THIS test process only (loopback test
oracle: credentials of generated test users, DB effect readback, flag toggle,
display-orientation solution for the synthetic corpus). They are not product
routes and do not exist in app.py.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
os.chdir(ROOT)

import g079_rating_real_app_boot as boot  # noqa: E402

corpus = Path(tempfile.mkdtemp(prefix='g079-c-chrome-corpus-')) / 'questions.json'
app = boot.boot(corpus, rating='on', privacy='off')
USERS = {name: boot.seed_user(app, name) for name in ('g079chrome_a', 'g079chrome_b', 'g079chrome_c')}

from flask import jsonify, request  # noqa: E402

flask_app = app.app


def _loopback():
    if request.remote_addr not in ('127.0.0.1', '::1'):
        return jsonify(error='loopback_only'), 403
    return None


@flask_app.get('/fixture/credentials/<name>')
def fixture_credentials(name):
    deny = _loopback()
    if deny:
        return deny
    if name not in USERS:
        return jsonify(error='unknown'), 404
    uid, password = USERS[name]
    return jsonify(uid=uid, username=name, password=password)


@flask_app.get('/fixture/effects')
def fixture_effects():
    return _loopback() or jsonify(boot.effects(app, request.args.get('sid')))


@flask_app.post('/fixture/flags')
def fixture_flags():
    deny = _loopback()
    if deny:
        return deny
    body = request.get_json()
    os.environ[boot.RATING_FLAG] = body['rating']
    os.environ[boot.PRIVACY_FLAG] = body.get('privacy', 'off')
    return jsonify(ok=True)


@flask_app.get('/fixture/solution/<sid>')
def fixture_solution(sid):
    """Test oracle: correct line of the CURRENT question in display orientation."""
    deny = _loopback()
    if deny:
        return deny
    import re
    from sgf_point_transform import transform_sgf
    with app.get_db() as conn:
        row = conn.execute('SELECT current_question_id FROM rating_test_sessions WHERE id=?', (sid,)).fetchone()
    q = next(p for p in app._RT_POOL if p['id'] == row['current_question_id'])
    sgf = transform_sgf(q['content'], app._rt_transform_idx(sid, q['id']))
    return jsonify(question_id=q['id'], moves=[dict(x=ord(x) - 97, y=ord(y) - 97)
                   for x, y in re.findall(r';B\[([a-z])([a-z])\]', sgf)])


def main():
    from werkzeug.serving import make_server
    server = make_server('127.0.0.1', 0, flask_app, threaded=True)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print('[g079-server] real app.py on 127.0.0.1:%d (disposable PG %s)' % (port, os.environ.get('G079_PG_DATABASE')), flush=True)
    env = dict(os.environ, G079_BASE='http://127.0.0.1:%d' % port)
    for key in ('PG_DSN', 'DATABASE_URL'):
        env.pop(key, None)  # the browser driver never sees database credentials
    try:
        code = subprocess.call(['node', sys.argv[1]], env=env, cwd=str(ROOT))
    finally:
        server.shutdown()
    print('[g079-server] node exit', code, flush=True)
    sys.exit(code)


if __name__ == '__main__':
    main()
