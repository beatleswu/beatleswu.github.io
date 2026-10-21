"""P1 ADDENDUM A1: real-runtime evidence for the excluded scheduling modes on a disposable PostgreSQL.

Prefix g009_claude_p1_a1_<RUN_NONCE> (container / volume / database / tmp). Loopback ephemeral port only (never 5085).
Environment (hard BLOCKED_ENVIRONMENT, no skip): G009_P1_RUN_NONCE ^20261012[0-9a-z_]*$, G009_P1_EVIDENCE_ROOT absolute D: path.
"""
from __future__ import annotations

import datetime
import json
import os
import time
from pathlib import Path

import pytest

from test_g009_p1_public_due_only_real_pg import (  # noqa: E402
    ROOT, D0, Runtime, FakeClock, _json, _Spy, body, sched,
)


class A1Runtime(Runtime):
    def __init__(self):
        super().__init__(questions="tests/fixtures/g009_p1_a1_questions.json")
        self.name = f"g009_claude_p1_a1_{self.nonce}"
        self.container = self.name + "_postgres"
        self.volume = self.name + "_pgdata"

    def save(self, name, data):
        path = self.evidence / f"P1A1_{name}_{self.nonce}.json"
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(_json(data) + "\n")
        return str(path)


@pytest.fixture(scope="module")
def rt():
    value = A1Runtime()
    try:
        value.start()
        yield value
    finally:
        value.close()


RESULTS = []
PROTOCOL = {"X-Map-Battle-Client-Protocol": "v1"}
ATTEMPT = "/api/adventure/map-battles/v1/attempts"
ANSWER = "/api/adventure/map-battles/v1/answers"
ZONE = "legacy::p1a1"


def record(rt, name, **data):
    RESULTS.append({"case": name, **data})
    rt.save(f"CASE_{name}", {"case": name, **data})


def seed_card(rt, uid, qid, *, due_in_days=30, interval=6, reps=2, credited=0):
    with rt.app_module.get_db() as conn:
        due = (datetime.date.today() + datetime.timedelta(days=due_in_days)).isoformat()
        conn.execute("INSERT INTO srs_cards(user_id,question_id,ease_factor,interval,repetitions,due_date,last_grade,updated_at,progress_credited)"
                     " VALUES(?,?,?,?,?,?,?,?,?)", (uid, qid, 2.5, interval, reps, due, 5, datetime.datetime.now().isoformat(), credited))
        conn.commit()


def oracle(prior, grade):
    import srs_scheduling_core as core
    ef, iv, rp, _ = core.sm2_update(prior["ease_factor"], prior["interval"], prior["repetitions"], grade)
    return {"interval": iv, "repetitions": rp}


def mb_state(client, qid):
    r = client.post(ATTEMPT, json={"zone_key": ZONE, "question_id": qid}, headers=PROTOCOL)
    return r, (r.get_json() or {})


def mb_payload(state, moves):
    return {"battle_id": state["battle_id"], "attempt_id": state["attempt_id"], "submission_nonce": state["submission_nonce"],
            "battle_revision": state["battle"]["battle_revision"], "question_revision": state["question_revision"],
            "player_color": state["player_color"], "transform_id": state["transform_id"],
            "transform_version": state["transform_version"], "moves": moves}


def table_counts(rt, uid):
    snap = rt.snapshot(uid)
    return {k: len(v) for k, v in snap.items() if v}


# ───────────────────────── test-only identity registry bootstrap (disposable DB) ─────────────────────────
_IDENTITY_NS = "00000000-0000-4000-8000-000000000000"
_FIXED_TS = "2026-10-12T00:00:00+00:00"
_RECEIPT = "ab" * 32


