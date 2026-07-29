[CmdletBinding()]
param(
    [switch]$NoUI,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    throw 'The project is not installed. Run .\scripts\install.ps1 first.'
}
$Ready = Join-Path $ProjectRoot 'work\bridge.ready'
$BridgeHealthy = $false
if (-not $env:LMSTUDIO_API_KEY) {
    Write-Warning 'LMSTUDIO_API_KEY is not present. The UI will start in diagnostic mode.'
}
else {
    & $Python -m codex_hermes_worker.cli health
    $BridgeHealthy = $LASTEXITCODE -eq 0
}
if ($BridgeHealthy) {
    New-Item -ItemType File -Path $Ready -Force | Out-Null
    Write-Host 'Bridge is healthy. Codex starts its stdio MCP process on demand.'
}
else {
    Remove-Item -LiteralPath $Ready -Force -ErrorAction SilentlyContinue
    Write-Warning 'Bridge is not healthy. Open the console to inspect Hermes and Qwen status.'
}
if (-not $NoUI) {
    & (Join-Path $PSScriptRoot 'start-ui.ps1') -NoBrowser:$NoBrowser
}
