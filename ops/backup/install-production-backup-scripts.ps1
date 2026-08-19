#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$ExpectedSourceSha,

    [string]$LayoutFile = 'deploy\release-layout.production.json',
    [switch]$Execute,
    [string]$OwnerGate,
    [string]$RenderRemoteScriptPath
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

Import-Module (Join-Path $PSScriptRoot '..\..\scripts\release\ReleaseTooling.psm1') -Force -DisableNameChecking

function ConvertTo-CanonicalModeString {
    param([Parameter(Mandatory = $true)][string]$Mode)
    $normalized = $Mode.TrimStart('0')
    if ([string]::IsNullOrEmpty($normalized)) { $normalized = '0' }
    return $normalized
}

function Assert-PreimageIdentityShape {
    param(
        [Parameter(Mandatory = $true)][object]$Identity,
        [Parameter(Mandatory = $true)][string]$Label
    )
    if ([string]$Identity.sha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw "Production backup pre-image contract has an invalid SHA256 for $Label."
    }
    if ([string]$Identity.file_type -ne 'regular file') {
        throw "Production backup pre-image contract must require regular files: $Label"
    }
    if ([string]$Identity.owner -notmatch '^[A-Za-z0-9_.-]+$' -or [string]$Identity.group -notmatch '^[A-Za-z0-9_.-]+$') {
        throw "Production backup pre-image contract has an invalid owner/group for $Label."
    }
    if ([string]$Identity.mode -notmatch '^[0-7]{3,4}$') {
        throw "Production backup pre-image contract has an invalid mode for $Label."
    }
}

function Get-DeclaredPreviousCanonical {
    param([Parameter(Mandatory = $true)][object]$Entry)
    if ($null -eq $Entry.PSObject.Properties['accepted_previous_canonical']) { return @() }
    if ($null -eq $Entry.accepted_previous_canonical) { return @() }
    return @($Entry.accepted_previous_canonical)
}

function Get-GitBlobSha256 {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$CommitSha,
        [Parameter(Mandatory = $true)][string]$RelativePath
    )

    $spec = '{0}:{1}' -f $CommitSha, $RelativePath
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = 'git'
    $startInfo.Arguments = '-C "{0}" cat-file blob "{1}"' -f $RepoRoot, $spec
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = [System.Diagnostics.Process]::Start($startInfo)
    $buffer = New-Object System.IO.MemoryStream
    try {
        $process.StandardOutput.BaseStream.CopyTo($buffer)
        $standardError = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            throw "Unable to read $spec from local Git history: $standardError"
        }
        $hasher = [System.Security.Cryptography.SHA256]::Create()
        try {
            return ([BitConverter]::ToString($hasher.ComputeHash($buffer.ToArray())) -replace '-', '').ToLowerInvariant()
        } finally {
            $hasher.Dispose()
        }
    } finally {
        $buffer.Dispose()
        $process.Dispose()
    }
}

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

$preimageContractPath = Resolve-RepoPath 'ops/backup/production-preimage.json'
if (-not (Test-Path -LiteralPath $preimageContractPath -PathType Leaf)) {
    throw "Production backup pre-image contract is missing: $preimageContractPath"
}
$preimageContract = Get-Content -LiteralPath $preimageContractPath -Raw -Encoding UTF8 | ConvertFrom-Json
$preimageSchemaVersion = [int]$preimageContract.schema_version
if ($preimageSchemaVersion -ne 1 -and $preimageSchemaVersion -ne 2) {
    throw "Production backup pre-image contract has an unsupported schema_version: $preimageSchemaVersion."
}
$preimageEntries = @($preimageContract.targets)
if ($preimageEntries.Count -ne $runtimeFiles.Count) {
    throw "Production backup pre-image contract must contain exactly $($runtimeFiles.Count) targets."
}
$preimageByRemotePath = @{}
foreach ($entry in $preimageEntries) {
    $remotePath = [string]$entry.remote_path
    if ([string]::IsNullOrWhiteSpace($remotePath) -or $preimageByRemotePath.ContainsKey($remotePath)) {
        throw "Production backup pre-image contract contains a missing or duplicate remote path."
    }
    Assert-PreimageIdentityShape -Identity $entry -Label $remotePath
    $declaredPrevious = Get-DeclaredPreviousCanonical -Entry $entry
    if ($declaredPrevious.Count -gt 0 -and $preimageSchemaVersion -lt 2) {
        throw "Production backup pre-image contract declares accepted_previous_canonical below schema_version 2: $remotePath"
    }
    $seenPreviousIdentity = @{}
    foreach ($previous in $declaredPrevious) {
        $previousLabel = "$remotePath (accepted previous canonical)"
        Assert-PreimageIdentityShape -Identity $previous -Label $previousLabel
        if ([string]$previous.file_type -ne [string]$entry.file_type) {
            throw "Production backup pre-image contract has a mismatched file type for $previousLabel."
        }
        if ([string]$previous.source_sha -notmatch '^[0-9a-fA-F]{40}$') {
            throw "Production backup pre-image contract must name an exact source commit for $previousLabel."
        }
        $identityKey = '{0}|{1}|{2}|{3}' -f ([string]$previous.sha256).ToLowerInvariant(), [string]$previous.owner, [string]$previous.group, (ConvertTo-CanonicalModeString ([string]$previous.mode))
        if ($seenPreviousIdentity.ContainsKey($identityKey)) {
            throw "Production backup pre-image contract has a duplicate accepted previous canonical identity for $remotePath."
        }
        $seenPreviousIdentity[$identityKey] = $true
    }
    $preimageByRemotePath[$remotePath] = $entry
}

