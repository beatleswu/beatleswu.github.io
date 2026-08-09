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
Windows machine again: they inspect raw bytes, not decoded text. They run
against every Run_Audition_Set_*.{cmd,ps1} launcher pair (Set A, Set B, and
any future set), since the whole point of the .gitattributes glob fix is
that new launchers automatically get the same CRLF treatment.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL_DIR = REPO_ROOT / "tools" / "e10_zone1_audio"

LAUNCHERS = [
    pytest.param(
        {
            "cmd": TOOL_DIR / "Run_Audition_Set_A.cmd",
            "ps1": TOOL_DIR / "Run_Audition_Set_A.ps1",
            "ps1_name": "Run_Audition_Set_A.ps1",
            "mode": "--audition-set-a",
            "output_dir_name": "audition_set_a",
        },
        id="set_a",
    ),
    pytest.param(
        {
            "cmd": TOOL_DIR / "Run_Audition_Set_B.cmd",
            "ps1": TOOL_DIR / "Run_Audition_Set_B.ps1",
            "ps1_name": "Run_Audition_Set_B.ps1",
            "mode": "--audition-set-b",
            "output_dir_name": "audition_set_b",
        },
        id="set_b",
    ),
]


@pytest.mark.parametrize("launcher", LAUNCHERS)
def test_cmd_launcher_exists(launcher):
    assert launcher["cmd"].is_file(), f"missing launcher: {launcher['cmd']}"


@pytest.mark.parametrize("launcher", LAUNCHERS)
def test_cmd_launcher_uses_crlf_only(launcher):
    data = launcher["cmd"].read_bytes()
    assert b"\n" in data, "file appears to have no line breaks at all"
    bare_lf = data.count(b"\n") - data.count(b"\r\n")
    bare_cr = data.count(b"\r") - data.count(b"\r\n")
    assert bare_lf == 0, f"found {bare_lf} bare LF byte(s) without a preceding CR"
    assert bare_cr == 0, f"found {bare_cr} bare CR byte(s) without a following LF"


@pytest.mark.parametrize("launcher", LAUNCHERS)
def test_cmd_launcher_is_ascii_only(launcher):
    data = launcher["cmd"].read_bytes()
    try:
        data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise AssertionError(
            f"{launcher['cmd'].name} must be ASCII-only -- cmd.exe's batch "
            "parser is byte-oriented and non-ASCII bytes (even valid UTF-8) "
            "can corrupt line/token parsing. Put user-facing non-ASCII text "
            "in the paired .ps1 file instead."
        ) from exc


@pytest.mark.parametrize("launcher", LAUNCHERS)
def test_cmd_launcher_has_no_split_keywords(launcher):
    # A regression-specific tripwire: the failure symptom was words like
    # "AUDITION" splitting across a corrupted line boundary into a bogus
    # command token ("DITION"). Assert the whole word survives intact and
    # is not reachable by naively splitting on raw '\n'.
    text = launcher["cmd"].read_text(encoding="ascii")
    assert "AUDITION" in text
    for line in text.splitlines():
        assert not line.strip().startswith("DITION"), (
            "found a bare 'DITION' line fragment -- indicates a corrupted "
            "line break inside the word 'AUDITION'"
        )


@pytest.mark.parametrize("launcher", LAUNCHERS)
def test_cmd_launcher_resolves_script_directory_safely(launcher):
    text = launcher["cmd"].read_text(encoding="ascii")
    assert 'cd /d "%~dp0"' in text, "must cd to its own directory using a quoted %~dp0"
    # The PowerShell script path must be built from %~dp0 and quoted as a whole,
    # not split across tokens (which was the other observed failure: a bare
    # `dp0"` fragment executed as its own command).
    expected_ps1 = re.escape(launcher["ps1_name"])
    assert re.search(rf'-File\s+"%~dp0{expected_ps1}"', text), (
        f"the -File argument must be a single quoted \"%~dp0{launcher['ps1_name']}\" token"
    )


