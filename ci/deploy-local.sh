#!/usr/bin/env bash
# Local CD: if Django is not already healthy on :8000, start runserver with real settings.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${BACKEND_PORT:-8000}"
URL="http://127.0.0.1:${PORT}/api/v1/health/"
RUN_DIR="$ROOT/.local-run"
mkdir -p "$RUN_DIR"

if curl -sf --max-time 2 "$URL" >/dev/null; then
  echo "==> [backend] already healthy at $URL"
  exit 0
fi

if [[ -x .venv/bin/python ]]; then
  PYTHON=.venv/bin/python
elif [[ -x venv/bin/python ]]; then
  PYTHON=venv/bin/python
else
  PYTHON="${PYTHON:-python3}"
fi

unset DJANGO_SETTINGS_MODULE
export DJANGO_SETTINGS_MODULE=jeepath.settings

echo "==> [backend] starting runserver on :${PORT}"
nohup "$PYTHON" manage.py runserver "127.0.0.1:${PORT}" \
  >"$RUN_DIR/backend.log" 2>&1 &
echo $! >"$RUN_DIR/backend.pid"

for _ in $(seq 1 40); do
  if curl -sf --max-time 1 "$URL" >/dev/null; then
    echo "==> [backend] healthy at $URL (pid $(cat "$RUN_DIR/backend.pid"))"
    exit 0
  fi
  sleep 1
done

echo "backend failed to become healthy. Last log:" >&2
tail -n 40 "$RUN_DIR/backend.log" >&2
exit 1
