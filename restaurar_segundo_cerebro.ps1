# Restauracao do Segundo Cerebro a partir de um backup ZIP
$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$RestoreScript = Join-Path $ProjectDir "restaurar_segundo_cerebro.py"

Set-Location $ProjectDir

if (-not (Test-Path $Python)) {
    Write-Host "ERRO: ambiente virtual nao encontrado." -ForegroundColor Red
    Write-Host "Configure o projeto primeiro e depois rode a restauracao." -ForegroundColor Yellow
    Read-Host "Pressione Enter para sair"
    exit 1
}

Add-Type -AssemblyName System.Windows.Forms

$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = "Escolha o backup do Segundo Cerebro"
$dialog.Filter = "Backup ZIP (*.zip)|*.zip|Todos os arquivos (*.*)|*.*"
$dialog.Multiselect = $false

if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
    exit 0
}

$BackupZip = $dialog.FileName

Write-Host ""
Write-Host "Restaurando Segundo Cerebro" -ForegroundColor Cyan
Write-Host "Backup: $BackupZip"
Write-Host ""
Write-Host "IMPORTANTE: feche o servidor e o worker antes de restaurar." -ForegroundColor Yellow
$confirm = Read-Host "Digite SIM para continuar"
if ($confirm -ne "SIM") {
    Write-Host "Restauracao cancelada."
    exit 0
}

& $Python $RestoreScript $BackupZip
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "A restauracao falhou." -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Aplicando migrations do projeto atual..." -ForegroundColor Yellow
& $Python manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) {
    Write-Host "O banco foi restaurado, mas houve erro ao aplicar migrations." -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Restauracao concluida." -ForegroundColor Green
Write-Host "Agora voce pode abrir o Segundo Cerebro normalmente."
Read-Host "Pressione Enter para fechar"
