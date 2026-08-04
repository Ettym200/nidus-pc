#!/usr/bin/env bash
# Instala deps de sistema + Python para Nidus no Linux.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "================================"
echo " Instalando Nidus (Linux)"
echo "================================"

if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y \
    python3 python3-pip python3-venv \
    python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
    gir1.2-webkit2-4.1 || sudo apt-get install -y gir1.2-webkit2-4.0 || true
  sudo apt-get install -y pulseaudio-utils pipewire-pulse || true
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y python3 python3-pip python3-gobject gtk3 webkit2gtk4.1 || true
elif command -v pacman >/dev/null 2>&1; then
  sudo pacman -S --needed --noconfirm python python-pip python-gobject gtk3 webkit2gtk || true
fi

python3 -m pip install -U pip
python3 -m pip install -r requirements.txt

echo ""
echo "Pronto. Rode: bash scripts/iniciar.sh"
