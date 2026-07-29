[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$RemoveData
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function ConvertTo-TomlBasicString {
    param([Parameter(Mandatory = $true)][string]$Value)
    return '"' + $Value.Replace('\', '\\').Replace('"', '\"') + '"'
}

$UserCodexConfig = Join-Path $env:USERPROFILE '.codex\config.toml'
if (Test-Path $UserCodexConfig) {
    $ConfigText = [System.IO.File]::ReadAllText($UserCodexConfig)
    $ProjectKeyToml = ConvertTo-TomlBasicString $ProjectRoot.ToLowerInvariant()
    $Sections = @(
        "[projects.$ProjectKeyToml]",
        "[projects.'$($ProjectRoot.ToLowerInvariant())']"
    )
    $UpdatedConfigText = $ConfigText
    foreach ($Section in $Sections) {
        $Pattern = '(?im)\r?\n?' + [Regex]::Escape($Section) +
            '\r?\ntrust_level\s*=\s*"trusted"\s*\r?\n?'
        $UpdatedConfigText = [Regex]::Replace(
            $UpdatedConfigText,
            $Pattern,
            [Environment]::NewLine
        )
    }
    if (
        ($UpdatedConfigText -ne $ConfigText) -and
        $PSCmdlet.ShouldProcess($UserCodexConfig, 'Remove this project trust entry')
    ) {
        $BackupDir = Join-Path $ProjectRoot 'work\backups'
        New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
        $Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        Copy-Item -LiteralPath $UserCodexConfig -Destination (
            Join-Path $BackupDir "user-config.toml.uninstall-$Stamp.bak"
        )
        [System.IO.File]::WriteAllText(
            $UserCodexConfig,
            $UpdatedConfigText,
            [System.Text.UTF8Encoding]::new($false)
        )
    }
}

$Targets = @(
    (Join-Path $ProjectRoot '.venv'),
    (Join-Path $ProjectRoot '.codex\config.toml')
)
if ($RemoveData) {
    $Targets += (Join-Path $ProjectRoot 'work')
}
foreach ($Target in $Targets) {
    $Parent = (Resolve-Path (Split-Path $Target -Parent)).Path
    if (-not $Parent.StartsWith($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a path outside the project: $Target"
    }
    if (
        (Test-Path $Target) -and
        $PSCmdlet.ShouldProcess($Target, 'Remove project-created content')
    ) {
        Remove-Item -LiteralPath $Target -Recurse -Force
    }
}

if ($WhatIfPreference) {
    Write-Host 'Uninstall preview complete; no changes were made.'
}
else {
    Write-Host 'Uninstall complete. Hermes, LM Studio, local models, and source research data were not changed.'
}
