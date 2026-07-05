#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR/.."

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
PYTHONUTF8="${PYTHONUTF8:-1}"
export PYTHONUTF8

if [ -x ".venv/bin/python" ]; then
  PYTHON_EXE=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then
  PYTHON_EXE=".venv/Scripts/python.exe"
else
  PYTHON_EXE="python"
fi

echo "Starting Atelier demo at http://$HOST:$PORT"
exec "$PYTHON_EXE" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
