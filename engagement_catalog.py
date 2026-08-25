"""Separate engagement-track catalog boundary.

Login Journey is intentionally not a Quest.  This module defines only the
future D016 identity/policy boundary; it has no attendance, claim, period,
reward, or login mutation behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence
import re

from quest_catalog import QUEST_PERIOD_SET


ENGAGEMENT_TYPE_SET = ("LOGIN_JOURNEY", "LOGIN_STREAK", "TOTAL_LOGIN_DAYS")
LOGIN_JOURNEY_LENGTH = 7
MISSED_LOGIN_RESETS_JOURNEY = False
LOGIN_STREAK_TRACKED_SEPARATELY = True
LOGIN_REWARD_PROFILE_STATUS = "UNDEFINED_FOR_D016"
LOGIN_RUNTIME_CHANGED = False
LOGIN_REWARD_GRANTED = False

_ENGAGEMENT_ID = re.compile(r"^engagement:[a-z0-9][a-z0-9_.-]*$")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


class EngagementCatalogValidationError(ValueError):
    """Raised when an engagement definition is not safe to accept."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(errors)
        super().__init__("invalid engagement catalog: " + "; ".join(self.errors))


@dataclass(frozen=True)
class EngagementTrackDefinition:
    engagement_id: str
    engagement_type: str
    period: str
    length: int | None = None
    missed_login_resets: bool | None = None
    tracked_separately: bool = False
    reward_profile_id: str | None = None
    enabled: bool = False
    version: int = 1
    aliases: tuple[str, ...] = ()
    source_key: str | None = None
    catalog_status: str = "reserved"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.aliases, str):
            object.__setattr__(self, "aliases", (self.aliases,))
        else:
            object.__setattr__(self, "aliases", tuple(self.aliases))
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True)
class EngagementCatalog:
    definitions: tuple[EngagementTrackDefinition, ...]
    _identity_map: Mapping[str, EngagementTrackDefinition] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        definitions = tuple(self.definitions)
        errors = engagement_catalog_validation_errors(definitions)
        if errors:
            raise EngagementCatalogValidationError(errors)
        identity_map: dict[str, EngagementTrackDefinition] = {}
        for definition in definitions:
            identity_map[definition.engagement_id] = definition
            for alias in definition.aliases:
                identity_map[alias] = definition
        object.__setattr__(self, "definitions", definitions)
        object.__setattr__(self, "_identity_map", MappingProxyType(identity_map))

    @property
    def identity_map(self) -> Mapping[str, EngagementTrackDefinition]:
        return self._identity_map


def engagement_catalog_validation_errors(
    definitions: Iterable[EngagementTrackDefinition],
) -> tuple[str, ...]:
    definitions = tuple(definitions)
    errors: list[str] = []
    identities: dict[str, int] = {}
    for index, definition in enumerate(definitions):
        prefix = f"definitions[{index}]"
        if not isinstance(definition, EngagementTrackDefinition):
            errors.append(f"{prefix}:not_engagement_definition")
            continue
        if not _ENGAGEMENT_ID.fullmatch(definition.engagement_id):
            errors.append(f"{prefix}:invalid_engagement_id")
        if definition.engagement_type not in ENGAGEMENT_TYPE_SET:
            errors.append(f"{prefix}:unknown_engagement_type")
        if definition.period not in QUEST_PERIOD_SET:
            errors.append(f"{prefix}:unknown_period")
        if definition.length is not None and (
            not isinstance(definition.length, int)
            or isinstance(definition.length, bool)
            or definition.length <= 0
        ):
            errors.append(f"{prefix}:length_must_be_positive")
        if not isinstance(definition.enabled, bool):
            errors.append(f"{prefix}:enabled_must_be_bool")
        if not isinstance(definition.version, int) or isinstance(definition.version, bool) or definition.version < 1:
            errors.append(f"{prefix}:version_must_be_positive")
        if definition.engagement_type == "LOGIN_JOURNEY":
            if definition.length != LOGIN_JOURNEY_LENGTH:
                errors.append(f"{prefix}:login_journey_length_must_be_7")
            if definition.missed_login_resets is not MISSED_LOGIN_RESETS_JOURNEY:
                errors.append(f"{prefix}:login_journey_reset_policy_mismatch")
        if definition.engagement_type == "LOGIN_STREAK" and not definition.tracked_separately:
            errors.append(f"{prefix}:login_streak_must_be_separate")
        for identity in (definition.engagement_id, *definition.aliases):
            identities[identity] = identities.get(identity, 0) + 1
        if definition.reward_profile_id is not None and not isinstance(definition.reward_profile_id, str):
            errors.append(f"{prefix}:invalid_reward_profile_reference")

    for identity, count in sorted(identities.items()):
        if count > 1:
            errors.append(f"identity_collision:{identity}")
    return tuple(dict.fromkeys(errors))


def validate_engagement_catalog(definitions: Iterable[EngagementTrackDefinition]) -> None:
    errors = engagement_catalog_validation_errors(definitions)
    if errors:
        raise EngagementCatalogValidationError(errors)


CANONICAL_ENGAGEMENT_CATALOG = EngagementCatalog(
    (
        EngagementTrackDefinition(
            engagement_id="engagement:login_journey",
            engagement_type="LOGIN_JOURNEY",
            period="one_time",
            length=LOGIN_JOURNEY_LENGTH,
            missed_login_resets=MISSED_LOGIN_RESETS_JOURNEY,
            tracked_separately=False,
            source_key="login_journey",
            catalog_status="reserved",
            metadata={"reward_profile_status": LOGIN_REWARD_PROFILE_STATUS},
        ),
        EngagementTrackDefinition(
            engagement_id="engagement:login_streak",
            engagement_type="LOGIN_STREAK",
            period="lifetime",
            tracked_separately=True,
            source_key="login_streak",
            catalog_status="reserved",
        ),
        EngagementTrackDefinition(
            engagement_id="engagement:total_login_days",
            engagement_type="TOTAL_LOGIN_DAYS",
            period="lifetime",
            tracked_separately=True,
            source_key="total_login_days",
            catalog_status="reserved",
        ),
    )
)


__all__ = [
    "CANONICAL_ENGAGEMENT_CATALOG",
    "ENGAGEMENT_TYPE_SET",
    "EngagementCatalog",
    "EngagementCatalogValidationError",
    "EngagementTrackDefinition",
    "LOGIN_JOURNEY_LENGTH",
    "LOGIN_REWARD_GRANTED",
    "LOGIN_REWARD_PROFILE_STATUS",
    "LOGIN_RUNTIME_CHANGED",
    "LOGIN_STREAK_TRACKED_SEPARATELY",
    "MISSED_LOGIN_RESETS_JOURNEY",
    "engagement_catalog_validation_errors",
    "validate_engagement_catalog",
]
