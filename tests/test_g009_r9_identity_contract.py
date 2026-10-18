"""R8 independent boundary characterization against REAL Product B050 in-memory database.
D-only, no Product changes; new tests supplement, never waive original 21 FAIL.
"""
import os, sys
from pathlib import Path
import pytest

ROOT=Path(os.environ["G009_PRODUCT_ROOT"])
assert (ROOT/"app.py").is_file()
sys.path.insert(0,str(ROOT/"tests"))
from test_b050_public_srs_review_authority import api_env,app_module,_post,QUESTION

def _rows(conn):
    return conn.execute(
        "SELECT user_id, question_id, grade, submission_id, submission_payload_hash, response_ms "
        "FROM review_log ORDER BY user_id, rowid").fetchall()

def _counts(conn):
    return (
      conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0],
      conn.execute("SELECT COUNT(*) FROM srs_cards").fetchone()[0],
    )

def test_changed_response_ms_same_identity_is_duplicate_not_second_write(api_env):
    client,conn=api_env
    first=_post(client,grade=5,submission_id="r8-telemetry-1",response_ms=230)
    assert first.status_code==200,first.get_json()
    before=_rows(conn);counts=_counts(conn)
    assert len(before)==1
    assert before[0]["response_ms"]==230
    second=_post(client,grade=5,submission_id="r8-telemetry-1",response_ms=9876)
    assert second.status_code==200,second.get_json()
    assert second.get_json().get("submission_duplicate") is True
    assert _counts(conn)==counts
    assert [dict(x) for x in _rows(conn)]==[dict(x) for x in before]

def test_tampered_unit_done_same_submission_rejects_and_preserves_db(api_env):
    client,conn=api_env
    first=_post(client,grade=5,submission_id="r8-unit-1",unit_done=False)
    assert first.status_code==200,first.get_json()
    before=[dict(x) for x in _rows(conn)];count=_counts(conn)
    conflicting=_post(client,grade=5,submission_id="r8-unit-1",unit_done=True)
    assert conflicting.status_code==409,conflicting.get_json()
    assert conflicting.get_json().get("error")=="idempotency_conflict"
    assert _counts(conn)==count and [dict(x) for x in _rows(conn)]==before

def test_tampered_grade_same_submission_rejects_and_preserves_db(api_env):
    client,conn=api_env
    first=_post(client,grade=5,submission_id="r8-grade-1")
    assert first.status_code==200,first.get_json()
    before=[dict(x) for x in _rows(conn)];count=_counts(conn)
    conflicting=_post(client,grade=0,submission_id="r8-grade-1")
    assert conflicting.status_code==409,conflicting.get_json()
    assert conflicting.get_json().get("error")=="idempotency_conflict"
    assert _counts(conn)==count and [dict(x) for x in _rows(conn)]==before

def test_reusing_another_users_submission_id_cannot_take_over_their_review(api_env):
    client,conn=api_env
    a=_post(client,grade=5,submission_id="r8-cross-user-1")
    assert a.status_code==200,a.get_json()
    user1=[dict(x) for x in conn.execute(
        "SELECT * FROM review_log WHERE user_id=101").fetchall()]
    conn.execute("INSERT INTO users(id) VALUES (102)")
    conn.execute("INSERT INTO user_stats(user_id,player_hp,player_max_hp) VALUES (102,30,30)")
    conn.commit()
    with client.session_transaction() as sess:
        sess["user_id"]=102
    b=_post(client,grade=0,submission_id="r8-cross-user-1")
    assert b.status_code==200,b.get_json()
    assert not b.get_json().get("submission_duplicate"),b.get_json()
    assert [dict(x) for x in conn.execute(
        "SELECT * FROM review_log WHERE user_id=101").fetchall()]==user1
    cross=conn.execute(
        "SELECT user_id,grade,submission_id FROM review_log WHERE submission_id=? ORDER BY user_id",
        ("r8-cross-user-1",)).fetchall()
    assert [(x["user_id"],x["grade"]) for x in cross]==[(101,5),(102,0)]
    assert _counts(conn)[0]==2

@pytest.mark.parametrize("bad_id",[17,True,"x"*4097])
def test_invalid_client_submission_identity_fails_without_write(api_env,bad_id):
    client,conn=api_env
    result=_post(client,grade=5,submission_id=bad_id)
    assert result.status_code==400,result.get_json()
    assert result.get_json()["error"]=="invalid_submission_identity"
    assert _counts(conn)[0]==0


@pytest.mark.parametrize("empty_id",[{},[]])
def test_present_empty_mapping_or_list_identity_fails_closed_without_write(api_env,empty_id):
    client,conn=api_env
    result=_post(client,grade=5,submission_id=empty_id)
    assert result.status_code==400,result.get_json()
    assert result.get_json()["error"]=="invalid_submission_identity"
    assert _counts(conn)==(0,0)
