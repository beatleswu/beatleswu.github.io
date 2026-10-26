"""G076 optimistic concurrency and nonce idempotence with two real SQLite connections."""
import hashlib
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from map_battle_persistence import ensure_map_battle_tables, create_map_battle
from map_battle_runtime import (
    ensure_submission_lifecycle_schema, issue_attempt_for_context,
    issue_submission_nonce_for_attempt,
)
from g076_step_ledger import (
    ensure_isolated_step_schema, open_steps, submit_step, StepLedgerRejected,
)

Q={"id":7001,"source":"g076/race.sgf","content":"(;SZ[9]PL[B];B[aa];W[bb];B[cc])",
   "monster_atk":6}
NOW="2026-10-23T10:00:00+00:00"
SECRET="concurrency-fixture-secret"


@pytest.fixture
def isolated_file(tmp_path):
    file=tmp_path/"g076-concurrent.sqlite"
    conn=sqlite3.connect(file)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO users(id) VALUES(101)")
    ensure_map_battle_tables(conn)
    ensure_submission_lifecycle_schema(conn)
    ensure_isolated_step_schema(conn)
    create_map_battle(
        conn,battle_id="b1",user_id=101,zone_key="legacy::race",
        player_hp=20,player_hp_max=20,monster_hp=30,monster_hp_max=30,now=NOW)
    issue_attempt_for_context(
        conn,user_id=101,battle_id="b1",question=Q,
        initial_position_identity=hashlib.sha256(Q["content"].encode()).hexdigest(),
        board_size=9,player_color="B",
        transform_version="map-battle-v1",transform_id="identity",
        attempt_id="a1",issued_at=NOW,expires_at="2026-10-24T10:00:00+00:00")
    issued=issue_submission_nonce_for_attempt(
        conn,user_id=101,attempt_id="a1",now=NOW,
        mode_environ={"E10_MAP_BATTLE_V1_MODE":"global"})
    conn.commit()
    conn.close()
    return file,issued["submission_nonce"]


def connection(file):
    conn=sqlite3.connect(file,timeout=10,isolation_level=None)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def common(conn,nonce):
    return dict(conn=conn,uid=101,attempt_id="a1",
                submission_nonce=nonce,question_loader=lambda qid:Q,
                secret=SECRET,now=NOW)


def do_concurrent(file,nonce,seq,token,move,barrier):
    conn=connection(file)
    try:
        barrier.wait()
        conn.execute("BEGIN IMMEDIATE")
        try:
            result=submit_step(
                **common(conn,nonce),step_index=seq,step_nonce=token,
                move=move)
            conn.commit()
            return ("OK",result["duplicate"],result["status"])
        except StepLedgerRejected as e:
            conn.rollback()
            return ("REJECTED",e.reason,None)
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()


def test_identical_parallel_first_step_is_recorded_once(isolated_file):
    file,nonce=isolated_file
    with connection(file) as conn:
        conn.execute("BEGIN IMMEDIATE")
        boot=open_steps(**common(conn,nonce))
        conn.commit()
    barrier=threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[
            pool.submit(do_concurrent,file,nonce,0,boot["step_nonce"],
                        {"x":0,"y":0},barrier) for _ in range(2)]
        results=[f.result(timeout=15) for f in futures]
    assert sorted(results)==[
        ("OK",False,"CONTINUE"),("OK",True,"CONTINUE")]
    with connection(file) as conn:
        assert conn.execute("SELECT COUNT(*) FROM g076_step_events").fetchone()[0]==1
        assert conn.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0]==0


def test_parallel_terminal_settlement_has_exactly_one_damage(isolated_file):
    file,nonce=isolated_file
    with connection(file) as conn:
        conn.execute("BEGIN IMMEDIATE")
        boot=open_steps(**common(conn,nonce))
        first=submit_step(
            **common(conn,nonce),step_index=0,step_nonce=boot["step_nonce"],
            move={"x":0,"y":0})
        conn.commit()
    barrier=threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[
            pool.submit(do_concurrent,file,nonce,1,first["next_step_nonce"],
                        {"x":2,"y":2},barrier) for _ in range(2)]
        results=[f.result(timeout=15) for f in futures]
    assert sorted(results)==[("OK",False,"CORRECT"),("OK",True,"CORRECT")]
    with connection(file) as conn:
        assert conn.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0]==1
        assert conn.execute("SELECT COUNT(*) FROM g076_step_events").fetchone()[0]==2
        assert conn.execute("SELECT monster_hp FROM map_battles WHERE id='b1'").fetchone()[0]<30


def test_same_nonce_different_parallel_answers_cannot_both_commit(isolated_file):
    file,nonce=isolated_file
    with connection(file) as conn:
        conn.execute("BEGIN IMMEDIATE")
        boot=open_steps(**common(conn,nonce))
        conn.commit()
    barrier=threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(do_concurrent,file,nonce,0,boot["step_nonce"],
                      {"x":0,"y":0},barrier)
        b=pool.submit(do_concurrent,file,nonce,0,boot["step_nonce"],
                      {"x":3,"y":3},barrier)
        results=[a.result(timeout=15),b.result(timeout=15)]
    assert sum(1 for r in results if r[0]=="OK")==1
    assert sum(1 for r in results if r[0]=="REJECTED")==1
    with connection(file) as conn:
        assert conn.execute("SELECT COUNT(*) FROM g076_step_events").fetchone()[0]==1


def test_postgres_path_explicitly_uses_row_lock():
    from g076_step_ledger import _state
    class PostgreSQLSentinel:
        def __init__(self):
            self.sql=None
        def execute(self,sql,params):
            self.sql=sql
            class Cursor:
                def fetchone(self):return None
            return Cursor()
    fake=PostgreSQLSentinel()
    _state(fake,101,{"id":"a1","battle_id":"b1"})
    assert " FOR UPDATE" in fake.sql
