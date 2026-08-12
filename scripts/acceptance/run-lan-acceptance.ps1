[CmdletBinding()]
param(
    [ValidateSet('Start', 'Stop', 'Reset', 'Verify')]
    [string]$Action = 'Start',
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$ExpectedSourceSha = '8910160855030d6266b52b63242b7a9c384d0e24',
    [ValidateRange(1024, 65535)]
    [int]$Port = 5080,
    [string]$LanHost = '',
    [switch]$NoBuild
)

$ErrorActionPreference = 'Stop'
$ProjectName = 'go-odyssey-acceptance'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ComposeFile = Join-Path $RepoRoot 'docker-compose.acceptance.yml'
$StateRoot = Join-Path $env:LOCALAPPDATA 'GoOdyssey\acceptance\sgf-admin-workbench'
$EnvFile = Join-Path $StateRoot 'acceptance.env'
$CredentialsFile = Join-Path $StateRoot 'owner-login.txt'
$ExpectedSourceSha = $ExpectedSourceSha.ToLowerInvariant()

function Assert-SafeAcceptancePaths {
    if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf) -or
        [IO.Path]::GetFileName($ComposeFile) -ne 'docker-compose.acceptance.yml') {
        throw "Acceptance compose file is missing or not the governed acceptance compose file."
    }
    if ($ProjectName -ne 'go-odyssey-acceptance') {
        throw "Unexpected acceptance compose project name."
    }
}

function Assert-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker CLI is required for the isolated acceptance environment.'
    }
    & docker compose version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Compose v2 is required for the isolated acceptance environment.'
    }
}

function Get-CurrentSourceSha {
    $sha = (& git -C $RepoRoot rev-parse HEAD 2>$null).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $sha -notmatch '^[0-9a-f]{40}$') {
        throw 'The acceptance worktree does not have a readable Git HEAD.'
    }
    return $sha
}

function New-RandomAlphaNumeric([int]$Length = 40) {
    $bytes = New-Object byte[] ($Length + 16)
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $value = [Convert]::ToBase64String($bytes) -replace '[^A-Za-z0-9]', ''
    if ($value.Length -lt $Length) { return New-RandomAlphaNumeric -Length $Length }
    return $value.Substring(0, $Length)
}

function Read-StateValues {
    $values = @{}
    if (Test-Path -LiteralPath $EnvFile -PathType Leaf) {
        foreach ($line in Get-Content -LiteralPath $EnvFile) {
            if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
                $values[$Matches[1]] = $Matches[2]
            }
        }
    }
    return $values
}

