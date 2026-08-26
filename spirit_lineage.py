"""Executable S1 contracts for the E10 Six-Spirit companion domain.

This module is intentionally route-free.  It does not own a database table,
change gameplay state, or decide a reward.  It gives Lane B one vocabulary
for operation identity, D5A/D5C evidence payloads, legacy-resource safety,
evolution derivation, and the event boundary between server facts and
analytics consumers.

The existing D5A outbox remains evidence only.  The existing D5C item-use
operation record remains the item-use business authority.  Future Companion
callers must bind their own authoritative mutation to these contracts inside
their caller-owned transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import Any, Mapping
from uuid import uuid4

from event_outbox import DuplicateOutboxEvent, append_event


KNOWN_SPIRIT_IDS = (
    "ink_drop_kelpie",
    "whispering_void_kit",
    "star_shell_hatchling",
    "starpath_antlerling",
    "fatty",
    "obsidian_bastion",
)

# Data, not control flow: all six canonical catalog entries are validated by
# the same lineage contract; future entries can be added by catalog
# governance without new per-ID behavior branches.
SPIRIT_SLOT_ORDER = KNOWN_SPIRIT_IDS
# The first three are the existing level-gated unlocks.  Slots 4-6 remain
# catalog-registered but deliberately have no invented level gate until an
# authoritative Adventure/Boss/Quest settlement is approved.
SPIRIT_UNLOCK_LEVEL_THRESHOLDS = (None, 11, 16, None, None, None)

LEGACY_COSMETIC_PET_IDS = frozenset(
    {
        "pet_cat",
        "pet_turtle",
        "pet_rabbit",
        "pet_fox",
        "pet_wolf",
        "pet_dragon",
        "pet_premium",
    }
)

COMPANION_OPERATION_TYPES = frozenset(
    {
        "FEED",
        "TRAIN",
        "UNLOCK",
        "SWITCH",
        "ITEM_USE",
        "REWARD_GRANT",
        "EVOLUTION",
    }
)

OUTCOMES = frozenset({"SUCCESS", "FAILED", "UNKNOWN", "UNVERIFIED"})
TERMINAL_OPERATION_STATUSES = frozenset(
    {"SUCCESS", "FAILED", "UNKNOWN", "UNVERIFIED"}
)

SPIRIT_EFFECT_EVENT_TYPE = "SPIRIT_EFFECT_TRIGGERED"
SPIRIT_EFFECT_EVENT_CONTRACT_VERSION = "SPIRIT_EFFECT_EVENT_V1"
SPIRIT_EFFECT_SOURCE_AUTHORITY = "server_combat_settlement"
SPIRIT_EFFECT_TRIGGER_PHASE = "POST_JUDGE"
SPIRIT_EFFECT_STAGE_VALUES = frozenset({"STAGE_I", "STAGE_II", "STAGE_III"})
_SPIRIT_EFFECT_LEGACY_TRIGGER_PHASES = frozenset({"AFTER_SETTLEMENT", "POST_JUDGE"})
_SPIRIT_EFFECT_NUMERIC_FIELDS = frozenset(
    {
        "damage_before_spirit",
        "damage_after_spirit",
        "modifier_delta",
        "player_hp_before",
        "monster_hp_before",
    }
)
_SPIRIT_EFFECT_FORBIDDEN_KEYS = frozenset(
    {
        "answer_correct",
        "correct",
        "correctness",
        "grade",
        "is_correct",
        "player_answer",
        "score",
        "success",
    }
)

REWARD_SOURCE_TYPES = frozenset(
    {
        "QUESTION_REVIEW_SETTLEMENT",
        "ADVENTURE",
        "MONSTER",
        "BOSS_LORD",
        "QUEST",
        "DAILY_TRAINING",
        "EVOLUTION_MILESTONE",
        "ADMIN",
        "OTHER_AUTHORITATIVE_SETTLEMENT",
    }
)
NON_REWARD_SOURCES = frozenset({"REPLAY", "CINEMATIC", "SCENE_OVERRIDE"})
FUNCTIONAL_REWARD_TYPES = frozenset(
    {
        "SPIRIT_XP",
        "FOOD",
        "EVOLUTION_MATERIAL",
        "SPIRIT_RELIC",
        "ORNAMENT",
        "SKIN",
        "AURA_TRAIL",
    }
)

TRANSACTIONAL_EVENT_CONTRACTS = {
    "spirit_unlocked": "canonical ownership mutation",
    "spirit_selected": "canonical active-state mutation",
    "spirit_xp_gained": "committed XP/progression settlement",
    "spirit_level_up": "derived from committed Spirit progression",
    "spirit_evolved": "derived from committed level transition",
    "spirit_effect_triggered": "committed server effect result",
    "spirit_relic_equipped": "committed functional equipment mutation",
    "spirit_item_used": "committed D5C item-use mutation",
    "spirit_reward_granted": "committed reward authority plus D5A evidence",
    "spirit_cosmetic_equipped": "committed cosmetic selection mutation",
}

# Analytics consumers may subscribe to these committed facts.  They never
# authorize or retry a business mutation.
ANALYTICS_EVENT_CONTRACTS = tuple(TRANSACTIONAL_EVENT_CONTRACTS)

COMPANION_OPERATION_RECORD_CONTRACT = {
    "authority": "Lane B caller-owned durable operation record",
    "unique_key": ("user_id", "operation_type", "operation_id"),
    "required_fields": (
        "operation_id",
        "user_id",
        "operation_type",
        "request_fingerprint",
        "target_spirit_id",
        "target_item_id",
        "policy_version",
        "operation_status",
        "result_payload",
        "created_at",
        "committed_at",
    ),
    "replay": "same identity and fingerprint returns committed result",
    "conflict": "same identity with different fingerprint fails closed",
}

LEGACY_RESOURCE_ADAPTER_CONTRACT = {
    "authority": "pet_inventory.item_key",
    "mutation": "conditional decrement where qty > 0",
    "negative_quantity": "forbidden",
    "double_submit": "one committed decrement per operation",
    "big_bang_migration": False,
}

EVOLUTION_THRESHOLDS = ((10, "STAGE_I", "STAGE_II"), (25, "STAGE_II", "STAGE_III"))

_OPERATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_VOLATILE_KEYS = frozenset(
    {
        "created_at",
        "event_id",
        "occurred_at",
        "request_id",
        "timestamp",
        "client_timestamp",
        "nonce",
        "presentation",
        "render_state",
    }
)


class SpiritContractError(ValueError):
    """The proposed contract payload is not safe or canonical."""


class SpiritOperationConflict(SpiritContractError):
    """One operation identity was bound to a different logical request."""


class SpiritWrongUser(SpiritContractError):
    """An operation identity was presented by the wrong authenticated user."""


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpiritContractError(f"{field} must be a non-empty string")
    return value.strip()


def _require_user_id(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SpiritContractError("user_id must be a positive authenticated integer")
    return value


def is_legacy_cosmetic_pet(pet_id: Any) -> bool:
    return isinstance(pet_id, str) and pet_id.strip() in LEGACY_COSMETIC_PET_IDS


def validate_functional_spirit_id(spirit_id: Any) -> str:
    value = _require_text(spirit_id, "spirit_id")
    if is_legacy_cosmetic_pet(value):
        raise SpiritContractError("legacy cosmetic Pet is not a functional Spirit")
    if value not in KNOWN_SPIRIT_IDS:
        raise SpiritContractError("unknown functional Spirit ID")
    return value


def normalize_companion_operation_id(candidate: Any = None) -> tuple[str, bool]:
    """Validate a proposed identity or generate a server-bound one.

    The boolean is ``True`` only when the identity was server-generated.  A
    client proposal remains an opaque request key; it never grants ownership,
    eligibility, quantity, effect, or progression authority.
    """

    generated = candidate is None
    value = str(uuid4()) if generated else _require_text(candidate, "operation_id")
    if len(value) > 128 or not _OPERATION_ID_RE.fullmatch(value):
        raise SpiritContractError("operation_id has an invalid format or length")
    return value, generated


def _canonicalize(value: Any, *, path: str = "payload") -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            key_text = _require_text(str(key), f"{path} key")
            normalized_key = key_text.lower()
            if normalized_key in _VOLATILE_KEYS or normalized_key.startswith("client_"):
                raise SpiritContractError(f"{path}.{key_text} is not a business identity field")
            result[key_text] = _canonicalize(child, path=f"{path}.{key_text}")
        return result
    if isinstance(value, (list, tuple)):
        return [_canonicalize(child, path=f"{path}[]") for child in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise SpiritContractError(f"{path} contains a non-JSON value")


def canonical_companion_payload(
    *,
    user_id: int,
    operation_type: str,
    spirit_id: str | None = None,
    item_id: str | None = None,
    policy_version: str = "E10_SPIRIT_S1_V1",
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the server-defined identity payload without volatile fields."""

    user_id = _require_user_id(user_id)
    operation_type = _require_text(operation_type, "operation_type").upper()
    if operation_type not in COMPANION_OPERATION_TYPES:
        raise SpiritContractError(f"unsupported Companion operation type: {operation_type}")
    if spirit_id is not None:
        spirit_id = validate_functional_spirit_id(spirit_id)
    if item_id is not None:
        item_id = _require_text(item_id, "item_id")
        if is_legacy_cosmetic_pet(item_id):
            raise SpiritContractError("legacy cosmetic Pet cannot be a functional item target")
    policy_version = _require_text(policy_version, "policy_version")
    canonical_payload = {
        "user_id": user_id,
        "operation_type": operation_type,
        "spirit_id": spirit_id,
        "item_id": item_id,
        "policy_version": policy_version,
        "payload": _canonicalize(payload or {}),
    }
    return canonical_payload


