#Requires -Version 5.1
[CmdletBinding()]
param(
    # ExpectedGitSha is retained for the historical single-source invocation.
    [string]$ExpectedGitSha,
    [string]$GateSourceSha,
    [string]$ProductSourceSha,
    # External governance host must supply exact authority, never candidate defaults.
    [string]$GovernanceExpectedGitCommonDirectory,
    [string]$GovernanceGateSourceSha,
    [string]$GovernanceProductSourceSha,
    # Untrusted inputs: only a host-pinned cryptographic verifier can accept them.
    [string]$GovernanceDecision,
    [string]$GovernanceChallenge,
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

foreach ($authority in @($GovernanceExpectedGitCommonDirectory, $GovernanceGateSourceSha, $GovernanceProductSourceSha)) {
    if ([string]::IsNullOrWhiteSpace($authority)) {
        Fail 'EXTERNAL_GOVERNANCE_AUTHORITY_REQUIRED: common directory and exact Gate/Product commits must be supplied by a trusted external host.'
    }
}
if ($GovernanceGateSourceSha -cnotmatch '^[0-9a-f]{40}$' -or $GovernanceProductSourceSha -cnotmatch '^[0-9a-f]{40}$' -or
    -not [System.IO.Path]::IsPathRooted($GovernanceExpectedGitCommonDirectory)) {
    Fail 'EXTERNAL_GOVERNANCE_AUTHORITY_INVALID: absolute common directory and full lowercase commits required.'
}
# This also gates DryRun, before any detached worktree or test/build side effect.
# There is deliberately no policy/key/executable override: this candidate cannot
# nominate its own issuer. The bridge refuses until independently provisioned.
if (-not $GovernanceDecision -or -not $GovernanceChallenge) {
    Fail 'EXTERNAL_GOVERNANCE_ATTESTATION_REQUIRED: signed BUILD_APP decision and invocation challenge are missing.'
}
# Never execute a candidate script or PATH-resolved interpreter as the authority.
# Installation/hash must be authenticated out of band by governance administrators.
# No such installation receipt was supplied. An empty pin MUST remain closed.
$governanceVerifier = 'C:\Program Files\Go Odyssey Governance\verify-governance.exe'
$governanceVerifierSha256 = ''
if ($governanceVerifierSha256 -cnotmatch '^[0-9a-f]{64}$') {
    Fail 'EXTERNAL_GOVERNANCE_ATTESTATION_REQUIRED: EXTERNAL_GOVERNANCE_TRUST_ANCHOR_UNPROVISIONED; authenticated host verifier installation/hash and issuer pins are missing.'
}
if (-not (Test-Path -LiteralPath $governanceVerifier -PathType Leaf) -or
    (Get-FileHash -LiteralPath $governanceVerifier -Algorithm SHA256).Hash.ToLowerInvariant() -cne $governanceVerifierSha256) {
    Fail 'EXTERNAL_GOVERNANCE_ATTESTATION_REQUIRED: protected host verifier is missing or its authenticated bytes differ.'
}
$governanceOutput = @(& $governanceVerifier `
    --decision $GovernanceDecision `
    --challenge $GovernanceChallenge `
    --gate-sha $GovernanceGateSourceSha `
    --product-sha $GovernanceProductSourceSha `
    --expected-common-dir $GovernanceExpectedGitCommonDirectory 2>&1)
$governanceExitCode = $LASTEXITCODE
$governanceOutput | Out-Host
if ($governanceExitCode -ne 0) {
    Fail "EXTERNAL_GOVERNANCE_ATTESTATION_REQUIRED: independent verification rejected: $($governanceOutput -join [Environment]::NewLine)"
}
try {
    $governanceJson = $governanceOutput -join [Environment]::NewLine
    # Windows PowerShell unwraps one-element JSON arrays; require an object.
    if (-not $governanceJson.TrimStart().StartsWith('{')) {
        throw 'Expected one JSON object'
    }
    $governanceReport = $governanceJson | ConvertFrom-Json -ErrorAction Stop
} catch {
    Fail 'EXTERNAL_GOVERNANCE_REPORT_INVALID: protected verifier did not return one JSON report.'
}
if ($governanceReport.status -cne 'BUILD_APP_AUTHORIZED' -or
    $governanceReport.build_authorized -isnot [bool] -or $governanceReport.build_authorized -ne $true -or
    $governanceReport.evidence_admitted -isnot [bool] -or $governanceReport.evidence_admitted -ne $false -or
    $governanceReport.release_authorized -isnot [bool] -or $governanceReport.release_authorized -ne $false -or
    $governanceReport.gate_sha -cne $GovernanceGateSourceSha -or
    $governanceReport.product_sha -cne $GovernanceProductSourceSha -or
    $governanceReport.git_common_dir -cne $GovernanceExpectedGitCommonDirectory -or
    $governanceReport.challenge -cne $GovernanceChallenge -or
    $governanceReport.decision_sha256 -cnotmatch '^[0-9a-f]{64}$') {
    Fail 'EXTERNAL_GOVERNANCE_REPORT_INVALID: affirmative authorization with exact invocation bindings is required.'
}
$expectedGitCommonDirectory = $GovernanceExpectedGitCommonDirectory
$gateWorktree = Get-RepoRoot
if ($ExpectedGitSha -and ($GateSourceSha -or $ProductSourceSha)) {
    Fail 'ExpectedGitSha cannot be combined with the separated GateSourceSha/ProductSourceSha inputs.'
}
if (($GateSourceSha -and -not $ProductSourceSha) -or ($ProductSourceSha -and -not $GateSourceSha)) {
    Fail 'GateSourceSha and ProductSourceSha must be supplied together.'
}
if (-not $GateSourceSha -and -not $ProductSourceSha) {
    $GateSourceSha = $GovernanceGateSourceSha
    $ProductSourceSha = $GovernanceProductSourceSha
}
if ($GateSourceSha -cne $GovernanceGateSourceSha -or $ProductSourceSha -cne $GovernanceProductSourceSha) {
    Fail 'Candidate commits do not match externally supplied governance authority.'
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
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
$sourcePlan = Assert-ReleaseSourceSeparation `
    -GateSourceSha $gateSha `
    -ProductSourceSha $productSha `
    -GateWorkingDirectory $gateWorktree
$buildAppBaselinePath = Resolve-RepoPath 'deploy\build-app-known-failure-baseline.json'
$buildAppEvaluatorPath = Join-Path $gateWorktree 'scripts\release\evaluate_build_app_test_baseline.py'
# G009 Zone4 Owner option B: control-plane tools that bind the run to the exact Gate/Product candidate and let the
# evaluator recognise (never pass) exactly two Owner-approved Frozen contract conflicts. The policy accepts nothing
# until an authenticated external reviewer attests the receipt and its bytes.
# Governance authorization does not admit test evidence: policy and execution
# identity remain independently blocked pending their authenticated hosts.
$ownerConflictPolicyPath = Join-Path $gateWorktree 'scripts\release\zone4_owner_b_contract_conflict_policy.json'
$candidateBindingToolPath = Join-Path $gateWorktree 'scripts\release\verify_release_candidate_binding.py'
$sixRouteToolPath = Join-Path $gateWorktree 'scripts\release\verify_e10_six_route_contract.py'
$identityPluginDirectory = Join-Path $gateWorktree 'scripts\release'

$productWorktree = $null
$pytestReportPath = $null
$previousEnvironment = @{}
$environmentNames = @(
    'GO_ODYSSEY_RELEASE_GATE_SOURCE_SHA',
    'GO_ODYSSEY_RELEASE_PRODUCT_SOURCE_SHA',
    'GO_ODYSSEY_RELEASE_GATE_ROOT',
    'GO_ODYSSEY_RELEASE_PRODUCT_ROOT',
    'PYTHONPYCACHEPREFIX',
    'PYTHONDONTWRITEBYTECODE',
    'PYTHONPATH',
    'G009_RELEASE_IDENTITY_RECORD',
    'G009_RELEASE_IDENTITY_NONCE'
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
        if (-not (Test-Path -LiteralPath $buildAppBaselinePath -PathType Leaf)) {
            Fail "Tracked BUILD_APP failure baseline is missing: $buildAppBaselinePath"
        }
        if (-not (Test-Path -LiteralPath $buildAppEvaluatorPath -PathType Leaf)) {
            Fail "Tracked BUILD_APP failure baseline evaluator is missing: $buildAppEvaluatorPath"
        }
        foreach ($requiredGateTool in @($ownerConflictPolicyPath, $candidateBindingToolPath, $sixRouteToolPath, (Join-Path $identityPluginDirectory 'g009_release_identity_plugin.py'))) {
            if (-not (Test-Path -LiteralPath $requiredGateTool -PathType Leaf)) {
                Fail "Tracked BUILD_APP candidate-binding control-plane file is missing: $requiredGateTool"
            }
        }
        $runToken = [guid]::NewGuid().ToString('N')
        $runTempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("go-odyssey-build-app-{0}" -f $runToken)
        New-Item -ItemType Directory -Path $runTempRoot | Out-Null
        $pytestReportPath = Join-Path $runTempRoot 'build-app-junit.xml'
        $bindingReportPath = Join-Path $runTempRoot 'candidate-binding.json'
        $sixRouteReportPath = Join-Path $runTempRoot 'six-route-product.json'
        $identityRecordPath = Join-Path $runTempRoot 'identity-record.json'
        $identityReportPath = Join-Path $runTempRoot 'identity-binding.json'
        # Fresh bytecode cache outside both checkouts: a stale __pycache__ inside a candidate can never be imported.
        $env:PYTHONPYCACHEPREFIX = Join-Path $runTempRoot 'pycache'
        $env:PYTHONDONTWRITEBYTECODE = '1'
        try {
            # 1. Gate/Product identity, cleanliness, ancestry, control-plane-only difference, runtime byte identity.
            $bindingOutput = @(& python $candidateBindingToolPath check `
                --gate-root $gateWorktree `
                --product-root $productWorktree `
                --gate-sha $gateSha `
                --product-sha $productSha `
                --expected-common-dir $expectedGitCommonDirectory `
                --out $bindingReportPath 2>&1)
            $bindingExitCode = $LASTEXITCODE
            $bindingOutput | Out-Host
            if ($bindingExitCode -ne 0) {
                Fail "BUILD_APP Gate/Product candidate binding failed closed: $($bindingOutput -join [Environment]::NewLine)"
            }

            # 2. Exact six-route E10 contract on the PRODUCT subject (the build context), fresh, never a stored receipt.
            $sixRouteOutput = @(& python $sixRouteToolPath `
                --root $productWorktree `
                --require-clean `
                --expected-head $productSha `
                --out $sixRouteReportPath 2>&1)
            $sixRouteExitCode = $LASTEXITCODE
            $sixRouteOutput | Out-Host
            if ($sixRouteExitCode -ne 0) {
                Fail "BUILD_APP exact six-route E10 contract failed closed on the Product checkout: $($sixRouteOutput -join [Environment]::NewLine)"
            }

            # 3. Deployment suite from the Gate tree, recording which app/Frozen modules were actually imported.
            $env:G009_RELEASE_IDENTITY_RECORD = $identityRecordPath
            $env:G009_RELEASE_IDENTITY_NONCE = $runToken
            $env:PYTHONPATH = $identityPluginDirectory
            Push-Location $gateWorktree
            try {
                $pytestOutput = @(& python -X utf8 -m pytest -q tests/deployment/ -p g009_release_identity_plugin --junitxml $pytestReportPath 2>&1)
                $pytestExitCode = $LASTEXITCODE
                $pytestOutput | Out-Host
            }
            finally {
                Pop-Location
            }

            # 4. Recheck parent-bound sources and diagnostic collection/JUnit.
            # Candidate-controlled plugin/nonce data cannot authenticate execution;
            # identity remains blocked pending a separately trusted runner host.
            $identityOutput = @(& python $candidateBindingToolPath identity `
                --record $identityRecordPath `
                --nonce $runToken `
                --gate-root $gateWorktree `
                --product-root $productWorktree `
                --gate-sha $gateSha `
                --product-sha $productSha `
                --expected-common-dir $expectedGitCommonDirectory `
                --junitxml $pytestReportPath `
                --out $identityReportPath 2>&1)
            $identityExitCode = $LASTEXITCODE
            $identityOutput | Out-Host
            if ($identityExitCode -ne 0) {
                Fail "BUILD_APP imported-module identity failed closed: $($identityOutput -join [Environment]::NewLine)"
            }

            # 5. Evaluator: three-node baseline unchanged + independently reviewed Owner conflict policy.
            $baselineEvaluation = @(& python $buildAppEvaluatorPath `
                --junitxml $pytestReportPath `
                --baseline $buildAppBaselinePath `
                --repo-root $gateWorktree `
                --gate-source-sha $gateSha `
                --pytest-exit-code $pytestExitCode `
                --owner-conflict-policy $ownerConflictPolicyPath 2>&1)
            $baselineEvaluationExitCode = $LASTEXITCODE
            $baselineEvaluation | Out-Host
            if ($baselineEvaluationExitCode -ne 0) {
                Fail "BUILD_APP deployment test gate failed closed: $($baselineEvaluation -join [Environment]::NewLine)"
            }
        }
        finally {
            if ($runTempRoot -and (Test-Path -LiteralPath $runTempRoot)) {
                Remove-Item -LiteralPath $runTempRoot -Recurse -Force -ErrorAction SilentlyContinue
            }
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
