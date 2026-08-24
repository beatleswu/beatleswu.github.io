from __future__ import annotations

import sqlite3

import pytest

from migrations import monster_encounter_selector_state_v1 as selector_schema
from monster_combat_profiles import resolve_monster_combat_profile
from monster_encounter_selector import MonsterEncounterCandidate, MonsterSelectorPolicy
from monster_encounter_selector_runtime import (
    SelectorStateCorrupt,
    canonical_selector_zone_key,
    get_selection_operation,
    load_selector_state,
    monster_selector_v1_enabled,
    new_server_encounter_operation_id,
    reconstruct_selection_operation,
    select_durable_monster_encounter,
)


def _catalog(*, zone: str = "zone_01", count: int = 9):
    classes = ("COMMON",) * min(5, count) + ("RARE",) * max(0, min(2, count - 5))
    classes += ("ELITE",) * max(0, count - len(classes))
    return tuple(
        MonsterEncounterCandidate(
            monster_id=f"{zone}_monster_{index:02d}",
            zone_key=zone,
            encounter_class=classes[index - 1],
            family_id=f"family_{index:02d}",
        )
        for index in range(1, count + 1)
    )


@pytest.fixture()
def selector_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    selector_schema.upgrade(conn)
    try:
        yield conn
    finally:
        conn.close()


def test_schema_is_additive_and_caller_owns_commit(selector_db):
    inventory = selector_schema.validate_schema(selector_db)
    assert inventory["present"] is True
    assert inventory["schema_version"] == "monster_encounter_selector_state_v1"
    result = select_durable_monster_encounter(
        selector_db,
        user_id=101,
        zone_key="zone_01",
        encounter_operation_id="operation-1",
        candidates=_catalog(count=1),
    )
    assert result.replayed is False
    assert selector_db.execute(
        "SELECT COUNT(*) FROM monster_encounter_selection_operation"
    ).fetchone()[0] == 1
    selector_db.rollback()
    assert selector_db.execute(
        "SELECT COUNT(*) FROM monster_encounter_selection_operation"
    ).fetchone()[0] == 0


def test_same_operation_replays_without_advancing_state(selector_db):
    candidates = _catalog()
    first = select_durable_monster_encounter(
        selector_db,
        user_id=101,
        zone_key="zone_01",
        encounter_operation_id="operation-replay",
        candidates=candidates,
        now="2026-08-24T00:00:00+00:00",
    )
    selector_db.commit()
    before = load_selector_state(selector_db, user_id=101, zone_key="zone_01")
    replay = select_durable_monster_encounter(
        selector_db,
        user_id=101,
        zone_key="zone_01",
        encounter_operation_id="operation-replay",
        candidates=candidates,
        policy=MonsterSelectorPolicy(version="future-policy"),
        now="2026-08-24T01:00:00+00:00",
    )
    after = load_selector_state(selector_db, user_id=101, zone_key="zone_01")
    assert replay.replayed is True
    assert replay.monster_id == first.monster_id
    assert replay.operation.selector_policy_version == first.operation.selector_policy_version
    assert after == before
    assert get_selection_operation(
        selector_db,
        user_id=101,
        zone_key="zone_01",
        encounter_operation_id="operation-replay",
    ) == first.operation


def test_nine_regular_identities_are_seen_before_cycle_repeat(selector_db):
    candidates = _catalog()
    selected = []
    for index in range(9):
        result = select_durable_monster_encounter(
            selector_db,
            user_id=101,
            zone_key="zone_01",
            encounter_operation_id=f"cycle-{index}",
            candidates=candidates,
        )
        selector_db.commit()
        selected.append(result.monster_id)
        assert result.monster_id not in selected[:-1]
    assert len(set(selected)) == 9
    tenth = select_durable_monster_encounter(
        selector_db,
        user_id=101,
        zone_key="zone_01",
        encounter_operation_id="cycle-9",
        candidates=candidates,
    )
    assert tenth.operation.cycle_generation_after == 1
    assert tenth.monster_id != selected[-1]


