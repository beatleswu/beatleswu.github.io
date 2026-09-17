"""Prove the Owner-final Zone 4 review runtime is release-packaged exactly.

This is a packaging boundary test only. It does not grant gameplay, reward,
progression, or canonical-state authority to the review preview.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "deploy/live-static-asset-inventory.json"
ZONE4_PACK = ROOT / "deploy/canonical-e10-zone4-static-pack-manifest.json"
PARITY = ROOT / "ZONE4_005_OWNER_APPROVED_HASH_PARITY.json"
APP = ROOT / "app.py"
DOCKERFILE = ROOT / "Dockerfile"
PAGE = ROOT / "zone4_owner_story_runtime.html"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_zone4_static_pack_is_exact_owner_approved_parity():
    parity = _json(PARITY)
    pack = _json(ZONE4_PACK)

    expected = {
        record["path"]: {
            "size": record["byte_size"],
            "sha256": record["approved_sha256"],
        }
        for record in parity["visuals"] + parity["audio"]
    }
    actual = {
        record["path"]: {
            "size": record["size"],
            "sha256": record["sha256"],
        }
        for record in pack["files"]
    }

    assert len(parity["visuals"]) == 28
    assert len(parity["audio"]) == 111
    assert pack["owner_visual_count"] == 28
    assert pack["owner_audio_count"] == 111
    assert pack["total_files"] == 139
    assert actual == expected

    for relative_path, identity in actual.items():
        source = ROOT / relative_path
        assert source.is_file(), relative_path
        raw = source.read_bytes()
        assert len(raw) == identity["size"], relative_path
        assert hashlib.sha256(raw).hexdigest() == identity["sha256"], relative_path


def test_zone4_static_pack_has_no_duplicate_governed_path():
    inventory = _json(INVENTORY)
    manifests = [
        ROOT / entry["manifest"]
        for entry in inventory["required_subtrees"]["entries"]
    ]
    owners: dict[str, Path] = {}
    for manifest_path in manifests:
        manifest = _json(manifest_path)
        for record in manifest["files"]:
            previous = owners.setdefault(record["path"], manifest_path)
            assert previous == manifest_path, (
                f"static path is staged by multiple manifests: {record['path']} "
                f"({previous}, {manifest_path})"
            )


def test_zone4_runtime_resources_are_in_the_static_contract():
    inventory = _json(INVENTORY)
    eligible = set(inventory["eligible_files"]["entries"])
    required = set(inventory["required_in_generation"]["entries"])
    closure = inventory["runtime_dependency_closure"]
    subtree_prefixes = {entry["prefix"] for entry in closure["subtrees"]}
    required_subtrees = inventory["required_subtrees"]["entries"]

    root_resources = {
        "zone4_owner_story_runtime.html",
        "ZONE4_004_LORD_STATE_BINDING_MATRIX.json",
        "ZONE4_004_RUNTIME_MANIFEST.json",
        "ZONE4_RUNTIME_MANIFEST.json",
    }
    assert root_resources <= eligible
    assert root_resources <= required
    assert "zone4_owner_story_runtime.html" in closure["entrypoints"]
    assert "js/e10/" in subtree_prefixes
    assert {
        "js/e10/zone4_owner_story_runtime.js",
        "css/e10/zone4_owner_story_runtime.css",
    } <= eligible
    assert "css/e10/zone4_owner_story_runtime.css" in required
    assert any(
        entry["manifest"] == "deploy/canonical-e10-zone4-static-pack-manifest.json"
        for entry in required_subtrees
    )


def test_zone4_serving_boundary_is_explicit_and_baked_fallback_is_present():
    app = APP.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")

    for route in (
        "@app.route('/ZONE4_004_LORD_STATE_BINDING_MATRIX.json')",
        "@app.route('/ZONE4_004_RUNTIME_MANIFEST.json')",
        "@app.route('/ZONE4_RUNTIME_MANIFEST.json')",
        "@app.route('/js/e10/zone4_owner_story_runtime.js')",
        "@app.route('/css/e10/zone4_owner_story_runtime.css')",
        # P0 corrective: this file was staged into the static release and
        # referenced by index.html, but never given a rule. /js/e10/ has no
        # generic route to cover the omission, so it 404'd in Production.
        "@app.route('/js/e10/zone4_cinematic_content.js')",
    ):
        assert route in app
    for source in (
        "zone4_owner_story_runtime.html",
        "ZONE4_004_LORD_STATE_BINDING_MATRIX.json",
        "ZONE4_004_RUNTIME_MANIFEST.json",
        "ZONE4_RUNTIME_MANIFEST.json",
        "js/e10/zone4_owner_story_runtime.js",
        "css/e10/zone4_owner_story_runtime.css",
        "js/e10/zone4_cinematic_content.js",
    ):
        assert source in dockerfile
    assert '/css/e10/zone4_owner_story_runtime.css' in page
    assert '/js/e10/zone4_owner_story_runtime.js' in page
    assert '/ZONE4_004_LORD_STATE_BINDING_MATRIX.json' in page
    assert '/ZONE4_004_RUNTIME_MANIFEST.json' in page
