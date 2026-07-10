import json
from pathlib import Path

import pytest

import app as app_module
import shadow_judging


DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "planning" / "shadow_runtime_completion_e24.md"


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._row or []


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
def client():
    return app_module.app.test_client()


def _read_event(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    return json.loads(lines[-1])


def test_runtime_doc_mentions_canonical_pipeline():
    text = DOC_PATH.read_text(encoding="utf-8").lower()
    for phrase in [
        "canonical input pipeline",
        "shared compare flow",
        "/api/rating_test/answer",
        "/api/daily-challenge/submit",
        "/api/challenges/friend/<int:cid>/answer",
        "unsupported-route placeholders are no longer emitted",
    ]:
        assert phrase in text


def test_rating_shadow_success_event(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_JUDGING_ENABLED", "1")
    monkeypatch.setenv("SHADOW_EVENTS_PATH", str(tmp_path / "shadow_events.jsonl"))

    with app_module.app.test_request_context("/api/rating_test/answer", headers={"X-Request-Id": "req-rt"}):
        shadow_judging.observe_rating_test(
            question_id=101,
            session_id="sess-1",
            transform_idx=0,
            sgf_transformed="(;SZ[19];B[aa];W[ab];B[ac])",
            moves=[{"x": 0, "y": 0}, {"x": 0, "y": 2}],
            client_correct=True,
            final_correct=True,
            katago_best_move="A19",
        )

    event = _read_event(tmp_path / "shadow_events.jsonl")
    assert event["route"] == "/api/rating_test/answer"
    assert event["entry_point"] == "rating_test"
    assert event["parser_status"] == "ok"
    assert event["parser_failure_reason"] == ""
    assert event["shadow_judgement"] == "accept"


def test_daily_and_friend_use_shared_runtime_without_unsupported(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_JUDGING_ENABLED", "1")
    event_path = tmp_path / "shadow_events.jsonl"
    monkeypatch.setenv("SHADOW_EVENTS_PATH", str(event_path))

    with app_module.app.test_request_context("/api/daily-challenge/submit", headers={"X-Request-Id": "req-daily"}):
        shadow_judging.observe_answer_route(
            entry_point="daily_challenge",
            question_id=301,
            session_id="daily:7:2026-07-11",
            transform_idx=0,
            sgf_transformed="(;SZ[19];B[aa];W[ab];B[ac])",
            moves=None,
            client_correct=True,
            final_correct=True,
            katago_best_move="A19",
        )

    with app_module.app.test_request_context("/api/challenges/friend/9/answer", headers={"X-Request-Id": "req-friend"}):
        shadow_judging.observe_answer_route(
            entry_point="friend_challenge",
            question_id=301,
            session_id="friend:9:7",
            transform_idx=0,
            sgf_transformed="(;SZ[19];B[aa];W[ab];B[ac])",
            moves=None,
            client_correct=False,
            final_correct=False,
            katago_best_move="A19",
        )

    events = [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines()]
    assert len(events) == 2
    for event in events:
        assert event["schema_version"] == "shadow-v3"
        assert event["parser_failure_reason"] not in {
            "route unsupported: daily_challenge",
            "route unsupported: friend_challenge",
        }
        assert event["exception_class"] == ""
        assert event["exception_message"] == ""

    assert events[0]["parser_status"] == "ok"
    assert events[0]["shadow_judgement"] == "accept"
    assert events[1]["parser_status"] == "ok"
    assert events[1]["shadow_judgement"] in {"off_tree", "reject"}
    assert set(events[0]) == set(events[1])


def test_parser_failure_is_genuine_parse_issue(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_JUDGING_ENABLED", "1")
    monkeypatch.setenv("SHADOW_EVENTS_PATH", str(tmp_path / "shadow_events.jsonl"))

    with app_module.app.test_request_context("/api/daily-challenge/submit"):
        shadow_judging.observe_answer_route(
            entry_point="daily_challenge",
            question_id=301,
            session_id="daily:7:2026-07-11",
            transform_idx=0,
            sgf_transformed="not an sgf",
            moves=None,
            client_correct=True,
            final_correct=True,
            katago_best_move="",
        )

    event = _read_event(tmp_path / "shadow_events.jsonl")
    assert event["parser_status"] == "failed"
    assert event["parser_failure_reason"].startswith("parse failed:")
    assert "route unsupported" not in event["parser_failure_reason"]


def test_feature_flag_off_suppresses_events_for_all_routes(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_JUDGING_ENABLED", "0")
    monkeypatch.setenv("SHADOW_EVENTS_PATH", str(tmp_path / "shadow_events.jsonl"))

    with app_module.app.test_request_context("/api/rating_test/answer"):
        shadow_judging.observe_rating_test(
            question_id=1,
            session_id="rt",
            transform_idx=0,
            sgf_transformed="(;SZ[19];B[aa])",
            moves=[{"x": 0, "y": 0}],
            client_correct=True,
            final_correct=True,
            katago_best_move="A19",
        )
    with app_module.app.test_request_context("/api/daily-challenge/submit"):
        shadow_judging.observe_answer_route(
            entry_point="daily_challenge",
            question_id=1,
            session_id="daily",
            transform_idx=0,
            sgf_transformed="(;SZ[19];B[aa])",
            moves=None,
            client_correct=True,
            final_correct=True,
            katago_best_move="A19",
        )
    with app_module.app.test_request_context("/api/challenges/friend/9/answer"):
        shadow_judging.observe_answer_route(
            entry_point="friend_challenge",
            question_id=1,
            session_id="friend",
            transform_idx=0,
            sgf_transformed="(;SZ[19];B[aa])",
            moves=None,
            client_correct=False,
            final_correct=False,
            katago_best_move="A19",
        )

    assert not (tmp_path / "shadow_events.jsonl").exists()


def test_rating_test_route_legacy_response_is_unchanged_with_shadow_hook(client, monkeypatch):
    row = {
        "status": "in_progress",
        "user_id": 7,
        "cur_rating": 1500.0,
        "round": 0,
        "answers": "[]",
        "trigger": "manual",
    }
    conn = _FakeConn(row)
    monkeypatch.setattr(app_module, "get_db", lambda: _FakeConnCtx(conn))
    monkeypatch.setattr(app_module, "_ensure_rt_pool", lambda: None)
    monkeypatch.setattr(app_module, "_RT_POOL", [{"id": 123, "content": "(;SZ[19];B[aa])", "discipline": "tesuji", "rating": 1500.0, "katago_best_move": "A19"}])
    monkeypatch.setattr(app_module, "_compute_streak", lambda answers, correct: 1)
    monkeypatch.setattr(app_module, "_k_for_round", lambda round_idx, streak: 32.0)
    monkeypatch.setattr(app_module, "_elo_update", lambda cur, q_rating, correct, k: 1510.0)
    monkeypatch.setattr(app_module, "_get_recent_seen_ids", lambda uid: set())
    monkeypatch.setattr(app_module, "_pick_question", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, "_rating_to_rank", lambda value: "kyu")
    monkeypatch.setattr(app_module, "_RT_TOTAL_ROUNDS", 1)

    with client.session_transaction() as sess:
        sess["user_id"] = 7

    off_calls = []
    monkeypatch.setattr(shadow_judging, "is_enabled", lambda: False)
    monkeypatch.setattr(shadow_judging, "observe_rating_test", lambda **kwargs: off_calls.append(kwargs))
    off_response = client.post("/api/rating_test/answer", json={"session_id": "sess-1", "question_id": 123, "correct": True, "moves": [{"x": 0, "y": 0}]})

    on_calls = []
    monkeypatch.setattr(shadow_judging, "is_enabled", lambda: True)
    monkeypatch.setattr(shadow_judging, "observe_rating_test", lambda **kwargs: on_calls.append(kwargs))
    on_response = client.post("/api/rating_test/answer", json={"session_id": "sess-1", "question_id": 123, "correct": True, "moves": [{"x": 0, "y": 0}]})

    assert off_response.status_code == 200
    assert on_response.status_code == 200
    assert off_response.get_json() == on_response.get_json()
    assert off_calls == []
    assert len(on_calls) == 1


def test_daily_challenge_route_legacy_response_is_unchanged_with_shadow_hook(client, monkeypatch):
    conn = _FakeConn(
        query_map={
            "SELECT id FROM daily_challenge_log": None,
            "SELECT COUNT(*) as total, SUM(correct) as cnt": {"total": 1, "cnt": 0},
        }
    )
    monkeypatch.setattr(app_module, "get_db", lambda: _FakeConnCtx(conn))
    monkeypatch.setattr(app_module, "get_or_create_daily_challenge", lambda today: {"question_id": 301})
    monkeypatch.setattr(app_module, "_load_questions", lambda: [{"id": 301, "content": "(;SZ[19];B[aa])", "katago_best_move": "A19"}])
    monkeypatch.setattr(app_module, "check_and_award_daily", lambda *args, **kwargs: [])
    monkeypatch.setattr(app_module, "get_daily_submit_streak", lambda *args, **kwargs: 0)
    monkeypatch.setattr(app_module, "give_daily_appearance", lambda *args, **kwargs: [])

    with client.session_transaction() as sess:
        sess["user_id"] = 7

    off_calls = []
    monkeypatch.setattr(shadow_judging, "is_enabled", lambda: False)
    monkeypatch.setattr(shadow_judging, "observe_answer_route", lambda **kwargs: off_calls.append(kwargs))
    off_response = client.post("/api/daily-challenge/submit", json={"correct": False})

    on_calls = []
    monkeypatch.setattr(shadow_judging, "is_enabled", lambda: True)
    monkeypatch.setattr(shadow_judging, "observe_answer_route", lambda **kwargs: on_calls.append(kwargs))
    on_response = client.post("/api/daily-challenge/submit", json={"correct": False})

    assert off_response.status_code == 200
    assert on_response.status_code == 200
    assert off_response.get_json() == on_response.get_json()
    assert off_calls == []
    assert len(on_calls) == 1


def test_friend_challenge_route_legacy_response_is_unchanged_with_shadow_hook(client, monkeypatch):
    challenge_row = {
        "id": 9,
        "from_user": 7,
        "to_user": 8,
        "status": "active",
        "question_ids": json.dumps([301]),
        "num_questions": 2,
    }
    monkeypatch.setattr(app_module, "get_db", lambda: _FakeConnCtx(_FriendRouteConn(challenge_row)))
    monkeypatch.setattr(app_module, "_load_questions", lambda: [{"id": 301, "content": "(;SZ[19];B[aa])", "katago_best_move": "A19"}])

    with client.session_transaction() as sess:
        sess["user_id"] = 7

    off_calls = []
    monkeypatch.setattr(shadow_judging, "is_enabled", lambda: False)
    monkeypatch.setattr(shadow_judging, "observe_answer_route", lambda **kwargs: off_calls.append(kwargs))
    off_response = client.post("/api/challenges/friend/9/answer", json={"question_id": 301, "correct": True})

    on_calls = []
    monkeypatch.setattr(shadow_judging, "is_enabled", lambda: True)
    monkeypatch.setattr(shadow_judging, "observe_answer_route", lambda **kwargs: on_calls.append(kwargs))
    on_response = client.post("/api/challenges/friend/9/answer", json={"question_id": 301, "correct": True})

    assert off_response.status_code == 200
    assert on_response.status_code == 200
    assert off_response.get_json() == on_response.get_json()
    assert off_calls == []
    assert len(on_calls) == 1
