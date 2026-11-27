@echo off
rem Double-click: start EventLens (live data). A browser tab opens; close this window to stop.
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
set PYTHONUTF8=1
python -m walletlens app
