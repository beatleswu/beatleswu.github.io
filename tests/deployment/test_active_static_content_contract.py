"""Behavioural contracts the shipped static must satisfy.

These assert BEHAVIOUR, not a generated directory name, so they survive every
new timestamped static generation.

Context: the site-wide latency P0 was worsened by the answer critical path
issuing a second blocking ``/api/adventure/bootstrap`` request after an ordinary
answer. ``bootstrap`` reconstructs the full historical compatibility read model,
so paying for it per answer multiplied the very aggregate read that LC020 had to
bound. The repair moved Guild advancement onto the server-owned
``guild_progress`` projection returned by the review writer itself.
"""

from __future__ import annotations

import pathlib
import re


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
INDEX_HTML = REPO_ROOT / "index.html"


def _answer_commit_region() -> str:
    """The post-commit region of the answer handler.

    Anchored on stable markers rather than line numbers so ordinary edits
    elsewhere in index.html do not silently empty this window.
    """

    source = INDEX_HTML.read_text(encoding="utf-8")
    start = source.index("REVIEW_COMMITTED")
    end = source.index("_premiumWeeklyMode.setId", start)
    region = source[start:end]
    assert len(region) > 200, "answer-commit region anchors failed to locate real code"
    return region


def test_post_answer_path_does_not_refetch_adventure_bootstrap():
    """POST_ANSWER_REDUNDANT_BOOTSTRAP_GUARD.

    An ordinary answer must not trigger a second blocking bootstrap round trip.
    """

    region = _answer_commit_region()
    assert "/api/adventure/bootstrap" not in region, (
        "the answer critical path fetches /api/adventure/bootstrap again; that is "
        "the redundant post-answer aggregate read the latency P0 removed"
    )


def test_guild_advancement_uses_the_committed_server_projection():
    """The next question must come from the review response, not a second request."""

    source = INDEX_HTML.read_text(encoding="utf-8")
    assert "_applyGuildQuestProgressProjection(" in source, (
        "the server-owned guild_progress projection consumer is missing"
    )
    assert "data.guild_progress" in source, (
        "Guild advancement must read the projection returned by the review writer"
    )


def test_bootstrap_remains_available_for_genuine_map_reads():
    """The guard must not have deleted bootstrap entirely -- only removed it from
    the answer path. Map/HUD surfaces still legitimately call it."""

    source = INDEX_HTML.read_text(encoding="utf-8")
    assert source.count("/api/adventure/bootstrap") >= 1, (
        "bootstrap disappeared from the client entirely; the map read still needs it"
    )


def test_service_worker_declares_a_single_parseable_version():
    """SW identity must be machine-readable for the release identity lock."""

    sw = (REPO_ROOT / "sw.js").read_text(encoding="utf-8")
    matches = re.findall(r"^const VERSION\s*=\s*'([^']+)'", sw, re.MULTILINE)
    assert len(matches) == 1, f"expected exactly one active VERSION, found {matches}"
    assert matches[0].strip(), "service worker VERSION must be non-empty"
