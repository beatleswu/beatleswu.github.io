"""Focused tests for the owner-locked, pure Six-Spirit Combat V1 policy."""

from __future__ import annotations

import pytest

from spirit_combat_policy import (
    CANONICAL_SPIRIT_COUNT,
    MAX_ACTIVE_COMBAT_SPIRIT_EFFECTS,
    SPIRIT_COMBAT_EVALUATOR_COUNT,
    SPIRIT_COMBAT_POLICY,
    SPIRIT_COMBAT_POLICY_COUNT,
    SPIRIT_POLICY_VERSION,
    WITHIN_STAGE_SCALING,
    evaluate_spirit_combat_effect,
)


def _facts(spirit_id: str, stage: str = "STAGE_I", **overrides):
    facts = {
        "active_spirit_id": spirit_id,
        "ownership_validated": True,
        "enabled": True,
        "evolution_stage": stage,
        "answer_correct": True,
        "encounter_class": "COMMON",
        "outgoing_damage_after_equipment": 100,
        "incoming_damage_after_armor": 100,
        "monster_hp_before": 100,
        "monster_max_hp": 100,
        "player_hp_before": 100,
        "player_max_hp": 100,
    }
    facts.update(overrides)
    return facts


def _evaluate(spirit_id: str, stage: str = "STAGE_I", **overrides):
    return evaluate_spirit_combat_effect(_facts(spirit_id, stage, **overrides))


def test_one_policy_one_evaluator_and_exact_catalog():
    assert SPIRIT_COMBAT_POLICY_COUNT == 1
    assert SPIRIT_COMBAT_EVALUATOR_COUNT == 1
    assert CANONICAL_SPIRIT_COUNT == 6
    assert MAX_ACTIVE_COMBAT_SPIRIT_EFFECTS == 1
    assert WITHIN_STAGE_SCALING is False
    assert tuple(SPIRIT_COMBAT_POLICY) == (
        "ink_drop_kelpie",
        "whispering_void_kit",
        "star_shell_hatchling",
        "starpath_antlerling",
        "fatty",
        "obsidian_bastion",
    )


@pytest.mark.parametrize(
    ("spirit_id", "overrides", "effect_type", "expected"),
    [
        (
            "ink_drop_kelpie",
            {"answer_correct": True},
            "OUTGOING_DAMAGE_PERCENT_BONUS",
            (5, 105),
        ),
        (
            "whispering_void_kit",
            {"answer_correct": False},
            "INCOMING_DAMAGE_PERCENT_REDUCTION_MIN_ONE",
            (8, 92),
        ),
        (
            "star_shell_hatchling",
            {"encounter_class": "BATTLEFIELD_BOSS"},
            "OUTGOING_DAMAGE_PERCENT_BONUS",
            (6, 106),
        ),
        (
            "starpath_antlerling",
            {},
            "OUTGOING_DAMAGE_PERCENT_BONUS",
            (10, 110),
        ),
        (
            "fatty",
            {"monster_hp_before": 35, "monster_max_hp": 100},
            "OUTGOING_DAMAGE_PERCENT_BONUS",
            (10, 110),
        ),
        (
            "obsidian_bastion",
            {"player_hp_before": 35, "player_max_hp": 100},
            "INCOMING_DAMAGE_PERCENT_REDUCTION",
            (20, 80),
        ),
    ],
)
def test_stage_i_locked_matrix(spirit_id, overrides, effect_type, expected):
    result = _evaluate(spirit_id, **overrides)
    assert result["triggered"] is True
    assert result["effect_type"] == effect_type
    assert result["modifier"] == expected[0]
    assert result["effect_amount"] == expected[0]
    assert result["output_damage"] == expected[1]
    assert result["policy_version"] == SPIRIT_POLICY_VERSION


@pytest.mark.parametrize(
    ("spirit_id", "overrides", "expected"),
    [
        ("ink_drop_kelpie", {}, (5, 7, 9)),
        ("whispering_void_kit", {"answer_correct": False}, (8, 12, 16)),
        ("star_shell_hatchling", {"encounter_class": "BATTLEFIELD_BOSS"}, (6, 9, 12)),
        ("starpath_antlerling", {}, (10, 15, 20)),
        ("fatty", {"monster_hp_before": 35, "monster_max_hp": 100}, (10, 15, 20)),
        ("obsidian_bastion", {"player_hp_before": 35, "player_max_hp": 100}, (20, 30, 40)),
    ],
)
def test_all_locked_stage_percentages(spirit_id, overrides, expected):
    for stage, percentage in zip(("STAGE_I", "STAGE_II", "STAGE_III"), expected):
        result = _evaluate(spirit_id, stage, **overrides)
        assert result["triggered"] is True
        assert result["modifier"] == percentage


