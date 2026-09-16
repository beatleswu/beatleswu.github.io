"""Production-shaped Flask contract for the V1A Lord controller asset.

The controller is intentionally served through the same narrow Flask static
helper used by the existing E9 subpath routes.  This test keeps the serving
contract at the HTTP boundary: status, MIME type, exact candidate bytes, and
traversal rejection.
"""

import json
import os
import subprocess
import sys
import textwrap
import types
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROLLER = REPO_ROOT / "js" / "game" / "lord_trial_controller.js"
SYNTHETIC_SECRET = "e10-v1a-runtime-serving-test-secret"

# This module may be collected alongside tests that import app.py.  Set the
# process-only synthetic value before this module can import the application.
os.environ["SECRET_KEY"] = SYNTHETIC_SECRET

# NOTE: this module used to call sys.addaudithook(...) here, at module level.
# Audit hooks cannot be removed for the lifetime of the process (CPython/PEP
# 578 - that irreversibility is the whole point of the mechanism), so once
# pytest collected this module the hook stayed armed for every later test in
# the same session - including unrelated tests in other files that
# legitimately touch a temp-directory file that happens to also be named
# secret_key.txt (this hook only matches on basename). Reproduced directly:
# running this module ahead of
# tests/deployment/test_release_build_working_directory.py::
# test_protected_untracked_filename_fails_without_content_read in one pytest
# session made that unrelated test fail with a PermissionError raised from
# THIS module's hook, on a synthetic-repo fixture file in a tmp_path this
# module has no relationship to. Fixed the same way the sibling file
# (test_e10_presentation_dispatcher_static_serving.py) already does it: the
# audit hook only ever gets armed inside an isolated subprocess (see
# _run_protected_runtime_probe below), never in the shared pytest process.


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


def _protected_runtime_probe_source():
    return textwrap.dedent(
        f"""
        import json
        import os
        import sys
        import types

        secret_file_access_attempts = []
        katago_cache_access_attempts = []

        def protected_file_audit_hook(event, args):
            if event == "open":
                try:
                    name = os.path.basename(os.fspath(args[0]))
                except Exception:
                    return
                if str(name).lower() == "secret_key.txt":
                    secret_file_access_attempts.append({{"blocked": True}})
                    raise PermissionError("runtime-serving probe refuses secret_key.txt access")
            elif event == "sqlite3.connect":
                try:
                    name = os.path.basename(os.fspath(args[0]))
                except Exception:
                    return
                if str(name).lower() == "katago_cache.db":
                    katago_cache_access_attempts.append({{"blocked": True}})
                    raise PermissionError("runtime-serving probe refuses katago_cache.db access")

        sys.addaudithook(protected_file_audit_hook)
        os.environ["SECRET_KEY"] = {SYNTHETIC_SECRET!r}

        from flask import Blueprint

        katago_explain = types.ModuleType("katago_explain")
        katago_explain.KataGoExplainer = type("KataGoExplainer", (), {{}})
        explain_overrides = types.ModuleType("explain_overrides")
        explain_overrides.get_override = lambda *args, **kwargs: None
        grimoire_api = types.ModuleType("grimoire_api")
        grimoire_api.grimoire_bp = Blueprint("runtime_serving_probe_grimoire", __name__)
        question_taxonomy = types.ModuleType("question_taxonomy")
        question_taxonomy.get_taxonomy = lambda *args, **kwargs: {{}}
        monster_taxonomy = types.ModuleType("monster_taxonomy")
        monster_taxonomy.get_monster_taxonomy = lambda *args, **kwargs: {{}}
        monster_taxonomy.mark_encounters = lambda *args, **kwargs: None
        chapter_i18n = types.ModuleType("chapter_i18n")
        chapter_i18n.localize_topic = lambda *args, **kwargs: ""
        chapter_i18n.localize_level = lambda *args, **kwargs: ""
        backend_i18n = types.ModuleType("backend_i18n")
        backend_i18n.badge_en = lambda *args, **kwargs: ""
        backend_i18n.skill_node_en = lambda *args, **kwargs: ""
        backend_i18n.title_en = lambda *args, **kwargs: ""

        sys.modules.update({{
            "katago_explain": katago_explain,
            "explain_overrides": explain_overrides,
            "grimoire_api": grimoire_api,
            "question_taxonomy": question_taxonomy,
            "monster_taxonomy": monster_taxonomy,
            "chapter_i18n": chapter_i18n,
            "backend_i18n": backend_i18n,
        }})

        import app as app_module

        app_module.CACHE_DB = ":memory:"
        client = app_module.app.test_client()
        response = client.get("/js/game/lord_trial_controller.js")

        print(json.dumps({{
            "status_code": response.status_code,
            "mimetype": response.mimetype,
            "body_matches_controller_bytes": response.data == open(
                {str(CONTROLLER)!r}, "rb"
            ).read(),
            "secret_file_access_attempts": secret_file_access_attempts,
            "katago_cache_access_attempts": katago_cache_access_attempts,
        }}))
        """
    )


def _run_protected_runtime_probe():
    environment = os.environ.copy()
    environment["SECRET_KEY"] = SYNTHETIC_SECRET
    completed = subprocess.run(
        [sys.executable, "-c", _protected_runtime_probe_source()],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"protected probe failed: stdout={completed.stdout!r} "
        f"stderr={completed.stderr!r}"
    )
    output_lines = [line for line in completed.stdout.splitlines() if line.strip()]
    assert output_lines, f"protected probe produced no output: {completed.stderr!r}"
    return json.loads(output_lines[-1])


def test_protected_runtime_files_remain_unaccessed():
    """Same claim as before (the route never touches secret_key.txt or
    katago_cache.db), proved with an audit hook that only ever lives inside
    its own subprocess rather than the shared pytest process."""
    probe = _run_protected_runtime_probe()

    assert probe["status_code"] == 200
    assert probe["mimetype"] in {"application/javascript", "text/javascript"}
    assert probe["body_matches_controller_bytes"] is True
    assert probe["secret_file_access_attempts"] == []
    assert probe["katago_cache_access_attempts"] == []
