"""Executable, route-free S1 contract and corruption-fixture tests."""

from __future__ import annotations

import json
import sqlite3

import pytest

from event_outbox import DuplicateOutboxEvent
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from spirit_lineage import (
    ANALYTICS_EVENT_CONTRACTS,
    COMPANION_OPERATION_RECORD_CONTRACT,
    KNOWN_SPIRIT_IDS,
    LEGACY_COSMETIC_PET_IDS,
    append_spirit_item_use_event,
    append_spirit_reward_event,
    build_companion_operation_identity,
    build_evolution_transitions,
    build_spirit_item_use_payload,
    build_spirit_reward_payload,
    classify_operation_replay,
    evolution_stage_for_level,
    legacy_pet_can_create_functional_state,
    replay_creates_no_functional_reward,
    unlock_eligibility,
    validate_evolution_event,
    validate_feed_result,
    validate_legacy_resource_update,
    validate_spirit_effect_event,
    validate_switch_result,
    validate_train_result,
    validate_unlock_result,
    SpiritContractError,
    SpiritOperationConflict,
    SpiritWrongUser,
)
from spirit_lineage_auditor import audit_companion_snapshot, read_snapshot_tables


def _valid_snapshot():
    return {
        "reward_authorities": [
            {
                "authority_id": "reward-authority-1",
                "user_id": 1,
                "operation_id": "reward-op-1",
                "source_type": "BOSS_LORD",
                "source_id": "boss-clear-1",
                "committed": True,
                "request_fingerprint": "reward-fp-1",
            }
        ],
        "spirit_rewards": [
            {
                "reward_id": "spirit-reward-1",
                "authority_id": "reward-authority-1",
                "user_id": 1,
                "operation_id": "reward-op-1",
                "spirit_id": "ink_drop_kelpie",
                "reward_type": "SPIRIT_XP",
                "reward_key": "xp:10",
                "committed": True,
            }
        ],
        "domain_event_outbox": [
            {
                "event_id": "event-reward-1",
                "event_type": "ITEM_ACQUISITION",
                "player_id": "1",
                "payload": {
                    "lineage_kind": "SPIRIT_REWARD",
                    "authority_id": "reward-authority-1",
                    "reward_id": "spirit-reward-1",
                    "operation_id": "reward-op-1",
                    "user_id": 1,
                },
            },
            {
                "event_id": "event-item-1",
                "event_type": "ITEM_CONSUME_EFFECT",
                "player_id": "1",
                "payload": {
                    "lineage_kind": "SPIRIT_ITEM_USE",
                    "operation_id": "item-op-1",
                    "user_id": 1,
                },
            },
        ],
        "item_operations": [
            {
                "operation_id": "item-op-1",
                "user_id": 1,
                "operation_type": "ITEM_USE",
                "request_fingerprint": "item-fp-1",
                "operation_status": "SUCCESS",
            }
        ],
        "item_consumptions": [
            {
                "consumption_id": "consume-1",
                "operation_id": "item-op-1",
                "user_id": 1,
                "item_id": "pet_evolution_core",
                "spirit_id": "ink_drop_kelpie",
                "committed": True,
            }
        ],
        "catalog": [
            {"spirit_id": spirit_id, "functional": True}
            for spirit_id in KNOWN_SPIRIT_IDS
        ],
        "pet_collection": [
            {"id": 1, "user_id": 1, "pet_key": "ink_drop_kelpie"}
        ],
        "user_pets": [
            {"id": 1, "user_id": 1, "pet_key": "ink_drop_kelpie"}
        ],
        "spirit_events": [
            {
                "event_id": "unlock-1",
                "event_type": "SPIRIT_UNLOCKED",
                "user_id": 1,
                "spirit_id": "ink_drop_kelpie",
            },
            {
                "event_id": "xp-1",
                "event_type": "SPIRIT_XP_GAINED",
                "user_id": 1,
                "spirit_id": "ink_drop_kelpie",
            },
        ],
        "evolution_events": [
            {
                "event_id": "evolution-1",
                "operation_id": "evolution-op-1",
                "user_id": 1,
                "spirit_id": "ink_drop_kelpie",
                "from_stage": "STAGE_I",
                "to_stage": "STAGE_II",
                "from_level": 9,
                "to_level": 10,
                "client_can_set_evolution": False,
            }
        ],
        "effect_events": [
            {
                "event_id": "effect-1",
                "effect_id": "shield-1",
                "spirit_id": "ink_drop_kelpie",
                "source_settlement_id": "settlement-1",
                "before_judge": False,
                "trigger_phase": "AFTER_SETTLEMENT",
            }
        ],
        "replay_mutations": [],
    }


