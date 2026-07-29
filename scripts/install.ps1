[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

function ConvertTo-TomlBasicString {
    param([Parameter(Mandatory = $true)][string]$Value)
    return '"' + $Value.Replace('\', '\\').Replace('"', '\"') + '"'
}

Write-Host '[1/6] Checking Hermes, Codex, and Python'
$HermesCommand = Get-Command hermes -ErrorAction Stop
Get-Command codex -ErrorAction Stop | Out-Null
$HermesPython = Join-Path (Split-Path $HermesCommand.Source -Parent) 'python.exe'
if (-not (Test-Path $HermesPython)) {
    $PythonCommand = Get-Command python -ErrorAction Stop
    $HermesPython = $PythonCommand.Source
}

Write-Host '[2/6] Creating or reusing the project virtual environment'
if (-not (Test-Path $VenvPython)) {
    & $HermesPython -m venv (Join-Path $ProjectRoot '.venv')
}

Write-Host '[3/6] Installing project-local dependencies'
& $VenvPython -m pip install --disable-pip-version-check -e "$ProjectRoot[test]"
if ($LASTEXITCODE -ne 0) {
    throw "Project dependency installation failed with exit code $LASTEXITCODE."
}

$BackupDir = Join-Path $ProjectRoot 'work\backups'
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

Write-Host '[4/6] Generating this machine''s project MCP configuration'
$ProjectMcpDir = Join-Path $ProjectRoot '.codex'
$ProjectMcpConfig = Join-Path $ProjectMcpDir 'config.toml'
New-Item -ItemType Directory -Path $ProjectMcpDir -Force | Out-Null
if (Test-Path $ProjectMcpConfig) {
    Copy-Item -LiteralPath $ProjectMcpConfig -Destination (
        Join-Path $BackupDir "project-config.toml.$Stamp.bak"
    )
}
$PythonToml = ConvertTo-TomlBasicString $VenvPython
$RootToml = ConvertTo-TomlBasicString $ProjectRoot
$AppConfigToml = ConvertTo-TomlBasicString (Join-Path $ProjectRoot 'config\default.yaml')
$McpText = @(
    '[mcp_servers.hermes_worker]'
    "command = $PythonToml"
    'args = ["-m", "codex_hermes_worker.bridge.server"]'
    "cwd = $RootToml"
    'env_vars = ["LMSTUDIO_API_KEY"]'
    "env = { CODEX_HERMES_CONFIG = $AppConfigToml }"
    'enabled = true'
    'required = true'
    'startup_timeout_sec = 30'
    'tool_timeout_sec = 1800'
    ''
) -join [Environment]::NewLine
[System.IO.File]::WriteAllText(
    $ProjectMcpConfig,
    $McpText,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host '[5/6] Backing up Codex user configuration and trusting only this project'
$UserCodexConfig = Join-Path $env:USERPROFILE '.codex\config.toml'
if (-not (Test-Path $UserCodexConfig)) {
    throw "Codex user configuration does not exist: $UserCodexConfig"
}
Copy-Item -LiteralPath $UserCodexConfig -Destination (
    Join-Path $BackupDir "user-config.toml.$Stamp.bak"
)
$ConfigText = [System.IO.File]::ReadAllText($UserCodexConfig)
$ProjectKeyToml = ConvertTo-TomlBasicString $ProjectRoot.ToLowerInvariant()
$ProjectSection = "[projects.$ProjectKeyToml]"
$SectionPattern = '(?im)^' + [Regex]::Escape($ProjectSection) +
    '\r?\ntrust_level\s*=\s*"trusted"\s*$'
$LegacySection = "[projects.'$($ProjectRoot.ToLowerInvariant())']"
$LegacyPattern = '(?im)^' + [Regex]::Escape($LegacySection) +
    '\r?\ntrust_level\s*=\s*"trusted"\s*$'
if (($ConfigText -notmatch $SectionPattern) -and ($ConfigText -notmatch $LegacyPattern)) {
    $ConfigText = $ConfigText.TrimEnd() + [Environment]::NewLine +
        [Environment]::NewLine + $ProjectSection + [Environment]::NewLine +
        'trust_level = "trusted"' + [Environment]::NewLine
    [System.IO.File]::WriteAllText(
        $UserCodexConfig,
        $ConfigText,
        [System.Text.UTF8Encoding]::new($false)
    )
}

Write-Host '[6/6] Verifying the bridge and Codex MCP registration'
if (-not $env:LMSTUDIO_API_KEY) {
    Write-Warning 'LMSTUDIO_API_KEY is not present. Configuration is installed, but live Qwen checks will be unhealthy until Codex inherits it.'
}
& $VenvPython -m codex_hermes_worker.cli health
if ($LASTEXITCODE -ne 0) {
    throw 'Bridge health verification failed.'
}
Push-Location $ProjectRoot
try {
    codex mcp get hermes_worker
    if ($LASTEXITCODE -ne 0) {
        throw 'Codex did not recognize hermes_worker.'
    }
}
finally {
    Pop-Location
}
Write-Host 'Installation complete. Reopen Codex in this project so it loads the MCP server.'
