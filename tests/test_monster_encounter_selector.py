from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from monster_combat_profiles import resolve_monster_combat_profile
from monster_encounter_selector import (
    MonsterEncounterCandidate,
    MonsterEncounterCatalogError,
    MonsterEncounterSelectionError,
    build_legacy_selector_candidates,
    select_monster_encounter,
    validate_monster_encounter_catalog,
)
from monster_profiles import CANONICAL_MONSTER_PROFILE_REGISTRY


def _synthetic_catalog(zone_count: int = 10):
    candidates = []
    for zone_number in range(1, zone_count + 1):
        zone = f"zone_{zone_number:02d}"
        for index in range(1, 6):
            candidates.append(
                MonsterEncounterCandidate(
                    monster_id=f"{zone}_common_{index:02d}",
                    zone_key=zone,
                    encounter_class="COMMON",
                    family_id=f"family_{zone_number:02d}_common_{index:02d}",
                )
            )
        for index in range(1, 3):
            candidates.append(
                MonsterEncounterCandidate(
                    monster_id=f"{zone}_rare_{index:02d}",
                    zone_key=zone,
                    encounter_class="RARE",
                    family_id=f"family_{zone_number:02d}_rare_{index:02d}",
                )
            )
            candidates.append(
                MonsterEncounterCandidate(
                    monster_id=f"{zone}_elite_{index:02d}",
                    zone_key=zone,
                    encounter_class="ELITE",
                    family_id=f"family_{zone_number:02d}_elite_{index:02d}",
                )
            )
        candidates.append(
            MonsterEncounterCandidate(
                monster_id=f"{zone}_battlefield_boss",
                zone_key=zone,
                encounter_class="BATTLEFIELD_BOSS",
                family_id=f"family_{zone_number:02d}_boss",
            )
        )
    return tuple(candidates)


def _regular(candidates, zone="zone_01"):
    return tuple(
        candidate
        for candidate in candidates
        if candidate.zone_key == zone
        and candidate.encounter_class != "BATTLEFIELD_BOSS"
    )


def test_legacy_20_roster_adapts_and_resolves_through_f008():
    candidates = build_legacy_selector_candidates()

    assert len(candidates) == 20
    assert sum(c.encounter_class == "BATTLEFIELD_BOSS" for c in candidates) == 10
    assert sum(c.encounter_class == "COMMON" for c in candidates) == 10
    assert len({candidate.monster_id for candidate in candidates}) == 20

    for profile in CANONICAL_MONSTER_PROFILE_REGISTRY.profiles:
        selected = select_monster_encounter(
            candidates,
            user_id="legacy-user",
            zone_key=profile.zone_key,
            operation_id=f"legacy-regular-{profile.monster_id}",
        )
        if profile.encounter_class == "BATTLEFIELD_BOSS":
            boss = select_monster_encounter(
                candidates,
                user_id="legacy-user",
                zone_key=profile.zone_key,
                encounter_intent="BATTLEFIELD_BOSS",
                operation_id=f"legacy-boss-{profile.monster_id}",
                battlefield_boss_authorized=True,
            )
            assert boss.monster_id == profile.monster_id
            resolved = resolve_monster_combat_profile(boss.f008_profile_input)
            assert resolved.canonical_monster_id == profile.monster_id
            assert resolved.encounter_class == "BATTLEFIELD_BOSS"
        else:
            assert selected.encounter_class == "COMMON"
            resolved = resolve_monster_combat_profile(selected.f008_profile_input)
            assert resolved.canonical_monster_id == profile.monster_id
            assert resolved.max_hp > 0


def test_synthetic_100_catalog_has_90_regular_and_10_bosses():
    candidates = validate_monster_encounter_catalog(_synthetic_catalog())
    assert len(candidates) == 100
    assert len(_regular(candidates)) == 9
    assert sum(c.encounter_class == "BATTLEFIELD_BOSS" for c in candidates) == 10
    assert len({candidate.monster_id for candidate in candidates}) == 100

    for zone_number in range(1, 11):
        zone = f"zone_{zone_number:02d}"
        regular = _regular(candidates, zone)
        assert len(regular) == 9
        boss = select_monster_encounter(
            candidates,
            user_id="synthetic-user",
            zone_key=zone,
            encounter_intent="BATTLEFIELD_BOSS",
            operation_id=f"boss-{zone}",
            battlefield_boss_authorized=True,
        )
        assert boss.encounter_class == "BATTLEFIELD_BOSS"
        assert boss.zone_key == zone