def _failed_invariant(snapshot, name):
    report = audit_companion_snapshot(snapshot)
    assert not report.valid
    assert report.invariants
    assert report.failures.get(name), report.as_dict()
    return report


def test_contract_keeps_current_three_and_no_legacy_functional_ids():
    existing_ids = (
        "ink_drop_kelpie",
        "whispering_void_kit",
        "star_shell_hatchling",
    )
    assert tuple(KNOWN_SPIRIT_IDS[:3]) == existing_ids
    assert tuple(KNOWN_SPIRIT_IDS[3:]) == (
        "starpath_antlerling",
        "fatty",
        "obsidian_bastion",
    )
    assert len(KNOWN_SPIRIT_IDS) == 6
    assert not LEGACY_COSMETIC_PET_IDS.intersection(KNOWN_SPIRIT_IDS)
    assert all(legacy_pet_can_create_functional_state(item) is False for item in LEGACY_COSMETIC_PET_IDS)


def test_operation_identity_replay_conflict_and_wrong_user():
    request = build_companion_operation_identity(
        user_id=1,
        operation_type="FEED",
        operation_id="feed-1",
        spirit_id="ink_drop_kelpie",
        item_id="go_spirit_candy",
        payload={"quantity": 1, "server_effect": "fullness+24"},
    )
    existing = {**request, "operation_status": "SUCCESS", "result_payload": {"ok": True}}
    assert classify_operation_replay(existing, request, authenticated_user_id=1) == "REPLAY"
    changed = build_companion_operation_identity(
        user_id=1,
        operation_type="FEED",
        operation_id="feed-1",
        spirit_id="ink_drop_kelpie",
        item_id="go_spirit_candy",
        payload={"quantity": 2, "server_effect": "fullness+24"},
    )
    with pytest.raises(SpiritOperationConflict):
        classify_operation_replay(existing, changed, authenticated_user_id=1)
    with pytest.raises(SpiritWrongUser):
        classify_operation_replay(existing, {**request, "user_id": 2}, authenticated_user_id=2)
    assert request["client_identity_is_authority"] is False


def test_d5a_and_d5c_event_families_reuse_one_outbox(tmp_path):
    conn = sqlite3.connect(tmp_path / "d007-outbox.sqlite")
    conn.row_factory = sqlite3.Row
    try:
        upgrade_outbox(conn)
        reward = append_spirit_reward_event(
            conn,
            user_id=1,
            operation_id="reward-op-1",
            lineage_id="lineage-1",
            source_type="BOSS_LORD",
            source_id="boss-clear-1",
            reward_type="SPIRIT_XP",
            reward_key="xp:10",
            quantity=10,
            spirit_id="ink_drop_kelpie",
        )
        item = append_spirit_item_use_event(
            conn,
            user_id=1,
            operation_id="item-op-1",
            lineage_id="lineage-2",
            spirit_id="ink_drop_kelpie",
            item_id="pet_evolution_core",
            quantity_before=2,
            quantity_delta=-1,
            quantity_after=1,
            effect_applied=True,
            effect_id="spirit-xp-1",
            effect_type="SPIRIT_XP",
            effect_result={"xp": 25},
        )
        assert reward["event_type"] == "ITEM_ACQUISITION"
        assert item["event_type"] == "ITEM_CONSUME_EFFECT"
        assert conn.execute("SELECT COUNT(*) FROM domain_event_outbox").fetchone()[0] == 2
        with pytest.raises(DuplicateOutboxEvent):
            append_spirit_reward_event(
                conn,
                user_id=1,
                operation_id="reward-op-1",
                lineage_id="lineage-1",
                source_type="BOSS_LORD",
                source_id="boss-clear-1",
                reward_type="SPIRIT_XP",
                reward_key="xp:10",
                quantity=10,
                spirit_id="ink_drop_kelpie",
            )
        conn.rollback()
    finally:
        conn.close()


