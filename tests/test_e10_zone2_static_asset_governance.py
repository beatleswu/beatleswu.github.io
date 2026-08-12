"""Static-release closure contracts for the Owner-locked Zone 2 package."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ART_MANIFEST_PATH = ROOT / "deploy" / "canonical-e10-zone2-art-pack-manifest.json"
AUDIO_MANIFEST_PATH = ROOT / "deploy" / "canonical-e10-zone2-audio-pack-manifest.json"
INVENTORY_PATH = ROOT / "deploy" / "live-static-asset-inventory.json"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_exact_files(manifest, *, mime, prefix):
    files = manifest["files"]
    assert manifest["total_files"] == len(files)
    assert [item["path"] for item in files] == sorted(item["path"] for item in files)
    assert all(item["path"].startswith(prefix) for item in files)
    assert all(item["mime"] == mime for item in files)
    assert len({item["path"] for item in files}) == len(files)
    assert len({item["sha256"] for item in files}) == len(files)
    for item in files:
        source = ROOT / item["path"]
        assert source.is_file(), item["path"]
        assert source.stat().st_size == item["size"], item["path"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == item["sha256"], item["path"]


def test_zone2_art_manifest_is_exact_ten_owner_locked_webp_files():
    manifest = _load(ART_MANIFEST_PATH)
    _assert_exact_files(manifest, mime="image/webp", prefix="assets/storyboards/e10_z2_")
    assert manifest["total_files"] == 10
    assert all(item["width"] == 1280 and item["height"] == 720 for item in manifest["files"])
    assert [item["path"] for item in manifest["files"]] == [
        f"assets/storyboards/e10_z2_shot{i:02d}.webp" for i in range(1, 11)
    ]


def test_zone2_audio_manifest_is_exact_fifty_three_owner_locked_mp3_files():
    manifest = _load(AUDIO_MANIFEST_PATH)
    _assert_exact_files(manifest, mime="audio/mpeg", prefix="assets/e10/audio/zone2/")
    assert manifest["total_files"] == 53
    assert manifest["provenance_summary"] == {"owner-approved-project-created": 53}


def test_zone2_manifests_are_wired_as_disjoint_inventory_subtrees():
    inventory = _load(INVENTORY_PATH)
    entries = inventory["required_subtrees"]["entries"]
    art = next(item for item in entries if item["prefix"] == "assets/storyboards/e10_z2_")
    audio = next(item for item in entries if item["prefix"] == "assets/e10/audio/zone2/")
    assert art["manifest"] == "deploy/canonical-e10-zone2-art-pack-manifest.json"
    assert audio["manifest"] == "deploy/canonical-e10-zone2-audio-pack-manifest.json"

    art_paths = {item["path"] for item in _load(ART_MANIFEST_PATH)["files"]}
    audio_paths = {item["path"] for item in _load(AUDIO_MANIFEST_PATH)["files"]}
    image_paths = {item["path"] for item in _load(ROOT / "deploy/canonical-image-pack-manifest.json")["files"]}
    storyboard_audio_paths = {
        item["path"] for item in _load(ROOT / "deploy/canonical-audio-pack-manifest.json")["files"]
    }
    assert not art_paths & image_paths
    assert not art_paths & storyboard_audio_paths
    assert not audio_paths & storyboard_audio_paths
    assert not audio_paths & image_paths
