"""Owner-approved Zone 4-10 Monster economy policy contracts."""

import ast
from collections import Counter
from pathlib import Path

from adventure_zone4_10_monster_identity_authority import (
    ZONE4_10_MONSTER_IDENTITY_RECORD_COUNT,
    ZONE4_10_MONSTER_IDENTITIES,
)
from adventure_zone4_10_monster_reward_policy import (
    ADDITIONAL_FIRST_CLEAR_REWARD_BEYOND_F028,
    GACHA_ENABLEMENT,
    GLOBAL_COIN_DAILY_CAP,
    MONSTER_COIN_DAILY_CAP,
    MONSTER_SPECIFIC_XP,
    NORMAL_FIRST_DEFEAT_REWARD_POLICY,
    NORMAL_MONSTER_COIN_REWARD,
    PAYMENT_ENABLEMENT,
    PREMIUM_ENABLEMENT,
    QUEST_MID_BINDING,
    SHOP_EXPANSION,
    ZONE4_10_DROP_ELIGIBILITY,
    ZONE4_10_DROP_PROFILE,
    ZONE4_10_DROP_TABLES,
    get_zone4_10_monster_reward_policy,
    iter_zone4_10_monster_reward_policies,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY_SOURCE = (ROOT / "adventure_zone4_10_monster_reward_policy.py").read_text(
    encoding="utf-8"
)
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def _assignment(name: str):
    tree = ast.parse(APP_SOURCE)
    node = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        )
    )
    return ast.literal_eval(node.value)


def test_policy_consumes_all_79_identity_records_and_exact_zone_counts():
    policies = iter_zone4_10_monster_reward_policies()

    assert ZONE4_10_MONSTER_IDENTITY_RECORD_COUNT == 79
    assert len(policies) == 79
    assert len({policy.monster_id for policy in policies}) == 79
    assert Counter(policy.zone_key for policy in policies) == Counter(
        {
            "Z4": 12,
            "Z5": 12,
            "Z6": 12,
            "Z7": 12,
            "Z8": 11,
            "Z9": 10,
            "Z10": 10,
        }
    )


def test_m073_resolves_to_canonical_z10_identity():
    policy = get_zone4_10_monster_reward_policy("M073")

    assert policy is not None
    assert policy.monster_id == "M073"
    assert policy.zone_key == "Z10"


def test_unknown_and_wrong_zone_claims_fail_closed():
    assert get_zone4_10_monster_reward_policy("M999") is None
    assert get_zone4_10_monster_reward_policy("M073", claimed_zone_key="Z7") is None
    assert get_zone4_10_monster_reward_policy("M073", claimed_zone_key="Z10") is not None


def test_owner_approved_coin_and_xp_policy_is_exact():
    assert NORMAL_MONSTER_COIN_REWARD == 2
    assert MONSTER_COIN_DAILY_CAP == 40
    assert GLOBAL_COIN_DAILY_CAP == 500
    assert MONSTER_SPECIFIC_XP is None

    assert _assignment("_COIN_PER_MONSTER") == NORMAL_MONSTER_COIN_REWARD
    assert _assignment("_COIN_MONSTER_DAILY_CAP") == MONSTER_COIN_DAILY_CAP
    assert _assignment("_COIN_DAILY_CAP") == GLOBAL_COIN_DAILY_CAP

    assert all(policy.coin_reward == 2 for policy in iter_zone4_10_monster_reward_policies())
    assert all(policy.monster_specific_xp is None for policy in iter_zone4_10_monster_reward_policies())


def test_owner_approved_no_drop_no_quest_and_no_additional_clear_reward():
    assert ZONE4_10_DROP_ELIGIBILITY is False
    assert ZONE4_10_DROP_TABLES is None
    assert ZONE4_10_DROP_PROFILE is None
    assert QUEST_MID_BINDING is None
    assert ADDITIONAL_FIRST_CLEAR_REWARD_BEYOND_F028 is None

    for policy in iter_zone4_10_monster_reward_policies():
        assert policy.drop_eligible is False
        assert policy.drop_profile is None
        assert policy.quest_binding is None
        assert policy.additional_first_clear_reward is None
        assert policy.additional_first_defeat_reward is None


def test_first_defeat_and_repeat_use_same_normal_policy():
    assert NORMAL_FIRST_DEFEAT_REWARD_POLICY == "SAME_AS_NORMAL_REPEAT_DEFEAT"
    assert all(
        policy.first_defeat_reward_policy == "SAME_AS_NORMAL_REPEAT_DEFEAT"
        for policy in iter_zone4_10_monster_reward_policies()
    )


def test_no_legacy_battlefield_alias_or_second_79_record_authority():
    assert "legacy_bf_" not in POLICY_SOURCE
    assert "drop_legacy_" not in POLICY_SOURCE
    assert "AdventureZoneMonsterIdentity(" not in POLICY_SOURCE
    assert "M034" not in POLICY_SOURCE
    assert "M073" not in POLICY_SOURCE
    assert "M120" not in POLICY_SOURCE
    assert "ZONE4_10_MONSTER_IDENTITIES" in POLICY_SOURCE
    assert "get_zone4_10_monster_identity" in POLICY_SOURCE
    assert {
        policy.monster_id for policy in iter_zone4_10_monster_reward_policies()
    } == {identity.monster_id for identity in ZONE4_10_MONSTER_IDENTITIES}


def test_shop_payment_and_gacha_policy_is_contained_and_unchanged():
    assert SHOP_EXPANSION == "NONE"
    assert PAYMENT_ENABLEMENT is False
    assert PREMIUM_ENABLEMENT is False
    assert GACHA_ENABLEMENT is False

    assert "SHOP_ITEMS" not in POLICY_SOURCE
    assert "PAYPAL" not in POLICY_SOURCE
    assert "NewebPay" not in POLICY_SOURCE
    assert "GACHA_COST" not in POLICY_SOURCE

    equipment_defs = _assignment("EQUIPMENT_DEFS")
    assert {item["id"] for item in equipment_defs if item["id"] in {
        "wooden_sword",
        "cloth_robe",
        "lucky_stone",
    }} == {"wooden_sword", "cloth_robe", "lucky_stone"}
    assert "robe_plain" in APP_SOURCE
    assert "robe_bamboo" in APP_SOURCE
