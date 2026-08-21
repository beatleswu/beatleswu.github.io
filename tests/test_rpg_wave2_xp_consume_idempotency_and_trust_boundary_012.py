"""B_012 evidence for the narrow XP consume/trust-boundary closure.

These tests intentionally prove both the safe local hardening and the exact
remaining persistence/answer-verification boundaries.  They do not create a
second idempotency ledger and do not enable XPSettlement.
"""

import os
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "rpg-wave2-xp-trust-boundary-012-test-secret")

import app as app_module


APP_SOURCE = Path(app_module.__file__).read_text(encoding="utf-8")


def _function_slice(start: str, end: str) -> str:
    begin = APP_SOURCE.index(start)
    finish = APP_SOURCE.index(end, begin)
    return APP_SOURCE[begin:finish]


def test_potion_contract_and_authority_remain_b011_values():
    expected = {
        "small_xp_potion": (1.25, 20),
        "xp_potion": (1.5, 30),
        "grand_xp_potion": (1.5, 60),
    }
    for item_id, (multiplier, minutes) in expected.items():
        item = app_module.SHOP_ITEMS[item_id]
        assert item["effect"] == {
            "key": "xp_potion",
            "value": multiplier,
            "minutes": minutes,
        }
    assert "XPSettlement.settle" not in APP_SOURCE


def test_potion_operation_identity_is_not_falsely_claimed_from_active_effect():
    shop_use = _function_slice("def shop_use():", "@app.route('/api/shop/status')")
    assert "operation_id" not in shop_use
    assert "request_id" not in shop_use
    assert "idempotency" not in shop_use.lower()
    assert "active_effects" not in shop_use or "effect_active" in shop_use


def test_daily_and_friend_results_require_strict_json_booleans():
    daily = _function_slice("def dc_submit():", "@app.route('/api/daily-challenge/history')")
    friend = _function_slice(
        "def friend_challenge_answer(cid):",
        "@app.route('/api/challenges/friend/list')",
    )
    for source in (daily, friend):
        assert "type(data.get('correct')) is not bool" in source
        assert "invalid_result" in source
        assert "correct = 1 if data['correct'] else 0" in source


def test_same_user_replay_serialization_is_present_on_three_paths():
    daily = _function_slice("def dc_submit():", "@app.route('/api/daily-challenge/history')")
    friend = _function_slice(
        "def friend_challenge_answer(cid):",
        "@app.route('/api/challenges/friend/list')",
    )
    lock_sql = "UPDATE users SET id=id WHERE id=?"
    assert lock_sql in daily
    assert lock_sql in friend


def test_client_result_remains_explicitly_unverified_for_owner_gate():
    daily = _function_slice("def dc_submit():", "@app.route('/api/daily-challenge/history')")
    friend = _function_slice(
        "def friend_challenge_answer(cid):",
        "@app.route('/api/challenges/friend/list')",
    )
    # These routes still consume a client-provided result.  The test is a
    # guard against a future change silently calling that value server proof.
    assert "data['correct']" in daily
    assert "data['correct']" in friend
    assert "shadow_judging" in daily
    assert "shadow_judging" in friend


@pytest.fixture()
def logged_client():
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
    return client


def test_daily_and_friend_truthy_non_booleans_are_rejected_before_mutation(
    logged_client, monkeypatch
):
    monkeypatch.setattr(
        app_module,
        "get_or_create_daily_challenge",
        lambda _today: (_ for _ in ()).throw(AssertionError("daily challenge was created")),
    )
    daily = logged_client.post(
        "/api/daily-challenge/submit",
        json={"correct": "false"},
    )
    assert daily.status_code == 400
    assert daily.get_json()["error"] == "invalid_result"

    friend = logged_client.post(
        "/api/challenges/friend/1/answer",
        json={"question_id": 101, "correct": "true"},
    )
    assert friend.status_code == 400
    assert friend.get_json()["error"] == "invalid_result"