$records = foreach ($file in $runtimeFiles) {
    $localPath = Resolve-RepoPath $file.RelativePath
    if (-not (Test-Path -LiteralPath $localPath -PathType Leaf)) {
        throw "Required backup runtime file is missing: $($file.RelativePath)"
    }
    if (-not $preimageByRemotePath.ContainsKey($file.RemotePath)) {
        throw "Production backup pre-image contract does not cover $($file.RemotePath)"
    }
    $preimage = $preimageByRemotePath[$file.RemotePath]
    $canonicalMode = ConvertTo-CanonicalModeString $file.Mode
    $hash = (Get-FileHash -LiteralPath $localPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $acceptedPreviousCanonical = @(Get-DeclaredPreviousCanonical -Entry $preimage | ForEach-Object {
        $declaredSha = ([string]$_.sha256).ToLowerInvariant()
        $declaredSourceSha = ([string]$_.source_sha).ToLowerInvariant()
        $historySha = Get-GitBlobSha256 -RepoRoot $repoRoot -CommitSha $declaredSourceSha -RelativePath $file.RelativePath
        if ($historySha -ne $declaredSha) {
            throw "Accepted previous canonical identity for $($file.RemotePath) does not match ${declaredSourceSha}:$($file.RelativePath) (declared $declaredSha, actual $historySha)."
        }
        [pscustomobject]@{
            Sha256 = $declaredSha
            Owner = [string]$_.owner
            Group = [string]$_.group
            Mode = ConvertTo-CanonicalModeString ([string]$_.mode)
            FileType = [string]$_.file_type
            SourceSha = $declaredSourceSha
            Description = [string]$_.description
        }
    })
    [pscustomobject]@{
        RelativePath = $file.RelativePath
        LocalPath = $localPath
        RemotePath = $file.RemotePath
        Mode = $file.Mode
        Owner = $file.Owner
        Group = $file.Group
        RequiresSudo = $file.RequiresSudo
        Sha256 = $hash
        CanonicalMode = $canonicalMode
        PreimageSha256 = ([string]$preimage.sha256).ToLowerInvariant()
        PreimageOwner = [string]$preimage.owner
        PreimageGroup = [string]$preimage.group
        PreimageMode = [string]$preimage.mode
        PreimageFileType = [string]$preimage.file_type
        AcceptedPreviousCanonical = $acceptedPreviousCanonical
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
        [Parameter(Mandatory = $true)][string]$Previous,
        [Parameter(Mandatory = $true)][string]$OperationId
    )

    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add('set -eu')
    $lines.Add(('stage={0}' -f (ConvertTo-PosixQuoted $Stage)))
    $lines.Add(('previous={0}' -f (ConvertTo-PosixQuoted $Previous)))
    $lines.Add('rollback_needed=0')
    for ($index = 1; $index -le $Items.Count; $index++) {
        $lines.Add(("activated_{0}=0" -f $index))
    }
    $lines.Add('')
    $lines.Add('die() {')
    $lines.Add('  echo "$*" >&2')
    $lines.Add('  exit 1')
    $lines.Add('}')
    $lines.Add('')
    $lines.Add('restore_target() {')
    $lines.Add('  target="$1"')
    $lines.Add('  backup="$2"')
    $lines.Add('  if [ -f "$backup" ]; then')
    $lines.Add('    case "$target" in')
    $lines.Add('      /etc/systemd/*) sudo -n cp -p -- "$backup" "$target" ;;')
    $lines.Add('      *) cp -p -- "$backup" "$target" ;;')
    $lines.Add('    esac')
    $lines.Add('  else')
    $lines.Add('    case "$target" in')
    $lines.Add('      /etc/systemd/*) sudo -n rm -f -- "$target" ;;')
    $lines.Add('      *) rm -f -- "$target" ;;')
    $lines.Add('    esac')
    $lines.Add('  fi')
    $lines.Add('}')
    $lines.Add('')
    $lines.Add('fail_closed() {')
    $lines.Add('  rc=$?')
    $lines.Add('  set +e')
    $lines.Add('  recovery_failed=0')
    $lines.Add('  if [ "$rollback_needed" -eq 1 ]; then')
    for ($index = $Items.Count; $index -ge 1; $index--) {
        $item = $Items[$index - 1]
        $target = ConvertTo-PosixQuoted $item.RemotePath
        $backup = ConvertTo-PosixQuoted ("$Previous/" + [IO.Path]::GetFileName($item.RelativePath))
        $lines.Add(('    if [ "$activated_{0}" -eq 1 ]; then restore_target {1} {2} || recovery_failed=1; fi' -f $index, $target, $backup))
    }
    $reloadCondition = (1..$Items.Count | ForEach-Object { '[ "$activated_{0}" -eq 1 ]' -f $_ }) -join ' || '
    $lines.Add(('    if {0}; then sudo -n systemctl daemon-reload >/dev/null 2>&1 || recovery_failed=1; fi' -f $reloadCondition))
    $lines.Add('  fi')
    $lines.Add('  if [ "$recovery_failed" -eq 1 ]; then echo "canonical backup propagation recovery failed" >&2; fi')
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
    $lines.Add('')

    $index = 0
    foreach ($item in $Items) {
        $index++
        $target = ConvertTo-PosixQuoted $item.RemotePath
        $stagePath = ConvertTo-PosixQuoted ("$Stage/" + [IO.Path]::GetFileName($item.RelativePath))
        $previousPath = ConvertTo-PosixQuoted ("$Previous/" + [IO.Path]::GetFileName($item.RelativePath))
        $tmpPath = ConvertTo-PosixQuoted ("$($item.RemotePath).canonical.$OperationId")
        $preSha = ConvertTo-PosixQuoted $item.PreimageSha256
        $preOwner = ConvertTo-PosixQuoted $item.PreimageOwner
        $preGroup = ConvertTo-PosixQuoted $item.PreimageGroup
        $preMode = $item.PreimageMode.TrimStart('0')
        if ([string]::IsNullOrEmpty($preMode)) { $preMode = '0' }
        $preMode = ConvertTo-PosixQuoted $preMode
        $canonicalSha = ConvertTo-PosixQuoted $item.Sha256
        $canonicalOwner = ConvertTo-PosixQuoted $item.Owner
        $canonicalGroup = ConvertTo-PosixQuoted $item.Group
        $canonicalMode = ConvertTo-PosixQuoted $item.CanonicalMode
        $lines.Add("target=$target")
        $lines.Add('if [ ! -e "$target" ]; then die "remote target is missing: $target"; fi')
        $lines.Add('if [ -L "$target" ]; then die "remote target is a symlink: $target"; fi')
        $lines.Add('if [ ! -f "$target" ]; then die "remote target is not a regular file: $target"; fi')
        $lines.Add('actual_type=$(stat -c "%F" -- "$target")')
        $lines.Add(('if [ "$actual_type" != {0} ]; then die "remote file type mismatch: $target"; fi' -f (ConvertTo-PosixQuoted $item.PreimageFileType)))
        $lines.Add('actual_mode=$(stat -c "%a" -- "$target")')
        $lines.Add('actual_owner=$(stat -c "%U" -- "$target")')
        $lines.Add('actual_group=$(stat -c "%G" -- "$target")')
        $lines.Add('actual_sha=$(sha256sum -- "$target" | awk ''{print $1}'')')
        # Accepted identities, in owner-reviewed order: the original legacy
        # production pre-image, every explicitly declared previous canonical
        # identity for this target, then the canonical identity being installed
        # (which also makes an unchanged rerun idempotent). Anything else is
        # unknown drift and fails closed before any activation.
        $identityTest = 'if [ "$actual_sha" = {0} ] && [ "$actual_owner" = {1} ] && [ "$actual_group" = {2} ] && [ "$actual_mode" = {3} ]'
        $acceptedIdentities = [System.Collections.Generic.List[string]]::new()
        $acceptedIdentities.Add(($identityTest -f $preSha, $preOwner, $preGroup, $preMode))
        foreach ($previous in $item.AcceptedPreviousCanonical) {
            $acceptedIdentities.Add(($identityTest -f (ConvertTo-PosixQuoted $previous.Sha256), (ConvertTo-PosixQuoted $previous.Owner), (ConvertTo-PosixQuoted $previous.Group), (ConvertTo-PosixQuoted $previous.Mode)))
        }
        $acceptedIdentities.Add(($identityTest -f $canonicalSha, $canonicalOwner, $canonicalGroup, $canonicalMode))
        $gate = $acceptedIdentities[0] + '; then :; '
        for ($branch = 1; $branch -lt $acceptedIdentities.Count; $branch++) {
            $gate += ($acceptedIdentities[$branch] -replace '^if ', 'elif ') + '; then :; '
        }
        $gate += 'else die "remote pre-image identity mismatch: $target"; fi'
        $lines.Add($gate)
        $lines.Add(('if [ ! -f {0} ]; then die "staged backup file is missing: {0}"; fi' -f $stagePath))
        $lines.Add(("echo '{0}  {1}' | sha256sum --check --strict -" -f $item.Sha256, $stagePath.Trim("'")))
        if ($item.RelativePath.EndsWith('.sh')) {
            $lines.Add(("bash -n {0}" -f $stagePath))
        } else {
            $lines.Add(("sudo -n systemd-analyze verify {0}" -f $stagePath))
        }
        $lines.Add('')
    }
    $lines.Add('echo "REMOTE_PREIMAGE_MATCH=YES"')
    $lines.Add('rollback_needed=1')
    $lines.Add('')

    $index = 0
    foreach ($item in $Items) {
        $index++
        $target = ConvertTo-PosixQuoted $item.RemotePath
        $stagePath = ConvertTo-PosixQuoted ("$Stage/" + [IO.Path]::GetFileName($item.RelativePath))
        $previousPath = ConvertTo-PosixQuoted ("$Previous/" + [IO.Path]::GetFileName($item.RelativePath))
        $tmpPath = ConvertTo-PosixQuoted ("$($item.RemotePath).canonical.$OperationId")
        $lines.Add("target=$target")
        $lines.Add("stage_file=$stagePath")
        $lines.Add("previous_file=$previousPath")
        $lines.Add('if [ -f "$target" ]; then')
        $lines.Add('  case "$target" in')
        $lines.Add('    /etc/systemd/*) sudo -n cp -p -- "$target" "$previous_file" ;;')
        $lines.Add('    *) cp -p -- "$target" "$previous_file" ;;')
        $lines.Add('  esac')
        $lines.Add('fi')
        $lines.Add('case "$target" in')
        $lines.Add(('  /etc/systemd/*) sudo -n install -o {0} -g {1} -m {2} "$stage_file" {3}; sudo -n mv -Tf {3} "$target" ;;' -f $item.Owner, $item.Group, $item.Mode, $tmpPath))
        $lines.Add(('  *) install -o {0} -g {1} -m {2} "$stage_file" {3}; mv -Tf {3} "$target" ;;' -f $item.Owner, $item.Group, $item.Mode, $tmpPath))
        $lines.Add('esac')
        $lines.Add(("activated_{0}=1" -f $index))
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
    remote_execution_shell = 'sh -s'
    preimage_contract = 'ops/backup/production-preimage.json'
    files = @($records | ForEach-Object {
        [ordered]@{
            relative_path = $_.RelativePath
            remote_path = $_.RemotePath
            sha256 = $_.Sha256
            preimage_sha256 = $_.PreimageSha256
            preimage_owner = $_.PreimageOwner
            preimage_group = $_.PreimageGroup
            preimage_mode = $_.PreimageMode
            canonical_owner = $_.Owner
            canonical_group = $_.Group
            canonical_mode = $_.CanonicalMode
            accepted_previous_canonical = @($_.AcceptedPreviousCanonical | ForEach-Object {
                [ordered]@{
                    sha256 = $_.Sha256
                    owner = $_.Owner
                    group = $_.Group
                    mode = $_.Mode
                    file_type = $_.FileType
                    source_sha = $_.SourceSha
                    description = $_.Description
                }
            })
        }
    })
    remote_stage = $remoteStage
    remote_previous = $remotePrevious
}

$remoteScript = New-RemotePropagationScript -Items $records -Stage $remoteStage -Previous $remotePrevious -OperationId $operationId
if ($RenderRemoteScriptPath) {
    if ($Execute) {
        throw '-RenderRemoteScriptPath cannot be combined with -Execute.'
    }
    $renderPath = [IO.Path]::GetFullPath($RenderRemoteScriptPath)
    [IO.File]::WriteAllText($renderPath, $remoteScript, (New-Object System.Text.UTF8Encoding($false)))
    $report.rendered_remote_script = $renderPath
}

if (-not $Execute) {
    $report.mode = 'plan'
    $report | ConvertTo-Json -Depth 8
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

$result = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -ScriptText $remoteScript -TimeoutSeconds 180 -OperationLabel 'backup runtime atomic propagation'
if ($result.exit_code -ne 0) { throw "Backup propagation failed closed: $($result.stdout) $($result.stderr)" }
$report.mode = 'executed'
$report.remote_result = $result.stdout.Trim()
$report | ConvertTo-Json -Depth 8
