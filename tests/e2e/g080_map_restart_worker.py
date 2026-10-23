"""G080 fixture-only restart / disconnect worker. PG_DSN set by disposable pytest.
No production DSN or users; accepts user/submission identity from argv.
"""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import app
from flask import session
uid=int(sys.argv[1]); settlement=json.loads(sys.argv[2]); mode=sys.argv[3]
if mode == 'crash':
    def crash(*args,**kwargs):
        os._exit(97)  # abrupt worker death while core review is uncommitted
    app._map_battle_noncombat_progression=crash
elif mode == 'pg-disconnect':
    import psycopg2
    def disconnect(conn,*args,**kwargs):
        backend_pid=conn.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid']
        with psycopg2.connect(os.environ['DATABASE_URL']) as killer:
            with killer.cursor() as cur:
                cur.execute('SELECT pg_terminate_backend(%s)',(backend_pid,))
                assert cur.fetchone()[0] is True
        # The live transaction is invalidated; further DB I/O must fail.
        conn.execute('SELECT 1')
        raise AssertionError('terminated postgres backend survived')
    app._map_battle_noncombat_progression=disconnect
with app.app.test_request_context('/api/adventure/map-battles/v1/answers',method='POST'):
    session.update(user_id=uid,plan='premium')
    payload,status=app._run_map_battle_progression(uid,settlement)
print(json.dumps({'status':status,'payload':payload}),flush=True)
sys.exit(0 if status==200 else 3)
