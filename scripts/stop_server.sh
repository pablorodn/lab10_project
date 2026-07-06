#!/usr/bin/env bash
# Mata el servidor de desarrollo (uvicorn) y libera el puerto, incluyendo
# procesos huérfanos que hayan quedado escuchando en él.
# Uso: scripts/stop_server.sh [puerto]

set -uo pipefail

PORT="${1:-8000}"

# 1) Matar por patrón de comando (cubre el proceso normal de uvicorn).
pkill -f "uvicorn app.main:app" 2>/dev/null && echo "Proceso uvicorn (por nombre) terminado."

# 2) Matar cualquier proceso que siga escuchando en el puerto (huérfanos,
#    workers hijos, u otra instancia lanzada de forma distinta).
PIDS="$(lsof -ti "tcp:${PORT}" -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$PIDS" ]; then
  echo "Liberando puerto ${PORT} (PIDs: ${PIDS})..."
  # shellcheck disable=SC2086
  kill $PIDS 2>/dev/null
  sleep 1
  # Si alguno sigue vivo, forzar.
  PIDS_LEFT="$(lsof -ti "tcp:${PORT}" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$PIDS_LEFT" ]; then
    # shellcheck disable=SC2086
    kill -9 $PIDS_LEFT 2>/dev/null
  fi
fi

if lsof -ti "tcp:${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Puerto ${PORT} sigue ocupado, revisar manualmente." >&2
  exit 1
fi

echo "Puerto ${PORT} libre."
