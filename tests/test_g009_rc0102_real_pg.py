"""RC01 (app.py::srs_due) on a real disposable PostgreSQL + real Flask routes.

Prefix g009_claude_rc0102_20261012_<RUN_NONCE> (container / volume / database / tmp), loopback ephemeral port, never 5085.
Environment (hard BLOCKED_ENVIRONMENT, no skip): G009_P1_RUN_NONCE ^20261012[0-9a-z_]*$, G009_P1_EVIDENCE_ROOT absolute D: path.
The module is also a negative control: run against 308+P1 it must FAIL the RC01 expectations (see the matrix).
"""
from __future__ import annotations

import datetime
import json
import os
import statistics
import time
from pathlib import Path

import pytest

from test_g009_p1_public_due_only_real_pg import ROOT, Runtime, _json, body, sched
from test_g009_p1_a1_excluded_modes_real_pg import bootstrap_identity, seed_card


class RcRuntime(Runtime):
    def __init__(self):
        super().__init__(questions="tests/fixtures/g009_rc0102_questions.json")
        self.name = f"g009_claude_rc0102_20261012_{self.nonce}"
        self.container = self.name + "_postgres"
        self.volume = self.name + "_pgdata"

    def save(self, name, data):
        path = self.evidence / f"RC0102_{name}_{self.nonce}.json"
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(_json(data) + "\n")
        return str(path)


@pytest.fixture(scope="module")
def rt():
    value = RcRuntime()
    try:
        value.start()
        yield value
    finally:
        value.close()


RESULTS = []


def record(rt, name, **data):
    RESULTS.append({"case": name, **data})
    rt.save(f"CASE_{name}", {"case": name, **data})


def due_ids(client):
    r = client.get("/api/srs/due")
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    return data, {d["question_id"]: d for d in data["due"]}


def all_cards(client):
    r = client.get("/api/srs/all")
    assert r.status_code == 200
    return {c["question_id"]: c for c in r.get_json()}


def client_merge(all_c, due):
    """What SRS.init does with the two payloads (srs.js lines 192-194)."""
    merged = {qid: dict(c) for qid, c in all_c.items()}
    for qid, d in due.items():
        merged[qid] = {**merged.get(qid, {}), **d}
    return merged


def seed_card_at(rt, uid, qid, *, due_in_days, interval, reps, ease=2.5, last_grade=5):
    with rt.app_module.get_db() as conn:
        due = (datetime.date.today() + datetime.timedelta(days=due_in_days)).isoformat()
        conn.execute("INSERT INTO srs_cards(user_id,question_id,ease_factor,interval,repetitions,due_date,last_grade,updated_at,progress_credited)"
                     " VALUES(?,?,?,?,?,?,?,?,?)", (uid, qid, ease, interval, reps, due, last_grade, datetime.datetime.now().isoformat(), 0))
        conn.commit()


def test_neg01_persisted_future_card_is_not_synthesized_due(rt):
    uid, client = rt.user()
    assert client.post("/api/srs/review", json=body("rc-neg01-first", 5, 7001)).status_code == 200
    persisted = rt.card(uid, 7001)
    data, due = due_ids(client)
    cards = all_cards(client)
    merged = client_merge(cards, due)
    # same-day second answer with a new id: P1 keeps the schedule, the reader must not turn it into a due card either
    assert client.post("/api/srs/review", json=body("rc-neg01-second", 5, 7001)).status_code == 200
    after_second = rt.card(uid, 7001)
    data2, due2 = due_ids(client)
    ok = 7001 not in due
    record(rt, "NEG01_FUTURE_CARD", uid=uid, persisted=sched(persisted), due_contains_7001=(7001 in due), all_card=sched(cards[7001]),
           client_merged_card={k: merged[7001].get(k) for k in ("interval", "ease_factor", "due_date")},
           after_second_new_id=sched(after_second), due_contains_after_second=(7001 in due2), due_count=data["count"],
           verdict="PASS" if ok and merged[7001]["interval"] == persisted["interval"] and 7001 not in due2 else "FAIL_RC01_DEFECT_PRESENT")
    assert ok, due.get(7001)
    assert merged[7001]["interval"] == persisted["interval"] == 1 and merged[7001]["due_date"] == persisted["due_date"]
    assert sched(after_second) == sched(persisted) and 7001 not in due2


