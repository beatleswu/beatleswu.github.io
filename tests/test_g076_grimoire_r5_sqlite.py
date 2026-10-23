"""Stdlib runnable real SQLite regressions; no Flask/PG/application bootstrap.

Exact function AST extraction permits execution without unavailable Flask and
itsdangerous. This proves settlement SQL/formulas, NOT full imported HTTP flow.
Run: <python> tests/test_g076_grimoire_r5_sqlite.py
"""
import ast
import concurrent.futures
from contextlib import contextmanager
import datetime
import hashlib
import itertools
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def exact(filename, names, env):
    tree = ast.parse((ROOT / filename).read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    assert {n.name for n in nodes} == set(names)
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, 'exec'), env)


ENV = dict(json=json, sqlite3=sqlite3, hashlib=hashlib)
exact('g076_grimoire_adapter.py', ['GrimoireRejected'], ENV)
# Writer's function-local import loads grimoire_api. Supply only the exact
# purity function through a narrowly scoped import hook during invocation.
PURITY = {}
exact('grimoire_api.py', ['calc_node_purity', 'ensure_node_mastery_table'], PURITY)
import builtins


def legacy_import(name, *args, **kwargs):
    if name == 'grimoire_api':
        return SimpleNamespace(calc_node_purity=PURITY['calc_node_purity'])
    return builtins.__import__(name, *args, **kwargs)


ENV['__builtins__'] = {**vars(builtins), '__import__': legacy_import}
exact('g076_grimoire_adapter.py', ['_settle_node_mastery'], ENV)
exact('g076_grimoire_catalog.py', ['catalog_revision', '_ids', 'settle_catalog_and_cache'], ENV)
settle = ENV['settle_catalog_and_cache']
Rejected = ENV['GrimoireRejected']
NOW = datetime.datetime.now().isoformat()
QUESTIONS = [{'id': 701, 'grimoire_id': 5}, {'id': 702, 'grimoire_id': 5},
             {'id': 703, 'grimoire_id': 6}]


