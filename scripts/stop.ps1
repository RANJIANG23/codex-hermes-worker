[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Ready = Join-Path $ProjectRoot 'work\bridge.ready'
if (Test-Path $Ready) {
    Remove-Item -LiteralPath $Ready -Force
}
Write-Host 'Project readiness marker removed. Codex closes stdio MCP processes with its task; Hermes and LM Studio were not stopped.'
