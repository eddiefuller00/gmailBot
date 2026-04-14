#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "Missing .venv. Create it with: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

if [[ ! -d "frontend/node_modules" ]]; then
  echo "Frontend deps missing. Install with: cd frontend && npm install"
  exit 1
fi

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

source .venv/bin/activate
python -m uvicorn app.main:app --reload &
BACKEND_PID=$!

(
  cd frontend
  npm run dev
) &
FRONTEND_PID=$!

while true; do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    wait "$BACKEND_PID" 2>/dev/null || true
    exit 1
  fi
  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    wait "$FRONTEND_PID" 2>/dev/null || true
    exit 1
  fi
  sleep 1
done
