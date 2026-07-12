Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}

function Get-ImagePlatform {
    <#
    .SYNOPSIS
    Returns a Docker image's actual "os/architecture" string, e.g. "linux/arm64".
    .DESCRIPTION
    RELEASE-TOOLING-HOTFIX-02: pulled out as a shared helper so
    build-production-image.ps1's build-time platform verification and
    deploy-release-image.ps1's existing -ExpectedPlatform checks read this
    the same way, rather than each inlining their own `docker image inspect`
    format string.
    #>
    param([Parameter(Mandatory = $true)][string]$ImageTag)
    return (& docker image inspect $ImageTag --format '{{.Os}}/{{.Architecture}}').Trim().ToLowerInvariant()
}

function Resolve-RepoPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "Path is required."
    }
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path (Get-RepoRoot) $Path))
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [string]$WorkingDirectory = (Get-RepoRoot)
    )
    Push-Location $WorkingDirectory
    try {
        return (& git @Arguments)
    }
    finally {
        Pop-Location
    }
}

function Get-CurrentGitSha {
    return (Invoke-Git -Arguments @('rev-parse', 'HEAD')).Trim()
}

function Get-OriginMasterSha {
    return (Invoke-Git -Arguments @('rev-parse', 'origin/master')).Trim()
}

function Get-ShortGitSha {
    param([Parameter(Mandatory = $true)][string]$GitSha)
    $normalized = $GitSha.Trim()
    if ($normalized.Length -ge 8) {
        return $normalized.Substring(0, 8)
    }
    $safe = ($normalized -replace '[^0-9A-Za-z_-]', '')
    if ([string]::IsNullOrWhiteSpace($safe)) {
        $safe = 'unknown'
    }
    return $safe.PadRight(8, '0').Substring(0, 8)
}

function Get-ReleaseImageTag {
    param([Parameter(Mandatory = $true)][string]$GitSha)
    return "go-odyssey-app:{0}" -f (Get-ShortGitSha -GitSha $GitSha)
}

function Get-ReleaseArtifactBaseName {
    param([Parameter(Mandatory = $true)][string]$GitSha)
    return "go-odyssey-app_{0}" -f (Get-ShortGitSha -GitSha $GitSha)
}

function Test-TrackedTreeClean {
    param([string]$WorkingDirectory = (Get-RepoRoot))
    Push-Location $WorkingDirectory
    try {
        $status = (& git status --short --untracked-files=no)
        return [string]::IsNullOrWhiteSpace($status)
    }
    finally {
        Pop-Location
    }
}

function Assert-TrackedTreeClean {
    param([string]$WorkingDirectory = (Get-RepoRoot))
    if (-not (Test-TrackedTreeClean -WorkingDirectory $WorkingDirectory)) {
        throw "Tracked files must be clean before release work begins."
    }
}

function New-DetachedWorktree {
    param(
        [Parameter(Mandatory = $true)][string]$GitSha,
        [string]$Prefix = 'go-odyssey-release'
    )
    $worktree = Join-Path $env:TEMP ("{0}-{1}" -f $Prefix, ([guid]::NewGuid().ToString('N')))
    Invoke-Git -Arguments @('worktree', 'add', '--detach', $worktree, $GitSha) | Out-Null
    return $worktree
}

function Remove-DetachedWorktree {
    param([Parameter(Mandatory = $true)][string]$Path)
    try {
        if (Test-Path $Path) {
            Push-Location (Get-RepoRoot)
            try {
                & git worktree remove --force $Path | Out-Null
            }
            finally {
                Pop-Location
            }
        }
    }
    finally {
        Remove-Item -Recurse -Force -LiteralPath $Path -ErrorAction SilentlyContinue
    }
}

function Read-JsonFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path $Path)) {
        throw "Missing JSON file: $Path"
    }
    return (Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json)
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)]$InputObject,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $json = $InputObject | ConvertTo-Json -Depth 32
    Set-Content -LiteralPath $Path -Value $json -Encoding UTF8
}

function Get-ReleaseLayout {
    param([Parameter(Mandatory = $true)][string]$Path)
    $layout = Read-JsonFile -Path $Path
    $required = @(
        'ssh_alias',
        'remote_release_staging_directory',
        'compose_project',
        'compose_directory',
        'app_service_name',
        'scheduler_service_name',
        'nginx_service_name',
        'asset_source_path',
        'asset_container_mount_destination',
        'questions_content_source_path',
        'questions_content_mount_destination',
        'shadow_event_log_path',
        'health_url',
        'login_url',
        'homepage_url'
    )
    foreach ($name in $required) {
        if (-not $layout.PSObject.Properties.Name.Contains($name)) {
            throw "Release layout is missing required field: $name"
        }
    }
    return $layout
}

function Assert-OwnerGate {
    param(
        [Parameter(Mandatory = $true)][string]$Provided,
        [Parameter(Mandatory = $true)][string]$Expected
    )
    if ($Provided -ne $Expected) {
        throw "Owner gate mismatch. Expected -OwnerGate $Expected."
    }
}

function Quote-PosixShellArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    $singleQuote = [char]39
    if ($Value.Length -eq 0) {
        return "$singleQuote$singleQuote"
    }
    $escaped = $Value -replace "'", ($singleQuote + '"' + $singleQuote + '"' + $singleQuote)
    return $singleQuote + $escaped + $singleQuote
}

