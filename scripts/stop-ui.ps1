[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PidFile = Join-Path $ProjectRoot 'work\console.pid'

if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host 'Codex Hermes Console is not running.'
    return
}

$ConsolePid = [int](Get-Content -Raw -LiteralPath $PidFile)
$Process = Get-Process -Id $ConsolePid -ErrorAction SilentlyContinue
if (-not $Process) {
    Remove-Item -LiteralPath $PidFile -Force
    Write-Host 'Removed a stale console PID file.'
    return
}

$CommandLine = (Get-CimInstance Win32_Process -Filter "ProcessId=$ConsolePid").CommandLine
if ($CommandLine -notmatch 'codex_hermes_worker\.console\.server') {
    throw "PID $ConsolePid does not belong to Codex Hermes Console. It was not stopped."
}

Stop-Process -Id $ConsolePid
Wait-Process -Id $ConsolePid -Timeout 10 -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $PidFile -Force
Write-Host 'Codex Hermes Console stopped.'