def connect(path):
    c = sqlite3.connect(path, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def schema(c):
    PURITY['ensure_node_mastery_table'](c)
    c.executescript('''CREATE TABLE grimoires(id INTEGER PRIMARY KEY,node_count INTEGER);
        CREATE TABLE g076_grimoire_catalog_members(
            question_id INTEGER PRIMARY KEY,grimoire_id INTEGER NOT NULL);
        INSERT INTO grimoires VALUES(5,2);
        INSERT INTO g076_grimoire_catalog_members VALUES(701,5),(702,5),(703,6);
    ''')
    c.execute('INSERT INTO daily_training_cache VALUES (?,?,?,?,?)',
              (101, NOW[:10], '[701,702]', '[]', NOW))
    c.commit()


def snapshot(c):
    result = {}
    for name in ('node_mastery', 'player_grimoire_progress', 'daily_training_cache'):
        result[name] = [dict(r) for r in c.execute('SELECT * FROM ' + name + ' ORDER BY 1,2')]
        for row in result[name]:
            for field in ('last_correct_at', 'last_studied_at', 'created_at'):
                if row.get(field):
                    row[field] = row[field][:10]
    return result


def seed(c, history, rank=0, node_count=2):
    c.execute('INSERT INTO node_mastery VALUES(101,701,?,9,?,?,0)',
              (PURITY['calc_node_purity'](history), json.dumps(history), '2026-10-01T00:00:00'))
    c.execute("INSERT INTO node_mastery VALUES(101,702,.9,2,'[true,true]',NULL,0)")
    # Different owner and different catalog must not contribute.
    c.execute("INSERT INTO node_mastery VALUES(202,701,1,2,'[]',NULL,0)")
    c.execute("INSERT INTO node_mastery VALUES(101,703,1,2,'[]',NULL,0)")
    c.execute('INSERT INTO player_grimoire_progress VALUES(101,5,?,.7,11,6,?)', (rank, NOW))
    c.execute('UPDATE grimoires SET node_count=?', (node_count,))
    c.commit()


def legacy(c, correct):
    @contextmanager
    def db():
        yield c
    env = dict(json=json, datetime=datetime, request=SimpleNamespace(
        get_json=lambda: {'questionId': 701, 'correct': correct}), session={'user_id': 101},
        jsonify=lambda value: value, get_sdb=db, get_ldb=db,
        ensure_node_mastery_table=lambda conn: None,
        load_questions=lambda: QUESTIONS, calc_node_purity=PURITY['calc_node_purity'])
    exact('grimoire_api.py', ['api_training_answer'], env)
    return env['api_training_answer']()


class SQLiteSettlement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='g076-r5-')
        self.path = Path(self.tmp.name) / 'candidate.sqlite'
        self.c = connect(self.path)
        schema(self.c)

    def tearDown(self):
        self.c.close()
        self.tmp.cleanup()

    def apply(self, correct=True, q=None):
        self.c.execute('BEGIN IMMEDIATE')
        try:
            if q is None:
                q = {**QUESTIONS[0], 'g076_catalog_revision': ENV['catalog_revision'](self.c)}
            result = settle(self.c, uid=101, question=q, correct=correct,
                            event_id='fixture-event', now=NOW)
            self.c.commit()
            return result
        except BaseException:
            self.c.rollback()
            raise

    def test_exact_legacy_parity_all_histories_ranks_denominators(self):
        # 63 histories * 2 verdicts * 5 ranks * 4 denominators = 2520 cases.
        count = 0
        for length in range(6):
            for history in itertools.product((False, True), repeat=length):
                for correct, rank, denominator in itertools.product((False, True), range(5), (0,1,2,8)):
                    with self.subTest(history=history, correct=correct, rank=rank, denominator=denominator):
                        a, b = connect(':memory:'), connect(':memory:')
                        try:
                            for c in (a, b):
                                schema(c)
                                seed(c, list(history), rank, denominator)
                            result = legacy(a, correct)
                            b.execute('BEGIN IMMEDIATE')
                            settle(b, uid=101, question={**QUESTIONS[0],
                                   'g076_catalog_revision': ENV['catalog_revision'](b)}, correct=correct,
                                   event_id='parity', now=NOW)
                            b.commit()
                            self.assertEqual(snapshot(a), snapshot(b))
                            self.assertAlmostEqual(snapshot(b)['player_grimoire_progress'][0]['purity'],
                                                   result['grimoire_purity'], places=4)
                            count += 1
                        finally:
                            a.close()
                            b.close()
        self.assertEqual(count, 2520)

    def test_cache_wrong_answer_and_distinct_attempts_append_once(self):
        self.apply(False)
        self.apply(True)
        self.assertEqual(json.loads(self.c.execute('SELECT completed_ids FROM daily_training_cache').fetchone()[0]), [701])
        self.assertEqual(self.c.execute('SELECT attempt_count FROM node_mastery').fetchone()[0], 2)

    def test_unanswered_nodes_denominator_and_first_rank(self):
        self.apply()
        row = self.c.execute('SELECT * FROM player_grimoire_progress').fetchone()
        self.assertEqual((row['purity'], row['rank'], row['total_attempts'], row['correct_count']), (.15,0,1,1))

    def test_cache_absent_other_date_and_nonmember(self):
        for change in ('DELETE FROM daily_training_cache',
                       "UPDATE daily_training_cache SET date='2000-01-01'",
                       "UPDATE daily_training_cache SET question_ids='[702]'"):
            with self.subTest(change=change):
                self.c.execute('DELETE FROM daily_training_cache')
                self.c.execute('INSERT INTO daily_training_cache VALUES (?,?,?,?,?)',
                               (101,NOW[:10],'[701]','[]',NOW))
                self.c.execute(change)
                self.c.commit()
                self.apply()
                self.assertTrue(all(r[0] == '[]' for r in self.c.execute('SELECT completed_ids FROM daily_training_cache')))

    def test_missing_local_catalog_fails_closed(self):
        for table in ('grimoires','g076_grimoire_catalog_members'):
            with self.subTest(table=table):
                self.c.execute('ALTER TABLE ' + table + ' RENAME TO hidden')
                self.c.commit()
                before = snapshot(self.c)
                with self.assertRaisesRegex(Rejected, 'same_database_catalog_required'):
                    self.apply()
                self.assertEqual(snapshot(self.c), before)
                self.c.execute('ALTER TABLE hidden RENAME TO ' + table)
                self.c.commit()

    def test_catalog_projection_incomplete(self):
        self.c.execute('DELETE FROM g076_grimoire_catalog_members WHERE question_id=701')
        self.c.commit()
        with self.assertRaisesRegex(Rejected, 'catalog_projection_incomplete'):
            self.apply()
        self.assertEqual(snapshot(self.c)['node_mastery'], [])

    def test_malformed_cache_rolls_back(self):
        for value in ('bad', '{}', '[true]', '["701"]', '[0]'):
            with self.subTest(value=value):
                self.c.execute('UPDATE daily_training_cache SET completed_ids=?', (value,))
                self.c.commit()
                with self.assertRaisesRegex(Rejected, 'invalid_daily_cache'):
                    self.apply()
                self.assertEqual(snapshot(self.c)['node_mastery'], [])

    def test_post_catalog_and_post_cache_writes_rollback(self):
        for table in ('player_grimoire_progress','daily_training_cache'):
            with self.subTest(table=table):
                before = snapshot(self.c)
                operation = 'INSERT' if table == 'player_grimoire_progress' else 'UPDATE'
                # AFTER trigger fires after the corresponding state write.
                self.c.execute('CREATE TRIGGER failure AFTER ' + operation + ' ON ' + table +
                               " BEGIN SELECT RAISE(ABORT,'after state write'); END")
                self.c.commit()
                with self.assertRaises(sqlite3.IntegrityError):
                    self.apply()
                self.assertEqual(snapshot(self.c), before)
                self.c.execute('DROP TRIGGER failure')
                self.c.commit()

    def test_commit_failure_rolls_back_all_three_states(self):
        self.c.execute('PRAGMA foreign_keys=ON')
        self.c.executescript('''CREATE TABLE parent(id INTEGER PRIMARY KEY);
            CREATE TABLE deferred(id INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED);
            CREATE TRIGGER failure AFTER UPDATE ON daily_training_cache
            BEGIN INSERT INTO deferred VALUES(99); END;''')
        before = snapshot(self.c)
        with self.assertRaises(sqlite3.IntegrityError):
            self.apply()
        self.assertEqual(snapshot(self.c), before)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM deferred').fetchone()[0], 0)

    def test_concurrent_distinct_settlements_no_lost_updates(self):
        def run(i):
            c = connect(self.path)
            try:
                c.execute('BEGIN IMMEDIATE')
                settle(c,uid=101,question={**QUESTIONS[0],
                       'g076_catalog_revision': ENV['catalog_revision'](c)},
                       correct=True,event_id=str(i),now=NOW)
                c.commit()
            finally:
                c.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(run, range(8)))
        self.assertEqual(self.c.execute('SELECT attempt_count FROM node_mastery').fetchone()[0], 8)
        row = self.c.execute('SELECT * FROM player_grimoire_progress').fetchone()
        self.assertEqual((row['total_attempts'], row['correct_count'], row['rank']), (8,8,1))
        self.assertEqual(json.loads(self.c.execute('SELECT completed_ids FROM daily_training_cache').fetchone()[0]), [701])

    def test_catalog_revision_bound_to_question(self):
        q = {**QUESTIONS[0], 'g076_catalog_revision': ENV['catalog_revision'](self.c)}
        self.c.execute('UPDATE grimoires SET node_count=9')
        self.c.commit()
        before = snapshot(self.c)
        for candidate in (q, QUESTIONS[0]):
            with self.assertRaisesRegex(Rejected, 'catalog_projection_revision_changed'):
                self.apply(q=candidate)
            self.assertEqual(snapshot(self.c), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
