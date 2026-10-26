"""New adapter checks only. SQLite is NOT authentic PostgreSQL evidence.

No G077 acceptance suite rerun. No app import/startup DB or production access.
"""
import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from g076_rating_fixture import make_rating_fixture
from g076_rating_steps import RatingRejected, advance, open_current
from g078_rating_integration import RatingAppServices


class AdapterTests(unittest.TestCase):
    def setUp(self):
        # Do not create untracked output under the product worktree.
        # The A020 source-scope gate inspects git status while other test
        # shards execute; disposable SQLite belongs in system temp.
        self.tmp = tempfile.TemporaryDirectory(prefix="g080-g078-rating-")
        _, self.state, self.connect, seam = make_rating_fixture(Path(self.tmp.name)/'fixture.sqlite', core_only=True)
        self.runtime = seam.namespace(None, None)
        self.connections = []
        self.sql = []
        owner = self

        class Connection:
            def __init__(self):
                self.raw = owner.connect()
                self.commits = self.rollbacks = self.closes = 0
            def execute(self, sql, args=()):
                owner.sql.append(sql)
                return self.raw.execute(sql.replace(' FOR UPDATE', ''), args)
            def commit(self):
                self.commits += 1
                if owner.state['fail_commit']:
                    raise RuntimeError('injected commit failure')
                self.raw.commit()
            def rollback(self):
                self.rollbacks += 1
                self.raw.rollback()
            def close(self):
                self.closes += 1
                self.raw.close()

        def get_db():
            conn = Connection()
            self.connections.append(conn)
            return conn
        self.runtime['get_db'] = get_db
        self.services = RatingAppServices(self.runtime)

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, uid=7, trigger='manual'):
        with self.services.transaction() as conn:
            return open_current(conn, self.services.start(conn, uid, trigger), 1000.)

    def snapshot(self):
        with self.connect() as conn:
            tables = ('users', 'rating_test_sessions', 'rating_test_responses', 'mistake_log',
                      'g076_rating_attempts', 'g076_rating_events', 'adventure_zone_unlocks')
            return {t: [tuple(row) for row in conn.execute('SELECT * FROM '+t+' ORDER BY 1')]
                    for t in tables}

    def body(self, opened):
        step = opened['question']['step']
        return dict(session_id=opened['session_id'], attempt_id=step['attempt_id'],
                    nonce=step['nonce'], action='give_up')

    def step(self, body, uid=7):
        with self.services.transaction() as conn:
            ctx = self.services.resolve(conn, body['session_id'], uid)
            return advance(conn, self.services, ctx, body, 1001.)

    def test_canonical_account_prior_and_private_projection(self):
        with self.connect() as conn:
            conn.execute('UPDATE users SET elo_rating=2100 WHERE id=7')
        opened = self.start()
        self.assertEqual(opened['cur_rating'], 2100.)
        self.assertEqual(opened['rating_se'], 160.)
        self.assertTrue(opened['question']['board_only'])
        self.assertNotIn(';B[', opened['question']['content'])
        self.assertNotIn('token', opened['question'])
        locks = [s for s in self.sql if 'FOR UPDATE' in s]
        self.assertIn('FROM users', locks[0])
        self.assertIn('FROM rating_test_sessions', locks[-1])
        conn = self.connections[-1]
        self.assertEqual((conn.commits, conn.rollbacks, conn.closes), (1, 0, 1))

    def test_missing_account_never_fabricated(self):
        before = self.snapshot()
        with self.assertRaisesRegex(RatingRejected, 'authentication_required'):
            self.start(99)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.connections[-1].rollbacks, 1)

    def test_two_users_and_anonymous_owner_rules(self):
        a, b, anon = self.start(7), self.start(8), self.start(None)
        self.assertEqual(len({a['session_id'], b['session_id'], anon['session_id']}), 3)
        with self.assertRaisesRegex(RatingRejected, 'session_owner_mismatch'):
            self.step(self.body(a), 8)
        self.assertFalse(self.step(self.body(b), 8)['result']['correct'])
        self.assertFalse(self.step(self.body(anon), None)['result']['correct'])

    def test_adapter_forfeit_uses_writer_and_one_receipt(self):
        opened = self.start()
        body = self.body(opened)
        first = self.step(body)
        self.assertEqual(first, self.step(body))
        with self.connect() as conn:
            response = conn.execute('SELECT * FROM rating_test_responses').fetchone()
            self.assertEqual(response['correct'], 0)
            expected, se = self.runtime['_rt_estimate'](
                [dict(correct=False, q_rating=1500)], 1500., 160.)
            self.assertEqual(first['result']['cur_rating'], expected)
            self.assertEqual(first['result']['rating_se'], se)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM g076_rating_events').fetchone()[0], 1)

    def test_commit_failure_rolls_back_writer_and_nonce(self):
        opened = self.start()
        before = self.snapshot()
        self.state['fail_commit'] = True
        with self.assertRaisesRegex(RuntimeError, 'commit failure'):
            self.step(self.body(opened))
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.connections[-1].rollbacks, 1)
        self.assertEqual(self.connections[-1].closes, 1)
        self.state['fail_commit'] = False
        self.assertFalse(self.step(self.body(opened))['result']['correct'])

    def test_original_judge_is_required_before_writer(self):
        opened = self.start()
        with self.services.transaction() as conn:
            ctx = self.services.resolve(conn, opened['session_id'], 7)
            self.runtime['_rt_server_verify'] = lambda *args: None
            with self.assertRaisesRegex(RatingRejected, 'question_unverifiable'):
                self.services.settle(conn, ctx, [], 20)
        self.assertEqual(self.snapshot()['rating_test_responses'], [])

    def test_normal_steps_reach_original_judge_and_writer(self):
        from sgf_point_transform import transform_sgf
        opened = self.start()
        step = opened['question']['step']
        sgf = transform_sgf('(;SZ[5];B[aa];W[bb];B[cc])', opened['question']['transform_index'])
        import re
        moves = [dict(x=ord(x)-97, y=ord(y)-97) for x, y in re.findall(r';B\[([a-z])([a-z])\]', sgf)]
        body = self.body(opened) | dict(action='move', move=moves[0])
        continued = self.step(body)
        self.assertEqual(continued['status'], 'CONTINUE')
        self.assertEqual(self.snapshot()['rating_test_responses'], [])
        body |= dict(nonce=continued['nonce'], move=moves[1])
        final = self.step(body)
        self.assertTrue(final['result']['correct'])
        self.assertEqual(final, self.step(body))
        self.assertEqual(len(self.snapshot()['rating_test_responses']), 1)

    def test_current_corpus_revision_rejected_before_effects(self):
        opened = self.start()
        with self.services.transaction() as conn:
            ctx = self.services.resolve(conn, opened['session_id'], 7)
            self.runtime['_RT_POOL'][0]['content'] += ' '
            with self.assertRaisesRegex(RatingRejected, 'rating_question_revision_changed'):
                self.services.settle(conn, ctx, [], 20)
        self.assertEqual(self.snapshot()['rating_test_responses'], [])

    def test_placement_updates_account_queue_unlock_atomically(self):
        opened = self.start(trigger='placement')
        self.step(self.body(opened))
        with self.services.transaction() as conn:
            current = open_current(conn, self.services.resolve(conn, opened['session_id'], 7), 1001.)
        before = self.snapshot()
        self.state['fail_commit'] = True
        with self.assertRaises(RuntimeError):
            self.step(self.body(current))
        self.assertEqual(before, self.snapshot())
        self.state['fail_commit'] = False
        final = self.step(self.body(current))
        self.assertTrue(final['result']['finished'])
        snap = self.snapshot()
        self.assertTrue(snap['adventure_zone_unlocks'])
        self.assertEqual(snap['users'][0][1], final['result']['cur_rating'])

    def test_missing_schema_is_hold_without_ddl(self):
        self.assertTrue(self.services.ready())
        with self.connect() as conn:
            conn.execute('DROP TABLE g076_rating_events')
        self.assertFalse(self.services.ready())
        self.assertFalse(any('CREATE' in sql.upper() for sql in self.sql))

    def test_app_registers_adapter_and_asset_before_main(self):
        tree = ast.parse((ROOT/'app.py').read_text(encoding='utf-8-sig'))
        source = (ROOT/'app.py').read_text(encoding='utf-8-sig')
        self.assertLess(source.index('_g078_rating_services ='), source.rindex("if __name__ == '__main__':"))
        self.assertTrue(any(isinstance(n, ast.FunctionDef) and n.name == 'serve_g076_rating_step_client_js' for n in tree.body))


if __name__ == '__main__':
    unittest.main(verbosity=2)
