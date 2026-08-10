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

Output isolation (do not weaken this): every test that exercises
cmd_generate_tts() runs against mod.ZONE1_FINAL_DIR redirected to a fresh
pytest tmp_path via the casting_backup fixture below. No test may ever
point that path at the real
tools/e10_zone1_audio/_local_review/zone1_final_voices/ directory, which
holds real Owner-approved, real-money ElevenLabs output that is NOT tracked
by git (see .gitignore) and therefore unrecoverable if deleted.
test_generation_never_touches_the_real_production_output_dir below is a
standing regression guard for this; keep it passing.
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
REAL_ZONE1_FINAL_DIR = TOOL_DIR / "_local_review" / "zone1_final_voices"


@pytest.fixture
def casting_backup(monkeypatch, tmp_path):
    original = mod.CASTING_PATH.read_bytes()
    # Redirect all generated output to an isolated per-test tmp directory.
    # pytest owns tmp_path's lifecycle, so no manual rmtree of anything is
    # needed (or permitted) here -- that manual rmtree of mod.ZONE1_FINAL_DIR
    # is exactly what destroyed the real Owner-approved output on
    # 2026-08-09 when it still pointed at the real repo path.
    monkeypatch.setattr(mod, "ZONE1_FINAL_DIR", tmp_path / "zone1_final_voices_test_output")
    # Point the owner-approval lock check at a path that does not exist by
    # default, so tests of cmd_generate_tts()'s generation mechanics are
    # not entangled with the separate owner-approval-lock feature (which
    # has its own dedicated tests below using a synthetic lock file).
    monkeypatch.setattr(mod, "FINAL_TTS_LOCK_PATH", tmp_path / "zone1_final_tts_lock_test.json")
    try:
        yield
    finally:
        mod.CASTING_PATH.write_bytes(original)


def test_generation_never_touches_the_real_production_output_dir(monkeypatch, casting_backup, capsys):
    """Regression guard for the 2026-08-09 incident: prove that a normal
    destructive test run of cmd_generate_tts() cannot reach the real
    Owner review directory, even if some future test forgets to use the
    casting_backup isolation.
    """
    pre_existing = REAL_ZONE1_FINAL_DIR.exists()
    REAL_ZONE1_FINAL_DIR.mkdir(parents=True, exist_ok=True)
    canary = REAL_ZONE1_FINAL_DIR / "DO_NOT_DELETE_test_isolation_canary.txt"
    canary.write_text("canary", encoding="utf-8")

    try:
        assert mod.ZONE1_FINAL_DIR != REAL_ZONE1_FINAL_DIR, (
            "mod.ZONE1_FINAL_DIR is not isolated from the real production "
            "output directory in this test run -- do not proceed until the "
            "casting_backup fixture's monkeypatch is fixed."
        )

        _lock_all_roles_with_fake_ids()
        monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
        monkeypatch.setattr(
            mod,
            "_text_to_speech",
            lambda api_key, voice_id, text, model_id, output_path: (
                output_path.write_bytes(b"FAKE_MP3") or True
            ),
        )

        mod.cmd_generate_tts()

        assert "GENERATE_TTS_VERIFICATION=PASS" in capsys.readouterr().out
        assert canary.exists(), "canary file in the REAL output dir was deleted by a test run"
        assert canary.read_text(encoding="utf-8") == "canary"
    finally:
        canary.unlink(missing_ok=True)
        if not pre_existing:
            try:
                REAL_ZONE1_FINAL_DIR.rmdir()
            except OSError:
                pass


def _lock_all_roles_with_fake_ids():
    casting = json.loads(mod.CASTING_PATH.read_text(encoding="utf-8"))
    for role_key, role in casting["roles"].items():
        for locale, slot in role["voices"].items():
            slot["locked"] = True
            slot["voice_id"] = f"fake_{role_key}_{locale}".replace("-", "_")
    mod.CASTING_PATH.write_text(json.dumps(casting, ensure_ascii=False, indent=2), encoding="utf-8")
    return casting


