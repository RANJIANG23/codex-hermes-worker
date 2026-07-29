[CmdletBinding()]
param(
    [switch]$SkipLive
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    throw 'The project is not installed. Run .\scripts\install.ps1 first.'
}
Push-Location $ProjectRoot
try {
    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) {
        throw 'Offline test suite failed.'
    }
    if (-not $SkipLive) {
        if (-not $env:LMSTUDIO_API_KEY) {
            throw 'Live tests require LMSTUDIO_API_KEY. Use -SkipLive for offline tests only.'
        }
        $env:RUN_LIVE_QWEN = '1'
        & $Python -m pytest -q tests\test_live_chain.py tests\test_mcp_trusted_live.py
        if ($LASTEXITCODE -ne 0) {
            throw 'Live integration test suite failed.'
        }
        & $Python -m codex_hermes_worker.cli live-tool-test
        if ($LASTEXITCODE -ne 0) {
            throw 'Live batch tool test failed.'
        }
    }
}
finally {
    Remove-Item Env:\RUN_LIVE_QWEN -ErrorAction SilentlyContinue
    Pop-Location
}
