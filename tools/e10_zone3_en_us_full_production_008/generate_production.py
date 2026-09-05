"""Generate the Owner-approved Zone 3 en-US British-English production layer.

The committed en-US subtitle manifest is the sole dialogue source.  This
producer writes the locale-scoped production MP3s and manifest only; it does
not alter the Journey controller or any gameplay authority.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

from mutagen.mp3 import MP3


ROOT = Path(__file__).resolve().parents[2]
SUBTITLE_PATH = ROOT / "assets" / "e10" / "i18n" / "zone3" / "zone3-cinematic-subtitles-en-US.json"
AUDIO_ROOT = ROOT / "assets" / "e10" / "audio" / "zone3" / "dialogue" / "en-US"
AUDIO_MANIFEST_PATH = ROOT / "assets" / "e10" / "audio" / "zone3" / "zone3-cinematic-audio-manifest-en-US.json"
ZONE1_TOOL_PATH = ROOT / "tools" / "e10_zone1_audio" / "generate_zone1_audio.py"
API_KEY_ENV = "ELEVENLABS_API_KEY"
MODEL_ID = "eleven_v3"

APPROVED_CAST = {
    "HERO": {"VOICE_NAME": "Steve", "VOICE_ID": "RasuOwPKPBy67j7E43Su"},
    "GRIK": {"VOICE_NAME": "Nick", "VOICE_ID": "v4mOufztUtjxcpk65aWy"},
    "CENTURION": {"VOICE_NAME": "Mark", "VOICE_ID": "cso37AjcTkVqyjGkWbRz"},
}
FORBIDDEN_VOICE_IDS = {
    "6aOpkucJD6a4vTXyUKon",  # historical Anvay
    "DSyEP4HEaCKur8rFFOri",  # historical Zack
    "BrbEfHMQu0fyclQR7lfh",  # historical Kevin Tu
    "dqdOhmL2BvMSx2KtSAtN",  # prior Ali audition
    "3ZRnKeY0H10hhITAYx9o",  # prior Joe audition
    "wYz62et1CZw6fTWrIFHJ",  # prior Robert audition
    "JZ5PEPqtr05GbBRBqPhz",  # prior Craig audition
    "WoxRV1VQUDtxEHPVAZyL",  # prior Ethan audition
    "BuptxElFd80GDtsmyQIU",  # prior Alfie audition
}


def _load_helper():
    spec = importlib.util.spec_from_file_location("e10_zone1_audio_helper", ZONE1_TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load established ElevenLabs helper: {ZONE1_TOOL_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_subtitles() -> dict:
    document = json.loads(SUBTITLE_PATH.read_text(encoding="utf-8"))
    beats = document.get("beats")
    if not isinstance(beats, list) or len(beats) != 97:
        raise ValueError("en-US subtitle manifest must contain exactly 97 beats")
    ids = [beat.get("BEAT_ID") for beat in beats]
    if len(set(ids)) != 97 or any(not isinstance(value, str) or not value for value in ids):
        raise ValueError("en-US subtitle manifest has duplicate or empty beat IDs")
    if any(beat.get("ZONE") != 3 or beat.get("LOCALE") != "en-US" for beat in beats):
        raise ValueError("en-US subtitle manifest contains an invalid zone or locale")
    if any(beat.get("CHARACTER") not in APPROVED_CAST for beat in beats):
        raise ValueError("en-US subtitle manifest contains an unknown speaker")
    if {beat.get("SHOT_ID") for beat in beats} != {f"SHOT{number:02d}" for number in range(1, 11)}:
        raise ValueError("en-US subtitle manifest must represent all ten shots")
    return document


def _metadata(path: Path) -> tuple[int, int, str]:
    payload = path.read_bytes()
    duration_ms = round(float(MP3(path).info.length) * 1000)
    return duration_ms, len(payload), hashlib.sha256(payload).hexdigest()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _runtime_path(beat: dict) -> Path:
    beat_number = beat["BEAT_ID"].split("_")[-1].lower()
    return AUDIO_ROOT / (
        f"zone3_{beat['SHOT_ID'].lower()}_{beat_number}_en-US_{beat['CHARACTER'].lower()}.mp3"
    )


def _load_existing_manifest() -> dict | None:
    if not AUDIO_MANIFEST_PATH.is_file():
        return None
    try:
        value = json.loads(AUDIO_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _entry_matches(beat: dict, entry: dict, path: Path) -> bool:
    if not isinstance(entry, dict) or not path.is_file():
        return False
    cast = APPROVED_CAST[beat["CHARACTER"]]
    if (
        entry.get("ZONE") != 3
        or entry.get("LOCALE") != "en-US"
        or entry.get("SHOT_ID") != beat["SHOT_ID"]
        or entry.get("BEAT_ID") != beat["BEAT_ID"]
        or entry.get("I18N_KEY") != beat["I18N_KEY"]
        or entry.get("SPEAKER") != beat["CHARACTER"]
        or entry.get("EXACT_TEXT") != beat["VISIBLE_TEXT"]
        or entry.get("TEXT_HASH") != _text_hash(beat["VISIBLE_TEXT"])
        or entry.get("VOICE_ID") != cast["VOICE_ID"]
        or entry.get("AUDIO_PATH") != _relative(path)
        or entry.get("OWNER_APPROVED_VOICE") is not True
        or entry.get("VOICE_STATUS") != "OWNER_APPROVED_PRODUCTION"
    ):
        return False
    try:
        duration_ms, byte_count, sha256 = _metadata(path)
    except Exception:
        return False
    return (
        duration_ms > 0
        and byte_count > 0
        and entry.get("DURATION_MS") == duration_ms
        and entry.get("BYTES") == byte_count
        and entry.get("SHA256") == sha256
    )


def _production_entry(beat: dict, path: Path, metadata: tuple[int, int, str]) -> dict:
    cast = APPROVED_CAST[beat["CHARACTER"]]
    duration_ms, byte_count, sha256 = metadata
    return {
        "ZONE": 3,
        "LOCALE": "en-US",
        "SHOT_ID": beat["SHOT_ID"],
        "BEAT_ID": beat["BEAT_ID"],
        "SPEAKER": beat["CHARACTER"],
        "CHARACTER": beat["CHARACTER"],
        "I18N_KEY": beat["I18N_KEY"],
        "EXACT_TEXT": beat["VISIBLE_TEXT"],
        "TEXT_HASH": _text_hash(beat["VISIBLE_TEXT"]),
        "VOICE_NAME": cast["VOICE_NAME"],
        "VOICE_ID": cast["VOICE_ID"],
        "VOICE_LANGUAGE": "en",
        "AUDIO_PATH": _relative(path),
        "DURATION_MS": duration_ms,
        "BYTES": byte_count,
        "SHA256": sha256,
        "OWNER_APPROVED_VOICE": True,
        "VOICE_STATUS": "OWNER_APPROVED_PRODUCTION",
        "PRONUNCIATION_OVERRIDE": None,
    }


def _write_manifest(subtitles: dict, entries: list[dict], voice_metadata: dict) -> None:
    document = {
        "SCHEMA_VERSION": "E10_ZONE3_CINEMATIC_AUDIO_MANIFEST_V1",
        "ZONE": 3,
        "LOCALE": "en-US",
        "APPLICATION_LOCALE": "en",
        "CANONICAL_SCRIPT_SOURCE": _relative(SUBTITLE_PATH),
        "TEXT_SOURCE": _relative(SUBTITLE_PATH),
        "LOCALE_SCOPED_AUDIO_MANIFEST": True,
        "VOICE_LANGUAGE": "en",
        "VOICE_LANGUAGE_MISMATCH": "FORBIDDEN",
        "MISSING_LOCALE_VOICE_FALLBACK": "SUBTITLE_ONLY",
        "REPLAY_DIALOGUE_SOURCE": _relative(SUBTITLE_PATH),
        "REPLAY_REWARD_MUTATION": "FORBIDDEN",
        "OWNER_APPROVED_CAST": APPROVED_CAST,
        "VOICE_METADATA": voice_metadata,
        "EN_US_DIALOGUE_BEATS": len(subtitles["beats"]),
        "EN_US_PRODUCTION_AUDIO_COUNT": len(entries),
        "entries": entries,
    }
    AUDIO_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIO_MANIFEST_PATH.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _voice_metadata(helper, api_key: str) -> dict:
    status, body = helper._api_get("/v1/voices", api_key)
    if status != 200 or not isinstance(body, dict):
        raise RuntimeError(f"VOICE_METADATA_UNAVAILABLE_HTTP_STATUS={status}")
    voices = {
        voice.get("voice_id"): voice
        for voice in body.get("voices", [])
        if isinstance(voice, dict) and voice.get("voice_id")
    }
    result = {}
    for character, cast in APPROVED_CAST.items():
        voice = voices.get(cast["VOICE_ID"])
        if not voice:
            raise RuntimeError(f"SELECTED_VOICE_MISSING={character}")
        labels = voice.get("labels") if isinstance(voice.get("labels"), dict) else {}
        accent = str(labels.get("accent") or voice.get("accent") or "").lower()
        language = str(labels.get("language") or voice.get("language") or "").lower()
        age = labels.get("age") or voice.get("age")
        gender = labels.get("gender") or voice.get("gender")
        if accent != "british" or language != "en" or str(gender).lower() != "male":
            raise RuntimeError(f"SELECTED_VOICE_ACCENT_OR_LANGUAGE_CONFLICT={character}")
        result[character] = {
            "VOICE_ID": cast["VOICE_ID"],
            "OWNER_VOICE_NAME": cast["VOICE_NAME"],
            "ELEVENLABS_ACCOUNT_NAME": voice.get("name"),
            "ACCENT_METADATA": accent,
            "LANGUAGE_METADATA": language,
            "AGE_PROFILE": age,
            "GENDER_METADATA": gender,
            "DESCRIPTION": voice.get("description"),
            "LABELS": labels,
        }
    return result


def main() -> int:
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        print("AUDIO_AUTH_STATUS=UNAVAILABLE")
        return 2

    subtitles = _load_subtitles()
    helper = _load_helper()
    voice_metadata = _voice_metadata(helper, api_key)
    existing = _load_existing_manifest()
    existing_entries = {
        entry.get("BEAT_ID"): entry
        for entry in (existing or {}).get("entries", [])
        if isinstance(entry, dict) and isinstance(entry.get("BEAT_ID"), str)
    }

    records = []
    generated = 0
    skipped = 0
    for beat in subtitles["beats"]:
        path = _runtime_path(beat)
        if _entry_matches(beat, existing_entries.get(beat["BEAT_ID"]), path):
            records.append(existing_entries[beat["BEAT_ID"]])
            skipped += 1
            continue
        if path.exists():
            raise RuntimeError(f"EXISTING_AUDIO_INVALID_OR_UNMAPPED={_relative(path)}")
        path.parent.mkdir(parents=True, exist_ok=True)
        cast = APPROVED_CAST[beat["CHARACTER"]]
        print(f"Generating {beat['BEAT_ID']} ({cast['VOICE_NAME']}) ...")
        if not helper._text_to_speech(api_key, cast["VOICE_ID"], beat["VISIBLE_TEXT"], MODEL_ID, path):
            raise RuntimeError(f"TTS_GENERATION_FAILED={beat['BEAT_ID']}")
        metadata = _metadata(path)
        if metadata[0] <= 0 or metadata[1] <= 0 or not metadata[2]:
            raise RuntimeError(f"TTS_OUTPUT_INVALID={beat['BEAT_ID']}")
        records.append(_production_entry(beat, path, metadata))
        generated += 1

    if len(records) != 97:
        raise RuntimeError("PRODUCTION_RECORD_COUNT_MISMATCH")
    _write_manifest(subtitles, records, voice_metadata)
    written = json.loads(AUDIO_MANIFEST_PATH.read_text(encoding="utf-8"))
    by_id = {entry.get("BEAT_ID"): entry for entry in written.get("entries", [])}
    if len(by_id) != 97 or set(by_id) != {beat["BEAT_ID"] for beat in subtitles["beats"]}:
        raise RuntimeError("MANIFEST_BEAT_ALIGNMENT_FAILED")
    for beat in subtitles["beats"]:
        path = _runtime_path(beat)
        if not _entry_matches(beat, by_id[beat["BEAT_ID"]], path):
            raise RuntimeError(f"MANIFEST_AUDIO_ENTRY_INVALID={beat['BEAT_ID']}")
    if any(entry.get("VOICE_ID") in FORBIDDEN_VOICE_IDS for entry in written["entries"]):
        raise RuntimeError("FORBIDDEN_VOICE_PRODUCTION_BINDING")

    print("AUDIO_AUTH_STATUS=AVAILABLE")
    print("AUDIO_TECHNICAL_QA=PASS")
    print(f"EN_US_PRODUCTION_AUDIO_COUNT={len(records)}")
    print(f"PRODUCTION_GENERATED={generated}")
    print(f"PRODUCTION_SKIPPED={skipped}")
    print(f"AUDIO_MANIFEST_PATH={_relative(AUDIO_MANIFEST_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
