"""Focused synthetic coverage for the Shadow Event Envelope V4 contract.

The tests exercise ``shadow_judging`` directly. They use only in-memory SGF
fixtures and pytest temporary directories; no application corpus, database, or
production configuration is loaded.
"""

from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path

import pytest

import shadow_judging


SYNTHETIC_SGF = "(;SZ[19];B[aa])"
CANONICAL_A = "11111111-1111-4111-8111-111111111111"
CANONICAL_B = "22222222-2222-4222-8222-222222222222"
NON_V4_UUID = "33333333-3333-1333-8333-333333333333"

REQUIRED_V4_FIELDS = {
    "schema_version",
    "event_id",
    "created_at",
    "route",
    "request_id",
    "entry_point",
    "legacy_question_id",
    "canonical_puzzle_id",
    "invalid_identity",
    "session_id",
    "transform_idx",
    "player_color",
    "player_move_sgf",
    "player_move_board_coordinate",
    "source_judgement",
    "legacy_reason",
    "legacy_unknown",
    "client_judgement",
    "shadow_judgement",
    "shadow_reason",
    "classification",
    "candidate_only_detected",
    "candidate_source",
    "gf003_related",
    "parser_status",
    "parser_failure_reason",
    "exception_class",
    "exception_message",
    "latency_ms",
    "moves_count",
    "review_recommended",
    "owner_decision_required",
    "user_facing_judgement_changed",
}
VALID_CANDIDATE_SOURCES = {None, "accepted_moves", "katago_best_move"}


def _observation_kwargs(**overrides):
    kwargs = {
        "entry_point": "rating_test",
        "question_id": 4242,
        "session_id": "synthetic-session",
        "transform_idx": 0,
        "sgf_transformed": SYNTHETIC_SGF,
        "moves": [{"x": 0, "y": 0}],
        "client_correct": True,
        "final_correct": True,
        "katago_best_move": "",
        "accepted_moves": [],
        "canonical_puzzle_id": CANONICAL_A,
        "invalid_identity": False,
        "legacy_reason": "synthetic legacy result",
        "gf003_canonical_puzzle_id": None,
    }
    kwargs.update(overrides)
    return kwargs


def _configure_sink(tmp_path: Path, monkeypatch, *, flag: str = "1") -> Path:
    event_path = tmp_path / "shadow-events-v4.jsonl"
    monkeypatch.setenv("SHADOW_JUDGING_ENABLED", flag)
    monkeypatch.setenv("SHADOW_EVENTS_PATH", str(event_path))
    return event_path


