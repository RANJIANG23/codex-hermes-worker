[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Ready = Join-Path $ProjectRoot 'work\bridge.ready'
& (Join-Path $PSScriptRoot 'stop-ui.ps1')
if (Test-Path $Ready) {
    Remove-Item -LiteralPath $Ready -Force
}
Write-Host 'Project readiness marker removed. Hermes and LM Studio were not stopped.'
