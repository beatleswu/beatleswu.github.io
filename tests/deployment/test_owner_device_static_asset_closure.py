"""Regression coverage for the owner-device Equipment static asset closure.

The runtime closure is derived from the two registries and the loading semantics
of js/rpg_wave2_wearable_renderer.js. It deliberately does not maintain a
second hand-written list of today's asset paths.
"""

from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path
import re
import subprocess

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
BASE_HEAD = "d1e94b63be8cb96103c6f20e2db4e6401d48a41d"
EQUIPMENT_MANIFEST = ROOT / "deploy/canonical-equipment-runtime-asset-manifest.json"
IMAGE_MANIFEST = ROOT / "deploy/canonical-image-pack-manifest.json"
INVENTORY = ROOT / "deploy/live-static-asset-inventory.json"
HANDHELD_REGISTRY_PATH = (
    "assets/hero/equipment/wearables/handheld/handheld_runtime_registry.json"
)
WEARABLE_REGISTRY_PATH = "assets/hero/equipment/wearables/wearable_registry.json"
EQUIPMENT_MANIFEST_PATH = "deploy/canonical-equipment-runtime-asset-manifest.json"
REQUIRED_PREFIX = "assets/hero/"


def _normalise_asset_path(value: str) -> str:
    path = str(value).replace("\\", "/").lstrip("/")
    assert path and not path.startswith("../") and "/../" not in path
    return path


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_file_at(ref: str, path: str) -> bytes:
    return subprocess.check_output(
        ["git", "show", f"{ref}:{path}"],
        cwd=ROOT,
    )


def _json_at(ref: str, path: str) -> dict:
    return json.loads(_git_file_at(ref, path).decode("utf-8"))


def _manifest_paths(manifest: dict) -> set[str]:
    return {_normalise_asset_path(entry["path"]) for entry in manifest["files"]}


def _runtime_registry_paths(handheld: dict, wearable: dict) -> set[str]:
    """Mirror the renderer's registry loading and visibility decisions."""

    paths = {
        HANDHELD_REGISTRY_PATH,
        WEARABLE_REGISTRY_PATH,
    }

    for character in (handheld.get("characters") or {}).values():
        for field in (
            "base_asset",
            "open_hand_suppression_mask",
            "front_grip_hand_asset",
        ):
            if character.get(field):
                paths.add(_normalise_asset_path(character[field]))

    for weapon in (handheld.get("weapons") or {}).values():
        if weapon.get("runtime_supported") is not False and weapon.get("asset"):
            paths.add(_normalise_asset_path(weapon["asset"]))

    for character in (wearable.get("characters") or {}).values():
        for field in ("base", "hair_front_mask"):
            if character.get(field):
                paths.add(_normalise_asset_path(character[field]))

    for equipment in (wearable.get("equipment") or {}).values():
        if (
            equipment.get("wearable_visibility") != "INVENTORY_ONLY"
            and equipment.get("asset")
        ):
            paths.add(_normalise_asset_path(equipment["asset"]))

    return paths


def _current_runtime_registry_paths() -> set[str]:
    return _runtime_registry_paths(
        _load_json(ROOT / HANDHELD_REGISTRY_PATH),
        _load_json(ROOT / WEARABLE_REGISTRY_PATH),
    )


def _required_subtree_entries() -> list[dict]:
    return _load_json(INVENTORY)["required_subtrees"]["entries"]


def _all_governed_static_paths() -> set[str]:
    paths: set[str] = set()
    for subtree in _required_subtree_entries():
        paths |= _manifest_paths(_load_json(ROOT / subtree["manifest"]))
    return paths


def _git_commit_metadata(commit: str) -> tuple[str, str]:
    raw = subprocess.check_output(
        ["git", "show", "-s", "--format=%s%x09%cs", commit],
        cwd=ROOT,
        text=True,
    ).strip()
    subject, date = raw.split("\t", 1)
    return subject, date


def _git_blob(commit: str, path: str) -> bytes:
    return subprocess.check_output(
        ["git", "cat-file", "blob", f"{commit}:{path}"],
        cwd=ROOT,
    )


def test_runtime_registry_closure_is_complete():
    required = _current_runtime_registry_paths()
    governed = _all_governed_static_paths()
    assert required <= governed, sorted(required - governed)