def _read_events(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _emit_one(tmp_path: Path, monkeypatch, *, flag: str = "1", **overrides) -> dict:
    event_path = _configure_sink(tmp_path, monkeypatch, flag=flag)
    result = shadow_judging.observe_answer_route(**_observation_kwargs(**overrides))
    assert result is None
    events = _read_events(event_path)
    assert len(events) == 1
    return events[0]


def test_v4_event_contains_every_required_field_with_valid_types(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        shadow_judging,
        "_request_metadata",
        lambda: ("/api/rating_test/answer", "synthetic-request-id"),
    )
    monkeypatch.setattr(
        shadow_judging,
        "_shadow_verdict",
        lambda _sgf, _moves: ("accept", "synthetic accept"),
    )

    event = _emit_one(tmp_path, monkeypatch)

    assert REQUIRED_V4_FIELDS <= set(event)
    assert event["schema_version"] == "shadow-v4"
    assert uuid.UUID(event["event_id"]).version == 4
    created_at = datetime.datetime.fromisoformat(event["created_at"])
    assert created_at.utcoffset() == datetime.timedelta(0)
    assert event["route"] == "/api/rating_test/answer"
    assert event["request_id"] == "synthetic-request-id"
    assert event["entry_point"] == "rating_test"
    assert event["legacy_question_id"] == 4242
    assert event["canonical_puzzle_id"] == CANONICAL_A
    assert event["invalid_identity"] is False
    assert event["session_id"] == "synthetic-session"
    assert event["transform_idx"] == 0
    assert event["player_color"] == "B"
    assert event["player_move_sgf"] == "B[aa]"
    assert event["player_move_board_coordinate"] == "A19"
    assert event["source_judgement"] == "accept"
    assert event["legacy_reason"] == "synthetic legacy result"
    assert event["legacy_unknown"] is False
    assert event["client_judgement"] == "accept"
    assert event["shadow_judgement"] == "accept"
    assert event["shadow_reason"] == "synthetic accept"
    assert event["classification"] == "agreement_accept"
    assert event["candidate_only_detected"] is False
    assert event["candidate_source"] is None
    assert event["candidate_source"] in VALID_CANDIDATE_SOURCES
    assert event["gf003_related"] is False
    assert event["parser_status"] == "ok"
    assert event["parser_failure_reason"] == ""
    assert event["exception_class"] == ""
    assert event["exception_message"] == ""
    assert type(event["latency_ms"]) is int
    assert event["latency_ms"] >= 0
    assert event["moves_count"] == 1
    assert event["review_recommended"] is False
    assert event["owner_decision_required"] is False
    assert event["user_facing_judgement_changed"] is False


@pytest.mark.parametrize(
    ("candidate_source", "accepted_moves", "katago_best_move"),
    [
        ("accepted_moves", [{"x": 3, "y": 4}], ""),
        ("katago_best_move", [], "D15"),
    ],
)
@pytest.mark.parametrize(
    ("final_correct", "source_judgement", "expected_classification"),
    [
        (True, "accept", "legacy_accepts_shadow_candidate_match"),
        (False, "reject", "legacy_rejects_transform_candidate"),
    ],
)
def test_candidate_sources_preserve_class_a_and_class_b_separation(
    tmp_path,
    monkeypatch,
    candidate_source,
    accepted_moves,
    katago_best_move,
    final_correct,
    source_judgement,
    expected_classification,
):
    monkeypatch.setattr(
        shadow_judging,
        "_shadow_verdict",
        lambda _sgf, _moves: ("off_tree", "synthetic off-tree move"),
    )

    # Transform 4 maps canonical (3, 4) to presented-board (15, 4).
    event = _emit_one(
        tmp_path,
        monkeypatch,
        transform_idx=4,
        moves=[{"x": 15, "y": 4}],
        accepted_moves=accepted_moves,
        katago_best_move=katago_best_move,
        client_correct=final_correct,
        final_correct=final_correct,
    )

    assert event["source_judgement"] == source_judgement
    assert event["shadow_judgement"] == "off_tree"
    assert event["candidate_only_detected"] is True
    assert event["candidate_source"] == candidate_source
    assert event["candidate_source"] in VALID_CANDIDATE_SOURCES
    assert event["classification"] == expected_classification
    if final_correct:
        assert event["classification"] != "legacy_rejects_transform_candidate"
    else:
        assert event["classification"] != "legacy_accepts_shadow_candidate_match"


def test_accepted_moves_has_deterministic_precedence_when_both_sources_match(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        shadow_judging,
        "_shadow_verdict",
        lambda _sgf, _moves: ("reject", "synthetic rejection"),
    )

    event = _emit_one(
        tmp_path,
        monkeypatch,
        transform_idx=4,
        moves=[{"x": 15, "y": 4}],
        accepted_moves=[{"x": 3, "y": 4}],
        katago_best_move="D15",
    )

    assert event["candidate_only_detected"] is True
    assert event["candidate_source"] == "accepted_moves"
    assert event["classification"] == "legacy_accepts_shadow_candidate_match"


@pytest.mark.parametrize(
    (
        "canonical_puzzle_id",
        "gf003_canonical_puzzle_id",
        "expected_canonical_id",
        "expected_invalid_identity",
        "expected_gf003_related",
    ),
    [
        (CANONICAL_A, CANONICAL_A, CANONICAL_A, False, True),
        (CANONICAL_A, CANONICAL_B, CANONICAL_A, False, False),
        (None, CANONICAL_A, None, True, False),
        ("not-a-uuid", CANONICAL_A, None, True, False),
        (NON_V4_UUID, CANONICAL_A, None, True, False),
    ],
)
def test_gf003_related_requires_matching_valid_canonical_identity(
    tmp_path,
    monkeypatch,
    canonical_puzzle_id,
    gf003_canonical_puzzle_id,
    expected_canonical_id,
    expected_invalid_identity,
    expected_gf003_related,
):
    monkeypatch.setattr(
        shadow_judging,
        "_shadow_verdict",
        lambda _sgf, _moves: ("accept", "synthetic accept"),
    )

    event = _emit_one(
        tmp_path,
        monkeypatch,
        canonical_puzzle_id=canonical_puzzle_id,
        invalid_identity=None,
        gf003_canonical_puzzle_id=gf003_canonical_puzzle_id,
    )

    assert event["canonical_puzzle_id"] == expected_canonical_id
    assert event["invalid_identity"] is expected_invalid_identity
    assert event["gf003_related"] is expected_gf003_related


def test_gf003_is_not_inferred_from_candidate_coordinates(tmp_path, monkeypatch):
    monkeypatch.setattr(
        shadow_judging,
        "_shadow_verdict",
        lambda _sgf, _moves: ("off_tree", "synthetic off-tree move"),
    )

    event = _emit_one(
        tmp_path,
        monkeypatch,
        canonical_puzzle_id=None,
        invalid_identity=True,
        gf003_canonical_puzzle_id=CANONICAL_A,
        moves=[{"x": 18, "y": 5}],
        accepted_moves=[{"x": 18, "y": 5}],
    )

    assert event["candidate_only_detected"] is True
    assert event["candidate_source"] == "accepted_moves"
    assert event["canonical_puzzle_id"] is None
    assert event["invalid_identity"] is True
    assert event["gf003_related"] is False


def test_explicit_invalid_identity_nulls_canonical_id_and_blocks_gf003(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        shadow_judging,
        "_shadow_verdict",
        lambda _sgf, _moves: ("accept", "synthetic accept"),
    )

    event = _emit_one(
        tmp_path,
        monkeypatch,
        canonical_puzzle_id=CANONICAL_A,
        invalid_identity=True,
        gf003_canonical_puzzle_id=CANONICAL_A,
    )

    assert event["canonical_puzzle_id"] is None
    assert event["invalid_identity"] is True
    assert event["gf003_related"] is False


@pytest.mark.parametrize("malformed_flag", ["2", "enabled", "truthy", "0x1", "null"])
def test_malformed_enable_flag_fails_closed_without_evaluation_or_write(
    tmp_path, monkeypatch, malformed_flag
):
    event_path = _configure_sink(tmp_path, monkeypatch, flag=malformed_flag)
    verdict_calls = []
    monkeypatch.setattr(
        shadow_judging,
        "_shadow_verdict",
        lambda *_args: verdict_calls.append(True),
    )

    result = shadow_judging.observe_answer_route(**_observation_kwargs())

    assert result is None
    assert verdict_calls == []
    assert not event_path.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("off_flag", ["", "0", "false", "no", "off", " OFF "])
def test_explicit_off_flag_performs_zero_work_and_zero_writes(
    tmp_path, monkeypatch, off_flag
):
    event_path = _configure_sink(tmp_path, monkeypatch, flag=off_flag)
    verdict_calls = []
    monkeypatch.setattr(
        shadow_judging,
        "_shadow_verdict",
        lambda *_args: verdict_calls.append(True),
    )

    result = shadow_judging.observe_answer_route(**_observation_kwargs())

    assert result is None
    assert verdict_calls == []
    assert not event_path.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("on_flag", ["1", "true", "yes", "on", " ON "])
def test_explicit_on_flag_emits_exactly_one_event(tmp_path, monkeypatch, on_flag):
    monkeypatch.setattr(
        shadow_judging,
        "_shadow_verdict",
        lambda _sgf, _moves: ("accept", "synthetic accept"),
    )

    event = _emit_one(tmp_path, monkeypatch, flag=on_flag)

    assert event["schema_version"] == "shadow-v4"
    assert event["user_facing_judgement_changed"] is False


def test_engine_exception_is_isolated_and_emitted_as_observable_failure(
    tmp_path, monkeypatch
):
    def _raise_engine_error(_sgf, _moves):
        raise RuntimeError("token=synthetic-secret cookie=synthetic-cookie")

    monkeypatch.setattr(shadow_judging, "_shadow_verdict", _raise_engine_error)

    event = _emit_one(tmp_path, monkeypatch)

    assert event["source_judgement"] == "accept"
    assert event["shadow_judgement"] == "error"
    assert event["classification"] == "shadow_error"
    assert event["parser_status"] == "failed"
    assert event["parser_failure_reason"]
    assert event["exception_class"] == "RuntimeError"
    assert "synthetic-secret" not in event["exception_message"]
    assert "synthetic-cookie" not in event["exception_message"]
    assert "[redacted]" in event["exception_message"]
    assert event["candidate_only_detected"] is False
    assert event["candidate_source"] is None
    assert event["user_facing_judgement_changed"] is False


def test_storage_exception_is_isolated_from_the_answer_path(tmp_path, monkeypatch):
    event_path = _configure_sink(tmp_path, monkeypatch)
    attempted_events = []
    monkeypatch.setattr(
        shadow_judging,
        "_shadow_verdict",
        lambda _sgf, _moves: ("accept", "synthetic accept"),
    )

    def _raise_storage_error(event, *, path):
        attempted_events.append((event, path))
        raise OSError("synthetic storage failure")

    monkeypatch.setattr(shadow_judging, "append_event", _raise_storage_error)

    result = shadow_judging.observe_answer_route(**_observation_kwargs())

    assert result is None
    assert len(attempted_events) == 1
    attempted_event, attempted_path = attempted_events[0]
    assert attempted_path == str(event_path)
    assert attempted_event["schema_version"] == "shadow-v4"
    assert attempted_event["user_facing_judgement_changed"] is False
    assert not event_path.exists()