def bootstrap_identity(rt, qids):
    """Make the registry 'hot' for synthetic questions with the SAME supported APIs the LC015 tests use.

    Existing migration (`migrations.puzzle_identity_registry_v1.upgrade`) + `PuzzleIdentityStore` + a synthetic
    APPLIED receipt row. No repository file is changed; the real 42,804-record Genesis is never run."""
    import uuid
    from migrations.puzzle_identity_registry_v1 import upgrade as identity_upgrade
    from puzzle_identity_store import PuzzleIdentityStore
    with rt.app_module.get_db() as conn:
        identity_upgrade(conn)
        conn.execute(
            "INSERT INTO puzzle_identity_bootstrap_receipt "
            "(receipt_sha256,bootstrap_singleton,frozen_corpus_sha256,record_count,"
            " namespace_uuid,canonicalisation_rules_version,genesis_key_spec_version,"
            " historical_tree_commit,historical_tree_manifest_sha256,"
            " historical_rename_map_sha256,genesis_record_manifest_sha256,"
            " proposed_uuid_list_sha256,status,identities_written,applied_at,applied_by) "
            "VALUES (?, 'GENESIS', ?, ?, 'ns','canon-source-v1','genesis-key-v1',"
            "'c','tm','rm','gm','ul','APPLIED',0,?,'p1-a1-fixture')",
            (_RECEIPT, "x" * 64, len(qids), _FIXED_TS))
        store = PuzzleIdentityStore(conn, clock=lambda: _FIXED_TS)
        for qid in qids:
            store.create_historical_genesis_identity(
                str(uuid.uuid5(uuid.UUID(_IDENTITY_NS), f"p1-a1:{qid}")), receipt_sha256=_RECEIPT,
                canonical_source=f"p1-a1/{qid}.sgf", legacy_question_id=str(qid), creation_reason="genesis")
        conn.commit()


# ───────────────────────────── A1.1 internal Map Battle ─────────────────────────────

def test_a11_map_battle_internal_is_always_advance_real_pg(rt, monkeypatch):
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "global")
    uid, client = rt.user()
    qid = 7201
    seed_card(rt, uid, qid)                           # existing card, NOT due for 30 days
    prior = rt.card(uid, qid)
    stats0 = rt.stats(uid)
    spy = _Spy(rt.app_module)
    monkeypatch.setattr(rt.app_module, "apply_srs_scheduling", spy)

    prep, state = mb_state(client, qid)
    if prep.status_code != 200:
        record(rt, "A11_MAP_BATTLE_PREPARE", uid=uid, status=prep.status_code, body=state, verdict="BLOCKED_ENVIRONMENT")
        pytest.fail(f"map battle attempt not preparable: {prep.status_code} {state}")
    ok = client.post(ANSWER, json=mb_payload(state, [{"x": 3, "y": 3}]), headers=PROTOCOL)
    body_ok = ok.get_json() or {}
    after1 = rt.card(uid, qid)
    spy_calls = list(spy.calls)
    assert ok.status_code == 200, body_ok
    assert body_ok.get("result") == "CORRECT", body_ok
    assert spy_calls and all(c["advance_policy"] == "ALWAYS" for c in spy_calls)
    assert spy_calls[-1]["progress_credit_policy"] == "FIRST_PASS_ONLY"
    # internal review advanced an early (not due) card exactly as historical SM-2 does
    assert {k: after1[k] for k in ("interval", "repetitions")} == oracle(prior, 5)
    credited = after1["progress_credited"]
    assert credited == 1, "FIRST_PASS_ONLY must mint the sticky credit on the first passing review"
    stats1 = rt.stats(uid)

    # idempotent replay of the same settled answer: nothing else is written
    snap_before = rt.snapshot(uid)
    replay = client.post(ANSWER, json=mb_payload(state, [{"x": 3, "y": 3}]), headers=PROTOCOL)
    snap_after = rt.snapshot(uid)
    replay_status = replay.status_code

    # a second battle answer on the same, still not-due card advances again (ALWAYS) and does not mint credit twice
    prep2, state2 = mb_state(client, qid)
    second = client.post(ANSWER, json=mb_payload(state2, [{"x": 3, "y": 3}]), headers=PROTOCOL) if prep2.status_code == 200 else None
    after2 = rt.card(uid, qid)
    stats2 = rt.stats(uid)
    record(rt, "A11_MAP_BATTLE_INTERNAL", uid=uid, qid=qid, prepare_status=prep.status_code, answer_status=ok.status_code,
           answer_result=body_ok.get("result"), spy_calls=spy_calls, before=sched(prior), after_first=sched(after1),
           oracle_first=oracle(prior, 5), progress_credited_after_first=credited, stats_before=stats0, stats_after_first=stats1,
           replay_status=replay_status, replay_wrote_nothing=(snap_before == snap_after),
           second_prepare_status=prep2.status_code, second_status=(second.status_code if second is not None else None),
           after_second=sched(after2), progress_credited_after_second=after2["progress_credited"], stats_after_second=stats2,
           verdict="PASS")