def test_neg02_past_due_and_mastered_due_cards_are_returned_unchanged(rt):
    uid, client = rt.user()
    seed_card_at(rt, uid, 7002, due_in_days=-1, interval=15, reps=4, ease=2.7)      # past due, mastered-like (ease>=2.5, reps>=3)
    seed_card_at(rt, uid, 7003, due_in_days=0, interval=6, reps=2, ease=2.6)        # due today
    data, due = due_ids(client)
    for qid, interval, ease in ((7002, 15, 2.7), (7003, 6, 2.6)):
        assert qid in due and due[qid]["interval"] == interval and due[qid]["ease_factor"] == ease, due.get(qid)
    record(rt, "NEG02_DUE_CARDS_KEPT", uid=uid, rows={q: due[q] for q in (7002, 7003)}, verdict="PASS")


def test_neg03_never_persisted_questions_still_get_the_default_due_card(rt):
    uid, client = rt.user()
    data, due = due_ids(client)
    today = datetime.date.today().isoformat()
    free_ids = {7001, 7002, 7003, 7201, 7202, 7203, 7204, 7311, 7312, 7321, 7322, 7302} | set(range(7101, 7121))
    assert free_ids <= set(due), sorted(free_ids - set(due))
    d = due[7311]
    assert (d["interval"], d["ease_factor"], d["due_date"]) == (0, 2.5, today)
    record(rt, "NEG03_VIRGIN_DEFAULT", uid=uid, sample=d, due_count=data["count"],
           note="enabled=false question 7302 is still listed (the loader does not filter enabled; unchanged historical behaviour)",
           null_due_row="not representable in the canonical PostgreSQL schema (due_date NOT NULL); covered by the SQLite parity case", verdict="PASS")


def test_neg05_free_and_premium_filters_kept(rt):
    free_uid, free_client = rt.user()
    prem_uid, prem_client = rt.user()
    with rt.app_module.get_db() as conn:
        conn.execute("UPDATE users SET plan='premium', premium_until=? WHERE id=?",
                     ((datetime.date.today() + datetime.timedelta(days=30)).isoformat(), prem_uid))
        conn.commit()
    seed_card_at(rt, free_uid, 7301, due_in_days=5, interval=6, reps=2)           # a persisted FUTURE premium-only card must stay hidden
    _, free_due = due_ids(free_client)
    _, prem_due = due_ids(prem_client)
    assert 7301 not in free_due and 7301 in prem_due
    record(rt, "NEG05_ENTITLEMENT", free_has_premium_only=(7301 in free_due), premium_has_premium_only=(7301 in prem_due),
           free_count=len(free_due), premium_count=len(prem_due), verdict="PASS")


def test_neg13_same_board_different_answer_tree_is_never_merged(rt):
    uid, client = rt.user()
    seed_card_at(rt, uid, 7321, due_in_days=3, interval=6, reps=2)               # future card on tree A
    _, due = due_ids(client)
    assert 7321 not in due and 7322 in due   # tree B is a different puzzle: still a legitimate new question
    record(rt, "NEG13_BOARD_ONLY_NOT_MERGED", uid=uid, tree_a_in_due=(7321 in due), tree_b_in_due=(7322 in due), verdict="PASS")


