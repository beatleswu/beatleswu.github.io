import concurrent.futures
import datetime
import json
from dataclasses import replace
import pytest
from g076_daily_fixture import make_daily_fixture, SECRET
from g076_daily_step_integration import enabled, settle_daily
from g076_nonmap_steps import resolve_daily, NonMapRejected
from daily_challenge_authority import canonicalize_daily_answer, judge_daily_answer

@pytest.fixture
def fx(tmp_path):
    return make_daily_fixture(tmp_path/'daily.sqlite')

def login(fx, uid=7):
    client = fx[0].test_client()
    client.post('/fixture/login', json={'uid': uid})
    return client

def ready(fx, uid=7):
    c = login(fx, uid)
    r = c.get('/api/g076/daily/today')
    assert r.status_code == 200, r.json
    d = r.json
    h = {'X-G076-Daily-CSRF': d['csrf_token']}
    b = {'flow': 'daily', 'attempt_token': d['attempt_token']}
    r = c.post('/api/g076/daily/steps/start', json=b, headers=h)
    assert r.status_code == 200, r.json
    return c, h, b, r.json, d

def play(c, h, b, cursor, xy=(0, 0)):
    return c.post('/api/g076/daily/steps', headers=h, json={**b,
        'step_index': cursor['step_index'], 'step_nonce': cursor['step_nonce'],
        'move': dict(zip(('x', 'y'), xy))})

def rows(fx, table):
    with fx[2]() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM '+table)]

def finish(fx):
    c, h, b, cur, d = ready(fx)
    first = play(c,h,b,cur)
    assert first.status_code == 200, first.json
    final = play(c,h,b,first.json,(2,2))
    return c,h,b,first.json,final,d

def test_real_flask_d5b_effects_resume_retry_and_safe_board(fx):
    c,h,b,cur,d = ready(fx)
    assert d['content'] == '(;SZ[5]PL[B]AB[ee])'
    assert 'B[aa]' not in json.dumps(d) and 'B[cc]' not in json.dumps(d)
    first = play(c,h,b,cur)
    assert first.json['status'] == 'CONTINUE' and first.json['opponent_reply'] == [1,1]
    assert rows(fx,'review_log') == []
    new_data = c.get('/api/g076/daily/today').json
    b = {**b, 'attempt_token': new_data['attempt_token']}
    resumed = c.post('/api/g076/daily/steps/start', json=b, headers=h).json
    assert resumed['previous_steps'] == [{'player_move':[0,0], 'opponent_reply':[1,1]}]
    final = play(c,h,b,resumed,(2,2))
    assert final.status_code == 200, final.json
    assert final.json['status'] == 'CORRECT'
    assert final.json['settlement']['xp_awarded'] == 50
    retry = play(c,h,b,resumed,(2,2))
    assert retry.json == {**final.json,'duplicate':True}
    assert len(rows(fx,'review_log')) == len(rows(fx,'daily_challenge_log')) == 1
    assert rows(fx,'user_stats')[0]['xp'] == 50
    assert {r['badge_id'] for r in rows(fx,'badges_earned')} == {'daily_first','daily_ace'}
    envelope = rows(fx,'review_log')[0]['source_context']
    assert 'daily_d5b:v1:' in envelope and 'new_badges' in envelope
    assert c.get('/api/g076/daily/today').json['user_submitted']
    assert c.post('/api/g076/daily/steps/start', json=b, headers=h).json['duplicate']

def test_wrong_is_final_no_xp_no_reset(fx):
    c,h,b,cur,d = ready(fx)
    r = play(c,h,b,cur,(3,3))
    assert r.status_code == 200, r.json
    assert r.json['status'] == 'INCORRECT' and r.json['settlement']['xp_awarded'] == 0
    assert rows(fx,'user_stats') == []
    assert {r['badge_id'] for r in rows(fx,'badges_earned')} == {'daily_first'}
    c,h,b,new,d = ready(fx)
    assert new['status'] == 'INCORRECT'
    assert play(c,h,b,cur).status_code == 409

@pytest.mark.parametrize('failure',['fail_effect','fail_commit'])
def test_entire_terminal_transaction_rolls_back_and_retry_recovers(fx,failure):
    c,h,b,cur,d = ready(fx)
    first = play(c,h,b,cur).json
    fx[1][failure] = True
    r = play(c,h,b,first,(2,2))
    assert r.status_code == 503
    for table in ('review_log','daily_challenge_log','user_stats','badges_earned','player_wardrobe'):
        assert rows(fx,table) == []
    assert len(rows(fx,'g076_nonmap_events')) == 1
    fx[1][failure] = False
    assert play(c,h,b,first,(2,2)).json['status'] == 'CORRECT'

