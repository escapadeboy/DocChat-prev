# Starts the support bot for local development in three separate windows:
#   1. Backend API      http://localhost:5003
#   2. Voice agent      LiveKit worker "support-agent"
#   3. Frontend         http://localhost:5173
# Usage: right-click this file -> "Run with PowerShell", or run .\start_dev.ps1 from this folder.

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = Join-Path $backend "venv\Scripts\python.exe"

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backend'; `$host.UI.RawUI.WindowTitle = 'Backend API'; & '$python' -m uvicorn app.main:app --reload --port 5003"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backend'; `$host.UI.RawUI.WindowTitle = 'Voice agent'; `$env:PYTHONIOENCODING = 'utf-8'; & '$python' -m voice_agent.agent dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$frontend'; `$host.UI.RawUI.WindowTitle = 'Frontend'; npm run dev"

Write-Host "Starting... open http://localhost:5173 in a few seconds (login 9876543210 / Test123456!@)"
Start-Sleep -Seconds 6
Start-Process "http://localhost:5173/support"
