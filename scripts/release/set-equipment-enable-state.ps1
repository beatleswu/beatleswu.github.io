#Requires -Version 5.1
<#
.SYNOPSIS
EQ-F R3: the sole, isolated, Owner-gated control surface for
EQUIPMENT_CANONICAL_LOADOUT_ENABLED.

.DESCRIPTION
This script changes exactly one product flag, for exactly one runtime
consumer (the `app` compose service -- scheduler.py never reads either
CANONICAL_COIN_SHOP_PURCHASE_ENABLED or EQUIPMENT_CANONICAL_LOADOUT_ENABLED,
so it is never targeted here). It never touches
CANONICAL_COIN_SHOP_PURCHASE_ENABLED, payment/Turnstile/DB configuration, or
any other flag.

-State Enable layers docker-compose.release.equipment-enable.override.yml on
top of the tracked docker-compose.release.product-flags.yml baseline and
requires -OwnerGate GO_EQUIPMENT_ENABLE.

-State Disable (Equipment-only rollback) simply omits that override, so the
baseline file's EQUIPMENT_CANONICAL_LOADOUT_ENABLED=false applies again, and
requires -OwnerGate GO_ROLLBACK -- the repository's existing, established
rollback gate (see rollback-release.ps1).

Without -Execute this is a pure, read-only dry run: it resolves the release
layout and prints the exact plan (files, owner gate, target service, and the
literal docker compose command it would run) as JSON, and returns before
touching SSH, Docker, or any host. Exactly like every other canonical
release script's dry-run mode, per
docs/architecture/ADR-0001-canonical-repository-and-deployment.md and
docs/deployment/production_deployment_governance.md.

Never prints a full environment dump or any secret; effective-value
verification after -Execute is limited to the two named flags.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('Enable', 'Disable')][string]$State,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$Execute,
    [string]$OwnerGate,
    [int]$SshTimeoutSeconds = 30,
    [int]$HealthTimeoutSeconds = 20
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

function Join-RemotePath {
    param(
        [Parameter(Mandatory = $true)][string]$Left,
        [Parameter(Mandatory = $true)][string]$Right
    )
    return ($Left.TrimEnd('/') + '/' + $Right.TrimStart('/'))
}

$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)

$requiredOwnerGate = if ($State -eq 'Enable') { 'GO_EQUIPMENT_ENABLE' } else { 'GO_ROLLBACK' }
$flagName = 'EQUIPMENT_CANONICAL_LOADOUT_ENABLED'
$expectedShopValue = 'true'
$expectedEquipmentValue = if ($State -eq 'Enable') { 'true' } else { 'false' }

# These two tracked files are the entire product-flag authority. This script
# never writes to, edits, or depends on the historical untracked
# /opt/go-odyssey/docker-compose.shop-reopen.override.yml -- see
# docs/deployment/EQ_F_POST_MERGE_RELEASE_RUNBOOK_PREFLIGHT.md.
$productFlagsPath = Resolve-RepoPath 'docker-compose.release.product-flags.yml'
$equipmentEnableOverridePath = Resolve-RepoPath 'docker-compose.release.equipment-enable.override.yml'
if (-not (Test-Path -LiteralPath $productFlagsPath)) {
    throw "Tracked product-flags file is missing: $productFlagsPath"
}
if ($State -eq 'Enable' -and -not (Test-Path -LiteralPath $equipmentEnableOverridePath)) {
    throw "Tracked equipment-enable override is missing: $equipmentEnableOverridePath"
}

$remoteComposePath = Join-RemotePath $layout.compose_directory 'docker-compose.release.yml'
$remoteHealthcheckOverridePath = Join-RemotePath $layout.compose_directory 'docker-compose.release.healthcheck.override.yml'
$remoteProductFlagsPath = Join-RemotePath $layout.compose_directory 'docker-compose.release.product-flags.yml'
$remoteEquipmentEnableOverridePath = Join-RemotePath $layout.compose_directory 'docker-compose.release.equipment-enable.override.yml'

# Order matters: the baseline file is always present; the enable override
# (when used) is always LAST, so its single key wins the per-key merge
# without touching CANONICAL_COIN_SHOP_PURCHASE_ENABLED, which it never
# mentions.
$composeFileArgs = @(
    '-f', 'docker-compose.release.yml',
    '-f', $remoteHealthcheckOverridePath,
    '-f', $remoteProductFlagsPath
)
if ($State -eq 'Enable') {
    $composeFileArgs += @('-f', $remoteEquipmentEnableOverridePath)
}
$quotedComposeFileArgs = @()
for ($i = 0; $i -lt $composeFileArgs.Count; $i++) {
    if ($composeFileArgs[$i] -eq '-f') {
        $quotedComposeFileArgs += '-f'
    } else {
        $quotedComposeFileArgs += Quote-PosixShellArgument $composeFileArgs[$i]
    }
}
$composeFileArgText = [string]::Join(' ', $quotedComposeFileArgs)
$composeProjectArg = "-p $(Quote-PosixShellArgument $layout.compose_project)"
$composeEnvFileArg = "--env-file $(Quote-PosixShellArgument $layout.production_env_path)"
$targetService = $layout.app_service_name
$recreateCommand = "cd $(Quote-PosixShellArgument $layout.compose_directory) && docker compose $composeProjectArg $composeEnvFileArg $composeFileArgText up -d --no-build --no-deps --force-recreate $targetService"