function Get-BooleanFlag {
    param(
        [string]$Value,
        [bool]$Default = $false
    )
    if ($null -eq $Value) {
        return $Default
    }
    $normalized = $Value.Trim().ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        return $false
    }
    return $normalized -in @('1', 'true', 'yes', 'on')
}

function ConvertTo-Utf8NoBomLfBytes {
    <#
    .SYNOPSIS
    Normalizes text to LF-only line endings and returns UTF-8 (no BOM) bytes.
    .DESCRIPTION
    RELEASE-TOOLING-HOTFIX-01: pulled out of the SSH stdin-piping helper so
    the exact byte payload that would be written to a remote shell's stdin
    can be unit-tested without spawning ssh or any process at all. This is
    the byte-level contract that Invoke-RemoteShellCommand's stdin pipe
    must match at runtime.
    #>
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)
    $normalized = $Text -replace "`r`n", "`n" -replace "`r", "`n"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    return $utf8NoBom.GetBytes($normalized)
}

function Invoke-ProcessWithUtf8NoBomStdin {
    <#
    .SYNOPSIS
    Spawns a native process and writes LF-normalized, UTF-8-no-BOM stdin
    to it -- byte-for-byte, with no trailing terminator added.
    .DESCRIPTION
    RELEASE-TOOLING-HOTFIX-01. Split out of Invoke-RemoteShellCommand so it
    can be exercised directly in tests against a stand-in executable (by
    full path) instead of only ever against the real `ssh` -- this is what
    makes the fix's actual byte-level behavior testable end-to-end.

    Does NOT use the `|` pipe operator (which always appends a trailing
    NewLine after the payload, regardless of encoding) -- writes via
    Process.StandardInput.Write() instead, so the exact normalized text is
    sent with nothing added or rewritten.

    [Console]::InputEncoding is what actually controls the encoding .NET
    assigns to a redirected child process's StandardInput StreamWriter on
    classic .NET Framework (confirmed by direct experiment -- setting
    $OutputEncoding or [Console]::OutputEncoding instead had no effect on
    the emitted bytes). Saved and restored around the call so it never
    leaks into the caller's session.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$FileName,
        [Parameter(Mandatory = $true)][string]$Arguments,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$StdinText
    )
    $normalized = $StdinText -replace "`r`n", "`n" -replace "`r", "`n"
    $previousConsoleInputEncoding = [Console]::InputEncoding
    try {
        [Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $FileName
        $psi.Arguments = $Arguments
        $psi.RedirectStandardInput = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.UseShellExecute = $false
        $proc = New-Object System.Diagnostics.Process
        $proc.StartInfo = $psi
        $proc.Start() | Out-Null
        $proc.StandardInput.Write($normalized)
        $proc.StandardInput.Close()
        $stdout = $proc.StandardOutput.ReadToEnd()
        $stderr = $proc.StandardError.ReadToEnd()
        $proc.WaitForExit()
        return [ordered]@{
            output = ($stdout + $stderr).Trim()
            exit_code = $proc.ExitCode
        }
    }
    finally {
        [Console]::InputEncoding = $previousConsoleInputEncoding
    }
}

