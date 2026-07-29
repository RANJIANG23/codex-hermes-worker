[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765
)

$ErrorActionPreference = 'Continue'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PidFile = Join-Path $ProjectRoot 'work\console.pid'
$Url = "http://127.0.0.1:$Port/"

$PidValue = $null
if (Test-Path -LiteralPath $PidFile) {
    $PidValue = [int](Get-Content -Raw -LiteralPath $PidFile)
}
$ProcessRunning = $PidValue -and [bool](Get-Process -Id $PidValue -ErrorAction SilentlyContinue)
$HttpReady = $false
try {
    $Ping = Invoke-RestMethod -Uri ($Url + 'api/ping') -TimeoutSec 2
    $HttpReady = [bool]$Ping.ok
}
catch {
}

Write-Host "Console URL: $Url"
Write-Host "PID: $PidValue"
Write-Host "Process running: $ProcessRunning"
Write-Host "HTTP ready: $HttpReady"

if (-not ($ProcessRunning -and $HttpReady)) {
    exit 1
}
