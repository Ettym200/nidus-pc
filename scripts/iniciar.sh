#!/usr/bin/env bash
# Inicia o Nidus no Linux (sem sudo — sudo quebra o áudio do usuário no Pulse/PipeWire).
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pip install -r requirements.txt -q

ARGS=()
if [[ "${1:-}" == "--debug" ]] || [[ "${NIDUS_DEBUG:-}" == "1" ]]; then
  ARGS+=(--debug)
fi

echo "Iniciando Nidus (Linux)..."
echo "  Live: captura o áudio do sistema (PulseAudio/PipeWire)"
echo "  App específico: disponível só no Windows por enquanto"
echo ""
exec python3 main.py "${ARGS[@]:-}"
