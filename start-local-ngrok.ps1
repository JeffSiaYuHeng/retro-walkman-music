#!/usr/bin/env pwsh
Set-StrictMode -Version Latest

# Run from repo root: starts the Flask app (app.py) and an ngrok tunnel to port 5169.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    Write-Error "ngrok not found. Install and authenticate: https://ngrok.com/download"
    exit 1
}

Write-Output "Starting Flask app (app.py) on port 5169..."
$pythonCmd = if (Get-Command python -ErrorAction SilentlyContinue) { 'python' } else { 'py' }
$proc = Start-Process -FilePath $pythonCmd -ArgumentList 'app.py' -WorkingDirectory $scriptDir -PassThru

try {
    Write-Output "Starting ngrok tunnel to 127.0.0.1:5169 (avoid IPv6 ::1)..."
    & ngrok http 127.0.0.1:5169
} finally {
    if ($proc -and -not $proc.HasExited) {
        Write-Output "Stopping Flask (PID $($proc.Id))..."
        try { $proc.Kill() } catch { }
    }
}
