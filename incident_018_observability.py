"""Privacy-preserving diagnostics for Incident 018 Lord request correlation.

This module deliberately has no Flask, database, or application imports.  It
only emits short-lived, process-scoped hashes and fixed stage names so the
Lord answer lifecycle can be correlated without logging account/session data
or answer contents.  Observability failures are swallowed by design and can
never change request semantics.
"""

from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import logging
import re
import secrets
from typing import Any, Callable
from zoneinfo import ZoneInfo


LORD_REVIEW_ENDPOINT = "/api/srs/review"
LORD_START_ENDPOINT = "/api/adventure/boss/start"
LORD_FINISH_ENDPOINT = "/api/adventure/boss/finish"
LORD_ENDPOINTS = frozenset(
    {LORD_REVIEW_ENDPOINT, LORD_START_ENDPOINT, LORD_FINISH_ENDPOINT}
)

_LORD_SOURCE_PREFIX = "boss_trial:"
_HASH_SALT = secrets.token_bytes(32)
_CURRENT: ContextVar["Incident018Observation | None"] = ContextVar(
    "incident_018_observation", default=None
)
_TAIPEI = ZoneInfo("Asia/Taipei")
_SAFE_CODE = re.compile(r"^[A-Za-z0-9_./:-]{1,120}$")


def _short_hash(value: Any) -> str | None:
    """Return a process-scoped correlation hash without exposing ``value``."""

    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (str, int)):
        return None
    raw = str(value).encode("utf-8", "strict")
    return "h" + hashlib.sha256(_HASH_SALT + raw).hexdigest()[:16]


def _safe_token(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, (str, int)):
        return "UNSAFE_VALUE"
    candidate = str(value)
    return candidate if _SAFE_CODE.fullmatch(candidate) else "UNSAFE_VALUE"


