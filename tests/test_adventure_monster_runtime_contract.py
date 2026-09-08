"""Focused coverage for the shared Adventure/Map Battle runtime contract."""

from __future__ import annotations

import hashlib
import sqlite3

import pytest

from adventure_monster_runtime_contract import (
    AdventureMonsterRuntimeBinding,
    AdventureMonsterRuntimeProviderRegistry,
    AdventureQuestionBinding,
    CanonicalAdventureProviderSlot,
    ClientAuthorityClaimError,
    E055Zone3ProviderAdapter,
    InvalidHpStateError,
    LegacyCompatibilityAdapter,
    MissingZoneError,
    ProfileBindingMismatchError,
    ProviderDisabledError,
    StaleQuestionBindingError,
    UnknownProviderError,
    WrongZoneBindingError,
    build_f006_defeat_event_fields,
    persistence_metadata,
    reject_client_authority_claims,
    validate_hp_state,
    validate_runtime_binding,
)
from adventure_zone3_monster_authority import (
    ZONE3_BINDING_SOURCE,
    ZONE3_BINDING_VERSION,
    ZONE3_KEY,
    encode_zone3_binding,
    select_zone3_binding,
    zone3_combat_profile,
)
from map_battle_persistence import (
    create_map_battle,
    ensure_map_battle_tables,
)
from map_battle_runtime import (
    JudgeUnavailable,
    ensure_submission_lifecycle_schema,
    issue_submission_nonce_for_attempt,
    settle_answer,
)
from monster_combat_profiles import MonsterCombatProfile
from monster_settlement import build_monster_defeated_event


def _z3_binding(question_binding: AdventureQuestionBinding) -> AdventureMonsterRuntimeBinding:
    source = select_zone3_binding(question_binding.question_id)
    return AdventureMonsterRuntimeBinding(
        provider_id="e055-zone3-test-provider",
        zone_key=source.zone_key,
        monster_id=source.monster_id,
        roster_slot=source.roster_slot,
        encounter_class=source.encounter_class,
        family_id=source.taxonomy_family,
        profile_id=source.profile_id,
        profile_version=source.profile_version,
        max_hp=source.max_hp,
        combat_profile=zone3_combat_profile(source),
        question_binding=question_binding,
        binding_source=ZONE3_BINDING_SOURCE,
        binding_version=ZONE3_BINDING_VERSION,
        persistence_source=ZONE3_BINDING_SOURCE,
        persistence_version=encode_zone3_binding(source),
        drop_profile_id=source.drop_profile_id,
        reward_profile_id=source.reward_profile_id,
        server_enabled=True,
    )


def _legacy_binding(question_binding: AdventureQuestionBinding) -> AdventureMonsterRuntimeBinding:
    profile = MonsterCombatProfile(
        canonical_monster_id="legacy-test-monster",
        zone_key="Z1",
        roster_slot=1,
        encounter_class="NORMAL",
        max_hp=100,
        attack=8,
        profile_id="legacy.test.profile",
        stat_source="test-only-server-fixture",
        compatibility_mode="LEGACY_COMPATIBILITY_ADAPTER",
        profile_version="legacy.test.v1",
    )
    return AdventureMonsterRuntimeBinding(
        provider_id="legacy-test-provider",
        zone_key="Z1",
        monster_id="legacy-test-monster",
        roster_slot=1,
        encounter_class="NORMAL",
        family_id="legacy-test-family",
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        max_hp=profile.max_hp,
        combat_profile=profile,
        question_binding=question_binding,
        binding_source="legacy.test.authority",
        binding_version="legacy.test.binding.v1",
        persistence_source="legacy.test.authority",
        persistence_version="legacy.test.map-battle.v1",
        server_enabled=True,
    )


def test_provider_dispatch_and_z3_protocol_use_one_shared_contract():
    question = AdventureQuestionBinding(7001, "question-revision-z3")
    provider = E055Zone3ProviderAdapter(
        zone_keys=(ZONE3_KEY,),
        provider_id="e055-zone3-test-provider",
        binding_resolver=lambda **kwargs: _z3_binding(kwargs["question_binding"]),
    )
    registry = AdventureMonsterRuntimeProviderRegistry((provider,))

    resolved = registry.resolve_binding(
        zone_key=ZONE3_KEY,
        question_binding=question,
    )

    assert resolved.zone_key == ZONE3_KEY
    assert resolved.combat_profile.profile_id == resolved.profile_id
    assert resolved.question_binding == question
    assert provider.runtime_role == "e055_provider"


def test_unknown_missing_disabled_and_wrong_zone_dispatch_fail_closed():
    registry = AdventureMonsterRuntimeProviderRegistry(
        (
            E055Zone3ProviderAdapter(
                zone_keys=(ZONE3_KEY,),
                provider_id="e055-zone3-test-provider",
                binding_resolver=lambda **kwargs: _z3_binding(kwargs["question_binding"]),
            ),
            CanonicalAdventureProviderSlot(zone_keys=("Z4", "Z5", "Z6", "Z7", "Z8", "Z9", "Z10")),
        )
    )

    with pytest.raises(MissingZoneError):
        registry.dispatch(zone_key=None)
    with pytest.raises(UnknownProviderError):
        registry.dispatch(zone_key="unknown-zone")
    with pytest.raises(ProviderDisabledError):
        registry.dispatch(zone_key="Z4")
    with pytest.raises(WrongZoneBindingError):
        registry.dispatch(zone_key=ZONE3_KEY, provider_id="canonical-adventure-provider-slot")


