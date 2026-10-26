"""G114 P0-B: REAL disposable PostgreSQL row-lock and Flask stale-token tests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Event
from urllib.parse import urlsplit
import os

import pytest
import psycopg2
from psycopg2.extras import DictCursor

import app as product
from db import PostgresConnectionWrapper
from daily_challenge_authority import issue_daily_attempt

BAD = {"id": 15483, "content": "(;SZ[19](;B[aa])(;B[bb]))"}
GOOD = {"id": 301, "content": "(;GM[1]FF[4]SZ[19]PL[B](;B[dd]))"}


def _url():
    url = os.environ.get("G114_P0B_PG_URL")
    if not url or os.environ.get("G114_P0B_PG_DISPOSABLE") != "1":
        pytest.skip("G114 requires explicit disposable PostgreSQL")
    db = (urlsplit(url).path or "").lower()
    if "test" not in db or "g114" not in db:
        pytest.skip("refusing non-test DB")
    return url


def _connect(url):
    raw = psycopg2.connect(url, cursor_factory=DictCursor)
    return PostgresConnectionWrapper(raw)


@pytest.fixture
def pg(monkeypatch):
    url = _url()
    with _connect(url) as conn:
        conn.execute("DROP TABLE IF EXISTS daily_challenge_log CASCADE")
        conn.execute("DROP TABLE IF EXISTS daily_challenge CASCADE")
        conn.execute("CREATE TABLE daily_challenge (challenge_date TEXT PRIMARY KEY,"
                     "question_id INTEGER NOT NULL,set_by TEXT,note TEXT)")
        conn.execute("CREATE TABLE daily_challenge_log (id SERIAL PRIMARY KEY,"
                     "user_id INTEGER,challenge_date TEXT,question_id INTEGER,"
                     "correct INTEGER,submitted_at TEXT)")
    monkeypatch.setattr(product, "get_db", lambda: _connect(url))
    monkeypatch.setattr(product, "_load_questions", lambda: [BAD, GOOD])
    yield url
    with _connect(url) as conn:
        conn.execute("DROP TABLE IF EXISTS daily_challenge_log CASCADE")
        conn.execute("DROP TABLE IF EXISTS daily_challenge CASCADE")


def _seed(url, correct=None):
    dt = date.today().isoformat()
    with _connect(url) as conn:
        conn.execute("INSERT INTO daily_challenge VALUES(?,?,?,?)",
                     (dt, 15483, "auto", None))
        if correct is not None:
            conn.execute("INSERT INTO daily_challenge_log"
                         "(user_id,challenge_date,question_id,correct,submitted_at)"
                         "VALUES(?,?,?,?,?)", (98, dt, 15483, correct, "test"))
    return dt


def test_pg_incorrect_only_preserved_and_once_rotated(pg):
    dt = _seed(pg, correct=0)
    first = product.get_or_create_daily_challenge(dt)
    assert first["question_id"] == 301
    assert first["set_by"] == "auto_g114_rotated"
    assert first == product.get_or_create_daily_challenge(dt)
    with _connect(pg) as conn:
        assert conn.execute("SELECT correct FROM daily_challenge_log WHERE user_id=98").fetchone()[0] == 0


def test_pg_successful_receipt_never_overwritten(pg):
    dt = _seed(pg, correct=1)
    result = product.get_or_create_daily_challenge(dt)
    assert result["question_id"] == 15483 and result["set_by"] == "auto"
    with _connect(pg) as conn:
        assert conn.execute("SELECT COUNT(*) FROM daily_challenge_log WHERE correct=1").fetchone()[0] == 1


def test_pg_concurrent_rotations_one_global_question(pg):
    dt = _seed(pg, correct=0)
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(product.get_or_create_daily_challenge, [dt]*4))
    assert all(x["question_id"] == 301 and x["set_by"] == "auto_g114_rotated" for x in rows)
    with _connect(pg) as conn:
        assert conn.execute("SELECT COUNT(*) FROM daily_challenge").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM daily_challenge_log").fetchone()[0] == 1


def test_pg_live_settlement_lock_prevents_rotation_race(pg):
    dt = _seed(pg, correct=None)
    locked = Event()
    release = Event()
    def settling():
        with _connect(pg) as conn:
            row = product._g114_daily_locked_authority(conn, dt)
            assert row["question_id"] == 15483
            locked.set()
            assert release.wait(10)
            conn.execute("INSERT INTO daily_challenge_log"
                         "(user_id,challenge_date,question_id,correct,submitted_at)"
                         " VALUES(?,?,?,?,?)", (98, dt, 15483, 1, "test"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(settling)
        assert locked.wait(10)
        candidate = pool.submit(product.get_or_create_daily_challenge, dt)
        release.set()
        owner.result(timeout=15)
        result = candidate.result(timeout=15)
    assert result["question_id"] == 15483
    with _connect(pg) as conn:
        assert conn.execute("SELECT COUNT(*) FROM daily_challenge_log WHERE correct=1").fetchone()[0] == 1


def test_pg_old_signed_attempt_gets_specific_reload_error_not_reward(pg, monkeypatch):
    dt = _seed(pg, correct=0)
    token = issue_daily_attempt(
        product.app.secret_key, user_id=72, challenge_date=dt,
        question=BAD, question_context=product._map_battle_question_context(BAD),
    )
    assert product.get_or_create_daily_challenge(dt)["question_id"] == 301
    # No canonical replay record exists; still traverse the actual Flask HTTP
    # submit, cryptographic attempt verification and switch awareness.
    monkeypatch.setattr(product, "load_daily_replay", lambda *a, **k: None)
    c=product.app.test_client()
    with c.session_transaction() as session: session["user_id"]=72
    r=c.post("/api/daily-challenge/submit",json={
        "submission_id":"g114-pg-stale-token","attempt_token":token,
        "moves":[{"x":0,"y":0}],"correct":True,
    })
    assert r.status_code==409, r.get_json()
    assert r.get_json()["code"]=="daily_question_updated"
    assert r.get_json()["refresh_url"]=="/daily-challenge"
    with _connect(pg) as conn:
        assert conn.execute("SELECT COUNT(*) FROM daily_challenge_log").fetchone()[0] == 1
