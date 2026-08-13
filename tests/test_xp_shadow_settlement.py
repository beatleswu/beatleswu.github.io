"""Focused R1B tests for side-effect-free XP shadow comparison."""

import pytest

from xp_settlement import (
    FACTOR_SCALE,
    NO_PREMIUM_FACTOR_PPM,
    PREMIUM_18_FACTOR_PPM,
    SHADOW_MISMATCH_CATEGORIES,
    compare_xp_shadow,
    xp_shadow_enabled,
    xp_shadow_error_evidence,
)


def _comparison(**overrides):
    values = {
        "source_type": "DAILY_CHALLENGE",
        "source_id": "2026-08-13:42",
        "source_marker": "daily_challenge_log(user_id,challenge_date)",
        "event_identity": "daily_challenge_log:user:7:2026-08-13",
        "idempotency_key": "daily-challenge:2026-08-13",
        "legacy_xp": 10,
        "base_xp": 10,
    }
    values.update(overrides)
    return compare_xp_shadow(**values)


def test_shadow_flag_is_default_off(monkeypatch):
    monkeypatch.delenv("XP_SHADOW_ENABLED", raising=False)
    assert xp_shadow_enabled() is False
    monkeypatch.setenv("XP_SHADOW_ENABLED", "1")
    assert xp_shadow_enabled() is True


@pytest.mark.parametrize(
    ("legacy_xp", "base_xp", "bonuses", "combo", "support", "premium", "expected"),
    [
        (10, 10, (), FACTOR_SCALE, FACTOR_SCALE, "PREMIUM_INELIGIBLE", 10),
        (12, 10, (2,), FACTOR_SCALE, FACTOR_SCALE, "PREMIUM_INELIGIBLE", 12),
        (13, 10, (3,), FACTOR_SCALE, FACTOR_SCALE, "PREMIUM_INELIGIBLE", 13),
        (12, 10, (), 1_200_000, FACTOR_SCALE, "PREMIUM_INELIGIBLE", 12),
        (15, 10, (), FACTOR_SCALE, 1_500_000, "PREMIUM_INELIGIBLE", 15),
        (118, 100, (), FACTOR_SCALE, FACTOR_SCALE, "PREMIUM_ELIGIBLE", 118),
        (27, 15, (), 1_500_000, FACTOR_SCALE, "PREMIUM_ELIGIBLE", 27),
        (1, 1, (), 1_490_000, FACTOR_SCALE, "PREMIUM_INELIGIBLE", 1),
        (2, 1, (), 1_500_000, FACTOR_SCALE, "PREMIUM_INELIGIBLE", 2),
        (2, 1, (), 1_510_000, FACTOR_SCALE, "PREMIUM_INELIGIBLE", 2),
        (100, 100, (), FACTOR_SCALE, FACTOR_SCALE, "ALREADY_PREMIUM_ADJUSTED", 100),
    ],
)
def test_golden_old_vs_new_comparisons(
    legacy_xp, base_xp, bonuses, combo, support, premium, expected
):
    result = _comparison(
        legacy_xp=legacy_xp,
        base_xp=base_xp,
        additive_learning_bonuses=bonuses,
        combo_factor_ppm=combo,
        support_factor_ppm=support,
        premium_eligibility=premium,
        already_premium_adjusted=(premium == "ALREADY_PREMIUM_ADJUSTED"),
    )
    assert result.shadow_xp == expected
    assert result.difference == 0
    assert result.mismatch_category == "MATCH"
    assert result.premium_factor_ppm == (
        PREMIUM_18_FACTOR_PPM if premium == "PREMIUM_ELIGIBLE" else NO_PREMIUM_FACTOR_PPM
    )


def test_shadow_is_side_effect_free_and_preserves_event_provenance():
    result = _comparison(
        source_type="QUEST_BOARD_STAGE",
        source_id="whole_board::LV10::1-40",
        source_marker="reward_claimed(user_id,stage_key)",
        event_identity="reward_claimed(user_id,stage_key):user:7:sha256:"
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        idempotency_key="xp-shadow:stage-7-lv10",
        legacy_xp=30,
        base_xp=30,
    )
    evidence = result.as_dict()
    assert evidence["event_identity"].startswith(
        "reward_claimed(user_id,stage_key):user:7:"
    )
    assert len(evidence["event_identity"].rsplit(":", 1)[-1]) == 64
    assert evidence["side_effect_free"] is True
    assert evidence["ledger_inserted"] is False
    assert evidence["idempotency_consumed"] is False
    assert result.source_marker == "reward_claimed(user_id,stage_key)"


def test_shadow_mismatch_categories_are_explicit():
    assert set(
        (
            "MATCH",
            "ROUNDING_MISMATCH",
            "PREMIUM_MISMATCH",
            "BASE_XP_MISMATCH",
            "MODIFIER_MISMATCH",
            "EVENT_IDENTITY_MISMATCH",
            "UNSUPPORTED_WRITER",
            "LEGACY_SEMANTIC_DIFFERENCE",
            "ERROR_FAIL_CLOSED",
        )
    ) <= set(SHADOW_MISMATCH_CATEGORIES)
    result = _comparison(legacy_xp=11, base_xp=10, mismatch_hint="ROUNDING_MISMATCH")
    assert result.mismatch_category == "ROUNDING_MISMATCH"
    assert result.difference == -1


def test_shadow_rejects_double_premium_inputs():
    with pytest.raises(ValueError, match="already adjusted"):
        _comparison(
            premium_eligibility="PREMIUM_ELIGIBLE",
            already_premium_adjusted=True,
        )


def test_shadow_failure_evidence_contains_no_exception_payload():
    evidence = xp_shadow_error_evidence(
        source_type="DAILY_CHALLENGE",
        source_id="2026-08-13:42",
        source_marker="daily_challenge_log(user_id,challenge_date)",
        event_identity="daily_challenge_log:user:7:2026-08-13",
        error=RuntimeError("secret token must not be serialized"),
    )
    assert evidence["mismatch_category"] == "ERROR_FAIL_CLOSED"
    assert evidence["error_class"] == "RuntimeError"
    assert "secret token" not in str(evidence)
    assert evidence["ledger_inserted"] is False
    assert evidence["idempotency_consumed"] is False