@pytest.mark.parametrize("spirit_id", tuple(SPIRIT_COMBAT_POLICY))
@pytest.mark.parametrize("stage", ("STAGE_I", "STAGE_II", "STAGE_III"))
def test_each_spirit_has_a_false_trigger_neutral_result(spirit_id, stage):
    overrides = {"answer_correct": False}
    if spirit_id == "whispering_void_kit":
        overrides["incoming_damage_after_armor"] = 0
    elif spirit_id == "star_shell_hatchling":
        overrides["encounter_class"] = "ELITE"
    elif spirit_id == "starpath_antlerling":
        overrides["monster_hp_before"] = 99
    elif spirit_id == "fatty":
        overrides["monster_hp_before"] = 36
    elif spirit_id == "obsidian_bastion":
        overrides["player_hp_before"] = 36
    result = _evaluate(spirit_id, stage, **overrides)
    assert result["triggered"] is False
    assert result["effect_type"] == "NONE"
    assert result["effect_amount"] == 0


@pytest.mark.parametrize(
    ("incoming", "expected_reduction", "expected_output"),
    [(1, 1, 0), (2, 1, 1), (5, 1, 4), (10, 1, 9), (100, 8, 92)],
)
def test_void_kit_minimum_one_and_cap(incoming, expected_reduction, expected_output):
    result = _evaluate(
        "whispering_void_kit",
        answer_correct=False,
        incoming_damage_after_armor=incoming,
    )
    assert result["effect_amount"] == expected_reduction
    assert result["output_damage"] == expected_output
    assert result["output_damage"] >= 0
    assert result["effect_amount"] <= incoming


def test_void_kit_zero_damage_does_not_trigger():
    result = _evaluate(
        "whispering_void_kit",
        answer_correct=False,
        incoming_damage_after_armor=0,
    )
    assert result["triggered"] is False
    assert result["effect_amount"] == 0
    assert result["output_damage"] == 0


def test_bastion_has_no_minimum_one_override():
    result = _evaluate(
        "obsidian_bastion",
        incoming_damage_after_armor=1,
        player_hp_before=35,
        player_max_hp=100,
    )
    assert result["triggered"] is True
    assert result["effect_amount"] == 0
    assert result["output_damage"] == 1


def test_bastion_uses_pre_damage_hp_not_post_damage_hp():
    result = _evaluate(
        "obsidian_bastion",
        incoming_damage_after_armor=100,
        player_hp_before=400,
        player_max_hp=1000,
    )
    assert result["triggered"] is False
    assert result["effect_amount"] == 0


@pytest.mark.parametrize("encounter_class,expected", [("COMMON", False), ("RARE", False), ("ELITE", False), ("BATTLEFIELD_BOSS", True), ("LORD", False)])
def test_hatchling_only_accepts_battlefield_boss(encounter_class, expected):
    result = _evaluate("star_shell_hatchling", encounter_class=encounter_class)
    assert result["triggered"] is expected


@pytest.mark.parametrize(
    ("hp_before", "hp_max", "expected"),
    [(100, 100, True), (99, 100, False), (0, 100, False)],
)
def test_antlerling_requires_exact_pre_hit_full_hp(hp_before, hp_max, expected):
    result = _evaluate(
        "starpath_antlerling",
        monster_hp_before=hp_before,
        monster_max_hp=hp_max,
    )
    assert result["triggered"] is expected


@pytest.mark.parametrize(
    ("hp_before", "hp_max", "expected"),
    [(349, 1000, True), (350, 1000, True), (351, 1000, False)],
)
def test_fatty_uses_integer_inclusive_pre_hit_threshold(hp_before, hp_max, expected):
    result = _evaluate(
        "fatty",
        monster_hp_before=hp_before,
        monster_max_hp=hp_max,
    )
    assert result["triggered"] is expected


@pytest.mark.parametrize(
    ("hp_before", "hp_max", "expected"),
    [(349, 1000, True), (350, 1000, True), (351, 1000, False)],
)
def test_bastion_uses_integer_inclusive_pre_damage_threshold(hp_before, hp_max, expected):
    result = _evaluate(
        "obsidian_bastion",
        incoming_damage_after_armor=10,
        player_hp_before=hp_before,
        player_max_hp=hp_max,
    )
    assert result["triggered"] is expected


