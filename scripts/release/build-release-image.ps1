#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ExpectedGitSha,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

function Fail($msg) {
    throw $msg
}

$repoRoot = Get-RepoRoot
$expectedGitCommonDirectory = Get-GitCommonDirectory -WorkingDirectory $repoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
if (-not $ExpectedGitSha) {
    $ExpectedGitSha = Get-CurrentGitSha
}
else {
    $ExpectedGitSha = Get-SafeFirstOutputLine (Invoke-Git -Arguments @('rev-parse', $ExpectedGitSha) -WorkingDirectory $repoRoot)
}

Assert-TrackedTreeClean -WorkingDirectory $repoRoot

$worktree = $null
try {
    $worktree = New-DetachedWorktree -GitSha $ExpectedGitSha -Prefix 'go-odyssey-build'
    Push-Location $worktree
    try {
        python -X utf8 -m pytest -q tests/deployment/ | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Fail "pytest failed with exit code $LASTEXITCODE."
        }

        python shadow_judging.py --selftest | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Fail "shadow_judging.py --selftest failed with exit code $LASTEXITCODE."
        }

        python -m py_compile app.py db.py scheduler.py shadow_judging.py shadow_dashboard.py shadow_event_storage.py | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Fail "py_compile failed with exit code $LASTEXITCODE."
        }

        $imageTag = Get-ReleaseImageTag -GitSha $ExpectedGitSha
        if ($DryRun) {
            [ordered]@{
                dry_run = $true
                git_sha = $ExpectedGitSha
                image_tag = $imageTag
                release_layout = $layout
                build_pipeline = @(
                    'deployment tests',
                    'shadow self-test',
                    'py_compile',
                    'immutable image build'
                )
            } | ConvertTo-Json -Depth 8 | Write-Output
            return
        }

        $env:APP_BUILD_DATE_OVERRIDE = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        $worktree = Assert-GeneratedDetachedWorktreeIdentity -Path $worktree -ExpectedGitSha $ExpectedGitSha
        $childBuildScript = Join-Path $worktree 'scripts\build-production-image.ps1'
        $childBuildScript = Assert-GovernedBuildScriptPath -Path $childBuildScript -CanonicalWorktreeRoot $worktree
        # This is the final parent-side identity check immediately before
        # Process.Start(). The child repeats the same contract before any
        # Docker/build action; no cross-process filesystem atomicity is claimed.
        $worktree = Assert-GeneratedDetachedWorktreeIdentity -Path $worktree -ExpectedGitSha $ExpectedGitSha
        $buildResult = Invoke-BoundedNativeCommand `
            -FileName 'powershell.exe' `
            -ArgumentList @(
                '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                $childBuildScript,
                '-GitSha', $ExpectedGitSha,
                '-ExpectedCanonicalWorktreeRoot', $worktree,
                '-ExpectedExactGitSha', $ExpectedGitSha,
                '-ExpectedGitCommonDirectory', $expectedGitCommonDirectory,
                '-ExpectedHeadState', 'detached'
            ) `
            -WorkingDirectory $worktree `
            -RequireWorkingDirectory `
            -TimeoutSeconds 3900 `
            -OperationLabel 'canonical production image build script'
        Write-Host $buildResult.output
        if ($buildResult.exit_code -ne 0) {
            Fail "build-production-image.ps1 failed with exit code $($buildResult.exit_code)."
        }

        $labels = Assert-ImageRevisionMatches -ImageTag $imageTag -ExpectedGitSha $ExpectedGitSha
        [ordered]@{
            image_tag = $imageTag
            image_id = (Get-SafeFirstOutputLine (& docker image inspect $imageTag --format '{{.Id}}'))
            revision = $labels.'org.opencontainers.image.revision'
            source = $labels.'org.opencontainers.image.source'
            sgf_engine_source_commit = $labels.'com.godokoro.sgf-engine.source-commit'
            build_date = $labels.'org.opencontainers.image.created'
            release_layout = $layout
        } | ConvertTo-Json -Depth 8 | Write-Output
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($worktree) {
        Remove-DetachedWorktree -Path $worktree
    }
}
