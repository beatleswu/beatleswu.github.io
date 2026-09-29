"""Exact public static exposure for the already-packaged Formal9 runtime."""

import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin

import app as app_module


ROOT = Path(__file__).resolve().parents[2]
JS_FILES = (
    "formal_3d_character_equipment_runtime.js",
    "player_character_3d_runtime_bridge.js",
    "player_appearance_3d_attachment_adapter.js",
    "g009_d007_runtime_identity_resolver.mjs",
    "g009_formal9_rights_cleared_replacement_catalog.js",
    "g009_owner_approved_formal_equipment_mapping.js",
    "g009_d_r2_shared_host_bootstrap.js",
    "g009_equipment_inventory_projection.js",
    "hero_equipment_attachment_adapter.js",
    "g009_d007_shared_host_bootstrap.js",
    "g009_d007_shared_host_adapter.js",
    "g009_shared_hero_attachment_host.js",
)
SCHEMAS = (
    "g009_d007_runtime_prerequisite_v1.json",
    "g009_formal9_rights_cleared_replacement_v1.json",
    "future30_c005_real_asset_runtime_mapping_manifest.json",
)
ASSET_PATHS = (
    "assets/3d_shop/p048/runtime_manifest.json",
    "assets/3d_shop/p048/vendor/three.module.js",
    "assets/3d_shop/p048/vendor/jsm/loaders/GLTFLoader.js",
    "assets/3d_shop/p048/vendor/jsm/utils/BufferGeometryUtils.js",
    "assets/3d_shop/formal9_rights_cleared_v1/weapons/weapon_c43e15596ca6.glb",
    "assets/3d_shop/formal9_rights_cleared_v1/weapons/weapon_6f06505a7bed.glb",
    "assets/3d_shop/formal9_rights_cleared_v1/weapons/weapon_ec86ce30e759.glb",
    "assets/3d_shop/formal9_rights_cleared_v1/weapons/weapon_c84a8635bed2.glb",
)


def test_exact_formal_runtime_urls_serve_packaged_source_bytes():
    client = app_module.app.test_client()
    prerequisite = json.loads((ROOT / "schemas/g009_d007_runtime_prerequisite_v1.json").read_text(encoding="utf-8"))
    head_back = [url.lstrip("/") for slot in ("HEAD", "BACK")
                 for url in prerequisite["appearance_catalog"]["slots"][slot].values()]
    retired = {row["old_runtime_asset"].lstrip("/") for row in json.loads(
        (ROOT / "provenance/g009_formal9_rights_cleared_v1/old_asset_retirement_map.json").read_text(encoding="utf-8")
    )["retired"]}
    admitted_preview = [row["runtime_asset"].lstrip("/") for row in prerequisite["equipment_catalog"]["items"]
                        if row["runtime_asset"].lstrip("/") not in retired]
    for relative in (
        *("js/" + filename for filename in JS_FILES),
        "js/g008_future30_hero_renderer.js",
        *("schemas/" + filename for filename in SCHEMAS),
        *ASSET_PATHS,
        *head_back,
        *admitted_preview,
    ):
        response = client.get("/" + relative)
        assert response.status_code == 200, relative
        assert hashlib.sha256(response.data).digest() == hashlib.sha256((ROOT / relative).read_bytes()).digest(), relative
        if relative.endswith((".js", ".mjs")):
            assert "javascript" in response.content_type, relative
        if relative.endswith(".json"):
            assert "json" in response.content_type, relative


def test_exact_routes_are_registered_in_static_inventory():
    inventory = json.loads((ROOT / "deploy/live-static-asset-inventory.json").read_text(encoding="utf-8"))
    eligible = set(inventory["eligible_files"]["entries"])
    assert {"js/" + filename for filename in JS_FILES} <= eligible
    assert "js/g008_future30_hero_renderer.js" in eligible
    assert {"schemas/" + filename for filename in SCHEMAS} <= eligible


def test_formal_js_import_chain_is_http_reachable():
    client = app_module.app.test_client()
    assert '"three":"/assets/3d_shop/p048/vendor/three.module.js"' in (
        ROOT / "hero.html"
    ).read_text(encoding="utf-8")
    for filename in (*JS_FILES, "g008_future30_hero_renderer.js"):
        module_url = "/js/" + filename
        source = (ROOT / "js" / filename).read_text(encoding="utf-8")
        for specifier in re.findall(r'\bfrom\s+["\']([^"\']+)["\']', source):
            if specifier == "three":
                continue
            dependency_url = urljoin(module_url, specifier)
            assert client.get(dependency_url).status_code == 200, (module_url, dependency_url)


def test_formal_static_exposure_fails_closed_outside_allowlist():
    client = app_module.app.test_client()
    for url in (
        "/js/not-a-formal-runtime.js",
        "/js/app.py",
        "/js/.env",
        "/js/%2e%2e",
        "/schemas/not-a-formal-schema.json",
        "/schemas/.env",
        "/schemas/%2e%2e",
    ):
        assert client.get(url).status_code == 404, url