function Invoke-RemoteShellCommand {
    <#
    .SYNOPSIS
    Single shared implementation of "run a command over ssh, optionally
    piping a script/stdin payload" used by preflight-production.ps1,
    deploy-release-image.ps1, rollback-release.ps1, and
    verify-production-release.ps1.
    .DESCRIPTION
    RELEASE-TOOLING-HOTFIX-01: root cause of the preflight "docker: not
    found" failure. On classic .NET Framework (what Windows PowerShell 5.1
    runs on), piping a string to a native executable's stdin
    (`$text | & someexe`) goes through a StreamWriter whose Encoding
    defaults to [Console]::InputEncoding at the moment the child process's
    stdin is set up -- and that default is a UTF-8 encoding WITH a byte-
    order mark (BOM) in this environment. The BOM lands as the first bytes
    of the remote command, so the remote shell sees `<BOM>docker ...`
    instead of `docker ...` and fails to resolve it.

    Note this is [Console]::InputEncoding, NOT the $OutputEncoding
    preference variable -- $OutputEncoding was tried first during
    diagnosis and did not change the emitted bytes at all (confirmed by
    direct experiment); only [Console]::InputEncoding actually controls
    the encoding .NET uses to construct the redirected child process's
    stdin writer here.

    Fixed here, once, by explicitly setting [Console]::InputEncoding to a
    no-BOM UTF8Encoding for the duration of the pipe (saved and restored
    immediately after in a finally block, so it never leaks into the
    caller's session or any other process this session spawns). This is a
    code-level fix, not a per-session workaround -- every script that
    calls this function gets it for free, and none of them may
    re-implement their own stdin-piping path.

    Once the BOM was fixed, a second, separate artifact surfaced: piping a
    string to a native command via `$text | & someexe` always terminates
    it with the StreamWriter's NewLine (`\r\n` on Windows), appended AFTER
    the (already LF-normalized) payload, regardless of $Console]::InputEncoding.
    A trailing CRLF is harmless to `sh -s`/`python -` reading a script from
    stdin in practice, but the acceptance contract for this hotfix is
    exact LF-only bytes with nothing rewritten -- so the stdin-carrying
    branches (ScriptText/StdinText) do not use the `|` pipe operator at
    all. They spawn ssh via System.Diagnostics.Process and write the
    normalized payload directly with StandardInput.Write() (not
    WriteLine()), giving byte-for-byte control over exactly what is sent.
    The plain -Command-only branch (no stdin payload) is unaffected by
    either issue and is left as a simple `& ssh` call.

    PowerShell 7/Core compatibility: not executed against a live pwsh in
    this environment (pwsh is not installed here). [Console]::InputEncoding
    and System.Diagnostics.Process are both standard, cross-version .NET
    APIs with identical semantics on both hosts; PowerShell 7/Core's own
    default pipe-to-native-process encoding is already UTF-8 without BOM,
    so this fix is expected to be a no-op behavior-wise there, not a
    regression. See docs/deployment/release_tooling_hotfix_01_ssh_stdin_bom.md
    for the full root-cause writeup and the experiments that ruled out
    $OutputEncoding and [Console]::OutputEncoding before landing on
    [Console]::InputEncoding, and ruled out the `|` pipe operator entirely
    for stdin payloads because of the trailing-CRLF artifact.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$SshAlias,
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Command,
        [string]$ScriptText,
        [string]$StdinText
    )
    if ($PSBoundParameters.ContainsKey('ScriptText') -and $PSBoundParameters.ContainsKey('StdinText')) {
        throw "Invoke-RemoteShellCommand: specify only one of -ScriptText or -StdinText, not both."
    }
    if ($PSBoundParameters.ContainsKey('ScriptText') -or $PSBoundParameters.ContainsKey('StdinText')) {
        $remoteCommandArg = if ($PSBoundParameters.ContainsKey('ScriptText')) { 'sh -s' } else { $Command }
        $payload = if ($PSBoundParameters.ContainsKey('ScriptText')) { $ScriptText } else { $StdinText }
        $invokeResult = Invoke-ProcessWithUtf8NoBomStdin -FileName 'ssh' -Arguments "$SshAlias `"$remoteCommandArg`"" -StdinText $payload
        return [ordered]@{
            name = $Name
            output = $invokeResult.output
            exit_code = $invokeResult.exit_code
        }
    }

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $rawOutput = & ssh $SshAlias $Command 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $output = ($rawOutput | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) {
            $_.ToString()
        }
        else {
            [string]$_
        }
    } | Out-String).Trim()
    return [ordered]@{
        name = $Name
        output = $output
        exit_code = $exitCode
    }
}

function Invoke-BoundedNativeCommand {
    <#
    .SYNOPSIS
    RELEASE-FIX-A2-STATIC-DEPLOY-FIX1: run a native executable with a hard
    process-level timeout, killing it (and its process tree) if it does not
    exit in time.
    .DESCRIPTION
    Confirmed live during RELEASE-FIX-A2's own production deploy: a single
    `ssh ... "mkdir -p ..."` invocation hung for ~15 minutes with an
    established TCP connection and near-zero CPU activity. SSH protocol
    keepalive options (ServerAliveInterval/ServerAliveCountMax) did not
    detect or end that hang -- they depend on the remote side failing to
    answer a keepalive request, which is a different failure mode than a
    client-side process that never returns control. A process-level
    WaitForExit(timeout) + Kill() is the only mechanism that bounds this
    class of hang unconditionally.

    Never includes ArgumentList or StdinText in a thrown error message --
    only FileName, OperationLabel, exit code, and timeout status, so SSH
    command payloads (which may reference internal paths or tokens) are
    never echoed into logs or exceptions.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$FileName,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [AllowEmptyString()][string]$StdinText,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)][string]$OperationLabel
    )
    if ($TimeoutSeconds -le 0) {
        throw "Invoke-BoundedNativeCommand: TimeoutSeconds must be a positive number of seconds for '$OperationLabel'."
    }
    $hasStdin = $PSBoundParameters.ContainsKey('StdinText')
    $previousConsoleInputEncoding = $null
    if ($hasStdin) {
        $previousConsoleInputEncoding = [Console]::InputEncoding
        [Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
    }
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $FileName
        # .NET Framework 4.x under Windows PowerShell 5.1 does not expose
        # ProcessStartInfo.ArgumentList (added later in .NET) -- build a
        # correctly quoted Windows command-line string instead. None of
        # this Sprint's arguments (ssh -o options, POSIX paths, host
        # aliases) contain embedded double quotes, so simple
        # space-triggered double-quoting is sufficient and exact.
        $psi.Arguments = (($ArgumentList | ForEach-Object {
            if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
        }) -join ' ')
        $psi.RedirectStandardInput = $hasStdin
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.UseShellExecute = $false

        $proc = New-Object System.Diagnostics.Process
        $proc.StartInfo = $psi
        $proc.Start() | Out-Null

        if ($hasStdin) {
            $normalized = $StdinText -replace "`r`n", "`n" -replace "`r", "`n"
            $proc.StandardInput.Write($normalized)
            $proc.StandardInput.Close()
        }

        $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
        $stderrTask = $proc.StandardError.ReadToEndAsync()
        $exited = $proc.WaitForExit([Math]::Max(1, $TimeoutSeconds) * 1000)

        if (-not $exited) {
            # Process.Kill(bool entireProcessTree) is not available on the
            # .NET Framework runtime Windows PowerShell 5.1 uses -- calling
            # it throws MethodException, which a bare try/catch swallowed
            # silently in an earlier version of this function, leaving the
            # hung process running as an orphan (confirmed live: repeated
            # test runs left multiple orphaned `Start-Sleep` processes
            # behind). taskkill /T /F reliably kills the process tree on
            # every supported Windows/PowerShell version; a plain
            # single-process Kill() is a fallback in case taskkill itself
            # is ever unavailable.
            try { & taskkill /F /T /PID $proc.Id 2>&1 | Out-Null } catch {}
            try { $proc.Kill() } catch {}
            throw "Timed out after ${TimeoutSeconds}s waiting for: $OperationLabel (process was terminated)"
        }

        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()

        return [ordered]@{
            exit_code = $proc.ExitCode
            output = ($stdout + $stderr).Trim()
            timed_out = $false
            operation = $OperationLabel
        }
    }
    finally {
        if ($hasStdin) { [Console]::InputEncoding = $previousConsoleInputEncoding }
    }
}