@pytest.mark.parametrize('legacy_first',[False,True])
def test_legacy_and_steps_share_one_daily_winner(fx,legacy_first):
    c,h,b,cur,d = ready(fx)
    payload = {'submission_id':'legacy-daily-one','attempt_token':b['attempt_token'],
               'moves':[{'x':0,'y':0},{'x':2,'y':2}]}
    first = play(c,h,b,cur).json
    if legacy_first:
        saved = dict(fx[1]['environ'])
        fx[1]['environ'].clear()
        old = c.post('/api/daily-challenge/submit',json=payload)
        assert old.status_code == 200, old.json
        fx[1]['environ'].update(saved)
        assert play(c,h,b,first,(2,2)).status_code == 409
        assert c.post('/api/daily-challenge/submit',json=payload).json == old.json
    else:
        assert play(c,h,b,first,(2,2)).status_code == 200
        old = c.post('/api/daily-challenge/submit',json=payload)
        assert old.status_code == 409, old.json
    assert len(rows(fx,'review_log')) == len(rows(fx,'daily_challenge_log')) == 1
    assert rows(fx,'user_stats')[0]['xp'] == 50

def test_concurrent_terminal_retry_exactly_once(fx):
    c,h,b,cur,d = ready(fx)
    first = play(c,h,b,cur).json
    def request(_):
        other = login(fx)
        data = other.get('/api/g076/daily/today').json
        return play(other,{'X-G076-Daily-CSRF':data['csrf_token']},b,first,(2,2))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        replies = list(pool.map(request,range(4)))
    assert all(r.status_code == 200 for r in replies), [r.json for r in replies]
    assert sum(not r.json['duplicate'] for r in replies) == 1
    assert rows(fx,'user_stats')[0]['xp'] == 50
    assert len(rows(fx,'review_log')) == 1

def test_auth_csrf_origin_rights_date_and_payload_binding(fx):
    assert fx[0].test_client().get('/api/g076/daily/today').status_code == 401
    c,h,b,cur,d = ready(fx)
    assert c.post('/api/g076/daily/steps/start',json=b).status_code == 403
    assert c.post('/api/g076/daily/steps/start',json=b,headers={**h,'Origin':'https://evil.example'}).status_code == 403
    c2 = login(fx,8); d2 = c2.get('/api/g076/daily/today').json
    assert c2.post('/api/g076/daily/steps/start',json=b,headers={'X-G076-Daily-CSRF':d2['csrf_token']}).status_code == 409
    fx[1]['denied'] = True
    assert play(c,h,b,cur).status_code == 403
    fx[1]['denied'] = False
    assert c.post('/api/g076/daily/steps/start',json={**b,'grade':5},headers=h).status_code == 400
    fx[1]['day'] = (datetime.date.today()+datetime.timedelta(days=1)).isoformat()
    assert play(c,h,b,cur).status_code == 409
    assert rows(fx,'review_log') == []

@pytest.mark.parametrize('sgf,extras',[
    ('(;SZ[5]PL[B];B[aa](;W[bb];B[cc])(;W[dd];B[ee]))',{}),
    ('(;SZ[5]PL[B]B[aa])',{}),
    ('(;SZ[5]PL[B];B[aa];W[])',{}),
    ('(;SZ[5]PL[B];B[aa])',{'accepted_moves':['bb']}),
    ('(;SZ[5]PL[B])',{}),
])
def test_unsupported_fails_before_start_no_writes(fx,sgf,extras):
    fx[1]['question'] = {'id':301,'content':sgf,**extras}
    c=login(fx)
    assert c.get('/api/g076/daily/today').status_code == 422
    assert rows(fx,'g076_nonmap_sessions') == []
    assert rows(fx,'daily_challenge_log') == []

def test_flags_off_by_default(fx):
    assert not enabled({})
    fx[1]['environ'].pop('G076_DAILY_STEPS_ENABLED')
    assert login(fx).get('/api/g076/daily/today').status_code == 503

def test_real_seven_day_badge_and_appearance(fx):
    with fx[3]() as conn:
        for days in range(1,7):
            day=(datetime.date.today()-datetime.timedelta(days=days)).isoformat()
            conn.execute('INSERT INTO daily_challenge_log(user_id,challenge_date,question_id,correct,submitted_at) VALUES(7,?,301,1,?)',(day,day))
    assert finish(fx)[4].status_code == 200
    assert 'daily_7' in {r['badge_id'] for r in rows(fx,'badges_earned')}
    assert rows(fx,'player_wardrobe')[0]['item_id'] == 'title_wanderer'

