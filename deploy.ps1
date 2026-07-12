$ErrorActionPreference = "Continue"
Set-StrictMode -Version Latest

$REMOTE_HOST = "152.69.200.105"
$REMOTE_USER = "ubuntu"
$REMOTE_DIR  = "/opt/go-odyssey"
$SSH_TARGET  = "${REMOTE_USER}@${REMOTE_HOST}"
$SSH_KEY     = "$env:USERPROFILE\.ssh\oracle_godoyssey"
$DEPLOY_TAG  = Get-Date -Format "yyyyMMdd_HHmmss"
$LOCAL_BACKUP_ROOT = Join-Path $PSScriptRoot "backups\oracle-a1"
$LOCAL_BACKUP_DIR = Join-Path $LOCAL_BACKUP_ROOT $DEPLOY_TAG
$SSH_OPTS = @(
    "-i", $SSH_KEY
    "-o", "ConnectTimeout=10"
    "-o", "BatchMode=yes"
    "-o", "StrictHostKeyChecking=no"
    "-o", "UserKnownHostsFile=NUL"
)

New-Item -ItemType Directory -Force -Path $LOCAL_BACKUP_DIR | Out-Null

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$FailureMessage
    )
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

function Get-RemoteBackupPaths {
    return [ordered]@{
        DbDump   = "/tmp/go-odyssey-db-$DEPLOY_TAG.dump"
        SiteTar  = "/tmp/go-odyssey-site-$DEPLOY_TAG.tar.gz"
    }
}

Write-Host "[0/7] Generating runtime inventory and restore matrix..." -ForegroundColor Yellow
Invoke-Checked -FilePath "python" -ArgumentList @((Join-Path $PSScriptRoot "tools\build_runtime_restore_matrix.py")) -FailureMessage "Failed to build runtime restore matrix"

Write-Host "Deploying to Oracle A1 with backup first" -ForegroundColor Cyan
Write-Host "[1/7] Verifying SSH connectivity..." -ForegroundColor Yellow
Invoke-Checked -FilePath "ssh" -ArgumentList ($SSH_OPTS + @($SSH_TARGET, "echo 'SSH connection ok'")) -FailureMessage "SSH connection failed"

$remote = Get-RemoteBackupPaths

Write-Host "[2/7] Creating remote backup artifacts..." -ForegroundColor Yellow
$remoteBackupCmd = @(
    "set -e"
    "cd $REMOTE_DIR"
    "mkdir -p /tmp"
    "docker exec go-odyssey-postgres pg_dump -U go -d go_odyssey -Fc > `"$($remote.DbDump)`""
    "tar -czf `"$($remote.SiteTar)`" --exclude=.git --exclude=.venv --exclude=venv --exclude=__pycache__ --exclude='*.pyc' --exclude='*.pyo' --exclude='*.log' --exclude='*.tmp' --exclude='*.bak*' --exclude='*.tar.gz' --exclude='katago_cache.db' --exclude='katago_review_exports' --exclude='analysis_logs' --exclude='test_solve' --exclude='outputs' --exclude='_backup_*' ."
) -join "`n"
Invoke-Checked -FilePath "ssh" -ArgumentList ($SSH_OPTS + @($SSH_TARGET, $remoteBackupCmd)) -FailureMessage "Remote backup creation failed"

Write-Host "[3/7] Copying backups to local archive..." -ForegroundColor Yellow
Invoke-Checked -FilePath "scp" -ArgumentList ($SSH_OPTS + @("${SSH_TARGET}:$($remote.DbDump)", $LOCAL_BACKUP_DIR)) -FailureMessage "Failed to download database dump"
Invoke-Checked -FilePath "scp" -ArgumentList ($SSH_OPTS + @("${SSH_TARGET}:$($remote.SiteTar)", $LOCAL_BACKUP_DIR)) -FailureMessage "Failed to download site archive"

Write-Host "[4/7] Cleaning temporary backup files on remote..." -ForegroundColor Yellow
Invoke-Checked -FilePath "ssh" -ArgumentList ($SSH_OPTS + @($SSH_TARGET, "rm -f $($remote.DbDump) $($remote.SiteTar)")) -FailureMessage "Failed to clean remote backup files"

