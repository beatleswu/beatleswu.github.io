#Requires -Version 5.1
[CmdletBinding()]
param(
    # ExpectedGitSha is retained for the historical single-source invocation.
    [string]$ExpectedGitSha,
    [string]$GateSourceSha,
    [string]$ProductSourceSha,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

function Fail($msg) {
    throw $msg
}

function Resolve-ExactCommit([string]$WorkingDirectory, [string]$Value, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        Fail "$Label is required."
    }
    return Get-SafeFirstOutputLine (Invoke-Git -Arguments @('rev-parse', "$Value^{commit}") -WorkingDirectory $WorkingDirectory)
}

$gateWorktree = Get-RepoRoot
if ($ExpectedGitSha -and ($GateSourceSha -or $ProductSourceSha)) {
    Fail 'ExpectedGitSha cannot be combined with the separated GateSourceSha/ProductSourceSha inputs.'
}
if (($GateSourceSha -and -not $ProductSourceSha) -or ($ProductSourceSha -and -not $GateSourceSha)) {
    Fail 'GateSourceSha and ProductSourceSha must be supplied together.'
}
if (-not $GateSourceSha -and -not $ProductSourceSha) {
    $GateSourceSha = if ($ExpectedGitSha) { $ExpectedGitSha } else { Get-CurrentGitSha }
    $ProductSourceSha = $GateSourceSha
}

$gateSha = Resolve-ExactCommit -WorkingDirectory $gateWorktree -Value $GateSourceSha -Label 'GateSourceSha'
$productSha = Resolve-ExactCommit -WorkingDirectory $gateWorktree -Value $ProductSourceSha -Label 'ProductSourceSha'
$currentGateSha = Get-CurrentGitSha
if ($currentGateSha -ne $gateSha) {
    Fail "Gate worktree HEAD '$currentGateSha' does not equal GateSourceSha '$gateSha'."
}

