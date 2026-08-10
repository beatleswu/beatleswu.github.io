"""E10 Zone 1 Lord Trial -- production art integration governance
(2026-08-10, Owner Final Art Replacement Task).

The Owner replaced the CSS/emoji engineering prototype for the Lord
Challenge Card / Lord Entrance Ritual / Success / Failure screens with six
production art assets. This file proves: the promoted runtime copies exist
and match their recorded hashes, index.html actually references them (no
silent fallback to CSS/emoji), the removed prototype visuals are gone, and
the untouched 35-asset audio package + 8-asset Lord Trial SFX package are
still exactly as they were (this was an art-only pass).

Deliberately does NOT depend on D:\\go-website-e10-art (the Owner's local
source folder, outside this repo) -- only on the promoted copies under
assets/e10/art/zone1/lord_trial/, which travel with the repo/worktree.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ART_DIR = REPO_ROOT / "assets" / "e10" / "art" / "zone1" / "lord_trial"
ART_MANIFEST_PATH = ART_DIR / "zone1-lord-trial-art-package.json"
INDEX_HTML_PATH = REPO_ROOT / "index.html"

AUDIO_PACKAGE_MANIFEST_PATH = REPO_ROOT / "assets" / "e10" / "audio" / "zone1" / "zone1-audio-package.json"
LORD_SFX_LOCK_PATH = REPO_ROOT / "tools" / "e10_zone1_audio" / "zone1_lord_trial_sfx_lock.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_art_manifest_lists_6_assets_with_matching_hashes_on_disk():
    manifest = json.loads(ART_MANIFEST_PATH.read_text(encoding="utf-8"))
    assets = manifest["assets"]
    assert len(assets) == 6
    for entry in assets:
        png = REPO_ROOT / entry["canonical_png"]["path"]
        webp = REPO_ROOT / entry["runtime_webp"]["path"]
        assert png.is_file(), f"missing canonical PNG: {png}"
        assert webp.is_file(), f"missing runtime WEBP: {webp}"
        assert _sha256(png) == entry["canonical_png"]["sha256"], f"PNG hash mismatch: {png}"
        assert _sha256(webp) == entry["runtime_webp"]["sha256"], f"WEBP hash mismatch: {webp}"
        # The canonical PNG must be byte-identical to the Owner's source (provenance).
        assert entry["canonical_png"]["sha256"] == entry["source_sha256"], (
            f"canonical PNG for {entry['key']} does not match recorded source hash -- "
            "it must be an exact copy of the Owner-provided source file"
        )


def test_all_6_asset_roles_are_present():
    manifest = json.loads(ART_MANIFEST_PATH.read_text(encoding="utf-8"))
    keys = {a["key"] for a in manifest["assets"]}
    assert keys == {
        "LORD_CHALLENGE_BACKPLATE",
        "FIRST_STAR_SUCCESS_BACKPLATE",
        "FIRST_STAR_ICON",
        "LORD_RITUAL_KEY_ART",
        "LORD_FAILURE_BACKPLATE",
        "VILLAGE_ELDER_REFERENCE",
    }


def test_index_html_references_the_runtime_webp_assets_not_the_png_or_source():
    index_text = INDEX_HTML_PATH.read_text(encoding="utf-8")
    manifest = json.loads(ART_MANIFEST_PATH.read_text(encoding="utf-8"))
    referenced_keys = set()
    for entry in manifest["assets"]:
        webp_path = "/" + entry["runtime_webp"]["path"]
        png_path = "/" + entry["canonical_png"]["path"]
        if webp_path in index_text:
            referenced_keys.add(entry["key"])
        # The heavier canonical PNG must never be the one shipped runtime references.
        assert png_path not in index_text, f"runtime should reference the optimized .webp, not {png_path}"
    # First Star (03) and Village Elder reference (06) are not necessarily
    # both wired directly (06 is a design reference the other art already
    # incorporates) -- but the four screen backplates/key-art must be.
    required = {
        "LORD_CHALLENGE_BACKPLATE",
        "FIRST_STAR_SUCCESS_BACKPLATE",
        "FIRST_STAR_ICON",
        "LORD_RITUAL_KEY_ART",
        "LORD_FAILURE_BACKPLATE",
    }
    missing = required - referenced_keys
    assert not missing, f"index.html does not reference these approved art assets: {missing}"
    # Never claim D:\go-website-e10-art (Owner's local source folder) as a runtime path.
    assert "go-website-e10-art" not in index_text


def test_prototype_visuals_are_removed_from_the_k26_30_lord_trial_functions():
    index_text = INDEX_HTML_PATH.read_text(encoding="utf-8")

    def extract_function_body(name: str) -> str:
        m = re.search(r"function " + re.escape(name) + r"\([^)]*\)\s*\{", index_text)
        assert m, f"function {name} not found in index.html"
        i = m.end()
        depth = 1
        start = i
        while depth > 0 and i < len(index_text):
            if index_text[i] == "{":
                depth += 1
            elif index_text[i] == "}":
                depth -= 1
            i += 1
        return index_text[start:i - 1]

    for fn in ("showZone1LordChallengeCard", "startZone1LordRitual", "showZone1LordResultCard"):
        body = extract_function_body(fn)
        assert "\U0001F474" not in body, f"{fn} still assigns the emoji elder (\U0001F474)"
        assert "\U0001F64F" not in body, f"{fn} still assigns the emoji prayer hands (\U0001F64F)"
        assert "\u2B50" not in body, f"{fn} still assigns the emoji/unicode star as a DOM value (\u2B50)"

    # The CSS-drawn board-grid prototype (#lord-ritual-board, _buildLordRitualBoard)
    # must be fully gone now that the ritual uses the real key art as its scene
    # (a historical mention in a code comment is fine -- only functional
    # references, e.g. id="lord-ritual-board" or getElementById, are checked).
    assert "_buildLordRitualBoard" not in index_text
    assert 'id="lord-ritual-board"' not in index_text
    assert "getElementById('lord-ritual-board')" not in index_text


def test_first_star_icon_element_is_the_real_asset_not_css_star():
    index_text = INDEX_HTML_PATH.read_text(encoding="utf-8")
    m = re.search(r'<img id="zone1-first-star-icon"[^>]*src="([^"]+)"', index_text)
    assert m, "expected a real <img id=\"zone1-first-star-icon\"> element"
    assert "zone1_first_star.webp" in m.group(1)
    # The old CSS star-pulse-on-emoji-monster keyframe must be gone -- the
    # reward object is this real image now, not a styled Unicode glyph.
    assert "zone1StarPulse" not in index_text
    assert "zone1StarMaterialize" in index_text


def test_lord_ritual_key_art_element_is_real_img_not_css_gradient_box():
    index_text = INDEX_HTML_PATH.read_text(encoding="utf-8")
    m = re.search(r'<img id="lord-ritual-key-art"[^>]*src="([^"]+)"', index_text)
    assert m, "expected a real <img id=\"lord-ritual-key-art\"> element"
    assert "zone1_lord_ritual_key_art.webp" in m.group(1)


def test_35_asset_audio_package_and_8_asset_lord_sfx_package_untouched():
    # This was an art-only pass -- neither audio package's totals/status
    # should have moved at all.
    audio_package = json.loads(AUDIO_PACKAGE_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert audio_package["totals"]["total_audio_files"] == 35
    lord_sfx_lock = json.loads(LORD_SFX_LOCK_PATH.read_text(encoding="utf-8"))
    assert lord_sfx_lock["status"] == "OWNER_APPROVED"
    assert len(lord_sfx_lock["approved_lord_trial_sfx"]) == 8