if (-not $Execute) {
    $secondPlanStep = if ($State -eq 'Enable') {
        'upload tracked equipment-enable override'
    } else {
        'omit equipment-enable override so the baseline false applies'
    }
    $planSteps = @(
        'validate Owner gate',
        'upload tracked product-flags file (idempotent; always uploaded, never assumed present)',
        $secondPlanStep,
        'force-recreate the app service only (scheduler is not a consumer of either flag)',
        'read back only CANONICAL_COIN_SHOP_PURCHASE_ENABLED and EQUIPMENT_CANONICAL_LOADOUT_ENABLED from the app container',
        'bounded health check against the release layout health_url'
    )
    [ordered]@{
        dry_run              = $true
        execute_requested    = $false
        state                = $State
        required_owner_gate  = $requiredOwnerGate
        target_service       = $targetService
        shop_flag_untouched  = 'CANONICAL_COIN_SHOP_PURCHASE_ENABLED'
        expected_shop_value_after       = $expectedShopValue
        expected_equipment_value_after  = $expectedEquipmentValue
        compose_files        = $composeFileArgs
        recreate_command     = $recreateCommand
        plan                 = $planSteps
        result               = 'DRY_RUN_COMPLETE'
    } | ConvertTo-Json -Depth 6 | Write-Output
    return
}

Assert-OwnerGate -Provided $OwnerGate -Expected $requiredOwnerGate

# ---------------------------------------------------------------------------
# Everything below this line touches the network/host and is intentionally
# never invoked by an automated review -- only a human-run -Execute with the
# correct Owner gate reaches it. It reuses the same bounded SSH primitive
# every other governed release script uses; it does not invent a new
# ad hoc ssh/sed/compose-editing mechanism.
# ---------------------------------------------------------------------------

Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -Command "mkdir -p $(Quote-PosixShellArgument $layout.compose_directory)" -TimeoutSeconds $SshTimeoutSeconds -OperationLabel 'ensure_compose_directory' | Out-Null

Invoke-BoundedScpUpload -SshAlias $layout.ssh_alias -LocalPath $productFlagsPath -RemotePath $remoteProductFlagsPath -TimeoutSeconds $SshTimeoutSeconds -OperationLabel 'upload_product_flags' | Out-Null
if ($State -eq 'Enable') {
    Invoke-BoundedScpUpload -SshAlias $layout.ssh_alias -LocalPath $equipmentEnableOverridePath -RemotePath $remoteEquipmentEnableOverridePath -TimeoutSeconds $SshTimeoutSeconds -OperationLabel 'upload_equipment_enable_override' | Out-Null
}

$recreateResult = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -Command $recreateCommand -TimeoutSeconds ($SshTimeoutSeconds * 4) -OperationLabel 'force_recreate_app'
if ($recreateResult.exit_code -ne 0) {
    throw "Governed app recreate failed closed; sanitized remote output withheld."
}

# Read back only the two named flags -- never a full `env` dump, never any
# other variable. $printfScript is a single-quoted PowerShell literal so
# PowerShell performs no interpolation of its own; the two $VAR references
# stay literal text for the remote `sh -c` to expand inside the container.
$printfScript = 'printf "SHOP=%s\nEQUIPMENT=%s\n" "$CANONICAL_COIN_SHOP_PURCHASE_ENABLED" "$EQUIPMENT_CANONICAL_LOADOUT_ENABLED"'
$verifyCommand = "docker exec $(Quote-PosixShellArgument $targetService) sh -c $(Quote-PosixShellArgument $printfScript)"
$verifyResult = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -Command $verifyCommand -TimeoutSeconds $SshTimeoutSeconds -OperationLabel 'verify_effective_flags'
if ($verifyResult.exit_code -ne 0) {
    throw "Post-recreate flag verification failed closed; sanitized remote output withheld."
}
$observedShop = $null
$observedEquipment = $null
foreach ($line in ([regex]::Split($verifyResult.stdout, '\r?\n'))) {
    if ($line -like 'SHOP=*') { $observedShop = $line.Substring(5).Trim() }
    if ($line -like 'EQUIPMENT=*') { $observedEquipment = $line.Substring(10).Trim() }
}
if ($observedShop -ne $expectedShopValue) {
    throw "Post-recreate verification failed: CANONICAL_COIN_SHOP_PURCHASE_ENABLED observed '$observedShop', expected '$expectedShopValue'."
}
if ($observedEquipment -ne $expectedEquipmentValue) {
    throw "Post-recreate verification failed: EQUIPMENT_CANONICAL_LOADOUT_ENABLED observed '$observedEquipment', expected '$expectedEquipmentValue'."
}

$healthResult = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -Command "curl -sf --max-time 10 $(Quote-PosixShellArgument $layout.health_url)" -TimeoutSeconds $HealthTimeoutSeconds -OperationLabel 'bounded_health_check'
if ($healthResult.exit_code -ne 0) {
    throw "Post-recreate bounded health check failed closed; sanitized remote output withheld."
}

[ordered]@{
    dry_run                = $false
    execute_requested       = $true
    state                   = $State
    owner_gate              = $requiredOwnerGate
    target_service          = $targetService
    observed_shop_value     = $observedShop
    observed_equipment_value = $observedEquipment
    health_check            = 'PASS'
    result                  = 'EQUIPMENT_STATE_CHANGE_COMPLETE'
} | ConvertTo-Json -Depth 6 | Write-Output
