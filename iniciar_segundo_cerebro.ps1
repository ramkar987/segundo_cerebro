# Segundo Cérebro - inicializador local
# Inicia servidor Django + worker em duas abas do Windows Terminal e abre o navegador.

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"

Set-Location $ProjectDir

if (-not (Test-Path $Python)) {
    Write-Host ""
    Write-Host "Ambiente virtual nao encontrado em:" -ForegroundColor Red
    Write-Host "  $Python"
    Write-Host ""
    Write-Host "Crie o ambiente primeiro com:" -ForegroundColor Yellow
    Write-Host "  py -m venv .venv"
    Write-Host "  .venv\Scripts\Activate.ps1"
    Write-Host "  pip install -r requirements.txt"
    Write-Host ""
    Read-Host "Pressione Enter para sair"
    exit 1
}

Write-Host "Segundo Cerebro" -ForegroundColor Cyan
Write-Host "Projeto: $ProjectDir"
Write-Host ""

Write-Host "Aplicando migrations pendentes..." -ForegroundColor Yellow
& $Python manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) {
    Write-Host "Falha ao aplicar migrations." -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
    exit $LASTEXITCODE
}

$Shell = if (Get-Command pwsh.exe -ErrorAction SilentlyContinue) {
    "pwsh.exe"
} else {
    "powershell.exe"
}

$ServerCommand = "& '$Python' manage.py runserver"
$WorkerCommand = "& '$Python' manage.py process_jobs"

if (Get-Command wt.exe -ErrorAction SilentlyContinue) {
    Write-Host "Abrindo Windows Terminal com duas abas..." -ForegroundColor Green

    $wtArgs = @(
        "new-tab",
        "--title", "Segundo Cerebro - Site",
        "-d", $ProjectDir,
        $Shell,
        "-NoExit",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command", $ServerCommand,
        ";",
        "new-tab",
        "--title", "Segundo Cerebro - Worker",
        "-d", $ProjectDir,
        $Shell,
        "-NoExit",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command", $WorkerCommand
    )

    Start-Process wt.exe -ArgumentList $wtArgs
} else {
    Write-Host "Windows Terminal nao encontrado. Abrindo duas janelas do PowerShell..." -ForegroundColor Yellow

    Start-Process $Shell -ArgumentList @(
        "-NoExit",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command", "Set-Location '$ProjectDir'; $ServerCommand"
    )

    Start-Process $Shell -ArgumentList @(
        "-NoExit",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command", "Set-Location '$ProjectDir'; $WorkerCommand"
    )
}

Write-Host "Aguardando o servidor iniciar..." -ForegroundColor Yellow
Start-Sleep -Seconds 2

$url = "http://127.0.0.1:8000/"
Write-Host "Abrindo $url" -ForegroundColor Cyan
Start-Process $url

Write-Host ""
Write-Host "Pronto." -ForegroundColor Green
Write-Host "Site e worker foram iniciados."
Start-Sleep -Seconds 2