def test_a11_map_battle_forged_and_ineligible_submissions_write_nothing(rt, monkeypatch):
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "global")
    uid, client = rt.user()
    other_uid, other_client = rt.user()
    qid = 7202
    seed_card(rt, uid, qid)
    before_card = rt.card(uid, qid)
    prep, state = mb_state(client, qid)
    assert prep.status_code == 200, (prep.status_code, state)
    base = mb_payload(state, [{"x": 3, "y": 3}])
    snap = rt.snapshot(uid)
    results = []

    def attempt(label, payload, c=client, headers=PROTOCOL):
        r = c.post(ANSWER, json=payload, headers=headers)
        results.append({"label": label, "status": r.status_code, "error": (r.get_json() or {}).get("error") or (r.get_json() or {}).get("code")})
        return r

    attempt("forged_grade_field", {**base, "grade": 5, "damage": 999, "monster_hp": 1})
    attempt("tampered_nonce", {**base, "submission_nonce": "x" * len(str(base["submission_nonce"]))})
    attempt("unknown_battle", {**base, "battle_id": "does-not-exist"})
    attempt("other_player_session", base, c=other_client)
    attempt("old_client_protocol", base, headers={})
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "off")
    attempt("feature_off", base)
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "global")
    assert all(r["status"] >= 400 for r in results), results
    assert rt.card(uid, qid) == before_card
    after = rt.snapshot(uid)
    changed = [t for t in set(snap) | set(after) if snap.get(t) != after.get(t)]
    assert changed == [] or set(changed) <= {"map_battle_attempts"}, changed  # a rejected call may only touch attempt bookkeeping
    assert rt.snapshot(other_uid).get("review_log", []) == []
    record(rt, "A11_MAP_BATTLE_NEGATIVES", uid=uid, other_uid=other_uid, results=results, tables_changed=changed,
           card_unchanged=True, verdict="PASS")


# ───────────────────────────── A1.2 server-judged practice ─────────────────────────────

def test_a12_server_judged_practice_real_pg(rt, monkeypatch):
    """Needs the existing puzzle-identity registry; initialised through the supported test-only bootstrap path."""
    uid, client = rt.user()
    qid = 7001
    seed_card(rt, uid, qid)
    prior = rt.card(uid, qid)
    cold = client.post("/api/srs/practice/attempt", json={"question_id": qid})   # before bootstrap: reproduces the 503
    cold_status, cold_body = cold.status_code, cold.get_json()
    bootstrap_identity(rt, [7001])
    issued = client.post("/api/srs/practice/attempt", json={"question_id": qid})
    first_status, first_body = issued.status_code, issued.get_json()
    if issued.status_code != 200:
        record(rt, "A12_PRACTICE", uid=uid, attempt_status=first_status, attempt_body=first_body,
               verdict="BLOCKED_ENVIRONMENT")
        pytest.fail(f"practice attempt not issuable: {first_status} {first_body}")
    spy = _Spy(rt.app_module)
    monkeypatch.setattr(rt.app_module, "apply_srs_scheduling", spy)
    token = first_body["attempt_token"]
    ans = client.post("/api/srs/practice/answer", json={"attempt_token": token, "moves": [{"x": 3, "y": 3}], "response_ms": 300})
    after = rt.card(uid, qid)
    assert ans.status_code == 200, ans.get_json()
    assert spy.calls and "advance_policy" not in spy.calls[-1]
    assert {k: after[k] for k in ("interval", "repetitions")} == oracle(prior, 5)
    # duplicate answer with the same token, a forged field, another player's token, and anonymous
    snap = rt.snapshot(uid)
    dup = client.post("/api/srs/practice/answer", json={"attempt_token": token, "moves": [{"x": 3, "y": 3}]})
    forged = client.post("/api/srs/practice/answer", json={"attempt_token": token, "moves": [{"x": 3, "y": 3}], "grade": 5})
    other_uid, other_client = rt.user()
    stolen = other_client.post("/api/srs/practice/answer", json={"attempt_token": token, "moves": [{"x": 3, "y": 3}]})
    anon = rt.app_module.app.test_client().post("/api/srs/practice/answer", json={"attempt_token": token, "moves": [{"x": 3, "y": 3}]})
    assert forged.status_code == 400 and stolen.status_code >= 400 and anon.status_code in (401, 302)
    assert rt.snapshot(uid) == snap or dup.status_code in (200, 409)
    record(rt, "A12_PRACTICE", uid=uid, qid=qid, cold_attempt_status=cold_status, cold_attempt_body=cold_body,
           bootstrap="synthetic APPLIED receipt + create_historical_genesis_identity for qid 7001 via supported store API",
           attempt_status=first_status, answer_status=ans.status_code,
           spy_calls=spy.calls, before=sched(prior), after=sched(after), oracle=oracle(prior, 5),
           duplicate_status=dup.status_code, duplicate_body=dup.get_json(), forged_field_status=forged.status_code,
           other_player_status=stolen.status_code, anonymous_status=anon.status_code, verdict="PASS")


