"""Contracts for the Owner-provided Zone 2 Lord Trial visual integration."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
PACKAGE = ROOT / "assets/e10/art/zone2/lord_trial/zone2-lord-trial-art-package.json"
MANIFEST = ROOT / "deploy/canonical-e10-zone2-lord-trial-art-pack-manifest.json"
INVENTORY = ROOT / "deploy/live-static-asset-inventory.json"


EXPECTED_ROLES = {
    "LORD_RITUAL_KEY_ART": "assets/e10/art/zone2/lord_trial/zone2_lord_ritual_key_art.webp",
    "LORD_CHALLENGE_BACKPLATE": "assets/e10/art/zone2/lord_trial/zone2_lord_challenge_backplate.webp",
    "LORD_FAILURE_BACKPLATE": "assets/e10/art/zone2/lord_trial/zone2_lord_failure_backplate.webp",
    "FIRST_STAR_SUCCESS_BACKPLATE": "assets/e10/art/zone2/lord_trial/zone2_first_star_success_backplate.webp",
    "SUCCESS_LORD_PORTRAIT": "assets/e10/art/zone2/lord_trial/zone2_success_lord_portrait.webp",
    "LORD_PORTRAIT": "assets/e10/art/zone2/lord_trial/zone2_lord_portrait.webp",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_zone2_lord_trial_package_maps_all_six_owner_assets():
    package = _load(PACKAGE)
    assets = {entry["key"]: entry for entry in package["assets"]}
    assert package["status"] == "OWNER_PROVIDED_PRODUCTION_ART"
    assert len(assets) == 6
    assert set(assets) == set(EXPECTED_ROLES)
    for key, expected_path in EXPECTED_ROLES.items():
        entry = assets[key]
        runtime = entry["runtime_webp"]
        assert runtime["path"] == expected_path
        source = ROOT / expected_path
        assert source.is_file(), expected_path
        assert runtime["mime"] == "image/webp"
        assert runtime["size_bytes"] == source.stat().st_size
        assert runtime["sha256"] == _sha256(source)
        canonical = entry["canonical_source"]
        canonical_source = ROOT / canonical["path"]
        assert canonical_source.is_file(), canonical["path"]
        assert canonical["path"].endswith(".jpg")
        assert canonical["size_bytes"] == canonical_source.stat().st_size
        assert canonical["sha256"] == _sha256(canonical_source)
        assert entry["source_sha256"] == canonical["sha256"]


def test_zone2_lord_trial_manifest_is_exactly_six_sorted_webps():
    manifest = _load(MANIFEST)
    files = manifest["files"]
    assert manifest["total_files"] == len(files) == 6
    assert [item["path"] for item in files] == sorted(EXPECTED_ROLES.values())
    assert {item["path"] for item in files} == set(EXPECTED_ROLES.values())
    assert manifest["total_bytes"] == sum(item["size"] for item in files)
    for item in files:
        source = ROOT / item["path"]
        assert source.is_file(), item["path"]
        assert item["mime"] == "image/webp"
        assert item["size"] == source.stat().st_size
        assert item["sha256"] == _sha256(source)


def test_zone2_lord_trial_manifest_is_wired_as_disjoint_inventory_subtree():
    inventory = _load(INVENTORY)
    entries = inventory["required_subtrees"]["entries"]
    entry = next(item for item in entries if item["prefix"] == "assets/e10/art/zone2/lord_trial/")
    assert entry["manifest"] == "deploy/canonical-e10-zone2-lord-trial-art-pack-manifest.json"
    prefixes = [item["prefix"] for item in entries]
    assert prefixes.count("assets/e10/art/zone2/lord_trial/") == 1


def test_zone2_lord_trial_runtime_references_only_governed_webps():
    text = INDEX.read_text(encoding="utf-8")
    refs = set(re.findall(r"/assets/e10/art/zone2/lord_trial/[A-Za-z0-9_.-]+\.webp", text))
    assert {path.lstrip("/") for path in refs} == set(EXPECTED_ROLES.values())
    assert not re.search(r"/assets/e10/art/zone2/lord_trial/[^\"']+\.jpe?g", text, re.I)


def test_zone2_lord_trial_states_bind_assets_without_flattening_interaction():
    text = INDEX.read_text(encoding="utf-8")
    required = (
        "showZone2LordChallengeCard",
        "startZone2LordRitual",
        "showZone2LordResultCard",
        "overlay.dataset.zoneKey = zone.key || ''",
        "_startBossBattleNow(zone)",
        "background-image: url('/assets/e10/art/zone2/lord_trial/zone2_lord_challenge_backplate.webp')",
        "background-image: url('/assets/e10/art/zone2/lord_trial/zone2_first_star_success_backplate.webp')",
        "background-image: url('/assets/e10/art/zone2/lord_trial/zone2_lord_failure_backplate.webp')",
        "content: url('/assets/e10/art/zone2/lord_trial/zone2_lord_ritual_key_art.webp')",
        "zone2-lord-portrait",
        "zone2-success-lord-portrait",
    )
    for needle in required:
        assert needle in text, needle
    # E10_ZONE_GENERIC_CINEMATIC_REPLAY_001: the trigger now carries the replay
    # flag so a repeat Lord win still presents the post-victory story while
    # repeating no progression.
    assert "_triggerZone2PostClearFromBossWin(zone, { replay: result.replay === true })" in text
    assert "result-zone2-win" in text and "result-zone2-fail" in text


def test_zone2_lord_trial_responsive_contract_is_scoped_to_required_viewports():
    text = INDEX.read_text(encoding="utf-8")
    assert "@media (max-width: 600px), (max-height: 700px)" in text
    assert "width: 94vw" in text
    assert "max-height: 88dvh" in text
    assert "aspect-ratio: 1 / 1.28" in text
    assert "width: min(88vw, 520px)" in text
    assert "#boss-cinematic {" in text and "box-sizing: border-box" in text
    assert "width: min(760px, 100%)" in text
    assert "grid-template-columns: minmax(0, 1fr)" in text
    assert "white-space: normal" in text
    assert "boss-cinematic-scene::before" in text
    # Interactive controls stay DOM buttons; the new visual layer must not
    # replace the existing CTA with a baked image map.
    assert 'id="boss-cinematic-btn"' in text
    assert 'id="boss-cinematic-cancel-btn"' in text


def test_zone2_lord_trial_numbers_are_server_authoritative_not_preview_values():
    text = INDEX.read_text(encoding="utf-8")
    challenge = text[text.index("function showZone2LordChallengeCard") : text.index("\nfunction _zone2LordTrialAuthority")]
    authority = text[text.index("function _zone2LordTrialAuthority") : text.index("\nfunction startZone2LordRitual")]
    finish_start = text.index("} else if (finishedZone?.key === 'k21_25')")
    finish = text[finish_start : text.index("            } else {", finish_start)]
    result_start = text.index("function showZone2LordResultCard")
    result = text[result_start : text.index("\nasync function showBossResultCinematic", result_start)]

    for field in ("zone?.boss_exam_size", "zone?.boss_pass_score", "zone?.cooldown_required"):
        assert field in authority
    assert "_zone2LordTrialAuthority(zone)" in challenge
    assert "Number(data.total)" in finish
    assert "Number(data.pass_score)" in finish
    assert "Number(data.cooldown_left)" in finish
    assert "_zone2LordTrialAuthority" in result
    assert "authoritySource = '/api/adventure/progress'" in challenge
    assert "authoritySource = '/api/adventure/boss/finish'" in result
    assert "omitting the affected rule" in text
    # These literals may remain in the shared Zone 1/generic implementation,
    # but must not be fallback preview values in Zone 2's card/result blocks.
    for block in (challenge, result):
        assert "|| 20" not in block
        assert "|| 16" not in block
        assert "|| 30" not in block


def test_zone2_lord_trial_copy_has_no_authoritative_baked_title_dependency():
    text = INDEX.read_text(encoding="utf-8")
    challenge_css = text[text.index("#boss-cinematic.phase-lord-card[data-zone-key=\"k21_25\"]") : text.index(".adventure-ritual-toast")]
    assert "zone2-lord-card-plaque-title" in challenge_css
    assert "display: none" in challenge_css
    assert "soft shield hides it behind the live portrait" in challenge_css


def test_zone2_lord_trial_portrait_alignment_is_large_lower_and_ring_bound():
    text = INDEX.read_text(encoding="utf-8")
    alignment = text[text.index("Owner-approved portrait alignment") : text.index(".adventure-ritual-toast")]
    assert "top: 34%;" in alignment
    assert "width: 32%;" in alignment
    assert "width: 40%;" in alignment
    assert "width: 42%;" in alignment
    assert "@media (min-width: 420px) and (max-width: 480px)" in alignment
    assert "top: 30%;" in alignment
    assert "transform: translate(-50%, -50%);" in alignment
    assert "#zone2-lord-portrait" in alignment
    assert "#zone2-success-lord-portrait" in alignment
    assert "z-index: 4;" in alignment
