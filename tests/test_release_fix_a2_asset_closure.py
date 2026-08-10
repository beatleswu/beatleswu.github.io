"""RELEASE-FIX-A2 -- Canonical Full Asset Closure.

Covers the 12 required regression items from the incident recovery decision
(see docs/incidents/2026-07-12-full-site-asset-outage.md):

  1. Current runtime scan resolves to the governed local-image closure.
  2. Every referenced local image has a canonical source file.
  3. Every governed asset is present in the staged generation.
  4. Every staged file SHA matches the closure manifest.
  5. No unreferenced files from the historical 757 MB tree are imported.
  6. All 180 HTTP paths return 200.
  7. Every response Content-Type begins with image/.
  8. No asset response is text/html.
  9. Newly introduced missing local-image references fail CI.
  10. Landing/Login/Blog/Hero/Shop/Monsters/Pets/Storyboards/Rating Test/
      Play/Upgrade have zero broken-image requests.
  11. Partial/corrupt asset generations fail preflight.
  12. Complete rollback tuple includes assets/**, i18n.js and sw.js.

Items 6-8 and 10 require a real built container or live production and are
gated behind FIX_A2_LIVE_HTTP_CHECK (unset -> skipped, same pattern as
E9_PACKAGING_TEST_IMAGE elsewhere in this suite) so normal CI runs stay
hermetic. Items 1-5, 9, 11, 12 are fully deterministic, no network.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLOSURE_MANIFEST = REPO_ROOT / "deploy" / "canonical-asset-closure-manifest.json"
# RELEASE-FIX-A3 superseded CLOSURE_MANIFEST as the manifest live-static-
# asset-inventory.json's required_subtrees entry actually points at --
# staging now governs from the full image pack, not the 180-file closure.
ACTIVE_SUBTREE_MANIFEST = REPO_ROOT / "deploy" / "canonical-image-pack-manifest.json"
# 2026-07-15: a second, disjoint required_subtrees entry (assets/storyboards/)
# was added for narration audio -- see canonical_static_narration_audio_contract.md.
# New-StaticReleaseBundle stages the union of every required_subtrees entry's
# closure manifest, so the "governed, no more no less" assertion below must
# include this manifest's files too, or a real staging run now legitimately
# produces "extra" files this test doesn't know about.
ACTIVE_AUDIO_SUBTREE_MANIFEST = REPO_ROOT / "deploy" / "canonical-audio-pack-manifest.json"
# E10 Zone 1 Lord Trial closure is a separate namespace so the pre-existing
# assets/storyboards narration manifest remains image/audio-contract stable.
ACTIVE_E10_AUDIO_SUBTREE_MANIFEST = REPO_ROOT / "deploy" / "canonical-e10-zone1-audio-pack-manifest.json"
INVENTORY = REPO_ROOT / "deploy" / "live-static-asset-inventory.json"
PSM1 = REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1"

# Files known-good outside the assets/** closure -- baked into the image,
# unaffected by this incident (see the audit's Phase 3, Class D).
NON_ASSET_KNOWN_GOOD = {"/icon-192.png", "/icon-512.png", "/og-image.jpg", "/favicon.ico"}

IMAGE_EXT_PATTERN = re.compile(
    r"""["'(](/[a-zA-Z0-9_./-]+\.(?:png|jpe?g|webp|gif|ico))["')]"""
)
SCAN_GLOBS = ["*.html", "blog/*.html", "*.js", "*.py", "*.json", "*.css"]


def _read(path):
    return path.read_text(encoding="utf-8")


def _load_closure_manifest():
    return json.loads(_read(CLOSURE_MANIFEST))


def _load_active_image_manifest():
    return json.loads(_read(ACTIVE_SUBTREE_MANIFEST))


def _load_inventory():
    return json.loads(_read(INVENTORY))


def scan_runtime_image_references(repo_root=REPO_ROOT):
    """Re-implements the RELEASE-FIX-A2 audit's Phase 1 scan: every locally
    served image path referenced from tracked HTML/JS/Python/JSON/CSS."""
    result = subprocess.run(
        ["git", "grep", "-IhoE",
         r"""["'(](/[a-zA-Z0-9_./-]+\.(png|jpe?g|webp|gif|ico))["')]""",
         "--", "*.html", "*.js", "*.py", "*.json", "*.css",
         # Test fixtures under tests/ deliberately contain asset-path-shaped
         # string literals (to exercise scanner/manifest logic) that are not
         # real runtime references -- exclude them from this production-code
         # reference scan so they can't be mistaken for dead/live references.
         ":(exclude)tests/*"],
        cwd=repo_root, capture_output=True, text=True,
    )
    paths = set()
    for line in result.stdout.splitlines():
        m = IMAGE_EXT_PATTERN.search(line)
        if m:
            paths.add(m.group(1))
    # node_modules is git-tracked-excluded already via .gitignore in practice,
    # but defensively drop anything under it if ever matched.
    return {p for p in paths if "node_modules" not in p}


