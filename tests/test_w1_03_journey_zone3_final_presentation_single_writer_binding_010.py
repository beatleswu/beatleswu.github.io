"""W1-03 single-writer Zone 3 presentation integration contracts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "js" / "e9" / "journey_zone3_vertical_slice_content.js"
INDEX = ROOT / "index.html"
SOUND = ROOT / "sound.js"
FX = ROOT / "js" / "e9" / "zone3_presentation_fx.js"
AUDIO_RUNTIME = ROOT / "js" / "e9" / "journey_zone3_presentation_audio.js"
WORLD = ROOT / "assets" / "e10" / "art" / "zone3" / "zone3-world-asset-package.json"
CINEMATIC = ROOT / "assets" / "e10" / "art" / "zone3" / "cinematic" / "zone3-cinematic-asset-package.json"
ZH_SUBTITLES = ROOT / "assets" / "e10" / "i18n" / "zone3" / "zone3-cinematic-subtitles.json"
EN_SUBTITLES = ROOT / "assets" / "e10" / "i18n" / "zone3" / "zone3-cinematic-subtitles-en-US.json"
ZH_AUDIO = ROOT / "assets" / "e10" / "audio" / "zone3" / "zone3-cinematic-audio-manifest.json"
EN_AUDIO = ROOT / "assets" / "e10" / "audio" / "zone3" / "zone3-cinematic-audio-manifest-en-US.json"
PRESENTATION_AUDIO = ROOT / "assets" / "e10" / "audio" / "zone3" / "zone3-presentation-audio-manifest.json"
FX_PACKAGE = ROOT / "docs" / "planning" / "w1_01_world_zone3_presentation_fx_runtime_package_009.json"
FX_HANDOFF = ROOT / "docs" / "planning" / "w1_01_world_zone3_presentation_fx_binding_handoff_010.json"
RUNNER = ROOT / "tests" / "e2e" / "run_w1_03_journey_zone3_final_presentation_single_writer_binding_010.mjs"
INVENTORY = ROOT / "docs" / "planning" / "w1_zone3_final_presentation_candidate_inventory_010.json"

WORLD_HEAD = "fd7a1bcee2a01723a716f20683a4411d593f2dab"
HERO_HEAD = "15cd275b8f4992c30e93d874c45244d87909d334"
JOURNEY_HEAD = "aa5c4c25e50e4cd0843e50cdc685f81cf8337f95"
SYSTEMS_HEAD = "7bf4b5e1e7322e1d925f346c7d7096cee3b50faf"
MASTER = "616d51b17abe010de1e862382ca4db7bec65936f"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normal_path(value: str) -> str:
    return str(value or "").lstrip("/").replace("\\", "/")


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


def test_authority_refs_and_single_writer_runtime_surface_are_exact() -> None:
    content = load_content()
    presentation = content["cinematicPresentation"]
    assert presentation["worldCandidate"] == "39c587a216f6cc13efe572066d9d8f0299960f1b"
    assert content["cinematicPresentation"]["responsiveManifestReconciled"] is True
    assert content["cinematicLocalization"]["supportedLocales"] == ["zh-TW", "en-US"]
    assert content["authority"]["presentation"]["imageFailure"] == "NO_GAMEPLAY_AUTHORITY_CHANGE"
    assert content["authority"]["presentation"]["localeSwitchDoesNotProgress"] is True
    assert content["authority"]["presentation"]["replayDoesNotReward"] is True
    assert INDEX.read_text(encoding="utf-8").count("journey_zone3_presentation_audio.js") == 1
    assert INDEX.read_text(encoding="utf-8").count("zone3_presentation_fx.js") == 1
    assert "GoOdysseyZone3PresentationAudio" in AUDIO_RUNTIME.read_text(encoding="utf-8")


def test_exact_visual_slots_phase_mapping_responsive_and_source_bytes() -> None:
    world = load(WORLD)
    cinematic = load(CINEMATIC)
    content = load_content()["cinematicPresentation"]
    assert len([asset for asset in world["assets"] if asset["TYPE"] == "CINEMATIC_SHOT"]) == 10
    assert len([asset for asset in world["assets"] if asset["TYPE"] in {"WORLD_MAP_LANDMARK", "WORLD_ENVIRONMENT_PLATE"}]) == 2
    assert [shot["shotId"] for shot in content["shots"]] == [f"SHOT{i:02d}" for i in range(1, 11)]
    assert content["lifecycle"] == {
        "FIRST_ENTRY": [f"SHOT{i:02d}" for i in range(1, 6)],
        "BOSS_READY": ["SHOT06", "SHOT07"],
        "POST_CLEAR": ["SHOT08", "SHOT09", "SHOT10"],
    }
    responsive = {item["SHOT"]: item for item in world["responsive_recommendations"]}
    assert sum(item["IPAD_PORTRAIT_GENERIC_CROP_SAFE"] == "YES" for item in responsive.values()) == 2
    assert sum(item["IPAD_PORTRAIT_CUSTOM_POSITION_REQUIRED"] is True for item in responsive.values()) == 2
    assert sum(item["MOBILE_GENERIC_CROP_SAFE"] == "YES" for item in responsive.values()) == 2
    assert sum(item["MOBILE_CUSTOM_POSITION_REQUIRED"] is True for item in responsive.values()) == 2
    bound = {shot["shotId"]: shot for shot in content["shots"]}
    for source in cinematic["shots"]:
        shot = bound[source["SHOT_ID"]]
        assert normal_path(shot["imagePath"]) == source["RUNTIME_PATH"]
        assert shot["sourceSha256"] == source["SOURCE_SHA256"]
        assert shot["runtimeSha256"] == source["RUNTIME_SHA256"]
        assert shot["ownerApproved"] is True
        assert shot["noBakedRuntimeText"] is True
        note = responsive[source["SHOT_ID"]]
        assert shot["ipadPortraitPresentation"]["objectPosition"] == note["IPAD_PORTRAIT_OBJECT_POSITION"]
        assert shot["mobilePresentation"]["objectPosition"] == note["MOBILE_OBJECT_POSITION"]
        for field in ("sourcePath", "imagePath"):
            file_path = ROOT / normal_path(shot[field])
            assert file_path.is_file()
    assert bound["SHOT09"]["ipadPortraitPresentation"]["objectPosition"] == "58% 50%"
    assert bound["SHOT10"]["ipadPortraitPresentation"]["objectPosition"] == "58% 50%"
    assert bound["SHOT09"]["mobilePresentation"]["objectPosition"] == "58% 50%"
    assert bound["SHOT10"]["mobilePresentation"]["objectPosition"] == "58% 50%"
    for source in cinematic["shots"]:
        runtime = ROOT / source["RUNTIME_PATH"]
        assert hashlib.sha256(runtime.read_bytes()).hexdigest() == source["RUNTIME_SHA256"]


def test_both_locales_have_exactly_97_aligned_dialogue_beats_and_no_fallback() -> None:
    content = load_content()
    content_beats = [beat for shot in content["cinematicPresentation"]["shots"] for beat in shot["beats"]]
    assert len(content_beats) == 97
    assert Counter(beat["character"] for beat in content_beats) == Counter({"HERO": 41, "GRIK": 37, "CENTURION": 19})
    assert len({beat["beatId"] for beat in content_beats}) == 97
    assert len({beat["i18nKey"] for beat in content_beats}) == 97
    for subtitle_path, audio_path, locale in (
        (ZH_SUBTITLES, ZH_AUDIO, "zh-TW"),
        (EN_SUBTITLES, EN_AUDIO, "en-US"),
    ):
        subtitles = load(subtitle_path)["beats"]
        entries = load(audio_path)["entries"]
        assert len(subtitles) == len(entries) == 97
        assert all(item["LOCALE"] == locale for item in subtitles + entries)
        assert {item["BEAT_ID"] for item in subtitles} == {beat["beatId"] for beat in content_beats}
        assert {item["BEAT_ID"] for item in entries} == {beat["beatId"] for beat in content_beats}
        subtitle_by_id = {item["BEAT_ID"]: item for item in subtitles}
        audio_by_id = {item["BEAT_ID"]: item for item in entries}
        for beat in content_beats:
            subtitle = subtitle_by_id[beat["beatId"]]
            audio = audio_by_id[beat["beatId"]]
            assert subtitle["I18N_KEY"] == beat["i18nKey"] == audio["I18N_KEY"]
            assert subtitle["CHARACTER"] == beat["character"] == audio["CHARACTER"]
            assert beat["voiceStatusByLocale"][locale] == "OWNER_APPROVED_PRODUCTION"
            assert normal_path(beat["audioPathByLocale"][locale]) == audio["AUDIO_PATH"]
            assert beat["voiceIdByLocale"][locale] == audio["VOICE_ID"]
            assert audio["VOICE_ID"] != ""
        assert load(audio_path)["VOICE_LANGUAGE_MISMATCH"] == "FORBIDDEN"
        assert load(audio_path)["MISSING_LOCALE_VOICE_FALLBACK"] == "SUBTITLE_ONLY"
    assert content["cinematicLocalization"]["crossLocaleVoiceFallback"] == "FORBIDDEN"
    assert content["cinematicLocalization"]["replaySource"] == "same_localized_beat_manifest"


def test_presentation_audio_and_fx_contracts_are_bound_without_new_ui() -> None:
    presentation_audio = load(PRESENTATION_AUDIO)
    cues = presentation_audio["CUES"]
    assert len(cues) == 18
    assert Counter(cue["CATEGORY"] for cue in cues) == Counter(
        {"ambience": 5, "event_sfx": 7, "transition": 1, "bgm": 3}
    ) + Counter({"reusable_sfx": 2})
    assert len({cue["CUE_ID"] for cue in cues}) == 18
    assert len({cue["OUTPUT_PATH"] for cue in cues}) == 18
    assert presentation_audio["COUNTS"]["STONE_SHARD_MAGICAL_SFX_COUNT"] == 0
    assert presentation_audio["COUNTS"]["SHUI_HUMAN_VOICE_COUNT"] == 0
    for cue in cues:
        path = ROOT / cue["OUTPUT_PATH"]
        assert path.is_file()
        data = path.read_bytes()
        assert len(data) == cue["BYTES"]
        assert hashlib.sha256(data).hexdigest() == cue["SHA256"]
        assert cue["DURATION_MS"] > 0
    fx_package = load(FX_PACKAGE)
    fx_handoff = load(FX_HANDOFF)
    assert len(fx_package["EFFECTS"]) == 12
    assert len(fx_package["CAMERA_CUES"]) == 10
    assert len(fx_handoff["SHOT_BINDINGS"]) == 10
    assert fx_handoff["ACCEPTED_IMPLEMENTATION"]["PARALLAX_IMPLEMENTED"] is False
    assert fx_handoff["ACCEPTED_IMPLEMENTATION"]["PARALLAX_CLASSIFICATION"] == (
        "INTENTIONALLY_DIFFERENT_NOT_REQUIRED_FOR_ZONE3_V1"
    )
    index = INDEX.read_text(encoding="utf-8")
    sound = SOUND.read_text(encoding="utf-8")
    audio_runtime = AUDIO_RUNTIME.read_text(encoding="utf-8")
    assert "go-odyssey-audio-mute-changed" in sound
    assert "GLOBAL_MUTE" not in audio_runtime
    assert "newVolumeControlUi: false" in audio_runtime
    assert "go-odyssey-audio-mute-changed" in audio_runtime
    assert "_zone3PresentationAudio" in index
    assert "_stopZone3PresentationRuntime" in index
    assert "enterShot(shotId" in index
    assert "audio.muted = isZone3Presentation" in index
    assert "Z3_BGM_DISCOVERY" in audio_runtime
    assert "Z3_BGM_ESCALATION" in audio_runtime
    assert "Z3_BGM_RECOVERY" in audio_runtime


def test_dialogue_is_not_embedded_in_runtime_and_authority_boundaries_are_read_only() -> None:
    subtitles = load(ZH_SUBTITLES)["beats"]
    runtime = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (INDEX, CONTENT, ROOT / "js" / "e9" / "journey_zone3_vertical_slice.js", ROOT / "js" / "e9" / "journey_zone3_vertical_slice_view.js", AUDIO_RUNTIME)
    )
    for beat in subtitles:
        if beat["VISIBLE_TEXT"] == "好。":
            continue
        assert beat["VISIBLE_TEXT"] not in runtime
    assert "zone3-cinematic-subtitles.json" in runtime
    assert "same_localized_beat_manifest" in runtime
    audio_code = AUDIO_RUNTIME.read_text(encoding="utf-8")
    assert "fetch(" not in audio_code
    assert "/api/" not in audio_code
    assert "presentationOnly: true" in audio_code
    assert "BATTLEFIELD_BOSS" in CONTENT.read_text(encoding="utf-8")
    assert "LORD" in CONTENT.read_text(encoding="utf-8")
    changed = subprocess.check_output(["git", "diff", "--name-only", MASTER, "--"], cwd=ROOT, text=True)
    changed_paths = set(changed.splitlines())
    assert "app.py" not in changed_paths
    assert "sw.js" not in changed_paths
    assert "js/game/cinematic_replay.js" not in changed_paths
    assert not any(path.startswith("migrations/") or path.startswith("db/") for path in changed_paths)


def test_final_candidate_inventory_is_complete_and_hashes_current_bytes() -> None:
    inventory = load(INVENTORY)
    assert inventory["CANDIDATE_BASE"] == MASTER
    assert inventory["PATH_COUNT"] == 351
    assert inventory["OVERLAP_PATH_COUNT"] == 22
    assert inventory["BYTE_IDENTICAL_OVERLAP_COUNT"] == 22
    assert inventory["AUTHORIZED_SUCCESSOR_OVERLAP_COUNT"] == 0
    assert inventory["UNRESOLVED_OVERLAP_COUNT"] == 0
    assert inventory["UNRELATED_SOURCE_PATH_COUNT"] == 0
    expected = {
        "sound.js",
        "js/e9/journey_zone3_presentation_audio.js",
        "tests/e2e/fixtures/w1_03_journey_zone3_final_presentation_single_writer_binding_010.html",
        "tests/e2e/run_w1_03_journey_zone3_final_presentation_single_writer_binding_010.mjs",
        "tests/test_w1_03_journey_zone3_final_presentation_single_writer_binding_010.py",
    }
    for head in (WORLD_HEAD, HERO_HEAD, JOURNEY_HEAD, SYSTEMS_HEAD):
        output = subprocess.check_output(
            ["git", "-c", "core.quotePath=false", "diff", "--name-only", MASTER, head, "--"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        )
        expected.update(item.replace("\\", "/") for item in output.splitlines() if item)
    entries = {entry["PATH"]: entry for entry in inventory["ENTRIES"]}
    assert set(entries) == expected
    for entry in entries.values():
        path = ROOT / entry["PATH"]
        data = path.read_bytes()
        assert entry["BYTES"] == len(data)
        assert entry["SHA256"] == hashlib.sha256(data).hexdigest()
        assert entry["SOURCE_LANE"]
        assert entry["ROLE"] in {"PRODUCT_RUNTIME", "PRODUCT_ASSET", "MANIFEST", "I18N", "AUDIO", "TEST", "DOC"}


def test_real_browser_runner_passes_all_viewports_and_cleanup_contracts() -> None:
    env = os.environ.copy()
    env["PLAYWRIGHT_CORE_PATH"] = str(Path("D:/go-website/node_modules/playwright-core"))
    result = subprocess.run(
        ["node", str(RUNNER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    output = result.stdout
    for label in ("DESKTOP", "IPAD_LANDSCAPE", "IPAD_PORTRAIT", "MOBILE_PORTRAIT", "REDUCED_MOTION", "INTEGRATED_SHELL_BINDING", "BROWSER_QA"):
        assert f"{label}=PASS" in output, output
    assert "LIFECYCLE_STRESS_ITERATIONS=50" in output
    assert "ORPHAN_RESOURCE_COUNT=0" in output
