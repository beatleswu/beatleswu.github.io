"""P0-3: Guild answer counting must consume server-authoritative evidence.

The Production symptom: the current week held 323 ``guild_quest`` review rows
and 220 distinct correct user/question pairs, yet the Guild answer count did
not move, because the leaderboard's trusted-evidence boundary excludes
``guild_quest``.

That exclusion is correct and is preserved here.  On the public SRS transport
``source_context`` is a free-text client label and ``grade`` is a
client-supplied SM-2 scheduling signal, so a bare ``guild_quest`` row proves
nothing: any client could post ``grade=5`` for any question.  Widening the
allowlist would have made forged credit indistinguishable from real credit.

Instead the server judges the answer and writes a ``guild_quest:v1:``
envelope, and the leaderboard consumes only that.  The public request parser
rejects the prefix outright, so the envelope's presence is itself the proof
that the server settled the answer and confirmed Guild eligibility.
"""

from __future__ import annotations

import sqlite3

import pytest

import community_leaderboard_rewards as leaderboard_rewards
from guild_quest_answer_service import (
    GUILD_QUEST_JUDGE_VERSION,
    GUILD_QUEST_RESULT_SOURCE_PREFIX,
    GUILD_QUEST_SOURCE_CONTEXT,
    GuildQuestAnswerError,
    GuildQuestVerdictPersistenceError,
    build_guild_quest_verdict,
    decode_guild_quest_verdict,
    encode_guild_quest_verdict,
    judge_guild_quest_answer,
)
from map_battle_runtime import JudgeOutcome

QUEST_KEY = "life_death::LV3"

# A real judgeable question shape: explicit PL[B], one-move answer tree.
QUESTION = {
    "id": 5101,
    "topic": "quest-book",
    "content": "(;GM[1]FF[4]CA[UTF-8]SZ[19]PL[B]AB[dp]AW[pd](;B[dd]C[correct]))",
}

PERIOD_START = "2026-08-24T00:00:00"
PERIOD_END = "2026-08-31T00:00:00"


# --------------------------------------------------------------------------
# Server judging
# --------------------------------------------------------------------------


def test_correct_guild_answer_is_judged_pass_by_the_server():
    _, judge = judge_guild_quest_answer(
        {"moves": [{"action": "play", "x": 3, "y": 3}]},
        question=QUESTION,
        quest_key=QUEST_KEY,
    )
    assert judge.result == "CORRECT"
    assert judge.authoritative_grade == 5
    assert judge.judge_version == GUILD_QUEST_JUDGE_VERSION

    verdict = build_guild_quest_verdict(
        quest_key=QUEST_KEY, question_id=5101, judge=judge, guild_eligible=True
    )
    assert verdict["verdict"] == "AUTHORITATIVE_PASS"


def test_incorrect_guild_answer_is_judged_fail_by_the_server():
    _, judge = judge_guild_quest_answer(
        {"moves": [{"action": "play", "x": 15, "y": 15}]},
        question=QUESTION,
        quest_key=QUEST_KEY,
    )
    assert judge.result == "INCORRECT"
    assert judge.authoritative_grade == 0

    verdict = build_guild_quest_verdict(
        quest_key=QUEST_KEY, question_id=5101, judge=judge, guild_eligible=True
    )
    assert verdict["verdict"] == "AUTHORITATIVE_FAIL"


def test_a_verdict_requires_server_resolved_guild_eligibility():
    _, judge = judge_guild_quest_answer(
        {"moves": [{"action": "play", "x": 3, "y": 3}]},
        question=QUESTION,
        quest_key=QUEST_KEY,
    )
    with pytest.raises(GuildQuestVerdictPersistenceError):
        build_guild_quest_verdict(
            quest_key=QUEST_KEY, question_id=5101, judge=judge, guild_eligible=False
        )


def test_client_cannot_smuggle_authority_fields_into_the_answer():
    for forged in ("player_color", "authoritative_grade", "verdict", "quest_key"):
        with pytest.raises(GuildQuestAnswerError) as excinfo:
            judge_guild_quest_answer(
                {"moves": [{"action": "play", "x": 3, "y": 3}], forged: "B"},
                question=QUESTION,
                quest_key=QUEST_KEY,
            )
        assert excinfo.value.code == "forbidden_answer_field"


def test_unjudgeable_question_fails_closed_rather_than_granting_credit():
    with pytest.raises(GuildQuestAnswerError) as excinfo:
        judge_guild_quest_answer(
            {"moves": [{"action": "play", "x": 3, "y": 3}]},
            question={"id": 9, "content": "(;GM[1]SZ[19]AB[dp](;B[dd]))"},
            quest_key=QUEST_KEY,
        )
    assert excinfo.value.code == "judge_unavailable"
    assert excinfo.value.status == 503


