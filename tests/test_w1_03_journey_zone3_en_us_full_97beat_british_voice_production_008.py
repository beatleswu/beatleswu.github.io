import hashlib
import json
import subprocess
from pathlib import Path

from mutagen.mp3 import MP3


ROOT = Path(__file__).resolve().parents[1]
BASE = "146db5380d13b72f6ab803cef8092be24dee32bc"
SUBTITLE_PATH = ROOT / "assets/e10/i18n/zone3/zone3-cinematic-subtitles-en-US.json"
ZH_SUBTITLE_PATH = ROOT / "assets/e10/i18n/zone3/zone3-cinematic-subtitles.json"
ZH_AUDIO_MANIFEST_PATH = ROOT / "assets/e10/audio/zone3/zone3-cinematic-audio-manifest.json"
AUDIO_MANIFEST_PATH = ROOT / "assets/e10/audio/zone3/zone3-cinematic-audio-manifest-en-US.json"
PRODUCTION_ROOT = ROOT / "assets/e10/audio/zone3/dialogue/en-US"

CAST = {
    "HERO": ("Steve", "RasuOwPKPBy67j7E43Su"),
    "GRIK": ("Nick", "v4mOufztUtjxcpk65aWy"),
    "CENTURION": ("Mark", "cso37AjcTkVqyjGkWbRz"),
}
FORBIDDEN_IDS = {
    "6aOpkucJD6a4vTXyUKon",
    "DSyEP4HEaCKur8rFFOri",
    "BrbEfHMQu0fyclQR7lfh",
    "dqdOhmL2BvMSx2KtSAtN",
    "3ZRnKeY0H10hhITAYx9o",
    "wYz62et1CZw6fTWrIFHJ",
    "JZ5PEPqtr05GbBRBqPhz",
    "WoxRV1VQUDtxEHPVAZyL",
    "BuptxElFd80GDtsmyQIU",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def runtime_path(beat: dict) -> Path:
    beat_number = beat["BEAT_ID"].split("_")[-1].lower()
    return PRODUCTION_ROOT / (
        f"zone3_{beat['SHOT_ID'].lower()}_{beat_number}_en-US_{beat['CHARACTER'].lower()}.mp3"
    )


def test_manifest_has_exact_97_canonical_records_and_speaker_counts():
    subtitles = load(SUBTITLE_PATH)
    audio = load(AUDIO_MANIFEST_PATH)
    beats = subtitles["beats"]
    entries = audio["entries"]
    assert len(beats) == len(entries) == 97
    assert len({beat["BEAT_ID"] for beat in beats}) == 97
    assert len({entry["BEAT_ID"] for entry in entries}) == 97
    assert {entry["BEAT_ID"] for entry in entries} == {beat["BEAT_ID"] for beat in beats}
    assert {beat["SHOT_ID"] for beat in beats} == {f"SHOT{n:02d}" for n in range(1, 11)}
    assert {entry["SPEAKER"] for entry in entries} == set(CAST)
    assert sum(beat["CHARACTER"] == "HERO" for beat in beats) == 41
    assert sum(beat["CHARACTER"] == "GRIK" for beat in beats) == 37
    assert sum(beat["CHARACTER"] == "CENTURION" for beat in beats) == 19
    assert audio["EN_US_DIALOGUE_BEATS"] == 97
    assert audio["EN_US_PRODUCTION_AUDIO_COUNT"] == 97


def test_manifest_uses_exact_selected_british_cast_and_no_forbidden_voice():
    audio = load(AUDIO_MANIFEST_PATH)
    assert audio["LOCALE"] == "en-US"
    assert audio["APPLICATION_LOCALE"] == "en"
    assert audio["VOICE_LANGUAGE_MISMATCH"] == "FORBIDDEN"
    assert audio["MISSING_LOCALE_VOICE_FALLBACK"] == "SUBTITLE_ONLY"
    assert audio["LOCALE_SCOPED_AUDIO_MANIFEST"] is True
    assert all(entry["VOICE_ID"] not in FORBIDDEN_IDS for entry in audio["entries"])
    for entry in audio["entries"]:
        voice_name, voice_id = CAST[entry["SPEAKER"]]
        assert (entry["VOICE_NAME"], entry["VOICE_ID"]) == (voice_name, voice_id)
        assert entry["VOICE_LANGUAGE"] == "en"
        assert entry["OWNER_APPROVED_VOICE"] is True
        assert entry["VOICE_STATUS"] == "OWNER_APPROVED_PRODUCTION"
    assert all(audio["VOICE_METADATA"][role]["ACCENT_METADATA"] == "british" for role in CAST)
    assert all(audio["VOICE_METADATA"][role]["LANGUAGE_METADATA"] == "en" for role in CAST)
    assert audio["VOICE_METADATA"]["HERO"]["AGE_PROFILE"] == "young"
    assert audio["VOICE_METADATA"]["GRIK"]["AGE_PROFILE"] == "young"
    assert audio["VOICE_METADATA"]["CENTURION"]["AGE_PROFILE"] == "middle_aged"


def test_all_production_audio_decodes_and_hashes_match_manifest():
    subtitles = load(SUBTITLE_PATH)
    audio = load(AUDIO_MANIFEST_PATH)
    beats = {beat["BEAT_ID"]: beat for beat in subtitles["beats"]}
    paths = []
    for entry in audio["entries"]:
        beat = beats[entry["BEAT_ID"]]
        path = ROOT / entry["AUDIO_PATH"]
        assert path == runtime_path(beat)
        assert path.is_file()
        assert path not in paths
        paths.append(path)
        payload = path.read_bytes()
        assert len(payload) == entry["BYTES"] > 0
        assert hashlib.sha256(payload).hexdigest() == entry["SHA256"]
        assert entry["DURATION_MS"] == round(float(MP3(path).info.length) * 1000) > 0
        assert entry["EXACT_TEXT"] == beat["VISIBLE_TEXT"]
        assert entry["TEXT_HASH"] == text_hash(beat["VISIBLE_TEXT"])


def test_zh_tw_surfaces_are_source_unchanged_and_no_cross_language_fallback():
    assert SUBTITLE_PATH.is_file()
    for relative_path in (
        "assets/e10/i18n/zone3/zone3-cinematic-subtitles.json",
        "assets/e10/audio/zone3/zone3-cinematic-audio-manifest.json",
    ):
        result = subprocess.run(
            ["git", "diff", "--quiet", BASE, "--", relative_path],
            cwd=ROOT,
            check=False,
        )
        assert result.returncode == 0, relative_path
    audio = load(AUDIO_MANIFEST_PATH)
    assert all(entry["LOCALE"] == "en-US" for entry in audio["entries"])
    assert all(entry["VOICE_LANGUAGE"] == "en" for entry in audio["entries"])


def test_production_is_not_runtime_controller_binding_and_auditions_are_not_used():
    audio = load(AUDIO_MANIFEST_PATH)
    assert audio["REPLAY_DIALOGUE_SOURCE"] == "assets/e10/i18n/zone3/zone3-cinematic-subtitles-en-US.json"
    assert all("_local_review" not in entry["AUDIO_PATH"] for entry in audio["entries"])
    assert all("audition" not in entry["AUDIO_PATH"].lower() for entry in audio["entries"])
    assert not any("audition" in entry["AUDIO_PATH"].lower() for entry in audio["entries"])


def test_application_and_gameplay_authority_files_remain_protected_in_final_candidate():
    changed = set(
        subprocess.run(
            ["git", "diff", "--name-only", BASE, "--"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
    )
    protected = {
        "app.py",
        "sw.js",
        "js/game/cinematic_replay.js",
    }
    assert not changed.intersection(protected)
    authorized_presentation_changes = {
        "i18n.js",
        "index.html",
        "js/e9/journey_zone3_vertical_slice_content.js",
    }
    assert changed.intersection(authorized_presentation_changes) <= authorized_presentation_changes
    assert not any(path.startswith("migrations/") or path.startswith("db/") for path in changed)
