@echo off
chcp 65001 >nul
title Game Translator - Instalador
cd /d "%~dp0"

echo.
echo  ================================
echo   Game Translator - Instalando
echo  ================================
echo.

:: Detecta o Python disponível
set PYTHON=
python --version >nul 2>&1
if %errorlevel% == 0 set PYTHON=python

if "%PYTHON%"=="" (
    python3 --version >nul 2>&1
    if %errorlevel% == 0 set PYTHON=python3
)

if "%PYTHON%"=="" (
    echo  [ERRO] Python nao encontrado!
    echo.
    echo  Instale em: https://www.python.org/downloads/
    echo  IMPORTANTE: Marque "Add Python to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

echo  [OK] Python encontrado: %PYTHON%
echo.
echo  Instalando dependencias...
echo.

%PYTHON% -m pip install mss Pillow numpy openai anthropic keyboard

echo.
echo  ================================
echo   Instalacao concluida!
echo   Execute: iniciar.bat
echo  ================================
echo.
pause
