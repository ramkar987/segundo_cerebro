# Segundo Cérebro - inicializador local
# Inicia o servidor Django, o worker e abre o navegador.

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

$ServerCommand = @"
Set-Location '$ProjectDir'
& '$Python' manage.py runserver
"@

$WorkerCommand = @"
Set-Location '$ProjectDir'
& '$Python' manage.py process_jobs
"@

Write-Host "Abrindo servidor Django..." -ForegroundColor Green
Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command", $ServerCommand
)

Write-Host "Abrindo worker..." -ForegroundColor Green
Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command", $WorkerCommand
)

Write-Host "Aguardando o servidor iniciar..." -ForegroundColor Yellow
Start-Sleep -Seconds 2

$url = "http://127.0.0.1:8000/"
Write-Host "Abrindo $url" -ForegroundColor Cyan
Start-Process $url

Write-Host ""
Write-Host "Pronto." -ForegroundColor Green
Write-Host "Pode fechar esta janela. Deixe abertas as janelas do servidor e do worker."
Start-Sleep -Seconds 2
