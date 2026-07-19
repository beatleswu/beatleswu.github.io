Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:GeneratedDetachedWorktrees = @{}

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
    return (Get-SafeFirstOutputLine (& docker image inspect $ImageTag --format '{{.Os}}/{{.Architecture}}')).ToLowerInvariant()
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
    $stderrPath = Join-Path ([System.IO.Path]::GetTempPath()) ("go-odyssey-git-stderr-" + [guid]::NewGuid().ToString('N') + '.log')
    $stdoutPath = Join-Path ([System.IO.Path]::GetTempPath()) ("go-odyssey-git-stdout-" + [guid]::NewGuid().ToString('N') + '.log')
    try {
        # Git writes normal progress such as `Preparing worktree...` to stderr.
        # PowerShell 5 promotes native stderr to NativeCommandError when the
        # module-wide ErrorActionPreference is Stop. Keep stderr separate and
        # judge success only by git's actual process exit code.
        # Do not invoke git through PowerShell's native-command pipeline here.
        # Windows PowerShell 5.1 can surface redirected native stderr as a
        # NativeCommandError in the caller's ErrorActionPreference=Stop scope,
        # even when the process exits successfully.  ProcessStartInfo keeps
        # stdout/stderr as data and makes the exit code authoritative.
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = 'git.exe'
        $psi.WorkingDirectory = $WorkingDirectory
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.Arguments = (($Arguments | ForEach-Object {
            if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\\"') + '"' } else { $_ }
        }) -join ' ')
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $psi
        $process.Start() | Out-Null
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $stdout = ($stdoutTask.GetAwaiter().GetResult().TrimEnd("`r", "`n")) -split "`r?`n"
        $stderr = $stderrTask.GetAwaiter().GetResult()
        $exitCode = $process.ExitCode
        $stdout | Set-Content -LiteralPath $stdoutPath -Encoding UTF8
        $stderr | Set-Content -LiteralPath $stderrPath -Encoding UTF8
        $stderr = if (Test-Path -LiteralPath $stderrPath) {
            Get-Content -Raw -LiteralPath $stderrPath
        }
        else {
            ''
        }
        if (-not [string]::IsNullOrWhiteSpace($stderr)) {
            Write-Host $stderr.TrimEnd()
        }
        if ($exitCode -ne 0) {
            $diagnostic = $stderr.Trim()
            if ([string]::IsNullOrWhiteSpace($diagnostic)) {
                $diagnostic = ($stdout -join [Environment]::NewLine).Trim()
            }
            throw "git $($Arguments -join ' ') failed with exit code $exitCode`: $diagnostic"
        }
        return $stdout
    }
    finally {
        Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stdoutPath -Force -ErrorAction SilentlyContinue
        Pop-Location
    }
}

function Get-SafeFirstOutputLine {
    param([AllowNull()][object]$Value)
    $items = @($Value)
    if ($items.Count -eq 0 -or $null -eq $items[0]) {
        return [string]::Empty
    }
    return ([string]$items[0]).Trim()
}

function Get-CurrentGitSha {
    return Get-SafeFirstOutputLine (Invoke-Git -Arguments @('rev-parse', 'HEAD'))
}

function Get-OriginMasterSha {
    return Get-SafeFirstOutputLine (Invoke-Git -Arguments @('rev-parse', 'origin/master'))
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

function Get-CanonicalFilesystemPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [string]$Label = 'Path'
    )
    if ([string]::IsNullOrWhiteSpace($Path) -or -not [System.IO.Path]::IsPathRooted($Path)) {
        throw "$Label must be a nonblank absolute filesystem path."
    }
    try {
        $fullPath = [System.IO.Path]::GetFullPath($Path)
    }
    catch {
        throw "$Label is not a valid absolute filesystem path."
    }
    $root = [System.IO.Path]::GetPathRoot($fullPath)
    if ([string]::Equals($fullPath, $root, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $root
    }
    return $fullPath.TrimEnd('\', '/')
}

function Test-CanonicalPathEqual {
    param(
        [Parameter(Mandatory = $true)][string]$Left,
        [Parameter(Mandatory = $true)][string]$Right
    )
    $leftPath = Get-CanonicalFilesystemPath -Path $Left -Label 'Left path'
    $rightPath = Get-CanonicalFilesystemPath -Path $Right -Label 'Right path'
    return [string]::Equals($leftPath, $rightPath, [System.StringComparison]::OrdinalIgnoreCase)
}

function Assert-NoReparsePointPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [string]$Label = 'Path'
    )
    $canonical = Get-CanonicalFilesystemPath -Path $Path -Label $Label
    $root = [System.IO.Path]::GetPathRoot($canonical)
    $current = $root
    $components = $canonical.Substring($root.Length) -split '[\\/]+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $pathsToInspect = @($root)
    foreach ($component in $components) {
        $current = Join-Path $current $component
        $pathsToInspect += $current
    }
    foreach ($candidate in $pathsToInspect) {
        if (-not ([System.IO.Directory]::Exists($candidate) -or [System.IO.File]::Exists($candidate))) {
            throw "$Label contains a missing or unsupported filesystem component."
        }
        try {
            $attributes = [System.IO.File]::GetAttributes($candidate)
        }
        catch {
            throw "$Label contains a filesystem component whose attributes cannot be verified."
        }
        if (($attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$Label must not contain a symbolic link, junction, mount point, or filesystem reparse point."
        }
    }
    return $canonical
}

function Assert-PathInsideCanonicalRoot {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$CanonicalRoot,
        [string]$Label = 'Path'
    )
    $candidate = Get-CanonicalFilesystemPath -Path $Path -Label $Label
    $root = Get-CanonicalFilesystemPath -Path $CanonicalRoot -Label 'Canonical root'
    $separator = [System.IO.Path]::DirectorySeparatorChar
    $inside = [string]::Equals($candidate, $root, [System.StringComparison]::OrdinalIgnoreCase) -or
        $candidate.StartsWith($root + $separator, [System.StringComparison]::OrdinalIgnoreCase)
    if (-not $inside) {
        throw "$Label must be inside the exact canonical worktree root."
    }
    return $candidate
}

function Assert-GovernedBuildScriptPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$CanonicalWorktreeRoot
    )
    $root = Assert-NoReparsePointPath -Path $CanonicalWorktreeRoot -Label 'Canonical worktree path'
    $scriptPath = Assert-NoReparsePointPath -Path $Path -Label 'Child build script path'
    $scriptPath = Assert-PathInsideCanonicalRoot -Path $scriptPath -CanonicalRoot $root -Label 'Child build script path'
    if (-not [System.IO.File]::Exists($scriptPath)) {
        throw "Child build script path does not exist or is not a file."
    }
    return $scriptPath
}

