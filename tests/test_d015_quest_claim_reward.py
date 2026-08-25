from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace
import json
import sqlite3

import pytest

from migrations.domain_event_outbox_v1 import (
    TABLE_NAME as OUTBOX_TABLE,
    downgrade_for_isolated_test as downgrade_outbox,
    upgrade as upgrade_outbox,
)
from migrations.quest_claim_v1 import (
    TABLE_NAME as CLAIM_TABLE,
    downgrade_for_isolated_test as downgrade_claim,
    upgrade as upgrade_claim,
    validate_schema as validate_claim_schema,
)
from migrations.quest_progress_v2 import (
    APPLICATION_TABLE_NAME,
    PROGRESS_TABLE_NAME,
    downgrade_for_isolated_test as downgrade_progress,
    upgrade as upgrade_progress,
)
from quest_catalog import CANONICAL_QUEST_CATALOG, QuestDefinition, build_catalog
from quest_claim_authority import QuestClaimService
from quest_reward_adapters import (
    CallableQuestRewardAuthorities,
    CURRENT_DAILY_REWARD_PROFILES,
    QuestRewardCatalog,
    QuestRewardProfile,
    RewardItem,
)


NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
PERIOD = "2026-08-24"


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    upgrade_outbox(conn)
    upgrade_progress(conn)
    upgrade_claim(conn)
    conn.executescript(
        """
        CREATE TABLE user_stats (
            user_id TEXT PRIMARY KEY,
            coins INTEGER NOT NULL DEFAULT 0,
            xp INTEGER NOT NULL DEFAULT 0,
            rank_xp INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE currency_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            reason TEXT NOT NULL
        );
        CREATE TABLE pet_inventory (
            user_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            PRIMARY KEY (user_id, item_id)
        );
        CREATE TABLE player_wardrobe (
            user_id TEXT NOT NULL,
            cosmetic_id TEXT NOT NULL,
            PRIMARY KEY (user_id, cosmetic_id)
        );
        """
    )
    conn.execute("INSERT INTO user_stats(user_id) VALUES ('7'), ('8')")
    conn.commit()
    return conn


def _authorities() -> CallableQuestRewardAuthorities:
    def grant_xp(conn, user_id, amount, reason, _profile_id):
        conn.execute(
            "UPDATE user_stats SET xp=xp+?, rank_xp=rank_xp+? WHERE user_id=?",
            (amount, amount, str(user_id)),
        )
        return amount

    def grant_coins(conn, user_id, amount, reason, _profile_id):
        conn.execute(
            "UPDATE user_stats SET coins=coins+? WHERE user_id=?",
            (amount, str(user_id)),
        )
        conn.execute(
            "INSERT INTO currency_log(user_id,amount,reason) VALUES (?,?,?)",
            (str(user_id), amount, reason),
        )
        return amount

    def grant_item(conn, user_id, item_id, quantity, _reason, _profile_id):
        quantity_update = (
            "quantity=pet_inventory.quantity+EXCLUDED.quantity"
            if hasattr(conn, "_conn")
            else "quantity=quantity+excluded.quantity"
        )
        conn.execute(
            f"""INSERT INTO pet_inventory(user_id,item_id,quantity) VALUES (?,?,?)
               ON CONFLICT(user_id,item_id) DO UPDATE SET {quantity_update}""",
            (str(user_id), item_id, quantity),
        )
        resulting = conn.execute(
            "SELECT quantity FROM pet_inventory WHERE user_id=? AND item_id=?",
            (str(user_id), item_id),
        ).fetchone()[0]
        return {
            "item_id": item_id,
            "ownership_authority": "pet_inventory",
            "ownership_reference": f"pet_inventory:{user_id}:{item_id}",
            "granted_quantity": quantity,
            "resulting_quantity": resulting,
        }

    def grant_cosmetic(conn, user_id, cosmetic_id, _reason, _profile_id):
        conn.execute(
            "INSERT INTO player_wardrobe(user_id,cosmetic_id) VALUES (?,?)",
            (str(user_id), cosmetic_id),
        )
        return {
            "cosmetic_id": cosmetic_id,
            "ownership_authority": "player_wardrobe",
            "ownership_reference": f"player_wardrobe:{user_id}:{cosmetic_id}",
            "granted_quantity": 1,
        }

    return CallableQuestRewardAuthorities(
        grant_xp=grant_xp,
        grant_coins=grant_coins,
        grant_item=grant_item,
        grant_cosmetic=grant_cosmetic,
    )


