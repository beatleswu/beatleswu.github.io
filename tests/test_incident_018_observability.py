"""Focused, read-only contract tests for Incident 018 diagnostics."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from incident_018_observability import (
    LORD_REVIEW_ENDPOINT,
    begin_request,
    end_request,
    log_exception,
    log_stage,
    observe_lord_endpoint,
    update_current,
)


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
INDEX_SOURCE = (ROOT / "index.html").read_text(encoding="utf-8")


def test_lord_request_gets_unique_server_correlation_id_and_safe_hashes(caplog):
    caplog.set_level(logging.INFO, logger="incident_018")
    first, first_token = begin_request(
        LORD_REVIEW_ENDPOINT,
        source_context="boss_trial:owner-attempt-123",
        question_id=7001,
        submission_id="lord-trial:owner-attempt-123:7001",
    )
    second, second_token = begin_request(
        LORD_REVIEW_ENDPOINT,
        source_context="boss_trial:owner-attempt-456",
        question_id=7002,
    )
    try:
        assert first is not None and second is not None
        assert first.correlation_id.startswith("I018-")
        assert first.correlation_id != second.correlation_id
        assert first.lord_attempt_hash and first.lord_attempt_hash.startswith("h")
        assert first.idempotency_id_hash and first.idempotency_id_hash.startswith("h")
        assert first.question_id == 7001
    finally:
        end_request(second_token)
        end_request(first_token)


def test_lord_stage_records_cover_judge_persistence_response_and_safe_exception(caplog):
    caplog.set_level(logging.INFO, logger="incident_018")
    observation, token = begin_request(
        LORD_REVIEW_ENDPOINT,
        source_context="boss_trial:attempt-without-raw-log",
        question_id=7001,
    )
    assert observation is not None
    try:
        log_stage("REQUEST_RECEIVED", observation=observation)
        log_stage("INPUT_VALIDATION", observation=observation)
        log_stage("JUDGE_ENTER", observation=observation, JUDGE_STAGE_ENTERED=True)
        log_stage(
            "JUDGE_EXIT",
            observation=observation,
            JUDGE_STAGE_ENTERED=True,
            JUDGE_STAGE_COMPLETED=True,
            JUDGE_RESULT_CLASS="CORRECT",
        )
        update_current(submission_payload_hash="payload-digest-not-raw-answer")
        log_stage("PERSISTENCE_ENTER", observation=observation, PERSISTENCE_STAGE_ENTERED=True)
        log_stage(
            "PERSISTENCE_EXIT",
            observation=observation,
            PERSISTENCE_STAGE_COMPLETED=True,
            PERSISTENCE_RESULT="INSERTED",
            HTTP_STATUS=200,
        )
        log_stage(
            "RESPONSE_BUILD",
            observation=observation,
            RESPONSE_SERIALIZATION_COMPLETED=True,
            HTTP_STATUS=200,
        )
        log_stage("RESPONSE_SENT", observation=observation, HTTP_STATUS=200)
        log_exception(
            RuntimeError("raw-answer-and-session-data-must-not-be-logged"),
            stage="PERSISTENCE",
            safe_location="app.py:_srs_review_operation:insert_review_log_with_identity",
            error_code="review_record_write_failed",
            http_status=500,
            observation=observation,
        )
    finally:
        end_request(token)

    output = caplog.text
    for stage in (
        "REQUEST_RECEIVED",
        "INPUT_VALIDATION",
        "JUDGE_ENTER",
        "JUDGE_EXIT",
        "PERSISTENCE_ENTER",
        "PERSISTENCE_EXIT",
        "RESPONSE_BUILD",
        "RESPONSE_SENT",
        '"STAGE": "EXCEPTION"',
    ):
        assert stage in output
    assert '"JUDGE_RESULT_CLASS": "CORRECT"' in output
    assert '"SERVER_TIMESTAMP_UTC":' in output
    assert '"SERVER_TIMESTAMP_ASIA_TAIPEI":' in output
    assert '"HTTP_STATUS": 500' in output
    assert "raw-answer-and-session-data-must-not-be-logged" not in output
    assert "owner-attempt-123" not in output
    assert "payload-digest-not-raw-answer" not in output
    assert '"EXCEPTION_CLASS": "RuntimeError"' in output
    assert '"EXCEPTION_LOCATION_SAFE": "app.py:_srs_review_operation:insert_review_log_with_identity"' in output
    assert '"ERROR_CODE_SAFE": "review_record_write_failed"' in output


def test_non_lord_srs_request_is_not_observed(caplog):
    caplog.set_level(logging.INFO, logger="incident_018")
    observation, token = begin_request(
        LORD_REVIEW_ENDPOINT,
        source_context="practice",
        question_id=7001,
    )
    try:
        assert observation is None
        log_stage("REQUEST_RECEIVED", observation=observation)
    finally:
        end_request(token)
    assert caplog.records == []


def test_start_finish_decorator_preserves_success_and_rethrows_failures(caplog):
    caplog.set_level(logging.INFO, logger="incident_018")

    @observe_lord_endpoint("/api/adventure/boss/start")
    def start():
        update_current(attempt_id="server-attempt-1")
        return {"ok": True}

    @observe_lord_endpoint("/api/adventure/boss/finish")
    def finish():
        update_current(attempt_id="server-attempt-1")
        return type("Response", (), {"status_code": 200})()

    assert start() == {"ok": True}
    response = finish()
    assert response.status_code == 200
    assert '"ENDPOINT": "/api/adventure/boss/start"' in caplog.text
    assert '"ENDPOINT": "/api/adventure/boss/finish"' in caplog.text
    assert '"RESPONSE_SERIALIZATION_COMPLETED": true' in caplog.text
    assert '"LORD_ATTEMPT_HASH": "h' in caplog.text

    @observe_lord_endpoint("/api/adventure/boss/finish")
    def failed():
        raise ValueError("private request text")

    with pytest.raises(ValueError, match="private request text"):
        failed()
    assert '"EXCEPTION_CLASS": "ValueError"' in caplog.text
    assert "private request text" not in caplog.text


def test_source_contract_has_narrow_routes_client_reference_and_no_behavior_writers():
    assert "incident018_begin_request" in APP_SOURCE
    assert "incident018_observe_lord_endpoint(INCIDENT_018_LORD_START_ENDPOINT)" in APP_SOURCE
    assert "incident018_observe_lord_endpoint(INCIDENT_018_LORD_FINISH_ENDPOINT)" in APP_SOURCE
    for marker in (
        "'JUDGE_ENTER'",
        "'JUDGE_EXIT'",
        "'PERSISTENCE_ENTER'",
        "'PERSISTENCE_EXIT'",
        "'RESPONSE_BUILD'",
        "'RESPONSE_SENT'",
        "incident018_log_exception",
    ):
        assert marker in APP_SOURCE
    assert "normalize_identity(" in APP_SOURCE
    assert "lord_trial_submission_id(" in APP_SOURCE
    assert "diagnostic_ref" in APP_SOURCE
    assert "診斷碼：" in INDEX_SOURCE
    assert "errorType: e?.name || 'Error'" in INDEX_SOURCE


def test_observability_module_has_no_sensitive_request_logging_surface():
    source = (ROOT / "incident_018_observability.py").read_text(encoding="utf-8")
    for forbidden in ("Authorization", "Cookie", "csrf", "email", "user_id", "request.headers"):
        assert forbidden not in source
