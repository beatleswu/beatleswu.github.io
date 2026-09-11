"""ACT-B D1 proof for the canonical Map Battle provider boundary."""

from __future__ import annotations

import hashlib
import sqlite3

import pytest

from adventure_monster_runtime_contract import (
    AdventureQuestionBinding,
    AdventureMonsterRuntimeContractError,
    ClientAuthorityClaimError,
    StaleQuestionBindingError,
    UnknownProviderError,
    persistence_metadata,
)
from adventure_zone3_monster_authority import (
    ZONE3_BINDING_SOURCE,
    ZONE3_KEY,
)
from map_battle_persistence import (
    MAP_BATTLE_JUDGE_VERSION,
    create_map_battle,
    ensure_map_battle_tables,
    issue_map_battle_attempt,
)
from map_battle_runtime import (
    LEGACY_COMPATIBILITY_RESTORE,
    MAP_BATTLE_CANONICAL_PROVIDER_ZONE_BY_APP_ZONE,
    MAP_BATTLE_PROVIDER_BOUNDARY,
    RESTORE_EXISTING_PROVIDER_BOUND_BATTLE,
    ensure_submission_lifecycle_schema,
    issue_submission_nonce_for_attempt,
    resolve_map_battle_provider_for_new,
    resolve_map_battle_provider_for_new_resolution,
    resolve_map_battle_provider_for_restore,
    settle_answer,
)


QUESTION = {
    "id": 8101,
    "source": "act-b/provider-boundary.sgf",
    "content": "(;SZ[19];B[dd];W[ee])",
}
QUESTION_REVISION = hashlib.sha256(QUESTION["content"].encode("utf-8")).hexdigest()
QUESTION_BINDING = AdventureQuestionBinding(QUESTION["id"], QUESTION_REVISION)


def _battle_for_binding(binding, *, zone_key: str):
    return {
        "id": "act-b-provider-battle",
        "zone_key": zone_key,
        "state": "OPEN",
        "player_hp": 20,
        "player_hp_max": 20,
        "monster_hp": binding.max_hp,
        "monster_hp_max": binding.max_hp,
        **persistence_metadata(binding),
    }


def test_zone1_and_zone2_new_bindings_use_canonical_provider_identity():
    assert MAP_BATTLE_CANONICAL_PROVIDER_ZONE_BY_APP_ZONE["k26_30"] == "Z1"
    assert MAP_BATTLE_CANONICAL_PROVIDER_ZONE_BY_APP_ZONE["k21_25"] == "Z2"

    zone1 = resolve_map_battle_provider_for_new(
        zone_key="k26_30",
        question_binding=QUESTION_BINDING,
        user_id=101,
    )
    zone2 = resolve_map_battle_provider_for_new(
        zone_key="k21_25",
        question_binding=QUESTION_BINDING,
        user_id=101,
    )

    assert zone1 is not None and zone1.zone_key == "Z1"
    assert zone2 is not None and zone2.zone_key == "Z2"
    assert zone1.provider_id == zone2.provider_id
    assert zone1.persistence_source == zone2.persistence_source
    assert zone1.max_hp in (60, 78, 96)
    assert zone2.max_hp in (80, 104, 128)
    for app_zone, binding in (("k26_30", zone1), ("k21_25", zone2)):
        restored = resolve_map_battle_provider_for_restore(
            battle=_battle_for_binding(binding, zone_key=app_zone),
            question_binding=QUESTION_BINDING,
            user_id=101,
        )
        assert restored.binding is not None
        assert restored.binding.provider_id == binding.provider_id
        assert restored.binding.monster_id == binding.monster_id
    assert (
        resolve_map_battle_provider_for_new_resolution(
            zone_key="k26_30",
            question_binding=QUESTION_BINDING,
            user_id=101,
        ).mode
        == "NEW_BATTLE_BINDING"
    )


def test_zone3_creation_and_restore_preserve_existing_e055_authority():
    binding = resolve_map_battle_provider_for_new(
        zone_key=ZONE3_KEY,
        question_binding=QUESTION_BINDING,
        user_id=101,
    )
    assert binding is not None
    assert binding.zone_key == ZONE3_KEY
    assert binding.persistence_source == ZONE3_BINDING_SOURCE
    assert binding.max_hp == 100

    restored = resolve_map_battle_provider_for_restore(
        battle=_battle_for_binding(binding, zone_key=ZONE3_KEY),
        question_binding=QUESTION_BINDING,
        user_id=101,
    )
    assert restored.mode == RESTORE_EXISTING_PROVIDER_BOUND_BATTLE
    assert restored.provider_id == binding.provider_id
    assert restored.binding is not None
    assert restored.binding.monster_id == binding.monster_id
    assert restored.binding.profile_id == binding.profile_id


def test_zone4_to_zone10_slots_are_not_admitted_for_new_map_battles():
    with pytest.raises(AdventureMonsterRuntimeContractError):
        resolve_map_battle_provider_for_new(
            zone_key="k11_15",
            question_binding=QUESTION_BINDING,
            user_id=101,
        )


