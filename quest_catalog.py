"""Quest & Engagement V2 catalog foundation.

This module is deliberately a pure, read-only catalog boundary.  It does
not evaluate player state, calculate periods, write progress, settle claims,
or grant rewards.  The four legacy Daily definitions are represented here
only so a future runtime cutover can preserve their machine identities and
executable semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence
import re


QUEST_FAMILY_SET = (
    "daily",
    "weekly",
    "adventure",
    "achievement",
    "event",
    "onboarding",
)

QUEST_PERIOD_SET = (
    "daily",
    "weekly",
    "lifetime",
    "one_time",
    "event_window",
)

# QUEST_SET_COMPLETED is required to describe the existing all-primary
# completion bonus without pretending that it is a question or combat
# condition.  The other values are the D010/D012 event vocabulary.
QUEST_CONDITION_VOCABULARY = (
    "QUESTION_SETTLED",
    "QUESTION_COMPLETED",
    "QUESTION_CORRECT",
    "REVIEW_COMPLETED",
    "DAILY_CHALLENGE_COMPLETED",
    "MONSTER_DEFEATED",
    "BATTLEFIELD_BOSS_DEFEATED",
    "ZONE_CLEARED",
    "STAR_ACQUIRED",
    "LORD_CLEARED",
    "SPIRIT_OWNED",
    "SPIRIT_STAGE_REACHED",
    "LOGIN_RECORDED",
    "QUEST_SET_COMPLETED",
)

# Filters are deterministic machine predicates.  Display text, localized
# text and art keys are intentionally absent from this vocabulary.
QUEST_FILTER_KEYS = frozenset(
    {
        "correct",
        "monster_family",
        "monster_id",
        "encounter_class",
        "zone_key",
        "spirit_id",
        "spirit_stage",
        "streak_scope",
        "source_scope",
        "quest_group",
        "achievement_tier",
    }
)

QUEST_FEATURE_REQUIREMENTS = frozenset(
    {
        "requires_adventure",
        "requires_monster_battle",
        "requires_battlefield_boss",
        "requires_spirit",
        "requires_daily_challenge",
    }
)

_AVAILABILITY_KEYS = frozenset(
    {
        "feature_requirements",
        "event_window",
        "catalog_status",
    }
)
_EVENT_WINDOW_KEYS = frozenset({"start", "end", "timezone"})
_STABLE_KEY = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_QUEST_ID = re.compile(r"^(?P<family>[a-z]+):(?P<key>[a-z0-9][a-z0-9_.-]*)$")


class CatalogValidationError(ValueError):
    """Raised when a catalog cannot be accepted fail-closed."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(errors)
        super().__init__("invalid quest catalog: " + "; ".join(self.errors))


def _freeze(value: Any) -> Any:
    """Recursively make catalog metadata immutable and deterministic."""

    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _is_scalar_filter_value(value: Any) -> bool:
    return isinstance(value, (bool, int, str)) and not isinstance(value, float)


def _valid_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


@dataclass(frozen=True)
class QuestDefinition:
    """Immutable gameplay identity and condition metadata.

    ``reward_profile_id`` is a reference only.  This module never resolves
    or settles that profile.  ``enabled`` describes catalog availability and
    is not a feature flag or a runtime cutover switch.
    """

    quest_id: str
    quest_family: str
    quest_type: str
    period: str
    condition: str
    target: int | None
    filters: Mapping[str, Any] = field(default_factory=dict)
    reward_profile_id: str | None = None
    availability: Mapping[str, Any] = field(default_factory=dict)
    enabled: bool = True
    version: int = 1
    aliases: tuple[str, ...] = ()
    display_key: str | None = None
    source_key: str | None = None
    legacy_source: str | None = None
    selection_group: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "filters", _freeze(self.filters))
        object.__setattr__(self, "availability", _freeze(self.availability))
        if isinstance(self.aliases, str):
            object.__setattr__(self, "aliases", (self.aliases,))
        else:
            object.__setattr__(self, "aliases", tuple(self.aliases))