def _completed(
    conn: sqlite3.Connection,
    quest_id: str,
    *,
    user_id: str = "7",
    period_key: str = PERIOD,
    source_event_id: str | None = None,
    progress: int | None = None,
    definition: QuestDefinition | None = None,
) -> str:
    definition = definition or CANONICAL_QUEST_CATALOG.canonical_map[quest_id]
    source_event_id = source_event_id or f"d013-{quest_id.replace(':', '-')}-{user_id}"
    value = int(progress if progress is not None else definition.target)
    stamp = "2026-08-24T04:00:00Z"
    completed_value = bool(value >= definition.target) if hasattr(conn, "_conn") else int(value >= definition.target)
    conn.execute(
        f"""INSERT INTO {PROGRESS_TABLE_NAME}(
                   user_id,quest_id,period_key,progress,completed,
                   definition_version,target_snapshot,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            user_id,
            quest_id,
            period_key,
            value,
            completed_value,
            definition.version,
            definition.target,
            stamp,
            stamp,
        ),
    )
    conn.execute(
        f"""INSERT INTO {APPLICATION_TABLE_NAME}(
                   user_id,source_event_id,quest_id,period_key,
                   source_event_type,source_authority,source_operation_id,
                   operation,amount,resulting_progress,completed,
                   definition_version,target_snapshot,source_payload_hash,
                   source_occurred_at,applied_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            user_id,
            source_event_id,
            quest_id,
            period_key,
            "QUESTION_SETTLED",
            "d013:test",
            f"op-{source_event_id}",
            "INCREMENT",
            value,
            value,
            completed_value,
            definition.version,
            definition.target,
            "fixture-hash",
            stamp,
            stamp,
        ),
    )
    return source_event_id


def _service(conn, *, reward_catalog=None, catalog=None):
    return QuestClaimService(
        conn,
        catalog=catalog or CANONICAL_QUEST_CATALOG,
        reward_catalog=reward_catalog,
        reward_authorities=_authorities(),
    )