def test_neg04_identity_cold_then_hot_alias_folding(rt):
    import uuid
    from puzzle_identity_store import PuzzleIdentityStore
    # --- cold registry: raw-id semantics, no canonical invented
    cold_uid, cold = rt.user()
    seed_card_at(rt, cold_uid, 7311, due_in_days=4, interval=6, reps=2)
    _, cold_due = due_ids(cold)
    cold_row = {"7311_in_due": 7311 in cold_due, "7312_in_due": 7312 in cold_due}
    assert 7311 not in cold_due and 7312 in cold_due
    # --- hot registry with 7311 and 7312 as aliases of one canonical identity
    bootstrap_identity(rt, [7311])
    with rt.app_module.get_db() as conn:
        store = PuzzleIdentityStore(conn, clock=lambda: "2026-10-12T00:00:00+00:00")
        canon = str(uuid.uuid5(uuid.UUID("00000000-0000-4000-8000-000000000000"), "p1-a1:7311"))
        store._insert_alias(canon, "LEGACY_QUESTION_ID", "7312", context="post-genesis", confidence="RECORDED",
                            recorded_by="task-synthetic", when="2026-10-12T00:00:00+00:00")
        conn.commit()
    fut_uid, fut = rt.user()
    seed_card_at(rt, fut_uid, 7311, due_in_days=4, interval=6, reps=2)
    _, hot_future = due_ids(fut)
    past_uid, past = rt.user()
    seed_card_at(rt, past_uid, 7311, due_in_days=-2, interval=6, reps=2)
    _, hot_past = due_ids(past)
    assert 7311 not in hot_future and 7312 not in hot_future          # future card folds the whole alias group
    assert 7311 in hot_past and hot_past[7311]["interval"] == 6 and 7312 not in hot_past   # real due kept, alias suppressed (LC019-W2 preserved)
    record(rt, "NEG04_IDENTITY_COLD_HOT", cold=cold_row,
           hot_future={"7311": 7311 in hot_future, "7312": 7312 in hot_future},
           hot_past={"7311": 7311 in hot_past, "7312": 7312 in hot_past, "row": hot_past.get(7311)},
           verdict="PASS", note="hot registry is a synthetic bootstrap (supported store API); Production hot/cold state not inferred")


def test_neg14_idempotency_and_p1_interplay(rt):
    uid, client = rt.user()
    assert client.post("/api/srs/review", json=body("rc-neg14-a", 5, 7203)).status_code == 200
    first = sched(rt.card(uid, 7203))
    replay = client.post("/api/srs/review", json=body("rc-neg14-a", 5, 7203))
    conflict = client.post("/api/srs/review", json=body("rc-neg14-a", 0, 7203))
    early = client.post("/api/srs/review", json=body("rc-neg14-b", 5, 7203))     # new nonce, same day -> S2 shape
    after = sched(rt.card(uid, 7203))
    _, due = due_ids(client)
    assert replay.status_code == 200 and conflict.status_code == 409 and early.status_code == 200
    assert after == first and 7203 not in due and len(rt.reviews(uid, 7203)) == 2
    record(rt, "NEG14_IDEMPOTENCY_AND_S2", uid=uid, first=first, after_new_nonce=after, review_rows=len(rt.reviews(uid, 7203)),
           replay_status=replay.status_code, conflict_status=conflict.status_code, due_contains=(7203 in due), verdict="PASS")


