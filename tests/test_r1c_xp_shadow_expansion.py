"""R1C provenance and multi-support shadow coverage tests."""

from decimal import Decimal
from pathlib import Path

from xp_settlement import (
    FACTOR_SCALE,
    compare_xp_shadow,
    factor_value_to_ppm,
)


def _comparison(**overrides):
    values = {
        "source_type": "REVIEW_SUBMISSION",
        "source_id": "question:42",
        "source_marker": "srs_cards(user_id,question_id).progress_credited",
        "event_identity": "srs_cards.progress_credited:user:7:question:42",
        "idempotency_key": "xp-shadow:review:credited:7:42",
        "legacy_xp": 12,
        "base_xp": 10,
        "additive_learning_bonuses": (2,),
        "premium_eligibility": "PREMIUM_INELIGIBLE",
    }
    values.update(overrides)
    return compare_xp_shadow(**values)


def test_legacy_decimal_effects_convert_to_integer_ppm_only():
    assert factor_value_to_ppm(Decimal("1.05")) == 1_050_000
    assert factor_value_to_ppm(Decimal("1.18")) == 1_180_000
    assert factor_value_to_ppm("1.500000") == 1_500_000


def test_nonrepresentable_factor_fails_closed():
    try:
        factor_value_to_ppm(Decimal("1.0000001"))
    except ValueError as exc:
        assert "six decimal places" in str(exc)
    else:
        raise AssertionError("nonrepresentable factor was accepted")


def test_multiple_support_factors_are_canonical_and_final_rounded_once():
    result = _comparison(
        legacy_xp=12,
        base_xp=10,
        additive_learning_bonuses=(),
        support_factors_ppm=(1_050_000, 1_100_000),
    )
    assert result.shadow_xp == 12
    assert result.support_factors_ppm == (1_050_000, 1_100_000)
    assert result.as_dict()["support_factors_ppm"] == [1_050_000, 1_100_000]
    assert result.as_dict()["side_effect_free"] is True


def test_daily_quest_and_all_complete_have_distinct_event_identities():
    daily = _comparison(
        source_type="DAILY_QUEST",
        source_id="2026-08-14:streak_correct",
        source_marker="daily_quests(user_id,quest_key,quest_date).xp_awarded",
        event_identity="daily_quests:user:7:date:2026-08-14:key:streak_correct:completion",
        idempotency_key="xp-shadow:daily-quest:7:2026-08-14:streak_correct",
        legacy_xp=20,
        base_xp=20,
        additive_learning_bonuses=(),
    )
    all_complete = _comparison(
        source_type="DAILY_QUEST_ALL_COMPLETE",
        source_id="2026-08-14:all_complete",
        source_marker="daily_quests(user_id,quest_key,quest_date).xp_awarded",
        event_identity="daily_quests:user:7:date:2026-08-14:key:all_complete:completion",
        idempotency_key="xp-shadow:daily-quest-all-complete:7:2026-08-14",
        legacy_xp=100,
        base_xp=100,
        additive_learning_bonuses=(),
    )
    assert daily.event_identity != all_complete.event_identity
    assert daily.idempotency_key != all_complete.idempotency_key
    assert daily.mismatch_category == "MATCH"
    assert all_complete.mismatch_category == "MATCH"


def test_friend_reward_identity_is_per_challenge_and_recipient():
    first = _comparison(
        source_type="FRIEND_CHALLENGE_REWARD",
        source_id="91:7",
        source_marker="friend_challenge_answers(challenge_id,user_id,question_id):completion",
        event_identity="friend_challenge_reward:challenge:91:user:7",
        idempotency_key="xp-shadow:friend-challenge-reward:91:7",
        legacy_xp=40,
        base_xp=10,
        additive_learning_bonuses=(30,),
    )
    retry = _comparison(
        source_type="FRIEND_CHALLENGE_REWARD",
        source_id="91:7",
        source_marker="friend_challenge_answers(challenge_id,user_id,question_id):completion",
        event_identity="friend_challenge_reward:challenge:91:user:7",
        idempotency_key="xp-shadow:friend-challenge-reward:91:7",
        legacy_xp=40,
        base_xp=10,
        additive_learning_bonuses=(30,),
    )
    other_recipient = _comparison(
        source_type="FRIEND_CHALLENGE_REWARD",
        source_id="91:8",
        event_identity="friend_challenge_reward:challenge:91:user:8",
        idempotency_key="xp-shadow:friend-challenge-reward:91:8",
        legacy_xp=40,
        base_xp=10,
        additive_learning_bonuses=(30,),
    )
    assert first.event_identity == retry.event_identity
    assert first.idempotency_key == retry.idempotency_key
    assert first.event_identity != other_recipient.event_identity
    assert first.idempotency_key != other_recipient.idempotency_key


def test_review_shadow_is_gated_by_server_credited_progress_and_all_targets_exist():
    app_source = Path("app.py").read_text(encoding="utf-8")
    assert "if should_grant_progress:" in app_source
    assert "srs_cards.progress_credited:user:" in app_source
    assert "source_type': 'DAILY_QUEST'" in app_source
    assert "source_type': 'DAILY_QUEST_ALL_COMPLETE'" in app_source
    assert "source_type': 'FRIEND_CHALLENGE_REWARD'" in app_source
    assert "XPSettlement" not in app_source[app_source.index("def _observe_xp_shadow"):]


def test_r1c_flags_remain_default_off_in_foundation():
    settlement_source = Path("xp_settlement.py").read_text(encoding="utf-8")
    assert "SHADOW_FLAG = \"XP_SHADOW_ENABLED\"" in settlement_source
    assert "return _env_flag(SHADOW_FLAG, False)" in settlement_source
    assert FACTOR_SCALE == 1_000_000