def _count(conn, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_claim_schema_is_additive_valid_and_rerunnable():
    conn = _db()
    try:
        assert validate_claim_schema(conn)["valid"] is True
        assert upgrade_claim(conn)["valid"] is True
        assert CLAIM_TABLE == "quest_claims_v2"
    finally:
        downgrade_claim(conn)
        downgrade_progress(conn)
        downgrade_outbox(conn)
        conn.close()


def test_current_daily_reward_profiles_preserve_executable_compatibility_values():
    profiles = {profile.profile_id: profile for profile in CURRENT_DAILY_REWARD_PROFILES}
    assert (profiles["legacy:daily:kill_monsters"].xp, profiles["legacy:daily:kill_monsters"].coins) == (30, 15)
    assert (profiles["legacy:daily:streak_correct"].xp, profiles["legacy:daily:streak_correct"].coins) == (20, 15)
    assert (profiles["legacy:daily:challenge_dragon"].xp, profiles["legacy:daily:challenge_dragon"].coins) == (50, 15)
    assert (profiles["legacy:daily:all_complete"].xp, profiles["legacy:daily:all_complete"].coins) == (100, 50)
    assert profiles["legacy:daily:kill_monsters"].items == (RewardItem("go_spirit_candy", 1),)
    assert profiles["legacy:daily:all_complete"].items == (RewardItem("starfruit", 1),)


def test_first_claim_uses_server_completion_and_d5a_acquisition_lineage():
    conn = _db()
    source_event_id = _completed(conn, "daily:kill_monsters")
    service = _service(conn)
    try:
        result = service.claim("7", "kill_monsters", PERIOD, claim_operation_id="claim-1", now=NOW)
        assert result.status == "GRANTED"
        assert result.created is True
        assert result.quest_id == "daily:kill_monsters"
        assert result.completion_source_event_id == source_event_id
        assert result.acquisition_event_ids and len(result.acquisition_event_ids) == 1

        stats = conn.execute("SELECT coins,xp,rank_xp FROM user_stats WHERE user_id='7'").fetchone()
        assert tuple(stats) == (15, 30, 30)
        assert conn.execute(
            "SELECT quantity FROM pet_inventory WHERE user_id='7' AND item_id='go_spirit_candy'"
        ).fetchone()[0] == 1
        event = conn.execute(
            f"SELECT event_type,source_event_id,payload FROM {OUTBOX_TABLE}"
        ).fetchone()
        assert event[0] == "ITEM_ACQUISITION"
        assert event[1] == source_event_id
        payload = json.loads(event[2])
        assert payload["claim_id"] == result.claim_id
        assert payload["ownership_committed"] is True
        assert "token" not in json.dumps(payload).lower()
        conn.commit()
    finally:
        conn.close()


def test_same_operation_and_different_operation_replay_without_duplicate_reward():
    conn = _db()
    _completed(conn, "daily:streak_correct")
    service = _service(conn)
    try:
        first = service.claim("7", "daily:streak_correct", PERIOD, claim_operation_id="claim-replay", now=NOW)
        conn.commit()
        second = service.claim("7", "daily:streak_correct", PERIOD, claim_operation_id="claim-replay", now=NOW)
        third = service.claim("7", "daily:streak_correct", PERIOD, claim_operation_id="claim-other", now=NOW)
        assert first.status == second.status == third.status == "GRANTED"
        assert second.duplicate is True and third.duplicate is True
        assert second.claim_id == first.claim_id == third.claim_id
        assert tuple(conn.execute("SELECT coins,xp FROM user_stats WHERE user_id='7'").fetchone()) == (15, 20)
        assert _count(conn, OUTBOX_TABLE) == 1
        assert _count(conn, CLAIM_TABLE) == 1
        conn.rollback()
    finally:
        conn.close()


def test_prior_period_claim_is_exact_and_disabled_settlement_replay_is_preserved():
    conn = _db()
    _completed(conn, "daily:kill_monsters", period_key="2026-08-23")
    service = _service(conn)
    try:
        old_period = service.claim(
            "7",
            "daily:kill_monsters",
            "2026-08-23",
            claim_operation_id="old-period",
            now=NOW,
        )
        assert old_period.status == "GRANTED"
        conn.commit()

        current_definition = CANONICAL_QUEST_CATALOG.canonical_map["daily:kill_monsters"]
        disabled_definition = replace(
            current_definition,
            enabled=False,
            availability={"catalog_status": "disabled"},
        )
        disabled_catalog = build_catalog(
            disabled_definition if item.quest_id == disabled_definition.quest_id else item
            for item in CANONICAL_QUEST_CATALOG.definitions
        )
        disabled_service = _service(conn, catalog=disabled_catalog)
        replay = disabled_service.claim(
            "7",
            "daily:kill_monsters",
            "2026-08-23",
            claim_operation_id="old-period",
            now=NOW,
        )
        new_operation = disabled_service.claim(
            "7",
            "daily:kill_monsters",
            "2026-08-23",
            claim_operation_id="disabled-new",
            now=NOW,
        )
        assert replay.status == "GRANTED" and replay.duplicate is True
        assert new_operation.status == "DENIED"
        assert new_operation.reason == "QUEST_DISABLED"
    finally:
        conn.close()


def test_operation_conflict_cross_user_isolation_and_forgery_fail_closed():
    conn = _db()
    _completed(conn, "daily:kill_monsters", user_id="7")
    _completed(conn, "daily:kill_monsters", user_id="8")
    service = _service(conn)
    try:
        first = service.claim("7", "daily:kill_monsters", PERIOD, claim_operation_id="shared-op", now=NOW)
        conn.commit()
        conflict = service.claim("7", "daily:streak_correct", PERIOD, claim_operation_id="shared-op", now=NOW)
        assert conflict.status == "CONFLICT"
        own = service.claim("8", "daily:kill_monsters", PERIOD, claim_operation_id="shared-op", now=NOW)
        assert own.status == "GRANTED"
        forged = service.claim(
            "7",
            "daily:kill_monsters",
            PERIOD,
            claim_operation_id="forged",
            client_claimed=True,
            client_target=1,
            client_progress=999,
            client_reward_profile_id="attacker-profile",
        )
        assert forged.status == "DENIED"
        assert forged.reason == "CLIENT_AUTHORITY_FIELD_REJECTED"
        assert _count(conn, CLAIM_TABLE) == 2
        assert _count(conn, OUTBOX_TABLE) == 2
        conn.rollback()
    finally:
        conn.close()


def test_incomplete_version_mismatch_and_missing_completion_lineage_grant_nothing():
    conn = _db()
    try:
        _completed(conn, "daily:kill_monsters", progress=4)
        result = _service(conn).claim("7", "daily:kill_monsters", PERIOD, claim_operation_id="incomplete", now=NOW)
        assert result.status == "DENIED"
        assert result.reason == "QUEST_NOT_COMPLETED"
        assert _count(conn, CLAIM_TABLE) == 0
        assert _count(conn, OUTBOX_TABLE) == 0

        conn.execute(f"DELETE FROM {PROGRESS_TABLE_NAME}")
        conn.execute(f"DELETE FROM {APPLICATION_TABLE_NAME}")
        definition = CANONICAL_QUEST_CATALOG.canonical_map["daily:kill_monsters"]
        conn.execute(
            f"""INSERT INTO {PROGRESS_TABLE_NAME}(
                       user_id,quest_id,period_key,progress,completed,
                       definition_version,target_snapshot,created_at,updated_at)
                   VALUES ('7',?,?,5,1,99,5,?,?)""",
            (definition.quest_id, PERIOD, "2026-08-24T04:00:00Z", "2026-08-24T04:00:00Z"),
        )
        mismatch = _service(conn).claim("7", definition.quest_id, PERIOD, claim_operation_id="version", now=NOW)
        assert mismatch.status == "DENIED"
        assert mismatch.reason == "QUEST_DEFINITION_VERSION_UNAVAILABLE"

        conn.execute(f"DELETE FROM {PROGRESS_TABLE_NAME}")
        conn.execute(f"DELETE FROM {APPLICATION_TABLE_NAME}")
        conn.execute(
            f"""INSERT INTO {PROGRESS_TABLE_NAME}(
                       user_id,quest_id,period_key,progress,completed,
                       definition_version,target_snapshot,created_at,updated_at)
                   VALUES ('7',?,?,5,1,1,5,?,?)""",
            (definition.quest_id, PERIOD, "2026-08-24T04:00:00Z", "2026-08-24T04:00:00Z"),
        )
        no_lineage = _service(conn).claim("7", definition.quest_id, PERIOD, claim_operation_id="no-lineage", now=NOW)
        assert no_lineage.status == "DENIED"
        assert no_lineage.reason == "COMPLETION_LINEAGE_UNAVAILABLE"
        assert _count(conn, CLAIM_TABLE) == 0
        assert _count(conn, OUTBOX_TABLE) == 0
    finally:
        conn.close()


def test_all_complete_requires_durable_primary_completion_evidence():
    conn = _db()
    try:
        for quest_id in ("daily:kill_monsters", "daily:streak_correct"):
            _completed(conn, quest_id)
        _completed(conn, "daily:all_complete", source_event_id="d013-bonus")
        denied = _service(conn).claim("7", "daily:all_complete", PERIOD, claim_operation_id="bonus-denied", now=NOW)
        assert denied.status == "DENIED"
        assert denied.reason == "QUEST_SET_COMPLETION_EVIDENCE_MISSING"
        assert _count(conn, CLAIM_TABLE) == 0

        _completed(conn, "daily:challenge_dragon")
        granted = _service(conn).claim("7", "daily:all_complete", PERIOD, claim_operation_id="bonus-granted", now=NOW)
        assert granted.status == "GRANTED"
        assert tuple(conn.execute("SELECT coins,xp FROM user_stats WHERE user_id='7'").fetchone()) == (50, 100)
        assert conn.execute(
            "SELECT quantity FROM pet_inventory WHERE user_id='7' AND item_id='starfruit'"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_multi_component_failure_rolls_back_claim_rewards_and_lineage():
    definition = QuestDefinition(
        quest_id="daily:fixture_bundle",
        quest_family="daily",
        quest_type="fixture_bundle",
        period="daily",
        condition="QUESTION_CORRECT",
        target=1,
        filters={"correct": True},
        reward_profile_id="fixture:bundle",
        availability={"catalog_status": "test"},
        enabled=True,
        version=1,
        aliases=(),
    )
    catalog = build_catalog((*CANONICAL_QUEST_CATALOG.definitions, definition))
    reward_catalog = QuestRewardCatalog(
        (
            QuestRewardProfile(
                profile_id="fixture:bundle",
                xp=7,
                coins=11,
                items=(RewardItem("go_spirit_candy", 1),),
                cosmetics=("fixture_cosmetic",),
            ),
        )
    )
    conn = _db()
    _completed(conn, definition.quest_id, definition=definition)
    service = _service(conn, reward_catalog=reward_catalog, catalog=catalog)
    try:
        with pytest.raises(RuntimeError, match="forced rollback"):
            service.claim(
                "7",
                definition.quest_id,
                PERIOD,
                claim_operation_id="bundle-failure",
                now=NOW,
                fault_hook=lambda stage: (_ for _ in ()).throw(RuntimeError("forced rollback"))
                if stage == "after_lineage"
                else None,
            )
        conn.rollback()
        assert tuple(conn.execute("SELECT coins,xp FROM user_stats WHERE user_id='7'").fetchone()) == (0, 0)
        assert _count(conn, CLAIM_TABLE) == 0
        assert _count(conn, OUTBOX_TABLE) == 0
        assert _count(conn, "currency_log") == 0
        assert _count(conn, "pet_inventory") == 0
        assert _count(conn, "player_wardrobe") == 0
    finally:
        conn.close()
