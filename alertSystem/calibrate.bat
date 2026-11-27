@echo off
rem Double-click: D7 live calibration of the early warning (about 1 minute).
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
set PYTHONUTF8=1
python -m walletlens calibrate
