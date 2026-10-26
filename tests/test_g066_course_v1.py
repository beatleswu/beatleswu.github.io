"""Isolated course tests. All databases are disposable SQLite fixtures."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import copy
import json
from pathlib import Path
import sqlite3
import uuid

import pytest

from g066_course.service import CourseError, CourseService, Rules, create_temporary_schema

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "g066_course/data/catalog.json").read_text(encoding="utf-8"))


def binding(alias):
    return {"canonical_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"g066-fixture-only/{alias}")),
            "revision": "fixture-r1", "enabled": True, "identity_status": "EXACT",
            "katago_status": "APPROVED", "katago_revision": "fixture-r1", "katago_receipt": "FIXTURE_ONLY"}


@pytest.fixture
def factory(tmp_path):
    db = tmp_path / "disposable-course.sqlite"
    with sqlite3.connect(db) as conn:
        create_temporary_schema(conn)
    def make(**options):
        defaults = dict(resolve=binding, entitled=lambda u,q: True,
                        judge=lambda u,q,m: "CORRECT" if m == [{"x":0,"y":0}] else "INCORRECT",
                        video_evidence=lambda *args: True, enabled=True,
                        clock=lambda: datetime(2026,10,23,0,0,tzinfo=timezone.utc))
        defaults.update(options)
        return CourseService(db, CATALOG, **defaults)
    make.database = db
    return make


def finish(s, user=1, lesson=1, correct=8):
    run=s.start(user,lesson,f"start-{lesson}")["run_id"]
    result=None
    for slot in range(8):
        result=s.answer(user,run,slot,[{"x":0,"y":0}] if slot < correct else [{"x":1,"y":1}],f"answer-{lesson}-{slot}")
    return run,result


def test_catalog_source_and_v1_scope():
    assert CATALOG["source_base_sha"] == "d0f16e6ed1f7283ea39a1826d52a464a8a981cba"
    assert CATALOG["assignment_counts"] == {"csv_rows":698,"primary":240,"auxiliary":458}
    assert [l["week"] for l in CATALOG["lessons"]] == sum(([w]*5 for w in range(1,5)),[])
    assert all(len(l["questions"]["practice"])==8 for l in CATALOG["lessons"])
    assert all(q["canonical_id"] is None and q["katago_status"]=="UNKNOWN"
               for l in CATALOG["lessons"] for group in l["questions"].values() for q in group)
    assert CATALOG["runtime_enabled"] is False
    assert CATALOG["candidate_rules"]["enabled"] is False
    media=json.loads((ROOT/"g066_course/data/media-manifest.json").read_text(encoding="utf-8"))
    assert len(media["assets"])==20
    assert all(a["owner_review"]=="PENDING" and a["external_url"] is None and a["packaged"] is False for a in media["assets"])


@pytest.mark.parametrize("user",[None,0,-1,True,"1"])
def test_login_required(factory,user):
    with pytest.raises(CourseError,match="login_required"):
        factory().summary(user)


def test_default_off_without_database_touch(factory):
    s=factory(enabled=False)
    s.database="file-that-does-not-exist.sqlite"
    with pytest.raises(CourseError,match="feature_off"):
        s.start(1,1,"off")


@pytest.mark.parametrize("field,value,error",[
    ("identity_status","MISSING","canonical_binding"),("identity_status","AMBIGUOUS","canonical_binding"),
    ("identity_status","RETIRED","canonical_binding"),("enabled",False,"canonical_binding"),
    ("katago_status","PENDING","katago_review"),("katago_status","REJECTED","katago_review"),
    ("katago_receipt",None,"katago_review"),("katago_revision","stale","katago_review")])
def test_admission_fails_closed(factory,field,value,error):
    def resolve(alias):
        q=binding(alias);q[field]=value;return q
    with pytest.raises(CourseError,match=error):factory(resolve=resolve).start(1,1,"bad")
    with sqlite3.connect(factory.database) as c:assert c.execute("SELECT count(*) FROM course_runs").fetchone()[0]==0


def test_entitlement_and_video(factory):
    with pytest.raises(CourseError,match="entitlement"):factory(entitled=lambda *a:False).start(1,1,"no-entitlement")
    with pytest.raises(CourseError,match="video"):factory(video_evidence=lambda *a:False).start(1,1,"no-video")


def test_duplicate_canonical_practice_rejected(factory):
    with pytest.raises(CourseError,match="duplicate_practice"):
        factory(resolve=lambda alias:binding(1)).start(1,1,"duplicate")


@pytest.mark.parametrize("correct,complete",[(5,False),(6,True),(8,True)])
def test_first_score_threshold(factory,correct,complete):
    s=factory();run,result=finish(s,correct=correct)
    assert result["complete"] is complete
    assert s.summary(1)["lessons"][1]["unlocked"] is complete
    assert result["reward"]=="NOT_GRANTED"


def test_eight_answers_required_and_next_lesson_locked(factory):
    s=factory();run=s.start(1,1,"start")["run_id"]
    for slot in range(6):assert s.answer(1,run,slot,[{"x":0,"y":0}],str(slot))["complete"] is False
    with pytest.raises(CourseError,match="previous_lesson"):s.start(1,2,"skip")


def test_resume_relogin_other_user_and_idempotency(factory):
    s=factory();r=s.start(1,1,"start")
    assert factory().start(1,1,"another-browser")["run_id"]==r["run_id"]
    answer=s.answer(1,r["run_id"],0,[{"x":0,"y":0}],"answer")
    assert factory().answer(1,r["run_id"],0,[{"x":0,"y":0}],"answer")==answer
    assert len(factory().start(1,1,"relogin")["answers"])==1
    with pytest.raises(CourseError,match="idempotency_conflict"):s.answer(1,r["run_id"],1,[],"answer")
    with pytest.raises(CourseError,match="run_not_found"):s.answer(2,r["run_id"],1,[],"intruder")
    with pytest.raises(CourseError,match="already_recorded"):s.answer(1,r["run_id"],0,[],"new-key")


def test_concurrent_browsers_only_one_first_answer(factory):
    s=factory();run=s.start(1,1,"start")["run_id"]
    def submit(i):
        try:return factory().answer(1,run,0,[{"x":0,"y":0}],f"browser-{i}")["answered"]
        except CourseError as e:return e.code
    with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(submit,range(12)))
    assert results.count(1)==1
    assert results.count("first_answer_already_recorded")==11


def test_concurrent_same_request_replays(factory):
    run=factory().start(1,1,"start")["run_id"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(lambda _:factory().answer(1,run,0,[{"x":0,"y":0}],"same"),range(12)))
    assert all(r==results[0] for r in results)


def test_retries_and_replacements_never_inflate_first_score(factory):
    s=factory();run,result=finish(s,correct=5)
    for replace in (False,True):
        retry=s.retry(1,run,7,f"retry-{replace}",replace)
        assert retry["affects_first_score"] is False
        result=s.answer(1,run,7,[{"x":0,"y":0}],f"retry-answer-{replace}",retry["retry_id"])
        assert result["first_correct"]==5 and result["complete"] is False
        with pytest.raises(CourseError,match="retry_unavailable"):
            s.answer(1,run,7,[],"reuse"+str(replace),retry["retry_id"])


def test_replacement_never_reuses_canonical_identity(factory):
    s=factory();run,_=finish(s,correct=0)
    original={q["canonical_id"] for q in s.start(1,1,"resume")["questions"]}
    selected=[s.retry(1,run,0,f"replace-{i}",True)["question"]["canonical_id"] for i in range(3)]
    assert len(set(selected))==3 and not original.intersection(selected)


def test_empty_replacement_pool_and_correct_retry_block(factory):
    catalog=copy.deepcopy(CATALOG);catalog["lessons"][0]["questions"]["reserve"]=[]
    s=factory();s.catalog=catalog
    run,_=finish(s,correct=6)
    with pytest.raises(CourseError,match="pool_exhausted"):s.retry(1,run,7,"replace",True)
    with pytest.raises(CourseError,match="wrong_answer"):s.retry(1,run,0,"correct")


def test_rules_cannot_be_silently_enabled(factory):
    with pytest.raises(ValueError,match="Owner"):factory(rules=Rules(enabled=True))
    with pytest.raises(ValueError,match="shared free quota"):
        factory(rules=Rules(enabled=True,owner_approved=True,separate_from_free_daily_20=False))


def test_candidate_daily_new_lesson_limit_and_day_boundary(factory):
    rules=Rules(enabled=True,owner_approved=True)
    s=factory(rules=rules);finish(s,lesson=1);finish(s,lesson=2)
    with pytest.raises(CourseError,match="new_lesson_limit"):s.start(1,3,"third")
    tomorrow=factory(rules=rules,clock=lambda:datetime(2026,10,23,16,0,tzinfo=timezone.utc))
    assert tomorrow.start(1,3,"tomorrow")["run_id"]
    assert tomorrow.start(1,1,"resume")["resumed"] is True


def test_concurrent_retry_limit_is_atomic(factory):
    rules=Rules(enabled=True,owner_approved=True)
    s=factory(rules=rules);run,_=finish(s,correct=0)
    def issue(i):
        try:return factory(rules=rules).retry(1,run,0,str(i))["retry_id"]
        except CourseError as e:return e.code
    with ThreadPoolExecutor(max_workers=6) as p:results=list(p.map(issue,range(10)))
    assert results.count("daily_retry_limit")==7


def test_version_revision_and_review_revocation(factory):
    s=factory();run=s.start(1,1,"start")["run_id"]
    def revised(alias):
        q=binding(alias);q["revision"]=q["katago_revision"]="r2";return q
    with pytest.raises(CourseError,match="revision_changed"):factory(resolve=revised).answer(1,run,0,[],"revision")
    newer=factory();newer.version="v2"
    with pytest.raises(CourseError,match="not_found"):newer.answer(1,run,0,[],"version")
    changed=factory();changed.fingerprint="new-manifest"
    with pytest.raises(CourseError,match="catalog_changed"):changed.answer(1,run,0,[],"catalog")
    with pytest.raises(CourseError,match="entitlement"):factory(entitled=lambda *a:False).answer(1,run,0,[],"revoked")


def test_judge_unavailable_does_not_consume_first_answer(factory):
    s=factory(judge=lambda *a:"INVALID");run=s.start(1,1,"start")["run_id"]
    with pytest.raises(CourseError,match="judge_unavailable"):s.answer(1,run,0,[],"bad")
    assert factory().answer(1,run,0,[{"x":0,"y":0}],"valid")["answered"]==1


def test_finalization_rechecks_all_reviews_and_video(factory):
    s=factory();run=s.start(1,1,"start")["run_id"]
    for slot in range(7):s.answer(1,run,slot,[{"x":0,"y":0}],str(slot))
    first=CATALOG["lessons"][0]["questions"]["practice"][0]["legacy_question_id"]
    def revoke(alias):
        q=binding(alias)
        if alias==first:q["katago_status"]="REJECTED"
        return q
    with pytest.raises(CourseError,match="katago"):factory(resolve=revoke).answer(1,run,7,[{"x":0,"y":0}],"final")
    with pytest.raises(CourseError,match="video"):factory(video_evidence=lambda *a:False).answer(1,run,7,[{"x":0,"y":0}],"final-video")
    assert s.start(1,1,"resume")["complete"] is False


def test_reward_failure_rolls_back_final_answer_and_completion(factory):
    def fail(*a):raise RuntimeError("authority unavailable")
    s=factory(reward=fail);run=s.start(1,1,"start")["run_id"]
    for slot in range(7):s.answer(1,run,slot,[{"x":0,"y":0}],str(slot))
    with pytest.raises(RuntimeError):s.answer(1,run,7,[{"x":0,"y":0}],"final")
    resumed=s.start(1,1,"resume")
    assert len(resumed["answers"])==7 and resumed["complete"] is False


def test_real_existing_coin_authority_once_only(factory):
    from g066_course.adapters import existing_coin_reward
    # Minimal existing-authority schema fixture; NOT a new course wallet.
    with sqlite3.connect(factory.database) as c:
        c.executescript("""
        CREATE TABLE user_stats(user_id INTEGER PRIMARY KEY,coins INTEGER DEFAULT 0);
        CREATE TABLE reward_claimed(user_id INTEGER,stage_key TEXT,coins INTEGER,xp INTEGER,claimed_at TEXT,PRIMARY KEY(user_id,stage_key));
        CREATE TABLE currency_log(id INTEGER PRIMARY KEY,user_id INTEGER,delta INTEGER,balance_after INTEGER,reason TEXT,created_at TEXT);
        """)
    adapter=existing_coin_reward(coins=3,owner_approved=True)
    s=factory(reward=adapter);run,result=finish(s)
    assert result["complete"] is True
    with sqlite3.connect(factory.database) as c:
        adapter(c,1,"g066:v1:lesson:01")
        assert c.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()[0]==3
        assert c.execute("SELECT count(*) FROM currency_log").fetchone()[0]==1
        assert c.execute("SELECT xp FROM reward_claimed").fetchone()[0]==0


def test_existing_sgf_engine_adapter():
    from g066_course.adapters import existing_practice_judge
    from map_battle_runtime import question_revision_for
    q={"content":"(;GM[1]FF[4]SZ[9]AB[ba]AW[aa];B[ab])","board_size":9,"player_color":"B"}
    item={"canonical_id":str(uuid.uuid4()),"revision":question_revision_for(q)}
    judge=existing_practice_judge(lambda _:q)
    assert judge(1,item,[{"x":0,"y":1}])=="CORRECT"
    assert judge(1,item,[{"x":4,"y":4}])=="INCORRECT"
    with pytest.raises(CourseError):judge(1,item,[{"x":99,"y":99}])


def test_offline_schema_negative_constraints(factory):
    with sqlite3.connect(factory.database) as c:
        c.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):c.execute("INSERT INTO course_answers VALUES('missing',0,1)")
        with pytest.raises(sqlite3.IntegrityError):c.execute("INSERT INTO course_runs VALUES('x',0,'v',21,'d',0,'{}',0)")
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables=={"course_runs","course_answers","course_events","course_retries"}


@pytest.fixture
def http(factory):
    from flask import Flask, session, request
    from g066_course.http import create_blueprint
    app=Flask(__name__);app.secret_key="offline-fixture-only"
    app.register_blueprint(create_blueprint(factory(), current_user=lambda:session.get("user_id"),
        csrf_valid=lambda:request.headers.get("X-Course-CSRF")=="fixture-csrf",
        presenter=lambda *a:{"board_size":9,"stones":[]},media=lambda *a:None))
    client=app.test_client()
    return client


def test_http_auth_csrf_and_strict_authority_boundary(http):
    assert http.get("/api/course-v1/summary").status_code==401
    with http.session_transaction() as session:session["user_id"]=1
    assert http.post("/api/course-v1/start",json={"lesson":1,"request_id":"start"}).status_code==403
    headers={"X-Course-CSRF":"fixture-csrf"}
    r=http.post("/api/course-v1/start",json={"lesson":1,"request_id":"start","user_id":2},headers=headers)
    assert r.status_code==400
    run=http.post("/api/course-v1/start",json={"lesson":1,"request_id":"start"},headers=headers).json["run_id"]
    for field in ("correct","grade","coins","xp","canonical_id","version"):
        r=http.post("/api/course-v1/answer",json={"run_id":run,"slot":0,"moves":[],"request_id":field,field:True},headers=headers)
        assert r.status_code==400
    assert http.get("/api/course-v1/question",query_string={"run_id":run,"slot":0}).json=={"board_size":9,"stones":[]}
    assert http.get("/api/course-v1/media/1").status_code==403
    assert http.get("/api/course-v1/summary").headers["Cache-Control"]=="private, no-store"


def test_http_feature_off(factory):
    from flask import Flask
    from g066_course.http import create_blueprint
    app=Flask(__name__)
    app.register_blueprint(create_blueprint(factory(enabled=False), current_user=lambda:1,
        csrf_valid=lambda:True,presenter=lambda *a:{},media=lambda *a:None))
    assert app.test_client().get("/api/course-v1/summary").status_code==404


def test_integration_defaults_owner_gate_and_auth_assets(factory):
    from flask import Flask
    from g066_course.integration import install_course_v1
    app=Flask(__name__)
    assert install_course_v1(app) is False
    assert app.test_client().get("/course-v1/").status_code==404
    app.config["G066_COURSE_RUNTIME_ENABLED"]=True
    with pytest.raises(RuntimeError,match="Owner Gate"):install_course_v1(app)
    app=Flask("allowed")
    user=[None]
    app.config.update(G066_COURSE_RUNTIME_ENABLED=True,G066_COURSE_OWNER_APPROVED=True,
        G066_COURSE_ADAPTERS={"service":factory(),"current_user":lambda:user[0],"csrf_valid":lambda:True,
            "csrf_token":lambda:'"><script>bad</script>',"presenter":lambda *a:{},"media":lambda *a:None})
    assert install_course_v1(app) is True
    client=app.test_client()
    assert client.get("/course-v1/").status_code==401
    user[0]=1
    response=client.get("/course-v1/")
    assert response.status_code==200
    assert '<script>bad</script>' not in response.text
    assert '&lt;script&gt;bad&lt;/script&gt;' in response.text
    assert response.headers['X-Frame-Options']=='SAMEORIGIN'
    assert client.get('/course-v1/offline_schema.sql').status_code==404


def test_final_answer_concurrency_calls_reward_once(factory):
    calls=[]
    def reward(*args):calls.append(args[2])
    s=factory(reward=reward);run=s.start(1,1,"start")["run_id"]
    for slot in range(7):s.answer(1,run,slot,[{"x":0,"y":0}],str(slot))
    def submit(i):
        try:return factory(reward=reward).answer(1,run,7,[{"x":0,"y":0}],f"final-{i}")["complete"]
        except CourseError as e:return e.code
    with ThreadPoolExecutor(max_workers=5) as p:results=list(p.map(submit,range(10)))
    assert results.count(True)==1 and len(calls)==1


@pytest.mark.parametrize('url,status',[('https://media.example.invalid/lesson.mp4',200),('file:///D:/private.mp4',503),('http://media.invalid/x',503)])
def test_media_external_projection(factory,url,status):
    from flask import Flask
    from g066_course.http import create_blueprint
    app=Flask(__name__)
    app.register_blueprint(create_blueprint(factory(),current_user=lambda:1,csrf_valid=lambda:True,
        presenter=lambda *a:{},media=lambda *a:{"owner_review":"APPROVED","external_url":url,"source_file":"private"}))
    response=app.test_client().get('/api/course-v1/media/1')
    assert response.status_code==status
    assert 'source_file' not in response.json
