"""Server-controlled Quest V2 runtime gate.

The flag is intentionally read at call time so isolated acceptance tests can
turn the candidate on without changing application defaults.  No startup
migration or client-controlled override is performed here.
"""

from __future__ import annotations

import os
from typing import Mapping


QUEST_V2_FEATURE_FLAG = "QUEST_V2_RUNTIME_ENABLED"
QUEST_V2_DEFAULT_ENABLED = False
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"", "0", "false", "no", "off"})


def quest_v2_runtime_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return the server-only runtime state, failing closed on bad config."""

    values = environ if environ is not None else os.environ
    raw = str(values.get(QUEST_V2_FEATURE_FLAG, "")).strip().casefold()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return QUEST_V2_DEFAULT_ENABLED
    return QUEST_V2_DEFAULT_ENABLED


__all__ = [
    "QUEST_V2_DEFAULT_ENABLED",
    "QUEST_V2_FEATURE_FLAG",
    "quest_v2_runtime_enabled",
]