function Get-BoundedSshOptionArguments {
    <#
    .SYNOPSIS
    Standard non-interactive, bounded ssh/scp connection options shared by
    every bounded remote invocation this Sprint adds.
    #>
    param(
        [int]$ConnectTimeoutSeconds = 10,
        [int]$ServerAliveIntervalSeconds = 5,
        [int]$ServerAliveCountMax = 2
    )
    return @(
        '-o', 'BatchMode=yes',
        '-o', "ConnectTimeout=$ConnectTimeoutSeconds",
        '-o', 'ConnectionAttempts=1',
        '-o', "ServerAliveInterval=$ServerAliveIntervalSeconds",
        '-o', "ServerAliveCountMax=$ServerAliveCountMax"
    )
}

function Invoke-BoundedSshCommand {
    <#
    .SYNOPSIS
    Runs a single remote command (or a script piped to `sh -s` over stdin)
    with standard non-interactive/keepalive ssh options AND a hard
    process-level timeout. Use -ScriptText for a multi-statement script
    (e.g. creating many directories in one session); use -Command for a
    single simple remote command line.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$SshAlias,
        [string]$Command,
        [string]$ScriptText,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)][string]$OperationLabel,
        # Test-only override -- production code never sets this, so the
        # real 'ssh' on PATH is always used outside tests. Lets tests point
        # at a fake executable by exact path, avoiding Windows CreateProcess
        # .cmd/.bat PATH-resolution quirks that a bare-name PATH override
        # does not reliably trigger.
        [string]$SshExecutable = 'ssh'
    )
    if ($PSBoundParameters.ContainsKey('Command') -and $PSBoundParameters.ContainsKey('ScriptText')) {
        throw "Invoke-BoundedSshCommand: specify only one of -Command or -ScriptText, not both."
    }
    if (-not $PSBoundParameters.ContainsKey('Command') -and -not $PSBoundParameters.ContainsKey('ScriptText')) {
        throw "Invoke-BoundedSshCommand: one of -Command or -ScriptText is required."
    }
    $sshOptions = Get-BoundedSshOptionArguments
    if ($PSBoundParameters.ContainsKey('ScriptText')) {
        $argumentList = @($sshOptions) + @($SshAlias, 'sh -s')
        return Invoke-BoundedNativeCommand -FileName $SshExecutable -ArgumentList $argumentList -StdinText $ScriptText -TimeoutSeconds $TimeoutSeconds -OperationLabel $OperationLabel
    }
    $argumentList = @($sshOptions) + @($SshAlias, $Command)
    return Invoke-BoundedNativeCommand -FileName $SshExecutable -ArgumentList $argumentList -TimeoutSeconds $TimeoutSeconds -OperationLabel $OperationLabel
}

function Invoke-BoundedScpUpload {
    <#
    .SYNOPSIS
    Uploads a single local file to a remote destination via scp, with the
    same bounded/non-interactive connection options as
    Invoke-BoundedSshCommand plus a hard process-level timeout.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$LocalPath,
        [Parameter(Mandatory = $true)][string]$SshAlias,
        [Parameter(Mandatory = $true)][string]$RemotePath,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds,
        [string]$OperationLabel,
        # Test-only override -- see Invoke-BoundedSshCommand's -SshExecutable.
        [string]$ScpExecutable = 'scp'
    )
    if (-not $OperationLabel) { $OperationLabel = "scp upload to $RemotePath" }
    $sshOptions = Get-BoundedSshOptionArguments
    $argumentList = @($sshOptions) + @($LocalPath, "${SshAlias}:${RemotePath}")
    return Invoke-BoundedNativeCommand -FileName $ScpExecutable -ArgumentList $argumentList -TimeoutSeconds $TimeoutSeconds -OperationLabel $OperationLabel
}