def test_equipment_manifest_is_the_exact_delta_from_historical_image_pack():
    required = _current_runtime_registry_paths()
    image_paths = _manifest_paths(_load_json(IMAGE_MANIFEST))
    equipment_manifest = _load_json(EQUIPMENT_MANIFEST)
    equipment_paths = _manifest_paths(equipment_manifest)

    assert equipment_paths == required - image_paths
    assert len(equipment_paths) == 51
    assert all(path.startswith(REQUIRED_PREFIX) for path in equipment_paths)
    assert equipment_manifest["total_files"] == len(equipment_paths)
    assert equipment_manifest["total_bytes"] == sum(
        entry["size"] for entry in equipment_manifest["files"]
    )


def test_inventory_wires_equipment_manifest_and_keeps_file_membership_disjoint():
    matching = [
        subtree
        for subtree in _required_subtree_entries()
        if subtree["manifest"] == EQUIPMENT_MANIFEST_PATH
    ]
    assert len(matching) == 1
    assert matching[0]["prefix"] == REQUIRED_PREFIX
    assert "Stage exactly" in matching[0]["staging_rule"]
    assert "never stage an unlisted Equipment runtime asset" in matching[0]["staging_rule"]

    owners: dict[str, str] = {}
    for subtree in _required_subtree_entries():
        for path in _manifest_paths(_load_json(ROOT / subtree["manifest"])):
            previous = owners.setdefault(path, subtree["manifest"])
            assert previous == subtree["manifest"], (
                f"static path is staged by multiple manifests: {path} "
                f"({previous}, {subtree['manifest']})"
            )


def test_manifest_entries_are_byte_and_provenance_attested():
    manifest = _load_json(EQUIPMENT_MANIFEST)
    entries = manifest["files"]
    assert len(entries) == len({entry["path"] for entry in entries})
    assert [entry["path"] for entry in entries] == sorted(entry["path"] for entry in entries)

    final_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()
    for entry in entries:
        path = _normalise_asset_path(entry["path"])
        source = ROOT / path
        assert source.is_file(), path
        raw = source.read_bytes()
        assert len(raw) == entry["size"], path
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"], path

        source_commit = entry["source_commit"]
        assert re.fullmatch(r"[0-9a-f]{40}", source_commit), path
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", source_commit, final_head],
            cwd=ROOT,
            check=True,
        )
        assert _git_blob(source_commit, path) == raw, path
        subject, date = _git_commit_metadata(source_commit)
        assert entry["source_subject"] == subject, path
        assert entry["source_date"] == date, path
        assert entry["source_evidence"], path

        if entry["mime"] == "application/json":
            assert entry["line_ending_policy"] == "LF", path
            assert b"\r" not in raw, path
        else:
            with Image.open(BytesIO(raw)) as image:
                assert entry["mime"] == "image/png", path
                assert image.format == "PNG", path
                assert image.size == (entry["width"], entry["height"]), path
                assert image.mode in {"RGBA", "LA", "L"}, path


def test_pre_corrective_canonical_snapshot_contains_the_omission():
    base_handheld = _json_at(BASE_HEAD, HANDHELD_REGISTRY_PATH)
    base_wearable = _json_at(BASE_HEAD, WEARABLE_REGISTRY_PATH)
    base_image_manifest = _json_at(BASE_HEAD, "deploy/canonical-image-pack-manifest.json")
    base_inventory = _json_at(BASE_HEAD, "deploy/live-static-asset-inventory.json")

    base_required = _runtime_registry_paths(base_handheld, base_wearable)
    base_missing = base_required - _manifest_paths(base_image_manifest)
    base_manifests = {
        entry["manifest"]
        for entry in base_inventory["required_subtrees"]["entries"]
    }

    assert len(base_missing) == 51
    assert EQUIPMENT_MANIFEST_PATH not in base_manifests
    assert base_missing


def test_equipment_registry_paths_are_external_static_content():
    build_manifest = _load_json(ROOT / "deploy/build-manifest.json")
    boundary_text = json.dumps(
        build_manifest.get("build_inputs", {}).get("external_content_boundary", {}),
        ensure_ascii=False,
    )
    assert "assets/" in boundary_text
    assert "static" in boundary_text.lower()

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "VERSIONED STATIC ARTIFACT" in dockerfile
    assert "GO_ODYSSEY_LIVE_STATIC_ROOT" in dockerfile
    assert not re.search(r"(?m)^\s*COPY\s+assets(?:/|\s)", dockerfile)
