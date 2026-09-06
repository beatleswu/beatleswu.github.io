"""Shared test-only hygiene for process-local W1-D3 throttle state."""

from __future__ import annotations

import sys

import pytest


_FEATURE_KEY_PREFIXES = ("workbench:", "question-report:")


def _clear_feature_throttle_entries() -> None:
    """Remove only Workbench-owned test state, leaving other limiters intact."""
    # Never initialize application runtime from the shared fixture.  Tests
    # that need app import it themselves with their own synthetic test secret;
    # otherwise there is no process-local limiter state to clear.
    application = sys.modules.get("app")
    if application is None:
        return

    with application._auth_fail_lock:
        for key in tuple(application._auth_fail_log):
            if key.startswith(_FEATURE_KEY_PREFIXES):
                application._auth_fail_log.pop(key, None)


@pytest.fixture(autouse=True)
def isolate_w1_d3_throttle_state():
    """Keep independent tests isolated while preserving state within a test."""
    _clear_feature_throttle_entries()
    yield
    _clear_feature_throttle_entries()