@dataclass(frozen=True)
class QuestCatalog:
    """Validated definitions plus immutable lookup maps.

    Identity resolution intentionally lives in :mod:`quest_identity`.  This
    class stores exact canonical and alias keys but does not expose a second
    resolver API.
    """

    definitions: tuple[QuestDefinition, ...]
    _canonical_map: Mapping[str, QuestDefinition] = field(init=False, repr=False, compare=False)
    _identity_map: Mapping[str, str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        definitions = tuple(self.definitions)
        errors = catalog_validation_errors(definitions)
        if errors:
            raise CatalogValidationError(errors)

        canonical_map = {definition.quest_id: definition for definition in definitions}
        identity_map: dict[str, str] = {}
        for definition in definitions:
            identity_map[definition.quest_id] = definition.quest_id
            for alias in definition.aliases:
                identity_map[alias] = definition.quest_id

        object.__setattr__(self, "definitions", definitions)
        object.__setattr__(self, "_canonical_map", MappingProxyType(canonical_map))
        object.__setattr__(self, "_identity_map", MappingProxyType(identity_map))

    @property
    def canonical_map(self) -> Mapping[str, QuestDefinition]:
        return self._canonical_map

    @property
    def identity_map(self) -> Mapping[str, str]:
        return self._identity_map

    def by_family(self, family: str) -> tuple[QuestDefinition, ...]:
        """Return definitions by exact family, without identity fallback."""

        return tuple(definition for definition in self.definitions if definition.quest_family == family)


def _definition_errors(definition: QuestDefinition, index: int) -> list[str]:
    errors: list[str] = []
    prefix = f"definitions[{index}]"

    if not isinstance(definition, QuestDefinition):
        return [f"{prefix}:not_quest_definition"]
    if not _valid_nonempty_string(definition.quest_id):
        errors.append(f"{prefix}:invalid_quest_id")
    else:
        match = _QUEST_ID.fullmatch(definition.quest_id)
        if not match or match.group("family") != definition.quest_family:
            errors.append(f"{prefix}:quest_id_must_be_family_namespaced")
    if definition.quest_family not in QUEST_FAMILY_SET:
        errors.append(f"{prefix}:unknown_family")
    if not _valid_nonempty_string(definition.quest_type) or not _STABLE_KEY.fullmatch(definition.quest_type):
        errors.append(f"{prefix}:invalid_quest_type")
    if definition.period not in QUEST_PERIOD_SET:
        errors.append(f"{prefix}:unknown_period")
    if definition.condition not in QUEST_CONDITION_VOCABULARY:
        errors.append(f"{prefix}:unknown_condition")
    if definition.condition in QUEST_CONDITION_VOCABULARY:
        if not isinstance(definition.target, int) or isinstance(definition.target, bool) or definition.target <= 0:
            errors.append(f"{prefix}:positive_target_required")
    if not _valid_nonempty_string(definition.reward_profile_id):
        errors.append(f"{prefix}:reward_profile_required")
    if not isinstance(definition.enabled, bool):
        errors.append(f"{prefix}:enabled_must_be_bool")
    if not isinstance(definition.version, int) or isinstance(definition.version, bool) or definition.version < 1:
        errors.append(f"{prefix}:version_must_be_positive")

    if not isinstance(definition.filters, Mapping):
        errors.append(f"{prefix}:filters_must_be_mapping")
    else:
        for key, value in definition.filters.items():
            if key not in QUEST_FILTER_KEYS:
                errors.append(f"{prefix}:unknown_filter:{key}")
            if not _is_scalar_filter_value(value) or (isinstance(value, str) and not _valid_nonempty_string(value)):
                errors.append(f"{prefix}:invalid_filter_value:{key}")

    if not isinstance(definition.availability, Mapping):
        errors.append(f"{prefix}:availability_must_be_mapping")
    else:
        unknown_availability = set(definition.availability) - _AVAILABILITY_KEYS
        errors.extend(f"{prefix}:unknown_availability:{key}" for key in sorted(unknown_availability))

        feature_requirements = definition.availability.get("feature_requirements", ())
        if not isinstance(feature_requirements, (tuple, list)):
            errors.append(f"{prefix}:feature_requirements_must_be_sequence")
        else:
            for feature in feature_requirements:
                if feature not in QUEST_FEATURE_REQUIREMENTS:
                    errors.append(f"{prefix}:unknown_feature_requirement:{feature}")

        event_window = definition.availability.get("event_window")
        if event_window is not None:
            if not isinstance(event_window, Mapping):
                errors.append(f"{prefix}:event_window_must_be_mapping")
            else:
                unknown_window = set(event_window) - _EVENT_WINDOW_KEYS
                errors.extend(f"{prefix}:unknown_event_window:{key}" for key in sorted(unknown_window))
                start = event_window.get("start")
                end = event_window.get("end")
                if not _valid_nonempty_string(start) or not _valid_nonempty_string(end) or start >= end:
                    errors.append(f"{prefix}:invalid_event_window")
        if definition.quest_family == "event":
            if definition.period != "event_window" or event_window is None:
                errors.append(f"{prefix}:event_requires_explicit_window")
        elif event_window is not None:
            errors.append(f"{prefix}:event_window_only_for_event_family")

    if definition.quest_family == "adventure" and "zone_key" not in definition.filters:
        errors.append(f"{prefix}:adventure_zone_filter_required")

    aliases = definition.aliases
    if not isinstance(aliases, tuple):
        errors.append(f"{prefix}:aliases_must_be_tuple")
    else:
        for alias in aliases:
            if not _valid_nonempty_string(alias) or not _STABLE_KEY.fullmatch(alias.replace(":", ".")):
                errors.append(f"{prefix}:invalid_alias:{alias}")
            if alias == definition.quest_id:
                errors.append(f"{prefix}:alias_is_canonical_id")

    # A localized/display key is descriptive metadata only.  Reusing the
    # canonical ID as display identity is a contract error, not a fallback.
    if definition.display_key == definition.quest_id:
        errors.append(f"{prefix}:display_key_cannot_be_identity")
    return errors


def catalog_validation_errors(definitions: Iterable[QuestDefinition]) -> tuple[str, ...]:
    """Return deterministic validation errors without mutating the input."""

    definitions = tuple(definitions)
    errors: list[str] = []
    canonical_ids: dict[str, int] = {}
    aliases: dict[str, int] = {}

    for index, definition in enumerate(definitions):
        errors.extend(_definition_errors(definition, index))
        if isinstance(definition, QuestDefinition):
            canonical_ids[definition.quest_id] = canonical_ids.get(definition.quest_id, 0) + 1
            for alias in definition.aliases:
                aliases[alias] = aliases.get(alias, 0) + 1

    for quest_id, count in sorted(canonical_ids.items()):
        if count > 1:
            errors.append(f"canonical_id_collision:{quest_id}")
    for alias, count in sorted(aliases.items()):
        if count > 1:
            errors.append(f"alias_duplicate:{alias}")
    canonical_set = set(canonical_ids)
    for alias in sorted(aliases):
        if alias in canonical_set:
            errors.append(f"alias_canonical_collision:{alias}")

    return tuple(dict.fromkeys(errors))


def validate_catalog(definitions: Iterable[QuestDefinition]) -> None:
    """Validate and raise; callers must not silently accept invalid data."""

    errors = catalog_validation_errors(definitions)
    if errors:
        raise CatalogValidationError(errors)


def build_catalog(definitions: Iterable[QuestDefinition]) -> QuestCatalog:
    return QuestCatalog(tuple(definitions))


def _compatibility_record(
    legacy_machine_key: str,
    condition: str,
    target: int,
    current_reward_behavior: Mapping[str, Any],
    canonical_quest_id: str,
    canonical_alias_mapping: Sequence[str],
) -> Mapping[str, Any]:
    return _freeze(
        {
            "legacy_machine_key": legacy_machine_key,
            "current_condition": condition,
            "current_target": target,
            "current_reward_behavior": current_reward_behavior,
            "current_reset_behavior": (
                "lazy host-local date partition via datetime.date.today(); admin reset may delete "
                "today's rows and permit a later re-award"
            ),
            "canonical_quest_id": canonical_quest_id,
            "canonical_alias_mapping": tuple(canonical_alias_mapping),
        }
    )


CURRENT_DAILY_COMPATIBILITY = (
    _compatibility_record(
        "kill_monsters",
        "MONSTER_DEFEATED",
        5,
        {
            "xp": 30,
            "rank_xp": 30,
            "item_id": "go_spirit_candy",
            "item_quantity": 1,
            "coins": 15,
            "coin_cap_applies": True,
        },
        "daily:kill_monsters",
        ("kill_monsters",),
    ),
    _compatibility_record(
        "streak_correct",
        "QUESTION_CORRECT",
        3,
        {
            "xp": 20,
            "rank_xp": 20,
            "item_id": "go_spirit_candy",
            "item_quantity": 1,
            "coins": 15,
            "coin_cap_applies": True,
        },
        "daily:streak_correct",
        ("streak_correct",),
    ),
    _compatibility_record(
        "challenge_dragon",
        "QUESTION_CORRECT",
        1,
        {
            "xp": 50,
            "rank_xp": 50,
            "item_id": "go_spirit_candy",
            "item_quantity": 1,
            "coins": 15,
            "coin_cap_applies": True,
            "condition_truth": "daily battlefield monster_type == dragon; question metadata is not authoritative",
        },
        "daily:challenge_dragon",
        ("challenge_dragon",),
    ),
    _compatibility_record(
        "all_complete",
        "QUEST_SET_COMPLETED",
        3,
        {
            "xp": 100,
            "rank_xp": 100,
            "item_id": "starfruit",
            "item_quantity": 1,
            "coins": 50,
            "coin_cap_applies": True,
        },
        "daily:all_complete",
        ("all_complete",),
    ),
)


CURRENT_DAILY_PRIMARY_KEYS = ("kill_monsters", "streak_correct", "challenge_dragon")
CURRENT_DAILY_BONUS_KEY = "all_complete"
CURRENT_DAILY_PRIMARY_COUNT = 3
CURRENT_DAILY_BONUS_COUNT = 1
CURRENT_DAILY_TOTAL_COUNT = 4
DAILY_TARGET_COUNT_POLICY = 4
DAILY_POOL_CAPABILITY = True
D012_DAILY_DYNAMIC_SELECTION_ENABLED = False
DAILY_ELIGIBILITY_RUNTIME_ADDED = False
LEGACY_GUILD_COMPATIBILITY_REQUIRED = True

# These are explicit reconciliation blockers for future adapters, not
# runtime failures.  Guild segments are regenerated from mutable question
# pools, and the current Newbie implementation contains incompatible legacy
# and staged ladders.  D012 therefore does not create guessed aliases for
# either surface.
QUEST_IDENTITY_BLOCKERS = (
    "guild_segment_identity_requires_catalog_snapshot",
    "newbie_legacy_and_staged_ladders_require_explicit_migration_map",
)
QUEST_IDENTITY_BLOCKER_COUNT = len(QUEST_IDENTITY_BLOCKERS)


def _legacy_daily_definition(
    *,
    key: str,
    condition: str,
    target: int,
    filters: Mapping[str, Any],
    selection_group: str,
) -> QuestDefinition:
    return QuestDefinition(
        quest_id=f"daily:{key}",
        quest_family="daily",
        quest_type=key,
        period="daily",
        condition=condition,
        target=target,
        filters=filters,
        reward_profile_id=f"legacy:daily:{key}",
        availability={"catalog_status": "legacy_compatibility"},
        enabled=True,
        version=1,
        aliases=(key,),
        display_key=f"legacy.daily.{key}",
        source_key=key,
        legacy_source="app.py:DAILY_QUEST_DEFS",
        selection_group=selection_group,
    )


CURRENT_DAILY_DEFINITIONS = (
    _legacy_daily_definition(
        key="kill_monsters",
        condition="MONSTER_DEFEATED",
        target=5,
        filters={"source_scope": "daily_battlefield"},
        selection_group="daily_primary",
    ),
    _legacy_daily_definition(
        key="streak_correct",
        condition="QUESTION_CORRECT",
        target=3,
        filters={"correct": True, "streak_scope": "daily_consecutive"},
        selection_group="daily_primary",
    ),
    _legacy_daily_definition(
        key="challenge_dragon",
        condition="QUESTION_CORRECT",
        target=1,
        filters={"monster_family": "dragon", "source_scope": "daily_battlefield"},
        selection_group="daily_primary",
    ),
    _legacy_daily_definition(
        key="all_complete",
        condition="QUEST_SET_COMPLETED",
        target=3,
        filters={"quest_group": "daily_primary"},
        selection_group="daily_bonus",
    ),
)


CANONICAL_QUEST_CATALOG = build_catalog(CURRENT_DAILY_DEFINITIONS)
CANONICAL_QUEST_DEFINITIONS = CURRENT_DAILY_DEFINITIONS
CURRENT_DAILY_COMPATIBILITY_MATRIX = CURRENT_DAILY_COMPATIBILITY


__all__ = [
    "CANONICAL_QUEST_CATALOG",
    "CURRENT_DAILY_BONUS_KEY",
    "CURRENT_DAILY_BONUS_COUNT",
    "CURRENT_DAILY_COMPATIBILITY",
    "CURRENT_DAILY_COMPATIBILITY_MATRIX",
    "CURRENT_DAILY_DEFINITIONS",
    "CURRENT_DAILY_PRIMARY_COUNT",
    "CURRENT_DAILY_PRIMARY_KEYS",
    "CURRENT_DAILY_TOTAL_COUNT",
    "DAILY_ELIGIBILITY_RUNTIME_ADDED",
    "DAILY_POOL_CAPABILITY",
    "DAILY_TARGET_COUNT_POLICY",
    "D012_DAILY_DYNAMIC_SELECTION_ENABLED",
    "LEGACY_GUILD_COMPATIBILITY_REQUIRED",
    "QUEST_IDENTITY_BLOCKER_COUNT",
    "QUEST_IDENTITY_BLOCKERS",
    "CANONICAL_QUEST_DEFINITIONS",
    "CatalogValidationError",
    "QuestCatalog",
    "QuestDefinition",
    "QUEST_CONDITION_VOCABULARY",
    "QUEST_FEATURE_REQUIREMENTS",
    "QUEST_FAMILY_SET",
    "QUEST_FILTER_KEYS",
    "QUEST_PERIOD_SET",
    "build_catalog",
    "catalog_validation_errors",
    "validate_catalog",
]