def test_neg15_postgres_vs_sqlite_semantics_and_read_cost(rt, monkeypatch):
    import sqlite3
    app_module = rt.app_module
    uid, client = rt.user()
    with rt.app_module.get_db() as cc:
        cc.execute("UPDATE users SET plan='premium', premium_until=? WHERE id=?", ((datetime.date.today() + datetime.timedelta(days=30)).isoformat(), uid))
        cc.commit()
    today = datetime.date.today()
    cards = []
    for i, qid in enumerate((7001, 7002, 7003, 7321, 7201, 7202, 7203, 7204)):
        offset = (-5, -1, 0, 1, 3, 20, -30, 90)[i]
        cards.append((qid, offset, 6, 2, 2.6))
    for qid, offset, interval, reps, ease in cards:
        seed_card_at(rt, uid, qid, due_in_days=offset, interval=interval, reps=reps, ease=ease)
    pg_data, pg_due = due_ids(client)
    pg_key = {qid: (d["interval"], d["ease_factor"], d["due_date"]) for qid, d in pg_due.items()}

    # the SAME logic on SQLite (route function, sqlite connection, cold registry)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE srs_cards(user_id INTEGER, question_id INTEGER, ease_factor REAL, interval INTEGER, repetitions INTEGER,"
                 " due_date TEXT, last_grade INTEGER, updated_at TEXT, progress_credited INTEGER DEFAULT 0, PRIMARY KEY(user_id,question_id))")
    for qid, offset, interval, reps, ease in cards:
        conn.execute("INSERT INTO srs_cards VALUES(?,?,?,?,?,?,?,?,?)",
                     (uid, qid, ease, interval, reps, (today + datetime.timedelta(days=offset)).isoformat(), 5, "x", 0))
    conn.execute("INSERT INTO srs_cards VALUES(?,?,?,?,?,?,?,?,?)", (uid, 7311, 2.5, 4, 1, None, 5, "x", 0))   # legacy NULL due_date row

    class Ctx:
        def __enter__(self):
            return conn

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(app_module, "get_db", lambda: Ctx())
    monkeypatch.setattr(app_module, "is_premium", lambda *a, **k: True)
    sq_client = rt.client(uid)
    sq = sq_client.get("/api/srs/due").get_json()
    sq_due = {d["question_id"]: d for d in sq["due"]}
    monkeypatch.undo()
    sq_key = {qid: (d["interval"], d["ease_factor"], d["due_date"]) for qid, d in sq_due.items() if qid != 7311}
    pg_cmp = {qid: v for qid, v in pg_key.items() if qid != 7311}
    assert sq_key == pg_cmp
    null_row = sq_due.get(7311)
    assert null_row is not None and (null_row["interval"], null_row["due_date"]) == (0, today.isoformat())  # NULL-due row keeps the historical default

    # read cost with a large per-user card set
    bulk_uid, bulk = rt.user()
    with rt.app_module.get_db() as c2:
        for n in range(6000):
            offset = 1 + (n % 400) if n % 2 else -(n % 400)
            c2.execute("INSERT INTO srs_cards(user_id,question_id,ease_factor,interval,repetitions,due_date,last_grade,updated_at,progress_credited)"
                       " VALUES(?,?,?,?,?,?,?,?,?)", (bulk_uid, 900000 + n, 2.5, 6, 2, (today + datetime.timedelta(days=offset)).isoformat(), 5, "x", 0))
        c2.commit()
    times = []
    for _ in range(15):
        t0 = time.perf_counter()
        r = bulk.get("/api/srs/due")
        times.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200
    record(rt, "NEG15_PARITY_AND_COST", pg_vs_sqlite_equal=True, compared_questions=sorted(pg_cmp), pg_due_count=pg_data["count"],
           sqlite_due_count=sq["count"], sqlite_null_due_row_default_kept=True,
           bulk_cards_per_user=6000, due_ms_median=round(statistics.median(times), 2), due_ms_p95=round(sorted(times)[int(len(times) * 0.95) - 1], 2),
           due_ms_max=round(max(times), 2), verdict="PASS")


def test_zz_summary(rt):
    names = {r["case"] for r in RESULTS}
    expected = {"NEG01_FUTURE_CARD", "NEG02_DUE_CARDS_KEPT", "NEG03_VIRGIN_DEFAULT", "NEG05_ENTITLEMENT", "NEG13_BOARD_ONLY_NOT_MERGED",
                "NEG04_IDENTITY_COLD_HOT", "NEG14_IDEMPOTENCY_AND_S2", "NEG15_PARITY_AND_COST"}
    rt.save("SUMMARY", {"cases": RESULTS, "missing": sorted(expected - names)})
    assert expected <= names
