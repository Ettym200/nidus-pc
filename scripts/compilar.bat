@echo off
chcp 65001 >nul
title Nidus - Compilando...
cd /d "%~dp0\.."

echo.
echo  ================================
echo   Compilando Nidus
echo  ================================
echo.

pip install -r requirements.txt pyinstaller >nul 2>&1

echo  Convertendo icone...
python scripts\build_icon.py

echo  Gerando executavel...
echo.

set "EXTRA_DATA=--add-data assets\icon.png;assets --add-data assets\icon.ico;assets"
if exist assets\code.jpeg set "EXTRA_DATA=%EXTRA_DATA% --add-data assets\code.jpeg;assets"
REM UI web (pywebview) precisa ir dentro do exe
set "EXTRA_DATA=%EXTRA_DATA% --add-data src\ui\web;src\ui\web"

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
  --hidden-import webview ^
  --hidden-import webview.platforms.edgechromium ^
  --hidden-import bottle ^
  --hidden-import proxy_tools ^
  --hidden-import clr_loader ^
  --hidden-import pythonnet ^
  --hidden-import src.capture ^
  --hidden-import src.translator ^
  --hidden-import src.overlay ^
  --hidden-import src.ui_theme ^
  --hidden-import src.updater ^
  --hidden-import src.audio_pipeline ^
  --hidden-import src.audio_capture ^
  --hidden-import src.audio_capture_linux ^
  --hidden-import src.app_audio_capture ^
  --hidden-import src.audio_sources ^
  --hidden-import src.hotkeys ^
  --hidden-import src.speech_to_text ^
  --hidden-import src.vad_processor ^
  --hidden-import src.interview_buffer ^
  --hidden-import src.text_sanitize ^
  --hidden-import src.debug_log ^
  --hidden-import src.ui.window ^
  --hidden-import src.ui.controller ^
  --hidden-import src.ui.config_store ^
  --hidden-import src.ui.region_selector ^
  --hidden-import faster_whisper ^
  --hidden-import pyaudiowpatch ^
  --collect-all webview ^
  --collect-all mss ^
  --collect-all faster_whisper ^
  main.py

echo.
if exist "dist\Nidus.exe" (
    echo  ================================
    echo   Sucesso!
    echo   Arquivo: dist\Nidus.exe
    echo   Esse e o arquivo para distribuir.
    echo.
    echo   Requisito no PC do usuario:
    echo   Microsoft Edge WebView2 Runtime
    echo   ^(ja vem no Windows 10/11 atualizado^)
    echo  ================================
) else (
    echo  [ERRO] Compilacao falhou.
)
echo.
pause
