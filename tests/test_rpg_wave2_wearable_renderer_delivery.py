"""Narrow delivery contract for the Wave 2 wearable renderer."""

from pathlib import Path
import os

os.environ.setdefault("SECRET_KEY", "rpg-wave2-wearable-renderer-delivery-test-secret")
import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
RENDERER_PATH = "/js/rpg_wave2_wearable_renderer.js"
RENDERER_SOURCE = ROOT / "js" / "rpg_wave2_wearable_renderer.js"
APP_SOURCE = ROOT / "app.py"
DOCKERFILE = ROOT / "Dockerfile"


def test_renderer_source_is_present_in_the_image_and_narrow_route_is_declared():
    assert RENDERER_SOURCE.is_file()
    app_source = APP_SOURCE.read_text(encoding="utf-8")
    assert "@app.route('/js/rpg_wave2_wearable_renderer.js')" in app_source
    assert "'rpg_wave2_wearable_renderer.js', 'js', 'js'" in app_source
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY js/rpg_wave2_wearable_renderer.js ./js/rpg_wave2_wearable_renderer.js" in dockerfile


def test_direct_renderer_request_returns_the_exact_source_bytes():
    client = app_module.app.test_client()
    response = client.get(f"{RENDERER_PATH}?v=20260820p3")

    assert response.status_code == 200
    assert response.mimetype in {"application/javascript", "text/javascript"}
    assert response.data == RENDERER_SOURCE.read_bytes()
