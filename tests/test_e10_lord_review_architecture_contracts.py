"""Executable V1A source contracts.

These are intentionally expected-red against b3cb3a5: Lane B freezes the
contract before Lane A adds the Production controller.  They must fail for a
missing architectural invariant, not because a disposable runtime is absent.
"""

from __future__ import annotations

import re

import pytest

from lord_review_architecture_contracts import (
    dedicated_controller_source,
    function_block,
    load_contract,
    source_text,
)


CONTRACT = load_contract()


def _require_controller() -> str:
    controller = dedicated_controller_source()
    assert controller is not None, (
        "V1A requires a dedicated LordReviewController module or inline "
        "controller with an observable review/commit/transition boundary"
    )
    return controller


def test_committed_review_advances_through_lord_controller():
    controller = _require_controller()
    assert "review_request" in controller
    assert "server_commit" in controller
    assert "client_transition" in controller
    assert re.search(r"(?:commit|settle).*?(?:transition|advance)", controller, re.I | re.S)


def test_presentation_failure_is_not_transition_authority():
    controller = _require_controller()
    assert "presentation_failure" in controller
    assert re.search(r"presentation.*?(?:failure|error)", controller, re.I | re.S)
    assert re.search(r"(?:server_commit|committed).*?(?:transition|advance)", controller, re.I | re.S)
    assert not re.search(
        r"presentation.*?(?:failure|error).*?(?:review|retry|submit)",
        controller,
        re.I | re.S,
    )


def test_one_review_request_per_answer_has_one_transport_boundary():
    controller = _require_controller()
    assert controller.count("review_request") == 1
    assert controller.count("server_commit") == 1
    assert controller.count("client_transition") == 1


def test_server_rejection_cannot_transition_client_lord_state():
    controller = _require_controller()
    assert "server_rejection" in controller or "rejected_review" in controller
    assert re.search(
        r"(?:reject|rejection).*?(?:no|not|false).*?(?:transition|advance)",
        controller,
        re.I | re.S,
    )


def test_lord_trial_has_one_advancement_authority():
    controller = _require_controller()
    text = source_text()
    blocks = {
        name: function_block(name)
        for name in ("submitSRS", "nextQuestion", "_handleBossAnswer", "_loadBossQuestion")
    }
    assert "LordReviewController" in controller
    assert "LordReviewController" in text
    assert "LordReviewController" in blocks["_handleBossAnswer"] or "LordReviewController" in controller
    assert "LordReviewController" not in blocks["nextQuestion"]
    assert "review" not in blocks["nextQuestion"].lower()


def test_presentation_failure_is_observable():
    controller = _require_controller()
    observable = CONTRACT["controller_observable"]
    assert observable in controller or observable in source_text()
    for event in ("presentation_failure", "server_commit", "client_transition"):
        assert event in controller


def test_presentation_failure_cannot_retry_review():
    controller = _require_controller()
    assert "presentation_failure" in controller
    assert not re.search(
        r"presentation_failure.*?(?:review_request|fetch\([^)]*srs/review|retry)",
        controller,
        re.I | re.S,
    )


def test_server_commit_and_client_transition_are_separately_observable():
    controller = _require_controller()
    observable = CONTRACT["controller_observable"]
    assert observable in controller or observable in source_text()
    assert re.search(r"server_commit\s*[:(]", controller)
    assert re.search(r"client_transition\s*[:(]", controller)


@pytest.mark.parametrize("fault", CONTRACT["presentation_faults"])
def test_presentation_fault_interface_is_declared(fault):
    """Keep the test-only failure names stable for the real-path matrix."""
    assert isinstance(fault, str) and fault.endswith(("THROW", "REJECT"))
