"""E10-Z1-AUDIO-PRODUCTION-001 -- final audio package governance.

Covers the promoted assets/e10/audio/zone1/ package (28 dialogue + 2 BGM +
1 ambience + 4 SFX = 35 files): every file the package manifest and the
sound-design lock record, every hash matches the actual file on disk, and
the rejected BGM audition candidates are never referenced by the runtime
(index.html) or by the canonical package manifest.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIO_ROOT = REPO_ROOT / "assets" / "e10" / "audio" / "zone1"
PACKAGE_MANIFEST_PATH = AUDIO_ROOT / "zone1-audio-package.json"
SOUND_LOCK_PATH = REPO_ROOT / "tools" / "e10_zone1_audio" / "zone1_sound_design_lock.json"
TTS_LOCK_PATH = REPO_ROOT / "tools" / "e10_zone1_audio" / "zone1_final_tts_lock.json"
INDEX_HTML_PATH = REPO_ROOT / "index.html"

REJECTED_BGM_FILES = [
    "02_BGM_main_theme_B_strings_led.mp3",
    "03_BGM_post_clear_urgency_A_tremolo_pulse.mp3",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_package_manifest_totals_are_35():
    package = json.loads(PACKAGE_MANIFEST_PATH.read_text(encoding="utf-8"))
    totals = package["totals"]
    assert totals["dialogue_files"] == 28
    assert totals["bgm_files"] == 2
    assert totals["ambience_files"] == 1
    assert totals["sfx_files"] == 4
    assert totals["total_audio_files"] == 35


def test_every_package_manifest_file_exists_and_hash_matches_disk():
    package = json.loads(PACKAGE_MANIFEST_PATH.read_text(encoding="utf-8"))
    checked = 0
    for section in ("dialogue",):
        for entry in package[section]["files"]:
            path = REPO_ROOT / entry["path"]
            assert path.is_file(), f"{entry['path']} listed in package manifest but missing on disk"
            assert path.stat().st_size == entry["size_bytes"]
            assert _sha256(path) == entry["sha256"], f"hash mismatch for {entry['path']}"
            checked += 1
    for section in ("bgm", "ambience", "sfx"):
        for cue in package[section]["cues"]:
            entry = cue["file"]
            path = REPO_ROOT / entry["path"]
            assert path.is_file(), f"{entry['path']} listed in package manifest but missing on disk"
            assert path.stat().st_size == entry["size_bytes"]
            assert _sha256(path) == entry["sha256"], f"hash mismatch for {entry['path']}"
            checked += 1
    assert checked == 35


def test_package_manifest_hashes_match_the_sound_design_lock():
    package = json.loads(PACKAGE_MANIFEST_PATH.read_text(encoding="utf-8"))
    lock = json.loads(SOUND_LOCK_PATH.read_text(encoding="utf-8"))
    assert lock["status"] == "OWNER_APPROVED"

    approved_bgm = {c["file"]["filename"] for c in package["bgm"]["cues"]}
    approved_ambience = {c["file"]["filename"] for c in package["ambience"]["cues"]}
    approved_sfx = {c["file"]["filename"] for c in package["sfx"]["cues"]}
    assert approved_bgm == set(lock["approved_bgm"])
    assert approved_ambience == set(lock["approved_ambience"])
    assert approved_sfx == set(lock["approved_sfx"])


def test_package_manifest_hashes_match_the_final_tts_lock():
    package = json.loads(PACKAGE_MANIFEST_PATH.read_text(encoding="utf-8"))
    tts_lock = json.loads(TTS_LOCK_PATH.read_text(encoding="utf-8"))
    assert tts_lock["status"] == "OWNER_APPROVED_28_OF_28"
    lock_hashes = {f["filename"]: f["sha256"] for f in tts_lock["files"]}
    package_hashes = {e["filename"]: e["sha256"] for e in package["dialogue"]["files"]}
    assert lock_hashes == package_hashes


def test_rejected_bgm_candidates_never_referenced_as_active_assets():
    # A rejected candidate's filename MAY appear as documentary history
    # (e.g. package manifest's "rejected_variants" note, lock's
    # "rejected_bgm_audition_files" list) -- what must never happen is it
    # being referenced as an actual asset path (a real /assets/... file
    # reference, or listed under approved_bgm).
    index_text = INDEX_HTML_PATH.read_text(encoding="utf-8")
    package = json.loads(PACKAGE_MANIFEST_PATH.read_text(encoding="utf-8"))
    lock = json.loads(SOUND_LOCK_PATH.read_text(encoding="utf-8"))

    package_asset_paths = {c["file"]["filename"] for c in package["bgm"]["cues"]}
    package_asset_paths |= {c["file"]["filename"] for c in package["ambience"]["cues"]}
    package_asset_paths |= {c["file"]["filename"] for c in package["sfx"]["cues"]}
    package_asset_paths |= {e["filename"] for e in package["dialogue"]["files"]}

    for rejected in REJECTED_BGM_FILES:
        assert rejected not in index_text, f"rejected BGM candidate {rejected} is referenced in index.html"
        assert rejected not in package_asset_paths, f"rejected BGM candidate {rejected} is listed as an active asset in the package manifest"
        assert rejected not in lock["approved_bgm"], f"rejected BGM candidate {rejected} is listed as approved in the sound design lock"


def test_index_html_zone1_audio_references_resolve_to_existing_promoted_files():
    index_text = INDEX_HTML_PATH.read_text(encoding="utf-8")
    referenced = set(re.findall(r"/assets/e10/audio/zone1/[\w/.-]+\.mp3", index_text))
    assert referenced, "expected at least one /assets/e10/audio/zone1/*.mp3 reference in index.html"
    missing = [r for r in referenced if not (REPO_ROOT / r.lstrip("/")).is_file()]
    assert not missing, f"index.html references non-existent audio files: {missing}"


def test_index_html_zone1_dialogue_references_are_locale_correct():
    # Every zh-locale beat in the k26_30 config block must reference a
    # _zh_ dialogue file, every en-locale beat a _en_ file -- no
    # cross-language fallback wiring.
    index_text = INDEX_HTML_PATH.read_text(encoding="utf-8")
    start = index_text.index("if (zone?.key === 'k26_30')")
    end = index_text.index("if (zone?.key === 'k26_30')", start + 1)
    block = index_text[start:end]
    en_start = block.index("isEnglish")
    zh_block = block[block.index("return {", en_start + 500):] if False else None
    # Simpler: split on the two `return {` blocks inside this section.
    returns = [m.start() for m in re.finditer(r"return \{", block)]
    assert len(returns) >= 2
    en_block = block[returns[0]:returns[1]]
    zh_block = block[returns[1]:]
    en_dialogue_refs = re.findall(r"/assets/e10/audio/zone1/dialogue/[\w.-]+\.mp3", en_block)
    zh_dialogue_refs = re.findall(r"/assets/e10/audio/zone1/dialogue/[\w.-]+\.mp3", zh_block)
    assert en_dialogue_refs, "expected dialogue audioSrc references in the English k26_30 branch"
    assert zh_dialogue_refs, "expected dialogue audioSrc references in the zh-TW k26_30 branch"
    assert all("_en_" in ref for ref in en_dialogue_refs), f"non-English dialogue file referenced in English branch: {en_dialogue_refs}"
    assert all("_zh_" in ref for ref in zh_dialogue_refs), f"non-zh dialogue file referenced in zh-TW branch: {zh_dialogue_refs}"


# --- E10 Zone 1 Beginner Village Complete RPG Journey (2026-08-09) ---
# Lord Trial SFX: an audition pack, completely separate from the locked
# 35-asset package above, that Gate A promoted to its own canonical
# sub-package after the Owner approved all 8 candidates (2026-08-10).

LORD_TRIAL_SFX_AUDITION_DIR = REPO_ROOT / "tools" / "e10_zone1_audio" / "_local_review" / "lord_trial_sfx"
LORD_TRIAL_SFX_BRIEF_PATH = REPO_ROOT / "tools" / "e10_zone1_audio" / "zone1_lord_trial_sfx_brief.json"
LORD_TRIAL_SFX_LOCK_PATH = REPO_ROOT / "tools" / "e10_zone1_audio" / "zone1_lord_trial_sfx_lock.json"
LORD_TRIAL_SFX_CANONICAL_DIR = AUDIO_ROOT / "lord_trial"
LORD_TRIAL_SFX_MANIFEST_PATH = LORD_TRIAL_SFX_CANONICAL_DIR / "zone1-lord-trial-sfx-package.json"


def test_lord_trial_sfx_audition_pack_exists_and_is_non_empty():
    brief = json.loads(LORD_TRIAL_SFX_BRIEF_PATH.read_text(encoding="utf-8"))
    assert len(brief["sfx"]) == 8
    files = sorted(LORD_TRIAL_SFX_AUDITION_DIR.glob("*.mp3"))
    assert len(files) == 8, f"expected 8 Lord Trial SFX audition candidates, found {len(files)}"
    for f in files:
        assert f.stat().st_size > 0, f"{f.name} is empty"


def test_lord_trial_sfx_lock_is_owner_approved_with_8_files():
    lock = json.loads(LORD_TRIAL_SFX_LOCK_PATH.read_text(encoding="utf-8"))
    assert lock["status"] == "OWNER_APPROVED"
    assert len(lock["approved_lord_trial_sfx"]) == 8


def test_lord_trial_sfx_canonical_files_exist_and_hashes_match_manifest_and_lock():
    manifest = json.loads(LORD_TRIAL_SFX_MANIFEST_PATH.read_text(encoding="utf-8"))
    lock = json.loads(LORD_TRIAL_SFX_LOCK_PATH.read_text(encoding="utf-8"))
    cues = manifest["lord_trial_sfx"]["cues"]
    assert len(cues) == 8
    manifest_filenames = set()
    for cue in cues:
        entry = cue["file"]
        path = REPO_ROOT / entry["path"]
        assert path.is_file(), f"{entry['path']} listed in Lord Trial SFX manifest but missing on disk"
        assert path.stat().st_size == entry["size_bytes"]
        assert _sha256(path) == entry["sha256"], f"hash mismatch for {entry['path']}"
        manifest_filenames.add(entry["filename"])
    assert manifest_filenames == set(lock["approved_lord_trial_sfx"])


def test_lord_trial_sfx_candidates_are_promoted_via_canonical_path_only():
    # Gate A passed and these 8 are now legitimately wired -- but only via
    # the canonical assets/e10/audio/zone1/lord_trial/ path recorded in the
    # lock/manifest, never by referencing the local audition directory
    # directly from shipped runtime code.
    index_text = INDEX_HTML_PATH.read_text(encoding="utf-8")
    manifest = json.loads(LORD_TRIAL_SFX_MANIFEST_PATH.read_text(encoding="utf-8"))
    canonical_filenames = {cue["file"]["filename"] for cue in manifest["lord_trial_sfx"]["cues"]}
    assert canonical_filenames, "expected the Lord Trial SFX manifest to list cues for this check to be meaningful"
    for filename in canonical_filenames:
        assert filename in index_text, f"approved Lord Trial SFX {filename} is not referenced in index.html"
    assert "/lord_trial_sfx/" not in index_text, "index.html must reference the canonical /lord_trial/ path, not the local audition directory"


def test_lord_trial_sfx_pack_does_not_touch_the_locked_35_asset_package():
    # The existing 35-asset package manifest/hashes must be completely
    # unaffected by promoting this new, separate SFX category.
    package = json.loads(PACKAGE_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert package["totals"]["total_audio_files"] == 35
    lock = json.loads(SOUND_LOCK_PATH.read_text(encoding="utf-8"))
    assert lock["status"] == "OWNER_APPROVED"
    assert len(lock["approved_bgm"]) == 2
    assert len(lock["approved_ambience"]) == 1
    assert len(lock["approved_sfx"]) == 4