function Assert-SafeRemoteRelativeFilePath {
    <#
    .SYNOPSIS
    Fail-closed safety check for a single manifest file path before it is
    used to derive a remote directory or upload destination.
    #>
    param([Parameter(Mandatory = $true)][string]$RelativePath)
    if ([string]::IsNullOrWhiteSpace($RelativePath)) {
        throw "Empty or whitespace-only file path is not allowed in a static release manifest."
    }
    $normalized = $RelativePath.Replace('\', '/')
    if ($normalized.StartsWith('/')) {
        throw "Absolute path is not allowed in a static release manifest: $RelativePath"
    }
    if ($normalized -match '^[A-Za-z]:') {
        throw "Drive-absolute path is not allowed in a static release manifest: $RelativePath"
    }
    $segments = $normalized.Split('/')
    if ($segments -contains '..') {
        throw "Path traversal ('..') is not allowed in a static release manifest: $RelativePath"
    }
    if ($segments -contains '') {
        throw "Path contains an empty segment (e.g. a doubled slash), which is not allowed: $RelativePath"
    }
}

function Get-RemoteParentDirectorySet {
    <#
    .SYNOPSIS
    Given the relative file paths from a static release manifest, returns
    the deterministic, deduplicated, sorted set of remote directories (the
    generation root itself, plus every nested parent directory) that must
    exist before any file is uploaded.
    .DESCRIPTION
    Computed once, up front, entirely as local string logic (no network) --
    this is what lets every required remote directory be created in a
    single bounded remote operation instead of one ssh invocation per
    unique directory (the RELEASE-FIX-A2 defect this Sprint fixes).
    #>
    param(
        [Parameter(Mandatory = $true)][string[]]$RelativePaths,
        [Parameter(Mandatory = $true)][string]$RemoteReleaseDir
    )
    $dirs = New-Object System.Collections.Generic.HashSet[string]
    $dirs.Add($RemoteReleaseDir) | Out-Null
    foreach ($relativePath in $RelativePaths) {
        Assert-SafeRemoteRelativeFilePath -RelativePath $relativePath
        $normalized = $relativePath.Replace('\', '/')
        $segments = $normalized.Split('/')
        if ($segments.Count -gt 1) {
            $parentSegments = $segments[0..($segments.Count - 2)]
            $parentRelative = [string]::Join('/', $parentSegments)
            $dirs.Add("$RemoteReleaseDir/$parentRelative") | Out-Null
        }
    }
    return @($dirs) | Sort-Object
}

function New-RemoteMkdirScriptText {
    <#
    .SYNOPSIS
    Builds a single POSIX `sh -s` script that creates every directory in
    the given set via one `mkdir -p` invocation -- so all of them can be
    created over one bounded ssh session, regardless of how many unique
    directories a manifest's governed subtrees introduce.
    #>
    param([Parameter(Mandatory = $true)][string[]]$Directories)
    $quoted = $Directories | ForEach-Object { Quote-PosixShellArgument $_ }
    return "mkdir -p " + ($quoted -join ' ')
}

function New-RemoteBatchShaVerificationScript {
    <#
    .SYNOPSIS
    RELEASE-FIX-A2-STATIC-DEPLOY-FIX2: builds a single POSIX `sh -s` script
    that verifies every manifest file's SHA-256 in ONE remote
    `sha256sum --check --strict` invocation, instead of one ssh session per
    file. The expected-hash data is embedded as a quoted heredoc inside the
    same script text (not a second stdin channel) -- `sh -s` receives one
    stdin stream carrying both the `cd && sha256sum --check` command and the
    heredoc data for it.
    .DESCRIPTION
    Root cause this replaces: 182 sequential ssh sessions, one per file,
    each individually bounded but collectively far more likely to hit a
    slow/contended SSH channel -- confirmed live in production: one such
    session (verifying a small, already-hashed-in-under-a-second file)
    exceeded a 30s bound while 181 others succeeded. A single batched
    verification measured 1.13s wall-clock for the same 182 files, 53MB
    total, during this Sprint's own read-only diagnostic.

    File order is preserved exactly as given (the caller passes
    manifest.files in on-disk manifest order) -- this is what makes the
    check deterministic and reproducible run to run.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$RemoteReleaseDir,
        [Parameter(Mandatory = $true)][object[]]$Files
    )
    $delimiter = '___RELEASE_FIX_A2_SHA256_CHECK_EOF___'
    $lines = foreach ($f in $Files) {
        Assert-SafeRemoteRelativeFilePath -RelativePath $f.path
        "$($f.sha256)  $($f.path)"
    }
    $quotedDir = Quote-PosixShellArgument $RemoteReleaseDir
    $checkBody = ($lines -join "`n")
    return "cd $quotedDir && sha256sum --check --strict - <<'$delimiter'`n$checkBody`n$delimiter`n"
}

function Get-BatchVerificationTimeoutSeconds {
    <#
    .SYNOPSIS
    Size-aware timeout for the single batched SHA-256 verification
    operation, with documented min/max bounds -- not a blind reuse of the
    30s quick-command timeout that a large asset closure could plausibly
    exceed even in a single session under real-world load.
    .DESCRIPTION
    Assumes a deliberately pessimistic 1 MB/s remote throughput floor (real
    measured throughput during RELEASE-FIX-A2's diagnostic was roughly
    47 MB/s -- 53MB in 1.13s -- so this bound carries a large safety
    margin, not a tight fit to the measurement).
    #>
    param(
        [Parameter(Mandatory = $true)][long]$TotalBytes,
        [int]$MinSeconds = 60,
        [int]$MaxSeconds = 300,
        [long]$AssumedBytesPerSecond = 1MB
    )
    $sizeBasedSeconds = [Math]::Ceiling($TotalBytes / [double]$AssumedBytesPerSecond)
    return [Math]::Min($MaxSeconds, [Math]::Max($MinSeconds, $sizeBasedSeconds))
}

function Get-ImageLabels {
    param([Parameter(Mandatory = $true)][string]$ImageTag)
    $raw = & docker image inspect $ImageTag --format '{{json .Config.Labels}}'
    return ($raw | ConvertFrom-Json)
}

function Assert-ImageRevisionMatches {
    param(
        [Parameter(Mandatory = $true)][string]$ImageTag,
        [Parameter(Mandatory = $true)][string]$ExpectedGitSha,
        [string]$ExpectedSgfEngineCommit = 'd729645c0ae267be6d89a5b49c007bc64284bbcc'
    )
    $labels = Get-ImageLabels -ImageTag $ImageTag
    if ($labels.'org.opencontainers.image.revision' -ne $ExpectedGitSha) {
        throw "Image $ImageTag revision does not match expected Git SHA $ExpectedGitSha."
    }
    if ($labels.'com.godokoro.sgf-engine.source-commit' -ne $ExpectedSgfEngineCommit) {
        throw "Image $ImageTag SGF Engine label does not match expected commit."
    }
    return $labels
}

function New-ReleaseManifestObject {
    param(
        [Parameter(Mandatory = $true)][string]$GitSha,
        [Parameter(Mandatory = $true)][string]$ImageTag,
        [Parameter(Mandatory = $true)][string]$ImageId,
        [Parameter(Mandatory = $true)][string]$ArchiveFilename,
        [Parameter(Mandatory = $true)][string]$ArchiveSha256,
        [Parameter(Mandatory = $true)][string]$BuildTimestamp,
        [Parameter(Mandatory = $true)][string]$BuildMachineIdentityClass,
        [Parameter(Mandatory = $true)]$TargetServiceNames,
        [Parameter(Mandatory = $true)]$ExternalContentRequirements,
        [Parameter(Mandatory = $true)]$ExpectedHealthEndpoints,
        [Parameter(Mandatory = $true)]$RollbackImageIdentity,
        [Parameter(Mandatory = $true)]$VerificationResult,
        $DeploymentTimestamp = $null,
        $OCIRevision = $null,
        [string]$OCIImageSource = 'https://github.com/beatleswu/beatleswu.github.io',
        [string]$SGFEngineSourceCommit = 'd729645c0ae267be6d89a5b49c007bc64284bbcc'
    )
    return [ordered]@{
        release_git_sha = $GitSha
        image_tag = $ImageTag
        image_id = $ImageId
        image_archive_filename = $ArchiveFilename
        archive_sha256 = $ArchiveSha256
        oci_revision = $(if ($OCIRevision) { $OCIRevision } else { $GitSha })
        oci_source = $OCIImageSource
        sgf_engine_source_commit = $SGFEngineSourceCommit
        build_timestamp = $BuildTimestamp
        build_machine_identity_class = $BuildMachineIdentityClass
        target_service_names = @($TargetServiceNames)
        external_content_requirements = $ExternalContentRequirements
        expected_health_endpoints = @($ExpectedHealthEndpoints)
        rollback_image_identity = $RollbackImageIdentity
        deployment_timestamp = $DeploymentTimestamp
        verification_result = $VerificationResult
    }
}

function Ensure-Directory {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
    }
}

