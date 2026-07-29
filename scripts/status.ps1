[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
Write-Host "Project: $ProjectRoot"
Write-Host "VirtualEnv: $(Test-Path $Python)"
Write-Host "LMSTUDIO_API_KEY present: $([bool]$env:LMSTUDIO_API_KEY)"
Write-Host "Ready marker: $(Test-Path (Join-Path $ProjectRoot 'work\bridge.ready'))"
$Healthy = $false
$Registered = $false
if (Test-Path $Python) {
    & $Python -m codex_hermes_worker.cli health
    $Healthy = $LASTEXITCODE -eq 0
}
Push-Location $ProjectRoot
try {
    codex mcp get hermes_worker
    $Registered = $LASTEXITCODE -eq 0
}
finally {
    Pop-Location
}
if (-not ($Healthy -and $Registered)) {
    exit 1
}
