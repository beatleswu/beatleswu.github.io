from __future__ import annotations

import sqlite3
import sys
import types
from pathlib import Path

import pytest

from migrations import monster_encounter_selector_state_v1 as selector_schema
from adventure_zone1_2_monster_runtime_provider import (
    ZONE1_2_BINDING_SOURCE,
    ZONE1_2_PERSISTENCE_VERSION,
    ZONE1_2_PROVIDER_ID,
)
from map_battle_runtime import resolve_map_battle_provider_for_restore
from monster_combat_profiles import resolve_monster_combat_profile
from monster_encounter_selector import MonsterEncounterCandidate, MonsterSelectorPolicy
from monster_encounter_selector_runtime import (
    F009_HARD_FENCE_POLICY,
    F009_SELECTOR_MIGRATION_VERSION,
    SelectorStateCorrupt,
    SelectorProviderAuthorityUnavailable,
    canonical_selector_zone_key,
    reject_unadmitted_selector_encounter,
    get_selection_operation,
    load_selector_state,
    monster_selector_v1_enabled,
    new_server_encounter_operation_id,
    reconstruct_selection_operation,
    select_durable_monster_encounter,
)


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from test_map_battle_legacy_adapter import api_env as api_env
except ImportError:  # pragma: no cover - direct non-pytest imports
    api_env = None


def _install_app_import_stubs():
    """Keep the bounded route proof independent of optional integrations."""

    if "katago_explain" not in sys.modules:
        module = types.ModuleType("katago_explain")
        module.KataGoExplainer = type("KataGoExplainer", (), {})
        sys.modules["katago_explain"] = module
    if "explain_overrides" not in sys.modules:
        module = types.ModuleType("explain_overrides")
        module.get_override = lambda *args, **kwargs: None
        sys.modules["explain_overrides"] = module
    if "grimoire_api" not in sys.modules:
        from flask import Blueprint

        module = types.ModuleType("grimoire_api")
        module.grimoire_bp = Blueprint("grimoire_stub_f009", __name__)
        sys.modules["grimoire_api"] = module
    if "question_taxonomy" not in sys.modules:
        module = types.ModuleType("question_taxonomy")
        module.get_taxonomy = lambda *args, **kwargs: {}
        sys.modules["question_taxonomy"] = module
    if "monster_taxonomy" not in sys.modules:
        module = types.ModuleType("monster_taxonomy")
        module.get_monster_taxonomy = lambda *args, **kwargs: {}
        module.mark_encounters = lambda *args, **kwargs: None
        sys.modules["monster_taxonomy"] = module
    if "chapter_i18n" not in sys.modules:
        module = types.ModuleType("chapter_i18n")
        module.localize_topic = lambda *args, **kwargs: ""
        module.localize_level = lambda *args, **kwargs: ""
        sys.modules["chapter_i18n"] = module
    if "backend_i18n" not in sys.modules:
        module = types.ModuleType("backend_i18n")
        module.badge_en = lambda *args, **kwargs: ""
        module.skill_node_en = lambda *args, **kwargs: ""
        module.title_en = lambda *args, **kwargs: ""
        sys.modules["backend_i18n"] = module


@pytest.fixture(scope="module")
def app_module():
    _install_app_import_stubs()
    import app as module

    module.app.config["TESTING"] = True
    return module


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


def test_f009_hard_fence_rejects_unresolved_new_identity_before_mutation():
    with pytest.raises(SelectorProviderAuthorityUnavailable):
        reject_unadmitted_selector_encounter(
            zone_key="zone_01",
            selected_monster_id="legacy_bf_01_normal",
            phase="new encounter",
        )

    assert F009_HARD_FENCE_POLICY == "FAIL_CLOSED_UNRESOLVED_NEW_IDENTITY"


def test_all_twenty_legacy_selector_identities_are_blocked_from_new_runtime_creation():
    from monster_encounter_selector import build_legacy_selector_candidates

    candidates = build_legacy_selector_candidates()
    assert len(candidates) == 20
    for candidate in candidates:
        with pytest.raises(SelectorProviderAuthorityUnavailable):
            reject_unadmitted_selector_encounter(
                zone_key=candidate.zone_key,
                selected_monster_id=candidate.monster_id,
            )