def test_item_payload_and_legacy_resource_adapter_are_fail_closed():
    payload = build_spirit_item_use_payload(
        user_id=1,
        operation_id="item-op-1",
        lineage_id="lineage-1",
        spirit_id="ink_drop_kelpie",
        item_id="go_spirit_candy",
        quantity_before=1,
        quantity_delta=-1,
        quantity_after=0,
        effect_applied=True,
    )
    assert payload["quantity_after"] == 0
    assert validate_legacy_resource_update(
        quantity_before=1, requested_quantity=1, quantity_after=0, affected_rows=1
    )
    assert not validate_legacy_resource_update(
        quantity_before=0, requested_quantity=1, quantity_after=0, affected_rows=0
    )
    with pytest.raises(SpiritContractError):
        build_spirit_item_use_payload(
            user_id=1,
            operation_id="item-op-legacy",
            lineage_id="lineage-legacy",
            spirit_id="ink_drop_kelpie",
            item_id="pet_cat",
            quantity_before=1,
            quantity_delta=-1,
            quantity_after=0,
            effect_applied=True,
        )


def test_feed_train_unlock_switch_contracts():
    assert validate_feed_result(
        {
            "status": "SUCCESS",
            "target_owned": True,
            "consumable_owned": True,
            "quantity_before": 1,
            "quantity_after": 0,
            "consumed_quantity": 1,
            "effect_application_count": 1,
        }
    )
    assert validate_feed_result({"status": "REPLAY", "new_consumption_count": 0, "target_owned": True, "consumable_owned": True}, replay=True)
    assert validate_train_result(
        {
            "status": "SUCCESS",
            "target_owned": True,
            "cooldown_passed": True,
            "daily_count_before": 1,
            "daily_cap": 3,
            "daily_count_after": 2,
            "training_effect_count": 1,
        }
    )
    assert validate_train_result({"status": "REPLAY", "new_training_count": 0, "target_owned": True, "cooldown_passed": True}, replay=True)
    assert unlock_eligibility(spirit_slot=1, highest_owned_spirit_level=1)
    assert unlock_eligibility(spirit_slot=2, highest_owned_spirit_level=11)
    assert unlock_eligibility(spirit_slot=3, highest_owned_spirit_level=16)
    assert validate_unlock_result({"status": "SUCCESS", "eligible": True, "ownership_insert_count": 1, "reward_count": 0})
    assert validate_unlock_result({"status": "REPLAY", "ownership_insert_count": 0, "reward_count": 0}, already_owned=True)
    assert validate_switch_result({"status": "REJECTED_UNOWNED", "target_owned": False})
    assert validate_switch_result({"status": "REJECTED_STALE", "target_owned": True, "stale": True, "projection_mutation_count": 0})
    assert validate_switch_result({"status": "REPLAY", "requested_spirit_id": "ink_drop_kelpie", "active_spirit_id": "ink_drop_kelpie"}, replay=True)


def test_evolution_thresholds_are_server_derived_and_deterministic():
    assert evolution_stage_for_level(1) == "STAGE_I"
    assert evolution_stage_for_level(10) == "STAGE_II"
    assert evolution_stage_for_level(25) == "STAGE_III"
    events = build_evolution_transitions(
        user_id=1,
        spirit_id="ink_drop_kelpie",
        from_level=9,
        to_level=30,
        operation_id="xp-op-1",
        lineage_id="lineage-xp-1",
        source="QUESTION_REVIEW_SETTLEMENT",
    )
    assert [(event["from_stage"], event["to_stage"]) for event in events] == [
        ("STAGE_I", "STAGE_II"),
        ("STAGE_II", "STAGE_III"),
    ]
    assert all(validate_evolution_event(event) for event in events)
    assert all(event["client_can_set_evolution"] is False for event in events)


def test_event_boundary_replay_and_analytics_contracts():
    assert set(ANALYTICS_EVENT_CONTRACTS) == {
        "spirit_unlocked",
        "spirit_selected",
        "spirit_xp_gained",
        "spirit_level_up",
        "spirit_evolved",
        "spirit_effect_triggered",
        "spirit_relic_equipped",
        "spirit_item_used",
        "spirit_reward_granted",
        "spirit_cosmetic_equipped",
    }
    assert replay_creates_no_functional_reward("REPLAY")
    assert replay_creates_no_functional_reward("CINEMATIC")
    assert not replay_creates_no_functional_reward("BOSS_LORD")
    assert validate_spirit_effect_event(
        {
            "effect_id": "effect-1",
            "spirit_id": "ink_drop_kelpie",
            "source_settlement_id": "settlement-1",
            "before_judge": False,
            "trigger_phase": "AFTER_SETTLEMENT",
        }
    )
    assert not validate_spirit_effect_event(
        {
            "effect_id": "effect-1",
            "spirit_id": "ink_drop_kelpie",
            "source_settlement_id": "settlement-1",
            "before_judge": True,
            "trigger_phase": "BEFORE_JUDGE",
        }
    )
    assert COMPANION_OPERATION_RECORD_CONTRACT["unique_key"] == (
        "user_id",
        "operation_type",
        "operation_id",
    )


