"""16 opt-in native PostgreSQL checks; skips are NOT PostgreSQL evidence.

Only G MASTER supplies PG_DSN in-process. Never load/copy a credential file.
No app import, pool, SQLite connection, SQL emulation, or FOR UPDATE removal.
"""
import ast
from concurrent.futures import ThreadPoolExecutor
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
import g076_rating_fixture as original_fixture
from g076_rating_steps import RatingRejected, SCHEMA, advance, create_rating_blueprint, open_current
from g078_rating_integration import RatingAppServices

CONTAINER = 'g076-r5-isolated-pg-20261023'
LABEL = 'go-odyssey.g076.r5=isolated-disposable'
TABLES = ('users', 'user_stats', 'daily_training_queue', 'rating_test_sessions',
          'rating_test_responses', 'mistake_log', 'g076_rating_attempts',
          'g076_rating_events', 'adventure_zone_unlocks')


def fixture_runtime():
    """Reuse original fixture namespace/math AST without constructing SQLite.

    The fixture's namespace factory supplies the bounded two-question corpus and
    selection/rank stubs; original_functions supplies app judge/writer/math AST.
    Neither the legacy route nor its SharedConnection callback is invoked here.
    """
    tree = ast.parse((ROOT / 'tests/g076_rating_fixture.py').read_text(encoding='utf-8'))
    factory = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                   and n.name == 'make_rating_fixture')
    services = next(n for n in factory.body if isinstance(n, ast.ClassDef) and n.name == 'Services')
    namespace = next(n for n in services.body if isinstance(n, ast.FunctionDef) and n.name == 'namespace')
    pool_assignment = next(n for n in factory.body if isinstance(n, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == 'pool' for t in n.targets))
    env = dict(vars(original_fixture), code=original_fixture.original_functions())
    exec(compile(ast.fix_missing_locations(ast.Module(body=[pool_assignment, namespace],
                                                    type_ignores=[])), 'g076:pg-namespace', 'exec'), env)
    runtime = env['namespace'](None, None, None)
    ddl = next(n.args[0].value for n in ast.walk(factory)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == 'executescript')
    # INTEGER flags stay INTEGER: original writer stores 0/1, not PG booleans.
    return runtime, re.sub(r'\bREAL\b', 'DOUBLE PRECISION', ddl)


class NativePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.environ.get('PG_DSN')
        if not dsn:
            raise unittest.SkipTest('PG_DSN missing: native PG NOT_EXECUTED (not PASS)')
        if (os.environ.get('G078_PG_CONTAINER') != CONTAINER or
                os.environ.get('G078_PG_ISOLATION_MARKER') != LABEL):
            raise RuntimeError('Native PG refused: explicit isolation markers missing/mismatched')
        import psycopg2
        from psycopg2.extensions import parse_dsn
        from psycopg2.extras import DictCursor
        from db import PostgresConnectionWrapper
        try:
            params = parse_dsn(dsn)
        except Exception:
            raise RuntimeError('Native PG refused: invalid DSN (details withheld)') from None
        if (params.get('host') != '127.0.0.1' or params.get('port') != '55476'
                or not params.get('dbname') or params.get('service') or params.get('hostaddr')):
            raise RuntimeError('Native PG refused: DSN must explicitly target isolated loopback port')
        # Check only non-secret Docker metadata. Do not inspect Env or fixture JSON.
        try:
            check = subprocess.run(['docker', 'inspect', '--format',
                '{{json .State.Running}}|{{index .Config.Labels "go-odyssey.g076.r5"}}|{{json .NetworkSettings.Ports}}',
                CONTAINER], capture_output=True, text=True, timeout=15, check=True)
            running, label, ports = check.stdout.strip().split('|')
            bindings = json.loads(ports).get('5432/tcp')
            valid = (running == 'true' and label == 'isolated-disposable' and
                     bindings == [{'HostIp': '127.0.0.1', 'HostPort': '55476'}])
        except Exception:
            raise RuntimeError('Native PG refused: Docker isolation verification unavailable') from None
        if not valid:
            raise RuntimeError('Native PG refused: Docker isolation metadata mismatch')
        cls.pg = psycopg2
        cls.dict_cursor = DictCursor
        cls.wrapper = PostgresConnectionWrapper
        cls._dsn = dsn

    def raw_connection(self):
        try:
            return self.pg.connect(self._dsn, cursor_factory=self.dict_cursor,
                                   connect_timeout=5, options='-c statement_timeout=10000 -c lock_timeout=5000')
        except Exception:
            raise RuntimeError('Isolated PG connection failed (connection details withheld)') from None

    def setUp(self):
        self.schema = 'g078_b2_' + uuid.uuid4().hex
        self.connections = []
        self.sql = []
        self.inject_fk = False
        admin = self.raw_connection()
        try:
            admin.autocommit = True
            with admin.cursor() as c:
                c.execute('CREATE SCHEMA ' + self.schema)
        finally:
            admin.close()
        self.addCleanup(self.drop_schema)
        self.runtime, ddl = fixture_runtime()
        conn = self.connect()
        try:
            for sql in SCHEMA:
                conn.execute(sql)
            conn.execute(ddl)
            # Real commit-time failure, no simulated commit exception.
            conn.execute('CREATE TABLE commit_parent(id INTEGER PRIMARY KEY)')
            conn.execute('CREATE TABLE commit_child(id INTEGER REFERENCES commit_parent(id) '
                         'DEFERRABLE INITIALLY DEFERRED)')
            conn.commit()
        finally:
            conn.close()
        self.runtime['get_db'] = self.connect
        self.services = RatingAppServices(self.runtime)

    def drop_schema(self):
        if not re.fullmatch(r'g078_b2_[0-9a-f]{32}', self.schema):
            raise AssertionError('unsafe cleanup schema')
        admin = self.raw_connection()
        try:
            admin.autocommit = True
            with admin.cursor() as c:
                c.execute('DROP SCHEMA ' + self.schema + ' CASCADE')
        finally:
            admin.close()

    def connect(self):
        raw = self.raw_connection()
        try:
            with raw.cursor() as c:
                c.execute('SET search_path TO ' + self.schema)
            raw.commit()
        except BaseException:
            raw.close()
            raise
        owner = self

        class ObservedConnection(owner.wrapper):
            # Observe real wrapper calls; SQL and native transaction behavior unchanged.
            commits = rollbacks = closes = 0

            def execute(self, sql, parameters=None):
                owner.sql.append(sql)
                return super().execute(sql, parameters)

            def commit(self):
                self.commits += 1
                if owner.inject_fk:
                    self.execute('INSERT INTO commit_child VALUES(999)')
                return super().commit()

            def rollback(self):
                self.rollbacks += 1
                return super().rollback()

            def close(self):
                self.closes += 1
                return super().close()

        conn = ObservedConnection(raw)
        self.connections.append(conn)
        return conn

    def query(self, sql, args=()):
        conn = self.connect()
        try:
            cursor = conn.execute(sql, args)
            rows = cursor.fetchall() if cursor.description else []
            conn.commit()
            return rows
        finally:
            conn.close()

    def snapshot(self):
        return {t: sorted((tuple(row) for row in self.query('SELECT * FROM ' + t)), key=repr)
                for t in TABLES + ('commit_child',)}

    def start(self, uid=7, trigger='manual'):
        with self.services.transaction() as conn:
            return open_current(conn, self.services.start(conn, uid, trigger), 1000.)

    def body(self, opened, action='give_up'):
        step = opened['question']['step']
        return dict(session_id=opened['session_id'], attempt_id=step['attempt_id'],
                    nonce=step['nonce'], action=action)

    def step(self, body, uid=7, now=1001.):
        with self.services.transaction() as conn:
            return advance(conn, self.services, self.services.resolve(conn, body['session_id'], uid), body, now)

    def moves(self, opened):
        from sgf_point_transform import transform_sgf
        sgf = transform_sgf(self.runtime['_RT_POOL'][0]['content'], opened['question']['transform_index'])
        return [dict(x=ord(x)-97, y=ord(y)-97) for x, y in re.findall(r';B\[([a-z])([a-z])\]', sgf)]

    def test_01_real_pg_wrapper_and_locks(self):
        self.assertGreaterEqual(int(self.query('SHOW server_version_num')[0][0]), 120000)
        self.start()
        locks = [s for s in self.sql if 'FOR UPDATE' in s]
        self.assertIn('FROM users', locks[0])
        self.assertIn('FROM rating_test_sessions', locks[-1])
        self.assertIsInstance(self.connections[-1], self.wrapper)
        self.assertEqual((self.connections[-1].commits, self.connections[-1].rollbacks,
                          self.connections[-1].closes), (1, 0, 1))

    def test_02_original_authenticated_prior(self):
        self.query('UPDATE users SET elo_rating=2100 WHERE id=7 RETURNING id')
        opened = self.start()
        self.assertEqual((opened['cur_rating'], opened['rating_se']), (2100., 160.))

    def test_03_original_anonymous_prior_and_capability(self):
        opened = self.start(None)
        self.assertEqual((opened['cur_rating'], opened['rating_se']), (1500., 400.))
        self.assertFalse(self.step(self.body(opened), None)['result']['correct'])
        self.assertEqual(self.query('SELECT COUNT(*) FROM mistake_log')[0][0], 0)
        self.assertEqual(self.query('SELECT elo_rating FROM users ORDER BY id')[0][0], 1500.)

    def test_04_two_accounts_owner_rejection(self):
        a, b = self.start(7), self.start(8)
        before = self.snapshot()
        with self.assertRaisesRegex(RatingRejected, 'session_owner_mismatch'):
            self.step(self.body(a), 8)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.step(self.body(b), 8)['result']['correct'])
        self.assertEqual(self.query('SELECT round FROM rating_test_sessions WHERE id=?', (a['session_id'],))[0][0], 0)

    def test_05_missing_authenticated_account(self):
        before = self.snapshot()
        with self.assertRaisesRegex(RatingRejected, 'authentication_required'):
            self.start(99)
        self.assertEqual(before, self.snapshot())

    def test_06_forfeit_original_elo_se(self):
        result = self.step(self.body(self.start()))['result']
        rating, se = self.runtime['_rt_estimate']([dict(correct=False, q_rating=1500)], 1500., 160.)
        self.assertEqual((result['cur_rating'], result['rating_se']), (rating, se))
        self.assertEqual(tuple(self.query('SELECT correct,ability_after FROM rating_test_responses')[0]), (0, rating))

    def test_07_timeout_original_forfeit(self):
        opened = self.start()
        body = self.body(opened, 'timeout')
        before = self.snapshot()
        with self.assertRaisesRegex(RatingRejected, 'rating_timeout_not_due'):
            self.step(body)
        self.assertEqual(before, self.snapshot())
        result = self.step(body, now=opened['question']['step']['deadline'])
        self.assertFalse(result['result']['correct'])
        state = json.loads(self.query('SELECT state_json FROM g076_rating_attempts WHERE id=?', (body['attempt_id'],))[0][0])
        self.assertEqual(state['forfeit_reason'], 'timeout')
        self.assertEqual(state['moves'], [])

    def test_08_original_question_judge_and_math(self):
        opened = self.start()
        moves = self.moves(opened)
        body = self.body(opened, 'move') | dict(move=moves[0])
        continued = self.step(body)
        self.assertEqual(continued['status'], 'CONTINUE')
        self.assertEqual(self.query('SELECT COUNT(*) FROM rating_test_responses')[0][0], 0)
        body.update(nonce=continued['nonce'], move=moves[1])
        result = self.step(body)['result']
        self.assertTrue(result['correct'])
        self.assertEqual((result['cur_rating'], result['rating_se']),
                         self.runtime['_rt_estimate']([dict(correct=True, q_rating=1500)], 1500., 160.))

    def test_09_original_judge_required(self):
        opened = self.start()
        before = self.snapshot()
        self.runtime['_rt_server_verify'] = lambda *args: None
        with self.assertRaisesRegex(RatingRejected, 'question_unverifiable'):
            with self.services.transaction() as conn:
                self.services.settle(conn, self.services.resolve(conn, opened['session_id'], 7), [], 20)
        self.assertEqual(before, self.snapshot())

    def test_10_current_question_revision_authority(self):
        opened = self.start()
        before = self.snapshot()
        with self.assertRaisesRegex(RatingRejected, 'rating_question_revision_changed'):
            with self.services.transaction() as conn:
                ctx = self.services.resolve(conn, opened['session_id'], 7)
                self.runtime['_RT_POOL'][0]['content'] += ' '
                self.services.settle_forfeit(conn, ctx, [], 20, 'give_up')
        self.assertEqual(before, self.snapshot())

    def test_11_exact_receipt_once_and_conflict(self):
        body = self.body(self.start())
        first = self.step(body)
        before = self.snapshot()
        self.assertEqual(first, self.step(body))
        self.assertEqual(before, self.snapshot())
        with self.assertRaisesRegex(RatingRejected, 'rating_replay_conflict'):
            self.step(body | dict(action='timeout'))
        receipt = self.query('SELECT request_hash,response_json FROM g076_rating_events')[0]
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(receipt['request_hash'], digest)
        self.assertEqual(json.loads(receipt['response_json']), first)
        self.assertEqual(self.query('SELECT COUNT(*) FROM rating_test_responses')[0][0], 1)

    def test_12_concurrent_replay_native_session_lock(self):
        body = self.body(self.start())
        barrier = threading.Barrier(2)

        def worker():
            barrier.wait(timeout=10)
            return self.step(dict(body))

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker) for _ in range(2)]
            results = [f.result(timeout=20) for f in futures]
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.query('SELECT COUNT(*) FROM rating_test_responses')[0][0], 1)
        self.assertEqual(self.query('SELECT COUNT(*) FROM g076_rating_events')[0][0], 1)
        self.assertEqual(self.query('SELECT wrong_count FROM mistake_log')[0][0], 1)

    def test_13_deferred_fk_commit_failure_full_rollback(self):
        opened = self.start(trigger='placement')
        current = self.step(self.body(opened))['result']
        self.query('INSERT INTO daily_training_queue VALUES(7,?) RETURNING user_id',
                   (datetime.date.today().isoformat(),))
        body = self.body(current)
        before = self.snapshot()
        self.inject_fk = True
        try:
            with self.assertRaises(self.pg.errors.ForeignKeyViolation):
                self.step(body)
            failed = self.connections[-1]
            self.assertEqual((failed.commits, failed.rollbacks, failed.closes), (1, 1, 1))
        finally:
            self.inject_fk = False
        self.assertEqual(before, self.snapshot())
        self.assertTrue(self.step(body)['result']['finished'])

    def test_14_placement_account_queue_unlock_atomic(self):
        opened = self.start(trigger='placement')
        self.query('INSERT INTO daily_training_queue VALUES(7,?),(8,?) RETURNING user_id',
                   (datetime.date.today().isoformat(),) * 2)
        current = self.step(self.body(opened))['result']
        final = self.step(self.body(current))['result']
        self.assertTrue(final['finished'])
        users = self.query('SELECT id,elo_rating,elo_provisional FROM users ORDER BY id')
        self.assertEqual(tuple(users[0]), (7, final['cur_rating'], 1))
        self.assertEqual(users[1]['elo_rating'], 1500.)
        self.assertEqual([r[0] for r in self.query('SELECT user_id FROM daily_training_queue')], [8])
        self.assertEqual(self.query('SELECT user_id,source FROM adventure_zone_unlocks')[0]['source'], 'placement_test')
        self.assertEqual(self.query('SELECT COUNT(*) FROM rating_test_responses')[0][0], 2)

    def test_15_missing_schema_readiness_hold_no_ddl(self):
        self.assertTrue(self.services.ready())
        self.query('DROP TABLE g076_rating_events')
        self.sql.clear()
        self.assertFalse(self.services.ready())
        client = self.client('off')
        response = client.get('/api/g076/rating/capability')
        self.assertEqual((response.status_code, response.json['mode']), (503, 'hold'))
        self.assertFalse(any(re.search(r'\b(CREATE|ALTER)\b', s, re.I) for s in self.sql))

    def client(self, privacy):
        from flask import Flask
        app = Flask(__name__)
        app.secret_key = 'disposable-g078-pg-tests-only'
        app.config['TESTING'] = True
        app.register_blueprint(create_rating_blueprint(self.services,
            {'G076_RATING_STEPS_ENABLED': 'on', 'G076_ANSWER_PRIVACY_ENFORCED': privacy}, clock=lambda:1000.))
        return app.test_client()

    def test_16_rating_on_independent_global_privacy(self):
        for privacy in ('off', 'on'):
            with self.subTest(privacy=privacy):
                client = self.client(privacy)
                self.assertEqual(client.get('/api/g076/rating/capability').json['mode'], 'steps')
                with client.session_transaction() as session:
                    session['user_id'] = 7
                response = client.post('/api/g076/rating/start', json={})
                self.assertEqual(response.status_code, 200)
                q = response.json['question']
                self.assertTrue(q['board_only'])
                self.assertNotIn(';B[', q['content'])
                self.assertFalse({'token', 'accepted_moves', 'katago_best_move'} & q.keys())
                self.assertEqual(response.headers['Cache-Control'], 'no-store')


if __name__ == '__main__':
    unittest.main(verbosity=2)
