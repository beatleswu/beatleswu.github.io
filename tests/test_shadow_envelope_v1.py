from __future__ import annotations

import json
from pathlib import Path

import pytest

import app as app_module
import shadow_judging
from puzzle_identity import IdentityResolution


DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "planning" / "shadow_event_envelope_v1.md"


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []


class _FakeConn:
    def __init__(self, row=None, query_map=None):
        self.row = row
        self.query_map = query_map or {}
        self.executed = []
        self.committed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        for needle, result in self.query_map.items():
            if needle in sql:
                return _FakeResult(result)
        if "FROM rating_test_sessions" in sql:
            return _FakeResult(self.row)
        return _FakeResult()

    def commit(self):
        self.committed = True


class _FakeConnCtx:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _FriendRouteConn:
    def __init__(self, challenge_row):
        self.challenge_row = challenge_row
        self.executed = []
        self.committed = False
        self._count_calls = 0

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if "FROM friend_challenges WHERE id=?" in sql:
            return _FakeResult(self.challenge_row)
        if "SELECT 1 FROM friend_challenge_answers" in sql:
            return _FakeResult(None)
        if "SELECT COUNT(*) FROM friend_challenge_answers" in sql:
            self._count_calls += 1
            return _FakeResult((1,) if self._count_calls == 1 else (0,))
        return _FakeResult()

    def commit(self):
        self.committed = True


@pytest.fixture()
def app():
    return app_module.app


