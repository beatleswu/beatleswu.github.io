"""G076 owned Map Battle step ledger: real SQLite + canonical settlement.

No production DB or network used. Tests only the staged service contract,
not the dormant production route or Safari player E2E.
"""
import hashlib
import json
import sqlite3
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

Q = {
    "id": 7001, "source": "g076/isolated.sgf",
    "content": "(;SZ[19]PL[B];B[aa];W[bb];B[cc])",
    "monster_atk": 6,
}
BAD_Q = {
    "id": 7001, "source": "g076/isolated.sgf",
    "content": "(;SZ[19]PL[B];B[aa];W[bb];B[dd])",
}
MODE = {"E10_MAP_BATTLE_V1_MODE": "global"}
NOW = "2026-10-23T10:00:00+00:00"
SECRET = "isolated-never-real-signing-key"


@pytest.fixture
def live_fixture():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO users(id) VALUES(?)", [(101,), (202,)])
    ensure_map_battle_tables(conn)
    ensure_submission_lifecycle_schema(conn)
    ensure_isolated_step_schema(conn)
    create_map_battle(
        conn, battle_id="b1", user_id=101,
        zone_key="legacy::isolated",
        player_hp=20, player_hp_max=20,
        monster_hp=30, monster_hp_max=30,
        now=NOW)
    issue_attempt_for_context(
        conn, user_id=101, battle_id="b1", question=Q,
        initial_position_identity=hashlib.sha256(
            Q["content"].encode("utf-8")).hexdigest(),
        board_size=19, player_color="B",
        transform_version="map-battle-v1", transform_id="identity",
        attempt_id="a1", issued_at=NOW,
        expires_at="2026-10-24T10:00:00+00:00")
    issued = issue_submission_nonce_for_attempt(
        conn, user_id=101, attempt_id="a1",
        now=NOW, mode_environ=MODE)
    conn.commit()
    try:
        yield conn, issued["submission_nonce"]
    finally:
        conn.close()


def load_question(qid):
    return Q if qid == 7001 else None


def params(conn, nonce, **override):
    d=dict(conn=conn, uid=101, attempt_id="a1",
           submission_nonce=nonce, question_loader=load_question,
           secret=SECRET, now=NOW)
    d.update(override)
    return d


def answer(conn, nonce, step_index, step_nonce, x, y, **kw):
    return submit_step(**params(conn, nonce, **kw),
                       step_index=step_index, step_nonce=step_nonce,
                       move={"x": x, "y": y})


def test_entire_multistep_sqlite_battle_progresses_and_settles_once(live_fixture):
    conn, nonce=live_fixture
    start=open_steps(**params(conn, nonce))
    assert start["status"]=="READY"
    assert start["question_id"]==7001
    first=answer(conn,nonce,0,start["step_nonce"],0,0)
    assert first["status"]=="CONTINUE"
    assert first["opponent_reply"]==[1,1]
    assert "battle_settlement" not in first
    assert conn.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0]==0
    assert conn.execute("SELECT monster_hp FROM map_battles WHERE id='b1'").fetchone()[0]==30
    conn.commit()
    resumed=open_steps(**params(conn,nonce))
    assert resumed["step_index"]==1
    assert resumed["step_nonce"]==first["next_step_nonce"]
    second=answer(conn,nonce,1,resumed["step_nonce"],2,2)
    assert second["status"]=="CORRECT"
    assert second["battle_settlement"]["result"]=="CORRECT"
    assert second["battle_settlement"]["accepted"] is True
    hp=conn.execute("SELECT monster_hp FROM map_battles WHERE id='b1'").fetchone()[0]
    assert hp<30
    conn.commit()
    replay=answer(conn,nonce,1,resumed["step_nonce"],2,2)
    assert replay["duplicate"] is True
    assert replay["battle_settlement"]["submission_id"]==second["battle_settlement"]["submission_id"]
    assert conn.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0]==1
    assert conn.execute("SELECT monster_hp FROM map_battles WHERE id='b1'").fetchone()[0]==hp
    assert open_steps(**params(conn,nonce))["status"]=="SETTLED"


def test_duplicate_prefix_replays_no_extra_event(live_fixture):
    conn,nonce=live_fixture
    begin=open_steps(**params(conn,nonce))
    a=answer(conn,nonce,0,begin["step_nonce"],0,0)
    conn.commit()
    a_again=answer(conn,nonce,0,begin["step_nonce"],0,0)
    assert a_again["duplicate"] is True
    assert a_again["next_step_nonce"]==a["next_step_nonce"]
    assert conn.execute("SELECT COUNT(*) FROM g076_step_events").fetchone()[0]==1
    with pytest.raises(StepLedgerRejected,match="different_move"):
        answer(conn,nonce,0,begin["step_nonce"],2,2)


