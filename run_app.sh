#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[ERROR] .env file not found at project root."
  exit 1
fi

if ! grep -q '^OPENAI_API_KEY=' "$ENV_FILE"; then
  echo "[ERROR] OPENAI_API_KEY is missing in .env."
  exit 1
fi

if [[ ! -f "$ROOT_DIR/venv/bin/activate" ]]; then
  echo "[ERROR] venv not found. Please create it with: python -m venv venv"
  exit 1
fi

echo "Starting backend..."
cd "$ROOT_DIR"
source "$ROOT_DIR/venv/bin/activate"
python -m pip install -r requirements.txt

(
  cd "$ROOT_DIR/frontend"
  npm install
  npm run dev
) &

(
  cd "$ROOT_DIR"
  source "$ROOT_DIR/venv/bin/activate"
  uvicorn main:app --reload --port 8000
) &

echo "System Live! Access Frontend at http://localhost:5173 and Backend Docs at http://localhost:8000/docs"
wait
