@echo off
title Segundo Cerebro

cd /d "C:\Users\antonio.pinheiro\segundo_cerebro"

where pwsh.exe >nul 2>&1
if %errorlevel%==0 (
    start "" /min pwsh.exe -NoProfile -ExecutionPolicy Bypass -File ".\iniciar_segundo_cerebro.ps1"
) else (
    start "" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\iniciar_segundo_cerebro.ps1"
)

exit
