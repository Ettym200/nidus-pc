@echo off
chcp 65001 >nul
title Nidus - Compilando...

echo.
echo  ================================
echo   Compilando Nidus
echo  ================================
echo.

pip install pyinstaller >nul 2>&1

echo  Convertendo icone...
python build_icon.py

echo  Gerando executavel...
echo.

python -m PyInstaller --noconfirm --onefile --windowed ^
  --name "Nidus" ^
  --icon "icon.ico" ^
  --add-data "code.jpeg;." ^
  --add-data "icon.png;." ^
  --add-data "icon.ico;." ^
  --hidden-import PIL ^
  --hidden-import PIL.ImageTk ^
  --hidden-import mss ^
  --hidden-import openai ^
  --hidden-import anthropic ^
  --hidden-import keyboard ^
  --hidden-import mouse ^
  --hidden-import customtkinter ^
  --collect-all customtkinter ^
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
