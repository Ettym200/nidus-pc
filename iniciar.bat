@echo off
chcp 65001 >nul
title Game Translator
cd /d "%~dp0"

:: Garante dependencias instaladas
python -m pip install mss Pillow numpy openai anthropic keyboard >nul 2>&1

:: Tenta python, depois python3
python --version >nul 2>&1
if %errorlevel% == 0 (
    python main.py
    goto :check
)

python3 --version >nul 2>&1
if %errorlevel% == 0 (
    python3 main.py
    goto :check
)

echo.
echo  [ERRO] Python nao encontrado!
echo  Instale em: https://www.python.org/downloads/
echo  Marque "Add Python to PATH" durante a instalacao.
echo.
pause
exit /b 1

:check
if errorlevel 1 (
    echo.
    echo  Ocorreu um erro ao iniciar o app.
    echo  Execute instalar.bat primeiro e tente novamente.
    echo.
    pause
)
