"""Focused proof for the Owner-approved Zone4-10 provider authority."""

from __future__ import annotations

import pytest

from adventure_monster_runtime_contract import (
    AdventureMonsterRuntimeProviderRegistry,
    AdventureQuestionBinding,
    ClientAuthorityClaimError,
    MissingBindingError,
    StaleQuestionBindingError,
    WrongZoneBindingError,
    reject_client_authority_claims,
    validate_runtime_binding,
)
from adventure_zone4_10_monster_identity_authority import (
    get_zone4_10_monster_identity,
)
from adventure_zone4_10_monster_runtime_provider import (
    E1A_POLICY_REFERENCE,
    ZONE4_10_BINDING_SOURCE,
    ZONE4_10_MONSTER_RUNTIME_PROVIDER,
    ZONE4_10_PERSISTENCE_VERSION,
    ZONE4_10_PROFILE_VERSION,
    get_zone4_10_monster_profile,
    iter_zone4_10_monster_profiles,
    require_zone4_10_monster_profile,
)


QUESTION = AdventureQuestionBinding(7401, "question-revision-7401")


def _expected_values(zone: str, encounter_class: str) -> tuple[int, int]:
    values = {
        "Z4": {"NORMAL": (143, 9), "ELITE": (229, 11), "BOSS": (329, 12)},
        "Z5": {"NORMAL": (180, 10), "ELITE": (288, 12), "BOSS": (414, 14)},
        "Z6": {"NORMAL": (223, 12), "ELITE": (357, 14), "BOSS": (513, 16)},
        "Z7": {"NORMAL": (278, 13), "ELITE": (445, 16), "BOSS": (639, 18)},
        "Z8": {"NORMAL": (340, 15), "ELITE": (544, 18), "BOSS": (782, 20)},
        "Z9": {"NORMAL": (420, 16), "ELITE": (672, 19), "BOSS": (966, 22)},
        "Z10": {"NORMAL": (520, 18), "ELITE": (832, 22), "BOSS": (1196, 24)},
    }
    return values[zone][encounter_class]


def _battle(binding, *, state="OPEN", hp=None):
    return {
        "zone_key": binding.zone_key,
        "question_id": binding.question_binding.question_id,
        "question_revision": binding.question_binding.question_revision,
        "migration_source": binding.persistence_source,
        "migration_version": binding.persistence_version,
        "profile_id": binding.profile_id,
        "profile_version": binding.profile_version,
        "monster_hp": binding.max_hp if hp is None else hp,
        "monster_hp_max": binding.max_hp,
        "player_hp": 20,
        "player_hp_max": 20,
        "state": state,
    }


def test_exact_79_rows_cover_c2a_with_owner_values_and_null_family():
    rows = iter_zone4_10_monster_profiles()

    assert len(rows) == 79
    assert len({row.monster_id for row in rows}) == 79
    assert len({row.profile_id for row in rows}) == 79
    assert {row.encounter_class for row in rows} == {"NORMAL", "ELITE", "BOSS"}
    assert sum(row.encounter_class == "NORMAL" for row in rows) == 44
    assert sum(row.encounter_class == "ELITE" for row in rows) == 22
    assert sum(row.encounter_class == "BOSS" for row in rows) == 13

    for row in rows:
        identity = get_zone4_10_monster_identity(row.monster_id)
        assert identity is not None
        assert row.zone_key == identity.zone_key
        assert row.max_hp, row.monster_id
        assert row.attack, row.monster_id
        assert (row.max_hp, row.attack) == _expected_values(
            row.zone_key,
            row.encounter_class,
        )
        assert row.family_id is None
        assert row.server_enabled is True
        assert row.profile_id == (
            f"adventure_{row.zone_key.lower()}_"
            f"{row.encounter_class.lower()}_{row.monster_id}"
        )
        assert row.profile_version == ZONE4_10_PROFILE_VERSION


def test_c2a_and_e1a_are_referenced_without_recreated_policy_values():
    for row in iter_zone4_10_monster_profiles():
        identity = get_zone4_10_monster_identity(row.monster_id)
        assert identity is not None
        policy = ZONE4_10_MONSTER_RUNTIME_PROVIDER.reward_policy_for(row.monster_id)
        assert policy is not None
        assert policy.monster_id == identity.monster_id
        assert policy.zone_key == identity.zone_key
        assert policy.coin_reward == 2
        assert policy.drop_eligible is False
        assert policy.monster_specific_xp is None

    binding = ZONE4_10_MONSTER_RUNTIME_PROVIDER.bind_new_battle(
        101,
        "Z4",
        QUESTION,
    )
    assert binding.reward_profile_id == E1A_POLICY_REFERENCE
    assert binding.persistence_source == ZONE4_10_BINDING_SOURCE


