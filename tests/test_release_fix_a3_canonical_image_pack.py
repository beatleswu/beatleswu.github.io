"""RELEASE-FIX-A3 -- Canonical Full Image Pack.

Covers the required regression items for the RELEASE-FIX-A3 incident scope
expansion (see docs/incidents/2026-07-12-full-site-asset-outage.md, A3
addendum): the runtime-reference-derived 180-file closure (RELEASE-FIX-A2)
was proven an insufficient ownership boundary by live browser audits, and
was superseded by deploy/canonical-image-pack-manifest.json -- the complete
verified historical production image tree (1,298 files), with reference
scanning demoted to a regression/observability layer only.

Deterministic, no network, no PowerShell required except where noted.
"""
import hashlib
import json
import re
import sys
import tarfile
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
IMAGE_PACK_MANIFEST = REPO_ROOT / "deploy" / "canonical-image-pack-manifest.json"
LEGACY_CLOSURE_MANIFEST = REPO_ROOT / "deploy" / "canonical-asset-closure-manifest.json"
INVENTORY = REPO_ROOT / "deploy" / "live-static-asset-inventory.json"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "release"))
import asset_reference_scanner as scanner  # noqa: E402


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def image_pack_manifest():
    return _load(IMAGE_PACK_MANIFEST)


@pytest.fixture(scope="module")
def legacy_closure_manifest():
    return _load(LEGACY_CLOSURE_MANIFEST)


# ---------------------------------------------------------------------------
# 1. Every governed manifest file exists on disk, with matching size + SHA.
# ---------------------------------------------------------------------------

def test_every_manifest_file_exists_with_matching_hash_and_size(image_pack_manifest):
    mismatches = []
    for f in image_pack_manifest["files"]:
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
# 2. No audio/video/non-image file is present in the manifest.
# ---------------------------------------------------------------------------

def test_manifest_contains_only_image_mime_types(image_pack_manifest):
    bad = [f["path"] for f in image_pack_manifest["files"] if not f["mime"].startswith("image/")]
    assert not bad, f"non-image entries in image pack manifest: {bad}"


# ---------------------------------------------------------------------------
# 3. The pre-existing 180 RELEASE-FIX-A2-governed files remain byte-identical
#    -- the A3 full-pack import must not have regressed the earlier closure.
# ---------------------------------------------------------------------------

def test_legacy_180_file_closure_remains_byte_identical(legacy_closure_manifest):
    mismatches = []
    for f in legacy_closure_manifest["files"]:
        source = REPO_ROOT / f["path"]
        assert source.is_file(), f"legacy governed file missing after A3 import: {f['path']}"
        actual_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual_sha != f["sha256"]:
            mismatches.append(f["path"])
    assert not mismatches, f"legacy 180-file closure changed during A3 import: {mismatches}"


# ---------------------------------------------------------------------------
# 4. live-static-asset-inventory.json points at the new image-pack manifest,
#    not the superseded 180-file closure -- this is the actual ownership
#    boundary switch that makes A3 the active source of truth.
# ---------------------------------------------------------------------------

def test_inventory_required_subtree_points_at_image_pack_manifest():
    inventory = _load(INVENTORY)
    entry = inventory["required_subtrees"]["entries"][0]
    assert entry["manifest"] == "deploy/canonical-image-pack-manifest.json"


# ---------------------------------------------------------------------------
# 5 & 6. Manifest path hygiene -- no traversal, no absolute paths, no
# duplicates, no case collisions (same class of check as RELEASE-FIX-A2,
# re-applied to the much larger A3 manifest).
# ---------------------------------------------------------------------------

def test_manifest_paths_have_no_traversal_or_absolute_components(image_pack_manifest):
    for f in image_pack_manifest["files"]:
        p = f["path"]
        assert not p.startswith("/"), f"absolute path: {p}"
        assert not re.match(r"^[A-Za-z]:", p), f"drive-absolute path: {p}"
        assert ".." not in p.split("/"), f"traversal component: {p}"


def test_manifest_paths_have_no_duplicates_or_case_collisions(image_pack_manifest):
    paths = [f["path"] for f in image_pack_manifest["files"]]
    assert len(paths) == len(set(paths)), "duplicate path(s) in image pack manifest"
    lowered = {}
    for p in paths:
        key = p.lower()
        assert key not in lowered, f"case-collision: {p!r} vs {lowered.get(key)!r}"
        lowered[key] = p


# ---------------------------------------------------------------------------
# 7. Query-string references normalize correctly (Phase 5 scanner hardening).
# ---------------------------------------------------------------------------