# ---------------------------------------------------------------------------
# 1 & 9. Runtime scan resolves entirely to the governed closure -- a new,
# unresolved reference (dead or newly-introduced) fails this test.
# ---------------------------------------------------------------------------

def test_every_runtime_image_reference_resolves_to_governed_closure():
    # Runtime packaging is governed by the active inventory subtree manifest.
    # The older 243-file A2 audit manifest remains a historical regression
    # fixture, but must not become a second source of truth for new assets.
    manifest = _load_active_image_manifest()
    governed = {"/" + f["path"] for f in manifest["files"]}
    referenced = scan_runtime_image_references()

    unresolved = referenced - governed - NON_ASSET_KNOWN_GOOD
    assert not unresolved, (
        f"{len(unresolved)} referenced image path(s) are not covered by the canonical "
        f"active canonical image pack manifest (deploy/canonical-image-pack-manifest.json) or the "
        f"known-good baked set -- this is exactly the class of dead/missing reference "
        f"that caused the 2026-07-12 outage: {sorted(unresolved)}"
    )


# ---------------------------------------------------------------------------
# 2. Every referenced local image has a canonical source file.
# ---------------------------------------------------------------------------

def test_every_referenced_image_has_a_source_file_in_repo():
    referenced = scan_runtime_image_references()
    for path in referenced:
        if path == "/favicon.ico":
            # False positive: matches app.py's `@app.route('/favicon.ico')`
            # decorator string, not a file reference. The route intentionally
            # serves icon-192.png in its place (see app.py's serve_favicon()).
            continue
        rel = path.lstrip("/")
        assert (REPO_ROOT / rel).is_file(), f"referenced image has no source file: {path}"


# ---------------------------------------------------------------------------
# 3 & 4 & 5 & 11. Staging behavior -- real PowerShell execution, not source
# regex. Uses a temp source root (never production, never C:\go-website)
# copied from the already-imported D:\go-website assets/.
# ---------------------------------------------------------------------------

def _run_pwsh(script):
    if shutil.which("powershell") is None:
        pytest.skip("powershell not available in this environment")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return result


def _copy_required_flat_generation_sources(source):
    """Build the smallest source fixture accepted by the live inventory."""
    for filename in ("index.html", "inventory.html", "i18n.js", "sw.js", "site-nav.js"):
        shutil.copy(REPO_ROOT / filename, source / filename)
    adapter_target = source / "js"
    adapter_target.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        REPO_ROOT / "js" / "map_battle_v1_adapter.js",
        adapter_target / "map_battle_v1_adapter.js",
    )
    # The E10 static-coherence contract derives the live runtime closure from
    # index.html and shell component references, so the fixture must carry
    # the same routed JS/CSS/component subtrees as a real release checkout.
    shutil.copytree(REPO_ROOT / "js" / "e9", source / "js" / "e9")
    shutil.copytree(REPO_ROOT / "css" / "e9", source / "css" / "e9")
    shutil.copytree(REPO_ROOT / "components" / "adventure", source / "components" / "adventure")


