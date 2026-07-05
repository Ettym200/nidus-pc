#!/bin/bash
cd "$(dirname "$0")/.."

# Instala dependências se necessário
pip install -r requirements.txt -q

# Roda como sudo para hotkeys globais funcionarem
if [ "$EUID" -ne 0 ]; then
    echo "Solicitando permissão para hotkeys globais..."
    sudo python3 main.py
else
    python3 main.py
fi
