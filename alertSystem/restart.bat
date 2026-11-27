@echo off
rem Double-click: stop the running EventLens server (if any) and start it again with the newest code.
cd /d "%~dp0"
curl -s -X POST http://127.0.0.1:8765/api/shutdown >nul 2>&1
timeout /t 3 /nobreak >nul
set PYTHONPATH=%~dp0src
set PYTHONUTF8=1
python -m walletlens app