function Select-ContainerMountForDestination {
    param(
        [Parameter(Mandatory = $true)][string]$MountsJson,
        [Parameter(Mandatory = $true)][string]$Destination,
        [string]$Context = 'container'
    )
    $parsedMounts = $MountsJson | ConvertFrom-Json
    $mounts = @($parsedMounts)
    $match = $mounts | Where-Object { $_.Destination -eq $Destination } | Select-Object -First 1
    if (-not $match) {
        throw "No live mount found for destination '$Destination' on $Context."
    }
    if ($match.Type -eq 'volume') {
        return [ordered]@{ type = 'volume'; name = $match.Name }
    }
    return [ordered]@{ type = 'bind'; source = $match.Source }
}

function ConvertFrom-NestedPowerShellJson {
    param(
        [Parameter(Mandatory = $true)]$RawOutput,
        [Parameter(Mandatory = $true)][string]$Context
    )
    $joined = if ($RawOutput -is [System.Array]) { $RawOutput -join [Environment]::NewLine } else { [string]$RawOutput }
    try {
        return ($joined | ConvertFrom-Json)
    }
    catch {
        $preview = if ($joined.Length -gt 2000) { $joined.Substring(0, 2000) + '...' } else { $joined }
        throw "$Context produced output that could not be parsed as JSON: $($_.Exception.Message)`nRaw output preview:`n$preview"
    }
}

function Get-CanonicalAppHealthcheckDefinition {
    return [ordered]@{
        test = @(
            'CMD',
            'python',
            '-c',
            "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=5)"
        )
        interval = '10s'
        timeout = '5s'
        retries = 12
        start_period = '30s'
    }
}

function New-CanonicalAppHealthcheckOverrideYaml {
    $definition = Get-CanonicalAppHealthcheckDefinition
    $testJson = ($definition.test | ConvertTo-Json -Compress)
    return @"
services:
  app:
    healthcheck:
      test: $testJson
      interval: $($definition.interval)
      timeout: $($definition.timeout)
      retries: $($definition.retries)
      start_period: $($definition.start_period)
"@
}

function Get-StaticAssetInventory {
    <#
    .SYNOPSIS
    RELEASE-FIX-A: reads deploy/live-static-asset-inventory.json, the single
    tracked source of truth for which root-level files app.py's
    _LIVE_STATIC_ELIGIBLE_FILES allowlist permits to be served from the
    live-static override root, and which of those this Sprint's static
    release tooling actually manages (required_in_generation).
    #>
    param([string]$Path = (Resolve-RepoPath 'deploy\live-static-asset-inventory.json'))
    return Read-JsonFile -Path $Path
}

