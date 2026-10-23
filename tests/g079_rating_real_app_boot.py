"""G079 C: boot the REAL app.py against a disposable PostgreSQL database.

Test-only helper (not a test module). It imports the official app.py module,
so the real auth/session system, the real _load_questions/_build_rt_pool
loader (pointed at a synthetic corpus file via QUESTIONS_JSON_PATH), the real
before_request guard and the installed g078 Rating blueprint all execute.

Isolation: PG_DSN must explicitly target the disposable container's loopback
port and Docker must report the isolation label; nothing else is accepted.
The Rating step ledger DDL (g076_rating_steps.SCHEMA, PROPOSED) is installed
here by the TEST harness, never by the application.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = 'g076-r5-isolated-pg-20261023'
LABEL_KEY, LABEL_VALUE = 'go-odyssey.g076.r5', 'isolated-disposable'
RATING_FLAG, PRIVACY_FLAG = 'G076_RATING_STEPS_ENABLED', 'G076_ANSWER_PRIVACY_ENFORCED'


def verify_isolated():
    """Reads PG_DSN itself so no frame ever holds it as an argument."""
    from psycopg2.extensions import parse_dsn
    params = parse_dsn(os.environ['PG_DSN'])
    if (params.get('host') != '127.0.0.1' or params.get('port') != '55476'
            or not str(params.get('dbname', '')).startswith('g079_c_')
            or params.get('service') or params.get('hostaddr')):
        raise RuntimeError('refused: DSN must name a g079_c_* database on the isolated loopback port')
    out = subprocess.run(['docker', 'inspect', '--format',
                          '{{json .State.Running}}|{{index .Config.Labels "%s"}}|{{json .NetworkSettings.Ports}}' % LABEL_KEY,
                          CONTAINER], capture_output=True, text=True, timeout=30, check=True).stdout.strip()
    running, label, ports = out.split('|')
    if not (running == 'true' and label == LABEL_VALUE and
            json.loads(ports).get('5432/tcp') == [{'HostIp': '127.0.0.1', 'HostPort': '55476'}]):
        raise RuntimeError('refused: Docker isolation metadata mismatch')
    return params['dbname']


def _point(i):
    return chr(97 + i % 5) + chr(97 + i // 5)


def synthetic_corpus():
    """Step-compatible 5x5 problems: B[aa] W[bb] B[cc] is the only correct line.

    Distinct setup stones keep content hashes unique (the pool deduplicates).
    Ranks 20k..10k keep every timer at 25 s. Two deliberately step-INELIGIBLE
    questions (duplicate player branch; alternative-answer policy) prove the
    server never hands them to a step session.
    """
    free = [i for i in range(25) if _point(i) not in ('aa', 'bb', 'cc', 'ab', 'ba')]
    ranks = ['20k', '18k', '16k', '15k', '14k', '13k', '12k', '11k', '10k']
    questions, n = [], 0
    for a in free:
        for b in free:
            if b <= a or n >= 60:
                continue
            n += 1
            questions.append(dict(
                id=920000 + n, content='(;GM[1]FF[4]SZ[5]PL[B]AB[%s]AW[%s];B[aa];W[bb];B[cc])' % (_point(a), _point(b)),
                source='g079-synthetic/q%d.sgf' % n, discipline='life_death', topic='life_death',
                stage='LV1', rank=ranks[n % len(ranks)], difficulty=ranks[n % len(ranks)],
                enabled=True, is_free=True, free=True))
    questions.append(dict(id=929001, content='(;GM[1]FF[4]SZ[5]PL[B]AB[ee](;B[aa];W[bb];B[cc])(;B[aa];W[cc];B[bb]))',
                          source='g079-synthetic/dup.sgf', discipline='life_death', topic='life_death',
                          stage='LV1', rank='12k', difficulty='12k', enabled=True))
    questions.append(dict(id=929002, content='(;GM[1]FF[4]SZ[5]PL[B]AB[ed];B[aa];W[bb];B[cc])',
                          source='g079-synthetic/alt.sgf', discipline='life_death', topic='life_death',
                          stage='LV1', rank='12k', difficulty='12k', enabled=True,
                          accepted_moves=[{'x': 4, 'y': 4}]))
    return questions


INELIGIBLE_IDS = frozenset({929001, 929002})


def boot(corpus_path, *, rating='off', privacy='off'):
    verify_isolated()
    Path(corpus_path).write_text(json.dumps(synthetic_corpus(), ensure_ascii=False), encoding='utf-8')
    os.environ['DATABASE_URL'] = os.environ['PG_DSN']
    os.environ.update(QUESTIONS_JSON_PATH=str(corpus_path),
                      SECRET_KEY='g079-c-disposable-real-app-test-secret')
    os.environ[RATING_FLAG], os.environ[PRIVACY_FLAG] = rating, privacy
    sys.path.insert(0, str(ROOT))
    import db
    from migrations.sgf_admin_workbench_v1 import upgrade
    with db.get_db() as conn:
        upgrade(conn)
        conn.commit()
    import app
    app.app.config.update(TESTING=True)
    app.init_db()
    from g076_rating_steps import SCHEMA
    with db.get_db() as conn:
        for sql in SCHEMA:
            conn.execute(sql)
        conn.commit()
    return app


def seed_user(app, username, *, elo=None):
    """Real users row + password hash; login then goes through /api/auth/login."""
    from werkzeug.security import generate_password_hash
    password = secrets.token_urlsafe(18)
    with app.get_db() as conn:
        uid = conn.execute(
            'INSERT INTO users(username,password_hash,is_admin,plan,created_at,email,email_verified,elo_rating)'
            " VALUES(?,?,0,'free','2026-10-23T00:00:00',?,1,?) RETURNING id",
            (username, generate_password_hash(password), username + '@g079.test', elo)).fetchone()[0]
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (uid,))
        conn.commit()
    return uid, password


def effects(app, sid=None):
    with app.get_db() as conn:
        where, args = ('WHERE session_id=?', (sid,)) if sid else ('', ())
        responses = [dict(r) for r in conn.execute(
            'SELECT session_id,user_id,question_id,round,correct,ability_before,ability_after '
            'FROM rating_test_responses ' + where + ' ORDER BY id', args).fetchall()]
        sessions = [dict(r) for r in conn.execute(
            'SELECT id,user_id,status,round,cur_rating,current_question_id FROM rating_test_sessions').fetchall()]
        users = [dict(r) for r in conn.execute(
            'SELECT id,elo_rating,elo_provisional FROM users ORDER BY id').fetchall()]
        events = conn.execute('SELECT COUNT(*) FROM g076_rating_events').fetchone()[0]
        unlocks = [dict(r) for r in conn.execute(
            'SELECT user_id,zone_key,source FROM adventure_zone_unlocks ORDER BY user_id,zone_key').fetchall()]
        mistakes = [dict(r) for r in conn.execute(
            'SELECT user_id,question_id,wrong_count FROM mistake_log ORDER BY user_id,question_id').fetchall()]
    return dict(responses=responses, sessions=sessions, users=users, events=events,
                unlocks=unlocks, mistakes=mistakes)
