#!/usr/bin/env bash
# Compila Nidus para Linux (onefile) com PyInstaller.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "================================"
echo " Compilando Nidus (Linux)"
echo "================================"
echo ""

python3 -m pip install -r requirements.txt pyinstaller -q
python3 scripts/build_icon.py || true

EXTRA_DATA=(
  --add-data "assets/icon.png:assets"
  --add-data "src/ui/web:src/ui/web"
)
if [[ -f assets/icon.ico ]]; then
  EXTRA_DATA+=(--add-data "assets/icon.ico:assets")
fi
if [[ -f assets/code.jpeg ]]; then
  EXTRA_DATA+=(--add-data "assets/code.jpeg:assets")
fi

python3 -m PyInstaller --noconfirm --onefile --windowed \
  --name "Nidus-linux" \
  "${EXTRA_DATA[@]}" \
  --hidden-import PIL \
  --hidden-import mss \
  --hidden-import openai \
  --hidden-import anthropic \
  --hidden-import webview \
  --hidden-import bottle \
  --hidden-import soundcard \
  --hidden-import pynput \
  --hidden-import src.capture \
  --hidden-import src.translator \
  --hidden-import src.overlay \
  --hidden-import src.ui_theme \
  --hidden-import src.updater \
  --hidden-import src.audio_pipeline \
  --hidden-import src.audio_capture \
  --hidden-import src.audio_capture_linux \
  --hidden-import src.audio_sources \
  --hidden-import src.hotkeys \
  --hidden-import src.speech_to_text \
  --hidden-import src.vad_processor \
  --hidden-import src.interview_buffer \
  --hidden-import src.text_sanitize \
  --hidden-import src.debug_log \
  --hidden-import src.ui.window \
  --hidden-import src.ui.controller \
  --hidden-import src.ui.config_store \
  --hidden-import src.ui.region_selector \
  --hidden-import faster_whisper \
  --collect-all webview \
  --collect-all mss \
  --collect-all faster_whisper \
  --collect-all soundcard \
  main.py

echo ""
if [[ -f dist/Nidus-linux ]]; then
  chmod +x dist/Nidus-linux
  echo "================================"
  echo " Sucesso!"
  echo " Arquivo: dist/Nidus-linux"
  echo ""
  echo " Dependencias de sistema recomendadas:"
  echo "   - PulseAudio ou PipeWire"
  echo "   - webkit2gtk / gir1.2-webkit2 (pywebview)"
  echo "================================"
else
  echo "[ERRO] Compilacao falhou."
  exit 1
fi