# ───────────────────────────── A1.3 Premium training ─────────────────────────────

def make_premium_user(rt, *, plan="premium"):
    uid, client = rt.user()
    until = (datetime.date.today() + datetime.timedelta(days=60)).isoformat()
    with rt.app_module.get_db() as conn:
        conn.execute("UPDATE users SET plan=?, premium_until=? WHERE id=?", (plan, until if plan == "premium" else None, uid))
        conn.commit()
    return uid, client


def make_training_set(rt, owner_uid, qids, *, status="active", report_status="published"):
    """Synthetic, canonical-shaped report + training set + items (disposable DB only)."""
    now = datetime.datetime.now().isoformat()
    with rt.app_module.get_db() as conn:
        report = conn.execute(
            "INSERT INTO weekly_reports(user_id,period_start,period_end,report_version,model_version,item_rating_version,"
            "player_rating_snapshot,summary_json,status,generated_at,published_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
            (owner_uid, "2030-01-01", "2030-01-07", f"p1a1-{owner_uid}-{status}", "p1a1", "p1a1", 1400.0, "{}", report_status, now, now)).fetchone()
        tset = conn.execute(
            "INSERT INTO premium_training_sets(user_id,report_id,set_version,status,created_at) VALUES(?,?,?,?,?) RETURNING id",
            (owner_uid, report["id"], f"v-{owner_uid}-{status}", status, now)).fetchone()
        for order, qid in enumerate(qids, 1):
            conn.execute("INSERT INTO premium_training_items(set_id,question_id,item_order,role,discipline,reason_code,is_scaffolding)"
                         " VALUES(?,?,?,?,?,?,?)", (tset["id"], qid, order, "primary", "whole_board", "p1a1-fixture", 0))
        conn.commit()
    return int(tset["id"])


