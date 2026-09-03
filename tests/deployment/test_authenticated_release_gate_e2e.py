"""Authenticated production-like E2E release gate over a disposable PostgreSQL.

Why this exists
---------------
Two P0s reached Production while the governed gate stayed green:

* the Guild answer-write outage -- every Guild answer returned 503 and persisted
  nothing, yet no gated test ever issued an authenticated POST to
  ``/api/srs/review``;
* the LC020 identity-read latency regression -- per-ID query fanout that no unit
  test measured.

Both share a shape: the unit suites exercised helpers directly, so an authenticated
request travelling the real Flask -> app -> PostgreSQL stack was never executed
inside the release gate. This module closes that by driving the actual routes with
a real session against a throwaway PostgreSQL, and asserting DURABLE DATABASE
STATE rather than HTTP 200.

Scope and safety
----------------
Disposable infrastructure only. Never touches Production, never reads secrets.
Skips cleanly when Docker is unavailable so the gate stays runnable offline.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import types

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
TESTS_DIR = REPO_ROOT / "tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))


USER_ID = 880101
QIDS = list(range(880001, 880013))
TOPIC = "1圍棋新手村"
# An ordinary problem SGF: board size plus a first move, no PL[] property.
# This is the exact shape that produced the Guild P0.
ORDINARY_SGF = "(;GM[1]FF[4]SZ[19]AB[dd][pp]AW[dp][pd];B[qf])"
CORRECT_MOVE = {"action": "play", "x": 16, "y": 5}   # B qf
WRONG_MOVE = {"action": "play", "x": 0, "y": 0}


def _install_app_import_stubs():
    for name, attrs in (
        ("katago_explain", {"KataGoExplainer": type("K", (), {})}),
        ("explain_overrides", {"get_override": lambda *a, **k: None}),
        ("question_taxonomy", {"get_taxonomy": lambda *a, **k: {}}),
        ("monster_taxonomy", {"get_monster_taxonomy": lambda *a, **k: {},
                              "mark_encounters": lambda *a, **k: None}),
        ("chapter_i18n", {"localize_topic": lambda *a, **k: "",
                          "localize_level": lambda *a, **k: ""}),
        ("backend_i18n", {"badge_en": lambda *a, **k: "",
                          "skill_node_en": lambda *a, **k: "",
                          "title_en": lambda *a, **k: ""}),
    ):
        if name not in sys.modules:
            module = types.ModuleType(name)
            for key, value in attrs.items():
                setattr(module, key, value)
            sys.modules[name] = module


def _questions():
    return [
        {
            "id": qid,
            "enabled": True,
            "topic": TOPIC,
            "level": "L1",
            "difficulty": "easy",
            "discipline": "whole_board",
            "free": True,
            "content": ORDINARY_SGF,
        }
        for qid in QIDS
    ]


@pytest.fixture(scope="module")
def authenticated_stack():
    """Boot the real app against a disposable PostgreSQL with a live session."""

    from postgres_test_harness import disposable_postgres

    with disposable_postgres(name_prefix="go-odyssey-auth-e2e") as database:
        os.environ["DATABASE_URL"] = database["database_url"]
        os.environ["QUESTIONS_JSON_PATH"] = str(REPO_ROOT / "questions.json")
        _install_app_import_stubs()

        import app as app_module

        from migrations.sgf_admin_workbench_v1 import upgrade as upgrade_workbench

        with app_module.get_db() as conn:
            upgrade_workbench(conn)
            conn.commit()
        app_module.init_db()

        app_module._load_questions = _questions
        app_module._load_questions_fresh = _questions
        app_module.question_is_free = lambda q: True
        app_module.is_premium = lambda uid=None: True

        quest_key = app_module._quest_group_key(_questions()[0])
        segment = app_module._quest_segment_for_key(quest_key, True)
        assert segment, "quest segment must resolve for the synthetic corpus"

        with app_module.get_db() as conn:
            conn.execute(
                "INSERT INTO users(id,username,password_hash,created_at) "
                "VALUES(?,?,?,?) ON CONFLICT DO NOTHING",
                (USER_ID, "auth_e2e_user", "x", "2026-09-03T00:00:00"),
            )
            conn.execute(
                "INSERT INTO quest_accepted(user_id,quest_key,accepted_at) "
                "VALUES(?,?,?) ON CONFLICT DO NOTHING",
                (USER_ID, segment["quest_key"], "2026-09-03T00:00:00"),
            )
            conn.commit()

        app_module.app.config.update(TESTING=True)
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = USER_ID
            session["username"] = "auth_e2e_user"

        yield {
            "app": app_module,
            "client": client,
            "quest_key": segment["quest_key"],
            "question_ids": segment["question_ids"],
        }


def _review_log_rows(app_module, question_id=None):
    with app_module.get_db() as conn:
        if question_id is None:
            return conn.execute(
                "SELECT COUNT(*) FROM review_log WHERE user_id=?", (USER_ID,)
            ).fetchone()[0]
        return conn.execute(
            "SELECT COUNT(*) FROM review_log WHERE user_id=? AND question_id=?",
            (USER_ID, question_id),
        ).fetchone()[0]


def _source_contexts(app_module, question_id):
    with app_module.get_db() as conn:
        return [
            str(row[0])
            for row in conn.execute(
                "SELECT source_context FROM review_log "
                "WHERE user_id=? AND question_id=? ORDER BY id",
                (USER_ID, question_id),
            ).fetchall()
        ]


# ---------------------------------------------------------------------------
# Authenticated read paths
# ---------------------------------------------------------------------------
def test_authenticated_home_shell_is_served(authenticated_stack):
    """AUTHENTICATED_HOME."""

    response = authenticated_stack["client"].get("/")
    assert response.status_code == 200


def test_authenticated_adventure_bootstrap(authenticated_stack):
    """AUTHENTICATED_ADVENTURE -- the aggregate read that carried the LC020 cost."""

    response = authenticated_stack["client"].get("/api/adventure/bootstrap")
    assert response.status_code == 200, response.data[:400]
    payload = response.get_json()
    assert isinstance(payload, dict)


def test_authenticated_srs_due_read(authenticated_stack):
    """AUTHENTICATED_SRS_READ."""

    response = authenticated_stack["client"].get("/api/srs/due")
    assert response.status_code == 200, response.data[:400]


# ---------------------------------------------------------------------------
# Authenticated write paths -- durable evidence, not HTTP 200
# ---------------------------------------------------------------------------
def test_ordinary_srs_answer_is_durably_persisted(authenticated_stack):
    """AUTHENTICATED_SRS_WRITE + DURABLE_POSTGRES_EVIDENCE."""

    app_module = authenticated_stack["app"]
    qid = authenticated_stack["question_ids"][5]
    before = _review_log_rows(app_module, qid)

    response = authenticated_stack["client"].post(
        "/api/srs/review",
        json={
            "question_id": qid,
            "grade": 5,
            "unit_name": None,
            "unit_done": False,
            "source_context": "practice",
            "submission_id": "e2e-ordinary-1",
        },
    )
    assert response.status_code == 200, response.data[:400]
    assert response.get_json().get("ok") is True
    assert _review_log_rows(app_module, qid) == before + 1, "answer was not durable"


def test_guild_answer_on_a_no_pl_question_is_durably_persisted(authenticated_stack):
    """AUTHENTICATED_GUILD_WRITE -- the exact production P0, end to end.

    Before the fix this returned 503 judge_unavailable and wrote nothing.
    """

    app_module = authenticated_stack["app"]
    qid = authenticated_stack["question_ids"][0]

    response = authenticated_stack["client"].post(
        "/api/srs/review",
        json={
            "question_id": qid,
            "grade": 5,
            "unit_name": None,
            "unit_done": False,
            "source_context": "guild_quest",
            "guild_answer": {"moves": [CORRECT_MOVE]},
            "guild_quest_key": authenticated_stack["quest_key"],
            "submission_id": "e2e-guild-correct-1",
        },
    )
    assert response.status_code == 200, response.data[:400]
    assert response.get_json().get("ok") is True
    assert _review_log_rows(app_module, qid) == 1, "Guild answer was not durable"

    contexts = _source_contexts(app_module, qid)
    assert contexts and contexts[0].startswith("guild_quest:v1:"), (
        "durable evidence must be the server-written envelope, not the client label"
    )
    assert contexts[0] != "guild_quest"


def test_guild_duplicate_submission_creates_no_second_row(authenticated_stack):
    """AUTHENTICATED_GUILD_IDEMPOTENCY -- replaying an id must not double-credit."""

    app_module = authenticated_stack["app"]
    qid = authenticated_stack["question_ids"][0]
    before = _review_log_rows(app_module, qid)

    response = authenticated_stack["client"].post(
        "/api/srs/review",
        json={
            "question_id": qid,
            "grade": 5,
            "unit_name": None,
            "unit_done": False,
            "source_context": "guild_quest",
            "guild_answer": {"moves": [CORRECT_MOVE]},
            "guild_quest_key": authenticated_stack["quest_key"],
            "submission_id": "e2e-guild-correct-1",
        },
    )
    assert response.status_code == 200, response.data[:400]
    assert _review_log_rows(app_module, qid) == before, "duplicate created a second row"


def test_guild_wrong_answer_is_judged_not_errored(authenticated_stack):
    """AUTHENTICATED_GUILD_WRONG_ANSWER -- a wrong move is a verdict, not a 503."""

    app_module = authenticated_stack["app"]
    qid = authenticated_stack["question_ids"][1]

    response = authenticated_stack["client"].post(
        "/api/srs/review",
        json={
            "question_id": qid,
            "grade": 5,
            "unit_name": None,
            "unit_done": False,
            "source_context": "guild_quest",
            "guild_answer": {"moves": [WRONG_MOVE]},
            "guild_quest_key": authenticated_stack["quest_key"],
            "submission_id": "e2e-guild-wrong-1",
        },
    )
    assert response.status_code == 200, response.data[:400]
    assert _review_log_rows(app_module, qid) == 1

    envelope = _source_contexts(app_module, qid)[0]
    assert envelope.startswith("guild_quest:v1:")
    decoded = json.loads(envelope[len("guild_quest:v1:"):])
    assert decoded["verdict"] == "AUTHORITATIVE_FAIL"
    assert decoded["authoritative_grade"] == 0


def test_guild_unjudgeable_question_still_fails_closed(authenticated_stack):
    """Fail-closed must survive the fix: no verdict, no row, for unresolvable content."""

    app_module = authenticated_stack["app"]
    qid = authenticated_stack["question_ids"][7]
    unresolvable = [
        dict(q, content="(;GM[1]SZ[19]AB[dp]AW[pd])") if q["id"] == qid else q
        for q in _questions()
    ]
    original = app_module._load_questions
    app_module._load_questions = lambda: unresolvable
    try:
        response = authenticated_stack["client"].post(
            "/api/srs/review",
            json={
                "question_id": qid,
                "grade": 5,
                "unit_name": None,
                "unit_done": False,
                "source_context": "guild_quest",
                "guild_answer": {"moves": [CORRECT_MOVE]},
                "guild_quest_key": authenticated_stack["quest_key"],
                "submission_id": "e2e-guild-unjudgeable-1",
            },
        )
    finally:
        app_module._load_questions = original

    assert response.status_code == 503, response.data[:400]
    assert response.get_json().get("error") == "judge_unavailable"
    assert _review_log_rows(app_module, qid) == 0, "fail-closed path must persist nothing"


def test_answer_then_next_question_flow(authenticated_stack):
    """The answer -> next-question loop the player actually experiences."""

    app_module = authenticated_stack["app"]
    qid = authenticated_stack["question_ids"][2]

    response = authenticated_stack["client"].post(
        "/api/srs/review",
        json={
            "question_id": qid,
            "grade": 5,
            "unit_name": None,
            "unit_done": False,
            "source_context": "guild_quest",
            "guild_answer": {"moves": [CORRECT_MOVE]},
            "guild_quest_key": authenticated_stack["quest_key"],
            "submission_id": "e2e-guild-flow-1",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    progress = payload.get("guild_progress")
    assert isinstance(progress, dict), "committed answer must carry its next-question projection"
    assert progress.get("quest_key") == authenticated_stack["quest_key"]

    assert authenticated_stack["client"].get("/api/srs/due").status_code == 200
