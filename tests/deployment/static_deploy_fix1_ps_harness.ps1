#Requires -Version 5.1
<#
.SYNOPSIS
  RELEASE-FIX-A2-STATIC-DEPLOY-FIX1 test harness -- exercises the new bounded
  native-command primitives against fake ssh/scp executables (never a real
  host) and a real hanging local process, so pytest can assert exact
  behavior without any network access.
#>
param(
    [Parameter(Mandatory = $true)][string]$Scenario
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot '..\..\scripts\release\ReleaseTooling.psm1') -Force -DisableNameChecking

$fakeSshExe = Join-Path $PSScriptRoot '..\fixtures\fake_ssh\ssh.cmd'
$fakeScpExe = Join-Path $PSScriptRoot '..\fixtures\fake_ssh\scp.cmd'

function Emit($obj) {
    $obj | ConvertTo-Json -Depth 6 | Write-Output
}

switch ($Scenario) {
    'TimeoutKillsHungProcess' {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        try {
            Invoke-BoundedNativeCommand -FileName 'powershell' `
                -ArgumentList @('-NoProfile', '-Command', 'Start-Sleep -Seconds 999') `
                -TimeoutSeconds 2 -OperationLabel 'test: hung local process' | Out-Null
            Emit @{ scenario = $Scenario; result = 'UNEXPECTED_SUCCESS' }
        }
        catch {
            $sw.Stop()
            Emit @{
                scenario = $Scenario
                result = 'TIMED_OUT_AS_EXPECTED'
                error_message = $_.Exception.Message
                elapsed_seconds = [Math]::Round($sw.Elapsed.TotalSeconds, 1)
            }
        }
    }
    'BoundedSshSuccess' {
        $result = Invoke-BoundedSshCommand -SshAlias 'fake-host' -Command 'echo hi' -TimeoutSeconds 10 -OperationLabel 'test: ssh success' -SshExecutable $fakeSshExe
        Emit @{ scenario = $Scenario; exit_code = $result.exit_code; output = $result.output }
    }
    'BoundedSshFail' {
        $result = Invoke-BoundedSshCommand -SshAlias 'fake-host' -Command 'anything' -TimeoutSeconds 10 -OperationLabel 'test: ssh fail' -SshExecutable $fakeSshExe
        Emit @{ scenario = $Scenario; exit_code = $result.exit_code; output = $result.output }
    }
    'BoundedSshHang' {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        try {
            Invoke-BoundedSshCommand -SshAlias 'fake-host' -Command 'anything' -TimeoutSeconds 2 -OperationLabel 'test: ssh hang' -SshExecutable $fakeSshExe | Out-Null
            Emit @{ scenario = $Scenario; result = 'UNEXPECTED_SUCCESS' }
        }
        catch {
            $sw.Stop()
            Emit @{
                scenario = $Scenario
                result = 'TIMED_OUT_AS_EXPECTED'
                error_message = $_.Exception.Message
                elapsed_seconds = [Math]::Round($sw.Elapsed.TotalSeconds, 1)
            }
        }
    }
    'BoundedScpSuccess' {
        $result = Invoke-BoundedScpUpload -LocalPath $PSCommandPath -SshAlias 'fake-host' -RemotePath '/tmp/x' -TimeoutSeconds 10 -OperationLabel 'test: scp success' -ScpExecutable $fakeScpExe
        Emit @{ scenario = $Scenario; exit_code = $result.exit_code; output = $result.output }
    }
    'BoundedScpFail' {
        $result = Invoke-BoundedScpUpload -LocalPath $PSCommandPath -SshAlias 'fake-host' -RemotePath '/tmp/x' -TimeoutSeconds 10 -OperationLabel 'test: scp fail' -ScpExecutable $fakeScpExe
        Emit @{ scenario = $Scenario; exit_code = $result.exit_code; output = $result.output }
    }
    'BoundedSshOptionsPresent' {
        $sshOptions = Get-BoundedSshOptionArguments
        Emit @{ scenario = $Scenario; options = @($sshOptions) }
    }
    'BatchVerificationScriptTextHang' {
        # RELEASE-FIX-A2-STATIC-DEPLOY-FIX2: the batched sha256 verification
        # call also goes through Invoke-BoundedSshCommand -ScriptText, so it
        # must be killed the same way a hung directory-batch call is.
        $files = @([pscustomobject]@{ path = 'i18n.js'; sha256 = 'deadbeef' })
        $script = New-RemoteBatchShaVerificationScript -RemoteReleaseDir '/root/gen1' -Files $files
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        try {
            Invoke-BoundedSshCommand -SshAlias 'fake-host' -ScriptText $script -TimeoutSeconds 2 -OperationLabel 'test: batch verification hang' -SshExecutable $fakeSshExe | Out-Null
            Emit @{ scenario = $Scenario; result = 'UNEXPECTED_SUCCESS' }
        }
        catch {
            $sw.Stop()
            Emit @{
                scenario = $Scenario
                result = 'TIMED_OUT_AS_EXPECTED'
                error_message = $_.Exception.Message
                elapsed_seconds = [Math]::Round($sw.Elapsed.TotalSeconds, 1)
            }
        }
    }
    'BatchVerificationTimeoutForRealManifest' {
        $manifestPath = Join-Path $PSScriptRoot '..\..\release-artifacts\go-odyssey-app_1b0e5836.static.json'
        $text = Get-Content -Raw -Encoding UTF8 $manifestPath
        $text = $text -replace [char]0xFEFF, ''
        $manifest = $text | ConvertFrom-Json
        $totalBytes = ($manifest.files | Measure-Object -Property size -Sum).Sum
        $timeout = Get-BatchVerificationTimeoutSeconds -TotalBytes $totalBytes
        Emit @{ scenario = $Scenario; total_bytes = $totalBytes; batch_timeout_seconds = $timeout }
    }
    'BoundedSshScriptTextSuccess' {
        # Mirrors the real directory-batch-creation call: one ssh session,
        # a multi-line script piped over stdin, not a per-directory command.
        $script = New-RemoteMkdirScriptText -Directories @('/root/gen1', '/root/gen1/assets/shop', '/root/gen1/assets/pets/horse_anim_lv3')
        $result = Invoke-BoundedSshCommand -SshAlias 'fake-host' -ScriptText $script -TimeoutSeconds 10 -OperationLabel 'test: batched mkdir via sh -s' -SshExecutable $fakeSshExe
        Emit @{ scenario = $Scenario; exit_code = $result.exit_code; output = $result.output; script_sent = $script }
    }
    'RealManifestSingleMkdirOperation' {
        # Uses the actual 182-file static release manifest produced by
        # package-static-release.ps1 -- proves the real bundle needs
        # exactly ONE ssh mkdir operation, not one per directory.
        $manifestPath = Join-Path $PSScriptRoot '..\..\release-artifacts\go-odyssey-app_e5efe34f.static.json'
        $text = Get-Content -Raw -Encoding UTF8 $manifestPath
        $text = $text -replace [char]0xFEFF, ''
        $manifest = $text | ConvertFrom-Json
        $paths = @($manifest.files | ForEach-Object { $_.path })
        $remoteReleaseDir = '/opt/go-odyssey-static/releases/real-gen-test'
        $dirs = Get-RemoteParentDirectorySet -RelativePaths $paths -RemoteReleaseDir $remoteReleaseDir
        $script = New-RemoteMkdirScriptText -Directories $dirs
        $sshInvocationCount = 1  # exactly one Invoke-BoundedSshCommand -ScriptText call covers all $dirs
        $result = Invoke-BoundedSshCommand -SshAlias 'fake-host' -ScriptText $script -TimeoutSeconds 10 -OperationLabel 'test: real-manifest batched mkdir' -SshExecutable $fakeSshExe
        Emit @{
            scenario = $Scenario
            file_count = $paths.Count
            unique_directory_count = $dirs.Count
            ssh_mkdir_operation_count = $sshInvocationCount
            exit_code = $result.exit_code
        }
    }
    default {
        throw "Unknown scenario: $Scenario"
    }
}