def test_unseen_first_exposes_all_nine_before_a_cycle_repeat():
    candidates = validate_monster_encounter_catalog(_synthetic_catalog(1))
    seen = set()
    last = None
    selected_ids = []

    for index in range(9):
        selected = select_monster_encounter(
            candidates,
            user_id="cycle-user",
            zone_key="zone_01",
            seen_monster_ids=seen,
            last_monster_id=last,
            operation_id=f"cycle-{index}",
        )
        assert selected.monster_id not in selected_ids
        assert selected.cycle_reset is False
        selected_ids.append(selected.monster_id)
        seen.add(selected.monster_id)
        last = selected.monster_id

    assert len(selected_ids) == 9
    next_selected = select_monster_encounter(
        candidates,
        user_id="cycle-user",
        zone_key="zone_01",
        seen_monster_ids=seen,
        last_monster_id=last,
        operation_id="cycle-9",
    )
    assert next_selected.cycle_reset is True
    assert next_selected.monster_id != last


def test_immediate_repeat_is_blocked_but_single_candidate_repeats():
    candidates = validate_monster_encounter_catalog(_synthetic_catalog(1))
    first = select_monster_encounter(
        candidates,
        user_id="repeat-user",
        zone_key="zone_01",
        operation_id="repeat-1",
    )
    second = select_monster_encounter(
        candidates,
        user_id="repeat-user",
        zone_key="zone_01",
        last_monster_id=first.monster_id,
        seen_monster_ids=(first.monster_id,),
        operation_id="repeat-2",
    )
    assert second.monster_id != first.monster_id

    one = (MonsterEncounterCandidate(
        monster_id="zone_01_only_monster",
        zone_key="zone_01",
        encounter_class="COMMON",
        family_id="only_family",
    ),)
    repeated = select_monster_encounter(
        one,
        user_id="repeat-user",
        zone_key="zone_01",
        last_monster_id="zone_01_only_monster",
        seen_monster_ids=("zone_01_only_monster",),
        operation_id="repeat-single",
    )
    assert repeated.monster_id == "zone_01_only_monster"


def test_family_diversity_is_soft_and_does_not_block_same_family_pool():
    candidates = (
        MonsterEncounterCandidate("zone_01_a", "zone_01", "COMMON", "family_a"),
        MonsterEncounterCandidate("zone_01_b", "zone_01", "COMMON", "family_b"),
    )
    selected = select_monster_encounter(
        candidates,
        user_id="family-user",
        zone_key="zone_01",
        last_family_id="family_a",
        operation_id="family-alt",
    )
    assert selected.family_id == "family_b"

    same_family = (
        MonsterEncounterCandidate("zone_01_a", "zone_01", "COMMON", "family_a"),
        MonsterEncounterCandidate("zone_01_b", "zone_01", "COMMON", "family_a"),
    )
    selected_same = select_monster_encounter(
        same_family,
        user_id="family-user",
        zone_key="zone_01",
        last_family_id="family_a",
        operation_id="family-same",
    )
    assert selected_same.monster_id in {"zone_01_a", "zone_01_b"}


def test_same_operation_is_deterministic_without_process_global_rng():
    candidates = validate_monster_encounter_catalog(_synthetic_catalog(1))
    args = dict(
        user_id="determinism-user",
        zone_key="zone_01",
        seen_monster_ids=("zone_01_common_01",),
        last_monster_id="zone_01_common_01",
        operation_id="server-operation-123",
    )
    first = select_monster_encounter(candidates, **args)
    second = select_monster_encounter(candidates, **args)
    assert first.runtime_fields() == second.runtime_fields()
    assert first.deterministic_seed_digest == second.deterministic_seed_digest


