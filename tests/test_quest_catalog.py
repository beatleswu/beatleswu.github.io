from __future__ import annotations

import pytest

from quest_catalog import (
    CANONICAL_QUEST_CATALOG,
    CURRENT_DAILY_BONUS_COUNT,
    CURRENT_DAILY_COMPATIBILITY,
    CURRENT_DAILY_DEFINITIONS,
    CURRENT_DAILY_PRIMARY_COUNT,
    CURRENT_DAILY_PRIMARY_KEYS,
    CURRENT_DAILY_TOTAL_COUNT,
    D012_DAILY_DYNAMIC_SELECTION_ENABLED,
    DAILY_ELIGIBILITY_RUNTIME_ADDED,
    DAILY_POOL_CAPABILITY,
    DAILY_TARGET_COUNT_POLICY,
    CatalogValidationError,
    QuestDefinition,
    build_catalog,
    validate_catalog,
)


def _definition(**overrides):
    values = {
        "quest_id": "weekly:complete_reviews",
        "quest_family": "weekly",
        "quest_type": "complete_reviews",
        "period": "weekly",
        "condition": "REVIEW_COMPLETED",
        "target": 5,
        "filters": {},
        "reward_profile_id": "fixture:weekly:complete_reviews",
        "availability": {"catalog_status": "planned"},
        "enabled": False,
        "version": 1,
        "aliases": (),
    }
    values.update(overrides)
    return QuestDefinition(**values)


def test_current_daily_compatibility_is_exactly_three_primary_plus_bonus():
    assert CURRENT_DAILY_PRIMARY_COUNT == 3
    assert CURRENT_DAILY_BONUS_COUNT == 1
    assert CURRENT_DAILY_TOTAL_COUNT == 4
    assert CURRENT_DAILY_PRIMARY_KEYS == ("kill_monsters", "streak_correct", "challenge_dragon")
    assert tuple(item["legacy_machine_key"] for item in CURRENT_DAILY_COMPATIBILITY) == (
        "kill_monsters",
        "streak_correct",
        "challenge_dragon",
        "all_complete",
    )
    assert tuple(definition.source_key for definition in CURRENT_DAILY_DEFINITIONS) == (
        "kill_monsters",
        "streak_correct",
        "challenge_dragon",
        "all_complete",
    )
    assert CURRENT_DAILY_COMPATIBILITY[2]["current_reward_behavior"]["condition_truth"].startswith(
        "daily battlefield"
    )


def test_daily_pool_and_eligibility_are_capability_only():
    assert DAILY_TARGET_COUNT_POLICY == 4
    assert DAILY_POOL_CAPABILITY is True
    assert D012_DAILY_DYNAMIC_SELECTION_ENABLED is False
    assert DAILY_ELIGIBILITY_RUNTIME_ADDED is False


@pytest.mark.parametrize(
    "definition,fragment",
    [
        (_definition(quest_family="unknown"), "unknown_family"),
        (_definition(period="monthly"), "unknown_period"),
        (_definition(condition="NOT_A_REAL_EVENT"), "unknown_condition"),
        (_definition(target=0), "positive_target_required"),
        (_definition(reward_profile_id=None), "reward_profile_required"),
        (_definition(filters={"not_supported": True}), "unknown_filter"),
        (
            _definition(
                quest_family="event",
                quest_id="event:summer",
                quest_type="summer",
                period="event_window",
                availability={"catalog_status": "planned"},
            ),
            "event_requires_explicit_window",
        ),
    ],
)
def test_catalog_validation_fails_closed(definition, fragment):
    with pytest.raises(CatalogValidationError) as error:
        validate_catalog((definition,))
    assert fragment in str(error.value)


def test_event_window_and_adventure_zone_filters_are_representable():
    event = _definition(
        quest_id="event:summer",
        quest_family="event",
        quest_type="summer",
        period="event_window",
        filters={"encounter_class": "event"},
        availability={
            "catalog_status": "planned",
            "event_window": {
                "start": "2026-09-01T00:00:00+08:00",
                "end": "2026-10-01T00:00:00+08:00",
                "timezone": "Asia/Taipei",
            },
        },
    )
    adventure = _definition(
        quest_id="adventure:zone_03_clear",
        quest_family="adventure",
        quest_type="zone_03_clear",
        period="one_time",
        condition="ZONE_CLEARED",
        target=1,
        filters={"zone_key": "zone_03"},
        availability={"feature_requirements": ("requires_adventure",), "catalog_status": "planned"},
    )
    catalog = build_catalog((event, adventure))
    assert catalog.canonical_map["event:summer"].availability["event_window"]["timezone"] == "Asia/Taipei"
    assert catalog.canonical_map["adventure:zone_03_clear"].filters["zone_key"] == "zone_03"


def test_achievement_lifetime_tier_is_catalog_capability_only():
    achievement = _definition(
        quest_id="achievement:spirit_stage_iii",
        quest_family="achievement",
        quest_type="spirit_stage_iii",
        period="lifetime",
        condition="SPIRIT_STAGE_REACHED",
        target=1,
        filters={"spirit_stage": "III"},
        availability={"catalog_status": "planned"},
    )
    catalog = build_catalog((achievement,))
    assert catalog.canonical_map["achievement:spirit_stage_iii"].period == "lifetime"
    assert catalog.canonical_map["achievement:spirit_stage_iii"].enabled is False


def test_invalid_event_window_fails_closed():
    with pytest.raises(CatalogValidationError) as error:
        validate_catalog(
            (
                _definition(
                    quest_id="event:invalid_window",
                    quest_family="event",
                    quest_type="invalid_window",
                    period="event_window",
                    availability={
                        "catalog_status": "planned",
                        "event_window": {"start": "2026-10-01", "end": "2026-09-01"},
                    },
                ),
            )
        )
    assert "invalid_event_window" in str(error.value)


def test_catalog_definitions_are_immutable():
    definition = CANONICAL_QUEST_CATALOG.definitions[0]
    with pytest.raises((AttributeError, TypeError)):
        definition.quest_id = "daily:changed"
    with pytest.raises(TypeError):
        definition.filters["source_scope"] = "changed"


def test_catalog_has_no_progress_claim_or_period_runtime_surface():
    exported = set(__import__("quest_catalog").__all__)
    assert not {"save_progress", "claim_quest", "calculate_period", "grant_reward"} & exported
