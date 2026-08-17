"""RELEASE-TOOLING-HOTFIX-03: executable coverage for the buildx platform parser.

Root cause: `docker buildx inspect` output is not a stable contract. Under a
transient Docker Desktop connectivity hiccup (observed directly on this host:
the daemon pipe timed out mid-ping) it emits an `Error:` line and OMITS the
`Nodes:`/`Platforms:` block entirely, while still exiting 0. The original
parser -- `(...).Matches | ForEach-Object { $_.Groups[1].Value }` -- crashed
with "Cannot index into a null array" on that shape: when Select-String finds
zero matches it emits nothing, so `(...).Matches` is $null; piping $null into
ForEach-Object is a PowerShell gotcha -- it invokes the script block ONCE
with $_ = $null (unlike an empty array, which invokes it zero times) -- so
`$_.Groups[1]` becomes `$null[1]`, which throws.

This file proves the hardened `Get-BuildxReportedPlatforms` function (and the
capability gate built on it) never has that shape: every malformed/absent/
failed input fails closed through the existing `Fail(...)` path instead of
crashing before it, and every well-formed input -- including realistic
whitespace variation -- still parses correctly.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest


def _ps_single_quoted(value: str) -> str:
    """A safe PowerShell single-quoted string literal for arbitrary text.

    Single-quoted PowerShell strings have exactly one escape rule (double
    the embedded `'`) and no backslash-escape processing at all, so this is
    safe for text containing double quotes, backslashes, or `$` -- unlike
    json.dumps(), whose backslash-escapes (e.g. `\\"`) are not meaningful
    inside a PowerShell string and previously broke the parser here.
    """
    return "'" + value.replace("'", "''") + "'"


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BUILD_PRODUCTION_IMAGE_SCRIPT = REPO_ROOT / "scripts" / "build-production-image.ps1"

FUNCTION_START_MARKER = "function Get-BuildxReportedPlatforms"
GATE_START_MARKER = "$buildxInspectOutput = @(& docker buildx inspect 2>$null)"
GATE_END_MARKER = "# 9. Build with buildx"
REAL_INSPECT_INVOCATION = "@(& docker buildx inspect 2>$null)"


def _source() -> str:
    return BUILD_PRODUCTION_IMAGE_SCRIPT.read_text(encoding="utf-8")


def _function_block() -> str:
    source = _source()
    start = source.index(FUNCTION_START_MARKER)
    # The function body is short and flat (no nested braces at column 0);
    # its closing brace is the first line consisting of exactly "}".
    end = source.index("\n}\n", start) + len("\n}\n")
    return source[start:end]


def _capability_gate_block() -> str:
    source = _source()
    start = source.index(GATE_START_MARKER)
    end = source.index(GATE_END_MARKER, start)
    return source[start:end]


def run_powershell(script: str, *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    preamble = (
        "$OutputEncoding = [Console]::OutputEncoding = "
        "New-Object System.Text.UTF8Encoding($false);\n"
        "$ErrorActionPreference = 'Stop'\n"
    )
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", preamble + script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )


def _parse_probe(output_lines, exit_code) -> dict:
    """Calls the real, unmodified Get-BuildxReportedPlatforms with synthetic input."""
    lines_literal = (
        "@(" + ", ".join(_ps_single_quoted(line) for line in output_lines) + ")"
        if output_lines is not None
        else "$null"
    )
    script = (
        _function_block()
        + "\n"
        + f"$__lines = {lines_literal}\n"
        + f"$__exit = {exit_code}\n"
        + "try {\n"
        + "  $r = Get-BuildxReportedPlatforms -InspectOutput $__lines -InspectExitCode $__exit\n"
        + "  [ordered]@{ ok = $true; platforms = @($r) } | ConvertTo-Json -Compress\n"
        + "} catch {\n"
        + "  [ordered]@{ ok = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress\n"
        + "}\n"
    )
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def _gate_probe(output_lines, exit_code, *, platform="linux/arm64") -> dict:
    """Runs the REAL capability-gate source (function + call site) with only
    the external `docker buildx inspect` invocation replaced by a fake -- the
    same "stub exactly the external-boundary call, run everything else for
    real" technique already used by test_canary_readiness_json_channel.py."""
    lines_literal = (
        "@(" + ", ".join(_ps_single_quoted(line) for line in output_lines) + ")"
        if output_lines is not None
        else "$null"
    )
    gate_block = _capability_gate_block().replace(
        REAL_INSPECT_INVOCATION, "@($script:FakeInspectOutput)"
    )
    assert "$script:FakeInspectOutput" in gate_block, "fake-injection substitution did not match"
    script = (
        _function_block()
        + "\n"
        + "function Fail($msg) { throw $msg }\n"
        + f"$Platform = {json.dumps(platform)}\n"
        + f"$script:FakeInspectOutput = {lines_literal}\n"
        + f"$LASTEXITCODE = {exit_code}\n"
        + "try {\n"
        + gate_block
        + "\n"
        + "  [ordered]@{ ok = $true; platforms = @($reportedPlatforms) } | ConvertTo-Json -Compress\n"
        + "} catch {\n"
        + "  [ordered]@{ ok = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress\n"
        + "}\n"
    )
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------------------
# 1. Standard, well-formed output -> PASS
# ---------------------------------------------------------------------------

