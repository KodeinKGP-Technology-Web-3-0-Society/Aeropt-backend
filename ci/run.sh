#!/usr/bin/env bash
# Local + GitHub CI for Aeropt-backend. Uses sqlite (prepwise.ci_settings), not live Postgres.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -x .venv/bin/python ]]; then
  PYTHON=.venv/bin/python
elif [[ -x venv/bin/python ]]; then
  PYTHON=venv/bin/python
else
  PYTHON="${PYTHON:-python3}"
fi

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-prepwise.ci_settings}"

echo "==> [backend] syntax"
"$PYTHON" -m compileall -q -x '(\.venv|venv)' \
  prepwise users apis analytics roadmap sandbox classroom manage.py

echo "==> [backend] django check"
"$PYTHON" manage.py check

echo "==> [backend] tests"
"$PYTHON" manage.py test --verbosity=1

echo "==> [backend] CI passed"