def test_scanner_strips_query_string_and_fragment():
    assert scanner.strip_query_and_fragment("/assets/shop/newbie_gift_pack.webp?v=1") == \
        "/assets/shop/newbie_gift_pack.webp"
    assert scanner.strip_query_and_fragment("/assets/foo.png#frag") == "/assets/foo.png"
    assert scanner.strip_query_and_fragment("/assets/foo.png?v=2#frag") == "/assets/foo.png"


def test_scanner_resolves_literal_path_with_query_string():
    text = "<img src=\"/assets/shop/newbie_gift_pack.webp?v=1\">"
    result = scanner.scan_text(text, "test.html")
    assert "/assets/shop/newbie_gift_pack.webp" in result.resolved_paths


# ---------------------------------------------------------------------------
# 8. Root-constant + literal concatenation (both plain-concat and
# template-literal forms) resolves to the correct static path.
# ---------------------------------------------------------------------------

def test_scanner_resolves_root_constant_plus_literal_concatenation():
    text = """
    const HERO_ITEM_ROOT = '/assets/hero/items/';
    return HERO_ITEM_ROOT + 'unknown.svg';
    """
    result = scanner.scan_text(text, "test.js")
    assert "/assets/hero/items/unknown.svg" in result.resolved_paths


def test_scanner_resolves_root_constant_plus_literal_template_form():
    text = """
    const HERO_ITEM_ROOT = '/assets/hero/items/';
    return `${HERO_ITEM_ROOT}unknown.svg`;
    """
    result = scanner.scan_text(text, "test.js")
    assert "/assets/hero/items/unknown.svg" in result.resolved_paths


# ---------------------------------------------------------------------------
# 9. Dict-literal + literal-root concatenation (messages.html's
# CHARACTER_ART pattern) resolves every dict value to a full path.
# ---------------------------------------------------------------------------

def test_scanner_resolves_dict_literal_combined_with_literal_root():
    text = """
    const CHARACTER_ART = {apprentice:'chibi_apprentice_normalized.webp',ranger:'chibi_ranger_normalized.webp'};
    add('/assets/hero/characters/'+CHARACTER_ART.apprentice,'base');
    """
    result = scanner.scan_text(text, "test.html")
    assert "/assets/hero/characters/chibi_apprentice_normalized.webp" in result.resolved_paths
    assert "/assets/hero/characters/chibi_ranger_normalized.webp" in result.resolved_paths


# ---------------------------------------------------------------------------
# 10. Genuinely runtime-composed references are reported, not silently
# ignored -- messages.html's `root + value + '.webp'` (value from a data
# field) and hero.html's `(item.root || HERO_GEAR_ROOT) + (variant ||
# item.art)` (value from a data array).
# ---------------------------------------------------------------------------

def test_scanner_reports_unresolved_dynamic_concatenation():
    text = """
    const LAYERS = [['combat_aura','/assets/hero/accessories/','aura']];
    function avatar(data){for(const [field,root,cls] of LAYERS){const value=data[field];if(value)add(root+value+'.webp',cls)}}
    """
    result = scanner.scan_text(text, "test.html")
    assert result.unresolved_dynamic_references, "expected an unresolved dynamic reference to be reported"
    patterns = [r["pattern"] for r in result.unresolved_dynamic_references]
    assert any("root+value+'.webp'" in p for p in patterns)


def test_scanner_does_not_silently_drop_property_access_concatenation():
    text = """
    const HERO_GEAR_ROOT = '/assets/hero/gear_v2/';
    function combatGearAssetSrc(item, variant) {
      return (item.root || HERO_GEAR_ROOT) + (variant || item.art);
    }
    """
    result = scanner.scan_text(text, "test.js")
    assert result.unresolved_dynamic_references, "structurally-varied root concatenation must be flagged, not ignored"


def test_scanner_flags_real_messages_html_and_hero_html_dynamic_patterns():
    # Regression guard against the exact real-world patterns discovered
    # during the RELEASE-FIX-A3 live browser audit -- if these files change
    # such that the dynamic pattern disappears, that's fine (re-run and
    # update), but a silent scan that finds *nothing* to flag here again
    # would mean the scanner regressed to A2's blind-spot behavior.
    messages_result = scanner.scan_text((REPO_ROOT / "messages.html").read_text(encoding="utf-8"), "messages.html")
    assert messages_result.unresolved_dynamic_references

    hero_result = scanner.scan_text((REPO_ROOT / "hero.html").read_text(encoding="utf-8"), "hero.html")
    assert hero_result.unresolved_dynamic_references


