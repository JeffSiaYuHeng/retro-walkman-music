#!/usr/bin/env bash
set -euo pipefail

# Run from repo root: starts the Flask app (app.py) and an ngrok tunnel to 127.0.0.1:5169.
cd "$(dirname "$0")"

if ! command -v ngrok >/dev/null 2>&1; then
  echo "ngrok not found. Install and authenticate: https://ngrok.com/download"
  exit 1
fi

echo "Starting Flask app (app.py) on port 5169..."
python app.py >/dev/null 2>&1 &
APP_PID=$!

trap 'echo "Stopping Flask..."; kill "$APP_PID" 2>/dev/null || true' EXIT

echo "Starting ngrok tunnel to 127.0.0.1:5169 (avoid IPv6 ::1)..."
ngrok http 127.0.0.1:5169

echo "ngrok exited; stopping Flask (if running)"
