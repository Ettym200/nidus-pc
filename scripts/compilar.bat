@echo off
chcp 65001 >nul
title Nidus - Compilando...
cd /d "%~dp0\.."

echo.
echo  ================================
echo   Compilando Nidus
echo  ================================
echo.

pip install pyinstaller >nul 2>&1

echo  Convertendo icone...
python scripts\build_icon.py

echo  Gerando executavel...
echo.

set "EXTRA_DATA=--add-data assets\icon.png;assets --add-data assets\icon.ico;assets"
if exist assets\code.jpeg set "EXTRA_DATA=%EXTRA_DATA% --add-data assets\code.jpeg;assets"

python -m PyInstaller --noconfirm --onefile --windowed ^
  --name "Nidus" ^
  --icon "assets\icon.ico" ^
  %EXTRA_DATA% ^
  --hidden-import PIL ^
  --hidden-import PIL.ImageTk ^
  --hidden-import mss ^
  --hidden-import openai ^
  --hidden-import anthropic ^
  --hidden-import keyboard ^
  --hidden-import mouse ^
  --hidden-import customtkinter ^
  --hidden-import src.capture ^
  --hidden-import src.translator ^
  --hidden-import src.overlay ^
  --hidden-import src.ui_theme ^
  --hidden-import src.updater ^
  --collect-all customtkinter ^
  --collect-all mss ^
  main.py

echo.
if exist "dist\Nidus.exe" (
    echo  ================================
    echo   Sucesso!
    echo   Arquivo: dist\Nidus.exe
    echo   Esse e o arquivo para distribuir.
    echo  ================================
) else (
    echo  [ERRO] Compilacao falhou.
)
echo.
pause
