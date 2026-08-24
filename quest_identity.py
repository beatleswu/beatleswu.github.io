"""Exact Quest identity resolution for Quest & Engagement V2.

Only canonical IDs and explicit aliases are accepted.  There is no display
name, substring, localization, array-order, or fuzzy fallback.
"""

from __future__ import annotations

from quest_catalog import CANONICAL_QUEST_CATALOG, QuestCatalog, QuestDefinition


class UnknownQuestIdentity(ValueError):
    """Raised when a caller supplies no exact canonical ID or alias."""


def resolve_quest_id(raw_id: str, catalog: QuestCatalog | None = None) -> str:
    """Resolve one exact identity or fail closed."""

    active_catalog = catalog or CANONICAL_QUEST_CATALOG
    if not isinstance(raw_id, str) or not raw_id or raw_id not in active_catalog.identity_map:
        raise UnknownQuestIdentity("unknown quest identity")
    return active_catalog.identity_map[raw_id]


def get_quest_definition(raw_id: str, catalog: QuestCatalog | None = None) -> QuestDefinition:
    """Return the definition behind one exact identity."""

    active_catalog = catalog or CANONICAL_QUEST_CATALOG
    return active_catalog.canonical_map[resolve_quest_id(raw_id, active_catalog)]


__all__ = ["UnknownQuestIdentity", "get_quest_definition", "resolve_quest_id"]