# ---------------------------------------------------------------------------
# 11. Archive path-traversal / absolute-path rejection for the RELEASE-FIX-A3
# deterministic-archive extraction flow -- simulated with Python's tarfile
# (equivalent semantics to the real `tar -xf` used by deploy-static-release.ps1,
# verifying that maliciously-crafted archive members cannot escape the
# extraction root).
# ---------------------------------------------------------------------------

def _is_within_directory(directory, target):
    abs_directory = Path(directory).resolve()
    abs_target = Path(target).resolve()
    return abs_directory in abs_target.parents or abs_directory == abs_target


def _safe_extract(tar, path):
    for member in tar.getmembers():
        if member.name.startswith("/") or re.match(r"^[A-Za-z]:", member.name):
            raise ValueError(f"absolute path detected in archive member: {member.name}")
        member_path = Path(path) / member.name
        if not _is_within_directory(path, member_path):
            raise ValueError(f"path traversal detected in archive member: {member.name}")
    tar.extractall(path)


def test_archive_extraction_rejects_path_traversal_member():
    with tempfile.TemporaryDirectory() as tmp:
        archive_path = Path(tmp) / "malicious.tar"
        extract_dir = Path(tmp) / "extract"
        extract_dir.mkdir()
        with tarfile.open(archive_path, "w") as tar:
            evil = tarfile.TarInfo(name="../../etc/passwd")
            data = b"pwned"
            evil.size = len(data)
            import io
            tar.addfile(evil, io.BytesIO(data))
        with tarfile.open(archive_path, "r") as tar:
            with pytest.raises(ValueError, match="path traversal"):
                _safe_extract(tar, extract_dir)


def test_archive_extraction_rejects_absolute_path_member():
    with tempfile.TemporaryDirectory() as tmp:
        archive_path = Path(tmp) / "malicious.tar"
        extract_dir = Path(tmp) / "extract"
        extract_dir.mkdir()
        with tarfile.open(archive_path, "w") as tar:
            evil = tarfile.TarInfo(name="/etc/passwd")
            data = b"pwned"
            evil.size = len(data)
            import io
            tar.addfile(evil, io.BytesIO(data))
        with tarfile.open(archive_path, "r") as tar:
            with pytest.raises(ValueError, match="[Aa]bsolute path"):
                _safe_extract(tar, extract_dir)


def test_archive_extraction_succeeds_for_well_formed_relative_members():
    with tempfile.TemporaryDirectory() as tmp:
        archive_path = Path(tmp) / "good.tar"
        extract_dir = Path(tmp) / "extract"
        extract_dir.mkdir()
        with tarfile.open(archive_path, "w") as tar:
            good = tarfile.TarInfo(name="assets/shop/ok.webp")
            data = b"fake-image-bytes"
            good.size = len(data)
            import io
            tar.addfile(good, io.BytesIO(data))
        with tarfile.open(archive_path, "r") as tar:
            _safe_extract(tar, extract_dir)
        assert (extract_dir / "assets" / "shop" / "ok.webp").read_bytes() == b"fake-image-bytes"


# ---------------------------------------------------------------------------
# 12. Deterministic archive tooling (New-DeterministicStaticArchive /
# Get-ArchiveTransferTimeoutSeconds) exists, is exported, and is wired into
# deploy-static-release.ps1's Step 4 in place of the old per-file scp loop.
# ---------------------------------------------------------------------------

def test_release_tooling_exports_archive_functions():
    content = (REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1").read_text(encoding="utf-8")
    assert "function New-DeterministicStaticArchive" in content
    assert "function Get-ArchiveTransferTimeoutSeconds" in content
    assert "'New-DeterministicStaticArchive'" in content
    assert "'Get-ArchiveTransferTimeoutSeconds'" in content


def test_deploy_script_uses_archive_upload_not_per_file_loop():
    content = (REPO_ROOT / "scripts" / "release" / "deploy-static-release.ps1").read_text(encoding="utf-8")
    assert "New-DeterministicStaticArchive" in content
    assert "tar -xf" in content
    # Invoke-BoundedFileUpload must be called exactly twice: the single
    # archive upload, and the manifest.json upload -- never once per
    # governed file (the old per-file scp loop this replaces).
    call_sites = re.findall(r"(?<!function )Invoke-BoundedFileUpload\s+-LocalPath", content)
    assert len(call_sites) == 2, (
        f"expected exactly 2 Invoke-BoundedFileUpload call sites (archive + "
        f"manifest.json), found {len(call_sites)} -- a per-file upload loop "
        f"would not scale to a hundreds-of-files image pack"
    )