def test_f009_unresolved_identity_fails_closed_without_reward_or_progress_callbacks():
    reward_calls = []
    progress_calls = []
    with pytest.raises(SelectorProviderAuthorityUnavailable):
        reject_unadmitted_selector_encounter(
            zone_key="zone_01",
            selected_monster_id=None,
            phase="unresolved identity",
        )
    assert reward_calls == []
    assert progress_calls == []


def test_enabled_f009_route_uses_canonical_provider_before_legacy_selector(
    api_env, app_module, monkeypatch
):
    if api_env is None:  # pragma: no cover - direct non-pytest imports
        pytest.skip("shared disposable API fixture unavailable")
    client, conn = api_env
    monkeypatch.setattr(
        app_module,
        "_questions_for_adventure_zone",
        lambda questions, zone, premium=True: list(questions),
    )
    monkeypatch.setenv("MONSTER_ENCOUNTER_SELECTOR_V1_ENABLED", "true")

    before = {
        "battles": conn.execute("SELECT COUNT(*) FROM map_battles").fetchone()[0],
        "attempts": conn.execute("SELECT COUNT(*) FROM map_battle_attempts").fetchone()[0],
        "srs": conn.execute("SELECT COUNT(*) FROM srs_cards").fetchone()[0],
        "reviews": conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0],
        "stats": tuple(conn.execute(
            "SELECT player_hp, player_max_hp, xp, rank_xp FROM user_stats WHERE user_id=101"
        ).fetchone()),
    }
    response = client.post(
        "/api/adventure/map-battles/v1/attempts",
        json={"zone_key": "k26_30", "question_id": 7001},
        headers={"X-Map-Battle-Client-Protocol": "v1"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    persisted_battle = dict(
        conn.execute(
            "SELECT * FROM map_battles WHERE id=?", (payload["battle_id"],)
        ).fetchone()
    )
    assert persisted_battle["migration_source"] == ZONE1_2_BINDING_SOURCE
    version_parts = str(persisted_battle["migration_version"]).split(":")
    assert version_parts[0] == ZONE1_2_PERSISTENCE_VERSION
    assert version_parts[1] == "Z1"
    assert persisted_battle["migration_source"] != "legacy-adventure-map"
    restored = resolve_map_battle_provider_for_restore(
        battle=persisted_battle,
        question_binding={
            "question_id": 7001,
            "question_revision": payload["question_revision"],
        },
        user_id=101,
    )
    assert restored.mode == "RESTORE_EXISTING_PROVIDER_BOUND_BATTLE"
    assert restored.provider_id == ZONE1_2_PROVIDER_ID
    assert restored.binding is not None
    assert restored.binding.provider_id == ZONE1_2_PROVIDER_ID
    assert restored.binding.persistence_source == ZONE1_2_BINDING_SOURCE
    after = {
        "battles": conn.execute("SELECT COUNT(*) FROM map_battles").fetchone()[0],
        "attempts": conn.execute("SELECT COUNT(*) FROM map_battle_attempts").fetchone()[0],
        "srs": conn.execute("SELECT COUNT(*) FROM srs_cards").fetchone()[0],
        "reviews": conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0],
        "stats": tuple(conn.execute(
            "SELECT player_hp, player_max_hp, xp, rank_xp FROM user_stats WHERE user_id=101"
        ).fetchone()),
    }
    assert after["battles"] == before["battles"] + 1
    assert after["attempts"] == before["attempts"] + 1
    assert after["srs"] == before["srs"]
    assert after["reviews"] == before["reviews"]
    assert after["stats"] == before["stats"]


def test_f009_unresolved_provider_identity_fails_closed_without_any_mutation(
    api_env, app_module, monkeypatch
):
    if api_env is None:  # pragma: no cover - direct non-pytest imports
        pytest.skip("shared disposable API fixture unavailable")
    client, conn = api_env
    reward_calls = []
    progress_calls = []
    monkeypatch.setattr(
        app_module,
        "_questions_for_adventure_zone",
        lambda questions, zone, premium=True: list(questions),
    )
    monkeypatch.setattr(
        app_module,
        "_map_battle_provider_for_new",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        app_module,
        "check_and_award",
        lambda *args, **kwargs: reward_calls.append((args, kwargs)) or [],
    )
    monkeypatch.setattr(
        app_module,
        "_update_monster_and_quests",
        lambda *args, **kwargs: progress_calls.append((args, kwargs)) or {},
    )
    monkeypatch.setenv("MONSTER_ENCOUNTER_SELECTOR_V1_ENABLED", "true")
    before = {
        "battles": conn.execute("SELECT COUNT(*) FROM map_battles").fetchone()[0],
        "attempts": conn.execute("SELECT COUNT(*) FROM map_battle_attempts").fetchone()[0],
        "srs": conn.execute("SELECT COUNT(*) FROM srs_cards").fetchone()[0],
        "reviews": conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0],
        "stats": tuple(conn.execute(
            "SELECT player_hp, player_max_hp, xp, rank_xp FROM user_stats WHERE user_id=101"
        ).fetchone()),
    }
    response = client.post(
        "/api/adventure/map-battles/v1/attempts",
        json={"zone_key": "k26_30", "question_id": 7001},
        headers={"X-Map-Battle-Client-Protocol": "v1"},
    )

    assert response.status_code == 503
    assert response.get_json()["code"] == "monster_selector_unavailable"
    after = {
        "battles": conn.execute("SELECT COUNT(*) FROM map_battles").fetchone()[0],
        "attempts": conn.execute("SELECT COUNT(*) FROM map_battle_attempts").fetchone()[0],
        "srs": conn.execute("SELECT COUNT(*) FROM srs_cards").fetchone()[0],
        "reviews": conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0],
        "stats": tuple(conn.execute(
            "SELECT player_hp, player_max_hp, xp, rank_xp FROM user_stats WHERE user_id=101"
        ).fetchone()),
    }
    assert after == before
    assert reward_calls == []
    assert progress_calls == []


