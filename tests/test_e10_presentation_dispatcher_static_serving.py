"""Narrow static contract for the future V1B presentation dispatcher asset.

The bridge is intentionally landed before the JavaScript module.  The success
case uses a temporary fixture while the route still delegates to the existing
fixed-subpath helper.  No repository runtime asset is created by this test.

Protected-file probing runs in a subprocess so its audit hook cannot become a
permanent hook in the pytest process.  The absent-asset check is explicitly a
transitional baseline characterization; once the real asset lands, the same
test asserts the exact asset bytes instead.
"""

import builtins
import json
import os
import sqlite3
import subprocess
import sys
import textwrap
import types
from contextlib import contextmanager
from pathlib import Path

import pytest
from flask import send_file


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = REPO_ROOT / "js" / "game" / "lord_trial_controller.js"
MAP_ADAPTER = REPO_ROOT / "js" / "map_battle_v1_adapter.js"
PRESENTATION_ASSET = REPO_ROOT / "js" / "game" / "presentation_dispatcher.js"
SYNTHETIC_SECRET = "e10-v1b-static-bridge-test-secret"
PRESENTATION_BYTES = b"window.__fixturePresentationDispatcher = true;\n"
PROTECTED_PATHS = (
    "/js/game/presentation_dispatcher.js/../../secret_key.txt",
    "/js/game/../../secret_key.txt",
)
IMPORT_STUB_NAMES = (
    "katago_explain",
    "explain_overrides",
    "grimoire_api",
    "question_taxonomy",
    "monster_taxonomy",
    "chapter_i18n",
    "backend_i18n",
)
_MISSING = object()


def _build_app_import_stubs():
    """Build optional-import stubs without mutating ``sys.modules``."""
    from flask import Blueprint

    katago_explain = types.ModuleType("katago_explain")
    katago_explain.KataGoExplainer = type("KataGoExplainer", (), {})

    explain_overrides = types.ModuleType("explain_overrides")
    explain_overrides.get_override = lambda *args, **kwargs: None

    grimoire_api = types.ModuleType("grimoire_api")
    grimoire_api.grimoire_bp = Blueprint("static_bridge_grimoire_stub", __name__)

    question_taxonomy = types.ModuleType("question_taxonomy")
    question_taxonomy.get_taxonomy = lambda *args, **kwargs: {}

    monster_taxonomy = types.ModuleType("monster_taxonomy")
    monster_taxonomy.get_monster_taxonomy = lambda *args, **kwargs: {}
    monster_taxonomy.mark_encounters = lambda *args, **kwargs: None

    chapter_i18n = types.ModuleType("chapter_i18n")
    chapter_i18n.localize_topic = lambda *args, **kwargs: ""
    chapter_i18n.localize_level = lambda *args, **kwargs: ""

    backend_i18n = types.ModuleType("backend_i18n")
    backend_i18n.badge_en = lambda *args, **kwargs: ""
    backend_i18n.skill_node_en = lambda *args, **kwargs: ""
    backend_i18n.title_en = lambda *args, **kwargs: ""

    return {
        "katago_explain": katago_explain,
        "explain_overrides": explain_overrides,
        "grimoire_api": grimoire_api,
        "question_taxonomy": question_taxonomy,
        "monster_taxonomy": monster_taxonomy,
        "chapter_i18n": chapter_i18n,
        "backend_i18n": backend_i18n,
    }


@contextmanager
def _temporary_app_import_stubs():
    """Install optional-import stubs and restore every prior module entry."""
    originals = {
        name: sys.modules.get(name, _MISSING) for name in IMPORT_STUB_NAMES
    }
    try:
        sys.modules.update(_build_app_import_stubs())
        yield
    finally:
        for name, original in originals.items():
            if original is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.fixture(scope="module")
def app_module(request):
    patcher = pytest.MonkeyPatch()
    patcher.setenv("SECRET_KEY", SYNTHETIC_SECRET)
    request.addfinalizer(patcher.undo)

    if "app" in sys.modules:
        app_module = sys.modules["app"]
    else:
        with _temporary_app_import_stubs():
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


