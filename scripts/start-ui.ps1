[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$PidFile = Join-Path $ProjectRoot 'work\console.pid'
$LogDir = Join-Path $ProjectRoot 'work\logs'
$StdoutLog = Join-Path $LogDir 'console.stdout.log'
$StderrLog = Join-Path $LogDir 'console.stderr.log'
$Url = "http://127.0.0.1:$Port/"

if (-not (Test-Path -LiteralPath $Python)) {
    throw 'The project is not installed. Run .\scripts\install.ps1 first.'
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

if (Test-Path -LiteralPath $PidFile) {
    $ExistingPid = [int](Get-Content -Raw -LiteralPath $PidFile)
    $Existing = Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue
    if ($Existing) {
        try {
            Invoke-RestMethod -Uri ($Url + 'api/ping') -TimeoutSec 2 | Out-Null
            Write-Host "Console is already running: $Url"
            if (-not $NoBrowser) {
                Start-Process $Url
            }
            return
        }
        catch {
            throw "PID $ExistingPid is still running, but the console did not answer on $Url."
        }
    }
    Remove-Item -LiteralPath $PidFile -Force
}

$Arguments = @(
    '-m'
    'codex_hermes_worker.console.server'
    '--host'
    '127.0.0.1'
    '--port'
    $Port.ToString()
    '--no-browser'
)
$Process = Start-Process `
    -FilePath $Python `
    -ArgumentList $Arguments `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $StdoutLog `
    -RedirectStandardError $StderrLog `
    -PassThru
[System.IO.File]::WriteAllText(
    $PidFile,
    $Process.Id.ToString(),
    [System.Text.UTF8Encoding]::new($false)
)

$Ready = $false
for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
    Start-Sleep -Milliseconds 250
    if (-not (Get-Process -Id $Process.Id -ErrorAction SilentlyContinue)) {
        break
    }
    try {
        $Ping = Invoke-RestMethod -Uri ($Url + 'api/ping') -TimeoutSec 1
        if ($Ping.ok) {
            $Ready = $true
            break
        }
    }
    catch {
    }
}

if (-not $Ready) {
    $Tail = if (Test-Path -LiteralPath $StderrLog) {
        (Get-Content -LiteralPath $StderrLog -Tail 20) -join [Environment]::NewLine
    }
    else {
        'No error log was created.'
    }
    throw "Console failed to start. See $StderrLog`n$Tail"
}

Write-Host "Codex Hermes Console is running: $Url"
if (-not $NoBrowser) {
    Start-Process $Url
}
