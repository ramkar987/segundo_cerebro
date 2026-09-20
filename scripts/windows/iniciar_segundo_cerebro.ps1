# Segundo Cerebro - inicializador local para Windows
$ErrorActionPreference = "Stop"

$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
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

$Shell = if (Get-Command pwsh.exe -ErrorAction SilentlyContinue) { "pwsh.exe" } else { "powershell.exe" }
$ServerCommand = "& '$Python' manage.py runserver"
$WorkerCommand = "& '$Python' manage.py process_jobs"

if (Get-Command wt.exe -ErrorAction SilentlyContinue) {
    Write-Host "Abrindo Windows Terminal com duas abas..." -ForegroundColor Green

    $wtArgs = @(
        "new-tab",
        "--title", "Segundo Cerebro - Site",
        "-d", $ProjectDir,
        $Shell, "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-Command", $ServerCommand,
        ";",
        "new-tab",
        "--title", "Segundo Cerebro - Worker",
        "-d", $ProjectDir,
        $Shell, "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-Command", $WorkerCommand
    )
    & wt.exe @wtArgs
}
else {
    Write-Host "Windows Terminal nao encontrado. Abrindo duas janelas..." -ForegroundColor Yellow
    Start-Process $Shell -ArgumentList @(
        "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-Command", "Set-Location '$ProjectDir'; $ServerCommand"
    )
    Start-Process $Shell -ArgumentList @(
        "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-Command", "Set-Location '$ProjectDir'; $WorkerCommand"
    )
}

$url = "http://127.0.0.1:8000/"
Write-Host "Aguardando o servidor ficar pronto..." -ForegroundColor Yellow

$serverReady = $false
for ($i = 1; $i -le 40; $i++) {
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
            $serverReady = $true
            break
        }
    }
    catch {
        Start-Sleep -Milliseconds 500
    }
}

if ($serverReady) {
    Write-Host "Servidor pronto. Abrindo $url" -ForegroundColor Cyan
    Start-Process $url
}
else {
    Write-Host "O servidor ainda nao respondeu." -ForegroundColor Red
    Write-Host "Verifique a aba 'Segundo Cerebro - Site'." -ForegroundColor Yellow
}

Start-Sleep -Seconds 2
