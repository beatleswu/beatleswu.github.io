"""E2.4A: sgf_engine failures must be explicit and observable, never silently
substituted with an alternate parser/verdict implementation.

These tests exercise shadow_judging.py directly (no Flask app import) so
they stay isolated from unrelated app.py dependencies.
"""
from __future__ import annotations

import builtins
import json
import sys
from pathlib import Path

import pytest

import shadow_judging


_LEAF_SGF = "(;SZ[19];B[qd](;W[od];B[oc]))"
_LEAF_MOVES = [{"x": 16, "y": 3}, {"x": 14, "y": 2}]


def _read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _run(tmp_path, monkeypatch, **kwargs):
    monkeypatch.setenv("SHADOW_JUDGING_ENABLED", "1")
    events_path = tmp_path / "shadow_events.jsonl"
    monkeypatch.setenv("SHADOW_EVENTS_PATH", str(events_path))
    defaults = dict(
        question_id=1,
        session_id="sess-e24a",
        transform_idx=0,
        sgf_transformed=_LEAF_SGF,
        moves=_LEAF_MOVES,
        client_correct=True,
        final_correct=True,
        katago_best_move="Q16",
    )
    defaults.update(kwargs)
    shadow_judging.observe_answer_route(**defaults)
    return _read_events(events_path)


def test_fallback_function_no_longer_exists():
    """The silent fallback must be removed, not merely unreachable."""
    assert not hasattr(shadow_judging, "_shadow_verdict_simple")
    assert not hasattr(shadow_judging, "_xy_to_sgf_simple")


@pytest.mark.parametrize("entry_point", ["rating_test", "daily_challenge", "friend_challenge"])
def test_import_failure_is_explicit_and_observable(tmp_path, monkeypatch, entry_point):
    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if name == "sgf_engine.core" or name.startswith("sgf_engine.core."):
            raise ModuleNotFoundError("No module named 'sgf_engine.core' (simulated)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocking_import)

    events = _run(tmp_path, monkeypatch, entry_point=entry_point)

    assert len(events) == 1
    event = events[0]

    assert event["shadow_judgement"] == "error"
    assert event["parser_status"] == "failed"
    assert event["parser_failure_reason"]
    assert event["exception_class"] == "ModuleNotFoundError"
    assert event["exception_message"]
    assert event["schema_version"] == "shadow-v3"
    assert event["route"]
    assert event["request_id"]
    assert isinstance(event["latency_ms"], int) and event["latency_ms"] >= 0
    assert event["entry_point"] == entry_point
    assert event["user_facing_judgement_changed"] is False


@pytest.mark.parametrize("entry_point", ["rating_test", "daily_challenge", "friend_challenge"])
def test_runtime_exception_is_explicit_and_observable(tmp_path, monkeypatch, entry_point):
    def _raise(*args, **kwargs):
        raise RuntimeError("token=abc simulated engine crash")

    monkeypatch.setattr(shadow_judging, "_shadow_verdict", _raise)

    events = _run(tmp_path, monkeypatch, entry_point=entry_point)

    assert len(events) == 1
    event = events[0]

    assert event["shadow_judgement"] == "error"
    assert event["parser_status"] == "failed"
    assert event["parser_failure_reason"]
    assert event["exception_class"] == "RuntimeError"
    assert "token=abc" not in event["exception_message"].lower()
    assert event["entry_point"] == entry_point
    assert event["user_facing_judgement_changed"] is False


def test_fallback_never_invoked_even_when_import_fails(tmp_path, monkeypatch):
    """Belt-and-suspenders: even if a fallback existed, it must not run.

    Since _shadow_verdict_simple has been removed entirely, calling it would
    raise AttributeError. We assert the module has no such callable AND that
    the import-failure path above never produces a normal-looking verdict
    (accept/reject/off_tree) — only "error".
    """
    assert not hasattr(shadow_judging, "_shadow_verdict_simple")

    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if name == "sgf_engine.core" or name.startswith("sgf_engine.core."):
            raise ImportError("simulated: sgf_engine unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocking_import)

    events = _run(tmp_path, monkeypatch, entry_point="rating_test")
    assert events[0]["shadow_judgement"] not in {"accept", "reject", "off_tree", "unsupported"}
    assert events[0]["shadow_judgement"] == "error"


@pytest.mark.parametrize("entry_point", ["rating_test", "daily_challenge", "friend_challenge"])
def test_success_path_unchanged_when_engine_available(tmp_path, monkeypatch, entry_point):
    events = _run(tmp_path, monkeypatch, entry_point=entry_point)

    assert len(events) == 1
    event = events[0]

    assert event["shadow_judgement"] == "accept"
    assert event["parser_status"] == "ok"
    assert event["parser_failure_reason"] == ""
    assert event["exception_class"] == ""
    assert event["exception_message"] == ""
    assert event["classification"] == "agreement_accept"
    assert event["user_facing_judgement_changed"] is False


def test_feature_flag_off_suppresses_event_even_on_import_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_JUDGING_ENABLED", "0")
    events_path = tmp_path / "shadow_events.jsonl"
    monkeypatch.setenv("SHADOW_EVENTS_PATH", str(events_path))

    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if name == "sgf_engine.core" or name.startswith("sgf_engine.core."):
            raise ModuleNotFoundError("simulated")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocking_import)

    shadow_judging.observe_answer_route(
        entry_point="rating_test",
        question_id=1,
        session_id="sess-flagoff",
        transform_idx=0,
        sgf_transformed=_LEAF_SGF,
        moves=_LEAF_MOVES,
        client_correct=True,
        final_correct=True,
        katago_best_move="Q16",
    )

    assert not events_path.exists()
