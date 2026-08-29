"""E045 candidate-only Monster catalog/profile foundation contracts."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from monster_catalog_foundation import (
    ADVENTURE_NORMAL,
    ADVENTURE_PROFILE_AUTO_INHERITS_BATTLEFIELD,
    ART002_AUTOPROMOTED_COUNT,
    ART002_GAMEPLAY_AUTHORITY,
    BATTLEFIELD_BOSS,
    BATTLEFIELD_NORMAL,
    CANONICAL_MONSTER_CATALOG,
    COMMON_RARE_ELITE_ENABLED,
    COMBAT_CLASS_FREQUENCY_COUPLED,
    CombatProfileReference,
    CONTEXT_PROFILE_REFERENCE_EXPLICIT,
    CURRENT_BATTLEFIELD_PROFILE_SNAPSHOT,
    CURRENT_RUNTIME_AUTHORITY_PRESERVED,
    ELO_MONSTER_STAT_AUTHORITY,
    ENCOUNTER_CLASS_EXPLICIT,
    FABRICATED_LORD_NUMERIC_PROFILE,
    LORD,
    MISSING_PROFILE_FAIL_CLOSED,
    MONSTER_ID_IS_EXPLICIT,
    MonsterCatalog,
    NORMAL_BOSS_LORD_COLLAPSED,
    NEW_FOUNDATION_RUNTIME_ACTIVE,
    PROFILE_REFERENCE_VERSIONED,
    PROFILE_REGISTRY_VERSION,
    ROSTER_COUNT_USED_FOR_HP_ATK,
    SUPPORTED_CONTEXTS,
    UnknownMonsterError,
    UnknownProfileError,
    UNKNOWN_MONSTER_FAIL_CLOSED,
    UNKNOWN_PROFILE_FAIL_CLOSED,
    ZONE_QUESTION_STAGE_EVIDENCE,
    ZONE_QUESTION_STAGE_EVIDENCE_STATUS,
    ZONE_QUESTION_STAGE_MAPPING_CHANGED,
    get_monster,
    get_profile,
    list_monsters_for_zone,
    resolve_context_profile,
    MissingCombatProfileError,
)
from monster_encounter_selector import (
    MONSTER_SELECTOR_LIVE_ACTIVATED,
    RARITY_WEIGHT_POLICY_STATUS,
)
from monster_identity import ENCOUNTER_CLASS_BATTLEFIELD_BOSS, ENCOUNTER_CLASS_NORMAL
from monster_profiles import CANONICAL_MONSTER_PROFILE_REGISTRY


ROOT = Path(__file__).resolve().parents[1]


def _literal_assignment(name: str):
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    node = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    )
    return ast.literal_eval(node.value)


def test_foundation_flags_preserve_non_active_boundaries():
    assert MONSTER_ID_IS_EXPLICIT is True
    assert CONTEXT_PROFILE_REFERENCE_EXPLICIT is True
    assert PROFILE_REFERENCE_VERSIONED is True
    assert MISSING_PROFILE_FAIL_CLOSED is True
    assert UNKNOWN_MONSTER_FAIL_CLOSED is True
    assert UNKNOWN_PROFILE_FAIL_CLOSED is True
    assert ENCOUNTER_CLASS_EXPLICIT is True
    assert NORMAL_BOSS_LORD_COLLAPSED is False
    assert FABRICATED_LORD_NUMERIC_PROFILE is False
    assert ADVENTURE_PROFILE_AUTO_INHERITS_BATTLEFIELD is False
    assert ROSTER_COUNT_USED_FOR_HP_ATK is False
    assert NEW_FOUNDATION_RUNTIME_ACTIVE is False
    assert CURRENT_RUNTIME_AUTHORITY_PRESERVED is True


def test_catalog_has_explicit_stable_ids_and_no_art_autopromotion():
    entries = CANONICAL_MONSTER_CATALOG.entries

    assert len(entries) == 20
    assert len({entry.monster_id for entry in entries}) == len(entries)
    assert all(entry.monster_id.startswith("legacy_bf_") for entry in entries)
    assert all(not entry.monster_id.startswith("M") for entry in entries)
    assert all(entry.art_content_ref is None for entry in entries)
    assert ART002_GAMEPLAY_AUTHORITY is False
    assert ART002_AUTOPROMOTED_COUNT == 0
    assert all(entry.catalog_version == CANONICAL_MONSTER_CATALOG.version for entry in entries)
    assert all(entry.status == "CANDIDATE_NOT_LIVE" for entry in entries)


def test_catalog_context_contract_is_explicit_for_every_entry():
    entries = CANONICAL_MONSTER_CATALOG.entries

    assert SUPPORTED_CONTEXTS == {
        ADVENTURE_NORMAL,
        BATTLEFIELD_NORMAL,
        BATTLEFIELD_BOSS,
        LORD,
    }
    for entry in entries:
        assert set(entry.context_profile_refs) == set(SUPPORTED_CONTEXTS)
        assert len(entry.context_eligibility) == 1
        active_context = entry.context_eligibility[0]
        assert active_context in (BATTLEFIELD_NORMAL, BATTLEFIELD_BOSS)
        assert entry.context_profile_refs[active_context] is not None
        assert entry.context_profile_refs[ADVENTURE_NORMAL] is None
        assert entry.context_profile_refs[LORD] is None
        expected_class = (
            ENCOUNTER_CLASS_NORMAL
            if active_context == BATTLEFIELD_NORMAL
            else ENCOUNTER_CLASS_BATTLEFIELD_BOSS
        )
        assert entry.encounter_class == expected_class


def test_versioned_profiles_match_current_battlefield_roster_exactly():
    roster = _literal_assignment("_BATTLEFIELD_ROSTER")
    expected = []
    for index, row in enumerate(roster):
        zone_number = index // 2 + 1
        encounter_class = (
            ENCOUNTER_CLASS_NORMAL
            if row[4] == "normal"
            else ENCOUNTER_CLASS_BATTLEFIELD_BOSS
        )
        expected.append(
            (
                f"legacy_bf_{zone_number:02d}_{'normal' if row[4] == 'normal' else 'boss'}",
                f"zone_{zone_number:02d}",
                encounter_class,
                row[2],
                row[3],
            )
        )

    assert CURRENT_BATTLEFIELD_PROFILE_SNAPSHOT == tuple(expected)
    assert len(CANONICAL_MONSTER_CATALOG.profiles) == 20
    assert all(
        profile.source_authority == "F004_MONSTER_PROFILE_REGISTRY"
        and profile.version == PROFILE_REGISTRY_VERSION
        and profile.generated_from_zone is False
        and profile.generated_from_elo is False
        and profile.generated_from_roster_count is False
        for profile in CANONICAL_MONSTER_CATALOG.profiles.values()
    )


def test_profile_identity_and_context_resolution_are_separate():
    normal = get_monster("legacy_bf_01_normal")
    boss = get_monster("legacy_bf_01_boss")
    assert normal is not None
    assert boss is not None

    normal_profile = resolve_context_profile("legacy_bf_01_normal", BATTLEFIELD_NORMAL)
    boss_profile = resolve_context_profile("legacy_bf_01_boss", BATTLEFIELD_BOSS)
    assert (normal_profile.max_hp, normal_profile.attack) == (80, 2)
    assert (boss_profile.max_hp, boss_profile.attack) == (100, 2)
    assert normal_profile.profile_id != boss_profile.profile_id
    assert normal_profile.version == boss_profile.version == PROFILE_REGISTRY_VERSION

    with pytest.raises(MissingCombatProfileError):
        resolve_context_profile("legacy_bf_01_normal", BATTLEFIELD_BOSS)
    with pytest.raises(MissingCombatProfileError):
        resolve_context_profile("legacy_bf_01_boss", BATTLEFIELD_NORMAL)


def test_adventure_and_lord_contexts_do_not_inherit_or_fabricate_profiles():
    for entry in CANONICAL_MONSTER_CATALOG.entries:
        assert entry.context_profile_refs[ADVENTURE_NORMAL] is None
        assert entry.context_profile_refs[LORD] is None
        with pytest.raises(MissingCombatProfileError):
            resolve_context_profile(entry.monster_id, ADVENTURE_NORMAL)
        with pytest.raises(MissingCombatProfileError):
            resolve_context_profile(entry.monster_id, LORD)

    assert list_monsters_for_zone("zone_01", ADVENTURE_NORMAL) == ()
    assert list_monsters_for_zone("zone_01", LORD) == ()
    assert FABRICATED_LORD_NUMERIC_PROFILE is False


def test_zone_context_lists_only_explicit_memberships_without_random_selection():
    normal = list_monsters_for_zone("zone_01", BATTLEFIELD_NORMAL)
    boss = list_monsters_for_zone("zone_01", BATTLEFIELD_BOSS)
    assert [entry.monster_id for entry in normal] == ["legacy_bf_01_normal"]
    assert [entry.monster_id for entry in boss] == ["legacy_bf_01_boss"]
    assert list_monsters_for_zone("not-a-zone", BATTLEFIELD_NORMAL) == ()


def test_unknown_monster_and_profile_fail_closed_without_fuzzy_or_latest_fallback():
    assert get_monster("dragon") is None
    assert get_monster("monster.battlefield.zone_01.normal") is None
    assert get_profile("stat_legacy_bf_01_normal", "unknown-version") is None
    assert get_profile("missing-profile", PROFILE_REGISTRY_VERSION) is None
    with pytest.raises(UnknownMonsterError):
        resolve_context_profile("dragon", BATTLEFIELD_NORMAL)

    entry = get_monster("legacy_bf_01_normal")
    assert entry is not None
    broken_entry = replace(
        entry,
        context_profile_refs={
            **entry.context_profile_refs,
            BATTLEFIELD_NORMAL: CombatProfileReference(
                profile_id="missing-profile",
                version=PROFILE_REGISTRY_VERSION,
            ),
        },
    )
    broken_catalog = MonsterCatalog(
        entries=(broken_entry,),
        by_id={broken_entry.monster_id: broken_entry},
        profiles={},
    )
    with pytest.raises(UnknownProfileError):
        resolve_context_profile(
            broken_entry.monster_id,
            BATTLEFIELD_NORMAL,
            catalog=broken_catalog,
        )


def test_f009_stays_off_and_combat_class_is_not_frequency_authority():
    assert MONSTER_SELECTOR_LIVE_ACTIVATED is False
    assert RARITY_WEIGHT_POLICY_STATUS == "CANDIDATE_NOT_LIVE"
    assert COMMON_RARE_ELITE_ENABLED is False
    assert COMBAT_CLASS_FREQUENCY_COUPLED is False


def test_zone_question_stage_mismatch_is_explicit_evidence_only():
    assert ZONE_QUESTION_STAGE_EVIDENCE == (
        ("k26_30", "LV1", "LV1"),
        ("k21_25", "LV2", "LV1"),
        ("k16_20", "LV3", "LV2"),
        ("k11_15", "LV4", "LV3"),
        ("k6_10", "LV5", "LV4"),
        ("k1_5", "LV6", "LV5"),
        ("d1_2", "LV7", "LV7"),
        ("d3_4", "LV8", "LV8"),
        ("d5_6", "LV9", "LV9"),
        ("d7_plus", "LV10", "LV10"),
    )
    assert any(zone_stage != question_stage for _, zone_stage, question_stage in ZONE_QUESTION_STAGE_EVIDENCE)
    assert ZONE_QUESTION_STAGE_EVIDENCE_STATUS == "OBSERVED_NOT_GAMEPLAY_AUTHORITY"
    assert ZONE_QUESTION_STAGE_MAPPING_CHANGED is False
