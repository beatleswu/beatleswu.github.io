"""W1_03 Zone 3 WORLD cinematic asset-slot and responsive binding contracts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = "aa5c4c25e50e4cd0843e50cdc685f81cf8337f95"
CANONICAL_MASTER = "616d51b17abe010de1e862382ca4db7bec65936f"
SOURCE_AUTHORITY_HEADS = (
    "fd7a1bcee2a01723a716f20683a4411d593f2dab",
    "15cd275b8f4992c30e93d874c45244d87909d334",
    "aa5c4c25e50e4cd0843e50cdc685f81cf8337f95",
    "7bf4b5e1e7322e1d925f346c7d7096cee3b50faf",
)
INTEGRATION_PATHS = {
    "sound.js",
    "js/e9/journey_zone3_presentation_audio.js",
    "tests/e2e/fixtures/w1_03_journey_zone3_final_presentation_single_writer_binding_010.html",
    "tests/e2e/run_w1_03_journey_zone3_final_presentation_single_writer_binding_010.mjs",
    "tests/test_w1_03_journey_zone3_final_presentation_single_writer_binding_010.py",
    "docs/planning/w1_zone3_final_presentation_candidate_inventory_010.json",
}
WORLD_CANDIDATE = "39c587a216f6cc13efe572066d9d8f0299960f1b"
WORLD_MANIFEST = ROOT / "assets" / "e10" / "art" / "zone3" / "zone3-world-asset-package.json"
CINEMATIC_MANIFEST = (
    ROOT / "assets" / "e10" / "art" / "zone3" / "cinematic" / "zone3-cinematic-asset-package.json"
)
CONTENT = ROOT / "js" / "e9" / "journey_zone3_vertical_slice_content.js"
INDEX = ROOT / "index.html"
CSS = ROOT / "css" / "e9" / "zone3_vertical_slice.css"
SUBTITLE = ROOT / "assets" / "e10" / "i18n" / "zone3" / "zone3-cinematic-subtitles.json"
AUDIO = ROOT / "assets" / "e10" / "audio" / "zone3" / "zone3-cinematic-audio-manifest.json"
I18N = ROOT / "i18n.js"
WORLD_STAGE = ROOT / "js" / "e9" / "world_stage.js"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_path(value: str) -> str:
    return value.replace("\\", "/")


def accepted_authority_paths() -> set[str]:
    paths: set[str] = set()
    for head in SOURCE_AUTHORITY_HEADS:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false", "diff", "--name-only", CANONICAL_MASTER, head, "--"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        paths.update(normalized_path(item) for item in result.stdout.splitlines() if item)
    return paths | INTEGRATION_PATHS


def git_bytes(ref: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=ROOT)


def load_content() -> dict:
    bridge = r"""
