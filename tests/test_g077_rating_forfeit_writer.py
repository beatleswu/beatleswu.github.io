"""Windows stdlib core acceptance; no Flask/PG/browser claims.

Uses actual ledger and AST-extracted original app helpers on disposable SQLite.
Run: python -B tests/test_g077_rating_forfeit_writer.py
"""
import ast
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from g076_rating_fixture import make_rating_fixture
from g076_rating_steps import RatingRejected, advance, mode, open_current


class ForfeitWriterTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'artifacts/g077-b2').mkdir(parents=True,exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT/'artifacts/g077-b2', prefix='core-')
        _, self.state, self.connect, self.services = make_rating_fixture(Path(self.tmp.name)/'test.sqlite',core_only=True)

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, uid=7, trigger='manual'):
        with self.services.transaction() as c:
            return open_current(c,self.services.start(c,uid,trigger),self.state['now'])

    def body(self, d, action='timeout', move=None):
        step=d['question']['step']
        b=dict(session_id=d['session_id'],attempt_id=step['attempt_id'],nonce=step['nonce'],action=action)
        if move is not None:
            b['move']=move
        return b

    def step(self, b, uid=7):
        with self.services.transaction() as c:
            ctx=self.services.resolve(c,b['session_id'],uid)
            return advance(c,self.services,ctx,b,self.state['now'])

    def resume(self, d, uid=7):
        with self.services.transaction() as c:
            return open_current(c,self.services.resolve(c,d['session_id'],uid),self.state['now'])

    def move(self, d, xy=(0,0)):
        from sgf_point_transform import transform_sgf
        sgf=transform_sgf('(;SZ[5];B['+''.join(chr(97+i) for i in xy)+'])',d['question']['transform_index'])
        coord=sgf.split('B[')[1][:2]
        return self.body(d,'move',dict(zip(('x','y'),(ord(i)-97 for i in coord))))

    def snapshot(self):
        with self.connect() as c:
            return {table:[dict(r) for r in c.execute('SELECT * FROM '+table)] for table in (
                'users','rating_test_sessions','rating_test_responses','mistake_log',
                'g076_rating_attempts','g076_rating_events','adventure_zone_unlocks','daily_training_queue')}

    def test_four_forfeits_two_accounts_original_elo_once(self):
        for uid in (7,8):
            for kind in ('timeout','partial_timeout','give_up','late_move'):
                with self.subTest(uid=uid,kind=kind):
                    d=self.start(uid)
                    if kind=='partial_timeout':
                        self.assertEqual(self.step(self.move(d),uid)['status'],'CONTINUE')
                        d=self.resume(d,uid)
                    if kind!='give_up':
                        self.state['now']=d['question']['step']['deadline']
                    action='give_up' if kind=='give_up' else 'move' if kind=='late_move' else 'timeout'
                    b=self.move(d) if action=='move' else self.body(d,action)
                    before=self.snapshot()
                    result=self.step(b,uid)
                    self.assertEqual(result['status'],'INCORRECT')
                    self.assertIs(result['result']['correct'],False)
                    self.assertLess(result['result']['cur_rating'],d['cur_rating'])
                    ns=self.services.namespace(None,uid)
                    expected,se=ns['_rt_estimate']([dict(correct=False,q_rating=1500)],1500.,160.)
                    self.assertEqual(result['result']['cur_rating'],expected)
                    self.assertEqual(result['result']['rating_se'],se)
                    after=self.snapshot()
                    self.assertEqual(len(after['rating_test_responses']),len(before['rating_test_responses'])+1)
                    self.assertEqual(after['rating_test_responses'][-1]['correct'],0)
                    # Timeout/give-up must not append any fake or late stone.
                    attempt=next(r for r in after['g076_rating_attempts'] if r['id']==b['attempt_id'])
                    stored=json.loads(attempt['state_json'])
                    self.assertEqual(stored['forfeit_reason'],'give_up' if kind=='give_up' else 'timeout')
                    self.assertEqual(len(stored['moves']),1 if kind=='partial_timeout' else 0)
                    self.assertEqual(len(result['played']),2 if kind=='partial_timeout' else 0)
                    self.assertEqual(self.step(b,uid),result)
                    self.assertEqual(self.snapshot(),after)
                    with self.assertRaises(RatingRejected):
                        self.step(dict(b,action='give_up' if action!='give_up' else 'timeout'),uid)
                    with self.assertRaises(RatingRejected):
                        self.step(b,8 if uid==7 else 7)
                    encoded=json.dumps(result)
                    self.assertNotIn(';B[',encoded)
                    self.assertNotIn(';W[',encoded)
                    self.assertNotIn('question_token',encoded)

    def test_placement_finalize_unlock_and_commit_rollback(self):
        for fail in ('fail_settle','fail_commit'):
            with self.subTest(fail=fail):
                d=self.start(trigger='placement')
                r=self.step(self.body(d,'give_up'))
                d=self.resume(d)
                with self.connect() as c:
                    import datetime
                    c.execute('INSERT INTO daily_training_queue VALUES(?,?)',(7,datetime.date.today().isoformat()))
                before=self.snapshot()
                b=self.body(d,'give_up')
                self.state[fail]=True
                with self.assertRaises(RuntimeError):
                    self.step(b)
                self.assertEqual(self.snapshot(),before)
                self.state[fail]=False
                r=self.step(b)
                self.assertTrue(r['result']['finished'])
                self.assertEqual(r['result']['start_zone_key'],'z1')
                after=self.snapshot()
                user=next(u for u in after['users'] if u['id']==7)
                self.assertEqual(user['elo_rating'],r['result']['cur_rating'])
                self.assertEqual(user['elo_provisional'],1)
                self.assertTrue(user['elo_updated_at'])
                self.assertFalse(after['daily_training_queue'])
                self.assertEqual(len(after['adventure_zone_unlocks']),1)
                self.assertEqual(after['adventure_zone_unlocks'][0]['source'],'placement_test')
                self.assertEqual(self.step(b),r)
                self.assertEqual(self.snapshot(),after)

    def test_missing_adapter_holds_and_early_timeout_does_not_write(self):
        d=self.start()
        before=self.snapshot()
        with self.assertRaisesRegex(RatingRejected,'rating_timeout_not_due'):
            self.step(self.body(d))
        self.assertEqual(self.snapshot(),before)
        self.services.settle_forfeit=None
        with self.assertRaisesRegex(RatingRejected,'rating_forfeit_transaction_not_integrated'):
            self.step(self.body(d,'give_up'))
        self.assertEqual(self.snapshot(),before)

    def test_concurrent_forfeit_replay_one_settlement(self):
        d=self.start()
        b=self.body(d,'give_up')
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda _:self.step(b),range(6)))
        self.assertTrue(all(r==results[0] for r in results))
        snap=self.snapshot()
        self.assertEqual(len(snap['rating_test_responses']),1)
        self.assertEqual(len(snap['g076_rating_events']),1)
        self.assertEqual(snap['mistake_log'][0]['wrong_count'],1)

    def test_native_judge_and_regular_step_still_work(self):
        d=self.start()
        self.assertEqual(self.step(self.move(d))['status'],'CONTINUE')
        d=self.resume(d)
        r=self.step(self.move(d,(2,2)))
        self.assertIs(r['result']['correct'],True)
        self.assertGreater(r['result']['cur_rating'],1500)

    def test_writer_effects_ast_match_original_wrong_answer(self):
        tree=ast.parse((ROOT/'app.py').read_text(encoding='utf-8-sig'))
        functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
        legacy=next(n for n in functions['rt_answer'].body if isinstance(n,ast.With)).body
        writer=functions['_rt_write_step_result'].body
        def effects(nodes):
            start=next(i for i,n in enumerate(nodes) if isinstance(n,ast.Assign)
                       and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='question_role')
            end=next(i for i,n in enumerate(nodes[start:],start) if isinstance(n,ast.If)
                     and any(isinstance(c,ast.Call) and isinstance(c.func,ast.Name)
                             and c.func.id=='_finalize_placement' for c in ast.walk(n)))
            return [ast.dump(n) for n in nodes[start:end+1]]
        self.assertEqual(effects(legacy),effects(writer))
        for name in ('_rt_write_step_result','_rt_step_placement_unlock','_rt_forfeit_on_connection'):
            for node in ast.walk(functions[name]):
                if isinstance(node,ast.Call):
                    self.assertFalse(isinstance(node.func,ast.Attribute) and node.func.attr=='commit',name)
                    self.assertFalse(isinstance(node.func,ast.Name) and node.func.id in ('get_db','_ensure_rt_pool'),name)
        # The original native rating_trial judge still refuses empty moves;
        # forfeit settlement cannot be mistaken for a successful move replay.
        ns=self.services.namespace(None,7)
        self.assertIsNone(ns['_rt_server_verify'](self.state['pool'][0],'sid',[]))

    def test_wrong_answer_and_forfeit_full_session_effects_parity(self):
        for trigger in ('manual','placement'):
            with self.subTest(trigger=trigger):
                wrong=self.start(7,trigger)
                forfeited=self.start(8,trigger)
                for _ in range(2):
                    a=self.step(self.move(wrong,(3,3)),7)
                    b=self.step(self.body(forfeited,'give_up'),8)
                    for key in ('correct','cur_rating','rating_se','rating_change','streak',
                                'converged','provisional','finished','rounds_used','start_zone_key'):
                        self.assertEqual(a['result'].get(key),b['result'].get(key),key)
                    if not a['result']['finished']:
                        wrong=self.resume(wrong,7)
                        forfeited=self.resume(forfeited,8)
                snap=self.snapshot()
                rows=[r for r in snap['rating_test_responses'] if r['session_id'] in (wrong['session_id'],forfeited['session_id'])]
                self.assertEqual(len(rows),4)
                for first,second in zip(rows[::2],rows[1::2]):
                    for key in ('round','correct','question_rating','ability_before','ability_after',
                                'question_role','bank_version','algorithm_version'):
                        self.assertEqual(first[key],second[key],key)

    def test_live_context_forfeit_denies_bad_owner_token_and_changed_corpus(self):
        from dataclasses import replace
        d=self.start()
        before=self.snapshot()
        with self.services.transaction() as c:
            ctx=self.services.resolve(c,d['session_id'],7)
            for altered in (replace(ctx,user_id=8),replace(ctx,question_token='forged')):
                with self.assertRaises(RatingRejected):
                    self.services.settle_forfeit(c,altered,[],0,'give_up')
            with self.assertRaisesRegex(RatingRejected,'rating_invalid_forfeit'):
                self.services.settle_forfeit(c,ctx,[],0,'unknown')
        self.assertEqual(self.snapshot(),before)
        self.state['pool'][0]['rating']=1600
        with self.assertRaisesRegex(RatingRejected,'rating_stale_step'):
            self.step(self.body(d,'give_up'))
        self.assertEqual(self.snapshot(),before)

    def test_unsupported_policy_stays_hold_before_forfeit(self):
        d=self.start()
        before=self.snapshot()
        self.state['pool'][0]['answer_policy']='unknown-policy'
        with self.assertRaises(RatingRejected):
            self.step(self.body(d,'give_up'))
        self.assertEqual(self.snapshot(),before)

    def test_unknown_and_independent_flags(self):
        self.assertEqual(mode({}),'legacy')
        for privacy in ('','off','on'):
            self.assertEqual(mode({'G076_RATING_STEPS_ENABLED':'on','G076_ANSWER_PRIVACY_ENFORCED':privacy}),'steps')
        for key in ('G076_RATING_STEPS_ENABLED','G076_ANSWER_PRIVACY_ENFORCED'):
            self.assertEqual(mode({'G076_RATING_STEPS_ENABLED':'on',key:'unknown'}),'hold')

    def test_off_original_functions_exactly_unchanged(self):
        # Local B1/B3/B4 was adopted before Rating; compare every pre-existing
        # Product function against that exact approved B1 snapshot, including
        # its mandatory Mistakes privacy projection. B2 adds only new helpers.
        baseline=subprocess.check_output(['git','show','8a5101fae1ac685ce2c05b76fa330155b9631052:app.py'],cwd=ROOT).decode('utf-8-sig')
        def functions(source):
            return {n.name:ast.dump(n) for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
        old,new=functions(baseline),functions((ROOT/'app.py').read_text(encoding='utf-8-sig'))
        for name,node in old.items():
            self.assertEqual(new[name],node,name)


if __name__=='__main__':
    (ROOT/'artifacts/g077-b2').mkdir(parents=True,exist_ok=True)
    unittest.main(verbosity=2)