def _read_event(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8").splitlines()[0])


def _write_success_event(tmp_path: Path, *, sgf_text: str = "(;SZ[19];B[aa])", moves=None):
    event_path = tmp_path / "shadow_events.jsonl"
    if moves is None:
        moves = [{"x": 0, "y": 0}]

    with app_module.app.test_request_context(
        "/api/rating_test/answer",
        headers={"X-Request-Id": "req-123"},
    ):
        shadow_judging.observe_rating_test(
            question_id=29830,
            session_id="sess-1",
            transform_idx=4,
            sgf_transformed=sgf_text,
            moves=moves,
            client_correct=True,
            final_correct=True,
            katago_best_move="Q16",
        )

    return _read_event(event_path)


def test_shadow_envelope_doc_has_v1_contract() -> None:
    text = DOC_PATH.read_text(encoding="utf-8").lower()

    for phrase in [
        "production shadow event envelope v3",
        "schema_version",
        "route",
        "request_id",
        "latency_ms",
        "entry_point",
        "parser_status",
        "parser_failure_reason",
        "exception_class",
        "exception_message",
        "shadow-v3",
        "supported routes",
        "/api/daily-challenge/submit",
        "/api/challenges/friend/<int:cid>/answer",
    ]:
        assert phrase in text


def test_successful_shadow_event_emits_new_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_JUDGING_ENABLED", "1")
    monkeypatch.setenv("SHADOW_EVENTS_PATH", str(tmp_path / "shadow_events.jsonl"))

    with app_module.app.test_request_context(
        "/api/rating_test/answer",
        headers={"X-Request-Id": "req-123"},
    ):
        shadow_judging.observe_rating_test(
            question_id=29830,
            session_id="sess-1",
            transform_idx=4,
            sgf_transformed="(;SZ[19];B[aa])",
            moves=[{"x": 0, "y": 0}],
            client_correct=True,
            final_correct=True,
            katago_best_move="Q16",
        )

    event = _read_event(tmp_path / "shadow_events.jsonl")

    assert event["schema_version"] == "shadow-v4"
    assert event["route"] == "/api/rating_test/answer"
    assert event["entry_point"] == "rating_test"
    assert event["request_id"] == "req-123"
    assert event["latency_ms"] >= 0
    assert event["parser_status"] == "ok"
    assert event["parser_failure_reason"] == ""
    assert event["exception_class"] == ""
    assert event["exception_message"] == ""
    assert event["user_facing_judgement_changed"] is False


def test_parser_failure_marks_failed_and_populates_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_JUDGING_ENABLED", "1")
    monkeypatch.setenv("SHADOW_EVENTS_PATH", str(tmp_path / "shadow_events.jsonl"))

    with app_module.app.test_request_context("/api/rating_test/answer"):
        shadow_judging.observe_rating_test(
            question_id=29830,
            session_id="sess-1",
            transform_idx=4,
            sgf_transformed="not an sgf",
            moves=[{"x": 0, "y": 0}],
            client_correct=True,
            final_correct=True,
            katago_best_move="Q16",
        )

    event = _read_event(tmp_path / "shadow_events.jsonl")

    assert event["route"] == "/api/rating_test/answer"
    assert event["entry_point"] == "rating_test"
    assert event["parser_status"] == "failed"
    assert event["parser_failure_reason"]
    assert event["exception_class"] == ""
    assert event["exception_message"] == ""


def test_exception_path_records_exception_fields_and_sanitizes_message(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_JUDGING_ENABLED", "1")
    monkeypatch.setenv("SHADOW_EVENTS_PATH", str(tmp_path / "shadow_events.jsonl"))
    monkeypatch.setattr(
        shadow_judging,
        "_shadow_verdict",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("token=abc cookie=def header=ghi")
        ),
    )

    with app_module.app.test_request_context("/api/rating_test/answer"):
        shadow_judging.observe_rating_test(
            question_id=29830,
            session_id="sess-1",
            transform_idx=4,
            sgf_transformed="(;SZ[19];B[aa])",
            moves=[{"x": 0, "y": 0}],
            client_correct=True,
            final_correct=True,
            katago_best_move="Q16",
        )

    event = _read_event(tmp_path / "shadow_events.jsonl")

    assert event["exception_class"] == "ValueError"
    assert "token=abc" not in event["exception_message"].lower()
    assert "cookie=def" not in event["exception_message"].lower()
    assert "header=ghi" not in event["exception_message"].lower()
    # E2.4A: a raised exception during Shadow evaluation is an explicit,
    # observable failure — it must not be reported as parser_status "ok".
    assert event["parser_status"] == "failed"
    assert event["shadow_judgement"] == "error"


def test_latency_and_request_id_are_present(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_JUDGING_ENABLED", "1")
    monkeypatch.setenv("SHADOW_EVENTS_PATH", str(tmp_path / "shadow_events.jsonl"))

    with app_module.app.test_request_context("/api/rating_test/answer"):
        shadow_judging.observe_rating_test(
            question_id=29830,
            session_id="sess-1",
            transform_idx=4,
            sgf_transformed="(;SZ[19];B[aa])",
            moves=[{"x": 0, "y": 0}],
            client_correct=True,
            final_correct=True,
            katago_best_move="Q16",
        )

    event = _read_event(tmp_path / "shadow_events.jsonl")

    assert isinstance(event["request_id"], str)
    assert event["request_id"]
    assert event["latency_ms"] >= 0


def test_feature_flag_off_emits_no_shadow_event(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_JUDGING_ENABLED", "0")
    monkeypatch.setenv("SHADOW_EVENTS_PATH", str(tmp_path / "shadow_events.jsonl"))

    with app_module.app.test_request_context("/api/rating_test/answer"):
        shadow_judging.observe_rating_test(
            question_id=29830,
            session_id="sess-1",
            transform_idx=4,
            sgf_transformed="(;SZ[19];B[aa])",
            moves=[{"x": 0, "y": 0}],
            client_correct=True,
            final_correct=True,
            katago_best_move="Q16",
        )

    assert not (tmp_path / "shadow_events.jsonl").exists()


def test_daily_challenge_route_emits_missing_move_parser_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_JUDGING_ENABLED", "1")
    monkeypatch.setenv("SHADOW_EVENTS_PATH", str(tmp_path / "shadow_events.jsonl"))

    with app_module.app.test_request_context("/api/daily-challenge/submit"):
        shadow_judging.observe_answer_route(
            entry_point="daily_challenge",
            question_id=301,
            session_id="daily:7:2026-07-11",
            transform_idx=0,
            sgf_transformed="",
            moves=None,
            client_correct=False,
            final_correct=False,
            katago_best_move="",
        )

    event = _read_event(tmp_path / "shadow_events.jsonl")

    assert event["route"] == "/api/daily-challenge/submit"
    assert event["entry_point"] == "daily_challenge"
    assert event["schema_version"] == "shadow-v4"
    assert event["parser_status"] == "failed"
    assert event["parser_failure_reason"] == "missing canonical moves"
    assert event["shadow_judgement"] == "unsupported"
    assert event["user_facing_judgement_changed"] is False


def test_friend_challenge_route_emits_missing_move_parser_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_JUDGING_ENABLED", "1")
    monkeypatch.setenv("SHADOW_EVENTS_PATH", str(tmp_path / "shadow_events.jsonl"))

    with app_module.app.test_request_context("/api/challenges/friend/9/answer"):
        shadow_judging.observe_answer_route(
            entry_point="friend_challenge",
            question_id=301,
            session_id="friend:9:7",
            transform_idx=0,
            sgf_transformed="",
            moves=None,
            client_correct=True,
            final_correct=True,
            katago_best_move="",
        )

    event = _read_event(tmp_path / "shadow_events.jsonl")

    assert event["route"] == "/api/challenges/friend/9/answer"
    assert event["entry_point"] == "friend_challenge"
    assert event["schema_version"] == "shadow-v4"
    assert event["parser_status"] == "failed"
    assert event["parser_failure_reason"] == "missing canonical moves"
    assert event["shadow_judgement"] == "unsupported"
    assert event["user_facing_judgement_changed"] is False


def test_rating_test_route_legacy_response_is_unchanged_with_shadow_hook(
    client, monkeypatch
):
    row = {
        "status": "in_progress",
        "user_id": 7,
        "current_question_id": 123,
        "current_question_token": "tok-123",
        "cur_rating": 1500.0,
        "init_rating": 1500.0,
        "prior_sd": 300.0,
        "round": 1,
        "answers": json.dumps([{"q_id": 123}]),
        "current_question_role": "regular",
        "bank_version": "v1",
        "algorithm_version": "algo-1",
        "trigger": "regular",
    }
    conn = _FakeConn(row)

    monkeypatch.setattr(app_module, "get_db", lambda: _FakeConnCtx(conn))
    monkeypatch.setattr(app_module, "_ensure_rt_pool", lambda: None)
    monkeypatch.setattr(
        app_module,
        "_RT_POOL",
        [
            {
                "id": 123,
                "content": "(;SZ[19];B[aa])",
                "discipline": "tesuji",
                "source_group": "source-a",
                "rating": 1500.0,
                "katago_best_move": "Q16",
            },
            {
                "id": 123,
                "content": "(;SZ[19];B[bb])",
                "discipline": "tesuji",
                "source_group": "source-b",
                "rating": 1500.0,
                "katago_best_move": "R16",
            },
        ],
    )
    monkeypatch.setattr(app_module, "_rt_server_verify", lambda pool_q, sid, moves: True)
    monkeypatch.setattr(app_module, "_rt_transform_idx", lambda sid, qid: 0)
    monkeypatch.setattr(app_module, "_transform_sgf", lambda content, idx: content)
    monkeypatch.setattr(app_module, "_compute_streak", lambda answers, correct: 3)
    monkeypatch.setattr(app_module, "_rt_estimate", lambda estimate_input, prior_mean, prior_sd: (1550.0, 42.0))
    monkeypatch.setattr(app_module, "_RT_MAX_ROUNDS", 1)
    monkeypatch.setattr(app_module, "_rt_converged", lambda answers, prior_mean, prior_sd: False)
    monkeypatch.setattr(app_module, "_rt_recent_seen_ids", lambda conn, user_id, exclude_sid=None: set())
    monkeypatch.setattr(app_module, "_rt_desired_question_role", lambda *args, **kwargs: "regular")
    monkeypatch.setattr(app_module, "_pick_question", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, "_strip_question", lambda q, sid, token: q)
    monkeypatch.setattr(app_module, "_rating_to_rank", lambda value: "kyu")
    monkeypatch.setattr(app_module, "_apply_placement_adventure_unlock", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, "_finalize_placement", lambda *args, **kwargs: None)

    with client.session_transaction() as sess:
        sess["user_id"] = 7

    identity_calls = []
    canonical_puzzle_id = "00000000-0000-4000-8000-000000000001"
    monkeypatch.setattr(
        app_module,
        "_resolve_shadow_puzzle_identity",
        lambda **kwargs: (
            identity_calls.append(kwargs)
            or IdentityResolution(canonical_puzzle_id, False)
        ),
    )

    off_calls = []
    monkeypatch.setattr(shadow_judging, "is_enabled", lambda: False)
    monkeypatch.setattr(
        shadow_judging,
        "observe_rating_test",
        lambda **kwargs: off_calls.append(kwargs),
    )
    off_response = client.post(
        "/api/rating_test/answer",
        json={
            "session_id": "sess-1",
            "question_id": 123,
            "question_token": "tok-123",
            "moves": [{"x": 0, "y": 0}],
            "correct": True,
            "response_ms": 15,
        },
    )

    on_calls = []
    monkeypatch.setattr(shadow_judging, "is_enabled", lambda: True)
    monkeypatch.setattr(
        shadow_judging,
        "observe_rating_test",
        lambda **kwargs: on_calls.append(kwargs),
    )
    on_response = client.post(
        "/api/rating_test/answer",
        json={
            "session_id": "sess-1",
            "question_id": 123,
            "question_token": "tok-123",
            "moves": [{"x": 0, "y": 0}],
            "correct": True,
            "response_ms": 15,
        },
    )

    assert off_response.status_code == 200
    assert on_response.status_code == 200
    assert off_response.get_json() == on_response.get_json()
    assert off_calls == []
    assert len(on_calls) == 1
    assert identity_calls == [{"legacy_question_id": 123}]
    assert on_calls[0]["canonical_puzzle_id"] == canonical_puzzle_id
    assert on_calls[0]["invalid_identity"] is False


def test_daily_challenge_route_legacy_response_is_unchanged_with_shadow_hook(
    client, monkeypatch
):
    conn = _FakeConn(
        query_map={
            "SELECT id FROM daily_challenge_log": None,
            "SELECT COUNT(*) as total, SUM(correct) as cnt": {
                "total": 1,
                "cnt": 0,
            },
        }
    )

    monkeypatch.setattr(app_module, "get_db", lambda: _FakeConnCtx(conn))
    monkeypatch.setattr(
        app_module,
        "get_or_create_daily_challenge",
        lambda today: {"question_id": 301},
    )
    monkeypatch.setattr(app_module, "check_and_award_daily", lambda *args, **kwargs: [])
    monkeypatch.setattr(app_module, "get_daily_submit_streak", lambda *args, **kwargs: 0)
    monkeypatch.setattr(app_module, "give_daily_appearance", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        app_module,
        "_load_questions",
        lambda: [{"id": 301, "content": "(;SZ[19];B[aa])", "accepted_moves": []}],
    )

    with client.session_transaction() as sess:
        sess["user_id"] = 7

    identity_calls = []
    canonical_puzzle_id = "00000000-0000-4000-9000-000000000002"
    monkeypatch.setattr(
        app_module,
        "_resolve_shadow_puzzle_identity",
        lambda **kwargs: (
            identity_calls.append(kwargs)
            or IdentityResolution(canonical_puzzle_id, False)
        ),
    )

    off_calls = []
    monkeypatch.setattr(shadow_judging, "is_enabled", lambda: False)
    monkeypatch.setattr(
        shadow_judging,
        "observe_answer_route",
        lambda **kwargs: off_calls.append(kwargs),
    )
    off_response = client.post(
        "/api/daily-challenge/submit",
        json={"correct": False},
    )

    on_calls = []
    monkeypatch.setattr(shadow_judging, "is_enabled", lambda: True)
    monkeypatch.setattr(
        shadow_judging,
        "observe_answer_route",
        lambda **kwargs: on_calls.append(kwargs),
    )
    on_response = client.post(
        "/api/daily-challenge/submit",
        json={"correct": False},
    )

    assert off_response.status_code == 200
    assert on_response.status_code == 200
    assert off_response.get_json() == on_response.get_json()
    assert off_calls == []
    assert len(on_calls) == 1
    assert identity_calls == [{"legacy_question_id": 301}]
    assert on_calls[0]["canonical_puzzle_id"] == canonical_puzzle_id
    assert on_calls[0]["invalid_identity"] is False


def test_friend_challenge_route_legacy_response_is_unchanged_with_shadow_hook(
    client, monkeypatch
):
    challenge_row = {
        "id": 9,
        "from_user": 7,
        "to_user": 8,
        "status": "active",
        "question_ids": json.dumps([301]),
        "num_questions": 2,
    }
    monkeypatch.setattr(
        app_module,
        "get_db",
        lambda: _FakeConnCtx(_FriendRouteConn(challenge_row)),
    )
    monkeypatch.setattr(
        app_module,
        "_load_questions",
        lambda: [{"id": 301, "content": "(;SZ[19];B[aa])", "accepted_moves": []}],
    )

    with client.session_transaction() as sess:
        sess["user_id"] = 7

    identity_calls = []
    monkeypatch.setattr(
        app_module,
        "_resolve_shadow_puzzle_identity",
        lambda **kwargs: (
            identity_calls.append(kwargs)
            or IdentityResolution(None, True)
        ),
    )

    off_calls = []
    monkeypatch.setattr(shadow_judging, "is_enabled", lambda: False)
    monkeypatch.setattr(
        shadow_judging,
        "observe_answer_route",
        lambda **kwargs: off_calls.append(kwargs),
    )
    off_response = client.post(
        "/api/challenges/friend/9/answer",
        json={"question_id": 301, "correct": True},
    )

    on_calls = []
    monkeypatch.setattr(shadow_judging, "is_enabled", lambda: True)
    monkeypatch.setattr(
        shadow_judging,
        "observe_answer_route",
        lambda **kwargs: on_calls.append(kwargs),
    )
    on_response = client.post(
        "/api/challenges/friend/9/answer",
        json={"question_id": 301, "correct": True},
    )

    assert off_response.status_code == 200
    assert on_response.status_code == 200
    assert off_response.get_json() == on_response.get_json()
    assert off_calls == []
    assert len(on_calls) == 1
    assert identity_calls == [{"legacy_question_id": 301}]
    assert on_calls[0]["canonical_puzzle_id"] is None
    assert on_calls[0]["invalid_identity"] is True
