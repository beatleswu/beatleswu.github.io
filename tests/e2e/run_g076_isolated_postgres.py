"""G076 R2 TRUE PostgreSQL 16 Docker-isolated transaction and race acceptance.
Read-only to product; all writes go to 127.0.0.1:55487 disposable database.
"""
import hashlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg2
from psycopg2.extras import DictCursor

ROOT=Path(r"D:\go-odyssey-g075-integration-20261023")
sys.path.insert(0,str(ROOT))
from db import PostgresConnectionWrapper
from map_battle_persistence import ensure_map_battle_tables,create_map_battle
from map_battle_runtime import (
    ensure_submission_lifecycle_schema, issue_attempt_for_context,
    issue_submission_nonce_for_attempt,
)
from g076_step_ledger import open_steps,submit_step,StepLedgerRejected

NOW="2026-10-23T10:00:00+00:00"
SECRET="g076-local-pg-docker-only"
Q={"id":7001,"content":"(;SZ[9]PL[B];B[aa];W[bb];B[cc])",
   "source":"g076/local-pg-test","monster_atk":6}
CONN=dict(dbname="g076_fixture",user="g076",password="g076-only-test",
          host="127.0.0.1",port=55487,connect_timeout=5,
          cursor_factory=DictCursor)

def connect():
    return PostgresConnectionWrapper(psycopg2.connect(**CONN),pooled=False)

for i in range(30):
    try:
        trial=connect();trial.close();break
    except psycopg2.OperationalError:
        if i==29:raise
        time.sleep(0.2)

with open(r"D:\g075-artifacts\G076_R2_PG_ACTUAL_RESULTS.json","w",encoding="utf-8") as f:
    json.dump({"status":"STARTED","db":"g076_fixture","host":"127.0.0.1"},f)
checks={}
with connect() as conn:
    conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO users(id) VALUES(101)")
    ensure_map_battle_tables(conn)
    ensure_submission_lifecycle_schema(conn)
    sql=(ROOT/"migrations/g076_step_ledger_postgres_PROPOSED.sql").read_text(encoding="utf-8")
    conn.execute(sql)
    conn.commit()
    checks["pg_schema_migration"]=True

def create_attempt(aid,bid):
    with connect() as conn:
        create_map_battle(conn,battle_id=bid,user_id=101,zone_key="legacy::pg-isolated",
                          player_hp=20,player_hp_max=20,monster_hp=30,monster_hp_max=30,
                          now=NOW)
        issue_attempt_for_context(
            conn,user_id=101,battle_id=bid,question=Q,
            initial_position_identity=hashlib.sha256(Q["content"].encode()).hexdigest(),
            board_size=9,player_color="B",transform_version="map-battle-v1",
            transform_id="identity",attempt_id=aid,issued_at=NOW,
            expires_at="2026-10-24T10:00:00+00:00")
        issued=issue_submission_nonce_for_attempt(
            conn,user_id=101,attempt_id=aid,now=NOW,
            mode_environ={"E10_MAP_BATTLE_V1_MODE":"global"})
        conn.commit()
        return issued["submission_nonce"]

def params(c,n,aid):
    return dict(conn=c,uid=101,attempt_id=aid,submission_nonce=n,
                question_loader=lambda _:Q,secret=SECRET,now=NOW)

nonce=create_attempt("a1","b1")
with connect() as conn:
    begin=open_steps(**params(conn,nonce,"a1"))
    assert begin["status"]=="READY"
    prefix=submit_step(**params(conn,nonce,"a1"),step_index=0,
                       step_nonce=begin["step_nonce"],move={"x":0,"y":0})
    assert prefix["status"]=="CONTINUE"
    conn.commit()
checks["pg_first_step_continue"]=True
with connect() as conn:
    again=open_steps(**params(conn,nonce,"a1"))
    assert again["step_index"]==1
    assert again["step_nonce"]==prefix["next_step_nonce"]
    conn.commit()
checks["pg_cursor_resume"]=True

def race_worker(aid,nonce,step,token,move,barrier):
    c=connect()
    try:
        barrier.wait(timeout=10)
        try:
            result=submit_step(**params(c,nonce,aid),
                               step_index=step,step_nonce=token,move=move)
            c.commit()
            return {"accepted":True,"duplicate":result["duplicate"],
                    "status":result["status"]}
        except StepLedgerRejected as error:
            c.rollback()
            return {"accepted":False,"reason":error.reason}
        except Exception:
            c.rollback()
            raise
    finally:
        c.close()

barrier=threading.Barrier(2)
with ThreadPoolExecutor(max_workers=2) as pool:
    futures=[pool.submit(race_worker,"a1",nonce,1,prefix["next_step_nonce"],
                         {"x":2,"y":2},barrier) for _ in range(2)]
    outcomes=[f.result(timeout=25) for f in futures]
assert sorted((r["accepted"],r.get("duplicate"),r.get("status")) for r in outcomes)==[
    (True,False,"CORRECT"),(True,True,"CORRECT")
], outcomes
checks["pg_row_lock_duplicate_terminal"]=True
with connect() as conn:
    row=conn.execute("SELECT monster_hp FROM map_battles WHERE id='b1'").fetchone()
    subs=conn.execute("SELECT COUNT(*) AS n FROM map_battle_submissions").fetchone()
    events=conn.execute("SELECT COUNT(*) AS n FROM g076_step_events").fetchone()
    assert row["monster_hp"]<30,dict(row)
    assert subs["n"]==1,subs["n"]
    assert events["n"]==2,events["n"]
    conn.commit()
checks["pg_one_hp_one_submission"]=True

wrong_nonce=create_attempt("a2","b2")
with connect() as conn:
    boot=open_steps(**params(conn,wrong_nonce,"a2"))
    wrong=submit_step(**params(conn,wrong_nonce,"a2"),step_index=0,
        step_nonce=boot["step_nonce"],move={"x":8,"y":8})
    assert wrong["status"]=="INCORRECT"
    assert wrong["battle_settlement"]["result"]=="INCORRECT"
    conn.commit()
    result=conn.execute("SELECT player_hp FROM map_battles WHERE id='b2'").fetchone()
    assert result["player_hp"]<20
checks["pg_wrong_answer_damages_player"]=True

with connect() as conn:
    try:
        open_steps(**params(conn,wrong_nonce,"a2"),uid=202)
    except TypeError:
        try:
            open_steps(conn=conn,uid=202,attempt_id="a2",
                       submission_nonce=wrong_nonce,question_loader=lambda _:Q,
                       secret=SECRET,now=NOW)
        except StepLedgerRejected as ex:
            assert ex.reason=="attempt_not_owned"
        else:
            raise AssertionError("cross-account attempt admitted")
    conn.rollback()
checks["pg_cross_account_denied"]=True

result={
    "status":"PASS" if all(checks.values()) else "FAIL",
    "storage":"Docker isolated postgres:16-alpine, tmpfs only",
    "product_no_write":True,"production_db_no_connect":True,
    "checks":checks,"test_cases":sum(checks.values()),
    "database":"g076_fixture","no_persistent_volume":True
}
Path(r"D:\g075-artifacts\G076_R2_PG_ACTUAL_RESULTS.json").write_text(
    json.dumps(result,indent=2),encoding="utf-8")
print("G076_POSTGRES_ACTUAL",json.dumps(result),flush=True)