const fs = require('fs');
const vm = require('vm');
const filename = process.argv[1];
const context = {};
vm.runInNewContext(fs.readFileSync(filename, 'utf8'), context, { filename });
process.stdout.write(JSON.stringify(context.GoOdysseyJourneyZone3Content));
"""
    result = subprocess.run(
        ["node", "-e", bridge, str(CONTENT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(result.stdout)


def normal_path(value: str) -> str:
    return str(value or "").lstrip("/").replace("\\", "/")


def test_world_candidate_is_exact_and_supplies_only_the_ten_cinematic_slots():
    world_rel = "assets/e10/art/zone3/zone3-world-asset-package.json"
    cinematic_rel = "assets/e10/art/zone3/cinematic/zone3-cinematic-asset-package.json"
    assert WORLD_MANIFEST.read_bytes() == git_bytes(WORLD_CANDIDATE, world_rel)
    assert CINEMATIC_MANIFEST.read_bytes() == git_bytes(WORLD_CANDIDATE, cinematic_rel)

    world = load(WORLD_MANIFEST)
    cinematic = load(CINEMATIC_MANIFEST)
    assert cinematic["owner_approved"] is True
    assert cinematic["source_shot_count"] == 10
    assert cinematic["runtime_derivative_count"] == 10
    assert len(cinematic["shots"]) == 10
    assert [shot["SHOT_ID"] for shot in cinematic["shots"]] == [f"SHOT{i:02d}" for i in range(1, 11)]
    assert world["canonical_zone"]["zone_id"] == 3
    assert world["responsive_recommendations"]

    # The map landmark and cave environment plate are WORLD assets, but not
    # cinematic slots.  Only the nested cinematic package may feed these
    # Journey frames.
    cinematic_paths = {shot["RUNTIME_PATH"] for shot in cinematic["shots"]}
    assert all("cinematic/" in path for path in cinematic_paths)
    assert not any("landmark" in path.lower() or "environment" in path.lower() for path in cinematic_paths)


def test_manifest_drives_exact_phase_paths_hashes_and_responsive_matrix():
    world = load(WORLD_MANIFEST)
    cinematic = load(CINEMATIC_MANIFEST)
    content = load_content()
    presentation = content["cinematicPresentation"]
    content_shots = {shot["shotId"]: shot for shot in presentation["shots"]}
    cinematic_shots = {shot["SHOT_ID"]: shot for shot in cinematic["shots"]}
    responsive = {item["SHOT"]: item for item in world["responsive_recommendations"]}

    assert set(content_shots) == {f"SHOT{i:02d}" for i in range(1, 11)}
    assert presentation["lifecycle"] == {
        "FIRST_ENTRY": [f"SHOT{i:02d}" for i in range(1, 6)],
        "BOSS_READY": ["SHOT06", "SHOT07"],
        "POST_CLEAR": [f"SHOT{i:02d}" for i in range(8, 11)],
    }
    assert content["assetSlots"]["zone3Entry"]["status"] == "READY"
    assert content["assetSlots"]["zone3BossReady"]["status"] == "READY"
    assert content["assetSlots"]["zone3PostClear"]["status"] == "READY"

    expected_counts = {
        "ipadPortraitGenericSafe": sum(
            item["IPAD_PORTRAIT_GENERIC_CROP_SAFE"] == "YES" for item in responsive.values()
        ),
        "ipadPortraitCustomPositionRequired": sum(
            bool(item["IPAD_PORTRAIT_CUSTOM_POSITION_REQUIRED"]) for item in responsive.values()
        ),
        "mobileGenericSafe": sum(item["MOBILE_GENERIC_CROP_SAFE"] == "YES" for item in responsive.values()),
        "mobileCustomPositionRequired": sum(
            bool(item["MOBILE_CUSTOM_POSITION_REQUIRED"]) for item in responsive.values()
        ),
    }
    assert expected_counts == {
        "ipadPortraitGenericSafe": 2,
        "ipadPortraitCustomPositionRequired": 2,
        "mobileGenericSafe": 2,
        "mobileCustomPositionRequired": 2,
    }
    assert presentation["responsiveCounts"] == expected_counts

    note_slots = {
        "desktopPresentation": ("DESKTOP_16_9", "DESKTOP_OBJECT_POSITION"),
        "ipadLandscapePresentation": ("IPAD_LANDSCAPE", "IPAD_LANDSCAPE_OBJECT_POSITION"),
        "ipadPortraitPresentation": ("IPAD_PORTRAIT", "IPAD_PORTRAIT_OBJECT_POSITION"),
        "mobilePresentation": ("MOBILE_PORTRAIT", "MOBILE_OBJECT_POSITION"),
    }
    for shot_id, source in cinematic_shots.items():
        bound = content_shots[shot_id]
        world_note = responsive[shot_id]
        assert bound["shotNumber"] == source["SHOT_NUMBER"]
        assert bound["phase"] == source["PHASE"]
        assert bound["imageAssetId"] == f"ZONE3_CINEMATIC_{shot_id}"
        assert normal_path(bound["imagePath"]) == source["RUNTIME_PATH"]
        assert bound["sourcePath"] == source["SOURCE_PATH"]
        assert bound["sourceSha256"] == source["SOURCE_SHA256"]
        assert bound["runtimeSha256"] == source["RUNTIME_SHA256"]
        assert bound["ownerApproved"] is True
        assert bound["noBakedRuntimeText"] is True
        for field, (nested_key, top_key) in note_slots.items():
            slot = bound[field]
            note = source["RESPONSIVE_NOTES"][nested_key]
            assert slot["mode"] == note["MODE"].lower()
            assert slot["objectPosition"] == world_note[top_key]
        assert bound["ipadPortraitPresentation"]["genericSafe"] == (
            world_note["IPAD_PORTRAIT_GENERIC_CROP_SAFE"] == "YES"
        )
        assert bound["ipadPortraitPresentation"]["customPositionRequired"] is bool(
            world_note["IPAD_PORTRAIT_CUSTOM_POSITION_REQUIRED"]
        )
        assert bound["mobilePresentation"]["genericSafe"] == (world_note["MOBILE_GENERIC_CROP_SAFE"] == "YES")
        assert bound["mobilePresentation"]["customPositionRequired"] is bool(
            world_note["MOBILE_CUSTOM_POSITION_REQUIRED"]
        )

    assert content_shots["SHOT09"]["ipadPortraitPresentation"]["objectPosition"] == "58% 50%"
    assert content_shots["SHOT10"]["ipadPortraitPresentation"]["objectPosition"] == "58% 50%"
    assert content_shots["SHOT09"]["mobilePresentation"]["objectPosition"] == "58% 50%"
    assert content_shots["SHOT10"]["mobilePresentation"]["objectPosition"] == "58% 50%"


def test_world_asset_bytes_and_runtime_derivatives_match_manifest_hashes():
    cinematic = load(CINEMATIC_MANIFEST)
    for shot in cinematic["shots"]:
        source = ROOT / shot["SOURCE_PATH"]
        runtime = ROOT / shot["RUNTIME_PATH"]
        assert source.is_file()
        assert runtime.is_file()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == shot["SOURCE_SHA256"]
        assert hashlib.sha256(runtime.read_bytes()).hexdigest() == shot["RUNTIME_SHA256"]
        assert source.read_bytes() == git_bytes(WORLD_CANDIDATE, shot["SOURCE_PATH"])
        assert runtime.read_bytes() == git_bytes(WORLD_CANDIDATE, shot["RUNTIME_PATH"])


def test_localized_beats_and_voice_sources_remain_bound_to_the_same_97_identities():
    content = load_content()
    subtitles = load(SUBTITLE)
    audio = load(AUDIO)
    content_beats = [beat for shot in content["cinematicPresentation"]["shots"] for beat in shot["beats"]]
    subtitle_by_id = {beat["BEAT_ID"]: beat for beat in subtitles["beats"]}
    audio_by_id = {beat["BEAT_ID"]: beat for beat in audio["entries"]}

    assert len(content_beats) == 97
    assert sum(beat["character"] == "HERO" for beat in content_beats) == 41
    assert sum(beat["character"] == "GRIK" for beat in content_beats) == 37
    assert sum(beat["character"] == "CENTURION" for beat in content_beats) == 19
    assert len({beat["beatId"] for beat in content_beats}) == 97
    assert len({beat["i18nKey"] for beat in content_beats}) == 97
    assert set(subtitle_by_id) == {beat["beatId"] for beat in content_beats}
    for beat in content_beats:
        subtitle = subtitle_by_id[beat["beatId"]]
        voice = audio_by_id[beat["beatId"]]
        assert beat["i18nKey"] == subtitle["I18N_KEY"] == voice["I18N_KEY"]
        assert beat["locale"] == subtitle["LOCALE"] == voice["LOCALE"] == "zh-TW"
        assert beat["character"] == subtitle["CHARACTER"] == voice["CHARACTER"]
        if beat["character"] == "HERO":
            expected_voice = "XXxvxx0YUt8icTEFE3c6"
        else:
            expected_voice = {
                "GRIK": "DSyEP4HEaCKur8rFFOri",
                "CENTURION": "BrbEfHMQu0fyclQR7lfh",
            }[beat["character"]]
        assert beat["voiceStatus"] == "OWNER_APPROVED_PRODUCTION"
        assert beat["voiceId"] == voice["VOICE_ID"] == expected_voice
        assert normal_path(beat["audioPath"]) == voice["AUDIO_PATH"]

    assert content["cinematicLocalization"]["replaySource"] == "same_localized_beat_manifest"
    assert content["cinematicPresentation"]["subtitleBeatSource"].endswith(
        "assets/e10/i18n/zone3/zone3-cinematic-subtitles.json"
    )
    assert content["cinematicPresentation"]["voiceBeatSource"].endswith(
        "assets/e10/audio/zone3/zone3-cinematic-audio-manifest.json"
    )


def test_voice_fallback_and_image_failure_are_presentation_only():
    content = load_content()
    index = INDEX.read_text(encoding="utf-8")
    world_stage = WORLD_STAGE.read_text(encoding="utf-8")

    assert content["cinematicLocalization"]["missingVoicePolicy"] == "SUBTITLE_ONLY"
    assert content["cinematicLocalization"]["crossLocaleVoiceFallback"] == "FORBIDDEN"
    assert content["cinematicLocalization"]["shuiHumanDialogue"] is False
    assert content["authority"]["presentation"]["imageFailure"] == "NO_GAMEPLAY_AUTHORITY_CHANGE"
    assert content["authority"]["presentation"]["localeSwitchDoesNotProgress"] is True
    assert content["authority"]["presentation"]["replayDoesNotReward"] is True
    assert "function _zone3CinematicTimeline" in index
    assert "allowTtsFallback: false" in index
    assert "crossLocaleVoiceFallback: 'FORBIDDEN'" in index
    assert "zone3-image-load-failed" in index
    failure_start = index.index("img.onerror = () => {")
    failure_end = index.index("};", failure_start) + 2
    failure_handler = index[failure_start:failure_end]
    assert "fetch(" not in failure_handler
    assert "location" not in failure_handler
    assert "reward" not in failure_handler.lower()
    assert "progression" not in failure_handler.lower()
    assert "failed_presentation_only" in failure_handler
    assert "if (zone.key === 'k16_20') return false;" not in world_stage


def test_zone3_runtime_does_not_embed_the_canonical_dialogue_or_old_storyboard():
    subtitles = load(SUBTITLE)
    index = INDEX.read_text(encoding="utf-8")
    content = CONTENT.read_text(encoding="utf-8")
    controller = (ROOT / "js" / "e9" / "journey_zone3_vertical_slice.js").read_text(encoding="utf-8")
    view = (ROOT / "js" / "e9" / "journey_zone3_vertical_slice_view.js").read_text(encoding="utf-8")
    runtime = "\n".join((index, content, controller, view))
    for beat in subtitles["beats"]:
        # The two-character approval response is generic UI vocabulary and
        # exists elsewhere in the application; all substantive Zone 3 lines
        # must remain outside the renderer/controller/view sources.
        if beat["VISIBLE_TEXT"] == "好。":
            continue
        assert beat["VISIBLE_TEXT"] not in runtime
    assert "go_goblin_cave_" not in index
    assert "/assets/storyboards/go_goblin_cave" not in index
    assert "zone3-cinematic-subtitles.json" in content
    assert "assets/e10/art/zone3/cinematic/zone3-cinematic-asset-package.json" in content
    assert "assets/e10/art/zone3/cinematic" not in index
    assert "/assets/e10/audio/zone3" not in index
    assert re.search(r"function getIntroFilmLocaleConfig\(zone\)\s*\{\s*if \(zone\?\.key === 'k16_20'\)", index)


def test_responsive_css_selects_manifest_slots_without_stretching_art():
    css = CSS.read_text(encoding="utf-8")
    assert "--zone3-desktop-object-position" in css
    assert "--zone3-ipad-landscape-object-position" in css
    assert "--zone3-ipad-portrait-object-position" in css
    assert "--zone3-mobile-object-position" in css
    assert "object-fit: var(--zone3-desktop-object-fit, cover)" in css
    assert "object-fit: var(--zone3-ipad-portrait-object-fit, contain)" in css
    assert "object-fit: var(--zone3-mobile-object-fit, contain)" in css
    assert "object-position: var(--zone3-mobile-object-position, 50% 50%)" in css
    assert "@media (orientation: landscape) and (max-width: 900px)" in css
    assert "@media (orientation: portrait) and (max-width: 900px)" in css
    assert "@media (orientation: portrait) and (max-width: 767px)" in css
    assert "transform: scale" not in css
    assert "background-size: 100% 100%" not in css


def test_only_allowed_presentation_paths_changed_from_the_exact_base():
    changed = {
        normalized_path(path)
        for path in subprocess.check_output(
            ["git", "-c", "core.quotePath=false", "diff", "--name-only", BASE, "--"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        ).splitlines()
    }
    unexpected = changed - accepted_authority_paths()
    assert not unexpected, sorted(unexpected)
    assert "app.py" not in changed
    assert "sw.js" not in changed
    assert "js/game/cinematic_replay.js" not in changed
    assert not any(path.startswith("migrations/") or path.startswith("db/") for path in changed)
