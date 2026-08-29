"""B065: the A041 Hero cache guard must be publicly served by the app."""

import hashlib
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "b065-static-route-test-secret")

import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "js" / "hero_legacy_cache_guard.js"


def test_hero_legacy_cache_guard_public_route_serves_exact_asset_without_auth(
    monkeypatch, tmp_path
):
    source_bytes = ASSET.read_bytes()
    live_static_root = tmp_path / "live-static"
    live_asset = live_static_root / "js" / ASSET.name
    live_asset.parent.mkdir(parents=True)
    live_asset.write_bytes(source_bytes)
    monkeypatch.setenv("GO_ODYSSEY_LIVE_STATIC_ROOT", str(live_static_root))

    app_module.app.config.update(TESTING=True)
    response = app_module.app.test_client().get(
        "/js/hero_legacy_cache_guard.js?v=20260829a0401"
    )

    assert response.status_code == 200
    assert response.content_type.startswith("text/javascript") or response.content_type.startswith(
        "application/javascript"
    )
    assert hashlib.sha256(response.data).hexdigest() == hashlib.sha256(source_bytes).hexdigest()


def test_hero_legacy_cache_guard_route_is_narrow_and_publicly_registered():
    rule = next(
        rule
        for rule in app_module.app.url_map.iter_rules()
        if rule.rule == "/js/hero_legacy_cache_guard.js"
    )
    assert rule.methods == {"GET", "HEAD", "OPTIONS"}
    assert "serve_hero_legacy_cache_guard_js" in rule.endpoint
