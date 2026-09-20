@echo off
title Restaurar Segundo Cerebro

if defined SEGUNDO_CEREBRO_DIR (
    set "PROJECT_DIR=%SEGUNDO_CEREBRO_DIR%"
) else (
    set "PROJECT_DIR=%USERPROFILE%\segundo_cerebro"
)

if not exist "%PROJECT_DIR%\scripts\windows\restaurar_segundo_cerebro.ps1" (
    echo ERRO: Segundo Cerebro nao encontrado em:
    echo %PROJECT_DIR%
    pause
    exit /b 1
)

where pwsh.exe >nul 2>&1
if %errorlevel%==0 (
    pwsh.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%\scripts\windows\restaurar_segundo_cerebro.ps1"
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%\scripts\windows\restaurar_segundo_cerebro.ps1"
)

exit
