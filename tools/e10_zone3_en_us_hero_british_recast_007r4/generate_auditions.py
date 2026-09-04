"""Generate the bounded Zone 3 en-US British-English Hero audition round.

This is an Owner-review-only producer.  It reads one exact Hero beat from the
committed 97-beat English subtitle manifest and uses the established Zone 1
ElevenLabs request helper.  It writes exactly three audition files and a
manifest; it never creates runtime bindings or full-production audio.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

from mutagen.mp3 import MP3


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "assets" / "e10" / "i18n" / "zone3" / "zone3-cinematic-subtitles-en-US.json"
OUTPUT_ROOT = ROOT / "tools" / "e10_zone3_audio" / "_local_review" / "auditions" / "en-US-british-hero-round1"
PACKAGE_PATH = ROOT / "tools" / "e10_zone3_audio" / "zone3_en_us_hero_british_round1_audition_manifest.json"
ZONE1_TOOL_PATH = ROOT / "tools" / "e10_zone1_audio" / "generate_zone1_audio.py"
API_KEY_ENV = "ELEVENLABS_API_KEY"
MODEL_ID = "eleven_v3"
AUDITION_BEAT_ID = "Z3_S07_B007"
REJECTED_HISTORICAL_ANVAY_ID = "6aOpkucJD6a4vTXyUKon"


# These three candidates are a bounded shortlist from the live Voice Library
# search.  The metadata is retained for Owner comparison; it is not an
# approval or runtime cast lock.
CANDIDATES = (
    {
        "label": "HERO_A",
        "name": "Steve - Calm, Youthful & Positive",
        "voice_id": "RasuOwPKPBy67j7E43Su",
        "public_owner_id": "273015a5bfc07d2e8de9a7a5b1a015b10ebdb4f5ac430ca011c9665cf8e6da40",
        "accent": "british",
        "age": "young",
        "gender": "male",
        "language": "en",
        "category": "professional",
        "description": "Youthful calm voice, great for narration and voice over.",
        "why": "Young-male British metadata and a calm youthful brief make this a grounded, child-readable baseline.",
    },
    {
        "label": "HERO_B",
        "name": "Ethan - Warm & Trusting",
        "voice_id": "WoxRV1VQUDtxEHPVAZyL",
        "public_owner_id": "a665df52dbd0dedd42374a35dc4af1074e41a24dd28b9a678b47e142d0e9e789",
        "accent": "british",
        "age": "young",
        "gender": "male",
        "language": "en",
        "category": "professional",
        "description": "Authentic British male voice with a warm, trustworthy tone and strong acting foundation; suited to video games and emotionally grounded character work.",
        "why": "Existing UK voice-pool continuity plus warm, trusting character-work metadata gives a natural adventure-hero comparison.",
    },
    {
        "label": "HERO_C",
        "name": "Alfie - Clear & Expressive",
        "voice_id": "BuptxElFd80GDtsmyQIU",
        "public_owner_id": "7af658e028c1310ee29f3c29252123e419f09f04e6d8a5e95c9b06dba1ba1aec",
        "accent": "british",
        "age": "young",
        "gender": "male",
        "language": "en",
        "category": "professional",
        "description": "Young, British, expressive voice; suitable for calm and clear conversation.",
        "why": "Young British metadata and clear expressive delivery provide a more emotionally readable alternative without a narrator or warrior brief.",
    },
)


def _load_zone1_helper():
    spec = importlib.util.spec_from_file_location("e10_zone1_audio_helper", ZONE1_TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load established ElevenLabs helper: {ZONE1_TOOL_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_script() -> tuple[dict, dict]:
    document = json.loads(SCRIPT_PATH.read_text(encoding="utf-8"))
    beats = document.get("beats")
    if not isinstance(beats, list) or len(beats) != 97:
        raise ValueError("en-US script must contain exactly 97 beats")
    by_id = {beat.get("BEAT_ID"): beat for beat in beats}
    if len(by_id) != 97 or any(not isinstance(key, str) or not key for key in by_id):
        raise ValueError("en-US script has duplicate or empty beat identities")
    beat = by_id.get(AUDITION_BEAT_ID)
    if not beat or beat.get("ZONE") != 3 or beat.get("LOCALE") != "en-US":
        raise ValueError(f"missing canonical Hero audition beat: {AUDITION_BEAT_ID}")
    if beat.get("CHARACTER") != "HERO":
        raise ValueError(f"audition beat is not a Hero line: {AUDITION_BEAT_ID}")
    return document, beat


def _metadata(path: Path) -> tuple[int, int, str]:
    payload = path.read_bytes()
    duration_ms = round(float(MP3(path).info.length) * 1000)
    return duration_ms, len(payload), hashlib.sha256(payload).hexdigest()


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _filename(label: str, name: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return f"hero_{label.split('_')[-1]}_{suffix}.mp3"


def _resolve_voice_id(helper, api_key: str, candidate: dict, current_voices: dict[str, dict]) -> str:
    public_id = candidate["voice_id"]
    if public_id in current_voices:
        return public_id
    status, body = helper._add_shared_voice(
        api_key,
        candidate["public_owner_id"],
        public_id,
        f"W1_03_Z3_007R4_{candidate['label']}",
    )
    if status not in (200, 201) or not isinstance(body, dict) or not body.get("voice_id"):
        detail = helper._describe_elevenlabs_error(status, body)
        raise RuntimeError(f"VOICE_ADD_FAILED candidate={candidate['label']} {detail}")
    return body["voice_id"]


def main() -> int:
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        print("AUDIO_AUTH_STATUS=UNAVAILABLE")
        return 2

    script, beat = _load_script()
    helper = _load_zone1_helper()
    status, body = helper._api_get("/v1/voices", api_key)
    if status != 200 or not isinstance(body, dict):
        print(f"VOICE_API_ACCESS=NO HTTP_STATUS={status}")
        return 1
    current_voices = {
        voice.get("voice_id"): voice
        for voice in body.get("voices", [])
        if isinstance(voice, dict) and voice.get("voice_id")
    }

    ids = [candidate["voice_id"] for candidate in CANDIDATES]
    if len(ids) != 3 or len(set(ids)) != 3:
        raise ValueError("Hero audition candidates must contain exactly three distinct voice IDs")
    if REJECTED_HISTORICAL_ANVAY_ID in ids:
        raise ValueError("historical Anvay voice is forbidden for new Zone 3 English Hero auditions")

    records = []
    for candidate in CANDIDATES:
        output_path = OUTPUT_ROOT / _filename(candidate["label"], candidate["name"])
        if output_path.exists():
            raise RuntimeError(f"refusing to overwrite existing audition: {output_path}")
        local_voice_id = _resolve_voice_id(helper, api_key, candidate, current_voices)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not helper._text_to_speech(api_key, local_voice_id, beat["VISIBLE_TEXT"], MODEL_ID, output_path):
            raise RuntimeError(f"TTS_FAILED candidate={candidate['label']}")
        duration_ms, byte_count, sha256 = _metadata(output_path)
        if duration_ms <= 0 or byte_count <= 0:
            raise RuntimeError(f"INVALID_AUDIO candidate={candidate['label']}")
        records.append(
            {
                "CHARACTER": "HERO",
                "CANDIDATE_LABEL": candidate["label"],
                "VOICE_NAME": candidate["name"],
                "VOICE_ID": local_voice_id,
                "SHARED_VOICE_ID": candidate["voice_id"],
                "ACCENT_METADATA": candidate["accent"],
                "LANGUAGE_METADATA": candidate["language"],
                "APPROXIMATE_AGE_PROFILE": candidate["age"],
                "GENDER_METADATA": candidate["gender"],
                "VOICE_CATEGORY": candidate["category"],
                "VOICE_CHARACTER": candidate["description"],
                "WHY_SHORTLISTED": candidate["why"],
                "SHOT_ID": beat["SHOT_ID"],
                "BEAT_ID": beat["BEAT_ID"],
                "I18N_KEY": beat["I18N_KEY"],
                "EXACT_SAMPLE_TEXT": beat["VISIBLE_TEXT"],
                "AUDIO_PATH": _relative(output_path),
                "BYTES": byte_count,
                "DURATION_MS": duration_ms,
                "SHA256": sha256,
                "MODEL_ID": MODEL_ID,
                "PROVIDER": "ElevenLabs",
                "OWNER_APPROVED_VOICE": False,
                "OWNER_APPROVAL": "PENDING",
                "RUNTIME_BINDING": "NONE",
            }
        )

    package = {
        "SCHEMA_VERSION": "W1_03_ZONE3_EN_US_BRITISH_HERO_OWNER_AUDITION_PACKAGE_V1",
        "ZONE": 3,
        "LOCALE": "en-US",
        "CHARACTER": "HERO",
        "SCRIPT_SOURCE": _relative(SCRIPT_PATH),
        "AUDITION_BEAT_ID": beat["BEAT_ID"],
        "AUDITION_SHOT_ID": beat["SHOT_ID"],
        "AUDITION_TEXT": beat["VISIBLE_TEXT"],
        "BRITISH_ENGLISH_ACCENT_REQUIREMENT": True,
        "GO_ODYSSEY_ENGLISH_VOICE_ACCENT_POLICY": "BRITISH_ENGLISH",
        "NEW_ENGLISH_PRODUCTION_NON_BRITISH_VOICE_ALLOWED": False,
        "STATUS": "OWNER_REVIEW_REQUIRED",
        "HERO_CANDIDATE_COUNT": 3,
        "TOTAL_NEW_AUDITION_COUNT": 3,
        "EN_US_DIALOGUE_BEATS": len(script["beats"]),
        "EN_US_SCRIPT_CHANGED": False,
        "ANVAY_HISTORICAL_VOICE_ID": REJECTED_HISTORICAL_ANVAY_ID,
        "ANVAY_NEW_ZONE3_BINDING_COUNT": 0,
        "NO_RUNTIME_WIRING": True,
        "NO_FULL_PRODUCTION_AUDIO": True,
        "CROSS_LANGUAGE_VOICE_FALLBACK": "FORBIDDEN",
        "HERO_OWNER_SELECTION": "PENDING",
        "GRIK_PRESERVED_VOICE": {"VOICE_NAME": "Nick", "VOICE_ID": "v4mOufztUtjxcpk65aWy"},
        "CENTURION_PRESERVED_VOICE": {"VOICE_NAME": "Mark", "VOICE_ID": "cso37AjcTkVqyjGkWbRz"},
        "ZH_TW_CHANGED": False,
        "candidates": records,
    }
    PACKAGE_PATH.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("AUDIO_AUTH_STATUS=AVAILABLE")
    print("AUTOMATED_AUDIO_TECHNICAL_QA=PASS")
    print("HERO_CANDIDATE_COUNT=3")
    print("TOTAL_NEW_AUDITION_COUNT=3")
    print(f"OWNER_AUDITION_MANIFEST={_relative(PACKAGE_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
