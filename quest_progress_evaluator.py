"""Pure Quest V2 authoritative-event to progress-delta evaluation.

The evaluator accepts an already-authoritative server event and returns a
deterministically ordered tuple of progress intents.  It deliberately does
not persist progress, calculate period keys, settle claims, grant rewards,
or inspect any gameplay authority such as Monster HP.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from quest_catalog import (
    CANONICAL_QUEST_CATALOG,
    QUEST_CONDITION_VOCABULARY,
    QuestCatalog,
    QuestDefinition,
)


SUPPORTED_EVENT_TYPES = tuple(QUEST_CONDITION_VOCABULARY)
SUPPORTED_PROGRESS_OPERATIONS = ("INCREMENT", "RESET")
SUPPORTED_SOURCE_AUTHORITIES = (
    "review_settlement",
    "monster_settlement",
    "adventure_settlement",
    "lord_trial_authority",
    "spirit_authority",
    "daily_challenge_authority",
    "quest_evaluator:derived",
)
EVENT_ENVELOPE_FIELDS = (
    "event_id",
    "event_type",
    "user_id",
    "source_authority",
    "source_operation_id",
    "occurred_at",
    "payload",
)

_CLIENT_AUTHORITIES = frozenset({"client", "browser", "frontend", "user", "untrusted"})
_NON_RUNTIME_CATALOG_STATES = frozenset({"disabled", "retired"})
_TEST_SOURCE_AUTHORITIES = frozenset({"server:test"})


class EventContractError(ValueError):
    """Raised when an event is not a valid authoritative D013 input."""


class UnknownEventType(EventContractError):
    """Raised instead of silently mapping an unknown event type."""


class ClientEventAuthorityError(EventContractError):
    """Raised when a client/untrusted source attempts to author an event."""


class InvalidCompletionIdentity(EventContractError):
    """Raised when set-completion input is not canonical Quest identity."""


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise EventContractError("payload_mapping_keys_must_be_strings")
        return MappingProxyType(
            {key: _freeze(item) for key, item in sorted(value.items())}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        raise EventContractError("payload_sets_are_not_canonical")
    return value


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _valid_user_id(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value > 0
    return _nonempty_string(value)


def _is_client_authority(source_authority: str) -> bool:
    normalized = source_authority.casefold()
    return (
        normalized in _CLIENT_AUTHORITIES
        or normalized.startswith("client:")
        or normalized.endswith(":client")
        or normalized.startswith("browser:")
        or normalized.endswith(":browser")
    )


def _is_allowed_source_authority(source_authority: str) -> bool:
    return source_authority in SUPPORTED_SOURCE_AUTHORITIES or source_authority in _TEST_SOURCE_AUTHORITIES


@dataclass(frozen=True)
class AuthoritativeEvent:
    """Immutable event envelope produced by a server-owned authority.

    There is intentionally no constructor from arbitrary client JSON.  A
    future producer should create this value only after its own authority has
    committed/validated the underlying fact.
    """

    event_id: str
    event_type: str
    user_id: int | str
    source_authority: str
    source_operation_id: str
    occurred_at: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not _nonempty_string(self.event_id):
            raise EventContractError("event_id_required")
        if self.event_type not in SUPPORTED_EVENT_TYPES:
            raise UnknownEventType("unknown event_type")
        if not _valid_user_id(self.user_id):
            raise EventContractError("user_id_required")
        if not _nonempty_string(self.source_authority):
            raise EventContractError("source_authority_required")
        if _is_client_authority(self.source_authority):
            raise ClientEventAuthorityError("client cannot author authoritative events")
        if not _is_allowed_source_authority(self.source_authority):
            raise EventContractError("unknown_source_authority")
        if not _nonempty_string(self.source_operation_id):
            raise EventContractError("source_operation_id_required")
        if not _nonempty_string(self.occurred_at):
            raise EventContractError("occurred_at_required")
        if not isinstance(self.payload, Mapping):
            raise EventContractError("payload_must_be_mapping")
        if self.event_type == "QUEST_SET_COMPLETED" and self.source_authority != "quest_evaluator:derived":
            raise EventContractError("quest_set_completion_must_be_evaluator_derived")
        object.__setattr__(self, "payload", _freeze(self.payload))

    @classmethod
    def from_server(
        cls,
        *,
        event_id: str,
        event_type: str,
        user_id: int | str,
        source_authority: str,
        source_operation_id: str,
        occurred_at: str,
        payload: Mapping[str, Any],
    ) -> "AuthoritativeEvent":
        """Named constructor for future server producers, not clients."""

        return cls(
            event_id=event_id,
            event_type=event_type,
            user_id=user_id,
            source_authority=source_authority,
            source_operation_id=source_operation_id,
            occurred_at=occurred_at,
            payload=payload,
        )


@dataclass(frozen=True)
class ProgressDelta:
    """One pure intent to be consumed by a later progress authority."""

    quest_id: str
    operation: str
    amount: int
    source_event_id: str
    condition: str
    reason: str
    quest_family: str
    period: str
    period_key: None = None

    def __post_init__(self) -> None:
        if not _nonempty_string(self.quest_id):
            raise EventContractError("delta_quest_id_required")
        if self.operation not in SUPPORTED_PROGRESS_OPERATIONS:
            raise EventContractError("unknown_progress_operation")
        if not isinstance(self.amount, int) or isinstance(self.amount, bool) or self.amount < 0:
            raise EventContractError("delta_amount_must_be_nonnegative_integer")
        if self.operation == "RESET" and self.amount != 0:
            raise EventContractError("reset_delta_amount_must_be_zero")
        if self.operation == "INCREMENT" and self.amount <= 0:
            raise EventContractError("increment_delta_amount_must_be_positive")
        if not _nonempty_string(self.source_event_id):
            raise EventContractError("delta_source_event_id_required")
        if not _nonempty_string(self.condition) or not _nonempty_string(self.reason):
            raise EventContractError("delta_semantics_required")
        if self.period_key is not None:
            raise EventContractError("period_key_is_not_resolved_by_d013")


def _catalog_status_allows_evaluation(definition: QuestDefinition) -> bool:
    # D015 owns clock/period authority.  D013 only honors static catalog
    # status here; event-window and feature eligibility evaluation remain
    # outside this pure event-to-delta layer.
    status = definition.availability.get("catalog_status")
    return status not in _NON_RUNTIME_CATALOG_STATES


def _filter_value_matches(actual: Any, expected: Any) -> bool:
    """Compare scalar catalog/event values without Python bool/int coercion."""

    return type(actual) is type(expected) and actual == expected


def _filter_matches(
    definition: QuestDefinition,
    event: AuthoritativeEvent,
    *,
    ignored_keys: frozenset[str] = frozenset(),
) -> bool:
    """Apply validated D012 filters with exact AND semantics."""

    payload = event.payload
    for key, expected in definition.filters.items():
        if key in ignored_keys:
            continue
        if key not in payload:
            return False
        if not _filter_value_matches(payload[key], expected):
            return False
    return True


def _delta_for_definition(definition: QuestDefinition, event: AuthoritativeEvent) -> ProgressDelta | None:
    if not definition.enabled or not _catalog_status_allows_evaluation(definition):
        return None
    if definition.condition != event.event_type:
        return None

    # Current streak_correct is a consecutive-correct quest.  A server
    # QUESTION_CORRECT event carrying correct=False resets its daily streak
    # intent; it must not be treated as an ordinary cumulative increment.
    if (
        event.event_type == "QUESTION_CORRECT"
        and event.payload.get("correct") is False
        and definition.filters.get("streak_scope") == "daily_consecutive"
        and _filter_matches(definition, event, ignored_keys=frozenset({"correct"}))
    ):
        return ProgressDelta(
            quest_id=definition.quest_id,
            operation="RESET",
            amount=0,
            source_event_id=event.event_id,
            condition=definition.condition,
            reason="streak_incorrect_answer_resets_daily_progress",
            quest_family=definition.quest_family,
            period=definition.period,
        )

    # QUESTION_CORRECT is still required to carry explicit server-derived
    # correct=True evidence.  The event type alone is not permission to
    # advance a quest, which keeps an incorrectly labelled dragon event from
    # progressing challenge_dragon.
    if event.event_type == "QUESTION_CORRECT" and event.payload.get("correct") is not True:
        return None

    if not _filter_matches(definition, event):
        return None
    amount = definition.target if event.event_type == "QUEST_SET_COMPLETED" else 1
    if amount is None:
        return None
    return ProgressDelta(
        quest_id=definition.quest_id,
        operation="INCREMENT",
        amount=amount,
        source_event_id=event.event_id,
        condition=definition.condition,
        reason="authoritative_condition_match",
        quest_family=definition.quest_family,
        period=definition.period,
    )


def evaluate_event(
    event: AuthoritativeEvent,
    catalog: QuestCatalog | None = None,
) -> tuple[ProgressDelta, ...]:
    """Evaluate one event against every eligible definition.

    Catalog iteration order is deliberately ignored.  No durable exactly-once
    claim is implied; a later task owns persistence/idempotency.
    """

    if not isinstance(event, AuthoritativeEvent):
        raise EventContractError("authoritative_event_instance_required")
    active_catalog = catalog or CANONICAL_QUEST_CATALOG
    if not isinstance(active_catalog, QuestCatalog):
        raise EventContractError("quest_catalog_instance_required")
    deltas = [
        delta
        for definition in active_catalog.definitions
        if (delta := _delta_for_definition(definition, event)) is not None
    ]
    return tuple(sorted(deltas, key=lambda delta: (delta.quest_id, delta.operation, delta.source_event_id)))


def evaluate_quest_set_completion(
    *,
    source_event: AuthoritativeEvent,
    completed_quest_ids: Iterable[str],
    catalog: QuestCatalog | None = None,
) -> tuple[ProgressDelta, ...]:
    """Derive set-completion deltas from engine-owned completed IDs.

    The source event must be authoritative.  The completed-ID set is an
    input from a future progress authority, not a client claim.  This helper
    derives the internal ``QUEST_SET_COMPLETED`` event; clients cannot create
    that event type directly through :class:`AuthoritativeEvent`.
    """

    if not isinstance(source_event, AuthoritativeEvent):
        raise EventContractError("authoritative_source_event_required")
    active_catalog = catalog or CANONICAL_QUEST_CATALOG
    if not isinstance(active_catalog, QuestCatalog):
        raise EventContractError("quest_catalog_instance_required")
    try:
        raw_completed = tuple(completed_quest_ids)
    except TypeError as exc:
        raise InvalidCompletionIdentity("completed_quest_ids_must_be_iterable") from exc
    if any(not _nonempty_string(quest_id) for quest_id in raw_completed):
        raise InvalidCompletionIdentity("completed_quest_ids_must_be_nonempty_strings")
    if len(raw_completed) != len(set(raw_completed)):
        raise InvalidCompletionIdentity("completed_quest_ids_must_be_unique")
    unknown_ids = set(raw_completed).difference(active_catalog.canonical_map)
    if unknown_ids:
        raise InvalidCompletionIdentity("completed_quest_ids_must_be_canonical")
    completed = frozenset(raw_completed)
    deltas: list[ProgressDelta] = []

    set_definitions = [
        definition
        for definition in active_catalog.definitions
        if definition.enabled
        and _catalog_status_allows_evaluation(definition)
        and definition.condition == "QUEST_SET_COMPLETED"
    ]
    for definition in sorted(set_definitions, key=lambda item: item.quest_id):
        quest_group = definition.filters.get("quest_group")
        if not isinstance(quest_group, str):
            continue
        members = frozenset(
            member.quest_id
            for member in active_catalog.definitions
            if (
                member.selection_group == quest_group
                and member.quest_id != definition.quest_id
                and member.enabled
                and _catalog_status_allows_evaluation(member)
            )
        )
        if not members or not members.issubset(completed):
            continue
        derived_event = AuthoritativeEvent.from_server(
            event_id=f"{source_event.event_id}:quest-set:{quest_group}",
            event_type="QUEST_SET_COMPLETED",
            user_id=source_event.user_id,
            source_authority="quest_evaluator:derived",
            source_operation_id=f"{source_event.source_operation_id}:quest-set:{quest_group}",
            occurred_at=source_event.occurred_at,
            payload={
                "quest_group": quest_group,
                "completed_quest_ids": tuple(sorted(completed)),
            },
        )
        deltas.extend(evaluate_event(derived_event, active_catalog))
    return tuple(sorted(deltas, key=lambda delta: (delta.quest_id, delta.operation, delta.source_event_id)))


__all__ = [
    "AuthoritativeEvent",
    "ClientEventAuthorityError",
    "EVENT_ENVELOPE_FIELDS",
    "EventContractError",
    "InvalidCompletionIdentity",
    "ProgressDelta",
    "SUPPORTED_EVENT_TYPES",
    "SUPPORTED_PROGRESS_OPERATIONS",
    "SUPPORTED_SOURCE_AUTHORITIES",
    "UnknownEventType",
    "evaluate_event",
    "evaluate_quest_set_completion",
]
