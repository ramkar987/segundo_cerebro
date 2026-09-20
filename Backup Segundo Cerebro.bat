@echo off
title Backup Segundo Cerebro

cd /d "C:\Users\antonio.pinheiro\segundo_cerebro"

where pwsh.exe >nul 2>&1
if %errorlevel%==0 (
    pwsh.exe -NoProfile -ExecutionPolicy Bypass -File ".\backup_segundo_cerebro.ps1"
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\backup_segundo_cerebro.ps1"
)

exit
