@echo off
REM Run from repo root: starts the Flask app (app.py) and an ngrok tunnel to port 5169.
cd /d %~dp0

where ngrok >nul 2>&1
if errorlevel 1 (
  echo ngrok not found. Install and authenticate: https://ngrok.com/download
  exit /b 1
)

echo Starting Flask app (app.py) on port 5169...
start "" /b py app.py

echo Starting ngrok tunnel to 127.0.0.1:5169 (avoid IPv6 ::1)...
ngrok http 127.0.0.1:5169

echo ngrok exited. If the Python process is still running, stop it manually.