def test_binding_validation_rejects_stale_question_bad_hp_and_profile_version():
    question = AdventureQuestionBinding(7001, "question-revision-z3")
    binding = _z3_binding(question)

    with pytest.raises(StaleQuestionBindingError):
        validate_runtime_binding(
            binding,
            expected_zone_key=ZONE3_KEY,
            expected_question_binding=AdventureQuestionBinding(7001, "stale-revision"),
        )
    with pytest.raises(InvalidHpStateError):
        validate_hp_state(101, 100)
    with pytest.raises(ProfileBindingMismatchError):
        validate_runtime_binding(
            binding,
            expected_zone_key=ZONE3_KEY,
            expected_question_binding=question,
            expected_profile_version="e055.zone3.other.v1",
        )


def test_client_cannot_supply_monster_authority_claims():
    with pytest.raises(ClientAuthorityClaimError):
        reject_client_authority_claims({"profile_id": "client-supplied"})
    with pytest.raises(ClientAuthorityClaimError):
        reject_client_authority_claims({"MAX_HP": 999})


def test_legacy_compatibility_is_an_adapter_only():
    question = AdventureQuestionBinding(1, "legacy-question-revision")
    adapter = LegacyCompatibilityAdapter(
        zone_keys=("Z1", "Z2"),
        provider_id="legacy-test-provider",
        binding_resolver=lambda **kwargs: _legacy_binding(kwargs["question_binding"]),
    )
    registry = AdventureMonsterRuntimeProviderRegistry((adapter,))

    resolved = registry.resolve_binding(zone_key="Z1", question_binding=question)

    assert adapter.runtime_role == "legacy_compatibility_adapter"
    assert resolved.combat_profile.compatibility_mode == "LEGACY_COMPATIBILITY_ADAPTER"
    assert resolved.zone_key == "Z1"
    assert not hasattr(adapter, "calculate_damage")


def test_z4_to_z10_canonical_slots_are_disabled_without_authority():
    slot = CanonicalAdventureProviderSlot(
        zone_keys=tuple(f"Z{zone}" for zone in range(4, 11))
    )
    registry = AdventureMonsterRuntimeProviderRegistry((slot,))

    for zone in tuple(f"Z{number}" for number in range(4, 11)):
        with pytest.raises(ProviderDisabledError):
            registry.resolve_binding(
                zone_key=zone,
                question_binding=AdventureQuestionBinding(1, "not-admitted"),
            )


def test_persistence_and_f006_adapters_preserve_existing_interfaces():
    question = AdventureQuestionBinding(7001, "question-revision-z3")
    binding = _z3_binding(question)

    assert persistence_metadata(binding) == {
        "migration_source": ZONE3_BINDING_SOURCE,
        "migration_version": binding.persistence_version,
    }
    event = build_monster_defeated_event(
        **build_f006_defeat_event_fields(
            binding,
            settlement_id="map-battle-submission-1",
            user_id=101,
            hp_before=100,
            hp_after=0,
        )
    )
    assert event.monster_id == binding.monster_id
    assert event.zone_id == ZONE3_KEY
    assert event.hp_before == 100
    assert event.hp_after == 0


@pytest.fixture()
def map_battle_fixture():
    question = {
        "id": 7001,
        "source": "runtime-contract/test.sgf",
        "content": "(;SZ[19];B[dd];W[ee])",
        "monster_atk": 6,
    }
    revision = hashlib.sha256(question["content"].encode("utf-8")).hexdigest()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO users(id) VALUES (101)")
    ensure_map_battle_tables(conn)
    ensure_submission_lifecycle_schema(conn)
    create_map_battle(
        conn,
        battle_id="contract-battle",
        user_id=101,
        zone_key="legacy::forest",
        player_hp=20,
        player_hp_max=20,
        monster_hp=20,
        monster_hp_max=20,
        now="2026-08-02T00:00:00+00:00",
    )
    from map_battle_persistence import issue_map_battle_attempt

    issue_map_battle_attempt(
        conn,
        user_id=101,
        battle_id="contract-battle",
        question_id=question["id"],
        question_revision=revision,
        initial_position_identity="contract-position",
        board_size=19,
        player_color="B",
        transform_version="transform-v1",
        transform_id="identity",
        battle_revision_at_issue=0,
        attempt_id="contract-attempt",
        issued_at="2026-08-02T00:00:00+00:00",
        expires_at="2026-08-03T00:00:00+00:00",
    )
    nonce = issue_submission_nonce_for_attempt(
        conn,
        user_id=101,
        attempt_id="contract-attempt",
        now="2026-08-02T00:00:00+00:00",
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
    )["submission_nonce"]
    conn.commit()
    try:
        yield conn, question, revision, nonce
    finally:
        conn.close()


def test_new_provider_callers_do_not_fall_back_to_legacy_combat(map_battle_fixture):
    conn, question, revision, nonce = map_battle_fixture
    payload = {
        "battle_id": "contract-battle",
        "attempt_id": "contract-attempt",
        "submission_nonce": nonce,
        "battle_revision": 0,
        "question_revision": revision,
        "player_color": "black",
        "transform_id": "identity",
        "transform_version": "transform-v1",
        "moves": [{"x": 3, "y": 3}],
    }

    with pytest.raises(JudgeUnavailable):
        settle_answer(
            conn,
            user_id=101,
            payload=payload,
            question_loader=lambda question_id: question if question_id == question["id"] else None,
            mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
            now="2026-08-02T00:01:00+00:00",
            runtime_provider=CanonicalAdventureProviderSlot(
                zone_keys=("legacy::forest",),
            ),
        )

    battle = conn.execute(
        "SELECT monster_hp, player_hp, battle_revision, state FROM map_battles WHERE id=?",
        ("contract-battle",),
    ).fetchone()
    assert tuple(battle) == (20, 20, 0, "OPEN")
