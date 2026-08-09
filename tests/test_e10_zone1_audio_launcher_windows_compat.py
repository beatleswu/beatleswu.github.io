"""E10-Z1-AUDIO-PRODUCTION-001 -- Windows launcher byte-level compatibility.

A live Owner test on Windows 10 failed: Run_Audition_Set_A.cmd fell apart
into nonsense tokens ('DITION', 'lf', 'dp0"', ...) and cmd.exe reported a
false "PowerShell was not found" result, even though PowerShell was running
and had just been used to invoke the launcher.

Root cause: the .cmd file had LF-only line endings (no CR) combined with
UTF-8-encoded Chinese text. cmd.exe's line/token parser is byte-oriented
and codepage-dependent; that combination corrupts line-boundary detection
in ways a text diff never surfaces, since every *character* is still
correct -- only the raw bytes are wrong for cmd.exe specifically.

These checks catch that class of regression before it reaches a real
Windows machine again: they inspect raw bytes, not decoded text.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CMD_PATH = REPO_ROOT / "tools" / "e10_zone1_audio" / "Run_Audition_Set_A.cmd"
PS1_PATH = REPO_ROOT / "tools" / "e10_zone1_audio" / "Run_Audition_Set_A.ps1"


def test_cmd_launcher_exists():
    assert CMD_PATH.is_file(), f"missing launcher: {CMD_PATH}"


def test_cmd_launcher_uses_crlf_only():
    data = CMD_PATH.read_bytes()
    assert b"\n" in data, "file appears to have no line breaks at all"
    bare_lf = data.count(b"\n") - data.count(b"\r\n")
    bare_cr = data.count(b"\r") - data.count(b"\r\n")
    assert bare_lf == 0, f"found {bare_lf} bare LF byte(s) without a preceding CR"
    assert bare_cr == 0, f"found {bare_cr} bare CR byte(s) without a following LF"


def test_cmd_launcher_is_ascii_only():
    data = CMD_PATH.read_bytes()
    try:
        data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise AssertionError(
            "Run_Audition_Set_A.cmd must be ASCII-only -- cmd.exe's batch "
            "parser is byte-oriented and non-ASCII bytes (even valid UTF-8) "
            "can corrupt line/token parsing. Put user-facing non-ASCII text "
            "in Run_Audition_Set_A.ps1 instead."
        ) from exc


def test_cmd_launcher_has_no_split_keywords():
    # A regression-specific tripwire: the failure symptom was words like
    # "AUDITION" splitting across a corrupted line boundary into a bogus
    # command token ("DITION"). Assert the whole word survives intact and
    # is not reachable by naively splitting on raw '\n'.
    text = CMD_PATH.read_text(encoding="ascii")
    assert "AUDITION" in text
    for line in text.splitlines():
        assert not line.strip().startswith("DITION"), (
            "found a bare 'DITION' line fragment -- indicates a corrupted "
            "line break inside the word 'AUDITION'"
        )


def test_cmd_launcher_resolves_script_directory_safely():
    text = CMD_PATH.read_text(encoding="ascii")
    assert 'cd /d "%~dp0"' in text, "must cd to its own directory using a quoted %~dp0"
    # The PowerShell script path must be built from %~dp0 and quoted as a whole,
    # not split across tokens (which was the other observed failure: a bare
    # `dp0"` fragment executed as its own command).
    assert re.search(r'-File\s+"%~dp0Run_Audition_Set_A\.ps1"', text), (
        "the -File argument must be a single quoted \"%~dp0Run_Audition_Set_A.ps1\" token"
    )


def test_cmd_launcher_detects_and_invokes_powershell_exe_explicitly():
    text = CMD_PATH.read_text(encoding="ascii")
    assert "where powershell.exe" in text, "must detect PowerShell via 'where powershell.exe'"
    assert "powershell.exe -NoProfile -ExecutionPolicy Bypass -File" in text, (
        "must invoke powershell.exe explicitly with -NoProfile -ExecutionPolicy Bypass -File"
    )
    # -NoProfile is required so the launcher does not depend on (or get
    # blocked by) the Owner's profile.ps1 execution policy.
    assert "-NoProfile" in text


def test_cmd_launcher_propagates_exit_code():
    text = CMD_PATH.read_text(encoding="ascii")
    assert 'set "EXITCODE=%ERRORLEVEL%"' in text
    assert "exit /b %EXITCODE%" in text


def test_ps1_launcher_exists():
    assert PS1_PATH.is_file(), f"missing launcher: {PS1_PATH}"


def test_ps1_launcher_uses_crlf_only():
    data = PS1_PATH.read_bytes()
    bare_lf = data.count(b"\n") - data.count(b"\r\n")
    bare_cr = data.count(b"\r") - data.count(b"\r\n")
    assert bare_lf == 0, f"found {bare_lf} bare LF byte(s) without a preceding CR"
    assert bare_cr == 0, f"found {bare_cr} bare CR byte(s) without a following LF"


def test_ps1_launcher_has_utf8_bom():
    # Windows PowerShell 5.1 (the Owner's confirmed environment) reads .ps1
    # files using the system codepage unless a UTF-8 BOM is present. Without
    # it, the embedded Chinese error/status text can render as mojibake even
    # though the script still parses and runs correctly.
    data = PS1_PATH.read_bytes()
    assert data[:3] == b"\xef\xbb\xbf", "Run_Audition_Set_A.ps1 must start with a UTF-8 BOM"


def test_ps1_launcher_never_writes_or_logs_the_key():
    text = PS1_PATH.read_text(encoding="utf-8-sig")
    banned_patterns = [
        r"Write-Host\s+\$PlainKey",
        r"Write-Host\s+\$env:ELEVENLABS_API_KEY",
        r"Out-File.*ELEVENLABS_API_KEY",
        r"\.env",
        r"secret_key\.txt",
    ]
    for pattern in banned_patterns:
        assert not re.search(pattern, text), f"found forbidden credential-handling pattern: {pattern}"
    assert "$env:ELEVENLABS_API_KEY = $PlainKey" in text
    assert "Remove-Item Env:\\ELEVENLABS_API_KEY" in text


def test_ps1_launcher_runs_check_then_audition_set_a_only():
    text = PS1_PATH.read_text(encoding="utf-8-sig")
    assert "--check" in text
    assert "--audition-set-a" in text
    for forbidden in ("--generate-tts", "--generate-sfx", "--generate-music", "--audition ", "'--audition'"):
        assert forbidden not in text, f"launcher must not invoke {forbidden!r}"


def test_ps1_launcher_opens_output_folder():
    text = PS1_PATH.read_text(encoding="utf-8-sig")
    assert "explorer.exe" in text
    assert "audition_set_a" in text
