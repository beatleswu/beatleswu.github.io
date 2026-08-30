"""Focused public-route contract for the A040 Hero cache guard asset."""

import hashlib
import os
from pathlib import Path

import pytest


os.environ["SECRET_KEY"] = "d044-r2-focused-hero-route-test-secret"

import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "js" / "hero_legacy_cache_guard.js"
PUBLIC_URL = "/js/hero_legacy_cache_guard.js?v=20260829a0401"
PUBLIC_PATH = "/js/hero_legacy_cache_guard.js"


@pytest.fixture()
def client():
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_exact_public_route_serves_canonical_asset_without_auth(client):
    source_bytes = ASSET.read_bytes()
    response = client.get(PUBLIC_URL)

    assert response.status_code == 200
    assert response.mimetype in {"text/javascript", "application/javascript"}
    assert hashlib.sha256(response.data).hexdigest() == hashlib.sha256(source_bytes).hexdigest()


def test_route_uses_fixed_governed_asset_and_does_not_touch_db_or_session(
    client, monkeypatch
):
    calls = []
    real_helper = app_module._serve_live_static_or_baked_subpath

    def capture_helper(*args, **kwargs):
        calls.append((args, kwargs))
        return real_helper(*args, **kwargs)

    def fail_if_db_accessed(*_args, **_kwargs):
        raise AssertionError("Hero static route must not access the database")

    monkeypatch.setattr(app_module, "_serve_live_static_or_baked_subpath", capture_helper)
    monkeypatch.setattr(app_module, "get_db", fail_if_db_accessed)

    with client.session_transaction() as session:
        session["d044_route_probe"] = "unchanged"

    response = client.get(PUBLIC_URL)

    assert response.status_code == 200
    assert calls == [
        (("hero_legacy_cache_guard.js", "js", "js"), {})
    ]
    with client.session_transaction() as session:
        assert session.get("d044_route_probe") == "unchanged"


def test_route_is_exact_and_does_not_expose_sibling_or_traversal_paths(client):
    rule = next(
        rule
        for rule in app_module.app.url_map.iter_rules()
        if rule.rule == PUBLIC_PATH
    )
    assert rule.methods == {"GET", "HEAD", "OPTIONS"}

    for path in (
        "/js/unknown-hero-guard.js",
        "/js/hero_legacy_cache_guard.js/extra",
        "/js/hero_legacy_cache_guard.js/../app.py",
    ):
        response = client.get(path)
        assert response.status_code != 200
        assert response.status_code != 500


def test_index_and_release_manifests_keep_the_existing_guard_reference():
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    build_manifest = (ROOT / "deploy" / "build-manifest.json").read_text(encoding="utf-8")
    inventory = (ROOT / "deploy" / "live-static-asset-inventory.json").read_text(
        encoding="utf-8"
    )
    provenance = (ROOT / "deploy" / "runtime-source-provenance.json").read_text(
        encoding="utf-8"
    )

    assert PUBLIC_URL in index
    assert "js/hero_legacy_cache_guard.js" in build_manifest
    assert "js/hero_legacy_cache_guard.js" in inventory
    assert "js/hero_legacy_cache_guard.js" in provenance
