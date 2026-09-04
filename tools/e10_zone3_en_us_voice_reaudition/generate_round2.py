"""Generate the bounded Zone 3 en-US British-English audition round.

This is an Owner-review-only producer.  It reads the canonical 97-beat
English subtitle manifest, uses the established Zone 1 ElevenLabs request
helper, and writes exactly three Grik plus three Centurion audition files.
It never writes runtime audio, changes casting locks, or generates the full
97-beat production package.
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
OUTPUT_ROOT = ROOT / "tools" / "e10_zone3_audio" / "_local_review" / "auditions" / "en-US-british-round2"
PACKAGE_PATH = ROOT / "tools" / "e10_zone3_audio" / "zone3_en_us_british_round2_audition_manifest.json"
ZONE1_TOOL_PATH = ROOT / "tools" / "e10_zone1_audio" / "generate_zone1_audio.py"
API_KEY_ENV = "ELEVENLABS_API_KEY"
MODEL_ID = "eleven_v3"

REJECTED_IDS = {
    "DSyEP4HEaCKur8rFFOri",
    "BrbEfHMQu0fyclQR7lfh",
}

# Candidates were shortlisted from a live Voice Library search using the
# established account helper.  Accent, age, gender, and descriptions below
# are recorded API metadata; the generated MP3s remain Owner-review samples.
CANDIDATES = {
    "GRIK": (
        {
            "label": "GRIK_A",
            "name": "Ali - Everyday British (London) Male",
            "voice_id": "dqdOhmL2BvMSx2KtSAtN",
            "public_owner_id": "7d19359f1cdbf34cadf6bb904fffb79b3eeff592edc8fe9a31c276d4789dc167",
            "accent": "british",
            "age": "young",
            "gender": "male",
            "character": "warm, natural, relaxed London delivery; clear and conversational",
            "why": "Young male British metadata and natural conversational description fit Grik's civilian/scout read.",
        },
        {
            "label": "GRIK_B",
            "name": "Nick - British",
            "voice_id": "v4mOufztUtjxcpk65aWy",
            "public_owner_id": "bf26481ceaae61612121c6b8741d3dec79364749017daa3cd88d823b7cbf38f3",
            "accent": "british",
            "age": "young",
            "gender": "male",
            "character": "clear, refined, understated, articulate British delivery",
            "why": "Young male British metadata with understated clarity gives a child-readable comparison against the warmer candidate.",
        },
        {
            "label": "GRIK_C",
            "name": "Joe - Deep British Narrator",
            "voice_id": "3ZRnKeY0H10hhITAYx9o",
            "public_owner_id": "e018347a661b08ca39dda17191e5ffd6c5ffae0c807c1539eb818a7362199f12",
            "accent": "british",
            "age": "young",
            "gender": "male",
            "character": "deep but natural, warm, engaging British delivery",
            "why": "Young male British metadata and conversational warmth provide a textured option without a comic or monster read.",
        },
    ),
    "CENTURION": (
        {
            "label": "CENTURION_A",
            "name": "Mark - Calm British Authority",
            "voice_id": "cso37AjcTkVqyjGkWbRz",
            "public_owner_id": "247612f2ce3846c127cb749a96a051da35be45a5ec72628728d2eac93fcbe990",
            "accent": "british",
            "age": "middle_aged",
            "gender": "male",
            "character": "mature, measured, warm authority, reassuring and controlled",
            "why": "Middle-aged British metadata and calm-authority description directly fit Centurion's protective strength.",
        },
        {
            "label": "CENTURION_B",
            "name": "Robert",
            "voice_id": "wYz62et1CZw6fTWrIFHJ",
            "public_owner_id": "8665225c8a004d1a24aade798b747cccd257e977b8ec2e682868aa1f52572fd0",
            "accent": "british",
            "age": "middle_aged",
            "gender": "male",
            "character": "neutral southern English, mature yet younger-sounding, warm and measured",
            "why": "Native southern-English metadata, mature profile, and gentle authority suit a grounded protector rather than a villain.",
        },
        {
            "label": "CENTURION_C",
            "name": "Craig - Warm, articulate British male",
            "voice_id": "JZ5PEPqtr05GbBRBqPhz",
            "public_owner_id": "1cb3dcf2ec8893c9663b9be0385644ac80872038f88079bc2cbf9a31408be50a",
            "accent": "british",
            "age": "middle_aged",
            "gender": "male",
            "character": "warm, articulate, clear, naturally authoritative without stiffness",
            "why": "Middle-aged British metadata and natural, no-nonsense articulation provide a restrained protective alternative.",
        },
    ),
}


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
    by_id = {beat.get("BEAT_ID"): beat for beat in beats}
    if len(by_id) != 97 or any(not isinstance(key, str) or not key for key in by_id):
        raise ValueError("en-US script has duplicate or empty beat identities")
    for beat_id in ("Z3_S03_B003", "Z3_S06_B003"):
        beat = by_id.get(beat_id)
        if not beat or beat.get("ZONE") != 3 or beat.get("LOCALE") != "en-US":
            raise ValueError(f"missing canonical audition beat: {beat_id}")
    return document


def _metadata(path: Path) -> tuple[int, int, str]:
    data = path.read_bytes()
    duration_ms = round(float(MP3(path).info.length) * 1000)
    return duration_ms, len(data), hashlib.sha256(data).hexdigest()


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _resolve_voice_id(helper, api_key: str, candidate: dict, current_voices: dict[str, dict]) -> str:
    public_id = candidate["voice_id"]
    if public_id in current_voices:
        return public_id
    status, body = helper._add_shared_voice(
        api_key,
        candidate["public_owner_id"],
        public_id,
        f"W1_03_Z3_007R2_{candidate['label']}",
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

    script = _load_script()
    beats = {beat["BEAT_ID"]: beat for beat in script["beats"]}
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

    selected = [*CANDIDATES["GRIK"], *CANDIDATES["CENTURION"]]
    ids = [candidate["voice_id"] for candidate in selected]
    if len(ids) != len(set(ids)) or REJECTED_IDS.intersection(ids):
        raise ValueError("candidate set contains duplicate or previously rejected voice IDs")

    records = []
    for character, candidates in CANDIDATES.items():
        beat = beats["Z3_S03_B003" if character == "GRIK" else "Z3_S06_B003"]
        for candidate in candidates:
            output_path = OUTPUT_ROOT / character.lower() / (
                f"{character.lower()}_{candidate['label'].split('_')[-1]}_"
                f"{candidate['name'].replace(' ', '_').replace('/', '_')}.mp3"
            )
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
                    "CHARACTER": character,
                    "CANDIDATE_LABEL": candidate["label"],
                    "VOICE_NAME": candidate["name"],
                    "VOICE_ID": local_voice_id,
                    "SHARED_VOICE_ID": candidate["voice_id"],
                    "ACCENT_METADATA": candidate["accent"],
                    "APPROXIMATE_AGE_PROFILE": candidate["age"],
                    "GENDER_METADATA": candidate["gender"],
                    "VOICE_CHARACTER": candidate["character"],
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
        "SCHEMA_VERSION": "W1_03_ZONE3_EN_US_BRITISH_OWNER_AUDITION_PACKAGE_V2",
        "ZONE": 3,
        "LOCALE": "en-US",
        "SCRIPT_SOURCE": _relative(SCRIPT_PATH),
        "BRITISH_ENGLISH_ACCENT_REQUIREMENT": True,
        "STATUS": "OWNER_REVIEW_REQUIRED",
        "GRIK_CANDIDATE_COUNT": 3,
        "CENTURION_CANDIDATE_COUNT": 3,
        "TOTAL_NEW_AUDITION_COUNT": 6,
        "EN_US_DIALOGUE_BEATS": 97,
        "NO_RUNTIME_WIRING": True,
        "NO_FULL_PRODUCTION_AUDIO": True,
        "CROSS_LANGUAGE_VOICE_FALLBACK": "FORBIDDEN",
        "GRIK_OWNER_SELECTION": "PENDING",
        "CENTURION_OWNER_SELECTION": "PENDING",
        "REJECTED_HISTORICAL_VOICES": [
            {"VOICE_ID": "DSyEP4HEaCKur8rFFOri", "STATUS": "OWNER_REJECTED_FOR_EN_US_ZONE3"},
            {"VOICE_ID": "BrbEfHMQu0fyclQR7lfh", "STATUS": "OWNER_REJECTED_FOR_EN_US_ZONE3"},
        ],
        "REJECTED_VOICE_RUNTIME_BINDING_COUNT": 0,
        "candidates": records,
    }
    PACKAGE_PATH.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("AUDIO_AUTH_STATUS=AVAILABLE")
    print("AUTOMATED_AUDIO_TECHNICAL_QA=PASS")
    print("GRIK_CANDIDATE_COUNT=3")
    print("CENTURION_CANDIDATE_COUNT=3")
    print("TOTAL_NEW_AUDITION_COUNT=6")
    print(f"OWNER_AUDITION_MANIFEST={_relative(PACKAGE_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
