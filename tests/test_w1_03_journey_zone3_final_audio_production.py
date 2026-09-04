"""W1-03 Zone 3 final locked zh-TW runtime audio package checks."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from mutagen.mp3 import MP3


ROOT = Path(__file__).resolve().parents[1]
SUBTITLE_PATH = ROOT / "assets" / "e10" / "i18n" / "zone3" / "zone3-cinematic-subtitles.json"
AUDIO_PATH = ROOT / "assets" / "e10" / "audio" / "zone3" / "zone3-cinematic-audio-manifest.json"
BASE = "356bb94f3fa64b801107c78944e5b09c59c44ca9"
VOICE_IDS = {
    "HERO": ("Roy", "XXxvxx0YUt8icTEFE3c6"),
    "GRIK": ("Zack", "DSyEP4HEaCKur8rFFOri"),
    "CENTURION": ("Kevin Tu", "BrbEfHMQu0fyclQR7lfh"),
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_final_manifest_is_exactly_97_locked_locale_scoped_beats():
    subtitles = load(SUBTITLE_PATH)
    audio = load(AUDIO_PATH)
    subtitle_beats = subtitles["beats"]
    entries = audio["entries"]
    assert len(subtitle_beats) == len(entries) == 97
    assert audio["LOCALE"] == "zh-TW"
    assert audio["CANONICAL_SCRIPT_SOURCE"] == (
        "COORDINATOR_ISSUED_OWNER_APPROVED_ZONE3_CHILD_READABLE_PAYLOAD"
    )
    assert audio["LOCALE_SCOPED_AUDIO_MANIFEST"] is True
    assert audio["MISSING_LOCALE_VOICE_FALLBACK"] == "SUBTITLE_ONLY"
    assert audio["VOICE_LANGUAGE_MISMATCH"] == "FORBIDDEN"
    assert len({entry["BEAT_ID"] for entry in entries}) == 97
    assert len({entry["AUDIO_PATH"] for entry in entries}) == 97
    assert {entry["BEAT_ID"] for entry in entries} == {beat["BEAT_ID"] for beat in subtitle_beats}
    assert {entry["CHARACTER"] for entry in entries} == set(VOICE_IDS)
    assert sum(entry["CHARACTER"] == "HERO" for entry in entries) == 41
    assert sum(entry["CHARACTER"] == "GRIK" for entry in entries) == 37
    assert sum(entry["CHARACTER"] == "CENTURION" for entry in entries) == 19
    assert not any("audition" in (entry["AUDIO_PATH"] or "").lower() for entry in entries)

    subtitles_by_id = {beat["BEAT_ID"]: beat for beat in subtitle_beats}
    for entry in entries:
        beat = subtitles_by_id[entry["BEAT_ID"]]
        voice_name, voice_id = VOICE_IDS[entry["CHARACTER"]]
        assert entry["ZONE"] == 3
        assert entry["LOCALE"] == beat["LOCALE"] == "zh-TW"
        assert entry["SHOT_ID"] == beat["SHOT_ID"]
        assert entry["I18N_KEY"] == beat["I18N_KEY"]
        assert entry["TEXT_HASH"] == hashlib.sha256(beat["VISIBLE_TEXT"].encode("utf-8")).hexdigest()
        assert entry["VOICE_NAME"] == voice_name
        assert entry["VOICE_ID"] == voice_id
        assert entry["VOICE_LANGUAGE"] == "zh"
        assert entry["OWNER_APPROVED_VOICE"] is True
        assert entry["VOICE_STATUS"] == "OWNER_APPROVED_PRODUCTION"
        path = ROOT / entry["AUDIO_PATH"]
        assert path.is_file()
        data = path.read_bytes()
        assert len(data) > 0
        assert entry["BYTES"] == len(data)
        assert entry["SHA256"] == hashlib.sha256(data).hexdigest()
        assert entry["DURATION_MS"] == round(float(MP3(path).info.length) * 1000)
        assert entry["DURATION_MS"] > 0


def test_hero_runtime_audio_is_byte_identical_to_locked_base():
    subtitles = load(SUBTITLE_PATH)
    audio = load(AUDIO_PATH)
    entries = {entry["BEAT_ID"]: entry for entry in audio["entries"]}
    hero_beats = [beat for beat in subtitles["beats"] if beat["CHARACTER"] == "HERO"]
    assert len(hero_beats) == 41
    for beat in hero_beats:
        relative_path = entries[beat["BEAT_ID"]]["AUDIO_PATH"]
        current = (ROOT / relative_path).read_bytes()
        base = subprocess.run(
            ["git", "show", f"{BASE}:{relative_path}"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        assert current == base, beat["BEAT_ID"]


def test_missing_locale_voice_contract_remains_subtitle_only_without_cross_language_fallback():
    audio = load(AUDIO_PATH)
    assert audio["MISSING_LOCALE_VOICE_FALLBACK"] == "SUBTITLE_ONLY"
    assert audio["VOICE_LANGUAGE_MISMATCH"] == "FORBIDDEN"
    assert all(entry["LOCALE"] == "zh-TW" for entry in audio["entries"])
    assert all(entry["VOICE_LANGUAGE"] == "zh" for entry in audio["entries"])


def test_final_generation_is_resumable_and_does_not_regenerate_valid_assets(monkeypatch, capsys):
    tool_dir = ROOT / "tools" / "e10_zone3_audio"
    sys.path.insert(0, str(tool_dir))
    try:
        import generate_zone3_audio as generator  # noqa: PLC0415

        class NoNetworkTts:
            def _text_to_speech(self, *args, **kwargs):
                raise AssertionError("valid locked production assets must not be regenerated")

        monkeypatch.setenv("ELEVENLABS_API_KEY", "dummy_test_value_not_real")
        result = generator._generate_final_production(generator._load_subtitles(), NoNetworkTts())
        assert result == 0
        output = capsys.readouterr().out
        assert "FINAL_PRODUCTION_GENERATED=0" in output
        assert "FINAL_PRODUCTION_SKIPPED=56" in output
        assert "FINAL_PRODUCTION_VERIFICATION=PASS" in output
    finally:
        sys.path.remove(str(tool_dir))