function Get-SwVersionFromText {
    <#
    .SYNOPSIS
    Parses `const VERSION = '...'` out of sw.js source text.
    .DESCRIPTION
    Mirrors the pattern already proven by the untracked, host-only
    /opt/go-odyssey/deploy-static.ps1 (see
    docs/deployment/canonical_static_release_contract.md) -- re-implemented
    here as tracked, tested code.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$SwText,
        [string]$SourceLabel = 'sw.js'
    )
    $match = [regex]::Match($SwText, "const VERSION\s*=\s*'([^']+)'")
    if (-not $match.Success) {
        throw "Could not find sw.js VERSION in $SourceLabel."
    }
    return $match.Groups[1].Value
}

function Assert-SafeStaticRelativePath {
    <#
    .SYNOPSIS
    Fail-closed path safety check for static release files, independent of
    (and in addition to) the declarative allowlist in
    deploy/live-static-asset-inventory.json.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [Parameter(Mandatory = $true)]$Inventory
    )
    $normalized = $RelativePath.Replace('\', '/')
    if ($normalized -match '^[A-Za-z]:') {
        throw "Absolute drive paths are not allowed: $RelativePath"
    }
    if ($normalized.StartsWith('/')) {
        throw "Absolute paths are not allowed: $RelativePath"
    }
    if ($normalized.Contains('..')) {
        throw "Path traversal is not allowed: $RelativePath"
    }
    foreach ($pattern in $Inventory.forbidden_patterns.path_patterns) {
        if ($normalized -match $pattern) {
            throw "Forbidden path for static release: $RelativePath"
        }
    }
    if ($Inventory.eligible_files.entries -notcontains $normalized) {
        throw "Path is not in the live-static eligible_files allowlist: $RelativePath"
    }
}

