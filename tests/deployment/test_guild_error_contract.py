"""The Guild answer error contract: no server decision may become an opaque failure.

The Guild outage was undiagnosable for a structural reason. ReviewTransport hands
a rejection back to the caller as a payload only when its code appears in an
explicit allowlist; anything else is re-thrown and index.html renders the generic

    答題記錄寫入失敗，這題尚未儲存。請稍後重試或重新整理頁面。

with no code at all. Every Guild code -- including ``judge_unavailable``, which
WAS the incident -- fell outside that allowlist, so a one-property content bug and
a genuine server fault were indistinguishable to the player and to support.

This module enumerates the backend codes FROM SOURCE and fails the release gate if
any of them is not represented on the client. Adding a new backend code without
mapping it is therefore a build failure rather than a silent diagnostic hole.

Surfacing a reason is diagnostics only: index.html gates ``markSeen`` and question
advancement on ``data.ok``, so a rejection still never advances and never records.
"""

from __future__ import annotations

import pathlib
import re

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
GUILD_SERVICE = REPO_ROOT / "guild_quest_answer_service.py"
TRANSPORT = REPO_ROOT / "js" / "game" / "review_transport.js"
INDEX_HTML = REPO_ROOT / "index.html"
I18N = REPO_ROOT / "i18n.js"
APP_PY = REPO_ROOT / "app.py"


def _guild_service_codes() -> set[str]:
    text = GUILD_SERVICE.read_text(encoding="utf-8")
    return set(re.findall(r'GuildQuestAnswerError\(\s*"([a-z_]+)"', text))


def _guild_route_codes() -> set[str]:
    """Guild-specific codes returned by the review route's Guild branch."""

    text = APP_PY.read_text(encoding="utf-8")
    start = text.index("    guild_canonical = None")
    end = text.index("submission_payload = {", start)
    branch = text[start:end]
    return {
        code
        for code in re.findall(r"'error':\s*'([a-z_]+)'", branch)
        if code.startswith("guild_")
    }


def _transport_allowlist() -> set[str]:
    text = TRANSPORT.read_text(encoding="utf-8")
    block = re.search(
        r"const SERVER_OWNED_REJECTIONS = new Set\(\[(.*?)\]\);", text, re.S
    )
    assert block, "the transport must declare an explicit server-owned rejection set"
    return set(re.findall(r"'([a-z_]+)'", block.group(1)))


def test_backend_guild_codes_are_all_known_to_the_transport():
    """GUILD_GENERIC_FAILURE_REGRESSION_GUARD.

    Every Guild code the backend can return must be a recognised server-owned
    rejection, or it collapses into the generic save-failure message.
    """

    backend = _guild_service_codes() | _guild_route_codes()
    assert backend, "sanity: the backend must raise at least one Guild code"

    unmapped = sorted(backend - _transport_allowlist())
    assert unmapped == [], (
        "these backend Guild error codes would surface as an opaque "
        f"'answer not saved' with no code: {unmapped}. Add them to "
        "SERVER_OWNED_REJECTIONS in js/game/review_transport.js."
    )


def test_the_incident_code_is_specifically_mapped():
    """judge_unavailable is the code that WAS the outage; it must never regress."""

    assert "judge_unavailable" in _transport_allowlist()
    index_text = INDEX_HTML.read_text(encoding="utf-8")
    assert "data.error==='judge_unavailable'" in index_text.replace(" ", ""), (
        "index.html must explain an unjudgeable question rather than reporting "
        "a write failure"
    )
    assert "index.srs.guild_judge_unavailable" in I18N.read_text(encoding="utf-8")


def test_guild_not_eligible_is_mapped():
    assert "guild_quest_not_eligible" in _transport_allowlist()
    assert "index.srs.guild_not_eligible" in I18N.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "key", ["index.srs.guild_judge_unavailable", "index.srs.guild_not_eligible"]
)
def test_new_messages_are_bilingual(key):
    """The product ships zh/en; a new key must not be half-translated."""

    text = I18N.read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if key in l)
    assert "en:" in line and "zh:" in line, f"{key} must define both en and zh"
    assert re.search(r"zh:\s*'[^']{4,}'", line), f"{key} zh text must be non-trivial"


def test_previously_mapped_codes_are_still_mapped():
    """The pre-existing three must not be lost while extending the set."""

    allowlist = _transport_allowlist()
    for code in ("premium_required", "daily_limit", "boss_attempt_expired"):
        assert code in allowlist, f"{code} lost its server-owned mapping"


def test_surfacing_a_reason_does_not_advance_or_mark_seen():
    """Diagnostics only: progression must still gate on data.ok."""

    text = INDEX_HTML.read_text(encoding="utf-8").replace(" ", "")
    assert "if(data.ok)SRS.markSeen(" in text, (
        "markSeen must remain gated on data.ok so a surfaced rejection cannot "
        "mark a question answered"
    )
    assert "if(!data.ok){" in text


def test_unknown_codes_still_fail_closed_as_transport_errors():
    """An unrecognised code must still be re-thrown, not silently accepted."""

    text = TRANSPORT.read_text(encoding="utf-8")
    assert "throw error;" in text, (
        "the transport must still re-throw rejections it does not recognise"
    )
    assert "SERVER_OWNED_REJECTIONS.has(error.code)" in text
