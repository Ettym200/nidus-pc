@echo off
chcp 65001 >nul
title Nidus - Instalador
cd /d "%~dp0\.."

echo.
echo  ================================
echo   Nidus - Instalador
echo  ================================
echo.

:: Verifica se Python já está instalado
python --version >nul 2>&1
if %errorlevel% == 0 (
    echo  [OK] Python ja esta instalado.
    goto :instalar_deps
)

python3 --version >nul 2>&1
if %errorlevel% == 0 (
    set PYTHON=python3
    echo  [OK] Python ja esta instalado.
    goto :instalar_deps
)

:: Python não encontrado — baixa e instala automaticamente
echo  [!] Python nao encontrado. Baixando instalador...
echo.

:: Baixa o instalador do Python 3.12
powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe' -OutFile '%TEMP%\python_installer.exe'"

if not exist "%TEMP%\python_installer.exe" (
    echo.
    echo  [ERRO] Nao foi possivel baixar o Python.
    echo  Instale manualmente em: https://www.python.org/downloads/
    echo  Marque "Add Python to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

echo.
echo  Instalando Python (isso pode demorar alguns minutos)...
echo  AGUARDE — nao feche esta janela.
echo.

:: Instala silenciosamente com PATH configurado
"%TEMP%\python_installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1

:: Aguarda um momento para o PATH ser atualizado
timeout /t 3 >nul

:: Atualiza o PATH desta sessão
for /f "tokens=*" %%i in ('powershell -Command "[System.Environment]::GetEnvironmentVariable(\"PATH\", \"User\")"') do set PATH=%%i;%PATH%

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [!] Python instalado mas precisa reiniciar o terminal.
    echo  Feche esta janela e execute instalar.bat novamente.
    echo.
    pause
    exit /b 1
)

echo  [OK] Python instalado com sucesso!
echo.

:instalar_deps
echo  Instalando dependencias do app...
echo.

python -m pip install --upgrade pip --quiet
python -m pip install mss Pillow numpy openai anthropic customtkinter keyboard mouse

if %errorlevel% neq 0 (
    echo.
    echo  [ERRO] Falha ao instalar dependencias.
    echo  Tente rodar este arquivo como Administrador.
    echo.
    pause
    exit /b 1
)

:: Limpa instalador baixado
if exist "%TEMP%\python_installer.exe" del "%TEMP%\python_installer.exe"

echo.
echo  ================================
echo   Tudo pronto!
echo   Execute: scripts\iniciar.bat
echo  ================================
echo.
pause
