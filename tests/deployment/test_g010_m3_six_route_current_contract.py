"""G010 M3 independent current-state acceptance for Owner-approved sixth E10 route.

This is separate from the immutable G009 Frozen snapshot. It cannot
authorize builds, rewrite the 2026-10-16 Owner policy, or mark known
historical contract conflicts as PASS.
"""
import hashlib
import os
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "g010-isolated-six-route-test-secret")
import app as app_module  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BACKPACK_URL = "/css/e10/backpack.css"
BACKPACK_SHA = "a7bb0e14a24f8845c79f4850c36f37f7c69c49452d3699a93bbbfdd2fe93c888"
EXACT_E10_ROUTES = {
    "/js/e10/zone4_owner_story_runtime.js",
    "/css/e10/zone4_owner_story_runtime.css",
    "/js/e10/zone4_cinematic_content.js",
    "/css/e10/encounter_presentation_framework_v1.css",
    "/css/e10/go_combat_owner_reference_v1.css",
    BACKPACK_URL,
}


def test_six_explicit_routes_only_no_generic_exposure():
    rules = {rule.rule for rule in app_module.app.url_map.iter_rules()}
    assert {r for r in rules if r.startswith(("/js/e10/", "/css/e10/"))} == EXACT_E10_ROUTES
    assert "/js/e10/<path:subpath>" not in rules
    assert "/css/e10/<path:subpath>" not in rules


def test_backpack_css_served_with_exact_owner_approved_bytes():
    expected = (ROOT / "css" / "e10" / "backpack.css").read_bytes()
    assert hashlib.sha256(expected).hexdigest() == BACKPACK_SHA
    with app_module.app.test_client() as client:
        response = client.get(BACKPACK_URL)
        assert response.status_code == 200
        assert response.mimetype == "text/css"
        assert response.get_data() == expected


def test_unlisted_e10_siblings_do_not_route():
    with app_module.app.test_client() as client:
        assert client.get("/css/e10/not_a_real_stylesheet.css").status_code == 404
        assert client.get("/js/e10/not_a_real_zone4_file.js").status_code == 404


def test_backpack_css_disallows_post_and_has_exact_baked_copy():
    with app_module.app.test_client() as client:
        assert client.post(BACKPACK_URL).status_code == 405
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY css/e10/backpack.css ./css/e10/backpack.css" in docker
    assert "COPY css/e10/ ./css/e10/" not in docker