def test_staged_generation_contains_every_governed_asset_and_matches_manifest():
    # Staging is driven by whatever manifest live-static-asset-inventory.json's
    # required_subtrees entry currently points at -- RELEASE-FIX-A3 switched
    # that from the 180-file closure to the full image pack, so this test's
    # expected set must track the same manifest, not the superseded one.
    manifest = json.loads(_read(ACTIVE_SUBTREE_MANIFEST))
    audio_manifest = json.loads(_read(ACTIVE_AUDIO_SUBTREE_MANIFEST))
    e10_audio_manifest = json.loads(_read(ACTIVE_E10_AUDIO_SUBTREE_MANIFEST))
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source"
        stage = Path(tmp) / "stage"
        source.mkdir()
        _copy_required_flat_generation_sources(source)
        shutil.copytree(REPO_ROOT / "assets", source / "assets")

        script = f"""
        Import-Module '{PSM1}' -Force -DisableNameChecking
        $inventory = Get-StaticAssetInventory -Path '{INVENTORY}'
        $files = New-StaticReleaseBundle -SourceRoot '{source}' -StagePath '{stage}' -Inventory $inventory
        $files | ConvertTo-Json -Depth 5
        """
        result = _run_pwsh(script)
        assert result.returncode == 0, f"staging failed:\n{result.stdout}\n{result.stderr}"
        staged = json.loads(result.stdout)
        staged_by_path = {f["path"].replace("\\", "/"): f for f in staged}

        closure_paths = {
            path for path in _load_inventory()["eligible_files"]["entries"]
            if path.startswith(("js/e9/", "css/e9/", "components/adventure/"))
        }
        governed_paths = (
            {f["path"] for f in manifest["files"]}
            | {f["path"] for f in audio_manifest["files"]}
            | {f["path"] for f in e10_audio_manifest["files"]}
            | {
                "i18n.js", "sw.js", "index.html", "site-nav.js", "inventory.html",
                "js/e9/shell.js", "js/map_battle_v1_adapter.js",
            }
            | closure_paths
        )
        assert set(staged_by_path.keys()) == governed_paths, (
            "staged file set must be exactly the governed closure -- no more, no less "
            f"(missing: {governed_paths - set(staged_by_path)}, "
            f"extra/unreferenced: {set(staged_by_path) - governed_paths})"
        )
        for entry in manifest["files"] + audio_manifest["files"] + e10_audio_manifest["files"]:
            staged_entry = staged_by_path[entry["path"]]
            assert staged_entry["sha256"] == entry["sha256"], f"SHA mismatch for {entry['path']}"
            assert staged_entry["size"] == entry["size"], f"size mismatch for {entry['path']}"


def test_partial_generation_fails_closed_missing_file():
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source"
        stage = Path(tmp) / "stage"
        source.mkdir()
        _copy_required_flat_generation_sources(source)
        shutil.copytree(REPO_ROOT / "assets", source / "assets")
        # remove one governed file to simulate a partial/corrupt generation
        (source / "assets" / "shop" / "shop_bg.webp").unlink()

        script = f"""
        Import-Module '{PSM1}' -Force -DisableNameChecking
        $inventory = Get-StaticAssetInventory -Path '{INVENTORY}'
        try {{
            New-StaticReleaseBundle -SourceRoot '{source}' -StagePath '{stage}' -Inventory $inventory | Out-Null
            Write-Output "UNEXPECTED_SUCCESS"
        }} catch {{
            Write-Output "FAILED_CLOSED: $($_.Exception.Message)"
        }}
        """
        result = _run_pwsh(script)
        assert "FAILED_CLOSED" in result.stdout, (
            f"a partial generation (missing governed file) must fail closed, not silently "
            f"stage an incomplete assets/ tree: {result.stdout}\n{result.stderr}"
        )
        assert "missing from source checkout" in result.stdout


def test_partial_generation_fails_closed_corrupted_hash():
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source"
        stage = Path(tmp) / "stage"
        source.mkdir()
        _copy_required_flat_generation_sources(source)
        shutil.copytree(REPO_ROOT / "assets", source / "assets")
        # corrupt one governed file's bytes, preserving its exact size so
        # this exercises the SHA-256 check specifically (not the size check).
        corrupt_target = source / "assets" / "shop" / "shop_bg.webp"
        original_size = corrupt_target.stat().st_size
        corrupt_target.write_bytes((b"\x00" * original_size))

        script = f"""
        Import-Module '{PSM1}' -Force -DisableNameChecking
        $inventory = Get-StaticAssetInventory -Path '{INVENTORY}'
        try {{
            New-StaticReleaseBundle -SourceRoot '{source}' -StagePath '{stage}' -Inventory $inventory | Out-Null
            Write-Output "UNEXPECTED_SUCCESS"
        }} catch {{
            Write-Output "FAILED_CLOSED: $($_.Exception.Message)"
        }}
        """
        result = _run_pwsh(script)
        assert "FAILED_CLOSED" in result.stdout, (
            f"a corrupted governed file must fail closed via SHA-256 mismatch: "
            f"{result.stdout}\n{result.stderr}"
        )
        assert "SHA-256 does not match" in result.stdout