function Write-State {
    New-Item -ItemType Directory -Force -Path $StateRoot | Out-Null
    $values = Read-StateValues
    if (-not $values.ContainsKey('ACCEPTANCE_DB_PASSWORD')) { $values['ACCEPTANCE_DB_PASSWORD'] = New-RandomAlphaNumeric 40 }
    if (-not $values.ContainsKey('ACCEPTANCE_SECRET_KEY')) { $values['ACCEPTANCE_SECRET_KEY'] = New-RandomAlphaNumeric 64 }
    if (-not $values.ContainsKey('ACCEPTANCE_ADMIN_PASSWORD')) { $values['ACCEPTANCE_ADMIN_PASSWORD'] = 'GO-Accept-' + (New-RandomAlphaNumeric 24) }
    if (-not $values.ContainsKey('ACCEPTANCE_PLAYER_PASSWORD')) { $values['ACCEPTANCE_PLAYER_PASSWORD'] = 'GO-Player-' + (New-RandomAlphaNumeric 24) }
    $values['ACCEPTANCE_ADMIN_USERNAME'] = 'owner.acceptance.admin'
    $values['ACCEPTANCE_PLAYER_USERNAME'] = 'owner.acceptance.player'
    $values['ACCEPTANCE_SOURCE_SHA'] = $ExpectedSourceSha
    $values['ACCEPTANCE_IMAGE'] = 'go-odyssey-app:acceptance-' + $ExpectedSourceSha.Substring(0, 12)
    $values['ACCEPTANCE_BUILD_DATE'] = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $values['ACCEPTANCE_SGF_ENGINE_SOURCE_COMMIT'] = 'unknown'
    $values['ACCEPTANCE_PORT'] = [string]$Port
    $values['ACCEPTANCE_BIND_HOST'] = '0.0.0.0'
    $ordered = @(
        'ACCEPTANCE_DB_PASSWORD', 'ACCEPTANCE_SECRET_KEY',
        'ACCEPTANCE_ADMIN_USERNAME', 'ACCEPTANCE_ADMIN_PASSWORD',
        'ACCEPTANCE_PLAYER_USERNAME', 'ACCEPTANCE_PLAYER_PASSWORD',
        'ACCEPTANCE_SOURCE_SHA', 'ACCEPTANCE_IMAGE', 'ACCEPTANCE_BUILD_DATE',
        'ACCEPTANCE_SGF_ENGINE_SOURCE_COMMIT', 'ACCEPTANCE_PORT', 'ACCEPTANCE_BIND_HOST'
    )
    $lines = foreach ($key in $ordered) { "$key=$($values[$key])" }
    Set-Content -LiteralPath $EnvFile -Value $lines -Encoding UTF8
    @(
        'Go Odyssey SGF Admin Workbench - NON-PRODUCTION ACCEPTANCE',
        "source_sha=$ExpectedSourceSha",
        "admin_username=$($values['ACCEPTANCE_ADMIN_USERNAME'])",
        "admin_password=$($values['ACCEPTANCE_ADMIN_PASSWORD'])",
        "player_username=$($values['ACCEPTANCE_PLAYER_USERNAME'])",
        "player_password=$($values['ACCEPTANCE_PLAYER_PASSWORD'])",
        'Use only with the isolated acceptance URL. Do not commit this file.'
    ) | Set-Content -LiteralPath $CredentialsFile -Encoding UTF8
    return $values
}

function Invoke-AcceptanceCompose([string[]]$ComposeArgs) {
    $args = @('compose', '--project-name', $ProjectName, '--env-file', $EnvFile, '-f', $ComposeFile) + $ComposeArgs
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed: $($ComposeArgs -join ' ')" }
}

function Get-LanAddress {
    if ($LanHost) { return $LanHost }
    $addresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike '127.*' -and
            $_.IPAddress -notlike '169.254.*' -and
            $_.PrefixOrigin -ne 'WellKnown'
        } |
        Sort-Object InterfaceIndex, SkipAsSource |
        Select-Object -ExpandProperty IPAddress)
    if ($addresses.Count -eq 0) { throw 'No LAN IPv4 address was found. Supply -LanHost explicitly.' }
    return $addresses[0]
}

function Get-Response([string]$Uri) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -MaximumRedirection 5 -Uri $Uri
        return [pscustomobject]@{ Status = [int]$response.StatusCode; Body = [string]$response.Content; Headers = $response.Headers }
    } catch {
        $webResponse = $_.Exception.Response
        if ($null -ne $webResponse) {
            $reader = New-Object IO.StreamReader($webResponse.GetResponseStream())
            try { $body = $reader.ReadToEnd() } finally { $reader.Dispose() }
            return [pscustomobject]@{ Status = [int]$webResponse.StatusCode; Body = $body; Headers = $webResponse.Headers }
        }
        throw
    }
}

function Wait-ForHealth([int]$TimeoutSeconds = 120) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Get-Response "http://127.0.0.1:$Port/healthz"
            if ($response.Status -eq 200) { return }
        } catch { }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw 'Acceptance app did not become healthy before the timeout.'
}

