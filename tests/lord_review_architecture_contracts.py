"""Narrow V1A source contracts for the E10 Lord review architecture.

This module deliberately describes the observable boundary that Lane A must
provide.  It does not import ``app`` or execute Production code.  The tests
are red-first on the frozen b3cb base until the dedicated Lord controller and
its observability surface are integrated.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = REPO_ROOT / "index.html"
SRS_JS = REPO_ROOT / "srs.js"
CONTRACT_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "lord_review_architecture_contract_v1a.json"
)


def load_contract() -> dict:
    return json.loads(CONTRACT_FIXTURE.read_text(encoding="utf-8"))


def source_text() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def source_blocks(text: str) -> dict[str, str]:
    """Extract named JS function blocks without snapshotting whole files."""
    blocks: dict[str, str] = {}
    pattern = re.compile(
        r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{"
    )
    for match in pattern.finditer(text):
        depth = 0
        end = None
        for index in range(match.end() - 1, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is not None:
            blocks[match.group(1)] = text[match.start():end]
    return blocks


def dedicated_controller_source() -> str | None:
    """Return the dedicated controller source when Lane A provides it.

    The accepted locations keep the contract semantic while allowing the
    integration to use a separate browser module or an inline controller
    during the first V1A landing.
    """
    candidates = (
        REPO_ROOT / "js" / "game" / "lord_trial_controller.js",
        REPO_ROOT / "e10_lord_review_controller.js",
        REPO_ROOT / "lord_review_controller.js",
        REPO_ROOT / "static" / "e10_lord_review_controller.js",
        REPO_ROOT / "static" / "lord_review_controller.js",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")

    text = source_text()
    if "createLordReviewController" in text or "LordReviewController" in text:
        return text
    return None


def function_block(name: str) -> str:
    return source_blocks(source_text()).get(name, "")


def contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def expected_red_contract_names() -> tuple[str, ...]:
    return (
        "test_committed_review_advances_through_lord_controller",
        "test_presentation_failure_is_not_transition_authority",
        "test_one_review_request_per_answer_has_one_transport_boundary",
        "test_server_rejection_cannot_transition_client_lord_state",
        "test_lord_trial_has_one_advancement_authority",
        "test_presentation_failure_is_observable",
        "test_presentation_failure_cannot_retry_review",
        "test_server_commit_and_client_transition_are_separately_observable",
    )