def test_envelope_round_trips_and_rejects_tampering():
    verdict = build_guild_quest_verdict(
        quest_key=QUEST_KEY,
        question_id=5101,
        judge=JudgeOutcome("CORRECT", 5, GUILD_QUEST_JUDGE_VERSION, "answer_tree_leaf"),
        guild_eligible=True,
    )
    encoded = encode_guild_quest_verdict(verdict)
    assert encoded.startswith(GUILD_QUEST_RESULT_SOURCE_PREFIX)
    assert decode_guild_quest_verdict(encoded) == verdict

    assert decode_guild_quest_verdict(GUILD_QUEST_SOURCE_CONTEXT) is None
    assert decode_guild_quest_verdict(GUILD_QUEST_RESULT_SOURCE_PREFIX) is None
    assert decode_guild_quest_verdict(GUILD_QUEST_RESULT_SOURCE_PREFIX + "{}") is None
    # A PASS claim whose grade does not match is internally inconsistent.
    assert (
        decode_guild_quest_verdict(
            GUILD_QUEST_RESULT_SOURCE_PREFIX
            + '{"authoritative_grade":0,"judge_version":"%s","question_id":5101,'
            '"quest_key":"%s","reason_code":"x","schema":"guild_quest_verdict_v1",'
            '"verdict":"AUTHORITATIVE_PASS"}' % (GUILD_QUEST_JUDGE_VERSION, QUEST_KEY)
        )
        is None
    )


# --------------------------------------------------------------------------
# Leaderboard admission
# --------------------------------------------------------------------------


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE users(
            id INTEGER PRIMARY KEY, username TEXT NOT NULL, nickname TEXT,
            plan TEXT DEFAULT 'free', is_admin INTEGER DEFAULT 0
        );
        CREATE TABLE review_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, question_id INTEGER NOT NULL,
            grade INTEGER NOT NULL, reviewed_at TEXT NOT NULL,
            source TEXT, source_context TEXT
        );
        CREATE TABLE user_stats(user_id INTEGER PRIMARY KEY, rank_level TEXT);
        CREATE TABLE player_appearance(
            user_id INTEGER PRIMARY KEY, character_key TEXT,
            combat_armor TEXT, combat_weapon TEXT, combat_cape TEXT,
            combat_offhand TEXT, combat_hat TEXT, combat_pet TEXT,
            combat_aura TEXT
        );
        """
    )
    return conn


def _add_user(conn, user_id: int) -> None:
    conn.execute(
        "INSERT INTO users(id, username, nickname) VALUES (?, ?, ?)",
        (user_id, f"user_{user_id}", f"User {user_id}"),
    )
    conn.execute(
        "INSERT INTO user_stats(user_id, rank_level) VALUES (?, 'LV1')", (user_id,)
    )
    conn.execute(
        "INSERT INTO player_appearance(user_id, character_key) VALUES (?, 'apprentice')",
        (user_id,),
    )


def _guild_envelope(
    *, question_id: int, verdict: str = "AUTHORITATIVE_PASS", grade: int = 5,
    judge_version: str = GUILD_QUEST_JUDGE_VERSION, quest_key: str = QUEST_KEY,
) -> str:
    return encode_guild_quest_verdict({
        "schema": "guild_quest_verdict_v1",
        "quest_key": quest_key,
        "question_id": question_id,
        "verdict": verdict,
        "authoritative_grade": grade,
        "judge_version": judge_version,
        "reason_code": "answer_tree_leaf",
    })


def _review(conn, *, user_id, question_id, reviewed_at, grade=5,
            source_context=None, source=None) -> None:
    conn.execute(
        "INSERT INTO review_log(user_id, question_id, grade, reviewed_at,"
        " source_context, source) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, question_id, grade, reviewed_at, source_context, source),
    )


def _score(conn, user_id: int) -> int:
    rows = leaderboard_rewards.fetch_leaderboard_participant_rows(
        conn, PERIOD_START, PERIOD_END
    )
    for row in rows:
        if int(row["id"]) == user_id:
            return int(row["score"])
    return 0


def test_legitimate_guild_answer_increments_the_count():
    conn = _db()
    _add_user(conn, 11)
    _review(
        conn,
        user_id=11,
        question_id=5101,
        reviewed_at="2026-08-26T10:00:00",
        grade=0,  # the client scheduling grade is irrelevant
        source_context=_guild_envelope(question_id=5101),
    )
    assert _score(conn, 11) == 1


def test_incorrect_guild_answer_does_not_count():
    conn = _db()
    _add_user(conn, 12)
    _review(
        conn,
        user_id=12,
        question_id=5101,
        reviewed_at="2026-08-26T10:00:00",
        grade=5,  # client claims success; the server verdict says otherwise
        source_context=_guild_envelope(
            question_id=5101, verdict="AUTHORITATIVE_FAIL", grade=0
        ),
    )
    assert _score(conn, 12) == 0


def test_duplicate_user_question_does_not_double_count():
    conn = _db()
    _add_user(conn, 13)
    for at in ("2026-08-26T10:00:00", "2026-08-27T11:00:00", "2026-08-28T12:00:00"):
        _review(
            conn,
            user_id=13,
            question_id=5101,
            reviewed_at=at,
            source_context=_guild_envelope(question_id=5101),
        )
    _review(
        conn,
        user_id=13,
        question_id=5102,
        reviewed_at="2026-08-26T13:00:00",
        source_context=_guild_envelope(question_id=5102),
    )
    assert _score(conn, 13) == 2


def test_arbitrary_source_context_cannot_forge_credit():
    """The historical Production shape: a bare client label earns nothing."""
    conn = _db()
    _add_user(conn, 14)
    for question_id, context in (
        (5101, GUILD_QUEST_SOURCE_CONTEXT),
        (5102, "guild_quest"),
        (5103, "guild"),
        (5104, "practice"),
        (5105, GUILD_QUEST_RESULT_SOURCE_PREFIX + "not-json"),
        (5106, GUILD_QUEST_RESULT_SOURCE_PREFIX + '{"verdict":"AUTHORITATIVE_PASS"}'),
    ):
        _review(
            conn,
            user_id=14,
            question_id=question_id,
            reviewed_at="2026-08-26T10:00:00",
            grade=5,
            source_context=context,
        )
    assert _score(conn, 14) == 0


def test_unknown_judge_version_cannot_forge_credit():
    conn = _db()
    _add_user(conn, 15)
    _review(
        conn,
        user_id=15,
        question_id=5101,
        reviewed_at="2026-08-26T10:00:00",
        source_context=_guild_envelope(question_id=5101, judge_version="my-own-judge"),
    )
    assert _score(conn, 15) == 0


def test_envelope_question_id_must_match_its_row():
    """A copied envelope cannot be replayed onto a different question."""
    conn = _db()
    _add_user(conn, 16)
    _review(
        conn,
        user_id=16,
        question_id=5999,
        reviewed_at="2026-08-26T10:00:00",
        source_context=_guild_envelope(question_id=5101),
    )
    assert _score(conn, 16) == 0


def test_wrong_user_cannot_forge_credit():
    """Credit follows the row's authenticated owner, never the envelope."""
    conn = _db()
    _add_user(conn, 17)
    _add_user(conn, 18)
    _review(
        conn,
        user_id=17,
        question_id=5101,
        reviewed_at="2026-08-26T10:00:00",
        source_context=_guild_envelope(question_id=5101),
    )
    assert _score(conn, 17) == 1
    assert _score(conn, 18) == 0


