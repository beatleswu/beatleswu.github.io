"""Generate the Zone 3 zh-TW voice layer from the canonical subtitle manifest.

This is a thin Zone 3 adapter over the established Zone 1 ElevenLabs request
helper.  It reads ELEVENLABS_API_KEY only from the current process environment
and never reads, writes, or prints credential material.

The canonical subtitle manifest is the only dialogue text source.  Approved
Hero lines may be generated in full.  Grik and Centurion are available as
bounded auditions until the Owner locks a voice; the explicit
--final-production mode is the only path that promotes those locked Owner
selections into the runtime manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

from mutagen.mp3 import MP3


REPO_ROOT = Path(__file__).resolve().parents[2]
SUBTITLE_MANIFEST_PATH = REPO_ROOT / "assets" / "e10" / "i18n" / "zone3" / "zone3-cinematic-subtitles.json"
AUDIO_MANIFEST_PATH = REPO_ROOT / "assets" / "e10" / "audio" / "zone3" / "zone3-cinematic-audio-manifest.json"
AUDITION_MANIFEST_PATH = REPO_ROOT / "tools" / "e10_zone3_audio" / "zone3_voice_audition_manifest.json"
RUNTIME_AUDIO_ROOT = REPO_ROOT / "assets" / "e10" / "audio" / "zone3" / "dialogue" / "zh-TW"
AUDITION_ROOT = REPO_ROOT / "tools" / "e10_zone3_audio" / "_local_review" / "auditions" / "zh-TW"
ZONE1_TOOL_PATH = REPO_ROOT / "tools" / "e10_zone1_audio" / "generate_zone1_audio.py"

API_KEY_ENV = "ELEVENLABS_API_KEY"
MODEL_ID = "eleven_v3"
HERO_VOICE_ID = "XXxvxx0YUt8icTEFE3c6"
HERO_VOICE_NAME = "Roy"
GRIK_VOICE_ID = "DSyEP4HEaCKur8rFFOri"
GRIK_VOICE_NAME = "Zack"
CENTURION_VOICE_ID = "BrbEfHMQu0fyclQR7lfh"
CENTURION_VOICE_NAME = "Kevin Tu"

LOCKED_PRODUCTION_VOICES = {
    "HERO": (HERO_VOICE_ID, HERO_VOICE_NAME),
    "GRIK": (GRIK_VOICE_ID, GRIK_VOICE_NAME),
    "CENTURION": (CENTURION_VOICE_ID, CENTURION_VOICE_NAME),
}

# These are bounded review candidates selected from the Owner account's
# currently available zh voice pool. They are not casting locks.
GRIK_CANDIDATES = (
    ("DSyEP4HEaCKur8rFFOri", "Zack", "young, soft, conversational comparison"),
    ("4aW8bNY2tSD8eaHmuXZ0", "Chen", "young, clear, conversational comparison"),
    ("R55vTH9XmVSyAcM6YvtV", "Yao Yuan Wu", "young, natural, conversational comparison"),
)
CENTURION_CANDIDATES = (
    ("BrbEfHMQu0fyclQR7lfh", "Kevin Tu", "middle-aged, steady, weathered comparison"),
    ("4aW8bNY2tSD8eaHmuXZ0", "Chen", "younger, firm, controlled comparison"),
    ("R55vTH9XmVSyAcM6YvtV", "Yao Yuan Wu", "younger, restrained, grounded comparison"),
)


def _load_zone1_tool():
    spec = importlib.util.spec_from_file_location("e10_zone1_audio_tool", ZONE1_TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load established audio helper: {ZONE1_TOOL_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_subtitles() -> dict:
    document = json.loads(SUBTITLE_MANIFEST_PATH.read_text(encoding="utf-8"))
    beats = document.get("beats")
    if not isinstance(beats, list) or not beats:
        raise ValueError("subtitle manifest has no beats")
    ids = [item.get("BEAT_ID") for item in beats]
    keys = [item.get("I18N_KEY") for item in beats]
    if any(not isinstance(value, str) or not value for value in ids + keys):
        raise ValueError("subtitle manifest contains an empty stable identity")
    if len(ids) != len(set(ids)) or len(keys) != len(set(keys)):
        raise ValueError("subtitle manifest contains duplicate identities")
    if {item.get("SHOT_ID") for item in beats} != {f"SHOT{number:02d}" for number in range(1, 11)}:
        raise ValueError("subtitle manifest must represent all ten shots")
    if any(item.get("LOCALE") != "zh-TW" or item.get("ZONE") != 3 for item in beats):
        raise ValueError("subtitle manifest contains a non-canonical locale or zone")
    if any(item.get("CHARACTER") not in {"HERO", "GRIK", "CENTURION"} for item in beats):
        raise ValueError("unexpected spoken character in subtitle manifest")
    return document


def _file_metadata(path: Path) -> tuple[int, int, str]:
    data = path.read_bytes()
    duration_ms = round(float(MP3(path).info.length) * 1000)
    return duration_ms, len(data), hashlib.sha256(data).hexdigest()


def _runtime_filename(beat: dict) -> str:
    return f"zone3_{beat['SHOT_ID'].lower()}_{beat['BEAT_ID'].split('_')[-1].lower()}_zh-TW_{beat['CHARACTER'].lower()}.mp3"


def _runtime_path(beat: dict) -> Path:
    return RUNTIME_AUDIO_ROOT / _runtime_filename(beat)


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _base_audio_entry(beat: dict) -> dict:
    character = beat["CHARACTER"]
    approved = character == "HERO"
    voice_id = HERO_VOICE_ID if approved else None
    path = _runtime_path(beat)
    entry = {
        "ZONE": 3,
        "LOCALE": "zh-TW",
        "SHOT_ID": beat["SHOT_ID"],
        "BEAT_ID": beat["BEAT_ID"],
        "CHARACTER": character,
        "I18N_KEY": beat["I18N_KEY"],
        "TEXT_HASH": _text_hash(beat["VISIBLE_TEXT"]),
        "VOICE_ID": voice_id,
        "VOICE_LANGUAGE": "zh" if approved else None,
        "AUDIO_PATH": _relative(path) if path.is_file() else None,
        "DURATION_MS": None,
        "BYTES": None,
        "SHA256": None,
        "OWNER_APPROVED_VOICE": approved,
        "VOICE_STATUS": "OWNER_APPROVED_PRODUCTION" if approved else "PENDING_OWNER_SELECTION",
        "PRONUNCIATION_OVERRIDE": None,
    }
    if path.is_file():
        entry["DURATION_MS"], entry["BYTES"], entry["SHA256"] = _file_metadata(path)
    elif approved:
        entry["VOICE_STATUS"] = "OWNER_APPROVED_PENDING_GENERATION"
    return entry


def _write_audio_manifest(subtitles: dict) -> dict:
    AUDIO_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "SCHEMA_VERSION": "E10_ZONE3_CINEMATIC_AUDIO_MANIFEST_V1",
        "ZONE": 3,
        "LOCALE": "zh-TW",
        "CANONICAL_SCRIPT_SOURCE": subtitles["CANONICAL_SCRIPT_SOURCE"],
        "TEXT_SOURCE": _relative(SUBTITLE_MANIFEST_PATH),
        "LOCALE_SCOPED_AUDIO_MANIFEST": True,
        "VOICE_LANGUAGE_MISMATCH": "FORBIDDEN",
        "MISSING_LOCALE_VOICE_FALLBACK": "SUBTITLE_ONLY",
        "REPLAY_DIALOGUE_SOURCE": _relative(SUBTITLE_MANIFEST_PATH),
        "entries": [_base_audio_entry(beat) for beat in subtitles["beats"]],
    }
    AUDIO_MANIFEST_PATH.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return document


def _load_existing_audio_entries() -> dict[str, dict]:
    if not AUDIO_MANIFEST_PATH.is_file():
        return {}
    try:
        document = json.loads(AUDIO_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = document.get("entries") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        return {}
    return {
        entry["BEAT_ID"]: entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("BEAT_ID"), str)
    }


def _production_entry(beat: dict) -> dict:
    character = beat["CHARACTER"]
    voice_id, voice_name = LOCKED_PRODUCTION_VOICES[character]
    path = _runtime_path(beat)
    entry = {
        "ZONE": 3,
        "LOCALE": "zh-TW",
        "SHOT_ID": beat["SHOT_ID"],
        "BEAT_ID": beat["BEAT_ID"],
        "CHARACTER": character,
        "I18N_KEY": beat["I18N_KEY"],
        "TEXT_HASH": _text_hash(beat["VISIBLE_TEXT"]),
        "VOICE_NAME": voice_name,
        "VOICE_ID": voice_id,
        "VOICE_LANGUAGE": "zh",
        "AUDIO_PATH": _relative(path) if path.is_file() else None,
        "DURATION_MS": None,
        "BYTES": None,
        "SHA256": None,
        "OWNER_APPROVED_VOICE": True,
        "VOICE_STATUS": "OWNER_APPROVED_PENDING_GENERATION",
        "PRONUNCIATION_OVERRIDE": None,
    }
    if path.is_file():
        try:
            entry["DURATION_MS"], entry["BYTES"], entry["SHA256"] = _file_metadata(path)
        except Exception:
            entry["AUDIO_PATH"] = None
        else:
            entry["VOICE_STATUS"] = "OWNER_APPROVED_PRODUCTION"
    return entry


def _write_final_audio_manifest(subtitles: dict) -> dict:
    """Write the one locale-scoped production manifest from subtitle beats."""
    AUDIO_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "SCHEMA_VERSION": "E10_ZONE3_CINEMATIC_AUDIO_MANIFEST_V1",
        "ZONE": 3,
        "LOCALE": "zh-TW",
        "CANONICAL_SCRIPT_SOURCE": subtitles["CANONICAL_SCRIPT_SOURCE"],
        "TEXT_SOURCE": _relative(SUBTITLE_MANIFEST_PATH),
        "LOCALE_SCOPED_AUDIO_MANIFEST": True,
        "VOICE_LANGUAGE_MISMATCH": "FORBIDDEN",
        "MISSING_LOCALE_VOICE_FALLBACK": "SUBTITLE_ONLY",
        "REPLAY_DIALOGUE_SOURCE": _relative(SUBTITLE_MANIFEST_PATH),
        "entries": [_production_entry(beat) for beat in subtitles["beats"]],
    }
    AUDIO_MANIFEST_PATH.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return document


def _metadata_matches_entry(path: Path, entry: dict, beat: dict, voice_id: str) -> bool:
    if not path.is_file() or not isinstance(entry, dict):
        return False
    if (
        entry.get("ZONE") != 3
        or entry.get("LOCALE") != "zh-TW"
        or entry.get("BEAT_ID") != beat["BEAT_ID"]
        or entry.get("I18N_KEY") != beat["I18N_KEY"]
        or entry.get("TEXT_HASH") != _text_hash(beat["VISIBLE_TEXT"])
        or entry.get("VOICE_ID") != voice_id
        or entry.get("AUDIO_PATH") != _relative(path)
        or entry.get("OWNER_APPROVED_VOICE") is not True
        or entry.get("VOICE_STATUS") != "OWNER_APPROVED_PRODUCTION"
    ):
        return False
    try:
        duration_ms, byte_count, sha256 = _file_metadata(path)
    except Exception:
        return False
    return (
        duration_ms > 0
        and byte_count > 0
        and entry.get("DURATION_MS") == duration_ms
        and entry.get("BYTES") == byte_count
        and entry.get("SHA256") == sha256
    )


def _verify_existing_hero(subtitles: dict, existing_entries: dict[str, dict]) -> None:
    """Fail closed if any already-approved Hero runtime file is missing/corrupt."""
    hero_beats = [beat for beat in subtitles["beats"] if beat["CHARACTER"] == "HERO"]
    failures = []
    for beat in hero_beats:
        path = _runtime_path(beat)
        if not _metadata_matches_entry(path, existing_entries.get(beat["BEAT_ID"], {}), beat, HERO_VOICE_ID):
            failures.append(beat["BEAT_ID"])
    if failures:
        raise RuntimeError("HERO_EXISTING_AUDIO_CORRUPTION=" + ",".join(failures))


def _verify_final_manifest(document: dict, subtitles: dict) -> None:
    entries = document.get("entries") if isinstance(document, dict) else None
    expected = subtitles["beats"]
    if not isinstance(entries, list) or len(entries) != len(expected):
        raise RuntimeError("FINAL_AUDIO_MANIFEST_COUNT_MISMATCH")
    by_id = {entry.get("BEAT_ID"): entry for entry in entries if isinstance(entry, dict)}
    if len(by_id) != len(entries) or set(by_id) != {beat["BEAT_ID"] for beat in expected}:
        raise RuntimeError("FINAL_AUDIO_MANIFEST_ID_MISMATCH")
    for beat in expected:
        entry = by_id[beat["BEAT_ID"]]
        voice_id, _ = LOCKED_PRODUCTION_VOICES[beat["CHARACTER"]]
        if not _metadata_matches_entry(_runtime_path(beat), entry, beat, voice_id):
            raise RuntimeError("FINAL_AUDIO_MANIFEST_ENTRY_INVALID=" + beat["BEAT_ID"])


def _generate_final_production(subtitles: dict, audio_tool) -> int:
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        print("AUDIO_AUTH_STATUS=UNAVAILABLE")
        return 2

    existing_entries = _load_existing_audio_entries()
    _verify_existing_hero(subtitles, existing_entries)
    targets = [beat for beat in subtitles["beats"] if beat["CHARACTER"] != "HERO"]
    generated_ids = {"GRIK": set(), "CENTURION": set()}
    generated = 0
    skipped = 0
    for beat in targets:
        path = _runtime_path(beat)
        path.parent.mkdir(parents=True, exist_ok=True)
        voice_id, voice_name = LOCKED_PRODUCTION_VOICES[beat["CHARACTER"]]
        current_entry = existing_entries.get(beat["BEAT_ID"], {})
        if _metadata_matches_entry(path, current_entry, beat, voice_id):
            print(f"SKIP existing {beat['BEAT_ID']} ({voice_name})")
            skipped += 1
            continue
        print(f"Generating {beat['BEAT_ID']} ({voice_name}) ...")
        if not audio_tool._text_to_speech(api_key, voice_id, beat["VISIBLE_TEXT"], MODEL_ID, path):
            raise RuntimeError("TTS_GENERATION_FAILED=" + beat["BEAT_ID"])
        duration_ms, byte_count, sha256 = _file_metadata(path)
        if duration_ms <= 0 or byte_count <= 0 or not sha256:
            raise RuntimeError("TTS_OUTPUT_INVALID=" + beat["BEAT_ID"])
        generated_ids[beat["CHARACTER"]].add(beat["BEAT_ID"])
        generated += 1
        # Persist a resumable manifest checkpoint after each successful beat.
        _write_final_audio_manifest(subtitles)
        existing_entries = _load_existing_audio_entries()

    final_manifest = _write_final_audio_manifest(subtitles)
    _verify_final_manifest(final_manifest, subtitles)
    print(f"GRIK_PRODUCTION_GENERATED={len(generated_ids['GRIK'])}/37")
    print(f"CENTURION_PRODUCTION_GENERATED={len(generated_ids['CENTURION'])}/19")
    print(f"FINAL_PRODUCTION_GENERATED={generated}")
    print(f"FINAL_PRODUCTION_SKIPPED={skipped}")
    print("FINAL_PRODUCTION_VERIFICATION=PASS")
    return 0


def _find_beat(subtitles: dict, beat_id: str) -> dict:
    for beat in subtitles["beats"]:
        if beat["BEAT_ID"] == beat_id:
            return beat
    raise ValueError(f"audition beat not found: {beat_id}")


def _audition_path(character: str, voice_id: str) -> Path:
    return AUDITION_ROOT / character.lower() / f"{character.lower()}_{voice_id}.mp3"


def _generate_auditions(subtitles: dict, audio_tool) -> dict:
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        print("AUDIO_AUTH_STATUS=UNAVAILABLE")
        return {"status": "BLOCKED_AUDIO_AUTH_ONLY", "candidates": []}

    specs = (
        ("GRIK", "Z3_S03_B007", GRIK_CANDIDATES),
        ("CENTURION", "Z3_S06_B003", CENTURION_CANDIDATES),
    )
    candidates = []
    for character, beat_id, voices in specs:
        beat = _find_beat(subtitles, beat_id)
        for voice_id, name, direction in voices:
            path = _audition_path(character, voice_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            print(f"Generating {character} audition {name} ({voice_id}) ...")
            ok = bool(audio_tool._text_to_speech(api_key, voice_id, beat["VISIBLE_TEXT"], MODEL_ID, path))
            record = {
                "ZONE": 3,
                "LOCALE": "zh-TW",
                "SHOT_ID": beat["SHOT_ID"],
                "BEAT_ID": beat["BEAT_ID"],
                "CHARACTER": character,
                "I18N_KEY": beat["I18N_KEY"],
                "VISIBLE_TEXT": beat["VISIBLE_TEXT"],
                "TTS_INPUT_TEXT": beat["VISIBLE_TEXT"],
                "VOICE_ID": voice_id,
                "VOICE_LANGUAGE": "zh",
                "VOICE_NAME": name,
                "DIRECTION": direction,
                "AUDIO_PATH": _relative(path) if ok and path.is_file() else None,
                "DURATION_MS": None,
                "BYTES": None,
                "SHA256": None,
                "OWNER_APPROVED_VOICE": False,
                "GENERATED": ok and path.is_file(),
            }
            if record["GENERATED"]:
                record["DURATION_MS"], record["BYTES"], record["SHA256"] = _file_metadata(path)
            candidates.append(record)

    document = {
        "SCHEMA_VERSION": "E10_ZONE3_VOICE_AUDITION_MANIFEST_V1",
        "ZONE": 3,
        "LOCALE": "zh-TW",
        "STATUS": "OWNER_REVIEW_REQUIRED",
        "CANONICAL_SCRIPT_SOURCE": subtitles["CANONICAL_SCRIPT_SOURCE"],
        "NO_RUNTIME_WIRING": True,
        "candidates": candidates,
    }
    AUDITION_MANIFEST_PATH.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    generated = sum(1 for item in candidates if item["GENERATED"])
    print(f"GRIK_AUDITION_GENERATED={sum(1 for item in candidates if item['CHARACTER'] == 'GRIK' and item['GENERATED'])}/3")
    print(f"CENTURION_AUDITION_GENERATED={sum(1 for item in candidates if item['CHARACTER'] == 'CENTURION' and item['GENERATED'])}/3")
    print(f"AUDITION_GENERATED_TOTAL={generated}/6")
    return {"status": "OWNER_REVIEW_REQUIRED", "candidates": candidates}


def _generate_hero(subtitles: dict, audio_tool) -> int:
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        print("AUDIO_AUTH_STATUS=UNAVAILABLE")
        return 0
    hero_beats = [beat for beat in subtitles["beats"] if beat["CHARACTER"] == "HERO"]
    generated = 0
    for beat in hero_beats:
        path = _runtime_path(beat)
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Generating Hero {beat['BEAT_ID']} ...")
        if path.is_file():
            print(f"SKIP existing {path.name}")
            generated += 1
            continue
        if audio_tool._text_to_speech(api_key, HERO_VOICE_ID, beat["VISIBLE_TEXT"], MODEL_ID, path):
            generated += 1
    print(f"HERO_PRODUCTION_GENERATED={generated}/{len(hero_beats)}")
    return generated


def main() -> int:
    parser = argparse.ArgumentParser(description="E10 Zone 3 localized audio production and bounded auditions")
    parser.add_argument("--hero-production", action="store_true", help="Generate all Hero zh-TW beats using the locked Roy voice")
    parser.add_argument("--auditions", action="store_true", help="Generate exactly three Grik and three Centurion auditions")
    parser.add_argument("--final-production", action="store_true", help="Generate the locked Grik and Centurion runtime beats without regenerating Hero")
    parser.add_argument("--manifest-only", action="store_true", help="Write the deterministic audio manifest without network calls")
    args = parser.parse_args()
    if not (args.hero_production or args.auditions or args.final_production or args.manifest_only):
        parser.error("choose --hero-production, --auditions, --final-production, or --manifest-only")
    if args.final_production and (args.hero_production or args.auditions or args.manifest_only):
        parser.error("--final-production cannot be combined with another mode")

    subtitles = _load_subtitles()
    audio_tool = None
    if not args.manifest_only:
        audio_tool = _load_zone1_tool()
    if args.final_production:
        result = _generate_final_production(subtitles, audio_tool)
        print(f"AUDIO_MANIFEST_PATH={_relative(AUDIO_MANIFEST_PATH)}")
        print(f"AUDIO_MANIFEST_ENTRIES={len(subtitles['beats'])}")
        return result
    if args.hero_production:
        if not os.environ.get(API_KEY_ENV):
            print("AUDIO_AUTH_STATUS=UNAVAILABLE")
        else:
            _generate_hero(subtitles, audio_tool)
    audition_result = None
    if args.auditions:
        audition_result = _generate_auditions(subtitles, audio_tool)
    audio_manifest = _write_audio_manifest(subtitles)
    print(f"AUDIO_MANIFEST_PATH={_relative(AUDIO_MANIFEST_PATH)}")
    print(f"AUDIO_MANIFEST_ENTRIES={len(audio_manifest['entries'])}")
    if audition_result and audition_result["status"] == "BLOCKED_AUDIO_AUTH_ONLY":
        print("GRIK_AUDITION_STATUS=BLOCKED_AUDIO_AUTH_ONLY")
        print("CENTURION_AUDITION_STATUS=BLOCKED_AUDIO_AUTH_ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