function Assert-SafeStaticSubtreeRelativePath {
    <#
    .SYNOPSIS
    Fail-closed path safety check for governed subtree files (e.g. assets/**,
    see required_subtrees in deploy/live-static-asset-inventory.json) -- same
    traversal/forbidden-pattern defenses as Assert-SafeStaticRelativePath, but
    checked against a subtree prefix instead of the flat eligible_files list
    (a directory tree can never be fully enumerated in that flat allowlist).
    #>
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [Parameter(Mandatory = $true)][string]$Prefix,
        [Parameter(Mandatory = $true)]$Inventory
    )
    $normalized = $RelativePath.Replace('\', '/')
    if ($normalized -match '^[A-Za-z]:') {
        throw "Absolute drive paths are not allowed: $RelativePath"
    }
    if ($normalized.StartsWith('/')) {
        throw "Absolute paths are not allowed: $RelativePath"
    }
    if ($normalized.Contains('..')) {
        throw "Path traversal is not allowed: $RelativePath"
    }
    if (-not $normalized.StartsWith($Prefix)) {
        throw "Governed subtree file is not under its declared prefix '$Prefix': $RelativePath"
    }
    foreach ($pattern in $Inventory.forbidden_patterns.path_patterns) {
        if ($normalized -match $pattern) {
            throw "Forbidden path for static release: $RelativePath"
        }
    }
}

function Get-CanonicalAssetClosureManifest {
    <#
    .SYNOPSIS
    RELEASE-FIX-A2: reads the declarative closure manifest a required_subtrees
    entry points at (deploy/canonical-asset-closure-manifest.json) -- the
    single source of truth for exactly which files under a governed subtree
    (e.g. assets/**) a static release generation stages. See
    docs/incidents/2026-07-12-full-site-asset-outage.md.
    #>
    param([Parameter(Mandatory = $true)][string]$ManifestPath)
    return Read-JsonFile -Path (Resolve-RepoPath $ManifestPath)
}

function Get-StaticReleaseGenerationName {
    <#
    .SYNOPSIS
    Builds the release generation directory name, reusing the exact naming
    convention already established by the 93 pre-existing generations under
    /opt/go-odyssey-static/releases/ on the production host:
    <YYYYMMDD-HHMMSS>-<short-git-sha>-<sw-version-label>
    #>
    param(
        [Parameter(Mandatory = $true)][string]$GitSha,
        [Parameter(Mandatory = $true)][string]$SwVersion,
        [Parameter(Mandatory = $true)][DateTime]$TimestampUtc
    )
    $shortSha = Get-ShortGitSha -GitSha $GitSha
    $safeLabel = ($SwVersion -replace '[^0-9A-Za-z_-]', '-')
    $stamp = $TimestampUtc.ToString('yyyyMMdd-HHmmss')
    return "{0}-{1}-{2}" -f $stamp, $shortSha, $safeLabel
}

function New-StaticReleaseBundle {
    <#
    .SYNOPSIS
    Stages the required_in_generation files from an exact source checkout
    into a local staging directory, computing SHA-256/size for each.
    .DESCRIPTION
    Source files must come from the exact release git SHA's own worktree
    (see New-DetachedWorktree) -- never from the current working directory,
    production's live-static current, or an unrelated prior release bundle.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$SourceRoot,
        [Parameter(Mandatory = $true)][string]$StagePath,
        [Parameter(Mandatory = $true)]$Inventory
    )
    if (Test-Path -LiteralPath $StagePath) {
        Remove-Item -LiteralPath $StagePath -Recurse -Force
    }
    New-Item -ItemType Directory -Path $StagePath -Force | Out-Null

    $files = @()
    foreach ($relativePath in $Inventory.required_in_generation.entries) {
        Assert-SafeStaticRelativePath -RelativePath $relativePath -Inventory $Inventory
        $sourceFile = Join-Path $SourceRoot $relativePath
        if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
            throw "Static release source file missing: $sourceFile"
        }
        $targetFile = Join-Path $StagePath $relativePath
        Copy-Item -LiteralPath $sourceFile -Destination $targetFile -Force
        $hash = (Get-FileHash -LiteralPath $targetFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $size = (Get-Item -LiteralPath $targetFile).Length
        if ($size -le 0) {
            throw "Staged static release file is empty: $relativePath"
        }
        $files += [ordered]@{
            path = $relativePath
            sha256 = $hash
            size = $size
        }
    }

    foreach ($subtree in @($Inventory.required_subtrees.entries)) {
        $closureManifest = Get-CanonicalAssetClosureManifest -ManifestPath $subtree.manifest
        foreach ($entry in @($closureManifest.files)) {
            $relativePath = $entry.path
            Assert-SafeStaticSubtreeRelativePath -RelativePath $relativePath -Prefix $subtree.prefix -Inventory $Inventory
            $sourceFile = Join-Path $SourceRoot $relativePath
            if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
                throw "Governed subtree file declared in closure manifest is missing from source checkout (fail closed -- partial generation refused): $relativePath"
            }
            $targetFile = Join-Path $StagePath $relativePath
            New-Item -ItemType Directory -Path (Split-Path -Parent $targetFile) -Force | Out-Null
            Copy-Item -LiteralPath $sourceFile -Destination $targetFile -Force
            $hash = (Get-FileHash -LiteralPath $targetFile -Algorithm SHA256).Hash.ToLowerInvariant()
            $size = (Get-Item -LiteralPath $targetFile).Length
            if ($size -ne $entry.size) {
                throw "Staged subtree file size does not match closure manifest (fail closed): $relativePath -- expected $($entry.size), got $size"
            }
            if ($hash -ne $entry.sha256) {
                throw "Staged subtree file SHA-256 does not match closure manifest (fail closed): $relativePath -- expected $($entry.sha256), got $hash"
            }
            $files += [ordered]@{
                path = $relativePath
                sha256 = $hash
                size = $size
            }
        }
    }

    return $files
}

function New-StaticReleaseManifestObject {
    param(
        [Parameter(Mandatory = $true)][string]$GitSha,
        [Parameter(Mandatory = $true)][string]$GenerationId,
        [Parameter(Mandatory = $true)][string]$SwVersion,
        [Parameter(Mandatory = $true)][object[]]$Files,
        [Parameter(Mandatory = $true)][string]$CreatedAtUtc
    )
    return [ordered]@{
        release_git_sha = $GitSha
        static_generation_id = $GenerationId
        static_root = '/opt/go-odyssey-static'
        service_worker_version = $SwVersion
        asset_count = @($Files).Count
        files = @($Files)
        created_at = $CreatedAtUtc
    }
}

Export-ModuleMember -Function @(
    'Assert-ImageRevisionMatches',
    'Assert-OwnerGate',
    'Assert-TrackedTreeClean',
    'ConvertFrom-NestedPowerShellJson',
    'ConvertTo-Utf8NoBomLfBytes',
    'Ensure-Directory',
    'Get-ImagePlatform',
    'Invoke-ProcessWithUtf8NoBomStdin',
    'Invoke-RemoteShellCommand',
    'Get-CanonicalAppHealthcheckDefinition',
    'Get-BooleanFlag',
    'Get-CurrentGitSha',
    'Get-ImageLabels',
    'Get-OriginMasterSha',
    'Get-ReleaseArtifactBaseName',
    'Get-ReleaseImageTag',
    'Get-ReleaseLayout',
    'Get-RepoRoot',
    'Get-ShortGitSha',
    'New-CanonicalAppHealthcheckOverrideYaml',
    'Quote-PosixShellArgument',
    'Invoke-Git',
    'New-DetachedWorktree',
    'New-ReleaseManifestObject',
    'Read-JsonFile',
    'Remove-DetachedWorktree',
    'Resolve-RepoPath',
    'Select-ContainerMountForDestination',
    'Test-TrackedTreeClean',
    'Write-JsonFile',
    'Get-StaticAssetInventory',
    'Get-SwVersionFromText',
    'Assert-SafeStaticRelativePath',
    'Assert-SafeStaticSubtreeRelativePath',
    'Get-CanonicalAssetClosureManifest',
    'Get-StaticReleaseGenerationName',
    'New-StaticReleaseBundle',
    'New-StaticReleaseManifestObject',
    'Invoke-BoundedNativeCommand',
    'Get-BoundedSshOptionArguments',
    'Invoke-BoundedSshCommand',
    'Invoke-BoundedScpUpload',
    'Assert-SafeRemoteRelativeFilePath',
    'Get-RemoteParentDirectorySet',
    'New-RemoteMkdirScriptText',
    'New-RemoteBatchShaVerificationScript',
    'Get-BatchVerificationTimeoutSeconds'
)
