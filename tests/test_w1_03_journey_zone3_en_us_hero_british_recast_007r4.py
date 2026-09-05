import hashlib
import json
from pathlib import Path

from mutagen.mp3 import MP3


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "assets/e10/i18n/zone3/zone3-cinematic-subtitles-en-US.json"
MANIFEST_PATH = ROOT / "tools/e10_zone3_audio/zone3_en_us_hero_british_round1_audition_manifest.json"
HISTORICAL_ANVAY_ID = "6aOpkucJD6a4vTXyUKon"


def _documents():
    return (
        json.loads(SCRIPT_PATH.read_text(encoding="utf-8")),
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8")),
    )


def test_package_has_exactly_three_distinct_pending_hero_auditions():
    _, manifest = _documents()
    records = manifest["candidates"]
    assert len(records) == 3
    assert {record["CHARACTER"] for record in records} == {"HERO"}
    assert {record["CANDIDATE_LABEL"] for record in records} == {"HERO_A", "HERO_B", "HERO_C"}
    assert len({record["VOICE_ID"] for record in records}) == 3
    assert all(record["OWNER_APPROVAL"] == "PENDING" for record in records)
    assert all(record["OWNER_APPROVED_VOICE"] is False for record in records)
    assert all(record["RUNTIME_BINDING"] == "NONE" for record in records)


def test_candidates_are_british_and_historical_anvay_is_absent():
    _, manifest = _documents()
    records = manifest["candidates"]
    assert manifest["GO_ODYSSEY_ENGLISH_VOICE_ACCENT_POLICY"] == "BRITISH_ENGLISH"
    assert manifest["NEW_ENGLISH_PRODUCTION_NON_BRITISH_VOICE_ALLOWED"] is False
    for record in records:
        assert record["ACCENT_METADATA"].lower() == "british"
        assert record["LANGUAGE_METADATA"] == "en"
        assert record["APPROXIMATE_AGE_PROFILE"] == "young"
        assert record["GENDER_METADATA"] == "male"
        assert record["VOICE_ID"] != HISTORICAL_ANVAY_ID
        assert record["SHARED_VOICE_ID"] != HISTORICAL_ANVAY_ID
    assert manifest["ANVAY_NEW_ZONE3_BINDING_COUNT"] == 0


def test_all_candidates_use_one_exact_canonical_hero_beat():
    script, manifest = _documents()
    assert len(script["beats"]) == 97
    beats = {beat["BEAT_ID"]: beat for beat in script["beats"]}
    assert len(beats) == 97
    records = manifest["candidates"]
    assert {record["BEAT_ID"] for record in records} == {"Z3_S07_B007"}
    beat = beats["Z3_S07_B007"]
    assert beat["CHARACTER"] == "HERO"
    for record in records:
        assert record["SHOT_ID"] == beat["SHOT_ID"]
        assert record["I18N_KEY"] == beat["I18N_KEY"]
        assert record["EXACT_SAMPLE_TEXT"] == beat["VISIBLE_TEXT"]
    assert manifest["AUDITION_BEAT_ID"] == beat["BEAT_ID"]
    assert manifest["AUDITION_TEXT"] == beat["VISIBLE_TEXT"]


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


def test_round_is_review_only_and_does_not_bind_english_production_audio():
    _, manifest = _documents()
    records = manifest["candidates"]
    assert manifest["STATUS"] == "OWNER_REVIEW_REQUIRED"
    assert manifest["HERO_OWNER_SELECTION"] == "PENDING"
    assert manifest["NO_RUNTIME_WIRING"] is True
    assert manifest["NO_FULL_PRODUCTION_AUDIO"] is True
    assert manifest["CROSS_LANGUAGE_VOICE_FALLBACK"] == "FORBIDDEN"
    assert manifest["GRIK_PRESERVED_VOICE"] == {"VOICE_NAME": "Nick", "VOICE_ID": "v4mOufztUtjxcpk65aWy"}
    assert manifest["CENTURION_PRESERVED_VOICE"] == {"VOICE_NAME": "Mark", "VOICE_ID": "cso37AjcTkVqyjGkWbRz"}
    assert all("assets/e10/audio/zone3/dialogue/en-US" not in record["AUDIO_PATH"] for record in records)