def test_shared_registry_uses_one_protocol_and_deterministic_server_selection():
    registry = AdventureMonsterRuntimeProviderRegistry(
        (ZONE4_10_MONSTER_RUNTIME_PROVIDER,)
    )
    first = registry.resolve_binding(
        zone_key="Z4",
        question_binding=QUESTION,
        user_id=101,
    )
    second = registry.resolve_binding(
        zone_key="Z4",
        question_binding=QUESTION,
        user_id=999,
    )
    assert first.monster_id == second.monster_id
    assert first.zone_key == "Z4"
    assert first.server_enabled is True
    assert first.family_id is None


def test_selection_is_zone_bounded_and_does_not_use_art_or_name():
    for zone in ("Z4", "Z5", "Z6", "Z7", "Z8", "Z9", "Z10"):
        binding = ZONE4_10_MONSTER_RUNTIME_PROVIDER.bind_new_battle(
            101,
            zone,
            QUESTION,
        )
        identity = get_zone4_10_monster_identity(binding.monster_id)
        assert identity is not None
        assert identity.zone_key == zone
        assert "art" not in binding.monster_id.casefold()


def test_client_m_id_claims_are_rejected_by_shared_boundary():
    with pytest.raises(ClientAuthorityClaimError):
        reject_client_authority_claims({"monster_id": "M034"})


def test_unknown_and_wrong_zone_profiles_fail_closed():
    assert get_zone4_10_monster_profile("M001") is None
    with pytest.raises(MissingBindingError):
        require_zone4_10_monster_profile("M001")

    binding = ZONE4_10_MONSTER_RUNTIME_PROVIDER.bind_new_battle(101, "Z4", QUESTION)
    wrong_zone_battle = _battle(binding)
    wrong_zone_battle["zone_key"] = "Z5"
    with pytest.raises(WrongZoneBindingError):
        ZONE4_10_MONSTER_RUNTIME_PROVIDER.restore_binding(
            wrong_zone_battle,
            QUESTION,
        )

    unknown_token_battle = _battle(binding)
    unknown_token_battle["migration_version"] = ":".join(
        (
            ZONE4_10_PERSISTENCE_VERSION,
            "Z4",
            "M001",
            "adventure_z4_normal_M001",
            ZONE4_10_PROFILE_VERSION,
        )
    )
    with pytest.raises(MissingBindingError):
        ZONE4_10_MONSTER_RUNTIME_PROVIDER.restore_binding(
            unknown_token_battle,
            QUESTION,
        )


def test_restore_preserves_immutable_identity_and_rejects_stale_question():
    binding = ZONE4_10_MONSTER_RUNTIME_PROVIDER.bind_new_battle(101, "Z6", QUESTION)
    restored = ZONE4_10_MONSTER_RUNTIME_PROVIDER.restore_binding(
        _battle(binding),
        QUESTION,
    )
    assert restored.monster_id == binding.monster_id
    assert restored.profile_id == binding.profile_id
    assert restored.profile_version == binding.profile_version
    assert restored.question_binding == QUESTION

    with pytest.raises(StaleQuestionBindingError):
        ZONE4_10_MONSTER_RUNTIME_PROVIDER.restore_binding(
            _battle(binding),
            AdventureQuestionBinding(QUESTION.question_id, "different-revision"),
        )


def test_presentation_payload_matches_binding_and_deferred_taxonomy():
    binding = ZONE4_10_MONSTER_RUNTIME_PROVIDER.bind_new_battle(101, "Z10", QUESTION)
    payload = ZONE4_10_MONSTER_RUNTIME_PROVIDER.presentation_payload(
        binding,
        _battle(binding),
    )
    assert payload["monster_id"] == binding.monster_id
    assert payload["zone_key"] == "Z10"
    assert payload["max_hp"] == binding.max_hp
    assert payload["attack"] == binding.combat_profile.attack
    assert payload["family_id"] is None
    assert payload["server_enabled"] is True


def test_shared_contract_validates_null_family_and_persisted_binding():
    binding = ZONE4_10_MONSTER_RUNTIME_PROVIDER.bind_new_battle(101, "Z8", QUESTION)
    validated = validate_runtime_binding(
        binding,
        expected_zone_key="Z8",
        expected_question_binding=QUESTION,
        expected_provider_id=ZONE4_10_MONSTER_RUNTIME_PROVIDER.provider_id,
        battle=_battle(binding),
    )
    assert validated.family_id is None
    assert validated.persistence_version.startswith(
        f"{ZONE4_10_PERSISTENCE_VERSION}:Z8:"
    )
