"""Deterministic contracts for the final Zone 2 bilingual integration."""

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
PACKAGE_PATH = ROOT / "assets" / "e10" / "audio" / "zone2" / "zone2-audio-package.json"
PACKAGE = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
ART_MANIFEST = json.loads(
    (ROOT / "deploy" / "canonical-e10-zone2-art-pack-manifest.json").read_text(encoding="utf-8")
)
AUD_MANIFEST = json.loads(
    (ROOT / "deploy" / "canonical-e10-zone2-audio-pack-manifest.json").read_text(encoding="utf-8")
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _zone2_slots() -> str:
    return INDEX[INDEX.index("function _zone2CinematicPhaseSlots") : INDEX.index("\nfunction getIntroFilmLocaleConfig")]


def test_final_art_and_audio_are_exactly_governed():
    assert len(ART_MANIFEST["files"]) == 10
    assert len(AUD_MANIFEST["files"]) == 53
    assert PACKAGE["asset_count"] == 53
    for entry in ART_MANIFEST["files"] + AUD_MANIFEST["files"]:
        path = ROOT / entry["path"]
        assert path.is_file(), entry["path"]
        assert path.stat().st_size == entry["size"], entry["path"]
        assert _sha(path) == entry["sha256"], entry["path"]


def test_bilingual_dialogue_is_complete_and_uses_locked_identities():
    dialogue = [item for item in PACKAGE["assets"] if item["category"] == "dialogue"]
    assert len(dialogue) == 36
    assert {item["locale"] for item in dialogue} == {"zh-TW", "en"}
    assert sum(item["locale"] == "zh-TW" for item in dialogue) == 18
    assert sum(item["locale"] == "en" for item in dialogue) == 18
    assert {item["voice_id"] for item in dialogue if item["locale"] == "zh-TW" and item["speaker"] == "hero"} == {"XXxvxx0YUt8icTEFE3c6"}
    assert {item["voice_id"] for item in dialogue if item["locale"] == "en" and item["speaker"] == "hero"} == {"6aOpkucJD6a4vTXyUKon"}
    assert {item["voice_id"] for item in dialogue if item["locale"] == "zh-TW" and item["speaker"] == "herder"} == {"BrbEfHMQu0fyclQR7lfh"}
    assert {item["voice_id"] for item in dialogue if item["locale"] == "en" and item["speaker"] == "herder"} == {"dqdOhmL2BvMSx2KtSAtN"}
    assert all(item["model"] == "eleven_v3" for item in dialogue)


def test_shot_phases_and_locale_audio_wiring_are_stable():
    slots = _zone2_slots()
    for expected in ("timeline", "bossReadyTimeline", "postClearTimeline"):
        assert expected in slots
    for shot in range(1, 11):
        assert f"shot({shot}," in slots
    assert slots.index("shot(4,") < slots.index("bossReadyTimeline")
    assert slots.index("shot(7,") < slots.index("postClearTimeline")
    assert slots.index("shot(10,") < slots.index("audioSlots")
    assert "locale.uiLang === 'en'" in INDEX
    assert "audioSrc: en ? enAudioSrc : zhAudioSrc" in slots
    assert "ZONE2_AUDIO.dialogue.zh" in INDEX
    assert "ZONE2_AUDIO.dialogue.en" in INDEX
    assert "_setIntroBgmDucked" in INDEX


def test_zone2_player_copy_uses_i18n_keys_in_both_locales():
    used = set(re.findall(r"_zone2(?:I18n|Format)\('([^']+)'", INDEX))
    assert used
    for key in used:
        line = next((line for line in I18N.splitlines() if f"'{key}'" in line), "")
        assert line, key
        assert re.search(r"\ben\s*:", line), key
        assert re.search(r"\bzh\s*:", line), key
    lord_card = INDEX[INDEX.index("function showZone2LordChallengeCard"):INDEX.index("\nfunction startZone2LordRitual")]
    result_start = INDEX.index("function showZone2LordResultCard")
    result_card = INDEX[result_start:INDEX.index("\nfunction", result_start + 10)]
    assert "史萊姆平原" not in lord_card
    assert "史萊姆平原" not in result_card
    assert "e10.zone2." in lord_card and "e10.zone2." in result_card


def test_rwd_contract_covers_all_required_device_classes():
    assert 'data-zone-key="k21_25"' in INDEX
    assert "@media (orientation: portrait) and (max-width: 900px)" in INDEX
    assert "@media (max-width: 600px), (max-height: 700px)" in INDEX
    assert "object-fit: contain" in INDEX
    assert "overflow-wrap: anywhere" in INDEX
    assert "min-height: 44px" in INDEX
    assert "max-height: 34dvh" in INDEX
    assert "max-height: 88dvh" in INDEX


def test_lord_and_map_authority_remain_server_derived():
    assert "CORRECT_PROGRESS" in INDEX or "historical" in INDEX.lower()
    assert "_triggerZone2PostClearFromBossWin" in INDEX
    reveal = INDEX[INDEX.index("function showZone2UnlockReveal"):INDEX.index("\nfunction", INDEX.index("function showZone2UnlockReveal") + 10)]
    assert "nextZone.unlocked" in reveal
    assert "zone.unlocked =" not in reveal
    gate = (ROOT / "docs" / "planning" / "e10_zone2_final_bilingual_integration_gate_20260812.md").read_text(encoding="utf-8")
    assert "Zone 3" in gate and "does not write unlock authority" in gate
