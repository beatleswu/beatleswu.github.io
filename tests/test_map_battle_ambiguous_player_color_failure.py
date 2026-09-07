"""P1-L3-22 deterministic Map Battle question incompatibility contract."""

from __future__ import annotations

import os
import sys
import types

import pytest


AMBIGUOUS_QUESTION_IDS = [
    31706,
    31707,
    35389,
    46389,
    47474,
    47475,
    47476,
    47477,
    47479,
    47480,
    47481,
    47482,
    47484,
    47485,
    50167,
    50168,
    50169,
    50171,
    50173,
    50178,
    50179,
    74535,
]

AMBIGUOUS_SGF = "(;SZ[19](;B[dd])(;W[ee]))"
NORMAL_SGF = "(;SZ[19];B[dd];W[ee])"
PROTOCOL = {"X-Map-Battle-Client-Protocol": "v1"}


def _install_app_import_stubs():
    """Keep this focused test independent from optional local app modules."""

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
        module.grimoire_bp = Blueprint("grimoire_stub_map_battle_p1_l3_22", __name__)
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
    os.environ["SECRET_KEY"] = "p1-l3-22-map-battle-test-secret"
    _install_app_import_stubs()
    import app as application

    application.app.config["TESTING"] = True
    return application


def test_all_22_ambiguous_records_get_the_same_typed_permanent_failure(app_module, monkeypatch):
    """The fixture IDs exercise generic content classification, not an ID list."""

    def load_questions():
        return [{"id": question_id, "content": AMBIGUOUS_SGF}]

    monkeypatch.setattr(app_module, "_load_questions", load_questions)
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "global")

    # Ambiguous content is rejected before get_db(), so this test also proves
    # there is no battle/attempt/SRS/progression write on the failure path.
    def unexpected_db_access():
        raise AssertionError("ambiguous preparation must not open a DB writer")

    monkeypatch.setattr(app_module, "get_db", unexpected_db_access)
    seen = []
    with app_module.app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 101
        for question_id in AMBIGUOUS_QUESTION_IDS:
            response = client.post(
                "/api/adventure/map-battles/v1/attempts",
                json={"zone_key": "legacy::ambiguous-fixture", "question_id": question_id},
                headers=PROTOCOL,
            )
            assert response.status_code == 409, response.get_json()
            payload = response.get_json()
            assert payload["code"] == "map_battle_question_incompatible"
            assert payload["failure_class"] == "MAP_BATTLE_QUESTION_INCOMPATIBLE"
            assert payload["reason_code"] == "ambiguous_authoritative_sgf_player_color"
            assert payload["retryable"] is False
            assert payload["question_id"] == question_id
            assert payload["question_revision"]
            assert payload["session_question_fingerprint"]
            assert payload["quarantine_scope"] == "session_question_revision"
            assert "attempt_id" not in payload
            assert "battle_id" not in payload
            assert "xp" not in payload
            seen.append(question_id)

    assert seen == AMBIGUOUS_QUESTION_IDS
    assert len(seen) == 22


def test_normal_map_battle_question_still_resolves_first_authoritative_color(app_module):
    context = app_module._map_battle_question_context(
        {"id": 90001, "content": NORMAL_SGF}
    )
    assert context["player_color"] == "B"
    assert context["transform_id"] == "identity"


def test_transient_map_battle_failure_remains_retryable_and_unclassified(app_module):
    from map_battle_runtime import JudgeUnavailable

    with app_module.app.app_context():
        response, status = app_module._map_battle_error_response(
            JudgeUnavailable("runtime temporarily unavailable"),
            question={"id": 90002, "content": NORMAL_SGF},
        )
    payload = response.get_json()
    assert status == 503
    assert payload["retryable"] is True
    assert payload["code"] == "map_battle_judge_unavailable"
    assert "failure_class" not in payload


def test_runtime_does_not_embed_the_22_id_list(app_module):
    from pathlib import Path

    root = Path(app_module.__file__).resolve().parent
    for path in (root / "app.py", root / "index.html", root / "srs.js"):
        source = path.read_text(encoding="utf-8")
        for question_id in AMBIGUOUS_QUESTION_IDS:
            assert str(question_id) not in source, f"hardcoded runtime exclusion: {path} {question_id}"


def test_same_page_adventure_reentry_preserves_session_quarantine(app_module):
    from pathlib import Path

    index_source = (Path(app_module.__file__).resolve().parent / "index.html").read_text(
        encoding="utf-8"
    )
    start = index_source.index("async function enterAdventureZoneInPage")
    end = index_source.index("function adventureActiveZone", start)
    entry_source = index_source[start:end]
    assert "clearSessionQuarantine" not in entry_source
    assert "_pickAdventureTarget(unitQs)" in entry_source
