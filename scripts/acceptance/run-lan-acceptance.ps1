[CmdletBinding()]
param(
    [ValidateSet('Start', 'Stop', 'Reset', 'Verify', 'StartRemote', 'StopRemote')]
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
$RemoteStateRoot = Join-Path $StateRoot 'remote-tunnel'
$RemotePidFile = Join-Path $RemoteStateRoot 'cloudflared.pid'
$RemoteUrlFile = Join-Path $RemoteStateRoot 'remote-url.txt'
$RemoteStdoutFile = Join-Path $RemoteStateRoot 'cloudflared.stdout.log'
$RemoteStderrFile = Join-Path $RemoteStateRoot 'cloudflared.stderr.log'
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

function Resolve-Cloudflared {
    $command = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($command -and (Test-Path -LiteralPath $command.Source -PathType Leaf)) {
        return $command.Source
    }
    $wingetRoot = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
    if (Test-Path -LiteralPath $wingetRoot -PathType Container) {
        $packageDirs = Get-ChildItem -LiteralPath $wingetRoot -Directory -Filter 'Cloudflare.cloudflared*' -ErrorAction SilentlyContinue
        foreach ($packageDir in $packageDirs) {
            $candidate = Join-Path $packageDir.FullName 'cloudflared.exe'
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
        }
    }
    throw 'cloudflared is not installed. Install it outside the repository with: winget install --id Cloudflare.cloudflared --exact --scope user'
}

function Read-RemoteUrl {
    if (-not (Test-Path -LiteralPath $RemoteUrlFile -PathType Leaf)) { return '' }
    return (Get-Content -LiteralPath $RemoteUrlFile -Raw).Trim().TrimEnd('/')
}

function Get-RemoteProcess {
    if (-not (Test-Path -LiteralPath $RemotePidFile -PathType Leaf)) { return $null }
    $rawPid = (Get-Content -LiteralPath $RemotePidFile -Raw).Trim()
    $pidValue = 0
    if (-not [int]::TryParse($rawPid, [ref]$pidValue) -or $pidValue -le 0) {
        throw 'Remote tunnel PID state is invalid; remove only the acceptance remote state and retry.'
    }
    try { return Get-Process -Id $pidValue -ErrorAction Stop } catch { return $null }
}

function Assert-RemoteProcessOwnership([System.Diagnostics.Process]$Process) {
    if ($null -eq $Process) { return }
    $expectedPath = Resolve-Cloudflared
    try { $actualPath = $Process.Path } catch { throw 'Could not verify the remote tunnel process executable path.' }
    if (-not $actualPath -or [IO.Path]::GetFullPath($actualPath) -ne [IO.Path]::GetFullPath($expectedPath)) {
        throw 'Remote tunnel PID does not belong to the expected cloudflared executable; refusing to stop it.'
    }
}

function Get-RemoteLogText {
    $parts = @()
    foreach ($path in @($RemoteStdoutFile, $RemoteStderrFile)) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            try { $parts += Get-Content -LiteralPath $path -Raw } catch { }
        }
    }
    return ($parts -join "`n")
}

