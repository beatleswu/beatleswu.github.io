"""G079 B1 loopback fixture server: REAL app.py + REAL mistakes.html + disposable PG16.

Creates database g079_a_<hex> inside the disposable container
g076-r5-isolated-pg-20261023 (label verified), runs the real init_db, the
explicit Mistakes migration and the test-only identity bootstrap, seeds
synthetic users, and serves the official Flask app on 127.0.0.1 only.
Fixture-only routes under /__g079/ (loopback-guarded) sign in a synthetic
user, toggle the Mistakes flag, read back durable effects and shut down.
The database is dropped on shutdown. The DSN is never printed.
"""
import datetime
import json
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
os.chdir(ROOT)

from test_g079_mistakes_product_pg import PG, QUESTIONS, _bootstrap_identity, FLAG  # noqa: E402

PORT = int(os.environ.get('G079_BROWSER_PORT', '55491'))
OUT = Path(os.environ.get('G079_EVIDENCE_DIR', r'D:\g079-artifacts\a')) / 'chrome'
USERS = {9101: (7901, 7902), 9102: (7901, 7902), 9103: (7901,)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pg = PG()
    receipt = {'database': pg.name, 'port': PORT, 'host': '127.0.0.1', 'production_access': False}
    server = None
    try:
        os.environ.update(DATABASE_URL=pg.dsn, QUESTIONS_JSON_PATH=str(QUESTIONS),
                          SECRET_KEY='g079-a-browser-fixture-secret')
        os.environ[FLAG] = 'on'
        os.environ.pop('G076_ANSWER_PRIVACY_ENFORCED', None)
        import db
        db.DATABASE_URL = pg.dsn
        db._pool = None
        from migrations.sgf_admin_workbench_v1 import upgrade as workbench_upgrade
        with db.get_db() as conn:
            workbench_upgrade(conn)
            conn.commit()
        import app as product
        product.init_db()
        from migrations.g079_mistakes_steps_v1 import upgrade as mistakes_upgrade
        with db.get_db() as conn:
            mistakes_upgrade(conn, environ={'G079_MISTAKES_STEPS_MIGRATION_APPROVED': '1'})
            conn.commit()
        _bootstrap_identity(product, [q['id'] for q in json.loads(QUESTIONS.read_text(encoding='utf-8'))])
        with product.get_db() as conn:
            for uid, qids in USERS.items():
                conn.execute('INSERT INTO users(id,username,password_hash,plan,created_at) VALUES(?,?,?,?,?)',
                             (uid, f'g079-browser-{uid}', 'synthetic-not-login-capable', 'free',
                              datetime.datetime.now().isoformat()))
                conn.execute('INSERT INTO user_stats(user_id,go_rank,go_rank_initialized,tour_done) '
                             'VALUES(?,?,?,?)', (uid, '20k', 1, 1))
                for qid in qids:
                    conn.execute('INSERT INTO mistake_log(user_id,question_id,wrong_count,correct_after,'
                                 'first_wrong_at,last_wrong_at) VALUES(?,?,1,0,?,?)',
                                 (uid, qid, '2026-10-01T00:00:00', '2026-10-01T00:00:00'))
            conn.commit()

        from flask import abort, jsonify, redirect, request, session
        flask_app = product.app

        def loopback():
            if request.remote_addr != '127.0.0.1':
                abort(403)

        def login(uid):
            loopback()
            if uid not in USERS:
                abort(404)
            session.clear()
            session.update(user_id=uid, username=f'g079-browser-{uid}', plan='free', is_admin=False)
            return redirect('/mistakes')

        def flag(value):
            loopback()
            if value == 'on':
                os.environ[FLAG] = 'on'
            else:
                os.environ.pop(FLAG, None)
            return jsonify(flag=os.environ.get(FLAG))

        def effects(uid):
            loopback()
            with product.get_db() as conn:
                def one(sql):
                    row = conn.execute(sql, (uid,)).fetchone()
                    return dict(row) if row else None
                stats = one('SELECT xp,coins,total_correct,mistake_corrected,current_streak,combo_streak,'
                            'rank_level FROM user_stats WHERE user_id=?')
                value = {
                    'stats': stats,
                    'review_log': one('SELECT COUNT(*) AS n FROM review_log WHERE user_id=?')['n'],
                    'mistakes_reviews': one("SELECT COUNT(*) AS n FROM review_log WHERE user_id=? "
                                            "AND source_context='mistakes'")['n'],
                    'mistake_log': [dict(r) for r in conn.execute(
                        'SELECT question_id,wrong_count,correct_after FROM mistake_log WHERE user_id=? '
                        'ORDER BY question_id', (uid,)).fetchall()],
                    'srs_cards': [dict(r) for r in conn.execute(
                        'SELECT question_id,repetitions,progress_credited FROM srs_cards WHERE user_id=? '
                        'ORDER BY question_id', (uid,)).fetchall()],
                    'step_events': one('SELECT COUNT(*) AS n FROM g076_nonmap_events e JOIN '
                                       'g076_nonmap_sessions s ON s.id=e.session_id WHERE s.user_id=?')['n'],
                    'daily_quests': [dict(r) for r in conn.execute(
                        'SELECT quest_key,progress,completed FROM daily_quests WHERE user_id=? '
                        'ORDER BY quest_key', (uid,)).fetchall()],
                    'badges': [r['badge_id'] for r in conn.execute(
                        'SELECT badge_id FROM badges_earned WHERE user_id=? ORDER BY badge_id',
                        (uid,)).fetchall()],
                }
            return jsonify(value)

        def shutdown():
            loopback()
            threading.Thread(target=server.shutdown, daemon=True).start()
            return jsonify(ok=True)

        flask_app.add_url_rule('/__g079/login/<int:uid>', 'g079_login', login)
        flask_app.add_url_rule('/__g079/flag/<value>', 'g079_flag', flag, methods=['POST'])
        flask_app.add_url_rule('/__g079/effects/<int:uid>', 'g079_effects', effects)
        flask_app.add_url_rule('/__g079/shutdown', 'g079_shutdown', shutdown, methods=['POST'])
        from werkzeug.serving import make_server
        server = make_server('127.0.0.1', PORT, flask_app, threaded=True)
        print(json.dumps({'ready': True, 'port': PORT, 'database': pg.name}), flush=True)
        server.serve_forever()
    finally:
        pg.drop()
        receipt.update(pg.receipt)
        (OUT / 'server_receipt.json').write_text(json.dumps(receipt, indent=1, sort_keys=True),
                                                 encoding='utf-8')
        print(json.dumps({'stopped': True, 'dropped': pg.receipt.get('dropped')}), flush=True)


if __name__ == '__main__':
    main()