function Get-ProtectedUntrackedPattern {
    param([Parameter(Mandatory = $true)][string]$RelativePath)
    $leaf = [System.IO.Path]::GetFileName(($RelativePath -replace '/', '\'))
    if ($leaf -ieq 'secret_key.txt') { return 'secret_key.txt' }
    if ($leaf -like '.env*') { return '.env*' }
    if ($leaf -like '*.db') { return '*.db' }
    if ($leaf -like '*.sqlite*') { return '*.sqlite*' }
    if ($leaf -ieq 'questions.json') { return 'questions.json' }
    if ($leaf -like '*.sgf') { return '*.sgf' }
    if ($leaf -like '*.pem') { return '*.pem' }
    if ($leaf -like '*.key') { return '*.key' }
    if ($leaf -like '*.bak*') { return '*.bak*' }
    return $null
}

function Assert-CompleteWorktreeClean {
    param([Parameter(Mandatory = $true)][string]$WorkingDirectory)
    $untrackedAndIgnored = @(
        Invoke-Git -Arguments @('ls-files', '--others', '--exclude-standard') -WorkingDirectory $WorkingDirectory
        Invoke-Git -Arguments @('ls-files', '--others', '--ignored', '--exclude-standard') -WorkingDirectory $WorkingDirectory
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique
    foreach ($relativePath in $untrackedAndIgnored) {
        $pattern = Get-ProtectedUntrackedPattern -RelativePath $relativePath
        if ($pattern) {
            throw "Detached worktree contains protected untracked or ignored path '$relativePath' (pattern '$pattern')."
        }
    }
    $status = @(
        @(Invoke-Git -Arguments @('status', '--porcelain=v1', '--untracked-files=all') -WorkingDirectory $WorkingDirectory) |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    if ($status.Count -ne 0) {
        throw "Detached worktree must be completely clean, including untracked files."
    }
}

function Get-GitCommonDirectory {
    param([Parameter(Mandatory = $true)][string]$WorkingDirectory)
    $raw = Get-SafeFirstOutputLine (Invoke-Git -Arguments @('rev-parse', '--git-common-dir') -WorkingDirectory $WorkingDirectory)
    if ([System.IO.Path]::IsPathRooted($raw)) {
        return Get-CanonicalFilesystemPath -Path $raw -Label 'Git common directory'
    }
    return Get-CanonicalFilesystemPath -Path (Join-Path $WorkingDirectory $raw) -Label 'Git common directory'
}

function Get-RegisteredGitWorktreePaths {
    return @(Invoke-Git -Arguments @('worktree', 'list', '--porcelain') | Where-Object { $_ -like 'worktree *' } | ForEach-Object {
        Get-CanonicalFilesystemPath -Path $_.Substring('worktree '.Length) -Label 'Registered Git worktree path'
    })
}

function Assert-DetachedWorktreeIdentity {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ExpectedGitSha
    )
    $resolvedPath = Get-CanonicalFilesystemPath -Path $Path -Label 'Detached worktree path'
    if (-not [System.IO.Directory]::Exists($resolvedPath)) {
        throw "Detached worktree path does not exist or is not a directory."
    }
    $resolvedPath = Assert-NoReparsePointPath -Path $resolvedPath -Label 'Detached worktree path'
    $topLevel = Get-SafeFirstOutputLine (Invoke-Git -Arguments @('rev-parse', '--show-toplevel') -WorkingDirectory $resolvedPath)
    $resolvedTopLevel = Get-CanonicalFilesystemPath -Path $topLevel -Label 'Git top-level path'
    if (-not (Test-CanonicalPathEqual -Left $resolvedPath -Right $resolvedTopLevel)) {
        throw "Detached worktree root does not match the supplied isolated path."
    }
    $head = Get-SafeFirstOutputLine (Invoke-Git -Arguments @('rev-parse', 'HEAD') -WorkingDirectory $resolvedPath)
    $expected = Get-SafeFirstOutputLine (Invoke-Git -Arguments @('rev-parse', $ExpectedGitSha) -WorkingDirectory $resolvedPath)
    if ($head -ne $expected) {
        throw "Detached worktree HEAD does not match the expected release Git SHA."
    }
    $branch = Get-SafeFirstOutputLine (Invoke-Git -Arguments @('branch', '--show-current') -WorkingDirectory $resolvedPath)
    if (-not [string]::IsNullOrWhiteSpace($branch)) {
        throw "Release build worktree must be detached."
    }
    Assert-CompleteWorktreeClean -WorkingDirectory $resolvedPath
    return $resolvedPath
}

function Assert-GeneratedDetachedWorktreeIdentity {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ExpectedGitSha
    )
    $candidate = Get-CanonicalFilesystemPath -Path $Path -Label 'Generated detached worktree path'
    $key = $candidate.ToLowerInvariant()
    if (-not $script:GeneratedDetachedWorktrees.ContainsKey($key)) {
        throw "Generated detached worktree identity is not registered by this operation."
    }
    $record = $script:GeneratedDetachedWorktrees[$key]
    if (-not (Test-CanonicalPathEqual -Left $candidate -Right $record.path)) {
        throw "Generated detached worktree path does not exactly match its registered identity."
    }
    $expected = Get-SafeFirstOutputLine (Invoke-Git -Arguments @('rev-parse', $ExpectedGitSha) -WorkingDirectory $candidate)
    if ($expected -ne $record.expected_sha) {
        throw "Generated detached worktree expected SHA does not match its registered identity."
    }
    return Assert-DetachedWorktreeIdentity -Path $candidate -ExpectedGitSha $record.expected_sha
}

function Assert-GovernedBuildChildIdentity {
    param(
        [Parameter(Mandatory = $true)][string]$ExpectedCanonicalWorktreeRoot,
        [Parameter(Mandatory = $true)][string]$ExpectedGitSha,
        [Parameter(Mandatory = $true)][string]$ExpectedGitCommonDirectory,
        [Parameter(Mandatory = $true)][string]$ExecutingBuildScriptPath,
        [Parameter(Mandatory = $true)][ValidateSet('detached')][string]$ExpectedHeadState
    )
    $expectedRoot = Assert-NoReparsePointPath -Path $ExpectedCanonicalWorktreeRoot -Label 'Expected canonical worktree path'
    $actualCurrentDirectory = Get-CanonicalFilesystemPath -Path ([Environment]::CurrentDirectory) -Label 'Child process current directory'
    $actualCurrentDirectory = Assert-NoReparsePointPath -Path $actualCurrentDirectory -Label 'Child process current directory'
    if (-not (Test-CanonicalPathEqual -Left $actualCurrentDirectory -Right $expectedRoot)) {
        throw "Child process current directory does not equal the expected canonical worktree root."
    }
    $validatedRoot = Assert-DetachedWorktreeIdentity -Path $expectedRoot -ExpectedGitSha $ExpectedGitSha
    $expectedCommonDirectory = Assert-NoReparsePointPath -Path $ExpectedGitCommonDirectory -Label 'Expected Git common directory'
    $actualCommonDirectory = Assert-NoReparsePointPath -Path (Get-GitCommonDirectory -WorkingDirectory $validatedRoot) -Label 'Actual Git common directory'
    if (-not (Test-CanonicalPathEqual -Left $actualCommonDirectory -Right $expectedCommonDirectory)) {
        throw "Child worktree does not belong to the expected repository common Git directory."
    }
    Assert-GovernedBuildScriptPath -Path $ExecutingBuildScriptPath -CanonicalWorktreeRoot $validatedRoot | Out-Null
    return $validatedRoot
}

function New-DetachedWorktree {
    param(
        [Parameter(Mandatory = $true)][string]$GitSha,
        [string]$Prefix = 'go-odyssey-release'
    )
    if ($Prefix -notmatch '^[A-Za-z0-9][A-Za-z0-9-]*$') {
        throw "Detached worktree prefix contains unsupported characters."
    }
    $expectedParent = Assert-NoReparsePointPath -Path ([System.IO.Path]::GetTempPath()) -Label 'Generated worktree parent path'
    $worktree = Get-CanonicalFilesystemPath -Path (Join-Path $expectedParent ("{0}-{1}" -f $Prefix, ([guid]::NewGuid().ToString('N')))) -Label 'Generated worktree path'
    Invoke-Git -Arguments @('worktree', 'add', '--detach', $worktree, $GitSha) | Out-Null
    $resolvedSha = Get-SafeFirstOutputLine (Invoke-Git -Arguments @('rev-parse', $GitSha) -WorkingDirectory $worktree)
    $script:GeneratedDetachedWorktrees[$worktree.ToLowerInvariant()] = [ordered]@{
        path = $worktree
        parent = $expectedParent
        prefix = $Prefix
        expected_sha = $resolvedSha
        repository_root = Get-CanonicalFilesystemPath -Path (Get-RepoRoot) -Label 'Repository root'
        git_common_directory = Get-GitCommonDirectory -WorkingDirectory (Get-RepoRoot)
    }
    try {
        return Assert-GeneratedDetachedWorktreeIdentity -Path $worktree -ExpectedGitSha $resolvedSha
    }
    catch {
        Remove-DetachedWorktree -Path $worktree
        throw
    }
}

function Remove-DetachedWorktree {
    param([Parameter(Mandatory = $true)][string]$Path)
    $candidate = Get-CanonicalFilesystemPath -Path $Path -Label 'Cleanup worktree path'
    $key = $candidate.ToLowerInvariant()
    if (-not $script:GeneratedDetachedWorktrees.ContainsKey($key)) {
        throw "Cleanup refused: path was not created by this governed release-tooling operation."
    }
    $record = $script:GeneratedDetachedWorktrees[$key]
    if (-not (Test-CanonicalPathEqual -Left $candidate -Right $record.path)) {
        throw "Cleanup refused: path does not exactly match the generated worktree identity."
    }
    $parent = Get-CanonicalFilesystemPath -Path ([System.IO.Directory]::GetParent($candidate).FullName) -Label 'Cleanup parent path'
    if (-not (Test-CanonicalPathEqual -Left $parent -Right $record.parent)) {
        throw "Cleanup refused: generated worktree parent identity does not match."
    }
    $leaf = [System.IO.Path]::GetFileName($candidate)
    $expectedLeafPattern = '^{0}-[0-9a-f]{{32}}$' -f [regex]::Escape([string]$record.prefix)
    if ($leaf -notmatch $expectedLeafPattern) {
        throw "Cleanup refused: generated worktree leaf name is invalid."
    }
    $filesystemRoot = [System.IO.Path]::GetPathRoot($candidate)
    if (
        (Test-CanonicalPathEqual -Left $candidate -Right $filesystemRoot) -or
        (Test-CanonicalPathEqual -Left $candidate -Right $record.parent) -or
        (Test-CanonicalPathEqual -Left $candidate -Right $record.repository_root) -or
        (Test-CanonicalPathEqual -Left $candidate -Right (Get-RepoRoot))
    ) {
        throw "Cleanup refused: protected repository, parent, or filesystem root path."
    }
    $candidate = Assert-NoReparsePointPath -Path $candidate -Label 'Cleanup worktree path'
    $registeredMatches = @(Get-RegisteredGitWorktreePaths | Where-Object { Test-CanonicalPathEqual -Left $_ -Right $candidate })
    if ($registeredMatches.Count -ne 1) {
        throw "Cleanup refused: generated path is not exactly one registered Git worktree."
    }
    $candidateCommonDirectory = Get-GitCommonDirectory -WorkingDirectory $candidate
    if (-not (Test-CanonicalPathEqual -Left $candidateCommonDirectory -Right $record.git_common_directory)) {
        throw "Cleanup refused: worktree does not belong to the expected repository common Git directory."
    }
    $head = Get-SafeFirstOutputLine (Invoke-Git -Arguments @('rev-parse', 'HEAD') -WorkingDirectory $candidate)
    if ($head -ne $record.expected_sha) {
        throw "Cleanup refused: worktree HEAD does not match its generated identity."
    }
    Invoke-Git -Arguments @('worktree', 'remove', '--force', '--', $candidate) -WorkingDirectory $record.repository_root | Out-Null
    if ([System.IO.Directory]::Exists($candidate)) {
        throw "Governed Git worktree removal did not remove the exact path; directory left for manual review."
    }
    $stillRegistered = @(Get-RegisteredGitWorktreePaths | Where-Object { Test-CanonicalPathEqual -Left $_ -Right $candidate })
    if ($stillRegistered.Count -ne 0) {
        throw "Governed Git worktree removal did not unregister the exact path; state left for manual review."
    }
    $script:GeneratedDetachedWorktrees.Remove($key) | Out-Null
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
        'postgres_service_name',
        'asset_source_path',
        'asset_container_mount_destination',
        'questions_content_source_path',
        'questions_content_mount_destination',
        'shadow_event_log_path',
        'health_url',
        'login_url',
        'homepage_url',
        'production_env_path'
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

function Assert-ProtectedHostEnvCredentialAndTcpAuthentication {
    <#
    .SYNOPSIS
    The single, canonical DB credential gate for deploy and rollback. Runs
    entirely on the production host so the raw DB password never crosses
    back over SSH to the local machine -- not into an exception message, a
    PowerShell transcript, a captured command result, or local process
    memory.
    .DESCRIPTION
    PRODUCTION-RUNTIME-CANONICALIZATION (2026-07-14 godokoro.com 502
    incident follow-up, hardened after review): deploy and rollback used to
    derive POSTGRES_PASSWORD/DATABASE_URL by docker-inspecting the
    *existing* scheduler container's live environment, silently
    propagating a stale/incorrect credential forward on every future
    deploy/rollback. An earlier version of this fix read the protected
    .env back to the local machine and authenticated from here; that still
    let the raw password transit SSH stdout and live in a local PowerShell
    variable. This version instead sends one Python payload over SSH
    stdin (`python3 -`) that does everything remotely and returns only a
    sanitized `{"status": "ok"|"fail", "reason": ...}` JSON line -- this
    function and its caller never see the credential value itself.

    The remote payload:
      - reads production_env_path as KEY=VALUE data, never `source`d or
        dot-executed as shell code;
      - fails closed if the path is missing, not a regular file, has a
        duplicate assignment, POSTGRES_PASSWORD is missing/empty, its
        DATABASE_URL (if present) disagrees with the standalone
        POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB fields, or the
        credential contains a CR/LF/NUL byte;
      - determines the Postgres container's own already-pulled image ID
        and its Docker network purely from non-secret `docker inspect`
        provenance (never its environment) -- network resolution fails
        closed unless exactly one candidate network exists;
      - authenticates over a REAL TCP connection (`psql host=... port=...`,
        never the Postgres container's own Unix socket trust/peer) from a
        throwaway `--rm --pull=never` container built from that exact
        already-running image ID, so no floating/unverified image is ever
        pulled during a production deploy;
      - delivers the password to that throwaway container only via a 0600
        PGPASSFILE mounted read-only, escaped per the `.pgpass` format,
        removed in a `finally` regardless of outcome;
      - never prints the raw credential to stdout/stderr, and never
        mutates the Postgres role's credential or the Postgres
        container's lifecycle in any way.

    On any failure this throws and the caller must not proceed with any
    recreate/restart.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$SshAlias,
        [Parameter(Mandatory = $true)][string]$EnvPath,
        [Parameter(Mandatory = $true)][string]$PostgresContainerName
    )
    $script = @'
import json
import os
import subprocess
import sys
from urllib.parse import urlparse, unquote

ENV_PATH = "__ENV_PATH__"
POSTGRES_CONTAINER = "__POSTGRES_CONTAINER_NAME__"


def fail(reason):
    print(json.dumps({"status": "fail", "reason": reason}))
    sys.exit(1)


def pgpass_escape(value):
    return value.replace("\\", "\\\\").replace(":", "\\:")


def main():
    if not os.path.isfile(ENV_PATH) or os.path.islink(ENV_PATH):
        fail("env_path_missing_or_not_regular_file")

    # newline="" disables universal newline translation. Without it, a
    # lone CR embedded mid-value is silently rewritten to LF by Python's
    # default text-mode reading before the unsafe-character check below
    # ever runs -- turning what must be a fail-closed rejection into a
    # silent truncation of the credential instead (worse than failing).
    with open(ENV_PATH, "r", encoding="utf-8", errors="strict", newline="") as handle:
        raw_text = handle.read()

    assignments = {}
    seen = set()
    for raw_line in raw_text.split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in seen:
            fail("duplicate_assignment")
        seen.add(key)
        assignments[key] = value

    user = assignments.get("POSTGRES_USER") or "go"
    if "POSTGRES_PASSWORD" not in assignments:
        fail("postgres_password_missing")
    password = assignments["POSTGRES_PASSWORD"]
    if password == "":
        fail("postgres_password_empty")
    database = assignments.get("POSTGRES_DB") or "go_odyssey"

    for unsafe in ("\r", "\n", "\x00"):
        if unsafe in password or unsafe in user or unsafe in database:
            fail("credential_contains_unsafe_control_character")

    database_url = assignments.get("DATABASE_URL", "").strip()
    if database_url:
        parsed = urlparse(database_url)
        if (
            unquote(parsed.username or "") != user
            or unquote(parsed.password or "") != password
            or (parsed.path or "").lstrip("/") != database
        ):
            fail("database_url_disagrees_with_fields")

    try:
        inspect_raw = subprocess.check_output(
            ["docker", "inspect", POSTGRES_CONTAINER],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        fail("postgres_container_not_found")
    item = json.loads(inspect_raw)[0]
    image_id = item.get("Image")
    if not image_id:
        fail("postgres_image_identity_unavailable")
    networks = list(((item.get("NetworkSettings") or {}).get("Networks") or {}).keys())
    if len(networks) != 1:
        fail("postgres_network_not_uniquely_determined")
    network_name = networks[0]

    pgpass_line = "{}:5432:{}:{}:{}\n".format(
        POSTGRES_CONTAINER,
        pgpass_escape(database),
        pgpass_escape(user),
        pgpass_escape(password),
    )
    pgpass_path = "/tmp/.release-pgauth-{}.tmp".format(os.getpid())
    fd = os.open(pgpass_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(pgpass_line)
        conn_str = "host={} port=5432 dbname={} user={} sslmode=disable".format(
            POSTGRES_CONTAINER, database, user
        )
        try:
            result = subprocess.run(
                [
                    "docker", "run", "--rm", "--pull=never",
                    "--network", network_name,
                    "-v", "{}:/tmp/.pgpass:ro".format(pgpass_path),
                    "-e", "PGPASSFILE=/tmp/.pgpass",
                    image_id,
                    "psql", conn_str, "-tAc", "SELECT 1;",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            fail("tcp_auth_timeout")
    finally:
        try:
            os.remove(pgpass_path)
        except OSError:
            pass

    if result.returncode != 0 or result.stdout.strip() != "1":
        fail("tcp_password_authentication_failed")

    print(json.dumps({"status": "ok"}))


try:
    main()
except SystemExit:
    raise
except BaseException:
    # Catch-all: an unexpected exception here (malformed encoding, an
    # unexpected `docker inspect` shape, etc.) must never let a raw
    # traceback -- which could echo file contents or command output --
    # cross back over SSH. Only a fixed, non-secret reason code may.
    print(json.dumps({"status": "fail", "reason": "remote_helper_internal_failure"}))
    sys.exit(1)
'@
    $script = $script.Replace('__ENV_PATH__', $EnvPath).Replace('__POSTGRES_CONTAINER_NAME__', $PostgresContainerName)
    $result = Invoke-RemoteShellCommand -SshAlias $SshAlias -Name 'protected_credential_and_tcp_auth' -Command 'python3 -' -StdinText $script
    $sanitized = $null
    try { $sanitized = (Get-RemoteStandardOutput -Result $result) | ConvertFrom-Json } catch { $sanitized = $null }
    if ($result.exit_code -ne 0 -or -not $sanitized -or $sanitized.status -ne 'ok') {
        $reason = if ($sanitized -and $sanitized.reason) { $sanitized.reason } else { 'unknown' }
        throw "Protected credential / TCP authentication preflight failed (fail closed: no DB role repair, no recreate, no restart will be attempted). reason=$reason"
    }
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
            stdout = $stdout.Trim()
            stderr = $stderr.Trim()
            exit_code = $proc.ExitCode
        }
    }
    finally {
        [Console]::InputEncoding = $previousConsoleInputEncoding
    }
}

function Invoke-ProcessWithSeparateOutput {
    param(
        [Parameter(Mandatory = $true)][string]$FileName,
        [Parameter(Mandatory = $true)][string]$Arguments
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FileName
    $psi.Arguments = $Arguments
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    $proc.Start() | Out-Null
    $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
    $stderrTask = $proc.StandardError.ReadToEndAsync()
    $proc.WaitForExit()
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    return [ordered]@{
        output = ($stdout + $stderr).Trim()
        stdout = $stdout.Trim()
        stderr = $stderr.Trim()
        exit_code = $proc.ExitCode
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
            stdout = $invokeResult.stdout
            stderr = $invokeResult.stderr
            exit_code = $invokeResult.exit_code
        }
    }

    $sshArguments = ((@($SshAlias, $Command) | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    }) -join ' ')
    $invokeResult = Invoke-ProcessWithSeparateOutput -FileName 'ssh' -Arguments $sshArguments
    return [ordered]@{
        name = $Name
        output = $invokeResult.output
        stdout = $invokeResult.stdout
        stderr = $invokeResult.stderr
        exit_code = $invokeResult.exit_code
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
        [AllowEmptyString()][string]$WorkingDirectory,
        [switch]$RequireWorkingDirectory,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)][string]$OperationLabel
    )
    $workingDirectorySupplied = $PSBoundParameters.ContainsKey('WorkingDirectory')
    if ($RequireWorkingDirectory -and -not $workingDirectorySupplied) {
        throw "Invoke-BoundedNativeCommand: an explicit working directory is required for '$OperationLabel'."
    }
    $resolvedWorkingDirectory = $null
    if ($workingDirectorySupplied) {
        if ([string]::IsNullOrWhiteSpace($WorkingDirectory)) {
            throw "Invoke-BoundedNativeCommand: working directory must be nonblank for '$OperationLabel'."
        }
        if (-not [System.IO.Path]::IsPathRooted($WorkingDirectory)) {
            throw "Invoke-BoundedNativeCommand: working directory must be an absolute filesystem path for '$OperationLabel'."
        }
        $resolvedWorkingDirectory = Get-CanonicalFilesystemPath -Path $WorkingDirectory -Label 'Invoke-BoundedNativeCommand working directory'
        if (-not [System.IO.Directory]::Exists($resolvedWorkingDirectory)) {
            throw "Invoke-BoundedNativeCommand: working directory does not exist or is not a directory for '$OperationLabel'."
        }
        $resolvedWorkingDirectory = Assert-NoReparsePointPath -Path $resolvedWorkingDirectory -Label 'Invoke-BoundedNativeCommand working directory'
    }
    if ($TimeoutSeconds -le 0) {
        throw "Invoke-BoundedNativeCommand: TimeoutSeconds must be a positive number of seconds for '$OperationLabel'."
    }
    if ([string]::IsNullOrWhiteSpace($FileName)) {
        throw "Invoke-BoundedNativeCommand: native command is required for '$OperationLabel'."
    }
    $nativeCommand = Get-Command -Name $FileName -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $nativeCommand -or [string]::IsNullOrWhiteSpace([string]$nativeCommand.Source) -or -not (Test-Path -LiteralPath $nativeCommand.Source -PathType Leaf)) {
        throw "Invoke-BoundedNativeCommand: native command could not be resolved for '$OperationLabel'."
    }
    $resolvedFileName = [System.IO.Path]::GetFullPath($nativeCommand.Source)
    $hasStdin = $PSBoundParameters.ContainsKey('StdinText')
    $previousConsoleInputEncoding = $null
    if ($hasStdin) {
        $previousConsoleInputEncoding = [Console]::InputEncoding
        [Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
    }
    try {
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $resolvedFileName
        if ($resolvedWorkingDirectory) {
            $psi.WorkingDirectory = $resolvedWorkingDirectory
        }
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
        $stopwatch.Stop()

        return [ordered]@{
            exit_code = $proc.ExitCode
            output = ($stdout + $stderr).Trim()
            stdout = $stdout.Trim()
            stderr = $stderr.Trim()
            elapsed_seconds = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 3)
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

function Get-StaticPublicVerificationDeadlineSeconds {
    <#
    Scale-aware, bounded budget for public verification waves.
    Attempts means the initial request plus every configured retry.
    #>
    param(
        [long]$FileCount,
        [int]$Concurrency,
        [int]$RequestTimeoutSeconds,
        [int]$AttemptCount = 1
    )
    if ($FileCount -lt 0) { throw 'FileCount cannot be negative.' }
    if ($Concurrency -le 0) { throw 'Concurrency must be positive.' }
    if ($RequestTimeoutSeconds -lt 0) { throw 'RequestTimeoutSeconds cannot be negative.' }
    if ($AttemptCount -lt 1) { throw 'AttemptCount must be at least 1.' }

    $minimumSeconds = 120L
    $maximumSeconds = 7200L
    $startupAllowanceSeconds = 30L
    $completionAllowanceSeconds = 30L
    $safetyMarginSeconds = 60L
    $waves = [decimal][Math]::Ceiling([decimal]$FileCount / [decimal]$Concurrency)
    $maxWorkload = [decimal]$maximumSeconds - [decimal]$startupAllowanceSeconds - [decimal]$completionAllowanceSeconds - [decimal]$safetyMarginSeconds
    if ($RequestTimeoutSeconds -gt 0 -and $AttemptCount -gt 0) {
        $perWaveWork = [decimal]$RequestTimeoutSeconds * [decimal]$AttemptCount
        if ($waves -gt ($maxWorkload / $perWaveWork)) { return [int]$maximumSeconds }
    }
    $workload = $waves * [decimal]$RequestTimeoutSeconds * [decimal]$AttemptCount
    $computed = [decimal]$startupAllowanceSeconds + [decimal]$completionAllowanceSeconds + $workload + [decimal]$safetyMarginSeconds
    if ($computed -gt [decimal]$maximumSeconds) { return [int]$maximumSeconds }
    if ($computed -lt [decimal]$minimumSeconds) { return [int]$minimumSeconds }
    return [int][Math]::Ceiling($computed)
}

function Get-ArchiveTransferTimeoutSeconds {
    <#
    .SYNOPSIS
    RELEASE-FIX-A3: size-aware timeout for the single archive upload+extract
    operation, analogous to Get-BatchVerificationTimeoutSeconds but scaled
    for a much larger closure (hundreds of MB of images, not tens).
    #>
    param(
        [Parameter(Mandatory = $true)][long]$TotalBytes,
        [int]$MinSeconds = 120,
        [int]$MaxSeconds = 900,
        [long]$AssumedBytesPerSecond = 2MB
    )
    $sizeBasedSeconds = [Math]::Ceiling($TotalBytes / [double]$AssumedBytesPerSecond)
    return [Math]::Min($MaxSeconds, [Math]::Max($MinSeconds, $sizeBasedSeconds))
}

$script:DeterministicArchiveTarFlags = @(
    '--sort=name', '--mtime=UTC 1970-01-01', '--owner=0', '--group=0', '--numeric-owner'
)

# Git for Windows' GNU tar treats any path containing a colon (e.g.
# "D:\go-website\release-artifacts\x.tar") as a "host:path" remote-tar
# spec unless told otherwise, since GNU tar's remote-archive heuristic
# predates Windows drive letters -- confirmed live: an archive build with
# a Windows absolute path failed with "Cannot connect to C: resolve
# failed" against a real, correctly-resolved, genuinely-GNU tar binary.
# --force-local disables that heuristic and must be present on every tar
# invocation (build, list, smoke-test) that may receive a Windows path.
$script:TarForceLocalFlag = '--force-local'

function Test-GnuTarExecutableCapability {
    <#
    .SYNOPSIS
    RELEASE-FIX-A3-STATIC-DEPLOY-FIX3: verifies a candidate tar executable
    is real GNU tar AND actually supports the exact deterministic-archive
    flags packaging depends on -- via a real archive build through the
    SAME bounded native-process helper used for the real archive, not
    just a --version string check. A --version-only check would not have
    reliably caught the original incident (Windows bsdtar's --version
    output does not always make its identity unambiguous, and even a
    genuine GNU tar binary could in principle lack a specific flag on an
    old release) -- an actual smoke-test build is the only check that
    proves the exact invocation this Sprint relies on will work.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$TarExecutablePath
    )
    $result = [ordered]@{
        path = $TarExecutablePath
        exists = $false
        version_output = ''
        is_gnu_tar = $false
        smoke_test_passed = $false
        failure_reason = $null
    }
    if (-not (Test-Path -LiteralPath $TarExecutablePath -PathType Leaf)) {
        $result.failure_reason = 'executable not found at this path'
        return $result
    }
    $result.exists = $true

    try {
        $versionResult = Invoke-BoundedNativeCommand -FileName $TarExecutablePath -ArgumentList @('--version') -TimeoutSeconds 10 -OperationLabel "tar --version probe"
    }
    catch {
        $result.failure_reason = "failed to execute --version: $($_.Exception.Message)"
        return $result
    }
    $result.version_output = $versionResult.output
    if ($versionResult.exit_code -ne 0 -or $versionResult.output -notmatch 'GNU tar') {
        $result.failure_reason = 'not GNU tar (--version output did not contain "GNU tar") -- Windows bsdtar and other non-GNU implementations are rejected'
        return $result
    }
    $result.is_gnu_tar = $true

    $probeDir = Join-Path ([System.IO.Path]::GetTempPath()) ("gnu_tar_probe_" + [System.Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $probeDir -Force | Out-Null
    try {
        $sampleFile = Join-Path $probeDir 'probe.txt'
        Set-Content -LiteralPath $sampleFile -Value 'probe' -NoNewline -Encoding UTF8
        $listFile = Join-Path $probeDir 'filelist.txt'
        # WriteAllLines always uses Environment.NewLine (CRLF on Windows) --
        # GNU tar's -T file list only strips the trailing \n, leaving a
        # literal \r in the parsed filename ("probe.txt\r": not found).
        # Write LF-only, unconditionally, regardless of host platform.
        [System.IO.File]::WriteAllText($listFile, "probe.txt`n")
        $archivePath = Join-Path $probeDir 'probe.tar'
        $tarArgs = @($script:DeterministicArchiveTarFlags) + @($script:TarForceLocalFlag, '-cf', $archivePath, '-C', $probeDir, '-T', $listFile)
        $buildResult = Invoke-BoundedNativeCommand -FileName $TarExecutablePath -ArgumentList $tarArgs -TimeoutSeconds 15 -OperationLabel "tar capability smoke test"
        if ($buildResult.exit_code -ne 0) {
            $result.failure_reason = "smoke-test archive build with the required deterministic flags failed (exit $($buildResult.exit_code)): $($buildResult.output)"
            return $result
        }
        if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf)) {
            $result.failure_reason = 'smoke-test archive build reported success but produced no archive file'
            return $result
        }
        $result.smoke_test_passed = $true
    }
    finally {
        Remove-Item -LiteralPath $probeDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    return $result
}

function Resolve-GnuTarExecutable {
    <#
    .SYNOPSIS
    RELEASE-FIX-A3-STATIC-DEPLOY-FIX3: finds a real GNU tar executable
    capable of the exact deterministic-archive flags packaging requires,
    and fails closed rather than silently falling back to whatever a bare
    `tar` name happens to resolve to on PATH -- which on Windows can
    silently resolve to the bundled bsdtar (the exact production incident
    this function exists to prevent from recurring).
    .DESCRIPTION
    Resolution order:
      1. An explicit override -- the -OverridePath parameter if supplied,
         otherwise the GO_ODYSSEY_GNU_TAR environment variable. When an
         override is given, it is the ONLY candidate tried: if it fails
         capability verification, this throws immediately citing exactly
         why, rather than silently falling through to auto-discovery and
         masking an operator's explicit misconfiguration.
      2. A Git for Windows installation discovered from the real git.exe
         location on PATH (git.exe lives at <root>\cmd\git.exe or
         <root>\bin\git.exe; GNU tar ships at <root>\usr\bin\tar.exe).
      3. Known Git for Windows install locations, as a last-resort
         fallback only -- never the sole supported path, and only tried
         when no override was given and git.exe discovery found nothing
         usable.
    Every candidate is verified with Test-GnuTarExecutableCapability
    before being accepted. If nothing passes, this throws with every
    candidate examined and why each failed -- it never silently returns
    an unverified or non-GNU tar path.
    #>
    param(
        [string]$OverridePath
    )
    $override = $OverridePath
    if ([string]::IsNullOrWhiteSpace($override)) {
        $override = $env:GO_ODYSSEY_GNU_TAR
    }
    if (-not [string]::IsNullOrWhiteSpace($override)) {
        $probe = Test-GnuTarExecutableCapability -TarExecutablePath $override
        if ($probe.smoke_test_passed) {
            return [ordered]@{
                path = $override
                version_output = $probe.version_output
                source = 'override'
                examined_candidates = @($probe)
            }
        }
        throw "GNU tar override '$override' (from -GnuTarPath or `$env:GO_ODYSSEY_GNU_TAR) is not usable: $($probe.failure_reason)"
    }

    $examined = @()
    $candidates = @()

    $gitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($gitCommand) {
        $gitBinDir = Split-Path -Parent $gitCommand.Source
        $gitRoot = Split-Path -Parent $gitBinDir
        $candidates += (Join-Path $gitRoot 'usr\bin\tar.exe')
    }

    $candidates += @(
        'C:\Program Files\Git\usr\bin\tar.exe',
        'C:\Program Files (x86)\Git\usr\bin\tar.exe'
    )

    $seen = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($candidate in $candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        if (-not $seen.Add($candidate.ToLowerInvariant())) { continue }
        $probe = Test-GnuTarExecutableCapability -TarExecutablePath $candidate
        $examined += $probe
        if ($probe.smoke_test_passed) {
            return [ordered]@{
                path = $candidate
                version_output = $probe.version_output
                source = 'discovered'
                examined_candidates = $examined
            }
        }
    }

    $summary = (@($examined) | ForEach-Object { "$($_.path) -> $($_.failure_reason)" }) -join '; '
    throw "No GNU tar executable capable of the required deterministic-archive flags was found (Windows bsdtar is never accepted as a silent fallback). Set `$env:GO_ODYSSEY_GNU_TAR or pass -GnuTarPath to pin an explicit known-good GNU tar. Candidates examined: $summary"
}

function New-DeterministicStaticArchive {
    <#
    .SYNOPSIS
    RELEASE-FIX-A3: builds ONE deterministic tar archive of every staged
    file in a static release bundle, in sorted path order, with normalized
    mtime/owner/group -- so uploading a hundreds-of-files, hundreds-of-MB
    closure is one bounded transfer instead of one scp per file.
    .DESCRIPTION
    Every path added to the archive must already have passed
    Assert-SafeRemoteRelativeFilePath (the manifest/bundle build step
    upstream of this function already enforces that) -- this function does
    not re-validate, it only orders and archives what New-StaticReleaseBundle
    already staged and verified.

    RELEASE-FIX-A3-STATIC-DEPLOY-FIX3: requires an explicit, pre-resolved
    GnuTarExecutablePath (see Resolve-GnuTarExecutable) and invokes it
    through the same bounded native-process helper (Invoke-BoundedNativeCommand)
    used everywhere else in this module -- never a bare `tar` name via
    Start-Process, which on Windows can silently resolve to the bundled
    bsdtar instead of a real GNU tar.

    This is the ONLY place a static release archive is ever built. It is
    called exactly once, during packaging (package-static-release.ps1) --
    deploy-static-release.ps1 must never call this function; it consumes
    the already-built, already-hashed archive as an explicit input.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$BundlePath,
        [Parameter(Mandatory = $true)][string[]]$RelativePaths,
        [Parameter(Mandatory = $true)][string]$ArchivePath,
        [Parameter(Mandatory = $true)][string]$GnuTarExecutablePath,
        [int]$TimeoutSeconds = 300
    )
    if (-not (Test-Path -LiteralPath $GnuTarExecutablePath -PathType Leaf)) {
        throw "New-DeterministicStaticArchive: GnuTarExecutablePath does not exist: $GnuTarExecutablePath"
    }
    if (Test-Path -LiteralPath $ArchivePath) {
        Remove-Item -LiteralPath $ArchivePath -Force
    }
    $sorted = $RelativePaths | Sort-Object
    $listFile = [System.IO.Path]::GetTempFileName()
    try {
        # WriteAllLines always uses Environment.NewLine (CRLF on Windows) --
        # GNU tar's -T file list only strips the trailing \n, leaving a
        # literal \r in every parsed filename ("assets/foo.webp\r": not
        # found). Write LF-only, unconditionally, regardless of host
        # platform, so the file list parses identically wherever this runs.
        [System.IO.File]::WriteAllText($listFile, (($sorted -join "`n") + "`n"))
        $tarArgs = @($script:DeterministicArchiveTarFlags) + @($script:TarForceLocalFlag, '-cf', $ArchivePath, '-C', $BundlePath, '-T', $listFile)
        $result = Invoke-BoundedNativeCommand -FileName $GnuTarExecutablePath -ArgumentList $tarArgs -TimeoutSeconds $TimeoutSeconds -OperationLabel 'build deterministic static archive'
        if ($result.exit_code -ne 0) {
            throw "tar archive creation failed with exit code $($result.exit_code): $($result.output)"
        }
    }
    finally {
        Remove-Item -LiteralPath $listFile -Force -ErrorAction SilentlyContinue
    }
    if (-not (Test-Path -LiteralPath $ArchivePath)) {
        throw "Archive was not created: $ArchivePath"
    }
    return Get-Item -LiteralPath $ArchivePath
}

function Test-StaticArchiveEntrySafety {
    <#
    .SYNOPSIS
    RELEASE-FIX-A3-STATIC-DEPLOY-FIX3: lists a prebuilt static release
    archive's entries (via the resolved GNU tar's `-tvf`) and throws if any
    entry is not a safe plain file at a safe relative path -- absolute
    paths, traversal components, symlinks, hardlinks, devices, and FIFOs
    are all rejected. Deploy runs this against the already-built archive
    before uploading it -- it never rebuilds the archive to validate it.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$ArchivePath,
        [Parameter(Mandatory = $true)][string]$GnuTarExecutablePath,
        [int]$TimeoutSeconds = 60
    )
    $result = Invoke-BoundedNativeCommand -FileName $GnuTarExecutablePath -ArgumentList @($script:TarForceLocalFlag, '-tvf', $ArchivePath) -TimeoutSeconds $TimeoutSeconds -OperationLabel 'list static archive entries'
    if ($result.exit_code -ne 0) {
        throw "Failed to list static archive entries (exit $($result.exit_code)): $($result.output)"
    }
    $badEntries = @()
    foreach ($line in ($result.output -split "`n")) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $trimmed = $line.Trim()
        $typeChar = $trimmed.Substring(0, 1)
        if ($typeChar -ne '-') {
            $badEntries += $trimmed
            continue
        }
        $name = ($trimmed -split '\s+', 6)[-1]
        if ($name.StartsWith('/') -or ($name.Length -ge 2 -and $name[1] -eq ':')) {
            $badEntries += $trimmed
            continue
        }
        if (($name -split '/') -contains '..') {
            $badEntries += $trimmed
        }
    }
    if ($badEntries.Count -gt 0) {
        throw "Static archive contains unsafe entries: $($badEntries -join '; ')"
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

function ConvertFrom-FramedJsonRecord {
    <#
    .SYNOPSIS
    Extracts exactly one base64-encoded JSON record from otherwise diagnostic
    output. Human-readable stdout/stderr is never passed to ConvertFrom-Json.
    #>
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Output,
        [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$Prefix,
        [Parameter(Mandatory = $true)][string]$Context,
        [string[]]$RequiredProperties = @()
    )

    $records = @($Output -split "`r?`n" | Where-Object {
        $_.StartsWith($Prefix, [System.StringComparison]::Ordinal)
    })
    if ($records.Count -ne 1) {
        throw "$Context must contain exactly one framed JSON result; found $($records.Count)."
    }
    $encoded = $records[0].Substring($Prefix.Length)
    if ([string]::IsNullOrWhiteSpace($encoded)) {
        throw "$Context framed JSON result is empty."
    }
    try {
        $bytes = [Convert]::FromBase64String($encoded)
        $utf8 = New-Object System.Text.UTF8Encoding($false, $true)
        $json = $utf8.GetString($bytes)
        $payload = $json | ConvertFrom-Json
    }
    catch {
        throw "$Context framed JSON result is malformed."
    }
    $propertyNames = @($payload.PSObject.Properties.Name)
    foreach ($name in $RequiredProperties) {
        if ($propertyNames -notcontains $name) {
            throw "$Context framed JSON result has an invalid schema: missing $name."
        }
    }
    return $payload
}

function Get-RemoteStandardOutput {
    param([Parameter(Mandatory = $true)]$Result)
    # Invoke-BoundedNativeCommand and Invoke-RemoteShellCommand return
    # ordered dictionaries. Their keys are accessible through the PowerShell
    # adapter (`$Result.stdout`), but they are not listed by
    # PSObject.Properties.Name; that list only contains Count/Keys/Values and
    # other dictionary members. Detect dictionary keys explicitly so stderr
    # diagnostics can never make this helper fall back to merged `output`.
    if ($Result -is [System.Collections.IDictionary] -and $Result.Contains('stdout')) {
        return [string]$Result['stdout']
    }
    if ($null -ne $Result.PSObject.Properties['stdout']) {
        return [string]$Result.stdout
    }
    # Compatibility for existing injected test callbacks. Production remote
    # transports always provide stdout and stderr separately.
    return [string]$Result.output
}

function ConvertTo-FramedJsonRecord {
    param(
        [Parameter(Mandatory = $true)]$InputObject,
        [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$Prefix,
        [int]$Depth = 20
    )
    $json = $InputObject | ConvertTo-Json -Depth $Depth -Compress
    $bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes($json)
    return ($Prefix + [Convert]::ToBase64String($bytes))
}

function ConvertFrom-NestedPowerShellJson {
    param(
        [Parameter(Mandatory = $true)]$RawOutput,
        [Parameter(Mandatory = $true)][string]$Context
    )
    $joined = if ($RawOutput -is [System.Array]) { $RawOutput -join [Environment]::NewLine } else { [string]$RawOutput }
    return ConvertFrom-FramedJsonRecord `
        -Output $joined `
        -Prefix '__GO_ODYSSEY_POWERSHELL_RESULT_V1__:' `
        -Context $Context
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
    <#
    .SYNOPSIS
    RELEASE-FIX-A3-STATIC-DEPLOY-FIX3: the archive fields (ArchiveFileName/
    ArchiveSha256/ArchiveSize/ArchiveEntryCount/GnuTarExecutablePath/
    GnuTarVersion) make the manifest the honest, single source of truth for
    "this exact archive is the one that was reviewed" -- deploy-static-
    release.ps1 verifies the archive it is about to upload against these
    recorded values instead of rebuilding an archive and trusting it blind.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$GitSha,
        [Parameter(Mandatory = $true)][string]$GenerationId,
        [Parameter(Mandatory = $true)][string]$SwVersion,
        [Parameter(Mandatory = $true)][object[]]$Files,
        [Parameter(Mandatory = $true)][string]$CreatedAtUtc,
        [string]$ArchiveFileName,
        [string]$ArchiveSha256,
        [long]$ArchiveSize,
        [int]$ArchiveEntryCount,
        [string]$GnuTarExecutablePath,
        [string]$GnuTarVersion
    )
    return [ordered]@{
        release_git_sha = $GitSha
        static_generation_id = $GenerationId
        static_root = '/opt/go-odyssey-static'
        service_worker_version = $SwVersion
        asset_count = @($Files).Count
        # $Files entries may be ordered hashtables (from New-StaticReleaseBundle,
        # in-memory) or PSCustomObjects (after a JSON round-trip) -- extract
        # .size explicitly via ForEach-Object rather than Measure-Object
        # -Property, which does not bind to hashtable keys.
        total_bytes = (@($Files) | ForEach-Object { $_.size } | Measure-Object -Sum).Sum
        files = @($Files)
        archive_filename = $ArchiveFileName
        archive_sha256 = $ArchiveSha256
        archive_size = $ArchiveSize
        archive_entry_count = $ArchiveEntryCount
        gnu_tar_executable_path = $GnuTarExecutablePath
        gnu_tar_version = $GnuTarVersion
        created_at = $CreatedAtUtc
    }
}

function Enter-RemoteReleaseOperationLock {
    <#
    .SYNOPSIS
    Atomically serializes production deploy and rollback mutations.

    The lock is a short-lived lease directory on the production host. A lease
    makes the gate recoverable after a killed local process while the atomic
    mkdir prevents two release invocations from switching containers together.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$SshAlias,
        [Parameter(Mandatory = $true)][string]$LockPath,
        [Parameter(Mandatory = $true)][string]$OperationId,
        [int]$LeaseSeconds = 3600
    )
    $script = @'
import json
import os
import pathlib
import sys
import time

lock = pathlib.Path(sys.argv[1])
operation_id = sys.argv[2]
lease_seconds = int(sys.argv[3])
now = int(time.time())

def read_owner():
    try:
        return json.loads((lock / "owner.json").read_text(encoding="utf-8"))
    except Exception:
        return {}

try:
    lock.mkdir(mode=0o700)
except FileExistsError:
    owner = read_owner()
    created = int(owner.get("created_epoch", 0) or 0)
    age = max(0, now - created) if created else lease_seconds
    if age < lease_seconds:
        print(json.dumps({"acquired": False, "owner": owner.get("operation_id", "unknown"), "age_seconds": age}))
        raise SystemExit(73)
    stale = lock.with_name(lock.name + ".stale." + str(now))
    try:
        lock.rename(stale)
        lock.mkdir(mode=0o700)
    except Exception:
        print(json.dumps({"acquired": False, "owner": "concurrent-reclaimer", "age_seconds": age}))
        raise SystemExit(73)

payload = {"operation_id": operation_id, "created_epoch": now, "lease_seconds": lease_seconds}
(lock / "owner.json").write_text(json.dumps(payload), encoding="utf-8")
print(json.dumps({"acquired": True, "operation_id": operation_id, "lock_path": str(lock)}))
'@
    $command = "python3 - $(Quote-PosixShellArgument $LockPath) $(Quote-PosixShellArgument $OperationId) $LeaseSeconds"
    $result = Invoke-RemoteShellCommand -SshAlias $SshAlias -Name 'release_operation_lock_enter' -Command $command -StdinText $script
    if ($result.exit_code -ne 0) {
        throw "Another production release operation is active. Lock response: $($result.output)"
    }
    return ((Get-RemoteStandardOutput -Result $result) | ConvertFrom-Json)
}

function Exit-RemoteReleaseOperationLock {
    param(
        [Parameter(Mandatory = $true)][string]$SshAlias,
        [Parameter(Mandatory = $true)][string]$LockPath,
        [Parameter(Mandatory = $true)][string]$OperationId
    )
    $script = @'
import json
import pathlib
import shutil
import sys

lock = pathlib.Path(sys.argv[1])
operation_id = sys.argv[2]
if not lock.exists():
    print(json.dumps({"released": True, "already_absent": True}))
    raise SystemExit(0)
try:
    owner = json.loads((lock / "owner.json").read_text(encoding="utf-8"))
except Exception:
    owner = {}
if owner.get("operation_id") != operation_id:
    print(json.dumps({"released": False, "owner": owner.get("operation_id", "unknown")}))
    raise SystemExit(74)
shutil.rmtree(lock)
print(json.dumps({"released": True, "already_absent": False}))
'@
    $command = "python3 - $(Quote-PosixShellArgument $LockPath) $(Quote-PosixShellArgument $OperationId)"
    $result = Invoke-RemoteShellCommand -SshAlias $SshAlias -Name 'release_operation_lock_exit' -Command $command -StdinText $script
    if ($result.exit_code -ne 0) {
        throw "Production release operation lock could not be released safely: $($result.output)"
    }
    return ((Get-RemoteStandardOutput -Result $result) | ConvertFrom-Json)
}

function Wait-RemoteReleaseOperationLock {
    <# Standalone verification waits for mutation; nested verification supplies the owning ID. #>
    param(
        [Parameter(Mandatory = $true)][string]$SshAlias,
        [Parameter(Mandatory = $true)][string]$LockPath,
        [string]$AllowedOperationId,
        [int]$TimeoutSeconds = 300,
        [int]$PollIntervalSeconds = 2
    )
    $script = @'
import json
import pathlib
import sys

lock = pathlib.Path(sys.argv[1])
if not lock.exists():
    print(json.dumps({"locked": False, "owner": ""}))
else:
    try:
        owner = json.loads((lock / "owner.json").read_text(encoding="utf-8")).get("operation_id", "unknown")
    except Exception:
        owner = "unknown"
    print(json.dumps({"locked": True, "owner": owner}))
'@
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $command = "python3 - $(Quote-PosixShellArgument $LockPath)"
        $result = Invoke-RemoteShellCommand -SshAlias $SshAlias -Name 'release_operation_lock_wait' -Command $command -StdinText $script
        if ($result.exit_code -ne 0) {
            throw "Unable to inspect the production release operation lock: $($result.output)"
        }
        $state = (Get-RemoteStandardOutput -Result $result) | ConvertFrom-Json
        if (-not $state.locked -or (-not [string]::IsNullOrWhiteSpace($AllowedOperationId) -and $state.owner -eq $AllowedOperationId)) {
            return $state
        }
        if ((Get-Date) -ge $deadline) {
            throw "Timed out waiting for production release operation $($state.owner) to finish."
        }
        Start-Sleep -Seconds $PollIntervalSeconds
    } while ($true)
}

Export-ModuleMember -Function @(
    'Assert-ImageRevisionMatches',
    'Assert-OwnerGate',
    'Assert-TrackedTreeClean',
    'Assert-CompleteWorktreeClean',
    'Assert-NoReparsePointPath',
    'Assert-PathInsideCanonicalRoot',
    'Assert-GovernedBuildScriptPath',
    'Assert-GovernedBuildChildIdentity',
    'ConvertFrom-NestedPowerShellJson',
    'ConvertFrom-FramedJsonRecord',
    'ConvertTo-FramedJsonRecord',
    'Get-RemoteStandardOutput',
    'ConvertTo-Utf8NoBomLfBytes',
    'Ensure-Directory',
    'Enter-RemoteReleaseOperationLock',
    'Exit-RemoteReleaseOperationLock',
    'Get-ImagePlatform',
    'Invoke-ProcessWithUtf8NoBomStdin',
    'Invoke-RemoteShellCommand',
    'Get-CanonicalAppHealthcheckDefinition',
    'Assert-ProtectedHostEnvCredentialAndTcpAuthentication',
    'Get-BooleanFlag',
    'Get-CurrentGitSha',
    'Get-ImageLabels',
    'Get-OriginMasterSha',
    'Get-SafeFirstOutputLine',
    'Get-GitCommonDirectory',
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
    'Assert-DetachedWorktreeIdentity',
    'Assert-GeneratedDetachedWorktreeIdentity',
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
    'Get-BatchVerificationTimeoutSeconds',
    'Get-StaticPublicVerificationDeadlineSeconds',
    'Get-ArchiveTransferTimeoutSeconds',
    'New-DeterministicStaticArchive',
    'Test-GnuTarExecutableCapability',
    'Wait-RemoteReleaseOperationLock',
    'Resolve-GnuTarExecutable',
    'Test-StaticArchiveEntrySafety'
)
