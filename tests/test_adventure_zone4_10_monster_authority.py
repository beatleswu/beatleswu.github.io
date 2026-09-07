from __future__ import annotations

import pytest

import adventure_zone4_10_monster_authority as adapter
from adventure_zone4_10_monster_identity_authority import (
    AdventureZoneMonsterIdentity,
    ZONE4_10_MONSTER_IDENTITIES,
)


LEGACY_BATTLEFIELD_ANCHORS = {
    "M034": "legacy_bf_04_normal",
    "M046": "legacy_bf_05_normal",
    "M058": "legacy_bf_06_normal",
    "M071": "legacy_bf_07_normal",
    "M084": "legacy_bf_08_normal",
    "M098": "legacy_bf_09_normal",
    "M112": "legacy_bf_10_normal",
}


def test_adapter_consumes_canonical_objects_without_recopying_the_truth_set():
    assert adapter.ADVENTURE_ZONE4_10_MONSTER_IDENTITIES is ZONE4_10_MONSTER_IDENTITIES
    assert adapter.all_adventure_monster_identities() is ZONE4_10_MONSTER_IDENTITIES
    assert len(adapter.all_adventure_monster_identities()) == 79
    assert len(adapter.ADVENTURE_ZONE4_10_MONSTER_IDENTITY_BY_ID) == 79
    assert len({identity.monster_id for identity in adapter.all_adventure_monster_identities()}) == 79


def test_zone_membership_is_exact_and_derived_from_canonical_records():
    assert {
        zone: len(adapter.adventure_monster_identities_for_zone(zone))
        for zone in adapter.ADVENTURE_ZONE_KEYS
    } == {
        "Z4": 12,
        "Z5": 12,
        "Z6": 12,
        "Z7": 12,
        "Z8": 11,
        "Z9": 10,
        "Z10": 10,
    }
    assert all(
        identity.zone_key == zone
        for zone in adapter.ADVENTURE_ZONE_KEYS
        for identity in adapter.adventure_monster_identities_for_zone(zone)
    )


def test_canonical_identity_fields_and_m073_are_preserved():
    assert all(isinstance(identity, AdventureZoneMonsterIdentity) for identity in adapter.all_adventure_monster_identities())
    assert all(
        set(identity.as_record())
        == {"M_ID", "canonical_name_zh", "canonical_name_en", "zone_key"}
        for identity in adapter.all_adventure_monster_identities()
    )
    m073 = adapter.require_adventure_monster_identity("M073")
    assert (m073.canonical_name_zh, m073.canonical_name_en, m073.zone_key) == (
        "黃銅魔像",
        "Brass Golem",
        "Z10",
    )


@pytest.mark.parametrize("monster_id, legacy_id", LEGACY_BATTLEFIELD_ANCHORS.items())
def test_legacy_battlefield_anchors_are_not_automatic_adventure_aliases(monster_id, legacy_id):
    assert adapter.is_adventure_monster_identity(monster_id)
    assert adapter.get_adventure_monster_identity(legacy_id) is None
    with pytest.raises(adapter.AdventureMonsterIdentityLookupError):
        adapter.require_adventure_monster_identity(legacy_id)


def test_legacy_battlefield_auto_alias_count_is_zero():
    assert adapter.LEGACY_BATTLEFIELD_AUTO_ALIAS_COUNT == 0


def test_unknown_identity_fails_closed():
    assert adapter.get_adventure_monster_identity("M999") is None
    assert adapter.is_adventure_monster_identity("M999") is False
    with pytest.raises(adapter.AdventureMonsterIdentityLookupError):
        adapter.require_adventure_monster_identity("M999")


def test_wrong_zone_lookup_fails_closed():
    assert adapter.get_adventure_monster_identity("M034", zone_key="Z5") is None
    with pytest.raises(adapter.AdventureMonsterIdentityLookupError):
        adapter.require_adventure_monster_identity("M034", zone_key="Z5")
    with pytest.raises(adapter.AdventureMonsterIdentityLookupError):
        adapter.adventure_monster_identities_for_zone("zone_4")


def test_c2a_does_not_admit_runtime_or_gameplay_bindings():
    assert adapter.ADVENTURE_RUNTIME_ADMISSION_PERFORMED is False
    assert adapter.RUNTIME_READY_COUNT == 0
    assert adapter.QUESTION_BINDING_CREATED is False
    assert adapter.PROFILE_BINDING_CREATED is False
    assert adapter.COMBAT_BINDING_CREATED is False
    assert adapter.REWARD_BINDING_CREATED is False
    assert adapter.DROP_BINDING_CREATED is False
    assert adapter.PERSISTED_ENCOUNTER_BINDING_CREATED is False
    assert adapter.BOSS_LORD_IDENTITY_CREATED is False
    assert adapter.ELITE_IDENTITY_CREATED is False


def test_malformed_source_duplicate_is_rejected_before_indexing():
    duplicate = adapter.all_adventure_monster_identities() + (
        adapter.all_adventure_monster_identities()[0],
    )
    with pytest.raises(adapter.AdventureMonsterIdentityAuthorityError):
        adapter._validate_consumed_identity_authority(duplicate)


def test_malformed_source_wrong_zone_is_rejected_before_indexing():
    original = adapter.all_adventure_monster_identities()[0]
    malformed = (AdventureZoneMonsterIdentity(
        original.monster_id,
        original.canonical_name_zh,
        original.canonical_name_en,
        "Z11",
    ),) + adapter.all_adventure_monster_identities()[1:]
    with pytest.raises(adapter.AdventureMonsterIdentityAuthorityError):
        adapter._validate_consumed_identity_authority(malformed)
