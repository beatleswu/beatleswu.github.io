"""Narrow static contract for the future V1B presentation dispatcher asset.

The bridge is intentionally landed before the JavaScript module.  The success
case uses a temporary fixture while the route still delegates to the existing
fixed-subpath helper.  No repository runtime asset is created by this test.
"""

import os
import sys
import types
from pathlib import Path

import pytest
from flask import send_file


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = REPO_ROOT / "js" / "game" / "lord_trial_controller.js"
MAP_ADAPTER = REPO_ROOT / "js" / "map_battle_v1_adapter.js"
SYNTHETIC_SECRET = "e10-v1b-static-bridge-test-secret"
PRESENTATION_BYTES = b"window.__fixturePresentationDispatcher = true;\n"

# Inject a process-only synthetic key before app.py can be imported.  The
# harness never creates or reads secret_key.txt.
os.environ["SECRET_KEY"] = SYNTHETIC_SECRET

SECRET_FILE_ACCESS_ATTEMPTS = []
KATAGO_CACHE_ACCESS_ATTEMPTS = []


def _protected_file_audit_hook(event, args):
    if event == "open":
        try:
            name = os.path.basename(os.fspath(args[0]))
        except Exception:
            return
        if str(name).lower() == "secret_key.txt":
            SECRET_FILE_ACCESS_ATTEMPTS.append({"blocked": True})
            raise PermissionError("static bridge test refuses secret_key.txt access")
    elif event == "sqlite3.connect":
        try:
            name = os.path.basename(os.fspath(args[0]))
        except Exception:
            return
        if str(name).lower() == "katago_cache.db":
            KATAGO_CACHE_ACCESS_ATTEMPTS.append({"blocked": True})
            raise PermissionError("static bridge test refuses katago_cache.db access")


sys.addaudithook(_protected_file_audit_hook)


def _install_app_import_stubs():
    """Stub optional imports unrelated to the static routes under test."""
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
        module.grimoire_bp = Blueprint("static_bridge_grimoire_stub", __name__)
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
    os.environ["SECRET_KEY"] = SYNTHETIC_SECRET
    import app as app_module

    app_module.CACHE_DB = ":memory:"
    return app_module


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


def test_presentation_route_delegates_exact_filename_and_serves_fixture(
    client, app_module, tmp_path, monkeypatch
):
    fixture = tmp_path / "presentation_dispatcher.js"
    fixture.write_bytes(PRESENTATION_BYTES)
    calls = []

    def serve_fixture(subpath, baked_subdir, live_static_subdir):
        calls.append((subpath, baked_subdir, live_static_subdir))
        assert (subpath, baked_subdir, live_static_subdir) == (
            "presentation_dispatcher.js",
            "js/game",
            "js/game",
        )
        return send_file(fixture, mimetype="application/javascript")

    monkeypatch.setattr(app_module, "_serve_live_static_or_baked_subpath", serve_fixture)
    response = client.get("/js/game/presentation_dispatcher.js")

    assert response.status_code == 200
    assert response.headers.get("Location") is None
    assert response.mimetype in {"application/javascript", "text/javascript"}
    assert response.data == PRESENTATION_BYTES
    assert calls == [("presentation_dispatcher.js", "js/game", "js/game")]


def test_presentation_route_is_not_available_until_asset_exists(client):
    response = client.get("/js/game/presentation_dispatcher.js")

    assert response.status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/js/game/presentation_dispatcher.js/../lord_trial_controller.js",
        "/js/game/presentation_dispatcher.js/../../app.py",
        "/js/game/presentation_dispatcher.js/%2e%2e/app.py",
        "/js/game/%2e%2e/presentation_dispatcher.js",
        "/js/game/presentation_dispatcher.css",
        "/js/game/presentation_dispatcher.js/",
    ],
)
def test_presentation_route_rejects_traversal_and_other_assets(client, path):
    response = client.get(path)

    assert response.status_code != 200
    assert response.status_code != 500


def test_query_parameters_cannot_select_another_file(
    client, app_module, tmp_path, monkeypatch
):
    fixture = tmp_path / "presentation_dispatcher.js"
    fixture.write_bytes(PRESENTATION_BYTES)

    def serve_fixture(subpath, baked_subdir, live_static_subdir):
        assert subpath == "presentation_dispatcher.js"
        assert baked_subdir == live_static_subdir == "js/game"
        return send_file(fixture, mimetype="application/javascript")

    monkeypatch.setattr(app_module, "_serve_live_static_or_baked_subpath", serve_fixture)
    response = client.get(
        "/js/game/presentation_dispatcher.js?file=../../app.py&path=../../secret_key.txt"
    )

    assert response.status_code == 200
    assert response.data == PRESENTATION_BYTES


def test_existing_lord_controller_static_route_remains_exact(client):
    response = client.get("/js/game/lord_trial_controller.js")

    assert response.status_code == 200
    assert response.mimetype in {"application/javascript", "text/javascript"}
    assert response.data == CONTROLLER.read_bytes()


def test_existing_map_battle_static_route_remains_exact(client):
    response = client.get("/js/map_battle_v1_adapter.js")

    assert response.status_code == 200
    assert response.mimetype in {"application/javascript", "text/javascript"}
    assert response.data == MAP_ADAPTER.read_bytes()


@pytest.mark.parametrize(
    "path",
    [
        "/js/game/presentation_dispatcher.js?file=../../secret_key.txt",
        "/js/game/presentation_dispatcher.js/../../secret_key.txt",
        "/js/game/../../secret_key.txt",
    ],
)
def test_protected_runtime_files_are_not_served_or_touched(client, path):
    response = client.get(path)

    assert response.status_code != 200
    assert response.status_code != 500
    assert SECRET_FILE_ACCESS_ATTEMPTS == []
    assert KATAGO_CACHE_ACCESS_ATTEMPTS == []


def test_static_bridge_does_not_add_generic_js_game_route(app_module):
    route_rules = {rule.rule for rule in app_module.app.url_map.iter_rules()}

    assert "/js/game/presentation_dispatcher.js" in route_rules
    assert "/js/game/<path:subpath>" not in route_rules
    assert "/js/<path:subpath>" not in route_rules