function Invoke-Verify([hashtable]$State) {
    $source = Get-CurrentSourceSha
    if ($source -ne $ExpectedSourceSha) {
        throw "Source SHA mismatch: expected $ExpectedSourceSha, found $source."
    }
    $health = Get-Response "http://127.0.0.1:$Port/healthz"
    if ($health.Status -ne 200) { throw "Acceptance health check returned HTTP $($health.Status)." }
    $identity = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/acceptance/identity" -Method Get
    if (-not $identity.ok -or -not $identity.source_sha_match -or $identity.production -or $identity.production_publish_available) {
        throw 'Acceptance identity endpoint did not prove the expected non-Production profile.'
    }
    $routes = @{
        '/login' = @(200, 302)
        '/index.html' = @(200, 302)
        '/admin/sgf-answer-review' = @(200, 302)
    }
    $routeResults = @{}
    foreach ($route in $routes.Keys) {
        $result = Get-Response "http://127.0.0.1:$Port$route"
        $routeResults[$route] = $result.Status
        if ($routes[$route] -notcontains $result.Status) { throw "$route returned HTTP $($result.Status)." }
    }
    $lan = Get-LanAddress
    Write-Output "RUNNING_SOURCE_SHA=$source"
    Write-Output 'EXPECTED_SOURCE_SHA_MATCH=YES'
    Write-Output 'ENVIRONMENT=NON-PRODUCTION ACCEPTANCE'
    Write-Output "LAN_HOST=$lan"
    Write-Output "PORT=$Port"
    Write-Output 'PROTOCOL=http'
    Write-Output "ACCEPTANCE_URL=http://$lan`:$Port/"
    Write-Output "CREDENTIALS_FILE=$CredentialsFile"
    Write-Output "ROUTE_STATUS_LOGIN=$($routeResults['/login'])"
    Write-Output "ROUTE_STATUS_INDEX=$($routeResults['/index.html'])"
    Write-Output "ROUTE_STATUS_REVIEW=$($routeResults['/admin/sgf-answer-review'])"
    Write-Output 'PRODUCTION_PUBLISH_AVAILABLE=NO'
    Write-Output 'PRODUCTION_MUTATION=NO'
}

function Start-Acceptance {
    Assert-SafeAcceptancePaths
    Assert-Docker
    $source = Get-CurrentSourceSha
    if ($source -ne $ExpectedSourceSha) { throw "Source SHA mismatch: expected $ExpectedSourceSha, found $source." }
    $state = Write-State
    $upArgs = @('up', '-d')
    if (-not $NoBuild) { $upArgs += '--build' }
    Invoke-AcceptanceCompose $upArgs
    Wait-ForHealth
    Invoke-AcceptanceCompose @('run', '--rm', '--no-deps', 'app', 'python', '/tmp/seed_acceptance.py')
    Invoke-Verify $state
    Write-Output 'STARTED=YES'
    Write-Output 'STOP_COMMAND=powershell -ExecutionPolicy Bypass -File scripts/acceptance/run-lan-acceptance.ps1 -Action Stop'
    Write-Output 'RESET_TEST_DATA_COMMAND=powershell -ExecutionPolicy Bypass -File scripts/acceptance/run-lan-acceptance.ps1 -Action Reset'
}

function Stop-Acceptance {
    Assert-SafeAcceptancePaths
    Assert-Docker
    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        Write-Output 'STOPPED=NOOP_STATE_FILE_ABSENT'
        return
    }
    Invoke-AcceptanceCompose @('down', '--remove-orphans')
    Write-Output 'STOPPED=YES'
}

function Reset-Acceptance {
    Assert-SafeAcceptancePaths
    Assert-Docker
    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) { $null = Write-State }
    # This command is deliberately scoped to the fixed acceptance project and
    # compose file. It cannot target the Production compose project.
    Invoke-AcceptanceCompose @('down', '--volumes', '--remove-orphans')
    Start-Acceptance
}

switch ($Action) {
    'Start'  { Start-Acceptance }
    'Stop'   { Stop-Acceptance }
    'Reset'  { Reset-Acceptance }
    'Verify' {
        Assert-SafeAcceptancePaths
        Assert-Docker
        if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) { throw 'Acceptance state is absent; run Start first.' }
        $state = Read-StateValues
        Invoke-Verify $state
    }
}
