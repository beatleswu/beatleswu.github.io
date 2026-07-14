"""Canonical Audio Pack -- storyboard narration MP3 static-release governance.

canonical-image-pack-manifest.json's own $schema_note documents deliberately
excluding "90 mp3 voice files" -- it is validated image/*-MIME-only
(test_release_fix_a3_canonical_image_pack.py::test_manifest_contains_only_image_mime_types).
That contract must not be weakened to smuggle audio in. This companion
manifest (deploy/canonical-audio-pack-manifest.json) governs exactly the
narration MP3s the intro-film cinematic references, wired into
live-static-asset-inventory.json as a second required_subtrees entry with
its own disjoint prefix (assets/storyboards/) and its own closure manifest,
so package-static-release.ps1 stages both packs without either weakening the
other's contract.

See docs/deployment/canonical_static_narration_audio_contract.md and the
2026-07-14 narration incident (PR #107) this manifest exists to make
release-complete.

Deterministic, no network. PowerShell/live packaging is exercised
separately (this file is pure static/structural verification).
"""
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIO_PACK_MANIFEST = REPO_ROOT / "deploy" / "canonical-audio-pack-manifest.json"
IMAGE_PACK_MANIFEST = REPO_ROOT / "deploy" / "canonical-image-pack-manifest.json"
INVENTORY = REPO_ROOT / "deploy" / "live-static-asset-inventory.json"
INDEX_HTML = REPO_ROOT / "index.html"

AUDIO_SRC_RE = re.compile(r"audioSrc:\s*'(/assets/storyboards/[^']+\.mp3)'")


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def audio_pack_manifest():
    return _load(AUDIO_PACK_MANIFEST)


def _referenced_audio_paths():
    html = INDEX_HTML.read_text(encoding="utf-8")
    return AUDIO_SRC_RE.findall(html)


# ---------------------------------------------------------------------------
# 1. Every governed manifest file exists on disk, with matching size + SHA
#    against the currently committed bytes.
# ---------------------------------------------------------------------------

def test_every_manifest_file_exists_with_matching_hash_and_size(audio_pack_manifest):
    mismatches = []
    for f in audio_pack_manifest["files"]:
        source = REPO_ROOT / f["path"]
        if not source.is_file():
            mismatches.append(f"missing: {f['path']}")
            continue
        actual_size = source.stat().st_size
        if actual_size != f["size"]:
            mismatches.append(f"size mismatch {f['path']}: manifest={f['size']} actual={actual_size}")
            continue
        actual_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual_sha != f["sha256"]:
            mismatches.append(f"sha mismatch {f['path']}: manifest={f['sha256']} actual={actual_sha}")
    assert not mismatches, "\n".join(mismatches)


# ---------------------------------------------------------------------------
# 2. The audio pack contains only audio/mpeg entries -- disjoint from the
#    image pack's image/*-only contract, not overlapping it.
# ---------------------------------------------------------------------------

def test_manifest_contains_only_audio_mpeg_mime_types(audio_pack_manifest):
    bad = [f["path"] for f in audio_pack_manifest["files"] if f["mime"] != "audio/mpeg"]
    assert not bad, f"non-audio/mpeg entries in audio pack manifest: {bad}"


def test_manifest_mime_matches_decoded_file_type(audio_pack_manifest):
    if shutil.which("file") is None:
        pytest.skip("`file` command not available in this environment")
    mismatches = []
    for f in audio_pack_manifest["files"]:
        result = subprocess.run(
            ["file", "--mime-type", "-b", str(REPO_ROOT / f["path"])],
            capture_output=True, text=True,
        )
        detected = result.stdout.strip()
        if detected != f["mime"]:
            mismatches.append(f"{f['path']}: manifest={f['mime']!r} detected={detected!r}")
    assert not mismatches, "\n".join(mismatches)


def test_image_pack_still_contains_zero_audio_entries():
    # Regression guard: adding the audio pack must never smuggle mp3s back
    # into the image-only contract it was deliberately kept out of.
    image_manifest = _load(IMAGE_PACK_MANIFEST)
    bad = [f["path"] for f in image_manifest["files"] if not f["mime"].startswith("image/")]
    assert not bad, f"non-image entries leaked into image pack manifest: {bad}"


# ---------------------------------------------------------------------------
# 3. Manifest path hygiene -- no traversal, no absolute paths, no
#    duplicates, no case collisions, every path under the governed prefix.
# ---------------------------------------------------------------------------

def test_manifest_paths_have_no_traversal_or_absolute_components(audio_pack_manifest):
    for f in audio_pack_manifest["files"]:
        p = f["path"]
        assert not p.startswith("/"), f"absolute path: {p}"
        assert not re.match(r"^[A-Za-z]:", p), f"drive-absolute path: {p}"
        assert ".." not in p.split("/"), f"traversal component: {p}"
        assert p.startswith("assets/storyboards/"), f"path outside governed prefix: {p}"


