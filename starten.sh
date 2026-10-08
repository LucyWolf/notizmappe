#!/usr/bin/env bash
# Startet die Notizmappe. Datenordner ueber NOTIZEN_ORDNER, sonst ~/Notizen.
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
exec env PYTHONPATH=app "$PY" -m uvicorn main:app \
  --host "${HOST:-127.0.0.1}" --port "${PORT:-8099}" --app-dir app "$@"
