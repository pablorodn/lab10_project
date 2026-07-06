#!/usr/bin/env bash
# Levanta el servidor de desarrollo (uvicorn) en background.
# Uso: scripts/start_server.sh [puerto]

set -euo pipefail

PORT="${1:-8000}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="${ROOT_DIR}/.server.log"

cd "$ROOT_DIR"

# Corta cualquier instancia previa en ese puerto antes de arrancar.
"${ROOT_DIR}/scripts/stop_server.sh" "$PORT" >/dev/null 2>&1 || true

echo "Iniciando uvicorn en 127.0.0.1:${PORT} (log: ${LOG_FILE})..."
nohup uv run uvicorn app.main:app --port "$PORT" --host 127.0.0.1 &> "$LOG_FILE" &
disown

for i in $(seq 1 30); do
  if curl -sf -o /dev/null "http://127.0.0.1:${PORT}/login"; then
    echo "Servidor arriba en http://127.0.0.1:${PORT} (tardó ${i}s)"
    exit 0
  fi
  sleep 1
done

echo "El servidor no respondió tras 30s. Revisá ${LOG_FILE}:" >&2
tail -n 30 "$LOG_FILE" >&2
exit 1