@pytest.mark.parametrize('field,value', [('uid',8),('scope','1999-01-01')])
def test_adapter_rejects_context_binding_tampering(fx,field,value):
    c,h,b,cur,d=ready(fx)
    from g076_nonmap_steps import resolve_daily
    ctx=resolve_daily(SECRET,b['attempt_token'],uid=7,today=fx[1]['day'],
        question=fx[1]['question'],admit=lambda uid,q: None)
    answer=canonicalize_daily_answer({'moves':[{'x':0,'y':0},{'x':2,'y':2}]},ctx.attempt)
    judge=judge_daily_answer(ctx.question,ctx.attempt,answer)
    with pytest.raises(NonMapRejected, match='daily_settlement_binding_mismatch'):
        with fx[3]() as conn:
            settle_daily(conn,replace(ctx,**{field:value}),answer,judge,'tampered',services=fx[4])
    assert rows(fx,'review_log') == []

def test_changed_question_and_nonce_rejected(fx):
    c,h,b,cur,d=ready(fx)
    bad={**cur,'step_nonce':'0'*64}
    assert play(c,h,b,bad).status_code == 403
    fx[1]['question']['content']='(;SZ[5]PL[B];B[dd])'
    assert play(c,h,b,cur).status_code == 409
    assert rows(fx,'review_log') == []

def test_missing_schema_fails_closed(fx):
    with fx[3]() as conn:
        conn.execute('DROP TABLE g076_nonmap_events')
    c=login(fx)
    assert c.get('/api/g076/daily/today').status_code == 503
    assert rows(fx,'daily_challenge_log') == []

def test_legacy_races_terminal_with_single_winner(fx):
    c,h,b,cur,d=ready(fx)
    first=play(c,h,b,cur).json
    payload={'submission_id':'legacy-race-one','attempt_token':b['attempt_token'],
             'moves':[{'x':0,'y':0},{'x':2,'y':2}]}
    import threading
    barrier=threading.Barrier(2)
    def request(mode):
        other=login(fx)
        data=other.get('/api/g076/daily/today').json
        barrier.wait()
        if mode=='legacy':
            return other.post('/api/daily-challenge/submit',json=payload)
        return play(other,{'X-G076-Daily-CSRF':data['csrf_token']},b,first,(2,2))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        replies=list(pool.map(request,['legacy','step']))
    assert sorted(r.status_code for r in replies)==[200,409], [r.json for r in replies]
    assert len(rows(fx,'review_log'))==len(rows(fx,'daily_challenge_log'))==1
    assert rows(fx,'user_stats')[0]['xp']==50


def test_date_selection_keeps_existing_admin_winner_and_rejects_ambiguous_id(fx):
    from g076_daily_step_integration import select_daily_question
    q=fx[1]['question']
    other={'id':302,'content':'(;SZ[5]PL[B];B[dd])'}
    with fx[3]() as conn:
        conn.execute('INSERT INTO daily_challenge(challenge_date,question_id,set_by) VALUES(?,?,?)',(fx[1]['day'],302,'admin'))
        assert select_daily_question(conn,fx[1]['day'],load_questions=lambda:[q,other])['id']==302
    with pytest.raises(NonMapRejected,match='identity_ambiguous'):
        with fx[3]() as conn:
            select_daily_question(conn,fx[1]['day'],load_questions=lambda:[other,other])
    assert len(rows(fx,'daily_challenge'))==1

@pytest.mark.parametrize('color',['B','W'])
def test_multistep_color_and_terminal_opponent_reply(fx,color):
    other='W' if color=='B' else 'B'
    fx[1]['question']['content']=f'(;SZ[5]PL[{color}];{color}[aa];{other}[bb];{color}[cc];{other}[dd])'
    c,h,b,cur,d=ready(fx)
    first=play(c,h,b,cur).json
    assert first['status']=='CONTINUE' and first['opponent_reply']==[1,1]
    final=play(c,h,b,first,(2,2))
    assert final.status_code==200,final.json
    assert final.json['status']=='CORRECT' and final.json['opponent_reply']==[3,3]
    assert rows(fx,'user_stats')[0]['xp']==50

@pytest.mark.parametrize('move,status,xp',[((0,0),'CORRECT',50),((1,1),'INCORRECT',0)])
def test_explicit_branch_verdicts_use_real_final_judge(fx,move,status,xp):
    fx[1]['question'].update(answer_policy='g065-explicit-v1',
        content='(;SZ[5]PL[B](;B[aa]C[G065:CORRECT])(;B[bb]C[G065:INCORRECT]))')
    c,h,b,cur,d=ready(fx)
    result=play(c,h,b,cur,move)
    assert result.status_code==200,result.json
    assert result.json['status']==status and result.json['settlement']['xp_awarded']==xp
