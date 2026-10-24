"""G080 F: current-source A2 closure, not historical-only 2026-07 image scan.

The 49 formerly flagged runtime PNGs are sourced from existing, disjoint
Equipment and Zone4 manifests already admitted by live-static inventory.
Each asset is exact-SHA, exact-size, Git-blob anchored, and HTTP routable.
No production source, Owner credentials, or source art is modified here.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from collections import Counter

import pytest

from tests.test_release_fix_a2_asset_closure import (
    ACTIVE_E10_ZONE2_LORD_TRIAL_ART_SUBTREE_MANIFEST,
    ACTIVE_E10_ZONE3_STATIC_SUBTREE_MANIFEST,
    INTENTIONAL_NON_PACKAGED_REFERENCES,
    NON_ASSET_KNOWN_GOOD,
    _load_active_image_manifest,
    _load_build_input_image_paths,
    scan_runtime_image_references,
)

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "deploy/live-static-asset-inventory.json"
EQUIPMENT = "deploy/canonical-equipment-runtime-asset-manifest.json"
ZONE4 = "deploy/canonical-e10-zone4-static-pack-manifest.json"


def _authoritative_entries():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    observed = {}
    for subtree in inventory["required_subtrees"]["entries"]:
        manifest = json.loads((ROOT / subtree["manifest"]).read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            assert entry["path"] not in observed, (
                "Duplicate required_subtrees member: " + entry["path"]
            )
            observed[entry["path"]] = (subtree["manifest"], entry)
    return observed


def _family(relative):
    if relative.startswith("assets/e10/art/zone4/lord/") and relative.endswith(".png"):
        return "zone4_lord"
    if (relative.startswith("assets/hero/characters/wave2_p1/weapon_pose/handheld/")
            and relative.endswith(".png")):
        return "handheld_pose"
    if (relative.startswith("assets/hero/equipment/wearables/overlays/")
            and relative.endswith(".png")):
        return "wearables_overlay"
    return None


def _target_49():
    """Identify only the 49 previously misreported by legacy A2 audit."""
    legacy = {"/" + e["path"] for e in _load_active_image_manifest()["files"]}
    for p in (ACTIVE_E10_ZONE3_STATIC_SUBTREE_MANIFEST,
              ACTIVE_E10_ZONE2_LORD_TRIAL_ART_SUBTREE_MANIFEST):
        legacy.update("/" + e["path"] for e in json.loads(p.read_text(encoding="utf-8"))["files"])
    legacy.update(_load_build_input_image_paths())
    previously_reported = (scan_runtime_image_references() - legacy
                           - NON_ASSET_KNOWN_GOOD - INTENTIONAL_NON_PACKAGED_REFERENCES)
    assert all(_family(path.lstrip("/")) for path in previously_reported)
    return sorted(path.lstrip("/") for path in previously_reported)


def _blob(commit, path):
    result = subprocess.run(
        ["git", "cat-file", "blob", f"{commit}:{path}"],
        cwd=ROOT, capture_output=True, check=True,
    )
    return result.stdout


def _verify_bytes(payload, entry):
    if len(payload) != entry["size"]:
        raise ValueError("static release byte size differs from governed source")
    if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
        raise ValueError("static release SHA-256 differs from governed source")


def test_49_runtime_image_namespaces_are_exact_and_disjoint():
    files = _target_49()
    assert Counter(_family(path) for path in files) == {
        "zone4_lord": 6, "handheld_pose": 27, "wearables_overlay": 16,
    }
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    manifest_names = {e["manifest"] for e in inventory["required_subtrees"]["entries"]}
    assert {EQUIPMENT, ZONE4} <= manifest_names
    entries = _authoritative_entries()
    assert len(files) == len(set(files)) == 49
    for path in files:
        assert path in entries, "Runtime image absent from live release inventory: " + path
        actual_manifest = entries[path][0]
        assert actual_manifest == (ZONE4 if _family(path) == "zone4_lord" else EQUIPMENT)


def test_49_runtime_images_match_exact_source_git_blob_and_hash():
    entries = _authoritative_entries()
    for path in _target_49():
        entry = entries[path][1]
        source_bytes = (ROOT / path).read_bytes()
        _verify_bytes(source_bytes, entry)
        commit = entry["source_commit"]
        assert len(commit) == 40
        assert source_bytes == _blob(commit, path), "Source Git blob drift: " + path
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=ROOT, capture_output=True,
        )
        assert ancestor.returncode == 0, "Unadopted source commit: " + path


def test_asset_admission_refuses_same_size_corruption_and_missing_bytes():
    for path in (_target_49()[0], _target_49()[-1]):
        entry = _authoritative_entries()[path][1]
        data = (ROOT / path).read_bytes()
        _verify_bytes(data, entry)
        with pytest.raises(ValueError, match="size"):
            _verify_bytes(data[:-1], entry)
        tampered = bytes([data[0] ^ 1]) + data[1:]
        with pytest.raises(ValueError, match="SHA-256"):
            _verify_bytes(tampered, entry)


def test_all_49_assets_are_flask_routable_as_images(monkeypatch):
    monkeypatch.delenv("GO_ODYSSEY_LIVE_STATIC_ROOT", raising=False)
    os.environ.setdefault("SECRET_KEY", "g080-f-disposable-static-qa")
    import app as app_module
    client = app_module.app.test_client()
    for path in _target_49():
        response = client.head("/" + path)
        assert response.status_code == 200, (path, response.status_code)
        assert response.mimetype == "image/png", (path, response.mimetype)
