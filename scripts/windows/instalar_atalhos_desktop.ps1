# Instala/atualiza os atalhos .bat na Area de Trabalho
$ErrorActionPreference = "Stop"

$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Desktop = [Environment]::GetFolderPath("Desktop")
$WindowsScripts = Join-Path $ProjectDir "scripts\windows"

$launchers = @(
    "Segundo Cerebro.bat",
    "Backup Segundo Cerebro.bat",
    "Restaurar Segundo Cerebro.bat"
)

foreach ($name in $launchers) {
    $source = Join-Path $WindowsScripts $name
    $destination = Join-Path $Desktop $name
    Copy-Item $source $destination -Force
    Write-Host "Instalado: $destination" -ForegroundColor Green
}

Write-Host ""
Write-Host "Atalhos do Segundo Cerebro atualizados na Area de Trabalho." -ForegroundColor Cyan
