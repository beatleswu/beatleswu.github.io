"""D035 route-boundary proof for the final Adventure Spirit integration."""

from __future__ import annotations

from pathlib import Path
import sys
import types

import pytest


def _install_app_import_stubs():
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
        module.grimoire_bp = Blueprint("grimoire_stub_d035", __name__)
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

    return module


class _EmptyResult:
    def fetchone(self):
        return None


class _DbContext:
    def execute(self, _sql, _params=None):
        return _EmptyResult()

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False


@pytest.fixture()
def client(app_module, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext())
    monkeypatch.setattr(app_module, "_adventure_state", lambda _uid: [{
        "key": "k11_15",
        "seen": 50,
        "unlocked": True,
        "cleared": False,
    }])
    monkeypatch.setattr(
        app_module,
        "_adventure_map_state",
        lambda *args, **kwargs: {"existing_map_field": "preserved"},
    )
    monkeypatch.setattr(app_module, "_clear_adventure_state_cache", lambda _uid: None)
    app_module.app.config["TESTING"] = True
    app_module.app.config["PROPAGATE_EXCEPTIONS"] = True
    return app_module.app.test_client()


MILESTONES = (
    ("k11_15", 4, "starpath_antlerling"),
    ("k1_5", 6, "fatty"),
    ("d3_4", 8, "obsidian_bastion"),
)
USER_ID = 43102


def _raw_result(zone_index: int, status: str = "UNLOCKED"):
    zone_key, zone_number, spirit_id = MILESTONES[zone_index]
    eligible = status != "NOT_ELIGIBLE"
    replayed = status == "REPLAY"
    mutation_count = 1 if status == "UNLOCKED" else 0
    result = {
        "user_id": USER_ID,
        "zone_key": zone_key,
        "zone_number": zone_number,
        "spirit_id": spirit_id,
        "operation_id": f"adventure:spirit_unlock:{USER_ID}:{zone_key}",
        "source_authority": "ADVENTURE_ZONE_MILESTONE",
        "source_fact": "adventure_boss_progress.cleared=1",
        "source_reference": f"adventure_boss_progress:{USER_ID}:{zone_key}",
        "cleared": eligible,
        "eligible": eligible,
        "operation_type": "SPIRIT_UNLOCK",
        "ownership_store": "pet_collection",
        "compensation_count": 0,
        "replacement_count": 0,
        "client_completion_authority": False,
        "status": status,
        "replayed": replayed,
        "ownership_mutation_count": mutation_count,
        "new_unlock_count": mutation_count,
    }
    if eligible:
        result["operation_status"] = "COMPLETED"
    return result


def _login(client):
    with client.session_transaction() as session:
        session["user_id"] = USER_ID
        session["adventure_boss_exam"] = {
            "zone_key": "k11_15",
            "attempt_id": "d035-route-boundary",
        }


def _patch_common_route(app_module, monkeypatch, result=None, passed=True):
    monkeypatch.setattr(
        app_module,
        "_adventure_boss_authoritative_result",
        lambda _conn, _uid, _exam: (1, 1) if passed else (0, 1),
    )
    monkeypatch.setattr(
        app_module,
        "_adventure_boss_record_attempt",
        lambda *_args, **_kwargs: {
            "operation_id": f"adventure:first_clear:{USER_ID}:k11_15",
            "is_replay": False,
            "is_first_clear": False,
        },
    )
    monkeypatch.setattr(app_module, "_grant_coins", lambda *args, **kwargs: 0)
    if result is not None:
        monkeypatch.setattr(
            app_module,
            "_apply_adventure_spirit_milestone_catch_up",
            lambda _conn, _uid: [result],
        )


def test_failed_boss_attempt_returns_neutral_spirit_list_and_preserves_response(
    app_module, client, monkeypatch
):
    _patch_common_route(app_module, monkeypatch, passed=False)

    def unexpected_unlock_call(*_args, **_kwargs):
        pytest.fail("failed boss attempt must not invoke D030 catch-up")

    monkeypatch.setattr(
        app_module,
        "_apply_adventure_spirit_milestone_catch_up",
        unexpected_unlock_call,
    )
    _login(client)

    response = client.post("/api/adventure/boss/finish", json={})

    assert response.status_code == 200
    body = response.get_json()
    assert body["passed"] is False
    assert body["adventure_spirit_unlock_results"] == []
    assert body["existing_map_field"] == "preserved"
    assert body["reward"]["contract_version"] == "F028_BATTLEFIELD_BOSS_MAPPING_A_FIRST_CLEAR_V1"
    assert body["reward"]["status"] == "NO_REWARD"
    assert body["reward"]["coins"] == 0
    assert body["reward"]["first_clear"] is False
    assert body["reward"]["reward_item"] is None


@pytest.mark.parametrize(
    ("zone_index", "status", "result_state"),
    ((0, "UNLOCKED", "UNLOCKED"), (1, "NO_OP", "NO_OP"), (2, "NOT_ELIGIBLE", "NOT_ELIGIBLE")),
)
def test_passed_route_transports_server_result_as_historical_and_additive(
    app_module, client, monkeypatch, zone_index, status, result_state
):
    _patch_common_route(app_module, monkeypatch, _raw_result(zone_index, status))
    _login(client)

    response = client.post("/api/adventure/boss/finish", json={
        "zone_key": "forged-client-zone",
        "spirit_id": "ink_drop_kelpie",
    })

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["passed"] is True
    assert body["existing_map_field"] == "preserved"
    assert body["reward"]["contract_version"] == "F028_BATTLEFIELD_BOSS_MAPPING_A_FIRST_CLEAR_V1"
    assert body["reward"]["status"] == "NO_REWARD"
    assert body["reward"]["coins"] == 0
    assert body["reward"]["first_clear"] is False
    assert body["reward"]["reward_item"] is None
    assert len(body["adventure_spirit_unlock_results"]) == 1
    item = body["adventure_spirit_unlock_results"][0]
    assert item["result_state"] == result_state
    assert item["historical_catchup"] is True
    assert item["client_completion_authority"] is False
    assert item["spirit_id"] == MILESTONES[zone_index][2]


def test_route_wiring_has_no_new_spirit_business_logic(app_module):
    source = Path(app_module.__file__).read_text(encoding="utf-8")
    start = source.index("def adventure_boss_finish():")
    end = source.index("\n#", start)
    route = source[start:end]

    assert "build_adventure_spirit_unlock_results" in route
    assert "compose_adventure_boss_finish_response" in route
    assert "_apply_adventure_spirit_milestone_catch_up" in route
    assert "resolve_milestone_for_zone" not in route
    assert "_mutate_spirit_unlock" not in route
    assert "pet_collection" not in route