def test_parses_standard_platforms_line():
    result = _parse_probe(["Platforms:        linux/amd64, linux/arm64"], 0)
    assert result["ok"] is True
    assert result["platforms"] == ["linux/amd64", "linux/arm64"]


def test_gate_proceeds_when_target_platform_is_reported():
    result = _gate_probe(["Platforms:        linux/amd64, linux/arm64"], 0)
    assert result["ok"] is True
    assert "linux/arm64" in result["platforms"]


# ---------------------------------------------------------------------------
# 2. Target platform absent from an otherwise-valid list -> FAIL CLOSED
# ---------------------------------------------------------------------------

def test_gate_fails_closed_when_target_platform_not_reported():
    result = _gate_probe(["Platforms:        linux/amd64"], 0)
    assert result["ok"] is False
    assert "does not report support for" in result["error"]
    assert "linux/amd64" in result["error"]


# ---------------------------------------------------------------------------
# 3. No Platforms line at all (including the real observed Error: shape)
#    -> FAIL CLOSED, no null-array exception
# ---------------------------------------------------------------------------

def test_parse_fails_closed_when_no_platforms_line_present():
    result = _parse_probe(["Name: desktop-linux", "Driver: docker"], 0)
    assert result["ok"] is False
    assert "Cannot index into a null array" not in result["error"]
    assert "did not contain a recognizable 'Platforms:' line" in result["error"]


def test_parse_fails_closed_on_real_observed_docker_desktop_connectivity_error_shape():
    # Captured verbatim from this host: docker buildx inspect exited 0 but
    # emitted an Error: line and no Nodes:/Platforms: block at all, because
    # the Docker Desktop pipe timed out mid-ping. This is the exact input
    # that produced "Cannot index into a null array" before this hotfix.
    result = _parse_probe(
        [
            "Name:          desktop-linux",
            "Driver:        ",
            "Last Activity: 2026-08-17 11:06:14 +0000 UTC",
            "Error:         Get \"http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/_ping\": context deadline exceeded",
        ],
        0,
    )
    assert result["ok"] is False
    assert "Cannot index into a null array" not in result["error"]
    assert "did not contain a recognizable 'Platforms:' line" in result["error"]


def test_gate_fails_closed_on_real_observed_docker_desktop_connectivity_error_shape():
    result = _gate_probe(
        [
            "Name:          desktop-linux",
            "Driver:        ",
            "Error:         Get \"http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/_ping\": context deadline exceeded",
        ],
        0,
    )
    assert result["ok"] is False
    assert "Cannot index into a null array" not in result["error"]
    assert "Unable to determine active buildx builder platform capability" in result["error"]


# ---------------------------------------------------------------------------
# 4. Empty / null output -> FAIL CLOSED, no null-array exception
# ---------------------------------------------------------------------------

def test_parse_fails_closed_on_empty_output():
    result = _parse_probe([], 0)
    assert result["ok"] is False
    assert "Cannot index into a null array" not in result["error"]
    assert "produced no output" in result["error"]


