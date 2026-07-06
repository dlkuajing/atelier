#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR/.."

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
PYTHONUTF8="${PYTHONUTF8:-1}"
export PYTHONUTF8

if [ ! -f ".env" ]; then
  echo "Missing .env file." >&2
  echo "Create .env from .env.example and set OPENAI_API_KEY before starting the demo." >&2
  exit 1
fi

if ! awk -F= '
  /^[[:space:]]*(#|$)/ { next }
  {
    key = $1
    sub(/^[[:space:]]*export[[:space:]]+/, "", key)
    gsub(/[[:space:]]+$/, "", key)
    if (key == "OPENAI_API_KEY") {
      value = $0
      sub(/^[^=]*=/, "", value)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      if (value != "") found = 1
    }
  }
  END { exit found ? 0 : 1 }
' .env; then
  echo "OPENAI_API_KEY is missing or empty in .env." >&2
  echo "Edit .env and set OPENAI_API_KEY before starting the demo." >&2
  exit 1
fi

if [ -x ".venv/bin/python" ]; then
  PYTHON_EXE=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then
  PYTHON_EXE=".venv/Scripts/python.exe"
else
  PYTHON_EXE="python"
fi

echo "Starting Atelier demo at http://$HOST:$PORT"
exec "$PYTHON_EXE" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
