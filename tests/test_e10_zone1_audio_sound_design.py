"""E10-Z1-AUDIO-PRODUCTION-001 -- Zone 1 non-dialogue sound design (BGM/ambience/SFX).

Covers cmd_generate_music() and cmd_generate_sfx(): both must read
zone1_sound_design_brief.json, write into an isolated per-test tmp
directory (never the real repo path -- see the 2026-08-09 incident guarded
against in test_e10_zone1_audio_final_tts.py), verify every expected file
was actually written and non-empty, and fail closed if any generation call
fails.

Mocks _music and _sound_effect (no real network calls, no real credential).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL_DIR = REPO_ROOT / "tools" / "e10_zone1_audio"
sys.path.insert(0, str(TOOL_DIR))
import generate_zone1_audio as mod  # noqa: E402

DUMMY_KEY = "dummy_test_value_not_real"
REAL_SOUND_DESIGN_DIR = TOOL_DIR / "_local_review" / "sound_design"


@pytest.fixture
def isolated_sound_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "SOUND_DESIGN_DIR", tmp_path / "sound_design_test_output")
    # Point the owner-approval lock check at a path that does not exist by
    # default -- see the equivalent isolation in test_e10_zone1_audio_final_tts.py.
    monkeypatch.setattr(mod, "SOUND_DESIGN_LOCK_PATH", tmp_path / "zone1_sound_design_lock_test.json")
    yield


def test_generate_music_writes_two_candidates_per_cue(monkeypatch, isolated_sound_dir, capsys):
    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    calls = []

    def fake_music(api_key, prompt, length_ms, output_path):
        calls.append((prompt, length_ms, output_path.name))
        output_path.write_bytes(b"FAKE_MUSIC")
        return True

    monkeypatch.setattr(mod, "_music", fake_music)

    mod.cmd_generate_music()

    out = capsys.readouterr().out
    assert DUMMY_KEY not in out
    brief = json.loads(mod.SOUND_BRIEF_PATH.read_text(encoding="utf-8"))
    expected = sum(len(cue["candidates"]) for cue in brief["bgm_cues"])
    assert len(calls) == expected
    assert f"BGM_EXPECTED={expected}" in out
    assert f"BGM_GENERATED={expected}" in out
    assert "MUSIC_VERIFICATION=PASS" in out

    bgm_dir = mod.SOUND_DESIGN_DIR / "bgm"
    files = sorted(p.name for p in bgm_dir.glob("*.mp3"))
    assert len(files) == expected
    for name in files:
        assert (bgm_dir / name).stat().st_size > 0
        assert name.startswith(tuple(f"{i:02d}_BGM_" for i in range(1, expected + 1)))


def test_generate_music_fails_closed_on_a_missing_candidate(monkeypatch, isolated_sound_dir, capsys):
    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    call_count = {"n": 0}

    def flaky_music(api_key, prompt, length_ms, output_path):
        call_count["n"] += 1
        if call_count["n"] == 2:
            return False
        output_path.write_bytes(b"FAKE_MUSIC")
        return True

    monkeypatch.setattr(mod, "_music", flaky_music)

    with pytest.raises(SystemExit) as exc_info:
        mod.cmd_generate_music()

    out = capsys.readouterr().out
    assert exc_info.value.code == 1
    assert "MUSIC_VERIFICATION=FAIL" in out
    assert "BGM_MISSING=" in out


def test_generate_sfx_writes_ambience_and_highlighted_sfx(monkeypatch, isolated_sound_dir, capsys):
    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    calls = []

    def fake_sfx(api_key, text, duration_seconds, output_path):
        calls.append((text, duration_seconds, output_path.name))
        output_path.write_bytes(b"FAKE_SFX")
        return True

    monkeypatch.setattr(mod, "_sound_effect", fake_sfx)

    mod.cmd_generate_sfx()

    out = capsys.readouterr().out
    assert DUMMY_KEY not in out
    brief = json.loads(mod.SOUND_BRIEF_PATH.read_text(encoding="utf-8"))
    expected = len(brief["ambience"]) + len(brief["sfx"])
    assert len(calls) == expected
    assert f"SFX_AMBIENCE_EXPECTED={expected}" in out
    assert f"SFX_AMBIENCE_GENERATED={expected}" in out
    assert "SFX_VERIFICATION=PASS" in out

    ambience_dir = mod.SOUND_DESIGN_DIR / "ambience"
    sfx_dir = mod.SOUND_DESIGN_DIR / "sfx"
    assert len(list(ambience_dir.glob("*.mp3"))) == len(brief["ambience"])
    assert len(list(sfx_dir.glob("*.mp3"))) == len(brief["sfx"])

    highlighted = [s["key"] for s in brief["sfx"] if s.get("highlight")]
    assert highlighted, "brief should have at least one highlighted SFX for this test to be meaningful"
    for line in out.splitlines():
        if line.startswith("HIGHLIGHT_FOR_OWNER_LISTEN="):
            for key in highlighted:
                assert key in line


def test_generate_sfx_fails_closed_on_a_missing_file(monkeypatch, isolated_sound_dir, capsys):
    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    call_count = {"n": 0}

    def flaky_sfx(api_key, text, duration_seconds, output_path):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return False
        output_path.write_bytes(b"FAKE_SFX")
        return True

    monkeypatch.setattr(mod, "_sound_effect", flaky_sfx)

    with pytest.raises(SystemExit) as exc_info:
        mod.cmd_generate_sfx()

    out = capsys.readouterr().out
    assert exc_info.value.code == 1
    assert "SFX_VERIFICATION=FAIL" in out


def test_generate_music_and_sfx_never_touch_the_real_sound_design_dir(monkeypatch, isolated_sound_dir, capsys):
    """Regression guard mirroring the ZONE1_FINAL_DIR / AUDITION_SET_B_DIR
    canary tests: prove the isolation fixture actually redirects
    SOUND_DESIGN_DIR away from the real repo path.
    """
    assert mod.SOUND_DESIGN_DIR != REAL_SOUND_DESIGN_DIR
    pre_existing = REAL_SOUND_DESIGN_DIR.exists()
    REAL_SOUND_DESIGN_DIR.mkdir(parents=True, exist_ok=True)
    canary = REAL_SOUND_DESIGN_DIR / "DO_NOT_DELETE_test_isolation_canary.txt"
    canary.write_text("canary", encoding="utf-8")

    try:
        monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
        monkeypatch.setattr(
            mod, "_music",
            lambda api_key, prompt, length_ms, output_path: (output_path.write_bytes(b"FAKE_MUSIC") or True),
        )
        monkeypatch.setattr(
            mod, "_sound_effect",
            lambda api_key, text, duration_seconds, output_path: (output_path.write_bytes(b"FAKE_SFX") or True),
        )
        mod.cmd_generate_music()
        mod.cmd_generate_sfx()

        assert canary.exists()
        assert canary.read_text(encoding="utf-8") == "canary"
    finally:
        canary.unlink(missing_ok=True)
        if not pre_existing:
            try:
                REAL_SOUND_DESIGN_DIR.rmdir()
            except OSError:
                pass


def test_generate_music_blocked_when_owner_approval_lock_exists(monkeypatch, isolated_sound_dir, capsys):
    mod.SOUND_DESIGN_LOCK_PATH.write_text(json.dumps({"status": "OWNER_APPROVED"}), encoding="utf-8")
    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    calls = []
    monkeypatch.setattr(mod, "_music", lambda *a, **k: calls.append(1) or True)

    with pytest.raises(SystemExit) as exc_info:
        mod.cmd_generate_music()

    out = capsys.readouterr().out
    assert exc_info.value.code == 1
    assert "GENERATE_BLOCKED_BY_OWNER_APPROVAL_LOCK=YES" in out
    assert len(calls) == 0


def test_generate_sfx_blocked_when_owner_approval_lock_exists(monkeypatch, isolated_sound_dir, capsys):
    mod.SOUND_DESIGN_LOCK_PATH.write_text(json.dumps({"status": "OWNER_APPROVED"}), encoding="utf-8")
    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    calls = []
    monkeypatch.setattr(mod, "_sound_effect", lambda *a, **k: calls.append(1) or True)

    with pytest.raises(SystemExit) as exc_info:
        mod.cmd_generate_sfx()

    out = capsys.readouterr().out
    assert exc_info.value.code == 1
    assert "GENERATE_BLOCKED_BY_OWNER_APPROVAL_LOCK=YES" in out
    assert len(calls) == 0
