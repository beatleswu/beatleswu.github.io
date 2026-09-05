import hashlib
import json
from pathlib import Path

from mutagen.mp3 import MP3


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "assets/e10/i18n/zone3/zone3-cinematic-subtitles-en-US.json"
MANIFEST_PATH = ROOT / "tools/e10_zone3_audio/zone3_en_us_british_round2_audition_manifest.json"
REJECTED_IDS = {"DSyEP4HEaCKur8rFFOri", "BrbEfHMQu0fyclQR7lfh"}


def _documents():
    return (
        json.loads(SCRIPT_PATH.read_text(encoding="utf-8")),
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8")),
    )


def test_package_has_exact_six_unique_owner_auditions():
    _, manifest = _documents()
    records = manifest["candidates"]
    assert len(records) == 6
    assert len({record["CANDIDATE_LABEL"] for record in records}) == 6
    assert len({record["VOICE_ID"] for record in records}) == 6
    assert {record["CHARACTER"] for record in records} == {"GRIK", "CENTURION"}
    assert sum(record["CHARACTER"] == "GRIK" for record in records) == 3
    assert sum(record["CHARACTER"] == "CENTURION" for record in records) == 3


def test_samples_are_exact_canonical_english_beats_and_rejected_ids_are_absent():
    script, manifest = _documents()
    beats = {beat["BEAT_ID"]: beat for beat in script["beats"]}
    assert len(beats) == 97
    assert {record["BEAT_ID"] for record in manifest["candidates"]} == {
        "Z3_S03_B003",
        "Z3_S06_B003",
    }
    for record in manifest["candidates"]:
        beat = beats[record["BEAT_ID"]]
        assert record["SHOT_ID"] == beat["SHOT_ID"]
        assert record["I18N_KEY"] == beat["I18N_KEY"]
        assert record["EXACT_SAMPLE_TEXT"] == beat["VISIBLE_TEXT"]
        assert record["VOICE_ID"] not in REJECTED_IDS
        assert record["SHARED_VOICE_ID"] not in REJECTED_IDS


def test_all_mp3s_decode_and_manifest_hashes_match_bytes():
    _, manifest = _documents()
    paths = []
    for record in manifest["candidates"]:
        path = ROOT / record["AUDIO_PATH"]
        assert path.is_file()
        assert path not in paths
        paths.append(path)
        payload = path.read_bytes()
        assert len(payload) == record["BYTES"] > 0
        assert hashlib.sha256(payload).hexdigest() == record["SHA256"]
        duration_ms = round(float(MP3(path).info.length) * 1000)
        assert duration_ms == record["DURATION_MS"] > 0


def test_auditions_are_review_only_and_do_not_bind_english_production_audio():
    _, manifest = _documents()
    records = manifest["candidates"]
    assert manifest["STATUS"] == "OWNER_REVIEW_REQUIRED"
    assert manifest["NO_RUNTIME_WIRING"] is True
    assert manifest["NO_FULL_PRODUCTION_AUDIO"] is True
    assert manifest["CROSS_LANGUAGE_VOICE_FALLBACK"] == "FORBIDDEN"
    assert manifest["REJECTED_VOICE_RUNTIME_BINDING_COUNT"] == 0
    assert all("assets/e10/audio/zone3/dialogue/en-US" not in record["AUDIO_PATH"] for record in records)
