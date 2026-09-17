"""P0_ZONE4_NEW_ADAPTER_PUBLIC_ROUTE_CORRECTIVE_001.

Root cause this file guards against: ``/js/e10/`` has no generic
``<path:subpath>`` route the way ``/js/e9/`` does. Every ``/js/e10/`` file is an
explicit, governed Flask rule. The Zone4 cinematic content adapter was shipped
into the static release and referenced by index.html, but no rule was ever
added -- so Flask returned 404 at URL routing, before the live-static resolver
was consulted. nginx proxies everything through ``location /``, so there was no
second serving path to cover for it.

The failure mode is specifically *routing*, which is what ``test_client()``
genuinely proves. What ``test_client()`` cannot prove is packaging -- it reads
the host working tree, not the built image (see
``test_e9_runtime_asset_packaging`` for the full three-tier treatment of that
gap). The Dockerfile assertion below is therefore a source-level check, and the
built-image tier remains the responsibility of that existing suite.

This route carries no gameplay, progression, reward, or state authority.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "p0-zone4-route-test-secret")
import app as app_module  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_RELPATH = "js/e10/zone4_cinematic_content.js"
ADAPTER_URL = "/js/e10/zone4_cinematic_content.js"

# The Owner-approved adapter identity for this corrective.
EXPECTED_SHA256 = "50e86317bfbc0105e67ce3bee27b778912371b0abe0d350a004155e9e328999b"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def test_adapter_source_matches_the_owner_approved_identity():
    raw = (REPO_ROOT / ADAPTER_RELPATH).read_bytes()
    assert _sha256(raw) == EXPECTED_SHA256


def test_adapter_url_resolves_and_serves_the_approved_bytes():
    """The actual defect: no Flask rule matched this URL, so it 404'd.

    Fails against the pre-corrective baseline with 404.
    """
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    response = client.get(ADAPTER_URL)

    assert response.status_code == 200, (
        f"{ADAPTER_URL} returned {response.status_code}; "
        "/js/e10/ has no generic route, so this file needs an explicit rule"
    )
    assert _sha256(response.get_data()) == EXPECTED_SHA256


def test_adapter_url_is_a_registered_rule_not_an_accidental_catch_all():
    """Guards against 'fixing' this with a broad catch-all.

    /js/e10/ is a deliberately narrow governed surface. A generic
    <path:subpath> route would silently expose every future file placed in the
    tree, which is a different architectural decision than this corrective.
    """
    rules = {rule.rule for rule in app_module.app.url_map.iter_rules()}
    assert ADAPTER_URL in rules
    assert "/js/e10/<path:subpath>" not in rules


def test_sibling_e10_routes_are_unchanged():
    rules = {rule.rule for rule in app_module.app.url_map.iter_rules()}
    assert "/js/e10/zone4_owner_story_runtime.js" in rules
    assert "/css/e10/zone4_owner_story_runtime.css" in rules
    # The generic e9 surface must keep its existing shape.
    assert "/js/e9/<path:subpath>" in rules


def test_unrouted_e10_sibling_still_404s():
    """The narrow-allowlist property is intact, not widened by this fix."""
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    assert client.get("/js/e10/not_a_real_zone4_file.js").status_code == 404


def test_baked_fallback_is_packaged_in_the_image():
    """live-static serves it normally; the baked copy is the restore path.

    Source-level only -- see this module's docstring on the test_client gap.
    """
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert f"COPY {ADAPTER_RELPATH} ./{ADAPTER_RELPATH}" in dockerfile


def test_index_html_reference_matches_the_served_url():
    """The 404 was player-visible because index.html already loads this file."""
    index = (REPO_ROOT / "index.html").read_text(encoding="utf-8")
    assert ADAPTER_URL in index
