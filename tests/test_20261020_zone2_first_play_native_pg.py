"""Zone 1 Lord -> unlocked Zone 2 -> real Map answer on disposable native PG.

Synthetic zone-2 SGF is registered with PuzzleIdentity only in this fixture.
No production identity or player state is modified.
"""
from __future__ import annotations

from copy import deepcopy
import json
import pytest
from test_20261019_monthly_postgres import local_postgres, runtime as native_runtime
import test_20261019_lord_full_journey_native_pg as lord
from test_20261019_lord_full_journey_native_pg import lord_player

ZONE2 = "k21_25"
HEADERS = {"X-Map-Battle-Client-Protocol": "v1"}

ZONE2_QUESTION = deepcopy(lord.CORPUS[0])
ZONE2_QUESTION.update({
    "id": 970031,
    "rank": "25k",
    "difficulty": "25k",
    "topic": "3史萊姆平原",
    "stage": "LV2",
    "level": "LV2",
    "source": "disposable-zone2-fixture/q970031.sgf",
    "display_name": "Zone 2 real map-entry fixture",
    "content": lord.CORPUS[0]["content"].replace(
        "Deterministic Lord Trial fixture answer",
        "Unique zone two player map battle answer"),
})

ZONE2_EXTRA_QUESTIONS = []
for _qid in (970032, 970033, 970034):
    _question = deepcopy(ZONE2_QUESTION)
    _question.update({
        "id": _qid,
        "source": f"disposable-zone2-fixture/q{_qid}.sgf",
        "display_name": f"Zone 2 WGo fixture {_qid}",
        "content": ZONE2_QUESTION["content"].replace(
            "Unique zone two player map battle answer",
            f"Independent zone two board answer {_qid}"),
    })
    ZONE2_EXTRA_QUESTIONS.append(_question)


@pytest.fixture
def zone2_player(monkeypatch, request):
    # Four Zone 2 questions: the first API answer is 25%, below the
    # unchanged 30% Lord threshold. Original Zone 1 corpus is untouched.
    monkeypatch.setattr(lord, "CORPUS",
                        lord.CORPUS + [ZONE2_QUESTION] + ZONE2_EXTRA_QUESTIONS)
    return request.getfixturevalue("lord_player")


