[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Command,
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]] $Arguments,
    [string] $Root
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$core = Join-Path $scriptRoot 'evidence_core.py'
if (-not (Test-Path -LiteralPath $core -PathType Leaf)) {
    Write-Error 'evidence_core.py is missing'
    exit 2
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) {
    Write-Error 'python executable is unavailable'
    exit 2
}

$argumentsToForward = @()
if ($null -ne $Root) {
    $argumentsToForward += '--root'
    $argumentsToForward += $Root
}
$argumentsToForward += $Command
if ($null -ne $Arguments) {
    $argumentsToForward += $Arguments
}

& $python.Source $core @argumentsToForward
exit $LASTEXITCODE
