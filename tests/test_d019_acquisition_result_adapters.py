"""Pure, fail-closed tests for D019 producer adapters."""

from __future__ import annotations

import inspect

import pytest

import acquisition_result_adapters as adapters


def _acquisition(**overrides):
    facts = {
        "item_id": "go_spirit_candy",
        "quantity": 1,
        "source_operation_id": "source-op-1",
        "source_reference": "source-ref-1",
        "destination": "STACK_INVENTORY",
        "ownership_authority": "pet_inventory",
        "ownership_reference": "pet_inventory:7:go_spirit_candy",
        "resulting_quantity": 5,
        "is_new": None,
        "can_equip": False,
        "can_use": True,
        "can_wear": False,
        "replayed": False,
        "lineage_event_id": "lineage-event-1",
        "item_class": "SPIRIT_CONSUMABLE",
        "metadata": {},
    }
    facts.update(overrides)
    return facts


def _monster(**overrides):
    payload = {
        "settlement_status": "COMMITTED",
        "settlement_id": "monster-settlement-1",
        "acquisition": _acquisition(),
    }
    payload.update(overrides)
    return payload


def _quest(**overrides):
    payload = {
        "committed": True,
        "claim_status": "SETTLED",
        "claim_operation_id": "quest-claim-1",
        "claim_idempotency_key": "quest:daily:1",
        "reward": _acquisition(),
    }
    payload.update(overrides)
    return payload


def _premium(**overrides):
    payload = {
        "committed": True,
        "claim_status": "SUCCESS",
        "claim_operation_id": "premium-claim-1",
        "claim_idempotency_key": "premium:monthly:1",
        "reward": _acquisition(),
    }
    payload.update(overrides)
    return payload


def _shop(**overrides):
    payload = {
        "committed": True,
        "purchase_status": "COMMITTED",
        "purchase_operation_id": "purchase-1",
        "offer_id": "offer-1",
        "acquisition": _acquisition(),
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("adapter", "payload", "source_type"),
    [
        (adapters.adapt_monster_drop, _monster(), "MONSTER_DROP"),
        (adapters.adapt_quest_reward, _quest(), "QUEST_REWARD"),
        (adapters.adapt_premium_reward, _premium(), "PREMIUM_REWARD"),
        (adapters.adapt_shop_coin_purchase, _shop(), "SHOP_COIN_PURCHASE"),
    ],
)
def test_valid_committed_producer_mapping_returns_d018(adapter, payload, source_type):
    result = adapter(payload)

    assert result.status == adapters.READY
    assert result.result is not None
    assert result.result.source_type == source_type
    assert result.result.item_id == "go_spirit_candy"
    assert result.result.lineage_event_id == "lineage-event-1"


def test_dispatcher_has_one_core_path_for_all_supported_families():
    assert adapters.SUPPORTED_ADAPTER_FAMILIES == (
        "MONSTER_DROP",
        "QUEST_REWARD",
        "PREMIUM_REWARD",
        "SHOP_COIN_PURCHASE",
    )
    assert adapters.adapt_acquisition_result("SHOP_COIN_PURCHASE", _shop()).is_ready


def test_quest_success_status_alone_is_not_commit_evidence():
    payload = _quest(claim_status="SUCCESS")
    payload.pop("committed")

    result = adapters.adapt_quest_reward(payload)

    assert result.status == adapters.INSUFFICIENT_AUTHORITY_EVIDENCE
    assert result.reason_code == "COMMITTED_RESULT_EVIDENCE_REQUIRED"


def test_quest_success_status_with_separate_commit_marker_is_ready():
    payload = _quest(claim_status="SUCCESS", committed=True)

    result = adapters.adapt_quest_reward(payload)

    assert result.is_ready


def test_quest_settled_status_is_commit_evidence():
    payload = _quest(claim_status="SETTLED")
    payload.pop("committed")

    result = adapters.adapt_quest_reward(payload)

    assert result.is_ready


def test_premium_success_status_alone_is_not_commit_evidence():
    payload = _premium(claim_status="SUCCESS")
    payload.pop("committed")

    result = adapters.adapt_premium_reward(payload)

    assert result.status == adapters.INSUFFICIENT_AUTHORITY_EVIDENCE
    assert result.reason_code == "COMMITTED_RESULT_EVIDENCE_REQUIRED"


