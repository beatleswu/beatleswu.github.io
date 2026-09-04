"""Produce the Zone 3 non-dialogue presentation-audio package.

This task-owned wrapper deliberately reuses the established Zone 1 ElevenLabs
adapter for authenticated requests.  It does not read or write credential
files, does not print credentials, and does not touch Journey runtime code.

The output is a static audio package plus a deterministic manifest.  Runtime
binding remains a later lane/gate.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from mutagen.mp3 import MP3


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "tools" / "e10_zone1_audio" / "generate_zone1_audio.py"
OUTPUT_ROOT = REPO_ROOT / "assets" / "e10" / "audio" / "zone3"
MANIFEST_PATH = OUTPUT_ROOT / "zone3-presentation-audio-manifest.json"

TASK = "W1_03_JOURNEY_ZONE3_PRESENTATION_AUDIO_SOURCE_AND_PRODUCTION_PACKAGE_009"
SOURCE_HEAD = "6e5d0b9d8999476776d1a48277c0604c26589916"
SOURCE_TREE = "6af976e414410869a2725499bf0f11d77d385292"
OUTPUT_FORMAT = "audio/mpeg"
PIPELINE_AUTHORITY = (
    "Existing Go Odyssey Owner-authorized ElevenLabs project pipeline; "
    "generated audio only, no third-party source asset"
)


def _sound_effects() -> list[dict[str, Any]]:
    return [
        {
            "cue_id": "Z3_CAVE_ROOM_TONE",
            "role": "CAVE_ROOM_TONE",
            "category": "ambience",
            "world_reference_cue_id": "Z3_AMBIENCE_PRIMARY",
            "filename": "ambience/zone3_ambience_cave_room_tone.mp3",
            "duration_seconds": 12,
            "loopable": True,
            "default_playback_role": "FIRST_ENTRY_LOOP",
            "prompt": (
                "Warm inhabited limestone cave room tone for a family-friendly stylized adventure game, "
                "spacious but restrained, faint lantern hiss, tiny settling stone, soft rope tension, "
                "no melody, no voices, no speech, no horror, seamless loop"
            ),
        },
        {
            "cue_id": "Z3_DISTANT_CAVE_WIND",
            "role": "DISTANT_CAVE_WIND",
            "category": "ambience",
            "world_reference_cue_id": "Z3_AMBIENCE_PRIMARY",
            "filename": "ambience/zone3_ambience_distant_cave_wind.mp3",
            "duration_seconds": 12,
            "loopable": True,
            "default_playback_role": "CAVE_MOUTH_DEPTH_LOOP",
            "prompt": (
                "Sparse distant cave wind at an open cave mouth, cool airy depth for a child-safe stylized "
                "adventure game, gentle and spacious, no howl, no horror, no voices, no music, seamless loop"
            ),
        },
        {
            "cue_id": "Z3_FAMILY_ACTIVITY",
            "role": "FAMILY_ACTIVITY",
            "category": "ambience",
            "world_reference_cue_id": "DISTANT_FAMILY_ACTIVITY",
            "filename": "ambience/zone3_ambience_family_activity.mp3",
            "duration_seconds": 12,
            "loopable": True,
            "default_playback_role": "INHABITED_SHELTER_LOOP",
            "prompt": (
                "Soft distant family activity inside an inhabited cave: quiet cloth, basket and blanket "
                "movement, low safe footsteps, faint household bustle, no intelligible speech, no crying, "
                "no combat, no music, family-friendly seamless loop"
            ),
        },
        {
            "cue_id": "Z3_TRIAL_TENSION",
            "role": "TRIAL_TENSION",
            "category": "ambience",
            "world_reference_cue_id": "TRIAL_TENSION_AMBIENCE",
            "filename": "ambience/zone3_ambience_trial_tension.mp3",
            "duration_seconds": 12,
            "loopable": True,
            "default_playback_role": "LORD_TRIAL_TENSION_LOOP",
            "prompt": (
                "Restrained cave stillness for a guardian trial in a family-friendly adventure game: "
                "subtle low stone resonance, quiet boundary pressure, controlled tension without horror, "
                "no monster, no shouting, no voices, no music wall, seamless loop"
            ),
        },
        {
            "cue_id": "Z3_FRAGILE_TRUCE",
            "role": "FRAGILE_TRUCE",
            "category": "ambience",
            "world_reference_cue_id": "FRAGILE_TRUCE_AMBIENCE",
            "filename": "ambience/zone3_ambience_fragile_truce.mp3",
            "duration_seconds": 12,
            "loopable": True,
            "default_playback_role": "POST_CLEAR_GUARDED_PEACE_LOOP",
            "prompt": (
                "Quiet guarded peace in a warm inhabited cave after a trial, soft lantern air and distant "
                "belongings settling, calm spacious room tone, no celebration, no victory fanfare, no voices, "
                "no music swell, family-friendly seamless loop"
            ),
        },
        {
            "cue_id": "Z3_REFUGEE_FOOTSTEPS",
            "role": "REFUGEE_FOOTSTEPS",
            "category": "event_sfx",
            "world_reference_cue_id": "REFUGEE_FOOTSTEPS",
            "filename": "sfx/zone3_sfx_refugee_footsteps.mp3",
            "duration_seconds": 5,
            "loopable": False,
            "default_playback_role": "SHOT01_REFUGEE_RETREAT_EVENT",
            "prompt": (
                "Small group of tired families walking deeper through a cave, soft uneven footfalls on stone, "
                "cloth and packs moving, retreat not charge, no running, no combat, no voices"
            ),
        },
        {
            "cue_id": "Z3_BELONGINGS_MOVEMENT",
            "role": "BELONGINGS_MOVEMENT",
            "category": "event_sfx",
            "world_reference_cue_id": "BELONGINGS_MOVEMENT",
            "filename": "sfx/zone3_sfx_belongings_movement.mp3",
            "duration_seconds": 4,
            "loopable": False,
            "default_playback_role": "SHOT01_SHOT02_HOUSEHOLD_PROP_EVENT",
            "prompt": (
                "Household belongings being carried and set down: soft pots, blankets, water jugs, a wooden "
                "toy, cloth and rope movement, no metal weapons, no loot, no voices"
            ),
        },
        {
            "cue_id": "Z3_WATER_DRIP",
            "role": "WATER_DRIP",
            "category": "event_sfx",
            "world_reference_cue_id": "WATER_DRIP",
            "filename": "sfx/zone3_sfx_water_drip.mp3",
            "duration_seconds": 2,
            "loopable": False,
            "default_playback_role": "SHOT05_BLOCKED_WATER_DETAIL",
            "prompt": "Single neutral cave water drip with gentle stone resonance, very short, no music, no voices",
        },
        {
            "cue_id": "Z3_ROCKFALL",
            "role": "ROCKFALL",
            "category": "event_sfx",
            "world_reference_cue_id": "ROCKFALL",
            "filename": "sfx/zone3_sfx_rockfall.mp3",
            "duration_seconds": 5,
            "loopable": False,
            "default_playback_role": "SHOT05_ROUTE_BLOCK_EVENT",
            "prompt": (
                "Bounded small cave rockfall blocking a route: several stones tumble and settle, controlled and "
                "child-safe, no earthquake, no collapse roar, no debris hitting people, no horror"
            ),
        },
        {
            "cue_id": "Z3_BLOCKED_WATER_FLOW",
            "role": "BLOCKED_WATER_FLOW",
            "category": "event_sfx",
            "world_reference_cue_id": "BLOCKED_WATER_FLOW",
            "filename": "sfx/zone3_sfx_blocked_water_flow.mp3",
            "duration_seconds": 10,
            "loopable": True,
            "default_playback_role": "SHOT05_MUFFLED_WATER_LOOP",
            "prompt": (
                "Water remains audible behind a blocked cave passage: muffled gentle stream and a few small "
                "drips through stone, no magic, no voices, no music, calm and child-safe seamless loop"
            ),
        },
        {
            "cue_id": "Z3_CENTURION_ARMOR",
            "role": "CENTURION_ARMOR",
            "category": "event_sfx",
            "world_reference_cue_id": "CENTURION_ARMOR",
            "filename": "sfx/zone3_sfx_centurion_armor.mp3",
            "duration_seconds": 3,
            "loopable": False,
            "default_playback_role": "SHOT06_PROTECTOR_ARRIVAL_EVENT",
            "prompt": (
                "A middle-aged protector in practical worn armor takes one grounded step and settles in a cave, "
                "leather and muted metal, controlled and protective, not aggressive, no monster, no roar, no voices"
            ),
        },
        {
            "cue_id": "Z3_CENTURION_SPEAR_PLANT",
            "role": "CENTURION_SPEAR_PLANT",
            "category": "event_sfx",
            "world_reference_cue_id": "CENTURION_SPEAR_PLANT",
            "filename": "sfx/zone3_sfx_centurion_spear_plant.mp3",
            "duration_seconds": 3,
            "loopable": False,
            "default_playback_role": "SHOT06_BOUNDARY_EVENT",
            "prompt": (
                "Single controlled spear butt planted firmly on cave stone as a boundary, resonant but not violent, "
                "no attack, no explosion, no shouting, no monster sound"
            ),
        },
        {
            "cue_id": "Z3_MISTY_FOREST_WIND_TRANSITION",
            "role": "MISTY_FOREST_WIND_TRANSITION",
            "category": "transition",
            "world_reference_cue_id": "MISTY_FOREST_WIND_TRANSITION",
            "filename": "transition/zone3_to_zone4_misty_forest_wind.mp3",
            "duration_seconds": 5,
            "loopable": False,
            "default_playback_role": "SHOT10_ZONE4_HOOK_TRANSITION",
            "prompt": (
                "Cool airy natural wind passing from a cave threshold toward a misty forest, mysterious but gentle "
                "and child-safe, no supernatural whoosh, no horror, short transition, no voices"
            ),
        },
    ]


def _bgm() -> list[dict[str, Any]]:
    shared = (
        "Instrumental only, family-friendly stylized adventure game score, cave ingenuity and retreat not raid, "
        "dry folk texture over spacious cave air, readable and restrained, no vocals, no horror, no grimdark, "
        "no noise wall, leave headroom for dialogue"
    )
    return [
        {
            "cue_id": "Z3_BGM_DISCOVERY",
            "role": "BGM_DISCOVERY",
            "category": "bgm",
            "phase": "FIRST_ENTRY",
            "filename": "bgm/zone3_bgm_discovery.mp3",
            "length_ms": 30000,
            "loopable": True,
            "default_playback_role": "FIRST_ENTRY_BGM",
            "prompt": f"{shared}, gentle wooden flute and plucked strings, warm exploration and quiet curiosity, loop-friendly",
        },
        {
            "cue_id": "Z3_BGM_ESCALATION",
            "role": "BGM_ESCALATION",
            "category": "bgm",
            "phase": "BOSS_READY",
            "filename": "bgm/zone3_bgm_escalation.mp3",
            "length_ms": 30000,
            "loopable": True,
            "default_playback_role": "BOSS_READY_BGM",
            "prompt": f"{shared}, measured low strings and soft hand percussion, controlled protector-trial tension, increase scale without shouting or bombast, loop-friendly",
        },
        {
            "cue_id": "Z3_BGM_RECOVERY",
            "role": "BGM_RECOVERY",
            "category": "bgm",
            "phase": "POST_CLEAR",
            "filename": "bgm/zone3_bgm_recovery.mp3",
            "length_ms": 30000,
            "loopable": True,
            "default_playback_role": "POST_CLEAR_BGM",
            "prompt": f"{shared}, calm guarded truce with warm strings and light wooden texture, no victory fanfare, no celebratory swell, loop-friendly",
        },
    ]


def _load_adapter():
    spec = importlib.util.spec_from_file_location("go_odyssey_zone1_audio_adapter", ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load established adapter: {ADAPTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _metadata(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    audio = MP3(path)
    duration_ms = int(round(float(audio.info.length) * 1000))
    if not data or duration_ms <= 0:
        raise RuntimeError(f"Invalid generated audio: {path}")
    return {
        "output_path": path.relative_to(REPO_ROOT).as_posix(),
        "format": OUTPUT_FORMAT,
        "bytes": len(data),
        "duration_ms": duration_ms,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _record(cue: dict[str, Any], path: Path) -> dict[str, Any]:
    result = {
        "CUE_ID": cue["cue_id"],
        "ROLE": cue["role"],
        "CATEGORY": cue["category"],
        "SOURCE_CLASS": "AUTHORIZED_NEW_ASSET",
        "SOURCE_TYPE": "GENERATED_AUDIO",
        "TOOL_OR_PIPELINE": (
            "tools/e10_zone1_audio/generate_zone1_audio.py::_sound_effect"
            if cue["category"] != "bgm"
            else "tools/e10_zone1_audio/generate_zone1_audio.py::_music"
        ),
        "PROJECT_OR_LICENSE_AUTHORITY": PIPELINE_AUTHORITY,
        "REPRODUCIBILITY": "YES_PROMPT_AND_REQUEST_PARAMETERS_RECORDED",
        "OUTPUT_FORMAT": OUTPUT_FORMAT,
        "OUTPUT_PATH": path.relative_to(REPO_ROOT).as_posix(),
        "LOOPABLE": cue["loopable"],
        "DEFAULT_PLAYBACK_ROLE": cue["default_playback_role"],
        "WORLD_REFERENCE_CUE_ID": cue.get("world_reference_cue_id"),
        "OWNER_AUDIO_LOCK": False,
    }
    if "phase" in cue:
        result["PHASE"] = cue["phase"]
    result.update({
        "PROMPT_SHA256": hashlib.sha256(cue["prompt"].encode("utf-8")).hexdigest(),
        "PROMPT": cue["prompt"],
    })
    metadata = _metadata(path)
    # Keep the manifest field names required by the production handoff in the
    # same shape as the existing Zone 1/2 package records.
    result["SOURCE_ASSET_OR_PIPELINE"] = result["TOOL_OR_PIPELINE"]
    result["BYTES"] = metadata["bytes"]
    result["DURATION_MS"] = metadata["duration_ms"]
    result["SHA256"] = metadata["sha256"]
    return result


def _reuse_record(cue_id: str, role: str, source_path: str, default_role: str) -> dict[str, Any]:
    path = REPO_ROOT / source_path
    if not path.is_file():
        raise RuntimeError(f"Missing required reusable project cue: {source_path}")
    result = {
        "CUE_ID": cue_id,
        "ROLE": role,
        "CATEGORY": "reusable_sfx",
        "SOURCE_CLASS": "AUTHORIZED_REUSE",
        "SOURCE_TYPE": "EXISTING_PROJECT_ASSET",
        "TOOL_OR_PIPELINE": "Existing locked Go Odyssey Zone audio package",
        "PROJECT_OR_LICENSE_AUTHORITY": "Owner-approved canonical Zone 1/2 project asset",
        "REPRODUCIBILITY": "YES_CANONICAL_PATH_AND_HASH_RECORDED",
        "OUTPUT_FORMAT": OUTPUT_FORMAT,
        "SOURCE_ASSET_OR_PIPELINE": source_path,
        "OUTPUT_PATH": source_path,
        "LOOPABLE": False,
        "DEFAULT_PLAYBACK_ROLE": default_role,
        "OWNER_AUDIO_LOCK": True,
    }
    metadata = _metadata(path)
    result["BYTES"] = metadata["bytes"]
    result["DURATION_MS"] = metadata["duration_ms"]
    result["SHA256"] = metadata["sha256"]
    return result


def _build_manifest(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "MANIFEST_VERSION": "w1-zone3-presentation-audio-production-009-v1",
        "TASK": TASK,
        "SOURCE_HEAD": SOURCE_HEAD,
        "SOURCE_TREE": SOURCE_TREE,
        "ZONE": 3,
        "ZONE_NAME": {"zh-TW": "哥布林洞穴", "en": "Goblin Cave"},
        "STATUS": "PRODUCED_STATIC_PACKAGE_PENDING_OWNER_AUDIO_LOCK",
        "AUDIO_SOURCE_AUTHORITY": {
            "AUTHORIZED_PRESENTATION_AUDIO_PIPELINE_AVAILABLE": True,
            "SOURCE_TYPE": "GENERATED_AUDIO",
            "TOOL_OR_PIPELINE": "Existing Zone 1 ElevenLabs adapter reused by task-owned Zone 3 wrapper",
            "PROJECT_OR_LICENSE_AUTHORITY": PIPELINE_AUTHORITY,
            "REPRODUCIBILITY": "YES",
            "OUTPUT_FORMAT": OUTPUT_FORMAT,
        },
        "COUNTS": {
            "NEW_AMBIENCE_ASSET_COUNT": 5,
            "NEW_EVENT_SFX_ASSET_COUNT": 7,
            "NEW_TRANSITION_AUDIO_COUNT": 1,
            "NEW_NON_DIALOGUE_AUDIO_COUNT_EXCLUDING_BGM": 13,
            "NEW_BGM_ASSET_COUNT": 3,
            "REUSABLE_SFX_COUNT": 2,
            "STONE_SHARD_MAGICAL_SFX_COUNT": 0,
            "SHUI_HUMAN_VOICE_COUNT": 0,
        },
        "ARCHITECTURE": {
            "NEW_VOLUME_CONTROL_UI": False,
            "GLOBAL_MUTE_COMPATIBLE": True,
            "JOURNEY_RUNTIME_BINDING": "NOT_PERFORMED",
            "SOURCE_ART_MUTATED": False,
        },
        "CUES": records,
    }


def _write_manifest() -> None:
    all_new = _sound_effects() + _bgm()
    for cue in all_new:
        path = OUTPUT_ROOT / cue["filename"]
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Missing generated audio: {cue['cue_id']}")
    records = [_record(cue, OUTPUT_ROOT / cue["filename"]) for cue in all_new]
    records.extend([
        _reuse_record(
            "Z3_SHUI_REACTION",
            "SHUI_REACTION",
            "assets/e10/audio/zone2/sfx/zone2_sfx_shui_reaction_2.mp3",
            "NONVERBAL_SHUI_REACTION",
        ),
        _reuse_record(
            "Z3_STONE_PHYSICAL_HANDOFF",
            "STONE_PHYSICAL_HANDOFF",
            "assets/e10/audio/zone1/sfx/zone1_sfx_shot07_stone_placement.mp3",
            "SHOT09_STONE_HANDOFF",
        ),
    ])
    manifest = _build_manifest(records)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"MANIFEST={MANIFEST_PATH.relative_to(REPO_ROOT).as_posix()}")


def generate(force: bool) -> None:
    if not ADAPTER_PATH.is_file():
        raise RuntimeError(f"Established audio adapter not found: {ADAPTER_PATH}")
    all_new = _sound_effects() + _bgm()
    output_paths = [OUTPUT_ROOT / cue["filename"] for cue in all_new]
    existing = [p for p in output_paths if p.exists()]
    if existing and not force:
        raise RuntimeError(
            "Refusing to overwrite existing generated audio without --force: "
            + ", ".join(str(p.relative_to(REPO_ROOT)) for p in existing)
        )
    if force:
        for path in existing:
            path.unlink()

    adapter = _load_adapter()
    api_key = adapter.get_api_key()
    for cue in all_new:
        path = OUTPUT_ROOT / cue["filename"]
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"GENERATING={cue['cue_id']}")
        if cue["category"] == "bgm":
            ok = adapter._music(api_key, cue["prompt"], cue["length_ms"], path)
        else:
            ok = adapter._sound_effect(api_key, cue["prompt"], cue["duration_seconds"], path)
        if not ok or not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"AUDIO_GENERATION_FAILED={cue['cue_id']}")

    _write_manifest()
    print("GENERATION_VERIFICATION=PASS")


def verify() -> None:
    if not MANIFEST_PATH.is_file():
        raise RuntimeError(f"Missing manifest: {MANIFEST_PATH}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    records = manifest.get("CUES", [])
    ids = [r.get("CUE_ID") for r in records]
    paths = [r.get("OUTPUT_PATH") for r in records]
    if len(ids) != len(set(ids)):
        raise RuntimeError("DUPLICATE_CUE_ID")
    if len(paths) != len(set(paths)):
        raise RuntimeError("DUPLICATE_AUDIO_PATH")
    for record in records:
        path = REPO_ROOT / record["OUTPUT_PATH"]
        actual = _metadata(path)
        if (
            record["BYTES"] != actual["bytes"]
            or record["DURATION_MS"] != actual["duration_ms"]
            or record["SHA256"] != actual["sha256"]
        ):
            raise RuntimeError(f"MANIFEST_HASH_OR_MEDIA_MISMATCH={record['CUE_ID']}")
    expected_new = {cue["cue_id"] for cue in _sound_effects() + _bgm()}
    actual_new = {record["CUE_ID"] for record in records if record["SOURCE_CLASS"] == "AUTHORIZED_NEW_ASSET"}
    if actual_new != expected_new:
        raise RuntimeError("NEW_CUE_SET_MISMATCH")
    if len(records) != 18:
        raise RuntimeError(f"CUE_COUNT_EXPECTED_18_ACTUAL_{len(records)}")
    print("AUDIO_MANIFEST_VERIFICATION=PASS")
    print(f"CUE_COUNT={len(records)}")


def rebuild_manifest() -> None:
    """Rebuild only the deterministic manifest; never call the remote API."""
    _write_manifest()
    print("MANIFEST_REBUILD_VERIFICATION=PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true")
    group.add_argument("--verify", action="store_true")
    group.add_argument("--rebuild-manifest", action="store_true")
    parser.add_argument("--force", action="store_true", help="Explicitly overwrite this task's generated outputs")
    args = parser.parse_args()
    try:
        if args.generate:
            generate(force=args.force)
        elif args.verify:
            verify()
        else:
            rebuild_manifest()
    except Exception as exc:  # safe diagnostics only; never includes credential material
        print(f"ZONE3_PRESENTATION_AUDIO_ERROR={exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
