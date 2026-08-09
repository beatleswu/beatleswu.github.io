"""E10-Z1-AUDIO-PRODUCTION-001 -- full Zone 1 spoken dialogue generation.

Covers cmd_generate_tts() (the --generate-tts mode / Run_Zone1_Final_Voices
launcher): it must FAIL CLOSED and generate nothing at all if any of the 8
role x locale slots casting_candidates.json needs is not locked with a real
voice_id, must use the LOCKED voice_id (not any rejected/alternate
candidate), must generate exactly one file per canonical manifest entry with
a deterministic shot/beat/locale/speaker filename and no duplicates, must
use eleven_v3 (or whatever is configured) throughout, and must verify every
output file is real and non-empty before reporting success.

Mocks _text_to_speech (no real network calls, no real credential).
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL_DIR = REPO_ROOT / "tools" / "e10_zone1_audio"
sys.path.insert(0, str(TOOL_DIR))
import generate_zone1_audio as mod  # noqa: E402

DUMMY_KEY = "dummy_test_value_not_real"


@pytest.fixture
def casting_backup():
    original = mod.CASTING_PATH.read_bytes()
    try:
        yield
    finally:
        mod.CASTING_PATH.write_bytes(original)
        if mod.ZONE1_FINAL_DIR.exists():
            shutil.rmtree(mod.ZONE1_FINAL_DIR)


def _lock_all_roles_with_fake_ids():
    casting = json.loads(mod.CASTING_PATH.read_text(encoding="utf-8"))
    for role_key, role in casting["roles"].items():
        for locale, slot in role["voices"].items():
            slot["locked"] = True
            slot["voice_id"] = f"fake_{role_key}_{locale}".replace("-", "_")
    mod.CASTING_PATH.write_text(json.dumps(casting, ensure_ascii=False, indent=2), encoding="utf-8")
    return casting


def test_current_repo_state_is_5_of_8_locked_and_blocks_generation(monkeypatch, casting_backup, capsys):
    # Documents/locks in the real current state of casting_candidates.json
    # at the time of writing: 5 locked, 3 pending real voice_id handoff.
    # If this ever flips to 8/8, this test should be updated/removed rather
    # than silently left failing.
    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)

    with pytest.raises(SystemExit) as exc_info:
        mod.cmd_generate_tts()

    out = capsys.readouterr().out
    assert exc_info.value.code == 1
    assert "CAST_LOCKED=5/8" in out
    assert "GENERATE_TTS_VERIFICATION=FAIL" in out
    assert "GENERATE_TTS_BLOCKED_UNRESOLVED_ROLES=elder/zh-TW,hero/en,hero/zh-TW" in out
    assert not mod.ZONE1_FINAL_DIR.exists() or not any(mod.ZONE1_FINAL_DIR.iterdir())


def test_fails_closed_and_generates_nothing_when_any_role_unresolved(monkeypatch, casting_backup, capsys):
    casting = _lock_all_roles_with_fake_ids()
    # Deliberately unlock exactly one slot after locking all 8.
    casting["roles"]["hero"]["voices"]["zh-TW"]["locked"] = False
    casting["roles"]["hero"]["voices"]["zh-TW"]["voice_id"] = None
    mod.CASTING_PATH.write_text(json.dumps(casting, ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    calls = []
    monkeypatch.setattr(mod, "_text_to_speech", lambda *a, **k: calls.append(1) or True)

    with pytest.raises(SystemExit) as exc_info:
        mod.cmd_generate_tts()

    out = capsys.readouterr().out
    assert exc_info.value.code == 1
    assert "CAST_LOCKED=7/8" in out
    assert "GENERATE_TTS_BLOCKED_UNRESOLVED_ROLES=hero/zh-TW" in out
    assert len(calls) == 0, "no TTS call may happen when even one role is unresolved -- fail closed means ALL or NOTHING"
    assert not mod.ZONE1_FINAL_DIR.exists() or not any(mod.ZONE1_FINAL_DIR.iterdir())


def test_full_success_generates_all_28_with_deterministic_unique_filenames(monkeypatch, casting_backup, capsys):
    _lock_all_roles_with_fake_ids()
    manifest = json.loads(mod.MANIFEST_PATH.read_text(encoding="utf-8"))
    expected_count = len(manifest["entries"])

    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    calls = []

    def fake_tts(api_key, voice_id, text, model_id, output_path):
        calls.append((voice_id, text, model_id, output_path.name))
        output_path.write_bytes(b"FAKE_MP3")
        return True

    monkeypatch.setattr(mod, "_text_to_speech", fake_tts)

    mod.cmd_generate_tts()

    out = capsys.readouterr().out
    assert DUMMY_KEY not in out
    assert f"ZONE1_FINAL_TTS_EXPECTED={expected_count}" in out
    assert f"ZONE1_FINAL_TTS_GENERATED={expected_count}" in out
    assert "GENERATE_TTS_VERIFICATION=PASS" in out
    assert len(calls) == expected_count

    filenames = [c[3] for c in calls]
    assert len(set(filenames)) == expected_count, "every output filename must be unique"
    for filename in filenames:
        assert filename.startswith("zone1_final_shot")
        assert filename.endswith(".mp3")
    # Spot-check the deterministic shot/beat/locale/speaker mapping for the
    # first canonical beat (Narrator, shot 1 beat 1) in both locales.
    assert "zone1_final_shot01_beat01_zh_anna.mp3" in filenames
    assert "zone1_final_shot01_beat01_en_anna.mp3" in filenames

    # Model used throughout must be the configured one (eleven_v3 default).
    models_used = {c[2] for c in calls}
    assert models_used == {"eleven_v3"}

    # Every voice_id used must come from a role that was actually locked --
    # never an unlocked/rejected candidate.
    casting = json.loads(mod.CASTING_PATH.read_text(encoding="utf-8"))
    locked_voice_ids = {
        slot["voice_id"]
        for role in casting["roles"].values()
        for slot in role["voices"].values()
        if slot.get("locked")
    }
    voice_ids_used = {c[0] for c in calls}
    assert voice_ids_used <= locked_voice_ids, "generation must never use a voice_id outside the locked cast"

    on_disk = sorted(p.name for p in mod.ZONE1_FINAL_DIR.glob("*.mp3"))
    assert len(on_disk) == expected_count
    for name in on_disk:
        assert (mod.ZONE1_FINAL_DIR / name).stat().st_size > 0


def test_canonical_text_is_never_rewritten(monkeypatch, casting_backup):
    _lock_all_roles_with_fake_ids()
    manifest = json.loads(mod.MANIFEST_PATH.read_text(encoding="utf-8"))
    expected_texts = {(e["shot"], e["beat"], e["locale"]): e["text"] for e in manifest["entries"]}

    monkeypatch.setattr(mod, "get_api_key", lambda: "dummy_test_value_not_real")
    sent_texts = {}

    def fake_tts(api_key, voice_id, text, model_id, output_path):
        # filename encodes shot/beat/locale; parse it back out to cross-check.
        parts = output_path.stem.split("_")  # ['zone1', 'final', 'shot01', 'beat01', 'zh', 'anna']
        shot = int(parts[2].replace("shot", ""))
        beat = int(parts[3].replace("beat", ""))
        locale = "zh-TW" if parts[4] == "zh" else parts[4]
        sent_texts[(shot, beat, locale)] = text
        output_path.write_bytes(b"FAKE_MP3")
        return True

    monkeypatch.setattr(mod, "_text_to_speech", fake_tts)
    mod.cmd_generate_tts()

    assert sent_texts == expected_texts


def test_generate_tts_verification_fails_if_a_file_ends_up_missing(monkeypatch, casting_backup, capsys):
    _lock_all_roles_with_fake_ids()

    monkeypatch.setattr(mod, "get_api_key", lambda: "dummy_test_value_not_real")
    call_count = {"n": 0}

    def flaky_tts(api_key, voice_id, text, model_id, output_path):
        call_count["n"] += 1
        if call_count["n"] == 5:
            return False  # simulate one failed HTTP call, no file written
        output_path.write_bytes(b"FAKE_MP3")
        return True

    monkeypatch.setattr(mod, "_text_to_speech", flaky_tts)

    with pytest.raises(SystemExit) as exc_info:
        mod.cmd_generate_tts()

    out = capsys.readouterr().out
    assert exc_info.value.code == 1
    assert "GENERATE_TTS_VERIFICATION=FAIL" in out