@pytest.mark.parametrize(
    "facts",
    [
        {"active_spirit_id": "unknown_spirit"},
        {"active_spirit_id": "ink_drop_kelpie", "evolution_stage": "STAGE_IV"},
        {"active_spirit_id": "ink_drop_kelpie", "outgoing_damage_after_equipment": -1},
        {"active_spirit_id": "starpath_antlerling", "monster_hp_before": -1},
        {"active_spirit_id": "fatty", "monster_max_hp": 0},
        {"active_spirit_id": "obsidian_bastion", "player_max_hp": 0},
        {"active_spirit_id": "ink_drop_kelpie", "answer_correct": "true"},
        {"active_spirit_id": "star_shell_hatchling", "encounter_class": "UNKNOWN"},
        {"active_spirit_id": "star_shell_hatchling", "encounter_class": []},
    ],
)
def test_invalid_inputs_fail_closed_without_effect(facts):
    merged = _facts("ink_drop_kelpie")
    merged.update(facts)
    result = evaluate_spirit_combat_effect(merged)
    assert result["triggered"] is False
    assert result["effect_amount"] == 0
    assert result["effect_type"] == "NONE"


def test_invalid_projection_fails_closed():
    result = _evaluate("ink_drop_kelpie", ownership_validated=False)
    assert result["triggered"] is False
    assert result["reason"] == "INVALID_SPIRIT_PROJECTION"
    assert result["spirit_id"] is None
    assert result["stage"] is None


def test_missing_correct_answer_damage_fails_closed_without_assertion():
    facts = _facts("ink_drop_kelpie")
    facts.pop("outgoing_damage_after_equipment")
    result = evaluate_spirit_combat_effect(facts)
    assert result["triggered"] is False
    assert result["reason"] == "MISSING_COMBAT_FACT"
    assert result["effect_amount"] == 0
    assert result["output_damage"] is None


def test_bastion_does_not_require_answer_correct_when_its_facts_are_valid():
    facts = _facts(
        "obsidian_bastion",
        incoming_damage_after_armor=10,
        player_hp_before=35,
        player_max_hp=100,
    )
    facts.pop("answer_correct")
    result = evaluate_spirit_combat_effect(facts)
    assert result["triggered"] is True
    assert result["effect_amount"] == 2


def test_multiple_active_projection_flag_fails_closed():
    result = _evaluate("ink_drop_kelpie", single_active_spirit=False)
    assert result["triggered"] is False
    assert result["reason"] == "INVALID_SPIRIT_PROJECTION"


def test_missing_hatchling_encounter_class_fails_closed():
    facts = _facts("star_shell_hatchling")
    facts.pop("encounter_class")
    result = evaluate_spirit_combat_effect(facts)
    assert result["triggered"] is False
    assert result["reason"] == "MISSING_COMBAT_FACT"


def test_stage_is_consumed_from_authoritative_projection_without_scaling():
    stage_ii_low = _evaluate("ink_drop_kelpie", "STAGE_II", outgoing_damage_after_equipment=99)
    stage_ii_high = _evaluate("ink_drop_kelpie", "STAGE_II", outgoing_damage_after_equipment=99)
    stage_iii = _evaluate("ink_drop_kelpie", "STAGE_III", outgoing_damage_after_equipment=99)
    assert stage_ii_low == stage_ii_high
    assert stage_ii_low["modifier"] == 7
    assert stage_iii["modifier"] == 9


def test_kelpie_has_no_minimum_one_bonus_rule():
    result = _evaluate("ink_drop_kelpie", outgoing_damage_after_equipment=1)
    assert result["triggered"] is True
    assert result["effect_amount"] == 0
    assert result["output_damage"] == 1


def test_same_input_same_result_and_no_state_mutation():
    facts = _facts(
        "obsidian_bastion",
        stage="STAGE_III",
        incoming_damage_after_armor=37,
        player_hp_before=350,
        player_max_hp=1000,
    )
    before = dict(facts)
    first = evaluate_spirit_combat_effect(facts)
    second = evaluate_spirit_combat_effect(facts)
    assert first == second
    assert facts == before


def test_active_spirit_only_contract_has_no_stacking_surface():
    result = _evaluate("ink_drop_kelpie", outgoing_damage_after_equipment=100)
    assert result["spirit_id"] == "ink_drop_kelpie"
    assert result["effect_amount"] == 5
    assert MAX_ACTIVE_COMBAT_SPIRIT_EFFECTS == 1