def companion_request_fingerprint(canonical_payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _canonicalize(canonical_payload),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_companion_operation_identity(
    *,
    user_id: int,
    operation_type: str,
    operation_id: Any = None,
    spirit_id: str | None = None,
    item_id: str | None = None,
    policy_version: str = "E10_SPIRIT_S1_V1",
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    operation_id, server_generated = normalize_companion_operation_id(operation_id)
    canonical_payload = canonical_companion_payload(
        user_id=user_id,
        operation_type=operation_type,
        spirit_id=spirit_id,
        item_id=item_id,
        policy_version=policy_version,
        payload=payload,
    )
    return {
        "operation_id": operation_id,
        "user_id": canonical_payload["user_id"],
        "operation_type": canonical_payload["operation_type"],
        "target_spirit_id": canonical_payload["spirit_id"],
        "target_item_id": canonical_payload["item_id"],
        "policy_version": canonical_payload["policy_version"],
        "request_payload": canonical_payload,
        "request_fingerprint": companion_request_fingerprint(canonical_payload),
        "server_generated_identity": server_generated,
        "client_identity_is_authority": False,
    }


def classify_operation_replay(
    existing: Mapping[str, Any], requested: Mapping[str, Any], *, authenticated_user_id: int
) -> str:
    """Return ``NEW``, ``REPLAY``, ``CONFLICT``, ``WRONG_USER`` or ``IN_PROGRESS``."""

    authenticated_user_id = _require_user_id(authenticated_user_id)
    if existing.get("user_id") != authenticated_user_id:
        raise SpiritWrongUser("operation identity is not bound to this authenticated user")
    if existing.get("operation_id") != requested.get("operation_id"):
        return "CONFLICT"
    comparable = (
        "operation_type",
        "target_spirit_id",
        "target_item_id",
        "request_fingerprint",
    )
    if any(existing.get(field) != requested.get(field) for field in comparable):
        raise SpiritOperationConflict("same operation identity has a different canonical payload")
    status = str(existing.get("operation_status", "")).upper()
    if status in TERMINAL_OPERATION_STATUSES:
        return "REPLAY"
    if status == "PENDING":
        return "IN_PROGRESS"
    raise SpiritContractError("operation record has an unsupported status")


def _validate_outcome(outcome: str) -> str:
    outcome = _require_text(outcome, "outcome").upper()
    if outcome not in OUTCOMES:
        raise SpiritContractError(f"unsupported outcome: {outcome}")
    return outcome


def build_spirit_reward_payload(
    *,
    user_id: int,
    operation_id: str,
    lineage_id: str,
    source_type: str,
    source_id: str,
    reward_type: str,
    reward_key: str,
    quantity: int | float,
    policy_version: str = "E10_SPIRIT_S1_V1",
    spirit_id: str | None = None,
    outcome: str = "SUCCESS",
) -> dict[str, Any]:
    """Build the D5A payload for one committed functional Spirit reward."""

    user_id = _require_user_id(user_id)
    operation_id = _require_text(operation_id, "operation_id")
    lineage_id = _require_text(lineage_id, "lineage_id")
    source_type = _require_text(source_type, "source_type").upper()
    source_id = _require_text(source_id, "source_id")
    reward_type = _require_text(reward_type, "reward_type").upper()
    reward_key = _require_text(reward_key, "reward_key")
    policy_version = _require_text(policy_version, "policy_version")
    outcome = _validate_outcome(outcome)
    if source_type in NON_REWARD_SOURCES:
        raise SpiritContractError("replay/cinematic sources cannot create functional rewards")
    if source_type not in REWARD_SOURCE_TYPES:
        raise SpiritContractError(f"unsupported authoritative reward source: {source_type}")
    if reward_type not in FUNCTIONAL_REWARD_TYPES:
        raise SpiritContractError(f"unsupported Spirit reward type: {reward_type}")
    if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or quantity <= 0:
        raise SpiritContractError("reward quantity/value must be positive")
    if spirit_id is not None:
        spirit_id = validate_functional_spirit_id(spirit_id)
    return {
        "lineage_kind": "SPIRIT_REWARD",
        "user_id": user_id,
        "operation_id": operation_id,
        "lineage_id": lineage_id,
        "spirit_id": spirit_id,
        "source_type": source_type,
        "source_id": source_id,
        "reward_type": reward_type,
        "reward_key": reward_key,
        "quantity": quantity,
        "policy_version": policy_version,
        "outcome": outcome,
        "analytics_is_source_of_truth": False,
    }


def append_spirit_reward_event(
    conn: Any,
    *,
    user_id: int,
    operation_id: str,
    lineage_id: str,
    source_type: str,
    source_id: str,
    reward_type: str,
    reward_key: str,
    quantity: int | float,
    policy_version: str = "E10_SPIRIT_S1_V1",
    spirit_id: str | None = None,
    outcome: str = "SUCCESS",
    source_event_id: str | None = None,
) -> dict[str, Any]:
    payload = build_spirit_reward_payload(
        user_id=user_id,
        operation_id=operation_id,
        lineage_id=lineage_id,
        source_type=source_type,
        source_id=source_id,
        reward_type=reward_type,
        reward_key=reward_key,
        quantity=quantity,
        policy_version=policy_version,
        spirit_id=spirit_id,
        outcome=outcome,
    )
    return append_event(
        conn,
        event_type="ITEM_ACQUISITION",
        player_id=str(user_id),
        lineage_id=lineage_id,
        source_event_id=source_event_id,
        idempotency_key=f"spirit-reward:{operation_id}:{reward_key}",
        outcome=payload["outcome"],
        payload=payload,
    )


def build_spirit_item_use_payload(
    *,
    user_id: int,
    operation_id: str,
    lineage_id: str,
    spirit_id: str,
    item_id: str,
    quantity_before: int,
    quantity_delta: int,
    quantity_after: int,
    effect_applied: bool,
    effect_id: str | None = None,
    effect_type: str | None = None,
    effect_result: Mapping[str, Any] | None = None,
    outcome: str = "SUCCESS",
) -> dict[str, Any]:
    """Build the D5C payload for one committed functional Spirit item use."""

    user_id = _require_user_id(user_id)
    operation_id = _require_text(operation_id, "operation_id")
    lineage_id = _require_text(lineage_id, "lineage_id")
    spirit_id = validate_functional_spirit_id(spirit_id)
    item_id = _require_text(item_id, "item_id")
    if is_legacy_cosmetic_pet(item_id):
        raise SpiritContractError("legacy cosmetic Pet cannot be consumed as a Spirit item")
    if isinstance(quantity_before, bool) or not isinstance(quantity_before, int) or quantity_before < 0:
        raise SpiritContractError("quantity_before must be a non-negative integer")
    if isinstance(quantity_delta, bool) or not isinstance(quantity_delta, int) or quantity_delta >= 0:
        raise SpiritContractError("quantity_delta must be negative for a consume")
    if isinstance(quantity_after, bool) or not isinstance(quantity_after, int) or quantity_after < 0:
        raise SpiritContractError("quantity_after must be a non-negative integer")
    if quantity_after != quantity_before + quantity_delta:
        raise SpiritContractError("quantity transition is not arithmetically consistent")
    outcome = _validate_outcome(outcome)
    if outcome == "SUCCESS" and not effect_applied:
        raise SpiritContractError("successful item use must prove effect_applied")
    if effect_id is not None:
        effect_id = _require_text(effect_id, "effect_id")
    if effect_type is not None:
        effect_type = _require_text(effect_type, "effect_type")
    result = _canonicalize(effect_result or {}, path="effect_result")
    return {
        "lineage_kind": "SPIRIT_ITEM_USE",
        "user_id": user_id,
        "operation_id": operation_id,
        "lineage_id": lineage_id,
        "spirit_id": spirit_id,
        "item_id": item_id,
        "quantity_before": quantity_before,
        "quantity_delta": quantity_delta,
        "quantity_after": quantity_after,
        "effect_applied": bool(effect_applied),
        "effect_id": effect_id,
        "effect_type": effect_type,
        "effect_result": result,
        "outcome": outcome,
        "analytics_is_source_of_truth": False,
    }


def append_spirit_item_use_event(
    conn: Any,
    *,
    user_id: int,
    operation_id: str,
    lineage_id: str,
    spirit_id: str,
    item_id: str,
    quantity_before: int,
    quantity_delta: int,
    quantity_after: int,
    effect_applied: bool,
    effect_id: str | None = None,
    effect_type: str | None = None,
    effect_result: Mapping[str, Any] | None = None,
    outcome: str = "SUCCESS",
    source_event_id: str | None = None,
) -> dict[str, Any]:
    payload = build_spirit_item_use_payload(
        user_id=user_id,
        operation_id=operation_id,
        lineage_id=lineage_id,
        spirit_id=spirit_id,
        item_id=item_id,
        quantity_before=quantity_before,
        quantity_delta=quantity_delta,
        quantity_after=quantity_after,
        effect_applied=effect_applied,
        effect_id=effect_id,
        effect_type=effect_type,
        effect_result=effect_result,
        outcome=outcome,
    )
    return append_event(
        conn,
        event_type="ITEM_CONSUME_EFFECT",
        player_id=str(user_id),
        lineage_id=lineage_id,
        source_event_id=source_event_id,
        idempotency_key=f"spirit-item-use:{operation_id}",
        outcome=payload["outcome"],
        payload=payload,
    )


def validate_legacy_resource_update(
    *, quantity_before: int, requested_quantity: int, quantity_after: int, affected_rows: int
) -> bool:
    """Validate the adapter's conditional ``qty > 0`` decrement result."""

    return (
        isinstance(quantity_before, int)
        and not isinstance(quantity_before, bool)
        and quantity_before >= 0
        and isinstance(requested_quantity, int)
        and not isinstance(requested_quantity, bool)
        and requested_quantity > 0
        and isinstance(quantity_after, int)
        and not isinstance(quantity_after, bool)
        and quantity_after >= 0
        and quantity_after == quantity_before - requested_quantity
        and affected_rows == 1
    )


def validate_feed_result(result: Mapping[str, Any], *, replay: bool = False) -> bool:
    if not result.get("target_owned") or not result.get("consumable_owned"):
        return False
    if replay:
        return result.get("status") == "REPLAY" and result.get("new_consumption_count") == 0
    return (
        result.get("status") == "SUCCESS"
        and result.get("quantity_before", 0) >= 1
        and result.get("quantity_after") == result.get("quantity_before") - 1
        and result.get("consumed_quantity") == 1
        and result.get("effect_application_count") == 1
    )


def validate_train_result(result: Mapping[str, Any], *, replay: bool = False) -> bool:
    if not result.get("target_owned") or not result.get("cooldown_passed"):
        return False
    if replay:
        return result.get("status") == "REPLAY" and result.get("new_training_count") == 0
    return (
        result.get("status") == "SUCCESS"
        and result.get("daily_count_before", 0) < result.get("daily_cap", 0)
        and result.get("daily_count_after") == result.get("daily_count_before") + 1
        and result.get("training_effect_count") == 1
    )


def unlock_eligibility(*, spirit_slot: int, highest_owned_spirit_level: int) -> bool:
    """Evaluate the accepted starter/level thresholds without ID branches."""

    if isinstance(spirit_slot, bool) or not isinstance(spirit_slot, int) or spirit_slot < 1:
        raise SpiritContractError("spirit_slot must be a positive integer")
    if isinstance(highest_owned_spirit_level, bool) or not isinstance(highest_owned_spirit_level, int):
        raise SpiritContractError("highest_owned_spirit_level must be an integer")
    if spirit_slot == 1:
        return True
    if spirit_slot > len(SPIRIT_UNLOCK_LEVEL_THRESHOLDS):
        return False
    threshold = SPIRIT_UNLOCK_LEVEL_THRESHOLDS[spirit_slot - 1]
    return threshold is not None and highest_owned_spirit_level >= threshold


def validate_unlock_result(result: Mapping[str, Any], *, already_owned: bool = False) -> bool:
    if result.get("changed_target"):
        return False
    if already_owned:
        return result.get("status") == "REPLAY" and result.get("ownership_insert_count") == 0 and result.get("reward_count") == 0
    return (
        result.get("eligible") is True
        and result.get("status") == "SUCCESS"
        and result.get("ownership_insert_count") == 1
        and result.get("reward_count") <= 1
    )


def validate_switch_result(result: Mapping[str, Any], *, replay: bool = False) -> bool:
    if replay:
        return result.get("status") == "REPLAY" and result.get("active_spirit_id") == result.get("requested_spirit_id")
    if not result.get("target_owned"):
        return result.get("status") == "REJECTED_UNOWNED"
    if result.get("stale"):
        return result.get("status") == "REJECTED_STALE" and result.get("projection_mutation_count") == 0
    return result.get("status") == "SUCCESS" and result.get("active_spirit_id") == result.get("requested_spirit_id")


def evolution_stage_for_level(level: int) -> str:
    if isinstance(level, bool) or not isinstance(level, int) or level < 1:
        raise SpiritContractError("Spirit level must be a positive integer")
    if level >= 25:
        return "STAGE_III"
    if level >= 10:
        return "STAGE_II"
    return "STAGE_I"


def build_evolution_transitions(
    *,
    user_id: int,
    spirit_id: str,
    from_level: int,
    to_level: int,
    operation_id: str,
    lineage_id: str,
    source: str,
    policy_version: str = "E10_SPIRIT_S1_V1",
) -> tuple[dict[str, Any], ...]:
    """Derive one event per crossed threshold, in deterministic order."""

    user_id = _require_user_id(user_id)
    spirit_id = validate_functional_spirit_id(spirit_id)
    operation_id = _require_text(operation_id, "operation_id")
    lineage_id = _require_text(lineage_id, "lineage_id")
    source = _require_text(source, "source")
    policy_version = _require_text(policy_version, "policy_version")
    if isinstance(from_level, bool) or not isinstance(from_level, int) or from_level < 1:
        raise SpiritContractError("from_level must be a positive integer")
    if isinstance(to_level, bool) or not isinstance(to_level, int) or to_level < from_level:
        raise SpiritContractError("to_level must be >= from_level")
    transitions: list[dict[str, Any]] = []
    previous_level = from_level
    previous_stage = evolution_stage_for_level(from_level)
    for threshold, from_stage, to_stage in EVOLUTION_THRESHOLDS:
        if from_level < threshold <= to_level:
            transitions.append(
                {
                    "event_type": "spirit_evolved",
                    "event_id": f"{operation_id}:evolution:{to_stage}",
                    "lineage_id": lineage_id,
                    "operation_id": operation_id,
                    "user_id": user_id,
                    "spirit_id": spirit_id,
                    "from_stage": previous_stage,
                    "to_stage": to_stage,
                    "from_level": previous_level,
                    "to_level": threshold,
                    "source": source,
                    "policy_version": policy_version,
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "client_can_set_evolution": False,
                }
            )
            previous_level = threshold
            previous_stage = to_stage
    return tuple(transitions)


def validate_evolution_event(event: Mapping[str, Any]) -> bool:
    if event.get("client_can_set_evolution") is not False:
        return False
    if event.get("from_stage") != evolution_stage_for_level(int(event.get("from_level"))):
        return False
    if event.get("to_stage") != evolution_stage_for_level(int(event.get("to_level"))):
        return False
    return bool(event.get("operation_id")) and event.get("from_level") < event.get("to_level")


def _contains_forbidden_spirit_effect_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = str(key).strip().lower()
            if normalized_key.startswith("client_") or normalized_key in _SPIRIT_EFFECT_FORBIDDEN_KEYS:
                return True
            if _contains_forbidden_spirit_effect_key(child):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_forbidden_spirit_effect_key(child) for child in value)
    return False


def _optional_effect_number(value: Any, field: str, *, allow_negative: bool = False) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpiritContractError(f"{field} must be a finite number when supplied")
    if isinstance(value, float) and not math.isfinite(value):
        raise SpiritContractError(f"{field} must be a finite number when supplied")
    if not allow_negative and value < 0:
        raise SpiritContractError(f"{field} must be non-negative")
    return value


def _optional_effect_context(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise SpiritContractError("encounter_context must be a mapping when supplied")
    if _contains_forbidden_spirit_effect_key(value):
        raise SpiritContractError("encounter_context contains client/correctness authority")
    result = _canonicalize(value, path="encounter_context")
    if not isinstance(result, dict):  # pragma: no cover - guarded above
        raise SpiritContractError("encounter_context must be a mapping")
    return result


def _spirit_effect_payload_fingerprint(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _canonicalize(value, path="spirit_effect_payload"),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _spirit_effect_idempotency_key(
    *, user_id: int, source_settlement_id: str, spirit_id: str, effect_id: str
) -> str:
    identity = {
        "user_id": user_id,
        "source_settlement_id": source_settlement_id,
        "spirit_id": spirit_id,
        "effect_id": effect_id,
    }
    return f"spirit-effect:{_spirit_effect_payload_fingerprint(identity)}"


def build_spirit_effect_payload(
    *,
    user_id: int,
    spirit_id: str,
    source_settlement_id: str | None,
    effect_id: str | None,
    effect_policy_version: str | None = None,
    evolution_stage: str | None = None,
    encounter_class: str | None = None,
    encounter_context: Mapping[str, Any] | None = None,
    trigger_phase: str = SPIRIT_EFFECT_TRIGGER_PHASE,
    before_judge: bool = False,
    triggered: bool = True,
    ownership_validated: bool = True,
    enabled: bool = True,
    active: bool = True,
    effect_result: Mapping[str, Any] | None = None,
    damage_before_spirit: int | float | None = None,
    damage_after_spirit: int | float | None = None,
    modifier_delta: int | float | None = None,
    player_hp_before: int | float | None = None,
    monster_hp_before: int | float | None = None,
) -> dict[str, Any] | None:
    """Build one server-authored, post-judge Spirit effect fact.

    ``None`` is returned for a policy no-op, a non-owned/disabled/inactive
    projection, or a Lord encounter.  This helper never checks or mutates
    ownership and never decides the combat result; those facts must already
    have been established by the caller.
    """

    user_id = _require_user_id(user_id)
    if not isinstance(triggered, bool):
        raise SpiritContractError("triggered must be boolean")
    if not isinstance(ownership_validated, bool):
        raise SpiritContractError("ownership_validated must be boolean")
    if not isinstance(enabled, bool):
        raise SpiritContractError("enabled must be boolean")
    if not isinstance(active, bool):
        raise SpiritContractError("active must be boolean")
    if not triggered or not ownership_validated or not enabled or not active:
        return None

    spirit_id = validate_functional_spirit_id(spirit_id)
    if effect_result is not None:
        if not isinstance(effect_result, Mapping):
            raise SpiritContractError("effect_result must be a mapping when supplied")
        if _contains_forbidden_spirit_effect_key(effect_result):
            raise SpiritContractError("effect_result contains client/correctness authority")
        result_triggered = effect_result.get("triggered")
        if result_triggered is False:
            return None
        if result_triggered is not True:
            raise SpiritContractError("effect_result must prove triggered=true")
        result_spirit_id = effect_result.get("spirit_id")
        if result_spirit_id is not None and validate_functional_spirit_id(result_spirit_id) != spirit_id:
            raise SpiritContractError("effect_result Spirit identity does not match the request")
    source_settlement_id = _require_text(source_settlement_id, "source_settlement_id")
    effect_id = _require_text(effect_id, "effect_id")
    phase = _require_text(trigger_phase, "trigger_phase").upper()
    if phase in {"BEFORE_JUDGE", "JUDGE_INPUT"} or phase != SPIRIT_EFFECT_TRIGGER_PHASE:
        raise SpiritContractError("Spirit effect lineage must be POST_JUDGE")
    if before_judge is not False:
        raise SpiritContractError("Spirit effect lineage must set before_judge=false")

    normalized_encounter_class = (
        _require_text(encounter_class, "encounter_class").upper()
        if encounter_class is not None
        else None
    )
    if normalized_encounter_class == "LORD":
        return None

    if effect_policy_version is not None:
        effect_policy_version = _require_text(effect_policy_version, "effect_policy_version")
    if evolution_stage is not None:
        evolution_stage = _require_text(evolution_stage, "evolution_stage").upper()
        if evolution_stage not in SPIRIT_EFFECT_STAGE_VALUES:
            raise SpiritContractError("evolution_stage is not a canonical Spirit stage")
    context = _optional_effect_context(encounter_context)
    numeric_values = {
        "damage_before_spirit": _optional_effect_number(damage_before_spirit, "damage_before_spirit"),
        "damage_after_spirit": _optional_effect_number(damage_after_spirit, "damage_after_spirit"),
        "modifier_delta": _optional_effect_number(
            modifier_delta, "modifier_delta", allow_negative=True
        ),
        "player_hp_before": _optional_effect_number(player_hp_before, "player_hp_before"),
        "monster_hp_before": _optional_effect_number(monster_hp_before, "monster_hp_before"),
    }

    payload: dict[str, Any] = {
        "contract_version": SPIRIT_EFFECT_EVENT_CONTRACT_VERSION,
        "server_authored": True,
        "source_authority": SPIRIT_EFFECT_SOURCE_AUTHORITY,
        "user_id": user_id,
        "spirit_id": spirit_id,
        "effect_id": effect_id,
        "effect_policy_version": effect_policy_version,
        "evolution_stage": evolution_stage,
        "source_settlement_id": source_settlement_id,
        "encounter_class": normalized_encounter_class,
        "encounter_context": context,
        "trigger_phase": SPIRIT_EFFECT_TRIGGER_PHASE,
        "before_judge": False,
    }
    payload.update({key: value for key, value in numeric_values.items() if value is not None})
    if not validate_spirit_effect_event(payload):
        raise SpiritContractError("constructed Spirit effect event failed validation")
    return payload


def _same_spirit_effect_payload(existing: Mapping[str, Any], requested: Mapping[str, Any]) -> bool:
    existing_payload = existing.get("payload")
    if isinstance(existing_payload, str):
        try:
            existing_payload = json.loads(existing_payload)
        except (TypeError, ValueError):
            return False
    if not isinstance(existing_payload, Mapping):
        return False
    try:
        return _spirit_effect_payload_fingerprint(existing_payload) == _spirit_effect_payload_fingerprint(
            requested
        )
    except (SpiritContractError, TypeError, ValueError):
        return False


def append_spirit_effect_event(
    conn: Any,
    *,
    user_id: int,
    spirit_id: str,
    source_settlement_id: str | None,
    effect_id: str | None,
    effect_policy_version: str | None = None,
    evolution_stage: str | None = None,
    encounter_class: str | None = None,
    encounter_context: Mapping[str, Any] | None = None,
    trigger_phase: str = SPIRIT_EFFECT_TRIGGER_PHASE,
    before_judge: bool = False,
    triggered: bool = True,
    ownership_validated: bool = True,
    enabled: bool = True,
    active: bool = True,
    effect_result: Mapping[str, Any] | None = None,
    damage_before_spirit: int | float | None = None,
    damage_after_spirit: int | float | None = None,
    modifier_delta: int | float | None = None,
    player_hp_before: int | float | None = None,
    monster_hp_before: int | float | None = None,
    occurred_at: Any = None,
) -> dict[str, Any] | None:
    """Append one effect fact through the caller's open outbox transaction.

    The helper does not open a connection and never commits or rolls back.
    Duplicate logical events return the stored event as a replay.  A changed
    payload under the same logical identity raises ``SpiritOperationConflict``.
    """

    payload = build_spirit_effect_payload(
        user_id=user_id,
        spirit_id=spirit_id,
        source_settlement_id=source_settlement_id,
        effect_id=effect_id,
        effect_policy_version=effect_policy_version,
        evolution_stage=evolution_stage,
        encounter_class=encounter_class,
        encounter_context=encounter_context,
        trigger_phase=trigger_phase,
        before_judge=before_judge,
        triggered=triggered,
        ownership_validated=ownership_validated,
        enabled=enabled,
        active=active,
        effect_result=effect_result,
        damage_before_spirit=damage_before_spirit,
        damage_after_spirit=damage_after_spirit,
        modifier_delta=modifier_delta,
        player_hp_before=player_hp_before,
        monster_hp_before=monster_hp_before,
    )
    if payload is None:
        return None

    source_settlement_id = payload["source_settlement_id"]
    spirit_id = payload["spirit_id"]
    effect_id = payload["effect_id"]
    idempotency_key = _spirit_effect_idempotency_key(
        user_id=payload["user_id"],
        source_settlement_id=source_settlement_id,
        spirit_id=spirit_id,
        effect_id=effect_id,
    )
    try:
        result = append_event(
            conn,
            event_type=SPIRIT_EFFECT_EVENT_TYPE,
            player_id=str(payload["user_id"]),
            lineage_id=source_settlement_id,
            source_event_id=source_settlement_id,
            idempotency_key=idempotency_key,
            outcome="SUCCESS",
            payload=payload,
            occurred_at=occurred_at,
        )
    except DuplicateOutboxEvent as duplicate:
        existing = duplicate.existing_event
        if not _same_spirit_effect_payload(existing, payload):
            raise SpiritOperationConflict(
                "same Spirit effect identity has a different committed payload"
            ) from duplicate
        replay = dict(existing)
        replay["duplicate"] = True
        replay["replayed"] = True
        return replay
    result["replayed"] = False
    return result


def validate_spirit_effect_event(event: Mapping[str, Any]) -> bool:
    if not isinstance(event, Mapping):
        return False
    if _contains_forbidden_spirit_effect_key(event):
        return False
    try:
        spirit_id = validate_functional_spirit_id(event.get("spirit_id"))
        if not _require_text(event.get("effect_id"), "effect_id"):
            return False
        if not _require_text(event.get("source_settlement_id"), "source_settlement_id"):
            return False
        if event.get("before_judge") is not False:
            return False
        trigger_phase = _require_text(event.get("trigger_phase"), "trigger_phase").upper()
        if trigger_phase not in _SPIRIT_EFFECT_LEGACY_TRIGGER_PHASES:
            return False
        if trigger_phase in {"BEFORE_JUDGE", "JUDGE_INPUT"}:
            return False
        if event.get("triggered", True) is not True:
            return False
        if event.get("server_authored", True) is not True:
            return False
        for projection_field in ("ownership_validated", "enabled", "active"):
            if projection_field in event and event[projection_field] is not True:
                return False
        if event.get("contract_version") == SPIRIT_EFFECT_EVENT_CONTRACT_VERSION:
            if event.get("server_authored") is not True:
                return False
            if event.get("source_authority") != SPIRIT_EFFECT_SOURCE_AUTHORITY:
                return False
            if trigger_phase != SPIRIT_EFFECT_TRIGGER_PHASE:
                return False
        # D007's unversioned five-field contract remains readable for
        # compatibility.  Every D028-built event uses the versioned branch
        # above and therefore requires an explicit server-authored marker.
        elif "source_authority" in event and not _require_text(
            event.get("source_authority"), "source_authority"
        ):
            return False

        if event.get("user_id") is not None:
            _require_user_id(event["user_id"])
        if event.get("effect_policy_version") is not None:
            _require_text(event["effect_policy_version"], "effect_policy_version")
        if event.get("evolution_stage") is not None:
            stage = _require_text(event["evolution_stage"], "evolution_stage").upper()
            if stage not in SPIRIT_EFFECT_STAGE_VALUES:
                return False
        encounter_class = event.get("encounter_class")
        if encounter_class is not None:
            encounter_class = _require_text(encounter_class, "encounter_class").upper()
            if encounter_class == "LORD":
                return False
        if event.get("encounter_context") is not None:
            _optional_effect_context(event["encounter_context"])
        for field in _SPIRIT_EFFECT_NUMERIC_FIELDS:
            if field in event:
                _optional_effect_number(
                    event[field], field, allow_negative=field == "modifier_delta"
                )
        # Keep the local binding explicit for static analyzers and reviewers.
        if spirit_id not in KNOWN_SPIRIT_IDS:
            return False
        return True
    except (SpiritContractError, TypeError, ValueError):
        return False


def replay_creates_no_functional_reward(source_type: str) -> bool:
    return str(source_type).upper() in NON_REWARD_SOURCES


def legacy_pet_can_create_functional_state(pet_id: str) -> bool:
    return not is_legacy_cosmetic_pet(pet_id)


__all__ = [
    "ANALYTICS_EVENT_CONTRACTS",
    "COMPANION_OPERATION_RECORD_CONTRACT",
    "COMPANION_OPERATION_TYPES",
    "EVOLUTION_THRESHOLDS",
    "FUNCTIONAL_REWARD_TYPES",
    "KNOWN_SPIRIT_IDS",
    "LEGACY_COSMETIC_PET_IDS",
    "LEGACY_RESOURCE_ADAPTER_CONTRACT",
    "NON_REWARD_SOURCES",
    "OUTCOMES",
    "REWARD_SOURCE_TYPES",
    "SPIRIT_EFFECT_EVENT_CONTRACT_VERSION",
    "SPIRIT_EFFECT_EVENT_TYPE",
    "SPIRIT_EFFECT_SOURCE_AUTHORITY",
    "SPIRIT_EFFECT_TRIGGER_PHASE",
    "SPIRIT_EFFECT_STAGE_VALUES",
    "SPIRIT_SLOT_ORDER",
    "SPIRIT_UNLOCK_LEVEL_THRESHOLDS",
    "SpiritContractError",
    "SpiritOperationConflict",
    "SpiritWrongUser",
    "TRANSACTIONAL_EVENT_CONTRACTS",
    "append_spirit_item_use_event",
    "append_spirit_effect_event",
    "append_spirit_reward_event",
    "build_companion_operation_identity",
    "build_evolution_transitions",
    "build_spirit_item_use_payload",
    "build_spirit_effect_payload",
    "build_spirit_reward_payload",
    "canonical_companion_payload",
    "classify_operation_replay",
    "companion_request_fingerprint",
    "evolution_stage_for_level",
    "is_legacy_cosmetic_pet",
    "legacy_pet_can_create_functional_state",
    "normalize_companion_operation_id",
    "replay_creates_no_functional_reward",
    "unlock_eligibility",
    "validate_evolution_event",
    "validate_feed_result",
    "validate_functional_spirit_id",
    "validate_legacy_resource_update",
    "validate_spirit_effect_event",
    "validate_switch_result",
    "validate_train_result",
    "validate_unlock_result",
]