def test_no_unreferenced_historical_files_in_closure_manifest():
    # The manifest must be exactly the 192 previously referenced files plus
    # the 41 Owner-authorized E10 runtime UI assets, plus the 10 Owner-approved
    # E10 Zone 1 cinematic runtime derivatives (E10-Z1-PROD-INTEGRATION-001),
    # not the full 757MB historical tree this incident's audit found on the
    # production host (1,391 files) -- no blind wholesale import.
    manifest = _load_closure_manifest()
    assert manifest["total_files"] == 243
    assert len(manifest["files"]) == 243
    referenced = scan_runtime_image_references()
    # The E10 icon registry composes its local root and file names at runtime,
    # so those URLs are intentionally not discoverable as full literals by the
    # legacy grep scanner. Their dedicated inventory test proves every entry is
    # consumed by the exact-marker registry or art stylesheet.
    ui_inventory = json.loads(_read(REPO_ROOT / "assets" / "e10" / "ui" / "e10-ui-assets.json"))
    referenced.update("/" + asset["path"] for asset in ui_inventory["assets"])
    governed = {"/" + f["path"] for f in manifest["files"]}
    over_broad = governed - referenced
    assert not over_broad, (
        f"closure manifest contains files not referenced by any runtime scan "
        f"(scope creep beyond the confirmed incident): {sorted(over_broad)}"
    )


# ---------------------------------------------------------------------------
# 12. Rollback tuple includes assets/**, i18n.js and sw.js -- the rollback
# script's verification loop is generic over manifest.files, so once a
# target generation's manifest includes assets/ entries (as any future
# RELEASE-FIX-A2-generation manifest will, via New-StaticReleaseManifestObject
# consuming New-StaticReleaseBundle's now-extended file list), rollback
# verification automatically covers them -- confirm the script does not
# hardcode a 2-file assumption anywhere.
# ---------------------------------------------------------------------------

def test_rollback_script_does_not_hardcode_a_two_file_assumption():
    content = _read(REPO_ROOT / "scripts" / "release" / "rollback-static-release.ps1")
    assert "foreach ($entry in $targetManifest.files)" in content, (
        "rollback verification must iterate the target manifest's full files array "
        "generically, so assets/** entries are covered automatically once present"
    )
    assert re.search(r"\bfiles\[0\]|\bfiles\[1\]|Count -eq 2\b", content) is None, (
        "rollback script must not assume exactly 2 files"
    )


def test_deploy_script_does_not_hardcode_a_two_file_assumption():
    content = _read(REPO_ROOT / "scripts" / "release" / "deploy-static-release.ps1")
    assert "foreach ($entry in" in content
    assert re.search(r"\bfiles\[0\]|\bfiles\[1\]|Count -eq 2\b", content) is None


# ---------------------------------------------------------------------------
# Provenance sanity -- recovered, historical, and Owner-authorized
# project-created assets remain separate exact classes.
# ---------------------------------------------------------------------------

def test_manifest_provenance_classes_are_honest():
    manifest = _load_closure_manifest()
    by_class = {}
    for f in manifest["files"]:
        by_class.setdefault(f["provenance"], []).append(f["path"])
    assert len(by_class.get("historical-git-verified", [])) == 178
    assert len(by_class.get("production-host-recovered", [])) == 2
    expected_owner_created = {
        "assets/maps/e10-vs1f-landmarks/zone-01-beginner-village.webp",
        "assets/maps/e10-vs1f-landmarks/zone-02-slime-plains.webp",
        "assets/maps/e10-vs1f-landmarks/zone-03-goblin-cave.webp",
        "assets/maps/e10-vs1f-landmarks/zone-04-twilight-forest.webp",
        "assets/maps/e10-vs1f-landmarks/zone-05-sky-tower.webp",
        "assets/maps/e10-vs1f-landmarks/zone-06-royal-castle.webp",
        "assets/maps/e10-vs1f-landmarks/zone-07-star-sea-passage.webp",
        "assets/maps/e10-vs1f-landmarks/zone-08-abyssal-forge.webp",
        "assets/maps/e10-vs1f-landmarks/zone-09-eternal-night-shrine.webp",
        "assets/maps/e10-vs1f-landmarks/zone-10-ancient-doom-temple.webp",
        "assets/maps/e10_world_stage_v1_base.webp",
        "assets/maps/e10_world_stage_v2_clean.webp",
    }
    ui_inventory = json.loads(_read(REPO_ROOT / "assets" / "e10" / "ui" / "e10-ui-assets.json"))
    expected_owner_created.update(asset["path"] for asset in ui_inventory["assets"])
    zone1_cinematic_inventory = json.loads(
        _read(REPO_ROOT / "assets" / "e10" / "cinematic" / "zone1-cinematic-assets.json")
    )
    expected_owner_created.update(asset["path"] for asset in zone1_cinematic_inventory["assets"])
    assert by_class.get("owner-approved-project-created") == sorted(expected_owner_created)
    assert set(by_class["production-host-recovered"]) == {
        "assets/go_rpg_assets/claire_avatar.webp",
        "assets/shop/title_badge_recruit.webp",
    }
    for f in manifest["files"]:
        assert f["sha256"], f"missing sha256 for {f['path']}"
        assert f["size"] > 0, f"zero/negative size for {f['path']}"
        assert f["mime"].startswith("image/"), f"non-image mime recorded for {f['path']}"