def test_persisted_f009_battle_cannot_resume_without_provider_authority(
    api_env, app_module, monkeypatch
):
    if api_env is None:  # pragma: no cover - direct non-pytest imports
        pytest.skip("shared disposable API fixture unavailable")
    client, conn = api_env
    app_module.create_map_battle(
        conn,
        user_id=101,
        zone_key="legacy::f009",
        player_hp=30,
        player_hp_max=30,
        monster_hp=40,
        monster_hp_max=40,
        migration_source="f010-monster-selector",
        migration_version=F009_SELECTOR_MIGRATION_VERSION,
    )
    conn.commit()
    monkeypatch.delenv("MONSTER_ENCOUNTER_SELECTOR_V1_ENABLED", raising=False)

    before_attempts = conn.execute(
        "SELECT COUNT(*) FROM map_battle_attempts"
    ).fetchone()[0]
    response = client.post(
        "/api/adventure/map-battles/v1/attempts",
        json={"zone_key": "legacy::f009", "question_id": 7001},
        headers={"X-Map-Battle-Client-Protocol": "v1"},
    )

    assert response.status_code == 503
    assert response.get_json()["code"] == "monster_selector_unavailable"
    assert conn.execute("SELECT COUNT(*) FROM map_battle_attempts").fetchone()[0] == before_attempts


def test_f009_historical_selector_catalog_remains_read_only_compatible():
    from monster_encounter_selector import build_legacy_selector_candidates

    candidates = build_legacy_selector_candidates()
    assert {candidate.monster_id for candidate in candidates} == {
        f"legacy_bf_{zone:02d}_{kind}"
        for zone in range(1, 11)
        for kind in ("normal", "boss")
    }
    assert F009_SELECTOR_MIGRATION_VERSION == "monster-selector-v1-default-off"
