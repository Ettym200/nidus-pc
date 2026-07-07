@echo off
chcp 65001 >nul
title Nidus - Debug (com logs)
cd /d "%~dp0\.."

echo.
echo  ================================
echo   Nidus - Modo Debug
echo   Logs visiveis nesta janela
echo  ================================
echo.

set NIDUS_DEBUG=1
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
python -u main.py --debug 2>&1

echo.
echo  [Nidus encerrado]
pause
