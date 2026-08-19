#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$ExpectedSourceSha,

    [string]$LayoutFile = 'deploy\release-layout.production.json',
    [switch]$Execute,
    [string]$OwnerGate
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

Import-Module (Join-Path $PSScriptRoot '..\..\scripts\release\ReleaseTooling.psm1') -Force -DisableNameChecking

$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
$sourceSha = (git -C $repoRoot rev-parse --verify HEAD).Trim().ToLowerInvariant()
if ($sourceSha -ne $ExpectedSourceSha.ToLowerInvariant()) {
    throw "Backup propagation source SHA mismatch: expected $ExpectedSourceSha, got $sourceSha."
}
Assert-CompleteWorktreeClean -WorkingDirectory $repoRoot
if ($Execute) {
    Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_BACKUP_PROPAGATION'
}

$runtimeFiles = @(
    [ordered]@{
        RelativePath = 'ops/backup/linux/backup.sh'
        RemotePath = '/opt/go-odyssey/ops/backup/linux/backup.sh'
        Mode = '0755'
        Owner = 'ubuntu'
        Group = 'ubuntu'
        RequiresSudo = $false
    },
    [ordered]@{
        RelativePath = 'ops/backup/remote/make_db_dump.sh'
        RemotePath = '/opt/go-odyssey/ops/backup/remote/make_db_dump.sh'
        Mode = '0644'
        Owner = 'ubuntu'
        Group = 'ubuntu'
        RequiresSudo = $false
    },
    [ordered]@{
        RelativePath = 'ops/backup/remote/make_site_archive.sh'
        RemotePath = '/opt/go-odyssey/ops/backup/remote/make_site_archive.sh'
        Mode = '0644'
        Owner = 'ubuntu'
        Group = 'ubuntu'
        RequiresSudo = $false
    },
    [ordered]@{
        RelativePath = 'ops/backup/systemd/godokro-backup-daily.service'
        RemotePath = '/etc/systemd/system/godokro-backup-daily.service'
        Mode = '0644'
        Owner = 'root'
        Group = 'root'
        RequiresSudo = $true
    },
    [ordered]@{
        RelativePath = 'ops/backup/systemd/godokro-backup-daily.timer'
        RemotePath = '/etc/systemd/system/godokro-backup-daily.timer'
        Mode = '0644'
        Owner = 'root'
        Group = 'root'
        RequiresSudo = $true
    },
    [ordered]@{
        RelativePath = 'ops/backup/systemd/godokro-backup-weekly.service'
        RemotePath = '/etc/systemd/system/godokro-backup-weekly.service'
        Mode = '0644'
        Owner = 'root'
        Group = 'root'
        RequiresSudo = $true
    },
    [ordered]@{
        RelativePath = 'ops/backup/systemd/godokro-backup-weekly.timer'
        RemotePath = '/etc/systemd/system/godokro-backup-weekly.timer'
        Mode = '0644'
        Owner = 'root'
        Group = 'root'
        RequiresSudo = $true
    }
)

$records = foreach ($file in $runtimeFiles) {
    $localPath = Resolve-RepoPath $file.RelativePath
    if (-not (Test-Path -LiteralPath $localPath -PathType Leaf)) {
        throw "Required backup runtime file is missing: $($file.RelativePath)"
    }
    $hash = (Get-FileHash -LiteralPath $localPath -Algorithm SHA256).Hash.ToLowerInvariant()
    [pscustomobject]@{
        RelativePath = $file.RelativePath
        LocalPath = $localPath
        RemotePath = $file.RemotePath
        Mode = $file.Mode
        Owner = $file.Owner
        Group = $file.Group
        RequiresSudo = $file.RequiresSudo
        Sha256 = $hash
    }
}

$operationId = [guid]::NewGuid().ToString('N')
$remoteStage = "/opt/go-odyssey/ops/backup/_backup_pipeline_stage_$operationId"
$remotePrevious = "/opt/go-odyssey/ops/backup/_backup_pipeline_previous_$operationId"

