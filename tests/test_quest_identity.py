from __future__ import annotations

import pytest

from quest_catalog import CatalogValidationError, QuestDefinition, build_catalog
from quest_identity import UnknownQuestIdentity, get_quest_definition, resolve_quest_id


def test_canonical_id_and_explicit_alias_resolve_exactly():
    assert resolve_quest_id("daily:kill_monsters") == "daily:kill_monsters"
    assert resolve_quest_id("kill_monsters") == "daily:kill_monsters"
    assert get_quest_definition("kill_monsters").source_key == "kill_monsters"


@pytest.mark.parametrize("raw_id", ["", "DAILY:KILL_MONSTERS", "Warrior's First Trial", "daily:kill"])
def test_unknown_display_or_fuzzy_identity_fails_closed(raw_id):
    with pytest.raises(UnknownQuestIdentity):
        resolve_quest_id(raw_id)


def _definition(quest_id, aliases=()):
    family, key = quest_id.split(":", 1)
    return QuestDefinition(
        quest_id=quest_id,
        quest_family=family,
        quest_type=key,
        period="weekly",
        condition="REVIEW_COMPLETED",
        target=1,
        reward_profile_id=f"fixture:{key}",
        aliases=aliases,
        enabled=False,
    )


def test_duplicate_canonical_ids_and_aliases_fail_closed():
    with pytest.raises(CatalogValidationError) as error:
        build_catalog((_definition("weekly:first"), _definition("weekly:first")))
    assert "canonical_id_collision" in str(error.value)

    with pytest.raises(CatalogValidationError) as error:
        build_catalog((_definition("weekly:first", aliases=("shared",)), _definition("weekly:second", aliases=("shared",))))
    assert "alias_duplicate" in str(error.value)


def test_alias_cannot_shadow_another_canonical_id():
    with pytest.raises(CatalogValidationError) as error:
        build_catalog((_definition("weekly:first", aliases=("weekly:second",)), _definition("weekly:second")))
    assert "alias_canonical_collision" in str(error.value)


def test_resolver_uses_the_supplied_validated_catalog():
    catalog = build_catalog((_definition("weekly:first", aliases=("legacy_first",)),))
    assert resolve_quest_id("legacy_first", catalog) == "weekly:first"
    assert get_quest_definition("legacy_first", catalog).quest_id == "weekly:first"
