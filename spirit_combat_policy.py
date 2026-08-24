"""Pure server policy for the owner-locked Six-Spirit Combat V1 matrix.

This module is deliberately not a combat settlement engine.  It consumes a
transaction-local, server-owned Spirit projection and already-settled B021
combat facts, then returns one deterministic effect record.  It does not read
the database, inspect browser input, mutate combat state, or apply equipment
or armor calculations.

The future B027-R2 integration point is the single public evaluator below.
The policy is data-driven by trigger/effect descriptors so adding a profile
within an existing supported effect type does not require another combat
engine branch.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from spirit_runtime import CANONICAL_SPIRIT_IDS


SPIRIT_POLICY_VERSION = "spirit_combat_v1"
SPIRIT_COMBAT_POLICY_COUNT = 1
SPIRIT_COMBAT_EVALUATOR_COUNT = 1
CANONICAL_SPIRIT_COUNT = 6
MAX_ACTIVE_COMBAT_SPIRIT_EFFECTS = 1
WITHIN_STAGE_SCALING = False

STAGE_VALUES = ("STAGE_I", "STAGE_II", "STAGE_III")

_VALID_ENCOUNTER_CLASSES = frozenset(
    {
        "COMMON",
        "NORMAL_MONSTER",
        "RARE",
        "ELITE",
        "BATTLEFIELD_BOSS",
        "LORD",
    }
)

# This is the one locked Combat V1 policy.  Percentages are integer
# percentage points and are intentionally not derived from Spirit level.
SPIRIT_COMBAT_POLICY: dict[str, dict[str, Any]] = {
    "ink_drop_kelpie": {
        "role": "Training",
        "trigger": "CORRECT",
        "effect_type": "OUTGOING_DAMAGE_PERCENT_BONUS",
        "percent_by_stage": {"STAGE_I": 5, "STAGE_II": 7, "STAGE_III": 9},
    },
    "whispering_void_kit": {
        "role": "Review",
        "trigger": "INCORRECT_POSITIVE_RETALIATION",
        "effect_type": "INCOMING_DAMAGE_PERCENT_REDUCTION_MIN_ONE",
        "percent_by_stage": {"STAGE_I": 8, "STAGE_II": 12, "STAGE_III": 16},
    },
    "star_shell_hatchling": {
        "role": "Challenge",
        "trigger": "CORRECT_BATTLEFIELD_BOSS",
        "effect_type": "OUTGOING_DAMAGE_PERCENT_BONUS",
        "percent_by_stage": {"STAGE_I": 6, "STAGE_II": 9, "STAGE_III": 12},
    },
    "starpath_antlerling": {
        "role": "Exploration",
        "trigger": "CORRECT_FULL_MONSTER_HP",
        "effect_type": "OUTGOING_DAMAGE_PERCENT_BONUS",
        "percent_by_stage": {"STAGE_I": 10, "STAGE_II": 15, "STAGE_III": 20},
    },
    "fatty": {
        "role": "Precision",
        "trigger": "CORRECT_MONSTER_AT_OR_BELOW_35_PERCENT",
        "effect_type": "OUTGOING_DAMAGE_PERCENT_BONUS",
        "percent_by_stage": {"STAGE_I": 10, "STAGE_II": 15, "STAGE_III": 20},
    },
    "obsidian_bastion": {
        "role": "Support",
        "trigger": "POSITIVE_INCOMING_PLAYER_AT_OR_BELOW_35_PERCENT",
        "effect_type": "INCOMING_DAMAGE_PERCENT_REDUCTION",
        "percent_by_stage": {"STAGE_I": 20, "STAGE_II": 30, "STAGE_III": 40},
    },
}


def _neutral_result(
    *,
    spirit_id: str | None,
    role: str | None,
    stage: str | None,
    reason: str,
    input_damage: int | None = None,
) -> dict[str, Any]:
    return {
        "spirit_id": spirit_id,
        "role": role,
        "triggered": False,
        "effect_type": "NONE",
        "stage": stage,
        "input_damage": input_damage,
        "modifier": 0,
        "effect_amount": 0,
        "output_damage": input_damage,
        "reason": reason,
        "policy_version": SPIRIT_POLICY_VERSION,
    }


def _read_nonnegative_int(
    facts: Mapping[str, Any], key: str, *, positive: bool = False
) -> tuple[int | None, bool]:
    if key not in facts or facts[key] is None:
        return None, True
    value = facts[key]
    if isinstance(value, bool) or not isinstance(value, int):
        return None, False
    if value < 0 or (positive and value <= 0):
        return None, False
    return value, True


def _validate_numeric_facts(facts: Mapping[str, Any]) -> tuple[dict[str, int | None], bool]:
    fields = (
        "outgoing_damage_after_equipment",
        "incoming_damage_after_armor",
        "monster_hp_before",
        "monster_max_hp",
        "player_hp_before",
        "player_max_hp",
    )
    values: dict[str, int | None] = {}
    for key in fields:
        value, valid = _read_nonnegative_int(facts, key)
        if not valid:
            return {}, False
        values[key] = value

    for key in ("monster_max_hp", "player_max_hp"):
        value = values[key]
        if value is not None and value <= 0:
            return {}, False

    for before_key, max_key in (
        ("monster_hp_before", "monster_max_hp"),
        ("player_hp_before", "player_max_hp"),
    ):
        before = values[before_key]
        maximum = values[max_key]
        if before is not None and maximum is not None and before > maximum:
            return {}, False

    return values, True


def _validate_projection(facts: Mapping[str, Any]) -> tuple[str | None, str | None, str | None]:
    raw_id = facts.get("active_spirit_id")
    if raw_id is None or raw_id == "":
        return None, None, "NO_ACTIVE_SPIRIT"
    if not isinstance(raw_id, str) or raw_id not in CANONICAL_SPIRIT_IDS:
        return None, None, "UNKNOWN_SPIRIT"

    policy = SPIRIT_COMBAT_POLICY.get(raw_id)
    if policy is None:
        return None, None, "UNKNOWN_SPIRIT"

    if facts.get("ownership_validated") is not True or facts.get("enabled") is not True:
        return None, None, "INVALID_SPIRIT_PROJECTION"

    if "single_active_spirit" in facts and facts["single_active_spirit"] is not True:
        return None, None, "INVALID_SPIRIT_PROJECTION"

    supplied_policy_version = facts.get("effect_policy_version")
    if supplied_policy_version not in (None, SPIRIT_POLICY_VERSION):
        return None, None, "POLICY_VERSION_MISMATCH"

    stage = facts.get("evolution_stage")
    if stage not in STAGE_VALUES:
        return None, None, "INVALID_STAGE"

    return raw_id, policy["role"], None


def _validate_common_facts(facts: Mapping[str, Any], policy: Mapping[str, Any]) -> str | None:
    answer_correct = facts.get("answer_correct")
    if answer_correct is not None and not isinstance(answer_correct, bool):
        return "INVALID_ANSWER_CORRECT"
    if policy["trigger"] != "POSITIVE_INCOMING_PLAYER_AT_OR_BELOW_35_PERCENT" and not isinstance(answer_correct, bool):
        return "INVALID_ANSWER_CORRECT"

    encounter_class = facts.get("encounter_class")
    if (
        encounter_class is not None
        and (
            not isinstance(encounter_class, str)
            or encounter_class not in _VALID_ENCOUNTER_CLASSES
        )
    ):
        return "UNKNOWN_ENCOUNTER_CLASS"

    return None


def _trigger_result(
    policy: Mapping[str, Any],
    facts: Mapping[str, Any],
    values: Mapping[str, int | None],
) -> tuple[bool, str, str, int | None]:
    trigger = policy["trigger"]
    correct = facts.get("answer_correct")

    if trigger == "CORRECT":
        outgoing = values["outgoing_damage_after_equipment"]
        if outgoing is None:
            return False, "MISSING_COMBAT_FACT", "outgoing_damage_after_equipment", None
        return correct, "TRIGGER_MATCH" if correct else "TRIGGER_FALSE", "outgoing_damage_after_equipment", outgoing

    if trigger == "INCORRECT_POSITIVE_RETALIATION":
        incoming = values["incoming_damage_after_armor"]
        if correct:
            return False, "TRIGGER_FALSE", "incoming_damage_after_armor", incoming
        if incoming is None:
            return False, "MISSING_COMBAT_FACT", "incoming_damage_after_armor", None
        return incoming > 0, "TRIGGER_MATCH" if incoming > 0 else "TRIGGER_FALSE", "incoming_damage_after_armor", incoming

    if trigger == "CORRECT_BATTLEFIELD_BOSS":
        outgoing = values["outgoing_damage_after_equipment"]
        if not correct:
            return False, "TRIGGER_FALSE", "outgoing_damage_after_equipment", outgoing
        if facts.get("encounter_class") is None or outgoing is None:
            return False, "MISSING_COMBAT_FACT", "outgoing_damage_after_equipment", outgoing
        return facts["encounter_class"] == "BATTLEFIELD_BOSS", (
            "TRIGGER_MATCH" if facts["encounter_class"] == "BATTLEFIELD_BOSS" else "TRIGGER_FALSE"
        ), "outgoing_damage_after_equipment", outgoing

    if trigger == "CORRECT_FULL_MONSTER_HP":
        hp_before = values["monster_hp_before"]
        hp_max = values["monster_max_hp"]
        outgoing = values["outgoing_damage_after_equipment"]
        if not correct:
            return False, "TRIGGER_FALSE", "outgoing_damage_after_equipment", outgoing
        if hp_before is None or hp_max is None or outgoing is None:
            return False, "MISSING_COMBAT_FACT", "outgoing_damage_after_equipment", outgoing
        return hp_before == hp_max, "TRIGGER_MATCH" if hp_before == hp_max else "TRIGGER_FALSE", "outgoing_damage_after_equipment", outgoing

    if trigger == "CORRECT_MONSTER_AT_OR_BELOW_35_PERCENT":
        hp_before = values["monster_hp_before"]
        hp_max = values["monster_max_hp"]
        outgoing = values["outgoing_damage_after_equipment"]
        if not correct:
            return False, "TRIGGER_FALSE", "outgoing_damage_after_equipment", outgoing
        if hp_before is None or hp_max is None or outgoing is None:
            return False, "MISSING_COMBAT_FACT", "outgoing_damage_after_equipment", outgoing
        matched = hp_before * 100 <= hp_max * 35
        return matched, "TRIGGER_MATCH" if matched else "TRIGGER_FALSE", "outgoing_damage_after_equipment", outgoing

    if trigger == "POSITIVE_INCOMING_PLAYER_AT_OR_BELOW_35_PERCENT":
        incoming = values["incoming_damage_after_armor"]
        hp_before = values["player_hp_before"]
        hp_max = values["player_max_hp"]
        if incoming is None or hp_before is None or hp_max is None:
            return False, "MISSING_COMBAT_FACT", "incoming_damage_after_armor", incoming
        matched = incoming > 0 and hp_before * 100 <= hp_max * 35
        return matched, "TRIGGER_MATCH" if matched else "TRIGGER_FALSE", "incoming_damage_after_armor", incoming

    return False, "UNSUPPORTED_TRIGGER", "", None


def evaluate_spirit_combat_effect(facts: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate one active Spirit against authoritative combat facts.

    ``facts`` must be a server-owned projection.  The required projection
    fields are ``active_spirit_id``, ``ownership_validated``, ``enabled``, and
    ``evolution_stage``.  ``answer_correct`` and the relevant B021 effective
    damage/HP facts are supplied by the server settlement caller.  The
    evaluator never derives correctness, equipment damage, armor mitigation,
    Spirit ownership, or progression stage from client data.

    The returned ``modifier`` is an integer percentage-point value from the
    locked policy.  ``effect_amount`` is the integer damage-point delta.
    """

    if not isinstance(facts, Mapping):
        return _neutral_result(
            spirit_id=None,
            role=None,
            stage=None,
            reason="INVALID_INPUT",
        )

    spirit_id, role, projection_error = _validate_projection(facts)
    stage = (
        facts.get("evolution_stage")
        if projection_error is None and facts.get("evolution_stage") in STAGE_VALUES
        else None
    )
    if projection_error:
        return _neutral_result(
            spirit_id=spirit_id,
            role=role,
            stage=stage,
            reason=projection_error,
        )

    policy = SPIRIT_COMBAT_POLICY[spirit_id]
    common_error = _validate_common_facts(facts, policy)
    if common_error:
        return _neutral_result(
            spirit_id=spirit_id,
            role=role,
            stage=stage,
            reason=common_error,
        )

    values, numeric_valid = _validate_numeric_facts(facts)
    if not numeric_valid:
        return _neutral_result(
            spirit_id=spirit_id,
            role=role,
            stage=stage,
            reason="INVALID_COMBAT_INPUT",
        )

    triggered, reason, input_key, input_damage = _trigger_result(policy, facts, values)
    if not triggered:
        return _neutral_result(
            spirit_id=spirit_id,
            role=role,
            stage=stage,
            reason=reason,
            input_damage=input_damage,
        )

    percentage = int(policy["percent_by_stage"][stage])
    if input_damage is None:
        return _neutral_result(
            spirit_id=spirit_id,
            role=role,
            stage=stage,
            reason="MISSING_COMBAT_FACT",
        )
    if policy["effect_type"] == "OUTGOING_DAMAGE_PERCENT_BONUS":
        effect_amount = (input_damage * percentage) // 100
        output_damage = input_damage + effect_amount
    elif policy["effect_type"] == "INCOMING_DAMAGE_PERCENT_REDUCTION_MIN_ONE":
        effect_amount = min(input_damage, max(1, (input_damage * percentage) // 100))
        output_damage = input_damage - effect_amount
    elif policy["effect_type"] == "INCOMING_DAMAGE_PERCENT_REDUCTION":
        effect_amount = min(input_damage, (input_damage * percentage) // 100)
        output_damage = max(0, input_damage - effect_amount)
    else:  # Defensive guard if a policy record is malformed.
        return _neutral_result(
            spirit_id=spirit_id,
            role=role,
            stage=stage,
            reason="UNSUPPORTED_EFFECT_TYPE",
            input_damage=input_damage,
        )

    return {
        "spirit_id": spirit_id,
        "role": role,
        "triggered": True,
        "effect_type": policy["effect_type"],
        "stage": stage,
        "input_damage": input_damage,
        "modifier": percentage,
        "effect_amount": effect_amount,
        "output_damage": output_damage,
        "reason": "EFFECT_APPLIED",
        "policy_version": SPIRIT_POLICY_VERSION,
    }


__all__ = [
    "CANONICAL_SPIRIT_COUNT",
    "MAX_ACTIVE_COMBAT_SPIRIT_EFFECTS",
    "SPIRIT_COMBAT_EVALUATOR_COUNT",
    "SPIRIT_COMBAT_POLICY",
    "SPIRIT_COMBAT_POLICY_COUNT",
    "SPIRIT_POLICY_VERSION",
    "STAGE_VALUES",
    "WITHIN_STAGE_SCALING",
    "evaluate_spirit_combat_effect",
]