function ConvertTo-PosixQuoted {
    param([Parameter(Mandatory = $true)][string]$Value)
    return (Quote-PosixShellArgument $Value)
}

function New-RemotePropagationScript {
    param(
        [Parameter(Mandatory = $true)][object[]]$Items,
        [Parameter(Mandatory = $true)][string]$Stage,
        [Parameter(Mandatory = $true)][string]$Previous
    )

    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add('set -eu')
    $lines.Add(('stage={0}' -f (ConvertTo-PosixQuoted $Stage)))
    $lines.Add(('previous={0}' -f (ConvertTo-PosixQuoted $Previous)))
    $lines.Add('rollback_needed=0')
    $lines.Add('activated_paths=()')
    $lines.Add('')
    $lines.Add('fail_closed() {')
    $lines.Add('  rc=$?')
    $lines.Add('  set +e')
    $lines.Add('  if [ "$rollback_needed" -eq 1 ]; then')
    $lines.Add('    for ((i=${#activated_paths[@]}-1; i>=0; i--)); do')
    $lines.Add('      item="${activated_paths[$i]}"')
    $lines.Add('      target="${item%%|*}"')
    $lines.Add('      backup="${item#*|}"')
    $lines.Add('      if [ -f "$backup" ]; then')
    $lines.Add('        if [[ "$target" == /etc/systemd/* ]]; then sudo -n cp -p -- "$backup" "$target"; else cp -p -- "$backup" "$target"; fi')
    $lines.Add('      else')
    $lines.Add('        if [[ "$target" == /etc/systemd/* ]]; then sudo -n rm -f -- "$target"; else rm -f -- "$target"; fi')
    $lines.Add('      fi')
    $lines.Add('    done')
    $lines.Add('    if [[ "${#activated_paths[@]}" -gt 0 ]]; then sudo -n systemctl daemon-reload >/dev/null 2>&1 || true; fi')
    $lines.Add('  fi')
    $lines.Add('  rm -rf -- "$stage"')
    $lines.Add('  exit "$rc"')
    $lines.Add('}')
    $lines.Add('trap fail_closed EXIT')
    $lines.Add('')
    $lines.Add('test -d /opt/go-odyssey/ops/backup')
    $lines.Add('test -f /opt/go-odyssey/ops/backup/backup-config.json')
    $lines.Add('test ! -L /opt/go-odyssey/ops/backup')
    $lines.Add('[ "$(realpath -e /opt/go-odyssey/ops/backup)" = "/opt/go-odyssey/ops/backup" ]')
    $lines.Add('[ "$(realpath -e /etc/systemd/system)" = "/etc/systemd/system" ]')
    $lines.Add('sudo -n true')
    $lines.Add('test -d "$stage"')
    $lines.Add('test ! -L "$stage"')
    $lines.Add('mkdir -p -- "$previous"')
    $lines.Add('test ! -L "$previous"')
    $lines.Add('rollback_needed=1')
    $lines.Add('')

    foreach ($item in $Items) {
        $target = ConvertTo-PosixQuoted $item.RemotePath
        $stagePath = ConvertTo-PosixQuoted ("$Stage/" + [IO.Path]::GetFileName($item.RelativePath))
        $previousPath = ConvertTo-PosixQuoted ("$Previous/" + [IO.Path]::GetFileName($item.RelativePath))
        $tmpPath = ConvertTo-PosixQuoted ("$($item.RemotePath).canonical.$operationId")
        $lines.Add("target=$target")
        $lines.Add('if [ -e "$target" ] || [ -L "$target" ]; then test -f "$target"; test ! -L "$target"; fi')
        $lines.Add('if [ -f "$target" ]; then stat -c "%F|%a|%U|%G" "$target"; sha256sum -- "$target"; fi')
        $lines.Add("test -f $stagePath")
        $lines.Add(("echo '{0}  {1}' | sha256sum --check --strict -" -f $item.Sha256, $stagePath.Trim("'")))
        if ($item.RelativePath.EndsWith('.sh')) {
            $lines.Add(("bash -n {0}" -f $stagePath))
        }
        $lines.Add(('if [ -f "$target" ]; then if [[ "$target" == /etc/systemd/* ]]; then sudo -n cp -p -- "$target" {0}; else cp -p -- "$target" {0}; fi; fi' -f $previousPath))
        $lines.Add(('if [[ "$target" == /etc/systemd/* ]]; then sudo -n install -o {0} -g {1} -m {2} {3} {4}; sudo -n mv -Tf {4} "$target"; else install -o {0} -g {1} -m {2} {3} {4}; mv -Tf {4} "$target"; fi' -f $item.Owner, $item.Group, $item.Mode, $stagePath, $tmpPath))
        $activatedBackup = "$Previous/$([IO.Path]::GetFileName($item.RelativePath))"
        $lines.Add(('activated_paths+=("{0}|{1}")' -f $item.RemotePath, $activatedBackup))
        $lines.Add(("echo '{0}  {1}' | sha256sum --check --strict -" -f $item.Sha256, $target.Trim("'")))
        $lines.Add('')
    }
    $lines.Add('sudo -n systemd-analyze verify /etc/systemd/system/godokro-backup-daily.service /etc/systemd/system/godokro-backup-daily.timer /etc/systemd/system/godokro-backup-weekly.service /etc/systemd/system/godokro-backup-weekly.timer')
    $lines.Add('sudo -n systemctl daemon-reload')
    $lines.Add('rollback_needed=0')
    $lines.Add('trap - EXIT')
    $lines.Add('rm -rf -- "$stage"')
    $lines.Add('printf "%s\\n" "backup propagation complete; previous copy: $previous"')
    return ($lines -join "`n")
}

