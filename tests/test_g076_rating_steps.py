import concurrent.futures
import itertools
import json
from pathlib import Path
import pytest
from flask import Flask
from g076_rating_fixture import make_rating_fixture
from g076_rating_steps import create_rating_blueprint, mode
from sgf_point_transform import transform_sgf


@pytest.fixture
def fx(tmp_path, monkeypatch):
    monkeypatch.setenv('SHADOW_JUDGING_ENABLED','0')
    return make_rating_fixture(tmp_path/'rating.sqlite')


def login(fx, uid=7):
    c = fx[0].test_client()
    c.post('/fixture/login',json={'uid':uid})
    return c


def start(fx, uid=7, trigger='manual'):
    c = login(fx,uid)
    r = c.post('/api/g076/rating/start',json={'trigger':trigger})
    assert r.status_code == 200,r.json
    return c,r.json


def body(d, xy=(0,0), action='move'):
    step = d['question']['step']
    t = d['question']['transform_index']
    transformed = transform_sgf('(;SZ[5];B['+''.join(chr(97+i) for i in xy)+'])',t)
    coord = transformed.split('B[')[1][:2]
    result = dict(session_id=d['session_id'],attempt_id=step['attempt_id'],nonce=step['nonce'],action=action)
    if action == 'move':
        result['move'] = dict(zip(('x','y'),(ord(i)-97 for i in coord)))
    return result


def post(c,b):
    return c.post('/api/g076/rating/step',json=b)


def counts(fx):
    with fx[2]() as conn:
        return {t:conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]
                for t in ('rating_test_responses','g076_rating_events','mistake_log')}


@pytest.mark.parametrize('rating,privacy',tuple(itertools.product(('','off','on','typo'),repeat=2)))
def test_independent_mode_gate(rating,privacy):
    expected = 'legacy' if rating in ('','off') and privacy in ('','off') else (
        'steps' if rating=='on' and privacy!='typo' else 'hold')
    # Unrelated global/nonmap/daily flags cannot disable this mode.
    assert mode({'G076_RATING_STEPS_ENABLED':rating,'G076_ANSWER_PRIVACY_ENFORCED':privacy,
                 'G076_NONMAP_STEPS_ENABLED':'off','G076_STEP_RUNTIME_ENABLED':'off'}) == expected


def test_unregistered_settlement_is_hold_even_when_on():
    app = Flask(__name__)
    app.register_blueprint(create_rating_blueprint(None,{
        'G076_RATING_STEPS_ENABLED':'on','G076_ANSWER_PRIVACY_ENFORCED':'on'}))
    c = app.test_client()
    assert c.get('/api/g076/rating/capability').json['mode']=='hold'
    assert c.post('/api/g076/rating/start',json={}).status_code==503


@pytest.mark.parametrize('uid',[7,8,None])
def test_board_only_multistep_resume_and_original_rating_effects(fx,uid):
    c,d = start(fx,uid)
    encoded = json.dumps(d)
    assert d['question']['board_only']
    for key in ('accepted_moves','katago_best_move','token','children','solution','native_answer'):
        assert key not in d['question']
    assert ';B[' not in encoded and ';W[' not in encoded
    r = post(c,body(d))
    assert r.status_code==200,r.json
    assert r.json['status']=='CONTINUE' and len(r.json['played'])==2
    assert counts(fx)['rating_test_responses']==0
    resumed = c.get('/api/g076/rating/resume/'+d['session_id']).json
    assert resumed['question']['step']['played']==r.json['played']
    assert resumed['question']['step']['nonce']==r.json['nonce']
    r = post(c,body(resumed,(2,2)))
    assert r.status_code==200,r.json
    assert r.json['status']=='CORRECT' and r.json['result']['correct'] is True
    assert r.json['result']['cur_rating']>d['cur_rating']
    assert counts(fx)['rating_test_responses']==1
    assert ';B[' not in json.dumps(r.json) and ';W[' not in json.dumps(r.json)


def test_cross_account_forged_context_and_revoked_rights(fx):
    c,d = start(fx)
    other = login(fx,8)
    b = body(d)
    assert post(other,b).status_code==403
    assert other.get('/api/g076/rating/resume/'+d['session_id']).status_code==403
    for field in ('correct','user_id','question_id','question_token','moves','init_elo','mode'):
        assert post(c,{**b,field:True}).status_code==400
    assert post(c,{**b,'attempt_id':'fake'}).status_code==403
    assert post(c,{**b,'nonce':'fake'}).status_code==409
    assert counts(fx)['rating_test_responses']==0
    assert post(c,b).status_code==200
    fx[1]['deny']=True
    assert post(c,b).status_code==403  # cached responses still require session rights


