Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
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
    return $GitSha.Substring(0, 8)
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

Export-ModuleMember -Function @(
    'Assert-ImageRevisionMatches',
    'Assert-OwnerGate',
    'Assert-TrackedTreeClean',
    'Ensure-Directory',
    'Get-BooleanFlag',
    'Get-CurrentGitSha',
    'Get-ImageLabels',
    'Get-OriginMasterSha',
    'Get-ReleaseArtifactBaseName',
    'Get-ReleaseImageTag',
    'Get-ReleaseLayout',
    'Get-RepoRoot',
    'Invoke-Git',
    'New-DetachedWorktree',
    'New-ReleaseManifestObject',
    'Read-JsonFile',
    'Remove-DetachedWorktree',
    'Resolve-RepoPath',
    'Test-TrackedTreeClean',
    'Write-JsonFile'
)
