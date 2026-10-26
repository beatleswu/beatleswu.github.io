"""G087 independent native PostgreSQL evidence for real Product public Review.
No production PG, no Player data, no mock of the route or settlement.
Prior 7 P0 historical IDs remain OPEN unless those exact tests pass.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import json

import pytest
from test_20261019_monthly_postgres import runtime, local_postgres

Q={
 "id":7001,"source":"g087/p0/fixture.sgf",
 "content":"(;SZ[19]PL[B];B[dd];W[ee])",
 "difficulty":"10k","topic":"G087","level":"10k",
 "discipline":"whole_board",
}
BASE=994087

@pytest.fixture
def review_env(runtime, monkeypatch):
 app=runtime
 monkeypatch.setattr(app,"_load_questions",lambda:[dict(Q)])
 for uid in (BASE,BASE+1):
  with app.get_db() as conn:
   conn.execute(
    "INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at) VALUES(?,?,?,?,?,?,?)",
    (uid,f"g087-public-review-{uid}","G087 Synthetic", "not-authentic",0,"free","2026-10-24T00:00:00"))
   conn.execute("INSERT INTO user_stats(user_id,coins,rank_level,xp) VALUES(?,?,?,?)",
      (uid,777,"LV1",0))
 return app

def client_for(app,uid=BASE,other_session=False):
 client=app.app.test_client()
 with client.session_transaction() as sess:
  sess["user_id"]=uid
  sess["username"]=f"g087-public-review-{uid}"
  if other_session:sess["g087_unique_signed_session"]="independent session"
 return client

def payload(sid,grade=5,**extra):
 return {"question_id":7001,"source_context":"practice","grade":grade,
         "unit_name":None,"unit_done":False,
         "submission_id":sid,**extra}

def state(app,uid=BASE):
 with app.get_db() as conn:
  review=[dict(x) for x in conn.execute(
      "SELECT user_id,question_id,grade,submission_id,submission_payload_hash FROM review_log WHERE user_id=? ORDER BY id",(uid,)).fetchall()]
  card=[dict(x) for x in conn.execute(
      "SELECT user_id,question_id,interval,repetitions,progress_credited,last_grade FROM srs_cards WHERE user_id=? ORDER BY question_id",(uid,)).fetchall()]
  stats=dict(conn.execute("SELECT coins,xp FROM user_stats WHERE user_id=?",(uid,)).fetchone())
 return {"review":review,"card":card,"stats":stats}

def test_real_pg_timeout_retry_another_session_and_conflicting_replay(review_env, tmp_path):
 app=review_env
 a,b=client_for(app),client_for(app,other_session=True)
 assert a.get_cookie("session").value!=b.get_cookie("session").value
 before=state(app)
 sid="g087-lost-response-01"
 first=a.post("/api/srs/review",json=payload(sid,5))
 assert first.status_code==200,first.get_json()
 # Simulate a transport timeout: client receives no first response; identity
 # must still be recoverable using the SAME submission ID from a new session.
 after=state(app)
 assert len(after["review"])==1
 response=b.post("/api/srs/review",json=payload(sid,5))
 assert response.status_code==200,response.get_json()
 assert response.get_json().get("submission_duplicate") is True
 assert state(app)==after
 conflict=b.post("/api/srs/review",json=payload(sid,0))
 assert conflict.status_code==409,conflict.get_json()
 assert conflict.get_json()["error"]=="idempotency_conflict"
 assert state(app)==after
 assert before["stats"]==after["stats"]=={"coins":777,"xp":0}
 assert after["card"][0]["progress_credited"]==0
 assert after["review"][0]["submission_id"]==sid
 (tmp_path/"g087_timeout_retry.json").write_text(json.dumps({
  "first":first.status_code,"retry":response.status_code,"duplicate":True,
  "conflict":conflict.status_code,"states_equal":True,
  "xp_before_after":[0,0],"coins_before_after":[777,777]}),encoding="utf8")

def test_real_pg_forged_reward_fields_do_not_mint_credit(review_env):
 app=review_env
 client=client_for(app)
 response=client.post("/api/srs/review",json=payload(
     "g087-malicious-json-fields",5,correct=True,correctness=True,
     xp=999999,coins=999999,progress_eligible=True,damage=999999))
 assert response.status_code==200,response.get_json()
 rows=state(app)
 assert rows["stats"]=={"coins":777,"xp":0}
 assert rows["card"][0]["progress_credited"]==0
 assert len(rows["review"])==1

def test_real_pg_parallel_replay_same_signed_identity_only_one_row(review_env):
 app=review_env
 barrier=Barrier(4)
 sid="g087-4-parallel-same"
 def execute(_):
  client=client_for(app)
  barrier.wait(timeout=10)
  response=client.post("/api/srs/review",json=payload(sid,5))
  return response.status_code, response.get_json()
 with ThreadPoolExecutor(max_workers=4) as pool:
  results=list(pool.map(execute,range(4)))
 assert all(code==200 for code,_ in results),results
 assert sum(result.get("submission_duplicate") is not True for _,result in results)==1,results
 rows=state(app)
 assert len(rows["review"])==1,rows
 assert rows["stats"]=={"coins":777,"xp":0}
 assert rows["card"][0]["progress_credited"]==0
