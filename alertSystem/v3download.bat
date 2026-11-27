@echo off
rem V3: download sector volatility gauges (OVX, GVZ, MOVE, VXFXI, VXN, VIX) to data\raw\vol_gauges.csv
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
set PYTHONUTF8=1
python scripts\v3_download.py
pause
