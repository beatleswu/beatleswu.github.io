"""P1 (Owner 2026-10-12): ordinary public Review advances an existing card only when it is due.

Real Flask + the real ``/api/srs/review`` route + a disposable PostgreSQL container created and removed
by this module under the unique prefix ``g009_claude_p1_20261012_<RUN_NONCE>``.  Synthetic users, loopback
ephemeral ports (never 5085), no Production data.  The authoritative server clock for due comparison is
``srs_scheduling_core.datetime.date.today()``; date-boundary cases replace it with a deterministic clock.

Environment (hard BLOCKED_ENVIRONMENT if absent, never a skip):
  G009_P1_RUN_NONCE      must match ^20261012[0-9a-z_]*$
  G009_P1_EVIDENCE_ROOT  absolute D: path (new receipts are created with mode "x")
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TASK = "G009_CLAUDE_308_P1_PUBLIC_DUE_ONLY_RECOVERY_20261012_001"
NODE = shutil.which("node")
D0 = datetime.date(2030, 1, 10)


def _json(value):
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


class FakeClock:
    """Deterministic replacement for the ``datetime`` module as seen by srs_scheduling_core."""

    def __init__(self):
        self.today = D0

        clock = self

        class _Date(datetime.date):
            @classmethod
            def today(cls):
                return cls(clock.today.year, clock.today.month, clock.today.day)

        self.module = types.SimpleNamespace(date=_Date, timedelta=datetime.timedelta,
                                            datetime=datetime.datetime)


class Runtime:
    def __init__(self, questions="tests/fixtures/g009_p1_questions.json"):
        self.nonce = os.environ.get("G009_P1_RUN_NONCE", "")
        self.evidence = Path(os.environ.get("G009_P1_EVIDENCE_ROOT", ""))
        assert re.fullmatch(r"20261012[0-9a-z_]*", self.nonce), "BLOCKED_ENVIRONMENT: explicit run nonce required"
        assert self.evidence.is_absolute() and self.evidence.drive.upper() == "D:", "BLOCKED_ENVIRONMENT: D: evidence root required"
        self.question_file = questions
        self.name = f"g009_claude_p1_20261012_{self.nonce}"
        self.container = self.name + "_postgres"
        self.volume = self.name + "_pgdata"
        self.tmp = self.evidence / f"tmp_{self.nonce}"
        self.commands = []
        self.volume_created = self.container_created = False
        self.server = None
        self.app_module = None
        self.users = 2000

    def save(self, name, data):
        path = self.evidence / f"P1_{name}_{self.nonce}.json"
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(_json(data) + "\n")
        return str(path)

    def docker(self, *argv, check=True):
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result = subprocess.run(["docker", *argv], text=True, encoding="utf-8", errors="replace",
                                capture_output=True, timeout=90)
        self.commands.append({"command": ["docker", *argv], "started_utc": started, "exit": result.returncode,
                              "stdout": result.stdout[-2000:], "stderr": result.stderr[-1000:]})
        if check:
            assert result.returncode == 0, f"BLOCKED_ENVIRONMENT: docker {argv[:2]} failed: {result.stderr}"
        return result

    def start(self):
        assert shutil.which("docker"), "BLOCKED_ENVIRONMENT: Docker required"
        assert not self.tmp.exists(), "current-run namespace must be new"
        self.tmp.mkdir()
        for kind, name in (("container", self.container), ("volume", self.volume)):
            res = self.docker(kind, "inspect", name, check=False)
            assert res.returncode != 0 and "no such" in res.stderr.lower(), "ownership collision; do not reuse"
        labels = ["--label", f"g009.task={TASK}", "--label", f"g009.run={self.nonce}"]
        self.docker("volume", "create", *labels, self.volume)
        self.volume_created = True
        self.docker("run", "--detach", "--name", self.container, *labels,
                    "--mount", f"type=volume,source={self.volume},target=/var/lib/postgresql/data",
                    "--publish", "127.0.0.1::5432", "--env", "POSTGRES_USER=g009_p1",
                    "--env", "POSTGRES_PASSWORD=g009-p1-disposable-only", "--env", f"POSTGRES_DB={self.name}", "postgres:16")
        self.container_created = True
        port_text = self.docker("port", self.container, "5432/tcp").stdout.strip().splitlines()[0]
        assert port_text.startswith("127.0.0.1:")
        self.pg_port = int(port_text.rsplit(":", 1)[1])
        assert self.pg_port > 1024 and self.pg_port != 5085
        import psycopg2
        self.dsn = f"postgresql://g009_p1:g009-p1-disposable-only@127.0.0.1:{self.pg_port}/{self.name}"
        deadline = time.monotonic() + 60
        while True:
            try:
                psycopg2.connect(self.dsn).close()
                break
            except psycopg2.OperationalError:
                assert time.monotonic() < deadline, "BLOCKED_ENVIRONMENT: disposable PostgreSQL not ready"
                time.sleep(0.25)
        question_path = ROOT / self.question_file
        os.environ.update(DATABASE_URL=self.dsn, SECRET_KEY="g009-p1-synthetic-fixture-secret",
                          QUESTIONS_JSON_PATH=str(question_path))
        import db
        assert db.describe_database_url()["host"] == "127.0.0.1"
        from migrations.sgf_admin_workbench_v1 import upgrade
        with db.get_db() as conn:
            upgrade(conn)
            conn.commit()
        import app
        self.app_module = app
        app.app.config.update(TESTING=True, SECRET_KEY=os.environ["SECRET_KEY"])
        app.init_db()
        tz = {
            "host_python_tzname": list(time.tzname), "host_utc_offset_s": -time.timezone,
            "host_TZ_env": os.environ.get("TZ"),
            "pg_container_date": self.docker("exec", self.container, "date", "+%Z %z").stdout.strip(),
            "pg_container_TZ_env": self.docker("exec", self.container, "printenv", "TZ", check=False).stdout.strip() or None,
            "pg_show_timezone": self._scalar("SHOW timezone"),
            "app_process_note": "Flask runs in this host Python process, not in a container; the SRS core uses "
                                "datetime.date.today() of this process. Production container timezone is UNKNOWN.",
        }
        self.save("RUNTIME", {"namespace": self.name, "task": TASK, "pg_port": self.pg_port, "host": "127.0.0.1",
                              "question_fixture": str(question_path), "production_access": False, "timezone": tz,
                              "app_source": app.__file__, "node": NODE})

    def _scalar(self, sql):
        import psycopg2
        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchone()[0]

    def user(self):
        self.users += 1
        uid = self.users
        with self.app_module.get_db() as conn:
            conn.execute("INSERT INTO users(id,username,password_hash,plan,created_at) VALUES(?,?,?,?,?)",
                         (uid, f"p1-fixture-{uid}", "synthetic-not-login-capable", "free", datetime.datetime.now().isoformat()))
            conn.execute("INSERT INTO user_stats(user_id,go_rank,go_rank_initialized,tour_done) VALUES(?,?,?,?)", (uid, "30k", 1, 1))
            conn.commit()
        return uid, self.client(uid)

    def client(self, uid):
        client = self.app_module.app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=uid, username=f"p1-fixture-{uid}", plan="free", is_admin=False)
        return client

    def card(self, uid, qid=7001):
        with self.app_module.get_db() as conn:
            row = conn.execute("SELECT * FROM srs_cards WHERE user_id=? AND question_id=?", (uid, qid)).fetchone()
        return dict(row) if row else None

    def reviews(self, uid, qid=None):
        with self.app_module.get_db() as conn:
            if qid is None:
                rows = conn.execute("SELECT * FROM review_log WHERE user_id=? ORDER BY id", (uid,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM review_log WHERE user_id=? AND question_id=? ORDER BY id", (uid, qid)).fetchall()
        return [dict(r) for r in rows]

    def stats(self, uid):
        with self.app_module.get_db() as conn:
            row = conn.execute("SELECT xp,coins,rank_level,rank_xp FROM user_stats WHERE user_id=?", (uid,)).fetchone()
        return dict(row)

    def snapshot(self, uid):
        result = {}
        with self.app_module.get_db() as conn:
            tables = conn.execute("SELECT table_name FROM information_schema.columns WHERE table_schema='public' AND column_name='user_id'").fetchall()
            for row in tables:
                name = row["table_name"]
                assert name.replace("_", "").isalnum()
                rows = conn.execute(f'SELECT * FROM "{name}" WHERE user_id=?', (uid,)).fetchall()
                result[name] = sorted([dict(item) for item in rows], key=_json)
        return result

    def close(self):
        cleanup = {"namespace": self.name, "task": TASK, "container_created": self.container_created,
                   "volume_created": self.volume_created, "tmp": str(self.tmp), "production_access": False}
        db = sys.modules.get("db")
        if db is not None and getattr(db, "_pool", None) is not None:
            db._pool.closeall()
            db._pool = None
        for kind, name, created in (("container", self.container, self.container_created), ("volume", self.volume, self.volume_created)):
            if created:
                info = json.loads(self.docker(kind, "inspect", name).stdout)[0]
                labels = info.get("Config", {}).get("Labels", {}) if kind == "container" else info.get("Labels", {})
                assert labels.get("g009.task") == TASK and labels.get("g009.run") == self.nonce, "refuse to delete unowned resource"
                if kind == "container":
                    self.docker("stop", "--time", "10", name)
                    self.docker("rm", name)
                else:
                    self.docker("volume", "rm", name)
            absent = self.docker(kind, "inspect", name, check=False)
            cleanup[f"{kind}_absent"] = absent.returncode != 0 and "no such" in absent.stderr.lower()
        if self.tmp.exists():
            assert self.tmp.resolve().is_relative_to(self.evidence.resolve()) and self.tmp.name == f"tmp_{self.nonce}"
            shutil.rmtree(self.tmp)
        cleanup["tmp_absent"] = not self.tmp.exists()
        cleanup["commands"] = self.commands
        self.save("CLEANUP", cleanup)
        assert cleanup["container_absent"] and cleanup["volume_absent"] and cleanup["tmp_absent"]


@pytest.fixture(scope="module")
def rt():
    value = Runtime()
    try:
        value.start()
        yield value
    finally:
        value.close()


@pytest.fixture()
def clock(monkeypatch):
    import srs_scheduling_core
    fake = FakeClock()
    monkeypatch.setattr(srs_scheduling_core, "datetime", fake.module)
    return fake


def body(submission_id, grade=5, qid=7001, **extra):
    return {"question_id": qid, "grade": grade, "unit_name": None, "unit_done": False, "source_context": "practice",
            "training_set_id": None, "is_scaffolding": False, "response_ms": 500, "submission_id": submission_id, **extra}


def sched(card):
    return None if card is None else {k: card[k] for k in ("ease_factor", "interval", "repetitions", "due_date")}


MATRIX = []


def record(rt, name, **data):
    MATRIX.append({"case": name, **data})
    rt.save(f"CASE_{name}", {"case": name, **data})


def test_ordinary_public_matrix_sequence(rt, clock):
    uid, client = rt.user()
    steps = []

    def post(sid, grade, day):
        clock.today = D0 + datetime.timedelta(days=day)
        before = rt.card(uid)
        reviews_before = len(rt.reviews(uid, 7001))
        stats_before = rt.stats(uid)
        resp = client.post("/api/srs/review", json=body(sid, grade))
        after = rt.card(uid)
        steps.append({"sid": sid, "grade": grade, "day": day, "status": resp.status_code, "before": sched(before), "after": sched(after),
                      "last_grade_after": after and after["last_grade"], "review_rows_added": len(rt.reviews(uid, 7001)) - reviews_before,
                      "xp_coins_unchanged": rt.stats(uid) == stats_before, "progress_credited": after and after["progress_credited"]})
        assert resp.status_code == 200, resp.get_json()
        return before, after

    # M1 first correct review: normal SM-2 card creation
    b, a = post("p1-m1-first", 5, 0)
    assert b is None and (a["interval"], a["repetitions"], a["due_date"]) == (1, 1, (D0 + datetime.timedelta(days=1)).isoformat())
    created = sched(a)
    # M2 same-day second correct, different id: logged, schedule untouched
    b, a = post("p1-m2-same-day-new-id", 5, 0)
    assert sched(a) == created and len(rt.reviews(uid, 7001)) == 2
    # M3 same id replay: idempotent
    reviews = rt.reviews(uid, 7001)
    b, a = post("p1-m2-same-day-new-id", 5, 0)
    assert sched(a) == created and rt.reviews(uid, 7001) == reviews
    # M4 due day correct: advances (interval 6)
    b, a = post("p1-m4-due", 5, 1)
    assert (a["interval"], a["repetitions"]) == (6, 2) and a["due_date"] == (D0 + datetime.timedelta(days=7)).isoformat()
    after_due = sched(a)
    # M5 early correct (day 2): held back
    b, a = post("p1-m5-early-correct", 5, 2)
    assert sched(a) == after_due
    # M5b early correct with grade 3 also held back
    b, a = post("p1-m5b-early-correct-3", 3, 3)
    assert sched(a) == after_due
    # M6 early WRONG: forgetting reset still applies
    b, a = post("p1-m6-early-wrong", 0, 4)
    assert (a["interval"], a["repetitions"]) == (1, 0) and a["due_date"] == (D0 + datetime.timedelta(days=5)).isoformat()
    # M7 overdue correct: advances
    reset = sched(a)
    b, a = post("p1-m7-overdue", 5, 30)
    assert (a["interval"], a["repetitions"]) == (1, 1) and a["due_date"] == (D0 + datetime.timedelta(days=31)).isoformat()
    # M8 due exactly today
    b, a = post("p1-m8-due-today", 5, 31)
    assert a["repetitions"] == 2 and a["interval"] == 6
    # rewards: public review never mints credit or XP/coins
    assert all(s["xp_coins_unchanged"] for s in steps) and all(not s["progress_credited"] for s in steps)
    record(rt, "ORDINARY_PUBLIC_SEQUENCE", uid=uid, steps=steps, fake_clock_base=D0.isoformat(),
           verdict="PASS", note="deterministic clock replaces srs_scheduling_core.datetime only")


def test_same_id_changed_payload_conflict_and_auth(rt, clock):
    uid, client = rt.user()
    assert client.post("/api/srs/review", json=body("p1-conflict", 5)).status_code == 200
    before = rt.snapshot(uid)
    results = []
    for changed in ({"grade": 0}, {"question_id": 7002}, {"unit_name": "other"}):
        r = client.post("/api/srs/review", json={**body("p1-conflict", 5), **changed})
        results.append({"changed": changed, "status": r.status_code, "error": (r.get_json() or {}).get("error")})
        assert r.status_code == 409 and r.get_json()["error"] == "idempotency_conflict"
    assert rt.snapshot(uid) == before
    anon = rt.app_module.app.test_client().post("/api/srs/review", json=body("p1-anon", 5))
    assert anon.status_code in (401, 302)
    assert rt.snapshot(uid) == before
    record(rt, "CONFLICT_AND_AUTH", uid=uid, conflicts=results, anonymous_status=anon.status_code, verdict="PASS")


def _parallel(rt, uid, ids, grade=5, qid=7001, same_payload=True):
    barrier = threading.Barrier(len(ids))

    def work(sid):
        client = rt.client(uid)
        barrier.wait(timeout=20)
        r = client.post("/api/srs/review", json=body(sid, grade, qid))
        return r.status_code, (r.get_json() or {})

    with ThreadPoolExecutor(max_workers=len(ids)) as pool:
        return list(pool.map(work, ids))


def test_concurrency_new_ids_real_transactions(rt, clock):
    rounds = []
    for scenario in ("first_review", "due_correct", "early_correct", "same_id"):
        for attempt in range(4):
            uid, client = rt.user()
            qid = 7001
            if scenario != "first_review":
                clock.today = D0
                assert client.post("/api/srs/review", json=body(f"seed-{uid}", 5, qid)).status_code == 200
                if scenario == "due_correct":
                    clock.today = D0 + datetime.timedelta(days=1)   # due today
                else:
                    clock.today = D0                                 # not due
            else:
                clock.today = D0
            before = sched(rt.card(uid, qid))
            n_before = len(rt.reviews(uid, qid))
            ids = [f"p1-{scenario}-{uid}-{i}" for i in range(6)]
            if scenario == "same_id":
                ids = [f"p1-same-{uid}"] * 6
            results = _parallel(rt, uid, ids)
            statuses = sorted(s for s, _ in results)
            after = sched(rt.card(uid, qid))
            added = len(rt.reviews(uid, qid)) - n_before
            if scenario == "first_review":
                assert after["repetitions"] == 1 and after["interval"] == 1 and added == 6
            elif scenario == "due_correct":
                assert before["repetitions"] == 1 and after["repetitions"] == 2 and after["interval"] == 6 and added == 6, (before, after)
            elif scenario == "early_correct":
                assert after == before and added == 6
            else:
                assert added == 1 and set(statuses) == {200}
            rounds.append({"scenario": scenario, "attempt": attempt, "uid": uid, "statuses": statuses, "before": before, "after": after,
                           "review_rows_added": added})
    record(rt, "CONCURRENCY_REAL_POSTGRES", threads_per_round=6, rounds=rounds, verdict="PASS",
           note="each round = 6 simultaneous POSTs through separate Flask test clients / pooled PostgreSQL transactions")


class _Spy:
    def __init__(self, app_module):
        self.app_module = app_module
        self.calls = []
        self.real = app_module.apply_srs_scheduling

    def __call__(self, conn, **kwargs):
        self.calls.append({k: (v.value if hasattr(v, "value") else v) for k, v in kwargs.items() if k in ("advance_policy", "grade", "progress_credit_policy")})
        return self.real(conn, **kwargs)


def _seed_card(rt, uid, qid=7101):
    """An existing, not-yet-due card so any held-back advance would be visible."""
    with rt.app_module.get_db() as conn:
        due = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
        conn.execute("INSERT INTO srs_cards(user_id,question_id,ease_factor,interval,repetitions,due_date,last_grade,updated_at,progress_credited)"
                     " VALUES(?,?,?,?,?,?,?,?,?)", (uid, qid, 2.5, 6, 2, due, 5, datetime.datetime.now().isoformat(), 0))
        conn.commit()


def _expected_always(prior, grade):
    import srs_scheduling_core as core
    ef, iv, rp, _due = core.sm2_update(prior["ease_factor"], prior["interval"], prior["repetitions"], grade)
    return {"ease_factor": round(ef, 6), "interval": iv, "repetitions": rp}


def _spy(rt, monkeypatch):
    spy = _Spy(rt.app_module)
    monkeypatch.setattr(rt.app_module, "apply_srs_scheduling", spy)
    return spy


def test_ordinary_public_is_classified_due_only_and_card_held(rt, monkeypatch):
    uid, client = rt.user()
    _seed_card(rt, uid, 7102)
    prior = rt.card(uid, 7102)
    spy = _spy(rt, monkeypatch)
    resp = client.post("/api/srs/review", json=body("p1-mode-ordinary", 5, 7102))
    assert resp.status_code == 200
    after = rt.card(uid, 7102)
    assert spy.calls and spy.calls[-1]["advance_policy"] == "CORRECT_ONLY_WHEN_DUE"
    assert sched(after) == sched(prior)
    record(rt, "MODE_ORDINARY_PUBLIC", uid=uid, spy=spy.calls, before=sched(prior), after=sched(after), verdict="PASS")


def test_excluded_boss_keeps_always(rt, monkeypatch):
    uid, client = rt.user()
    _seed_card(rt, uid, 7101)
    prior = rt.card(uid, 7101)
    exam = {"attempt_id": "p1bossmode01", "zone_key": "k26_30", "attempt_mode": "first_clear",
            "question_ids": list(range(7101, 7121)), "started_at": datetime.datetime.now().isoformat()}
    with client.session_transaction() as session:
        session["adventure_boss_exam"] = exam
    spy = _spy(rt, monkeypatch)
    resp = client.post("/api/srs/review", json=body("p1-mode-boss", 0, 7101, source_context="boss_trial:p1bossmode01",
                                                    boss_answer={"moves": [{"x": 3, "y": 3}]}))
    assert resp.status_code == 200, resp.get_json()
    grade = rt.reviews(uid, 7101)[0]["grade"]
    after = rt.card(uid, 7101)
    assert spy.calls and spy.calls[-1]["advance_policy"] == "ALWAYS"
    assert sched(after)["repetitions"] == _expected_always(prior, grade)["repetitions"]
    assert sched(after)["interval"] == _expected_always(prior, grade)["interval"]
    record(rt, "MODE_BOSS_LORD_TRIAL", uid=uid, spy=spy.calls, stored_grade=grade, before=sched(prior), after=sched(after),
           expected_always=_expected_always(prior, grade), verdict="PASS",
           limit="boss admission is a signed test-session fixture (same as the A1 authority tests), not natural Lord unlock")


def test_excluded_guild_keeps_always(rt, monkeypatch):
    uid, client = rt.user()
    _seed_card(rt, uid, 7103)
    prior = rt.card(uid, 7103)
    accepted = client.post("/api/quest-board/accept", json={"quest_key": "whole_board::LV1"})
    assert accepted.status_code == 200, accepted.get_json()
    spy = _spy(rt, monkeypatch)
    resp = client.post("/api/srs/review", json=body("p1-mode-guild", 0, 7103, source_context="guild_quest",
                                                    guild_quest_key="whole_board::LV1",
                                                    guild_answer={"moves": [{"action": "play", "x": 3, "y": 3}]}))
    assert resp.status_code == 200, resp.get_json()
    grade = rt.reviews(uid, 7103)[0]["grade"]
    after = rt.card(uid, 7103)
    assert spy.calls and spy.calls[-1]["advance_policy"] == "ALWAYS"
    assert sched(after)["repetitions"] == _expected_always(prior, grade)["repetitions"]
    record(rt, "MODE_GUILD_QUEST", uid=uid, spy=spy.calls, stored_grade=grade, before=sched(prior), after=sched(after),
           expected_always=_expected_always(prior, grade), verdict="PASS")


def test_guild_label_without_judged_answer_is_due_only(rt, monkeypatch):
    uid, client = rt.user()
    _seed_card(rt, uid, 7104)
    prior = rt.card(uid, 7104)
    spy = _spy(rt, monkeypatch)
    resp = client.post("/api/srs/review", json=body("p1-mode-guild-label", 5, 7104, source_context="guild_quest"))
    status = resp.status_code
    after = rt.card(uid, 7104)
    assert status == 200, resp.get_json()
    assert spy.calls and spy.calls[-1]["advance_policy"] == "CORRECT_ONLY_WHEN_DUE"
    assert sched(after)["repetitions"] == prior["repetitions"]
    record(rt, "MODE_GUILD_LABEL_ONLY", uid=uid, spy=spy.calls, before=sched(prior), after=sched(after), verdict="PASS",
           note="unverified client guild label cannot bypass the due-only rule")


def test_server_judged_practice_static_call_site_and_runtime_status(rt, monkeypatch):
    """Runtime proof needs the puzzle-identity registry (Genesis), absent in a disposable fixture.

    The runtime verdict is therefore recorded as UNKNOWN_BLOCKED_ENVIRONMENT, not PASS; this test only
    asserts (a) the static call-site fact and (b) records what the real route answered.
    """
    import ast
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "apply_srs_scheduling"]
    kw = sorted(sorted(k.arg for k in c.keywords) for c in calls)
    assert len(calls) == 2
    with_policy = [c for c in calls if any(k.arg == "advance_policy" for k in c.keywords)]
    without_policy = [c for c in calls if not any(k.arg == "advance_policy" for k in c.keywords)]
    assert len(with_policy) == 1 and len(without_policy) == 1
    practice_line = without_policy[0].lineno
    uid, client = rt.user()
    issued = client.post("/api/srs/practice/attempt", json={"question_id": 7001})
    record(rt, "MODE_SERVER_JUDGED_PRACTICE", uid=uid, static_call_site_without_advance_policy_line=practice_line,
           static_keywords=kw, runtime_attempt_status=issued.status_code, runtime_attempt_body=issued.get_json(),
           verdict="STATIC_ONLY_RUNTIME_UNKNOWN_BLOCKED_ENVIRONMENT" if issued.status_code != 200 else "ATTEMPT_ISSUED_BUT_NOT_EXERCISED")


def test_internal_map_battle_is_classified_by_static_source_only():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("ordinary_public_review = (")
    block = source[start:source.index(")\n        _srs_outcome = apply_srs_scheduling(", start)]
    for term in ("not internal", "combat_settlement_context is None", "boss_source_context is None", "boss_answer is None",
                 "boss_verdict is None", "guild_answer is None", "guild_verdict is None",
                 "training_item is None", "not active_boss_question"):
        assert term in block, term


def test_zz_write_matrix(rt):
    names = {m["case"] for m in MATRIX}
    expected = {"ORDINARY_PUBLIC_SEQUENCE", "CONFLICT_AND_AUTH", "CONCURRENCY_REAL_POSTGRES", "MODE_ORDINARY_PUBLIC",
                "MODE_BOSS_LORD_TRIAL", "MODE_GUILD_QUEST", "MODE_GUILD_LABEL_ONLY", "MODE_SERVER_JUDGED_PRACTICE"}
    rt.save("MATRIX_SUMMARY", {"cases": MATRIX, "missing_cases": sorted(expected - names),
                               "unverified": ["internal Map Battle (static source check only)", "premium training set (no fixture)",
                                              "Production container timezone"]})
    assert expected <= names