@pytest.mark.parametrize("input_mode", ["desktop_mouse", "chrome_tablet_touch"])
def test_zone2_question_after_authoritative_zone1_lord_first_clear(zone2_player, monkeypatch, input_mode):
    app, client = zone2_player
    # Match the established disposable-PG Map Battle acceptance mode.
    # This affects only this pytest process, never deployed feature policy.
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "global")
    q = ZONE2_QUESTION
    # Locked Zone 2 must not issue a gameplay nonce prematurely.
    locked = client.post("/api/adventure/map-battles/v1/attempts",
                         json={"zone_key": ZONE2, "question_id": q["id"]},
                         headers=HEADERS)
    assert locked.status_code != 200, locked.get_json()

    lord.seed_lord_eligibility(client)
    started = lord.checked_json(client.post(
        "/api/adventure/boss/start", json={"zone_key": lord.ZONE}))
    assert len(started["question_ids"]) == 20
    for i, qid in enumerate(started["question_ids"]):
        question = lord.QUESTION_BY_ID[qid]
        result = lord.checked_json(client.post(
            "/api/srs/review", json={
                "question_id": qid,
                "grade": 5,
                "source_context": f'boss_trial:{started["attempt_id"]}',
                "response_ms": 1200 + i,
                "boss_answer": {"moves": [dict(question["accepted_moves"][0])]},
            }))
        assert result["ok"] is True

    finish = lord.checked_json(client.post(
        "/api/adventure/boss/finish", json={"correct": 0, "total": 0}))
    assert finish["passed"] is True
    assert finish["first_clear_projection"]["status"] == "COMPLETED"

    state = lord.checked_json(client.get("/api/adventure/bootstrap"))
    by_key = {z["key"]: z for z in state["zones"]}
    assert by_key[lord.ZONE]["cleared"] is True
    assert by_key[ZONE2]["unlocked"] is True

    # A fresh session is a genuine relogin and must retain Zone 2 entitlement.
    fresh = app.app.test_client()
    with fresh.session_transaction() as s:
        s["user_id"] = lord.UID
        s["username"] = "p1-lord-disposable"
    grant = lord.checked_json(fresh.post(
        "/api/adventure/map-battles/v1/attempts",
        json={"zone_key": ZONE2, "question_id": q["id"]},
        headers=HEADERS))
    answer = lord.checked_json(fresh.post(
        "/api/adventure/map-battles/v1/answers",
        json={
            "battle_id": grant["battle_id"],
            "attempt_id": grant["attempt_id"],
            "submission_nonce": grant["submission_nonce"],
            "battle_revision": grant["battle"]["battle_revision"],
            "question_revision": grant["question_revision"],
            "player_color": grant["player_color"],
            "transform_id": grant["transform_id"],
            "transform_version": grant["transform_version"],
            "moves": [dict(q["accepted_moves"][0])],
        }, headers=HEADERS))
    assert answer["accepted"] is True and answer["result"] == "CORRECT"
    assert answer["duplicate"] is False

    relogin_state = lord.checked_json(fresh.get("/api/adventure/bootstrap"))
    second = next(z for z in relogin_state["zones"] if z["key"] == ZONE2)
    assert second["unlocked"] is True
    assert second["cleared"] is False
    assert second["zone_authority_stars"] == 0
    assert second["correct_count"] >= 1

    # Exercise the ORIGINAL E9 map with a visible Zone 2 click, not a JS
    # function call or mocked API. Isolated schema is provisioned explicitly.
    import os
    import subprocess
    import threading
    from pathlib import Path
    from werkzeug.serving import make_server
    from migrations.companion_operations_v1 import upgrade as upgrade_companion
    from migrations.spirit_evolution_events_v1 import upgrade as upgrade_evolution
    with app.get_db() as conn:
        assert upgrade_companion(conn)["missing"] == []
        assert upgrade_evolution(conn)["missing"] == []
    with app.get_db() as conn:
        before_xp = conn.execute(
            "SELECT xp FROM user_stats WHERE user_id=?", (lord.UID,)
        ).fetchone()["xp"]
    cookie = fresh.get_cookie("session")
    assert cookie and cookie.value
    server = make_server("127.0.0.1", 0, app.app.wsgi_app, threaded=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        runner = Path(__file__).parent / "e2e" / "run_20261020_zone2_first_entry_browser.mjs"
        check = subprocess.run(
            ["node", str(runner)],
            input=json.dumps({
                "origin": f"http://127.0.0.1:{server.server_port}",
                "sessionCookie": cookie.value,
            }),
            capture_output=True, text=True, encoding="utf-8", timeout=80,
            cwd=Path(__file__).resolve().parent.parent,
            env={**os.environ, "GO_P2_ZONE2_TOUCH":
                 "1" if input_mode == "chrome_tablet_touch" else "0"},
        )
        assert check.returncode == 0, check.stderr[-1800:] + check.stdout[-1000:]
        assert "REAL_E9_ZONE2_WGO_ANSWER_PASS" in check.stdout
    finally:
        server.shutdown()
        worker.join(timeout=5)
    with app.get_db() as conn:
        after_xp = conn.execute(
            "SELECT xp FROM user_stats WHERE user_id=?", (lord.UID,)
        ).fetchone()["xp"]
        assert after_xp > before_xp
    relogged = app.app.test_client()
    with relogged.session_transaction() as s:
        s["user_id"] = lord.UID
        s["username"] = "p1-lord-disposable"
    persisted = lord.checked_json(relogged.get("/api/adventure/bootstrap"))
    zone2 = next(z for z in persisted["zones"] if z["key"] == ZONE2)
    assert zone2["correct_count"] >= 2
    assert zone2["unlocked"] is True
    assert zone2["cleared"] is False
    assert zone2["zone_authority_stars"] == 0
