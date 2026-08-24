from __future__ import annotations

import pytest

from engagement_catalog import (
    CANONICAL_ENGAGEMENT_CATALOG,
    ENGAGEMENT_TYPE_SET,
    LOGIN_JOURNEY_LENGTH,
    LOGIN_REWARD_GRANTED,
    LOGIN_REWARD_PROFILE_STATUS,
    LOGIN_RUNTIME_CHANGED,
    LOGIN_STREAK_TRACKED_SEPARATELY,
    MISSED_LOGIN_RESETS_JOURNEY,
    EngagementCatalog,
    EngagementCatalogValidationError,
    EngagementTrackDefinition,
    validate_engagement_catalog,
)


def _definition(**overrides):
    values = {
        "engagement_id": "engagement:fixture",
        "engagement_type": "LOGIN_STREAK",
        "period": "lifetime",
        "tracked_separately": True,
        "enabled": False,
    }
    values.update(overrides)
    return EngagementTrackDefinition(**values)


def test_login_is_a_separate_engagement_track():
    assert LOGIN_JOURNEY_LENGTH == 7
    assert MISSED_LOGIN_RESETS_JOURNEY is False
    assert LOGIN_STREAK_TRACKED_SEPARATELY is True
    assert LOGIN_RUNTIME_CHANGED is False
    assert LOGIN_REWARD_GRANTED is False
    assert LOGIN_REWARD_PROFILE_STATUS == "UNDEFINED_FOR_D016"
    assert {definition.engagement_type for definition in CANONICAL_ENGAGEMENT_CATALOG.definitions} == set(
        ENGAGEMENT_TYPE_SET
    )
    journey = CANONICAL_ENGAGEMENT_CATALOG.identity_map["engagement:login_journey"]
    assert journey.length == 7
    assert journey.missed_login_resets is False


def test_unknown_engagement_type_fails_closed():
    with pytest.raises(EngagementCatalogValidationError) as error:
        validate_engagement_catalog((_definition(engagement_type="QUEST"),))
    assert "unknown_engagement_type" in str(error.value)


def test_login_journey_cannot_become_a_claim_or_reward_runtime():
    journey = CANONICAL_ENGAGEMENT_CATALOG.identity_map["engagement:login_journey"]
    assert journey.reward_profile_id is None
    assert journey.enabled is False
    assert journey.catalog_status == "reserved"


def test_engagement_identity_collisions_fail_closed():
    with pytest.raises(EngagementCatalogValidationError) as error:
        EngagementCatalog(
            (
                _definition(aliases=("legacy_shared",)),
                _definition(engagement_id="engagement:other", aliases=("legacy_shared",)),
            )
        )
    assert "identity_collision:legacy_shared" in str(error.value)
    assert len(EngagementCatalog((_definition(), _definition(engagement_id="engagement:other"))).definitions) == 2
