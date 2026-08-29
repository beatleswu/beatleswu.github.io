"""Deterministic E046 shadow-adapter and authority-boundary contracts."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from monster_catalog_foundation import (
    ADVENTURE_NORMAL,
    BATTLEFIELD_BOSS,
    BATTLEFIELD_NORMAL,
    CANONICAL_MONSTER_CATALOG,
    CombatProfileReference,
    CURRENT_BATTLEFIELD_PROFILE_SNAPSHOT,
    LORD,
    PROFILE_REGISTRY_VERSION,
    ZONE_QUESTION_STAGE_EVIDENCE,
    get_monster,
)
from monster_catalog_shadow_adapter import (
    ACTIVE_GAMEPLAY_OUTPUT_CHANGED,
    ADVENTURE_MISSING_PROFILE_FAILS_CLOSED,
    F009_ENABLED,
    GENERATED_PROFILE_FORMULA_FALLBACK,
    LORD_NUMERIC_PROFILE_CREATED,
    LORD_SHADOW_CLASSIFICATION,
    MONSTER_ID_DERIVED_FROM_PRESENTATION,
    SHADOW_ADAPTER_CREATED,
    SHADOW_ADAPTER_RUNTIME_AUTHORITY,
    ShadowIdentityInputError,
    compare_runtime_encounter,
    compare_runtime_encounters,
)
from monster_catalog_foundation import (
    MissingCombatProfileError,
    UnknownMonsterError,
    UnknownProfileError,
)


ROOT = Path(__file__).resolve().parents[1]


def test_shadow_adapter_is_created_but_cannot_be_runtime_authority():
    assert SHADOW_ADAPTER_CREATED is True
    assert SHADOW_ADAPTER_RUNTIME_AUTHORITY is False
    assert ACTIVE_GAMEPLAY_OUTPUT_CHANGED is False
    assert MONSTER_ID_DERIVED_FROM_PRESENTATION is False
    assert GENERATED_PROFILE_FORMULA_FALLBACK is False
    assert F009_ENABLED is False
    assert ADVENTURE_MISSING_PROFILE_FAILS_CLOSED is True
    assert LORD_NUMERIC_PROFILE_CREATED is False


def test_battlefield_normal_all_ten_zones_have_exact_shadow_parity():
    rows = [
        row for row in CURRENT_BATTLEFIELD_PROFILE_SNAPSHOT if row[2] == "NORMAL"
    ]
    comparisons = compare_runtime_encounters(
        [
            {
                "monster_id": monster_id,
                "current_hp": max_hp,
                "current_atk": attack,
            }
            for monster_id, _zone, _class, max_hp, attack in rows
        ],
        context=BATTLEFIELD_NORMAL,
    )

    assert len(comparisons) == 10
    assert all(item.parity == "PASS" for item in comparisons)
    assert [item.foundation_monster_id for item in comparisons] == [row[0] for row in rows]
    assert [(item.foundation_hp, item.foundation_atk) for item in comparisons] == [
        (row[3], row[4]) for row in rows
    ]


def test_battlefield_boss_all_ten_zones_have_exact_shadow_parity():
    rows = [
        row
        for row in CURRENT_BATTLEFIELD_PROFILE_SNAPSHOT
        if row[2] == "BATTLEFIELD_BOSS"
    ]
    comparisons = compare_runtime_encounters(
        [
            {
                "roster_slot": index + 1,
                "current_hp": max_hp,
                "current_atk": attack,
            }
            for index, (_monster_id, _zone, _class, max_hp, attack) in enumerate(
                CURRENT_BATTLEFIELD_PROFILE_SNAPSHOT
            )
            if _class == "BATTLEFIELD_BOSS"
        ],
        context=BATTLEFIELD_BOSS,
    )

    assert len(comparisons) == 10
    assert all(item.parity == "PASS" for item in comparisons)
    assert [(item.foundation_hp, item.foundation_atk) for item in comparisons] == [
        (row[3], row[4]) for row in rows
    ]


def test_shadow_result_reports_requested_contract_without_correcting_runtime():
    result = compare_runtime_encounter(
        {
            "monster_id": "legacy_bf_01_normal",
            "current_hp": 81,
            "current_atk": 9,
        },
        context=BATTLEFIELD_NORMAL,
    )

    assert result.parity == "MISMATCH"
    assert result.current_hp == 81
    assert result.current_atk == 9
    assert result.foundation_hp == 80
    assert result.foundation_atk == 2
    assert result.as_contract()["PARITY"] == "MISMATCH"
    assert result.foundation_profile_version == PROFILE_REGISTRY_VERSION


def test_context_reference_is_explicit_and_does_not_inherit_battlefield_profile():
    adventure = compare_runtime_encounter(
        {"monster_id": "legacy_bf_01_normal", "current_hp": 80, "current_atk": 2},
        context=ADVENTURE_NORMAL,
    )
    assert adventure.parity == "NOT_APPLICABLE"
    assert adventure.foundation_hp is None
    assert adventure.foundation_atk is None
    assert adventure.reason == "NO_EXPLICIT_ADVENTURE_PROFILE"

    with pytest.raises(MissingCombatProfileError):
        compare_runtime_encounter(
            {"monster_id": "legacy_bf_01_normal", "current_hp": 80, "current_atk": 2},
            context=BATTLEFIELD_BOSS,
        )


def test_adventure_and_lord_missing_identity_are_typed_no_profile_observations():
    adventure = compare_runtime_encounter({}, context=ADVENTURE_NORMAL)
    lord = compare_runtime_encounter({}, context=LORD)

    assert adventure.parity == "NOT_APPLICABLE"
    assert adventure.reason == "NO_EXPLICIT_ADVENTURE_PROFILE"
    assert lord.parity == "NOT_APPLICABLE"
    assert lord.reason == LORD_SHADOW_CLASSIFICATION
    assert lord.foundation_hp is None
    assert lord.foundation_atk is None


def test_unknown_identity_and_presentation_only_inputs_fail_closed():
    with pytest.raises(UnknownMonsterError):
        compare_runtime_encounter(
            {"monster_id": "not-a-canonical-monster", "current_hp": 1, "current_atk": 1},
            context=BATTLEFIELD_NORMAL,
        )

    with pytest.raises(ShadowIdentityInputError):
        compare_runtime_encounter(
            {"display_name": "LV1 Slime / Goblin", "current_hp": 80, "current_atk": 2},
            context=BATTLEFIELD_NORMAL,
        )

    with pytest.raises(ShadowIdentityInputError):
        compare_runtime_encounter(
            {"monster_idx": 0, "current_hp": 80, "current_atk": 2},
            context=BATTLEFIELD_NORMAL,
        )

    with pytest.raises(UnknownMonsterError):
        compare_runtime_encounter(
            {"roster_slot": 999, "current_hp": 80, "current_atk": 2},
            context=BATTLEFIELD_NORMAL,
        )


def test_explicit_f003_roster_slot_is_allowed_and_id_slot_conflicts_fail_closed():
    result = compare_runtime_encounter(
        {"roster_slot": 1, "current_hp": 80, "current_atk": 2},
        context=BATTLEFIELD_NORMAL,
    )
    assert result.current_monster_id == "legacy_bf_01_normal"
    assert result.parity == "PASS"

    with pytest.raises(ShadowIdentityInputError):
        compare_runtime_encounter(
            {
                "monster_id": "legacy_bf_01_normal",
                "roster_slot": 2,
                "current_hp": 80,
                "current_atk": 2,
            },
            context=BATTLEFIELD_NORMAL,
        )


def test_broken_explicit_profile_reference_does_not_fallback_or_generate():
    entry = get_monster("legacy_bf_01_normal")
    assert entry is not None
    references = dict(entry.context_profile_refs)
    references[BATTLEFIELD_NORMAL] = CombatProfileReference(
        profile_id="missing-profile",
        version=PROFILE_REGISTRY_VERSION,
    )
    broken_entry = replace(entry, context_profile_refs=references)
    broken_catalog = replace(
        CANONICAL_MONSTER_CATALOG,
        entries=tuple(
            broken_entry if item.monster_id == entry.monster_id else item
            for item in CANONICAL_MONSTER_CATALOG.entries
        ),
        by_id={
            **CANONICAL_MONSTER_CATALOG.by_id,
            entry.monster_id: broken_entry,
        },
        profiles={
            key: profile
            for key, profile in CANONICAL_MONSTER_CATALOG.profiles.items()
            if key != ("missing-profile", PROFILE_REGISTRY_VERSION)
        },
    )

    with pytest.raises(UnknownProfileError):
        compare_runtime_encounter(
            {"monster_id": entry.monster_id, "current_hp": 80, "current_atk": 2},
            context=BATTLEFIELD_NORMAL,
            catalog=broken_catalog,
        )


def test_mapping_and_runtime_firewall_remain_unchanged():
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
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "monster_catalog_shadow_adapter" not in app_source