@pytest.mark.parametrize("launcher", LAUNCHERS)
def test_cmd_launcher_detects_and_invokes_powershell_exe_explicitly(launcher):
    text = launcher["cmd"].read_text(encoding="ascii")
    assert "where powershell.exe" in text, "must detect PowerShell via 'where powershell.exe'"
    assert "powershell.exe -NoProfile -ExecutionPolicy Bypass -File" in text, (
        "must invoke powershell.exe explicitly with -NoProfile -ExecutionPolicy Bypass -File"
    )
    # -NoProfile is required so the launcher does not depend on (or get
    # blocked by) the Owner's profile.ps1 execution policy.
    assert "-NoProfile" in text


@pytest.mark.parametrize("launcher", LAUNCHERS)
def test_cmd_launcher_propagates_exit_code(launcher):
    text = launcher["cmd"].read_text(encoding="ascii")
    assert 'set "EXITCODE=%ERRORLEVEL%"' in text
    assert "exit /b %EXITCODE%" in text


@pytest.mark.parametrize("launcher", LAUNCHERS)
def test_ps1_launcher_exists(launcher):
    assert launcher["ps1"].is_file(), f"missing launcher: {launcher['ps1']}"


@pytest.mark.parametrize("launcher", LAUNCHERS)
def test_ps1_launcher_uses_crlf_only(launcher):
    data = launcher["ps1"].read_bytes()
    bare_lf = data.count(b"\n") - data.count(b"\r\n")
    bare_cr = data.count(b"\r") - data.count(b"\r\n")
    assert bare_lf == 0, f"found {bare_lf} bare LF byte(s) without a preceding CR"
    assert bare_cr == 0, f"found {bare_cr} bare CR byte(s) without a following LF"


@pytest.mark.parametrize("launcher", LAUNCHERS)
def test_ps1_launcher_has_utf8_bom(launcher):
    # Windows PowerShell 5.1 (the Owner's confirmed environment) reads .ps1
    # files using the system codepage unless a UTF-8 BOM is present. Without
    # it, the embedded Chinese error/status text can render as mojibake even
    # though the script still parses and runs correctly.
    data = launcher["ps1"].read_bytes()
    assert data[:3] == b"\xef\xbb\xbf", f"{launcher['ps1'].name} must start with a UTF-8 BOM"


@pytest.mark.parametrize("launcher", LAUNCHERS)
def test_ps1_launcher_never_writes_or_logs_the_key(launcher):
    text = launcher["ps1"].read_text(encoding="utf-8-sig")
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


@pytest.mark.parametrize("launcher", LAUNCHERS)
def test_ps1_launcher_runs_check_then_its_own_mode_only(launcher):
    text = launcher["ps1"].read_text(encoding="utf-8-sig")
    assert "--check" in text
    assert launcher["mode"] in text
    other_modes = {"--audition-set-a", "--audition-set-b"} - {launcher["mode"]}
    forbidden = other_modes | {"--generate-tts", "--generate-sfx", "--generate-music", "--audition "}
    for flag in forbidden:
        assert flag not in text, f"{launcher['ps1'].name} must not invoke {flag!r}"


@pytest.mark.parametrize("launcher", LAUNCHERS)
def test_ps1_launcher_opens_its_own_output_folder(launcher):
    text = launcher["ps1"].read_text(encoding="utf-8-sig")
    assert "explorer.exe" in text
    assert launcher["output_dir_name"] in text


def test_gitattributes_forces_crlf_for_every_launcher():
    gitattributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"tools/e10_zone1_audio/Run_Audition_Set_\*\.cmd\s+text\s+eol=crlf", gitattributes), (
        ".gitattributes must force eol=crlf for tools/e10_zone1_audio/Run_Audition_Set_*.cmd, "
        "or a future launcher will silently inherit LF from the repo-wide eol=lf policy and "
        "reproduce this exact bug on Windows"
    )
    assert re.search(r"tools/e10_zone1_audio/Run_Audition_Set_\*\.ps1\s+text\s+eol=crlf", gitattributes)


def test_set_b_launcher_does_not_regenerate_set_a():
    text = (TOOL_DIR / "Run_Audition_Set_B.ps1").read_text(encoding="utf-8-sig")
    assert "--audition-set-a" not in text