def test_parse_fails_closed_on_null_output():
    result = _parse_probe(None, 0)
    assert result["ok"] is False
    assert "Cannot index into a null array" not in result["error"]
    assert "produced no output" in result["error"]


# ---------------------------------------------------------------------------
# 5. Realistic whitespace / formatting variation -> correct parse
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "line",
    [
        "Platforms:linux/amd64,linux/arm64",
        "Platforms:   linux/amd64,   linux/arm64   ",
        "Platforms:\tlinux/amd64, linux/arm64",
    ],
    ids=["no-space-after-colon", "extra-inner-and-trailing-space", "tab-after-colon"],
)
def test_parses_realistic_whitespace_variation_when_target_present(line):
    result = _parse_probe([line], 0)
    assert result["ok"] is True
    assert "linux/arm64" in result["platforms"]


def test_parses_platforms_line_when_not_the_first_line():
    result = _parse_probe(
        [
            "Name:          desktop-linux",
            "Driver:        docker",
            "Status:        running",
            "Platforms:     linux/amd64, linux/arm64",
            "Labels:",
        ],
        0,
    )
    assert result["ok"] is True
    assert result["platforms"] == ["linux/amd64", "linux/arm64"]


# ---------------------------------------------------------------------------
# 6. buildx command failure (non-zero exit) -> FAIL CLOSED
# ---------------------------------------------------------------------------

def test_parse_fails_closed_on_nonzero_exit_code():
    result = _parse_probe(["some transient error text"], 1)
    assert result["ok"] is False
    assert "Cannot index into a null array" not in result["error"]
    assert "exit code 1" in result["error"]


def test_gate_fails_closed_on_nonzero_exit_code():
    result = _gate_probe(["some transient error text"], 1)
    assert result["ok"] is False
    assert "Unable to determine active buildx builder platform capability" in result["error"]


# ---------------------------------------------------------------------------
# Source-level regression + preserved fail-closed contract
# ---------------------------------------------------------------------------

def test_null_array_crash_prone_pattern_is_gone_from_executable_code():
    # Checked as an executable-statement signature, not a bare substring --
    # the explanatory comment above Get-BuildxReportedPlatforms legitimately
    # quotes the old broken expression verbatim to document what it replaced.
    content = _source()
    executable_lines = [
        line
        for line in content.splitlines()
        if not line.strip().startswith("#") and "$builderPlatforms = (" in line
    ]
    assert executable_lines == [], (
        f"the old crash-prone assignment must not remain as live code: {executable_lines}"
    )
    assert "function Get-BuildxReportedPlatforms" in content


def test_capability_gate_still_requires_buildx_and_never_falls_back():
    content = _source()
    assert "docker buildx version" in content
    assert "docker buildx inspect" in content
    section_start = content.index("docker buildx version")
    build_invocation_pos = content.index("'buildx', 'build'")
    capability_section = content[section_start:build_invocation_pos]
    # buildx-not-available, parse-failure, and target-not-reported must each
    # still fail closed through Fail() -- three Fail() sites now (was two
    # before this hotfix added the parse-failure branch). Prose inside those
    # Fail() messages legitimately mentions plain `docker build` as the
    # fallback being refused -- that is covered precisely (build_pos before
    # the section, verify-after-build ordering, etc.) by the pre-existing
    # test_build_script_has_no_silent_fallback_between_capability_check_and_build
    # in test_release_tooling.py; duplicating a naive text-absence check of
    # "docker build" here would false-fail even against the original code.
    assert capability_section.count("Fail ") + capability_section.count("Fail(") >= 3
    assert "-ErrorAction SilentlyContinue" not in capability_section


def test_get_buildx_reported_platforms_never_returns_empty_success():
    """A function that could return an empty array on 'success' would let
    `-notcontains $Platform` fail closed anyway, but that's an accident of
    the call site, not a guarantee of the function -- assert the function
    itself never does this, so it stays safe to reuse elsewhere."""
    content = _function_block()
    assert "if ($platforms.Count -eq 0) {" in content
    assert "throw" in content
