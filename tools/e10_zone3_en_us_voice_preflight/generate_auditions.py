"""Generate the two bounded Zone 3 en-US voice auditions.

This is an Owner-review-only adapter.  It reads ELEVENLABS_API_KEY from the
current process environment, delegates the request to the established Zone 1
ElevenLabs helper, and never writes runtime audio or a credential.  It emits
one Grik audition and one Centurion audition from the canonical en-US script;
it does not generate the 97-beat production package.
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
SCRIPT_PATH = ROOT / "assets" / "e10" / "i18n" / "zone3" / "zone3-cinematic-subtitles-en-US.json"
OUTPUT_ROOT = ROOT / "tools" / "e10_zone3_audio" / "_local_review" / "auditions" / "en-US"
PACKAGE_PATH = ROOT / "tools" / "e10_zone3_audio" / "zone3_en_us_voice_audition_manifest.json"
ZONE1_TOOL_PATH = ROOT / "tools" / "e10_zone1_audio" / "generate_zone1_audio.py"
API_KEY_ENV = "ELEVENLABS_API_KEY"
MODEL_ID = "eleven_v3"

AUDITION_SPECS = (
    {
        "character": "GRIK",
        "beat_id": "Z3_S03_B003",
        "candidate_label": "GRIK_EN_US_ZACK_R1",
        "voice_name": "Zack",
        "voice_id": "DSyEP4HEaCKur8rFFOri",
        "performance_direction": (
            "young voice, slight rasp, tired and guarded, with kindness underneath; "
            "natural spoken English, never a monster growl or comic goblin read"
        ),
        "output_name": "grik_en-us_zack_r1.mp3",
    },
    {
        "character": "CENTURION",
        "beat_id": "Z3_S06_B003",
        "candidate_label": "CENTURION_EN_US_KEVIN_TU_R1",
        "voice_name": "Kevin Tu",
        "voice_id": "BrbEfHMQu0fyclQR7lfh",
        "performance_direction": (
            "middle-aged, weathered, controlled and protective; heavy but restrained; "
            "never villainous, monstrous, berserk, or an elderly caricature"
        ),
        "output_name": "centurion_en-us_kevin-tu_r1.mp3",
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


def _load_script() -> dict:
    document = json.loads(SCRIPT_PATH.read_text(encoding="utf-8"))
    beats = document.get("beats")
    if not isinstance(beats, list) or len(beats) != 97:
        raise ValueError("en-US script must contain exactly 97 beats")
    return document


def _find_beat(script: dict, beat_id: str) -> dict:
    for beat in script["beats"]:
        if beat.get("BEAT_ID") == beat_id:
            return beat
    raise ValueError(f"missing audition beat: {beat_id}")


def _metadata(path: Path) -> tuple[int, int, str]:
    data = path.read_bytes()
    duration_ms = round(float(MP3(path).info.length) * 1000)
    return duration_ms, len(data), hashlib.sha256(data).hexdigest()


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def main() -> int:
    script = _load_script()
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        print("AUDIO_AUTH_STATUS=UNAVAILABLE")
        print("OWNER_AUDITION_PACKAGE_STATUS=BLOCKED_AUDIO_AUTH_ONLY")
        return 2

    audio_helper = _load_zone1_helper()
    records = []
    for spec in AUDITION_SPECS:
        beat = _find_beat(script, spec["beat_id"])
        output_path = OUTPUT_ROOT / spec["character"].lower() / spec["output_name"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Generating {spec['character']} en-US audition ...")
        if not audio_helper._text_to_speech(
            api_key,
            spec["voice_id"],
            beat["VISIBLE_TEXT"],
            MODEL_ID,
            output_path,
        ):
            print(f"OWNER_AUDITION_PACKAGE_STATUS=FAILED_{spec['character']}")
            return 1
        duration_ms, byte_count, sha256 = _metadata(output_path)
        if duration_ms <= 0 or byte_count <= 0:
            print(f"OWNER_AUDITION_PACKAGE_STATUS=INVALID_{spec['character']}")
            return 1
        records.append(
            {
                "CHARACTER": spec["character"],
                "CANDIDATE_LABEL": spec["candidate_label"],
                "VOICE_NAME": spec["voice_name"],
                "VOICE_ID": spec["voice_id"],
                "ENGLISH_SAMPLE_TEXT": beat["VISIBLE_TEXT"],
                "SHOT_ID": beat["SHOT_ID"],
                "BEAT_ID": beat["BEAT_ID"],
                "I18N_KEY": beat["I18N_KEY"],
                "PERFORMANCE_DIRECTION": spec["performance_direction"],
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
        "SCHEMA_VERSION": "W1_03_ZONE3_EN_US_OWNER_AUDITION_PACKAGE_V1",
        "ZONE": 3,
        "LOCALE": "en-US",
        "SCRIPT_SOURCE": _relative(SCRIPT_PATH),
        "STATUS": "OWNER_REVIEW_REQUIRED",
        "NO_RUNTIME_WIRING": True,
        "NO_FULL_PRODUCTION_AUDIO": True,
        "CROSS_LANGUAGE_VOICE_FALLBACK": "FORBIDDEN",
        "candidates": records,
    }
    PACKAGE_PATH.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("GRIK_ENGLISH_AUDITION_COUNT=1")
    print("CENTURION_ENGLISH_AUDITION_COUNT=1")
    print("OWNER_AUDITION_PACKAGE_STATUS=OWNER_REVIEW_REQUIRED")
    print(f"OWNER_AUDITION_MANIFEST={_relative(PACKAGE_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