def test_presentation_route_is_exact_asset_or_transitional_404_before_asset_lands(
    client,
):
    response = client.get("/js/game/presentation_dispatcher.js")

    if PRESENTATION_ASSET.is_file():
        assert response.status_code == 200
        assert response.data == PRESENTATION_ASSET.read_bytes()
    else:
        # B0 baseline only: the future asset has not landed in this branch yet.
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
    secret_file_access_attempts = []
    katago_cache_access_attempts = []

    real_open = builtins.open

    def guarded_open(file, *args, **kwargs):
        try:
            name = os.path.basename(os.fspath(file))
        except Exception:
            name = ""
        if str(name).lower() == "secret_key.txt":
            secret_file_access_attempts.append(str(name))
            raise AssertionError("static bridge test refuses secret_key.txt access")
        return real_open(file, *args, **kwargs)

    real_connect = sqlite3.connect

    def guarded_connect(database, *args, **kwargs):
        try:
            name = os.path.basename(os.fspath(database))
        except Exception:
            name = ""
        if str(name).lower() == "katago_cache.db":
            katago_cache_access_attempts.append(str(name))
            raise AssertionError("static bridge test refuses katago_cache.db access")
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(sqlite3, "connect", guarded_connect)

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
    assert secret_file_access_attempts == []
    assert katago_cache_access_attempts == []


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


def _protected_runtime_probe_source():
    protected_paths = json.dumps(PROTECTED_PATHS)
    return textwrap.dedent(
        f"""
        import json
        import os
        import sys
        import types

        PROTECTED_PATHS = {protected_paths}
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
                    raise PermissionError("probe refuses secret_key.txt access")
            elif event == "sqlite3.connect":
                try:
                    name = os.path.basename(os.fspath(args[0]))
                except Exception:
                    return
                if str(name).lower() == "katago_cache.db":
                    katago_cache_access_attempts.append({{"blocked": True}})
                    raise PermissionError("probe refuses katago_cache.db access")

        sys.addaudithook(protected_file_audit_hook)
        os.environ["SECRET_KEY"] = {SYNTHETIC_SECRET!r}

        from flask import Blueprint

        katago_explain = types.ModuleType("katago_explain")
        katago_explain.KataGoExplainer = type("KataGoExplainer", (), {{}})
        explain_overrides = types.ModuleType("explain_overrides")
        explain_overrides.get_override = lambda *args, **kwargs: None
        grimoire_api = types.ModuleType("grimoire_api")
        grimoire_api.grimoire_bp = Blueprint("static_bridge_probe_grimoire", __name__)
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
        statuses = {{}}
        errors = []
        for path in PROTECTED_PATHS:
            try:
                statuses[path] = client.get(path).status_code
            except Exception as exc:
                errors.append(f"{{path}}: {{type(exc).__name__}}")
                statuses[path] = None

        print(json.dumps({{
            "statuses": statuses,
            "errors": errors,
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
    output_lines = [
        line for line in completed.stdout.splitlines() if line.strip()
    ]
    assert output_lines, f"protected probe produced no output: {completed.stderr!r}"
    return json.loads(output_lines[-1])


def test_protected_runtime_files_are_not_served_or_touched():
    probe = _run_protected_runtime_probe()

    assert probe["errors"] == []
    assert all(
        probe["statuses"][path] not in {200, 500} for path in PROTECTED_PATHS
    )
    assert probe["secret_file_access_attempts"] == []
    assert probe["katago_cache_access_attempts"] == []


def test_temporary_import_stubs_are_restored_after_context():
    originals = {
        name: sys.modules.get(name, _MISSING) for name in IMPORT_STUB_NAMES
    }

    with _temporary_app_import_stubs():
        assert all(name in sys.modules for name in IMPORT_STUB_NAMES)

    for name, original in originals.items():
        if original is _MISSING:
            assert name not in sys.modules
        else:
            assert sys.modules[name] is original


def test_static_bridge_does_not_add_generic_js_game_route(app_module):
    route_rules = {rule.rule for rule in app_module.app.url_map.iter_rules()}

    assert "/js/game/presentation_dispatcher.js" in route_rules
    assert "/js/game/<path:subpath>" not in route_rules
    assert "/js/<path:subpath>" not in route_rules