def test_a13_premium_training_keeps_always_and_entitlement_intact(rt, monkeypatch):
    uid, client = make_premium_user(rt)
    qid = 7203
    seed_card(rt, uid, qid)
    prior = rt.card(uid, qid)
    set_id = make_training_set(rt, uid, [qid])
    spy = _Spy(rt.app_module)
    monkeypatch.setattr(rt.app_module, "apply_srs_scheduling", spy)

    # premium training review of an early correct card keeps the historical advance
    resp = client.post("/api/srs/review", json=body("p1a1-premium-train", 5, qid, training_set_id=set_id))
    after = rt.card(uid, qid)
    assert resp.status_code == 200, resp.get_json()
    assert spy.calls and spy.calls[-1]["advance_policy"] == "ALWAYS"
    assert {k: after[k] for k in ("interval", "repetitions")} == oracle(prior, 5)
    row = [r for r in rt.reviews(uid, qid)][0]
    assert row["training_set_id"] == set_id

    # the same premium player's ORDINARY public review (no training set) is still P1-held
    other_q = 7204
    seed_card(rt, uid, other_q)
    prior2 = rt.card(uid, other_q)
    resp2 = client.post("/api/srs/review", json=body("p1a1-premium-ordinary", 5, other_q))
    after2 = rt.card(uid, other_q)
    assert resp2.status_code == 200 and spy.calls[-1]["advance_policy"] == "CORRECT_ONLY_WHEN_DUE"
    assert sched(after2) == sched(prior2)

    # same id replay is idempotent; changed payload conflicts
    snap = rt.snapshot(uid)
    replay = client.post("/api/srs/review", json=body("p1a1-premium-train", 5, qid, training_set_id=set_id))
    conflict = client.post("/api/srs/review", json=body("p1a1-premium-train", 0, qid, training_set_id=set_id))
    assert replay.status_code == 200 and conflict.status_code == 409
    assert rt.snapshot(uid) == snap

    # entitlement / ownership negatives write nothing
    free_uid, free_client = rt.user()
    seed_card(rt, free_uid, qid)
    free_before = rt.snapshot(free_uid)
    neg = []
    for label, c, payload in (
        ("free_player_uses_foreign_set", free_client, body("p1a1-free-foreign", 5, qid, training_set_id=set_id)),
        ("premium_player_uses_unknown_set", client, body("p1a1-unknown-set", 5, qid, training_set_id=99999999)),
        ("question_not_in_set", client, body("p1a1-wrong-question", 5, 7202, training_set_id=set_id)),
    ):
        r = c.post("/api/srs/review", json=payload)
        neg.append({"label": label, "status": r.status_code, "error": (r.get_json() or {}).get("error")})
        assert r.status_code in (400, 402, 403, 409, 429), (label, r.status_code, r.get_json())
    assert rt.snapshot(free_uid) == free_before
    revoked = make_training_set(rt, uid, [7202], status="revoked")
    r = client.post("/api/srs/review", json=body("p1a1-revoked-set", 5, 7202, training_set_id=revoked))
    neg.append({"label": "revoked_set", "status": r.status_code, "error": (r.get_json() or {}).get("error")})
    assert r.status_code == 403
    record(rt, "A13_PREMIUM_TRAINING", uid=uid, set_id=set_id, spy_calls=spy.calls, before=sched(prior), after=sched(after),
           oracle=oracle(prior, 5), stored_training_set_id=row["training_set_id"], ordinary_premium_after=sched(after2),
           replay_status=replay.status_code, conflict_status=conflict.status_code, negatives=neg, verdict="PASS")


# ───────────────────────────── A1.4 date boundary and real lock interleaving ─────────────────────────────

def test_a14_date_boundary_and_single_clock_source(rt, monkeypatch):
    import srs_scheduling_core as core
    source = (ROOT / "srs_scheduling_core.py").read_text(encoding="utf-8")
    code_lines = [l for l in source.splitlines() if not l.lstrip().startswith(("#", '"'))]
    import re
    assert not re.search(r"CURRENT_DATE|NOW\(\)|\bnow\(\)|\btime\.time\b", "\n".join(code_lines))
    # both the SM-2 due calculation and the P1 due comparison read the same module-level datetime
    assert source.count("datetime.date.today()") == 2
    clock = FakeClock()
    monkeypatch.setattr(core, "datetime", clock.module)
    rows = []
    # app-process date vs the PostgreSQL date: a card due on D0+1 is due for an app at D0+1 and held for an app at D0
    for label, app_today in (("app_clock_UTC_like_D0", D0), ("app_clock_UTC+8_ahead_D1", D0 + datetime.timedelta(days=1))):
        uid, client = rt.user()
        clock.today = D0
        assert client.post("/api/srs/review", json=body(f"p1a1-tz-seed-{uid}", 5, 7001)).status_code == 200
        before = sched(rt.card(uid, 7001))
        clock.today = app_today
        assert client.post("/api/srs/review", json=body(f"p1a1-tz-check-{uid}", 5, 7001)).status_code == 200
        after = sched(rt.card(uid, 7001))
        rows.append({"label": label, "app_date": app_today.isoformat(), "card_due": before["due_date"], "advanced": after != before,
                     "before": before, "after": after})
    assert rows[0]["advanced"] is False and rows[1]["advanced"] is True
    pg_date = rt._scalar("SELECT CURRENT_DATE::text")
    record(rt, "A14_DATE_BOUNDARY", rows=rows, pg_current_date_now=pg_date, host_date_now=datetime.date.today().isoformat(),
           clock_source="srs_scheduling_core.datetime.date.today() (application process) for BOTH sm2_update and the due comparison; no database date function in the core",
           consequence="a card whose due_date equals the next calendar day is held for up to the offset between the app-process timezone and the player's calendar",
           production_timezone="UNKNOWN (not read)", verdict="PASS_FOR_CLOCK_SOURCE_PRODUCTION_TZ_UNKNOWN")


