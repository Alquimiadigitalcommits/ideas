#!/usr/bin/env bash
# Modo desarrollo: backend con recarga automática (8765) + Vite (5173, con proxy /api).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
python -m uvicorn app.main:app --reload --port 8765 &
BACK=$!
trap 'kill $BACK' EXIT
cd "$ROOT/frontend"
npm run dev
