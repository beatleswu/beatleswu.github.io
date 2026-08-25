from __future__ import annotations

from copy import deepcopy

import app as app_module


class _ReadOnlyConnection:
    def __init__(self) -> None:
        self.execute_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

    def execute(self, *_args, **_kwargs):
        self.execute_calls += 1
        raise AssertionError("the route must not execute SQL directly")

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


class _ConnectionContext:
    def __init__(self, connection: _ReadOnlyConnection) -> None:
        self.connection = connection

    def __enter__(self) -> _ReadOnlyConnection:
        return self.connection

    def __exit__(self, *_args) -> bool:
        return False


def _service_result(*, player_id: int = 17) -> dict:
    slots = {
        slot: {
            "slot": slot,
            "item_id": None,
            "owned": False,
            "equipped": False,
            "quantity": 0,
            "functional_status": "NONE",
            "display": None,
        }
        for slot in ("weapon", "armor", "accessory")
    }
    return {
        "contract_version": "PLAYER_PRESENTATION_READ_CONTRACT_V1",
        "status": "OK",
        "player_state": {
            "read_model": "player_hero_state",
            "read_model_version": "player_hero_state_v1",
            "projection_status": "OK",
            "read_only": True,
            "mutates": False,
            "player_id": player_id,
            "hero": {
                "hero_id": "apprentice",
                "identity_status": "PRESENTATION_SELECTION",
                "authority": "player_appearance.character_key",
                "authority_scope": "presentation_only",
                "presentation_fallback_id": "apprentice",
            },
            "progression": {
                "projection_status": "OK",
                "authority": "user_stats",
                "source_version": "existing_user_stats_xp_rank_projection",
                "xp": 120,
                "rank_level": "LV3",
                "level": 3,
                "rank_xp": 20,
                "go_rank": "30k",
                "total_correct": 12,
                "current_streak": 2,
                "max_streak": 4,
            },
            "hp": {
                "projection_status": "OK",
                "authority": "user_stats",
                "scope": "persistent_player_state",
                "persistent_player_hp": 80,
                "persistent_player_max_hp": 100,
                "encounter_hp": {
                    "projected": False,
                    "authority": "encounter_local_battle_state",
                    "reason": "battle context required",
                },
            },
            "equipment": {
                "projection_status": "OK",
                "authority": "player_inventory",
                "slots": slots,
                "owned_items": [],
                "invalid_item_ids": [],
                "equipped_slot_conflicts": [],
                "combat_stats_projected": False,
            },
            "spirit": {
                "projection_status": "OK",
                "authority": "pet_collection_and_user_pets",
                "active": {
                    "spirit_id": "ink_drop_kelpie",
                    "enabled": True,
                    "ownership_validated": True,
                    "evolution_stage": "STAGE_I",
                    "progression_level": 1,
                    "authority": "server_b022_d008_active_spirit_projection",
                },
                "single_active_spirit": True,
                "combat_effects_projected": False,
            },
            "cosmetics": {
                "projection_status": "OK",
                "authority": "player_wardrobe_and_player_appearance",
                "selected": {
                    "outfit": {
                        "item_id": "robe_plain",
                        "presentation_only": True,
                        "combat_power_projected": False,
                    },
                    "hat": None,
                    "back": None,
                    "title": None,
                    "accessory": None,
                    "pet": None,
                    "aura": None,
                },
                "owned_items": [],
                "invalid_item_ids": [],
                "invalid_selected_ids": [],
                "gameplay_effects_projected": False,
            },
            "world": {
                "projected": False,
                "authority": "world_progression_system",
                "selected_zone_is_not_player_progression": True,
            },
            "provenance": {
                "player": {"authority": "users.id"},
                "hero": {"authority": "player_appearance.character_key", "scope": "presentation_only"},
                "progression": {"authority": "user_stats"},
                "hp": {"authority": "user_stats.player_hp/player_max_hp"},
                "equipment": {"authority": "player_inventory"},
                "spirit": {"authority": "pet_collection_and_user_pets"},
                "cosmetics": {"authority": "player_wardrobe_and_player_appearance"},
                "world": {"authority": "world_progression_system", "projected": False},
            },
        },
        "warnings": [],
        "read_only": True,
        "mutates": False,
    }