def test_premium_success_status_with_separate_commit_marker_is_ready():
    payload = _premium(claim_status="SUCCESS")
    payload.pop("committed")
    payload["reward_committed"] = True

    result = adapters.adapt_premium_reward(payload)

    assert result.is_ready


def test_premium_settled_status_is_commit_evidence():
    payload = _premium()
    payload.pop("committed")
    payload.pop("claim_status")
    payload["reward_status"] = "SETTLED"

    result = adapters.adapt_premium_reward(payload)

    assert result.is_ready


@pytest.mark.parametrize("adapter,payload", [(adapters.adapt_monster_drop, _monster()), (adapters.adapt_quest_reward, _quest()), (adapters.adapt_premium_reward, _premium()), (adapters.adapt_shop_coin_purchase, _shop())])
def test_missing_operation_id_fails_closed(adapter, payload):
    payload = dict(payload)
    nested_key = "acquisition" if "acquisition" in payload else "reward"
    nested = dict(payload[nested_key])
    nested.pop("source_operation_id")
    payload[nested_key] = nested
    for key in ("source_operation_id", "operation_id", "claim_operation_id", "purchase_operation_id", "settlement_operation_id"):
        payload.pop(key, None)

    result = adapter(payload)
    assert result.status == adapters.INSUFFICIENT_AUTHORITY_EVIDENCE
    assert "source_operation_id" in result.missing_fields


@pytest.mark.parametrize("missing_field", ["lineage_event_id", "ownership_reference"])
def test_missing_lineage_or_ownership_reference_fails_closed(missing_field):
    payload = _monster()
    nested = dict(payload["acquisition"])
    nested.pop(missing_field)
    payload["acquisition"] = nested

    result = adapters.adapt_monster_drop(payload)
    assert result.status == adapters.INSUFFICIENT_AUTHORITY_EVIDENCE
    assert missing_field in result.missing_fields


def test_is_new_unknown_is_preserved_as_null_not_derived_from_replay():
    payload = _shop()
    nested = dict(payload["acquisition"])
    nested.pop("is_new")
    payload["acquisition"] = nested

    result = adapters.adapt_shop_coin_purchase(payload)
    assert result.is_ready
    assert result.result is not None
    assert result.result.is_new is None


def test_replay_is_independent_from_is_new():
    replayed = _premium()
    replayed["reward"] = dict(replayed["reward"], replayed=True, is_new=False)
    result = adapters.adapt_premium_reward(replayed)
    assert result.is_ready
    assert result.result is not None
    assert result.result.replayed is True
    assert result.result.is_new is False

    unknown = _premium()
    unknown["reward"] = dict(unknown["reward"], replayed=True)
    unknown_result = adapters.adapt_premium_reward(unknown)
    assert unknown_result.is_ready
    assert unknown_result.result is not None
    assert unknown_result.result.is_new is None

    unsupported = _premium()
    unsupported["reward"] = dict(unsupported["reward"], replayed=True, is_new=True)
    unsupported_result = adapters.adapt_premium_reward(unsupported)
    assert unsupported_result.status == adapters.INSUFFICIENT_AUTHORITY_EVIDENCE
    assert unsupported_result.reason_code == "D018_REPLAY_NEW_OWNERSHIP_UNVERIFIED"


def test_monster_preview_and_uncommitted_settlement_are_rejected():
    preview = _monster(preview=True)
    assert adapters.adapt_monster_drop(preview).reason_code == "PREVIEW_NOT_COMMITTED"

    uncommitted = _monster(settlement_status="PREVIEW")
    assert adapters.adapt_monster_drop(uncommitted).status == adapters.INSUFFICIENT_AUTHORITY_EVIDENCE

    defeat_only = {"monster_defeated": True, "monster_id": "dragon_oracle"}
    assert adapters.adapt_monster_drop(defeat_only).status == adapters.INSUFFICIENT_AUTHORITY_EVIDENCE


