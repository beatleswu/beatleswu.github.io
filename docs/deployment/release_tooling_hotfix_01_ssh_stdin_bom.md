# RELEASE-TOOLING-HOTFIX-01: PowerShell 5.1 BOM injection in SSH stdin pipeline

```
Branch: hotfix/release-tooling-ssh-stdin-bom
Base: master
Scope: scripts/release/preflight-production.ps1, scripts/release/ReleaseTooling.psm1,
       tests/deployment/test_release_tooling.py, docs/deployment/*
Production mutation: NONE
Deployment: NONE
```

## Trigger

Running `preflight-production.ps1 -LayoutFile deploy\release-layout.production.json`
(read-only, no `-Execute`) as the first gate before the PREMIUM-UPSELL-HOTFIX-01
release attempt (target commit `b7ed3417281d3532b20d5b42a08f1736ade02a74`) failed
immediately:

```
Remote script failed [app_container_snapshot]: sh: 1: ﻿docker: not found
```

Note the invisible character between the colon and `docker` — a UTF-8 byte-order
mark (BOM, U+FEFF/`EF BB BF`).

## Root cause

`Invoke-RemoteCommandResult` (duplicated, near-identically, in all four release
scripts: `preflight-production.ps1`, `deploy-release-image.ps1`,
`rollback-release.ps1`, `verify-production-release.ps1`) piped script/stdin text
to `ssh` using PowerShell's `|` pipe operator:

```powershell
$normalizedScriptText | & ssh $layout.ssh_alias 'sh -s' 2>&1
```

On classic .NET Framework (what Windows PowerShell 5.1 runs on), piping a string
to a native executable's stdin goes through a `StreamWriter` whose `Encoding`
defaults to `[Console]::InputEncoding` at the moment the redirected child
process's stdin is set up. In this environment that default is `UTF8Encoding`
**with** a BOM (confirmed directly: `[Console]::InputEncoding.GetPreamble().Length`
== 3). The BOM lands as the literal first bytes written to the remote shell's
stdin, so `sh -s` (or `python3 -`) sees `<BOM>docker ...` instead of
`docker ...` and fails to resolve the first token.

This affects every script that duplicated this stdin-piping pattern, not just
`preflight-production.ps1` — confirmed by `grep`, all four scripts had their own
copy.

## Approaches tried, and ruled out, before finding the actual fix

Every hypothesis below was tested directly against a real (or realistically
faked) native child process on this exact Windows PowerShell 5.1 host — not
assumed from documentation, since the documented behavior of these APIs is
inconsistent/under-specified across .NET versions and turned out to not match
reality here in two of the four attempts below.

1. **`$OutputEncoding = New-Object System.Text.UTF8Encoding($false)`** before the
   pipe. This is the most commonly cited fix for this class of bug online.
   **Did not work** — the emitted bytes were unchanged (still `EF BB BF` first),
   even though `$OutputEncoding`'s default in this session is `ASCIIEncoding`
   (no BOM possible from ASCII at all), proving `$OutputEncoding` was never the
   variable controlling this in the first place.
2. **`[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)`**
   before the pipe. `[Console]::OutputEncoding`'s default WAS confirmed to be
   `UTF8Encoding` with a BOM in this session — a plausible-looking suspect — but
   setting it explicitly still did not change the emitted bytes.
3. **`System.Diagnostics.Process` + write directly to `.StandardInput.BaseStream`**
   (raw bytes, bypassing any `StreamWriter` encoding entirely, in theory). Still
   produced a BOM — 3 extra bytes appeared in the received data that were never
   in the byte array written. Root cause: merely *accessing* `Process.StandardInput`
   causes .NET to lazily construct its own internal `StreamWriter` using its own
   default encoding, and that `StreamWriter` writes its BOM preamble to the
   underlying stream on first use — **before** the caller ever touches
   `.BaseStream`. Writing to `.BaseStream` afterward doesn't undo bytes .NET
   already wrote via its own writer.
4. **`Process.StandardInput.Encoding`** was inspected directly at this point
   (`$proc.StandardInput.Encoding`) and confirmed to be `UTF8Encoding` with a
   3-byte preamble — matching `[Console]::InputEncoding`'s default, **not**
   `[Console]::OutputEncoding`. This is the actual controlling property.

## The fix

Set **`[Console]::InputEncoding`** (not `$OutputEncoding`, not
`[Console]::OutputEncoding`) to a no-BOM `UTF8Encoding` for the duration of the
call, saved and restored in a `finally` block:

```powershell
$previousConsoleInputEncoding = [Console]::InputEncoding
try {
    [Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
    # ... spawn process, write stdin ...
} finally {
    [Console]::InputEncoding = $previousConsoleInputEncoding
}
```

Confirmed directly: with this set, `Process.StandardInput.Encoding` reports a
0-byte preamble, and the receiving process gets exactly the intended bytes with
no BOM.

### A second artifact, found only after fixing the BOM

Once the BOM was gone, the payload the receiving side got still had one extra
trailing `\r\n` appended after the (correctly LF-normalized) content. Root
cause: PowerShell's `|` pipe operator always terminates a piped string with the
`StreamWriter`'s `NewLine` (`\r\n` on Windows) when writing it to a native
command — independent of encoding, and not something `[Console]::InputEncoding`
controls. A trailing blank/CRLF-only line is harmless to `sh -s`/`python -`
reading a script from stdin in practice, but this hotfix's acceptance bar was
exact-bytes, nothing rewritten — so the `|` pipe operator is no longer used for
stdin payloads at all. `Invoke-ProcessWithUtf8NoBomStdin` (new, shared) spawns
`ssh` via `System.Diagnostics.Process` directly and writes the normalized text
with `StandardInput.Write()` (not `WriteLine()`), giving byte-for-byte control
with nothing appended.

