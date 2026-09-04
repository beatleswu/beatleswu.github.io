"""Bounded completeness gate for the Zone 3 single-writer candidate.

This gate validates the final Journey binding against the immutable World,
Hero, Audio, and Systems handoffs.  It intentionally does not import
``app.py`` or exercise the whole repository suite.  Browser viewport checks
remain emulation evidence; physical-device acceptance is a later Owner gate.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from zone3_runtime_asset_bindings import (  # noqa: E402
    ZONE3_BATTLEFIELD_BOSS_RUNTIME_ID,
    ZONE3_LORD_ASSET_SLOT_COUNT,
    ZONE3_LORD_ID,
    ZONE3_LORD_PRESENTATION_SLOTS,
    ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS,
    ZONE3_NORMAL_IDS,
    ZONE3_ELITE_COUNT,
)


CANONICAL_MASTER = "616d51b17abe010de1e862382ca4db7bec65936f"
BASE = "1cc89b71296766e16fec6be238156f50ccf868d9"
WORLD_AUTHORITY = "fd7a1bcee2a01723a716f20683a4411d593f2dab"
HERO_AUTHORITY = "15cd275b8f4992c30e93d874c45244d87909d334"
AUDIO_AUTHORITY = "aa5c4c25e50e4cd0843e50cdc685f81cf8337f95"
SYSTEMS_AUTHORITY = "7bf4b5e1e7322e1d925f346c7d7096cee3b50faf"

CINEMATIC_PATH = ROOT / "assets/e10/art/zone3/cinematic/zone3-cinematic-asset-package.json"
WORLD_PATH = ROOT / "assets/e10/art/zone3/zone3-world-asset-package.json"
PRESENTATION_AUDIO_PATH = ROOT / "assets/e10/audio/zone3/zone3-presentation-audio-manifest.json"
SUBTITLE_PATHS = {
    "zh-TW": ROOT / "assets/e10/i18n/zone3/zone3-cinematic-subtitles.json",
    "en-US": ROOT / "assets/e10/i18n/zone3/zone3-cinematic-subtitles-en-US.json",
}
AUDIO_PATHS = {
    "zh-TW": ROOT / "assets/e10/audio/zone3/zone3-cinematic-audio-manifest.json",
    "en-US": ROOT / "assets/e10/audio/zone3/zone3-cinematic-audio-manifest-en-US.json",
}
FX_HANDOFF_PATH = ROOT / "docs/planning/w1_01_world_zone3_presentation_fx_binding_handoff_010.json"
SYSTEMS_CONTRACT_PATH = ROOT / "docs/contracts/w1_04_zone3_final_presentation_binding_contract_006.json"
INDEX_PATH = ROOT / "index.html"
BINDING_PATH = ROOT / "js/e10/zone3_presentation_binding.js"

SHOT_IDS = [f"SHOT{index:02d}" for index in range(1, 11)]
EXPECTED_STORY_FUNCTIONS = [
    "Goblin families move deeper into the cave.",
    "Hero realizes the carried objects are household belongings, not loot.",
    "Hero meets young Grik; mutual caution, no attack.",
    "Grik explains the shrinking living space.",
    "Rockfall blocks the water route; water remains visibly unreachable.",
    "Goblin Centurion is the last door, protecting the families behind him.",
    "Centurion challenges Hero to prove he is not here to take their land.",
    "Post-trial fragile truce; families can finally put belongings down for the night.",
    "Grik gives Hero the ordinary Stone Shard with natural marks.",
    "Grik points toward Mist Forest; Zone 4 hook.",
]
EN_VOICE_IDS = {
    "HERO": "RasuOwPKPBy67j7E43Su",
    "GRIK": "v4mOufztUtjxcpk65aWy",
    "CENTURION": "cso37AjcTkVqyjGkWbRz",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def local_path(value: str) -> Path:
    relative = PurePosixPath(str(value).split("?", 1)[0].split("#", 1)[0].lstrip("/"))
    candidate = (ROOT / Path(*relative.parts)).resolve()
    assert candidate.is_relative_to(ROOT.resolve()), value
    return candidate


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob(ref: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", f"{ref}:{path}"], cwd=ROOT, text=True
    ).strip()


def assert_decodes(path: Path, dimensions: str) -> None:
    expected = tuple(int(value) for value in dimensions.split("x"))
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        image.load()
        assert image.size == expected, (path, image.size, expected)


def test_authority_inputs_are_present_and_exact() -> None:
    subprocess.check_call(["git", "cat-file", "-e", f"{CANONICAL_MASTER}^{{commit}}"], cwd=ROOT)
    assert subprocess.run(
        ["git", "merge-base", "--is-ancestor", CANONICAL_MASTER, BASE],
        cwd=ROOT,
        check=False,
    ).returncode == 0
    for ref in (WORLD_AUTHORITY, HERO_AUTHORITY, AUDIO_AUTHORITY, SYSTEMS_AUTHORITY):
        subprocess.check_call(["git", "cat-file", "-e", f"{ref}^{{commit}}"], cwd=ROOT)

    exact_paths = {
        WORLD_AUTHORITY: (
            "assets/e10/art/zone3/zone3-world-asset-package.json",
            "assets/e10/art/zone3/cinematic/zone3-cinematic-asset-package.json",
            "js/e9/zone3_presentation_fx.js",
        ),
        HERO_AUTHORITY: ("zone3_runtime_asset_bindings.py",),
        AUDIO_AUTHORITY: (
            "assets/e10/audio/zone3/zone3-presentation-audio-manifest.json",
            "assets/e10/i18n/zone3/zone3-cinematic-subtitles.json",
        ),
        SYSTEMS_AUTHORITY: (
            "docs/contracts/w1_04_zone3_final_presentation_binding_contract_006.json",
        ),
    }
    for ref, paths in exact_paths.items():
        for relative in paths:
            local_blob = subprocess.check_output(
                ["git", "hash-object", "--", relative], cwd=ROOT, text=True
            ).strip()
            assert git_blob(ref, relative) == local_blob


def test_owner_package_and_cinematic_sequence_are_closed() -> None:
    cinematic = read_json(CINEMATIC_PATH)
    assert cinematic["owner_package"] == {
        "filename": "ZONE3_FINAL_10SHOT_OWNER_APPROVED.zip",
        "sha256": "b3aa7e3e4d0d06c294d8f30eb3a05f5e9c5375721bbf4a4e16ccd6a1134ed1b8",
        "sha256_match": True,
        "source_bytes_preserved": True,
    }
    assert cinematic["owner_approved"] is True
    assert [shot["SHOT_ID"] for shot in cinematic["shots"]] == SHOT_IDS
    assert len({shot["SHOT_ID"] for shot in cinematic["shots"]}) == 10
    assert cinematic["source_shot_count"] == 10
    assert cinematic["runtime_derivative_count"] == 10
    assert cinematic["rejected_asset_paths"] == []
    assert [shot["STORY_PURPOSE"] for shot in cinematic["shots"]] == EXPECTED_STORY_FUNCTIONS


def test_cinematic_sources_match_world_identity_and_decode() -> None:
    cinematic = read_json(CINEMATIC_PATH)
    world = read_json(WORLD_PATH)
    world_assets = {
        asset["SOURCE_FILENAME"]: asset
        for asset in world["assets"]
        if asset["TYPE"] == "CINEMATIC_SHOT"
    }
    assert len(world_assets) == 10

    for shot in cinematic["shots"]:
        source = local_path(shot["SOURCE_PATH"])
        runtime = local_path(shot["RUNTIME_PATH"])
        assert source.is_file() and runtime.is_file()
        world_asset = world_assets[PurePosixPath(shot["SOURCE_PATH"]).name]
        assert source.stat().st_size == int(shot["SOURCE_MASTER"]["bytes"])
        assert runtime.stat().st_size == int(world_asset["RUNTIME_BYTES"])
        assert sha256(source) == shot["SOURCE_MASTER"]["sha256"]
        assert sha256(runtime) == world_asset["RUNTIME_SHA256"]
        assert_decodes(source, shot["SOURCE_DIMENSIONS"])
        assert_decodes(runtime, shot["RUNTIME_DIMENSIONS"])

        assert world_asset["SOURCE_PATH"] == shot["SOURCE_PATH"]
        assert world_asset["SOURCE_BYTES"] == shot["SOURCE_MASTER"]["bytes"]
        assert world_asset["SOURCE_SHA256"] == shot["SOURCE_MASTER"]["sha256"]
        assert world_asset["SOURCE_DIMENSIONS"] == shot["SOURCE_DIMENSIONS"]


def test_world_support_and_content_guards_are_exact() -> None:
    world = read_json(WORLD_PATH)
    assert world["expected_world_visual_asset_count"] == 12
    assert world["actual_world_visual_asset_count"] == 12
    assert world["category_counts"] == {
        "CINEMATIC_SHOT": 10,
        "WORLD_MAP_LANDMARK": 1,
        "WORLD_ENVIRONMENT_PLATE": 1,
    }
    assert sum(
        count for category, count in world["category_counts"].items()
        if category != "CINEMATIC_SHOT"
    ) == 2
    assert world["content_guards"]["TEXT_NOT_BAKED_INTO_BASE_IMAGE"] is True
    assert world["content_guards"]["ROUTE_NOT_BAKED_INTO_BASE_IMAGE"] is True
    cinematic = read_json(CINEMATIC_PATH)
    assert cinematic["runtime_delivery"]["text_inserted"] is False
    assert all(
        cinematic["content_guards"][key] is True
        for key in (
            "TEXT_NOT_BAKED_INTO_BASE_IMAGE",
            "ZONE_STATE_NOT_BAKED_INTO_BASE_IMAGE",
            "BOSS_STATE_NOT_BAKED_INTO_BASE_IMAGE",
            "ROUTE_NOT_BAKED_INTO_BASE_IMAGE",
            "REWARD_NOT_BAKED_INTO_BASE_IMAGE",
        )
    )


def test_monster_hierarchy_remains_distinct() -> None:
    assert len(ZONE3_NORMAL_IDS) == 13
    assert len(ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS) == 13
    assert len({row.monster_id for row in ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS}) == 13
    assert ZONE3_ELITE_COUNT == 0
    assert ZONE3_BATTLEFIELD_BOSS_RUNTIME_ID != ZONE3_LORD_ID
    assert ZONE3_LORD_ASSET_SLOT_COUNT == 6
    assert len(ZONE3_LORD_PRESENTATION_SLOTS) == 6
    assert all(slot.lord_id == ZONE3_LORD_ID for slot in ZONE3_LORD_PRESENTATION_SLOTS)
    assert all(local_path(slot.expected_runtime_path).is_file() for slot in ZONE3_LORD_PRESENTATION_SLOTS)


def test_two_locale_dialogue_audio_is_complete_and_aligned() -> None:
    for locale in ("zh-TW", "en-US"):
        subtitles = read_json(SUBTITLE_PATHS[locale])
        audio = read_json(AUDIO_PATHS[locale])
        assert subtitles["ZONE"] == 3 and subtitles["LOCALE"] == locale
        assert audio["ZONE"] == 3 and audio["LOCALE"] == locale
        assert len(subtitles["beats"]) == 97
        assert len(audio["entries"]) == 97
        subtitle_ids = [beat["BEAT_ID"] for beat in subtitles["beats"]]
        audio_ids = [entry["BEAT_ID"] for entry in audio["entries"]]
        assert subtitle_ids == audio_ids
        assert len(set(subtitle_ids)) == 97
        assert audio["VOICE_LANGUAGE_MISMATCH"] == "FORBIDDEN"
        assert audio["MISSING_LOCALE_VOICE_FALLBACK"] == "SUBTITLE_ONLY"
        for entry in audio["entries"]:
            path = local_path(entry["AUDIO_PATH"])
            assert path.is_file() and path.stat().st_size == entry["BYTES"]
            assert sha256(path) == entry["SHA256"]
            assert f"/dialogue/{locale}/" in f"/{entry['AUDIO_PATH']}"

    english = read_json(AUDIO_PATHS["en-US"])
    assert {
        character: english["OWNER_APPROVED_CAST"][character]["VOICE_ID"]
        for character in EN_VOICE_IDS
    } == EN_VOICE_IDS
    assert all(
        entry["VOICE_ID"] == EN_VOICE_IDS[entry["CHARACTER"]]
        for entry in english["entries"]
        if entry["CHARACTER"] in EN_VOICE_IDS
    )
    assert read_json(SUBTITLE_PATHS["en-US"])["CROSS_LANGUAGE_VOICE_FALLBACK"] == "FORBIDDEN"


def test_presentation_audio_counts_and_phase_contract_are_exact() -> None:
    manifest = read_json(PRESENTATION_AUDIO_PATH)
    assert manifest["COUNTS"] == {
        "NEW_AMBIENCE_ASSET_COUNT": 5,
        "NEW_EVENT_SFX_ASSET_COUNT": 7,
        "NEW_TRANSITION_AUDIO_COUNT": 1,
        "NEW_NON_DIALOGUE_AUDIO_COUNT_EXCLUDING_BGM": 13,
        "NEW_BGM_ASSET_COUNT": 3,
        "REUSABLE_SFX_COUNT": 2,
        "STONE_SHARD_MAGICAL_SFX_COUNT": 0,
        "SHUI_HUMAN_VOICE_COUNT": 0,
    }
    assert manifest["ARCHITECTURE"]["GLOBAL_MUTE_COMPATIBLE"] is True
    assert manifest["ARCHITECTURE"]["NEW_VOLUME_CONTROL_UI"] is False
    cues = manifest["CUES"]
    assert len(cues) == 18
    assert len({cue["CUE_ID"] for cue in cues}) == 18
    assert {
        cue["ROLE"] for cue in cues if cue["CATEGORY"] == "bgm"
    } == {"BGM_DISCOVERY", "BGM_ESCALATION", "BGM_RECOVERY"}
    assert all(
        local_path(cue["OUTPUT_PATH"]).is_file()
        and local_path(cue["OUTPUT_PATH"]).stat().st_size == cue["BYTES"]
        and sha256(local_path(cue["OUTPUT_PATH"])) == cue["SHA256"]
        for cue in cues
    )


def test_visual_fx_camera_and_reduced_motion_bindings_are_closed() -> None:
    handoff = read_json(FX_HANDOFF_PATH)
    accepted = handoff["ACCEPTED_IMPLEMENTATION"]
    assert accepted["CODE_ONLY_EFFECT_COUNT"] == 12
    assert accepted["CAMERA_CUE_COUNT"] == 10
    bindings = handoff["SHOT_BINDINGS"]
    assert [row["SHOT_ID"] for row in bindings] == SHOT_IDS
    assert len(bindings) == 10
    known_effects = set(accepted["EFFECT_IDS"])
    assert all(
        set(row.get("ENTRY_EFFECT_IDS", []))
        | set(row.get("OPTIONAL_ENTRY_EFFECT_IDS", []))
        | set(row.get("PERSISTENT_EFFECT_IDS", []))
        | set(row.get("EXIT_EFFECT_IDS", []))
        <= known_effects
        and row["CAMERA_CUE_ID"] in SHOT_IDS
        for row in bindings
    )
    assert handoff["VALIDATION"] == {
        "SHOT_BINDING_RECORD_COUNT": 10,
        "UNKNOWN_EFFECT_REFERENCE_COUNT": 0,
        "UNKNOWN_CAMERA_CUE_COUNT": 0,
        "READY_FOR_FINAL_JOURNEY_BINDING": True,
    }
    assert handoff["REDUCED_MOTION"] == {
        "REDUCED_MOTION_EFFECT_COVERAGE": "12/12",
        "REDUCED_MOTION_CAMERA_COVERAGE": "10/10",
        "BEHAVIORAL_GUARDS": [
            "NO_ABRUPT_SHAKE",
            "NO_UNNECESSARY_CAMERA_MOTION",
            "NO_MISSING_STORY_STATE",
            "NO_GAMEPLAY_IMPACT",
        ],
    }
    assert handoff["STORY_GUARDS"]["STONE_SHARD_GLOW_EFFECT_COUNT"] == 0
    assert handoff["STORY_GUARDS"]["STONE_SHARD_MAGIC_EFFECT_COUNT"] == 0
    assert handoff["STORY_GUARDS"]["SHUI_NONVERBAL_VISUAL_CONTRACT"] == "PASS"
    assert handoff["STORY_GUARDS"]["FAILURE_BLOCKS_GAMEPLAY"] == "NO"
    shot10 = next(row for row in bindings if row["SHOT_ID"] == "SHOT10")
    assert shot10["VISUAL_TRANSITION"] == "Z3_T01_VISUAL"
    assert shot10["TRANSITION_TARGET"] == "MISTY_FOREST"


def test_responsive_binding_covers_all_ten_rows_without_physical_claim() -> None:
    cinematic = read_json(CINEMATIC_PATH)
    world = read_json(WORLD_PATH)
    assert len(cinematic["shots"]) == 10
    assert len(world["responsive_recommendations"]) == 10
    assert world["responsive_recommendations"][-2]["IPAD_PORTRAIT_OBJECT_POSITION"] == "58% 50%"
    assert world["responsive_recommendations"][-1]["IPAD_PORTRAIT_OBJECT_POSITION"] == "58% 50%"
    assert world["responsive_recommendations"][-2]["MOBILE_OBJECT_POSITION"] == "58% 50%"
    assert world["responsive_recommendations"][-1]["MOBILE_OBJECT_POSITION"] == "58% 50%"
    for shot in cinematic["shots"]:
        notes = shot["RESPONSIVE_NOTES"]
        assert all(
            notes[mode]["MODE"] in {"contain", "cover"}
            and notes[mode]["SAFE"] in {"YES", "NO"}
            for mode in ("DESKTOP_16_9", "IPAD_LANDSCAPE", "IPAD_PORTRAIT", "MOBILE_PORTRAIT")
        )
    assert sum(
        shot["RESPONSIVE_NOTES"]["IPAD_PORTRAIT"]["SAFE"] == "YES"
        for shot in cinematic["shots"]
    ) == 2
    assert sum(
        shot["RESPONSIVE_NOTES"]["MOBILE_PORTRAIT"]["SAFE"] == "YES"
        for shot in cinematic["shots"]
    ) == 2
    assert SYSTEMS_CONTRACT_PATH.is_file()
    systems = read_json(SYSTEMS_CONTRACT_PATH)
    assert systems["expected_components"]["cinematic_shots"]["count"] == 10
    assert systems["expected_components"]["world_support_images"]["count"] == 2
    assert systems["failure_contract"]["presentation_failure_must_not_block_gameplay"] is True
    assert cinematic["validation_contract"]["physical_device_acceptance"] == "REQUIRED_LATER"


def test_single_writer_runtime_contract_has_required_boundaries() -> None:
    source = INDEX_PATH.read_text(encoding="utf-8")
    binding = BINDING_PATH.read_text(encoding="utf-8")
    for marker in (
        "/js/e10/zone3_presentation_binding.js?v=",
        "/css/e10/zone3_presentation_binding.css?v=",
        "GoOdysseyZone3Presentation.ensureReady",
        "zone3Binding",
        "playZone3BossReadyFilm",
        "playZone3PostClearFilm",
        "showZone3LordResultCard",
        "presentation_failure",
        "_syncZone3PresentationMute",
        "go-odyssey-audio-mute-changed",
        "_finishZoneCinematicReplay",
    ):
        assert marker in source
    for marker in (
        "shotCount: 10",
        "subtitleBeatCount: 97",
        "dialogueAudioBeatCount: 97",
        "responsiveClassificationCoverage: '10/10'",
        "simultaneousBgmStreamCountMax: 1",
        "bgmDuplicationOnReplay: false",
        "bgmSurvivesRouteExit: false",
        "visualEffectCoverage: '12/12'",
        "cameraCoverage: '10/10'",
        "stressIterations: 50",
        "presentationFailureBlocksGameplay: false",
    ):
        assert marker in binding
    assert not re.search(r"(?:app\.py|i18n\.js|sw\.js)\s*changed", source, re.I)


def test_replay_and_presentation_failure_remain_non_mutating() -> None:
    source = INDEX_PATH.read_text(encoding="utf-8")
    replay_start = source.index("function playZoneStoryReplay(zoneKey)")
    replay_end = source.index("function _finishZoneCinematicReplay(zone)", replay_start)
    replay_body = source[replay_start:replay_end]
    assert "presentationOnly: true" in replay_body
    assert "fetch(" not in replay_body
    assert "markAdventure" not in replay_body
    assert "finishPostClearFilm" not in replay_body
    failure_start = source.index("if (bindingReady.ok !== true)")
    failure_end = source.index("delete overlay.dataset.zone3Presentation", failure_start)
    failure_body = source[failure_start:failure_end]
    assert "btn.disabled = false" in failure_body
    assert "window.location" not in failure_body
    assert "fetch(" not in failure_body


def test_protected_product_files_remain_outside_this_candidate_scope() -> None:
    for relative in ("app.py", "i18n.js", "sw.js"):
        result = subprocess.run(
            ["git", "diff", "--quiet", BASE, "--", relative],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"protected product file changed: {relative}"
