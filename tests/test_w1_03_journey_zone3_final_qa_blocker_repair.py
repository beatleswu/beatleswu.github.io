"""Bounded Zone 3 final-QA blocker repair contracts.

This test owns only the repair seam: the exact static closure, its five
QA-proven first-entry resources, and the presentation-only runtime guards.
The authoritative W1-05 40-case matrix remains a separate acceptance gate.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = "65dd8c00f217fc04942456d5b1dd02f52fc8f265"
STATIC_MANIFEST = ROOT / "deploy" / "canonical-e10-zone3-static-pack-manifest.json"
INVENTORY = ROOT / "deploy" / "live-static-asset-inventory.json"
INDEX = ROOT / "index.html"
WORLD_MAP_CSS = ROOT / "css" / "e9" / "reference_world_map.css"
ZONE3_FX_CSS = ROOT / "css" / "e9" / "zone3_presentation_fx.css"
RIGHT_CARDS = ROOT / "js" / "e9" / "right_cards.js"
WORLD_STAGE = ROOT / "js" / "e9" / "world_stage.js"

CURATED_MISSING_RESOURCES = [
    f"assets/e10/art/zone3/cinematic/zone3_shot{i:02d}.webp"
    for i in range(1, 6)
]

EXISTING_CLOSURE_MANIFESTS = [
    ROOT / "deploy" / "canonical-image-pack-manifest.json",
    ROOT / "deploy" / "canonical-audio-pack-manifest.json",
    ROOT / "deploy" / "canonical-e10-zone1-audio-pack-manifest.json",
    ROOT / "deploy" / "canonical-e10-zone2-art-pack-manifest.json",
    ROOT / "deploy" / "canonical-e10-zone2-audio-pack-manifest.json",
    ROOT / "deploy" / "canonical-e10-zone2-lord-trial-art-pack-manifest.json",
]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_zone3_static_closure_is_exact_and_hash_verified() -> None:
    manifest = load(STATIC_MANIFEST)
    files = manifest["files"]
    assert manifest["prefix"] == "assets/e10/"
    assert manifest["total_files"] == len(files) == 235
    assert manifest["total_bytes"] == sum(item["size"] for item in files)
    paths = [item["path"] for item in files]
    assert paths == sorted(paths)
    assert len(paths) == len(set(paths))
    assert all(path.startswith("assets/e10/") for path in paths)
    assert all("/source/" not in path for path in paths)
    assert all(Path(path).suffix.lower() in {".json", ".mp3", ".webp"} for path in paths)

    for item in files:
        source = ROOT / item["path"]
        raw = source.read_bytes()
        assert source.is_file(), item["path"]
        assert item["size"] == len(raw), item["path"]
        assert item["sha256"] == hashlib.sha256(raw).hexdigest(), item["path"]
        expected_mime = {
            ".json": "application/json",
            ".mp3": "audio/mpeg",
            ".webp": "image/webp",
        }[source.suffix.lower()]
        assert item["mime"] == expected_mime, item["path"]


def test_five_qa_proven_missing_resources_are_closed_without_source_masters() -> None:
    manifest = load(STATIC_MANIFEST)
    resources = manifest["curated_missing_resources"]
    assert [item["resource_path"] for item in resources] == CURATED_MISSING_RESOURCES
    for item in resources:
        assert item["source_present"] is True
        assert item["candidate_manifest_present"] is False
        assert item["image_present"] is False
        assert item["static_package_present"] is True
        assert item["runtime_requested"] is True
        assert item["omission_origin"] == "PACKAGE_MANIFEST"
        assert item["resource_path"] in {entry["path"] for entry in manifest["files"]}


def test_zone3_closure_is_wired_and_disjoint_from_previous_asset_packages() -> None:
    inventory = load(INVENTORY)
    entries = inventory["required_subtrees"]["entries"]
    zone3 = [item for item in entries if item["prefix"] == "assets/e10/"]
    assert len(zone3) == 1
    assert zone3[0]["manifest"] == "deploy/canonical-e10-zone3-static-pack-manifest.json"

    zone3_paths = {item["path"] for item in load(STATIC_MANIFEST)["files"]}
    previous_paths = {
        item["path"]
        for manifest_path in EXISTING_CLOSURE_MANIFESTS
        for item in load(manifest_path)["files"]
    }
    assert not zone3_paths & previous_paths


def test_repair_runtime_seams_remain_presentation_only() -> None:
    index = INDEX.read_text(encoding="utf-8")
    world_map_css = WORLD_MAP_CSS.read_text(encoding="utf-8")
    zone3_fx_css = ZONE3_FX_CSS.read_text(encoding="utf-8")
    right_cards = RIGHT_CARDS.read_text(encoding="utf-8")
    world_stage = WORLD_STAGE.read_text(encoding="utf-8")

    assert ".z3-fx-stage.intro-film-stage" in zone3_fx_css
    assert "position: absolute" in zone3_fx_css
    assert "width: 100%" in zone3_fx_css
    assert "height: 100%" in zone3_fx_css
    assert "body[data-e10-visual-skin=\"immersive-rpg\"] .cg-nav[data-e10-session-strip=\"1\"]" in world_map_css
    assert "position: fixed" in world_map_css
    assert "pointer-events: auto" in world_map_css
    assert "var replay = root.querySelector('[data-e10-zone-replay]')" in right_cards
    assert "var inlineReplay = document.createElement('button')" in world_stage
    assert "_registerZone3PresentationLifecycleCleanup" in index
    assert "_zone3PresentationAudio?.destroy?.()" in index
    assert "_zone3PresentationFx?.destroy?.()" in index
    assert "_zone3PresentationAudio = null" in index
    assert "_zone3PresentationFx = null" in index
    assert "onPresentationFailure" in index
    failure_start = index.index("function _failZone3PresentationOnly")
    failure_end = index.index("async function _continueZone3SafeEntry", failure_start)
    failure_handler = index[failure_start:failure_end]
    assert "fetch(" not in failure_handler
    assert "grantReward" not in failure_handler
    assert "clearZone" not in failure_handler
    assert "unlockZone" not in failure_handler
    assert "zone3PresentationFailsafe" in failure_handler


def test_repair_does_not_touch_protected_runtime_authority() -> None:
    changed = set(
        subprocess.check_output(
            ["git", "-c", "core.quotePath=false", "diff", "--name-only", BASE, "--"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        ).splitlines()
    )
    assert "app.py" not in changed
    assert "sw.js" not in changed
    assert "js/game/cinematic_replay.js" not in changed
    assert not any(path.startswith("migrations/") or path.startswith("db/") for path in changed)
