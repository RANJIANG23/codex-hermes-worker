[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    throw 'The project is not installed. Run .\scripts\install.ps1 first.'
}
if (-not $env:LMSTUDIO_API_KEY) {
    throw 'LMSTUDIO_API_KEY is not present in this PowerShell process.'
}
& $Python -m codex_hermes_worker.cli health
if ($LASTEXITCODE -ne 0) {
    throw 'Bridge health verification failed.'
}
$Ready = Join-Path $ProjectRoot 'work\bridge.ready'
New-Item -ItemType File -Path $Ready -Force | Out-Null
Write-Host 'Bridge is ready. It is a stdio MCP server that Codex starts on demand.'