def test_rarity_weights_are_deterministic_candidate_policy_when_unseen_state_is_empty():
    candidates = validate_monster_encounter_catalog(_synthetic_catalog(1))
    counts = Counter()
    for index in range(2600):
        selected = select_monster_encounter(
            candidates,
            user_id="weight-user",
            zone_key="zone_01",
            operation_id=f"weight-{index}",
        )
        counts[selected.encounter_class] += 1

    total = sum(counts.values())
    assert 0.55 <= counts["COMMON"] / total <= 0.75
    assert 0.12 <= counts["RARE"] / total <= 0.32
    assert 0.05 <= counts["ELITE"] / total <= 0.22


def test_boss_intent_is_explicit_and_lord_is_rejected():
    candidates = validate_monster_encounter_catalog(_synthetic_catalog(1))
    with pytest.raises(MonsterEncounterSelectionError):
        select_monster_encounter(
            candidates,
            user_id="boss-user",
            zone_key="zone_01",
            encounter_intent="BATTLEFIELD_BOSS",
            operation_id="forged-boss",
        )

    regular = select_monster_encounter(
        candidates,
        user_id="boss-user",
        zone_key="zone_01",
        operation_id="regular-never-boss",
    )
    assert regular.encounter_class != "BATTLEFIELD_BOSS"

    with pytest.raises(MonsterEncounterCatalogError):
        validate_monster_encounter_catalog(
            (*_regular(candidates), MonsterEncounterCandidate(
                "lord_zone_01", "zone_01", "COMMON", "lord_family", is_lord=True
            ))
        )


@pytest.mark.parametrize(
    "bad_catalog",
    [
        (
            MonsterEncounterCandidate("zone_01_same", "zone_01", "COMMON", "f1"),
            MonsterEncounterCandidate("zone_01_same", "zone_02", "COMMON", "f2"),
        ),
        (MonsterEncounterCandidate("zone_01_missing", "", "COMMON", "f1"),),
        (MonsterEncounterCandidate("zone_01_bad_rarity", "zone_01", "COMMON", "f1", "MYTHIC"),),
        (
            MonsterEncounterCandidate("zone_01_boss_a", "zone_01", "BATTLEFIELD_BOSS", "f1"),
            MonsterEncounterCandidate("zone_01_boss_b", "zone_01", "BATTLEFIELD_BOSS", "f2"),
        ),
        (MonsterEncounterCandidate("史萊姆", "zone_01", "COMMON", "f1"),),
        (MonsterEncounterCandidate("zone_01_unknown", "zone_01", "MYSTERY", "f1"),),
    ],
)
def test_invalid_catalog_fails_closed(bad_catalog):
    with pytest.raises(MonsterEncounterCatalogError):
        validate_monster_encounter_catalog(bad_catalog)


def test_seen_state_is_scoped_by_explicit_zone_and_user_inputs():
    candidates = validate_monster_encounter_catalog(_synthetic_catalog())
    zone_two = select_monster_encounter(
        candidates,
        user_id="user-b",
        zone_key="zone_02",
        seen_monster_ids=tuple(c.monster_id for c in _regular(candidates, "zone_01")),
        last_monster_id="zone_01_common_01",
        operation_id="cross-zone",
    )
    assert zone_two.zone_key == "zone_02"
    assert zone_two.candidate_count == 9
    assert zone_two.cycle_reset is False

    user_a = select_monster_encounter(
        candidates,
        user_id="user-a",
        zone_key="zone_03",
        operation_id="cross-user",
    )
    user_b = select_monster_encounter(
        candidates,
        user_id="user-b",
        zone_key="zone_03",
        operation_id="cross-user",
    )
    assert user_a.zone_key == user_b.zone_key == "zone_03"
    assert user_a.seen_state_scope == user_b.seen_state_scope == "USER_AND_ZONE"


def test_selector_is_not_live_wired_and_does_not_change_app_source():
    app_source = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(
        encoding="utf-8"
    )
    assert "monster_encounter_selector" not in app_source
    assert "select_monster_encounter" not in app_source
