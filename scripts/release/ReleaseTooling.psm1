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
    'Get-StaticReleaseGenerationName',
    'New-StaticReleaseBundle',
    'New-StaticReleaseManifestObject'
)
