"""W1_03 Zone 3 canonical localized subtitle/voice contracts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUBTITLE_PATH = ROOT / "assets" / "e10" / "i18n" / "zone3" / "zone3-cinematic-subtitles.json"
EN_SUBTITLE_PATH = ROOT / "assets" / "e10" / "i18n" / "zone3" / "zone3-cinematic-subtitles-en-US.json"
AUDIO_PATH = ROOT / "assets" / "e10" / "audio" / "zone3" / "zone3-cinematic-audio-manifest.json"
AUDITION_PATH = ROOT / "tools" / "e10_zone3_audio" / "zone3_voice_audition_manifest.json"
I18N_PATH = ROOT / "i18n.js"
CONTENT_PATH = ROOT / "js" / "e9" / "journey_zone3_vertical_slice_content.js"
RUNTIME_PATHS = (
    ROOT / "js" / "e9" / "journey_zone3_vertical_slice.js",
    ROOT / "js" / "e9" / "journey_zone3_vertical_slice_view.js",
    CONTENT_PATH,
)
BASE = "d5d3d3d08757d70e182d67a4547fbfbcaab8a561"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_canonical_manifest_covers_all_ten_shots_and_exact_beats():
    document = load(SUBTITLE_PATH)
    beats = document["beats"]
    assert document["ZONE"] == 3
    assert document["LOCALE"] == "zh-TW"
    assert document["APPLICATION_LOCALE"] == "zh"
    assert document["CANONICAL_SCRIPT_SOURCE"] == (
        "COORDINATOR_ISSUED_OWNER_APPROVED_ZONE3_CHILD_READABLE_PAYLOAD"
    )
    assert len(beats) == 97
    assert {item["SHOT_ID"] for item in beats} == {f"SHOT{number:02d}" for number in range(1, 11)}
    assert [sum(item["SHOT_ID"] == f"SHOT{number:02d}" for item in beats) for number in range(1, 11)] == [
        4, 5, 11, 9, 7, 9, 12, 11, 14, 15
    ]
    assert len({item["BEAT_ID"] for item in beats}) == len(beats)
    assert len({item["I18N_KEY"] for item in beats}) == len(beats)
    assert all(item["LOCALE"] == "zh-TW" and item["ZONE"] == 3 for item in beats)


def test_coordinator_locked_lines_and_no_old_abbreviated_lines():
    beats = {item["BEAT_ID"]: item["VISIBLE_TEXT"] for item in load(SUBTITLE_PATH)["beats"]}
    assert beats["Z3_S06_B003"] == "我是最後一道門。"
    assert beats["Z3_S07_B007"] == "那就讓我試試。"
    assert beats["Z3_S07_B008"] == "我不是來搶你們的地。"
    assert beats["Z3_S07_B009"] == "我想找的是一條，不需要再把任何人趕走的路。"
    assert beats["Z3_S10_B014"] == "別只記得路——"
    assert beats["Z3_S10_B015"] == "也要記得路上住著誰。"
    text = "\n".join(beats.values())
    assert "我不是來打你的。" not in text
    assert "證明你看得見的，不只有自己的地。" not in text


def test_every_subtitle_key_resolves_in_existing_i18n_dictionary():
    i18n = I18N_PATH.read_text(encoding="utf-8")
    en_by_id = {item["BEAT_ID"]: item["VISIBLE_TEXT"] for item in load(EN_SUBTITLE_PATH)["beats"]}
    for beat in load(SUBTITLE_PATH)["beats"]:
        assert f"'{beat['I18N_KEY']}':" in i18n, beat["BEAT_ID"]
        assert f"zh: '{beat['VISIBLE_TEXT']}'" in i18n, beat["BEAT_ID"]
        en_text = json.dumps(en_by_id[beat["BEAT_ID"]], ensure_ascii=False)
        assert f"en: {en_text}" in i18n, beat["BEAT_ID"]


def test_zone3_runtime_modules_have_no_embedded_dialogue_text():
    runtime = "\n".join(path.read_text(encoding="utf-8") for path in RUNTIME_PATHS)
    for beat in load(SUBTITLE_PATH)["beats"]:
        assert beat["VISIBLE_TEXT"] not in runtime
    assert "zone3-cinematic-subtitles.json" in runtime
    assert "same_localized_beat_manifest" in runtime


def test_audio_manifest_is_locale_scoped_and_subtitle_aligned():
    subtitles = {item["BEAT_ID"]: item for item in load(SUBTITLE_PATH)["beats"]}
    audio = load(AUDIO_PATH)
    entries = audio["entries"]
    assert audio["ZONE"] == 3
    assert audio["LOCALE"] == "zh-TW"
    assert audio["LOCALE_SCOPED_AUDIO_MANIFEST"] is True
    assert audio["MISSING_LOCALE_VOICE_FALLBACK"] == "SUBTITLE_ONLY"
    assert audio["VOICE_LANGUAGE_MISMATCH"] == "FORBIDDEN"
    assert len(entries) == len(subtitles) == 97
    assert {item["BEAT_ID"] for item in entries} == set(subtitles)
    assert len({item["AUDIO_PATH"] for item in entries if item["AUDIO_PATH"]}) == sum(
        bool(item["AUDIO_PATH"]) for item in entries
    )
    for entry in entries:
        subtitle = subtitles[entry["BEAT_ID"]]
        assert entry["I18N_KEY"] == subtitle["I18N_KEY"]
        assert entry["LOCALE"] == subtitle["LOCALE"] == "zh-TW"
        assert entry["TEXT_HASH"] == hashlib.sha256(subtitle["VISIBLE_TEXT"].encode("utf-8")).hexdigest()
        if entry["CHARACTER"] == "HERO":
            assert entry["VOICE_ID"] == "XXxvxx0YUt8icTEFE3c6"
            assert entry["VOICE_LANGUAGE"] == "zh"
            assert entry["OWNER_APPROVED_VOICE"] is True
        else:
            expected_voice = {
                "GRIK": "DSyEP4HEaCKur8rFFOri",
                "CENTURION": "BrbEfHMQu0fyclQR7lfh",
            }[entry["CHARACTER"]]
            assert entry["VOICE_ID"] == expected_voice
            assert entry["VOICE_LANGUAGE"] == "zh"
            assert entry["OWNER_APPROVED_VOICE"] is True
            assert entry["VOICE_STATUS"] == "OWNER_APPROVED_PRODUCTION"
        if entry["AUDIO_PATH"]:
            path = ROOT / entry["AUDIO_PATH"]
            assert path.is_file()
            data = path.read_bytes()
            assert entry["BYTES"] == len(data)
            assert entry["SHA256"] == hashlib.sha256(data).hexdigest()
            assert isinstance(entry["DURATION_MS"], int) and entry["DURATION_MS"] > 0


def test_bounded_auditions_are_review_only_and_never_runtime_voice_fallbacks():
    document = load(AUDITION_PATH)
    candidates = document["candidates"]
    assert document["STATUS"] == "OWNER_REVIEW_REQUIRED"
    assert len(candidates) == 6
    assert sum(item["CHARACTER"] == "GRIK" for item in candidates) == 3
    assert sum(item["CHARACTER"] == "CENTURION" for item in candidates) == 3
    assert all(item["LOCALE"] == "zh-TW" for item in candidates)
    assert all(item["OWNER_APPROVED_VOICE"] is False for item in candidates)
    assert all(item["GENERATED"] is True for item in candidates)
    assert {item["BEAT_ID"] for item in candidates} == {"Z3_S03_B007", "Z3_S06_B003"}
    assert all(item["TTS_INPUT_TEXT"] == item["VISIBLE_TEXT"] for item in candidates)
    assert len({item["AUDIO_PATH"] for item in candidates}) == 6
    assert all((ROOT / item["AUDIO_PATH"]).is_file() for item in candidates)


def test_replay_and_locale_contract_is_presentation_only():
    content = CONTENT_PATH.read_text(encoding="utf-8")
    audio = load(AUDIO_PATH)
    assert "replaySource: 'same_localized_beat_manifest'" in content
    assert audio["REPLAY_DIALOGUE_SOURCE"] == (
        "assets/e10/i18n/zone3/zone3-cinematic-subtitles.json"
    )
    assert "missingVoicePolicy: 'SUBTITLE_ONLY'" in content
    assert "crossLocaleVoiceFallback: 'FORBIDDEN'" in content
    assert "shuiHumanDialogue: false" in content
    assert not any(item["CHARACTER"] == "SHUI" for item in load(SUBTITLE_PATH)["beats"])
    localization = content[content.index("var CINEMATIC_LOCALIZATION"):content.index("var PHASES")]
    assert "progression" not in localization.lower()
    assert "reward" not in localization.lower()


def test_protected_runtime_boundaries_remain_unchanged_from_base():
    changed = set(
        subprocess.run(
            ["git", "diff", "--name-only", BASE, "--"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
    )
    assert "app.py" not in changed
    assert "js/game/cinematic_replay.js" not in changed
    assert "sw.js" not in changed
    assert not any(path.startswith("migrations/") for path in changed)
    assert not any(path.startswith("db/") for path in changed)