# The Gate checkout is the control-plane runner. It must be clean, but it is
# deliberately not used as the Docker/product build context in separated mode.
Assert-TrackedTreeClean -WorkingDirectory $gateWorktree
Assert-CompleteWorktreeClean -WorkingDirectory $gateWorktree
$expectedGitCommonDirectory = Get-GitCommonDirectory -WorkingDirectory $gateWorktree
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
$sourcePlan = Assert-ReleaseSourceSeparation `
    -GateSourceSha $gateSha `
    -ProductSourceSha $productSha `
    -GateWorkingDirectory $gateWorktree

$productWorktree = $null
$previousEnvironment = @{}
$environmentNames = @(
    'GO_ODYSSEY_RELEASE_GATE_SOURCE_SHA',
    'GO_ODYSSEY_RELEASE_PRODUCT_SOURCE_SHA',
    'GO_ODYSSEY_RELEASE_GATE_ROOT',
    'GO_ODYSSEY_RELEASE_PRODUCT_ROOT'
)
foreach ($name in $environmentNames) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

try {
    $productWorktree = New-DetachedWorktree -GitSha $productSha -Prefix 'go-odyssey-product'
    $productWorktree = Assert-GeneratedDetachedWorktreeIdentity -Path $productWorktree -ExpectedGitSha $productSha
    Assert-CompleteWorktreeClean -WorkingDirectory $productWorktree
    $productHead = Get-SafeFirstOutputLine (Invoke-Git -Arguments @('rev-parse', 'HEAD') -WorkingDirectory $productWorktree)
    if ($productHead -ne $productSha) {
        Fail "Product worktree HEAD '$productHead' does not equal ProductSourceSha '$productSha'."
    }

    $env:GO_ODYSSEY_RELEASE_GATE_SOURCE_SHA = $gateSha
    $env:GO_ODYSSEY_RELEASE_PRODUCT_SOURCE_SHA = $productSha
    $env:GO_ODYSSEY_RELEASE_GATE_ROOT = $gateWorktree
    $env:GO_ODYSSEY_RELEASE_PRODUCT_ROOT = $productWorktree

    if (-not $DryRun) {
        # Tests are implemented and loaded from the Gate/control-plane tree.
        # ProductRoot is explicit so a test may inspect the separate subject.
        Push-Location $gateWorktree
        try {
            python -X utf8 -m pytest -q tests/deployment/ | Out-Host
            if ($LASTEXITCODE -ne 0) {
                Fail "pytest failed with exit code $LASTEXITCODE."
            }
        }
        finally {
            Pop-Location
        }

        # Product runtime self-test and compile checks operate on the exact
        # Product worktree, never on the Gate checkout.
        Push-Location $productWorktree
        try {
            python shadow_judging.py --selftest | Out-Host
            if ($LASTEXITCODE -ne 0) {
                Fail "shadow_judging.py --selftest failed with exit code $LASTEXITCODE."
            }

            python -m py_compile app.py db.py scheduler.py shadow_judging.py shadow_dashboard.py shadow_event_storage.py | Out-Host
            if ($LASTEXITCODE -ne 0) {
                Fail "py_compile failed with exit code $LASTEXITCODE."
            }
        }
        finally {
            Pop-Location
        }
    }

    $imageTag = Get-ReleaseImageTag -GitSha $productSha
    if ($DryRun) {
        [ordered]@{
            dry_run = $true
            source_separation_check = 'PASS'
            gate_source_sha = $gateSha
            product_source_sha = $productSha
            gate_worktree = $gateWorktree
            product_worktree = $productWorktree
            product_worktree_head = $productHead
            product_worktree_clean = $true
            product_runtime_diff_from_product = 0
            build_context = 'PRODUCT_WORKTREE'
            test_source = 'GATE_WORKTREE'
            oci_revision_would_be = $productSha
            static_source_would_be = $productSha
            image_tag = $imageTag
            release_layout = $layout
            build_not_executed = $true
            gate_tests_would_run = $true
        } | ConvertTo-Json -Depth 8 | Write-Output
        return
    }

    $env:APP_BUILD_DATE_OVERRIDE = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $childBuildScript = Join-Path $gateWorktree 'scripts\build-production-image.ps1'
    $childBuildScript = Assert-GovernedBuildScriptPath -Path $childBuildScript -CanonicalWorktreeRoot $gateWorktree
    # Final parent-side Gate and Product identity checks immediately precede
    # Process.Start(). The child repeats both boundaries before Docker/build.
    Assert-CompleteWorktreeClean -WorkingDirectory $gateWorktree
    $productWorktree = Assert-GeneratedDetachedWorktreeIdentity -Path $productWorktree -ExpectedGitSha $productSha
    $buildResult = Invoke-BoundedNativeCommand `
        -FileName 'powershell.exe' `
        -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            $childBuildScript,
            '-GitSha', $productSha,
            '-ExpectedCanonicalWorktreeRoot', $gateWorktree,
            '-ExpectedExactGitSha', $gateSha,
            '-ExpectedGitCommonDirectory', $expectedGitCommonDirectory,
            '-ExpectedHeadState', 'branch',
            '-ProductSourceRoot', $productWorktree,
            '-ExpectedProductGitSha', $productSha
        ) `
        -WorkingDirectory $gateWorktree `
        -RequireWorkingDirectory `
        -TimeoutSeconds 3900 `
        -OperationLabel 'canonical production image build script'
    Write-Host $buildResult.output
    if ($buildResult.exit_code -ne 0) {
        Fail "build-production-image.ps1 failed with exit code $($buildResult.exit_code)."
    }

    $labels = Assert-ImageRevisionMatches -ImageTag $imageTag -ExpectedGitSha $productSha
    [ordered]@{
        image_tag = $imageTag
        image_id = (Get-SafeFirstOutputLine (& docker image inspect $imageTag --format '{{.Id}}'))
        revision = $labels.'org.opencontainers.image.revision'
        source = $labels.'org.opencontainers.image.source'
        sgf_engine_source_commit = $labels.'com.godokoro.sgf-engine.source-commit'
        build_date = $labels.'org.opencontainers.image.created'
        gate_source_sha = $gateSha
        product_source_sha = $productSha
        release_layout = $layout
    } | ConvertTo-Json -Depth 8 | Write-Output
}
finally {
    foreach ($name in $environmentNames) {
        $previous = $previousEnvironment[$name]
        if ($null -eq $previous) {
            Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        }
        else {
            Set-Item -LiteralPath "Env:$name" -Value $previous
        }
    }
    if ($productWorktree) {
        Remove-DetachedWorktree -Path $productWorktree
    }
}