def test_provider_bound_creation_rejects_client_monster_authority_claims():
    with pytest.raises(ClientAuthorityClaimError):
        resolve_map_battle_provider_for_new(
            zone_key="k26_30",
            question_binding=QUESTION_BINDING,
            user_id=101,
            payload={"zone_key": "k26_30", "monster_id": "M999"},
        )


def test_legacy_restore_is_explicit_and_unknown_provider_does_not_fallback():
    legacy = resolve_map_battle_provider_for_restore(
        battle={
            "zone_key": "k26_30",
            "migration_source": "legacy-adventure-map",
            "migration_version": "map-battle-v1",
        },
        question_binding=QUESTION_BINDING,
        user_id=101,
    )
    assert legacy.mode == LEGACY_COMPATIBILITY_RESTORE
    assert legacy.binding is None

    with pytest.raises(UnknownProviderError):
        resolve_map_battle_provider_for_restore(
            battle={
                "zone_key": "k26_30",
                "migration_source": "future-provider-v99",
                "migration_version": "future-v99",
            },
            question_binding=QUESTION_BINDING,
            user_id=101,
        )


def test_broken_provider_bound_identity_fails_closed_without_legacy_fallback():
    binding = resolve_map_battle_provider_for_new(
        zone_key="k26_30",
        question_binding=QUESTION_BINDING,
        user_id=101,
    )
    assert binding is not None
    broken = _battle_for_binding(binding, zone_key="k26_30")
    broken["migration_version"] = "w2.z1_z2.binding.v1:Z1:MISSING:missing:v1"

    with pytest.raises(AdventureMonsterRuntimeContractError):
        MAP_BATTLE_PROVIDER_BOUNDARY.settlement_binding(
            battle=broken,
            question_binding=QUESTION_BINDING,
            user_id=101,
        )


def test_ambiguous_and_retired_puzzle_identity_fail_closed():
    for status in ("AMBIGUOUS", "RETIRED"):
        with pytest.raises(StaleQuestionBindingError):
            resolve_map_battle_provider_for_new(
                zone_key="k26_30",
                question_binding={
                    "question_id": QUESTION["id"],
                    "question_revision": QUESTION_REVISION,
                    "identity_status": status,
                },
                user_id=101,
            )


def test_settlement_uses_the_same_provider_boundary_and_keeps_judge_cas_contract():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO users(id) VALUES (101)")
    ensure_map_battle_tables(conn)
    ensure_submission_lifecycle_schema(conn)

    binding = resolve_map_battle_provider_for_new(
        zone_key="k26_30",
        question_binding=QUESTION_BINDING,
        user_id=101,
    )
    assert binding is not None
    battle_id = create_map_battle(
        conn,
        battle_id="act-b-provider-battle",
        user_id=101,
        zone_key="k26_30",
        player_hp=20,
        player_hp_max=20,
        monster_hp=binding.max_hp,
        monster_hp_max=binding.max_hp,
        **persistence_metadata(binding),
        now="2026-09-11T00:00:00+00:00",
    )
    attempt_id = issue_map_battle_attempt(
        conn,
        user_id=101,
        battle_id=battle_id,
        question_id=QUESTION["id"],
        question_revision=QUESTION_REVISION,
        initial_position_identity="act-b-position",
        board_size=19,
        player_color="B",
        transform_version="transform-v1",
        transform_id="identity",
        battle_revision_at_issue=0,
        attempt_id="act-b-provider-attempt",
        issued_at="2026-09-11T00:00:00+00:00",
        expires_at="2026-09-12T00:00:00+00:00",
    )
    nonce = issue_submission_nonce_for_attempt(
        conn,
        user_id=101,
        attempt_id=attempt_id,
        now="2026-09-11T00:01:00+00:00",
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
    )["submission_nonce"]

    result = settle_answer(
        conn,
        user_id=101,
        payload={
            "battle_id": battle_id,
            "attempt_id": attempt_id,
            "submission_nonce": nonce,
            "battle_revision": 0,
            "question_revision": QUESTION_REVISION,
            "player_color": "black",
            "transform_id": "identity",
            "transform_version": "transform-v1",
            "moves": [{"x": 3, "y": 3}],
        },
        question_loader=lambda question_id: QUESTION,
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
        now="2026-09-11T00:02:00+00:00",
        runtime_provider=MAP_BATTLE_PROVIDER_BOUNDARY,
        monster_profile_resolver=lambda *args: pytest.fail(
            "provider-bound settlement fell back to legacy profile resolution"
        ),
    )

    assert result["result"] == "CORRECT"
    assert result["judge_version"] == MAP_BATTLE_JUDGE_VERSION
    settled = conn.execute(
        "SELECT monster_hp, battle_revision FROM map_battles WHERE id=?",
        (battle_id,),
    ).fetchone()
    assert settled["monster_hp"] < binding.max_hp
    assert settled["battle_revision"] == 1
    conn.close()