def test_user_and_zone_state_are_isolated(selector_db):
    candidates = _catalog()
    a = select_durable_monster_encounter(
        selector_db,
        user_id=101,
        zone_key="zone_01",
        encounter_operation_id="same-operation-scope",
        candidates=candidates,
    )
    selector_db.commit()
    b = select_durable_monster_encounter(
        selector_db,
        user_id=202,
        zone_key="zone_01",
        encounter_operation_id="same-operation-scope",
        candidates=candidates,
    )
    selector_db.commit()
    c = select_durable_monster_encounter(
        selector_db,
        user_id=101,
        zone_key="zone_02",
        encounter_operation_id="same-operation-scope",
        candidates=_catalog(zone="zone_02"),
    )
    assert a.operation.user_id != b.operation.user_id
    assert a.operation.zone_key != c.operation.zone_key
    assert load_selector_state(selector_db, user_id=101, zone_key="zone_02") is not None


def test_single_candidate_allows_genuine_new_operation_repeat(selector_db):
    candidates = _catalog(count=1)
    first = select_durable_monster_encounter(
        selector_db,
        user_id=101,
        zone_key="zone_01",
        encounter_operation_id="single-1",
        candidates=candidates,
    )
    selector_db.commit()
    second = select_durable_monster_encounter(
        selector_db,
        user_id=101,
        zone_key="zone_01",
        encounter_operation_id="single-2",
        candidates=candidates,
    )
    assert second.monster_id == first.monster_id
    assert second.replayed is False


def test_selected_legacy_identity_resolves_through_f008(selector_db):
    from monster_encounter_selector import build_legacy_selector_candidates

    result = select_durable_monster_encounter(
        selector_db,
        user_id=101,
        zone_key="zone_01",
        encounter_operation_id=new_server_encounter_operation_id(101, "zone_01"),
        candidates=build_legacy_selector_candidates(),
    )
    profile = resolve_monster_combat_profile(result.selection.f008_profile_input)
    assert profile.canonical_monster_id == result.monster_id
    assert profile.max_hp > 0
    assert profile.encounter_class == "COMMON"


def test_invalid_persisted_seen_identity_fails_closed(selector_db):
    selector_db.execute(
        """INSERT INTO monster_encounter_selector_state
           (user_id, zone_key, cycle_generation, seen_monster_ids,
            policy_version, updated_at)
           VALUES (?, ?, 0, ?, ?, ?)""",
        (101, "zone_01", '["not_a_catalog_monster"]', "f009.v1", "now"),
    )
    selector_db.commit()
    with pytest.raises(SelectorStateCorrupt):
        select_durable_monster_encounter(
            selector_db,
            user_id=101,
            zone_key="zone_01",
            encounter_operation_id="corrupt-state",
            candidates=_catalog(count=1),
        )


def test_boss_requires_external_eligibility_and_does_not_enter_regular_cycle(selector_db):
    boss = MonsterEncounterCandidate(
        "zone_01_boss", "zone_01", "BATTLEFIELD_BOSS", "boss_family"
    )
    with pytest.raises(ValueError):
        select_durable_monster_encounter(
            selector_db,
            user_id=101,
            zone_key="zone_01",
            encounter_operation_id="boss-forged",
            candidates=(boss,),
            encounter_intent="BATTLEFIELD_BOSS",
        )


def test_flag_defaults_off_and_accepts_only_server_environment_values():
    assert monster_selector_v1_enabled({}) is False
    assert monster_selector_v1_enabled({"MONSTER_ENCOUNTER_SELECTOR_V1_ENABLED": "0"}) is False
    assert monster_selector_v1_enabled({"MONSTER_ENCOUNTER_SELECTOR_V1_ENABLED": "true"}) is True


def test_map_battle_legacy_zone_vocabulary_maps_to_stable_selector_zone():
    assert canonical_selector_zone_key("k26_30") == "zone_01"
    assert canonical_selector_zone_key("d7_plus") == "zone_10"
    assert canonical_selector_zone_key("zone_03") == "zone_03"
    with pytest.raises(Exception):
        canonical_selector_zone_key("lord_trial")


def test_reconstruction_exposes_operation_before_after_and_current_state(selector_db):
    result = select_durable_monster_encounter(
        selector_db,
        user_id=101,
        zone_key="zone_01",
        encounter_operation_id="reconstruct-me",
        candidates=_catalog(count=1),
    )
    selector_db.commit()
    reconstruction = reconstruct_selection_operation(
        selector_db,
        user_id=101,
        zone_key="zone_01",
        encounter_operation_id="reconstruct-me",
    )
    assert reconstruction["selected_monster_id"] == result.monster_id
    assert reconstruction["seen_monster_ids_before"] == []
    assert reconstruction["seen_monster_ids_after"] == [result.monster_id]
    assert reconstruction["current_state"]["last_monster_id"] == result.monster_id