@pytest.mark.parametrize(
    ("name", "mutate"),
    [
        ("DUPLICATE_SPIRIT_REWARD", lambda s: s["spirit_rewards"].append({**s["spirit_rewards"][0], "reward_id": "spirit-reward-2"})),
        ("ORPHAN_SPIRIT_REWARD", lambda s: s["reward_authorities"].clear()),
        ("REWARD_REQUIRES_OUTBOX_LINEAGE", lambda s: s["domain_event_outbox"].pop(0)),
        ("ORPHAN_OUTBOX", lambda s: s["domain_event_outbox"].append({"event_id": "orphan", "payload": {"lineage_kind": "SPIRIT_REWARD", "authority_id": "missing", "reward_id": "missing"}})),
        ("OUTBOX_WITHOUT_AUTHORITY", lambda s: s["domain_event_outbox"].append({"event_id": "orphan-authority", "payload": {"lineage_kind": "SPIRIT_REWARD", "authority_id": "missing", "reward_id": "spirit-reward-1"}})),
        ("ITEM_CONSUMED_AT_MOST_ONCE", lambda s: s["item_consumptions"].append({**s["item_consumptions"][0], "consumption_id": "consume-2"})),
        ("COMPLETED_ITEM_OPERATION_HAS_CONSUMPTION", lambda s: s["item_consumptions"].clear()),
        ("SPIRIT_EVENT_VALID", lambda s: s["spirit_events"].append({"event_id": "bad", "event_type": "SPIRIT_XP_GAINED", "user_id": 1, "spirit_id": "missing-spirit"})),
        ("UNLOCK_REQUIRES_OWNERSHIP", lambda s: s["pet_collection"].clear()),
        ("OWNERSHIP_CATALOG_VALID", lambda s: s["pet_collection"].append({"id": 99, "user_id": 1, "pet_key": "not-in-catalog"})),
        ("ACTIVE_SPIRIT_OWNED", lambda s: s["user_pets"].append({"id": 2, "user_id": 1, "pet_key": "star_shell_hatchling"})),
        ("DUPLICATE_EVOLUTION_EVENT", lambda s: s["evolution_events"].append({**s["evolution_events"][0], "event_id": "evolution-2"})),
        ("REPLAY_NO_REWARD", lambda s: s["reward_authorities"][0].update({"source_type": "REPLAY"})),
        ("LEGACY_PET_QUARANTINE", lambda s: s["pet_collection"].append({"id": 99, "user_id": 1, "pet_key": "pet_cat"})),
        ("EFFECT_NOT_BEFORE_JUDGE", lambda s: s["effect_events"][0].update({"before_judge": True, "trigger_phase": "BEFORE_JUDGE"})),
        ("OPERATION_PAYLOAD_STABLE", lambda s: s["item_operations"].append({**s["item_operations"][0], "request_fingerprint": "changed"})),
    ],
)
def test_intentional_corruption_is_detected(name, mutate):
    snapshot = _valid_snapshot()
    mutate(snapshot)
    _failed_invariant(snapshot, name)


def test_valid_snapshot_has_zero_false_positives():
    report = audit_companion_snapshot(_valid_snapshot())
    assert report.valid, report.as_dict()
    assert report.failure_count == 0
    assert report.auditor_mutation_capability == "NO"
    assert report.source_of_truth_duplicated is False


def test_read_snapshot_tables_is_select_only(tmp_path):
    conn = sqlite3.connect(tmp_path / "snapshot.sqlite")
    try:
        conn.execute("CREATE TABLE d007_snapshot (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        payload = {"event_type": "SPIRIT_XP_GAINED", "spirit_id": "ink_drop_kelpie"}
        conn.execute("INSERT INTO d007_snapshot(id,payload) VALUES(?,?)", (1, json.dumps(payload)))
        conn.commit()
        before = conn.execute("SELECT COUNT(*), MIN(payload) FROM d007_snapshot").fetchone()
        rows = read_snapshot_tables(conn, {"events": "d007_snapshot"})
        after = conn.execute("SELECT COUNT(*), MIN(payload) FROM d007_snapshot").fetchone()
        assert rows["events"][0]["id"] == 1
        assert before == after
    finally:
        conn.close()