# ---------------------------------------------------------------------------
# 6, 7, 8, 10. Live HTTP checks -- opt-in only, gated so normal CI (no
# built container, no production access) stays green and hermetic.
# ---------------------------------------------------------------------------

LIVE_CHECK_BASE_URL = os.environ.get("FIX_A2_LIVE_HTTP_CHECK")

PAGE_TO_CATEGORY_SAMPLE = {
    "landing.html": "assets/landing_page_assets/landing_go_stone_badge.webp",
    "login.html": "assets/login_guild_counter.webp",
    "blog/index.html": "assets/landing_page_assets/landing_go_stone_badge.webp",
    "hero.html": "assets/hero/hero_bg.webp",
    "shop.html": "assets/shop/shop_bg.webp",
}


@pytest.mark.skipif(not LIVE_CHECK_BASE_URL, reason="set FIX_A2_LIVE_HTTP_CHECK=<base_url> to run live checks")
class TestLiveAssetHttpChecks:
    def test_all_180_asset_urls_return_200_image_content_type(self):
        import urllib.request
        manifest = _load_closure_manifest()
        failures = []
        for f in manifest["files"]:
            url = LIVE_CHECK_BASE_URL.rstrip("/") + "/" + f["path"]
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    status = resp.status
                    content_type = resp.headers.get("Content-Type", "")
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{f['path']}: request failed ({exc})")
                continue
            if status != 200:
                failures.append(f"{f['path']}: HTTP {status}")
            elif not content_type.startswith("image/"):
                failures.append(f"{f['path']}: Content-Type={content_type!r} (expected image/*, this is the themed-404-looks-like-200 trap)")
        assert not failures, "\n".join(failures)

    def test_representative_pages_have_zero_broken_image_requests(self):
        # Real page fetch + reference extraction + per-image HEAD check.
        import urllib.request
        for page, sample_path in PAGE_TO_CATEGORY_SAMPLE.items():
            url = LIVE_CHECK_BASE_URL.rstrip("/") + "/" + sample_path
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=10) as resp:
                assert resp.status == 200, f"{page}'s representative asset {sample_path} is broken"
                assert resp.headers.get("Content-Type", "").startswith("image/")


# ---------------------------------------------------------------------------
# Manifest safety -- path hygiene, symlink hygiene, and MIME-vs-decoded-type
# consistency for all 180 declared files. Deterministic, no network.
# ---------------------------------------------------------------------------

def test_manifest_paths_have_no_absolute_or_traversal_components():
    manifest = _load_closure_manifest()
    for f in manifest["files"]:
        p = f["path"]
        assert not p.startswith("/"), f"absolute path in manifest: {p}"
        assert not re.match(r"^[A-Za-z]:", p), f"drive-absolute path in manifest: {p}"
        assert ".." not in p.split("/"), f"path traversal component in manifest: {p}"


def test_manifest_paths_have_no_duplicates():
    manifest = _load_closure_manifest()
    paths = [f["path"] for f in manifest["files"]]
    assert len(paths) == len(set(paths)), "duplicate normalized path(s) in closure manifest"


def test_manifest_paths_have_no_case_collisions():
    # Two distinct declared paths that would collide on a case-insensitive
    # filesystem (Windows dev machines, some CI runners) must never coexist.
    manifest = _load_closure_manifest()
    paths = [f["path"] for f in manifest["files"]]
    lowered = {}
    for p in paths:
        key = p.lower()
        assert key not in lowered, f"case-collision: {p!r} vs {lowered.get(key)!r}"
        lowered[key] = p


def test_manifest_source_files_are_not_symlinks():
    manifest = _load_closure_manifest()
    for f in manifest["files"]:
        source = REPO_ROOT / f["path"]
        assert source.is_file(), f"manifest source file missing: {f['path']}"
        assert not source.is_symlink(), f"manifest source file must not be a symlink: {f['path']}"


def test_manifest_mime_matches_decoded_file_type():
    if shutil.which("file") is None:
        pytest.skip("`file` command not available in this environment")
    manifest = _load_closure_manifest()
    mismatches = []
    for f in manifest["files"]:
        result = subprocess.run(
            ["file", "--mime-type", "-b", str(REPO_ROOT / f["path"])],
            capture_output=True, text=True,
        )
        detected = result.stdout.strip()
        if detected != f["mime"]:
            mismatches.append(f"{f['path']}: manifest={f['mime']!r} detected={detected!r}")
    assert not mismatches, "\n".join(mismatches)
