"""Production-shaped Flask contract for the V1A Lord controller asset.

The controller is intentionally served through the same narrow Flask static
helper used by the existing E9 subpath routes.  This test keeps the serving
contract at the HTTP boundary: status, MIME type, exact candidate bytes, and
traversal rejection.
"""

import os
import sys
import types
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROLLER = REPO_ROOT / "js" / "game" / "lord_trial_controller.js"
SYNTHETIC_SECRET = "e10-v1a-runtime-serving-test-secret"

# This module may be collected alongside tests that import app.py.  Set the
# process-only synthetic value before this module can import the application.
os.environ["SECRET_KEY"] = SYNTHETIC_SECRET
sys.path.insert(0, str(REPO_ROOT / "tests"))
import lord_trial_natural_runtime as runtime_hygiene  # noqa: E402

runtime_hygiene.install_secret_hygiene()


def _install_app_import_stubs():
    """Stub unrelated optional imports; the tested routes need none of them."""
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
        module.grimoire_bp = Blueprint("runtime_serving_grimoire_stub", __name__)
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


def test_controller_route_returns_exact_candidate_bytes_without_auth(client):
    response = client.get("/js/game/lord_trial_controller.js")

    assert response.status_code == 200
    assert response.headers.get("Location") is None
    assert response.mimetype in {"application/javascript", "text/javascript"}
    assert response.data == CONTROLLER.read_bytes()
    assert b"LordTrialController" in response.data


@pytest.mark.parametrize(
    "path",
    [
        "/srs.js",
        "/i18n.js",
        "/js/e9/feature_flags.js",
        "/css/e9/shell.css",
        "/components/adventure/top_hud.html",
    ],
)
def test_existing_static_routes_remain_reachable(client, path):
    response = client.get(path)

    assert response.status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/js/game/../app.py",
        "/js/game/../../secret_key.txt",
        "/js/game/%2e%2e/app.py",
        "/js/game/lord_trial_controller.css",
        "/js/game/missing.js",
    ],
)
def test_controller_route_rejects_traversal_and_other_assets(client, path):
    response = client.get(path)

    assert response.status_code != 200
    assert response.status_code != 500