def test_week_boundary_remains_correct():
    conn = _db()
    _add_user(conn, 19)
    for at in ("2026-08-23T23:59:59", "2026-08-31T00:00:00"):
        _review(
            conn,
            user_id=19,
            question_id=5101,
            reviewed_at=at,
            source_context=_guild_envelope(question_id=5101),
        )
    assert _score(conn, 19) == 0

    _review(
        conn,
        user_id=19,
        question_id=5102,
        reviewed_at="2026-08-24T00:00:00",
        source_context=_guild_envelope(question_id=5102),
    )
    assert _score(conn, 19) == 1


def test_existing_leaderboard_sources_still_work_alongside_guild():
    conn = _db()
    _add_user(conn, 20)
    _review(
        conn,
        user_id=20,
        question_id=6001,
        reviewed_at="2026-08-25T09:00:00",
        grade=5,
        source_context="mbv1:settled-1",
    )
    _review(
        conn,
        user_id=20,
        question_id=6002,
        reviewed_at="2026-08-25T09:10:00",
        grade=4,
        source="rt:legacy",
    )
    assert _score(conn, 20) == 2

    _review(
        conn,
        user_id=20,
        question_id=6003,
        reviewed_at="2026-08-25T09:20:00",
        source_context=_guild_envelope(question_id=6003),
    )
    assert _score(conn, 20) == 3


def test_guild_and_trusted_evidence_for_one_question_count_once():
    conn = _db()
    _add_user(conn, 21)
    _review(
        conn,
        user_id=21,
        question_id=6100,
        reviewed_at="2026-08-25T09:00:00",
        grade=5,
        source_context="mbv1:settled-9",
    )
    _review(
        conn,
        user_id=21,
        question_id=6100,
        reviewed_at="2026-08-26T09:00:00",
        source_context=_guild_envelope(question_id=6100),
    )
    assert _score(conn, 21) == 1


def test_leaderboard_does_not_judge():
    """The leaderboard only decodes a settled verdict; it never judges."""
    import inspect

    source = inspect.getsource(leaderboard_rewards._fetch_admitted_guild_quest_evidence)
    assert "decode_guild_quest_verdict" in source
    for banned in ("judge_map_battle_answer", "canonicalize_answer", "accepted_moves"):
        assert banned not in source
