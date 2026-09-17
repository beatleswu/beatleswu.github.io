"""P0_ZONE4_NEW_ADAPTER_PUBLIC_ROUTE_CORRECTIVE_001 (+R2).

Root cause this file guards against: the ``/js/e10/`` and ``/css/e10/`` prefixes
have no generic ``<path:subpath>`` route the way ``/js/e9/`` and ``/css/e9/`` do.
Every E10 file is an explicit, governed Flask rule. nginx has no ``/js`` or
``/css`` location -- everything proxies through ``location /`` to Flask -- so
when a file is added to the tree and referenced by index.html but never given a
rule, Flask 404s at URL routing and there is no second serving path to cover it.

Three files were in exactly that state in Production:

* ``js/e10/zone4_cinematic_content.js`` -- already staged into live-static with
  the approved hash and already in the live-static inventory. Route missing only.
* ``css/e10/encounter_presentation_framework_v1.css``
* ``css/e10/go_combat_owner_reference_v1.css``

The two stylesheets share the routing defect but have a strictly broader gap:
they are absent from the live-static inventory, absent from live-static, and
absent from the baked image. For them the Dockerfile copy is the *only* serving
source, not a fallback -- which is why both a route and a baked copy are
required, and why a route alone would not have fixed them.

The failure mode is *routing*, which ``test_client()`` genuinely proves. What
``test_client()`` cannot prove is packaging -- it reads the host working tree,
not the built image (see ``test_e9_runtime_asset_packaging`` for the full
three-tier treatment of that gap). The Dockerfile assertions below are
therefore source-level checks.

None of these routes carry gameplay, progression, reward, or state authority.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "p0-zone4-route-test-secret")
import app as app_module  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

# The exact authorized public route set for this corrective -- three URLs, no
# more. Each entry is (url, repo-relative path, Owner-approved sha256).
AUTHORIZED_ROUTES = [
    (
        "/js/e10/zone4_cinematic_content.js",
        "js/e10/zone4_cinematic_content.js",
        "50e86317bfbc0105e67ce3bee27b778912371b0abe0d350a004155e9e328999b",
    ),
    (
        "/css/e10/encounter_presentation_framework_v1.css",
        "css/e10/encounter_presentation_framework_v1.css",
        "80e9acdb2977b1e624336456452193f8f86ae1ce4e1ff0609add7c01e609f1ad",
    ),
    (
        "/css/e10/go_combat_owner_reference_v1.css",
        "css/e10/go_combat_owner_reference_v1.css",
        "8ce6ca68de39d3e175c7382bf6b71c9e04bc2bda9a8de8ceead88ab23e8debbe",
    ),
]

IDS = [relpath for _url, relpath, _sha in AUTHORIZED_ROUTES]


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _client():
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


@pytest.mark.parametrize("url,relpath,expected_sha", AUTHORIZED_ROUTES, ids=IDS)
def test_source_matches_the_owner_approved_identity(url, relpath, expected_sha):
    assert _sha256((REPO_ROOT / relpath).read_bytes()) == expected_sha


@pytest.mark.parametrize("url,relpath,expected_sha", AUTHORIZED_ROUTES, ids=IDS)
def test_url_resolves_and_serves_the_approved_bytes(url, relpath, expected_sha):
    """The actual defect: no Flask rule matched these URLs, so they 404'd.

    Fails against the pre-corrective baseline with 404 for all three.
    """
    response = _client().get(url)
    assert response.status_code == 200, (
        f"{url} returned {response.status_code}; the E10 prefixes have no "
        "generic route, so each file needs an explicit rule"
    )
    assert _sha256(response.get_data()) == expected_sha


@pytest.mark.parametrize("url,relpath,expected_sha", AUTHORIZED_ROUTES, ids=IDS)
def test_url_is_a_registered_rule_not_an_accidental_catch_all(url, relpath, expected_sha):
    assert url in {rule.rule for rule in app_module.app.url_map.iter_rules()}


def test_no_generic_e10_catchall_was_introduced():
    """Guards against 'fixing' this by widening the governed surface.

    /js/e10/ and /css/e10/ are deliberately narrow explicit-route surfaces. A
    generic <path:subpath> route would silently expose every future file placed
    in either tree, which is a different architectural decision than this
    corrective.
    """
    rules = {rule.rule for rule in app_module.app.url_map.iter_rules()}
    assert "/js/e10/<path:subpath>" not in rules
    assert "/css/e10/<path:subpath>" not in rules


def test_public_route_set_is_exactly_the_three_authorized_additions():
    """No route expansion beyond the authorized set."""
    rules = {rule.rule for rule in app_module.app.url_map.iter_rules()}
    e10_rules = {r for r in rules if r.startswith(("/js/e10/", "/css/e10/"))}
    assert e10_rules == {
        # pre-existing, untouched
        "/js/e10/zone4_owner_story_runtime.js",
        "/css/e10/zone4_owner_story_runtime.css",
        # the three added by this corrective
        "/js/e10/zone4_cinematic_content.js",
        "/css/e10/encounter_presentation_framework_v1.css",
        "/css/e10/go_combat_owner_reference_v1.css",
    }


def test_sibling_and_generic_e9_surfaces_are_unchanged():
    rules = {rule.rule for rule in app_module.app.url_map.iter_rules()}
    assert "/js/e10/zone4_owner_story_runtime.js" in rules
    assert "/css/e10/zone4_owner_story_runtime.css" in rules
    assert "/js/e9/<path:subpath>" in rules
    assert "/css/e9/<path:subpath>" in rules


def test_unrouted_e10_siblings_still_404():
    """The narrow-allowlist property is intact, not widened by this fix."""
    client = _client()
    assert client.get("/js/e10/not_a_real_zone4_file.js").status_code == 404
    assert client.get("/css/e10/not_a_real_stylesheet.css").status_code == 404
    # backpack.css is in the tree but unreferenced by index.html and was NOT
    # authorized for routing; it must stay unrouted.
    assert client.get("/css/e10/backpack.css").status_code == 404


@pytest.mark.parametrize("url,relpath,expected_sha", AUTHORIZED_ROUTES, ids=IDS)
def test_baked_copy_is_packaged_in_the_image(url, relpath, expected_sha):
    """For the two stylesheets this is the ONLY serving source.

    Neither is in the live-static inventory, so unlike the JS adapter they
    cannot be served from a static release at all. Source-level check only --
    see this module's docstring on the test_client packaging gap.
    """
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert f"COPY {relpath} ./{relpath}" in dockerfile


@pytest.mark.parametrize("url,relpath,expected_sha", AUTHORIZED_ROUTES, ids=IDS)
def test_index_html_reference_matches_the_served_url(url, relpath, expected_sha):
    """All three 404s were player-visible: index.html already loads each one."""
    index = (REPO_ROOT / "index.html").read_text(encoding="utf-8")
    assert url in index
