# Backup local do Segundo Cerebro - Windows
$ErrorActionPreference = "Stop"

$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$BackupScript = Join-Path $ProjectDir "scripts\common\backup_segundo_cerebro.py"
$BackupDir = Join-Path $HOME "Segundo Cerebro Backups"

Set-Location $ProjectDir

if (-not (Test-Path $Python)) {
    Write-Host "ERRO: ambiente virtual nao encontrado." -ForegroundColor Red
    Write-Host $Python
    Read-Host "Pressione Enter para sair"
    exit 1
}

Write-Host ""
Write-Host "Backup do Segundo Cerebro" -ForegroundColor Cyan
Write-Host "Destino: $BackupDir"
Write-Host ""

& $Python $BackupScript
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "O backup falhou." -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Abrindo pasta de backups..." -ForegroundColor Green
Start-Process explorer.exe $BackupDir
Start-Sleep -Seconds 2