def test_current_repo_state_is_8_of_8_locked_and_generation_succeeds(monkeypatch, casting_backup, capsys):
    # Regression test against the REAL committed casting_candidates.json
    # (not a synthetic fixture): confirms all 8 role x locale slots are
    # locked with a real voice_id and that a full run succeeds end-to-end.
    # 2026-08-09: briefly 7/8 while zh-TW Messenger was recast (Owner
    # rejected Yui -- visual character is male); Owner approved Jun -
    # Bright and energetic and it was relocked, back to 8/8. If this ever
    # regresses to fewer than 8/8, this test will fail loudly rather than
    # silently -- update it deliberately if a role is ever unlocked for a
    # future recast.
    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    calls = []

    def fake_tts(api_key, voice_id, text, model_id, output_path):
        calls.append(voice_id)
        output_path.write_bytes(b"FAKE_MP3")
        return True

    monkeypatch.setattr(mod, "_text_to_speech", fake_tts)

    mod.cmd_generate_tts()

    out = capsys.readouterr().out
    assert DUMMY_KEY not in out
    assert "CAST_LOCKED=8/8" in out
    assert "GENERATE_TTS_VERIFICATION=PASS" in out
    manifest = json.loads(mod.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert len(calls) == len(manifest["entries"])


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


def test_only_mode_scopes_the_lock_gate_to_the_requested_roles(monkeypatch, casting_backup, capsys):
    # 2026-08-09: an unrelated in-progress recast of one role (e.g. the
    # messenger mid-audition) must not block a targeted --only fix for a
    # different, already-locked role -- only a full run needs all 8/8.
    casting = _lock_all_roles_with_fake_ids()
    casting["roles"]["runner"]["voices"]["zh-TW"]["locked"] = False
    casting["roles"]["runner"]["voices"]["zh-TW"]["voice_id"] = None
    mod.CASTING_PATH.write_text(json.dumps(casting, ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    calls = []

    def fake_tts(api_key, voice_id, text, model_id, output_path):
        calls.append(output_path.name)
        output_path.write_bytes(b"FAKE_MP3")
        return True

    monkeypatch.setattr(mod, "_text_to_speech", fake_tts)

    # anna/zh-TW (the narrator) is unrelated to the unlocked runner/zh-TW
    # slot, so this targeted regen must succeed even though the account is
    # only 7/8 locked overall.
    mod.cmd_generate_tts(only={"zone1_final_shot01_beat01_zh_anna.mp3"})

    out = capsys.readouterr().out
    assert "CAST_LOCKED=7/8" in out
    assert "GENERATE_TTS_VERIFICATION=PASS" in out
    assert calls == ["zone1_final_shot01_beat01_zh_anna.mp3"]


def test_only_mode_still_fails_closed_if_it_needs_the_unlocked_role(monkeypatch, casting_backup, capsys):
    casting = _lock_all_roles_with_fake_ids()
    casting["roles"]["runner"]["voices"]["zh-TW"]["locked"] = False
    casting["roles"]["runner"]["voices"]["zh-TW"]["voice_id"] = None
    mod.CASTING_PATH.write_text(json.dumps(casting, ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    calls = []
    monkeypatch.setattr(mod, "_text_to_speech", lambda *a, **k: calls.append(1) or True)

    with pytest.raises(SystemExit) as exc_info:
        mod.cmd_generate_tts(only={"zone1_final_shot10_beat01_zh_runner.mp3"})

    out = capsys.readouterr().out
    assert exc_info.value.code == 1
    assert "GENERATE_TTS_BLOCKED_UNRESOLVED_ROLES=runner/zh-TW" in out
    assert len(calls) == 0


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
    # The TTS input sent for an entry is its canonical "text" unless an
    # explicit "tts_text" override is present (a deliberate, per-entry,
    # TTS-input-only escape hatch -- e.g. for pronunciation/delivery fixes).
    # The canonical "text" field itself must never be silently rewritten.
    expected_texts = {
        (e["shot"], e["beat"], e["locale"]): e.get("tts_text", e["text"])
        for e in manifest["entries"]
    }

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


def test_full_regen_blocked_when_owner_approval_lock_exists(monkeypatch, casting_backup, capsys):
    _lock_all_roles_with_fake_ids()
    mod.FINAL_TTS_LOCK_PATH.write_text(
        json.dumps({"status": "OWNER_APPROVED_28_OF_28"}), encoding="utf-8"
    )
    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    calls = []
    monkeypatch.setattr(mod, "_text_to_speech", lambda *a, **k: calls.append(1) or True)

    with pytest.raises(SystemExit) as exc_info:
        mod.cmd_generate_tts()

    out = capsys.readouterr().out
    assert exc_info.value.code == 1
    assert "GENERATE_TTS_BLOCKED_BY_OWNER_APPROVAL_LOCK=YES" in out
    assert len(calls) == 0, "no TTS call may happen for a full run once the owner-approval lock exists"


def test_full_regen_proceeds_with_explicit_force_flag_despite_lock(monkeypatch, casting_backup, capsys):
    _lock_all_roles_with_fake_ids()
    mod.FINAL_TTS_LOCK_PATH.write_text(
        json.dumps({"status": "OWNER_APPROVED_28_OF_28"}), encoding="utf-8"
    )
    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    monkeypatch.setattr(
        mod, "_text_to_speech",
        lambda api_key, voice_id, text, model_id, output_path: (output_path.write_bytes(b"FAKE_MP3") or True),
    )

    mod.cmd_generate_tts(force_full_regen=True)

    assert "GENERATE_TTS_VERIFICATION=PASS" in capsys.readouterr().out


def test_only_mode_ignores_owner_approval_lock(monkeypatch, casting_backup, capsys):
    # A targeted --only run is itself an explicit per-file Owner request,
    # so the owner-approval lock must never block it.
    _lock_all_roles_with_fake_ids()
    mod.FINAL_TTS_LOCK_PATH.write_text(
        json.dumps({"status": "OWNER_APPROVED_28_OF_28"}), encoding="utf-8"
    )
    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    monkeypatch.setattr(
        mod, "_text_to_speech",
        lambda api_key, voice_id, text, model_id, output_path: (output_path.write_bytes(b"FAKE_MP3") or True),
    )

    mod.cmd_generate_tts(only={"zone1_final_shot01_beat01_zh_anna.mp3"})

    assert "GENERATE_TTS_VERIFICATION=PASS" in capsys.readouterr().out