def test_manifest_paths_have_no_duplicates_or_case_collisions(audio_pack_manifest):
    paths = [f["path"] for f in audio_pack_manifest["files"]]
    assert len(paths) == len(set(paths)), "duplicate path(s) in audio pack manifest"
    lowered = {}
    for p in paths:
        key = p.lower()
        assert key not in lowered, f"case-collision: {p!r} vs {lowered.get(key)!r}"
        lowered[key] = p


def test_manifest_ordering_is_deterministic(audio_pack_manifest):
    paths = [f["path"] for f in audio_pack_manifest["files"]]
    assert paths == sorted(paths), "audio pack manifest files must be sorted by path for deterministic ordering"


# ---------------------------------------------------------------------------
# 4. The manifest is exactly the currently-referenced set -- no orphaned
#    (unreferenced) MP3, no missing referenced MP3. This is the same
#    completeness invariant tests/deployment/test_storyboard_narration_asset_completeness.py
#    enforces against the working tree; this test enforces it against the
#    governed release manifest specifically.
# ---------------------------------------------------------------------------

def test_manifest_exactly_matches_currently_referenced_audio_paths(audio_pack_manifest):
    referenced = {p.lstrip("/") for p in _referenced_audio_paths()}
    manifest_paths = {f["path"] for f in audio_pack_manifest["files"]}
    missing_from_manifest = referenced - manifest_paths
    orphaned_in_manifest = manifest_paths - referenced
    assert not missing_from_manifest, f"referenced audioSrc missing from audio pack manifest: {sorted(missing_from_manifest)}"
    assert not orphaned_in_manifest, f"audio pack manifest contains unreferenced (orphaned) files: {sorted(orphaned_in_manifest)}"


def test_manifest_has_exactly_90_entries(audio_pack_manifest):
    # Not a hardcoded assumption about the future -- a sentinel so any drift
    # from the currently-accepted count is investigated, not silently
    # absorbed. If this legitimately changes (new zone added, etc.), update
    # alongside test_manifest_exactly_matches_currently_referenced_audio_paths,
    # which is the real source-of-truth check above.
    assert audio_pack_manifest["total_files"] == 90
    assert len(audio_pack_manifest["files"]) == 90


# ---------------------------------------------------------------------------
# 5. live-static-asset-inventory.json wires the audio manifest in as a
#    second, disjoint required_subtrees entry -- without disturbing the
#    pre-existing image entry's position or contents.
# ---------------------------------------------------------------------------

def test_inventory_governs_storyboards_via_second_required_subtree():
    inventory = _load(INVENTORY)
    subtrees = inventory["required_subtrees"]["entries"]
    audio_subtree = next((s for s in subtrees if s["prefix"] == "assets/storyboards/"), None)
    assert audio_subtree is not None, "assets/storyboards/ must be declared in required_subtrees"
    assert audio_subtree["manifest"] == "deploy/canonical-audio-pack-manifest.json"


def test_inventory_image_subtree_entry_unchanged():
    inventory = _load(INVENTORY)
    entry = inventory["required_subtrees"]["entries"][0]
    assert entry["prefix"] == "assets/"
    assert entry["manifest"] == "deploy/canonical-image-pack-manifest.json"


def test_inventory_subtree_prefixes_are_disjoint_in_file_membership():
    # The two subtree manifests may have overlapping directory prefixes
    # (assets/ is a parent of assets/storyboards/), but must never list the
    # same file twice between them -- that would double-stage it.
    image_paths = {f["path"] for f in _load(IMAGE_PACK_MANIFEST)["files"]}
    audio_paths = {f["path"] for f in _load(AUDIO_PACK_MANIFEST)["files"]}
    overlap = image_paths & audio_paths
    assert not overlap, f"file(s) listed in both image and audio pack manifests: {overlap}"


# ---------------------------------------------------------------------------
# 6. The static release tooling's fail-closed staging logic is generic
#    (path/sha256/size only -- see ReleaseTooling.psm1 New-StaticReleaseBundle)
#    and already iterates every required_subtrees entry, so wiring the audio
#    manifest in reuses the exact same fail-closed guarantees the image pack
#    has (missing file / wrong hash / wrong size / path-safety all throw).
#    This is a structural guard that the iteration is still generic (not
#    hardcoded to a single subtree) after this change.
# ---------------------------------------------------------------------------

def test_release_tooling_subtree_staging_is_not_hardcoded_to_a_single_entry():
    content = (REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1").read_text(encoding="utf-8")
    assert "foreach ($subtree in @($Inventory.required_subtrees.entries))" in content, (
        "New-StaticReleaseBundle must iterate all required_subtrees entries generically, "
        "not assume exactly one -- this is what lets the audio pack coexist with the image pack"
    )
    assert "Governed subtree file declared in closure manifest is missing from source checkout" in content, (
        "fail-closed missing-file guard must remain present"
    )
    assert "does not match closure manifest (fail closed)" in content, (
        "fail-closed hash/size mismatch guard must remain present"
    )