def test_quest_completed_but_unclaimed_is_rejected():
    completed = {
        "completed": True,
        "claimable": True,
        "claimed": False,
        "quest_id": "daily:answer_questions",
        "progress": 3,
    }
    result = adapters.adapt_quest_reward(completed)
    assert result.status == adapters.INSUFFICIENT_AUTHORITY_EVIDENCE
    assert result.reason_code == "QUEST_CLAIM_NOT_SETTLED"


def test_premium_entitlement_only_is_not_a_reward_result():
    result = adapters.adapt_premium_reward({"entitlement_active": True, "provenance": "VERIFIED_PAID"})
    assert result.status == adapters.INSUFFICIENT_AUTHORITY_EVIDENCE


def test_shop_offer_only_is_not_a_committed_purchase():
    result = adapters.adapt_shop_coin_purchase({"offer_id": "offer-1", "price": 299})
    assert result.status == adapters.INSUFFICIENT_AUTHORITY_EVIDENCE
    assert result.reason_code == "COMMITTED_RESULT_EVIDENCE_REQUIRED"


def test_go_stone_black_lock_is_preserved_through_adapter():
    payload = _shop()
    payload["acquisition"] = _acquisition(
        item_id="go_stone_black",
        quantity=1,
        destination="PLAYER_INVENTORY",
        ownership_authority="player_inventory",
        ownership_reference="player_inventory:stone-1",
        resulting_quantity=None,
        can_equip=False,
        can_use=False,
        can_wear=False,
        item_class="TROPHY",
        metadata={"special_status": "TROPHY_INVENTORY_ONLY_NO_COMBAT_POWER"},
    )
    result = adapters.adapt_shop_coin_purchase(payload)
    assert result.is_ready
    assert result.result is not None
    assert result.result.item_class == "TROPHY"
    assert result.result.can_equip is False
    assert result.result.can_use is False
    assert result.result.can_wear is False

    payload["acquisition"] = dict(payload["acquisition"], can_use=True)
    rejected = adapters.adapt_shop_coin_purchase(payload)
    assert rejected.status == adapters.INSUFFICIENT_AUTHORITY_EVIDENCE
    assert rejected.reason_code == "D018_GO_STONE_BLACK_LOCK"


def test_xp_amulet_hold_is_preserved_through_adapter():
    payload = _shop()
    payload["acquisition"] = _acquisition(
        item_id="xp_amulet",
        destination="PLAYER_INVENTORY",
        ownership_authority="player_inventory",
        ownership_reference="player_inventory:amulet-1",
        can_equip=False,
        can_use=False,
        can_wear=False,
        item_class="ACCESSORY",
        metadata={"special_status": "HOLD_FOR_AUTHORITY"},
    )
    result = adapters.adapt_shop_coin_purchase(payload)
    assert result.is_ready
    assert result.result is not None
    assert result.result.metadata["special_status"] == "HOLD_FOR_AUTHORITY"

    payload["acquisition"] = dict(payload["acquisition"], can_equip=True)
    rejected = adapters.adapt_shop_coin_purchase(payload)
    assert rejected.status == adapters.INSUFFICIENT_AUTHORITY_EVIDENCE
    assert rejected.reason_code == "D018_XP_AMULET_HOLD"


def test_adapters_have_no_mutation_or_database_hook():
    assert adapters.DATABASE_WRITES == 0
    assert adapters.MUTATION_CAPABILITY == "NO"
    for function in (
        adapters.adapt_monster_drop,
        adapters.adapt_quest_reward,
        adapters.adapt_premium_reward,
        adapters.adapt_shop_coin_purchase,
    ):
        assert list(inspect.signature(function).parameters) == ["payload"]
    source = inspect.getsource(adapters)
    assert "import app" not in source
    assert "sqlite" not in source.lower()
    assert "psycopg" not in source.lower()
    assert ".commit(" not in source
    assert ".execute(" not in source


def test_adapter_result_serialization_is_safe_and_truthful():
    result = adapters.adapt_quest_reward(_quest())
    serialized = result.as_dict()
    assert serialized["status"] == adapters.READY
    assert serialized["result"]["source_type"] == "QUEST_REWARD"
    assert serialized["result"]["replayed"] is False
    assert serialized["result"]["is_new"] is None