$report = [ordered]@{
    source_sha = $sourceSha
    operation_id = $operationId
    execute = [bool]$Execute
    files = @($records | ForEach-Object {
        [ordered]@{ relative_path = $_.RelativePath; remote_path = $_.RemotePath; sha256 = $_.Sha256 }
    })
    remote_stage = $remoteStage
    remote_previous = $remotePrevious
}

if (-not $Execute) {
    $report.mode = 'plan'
    $report | ConvertTo-Json -Depth 5
    exit 0
}

$mkdirScript = @"
set -eu
if [ -e $(ConvertTo-PosixQuoted $remoteStage) ] || [ -L $(ConvertTo-PosixQuoted $remoteStage) ]; then
  echo 'remote staging path already exists' >&2
  exit 1
fi
mkdir -p -- $(ConvertTo-PosixQuoted $remoteStage)
test ! -L $(ConvertTo-PosixQuoted $remoteStage)
test -d $(ConvertTo-PosixQuoted $remoteStage)
"@
$mkdirResult = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -ScriptText $mkdirScript -TimeoutSeconds 45 -OperationLabel 'backup propagation staging directory'
if ($mkdirResult.exit_code -ne 0) { throw "Remote staging setup failed: $($mkdirResult.stdout) $($mkdirResult.stderr)" }

foreach ($item in $records) {
    $remoteStagePath = "$remoteStage/$([IO.Path]::GetFileName($item.RelativePath))"
    $upload = Invoke-BoundedScpUpload -LocalPath $item.LocalPath -SshAlias $layout.ssh_alias -RemotePath $remoteStagePath -TimeoutSeconds 60 -OperationLabel "backup propagation upload $($item.RelativePath)"
    if ($upload.exit_code -ne 0) { throw "Upload failed for $($item.RelativePath): $($upload.stdout) $($upload.stderr)" }
}

$remoteScript = New-RemotePropagationScript -Items $records -Stage $remoteStage -Previous $remotePrevious
$result = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -ScriptText $remoteScript -TimeoutSeconds 180 -OperationLabel 'backup runtime atomic propagation'
if ($result.exit_code -ne 0) { throw "Backup propagation failed closed: $($result.stdout) $($result.stderr)" }
$report.mode = 'executed'
$report.remote_result = $result.stdout.Trim()
$report | ConvertTo-Json -Depth 5
