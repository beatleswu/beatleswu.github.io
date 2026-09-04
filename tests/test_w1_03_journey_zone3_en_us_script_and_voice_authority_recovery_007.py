"""W1-03 Zone 3 en-US script and voice-authority preflight checks."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest
from mutagen.mp3 import MP3


ROOT = Path(__file__).resolve().parents[1]
SOURCE_HEAD = "f77bce46302974c8a8aa9d296ae0ea548a707691"
ZH_SUBTITLE_PATH = ROOT / "assets" / "e10" / "i18n" / "zone3" / "zone3-cinematic-subtitles.json"
EN_SUBTITLE_PATH = ROOT / "assets" / "e10" / "i18n" / "zone3" / "zone3-cinematic-subtitles-en-US.json"
ZH_AUDIO_PATH = ROOT / "assets" / "e10" / "audio" / "zone3" / "zone3-cinematic-audio-manifest.json"
EN_AUDITION_PATH = ROOT / "tools" / "e10_zone3_audio" / "zone3_en_us_voice_audition_manifest.json"
AUDITION_GENERATOR_PATH = ROOT / "tools" / "e10_zone3_en_us_voice_preflight" / "generate_auditions.py"
I18N_PATH = ROOT / "i18n.js"
ZONE1_CASTING_PATH = ROOT / "tools" / "e10_zone1_audio" / "casting_candidates.json"
ZONE2_AUDIO_PACKAGE_PATH = ROOT / "assets" / "e10" / "audio" / "zone2" / "zone2-audio-package.json"
ZONE3_RUNTIME_FILES = (
    ROOT / "js" / "e9" / "journey_zone3_vertical_slice.js",
    ROOT / "js" / "e9" / "journey_zone3_vertical_slice_view.js",
    ROOT / "js" / "e9" / "journey_zone3_vertical_slice_content.js",
    ROOT / "js" / "game" / "cinematic_replay.js",
)

EXPECTED_HERO_EN_VOICE_ID = "6aOpkucJD6a4vTXyUKon"
EXPECTED_GRIK_VOICE_ID = "DSyEP4HEaCKur8rFFOri"
EXPECTED_CENTURION_VOICE_ID = "BrbEfHMQu0fyclQR7lfh"
EXPECTED_COUNTS = [4, 5, 11, 9, 7, 9, 12, 11, 14, 15]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def source_bytes(relative_path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{SOURCE_HEAD}:{relative_path}"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout


def test_en_us_manifest_has_exact_97_beat_identity_and_lifecycle_alignment():
    zh = load(ZH_SUBTITLE_PATH)
    en = load(EN_SUBTITLE_PATH)
    assert en["ZONE"] == 3
    assert en["LOCALE"] == "en-US"
    assert en["APPLICATION_LOCALE"] == "en"
    assert en["SOURCE_LOCALE"] == "zh-TW"
    assert len(en["beats"]) == 97
    assert len({item["BEAT_ID"] for item in en["beats"]}) == 97
    assert len({item["I18N_KEY"] for item in en["beats"]}) == 97
    assert [item["BEAT_ID"] for item in en["beats"]] == [item["BEAT_ID"] for item in zh["beats"]]
    assert [item["SHOT_ID"] for item in en["beats"]] == [item["SHOT_ID"] for item in zh["beats"]]
    assert [item["CHARACTER"] for item in en["beats"]] == [item["CHARACTER"] for item in zh["beats"]]
    assert [item["I18N_KEY"] for item in en["beats"]] == [item["I18N_KEY"] for item in zh["beats"]]
    assert [
        sum(item["SHOT_ID"] == f"SHOT{number:02d}" for item in en["beats"])
        for number in range(1, 11)
    ] == EXPECTED_COUNTS
    assert all(item["LIFECYCLE"] == "FIRST_ENTRY" for item in en["beats"][:36])
    assert all(item["LIFECYCLE"] == "BOSS_READY" for item in en["beats"][36:57])
    assert all(item["LIFECYCLE"] == "POST_CLEAR" for item in en["beats"][57:])
    assert en["SHOT_PHASES"] == {
        "FIRST_ENTRY": ["SHOT01", "SHOT02", "SHOT03", "SHOT04", "SHOT05"],
        "BOSS_READY": ["SHOT06", "SHOT07"],
        "POST_CLEAR": ["SHOT08", "SHOT09", "SHOT10"],
    }


def test_story_language_contracts_are_preserved_without_mystical_stone_claims():
    beats = {item["BEAT_ID"]: item["VISIBLE_TEXT"] for item in load(EN_SUBTITLE_PATH)["beats"]}
    assert beats["Z3_S06_B003"] == "I am the last gate."
    assert beats["Z3_S10_B014"] == "Don't just remember the path" + chr(0x2014)
    assert beats["Z3_S10_B015"] == "Remember who lives along it, too."
    assert "Water jars, blankets, pots" in beats["Z3_S02_B002"]
    assert "children's favorite toys" in beats["Z3_S02_B003"]
    assert "tired and hungry" in beats["Z3_S03_B003"]
    assert "almost gone" in beats["Z3_S04_B007"]
    assert "rocks came down" in beats["Z3_S05_B003"]
    assert "protective" not in " ".join(beats.values()).lower()
    assert "won't force anyone else to leave" in beats["Z3_S07_B009"]
    assert "truce" in beats["Z3_S08_B005"].lower()
    assert "clue" in beats["Z3_S09_B008"].lower()
    assert "loot" not in " ".join(beats.values()).lower()
    stone_text = " ".join(beats[key] for key in beats if key.startswith("Z3_S09_"))
    for forbidden in ("magic", "magical", "rune", "legendary", "treasure", "special power", "glow"):
        assert forbidden not in stone_text.lower()
    assert "Misty Forest" in beats["Z3_S10_B012"]


def test_i18n_keys_resolve_to_the_two_accepted_locales():
    i18n = I18N_PATH.read_text(encoding="utf-8")
    zh = load(ZH_SUBTITLE_PATH)
    en = {beat["BEAT_ID"]: beat["VISIBLE_TEXT"] for beat in load(EN_SUBTITLE_PATH)["beats"]}
    for beat in zh["beats"]:
        pattern = (
            rf"'{re.escape(beat['I18N_KEY'])}':\s*\{{\s*"
            rf"en:\s*{re.escape(json.dumps(en[beat['BEAT_ID']], ensure_ascii=False))}\s*,\s*"
            rf"zh:\s*'{re.escape(beat['VISIBLE_TEXT'])}'\s*\}}"
        )
        assert re.search(pattern, i18n), beat["BEAT_ID"]


def test_existing_zone1_and_zone2_english_hero_authority_is_canonical_and_identical():
    zone1 = load(ZONE1_CASTING_PATH)
    zone2 = load(ZONE2_AUDIO_PACKAGE_PATH)
    assert zone1["roles"]["hero"]["voices"]["en"]["voice_id"] == EXPECTED_HERO_EN_VOICE_ID
    assert zone1["roles"]["hero"]["voices"]["en"]["locked"] is True
    assert zone2["audio_lock"]["hero_voice_en"] == EXPECTED_HERO_EN_VOICE_ID
    assert zone2["runtime_integrated"] is True


def test_no_hardcoded_zone3_english_dialogue_or_english_runtime_audio_binding():
    english_text = [item["VISIBLE_TEXT"] for item in load(EN_SUBTITLE_PATH)["beats"]]
    runtime = "\n".join(path.read_text(encoding="utf-8") for path in ZONE3_RUNTIME_FILES)
    assert all(text not in runtime for text in english_text)
    # Later approved locale production may populate this asset directory. The
    # original boundary is runtime/controller binding, so keep that check
    # path-based and do not reject a legitimate product audio package.
    assert "assets/e10/audio/zone3/dialogue/en-US" not in runtime
    zh_audio = load(ZH_AUDIO_PATH)
    assert zh_audio["LOCALE"] == "zh-TW"
    assert zh_audio["VOICE_LANGUAGE_MISMATCH"] == "FORBIDDEN"


def test_audition_generator_is_bounded_to_one_grik_and_one_centurion():
    source = AUDITION_GENERATOR_PATH.read_text(encoding="utf-8")
    assert "ELEVENLABS_API_KEY" in source
    assert "DSyEP4HEaCKur8rFFOri" in source
    assert "BrbEfHMQu0fyclQR7lfh" in source
    assert "Z3_S03_B003" in source
    assert "Z3_S06_B003" in source
    assert "NO_FULL_PRODUCTION_AUDIO" in source
    assert "assets/e10/audio/zone3" not in source
    assert "97" in source


def test_owner_audition_package_is_technically_valid_when_generated():
    if not EN_AUDITION_PATH.is_file():
        pytest.skip("Owner audition package is pending authorized ElevenLabs audio generation")
    package = load(EN_AUDITION_PATH)
    assert package["STATUS"] == "OWNER_REVIEW_REQUIRED"
    assert package["LOCALE"] == "en-US"
    assert package["NO_RUNTIME_WIRING"] is True
    assert package["NO_FULL_PRODUCTION_AUDIO"] is True
    candidates = package["candidates"]
    assert len(candidates) == 2
    assert {item["CHARACTER"] for item in candidates} == {"GRIK", "CENTURION"}
    assert {item["VOICE_ID"] for item in candidates} == {
        EXPECTED_GRIK_VOICE_ID,
        EXPECTED_CENTURION_VOICE_ID,
    }
    assert all(item["OWNER_APPROVED_VOICE"] is False for item in candidates)
    assert all(item["OWNER_APPROVAL"] == "PENDING" for item in candidates)
    assert all(item["RUNTIME_BINDING"] == "NONE" for item in candidates)
    for item in candidates:
        path = ROOT / item["AUDIO_PATH"]
        data = path.read_bytes()
        assert path.is_file()
        assert item["BYTES"] == len(data) > 0
        assert item["SHA256"] == hashlib.sha256(data).hexdigest()
        assert item["DURATION_MS"] == round(float(MP3(path).info.length) * 1000) > 0


def test_protected_accepted_zone3_zh_tw_surfaces_match_source_bytes():
    for relative_path in (
        "assets/e10/i18n/zone3/zone3-cinematic-subtitles.json",
        "assets/e10/audio/zone3/zone3-cinematic-audio-manifest.json",
        "app.py",
        "js/game/cinematic_replay.js",
        "sw.js",
    ):
        result = subprocess.run(
            ["git", "diff", "--quiet", SOURCE_HEAD, "--", relative_path],
            cwd=ROOT,
        )
        assert result.returncode == 0, relative_path