def _safe_question_id(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


class Incident018Observation:
    """One request's non-sensitive diagnostic state."""

    __slots__ = (
        "correlation_id",
        "diagnostic_ref",
        "endpoint",
        "lord_attempt_hash",
        "question_id",
        "submission_hash",
        "idempotency_id_hash",
    )

    def __init__(self, endpoint: str) -> None:
        self.correlation_id = "I018-" + secrets.token_hex(8).upper()
        self.diagnostic_ref = self.correlation_id
        self.endpoint = endpoint
        self.lord_attempt_hash: str | None = None
        self.question_id: int | None = None
        self.submission_hash: str | None = None
        self.idempotency_id_hash: str | None = None

    def update(
        self,
        *,
        attempt_id: Any = None,
        question_id: Any = None,
        submission_id: Any = None,
        submission_payload_hash: Any = None,
    ) -> None:
        if attempt_id is not None:
            self.lord_attempt_hash = _short_hash(attempt_id)
        normalized_question_id = _safe_question_id(question_id)
        if normalized_question_id is not None:
            self.question_id = normalized_question_id
        if submission_id is not None:
            self.idempotency_id_hash = _short_hash(submission_id)
        if submission_payload_hash is not None:
            self.submission_hash = _short_hash(submission_payload_hash)

    def fields(self) -> dict[str, Any]:
        return {
            "REQUEST_CORRELATION_ID": self.correlation_id,
            "ENDPOINT": self.endpoint,
            "LORD_ATTEMPT_HASH": self.lord_attempt_hash,
            "QUESTION_ID": self.question_id,
            "SUBMISSION_HASH": self.submission_hash,
            "IDEMPOTENCY_ID_HASH": self.idempotency_id_hash,
        }


def _attempt_from_source_context(source_context: Any) -> Any:
    if not isinstance(source_context, str):
        return None
    if not source_context.startswith(_LORD_SOURCE_PREFIX):
        return None
    return source_context[len(_LORD_SOURCE_PREFIX) :]


def begin_request(
    endpoint: str,
    *,
    source_context: Any = None,
    question_id: Any = None,
    submission_id: Any = None,
) -> tuple[Incident018Observation | None, Any]:
    """Start an observation only for a Lord review or Lord route."""

    if endpoint not in LORD_ENDPOINTS:
        return None, None
    if endpoint == LORD_REVIEW_ENDPOINT and _attempt_from_source_context(source_context) is None:
        return None, None
    observation = Incident018Observation(endpoint)
    observation.update(
        attempt_id=_attempt_from_source_context(source_context),
        question_id=question_id,
        submission_id=submission_id,
    )
    return observation, _CURRENT.set(observation)


def end_request(token: Any) -> None:
    if token is None:
        return
    try:
        _CURRENT.reset(token)
    except Exception:
        # Diagnostics must never alter the request result.
        pass


def current_observation() -> Incident018Observation | None:
    return _CURRENT.get()


def update_current(**kwargs: Any) -> None:
    observation = current_observation()
    if observation is not None:
        observation.update(**kwargs)


def _timestamp_fields() -> dict[str, str]:
    now = datetime.now(timezone.utc)
    return {
        "SERVER_TIMESTAMP_UTC": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "SERVER_TIMESTAMP_ASIA_TAIPEI": now.astimezone(_TAIPEI).isoformat(
            timespec="milliseconds"
        ),
    }


def _emit(
    observation: Incident018Observation | None,
    stage: str,
    *,
    logger: logging.Logger | None = None,
    **fields: Any,
) -> None:
    if observation is None:
        return
    try:
        payload = {
            "EVENT": "INCIDENT_018_LORD_OBSERVABILITY",
            "STAGE": _safe_token(stage),
            **_timestamp_fields(),
            **observation.fields(),
        }
        for key, value in fields.items():
            safe_key = str(key).upper()
            if (
                safe_key.endswith("_CODE")
                or safe_key.endswith("_RESULT")
                or safe_key.endswith("_SAFE")
                or safe_key in {"FAILED_STAGE", "EXCEPTION_CLASS", "JUDGE_RESULT_CLASS"}
            ):
                value = _safe_token(value)
            payload[safe_key] = value
        (logger or logging.getLogger("incident_018")).info(
            "incident018 %s", json.dumps(payload, ensure_ascii=True, sort_keys=True)
        )
    except Exception:
        # Logging is diagnostic only; it cannot become a gameplay failure.
        pass


def log_stage(
    stage: str,
    *,
    observation: Incident018Observation | None = None,
    logger: logging.Logger | None = None,
    **fields: Any,
) -> None:
    """Emit one fixed stage record with only sanitized correlation fields."""

    _emit(observation or current_observation(), stage, logger=logger, **fields)


def log_exception(
    exception: BaseException,
    *,
    stage: str,
    safe_location: str,
    error_code: str | None = None,
    http_status: int | None = None,
    observation: Incident018Observation | None = None,
    logger: logging.Logger | None = None,
) -> None:
    """Record class/location/code only; never exception text or traceback."""

    _emit(
        observation or current_observation(),
        "EXCEPTION",
        logger=logger,
        FAILED_STAGE=stage,
        EXCEPTION_CLASS=type(exception).__name__,
        EXCEPTION_LOCATION_SAFE=safe_location,
        ERROR_CODE_SAFE=error_code,
        HTTP_STATUS=http_status,
    )


def response_status(response: Any) -> int:
    if isinstance(response, tuple) and len(response) > 1:
        try:
            return int(response[1])
        except (TypeError, ValueError):
            return 500
    try:
        return int(response.status_code)
    except (AttributeError, TypeError, ValueError):
        return 200


def observe_lord_endpoint(endpoint: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate the Lord start/finish endpoints with safe request lifecycle logs."""

    if endpoint not in {LORD_START_ENDPOINT, LORD_FINISH_ENDPOINT}:
        raise ValueError("unsupported Incident 018 endpoint")

    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            observation, token = begin_request(endpoint)
            log_stage("REQUEST_RECEIVED", observation=observation)
            try:
                response = view(*args, **kwargs)
                status = response_status(response)
                log_stage(
                    "RESPONSE_BUILD",
                    observation=observation,
                    HTTP_STATUS=status,
                    RESPONSE_SERIALIZATION_COMPLETED=True,
                )
                log_stage(
                    "RESPONSE_SENT",
                    observation=observation,
                    HTTP_STATUS=status,
                )
                return response
            except Exception as exception:
                log_exception(
                    exception,
                    stage="ROUTE",
                    safe_location=f"app.py:{endpoint}",
                    http_status=500,
                    observation=observation,
                )
                raise
            finally:
                end_request(token)

        return wrapped

    return decorator


__all__ = [
    "Incident018Observation",
    "LORD_FINISH_ENDPOINT",
    "LORD_REVIEW_ENDPOINT",
    "LORD_START_ENDPOINT",
    "begin_request",
    "current_observation",
    "end_request",
    "log_exception",
    "log_stage",
    "observe_lord_endpoint",
    "response_status",
    "update_current",
]