def _authenticated_client(user_id: int = 17):
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client


def _patch_read_path(monkeypatch, result: dict, *, connection: _ReadOnlyConnection | None = None):
    calls: list[int] = []
    if connection is None:
        connection = _ReadOnlyConnection()

    def build(_conn, *, user_id):
        calls.append(user_id)
        return deepcopy(result)

    monkeypatch.setattr(app_module, "build_player_presentation_state", build)
    monkeypatch.setattr(
        app_module,
        "get_db",
        lambda: _ConnectionContext(connection),
    )
    return calls


def test_unauthenticated_request_is_denied_before_read_service(monkeypatch):
    calls = []
    monkeypatch.setattr(
        app_module,
        "build_player_presentation_state",
        lambda *_args, **_kwargs: calls.append(True),
    )

    response = app_module.app.test_client().get("/api/player/presentation")

    assert response.status_code == 401
    assert calls == []


def test_authenticated_route_uses_session_identity_and_a025_transport(monkeypatch):
    calls = _patch_read_path(monkeypatch, _service_result())
    client = _authenticated_client()

    response = client.get("/api/player/presentation?user_id=999")

    assert response.status_code == 200
    assert calls == [17]
    payload = response.get_json()
    assert payload["contract_version"] == "PLAYER_PRESENTATION_API_V1"
    assert payload["player_id"] == 17
    assert payload["persistent_hp"]["persistent_player_hp"] == 80
    assert payload["persistent_hp"]["persistent_player_max_hp"] == 100
    assert "encounter_hp" not in payload["persistent_hp"]
    assert "total_correct" not in payload["progression"]
    assert "current_streak" not in payload["progression"]
    assert "world" not in payload
    assert "quest" not in payload
    assert "shop" not in payload
    assert "premium" not in payload
    assert payload["spirit"]["combat_effects_projected"] is False
    assert payload["cosmetics"]["selected"]["outfit"]["presentation_only"] is True


def test_route_is_read_only_and_does_not_execute_sql_or_mutate_connection(monkeypatch):
    connection = _ReadOnlyConnection()
    calls = _patch_read_path(monkeypatch, _service_result(), connection=connection)

    response = _authenticated_client().get("/api/player/presentation")

    assert response.status_code == 200
    assert calls == [17]
    assert connection.execute_calls == 0
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0


def test_malformed_equipment_projection_fails_closed(monkeypatch):
    result = _service_result()
    result["player_state"]["equipment"]["slots"]["weapon"]["equipped"] = True
    calls = _patch_read_path(monkeypatch, result)

    response = _authenticated_client().get("/api/player/presentation")

    assert response.status_code == 422
    assert response.get_json()["error"] == "PLAYER_PRESENTATION_CONTRACT_INVALID"
    assert calls == [17]


def test_service_authority_failure_fails_closed_without_second_authority(monkeypatch):
    connection = _ReadOnlyConnection()
    monkeypatch.setattr(
        app_module,
        "get_db",
        lambda: _ConnectionContext(connection),
    )

    def fail_closed(*_args, **_kwargs):
        raise app_module.PlayerPresentationReadServiceError(
            "PLAYER_STATE_INVALID",
            "INVALID_STATE",
            "invalid canonical projection",
        )

    monkeypatch.setattr(app_module, "build_player_presentation_state", fail_closed)

    response = _authenticated_client().get("/api/player/presentation")

    assert response.status_code == 422
    assert response.get_json() == {
        "error": "PLAYER_STATE_INVALID",
        "status": "INVALID_STATE",
    }
