"""E10 Zone 1 deployment asset closure regression tests.

These tests derive the six approved Lord Trial runtime WebP files from the
committed art package and the 43 Zone 1 MP3 files from the committed runtime
audio tree/index references. They validate both manifest closure and the
actual governed New-StaticReleaseBundle output, so a future runtime asset
cannot be added without registering it for static deployment.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
IMAGE_MANIFEST = REPO_ROOT / "deploy" / "canonical-image-pack-manifest.json"
AUDIO_MANIFEST = REPO_ROOT / "deploy" / "canonical-e10-zone1-audio-pack-manifest.json"
ZONE2_ART_MANIFEST = REPO_ROOT / "deploy" / "canonical-e10-zone2-art-pack-manifest.json"
ZONE2_AUDIO_MANIFEST = REPO_ROOT / "deploy" / "canonical-e10-zone2-audio-pack-manifest.json"
STORYBOARD_AUDIO_MANIFEST = REPO_ROOT / "deploy" / "canonical-audio-pack-manifest.json"
INVENTORY = REPO_ROOT / "deploy" / "live-static-asset-inventory.json"
PSM1 = REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
ART_PACKAGE = REPO_ROOT / "assets" / "e10" / "art" / "zone1" / "lord_trial" / "zone1-lord-trial-art-package.json"
ZONE1_AUDIO_ROOT = REPO_ROOT / "assets" / "e10" / "audio" / "zone1"
INDEX_HTML = REPO_ROOT / "index.html"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lord_trial_runtime_webp_paths() -> set[str]:
    art = _load(ART_PACKAGE)
    return {entry["runtime_webp"]["path"] for entry in art["assets"]}


def _zone1_audio_paths() -> set[str]:
    return {
        path.relative_to(REPO_ROOT).as_posix()
        for path in ZONE1_AUDIO_ROOT.rglob("*.mp3")
    }


def _ps_quote(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


@pytest.fixture(scope="module")
def generated_static_bundle(tmp_path_factory):
    """Run the same governed staging function used by package-static-release."""
    if shutil.which("powershell.exe") is None:
        pytest.skip("Windows PowerShell is required for governed static-bundle staging")

    temp_root = tmp_path_factory.mktemp("e10-zone1-static-bundle")
    stage = temp_root / "static-bundle"
    script = temp_root / "stage_bundle.ps1"
    script.write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                f"Import-Module {_ps_quote(PSM1)} -Force -DisableNameChecking",
                "$inventory = Get-StaticAssetInventory",
                f"$files = @(New-StaticReleaseBundle -SourceRoot {_ps_quote(REPO_ROOT)} -StagePath {_ps_quote(stage)} -Inventory $inventory)",
                "$files | ConvertTo-Json -Depth 8",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert result.returncode == 0, f"governed static bundle staging failed:\n{result.stdout}\n{result.stderr}"
    files = json.loads(result.stdout)
    if isinstance(files, dict):
        files = [files]
    return stage, files


def test_lord_trial_runtime_webp_closure_is_exact_and_hash_locked():
    manifest = _load(IMAGE_MANIFEST)
    expected = _lord_trial_runtime_webp_paths()
    manifest_paths = {entry["path"] for entry in manifest["files"]}

    assert len(expected) == 6
    assert expected <= manifest_paths
    assert not any(path.endswith(".png") for path in manifest_paths if "assets/e10/art/zone1/lord_trial/" in path)

    for path in sorted(expected):
        entry = next(item for item in manifest["files"] if item["path"] == path)
        source = REPO_ROOT / path
        assert source.is_file(), path
        assert entry["mime"] == "image/webp"
        assert entry["size"] == source.stat().st_size
        assert entry["sha256"] == _sha256(source)


def test_zone1_audio_closure_is_exactly_43_locked_mp3_files():
    manifest = _load(AUDIO_MANIFEST)
    expected = _zone1_audio_paths()
    manifest_paths = {entry["path"] for entry in manifest["files"]}
    index_refs = {
        match.lstrip("/")
        for match in re.findall(r"/assets/e10/audio/zone1/[\w/.-]+\.mp3", INDEX_HTML.read_text(encoding="utf-8"))
    }

    assert len(expected) == 43
    assert manifest_paths == expected
    assert index_refs == expected
    assert manifest["total_files"] == len(manifest["files"]) == 43
    assert manifest["total_bytes"] == sum((REPO_ROOT / path).stat().st_size for path in expected)
    assert [entry["path"] for entry in manifest["files"]] == sorted(manifest_paths)

    for entry in manifest["files"]:
        source = REPO_ROOT / entry["path"]
        assert entry["mime"] == "audio/mpeg"
        assert source.is_file(), entry["path"]
        assert entry["size"] == source.stat().st_size
        assert entry["sha256"] == _sha256(source)


def test_inventory_wires_disjoint_e10_zone1_audio_manifest():
    inventory = _load(INVENTORY)
    e10_audio = next(
        entry for entry in inventory["required_subtrees"]["entries"]
        if entry["prefix"] == "assets/e10/audio/zone1/"
    )
    assert e10_audio["manifest"] == "deploy/canonical-e10-zone1-audio-pack-manifest.json"

    image_paths = {entry["path"] for entry in _load(IMAGE_MANIFEST)["files"]}
    storyboard_paths = {entry["path"] for entry in _load(STORYBOARD_AUDIO_MANIFEST)["files"]}
    e10_paths = {entry["path"] for entry in _load(AUDIO_MANIFEST)["files"]}
    assert not image_paths & e10_paths
    assert not storyboard_paths & e10_paths


def test_actual_governed_static_bundle_contains_closure_and_no_broad_assets(generated_static_bundle):
    stage, files = generated_static_bundle
    staged_paths = {entry["path"] for entry in files}
    expected_images = {entry["path"] for entry in _load(IMAGE_MANIFEST)["files"]}
    expected_storyboard_audio = {entry["path"] for entry in _load(STORYBOARD_AUDIO_MANIFEST)["files"]}
    expected_e10_audio = {entry["path"] for entry in _load(AUDIO_MANIFEST)["files"]}
    expected_zone2_art = {entry["path"] for entry in _load(ZONE2_ART_MANIFEST)["files"]}
    expected_zone2_audio = {entry["path"] for entry in _load(ZONE2_AUDIO_MANIFEST)["files"]}
    governed_assets = (
        expected_images
        | expected_storyboard_audio
        | expected_e10_audio
        | expected_zone2_art
        | expected_zone2_audio
    )

    lord_paths = _lord_trial_runtime_webp_paths()
    zone1_audio = _zone1_audio_paths()
    assert len(lord_paths & staged_paths) == 6
    assert len(zone1_audio & staged_paths) == 43
    assert all((stage / path).is_file() for path in lord_paths | zone1_audio)

    for path in lord_paths | zone1_audio:
        source = REPO_ROOT / path
        packaged = stage / path
        assert _sha256(packaged) == _sha256(source), path

    existing_e10_ui = {
        entry["path"] for entry in _load(IMAGE_MANIFEST)["files"]
        if entry["path"].startswith("assets/e10/ui/")
    }
    assert existing_e10_ui <= staged_paths

    staged_assets = {path for path in staged_paths if path.startswith("assets/")}
    assert staged_assets <= governed_assets

    forbidden = []
    for path in staged_paths:
        lower = path.lower()
        if (
            ".git/" in lower
            or lower.startswith(".claude/")
            or lower == "secret_key.txt"
            or lower.startswith(".env")
            or lower.endswith((".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx"))
            or lower.startswith("sgf_engine/")
            or "_local_review/" in lower
        ):
            forbidden.append(path)
    assert not forbidden, f"forbidden/private files entered governed static bundle: {forbidden}"