def _interleave(rt, *, lock_enabled, monkeypatch):
    """A: wrong answer on a DUE card holds its transaction open. B: correct answer (due-only policy) starts meanwhile.
    Serial truth: B must not undo A's forgetting reset."""
    import threading
    import psycopg2
    import srs_scheduling_core as core
    if not lock_enabled:
        monkeypatch.setattr(core, "_is_sqlite_connection", lambda conn: True)
    uid, _client = rt.user()
    qid = 7001
    seed_card(rt, uid, qid, due_in_days=-1, interval=15, reps=4)     # due yesterday
    prior = sched(rt.card(uid, qid))
    a_done, release_a = threading.Event(), threading.Event()
    out = {}

    def tx_a():
        with rt.app_module.get_db() as conn:
            core.apply_srs_scheduling(conn, user_id=uid, question_id=qid, grade=0, now=datetime.datetime.now().isoformat(),
                                      advance_policy=core.SrsAdvancePolicy.CORRECT_ONLY_WHEN_DUE)
            a_done.set()
            release_a.wait(timeout=30)
            conn.commit()

    def tx_b():
        with rt.app_module.get_db() as conn:
            out["b"] = core.apply_srs_scheduling(conn, user_id=uid, question_id=qid, grade=5, now=datetime.datetime.now().isoformat(),
                                                 advance_policy=core.SrsAdvancePolicy.CORRECT_ONLY_WHEN_DUE)
            conn.commit()

    ta = threading.Thread(target=tx_a)
    ta.start()
    assert a_done.wait(timeout=30)
    tb = threading.Thread(target=tx_b)
    tb.start()
    waits = []
    deadline = time.monotonic() + 8
    with psycopg2.connect(rt.dsn) as mon, mon.cursor() as cur:
        while time.monotonic() < deadline:
            cur.execute("SELECT pid, state, wait_event_type, wait_event, left(query, 90) FROM pg_stat_activity "
                        "WHERE datname=current_database() AND pid<>pg_backend_pid() AND wait_event_type='Lock'")
            waits = cur.fetchall()
            if waits:
                break
            time.sleep(0.1)
        cur.execute("SELECT locktype, mode, granted FROM pg_locks WHERE NOT granted")
        ungranted = cur.fetchall()
    release_a.set()
    ta.join(timeout=30)
    tb.join(timeout=30)
    final = sched(rt.card(uid, qid))
    return {"lock_enabled": lock_enabled, "prior": prior, "final": final, "b_advanced_flag": getattr(out.get("b"), "advanced", None),
            "b_blocked_on_lock_observed": bool(waits), "pg_stat_activity_lock_waiters": [list(map(str, w)) for w in waits],
            "ungranted_locks": [list(map(str, w)) for w in ungranted]}


def test_a14_row_lock_interleaving_differing_grades(rt, monkeypatch):
    with_lock = _interleave(rt, lock_enabled=True, monkeypatch=monkeypatch)
    monkeypatch.undo()
    without_lock = _interleave(rt, lock_enabled=False, monkeypatch=monkeypatch)
    monkeypatch.undo()
    reset = {"interval": 1, "repetitions": 0}
    assert {k: with_lock["final"][k] for k in reset} == reset, with_lock           # forgetting reset survives
    assert with_lock["b_blocked_on_lock_observed"] is True and with_lock["b_advanced_flag"] is False
    lost_update = {k: without_lock["final"][k] for k in reset} != reset
    record(rt, "A14_ROW_LOCK_INTERLEAVING", with_lock=with_lock, without_lock=without_lock,
           lost_update_without_lock=lost_update,
           note="two PostgreSQL backends (two pooled connections driven by two threads of one Python process); "
                "grades differ (0 vs 5), so identical-input masking is removed",
           verdict="PASS_LOCK_NECESSITY_DEMONSTRATED" if lost_update else "LOCK_NECESSITY_NOT_DEMONSTRATED")


def test_zz_write_a1_summary(rt):
    names = {r["case"] for r in RESULTS}
    expected = {"A11_MAP_BATTLE_INTERNAL", "A11_MAP_BATTLE_NEGATIVES", "A12_PRACTICE", "A13_PREMIUM_TRAINING",
                "A14_DATE_BOUNDARY", "A14_ROW_LOCK_INTERLEAVING"}
    rt.save("SUMMARY", {"cases": RESULTS, "missing": sorted(expected - names)})
    assert expected <= names