function Wait-ForRemoteUrl([System.Diagnostics.Process]$Process, [int]$TimeoutSeconds = 90) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $pattern = 'https://[a-z0-9-]+\.trycloudflare\.com'
    do {
        $log = Get-RemoteLogText
        $match = [regex]::Match($log, $pattern, [Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if ($match.Success) {
            $url = $match.Value.ToLowerInvariant().TrimEnd('/')
            Set-Content -LiteralPath $RemoteUrlFile -Value $url -Encoding ASCII
            return $url
        }
        if ($Process.HasExited) {
            throw "cloudflared exited before producing an HTTPS URL. See $RemoteStderrFile."
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for a Cloudflare Quick Tunnel URL. See $RemoteStderrFile."
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

function Invoke-Verify([hashtable]$State, [switch]$RuntimeOnly) {
    $source = Get-CurrentSourceSha
    if (-not $RuntimeOnly -and $source -ne $ExpectedSourceSha) {
        throw "Source SHA mismatch: expected $ExpectedSourceSha, found $source."
    }
    $health = Get-Response "http://127.0.0.1:$Port/healthz"
    if ($health.Status -ne 200) { throw "Acceptance health check returned HTTP $($health.Status)." }
    $identity = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/acceptance/identity" -Method Get
    if (-not $identity.ok -or -not $identity.source_sha_match -or $identity.production -or $identity.production_publish_available) {
        throw 'Acceptance identity endpoint did not prove the expected non-Production profile.'
    }
    if ($RuntimeOnly) {
        $source = ([string]$identity.source_sha).Trim().ToLowerInvariant()
        if ($source -ne $ExpectedSourceSha) {
            throw "Running acceptance source SHA mismatch: expected $ExpectedSourceSha, found $source."
        }
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

function Invoke-RemoteSmoke([string]$RemoteUrl) {
    if (-not $RemoteUrl -or $RemoteUrl -notmatch '^https://[a-z0-9-]+\.trycloudflare\.com$') {
        throw 'Remote acceptance URL is not an HTTPS temporary Cloudflare URL.'
    }
    $identity = Invoke-RestMethod -Uri "$RemoteUrl/api/acceptance/identity" -Method Get
    if (-not $identity.ok -or -not $identity.source_sha_match -or $identity.production -or $identity.production_publish_available) {
        throw 'Remote acceptance identity did not prove the expected non-Production source/profile.'
    }
    $routes = @{
        '/login' = @(200, 302)
        '/index.html' = @(200, 302)
        '/admin/sgf-answer-review' = @(200, 302)
    }
    $routeResults = @{}
    foreach ($route in $routes.Keys) {
        $result = Get-Response "$RemoteUrl$route"
        $routeResults[$route] = $result.Status
        if ($routes[$route] -notcontains $result.Status) { throw "Remote $route returned HTTP $($result.Status)." }
    }

    $state = Read-StateValues
    foreach ($required in @('ACCEPTANCE_ADMIN_USERNAME', 'ACCEPTANCE_ADMIN_PASSWORD')) {
        if (-not $state.ContainsKey($required) -or [string]::IsNullOrWhiteSpace($state[$required])) {
            throw "Acceptance state is missing $required; run Start first."
        }
    }
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $login = Invoke-RestMethod -Uri "$RemoteUrl/api/auth/login" -Method Post -ContentType 'application/json' `
        -Body (@{ username = $state['ACCEPTANCE_ADMIN_USERNAME']; password = $state['ACCEPTANCE_ADMIN_PASSWORD'] } | ConvertTo-Json) `
        -WebSession $session
    if (-not $login.ok -or -not $login.is_admin) { throw 'Remote acceptance Admin login/session verification failed.' }

    $bootstrap = Invoke-RestMethod -Uri "$RemoteUrl/api/admin/sgf-workbench/bootstrap" -Method Get -WebSession $session
    if (-not $bootstrap.ok -or $null -eq $bootstrap.items) { throw 'Remote Admin Workbench bootstrap failed.' }
    $items = Invoke-RestMethod -Uri "$RemoteUrl/api/admin/sgf-workbench/items" -Method Get -WebSession $session
    if (-not $items.ok) { throw 'Remote Admin Workbench API session check failed.' }

    $csrfRejected = $false
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "$RemoteUrl/api/admin/sgf-workbench/batches" -Method Post `
            -ContentType 'application/json' -Body '{}' -WebSession $session -ErrorAction Stop | Out-Null
    } catch {
        $status = 0
        if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
        $csrfRejected = ($status -eq 403)
    }
    if (-not $csrfRejected) { throw 'Remote Admin API did not fail closed on a missing CSRF token.' }

    $csrfHeader = @{
        'X-SGF-Answer-Review-CSRF' = [string]$bootstrap.security.csrf_token
        'Content-Type' = 'application/json'
    }
    $csrfAccepted = $false
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "$RemoteUrl/api/admin/sgf-workbench/flag" -Method Post `
            -Headers $csrfHeader -Body '{}' -WebSession $session -ErrorAction Stop | Out-Null
    } catch {
        $status = 0
        if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
        # The valid CSRF header is accepted; the deliberately empty request is
        # then rejected by normal input validation without mutating a record.
        $csrfAccepted = ($status -eq 400)
    }
    if (-not $csrfAccepted) { throw 'Remote Admin API CSRF acceptance/input validation check failed.' }

    Write-Output 'REMOTE_LOGIN_SESSION=PASS'
    Write-Output 'REMOTE_CSRF=PASS'
    Write-Output 'REMOTE_ADMIN_API=PASS'
    Write-Output 'REMOTE_ENVIRONMENT_IDENTITY_VISIBLE=YES'
    Write-Output 'REMOTE_SPECIAL_TRANSPORT_REQUIRED=NO'
    Write-Output "REMOTE_ROUTE_STATUS_LOGIN=$($routeResults['/login'])"
    Write-Output "REMOTE_ROUTE_STATUS_INDEX=$($routeResults['/index.html'])"
    Write-Output "REMOTE_ROUTE_STATUS_REVIEW=$($routeResults['/admin/sgf-answer-review'])"
    Write-Output "REMOTE_WORKBENCH_ITEM_COUNT=$($items.items.Count)"
}

function Wait-ForRemoteReachability([string]$RemoteUrl, [int]$TimeoutSeconds = 90) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $identity = Invoke-RestMethod -Uri "$RemoteUrl/api/acceptance/identity" -Method Get -TimeoutSec 15
            if ($identity.ok -and $identity.source_sha_match -and -not $identity.production -and -not $identity.production_publish_available) {
                return
            }
        } catch { }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw 'Temporary HTTPS URL did not become reachable before the timeout; the tunnel was stopped.'
}

function Start-RemoteAcceptance {
    Assert-SafeAcceptancePaths
    Assert-Docker
    $cloudflaredPath = Resolve-Cloudflared
    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        throw 'Local acceptance state is absent. Start the local acceptance environment first.'
    }
    # This performs local source/profile/route verification without starting
    # or exposing any additional service.
    Invoke-Verify (Read-StateValues) -RuntimeOnly | Out-Null
    $localIdentity = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/acceptance/identity" -Method Get
    $source = ([string]$localIdentity.source_sha).Trim().ToLowerInvariant()
    New-Item -ItemType Directory -Force -Path $RemoteStateRoot | Out-Null

    $existing = Get-RemoteProcess
    if ($existing) {
        Assert-RemoteProcessOwnership $existing
        $existingUrl = Read-RemoteUrl
        if (-not $existingUrl) { throw 'An existing cloudflared process has no recorded URL; refusing to guess.' }
        Wait-ForRemoteReachability $existingUrl
        Invoke-RemoteSmoke $existingUrl
        Write-Output 'REMOTE_ACCESS_METHOD=Cloudflare Quick Tunnel (ephemeral HTTPS)'
        Write-Output "REMOTE_ACCEPTANCE_URL=$existingUrl"
        Write-Output "REMOTE_RUNNING_SOURCE_SHA=$source"
        Write-Output 'EXPECTED_SOURCE_SHA_MATCH=YES'
        Write-Output 'REMOTE_PROTOCOL=https'
        Write-Output 'TEMPORARY_URL=YES'
        Write-Output 'REVOCABLE=YES'
        Write-Output 'STOP_COMMAND_INVALIDATES_REMOTE_ACCESS=YES'
        return
    }

    Remove-Item -LiteralPath $RemotePidFile, $RemoteUrlFile, $RemoteStdoutFile, $RemoteStderrFile -Force -ErrorAction SilentlyContinue
    $process = Start-Process -FilePath $cloudflaredPath `
        -ArgumentList @('tunnel', '--no-autoupdate', '--url', "http://127.0.0.1:$Port") `
        -RedirectStandardOutput $RemoteStdoutFile -RedirectStandardError $RemoteStderrFile `
        -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $RemotePidFile -Value ([string]$process.Id) -Encoding ASCII
    try {
        $url = Wait-ForRemoteUrl $process
        Wait-ForRemoteReachability $url
        Invoke-RemoteSmoke $url
    } catch {
        try { Assert-RemoteProcessOwnership $process; Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } catch { }
        Remove-Item -LiteralPath $RemotePidFile, $RemoteUrlFile -Force -ErrorAction SilentlyContinue
        throw
    }
    Write-Output 'REMOTE_ACCESS_METHOD=Cloudflare Quick Tunnel (ephemeral HTTPS)'
    Write-Output "REMOTE_ACCEPTANCE_URL=$url"
    Write-Output "REMOTE_RUNNING_SOURCE_SHA=$source"
    Write-Output 'EXPECTED_SOURCE_SHA_MATCH=YES'
    Write-Output 'REMOTE_PROTOCOL=https'
    Write-Output 'TEMPORARY_URL=YES'
    Write-Output 'REVOCABLE=YES'
    Write-Output 'STOP_COMMAND_INVALIDATES_REMOTE_ACCESS=YES'
    Write-Output 'REMOTE_EXTERNAL_NETWORK_SMOKE=PASS'
}

function Stop-RemoteAcceptance {
    Assert-SafeAcceptancePaths
    $process = Get-RemoteProcess
    $url = Read-RemoteUrl
    if (-not $process) {
        Remove-Item -LiteralPath $RemotePidFile, $RemoteUrlFile -Force -ErrorAction SilentlyContinue
        Write-Output 'REMOTE_STOPPED=NOOP'
        Write-Output 'REMOTE_URL_ACCESSIBLE=NO'
        return
    }
    Assert-RemoteProcessOwnership $process
    Stop-Process -Id $process.Id -Force
    try { $process.WaitForExit(10000) | Out-Null } catch { }
    Remove-Item -LiteralPath $RemotePidFile, $RemoteUrlFile -Force -ErrorAction SilentlyContinue
    Write-Output 'REMOTE_STOPPED=YES'
    Write-Output 'REMOTE_URL_ACCESSIBLE=NO'
    Write-Output 'STOP_COMMAND_INVALIDATES_REMOTE_ACCESS=YES'
    if ($url) { Write-Output 'REMOTE_URL_REVOKED=YES' }
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
    # Never leave a public tunnel behind when the local acceptance target is
    # stopped. This remains scoped to the recorded cloudflared PID only.
    if (Test-Path -LiteralPath $RemotePidFile -PathType Leaf) { Stop-RemoteAcceptance }
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
    'StartRemote' { Start-RemoteAcceptance }
    'StopRemote' { Stop-RemoteAcceptance }
    'Verify' {
        Assert-SafeAcceptancePaths
        Assert-Docker
        if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) { throw 'Acceptance state is absent; run Start first.' }
        $state = Read-StateValues
        Invoke-Verify $state
    }
}