def test_wrong_first_move_commits_one_authoritative_wrong_result(live_fixture):
    conn,nonce=live_fixture
    begin=open_steps(**params(conn,nonce))
    result=answer(conn,nonce,0,begin["step_nonce"],4,4)
    assert result["status"]=="INCORRECT"
    assert result["battle_settlement"]["result"]=="INCORRECT"
    conn.commit()
    hp=conn.execute("SELECT player_hp FROM map_battles WHERE id='b1'").fetchone()[0]
    assert hp<20
    retry=answer(conn,nonce,0,begin["step_nonce"],4,4)
    assert retry["duplicate"]
    assert conn.execute("SELECT player_hp FROM map_battles WHERE id='b1'").fetchone()[0]==hp
    assert conn.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0]==1


def test_cross_account_nonce_and_nonissued_step_denied(live_fixture):
    conn,nonce=live_fixture
    begin=open_steps(**params(conn,nonce))
    with pytest.raises(StepLedgerRejected,match="attempt_not_owned"):
        open_steps(**params(conn,nonce,uid=202))
    with pytest.raises(StepLedgerRejected,match="nonce"):
        answer(conn,nonce,0,"forged",0,0)
    with pytest.raises(StepLedgerRejected,match="step_nonce_invalid"):
        answer(conn,nonce,1,begin["step_nonce"],0,0)


def test_spoofed_server_history_and_stale_question_revision_denied(live_fixture):
    conn,nonce=live_fixture
    begin=open_steps(**params(conn,nonce))
    with pytest.raises(TypeError):
        answer(conn,nonce,0,begin["step_nonce"],0,0, trusted_history=[(0,0)])
    with pytest.raises(StepLedgerRejected,match="stale_question_revision"):
        answer(conn,nonce,0,begin["step_nonce"],0,0,
               question_loader=lambda _: BAD_Q)


def test_expiry_and_battle_close_fail_closed(live_fixture):
    conn,nonce=live_fixture
    begin=open_steps(**params(conn,nonce))
    with pytest.raises(StepLedgerRejected,match="attempt_expired"):
        answer(conn,nonce,0,begin["step_nonce"],0,0,now="2026-10-25T00:00:00+00:00")
    conn.execute("UPDATE map_battles SET state='EXPIRED' WHERE id='b1'")
    with pytest.raises(StepLedgerRejected,match="battle_stale_or_closed"):
        answer(conn,nonce,0,begin["step_nonce"],0,0)


def test_transaction_rollback_does_not_credit_step_or_reward(live_fixture):
    conn,nonce=live_fixture
    begin=open_steps(**params(conn,nonce))
    conn.commit()
    first=answer(conn,nonce,0,begin["step_nonce"],0,0)
    assert first["status"]=="CONTINUE"
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM g076_step_events").fetchone()[0]==0
    assert open_steps(**params(conn,nonce))["step_index"]==0


def test_raw_nonce_absent_from_step_rows(live_fixture):
    conn,nonce=live_fixture
    begin=open_steps(**params(conn,nonce))
    next_result=answer(conn,nonce,0,begin["step_nonce"],0,0)
    rows=conn.execute("SELECT * FROM g076_step_events").fetchall()
    assert len(rows)==1
    assert nonce not in str(tuple(rows[0]))
    assert begin["step_nonce"] not in str(tuple(rows[0]))
    assert next_result["next_step_nonce"] not in str(tuple(rows[0]))
    assert "next_step_nonce" not in str(tuple(rows[0]))


def test_bad_step_shape_denied_before_write(live_fixture):
    conn,nonce=live_fixture
    begin=open_steps(**params(conn,nonce))
    with pytest.raises(StepLedgerRejected,match="invalid_step_move"):
        submit_step(**params(conn,nonce), step_index=0,
                    step_nonce=begin["step_nonce"],move={"x":0,"y":0,"grade":5})
    assert conn.execute("SELECT COUNT(*) FROM g076_step_events").fetchone()[0]==0


def test_table_schema_not_autocreated_in_runtime(live_fixture):
    src=Path(__file__).resolve().parents[1].joinpath("g076_step_ledger.py").read_text(encoding="utf-8")
    assert src.count("CREATE TABLE IF NOT EXISTS")==2
    assert "def ensure_isolated_step_schema" in src
    assert src.count("ensure_isolated_step_schema(conn)")==1