Write-Host "[5/7] Packaging workspace and uploading to Oracle A1..." -ForegroundColor Yellow
$excludes = @(
    ".env", ".env.*", ".git", ".claude", ".gemini", "__pycache__", "*.pyc", "*.log", "*.bak*", "*.csv", "*.tsv", "*.xlsx", "*.doc", "*.tmp",
    "analysis_logs", "katago_review_exports", "SGF*", "2023-06-15-*", "katago-v*", "test_solve", "_backup_*",
    "katago_cache.db*", "katago_answer_report_*.json", "katago_results.json",
    "katago_checkpoint.json", "ngrok.exe", "gnugo.exe", "cyg*.dll", "go_app.db", "go_game.db",
    "questions.json.bak*", "_cloudrun_*", "_deleted_*", "docs", "go-odyssey-deploy.tar.gz", "test*.tar.gz",
    "backups",
    # Local-only heavy artifacts: image builds its own deps via pip (.dockerignore drops venv too).
    # These never belong in the deploy archive and bloat the upload by ~650MB.
    "venv", "venv311", ".venv", "*.exe", "*.onnx", "voices-v1.0.bin", "kokoro-*", "media"
)
$excludeArgs = $excludes | ForEach-Object { "--exclude=$_" }
# Write archive OUTSIDE the packaged tree (TEMP) so tar -C . . does not include
# the growing archive itself (which corrupts the gzip stream: remote trailing garbage / status 2).
$archiveName = Join-Path $env:TEMP "go-odyssey-deploy.tar.gz"
Invoke-Checked -FilePath "tar" -ArgumentList (@("czf", $archiveName) + $excludeArgs + @("-C", ".", ".")) -FailureMessage "Failed to package workspace"
Invoke-Checked -FilePath "scp" -ArgumentList ($SSH_OPTS + @($archiveName, "${SSH_TARGET}:/tmp/")) -FailureMessage "Failed to upload deploy archive"

if (Test-Path "katago_cache.db") {
    $localSize = (Get-Item "katago_cache.db").Length
    $remoteSizeRaw = ssh @SSH_OPTS $SSH_TARGET "stat -c %s /opt/go-odyssey/katago_cache.db 2>/dev/null; true"
    $remoteSize = "$remoteSizeRaw".Trim()
    if ($remoteSize -ne "$localSize") {
        $mb = [math]::Round($localSize / 1MB, 1)
        Write-Host "  Syncing katago_cache.db ($mb MB)..." -ForegroundColor Yellow
        Invoke-Checked -FilePath "scp" -ArgumentList ($SSH_OPTS + @("katago_cache.db", "${SSH_TARGET}:/opt/go-odyssey/")) -FailureMessage "Failed to sync katago_cache.db"
    } else {
        Write-Host "  katago_cache.db already up to date" -ForegroundColor DarkGray
    }
}

Write-Host "[6/7] Deploying on remote host..." -ForegroundColor Yellow
# After scp the remote filename is the basename (/tmp/go-odyssey-deploy.tar.gz);
# $archiveName is now a local TEMP full path, so remote commands must use basename.
$remoteArchive = Split-Path -Leaf $archiveName
$remoteDeployCmd = @(
    "set -e"
    "mkdir -p $REMOTE_DIR"
    "cd $REMOTE_DIR"
    "tar xzf /tmp/$remoteArchive"
    "rm -f /tmp/$remoteArchive"
    "cp nginx/default-ssl.conf nginx/default.conf"
    "docker compose -f docker-compose.prod.yml build"
    "docker compose -f docker-compose.prod.yml up -d"
) -join "`n"
Invoke-Checked -FilePath "ssh" -ArgumentList ($SSH_OPTS + @($SSH_TARGET, $remoteDeployCmd)) -FailureMessage "Remote deploy failed"

Start-Sleep -Seconds 10
try {
    $health = Invoke-RestMethod -Uri "http://${REMOTE_HOST}/healthz" -TimeoutSec 10
    if ($health.ok -eq $true) {
        Write-Host "Deployment successful: http://${REMOTE_HOST}/" -ForegroundColor Green
        Write-Host "Local backup saved to: $LOCAL_BACKUP_DIR" -ForegroundColor Green
    } else {
        Write-Host "Deployment finished, but health check returned an unexpected payload." -ForegroundColor Yellow
    }
} catch {
    Write-Host "Deployment finished, but health check could not be confirmed." -ForegroundColor Yellow
    Write-Host "Local backup saved to: $LOCAL_BACKUP_DIR" -ForegroundColor Green
}

Remove-Item -Path $archiveName -ErrorAction SilentlyContinue