@pytest.mark.parametrize('extra',[{'init_elo':2500},{'user_id':8},{'trigger':'fake'},{'correct':True}])
def test_browser_cannot_supply_start_authority(fx,extra):
    c=login(fx)
    assert c.post('/api/g076/rating/start',json=extra).status_code==400


def test_concurrent_terminal_replay_settles_once_and_conflict(fx):
    c,d=start(fx)
    assert post(c,body(d)).json['status']=='CONTINUE'
    current=c.get('/api/g076/rating/resume/'+d['session_id']).json
    b=body(current,(2,2))
    def worker(_):
        return post(login(fx),b)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(worker,range(6)))
    assert all(r.status_code==200 for r in results),[r.json for r in results]
    assert all(r.json==results[0].json for r in results)
    assert counts(fx)['rating_test_responses']==1
    assert counts(fx)['g076_rating_events']==2
    assert post(c,{**b,'move':{'x':3,'y':3}}).status_code==409
    assert post(c,body(d)).json['status']=='CONTINUE'  # exact historical receipt


@pytest.mark.parametrize('kind',['wrong','timeout','partial_timeout','give_up','late_move'])
def test_wrong_and_timeout_original_judge_not_client_correct(fx,kind):
    c,d=start(fx)
    if kind=='partial_timeout':
        assert post(c,body(d)).json['status']=='CONTINUE'
        d=c.get('/api/g076/rating/resume/'+d['session_id']).json
    if kind in ('timeout','partial_timeout','late_move'):
        fx[1]['now']+=100
    b=body(d,(3,3) if kind=='wrong' else (0,0),
           action='timeout' if 'timeout' in kind else 'give_up' if kind=='give_up' else 'move')
    before=counts(fx)
    r=post(c,b)
    assert r.status_code==200,r.json
    assert r.json['status']=='INCORRECT'
    assert r.json['result']['correct'] is False
    assert r.json['result']['cur_rating']<1500
    assert post(c,b).json==r.json
    assert counts(fx)['rating_test_responses']==1
    assert counts(fx)['mistake_log']==1


def test_early_timeout_and_resume_do_not_reset_server_deadline(fx):
    c,d=start(fx)
    assert post(c,body(d,action='timeout')).status_code==409
    fx[1]['now']+=10
    r=c.get('/api/g076/rating/resume/'+d['session_id']).json
    assert r['question']['step']['deadline']==d['question']['step']['deadline']
    assert r['question']['step']['server_now']==fx[1]['now']


@pytest.mark.parametrize('failure',['fail_settle','fail_commit'])
def test_atomic_rollback_original_effects_and_receipt(fx,failure):
    c,d=start(fx)
    b=body(d,(3,3))
    fx[1][failure]=True
    with pytest.raises(RuntimeError):
        post(c,b)
    assert counts(fx)==dict(rating_test_responses=0,g076_rating_events=0,mistake_log=0)
    fx[1][failure]=False
    assert post(c,b).json['status']=='INCORRECT'
    assert counts(fx)['rating_test_responses']==1


@pytest.mark.parametrize('trigger',['manual','placement'])
def test_finished_uses_original_session_semantics_and_no_second_settlement(fx,trigger):
    c,d=start(fx,trigger=trigger)
    for _ in range(2):
        r=post(c,body(d,(3,3)))
        assert r.status_code==200,r.json
        if not r.json['result']['finished']:
            d=c.get('/api/g076/rating/resume/'+d['session_id']).json
    assert r.json['result']['finished']
    assert counts(fx)['rating_test_responses']==2
    resumed=c.get('/api/g076/rating/resume/'+d['session_id']).json
    assert resumed['finished'] and 'question' not in resumed
    assert len(resumed['answers'])==2


