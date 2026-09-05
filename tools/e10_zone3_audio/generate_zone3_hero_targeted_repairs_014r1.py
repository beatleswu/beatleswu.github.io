"""Generate only the three Owner-confirmed Zone 3 Hero zh-TW repairs.

Each target is resolved against the current canonical subtitle manifest.  The
Owner-reported wording for target C is retained as forensic metadata, while
the actual runtime beat (Z3_S01_B003) is regenerated with a targeted
pronunciation instruction and its visible canonical subtitle is unchanged.

The tool reads ELEVENLABS_API_KEY only from the current process environment.
It never reads, prints, hashes, copies, or moves credential files.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

from mutagen.mp3 import MP3


REPO_ROOT = Path(__file__).resolve().parents[2]
REPAIR_MANIFEST_PATH = REPO_ROOT / "tools" / "e10_zone3_audio" / "zone3_hero_targeted_repair_014r1.json"
SUBTITLE_MANIFEST_PATH = REPO_ROOT / "assets" / "e10" / "i18n" / "zone3" / "zone3-cinematic-subtitles.json"
AUDIO_MANIFEST_PATH = REPO_ROOT / "assets" / "e10" / "audio" / "zone3" / "zone3-cinematic-audio-manifest.json"
ZONE1_TOOL_PATH = REPO_ROOT / "tools" / "e10_zone1_audio" / "generate_zone1_audio.py"
API_KEY_ENV = "ELEVENLABS_API_KEY"
MODEL_ID = "eleven_v3"
HERO_VOICE_ID = "XXxvxx0YUt8icTEFE3c6"


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _load_zone1_tool():
    spec = importlib.util.spec_from_file_location("e10_zone1_audio_targeted_repair", ZONE1_TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load established Zone 1 TTS helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _metadata(path: Path) -> tuple[int, int, str]:
    raw = path.read_bytes()
    duration_ms = round(float(MP3(path).info.length) * 1000)
    return duration_ms, len(raw), hashlib.sha256(raw).hexdigest()


def _find_subtitle(subtitles: dict, beat_id: str) -> dict:
    for beat in subtitles.get("beats", []):
        if beat.get("BEAT_ID") == beat_id:
            return beat
    raise ValueError(f"missing canonical beat: {beat_id}")


def _validate_inputs(repair: dict, subtitles: dict) -> tuple[list[dict], dict]:
    items = repair.get("items")
    if not isinstance(items, list) or len(items) != 3:
        raise ValueError("targeted repair manifest must contain exactly three items")
    by_id = {beat.get("BEAT_ID"): beat for beat in subtitles.get("beats", [])}
    runtime_items = []
    for item in items:
        if item.get("SPEAKER") != "HERO" or item.get("VOICE_ID", HERO_VOICE_ID) != HERO_VOICE_ID:
            raise ValueError("targeted repair item is not locked to the approved Hero voice")
        if item.get("AUDITION_ONLY"):
            lookup_id = item.get("CANONICAL_LOOKUP_BEAT_ID")
            lookup = by_id.get(lookup_id)
            if not lookup or lookup.get("VISIBLE_TEXT") == item.get("EXACT_SUBTITLE"):
                raise ValueError("audition-only item no longer has the expected canonical-text mismatch")
            continue
        beat_id = item.get("BEAT_ID")
        beat = by_id.get(beat_id)
        if not beat or beat.get("VISIBLE_TEXT") != item.get("EXACT_SUBTITLE"):
            raise ValueError(f"runtime repair is not an exact canonical subtitle match: {beat_id}")
        runtime_items.append(item)
    return runtime_items, by_id


def _write_runtime_manifest(manifest: dict, generated_by_id: dict[str, tuple[int, int, str]], items: list[dict]) -> None:
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Zone 3 audio manifest has no entries")
    by_id = {entry.get("BEAT_ID"): entry for entry in entries}
    for item in items:
        entry = by_id[item["BEAT_ID"]]
        path = REPO_ROOT / Path(item["RUNTIME_AUDIO_PATH"])
        duration_ms, byte_count, sha256 = generated_by_id[item["BEAT_ID"]]
        entry["VOICE_ID"] = HERO_VOICE_ID
        entry["VOICE_LANGUAGE"] = "zh"
        entry["AUDIO_PATH"] = _relative(path)
        entry["DURATION_MS"] = duration_ms
        entry["BYTES"] = byte_count
        entry["SHA256"] = sha256
        entry["OWNER_APPROVED_VOICE"] = True
        entry["VOICE_STATUS"] = "OWNER_APPROVED_PRODUCTION"
        entry["PRONUNCIATION_OVERRIDE"] = {
            "TTS_INPUT_TEXT": item["TTS_INPUT_TEXT"],
            "REQUIRED_READING": item["REQUIRED_READING"],
            "REPAIR_REASON": item["REPAIR_REASON"],
            "VISIBLE_TEXT_UNCHANGED": True,
        }
    AUDIO_MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    repair = _load_json(REPAIR_MANIFEST_PATH)
    subtitles = _load_json(SUBTITLE_MANIFEST_PATH)
    runtime_items, _ = _validate_inputs(repair, subtitles)
    audition_only_count = sum(1 for item in repair["items"] if item.get("AUDITION_ONLY"))
    print("OWNER_CONFIRMED_REPAIR_COUNT=3")
    print(f"RUNTIME_TARGET_COUNT={len(runtime_items)}")
    print(f"AUDITION_ONLY_TARGET_COUNT={audition_only_count}")
    print("OWNER_AUDIO_ACCEPTANCE=PENDING")
    if not os.environ.get(API_KEY_ENV):
        print("AUDIO_REPAIR_AUTH_STATUS=UNAVAILABLE")
        print("GENERATED=NO")
        print("AUDIO_REPAIR_FILES_WRITTEN=0")
        print("AUDIO_REPAIR_STATUS=BLOCKED_AUDIO_AUTH_ONLY")
        return 2

    audio_tool = _load_zone1_tool()
    existing_manifest = _load_json(AUDIO_MANIFEST_PATH)
    generated_by_id: dict[str, tuple[int, int, str]] = {}
    generated_records = []

    for item in repair["items"]:
        output_text = item.get("TTS_INPUT_TEXT")
        if not isinstance(output_text, str) or not output_text:
            raise ValueError(f"empty TTS input: {item.get('BEAT_ID')}")
        output_key = "AUDITION_AUDIO_PATH" if item.get("AUDITION_ONLY") else "RUNTIME_AUDIO_PATH"
        output_path_value = item.get(output_key)
        if not output_path_value:
            raise ValueError(f"missing output path: {item.get('BEAT_ID')}")
        output_path = REPO_ROOT / Path(output_path_value)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_name(output_path.name + ".candidate")
        if temp_path.exists():
            temp_path.unlink()
        if not audio_tool._text_to_speech(
            os.environ[API_KEY_ENV], HERO_VOICE_ID, output_text, MODEL_ID, temp_path
        ):
            raise RuntimeError(f"TTS_GENERATION_FAILED={item.get('BEAT_ID') or 'OWNER_LINE_C'}")
        duration_ms, byte_count, sha256 = _metadata(temp_path)
        if duration_ms <= 0 or byte_count <= 0 or not sha256:
            raise RuntimeError(f"TTS_OUTPUT_INVALID={item.get('BEAT_ID') or 'OWNER_LINE_C'}")
        temp_path.replace(output_path)
        audition_path_value = item.get("AUDITION_AUDIO_PATH")
        audition_path = None
        if audition_path_value:
            audition_path = REPO_ROOT / Path(audition_path_value)
            audition_path.parent.mkdir(parents=True, exist_ok=True)
            if not item.get("AUDITION_ONLY"):
                shutil.copyfile(output_path, audition_path)
        record = {
            "BEAT_ID": item.get("BEAT_ID"),
            "SHOT": item["SHOT"],
            "SPEAKER": item["SPEAKER"],
            "EXACT_SUBTITLE": item["EXACT_SUBTITLE"],
            "OWNER_REPORTED_TEXT": item.get("OWNER_REPORTED_TEXT"),
            "OLD_AUDIO_PATH": item.get("RUNTIME_AUDIO_PATH"),
            "NEW_AUDIO_PATH": _relative(output_path),
            "AUDITION_AUDIO_PATH": _relative(audition_path) if audition_path else None,
            "REPAIR_REASON": item["REPAIR_REASON"],
            "AUDITION_ONLY": bool(item.get("AUDITION_ONLY")),
            "GENERATED": True,
            "AUTOMATED_VALIDATION": "PASS",
            "OWNER_AUDIO_ACCEPTANCE": "PENDING",
            "DURATION_MS": duration_ms,
            "BYTES": byte_count,
            "SHA256": sha256,
        }
        generated_records.append(record)
        if not item.get("AUDITION_ONLY"):
            generated_by_id[item["BEAT_ID"]] = (duration_ms, byte_count, sha256)

    _write_runtime_manifest(existing_manifest, generated_by_id, runtime_items)
    generated_manifest_path = REPAIR_MANIFEST_PATH.with_name(
        "zone3_hero_targeted_repair_014r1.generated.json"
    )
    generated_manifest_path.write_text(
        json.dumps(
            {
                **repair,
                "STATUS": "GENERATED_PENDING_OWNER_AUDITION",
                "GENERATED": True,
                "AUTOMATED_VALIDATION": "PASS",
                "OWNER_AUDIO_ACCEPTANCE": "PENDING",
                "generated": generated_records,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"AUDIO_REPAIR_FILES_WRITTEN={len(generated_records)}")
    print(f"OWNER_AUDITION_FILES_WRITTEN={sum(1 for item in generated_records if item.get('AUDITION_AUDIO_PATH'))}")
    print("RUNTIME_MANIFEST_UPDATED=YES")
    print("AUDIO_REPAIR_STATUS=PASS_TARGETED_FILES_GENERATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