## What changed

- **`scripts/release/ReleaseTooling.psm1`** (shared module, new functions):
  - `ConvertTo-Utf8NoBomLfBytes` — pure function: normalizes CRLF→LF and
    returns the exact UTF-8-no-BOM byte payload. No process/network involved;
    exists so the byte-level contract can be unit-tested directly.
  - `Invoke-ProcessWithUtf8NoBomStdin` — spawns a native process
    (`-FileName`/`-Arguments`) and writes LF-normalized, UTF-8-no-BOM stdin to
    it via `Process.StandardInput.Write()`, with the `[Console]::InputEncoding`
    fix applied and restored around the call. Takes `-FileName` as a parameter
    specifically so it can be tested directly against a known real executable
    (`python`) instead of only ever against `ssh`.
  - `Invoke-RemoteShellCommand` — single shared implementation of "run a
    command over ssh, optionally piping a script/stdin payload", replacing the
    four near-identical local copies. Delegates to
    `Invoke-ProcessWithUtf8NoBomStdin` for the `-ScriptText`/`-StdinText`
    branches; the plain `-Command`-only branch (no stdin payload, no BOM risk)
    is left as a simple `& ssh $SshAlias $Command 2>&1` call.
- **`scripts/release/preflight-production.ps1`**: its local
  `Invoke-RemoteCommandResult` now only adds the fake-remote-response test seam
  (`$script:FakeRemoteResponses`, used by this repo's own test suite) on top of
  a call to the shared `Invoke-RemoteShellCommand` — no longer re-implements
  stdin piping itself.
- **`scripts/release/deploy-release-image.ps1`,
  `rollback-release.ps1`, `verify-production-release.ps1`**: their local
  `Invoke-RemoteCommandResult` wrappers now delegate to the shared
  `Invoke-RemoteShellCommand` too. No other logic in these scripts changed —
  release gates, SSH target resolution, and remote command semantics are
  untouched.

## PowerShell 7 compatibility

`pwsh` (PowerShell 7) is not installed in this environment (`pwsh` is not on
`PATH` here) — this fix was **not** exercised against a live PowerShell 7
process. What can be said with confidence:

- `[Console]::InputEncoding` and `System.Diagnostics.Process` are both
  standard, cross-version .NET APIs with identical semantics on Windows
  PowerShell 5.1 (.NET Framework) and PowerShell 7/Core.
- PowerShell 7/Core's own default pipe-to-native-process encoding is already
  UTF-8 without a BOM (a well-documented behavior change from Windows
  PowerShell 5.1), so explicitly setting the same no-BOM `UTF8Encoding` here is
  expected to be a no-op on PowerShell 7, not a behavior change.
- No PowerShell-5.1-only cmdlet or parameter was introduced (verified by a
  dedicated test asserting no PS6+-only syntax like `-Encoding utf8NoBOM`
  appears in the module).

This is reported as a reasoned compatibility argument backed by a static check,
**not** a claim of having run a live PowerShell 7 test — that distinction is
deliberate and should not be papered over in any future summary of this fix.

## Verification performed

- `ConvertTo-Utf8NoBomLfBytes` unit test: byte payload for multi-line,
  CRLF-containing input has no BOM, is LF-only, and round-trips to the exact
  expected text (pure function, no process spawned).
- `Invoke-ProcessWithUtf8NoBomStdin` end-to-end test: spawns a real
  `python.exe` child process via the shared helper, captures the literal bytes
  it received on stdin, and asserts: no BOM, first bytes match the expected
  content, no CRLF anywhere (fully LF-normalized, nothing appended).
- All four release scripts still parse cleanly
  (`assert_powershell_parse_ok`, existing test, unaffected).
- **Real production preflight re-run** after the fix, against
  `deploy/release-layout.production.json` (real SSH to `oracle_godoyssey`, real
  `docker inspect`, real `curl` health checks) — succeeded end-to-end with a
  full JSON readiness report: app/scheduler/nginx all `running`/`healthy`/`0`
  restarts, database identity matches between app and scheduler, questions
  file 41,591 records (matches the known-good PR #55 baseline), `/healthz`
  `/login` `/` all `200`, current production image `go-odyssey-app:1581d13e`
  (git SHA `1581d13ebca47f93ea92a597729f431de7e6ed1e` — the commit immediately
  before the PREMIUM-UPSELL-HOTFIX-01 target `b7ed3417281d3532b20d5b42a08f1736ade02a74`,
  as expected). No production mutation — preflight is read-only by design
  (SSH `docker inspect`/`curl`/read-only Python checks only).
- Full `tests/deployment/test_release_tooling.py` suite: 46 passed (43
  pre-existing + 3 new for this hotfix; one pre-existing test updated to
  reflect the refactor, see below).

## Pre-existing test updated

`test_preflight_script_reports_read_only_production_state` asserted specific
literal source text (`[System.Management.Automation.ErrorRecord]`, the CRLF
normalization regex) that lived inline in `preflight-production.ps1` before
this refactor. That text now lives once, in the shared module, so the test was
updated to assert the delegation (`Invoke-RemoteShellCommand` is called,
the old inline patterns are gone from `preflight-production.ps1` specifically)
plus a new test asserting the shared module is the sole owner of the
implementation.

## Status

```
RELEASE-TOOLING-HOTFIX-01: READY FOR REVIEW
```

Do not deploy from this branch. Once merged, the original GO_DEPLOY
authorization for PREMIUM-UPSELL-HOTFIX-01 (target commit
`b7ed3417281d3532b20d5b42a08f1736ade02a74`) resumes from
`preflight-production.ps1`.