@pytest.mark.parametrize('change',[
    {'accepted_moves':[{'x':3,'y':3}]},
    {'content':'(;SZ[5];B[aa](;W[bb])(;W[cc]))'},
    {'content':'(;SZ[5];B[aa]C[unreviewed])'},
    {'content':'bad sgf'},
])
def test_unsupported_question_holds_before_answer_disclosure(fx,change):
    fx[1]['pool'][0].update(change)
    r=login(fx).post('/api/g076/rating/start',json={})
    assert r.status_code==422,r.json
    assert counts(fx)['g076_rating_events']==0


def test_gate_and_origin_cannot_be_bypassed_by_browser(fx):
    c,d=start(fx)
    assert c.get('/api/g076/rating/capability?mode=legacy').json['mode']=='steps'
    assert post(c,body(d,action='timeout')).status_code==409
    assert c.post('/api/g076/rating/step',json=body(d),headers={'Origin':'https://evil.example'}).status_code==403
    fx[1]['environ']['G076_RATING_STEPS_ENABLED']='off'
    assert post(c,body(d)).status_code==503
    fx[1]['environ'].clear()
    assert c.get('/api/g076/rating/capability').json['mode']=='legacy'


@pytest.mark.parametrize('t',range(8))
def test_each_server_transform_matches_original_judge(fx,t):
    # Keep original SHA1 transform implementation; search synthetic session ids.
    import hashlib
    c,d=start(fx)
    sid=next('transform-fixture-'+str(i) for i in range(1000)
             if int(hashlib.sha1(f'transform-fixture-{i}:301'.encode()).hexdigest(),16)%8==t)
    with fx[2]() as conn:
        conn.execute('UPDATE rating_test_sessions SET id=? WHERE id=?',(sid,d['session_id']))
        conn.execute('DELETE FROM g076_rating_attempts')
    d=c.get('/api/g076/rating/resume/'+sid).json
    assert d['question']['transform_index']==t
    assert post(c,body(d)).json['status']=='CONTINUE'
    d=c.get('/api/g076/rating/resume/'+sid).json
    assert post(c,body(d,(2,2))).json['result']['correct'] is True


def test_two_accounts_independent_and_question_revision_binding(fx):
    a,da=start(fx,7)
    b,db=start(fx,8)
    assert da['question']['step']['attempt_id']!=db['question']['step']['attempt_id']
    assert post(a,body(da)).json['status']=='CONTINUE'
    assert post(b,body(db,(3,3))).json['result']['correct'] is False
    fx[1]['pool'][0]['content']='(;SZ[5]PL[B]AB[ee];B[dd])'
    assert post(a,body(da)).json['status']=='CONTINUE'  # immutable past receipt
    assert a.get('/api/g076/rating/resume/'+da['session_id']).status_code==409
    # Changed corpus cannot consume the old live nonce or reset partial progress.
    stale={**body(da),'nonce':post(a,body(da)).json['nonce']}
    assert post(a,stale).status_code==409


def test_white_player_and_explicit_failure_branch(fx):
    fx[1]['pool'][0].update(content='(;SZ[5]PL[W]AW[ee];W[aa];B[bb];W[cc]C[G065:INCORRECT])',
                              answer_policy='g065-explicit-v1')
    c,d=start(fx)
    r=post(c,body(d))
    assert r.json['status']=='CONTINUE'
    assert [m['color'] for m in r.json['played']]==['W','B']
    d=c.get('/api/g076/rating/resume/'+d['session_id']).json
    r=post(c,body(d,(2,2)))
    assert r.json['status']=='INCORRECT' and r.json['result']['correct'] is False


def test_authorized_file_baseline_receipt():
    # B2 may add private helpers; every original top-level function is frozen.
    import ast
    import subprocess
    root=Path(__file__).resolve().parents[1]
    # Freeze only the original Rating trial callable behavior. B1 Mistakes
    # and R5 Grimoire may legitimately add/change unrelated Product functions.
    original=subprocess.check_output(
        ['git','show','6214f7b5f4f69c979da44d4ea989d3b03b6863f6:app.py'],
        cwd=root).decode('utf-8-sig')
    current=(root/'app.py').read_text(encoding='utf-8-sig')
    def rating_functions(source):
        return {n.name:ast.dump(n) for n in ast.parse(source).body
                if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
                and (n.name.startswith(('_rt_','rt_')))}
    old,new=rating_functions(original),rating_functions(current)
    assert all(new.get(k)==v for k,v in old.items())
    assert set(new)-set(old)=={
        '_rt_write_step_result','_rt_step_placement_unlock',
        '_rt_forfeit_on_connection'}
